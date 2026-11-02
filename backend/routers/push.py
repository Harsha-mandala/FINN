"""
FINN — Push Router
Endpoints:
  GET /push/digest?window_hours=24&include_low=false
  GET /push/alerts?window_hours=24
  POST /push/alerts/settings
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse

from backend.config import (
    ANNOUNCEMENTS_CACHE,
    GEMINI_API_KEY,
    PORTFOLIO_TICKERS,
    HIGH_PRIORITY_CATEGORIES,
    MEDIUM_PRIORITY_CATEGORIES,
)
# Note: GEMINI_API_KEY used only to decide whether to attempt LLM classification
from backend.models.schemas import DigestResponse, AlertsResponse, AlertThresholds, Alert
from backend.services.classifier import classify_announcements
from backend.services.alerts import get_all_alerts
from backend.services.enricher import enrich_announcement

router = APIRouter(prefix="/push", tags=["push"])


def load_announcements(window_hours: int = 24) -> list[dict]:
    """Load raw announcements from cache, filtered by time window."""
    latest_path = ANNOUNCEMENTS_CACHE / "_latest.json"
    if not latest_path.exists():
        return []

    with open(latest_path) as f:
        data = json.load(f)

    return data.get("announcements", [])


def get_classified_announcements(window_hours: int = 24) -> list[dict]:
    """
    Load + classify announcements from cache.
    Uses a day-level cache to avoid re-classifying on every request.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    classified_cache = ANNOUNCEMENTS_CACHE / f"_classified_{today_str}.json"

    # Return cached classified if fresh
    if classified_cache.exists():
        with open(classified_cache) as f:
            return json.load(f)

    raw = load_announcements(window_hours)
    if not raw:
        return []

    classified = classify_announcements(raw, GEMINI_API_KEY or None)

    # Cache classified results
    with open(classified_cache, "w") as f:
        json.dump(classified, f, indent=2)

    return classified


@router.get("/digest")
async def get_digest(
    window_hours: int = Query(default=24, ge=1, le=720),
    include_low: bool = Query(default=False),
    tickers: Optional[str] = Query(default=None, description="Comma-separated tickers"),
):
    """
    Return a windowed digest of announcements, prioritised into high/medium/low tiers.
    Enriches high-priority items (results card, management bio).
    """
    ticker_filter = set(tickers.split(",")) if (tickers and isinstance(tickers, str)) else set(PORTFOLIO_TICKERS)
    classified = get_classified_announcements(window_hours)

    # Filter by ticker and tier
    high, medium, low = [], [], []

    for ann in classified:
        if ann.get("ticker") not in ticker_filter:
            continue

        tier = ann.get("priority_tier", "low")

        # Enrich high-priority items (results card, management bio)
        if tier == "high" and ann.get("category") in {"results", "management_change"}:
            try:
                ann = enrich_announcement(ann)
            except Exception as ex:
                import logging
                logging.getLogger(__name__).warning("[PUSH] Enrichment failed for %s: %s", ann.get("ticker"), ex)

        if tier == "high":
            high.append(ann)
        elif tier == "medium":
            medium.append(ann)
        else:
            low.append(ann)

    # Sort by priority score descending
    high.sort(key=lambda x: x.get("priority", 0), reverse=True)
    medium.sort(key=lambda x: x.get("priority", 0), reverse=True)

    return {
        "window_hours": window_hours,
        "generated_at": datetime.now().isoformat(),
        "high": high,
        "medium": medium,
        "low": low if include_low else [],
        "low_count": len(low),
        "total": len(high) + len(medium) + len(low),
    }


@router.get("/alerts")
async def get_alerts(
    window_hours: int = Query(default=24, ge=1, le=168),
    volume_multiple: float = Query(default=2.0, ge=1.0, le=20.0),
    price_move_pct: float = Query(default=5.0, ge=0.5, le=50.0),
    alert_categories: Optional[str] = Query(
        default=None,
        description="Comma-separated categories to watch"
    ),
):
    """Return triggered alerts for price moves, volume spikes, and key announcements."""
    categories = (
        alert_categories.split(",")
        if (alert_categories and isinstance(alert_categories, str))
        else list(HIGH_PRIORITY_CATEGORIES)
    )

    thresholds = AlertThresholds(
        volume_multiple=volume_multiple,
        price_move_pct=price_move_pct,
        alert_categories=categories,
    )

    alerts = get_all_alerts(thresholds=thresholds, window_hours=window_hours)

    return {
        "generated_at": datetime.now().isoformat(),
        "thresholds": thresholds.model_dump(),
        "alerts": [a.model_dump() for a in alerts],
        "count": len(alerts),
    }


@router.get("/prices")
async def get_prices(
    tickers: Optional[str] = Query(default=None),
):
    """Return latest EOD price summary for portfolio or specified tickers."""
    from backend.config import PRICES_CACHE

    summary_path = PRICES_CACHE / "_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=503, detail="Price data not yet loaded. Run the price scraper first.")

    with open(summary_path) as f:
        data = json.load(f)

    all_tickers = data.get("tickers", {})

    if tickers and isinstance(tickers, str):
        ticker_list = tickers.split(",")
        filtered = {k: v for k, v in all_tickers.items() if k in ticker_list}
    else:
        filtered = {k: v for k, v in all_tickers.items() if k in PORTFOLIO_TICKERS}

    return {
        "generated_at": data.get("generated_at"),
        "tickers": filtered,
    }


@router.get("/prices/{ticker}/history")
async def get_price_history(ticker: str):
    """Return full price history for a single ticker."""
    from backend.config import PRICES_CACHE

    # Normalise ticker
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = ticker + ".NS"

    path = PRICES_CACHE / f"{ticker}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No price data for {ticker}")

    with open(path) as f:
        return json.load(f)
