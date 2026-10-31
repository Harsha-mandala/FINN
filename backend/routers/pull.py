"""
FINN — Pull Router (Research)
Endpoints:
  POST /pull/research  { ticker: "RELIANCE.NS", force_refresh: false }
  GET  /pull/research/{ticker}
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from backend.models.schemas import ResearchRequest, ResearchResponse
from backend.services.researcher import build_research_cards

router = APIRouter(prefix="/pull", tags=["pull"])

# Track tickers currently being researched (avoid parallel duplicate calls)
_in_progress: set[str] = set()


@router.post("/research")
async def start_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    """
    Start research for a ticker. Returns cached result immediately if available.
    For fresh requests, kicks off the pipeline and returns a 202 with status.
    """
    ticker = request.ticker.upper()
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = ticker + ".NS"

    # Check cache first
    if not request.force_refresh:
        result = build_research_cards(ticker, force=False)
        if result.get("cards"):
            return {"status": "ready", "ticker": ticker, **result}

    if ticker in _in_progress:
        return {"status": "in_progress", "ticker": ticker, "message": "Research in progress, check back shortly."}

    # Try to build synchronously for demo (fast if already extracted)
    _in_progress.add(ticker)
    try:
        result = build_research_cards(ticker, force=request.force_refresh)
        if result.get("error"):
            raise HTTPException(status_code=422, detail=result["error"])
        return {"status": "ready", "ticker": ticker, **result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _in_progress.discard(ticker)


@router.get("/research/{ticker}")
async def get_research(ticker: str, force_refresh: bool = False):
    """Get research cards for a ticker (GET convenience method)."""
    ticker = ticker.upper()
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = ticker + ".NS"

    result = build_research_cards(ticker, force=force_refresh)
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    return {"status": "ready", "ticker": ticker, **result}
