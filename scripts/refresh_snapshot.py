"""
FINN — Snapshot Refresh Script
================================
Refreshes live market data and exchange announcements from public sources:
1. BSE corporate announcements (last 30 days) for all portfolio & ad-hoc tickers
   using browser-compatible HTTP client (curl_cffi).
2. End-of-day price and volume data via yfinance.

Run this script anytime before a demo to refresh live data:
    python scripts/refresh_snapshot.py
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Set root directory
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("refresh_snapshot")


def refresh_announcements(days_back: int = 30):
    logger.info("--- 1. Refreshing BSE Announcements (last %d days) ---", days_back)
    from data_pipeline.scrapers.announcements import run as run_announcements
    run_announcements(days_back=days_back)
    logger.info("Announcements refresh complete.")


def refresh_prices():
    logger.info("--- 2. Refreshing EOD Prices & Volumes via yfinance ---")
    from data_pipeline.scrapers.prices import run as run_prices
    run_prices()
    logger.info("Price data refresh complete.")


def main():
    start_time = datetime.now()
    logger.info("Starting FINN snapshot refresh at %s...", start_time.isoformat())

    try:
        refresh_announcements(days_back=30)
    except Exception as e:
        logger.error("Announcement refresh encountered an error: %s", e)

    try:
        refresh_prices()
    except Exception as e:
        logger.error("Price refresh encountered an error: %s", e)

    duration = (datetime.now() - start_time).total_seconds()
    logger.info("Snapshot refresh finished in %.1f seconds.", duration)


if __name__ == "__main__":
    main()
