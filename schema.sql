-- =============================================================================
-- Nistula Unified Messaging Platform — PostgreSQL Schema
-- =============================================================================
-- Design principles:
--   • One guest record across all channels (matched via booking_ref or phone/email)
--   • Full audit trail: every AI decision is stored and reviewable
--   • Soft-delete everywhere (deleted_at) — never destroy guest data
--   • TIMESTAMPTZ throughout — timezone-safe for international guests
-- =============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- ─────────────────────────────────────────────────────────────────────────────
-- PROPERTIES
-- Separate table so schema can scale to multiple villas
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE properties (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_code   TEXT UNIQUE NOT NULL,           -- e.g. "villa-b1"
    display_name    TEXT NOT NULL,
    location        TEXT,
    max_guests      INT,
    bedrooms        INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ                     -- soft delete
);


-- ─────────────────────────────────────────────────────────────────────────────
-- GUESTS
-- One record per unique human guest, merged across channels.
-- Matching strategy: booking_ref first, then phone/email.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE guests (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name       TEXT NOT NULL,
    primary_email   TEXT,
    primary_phone   TEXT,
    -- Canonical channel identifiers (for deduplication)
    whatsapp_id     TEXT UNIQUE,
    airbnb_user_id  TEXT UNIQUE,
    booking_com_id  TEXT UNIQUE,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes           TEXT,
    deleted_at      TIMESTAMPTZ,

    CONSTRAINT guests_contact_check
        CHECK (primary_email IS NOT NULL OR primary_phone IS NOT NULL
               OR whatsapp_id IS NOT NULL)
);

