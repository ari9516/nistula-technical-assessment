"""
main.py
───────
FastAPI entry point for the Nistula Guest Message Handler.

Enhancements over basic solution:
  - /health endpoint for uptime monitoring.
  - Request ID injected into every response header (X-Request-ID)
    for traceability across logs.
  - Structured logging (JSON-friendly) so logs can be ingested by
    Datadog / CloudWatch without extra parsing.
  - Startup check: fails fast if CLAUDE_API_KEY is missing, with a
    clear error message rather than a cryptic 500 later.
"""

import logging
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load .env before anything reads env vars
load_dotenv()

# Use relative imports for local modules
from .classifier import classify_query, detect_sentiment
from .claude_client import draft_reply
from .confidence import compute_confidence, decide_action
from .models import (
    HandlerResponse,
    HealthResponse,
    InboundMessage,
    UnifiedMessage,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
)
logger = logging.getLogger("nistula")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Nistula Guest Message Handler",
    description="Receives guest messages, classifies them, and drafts AI replies.",
    version="2.0.0",  # Updated to match enhanced version
)

# Add CORS middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup check ─────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    """Check API key and log startup info"""
    if not os.environ.get("CLAUDE_API_KEY"):
        logger.error("CLAUDE_API_KEY not set. Copy .env.example to .env and add your key.")
        raise RuntimeError("CLAUDE_API_KEY is required but not set.")
    
    logger.info("=" * 50)
    logger.info("Nistula Guest Message Handler v2.0.0")
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    logger.info("Startup check passed — CLAUDE_API_KEY is present.")
    logger.info("=" * 50)


@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown event"""
    logger.info("Shutting down Nistula Guest Message Handler")


# ── Middleware: inject X-Request-ID and log requests ──────────────────────────
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    
    # Log incoming request
    logger.info(
        f"Request started | request_id={request_id} | "
        f"method={request.method} | path={request.url.path}"
    )
    
    response: Response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    
    # Log response status
    logger.info(
        f"Request completed | request_id={request_id} | "
        f"status={response.status_code}"
    )
    
    return response


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Info"])
async def root():
    """Root endpoint with API information"""
    return {
        "service": "Nistula Guest Message Handler",
        "version": "2.0.0",
        "status": "operational",
        "endpoints": {
            "webhook": {
                "path": "/webhook/message",
                "method": "POST",
                "description": "Receive and process guest messages"
            },
            "health": {
                "path": "/health",
                "method": "GET",
                "description": "Health check endpoint"
            }
        },
        "documentation": "/docs"
    }


@app.get("/health", response_model=HealthResponse, tags=["Monitoring"])
async def health():
    """Liveness and readiness check endpoint"""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc),
        version="2.0.0",
    )


@app.post(
    "/webhook/message",
    response_model=HandlerResponse,
    tags=["Webhook"],
    summary="Receive and process an inbound guest message",
    status_code=200,
)
async def handle_message(payload: InboundMessage):
    """
    Pipeline:
      1. Validate & normalise → UnifiedMessage
      2. Classify query type + detect sentiment
      3. Draft AI reply via Claude
      4. Compute confidence score + decide action
      5. Return HandlerResponse with reasoning
    """
    # Generate request ID for tracking this specific message
    message_process_id = str(uuid.uuid4())
    
    logger.info(
        f"Processing message | process_id={message_process_id} | "
        f"source={payload.source} | guest={payload.guest_name} | "
        f"property={payload.property_id} | has_booking={payload.booking_ref is not None}"
    )

    try:
        # Step 1 — classify & detect sentiment
        query_type = classify_query(payload.message, payload.booking_ref)
        sentiment = detect_sentiment(payload.message)

        logger.info(
            f"Classification complete | process_id={message_process_id} | "
            f"query_type={query_type.value} | sentiment={sentiment.value}"
        )

        # Step 2 — build unified message
        unified = UnifiedMessage(
            source=payload.source,
            guest_name=payload.guest_name,
            message_text=payload.message,
            timestamp=payload.timestamp,
            booking_ref=payload.booking_ref,
            property_id=payload.property_id,
            query_type=query_type,
            sentiment=sentiment,
        )

        # Step 3 — AI draft reply
        logger.info(f"Drafting reply | process_id={message_process_id}")
        drafted_reply_text = await draft_reply(unified)
        
        logger.info(
            f"Reply drafted | process_id={message_process_id} | "
            f"reply_length={len(drafted_reply_text)} chars"
        )

        # Step 4 — confidence + action
        confidence_score, confidence_reasoning = compute_confidence(unified)
        
        # decide_action now returns tuple (action, action_reasoning)
        action, action_reasoning = decide_action(confidence_score, query_type, sentiment)
        
        # Combine reasoning for response
        full_reasoning = f"Confidence: {confidence_reasoning} | Action: {action_reasoning}"

        logger.info(
            f"Decision made | process_id={message_process_id} | "
            f"action={action} | confidence={confidence_score:.2f} | "
            f"message_id={unified.message_id}"
        )

        # Return final response
        return HandlerResponse(
            message_id=unified.message_id,
            query_type=query_type,
            sentiment=sentiment,
            drafted_reply=drafted_reply_text,
            confidence_score=round(confidence_score, 2),
            action=action,
            reasoning=full_reasoning,
        )

    except EnvironmentError as e:
        # Configuration errors (missing API key, etc.)
        logger.error(f"Configuration error | process_id={message_process_id} | error={str(e)}")
        raise HTTPException(
            status_code=503, 
            detail=f"Service configuration error: {str(e)}"
        )

    except RuntimeError as e:
        # Runtime errors (Claude API failures, etc.)
        logger.error(f"Runtime error | process_id={message_process_id} | error={str(e)}")
        raise HTTPException(
            status_code=502, 
            detail=f"Service temporarily unavailable: {str(e)}"
        )

    except ValueError as e:
        # Validation errors
        logger.error(f"Validation error | process_id={message_process_id} | error={str(e)}")
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid input: {str(e)}"
        )

    except Exception as e:
        # Unexpected errors
        logger.exception(
            f"Unexpected error | process_id={message_process_id} | "
            f"error_type={type(e).__name__} | error={str(e)}"
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Our team has been notified.",
        )


# ── Optional: Add a metrics endpoint for monitoring ──────────────────────────
@app.get("/metrics", tags=["Monitoring"])
async def metrics():
    """Simple metrics endpoint for basic monitoring"""
    return {
        "service": "nistula-message-handler",
        "version": "2.0.0",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    