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
from backend.config import ANTHROPIC_API_KEY, GEMINI_API_KEY, RESEARCH_CACHE
from backend.models.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = """
You are FINN, a financial intelligence assistant for an investor.
You help investors understand their portfolio companies using primary source data.

Guidelines:
- Be concise and specific. No filler, no AI slop.
- When answering about a specific company, reference source documents (annual reports, concall transcripts).
- Do NOT make up financial numbers. Say "I don't have that data" if uncertain.
- Format responses with clear headers and bullet points where appropriate.
- For financial metrics, always state the period (e.g., Q2 FY25, FY24).
- When the user asks to "dig deeper" on something, provide structured analysis with citations.

You have access to research cards for companies in the portfolio. Use that context when provided.
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
    context_parts = [f"Research context for {ticker}:"]
    for card in cards:
        card_type = card.get("card_type", "")
        content = card.get("data", {}).get("content", "")
        if content:
            context_parts.append(f"\n--- {card_type.upper().replace('_', ' ')} ---\n{content[:1500]}")

    return "\n".join(context_parts)


@router.post("")
async def chat(request: ChatRequest):
    """
    Chat with FINN. Uses Claude Sonnet if available, falls back to Gemini Flash,
    or synthesizes from research cards if API keys are not provided.
    """
    ticker = request.ticker
    ctx = load_ticker_context(ticker) if ticker else ""
    system = SYSTEM_PROMPT + (f"\n\n{ctx}" if ctx else "")

    last_user_msg = ""
    for m in reversed(request.messages):
        if m.role == "user":
            last_user_msg = m.content
            break

    # 1. Try Claude if key present
    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
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
            print(f"Claude chat error: {e}")

    # 2. Try Gemini if key present
    if GEMINI_API_KEY:
        try:
            from google import genai
            from google.genai import types as genai_types
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=f"{system}\n\nUser Question: {last_user_msg}",
            )
            return {
                "response": response.text,
                "generated_at": datetime.now().isoformat(),
                "ticker_context": ticker or None,
            }
        except Exception as e:
            print(f"Gemini chat error: {e}")

    # 3. Grounded fallback using local research context
    if ctx:
        reply = (
            f"**Analysis grounded in primary filings for {ticker}:**\n\n"
            f"Based on our extracted documents and latest corporate filings:\n\n"
            f"{ctx[:1200]}\n\n"
            f"*To enable conversational multi-turn Q&A, provide your `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` in the `.env` file.*"
        )
    else:
        reply = (
            f"Hello! I am **FINN**, your financial investment intelligence agent.\n\n"
            f"- **Portfolio Digest**: Select the Feed tab to see prioritized corporate announcements.\n"
            f"- **Alerts**: Review triggered price moves and volume spikes on the Alerts tab.\n"
            f"- **Research**: Enter any NSE ticker (e.g., `PERSISTENT`, `RELIANCE`, `DMART`, `BAJFINANCE`) in the Research tab to view our 5-card analysis including **Promised vs. Delivered** accountability.\n\n"
            f"*Tip: To activate live conversational AI, add your `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` in `.env`.*"
        )

    return {
        "response": reply,
        "generated_at": datetime.now().isoformat(),
        "ticker_context": ticker or None,
    }
