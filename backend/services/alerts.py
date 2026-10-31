"""
FINN — EOD Alerts Engine
Rules-based engine over end-of-day price/volume data and classified announcements.
Generates alerts when thresholds are crossed.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import (
    PRICES_CACHE,
    ANNOUNCEMENTS_CACHE,
    DEFAULT_VOLUME_MULTIPLE,
    DEFAULT_PRICE_MOVE_PCT,
    DEFAULT_ALERT_CATEGORIES,
    PORTFOLIO_TICKERS,
)
from backend.models.schemas import Alert, AlertThresholds


def load_price_summary() -> dict:
    """Load latest EOD price summary from cache."""
    path = PRICES_CACHE / "_summary.json"
    if not path.exists():
        return {}
    with open(path) as f:
        data = json.load(f)
    return data.get("tickers", {})


def load_latest_announcements(window_hours: int = 24) -> list[dict]:
    """Load announcements from the latest cache snapshot within window_hours."""
    path = ANNOUNCEMENTS_CACHE / "_latest.json"
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)

    all_anns = data.get("announcements", [])

    # Filter by time window if dates are available
    # Announcements dates are strings — we do a best-effort parse
    cutoff = datetime.now().timestamp() - (window_hours * 3600)
    filtered = []
    for ann in all_anns:
        date_str = ann.get("date", "")
        try:
            # Try common formats
            for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d"]:
                try:
                    dt = datetime.strptime(date_str[:19], fmt)
                    if dt.timestamp() >= cutoff:
                        filtered.append(ann)
                    break
                except ValueError:
                    continue
            else:
                filtered.append(ann)  # can't parse date → include
        except Exception:
            filtered.append(ann)

    return filtered


def check_price_alerts(
    price_summary: dict,
    thresholds: AlertThresholds,
    tickers: Optional[list[str]] = None,
) -> list[Alert]:
    """Generate price move and volume spike alerts."""
    alerts = []
    targets = tickers or PORTFOLIO_TICKERS
    now = datetime.now().isoformat()

    for ticker in targets:
        data = price_summary.get(ticker)
        if not data or data.get("error"):
            continue

        price_change = data.get("price_change_pct", 0.0)
        vol_ratio = data.get("volume_ratio", 1.0)

        # Price move alert
        if abs(price_change) >= thresholds.price_move_pct:
            direction = "up" if price_change > 0 else "down"
            alerts.append(Alert(
                ticker=ticker,
                alert_type="price_move",
                triggered_at=now,
                description=(
                    f"{ticker.replace('.NS', '')} moved {price_change:+.1f}% "
                    f"({direction}) — threshold ±{thresholds.price_move_pct}%"
                ),
                value=price_change,
                threshold=thresholds.price_move_pct,
            ))

        # Volume spike alert
        if vol_ratio >= thresholds.volume_multiple:
            alerts.append(Alert(
                ticker=ticker,
                alert_type="volume_spike",
                triggered_at=now,
                description=(
                    f"{ticker.replace('.NS', '')} volume is {vol_ratio:.1f}× its 20-day average "
                    f"(threshold: {thresholds.volume_multiple}×)"
                ),
                value=vol_ratio,
                threshold=thresholds.volume_multiple,
            ))

    return alerts


def check_announcement_alerts(
    announcements: list[dict],
    thresholds: AlertThresholds,
) -> list[Alert]:
    """Generate alerts for high-priority announcement categories."""
    alerts = []
    now = datetime.now().isoformat()
    seen_news_ids = set()

    for ann in announcements:
        category = ann.get("category", "unclassified")
        news_id = ann.get("news_id", "")

        if category not in thresholds.alert_categories:
            continue
        if news_id and news_id in seen_news_ids:
            continue
        seen_news_ids.add(news_id)

        alerts.append(Alert(
            ticker=ann.get("ticker", ""),
            alert_type="announcement",
            triggered_at=ann.get("date", now),
            description=ann.get("summary", ann.get("headline", ""))[:200],
            announcement=ann,
        ))

    return alerts


def get_all_alerts(
    thresholds: Optional[AlertThresholds] = None,
    window_hours: int = 24,
    tickers: Optional[list[str]] = None,
) -> list[Alert]:
    """Get all triggered alerts — price, volume, and announcement."""
    if thresholds is None:
        thresholds = AlertThresholds()

    price_summary = load_price_summary()
    announcements = load_latest_announcements(window_hours)

    price_alerts = check_price_alerts(price_summary, thresholds, tickers)
    ann_alerts = check_announcement_alerts(announcements, thresholds)

    all_alerts = price_alerts + ann_alerts

    # Sort by severity — price moves first, then announcement alerts, then volume
    type_order = {"price_move": 0, "announcement": 1, "volume_spike": 2}
    all_alerts.sort(key=lambda a: type_order.get(a.alert_type, 99))

    return all_alerts
