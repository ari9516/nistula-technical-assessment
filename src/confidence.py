"""
confidence.py
─────────────
Confidence scoring and action routing.

"""

from .models import UnifiedMessage, QueryType, Sentiment


# ── Scoring constants (easy to tune without touching logic) ───────────────────
BASE_SCORE             =  0.70
BOOKING_REF_BONUS      =  0.10   # known guest, more context
CLEAR_QUERY_BONUS      =  0.10   # availability / pricing — clear from property context
VAGUE_QUERY_PENALTY    = -0.05   # general enquiry — may need human judgement
POSITIVE_BONUS         =  0.05   # positive sentiment — safe to auto-respond
NEGATIVE_PENALTY       = -0.10   # negative sentiment
URGENT_PENALTY         = -0.15   # urgent sentiment — escalate faster
COMPLAINT_FLOOR        =  0.40   # complaints are always capped here

AUTO_SEND_THRESHOLD    =  0.85
AGENT_REVIEW_THRESHOLD =  0.60
# Note: ESCALATE_THRESHOLD == AGENT_REVIEW_THRESHOLD; anything below 0.60 escalates.


def compute_confidence(unified: UnifiedMessage) -> tuple[float, str]:
    """
    Returns (score, reasoning_string).

    Score starts at BASE_SCORE and is adjusted additively by:
      - booking_ref presence (known guest)
      - query type (how answerable from property context)
      - sentiment (urgency / negativity risk)
    Final score is clamped to [0.0, 1.0].
    """
    reasons: list[str] = [f"Base score {BASE_SCORE:.2f}"]
    score = BASE_SCORE

    # Complaints bypass normal scoring — always floor for human review
    if unified.query_type == QueryType.complaint:
        return COMPLAINT_FLOOR, "Complaint detected — forced to floor score for human review."

    # Known guest bonus
    if unified.booking_ref:
        score += BOOKING_REF_BONUS
        reasons.append(f"+{BOOKING_REF_BONUS:.2f} booking_ref present (known guest)")

    # Query-type adjustment
    if unified.query_type in (QueryType.pre_sales_availability, QueryType.pre_sales_pricing):
        score += CLEAR_QUERY_BONUS
        reasons.append(f"+{CLEAR_QUERY_BONUS:.2f} clear pre-sales query (answerable from context)")
    elif unified.query_type == QueryType.post_sales_checkin:
        score += 0.05
        reasons.append("+0.05 standard post-sales query (wifi, check-in, etc.)")
    elif unified.query_type == QueryType.general_enquiry:
        score += VAGUE_QUERY_PENALTY
        reasons.append(f"{VAGUE_QUERY_PENALTY:.2f} general enquiry (may need human judgement)")
    elif unified.query_type == QueryType.special_request:
        score += -0.05
        reasons.append("-0.05 special request (may need human coordination)")

    # Sentiment adjustment
    if unified.sentiment == Sentiment.urgent:
        score += URGENT_PENALTY
        reasons.append(f"{URGENT_PENALTY:.2f} urgent sentiment detected")
    elif unified.sentiment == Sentiment.negative:
        score += NEGATIVE_PENALTY
        reasons.append(f"{NEGATIVE_PENALTY:.2f} negative sentiment detected")
    elif unified.sentiment == Sentiment.positive:
        score += POSITIVE_BONUS
        reasons.append(f"+{POSITIVE_BONUS:.2f} positive sentiment detected")

    # Clamp to [0.0, 1.0]
    score = max(0.0, min(1.0, score))
    reasons.append(f"→ Final score: {score:.2f}")

    return score, " | ".join(reasons)


def decide_action(score: float, query_type: QueryType, sentiment: Sentiment = None) -> tuple[str, str]:
    """
    Returns (action, action_reasoning).

    Decision ladder (highest priority first):
      1. Complaints → always escalate
      2. Urgent sentiment → agent_review if score >= threshold, else escalate
      3. Negative sentiment → agent_review if score >= threshold, else escalate
      4. Normal path → auto_send / agent_review / escalate by score

    FIX: threshold comparison uses >= (not >) so a score exactly equal to
    AUTO_SEND_THRESHOLD (0.85) correctly routes to auto_send rather than
    falling through to agent_review.
    """
    # Always escalate complaints
    if query_type == QueryType.complaint:
        return "escalate", "Complaint always requires human intervention."

    # Urgent messages need human eyes even when confidence is high
    if sentiment == Sentiment.urgent:
        if score >= AUTO_SEND_THRESHOLD:
            return (
                "agent_review",
                f"Urgent message needs human confirmation despite high confidence ({score:.2f}).",
            )
        return (
            "escalate",
            f"Urgent message with low confidence ({score:.2f}) — immediate escalation.",
        )

    # Negative sentiment: never auto-send, always at least agent_review
    if sentiment == Sentiment.negative:
        if score >= AGENT_REVIEW_THRESHOLD:
            return "agent_review", f"Negative sentiment requires agent review (score: {score:.2f})."
        return "escalate", f"Negative sentiment with low confidence ({score:.2f}) — escalate."

    # Normal path for neutral / positive sentiment
    if score >= AUTO_SEND_THRESHOLD:          # FIX: was `score > AUTO_SEND_THRESHOLD`
        return "auto_send", f"High confidence ({score:.2f}) — safe for auto-send."
    if score >= AGENT_REVIEW_THRESHOLD:
        return "agent_review", f"Medium confidence ({score:.2f}) — agent should review."
    return "escalate", f"Low confidence ({score:.2f}) — escalate to human."


# ── Helpers ───────────────────────────────────────────────────────────────────

def decide_action_simple(score: float, query_type: QueryType) -> str:
    """Backward-compatible wrapper that returns only the action string."""
    action, _ = decide_action(score, query_type)
    return action


def get_action_priority(action: str) -> int:
    """Return queue priority (lower number = higher priority)."""
    return {"escalate": 1, "agent_review": 2, "auto_send": 3}.get(action, 2)