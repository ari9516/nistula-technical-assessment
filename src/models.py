from pydantic import BaseModel, Field, validator
from uuid import uuid4
from datetime import datetime
from enum import Enum
from typing import Optional


class Source(str, Enum):
    whatsapp = "whatsapp"
    booking_com = "booking_com"
    airbnb = "airbnb"
    instagram = "instagram"
    direct = "direct"


class QueryType(str, Enum):
    pre_sales_availability = "pre_sales_availability"
    pre_sales_pricing = "pre_sales_pricing"
    post_sales_checkin = "post_sales_checkin"
    special_request = "special_request"
    complaint = "complaint"
    general_enquiry = "general_enquiry"


class Sentiment(str, Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"
    urgent = "urgent"


# ── Incoming webhook payload ──────────────────────────────────────────────────
class InboundMessage(BaseModel):
    source: Source
    guest_name: str
    message: str
    timestamp: datetime
    booking_ref: Optional[str] = None
    property_id: str

    @validator("message")
    def message_not_empty(cls, v):
        if not v.strip():
            raise ValueError("message cannot be empty")
        return v.strip()

    @validator("guest_name")
    def guest_name_not_empty(cls, v):
        if not v.strip():
            raise ValueError("guest_name cannot be empty")
        return v.strip()


# ── Normalised unified schema ─────────────────────────────────────────────────
class UnifiedMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    source: Source
    guest_name: str
    message_text: str
    timestamp: datetime
    booking_ref: Optional[str]
    property_id: str
    query_type: QueryType
    sentiment: Sentiment = Sentiment.neutral   # ENHANCEMENT: sentiment tracking


# ── Final API response ────────────────────────────────────────────────────────
class HandlerResponse(BaseModel):
    message_id: str
    query_type: QueryType
    sentiment: Sentiment                       # ENHANCEMENT: exposed in response
    drafted_reply: str
    confidence_score: float
    action: str                                # auto_send | agent_review | escalate
    reasoning: str                             # ENHANCEMENT: why this action was taken


# ── Health check response ─────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    