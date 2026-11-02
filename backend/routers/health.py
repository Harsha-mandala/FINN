"""
FINN — Health Router
GET /health          : service status + CORS config
GET /health/llm      : LLM model status + daily budget counters (no keys exposed)
"""

import logging
import os
from datetime import datetime

from fastapi import APIRouter

from backend.config import (
    ALLOWED_ORIGINS,
    GEMINI_MODEL,
    GEMINI_CHEAP_MODEL,
    GEMINI_FALLBACK_MODELS,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    gemini_key_set = bool(
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_GENAI_API_KEY")
    )
    return {
        "status": "ok",
        "service": "FINN API",
        "version": "2.0.0",
        "generated_at": datetime.now().isoformat(),
        "gemini_key_configured": gemini_key_set,
        "cors_origins": [o for o in ALLOWED_ORIGINS if o],
    }


@router.get("/health/llm")
async def health_llm():
    """
    Validate each configured LLM model and return budget counters.
    Makes a minimal 1-token test call to each model if key is present.
    Never includes API keys in the response.
    """
    from backend.llm import health_check_llm, get_budget_status, validate_models

    # First check model availability without test calls (fast)
    availability = validate_models()

    # If auth failed (no key set), return availability directly without slow HTTP timeouts
    if all(status == "auth" for status in availability.values()):
        combined = availability
    else:
        # Only make live test calls for models marked "ok" or "unknown"
        live_statuses: dict = {}
        try:
            live_statuses = health_check_llm()
        except Exception as e:
            logger.warning("[HEALTH/LLM] Live check failed: %s", e)
            live_statuses = {}

        combined: dict = {}
        all_slugs = list(dict.fromkeys(
            m.removeprefix("models/").strip()
            for m in [GEMINI_MODEL, GEMINI_CHEAP_MODEL] + GEMINI_FALLBACK_MODELS
        ))
        for s in all_slugs:
            combined[s] = live_statuses.get(s) or availability.get(s, "unknown")

    budget = get_budget_status()

    return {
        "generated_at": datetime.now().isoformat(),
        "models": {
            "primary_reasoning": GEMINI_MODEL,
            "primary_cheap": GEMINI_CHEAP_MODEL,
            "fallbacks": GEMINI_FALLBACK_MODELS,
        },
        "model_status": combined,
        "budget": budget,
        "note": (
            "estimated_daily_limit values are conservative estimates "
            "based on known free-tier RPD. Actual limits depend on your API key tier."
        ),
    }
