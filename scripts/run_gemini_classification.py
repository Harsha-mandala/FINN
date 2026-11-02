import json
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('.env', override=True)

from backend.config import ROOT, GEMINI_API_KEY
from backend.services.classifier import (
    classify_batch_llm,
    classify_heuristic,
    assign_priority,
)

def main():
    snapshot_path = ROOT / "cache" / "announcements" / "_raw_2026-11-02.json"
    if not snapshot_path.exists():
        snapshot_path = ROOT / "cache" / "announcements" / "_classified_2026-11-02.json"

    with open(snapshot_path, encoding="utf-8") as f:
        items = json.load(f)

    print(f"Total announcements to classify: {len(items)}")
    print(f"Using GEMINI_API_KEY: {GEMINI_API_KEY[:6]}... (length: {len(GEMINI_API_KEY)})")

    batch_size = 25
    gemini_count = 0
    fallback_count = 0
    disagreements = []

    final_classified = []

    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(items) + batch_size - 1) // batch_size
        print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} items)...")

        # Get heuristic classifications first
        heur_results = [classify_heuristic(it) for it in batch]

        # Call Gemini cheap model
        llm_results = classify_batch_llm(batch)

        for idx, (item, (h_cat, h_sum), l_res) in enumerate(zip(batch, heur_results, llm_results)):
            g_cat = l_res.get("category", "unclassified")
            g_sum = l_res.get("summary", "")

            # Check if Gemini provided a classified result
            used_gemini = (g_cat != "unclassified")
            if used_gemini:
                gemini_count += 1
                final_cat = g_cat
                final_sum = g_sum or item.get("headline", "")
            else:
                fallback_count += 1
                final_cat = h_cat
                final_sum = h_sum or item.get("headline", "")

            # Disagreement check
            if h_cat != g_cat:
                disagreements.append({
                    "ticker": item.get("ticker", ""),
                    "headline": item.get("headline", "")[:90],
                    "heuristic_cat": h_cat,
                    "gemini_cat": g_cat,
                })

            priority, tier = assign_priority(final_cat)
            enriched_item = dict(item)
            enriched_item["category"] = final_cat
            enriched_item["summary"] = final_sum
            enriched_item["priority"] = priority
            enriched_item["priority_tier"] = tier
            enriched_item["classification_source"] = "gemini" if used_gemini else "heuristic"
            final_classified.append(enriched_item)

        # Sleep briefly between batches to respect 15 RPM
        time.sleep(1.0)

    # Save to _classified_2026-11-02.json
    out_path = ROOT / "cache" / "announcements" / "_classified_2026-11-02.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final_classified, f, indent=2)

    print("\n" + "="*80)
    print("CLASSIFICATION SUMMARY:")
    print("="*80)
    print(f"Total items: {len(items)}")
    print(f"Classified by Gemini: {gemini_count} ({gemini_count/len(items)*100:.1f}%)")
    print(f"Fallback to Heuristic: {fallback_count} ({fallback_count/len(items)*100:.1f}%)")
    print(f"Disagreements between Heuristic and Gemini: {len(disagreements)}")

    print("\n" + "="*80)
    print("DISAGREEMENT SAMPLES (Heuristic vs Gemini):")
    print("="*80)
    for d in disagreements[:20]:
        print(f"{d['ticker']:<12} | Heur: {d['heuristic_cat']:<16} | Gemini: {d['gemini_cat']:<16} | {d['headline']}")

    # Save disagreement table to json for reporting
    with open(ROOT / "cache" / "announcements" / "_disagreements.json", "w", encoding="utf-8") as f:
        json.dump(disagreements, f, indent=2)

if __name__ == "__main__":
    main()
