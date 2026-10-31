"""
FINN — Price & Volume Scraper
Fetches end-of-day price + volume for portfolio tickers via yfinance.
Computes:
  - 1-day % price change
  - 20-day average volume
  - Volume ratio (today / 20d avg)
Output: cache/prices/<TICKER>.json (one file per ticker, full 6-month history)
        cache/prices/_summary.json (latest EOD snapshot for all tickers — used by alerts engine)
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf
import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "cache" / "prices"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Portfolio tickers ────────────────────────────────────────────────────────
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


def fetch_ticker(ticker: str, period_days: int = 180) -> dict | None:
    """
    Fetch OHLCV for the last `period_days` days.
    Returns a dict with history list and computed metrics, or None on failure.
    """
    try:
        end = datetime.today()
        start = end - timedelta(days=period_days)
        t = yf.Ticker(ticker)
        df = t.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))

        if df.empty:
            print(f"  [WARN] No data for {ticker}")
            return None

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = df.index.tz_localize(None)  # remove timezone for JSON serialisation
        df.index = df.index.strftime("%Y-%m-%d")

        # ── Compute metrics on the latest trading day ────────────────────────
        close_series = df["Close"]
        vol_series = df["Volume"]

        latest_date = df.index[-1]
        latest_close = float(close_series.iloc[-1])
        prev_close = float(close_series.iloc[-2]) if len(close_series) >= 2 else latest_close
        price_change_pct = round((latest_close - prev_close) / prev_close * 100, 2)

        vol_20d_avg = float(vol_series.iloc[-21:-1].mean()) if len(vol_series) > 20 else float(vol_series.mean())
        latest_vol = float(vol_series.iloc[-1])
        vol_ratio = round(latest_vol / vol_20d_avg, 2) if vol_20d_avg > 0 else 1.0

        # ── Build output ─────────────────────────────────────────────────────
        history = [
            {
                "date": date,
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            }
            for date, row in df.iterrows()
        ]

        result = {
            "ticker": ticker,
            "fetched_at": datetime.now().isoformat(),
            "latest_date": latest_date,
            "latest_close": latest_close,
            "prev_close": prev_close,
            "price_change_pct": price_change_pct,
            "volume_latest": int(latest_vol),
            "volume_20d_avg": round(vol_20d_avg, 0),
            "volume_ratio": vol_ratio,
            "history": history,
        }

        return result

    except Exception as e:
        print(f"  [ERROR] {ticker}: {e}")
        return None


def run(tickers: list[str] | None = None):
    """Fetch prices for all tickers and write cache files."""
    targets = tickers or ALL_TICKERS
    summary = {}

    for ticker in targets:
        print(f"Fetching {ticker}...")
        data = fetch_ticker(ticker)
        if data:
            out_path = CACHE_DIR / f"{ticker}.json"
            with open(out_path, "w") as f:
                json.dump(data, f, indent=2)
            # Summary entry (no history list — keep it lean)
            summary[ticker] = {k: v for k, v in data.items() if k != "history"}
            print(f"  OK {ticker}: {data['latest_close']} ({data['price_change_pct']:+.2f}%) "
                  f"vol_ratio={data['volume_ratio']}")
        else:
            summary[ticker] = {"ticker": ticker, "error": "fetch_failed"}

    # Write summary
    summary_path = CACHE_DIR / "_summary.json"
    with open(summary_path, "w") as f:
        json.dump({"generated_at": datetime.now().isoformat(), "tickers": summary}, f, indent=2)
    print(f"\n✅ Price summary written to {summary_path}")


if __name__ == "__main__":
    # Optionally pass ticker list as args: python prices.py RELIANCE.NS TCS.NS
    custom = sys.argv[1:] if len(sys.argv) > 1 else None
    run(custom)
