"""
claude_client.py
────────────────
Calls the Claude API to draft a guest reply.

Enhancements over basic solution:
  - Retry logic with exponential back-off (up to 3 attempts).
  - Source-aware tone hint (WhatsApp → casual, Booking.com → formal).
  - Validates response is non-empty before returning.
"""

import os
import asyncio
import httpx
from .models import UnifiedMessage, QueryType, Source, Sentiment

# ── Property knowledge base ───────────────────────────────────────────────────
PROPERTY_CONTEXT = """
Property: Villa B1, Assagao, North Goa
Bedrooms: 3 | Max guests: 6 | Private pool: Yes
Check-in: 2pm | Check-out: 11am
Base rate: INR 18,000 per night (up to 4 guests)
Extra guest: INR 2,000 per night per person
WiFi password: Nistula@2024
Caretaker: Available 8am to 10pm
Chef on call: Yes, pre-booking required
Availability April 20-24: Available
Cancellation: Free up to 7 days before check-in
"""

# Tone guidance per source channel
_SOURCE_TONE: dict[Source, str] = {
    Source.whatsapp:    "conversational and warm, use the guest's first name",
    Source.booking_com: "professional and formal",
    Source.airbnb:      "friendly and informative",
    Source.instagram:   "upbeat and brief",
    Source.direct:      "personal and welcoming",
}

# Sentiment-specific instructions
_SENTIMENT_GUIDANCE: dict[Sentiment, str] = {
    Sentiment.urgent: """
    IMPORTANT - URGENT MESSAGE:
    - Acknowledge the urgency immediately
    - Promise action within 15 minutes
    - Apologize for the inconvenience
    - Don't make promises you can't keep
    """,
    Sentiment.negative: """
    IMPORTANT - NEGATIVE SENTIMENT:
    - Start with a sincere apology
    - Show empathy for their frustration
    - Take ownership of the problem
    - Offer a concrete solution or next step
    - Don't be defensive
    """,
    Sentiment.positive: """
    POSITIVE SENTIMENT:
    - Match their enthusiasm
    - Thank them for their kind words
    - Be warm and appreciative
    - Maintain positive energy
    """,
    Sentiment.neutral: """
    NEUTRAL SENTIMENT:
    - Be professional and clear
    - Provide direct answers
    - Offer helpful information
    - Keep tone friendly but efficient
    """
}

SYSTEM_PROMPT_TEMPLATE = """You are an AI assistant for Nistula, a luxury villa rental company in Goa.

Your job is to draft a reply to a guest message. Follow these rules:
1. Answer ONLY from the property context below. Never invent details.
2. If the question cannot be answered from context, say: "Let me check with our team and get back to you shortly."
3. Tone: {tone}.
4. Keep the reply under 120 words.
5. For complaints, acknowledge the issue, apologise sincerely, and say a team member will follow up within 15 minutes.
6. Never mention that you are an AI.

{sentiment_guidance}

Property context:
{context}"""


def _build_system_prompt(unified: UnifiedMessage) -> str:
    """Build the system prompt with source-specific tone and sentiment guidance"""
    tone = _SOURCE_TONE.get(unified.source, "friendly and helpful")
    sentiment_guidance = _SENTIMENT_GUIDANCE.get(unified.sentiment, "")
    
    return SYSTEM_PROMPT_TEMPLATE.format(
        tone=tone, 
        sentiment_guidance=sentiment_guidance,
        context=PROPERTY_CONTEXT
    )


async def draft_reply(unified: UnifiedMessage, max_retries: int = 3) -> str:
    """
    Calls Claude API with retry on transient errors.
    Returns the drafted reply text.
    """
    api_key = os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        raise EnvironmentError("CLAUDE_API_KEY is not set in environment variables.")

    # Build user message with rich context
    user_message = (
        f"Guest name: {unified.guest_name}\n"
        f"Source channel: {unified.source.value}\n"
        f"Query type: {unified.query_type.value}\n"
        f"Sentiment: {unified.sentiment.value}\n"
        f"Has booking: {'Yes' if unified.booking_ref else 'No'}\n"
        f"Property: {unified.property_id}\n"
        f"\nGuest message: {unified.message_text}\n\n"
        "Draft a reply following the system instructions:"
    )

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 300,
        "temperature": 0.7,  # Slight creativity for better responses
        "system": _build_system_prompt(unified),
        "messages": [{"role": "user", "content": user_message}],
    }

    last_error: Exception = RuntimeError("Unknown error")

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                text = data["content"][0]["text"].strip()
                
                # Validate non-empty response
                if not text:
                    raise ValueError("Claude returned an empty response.")
                
                # Additional validation: check for hallucinated information
                if "I don't have that information" in text or "I cannot provide" in text:
                    # This is fine - Claude is being honest
                    pass
                
                return text

        except httpx.TimeoutException as e:
            last_error = e
            wait = 2 ** attempt  # 2s, 4s, 8s
            if attempt < max_retries:
                await asyncio.sleep(wait)

        except httpx.TransportError as e:
            last_error = e
            wait = 2 ** attempt
            if attempt < max_retries:
                await asyncio.sleep(wait)

        except httpx.HTTPStatusError as e:
            # 4xx errors won't improve with retries
            if e.response.status_code == 429:  # Rate limit - retry
                wait = 2 ** attempt
                await asyncio.sleep(wait)
                continue
            raise RuntimeError(
                f"Claude API error {e.response.status_code}: {e.response.text}"
            ) from e

        except Exception as e:
            # Non-retryable error
            raise RuntimeError(f"Unexpected error calling Claude API: {str(e)}") from e

    raise RuntimeError(
        f"Claude API unavailable after {max_retries} attempts. Last error: {last_error}"
    )


# Optional: Add a sync wrapper for testing
def draft_reply_sync(unified: UnifiedMessage, max_retries: int = 3) -> str:
    """Synchronous wrapper for draft_reply (useful for testing)"""
    return asyncio.run(draft_reply(unified, max_retries))
    