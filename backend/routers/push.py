"""
FINN — Push Router
Endpoints:
  GET /push/digest?window_hours=24&include_low=false
  GET /push/alerts?window_hours=24
  POST /push/alerts/settings
"""

import json
import logging
import re
from datetime import datetime, timedelta
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
from backend.models.schemas import DigestResponse, AlertsResponse, AlertThresholds, Alert
from backend.services.classifier import classify_announcements
from backend.services.alerts import get_all_alerts
from backend.services.enricher import enrich_announcement

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/push", tags=["push"])


def parse_ann_date(date_str: str) -> Optional[datetime]:
    """Parse announcement date string into a datetime object."""
    if not date_str:
        return None
    s = str(date_str).strip()[:19]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def thread_announcements(items: list[dict]) -> list[dict]:
    """
    Group announcements for the same ticker + related event into a thread.
    Results intimation, outcome, and financial results become one thread with
    the most informative item as the headline and the rest in sub_items.
    """
    groups: dict[str, list[dict]] = {}
    standalone: list[dict] = []

    for ann in items:
        ticker = ann.get("ticker", "")
        cat = ann.get("category", "")
        headline = ann.get("headline", "").lower()

        # Thread results / board meetings for results
        if cat == "results" or "board meeting" in headline or "financial results" in headline:
            quarter_match = re.search(r"q[1-4]|quarter|half year|september 30|june 30|december 31|march 31", headline)
            q_key = quarter_match.group(0) if quarter_match else "general_results"
            thread_key = f"{ticker}:results:{q_key}"
            groups.setdefault(thread_key, []).append(ann)
        else:
            standalone.append(ann)

    threaded: list[dict] = []

    def informativeness(a: dict) -> int:
        h = a.get("headline", "").lower()
        if "unaudited financial results" in h or "audited financial results" in h or "financial results" in h:
            return 100
        if "board meeting outcome" in h or "outcome of board meeting" in h:
            return 80
        if "board meeting intimation" in h or "intimation of board meeting" in h:
            return 60
        return 40

    for thread_key, group in groups.items():
        if len(group) == 1:
            standalone.append(group[0])
            continue

        # Sort: most informative first, then newest date
        group_sorted = sorted(
            group,
            key=lambda x: (informativeness(x), x.get("date", "")),
            reverse=True,
        )
        primary = group_sorted[0].copy()
        sub_items = [
            {
                "headline": other.get("headline", ""),
                "date": other.get("date", ""),
                "attachment_url": other.get("attachment_url"),
                "news_id": other.get("news_id"),
                "category": other.get("category"),
            }
            for other in group_sorted[1:]
        ]
        primary["sub_items"] = sub_items
        primary["thread_count"] = 1 + len(sub_items)
        threaded.append(primary)

    return threaded + standalone


def load_raw_announcements() -> list[dict]:
    """Load all raw announcements from latest cache snapshot."""
    latest_path = ANNOUNCEMENTS_CACHE / "_latest.json"
    if not latest_path.exists():
        return []

    with open(latest_path) as f:
        data = json.load(f)

    return data.get("announcements", [])


