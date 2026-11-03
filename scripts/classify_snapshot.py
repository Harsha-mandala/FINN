#!/usr/bin/env python3
"""
FINN — Gemini Announcement Classification Script
=================================================
Classifies recent announcements in batches using Gemini Flash Lite model.
Falls back to heuristic rules if unclassified or on rate limits.
Outputs classified items to cache/announcements/_classified_<date>.json.

Usage (run in terminal with GEMINI_API_KEY set in process env):
    python scripts/classify_snapshot.py
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def main():
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        print("GEMINI_API_KEY is not set in this terminal session. See README, 'Running snapshot jobs'.")
        sys.exit(1)

    from backend.config import ANNOUNCEMENTS_CACHE
    from backend.services.classifier import (
        classify_batch_llm,
        classify_heuristic,
        assign_priority,
    )
    from backend.llm import get_last_model_used

    # Locate latest raw or classified snapshot
    raw_files = sorted(ANNOUNCEMENTS_CACHE.glob("_raw_*.json"))
    classified_files = sorted(ANNOUNCEMENTS_CACHE.glob("_classified_*.json"))

    if raw_files:
        snapshot_path = raw_files[-1]
    elif classified_files:
        snapshot_path = classified_files[-1]
    else:
        print("[CLASSIFIER] No announcements snapshot found. Run scripts/refresh_snapshot.py first.")
        sys.exit(1)

    print(f"[CLASSIFIER] Loading snapshot: {snapshot_path.name}")
    with open(snapshot_path, encoding="utf-8") as f:
        items = json.load(f)

    print(f"[CLASSIFIER] Total announcements to classify: {len(items)}")

    batch_size = 25
    gemini_count = 0
    fallback_count = 0
    model_requests = Counter()
    disagreements = []
    final_classified = []

    start_time = time.time()
    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(items) + batch_size - 1) // batch_size
        print(f"[CLASSIFIER] Processing batch {batch_num}/{total_batches} ({len(batch)} items)...")

        # Heuristic baseline
        heur_results = [classify_heuristic(it) for it in batch]

        # Gemini cheap batch call
        llm_results = classify_batch_llm(batch)
        model_used = get_last_model_used()
        model_requests[model_used] += 1

        for item, (h_cat, h_sum), l_res in zip(batch, heur_results, llm_results):
            g_cat = l_res.get("category", "unclassified")
            g_sum = l_res.get("summary", "")

            used_gemini = (g_cat != "unclassified")
            if used_gemini:
                gemini_count += 1
                final_cat = g_cat
                final_sum = g_sum or item.get("headline", "")
            else:
                fallback_count += 1
                final_cat = h_cat
                final_sum = h_sum or item.get("headline", "")

            # Check disagreement between Gemini and Heuristic
            if used_gemini and g_cat != h_cat:
                disagreements.append({
                    "ticker": item.get("ticker"),
                    "headline": item.get("headline")[:80],
                    "heuristic_label": h_cat,
                    "gemini_label": g_cat,
                })

            priority = assign_priority(final_cat, item.get("headline", ""), item.get("ticker", ""))
            enriched_item = dict(item)
            enriched_item["category"] = final_cat
            enriched_item["summary"] = final_sum
            enriched_item["priority"] = priority
            enriched_item["classification_source"] = "gemini" if used_gemini else "heuristic_fallback"
            enriched_item["classified_model"] = model_used if used_gemini else None
            final_classified.append(enriched_item)

    elapsed = time.time() - start_time
    today_str = datetime.now().strftime("%Y-%m-%d")
    out_file = ANNOUNCEMENTS_CACHE / f"_classified_{today_str}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(final_classified, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("CLASSIFICATION REPORT")
    print("=" * 60)
    print(f"Elapsed Time           : {elapsed:.1f}s")
    print(f"Total Items            : {len(items)}")
    print(f"Classified by Gemini   : {gemini_count} ({gemini_count / len(items) * 100:.1f}%)")
    print(f"Fallback to Heuristic  : {fallback_count} ({fallback_count / len(items) * 100:.1f}%)")
    print(f"Output Saved To        : {out_file.name}")
    print("\nAPI Request Counts per Model:")
    for model, count in model_requests.items():
        print(f"  - {model}: {count} requests")
    print("=" * 60)

    if disagreements:
        print(f"\nTop Disagreements (Gemini vs Heuristic) — {len(disagreements)} total:")
        for d in disagreements[:10]:
            print(f"  [{d['ticker']}] \"{d['headline']}...\"")
            print(f"    Heuristic: {d['heuristic_label']} | Gemini: {d['gemini_label']}")

if __name__ == "__main__":
    main()
