"""
Nistula Guest Message Handler Package
A production-ready AI-powered guest message handling system.
"""

__version__ = "2.0.0"
__author__ = "Arnab Kumar"
__description__ = "Guest message handler with sentiment analysis and AI-powered replies"

# Export main components for easier imports
from .models import (
    InboundMessage,
    UnifiedMessage,
    HandlerResponse,
    HealthResponse,
    QueryType,
    Sentiment,
    Source
)

from .classifier import classify_query, detect_sentiment
from .claude_client import draft_reply
from .confidence import compute_confidence, decide_action

# Define what gets imported with "from src import *"
__all__ = [
    # Models
    "InboundMessage",
    "UnifiedMessage", 
    "HandlerResponse",
    "HealthResponse",
    "QueryType",
    "Sentiment",
    "Source",
    
    # Functions
    "classify_query",
    "detect_sentiment",
    "draft_reply",
    "compute_confidence",
    "decide_action",
    
    # Package info
    "__version__",
    "__author__",
]

# Optional: Package metadata for setup.py
PACKAGE_INFO = {
    "name": "nistula-message-handler",
    "version": __version__,
    "author": __author__,
    "description": __description__,
}