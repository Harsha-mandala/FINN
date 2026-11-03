#!/usr/bin/env python3
"""
FINN — Research Card Generation Script
=======================================
Executes the two-stage primary-source research pipeline for specified tickers.
Extracts guidance items and qualitative catalysts/risks using Gemini Flash Lite,
synthesizes 5 research cards using Gemini Flash reasoning model, and persists
results to cache/research/<ticker>/_research_cards.json.

Usage (run in terminal with GEMINI_API_KEY set in process env):
    python scripts/generate_research.py [TICKER]
    e.g. python scripts/generate_research.py RELIANCE.NS
         python scripts/generate_research.py PERSISTENT.NS
"""

import os
import sys
import json
import time
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def main():
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        print("GEMINI_API_KEY is not set in this terminal session. See README, 'Running snapshot jobs'.")
        sys.exit(1)

    from backend.services.researcher import build_research_cards
    from backend.llm import get_last_model_used

    # Pick target tickers from command line or default to targets
    if len(sys.argv) > 1:
        tickers = [sys.argv[1].upper()]
        if not tickers[0].endswith(".NS") and not tickers[0].endswith(".BO"):
            tickers[0] += ".NS"
    else:
        tickers = ["RELIANCE.NS", "PERSISTENT.NS"]

    print(f"[RESEARCH] Target tickers for generation: {tickers}")

    for ticker in tickers:
        print("\n" + "=" * 60)
        print(f"GENERATING RESEARCH CARDS FOR: {ticker}")
        print("=" * 60)

        t0 = time.time()
        res = build_research_cards(ticker=ticker, force=True)
        elapsed = time.time() - t0

        status = res.get("status")
        cards = res.get("cards", [])
        sources = res.get("sources_used", [])

        print(f"Status       : {status} (completed in {elapsed:.1f}s)")
        print(f"Cards Count  : {len(cards)}")
        print(f"Sources Used : {len(sources)} documents ({', '.join(sources)})")

        for idx, card in enumerate(cards, 1):
            ctype = card.get("card_type")
            model = card.get("provenance", {}).get("model_used", "Gemini")
            print(f"  [{idx}] {ctype.upper()} — Model: {model}")

        cache_out = ROOT / "cache" / "research" / ticker / "_research_cards.json"
        print(f"Cards persisted to: {cache_out.relative_to(ROOT)}")

    print("\n" + "=" * 60)
    print("RESEARCH GENERATION FINISHED")
    print("=" * 60)

if __name__ == "__main__":
    main()
