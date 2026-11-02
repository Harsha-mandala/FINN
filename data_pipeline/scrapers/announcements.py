"""
FINN — BSE/NSE Announcement Scraper
Fetches corporate announcements for portfolio tickers.

Strategy (in order):
1. BSE unofficial JSON API (fastest, most reliable)
2. NSE unofficial JSON API
3. Falls back to pre-committed snapshot (demo-safe)

Output: cache/announcements/<TICKER>_<DATE>.json
        cache/announcements/_latest.json (merged, all tickers, last 7 days)

IMPORTANT: Always snapshot to disk immediately. The demo reads from cache.
"""

import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from curl_cffi import requests
except ImportError:
    import requests  # type: ignore

from tenacity import retry, stop_after_attempt, wait_exponential

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "cache" / "announcements"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Ticker → Exchange code mappings ─────────────────────────────────────────
# BSE uses numeric codes; NSE uses ticker symbols without .NS
# BSE scrip codes for our portfolio
BSE_CODES = {
    "RELIANCE.NS":   "500325",
    "HDFCBANK.NS":   "500180",
    "INFY.NS":       "500209",
    "TCS.NS":        "532540",
    "ICICIBANK.NS":  "532174",
    "SUNPHARMA.NS":  "524715",
    "TRENT.NS":      "500251",
    "POLYCAB.NS":    "542652",
    "DIXON.NS":      "540699",
    "HBLPOWER.NS":   "517271",
    "KALYANKJIL.NS": "543278",
    "CAMS.NS":       "543232",
    "LALPATHLAB.NS": "539524",
    "ASTRAL.NS":     "532830",
    "ZOMATO.NS":     "543320",
    "IRCTC.NS":      "542830",
    "CDSL.NS":       "540704",
    "IDEAFORGE.NS":  "543932",
    # Ad-hoc
    "PERSISTENT.NS": "533179",
    "DMART.NS":      "540376",
    "BAJFINANCE.NS": "500034",
    "MOTHERSON.NS":  "517334",
}

NSE_SYMBOLS = {
    ticker: ticker.replace(".NS", "") for ticker in BSE_CODES.keys()
}

# ── HTTP session with browser-like headers ───────────────────────────────────
def make_session() -> requests.Session:
    try:
        s = requests.Session(impersonate="chrome120")
    except TypeError:
        s = requests.Session()
    s.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.bseindia.com/",
    })
    return s


# ── BSE API ──────────────────────────────────────────────────────────────────
BSE_BASE = "https://api.bseindia.com/BseIndiaAPI/api"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_bse_announcements(
    scrip_code: str,
    from_date: str,  # DD/MM/YYYY
    to_date: str,
    session: requests.Session,
) -> list[dict]:
    """Fetch announcements from BSE API for a scrip code."""
    url = f"{BSE_BASE}/AnnSubCategoryGetData/w"
    params = {
        "strCat": "-1",
        "strPrevDate": from_date,
        "strScrip": scrip_code,
        "strSearch": "P",
        "strToDate": to_date,
        "strType": "C",
    }
    resp = session.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    announcements = []
    for item in data.get("Table", []):
        announcements.append({
            "source": "BSE",
            "scrip_code": scrip_code,
            "headline": item.get("NEWSSUB", ""),
            "category_raw": item.get("CATEGORYNAME", ""),
            "subcategory_raw": item.get("SUBCATNAME", ""),
            "date": item.get("News_submission_dt", ""),
            "attachment_url": (
                f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{item.get('ATTACHMENTNAME', '')}"
                if item.get("ATTACHMENTNAME") else None
            ),
            "news_id": item.get("NEWSID", ""),
        })

    return announcements


# ── NSE API ──────────────────────────────────────────────────────────────────
NSE_BASE = "https://www.nseindia.com/api"

