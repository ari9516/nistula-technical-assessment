"""
classifier.py
─────────────
Rule-based query classification + sentiment detection.

Enhancement over the basic solution:
  - Weighted keyword scoring instead of first-match wins,
    so overlapping signals (e.g. "price for available dates?")
    resolve more accurately.
  - Separate sentiment detector used by confidence.py.
"""

from .models import QueryType, Sentiment
from typing import Optional


# Each entry: (keywords, score_weight)
# Higher weight = stronger signal for that category.
_RULES: list[tuple[QueryType, list[str], int]] = [
    (QueryType.complaint, [
        "unacceptable", "not working", "broken", "complaint",
        "angry", "refund", "disgusting", "terrible", "awful",
        "no hot water", "ac not", "not happy", "disappointed",
    ], 3),
    (QueryType.post_sales_checkin, [
        "check-in", "checkin", "check in", "check out", "checkout",
        "wifi", "wi-fi", "password", "pool", "caretaker", "key",
        "access", "door code", "parking",
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
        "pet", "dog", "cat", "parking", "smoking", "party", "event",
        "noise", "curfew", "allow",
    ], 1),
]

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


def classify_query(message_text: str, booking_ref: Optional[str]) -> QueryType:
    """
    Score every category against the message and return the winner.
    Falls back to general_enquiry if nothing scores.
    
    Note: booking_ref parameter is kept for future enhancement
    (e.g., known guests might have different query patterns)
    """
    text = message_text.lower()
    scores: dict[QueryType, int] = {qt: 0 for qt in QueryType}

    for query_type, keywords, weight in _RULES:
        for kw in keywords:
            if kw in text:
                scores[query_type] += weight

    best_type, best_score = max(scores.items(), key=lambda x: x[1])

    # If nothing matched at all, use general_enquiry
    if best_score == 0:
        return QueryType.general_enquiry

    return best_type


def detect_sentiment(message_text: str) -> Sentiment:
    """
    Simple priority-ordered sentiment detection.
    urgent > negative > positive > neutral
    """
    text = message_text.lower()

    for sentiment in (Sentiment.urgent, Sentiment.negative, Sentiment.positive):
        keywords = _SENTIMENT_RULES[sentiment]
        if any(kw in text for kw in keywords):
            return sentiment

    return Sentiment.neutral
    