CREATE INDEX idx_guests_email ON guests(primary_email) WHERE primary_email IS NOT NULL;
CREATE INDEX idx_guests_phone ON guests(primary_phone) WHERE primary_phone IS NOT NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- RESERVATIONS
-- A booking tied to a guest and a property.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE reservations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    guest_id        UUID NOT NULL REFERENCES guests(id) ON DELETE RESTRICT,
    property_id     UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
    booking_ref     TEXT UNIQUE NOT NULL,           -- e.g. "NIS-2024-0891"
    source          TEXT NOT NULL CHECK (source IN
                        ('whatsapp','booking_com','airbnb','instagram','direct')),
    check_in        DATE,
    check_out       DATE,
    num_guests      INT,
    total_amount    NUMERIC(12, 2),
    currency        CHAR(3) DEFAULT 'INR',
    status          TEXT NOT NULL DEFAULT 'confirmed'
                        CHECK (status IN ('enquiry','confirmed','cancelled','completed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,

    CONSTRAINT check_dates CHECK (check_out > check_in)
);

CREATE INDEX idx_reservations_guest_id ON reservations(guest_id);
CREATE INDEX idx_reservations_booking_ref ON reservations(booking_ref);


-- ─────────────────────────────────────────────────────────────────────────────
-- CONVERSATIONS
-- Groups related messages into a thread per guest × channel.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    guest_id        UUID NOT NULL REFERENCES guests(id) ON DELETE RESTRICT,
    reservation_id  UUID REFERENCES reservations(id) ON DELETE SET NULL,
    property_id     UUID REFERENCES properties(id) ON DELETE SET NULL,
    source          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','resolved','escalated')),
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX idx_conversations_guest_id ON conversations(guest_id);
CREATE INDEX idx_conversations_status ON conversations(status);


-- ─────────────────────────────────────────────────────────────────────────────
-- MESSAGES
-- Every inbound and outbound message in one table.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE messages (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Handler-generated UUID (returned in API response)
    message_id          TEXT UNIQUE NOT NULL,
    conversation_id     UUID REFERENCES conversations(id) ON DELETE SET NULL,
    guest_id            UUID REFERENCES guests(id) ON DELETE SET NULL,
    reservation_id      UUID REFERENCES reservations(id) ON DELETE SET NULL,
    property_id         UUID REFERENCES properties(id) ON DELETE SET NULL,

    -- Channel & direction
    source              TEXT NOT NULL CHECK (source IN
                            ('whatsapp','booking_com','airbnb','instagram','direct')),
    is_inbound          BOOLEAN NOT NULL DEFAULT TRUE,
    guest_name          TEXT NOT NULL,
    message_text        TEXT NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL,

    -- Classification (ENHANCEMENT: includes sentiment)
    query_type          TEXT NOT NULL CHECK (query_type IN (
                            'pre_sales_availability','pre_sales_pricing',
                            'post_sales_checkin','special_request',
                            'complaint','general_enquiry')),
    sentiment           TEXT CHECK (sentiment IN
                            ('positive','neutral','negative','urgent')),

    -- AI fields
    ai_drafted_reply    TEXT,
    confidence_score    NUMERIC(4, 3) CHECK (confidence_score BETWEEN 0 AND 1),
    confidence_reasoning TEXT,           -- ENHANCEMENT: audit trail for score
    action_taken        TEXT CHECK (action_taken IN
                            ('auto_send','agent_review','escalate')),

    -- Human edit audit trail
    final_reply         TEXT,
    edited_by_agent_id  UUID,            -- future: FK to agents table
    edited_at           TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_guest_id         ON messages(guest_id);
CREATE INDEX idx_messages_conversation_id  ON messages(conversation_id);
CREATE INDEX idx_messages_timestamp        ON messages(timestamp DESC);
CREATE INDEX idx_messages_query_type       ON messages(query_type);
-- ENHANCEMENT: index for complaint-pattern queries (Part 3 Learning answer)
CREATE INDEX idx_messages_complaint_lookup ON messages(property_id, query_type, timestamp)
    WHERE query_type = 'complaint';


-- ─────────────────────────────────────────────────────────────────────────────
-- SYSTEM EVENTS  ← ENHANCEMENT
-- Audit log for every automated action the platform takes:
-- escalations, notifications sent, pattern alerts, retries, etc.
-- This is the foundation of the "learning" system in Part 3.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE system_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type      TEXT NOT NULL,       -- e.g. 'escalation_triggered', 'pattern_alert'
    message_id      UUID REFERENCES messages(id) ON DELETE SET NULL,
    property_id     UUID REFERENCES properties(id) ON DELETE SET NULL,
    payload         JSONB,               -- flexible: notification details, thresholds, etc.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_system_events_type        ON system_events(event_type);
CREATE INDEX idx_system_events_property_id ON system_events(property_id);
CREATE INDEX idx_system_events_created_at  ON system_events(created_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- COMPLAINT PATTERN VIEW  ← ENHANCEMENT
-- Pre-built view to detect recurring complaints (used in Part 3 answer).
-- A scheduled job can query this view nightly to raise maintenance tickets.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE VIEW complaint_patterns AS
SELECT
    p.property_code,
    m.message_text,
    COUNT(*)                            AS complaint_count,
    MAX(m.timestamp)                    AS most_recent,
    MIN(m.timestamp)                    AS first_occurrence
FROM messages m
JOIN properties p ON p.id = m.property_id
WHERE m.query_type = 'complaint'
  AND m.timestamp  > NOW() - INTERVAL '60 days'
GROUP BY p.property_code, m.message_text
HAVING COUNT(*) >= 2                    -- flag if same complaint appears 2+ times
ORDER BY complaint_count DESC;

-- =============================================================================
-- DESIGN DECISIONS
-- =============================================================================
-- 1. HARDEST DECISION — messages.reservation_id is NULLABLE.
--    Pre-sales messages arrive before a reservation exists. Making
--    reservation_id required would lose pre-booking enquiries. Nullable
--    preserves them while still linking post-booking messages to their
--    reservation via a JOIN on booking_ref → reservations.booking_ref.
--
-- 2. guests table has per-channel IDs (whatsapp_id, airbnb_user_id, etc.)
--    rather than a generic "external_id + channel" pair. This is more
--    verbose but allows unique constraints per channel and avoids a
--    composite-key lookup at merge time.
--
-- 3. system_events uses JSONB payload for flexibility. Escalation events
--    might carry {notified_phone, method: "sms"} while pattern alerts carry
--    {threshold: 3, keyword: "hot water"}. One table handles both without
--    needing ALTER TABLE for every new event type.
--
-- 4. complaint_patterns VIEW materialises pattern detection in SQL.
--    A nightly cron SELECT * FROM complaint_patterns WHERE complaint_count >= 3
--    gives the ops team a proactive maintenance list without any application code.
-- =============================================================================
