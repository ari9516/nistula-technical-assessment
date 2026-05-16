"""
classifier.py
─────────────
Rule-based query classification + sentiment detection. """

from typing import Optional

from .models import QueryType, Sentiment


# ── Classification rules ──────────────────────────────────────────────────────
# Each entry: (QueryType, keywords, score_weight)
# Higher weight = stronger signal for that category.
# When multiple categories score, the highest total wins.
_RULES: list[tuple[QueryType, list[str], int]] = [
    (QueryType.complaint, [
        "unacceptable", "not working", "broken", "complaint",
        "angry", "refund", "disgusting", "terrible", "awful",
        "no hot water", "ac not", "not happy", "disappointed",
    ], 3),
    (QueryType.post_sales_checkin, [
        "check-in", "checkin", "check in", "check out", "checkout",
        "wifi", "wi-fi", "password", "pool", "caretaker", "key",
        "access", "door code", "parking",              # parking lives here only
    ], 2),
    (QueryType.special_request, [
        "early check", "late check", "transfer", "chef", "extra bed",
        "baby cot", "airport pickup", "taxi", "flowers", "surprise",
    ], 2),
    (QueryType.pre_sales_pricing, [
        "rate", "price", "cost", "how much", "total", "charge",
        "fee", "per night", "pricing",
    ], 2),
    (QueryType.pre_sales_availability, [
        "available", "availability", "vacancy", "free on", "open on",
        "book", "dates",
    ], 2),
    (QueryType.general_enquiry, [
        "pet", "dog", "cat", "smoking", "party", "event",   # FIX: "parking" removed
        "noise", "curfew", "allow",
    ], 1),
]


# ── Sentiment rules ───────────────────────────────────────────────────────────
# Priority order when detecting: urgent > negative > positive > neutral
_SENTIMENT_RULES: dict[Sentiment, list[str]] = {
    Sentiment.urgent: [
        "urgent", "emergency", "asap", "immediately", "right now",
        "no hot water", "not working", "3am", "4 hours",
    ],
    Sentiment.negative: [
        "unacceptable", "terrible", "awful", "disgusting", "refund",
        "not happy", "angry", "disappointed", "broken", "complaint",
    ],
    Sentiment.positive: [
        "amazing", "great", "excellent", "thank", "love", "perfect",
        "wonderful", "happy", "pleased",
    ],
}


# ── Public API ────────────────────────────────────────────────────────────────

def classify_query(message_text: str, booking_ref: Optional[str]) -> QueryType:
    """
    Score every category against the message and return the highest scorer.
    Falls back to general_enquiry if nothing matches.

    The booking_ref parameter is intentionally kept for future use —
    known guests may exhibit different query patterns (e.g. post-sales
    queries are more likely when a booking_ref is present).
    """
    text = message_text.lower()
    scores: dict[QueryType, int] = {qt: 0 for qt in QueryType}

    for query_type, keywords, weight in _RULES:
        for kw in keywords:
            if kw in text:
                scores[query_type] += weight

    best_type, best_score = max(scores.items(), key=lambda x: x[1])

    return best_type if best_score > 0 else QueryType.general_enquiry


def detect_sentiment(message_text: str) -> Sentiment:
    """
    Priority-ordered sentiment detection: urgent > negative > positive > neutral.
    Returns the first sentiment whose keyword list has any match.
    """
    text = message_text.lower()

    for sentiment in (Sentiment.urgent, Sentiment.negative, Sentiment.positive):
        if any(kw in text for kw in _SENTIMENT_RULES[sentiment]):
            return sentiment

    return Sentiment.neutral