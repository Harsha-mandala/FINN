"""
FINN — Health & Diagnostics Router
GET /health/llm : LLM model status + daily budget counters (no keys exposed)
NOTE: Uptime monitors / Render keepalive pings should use /health (in main.py),
NEVER /health/llm which invokes Gemini test calls.
"""

import logging
import os
from datetime import datetime

from fastapi import APIRouter

from backend.config import (
    GEMINI_MODEL,
    GEMINI_CHEAP_MODEL,
    GEMINI_FALLBACK_MODELS,
    GEMINI_CHEAP_CHAIN,
    GEMINI_REASONING_CHAIN,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health/llm")
def health_llm():
    """
    Validate each configured LLM model and return budget counters.
    Makes a minimal test call to each model if key is present.
    Never includes API keys, prefixes, suffixes, or lengths in the response.
    """
    gemini_key_set = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    from backend.llm import health_check_llm, get_budget_status, validate_models

    if not gemini_key_set:
        availability = {
            m: "auth"
            for m in list(dict.fromkeys(GEMINI_CHEAP_CHAIN + GEMINI_REASONING_CHAIN))
        }
        combined = availability
    else:
        availability = validate_models()
        if all(status == "auth" for status in availability.values()):
            combined = availability
        else:
            live_statuses: dict = {}
            try:
                live_statuses = health_check_llm()
            except Exception as e:
                logger.warning("[HEALTH/LLM] Live check failed: %s", e)
                live_statuses = {}

            combined: dict = {}
            from backend.llm import _slug

            all_slugs = list(
                dict.fromkeys(
                    _slug(m) for m in GEMINI_CHEAP_CHAIN + GEMINI_REASONING_CHAIN
                )
            )
            for s in all_slugs:
                combined[s] = live_statuses.get(s) or availability.get(s, "unknown")

    budget = get_budget_status()

    from backend.llm import _slug

    return {
        "gemini_key_configured": gemini_key_set,
        "generated_at": datetime.now().isoformat(),
        "chains": {
            "cheap": [_slug(m) for m in GEMINI_CHEAP_CHAIN],
            "reasoning": [_slug(m) for m in GEMINI_REASONING_CHAIN],
        },
        "models": {
            "primary_reasoning": GEMINI_MODEL,
            "primary_cheap": GEMINI_CHEAP_MODEL,
            "fallbacks": GEMINI_FALLBACK_MODELS,
        },
        "model_status": combined,
        "budget": budget,
        "note": (
            "estimated_daily_limit values are conservative estimates "
            "based on known free-tier RPD. The budget counter is best-effort and may "
            "reset on redeploy or container restart; real 429 (RESOURCE_EXHAUSTED) "
            "responses from Google API are the single authoritative source of truth."
        ),
    }
