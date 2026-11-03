"""
FINN — Pull Router (Research & Overview)
=========================================
Endpoints:
  GET  /pull/overview/{ticker} : Instant cached baseline overview (zero LLM calls)
  GET  /pull/research/{ticker} : Structured 5-card research report (reads cache)
  POST /pull/research          : On-demand research generation (rate-capped, queued)
"""

import os
import json
import logging
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks

from backend.config import (
    CACHE_DIR,
    PRICES_CACHE,
    ANNOUNCEMENTS_CACHE,
    DOCUMENTS_CACHE,
    RESEARCH_CACHE,
    ALL_TICKERS,
)
from backend.models.schemas import (
    ResearchRequest,
    ResearchResponse,
    TickerOverviewResponse,
)
from backend.services.researcher import build_research_cards

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pull", tags=["pull"])

RESULTS_CACHE = CACHE_DIR / "results"
RESEARCH_DAILY_LIMIT = int(os.getenv("MAX_DAILY_RESEARCH_GENERATIONS", "3"))

# Mutex to ensure single generation at a time
_generation_lock = threading.Lock()
_in_progress: set[str] = set()

# Daily quota tracking file
_RESEARCH_USAGE_FILE = CACHE_DIR / "_research_daily_usage.json"


def _normalize_ticker(t: str) -> str:
    t = t.strip().upper()
    if not t.endswith(".NS") and not t.endswith(".BO"):
        t += ".NS"
    return t


def _get_daily_usage() -> dict:
    today = date.today().isoformat()
    if _RESEARCH_USAGE_FILE.exists():
        try:
            data = json.loads(_RESEARCH_USAGE_FILE.read_text(encoding="utf-8"))
            if data.get("date") == today:
                return data
        except Exception:
            pass
    return {"date": today, "count": 0, "tickers": []}


def _increment_daily_usage(ticker: str):
    data = _get_daily_usage()
    data["count"] += 1
    if ticker not in data["tickers"]:
        data["tickers"].append(ticker)
    try:
        _RESEARCH_USAGE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("[PULL] Could not save research usage: %s", e)


# ── Baseline Overview (Reads Cache Only — No Key Required) ─────────────────────

@router.get("/overview/{ticker}")
def get_ticker_overview(ticker: str):
    """
    Returns baseline multi-layer overview for a ticker using cached data only:
    - Latest results card (from filing) with Revenue, EBITDA/bank equivalents, PBT, PAT
    - Price & volume with 6-month sparkline
    - Primary documents (annual reports, concalls)
    - Recent high/medium priority filings
    """
    norm_ticker = _normalize_ticker(ticker)
    comp_name = norm_ticker.replace(".NS", "").replace(".BO", "")

    # 1. Latest results card from cache/results/
    latest_results = None
    if RESULTS_CACHE.exists():
        matching_results = []
        for p in RESULTS_CACHE.glob("*.json"):
            if p.name.startswith("_"):
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("ticker") == norm_ticker:
                    matching_results.append(data)
            except Exception:
                continue
        # Prefer 'ok' status cards
        ok_cards = [c for c in matching_results if c.get("status") == "ok"]
        if ok_cards:
            latest_results = ok_cards[0]
        elif matching_results:
            latest_results = matching_results[0]

    # 2. Price & volume from cache/prices/
    price_volume = None
    price_file = PRICES_CACHE / f"{norm_ticker}.json"
    if price_file.exists():
        try:
            pdata = json.loads(price_file.read_text(encoding="utf-8"))
            history = pdata.get("history", [])
            # 6-month sparkline (up to last 125 trading days)
            sparkline = [pt.get("close") for pt in history[-125:] if pt.get("close") is not None]
            price_volume = {
                "latest_date": pdata.get("latest_date"),
                "latest_close": pdata.get("latest_close"),
                "prev_close": pdata.get("prev_close"),
                "price_change_pct": pdata.get("price_change_pct"),
                "volume_latest": pdata.get("volume_latest"),
                "volume_20d_avg": pdata.get("volume_20d_avg"),
                "volume_ratio": pdata.get("volume_ratio"),
                "sparkline": sparkline,
            }
        except Exception as e:
            logger.warning("[PULL] Could not load price data for %s: %s", norm_ticker, e)
    primary_documents = []
    links_file = DOCUMENTS_CACHE / norm_ticker / "links.json"
    if links_file.exists():
        try:
            ldata = json.loads(links_file.read_text(encoding="utf-8"))
            for item in ldata.get("selected", []):
                primary_documents.append({
                    "title": item.get("title", "Document"),
                    "type": item.get("type", "document"),
                    "url": item.get("url", ""),
                    "year": item.get("year"),
                    "date": item.get("date"),
                })
        except Exception:
            pass

    # If no links.json, list any local PDFs in documents cache
    if not primary_documents:
        ticker_docs_dir = DOCUMENTS_CACHE / norm_ticker
        if ticker_docs_dir.exists():
            for pdf_p in sorted(ticker_docs_dir.glob("*.pdf")):
                name = pdf_p.name
                doc_type = "concall_transcript" if "concall" in name.lower() or "transcript" in name.lower() else "results_filing"
                primary_documents.append({
                    "title": name.replace(".pdf", "").replace("_", " "),
                    "type": doc_type,
                    "url": f"/documents/{norm_ticker}/{name}",
                    "date": None,
                    "year": None,
                })

    # 4. Recent filings for this ticker from announcements cache
    recent_filings = []
    ann_files = sorted(ANNOUNCEMENTS_CACHE.glob("_classified_*.json"))
    if not ann_files:
        ann_files = sorted(ANNOUNCEMENTS_CACHE.glob("_raw_*.json"))

    if ann_files:
        try:
            items = json.loads(ann_files[-1].read_text(encoding="utf-8"))
            ticker_items = [
                it for it in items
                if it.get("ticker") == norm_ticker
            ]
            # Prioritize high and medium priority items
            sorted_items = sorted(
                ticker_items,
                key=lambda x: (x.get("priority", 0), x.get("date", "")),
                reverse=True,
            )
            for it in sorted_items[:5]:
                recent_filings.append({
                    "headline": it.get("headline"),
                    "category": it.get("category"),
                    "priority": it.get("priority"),
                    "priority_tier": it.get("priority_tier", "medium"),
                    "date": it.get("date"),
                    "attachment_url": it.get("attachment_url"),
                    "news_id": it.get("news_id"),
                })
        except Exception as e:
            logger.warning("[PULL] Could not load announcements for %s: %s", norm_ticker, e)

    # 5. Check if deep research cards already exist
    research_file = RESEARCH_CACHE / norm_ticker / "_research_cards.json"
    has_deep_research = False
    if research_file.exists():
        try:
            rdata = json.loads(research_file.read_text(encoding="utf-8"))
            if rdata.get("cards"):
                has_deep_research = True
        except Exception:
            pass

    return {
        "ticker": norm_ticker,
        "company_name": comp_name,
        "latest_results": latest_results,
        "price_volume": price_volume,
        "primary_documents": primary_documents,
        "recent_filings": recent_filings,
        "has_deep_research": has_deep_research,
        "generated_at": datetime.now().isoformat(),
    }