def get_classified_announcements() -> list[dict]:
    """
    Load + classify announcements from cache.
    Uses a day-level cache to avoid re-classifying on every request.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    classified_cache = ANNOUNCEMENTS_CACHE / f"_classified_{today_str}.json"

    if classified_cache.exists():
        try:
            with open(classified_cache) as f:
                return json.load(f)
        except Exception:
            pass

    raw = load_raw_announcements()
    if not raw:
        return []

    classified = classify_announcements(raw, GEMINI_API_KEY or None)

    try:
        with open(classified_cache, "w") as f:
            json.dump(classified, f, indent=2)
    except Exception as e:
        logger.warning("[PUSH] Could not cache classified announcements: %s", e)

    return classified


@router.get("/digest")
def get_digest(
    window: str = Query(default="24h", description="24h, 7d, 30d, or custom"),
    window_hours: Optional[int] = Query(default=None, ge=1, le=720),
    start_date: Optional[str] = Query(default=None, description="ISO date for custom start"),
    end_date: Optional[str] = Query(default=None, description="ISO date for custom end"),
    include_low: bool = Query(default=False),
    tickers: Optional[str] = Query(default=None, description="Comma-separated tickers"),
):
    """
    Return a windowed digest of announcements strictly filtered by time window.
    Window options: 24h, 7d, 30d, or custom (with start_date and end_date).
    Threads related announcements for the same event.
    Enriches high-priority items with QoQ/YoY results cards or management bios.
    """
    ticker_filter = set(tickers.split(",")) if (tickers and isinstance(tickers, str)) else set(PORTFOLIO_TICKERS)
    raw = load_raw_announcements()

    # Determine latest announcement timestamp across entire snapshot for data_as_of
    all_dates = [parse_ann_date(ann.get("date")) for ann in raw if ann.get("date")]
    valid_dates = [d for d in all_dates if d is not None]
    data_as_of = max(valid_dates).isoformat() if valid_dates else None

    # Handle direct function call vs FastAPI Query object defaults
    win_str = window if isinstance(window, str) else "24h"
    start_str = start_date if isinstance(start_date, str) else None
    end_str = end_date if isinstance(end_date, str) else None

    now = datetime.now()
    if win_str == "custom" and start_str:
        start_dt = parse_ann_date(start_str) or (now - timedelta(days=7))
        end_dt = parse_ann_date(end_str) if end_str else now
    elif win_str == "7d" or (isinstance(window_hours, int) and window_hours == 168):
        start_dt = now - timedelta(days=7)
        end_dt = now
    elif win_str == "30d" or (isinstance(window_hours, int) and window_hours == 720):
        start_dt = now - timedelta(days=30)
        end_dt = now
    else:  # default 24h
        h = window_hours if isinstance(window_hours, int) else 24
        start_dt = now - timedelta(hours=h)
        end_dt = now

    classified = get_classified_announcements()

    # Strict window & ticker filtering
    high, medium, low = [], [], []

    for ann in classified:
        if ann.get("ticker") not in ticker_filter:
            continue

        ann_dt = parse_ann_date(ann.get("date"))
        if not ann_dt:
            continue

        # Strict window filter: must be within [start_dt, end_dt + 5min]
        if ann_dt < start_dt or ann_dt > (end_dt + timedelta(minutes=5)):
            continue

        tier = ann.get("priority_tier", "low")

        if tier == "high":
            # Enrich high-priority items from cache (results card, management bio)
            if ann.get("category") in {"results", "management_change"}:
                try:
                    ann = enrich_announcement(ann, allow_network=False)
                except Exception as ex:
                    logger.warning("[PUSH] Enrichment failed for %s: %s", ann.get("ticker"), ex)
            high.append(ann)
        elif tier == "medium":
            medium.append(ann)
        else:
            low.append(ann)

    # Apply event threading / deduplication per tier
    threaded_high = thread_announcements(high)
    threaded_medium = thread_announcements(medium)

    # Sort descending by priority score and timestamp
    threaded_high.sort(key=lambda x: (x.get("priority", 0), x.get("date", "")), reverse=True)
    threaded_medium.sort(key=lambda x: (x.get("priority", 0), x.get("date", "")), reverse=True)

    effective_hours = int((end_dt - start_dt).total_seconds() / 3600)

    return {
        "window": win_str,
        "window_hours": effective_hours,
        "data_as_of": data_as_of,
        "generated_at": now.isoformat(),
        "high": threaded_high,
        "medium": threaded_medium,
        "low": low if (include_low is True) else [],
        "routine_summary": {
            "count": len(low),
            "label": f"{len(low)} routine filings",
        },
        "low_count": len(low),
        "total": len(threaded_high) + len(threaded_medium) + len(low),
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
