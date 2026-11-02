"""
FINN — Chat Copilot Router
POST /chat

Provider chain:
  1. Gemini (GEMINI_CHEAP_MODEL) with ticker research context when available
  2. Grounded answer from cached research cards (clearly labelled)
  3. Friendly instructional fallback — no infra details, no env var names shown to user

All LLM failures are logged server-side. User sees typed, friendly messages.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter

from backend.config import RESEARCH_CACHE
from backend.models.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

_SYSTEM_PROMPT = """
You are FINN, a financial investment intelligence agent serving institutional investors.

Guidelines:
- Be concise, analytical, and specific. No filler phrases.
- Ground all company observations in reported figures (revenue, margins, PAT, ROE, guidance).
- State the reporting period when citing metrics (e.g., Q2 FY25, FY24 Annual Report).
- If information is not in the context provided, say so clearly — do not speculate.
- Maintain an objective, institutional-investor tone.
- Format key numbers in tables or bullet lists when helpful. Use plain text — no markdown headers.
"""


def _load_ticker_context(ticker: str) -> str:
    """Load research cards from cache and return a compact context string."""
    cache_file = RESEARCH_CACHE / ticker / "_research_cards.json"
    if not cache_file.exists():
        return ""
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        cards = data.get("cards", [])
        if not cards:
            return ""
        parts = [f"Primary source research context for {ticker}:"]
        for card in cards:
            card_type = card.get("card_type", "")
            # Handle both old (data.content) and new (data.key_metrics etc.) card formats
            data_block = card.get("data", {})
            content = data_block.get("content") or json.dumps(data_block, indent=1)
            if content:
                parts.append(f"\n--- {card_type.upper().replace('_', ' ')} ---\n{str(content)[:2000]}")
        return "\n".join(parts)[:12000]
    except Exception as e:
        logger.warning("[CHAT] Failed to load context for %s: %s", ticker, e)
        return ""


def _build_context_prompt(user_msg: str, context: str) -> str:
    if context:
        return f"{context}\n\nUser question: {user_msg}"
    return user_msg


@router.post("")
async def chat(request: ChatRequest):
    """
    Multi-turn chat with FINN.
    Context is loaded from cached research cards if a ticker is set.
    """
    ticker = request.ticker or ""
    ctx = _load_ticker_context(ticker) if ticker else ""

    last_user_msg = ""
    for m in reversed(request.messages):
        if m.role == "user":
            last_user_msg = m.content
            break

    system = _SYSTEM_PROMPT
    if ctx:
        system += f"\n\nYou have access to primary-source research for {ticker}. Answer only from this context."

    # ── Attempt Gemini call ───────────────────────────────────────────────────
    try:
        from backend.llm import gemini_generate, LLMError

        full_prompt = _build_context_prompt(last_user_msg, ctx)
        reply = gemini_generate(
            prompt=full_prompt,
            task="cheap",
            system=system,
            temperature=0.4,
            max_tokens=1024,
        )
        return {
            "response": reply,
            "generated_at": datetime.now().isoformat(),
            "ticker_context": ticker or None,
            "context_used": bool(ctx),
        }

    except Exception as e:
        # Classify but don't surface technical details to the user
        from backend.llm import LLMError, _classify_error
        if isinstance(e, LLMError):
            err = e
        else:
            err = _classify_error(e, "gemini")

        logger.error("[CHAT] LLM call failed (%s): %s", err.kind, str(e)[:200])

        if err.kind == "quota":
            user_msg = (
                "FINN's AI engine has reached its request limit for today. Please try again tomorrow."
            )
        elif err.kind in ("auth", "model_not_found"):
            user_msg = (
                "FINN's conversational AI engine is temporarily unavailable. Please try again shortly."
            )
        else:
            user_msg = (
                "FINN encountered an issue processing your question. Please try again shortly."
            )

        # If we have context, return a grounded answer from cache
        if ctx:
            cache_reply = (
                f"Here is primary-source research context for **{ticker}**:\n\n"
                f"{ctx[:1800]}\n\n"
                f"_(Showing cached data — live conversational AI is temporarily unavailable.)_"
            )
            return {
                "response": cache_reply,
                "generated_at": datetime.now().isoformat(),
                "ticker_context": ticker or None,
                "context_used": True,
                "cached_fallback": True,
            }

        return {
            "response": user_msg,
            "generated_at": datetime.now().isoformat(),
            "ticker_context": ticker or None,
            "context_used": False,
        }