# ── Structured Research (Pull) ────────────────────────────────────────────────

@router.get("/research/{ticker}")
async def get_research(ticker: str, force_refresh: bool = False):
    """
    Get structured 5-card research for a ticker.
    Reads from cache by default.
    """
    norm_ticker = _normalize_ticker(ticker)
    result = build_research_cards(norm_ticker, force=force_refresh)
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    return {"status": result.get("status", "ok"), "ticker": norm_ticker, **result}


@router.post("/research")
async def start_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    """
    On-demand research generation button endpoint.
    Guarded by:
    - Daily generation cap (default 3 per day) to protect free quota
    - Single-flight concurrency lock (processes one at a time)
    - Re-uses cached report if already available
    """
    norm_ticker = _normalize_ticker(request.ticker)

    # Check cache first if not explicitly forced
    if not request.force_refresh:
        cached = build_research_cards(norm_ticker, force=False)
        if cached.get("cards"):
            return {"status": "ready", "ticker": norm_ticker, **cached}

    # Check daily generation cap
    usage = _get_daily_usage()
    if usage["count"] >= RESEARCH_DAILY_LIMIT:
        # Check if we can at least return existing cached cards
        cached = build_research_cards(norm_ticker, force=False)
        if cached.get("cards"):
            return {
                "status": "limit_reached",
                "message": "Daily research limit reached. Showing available data.",
                "ticker": norm_ticker,
                **cached,
            }
        return {
            "status": "limit_reached",
            "message": "Daily research limit reached. Showing available data.",
            "ticker": norm_ticker,
            "cards": [],
        }

    # Check if another generation is currently running
    if norm_ticker in _in_progress or not _generation_lock.acquire(blocking=False):
        return {
            "status": "in_progress",
            "ticker": norm_ticker,
            "message": "Research generation is in progress. Please wait a moment.",
        }

    _in_progress.add(norm_ticker)
    try:
        result = build_research_cards(norm_ticker, force=True)
        if result.get("status") == "ok" and result.get("cards"):
            _increment_daily_usage(norm_ticker)
        return {"status": "ready", "ticker": norm_ticker, **result}
    except Exception as e:
        logger.error("[PULL] Research generation error for %s: %s", norm_ticker, e)
        raise HTTPException(status_code=500, detail="Research generation encountered an issue.")
    finally:
        _in_progress.discard(norm_ticker)
        try:
            _generation_lock.release()
        except RuntimeError:
            pass
