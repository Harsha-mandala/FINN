"""
FINN — Pydantic Schemas
All request/response models for the API.
"""

from typing import Optional, Literal
from pydantic import BaseModel


# ── Price / Market Data ───────────────────────────────────────────────────────

class PricePoint(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class TickerSummary(BaseModel):
    ticker: str
    latest_date: str
    latest_close: float
    prev_close: float
    price_change_pct: float
    volume_latest: int
    volume_20d_avg: float
    volume_ratio: float


# ── Announcements ─────────────────────────────────────────────────────────────

class Announcement(BaseModel):
    ticker: str
    source: str  # "BSE" or "NSE"
    headline: str
    category: str  # FINN classification
    category_raw: str
    priority: int  # 0-100
    priority_tier: Literal["high", "medium", "low"]
    date: str
    attachment_url: Optional[str] = None
    news_id: Optional[str] = None
    summary: Optional[str] = None  # AI one-liner
    enrichment: Optional[dict] = None  # results card, bio, etc.
    sub_items: Optional[list[dict]] = None  # threaded sub-announcements
    thread_count: Optional[int] = None  # total items in thread


class DigestRequest(BaseModel):
    window_hours: int = 24  # default 24h
    window: Optional[str] = "24h"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    tickers: Optional[list[str]] = None  # None = all portfolio
    include_low: bool = False  # whether to include low-priority in response


class DigestResponse(BaseModel):
    window: str = "24h"
    window_hours: int
    data_as_of: Optional[str] = None
    generated_at: str
    high: list[Announcement]
    medium: list[Announcement]
    low: list[Announcement]
    routine_summary: Optional[dict] = None
    low_count: int = 0
    total: int


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertThresholds(BaseModel):
    volume_multiple: float = 2.0
    price_move_pct: float = 5.0
    alert_categories: list[str] = ["results", "M&A", "management_change", "litigation", "fund_raise"]


class Alert(BaseModel):
    ticker: str
    alert_type: Literal["price_move", "volume_spike", "announcement"]
    triggered_at: str
    description: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    announcement: Optional[Announcement] = None


class AlertsResponse(BaseModel):
    generated_at: str
    thresholds: AlertThresholds
    alerts: list[Alert]


# ── Research (Pull) ───────────────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    ticker: str  # any NSE ticker, e.g. "RELIANCE.NS"
    force_refresh: bool = False


class GuidanceItem(BaseModel):
    metric: str
    statement: str
    value: Optional[str] = None
    timeframe: Optional[str] = None
    speaker: Optional[str] = None
    confidence: str  # "explicit" or "implied"
    source_period: str  # which concall this came from


class PromisingVsDelivered(BaseModel):
    guidance_period: str
    metric: str
    promised: str
    delivered: Optional[str] = None
    verdict: Literal["met", "missed", "partial", "pending", "ambiguous"]
    evidence: str  # brief explanation


class ResearchCard(BaseModel):
    card_type: Literal[
        "snapshot", "trajectory", "guidance", "promised_vs_delivered", "bull_bear"
    ]
    ticker: str
    company_name: str
    generated_at: str
    data: dict  # card-specific payload


class ResearchResponse(BaseModel):
    ticker: str
    company_name: str
    generated_at: str
    cards: list[ResearchCard]
    sources_used: list[str]  # list of document names used


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    ticker: Optional[str] = None  # if set, load context for this ticker
    context_type: Optional[str] = None  # "announcement", "research", etc.


class ChatResponse(BaseModel):
    response: str
    cards: Optional[list[dict]] = None  # structured cards in the response
    sources: Optional[list[str]] = None
