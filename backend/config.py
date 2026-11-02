"""
FINN — Backend Config
Loads environment variables and defines all app settings.
All LLM model names come from env vars; nothing is hardcoded in app code.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ── API Keys ──────────────────────────────────────────────────────────────────

def get_gemini_key() -> str:
    key = (
        os.getenv("GEMINI_API_KEY", "")
        or os.getenv("GOOGLE_API_KEY", "")
        or os.getenv("GOOGLE_GENAI_API_KEY", "")
    )
    return key.strip().strip('"').strip("'")


GEMINI_API_KEY: str = get_gemini_key()

# ── LLM Model Selection ───────────────────────────────────────────────────────
# Route by task to spread quota across per-model daily limits:
#
#  GEMINI_CHEAP_MODEL  : bulk tasks — classification, per-doc extraction, chat
#  GEMINI_MODEL        : reasoning tasks — Stage-2 research synthesis, grounded bios
#  GEMINI_FALLBACK_MODELS : comma-separated list tried in order on 429/quota
#
# Defaults target the highest-RPD models visible on the free tier.
# Override any of these in .env or via Render environment variables.

GEMINI_CHEAP_CHAIN: list[str] = [
    m.strip()
    for m in os.getenv(
        "GEMINI_CHEAP_CHAIN",
        "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash-lite",
    ).split(",")
    if m.strip()
]
GEMINI_CHEAP_MODEL: str = GEMINI_CHEAP_CHAIN[0] if GEMINI_CHEAP_CHAIN else "gemini-3.5-flash-lite"

GEMINI_REASONING_CHAIN: list[str] = [
    m.strip()
    for m in os.getenv(
        "GEMINI_REASONING_CHAIN",
        "gemini-2.5-flash,gemini-3-flash,gemini-3.6-flash,gemini-3.8-flash",
    ).split(",")
    if m.strip()
]
GEMINI_MODEL: str = GEMINI_REASONING_CHAIN[0] if GEMINI_REASONING_CHAIN else "gemini-2.5-flash"

GEMINI_FALLBACK_MODELS: list[str] = [
    m for m in (GEMINI_CHEAP_CHAIN[1:] + GEMINI_REASONING_CHAIN[1:])
    if m not in (GEMINI_MODEL, GEMINI_CHEAP_MODEL)
]

# ── Cache paths ───────────────────────────────────────────────────────────────
CACHE_DIR = ROOT / "cache"
PRICES_CACHE = CACHE_DIR / "prices"
ANNOUNCEMENTS_CACHE = CACHE_DIR / "announcements"
DOCUMENTS_CACHE = CACHE_DIR / "documents"
RESEARCH_CACHE = CACHE_DIR / "research"

# ── Portfolio ──────────────────────────────────────────────────────────────────
PORTFOLIO_TICKERS = [
    "RELIANCE.NS", "HDFCBANK.NS", "INFY.NS", "TCS.NS", "ICICIBANK.NS",
    "SUNPHARMA.NS", "TRENT.NS", "POLYCAB.NS", "DIXON.NS", "HBLPOWER.NS",
    "KALYANKJIL.NS", "CAMS.NS", "LALPATHLAB.NS", "ASTRAL.NS", "ZOMATO.NS",
    "IRCTC.NS", "CDSL.NS", "IDEAFORGE.NS",
]

AD_HOC_TICKERS = [
    "PERSISTENT.NS", "DMART.NS", "BAJFINANCE.NS", "MOTHERSON.NS",
]

ALL_TICKERS = PORTFOLIO_TICKERS + AD_HOC_TICKERS

# ── Announcement priority rules ───────────────────────────────────────────────
PRIORITY_MAP = {
    "results": 90,
    "M&A": 85,
    "management_change": 80,
    "litigation": 75,
    "fund_raise": 70,
    "credit_rating": 60,
    "capex": 55,
    "pledging": 50,
    "press_release": 45,
    "insider_trading": 40,
    "dividend": 38,
    "bonus_split": 25,
    "postal_ballot": 20,
    "agm_egm": 20,
    "investor_meetings": 15,
    "earnings_call": 15,
    "unclassified": 5,
}

# Priority tiers
HIGH_PRIORITY_CATEGORIES = {"results", "M&A", "management_change", "litigation", "fund_raise"}
MEDIUM_PRIORITY_CATEGORIES = {"credit_rating", "capex", "pledging", "press_release", "insider_trading", "dividend"}
LOW_PRIORITY_CATEGORIES = {"bonus_split", "postal_ballot", "agm_egm", "investor_meetings", "earnings_call", "unclassified"}

# ── Default alert thresholds ──────────────────────────────────────────────────
DEFAULT_VOLUME_MULTIPLE = 2.0   # alert if volume > X × 20d avg
DEFAULT_PRICE_MOVE_PCT = 5.0    # alert if |price change| > X%
DEFAULT_ALERT_CATEGORIES = list(HIGH_PRIORITY_CATEGORIES)

# ── CORS ──────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "https://finn-seven-lyart.vercel.app",
    os.getenv("FRONTEND_URL", ""),
]
