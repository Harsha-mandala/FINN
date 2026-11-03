#!/usr/bin/env python3
"""
FINN — Grounded Management Bio Generation Script
=================================================
Processes management_change corporate announcements, extracts executive name/role
from the PDF filing text, and generates a grounded executive biography using
Google Search grounding on Gemini.
Stores bios with source citations under cache/research/_bios/<hash>.json.

Usage (run in terminal with GEMINI_API_KEY set in process env):
    python scripts/generate_bios.py
"""

import os
import sys
import json
import io
from pathlib import Path
from collections import Counter
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def main():
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        print("GEMINI_API_KEY is not set in this terminal session. See README, 'Running snapshot jobs'.")
        sys.exit(1)

    from backend.services.results_card import download_filing_pdf
    from backend.services.enricher import get_management_bio, _extract_person_hint
    from backend.llm import get_last_model_used

    ann_path = ROOT / "cache" / "announcements" / "_classified_2026-11-02.json"
    if not ann_path.exists():
        raw_files = sorted((ROOT / "cache" / "announcements").glob("_classified_*.json"))
        if raw_files:
            ann_path = raw_files[-1]
        else:
            print("[BIOS] No classified announcements found. Run scripts/classify_snapshot.py first.")
            sys.exit(1)

    with open(ann_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    mgmt_items = [it for it in items if it.get("category") == "management_change"]
    print(f"[BIOS] Total management_change announcements: {len(mgmt_items)}")

    model_requests = Counter()
    generated_count = 0
    skipped_count = 0

    for idx, it in enumerate(mgmt_items):
        ticker = it.get("ticker", "UNKNOWN")
        headline = it.get("headline", "")
        url = it.get("attachment_url")
        news_id = it.get("news_id")

        print(f"\n[{idx+1}/{len(mgmt_items)}] Processing {ticker}: {headline[:60]}...")

        pdf_text = ""
        if url:
            res = download_filing_pdf(url)
            if res:
                pdf_bytes, file_hash = res
                try:
                    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                        pdf_text = "\n".join([p.extract_text() or "" for p in pdf.pages[:3]])
                except Exception as e:
                    print(f"  Warning: PDF read failed: {e}")

        combined_text = f"{headline}\n{pdf_text}".strip()

        bio = get_management_bio(
            company=ticker.replace(".NS", ""),
            filing_text=combined_text[:1200],
            allow_network=True,
        )

        if bio and bio.get("name"):
            generated_count += 1
            model_used = get_last_model_used()
            model_requests[model_used] += 1
            print(f"  [SUCCESS] Generated bio for: {bio.get('name')} ({bio.get('role')})")
            print(f"  Sources : {len(bio.get('grounding_sources', []))} URLs cited")
        else:
            skipped_count += 1
            print(f"  [SKIPPED] No executive person identified from filing text.")

    print("\n" + "=" * 60)
    print("MANAGEMENT BIOS REPORT")
    print("=" * 60)
    print(f"Total Announcements   : {len(mgmt_items)}")
    print(f"Bios Generated        : {generated_count}")
    print(f"Skipped / Hidden      : {skipped_count}")
    print("\nAPI Request Counts per Model:")
    for m, c in model_requests.items():
        print(f"  - {m}: {c} requests")
    print("=" * 60)

if __name__ == "__main__":
    main()
