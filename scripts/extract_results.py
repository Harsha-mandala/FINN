#!/usr/bin/env python3
"""
FINN — Results Card Extraction Script
======================================
Builds structured results cards for quarterly financial results announcements.
Tries deterministic regex parsing first, falling back to Gemini vision on
complex or garbled PDF layouts.
Outputs cards as static JSON under cache/results/ for fast zero-LLM request serving.

Usage (run in terminal with GEMINI_API_KEY set in process env):
    python scripts/extract_results.py
"""

import os
import sys
import json
import time
from pathlib import Path
from collections import defaultdict, Counter
import pdfplumber
import pypdfium2 as pdfium
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def main():
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        print("GEMINI_API_KEY is not set in this terminal session. See README, 'Running snapshot jobs'.")
        sys.exit(1)

    from backend.services.results_card import (
        build_results_card,
        download_filing_pdf,
        parse_table_regex,
        extract_pdf_tables_text,
        RESULTS_DIR,
    )
    from backend.llm import gemini_generate_json, get_last_model_used

    ann_path = ROOT / "cache" / "announcements" / "_classified_2026-11-02.json"
    if not ann_path.exists():
        raw_files = sorted((ROOT / "cache" / "announcements").glob("_classified_*.json"))
        if raw_files:
            ann_path = raw_files[-1]
        else:
            print("[RESULTS] No classified announcements found. Run scripts/classify_snapshot.py first.")
            sys.exit(1)

    with open(ann_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    results_items = [it for it in items if it.get("category") == "results"]
    threads = defaultdict(list)
    for it in results_items:
        th_id = it.get("thread_id") or it.get("news_id")
        threads[th_id].append(it)

    print(f"[RESULTS] Found {len(results_items)} results filings across {len(threads)} unique threads.")

    model_requests = Counter()
    thread_report = []

    def run_vision_fallback(pdf_bytes):
        try:
            from google import genai
            from google.genai import types
            pdf = pdfium.PdfDocument(pdf_bytes)
            target_idx = None
            for i in range(min(25, len(pdf))):
                t = pdf.get_page(i).get_textpage().get_text_range()
                if any(k in t.lower() for k in ["statement of consolidated", "statement of audited", "statement of unaudited", "statement of standalone"]):
                    target_idx = i
                    if "consolidated" in t.lower():
                        break
            if target_idx is None:
                return None

            img = pdf[target_idx].render(scale=2.0).to_pil()
            key = os.environ.get("GEMINI_API_KEY", "").strip()
            client = genai.Client(api_key=key)
            prompt = """Extract the quarterly financial results from this table for the three columns:
- Current Quarter
- Previous Quarter
- Year-ago Quarter

Extract:
1. Period name (e.g. Q2 FY27)
2. Basis (consolidated or standalone)
3. Revenue from operations
4. Other income
5. Profit before tax (PBT)
6. Profit for the period (PAT)
7. Finance costs
8. Depreciation and amortisation expense

Return ONLY JSON:
{
  "period": "...",
  "basis": "consolidated" or "standalone",
  "currency": "INR",
  "unit": "Crore" or "Lakhs",
  "current_q": {"revenue": ..., "pbt": ..., "pat": ..., "finance_costs": ..., "depreciation": ...},
  "prev_q": {"revenue": ..., "pbt": ..., "pat": ...},
  "year_ago_q": {"revenue": ..., "pbt": ..., "pat": ...}
}"""
            model_requests["gemini-3.5-flash-lite"] += 1
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[img, prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(response.text)
        except Exception as e:
            return None

    for th_id, att_list in threads.items():
        ticker = att_list[0].get("ticker", "UNKNOWN")
        headline = att_list[0].get("headline", "")[:60]
        parsed_card = None
        method = "unavailable"

        # Try attachments
        for att in att_list:
            url = att.get("attachment_url")
            if not url:
                continue
            res = download_filing_pdf(url)
            if not res:
                continue
            pdf_bytes, file_hash = res

            # Try regex first
            extracted_text = extract_pdf_tables_text(pdf_bytes)
            if extracted_text:
                regex_res = parse_table_regex(extracted_text, ticker=ticker)
                if regex_res and regex_res.get("revenue", {}).get("current") is not None:
                    card = build_results_card(ticker, regex_res, url, th_id)
                    parsed_card = card
                    method = "regex"
                    break

            # If regex failed, try Gemini vision fallback
            vision_res = run_vision_fallback(pdf_bytes)
            if vision_res and vision_res.get("current_q", {}).get("revenue") is not None:
                curr = vision_res.get("current_q", {})
                prev = vision_res.get("prev_q", {})
                yoy = vision_res.get("year_ago_q", {})

                def _delta(c, b):
                    if c is not None and b is not None and b != 0:
                        return round(((c - b) / abs(b)) * 100, 2)
                    return None

                pbt = curr.get("pbt")
                fin = curr.get("finance_costs") or 0
                dep = curr.get("depreciation") or 0
                ebitda = round(pbt + fin + dep, 2) if pbt is not None else None

                parsed_data = {
                    "period": vision_res.get("period", "Q2 FY27"),
                    "basis": vision_res.get("basis", "consolidated"),
                    "revenue": {"current": curr.get("revenue"), "prev_q": prev.get("revenue"), "year_ago": yoy.get("revenue"), "qoq_pct": _delta(curr.get("revenue"), prev.get("revenue")), "yoy_pct": _delta(curr.get("revenue"), yoy.get("revenue"))},
                    "ebitda": {"current": ebitda, "prev_q": None, "year_ago": None, "qoq_pct": None, "yoy_pct": None},
                    "pbt": {"current": curr.get("pbt"), "prev_q": prev.get("pbt"), "year_ago": yoy.get("pbt"), "qoq_pct": _delta(curr.get("pbt"), prev.get("pbt")), "yoy_pct": _delta(curr.get("pbt"), yoy.get("pbt"))},
                    "pat": {"current": curr.get("pat"), "prev_q": prev.get("pat"), "year_ago": yoy.get("pat"), "qoq_pct": _delta(curr.get("pat"), prev.get("pat")), "yoy_pct": _delta(curr.get("pat"), yoy.get("pat"))},
                    "source": "gemini_vision_fallback",
                }
                card = build_results_card(ticker, parsed_data, url, th_id)
                parsed_card = card
                method = "gemini_vision"
                break

        status_str = "PASS" if parsed_card and method != "unavailable" else "LINK_ONLY"
        thread_report.append({
            "thread_id": th_id,
            "ticker": ticker,
            "headline": headline,
            "method": method,
            "status": status_str,
        })
        print(f"[{status_str}] Thread {th_id} ({ticker}): {method}")

    print("\n" + "=" * 60)
    print("RESULTS EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"Total Threads Processed : {len(thread_report)}")
    print(f"Parsed via Regex        : {sum(1 for r in thread_report if r['method'] == 'regex')}")
    print(f"Parsed via Gemini Vision: {sum(1 for r in thread_report if r['method'] == 'gemini_vision')}")
    print(f"Link-Only / Intimations : {sum(1 for r in thread_report if r['status'] == 'LINK_ONLY')}")
    print("\nAPI Request Counts per Model:")
    for m, c in model_requests.items():
        print(f"  - {m}: {c} requests")
    print("=" * 60)

if __name__ == "__main__":
    main()
