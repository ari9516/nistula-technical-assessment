"""
confidence.py
─────────────
Confidence scoring and action routing.

Enhancement over basic solution:
  - Sentiment feeds into the score (urgent messages get lower confidence
    even when the query type is straightforward).
  - Returns a human-readable `reasoning` string alongside score + action,
    so the agent dashboard can show WHY a message was escalated.
  - Scoring is additive/subtractive from a documented base, making it
    easy to audit and tune.
"""

from .models import UnifiedMessage, QueryType, Sentiment


# ── Scoring constants (easy to tune without touching logic) ───────────────────
BASE_SCORE           =  0.70
BOOKING_REF_BONUS    =  0.10   # known guest, more context
CLEAR_QUERY_BONUS    =  0.10   # availability / pricing — clear from property context
VAGUE_QUERY_PENALTY  = -0.05   # general enquiry — may need human judgement
POSITIVE_BONUS       =  0.05   # positive sentiment - safe to auto-respond
NEGATIVE_PENALTY     = -0.10   # negative sentiment
URGENT_PENALTY       = -0.15   # urgent sentiment — escalate faster
COMPLAINT_FLOOR      =  0.40   # complaints are always capped here

AUTO_SEND_THRESHOLD  =  0.85
AGENT_REVIEW_THRESHOLD = 0.60
ESCALATE_THRESHOLD   =  0.60


def compute_confidence(unified: UnifiedMessage) -> tuple[float, str]:
    """
    Returns (score, reasoning_string).
    """
    reasons: list[str] = [f"Base score {BASE_SCORE:.2f}"]
    score = BASE_SCORE

    # Complaints bypass normal scoring
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
        score += 0.05  # Standard check-in questions are usually straightforward
        reasons.append(f"+0.05 standard post-sales query (wifi, check-in, etc.)")
    elif unified.query_type == QueryType.general_enquiry:
        score += VAGUE_QUERY_PENALTY
        reasons.append(f"{VAGUE_QUERY_PENALTY:.2f} general enquiry (may need human judgement)")
    elif unified.query_type == QueryType.special_request:
        score += -0.05  # Special requests often need human coordination
        reasons.append(f"-0.05 special request (may need human coordination)")

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

    # Cap between 0 and 1
    score = max(0.0, min(1.0, score))
    reasons.append(f"→ Final score: {score:.2f}")
    
    return score, " | ".join(reasons)


def decide_action(score: float, query_type: QueryType, sentiment: Sentiment = None) -> tuple[str, str]:
    """
    Returns (action, action_reasoning)
    Enhanced to include sentiment-based decision making
    """
    # Always escalate complaints
    if query_type == QueryType.complaint:
        return "escalate", "Complaint always requires human intervention"
    
    # Urgent messages need extra caution
    if sentiment == Sentiment.urgent:
        if score >= AUTO_SEND_THRESHOLD:
            return "agent_review", f"Urgent message needs human confirmation despite high confidence ({score:.2f})"
        else:
            return "escalate", f"Urgent message with low confidence ({score:.2f}) - immediate escalation"
    
    # Negative sentiment messages should be reviewed
    if sentiment == Sentiment.negative:
        if score >= AGENT_REVIEW_THRESHOLD:
            return "agent_review", f"Negative sentiment requires agent review (score: {score:.2f})"
        else:
            return "escalate", f"Negative sentiment with low confidence ({score:.2f}) - escalate"
    
    # Normal decision logic for neutral/positive sentiment
    if score > AUTO_SEND_THRESHOLD:
        return "auto_send", f"High confidence ({score:.2f}) - safe for auto-send"
    elif score >= AGENT_REVIEW_THRESHOLD:
        return "agent_review", f"Medium confidence ({score:.2f}) - agent should review"
    else:
        return "escalate", f"Low confidence ({score:.2f}) - escalate to human"


# Legacy function for backward compatibility (if needed)
def decide_action_simple(score: float, query_type: QueryType) -> str:
    """Simple action decision without reasoning (backward compatible)"""
    if query_type == QueryType.complaint:
        return "escalate"
    if score >= AUTO_SEND_THRESHOLD:
        return "auto_send"
    if score >= AGENT_REVIEW_THRESHOLD:
        return "agent_review"
    return "escalate"


# Helper function to get action priority (for queue management)
def get_action_priority(action: str) -> int:
    """Return priority level for queue management (lower = higher priority)"""
    priorities = {
        "escalate": 1,      # Highest priority
        "agent_review": 2,  # Medium priority
        "auto_send": 3      # Lowest priority
    }
    return priorities.get(action, 2)
    