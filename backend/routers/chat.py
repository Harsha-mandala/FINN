"""
FINN — Chat Copilot Router
Endpoint: POST /chat
Uses Claude Sonnet with optional ticker context.
Renders structured cards when answering research questions.
"""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
import os
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from backend.config import ANTHROPIC_API_KEY, GEMINI_API_KEY, RESEARCH_CACHE
from backend.models.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = """
You are FINN, an expert financial investment intelligence agent for public-markets investors.
You provide high-conviction, evidence-backed answers using primary source financial data.

Guidelines:
- Be concise, analytical, and specific. No generic filler.
- Ground all company observations in reported financial numbers (revenue, margins, PAT, ROE, guidance).
- Clearly mention the reporting period when citing metrics (e.g., Q2 FY25, FY24).
- If information is not available in primary filings, state that clearly rather than speculating.
- Maintain an objective, disciplined institutional investor tone.
"""


def load_ticker_context(ticker: str) -> str:
    """Load research card context for a ticker, if available."""
    cache_dir = RESEARCH_CACHE / ticker
    card_cache = cache_dir / "_research_cards.json"

    if not card_cache.exists():
        return ""

    with open(card_cache) as f:
        data = json.load(f)

    cards = data.get("cards", [])
    if not cards:
        return ""

    # Build a compact context string from cards
    context_parts = [f"Primary source research context for {ticker}:"]
    for card in cards:
        card_type = card.get("card_type", "")
        content = card.get("data", {}).get("content", "")
        if content:
            context_parts.append(f"\n--- {card_type.upper().replace('_', ' ')} ---\n{content[:1500]}")

    return "\n".join(context_parts)


def call_gemini_api(system_prompt: str, user_prompt: str, api_key: str) -> str:
    """
    Call Gemini 1.5 Flash using either google-genai or google-generativeai SDK.
    """
    full_prompt = f"{system_prompt}\n\nUser Question: {user_prompt}"

    # Try 1: google-genai SDK
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        res = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=full_prompt,
        )
        if res and res.text:
            return res.text
    except Exception as e_new:
        print(f"google-genai call failed ({e_new}); falling back to google.generativeai...")

    # Try 2: legacy google.generativeai SDK
    try:
        import google.generativeai as legacy_genai
        legacy_genai.configure(api_key=api_key)
        model = legacy_genai.GenerativeModel("gemini-1.5-flash")
        res = model.generate_content(full_prompt)
        if res and res.text:
            return res.text
    except Exception as e_legacy:
        print(f"google.generativeai call failed: {e_legacy}")
        raise RuntimeError(f"Gemini API error: {e_legacy}")

    return "No text returned from Gemini."


@router.post("")
async def chat(request: ChatRequest):
    """
    Chat with FINN. Prioritizes Gemini / Claude when keys are configured,
    and falls back to primary-source research context if no keys are provided.
    """
    ticker = request.ticker
    ctx = load_ticker_context(ticker) if ticker else ""
    system = SYSTEM_PROMPT + (f"\n\n{ctx}" if ctx else "")

    last_user_msg = ""
    for m in reversed(request.messages):
        if m.role == "user":
            last_user_msg = m.content
            break

    # Resolve API keys dynamically from environment
    gemini_key = os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY
    anthropic_key = os.getenv("ANTHROPIC_API_KEY") or ANTHROPIC_API_KEY

    # 1. Prioritize Gemini if key is present
    if gemini_key:
        try:
            reply = call_gemini_api(system, last_user_msg, gemini_key)
            return {
                "response": reply,
                "generated_at": datetime.now().isoformat(),
                "ticker_context": ticker or None,
            }
        except Exception as e:
            print(f"Gemini error in chat router: {e}")
            return {
                "response": f"⚠️ Gemini API Error: {e}\n\nPlease check that your `GEMINI_API_KEY` is valid in Render's Environment Variables.",
                "generated_at": datetime.now().isoformat(),
                "ticker_context": ticker or None,
            }

    # 2. Try Claude if Anthropic key is present
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1024,
                system=system,
                messages=messages,
            )
            return {
                "response": response.content[0].text,
                "generated_at": datetime.now().isoformat(),
                "ticker_context": ticker or None,
            }
        except Exception as e:
            print(f"Claude error in chat router: {e}")
            return {
                "response": f"⚠️ Claude API Error: {e}",
                "generated_at": datetime.now().isoformat(),
                "ticker_context": ticker or None,
            }

    # 3. Grounded fallback when no API key is provided
    if ctx:
        reply = (
            f"**Analysis grounded in primary filings for {ticker}:**\n\n"
            f"Based on our extracted documents and latest corporate filings:\n\n"
            f"{ctx[:1200]}\n\n"
            f"*Tip: Set `GEMINI_API_KEY` in Render Environment Variables to enable live multi-turn conversational AI.*"
        )
    else:
        reply = (
            f"Hello! I am **FINN**, your financial investment intelligence agent.\n\n"
            f"- **Feed**: Select the Feed tab to see prioritized corporate filings.\n"
            f"- **Alerts**: Review triggered price moves (±5%) and volume spikes (≥2×).\n"
            f"- **Research**: Enter any NSE ticker (e.g., `PERSISTENT`, `RELIANCE`, `DMART`, `BAJFINANCE`) in the Research tab to view our 5-card analysis including **Promised vs. Delivered** accountability.\n\n"
            f"*Tip: Set `GEMINI_API_KEY` in Render Environment Variables to enable live conversational AI.*"
        )

    return {
        "response": reply,
        "generated_at": datetime.now().isoformat(),
        "ticker_context": ticker or None,
    }
