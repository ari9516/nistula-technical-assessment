# Part 3 — Thinking Question

## Question A — The Immediate Response

**AI reply sent at 3am:**

> Hi [Guest Name], I'm truly sorry you have no hot water — that's completely unacceptable and I sincerely apologise for this experience. I've immediately alerted our on-call caretaker, who will contact you directly within the next 15 minutes. I'll also ensure you receive a partial refund for tonight. Please do not hesitate to message me if anything else comes up — we are here for you.

**Why this wording:**
The message does three things in order: acknowledges the specific problem without excuses, gives a concrete next action with a realistic timeframe (15 minutes, not "soon"), and commits to a refund so the guest feels heard before a human even picks up. The 4-hour window the guest mentioned is not referenced directly — promising to "fix hot water in 4 hours" at 3am would be an overcommit. Instead, the human caretaker contact resolves that ambiguity in person.

---

## Question B — The System Design

When the message is received, the platform detects `query_type = complaint` and `sentiment = urgent`. This triggers the following automated sequence:

1. **Immediate**: Message is stored in `messages` with `action_taken = 'escalate'`. A `system_events` row is written: `event_type = 'escalation_triggered'`.

2. **Notifications (within 30 seconds)**:
   - SMS + push notification to the property manager's phone via Twilio.
   - WhatsApp message to the on-site caretaker (pre-configured per property in the `properties` table).
   - Slack/internal ops channel ping: "URGENT: Villa B1 — guest complaint — no hot water — 3am."

3. **AI auto-sends** the draft reply immediately (low confidence = escalate, but the courtesy reply is sent automatically because waiting is worse than sending).

4. **If no human acknowledges within 30 minutes**:
   - Auto-send a follow-up: *"Our team is still working on this. We haven't forgotten you — we'll update you within 15 minutes."*
   - A second `system_events` entry is written: `event_type = 'escalation_unacknowledged'`.
   - Escalate to the founder/ops lead via a second notification channel (email + call).

5. **Everything logged**: every notification sent, every acknowledgement, every reply — written to `system_events` with timestamps. This makes post-incident analysis possible and builds accountability.

---

## Question C — The Learning

**Detection:**
The system queries `complaint_patterns` (a pre-built SQL view in the schema) nightly:

```sql
SELECT * FROM complaint_patterns
WHERE property_code = 'villa-b1'
  AND complaint_count >= 3;
```

When hot water complaints at Villa B1 cross threshold 3 in 60 days, the following is triggered automatically:

1. **Create a maintenance ticket** in the property ops system (Notion, Asana, or equivalent via webhook) tagged: `type=preventive_maintenance | property=villa-b1 | issue=hot_water`.

2. **Flag the property** for a human review: the property manager receives a weekly digest listing recurring complaint patterns across all villas.

3. **Modify the AI system prompt** for Villa B1 messages: inject a context note — *"Important: there have been recent complaints about hot water at this property. Treat any similar complaint as urgent and immediately notify the caretaker."* — so the AI handles the fourth complaint even faster.

**Prevention (proactive layer):**
Build a nightly automated check (a cron job or serverless function) that:
- Pings the IoT temperature sensor on the Villa B1 water heater at 10pm each evening.
- If temperature is below threshold → auto-alert the caretaker to inspect before any guest wakes up.
- If the sensor is unavailable → alert the property manager to install one.

This shifts the system from **reactive** (handling the complaint after it happens) to **predictive** (resolving the root cause before the guest ever notices). The third complaint is the data signal; the goal is to make it the last one.
