# Nistula Technical Assessment — Arnab Kumar

> Submission for the Nistula Summer Technology Internship 2026  
> Built with FastAPI + Claude API | Python 3.11+

---

## What's Inside

| File | Purpose |
|---|---|
| `src/main.py` | FastAPI app — `/webhook/message` + `/health` endpoints |
| `src/classifier.py` | Weighted keyword classifier + sentiment detection |
| `src/claude_client.py` | Claude API integration with retry logic + source-aware tone |
| `src/confidence.py` | Confidence scoring with human-readable reasoning |
| `src/models.py` | All Pydantic schemas |
| `schema.sql` | Full PostgreSQL schema (Part 2) |
| `thinking.md` | Written answers (Part 3) |

---

## Setup & Run

```bash
# 1. Clone
git clone https://github.com/ari9516/nistula-technical-assessment.git
cd nistula-technical-assessment

# 2. Virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your API key
cp .env.example .env
# Open .env and set: CLAUDE_API_KEY=your-key-here

# 5. Start the server
uvicorn src.main:app --reload --port 8000
```

API at `http://localhost:8000` | Docs at `http://localhost:8000/docs`

---

## Endpoint

### `POST /webhook/message`

```bash
# Test 1 — Availability query (known guest)
curl -s -X POST http://localhost:8000/webhook/message \
  -H "Content-Type: application/json" \
  -d '{
    "source": "whatsapp",
    "guest_name": "Rahul Sharma",
    "message": "Is the villa available from April 20 to 24? What is the rate for 2 adults?",
    "timestamp": "2026-05-05T10:30:00Z",
    "booking_ref": "NIS-2024-0891",
    "property_id": "villa-b1"
  }' | python -m json.tool
```

```bash
# Test 2 — WiFi password (post-sales)
curl -s -X POST http://localhost:8000/webhook/message \
  -H "Content-Type: application/json" \
  -d '{
    "source": "whatsapp",
    "guest_name": "Priya Mehta",
    "message": "Hi, what is the WiFi password please?",
    "timestamp": "2026-05-06T14:00:00Z",
    "booking_ref": "NIS-2024-0992",
    "property_id": "villa-b1"
  }' | python -m json.tool
```

```bash
# Test 3 — Urgent complaint (3am, no booking ref)
curl -s -X POST http://localhost:8000/webhook/message \
  -H "Content-Type: application/json" \
  -d '{
    "source": "whatsapp",
    "guest_name": "James Wilson",
    "message": "There is no hot water and we have guests arriving for breakfast in 4 hours. This is unacceptable. I want a refund for tonight.",
    "timestamp": "2026-05-07T03:00:00Z",
    "property_id": "villa-b1"
  }' | python -m json.tool
```

**Expected results:**

| Test | `query_type` | `sentiment` | `action` | `confidence` |
|---|---|---|---|---|
| Availability | `pre_sales_availability` | `neutral` | `auto_send` | 0.90 |
| WiFi password | `post_sales_checkin` | `neutral` | `agent_review` | 0.80 |
| 3am complaint | `complaint` | `urgent` | `escalate` | 0.40 |

### `GET /health`

```bash
curl http://localhost:8000/health
# {"status":"ok","timestamp":"...","version":"2.0.0"}
```

---

## Confidence Scoring Logic

Every message starts at a base score of `0.70` and is adjusted:

| Factor | Adjustment |
|---|---|
| `booking_ref` present (known guest) | +0.10 |
| Clear pre-sales query (availability / pricing) | +0.10 |
| Standard post-sales query (wifi, check-in, etc.) | +0.05 |
| General enquiry (vague) | −0.05 |
| Special request (needs human coordination) | −0.05 |
| Positive sentiment detected | +0.05 |
| Negative sentiment detected | −0.10 |
| Urgent sentiment detected | −0.15 |
| Complaint (any) | Forced floor: **0.40** |

**Action thresholds:**

| Score | Action |
|---|---|
| >= 0.85 | `auto_send` |
| 0.60 – 0.84 | `agent_review` |
| < 0.60 or complaint | `escalate` |

Every response includes a `reasoning` field explaining exactly which factors applied, so agents can audit any decision.

---

## Enhancements Beyond the Brief

**Sentiment detection** — messages tagged `urgent / negative / positive / neutral`. A 3am complaint routes differently from a daytime one.

**Weighted keyword scoring** — all categories scored simultaneously; highest wins. Avoids misclassification on overlapping signals like "price for available dates."

**Retry with back-off** — Claude API retries up to 3 times (2s → 4s → 8s) on transient errors.

**Source-aware tone** — WhatsApp gets warm first-name replies. Booking.com gets formal English. Same prompt template, tone injected per channel.

**`reasoning` field** — every response explains the confidence decision in plain English.

**`system_events` table** — audit log in schema for every automated action: escalations, notifications, pattern alerts.

**`complaint_patterns` view** — pre-built SQL view for nightly pattern detection (see `thinking.md` Part 3).

---

## Error Handling

| Situation | HTTP Status |
|---|---|
| Missing or invalid fields | `422` — FastAPI auto-validates |
| `CLAUDE_API_KEY` not set | Server refuses to start with clear message |
| Claude API timeout (3 retries exhausted) | `502` with explanation |
| Unexpected exception | `500` — generic message to client, full trace in logs |

---

## Assumptions

- `booking_ref` identifies a confirmed guest. Production would JOIN to `guests` + `reservations` for richer Claude context.
- Keyword classification is deterministic and auditable. Can be upgraded to an LLM classifier if needed.
- Property context is hardcoded for this assessment. Production fetches from `properties` table by `property_id`.

---

## If I Had More Time

- Async SQLAlchemy to persist every message to the PostgreSQL schema
- Nightly cron querying `complaint_patterns` to auto-raise maintenance tickets
- `pytest` suite with full integration tests
- Rate limiting per property to protect Claude API budget