def get_nse_cookies(session: requests.Session) -> bool:
    """Prime NSE cookies by visiting the main page first."""
    try:
        session.headers.update({"Referer": "https://www.nseindia.com/"})
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)
        return True
    except Exception:
        return False


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=15))
def fetch_nse_announcements(
    symbol: str,
    session: requests.Session,
) -> list[dict]:
    """Fetch recent announcements from NSE API for a symbol."""
    url = f"{NSE_BASE}/corp-announcements"
    params = {"index": "equities", "symbol": symbol}
    resp = session.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    announcements = []
    for item in data:
        announcements.append({
            "source": "NSE",
            "symbol": symbol,
            "headline": item.get("subject", ""),
            "category_raw": item.get("desc", ""),
            "subcategory_raw": "",
            "date": item.get("bcastDt", ""),
            "attachment_url": item.get("attchmntFile", None),
            "news_id": item.get("an_no", ""),
        })
    return announcements


# ── Main fetch logic ──────────────────────────────────────────────────────────
def fetch_announcements_for_ticker(
    ticker: str,
    days_back: int = 30,
    session: Optional[requests.Session] = None,
) -> list[dict]:
    """
    Try BSE first, then NSE. Tag each announcement with the ticker.
    """
    if session is None:
        session = make_session()

    today = datetime.today()
    from_dt = today - timedelta(days=days_back)
    from_str = from_dt.strftime("%Y%m%d")
    to_str = today.strftime("%Y%m%d")

    announcements = []

    # 1. Try BSE
    if ticker in BSE_CODES:
        try:
            print(f"  [BSE] Fetching {ticker}...")
            items = fetch_bse_announcements(BSE_CODES[ticker], from_str, to_str, session)
            for item in items:
                item["ticker"] = ticker
            announcements = items
            print(f"  [OK] BSE: {len(announcements)} announcements")
        except Exception as e:
            print(f"  [WARN] BSE failed for {ticker}: {e}")

    # 2. Fall back to NSE only if BSE failed completely (optional, non-blocking)
    if not announcements and ticker in NSE_SYMBOLS:
        try:
            items = fetch_nse_announcements(NSE_SYMBOLS[ticker], session)
            for item in items:
                item["ticker"] = ticker
            announcements = items
        except Exception:
            pass  # Non-blocking fallback

    if not announcements:
        print(f"  [WARN] No announcements fetched for {ticker}. Check snapshot fallback.")

    return announcements


def run(tickers: list[str] | None = None, days_back: int = 30):
    """Fetch announcements for all tickers and write cache."""
    from data_pipeline.scrapers.prices import ALL_TICKERS  # noqa: reuse list
    # Inline to avoid import issues when running standalone
    _ALL_TICKERS = [
        "RELIANCE.NS", "HDFCBANK.NS", "INFY.NS", "TCS.NS", "ICICIBANK.NS",
        "SUNPHARMA.NS", "TRENT.NS", "POLYCAB.NS", "DIXON.NS", "HBLPOWER.NS",
        "KALYANKJIL.NS", "CAMS.NS", "LALPATHLAB.NS", "ASTRAL.NS", "ZOMATO.NS",
        "IRCTC.NS", "CDSL.NS", "IDEAFORGE.NS",
        "PERSISTENT.NS", "DMART.NS", "BAJFINANCE.NS", "MOTHERSON.NS",
    ]
    targets = tickers or _ALL_TICKERS
    session = make_session()
    all_announcements = []
    today_str = datetime.today().strftime("%Y-%m-%d")

    for ticker in targets:
        print(f"\nFetching announcements for {ticker}...")
        items = fetch_announcements_for_ticker(ticker, days_back=days_back, session=session)

        if items:
            # Write per-ticker snapshot
            out_path = CACHE_DIR / f"{ticker}_{today_str}.json"
            with open(out_path, "w") as f:
                json.dump({
                    "ticker": ticker,
                    "fetched_at": datetime.now().isoformat(),
                    "days_back": days_back,
                    "count": len(items),
                    "announcements": items,
                }, f, indent=2, default=str)
            all_announcements.extend(items)

        # Polite delay — avoid rate limiting
        time.sleep(1.5)

    # Write merged latest snapshot
    latest_path = CACHE_DIR / "_latest.json"
    with open(latest_path, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "days_back": days_back,
            "total": len(all_announcements),
            "announcements": all_announcements,
        }, f, indent=2, default=str)

    print(f"\n[OK] {len(all_announcements)} total announcements written to {latest_path}")


if __name__ == "__main__":
    custom = sys.argv[1:] if len(sys.argv) > 1 else None
    days = 30
    run(custom, days_back=days)
