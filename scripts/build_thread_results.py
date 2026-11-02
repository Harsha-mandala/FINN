import sys
import os
import json
from pathlib import Path
from collections import defaultdict
import pdfplumber
import pypdfium2 as pdfium
from PIL import Image

sys.path.insert(0, os.path.abspath("."))
import backend.config
from backend.services.results_card import (
    build_results_card,
    download_filing_pdf,
    parse_table_regex,
    extract_pdf_tables_text,
    RESULTS_DIR,
)
from backend.llm import gemini_generate_json, get_last_model_used

def run_vision_extraction(pdf_bytes):
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
        client = genai.Client()
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
8. Depreciation

Return valid JSON:
{
  "found": true,
  "basis": "consolidated",
  "period_current": "Q2 FY27",
  "units": "Rs. Crore",
  "revenue": {"current": 0.0, "previous": 0.0, "year_ago": 0.0},
  "pbt": {"current": 0.0, "previous": 0.0, "year_ago": 0.0},
  "pat": {"current": 0.0, "previous": 0.0, "year_ago": 0.0},
  "finance_cost": {"current": 0.0, "previous": 0.0, "year_ago": 0.0},
  "depreciation": {"current": 0.0, "previous": 0.0, "year_ago": 0.0}
}
If no financial results table is on this page, return {"found": false}.
"""
        resp = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[img, prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0)
        )
        data = json.loads(resp.text)
        if data.get("found"):
            data["method"] = "gemini_vision"
            data["model_used"] = "gemini-3.5-flash-lite"
            return data
    except Exception as e:
        print("Vision extraction error:", e)
    return None

def main():
    with open("cache/announcements/_classified_2026-11-02.json", "r", encoding="utf-8") as f:
        items = json.load(f)

    results_items = [it for it in items if it.get("category") == "results"]
    
    # Group by (ticker, date[:10])
    threads = defaultdict(list)
    for it in results_items:
        key = (it.get("ticker"), it.get("date", "")[:10])
        threads[key].append(it)

    print(f"Total results items: {len(results_items)}")
    print(f"Total unique filing threads: {len(threads)}")

    thread_results = []
    regex_pass_count = 0
    gemini_pass_count = 0
    failed_threads = 0

    for (ticker, dt), atts in threads.items():
        print(f"\nProcessing Thread: {ticker} on {dt} ({len(atts)} attachments)...")
        # Sort attachments: prioritize "Results" or "Outcome" over "Presentation"
        def _prio(a):
            h = a.get("headline", "").lower()
            if "financial results" in h or "unaudited" in h or "audited" in h:
                return 0
            if "outcome" in h:
                return 1
            return 2
        
        sorted_atts = sorted(atts, key=_prio)
        parsed_card = None
        method_used = None

        for att in sorted_atts:
            url = att.get("attachment_url")
            nid = att.get("news_id")
            h = att.get("headline")
            if not url:
                continue

            # Try regex or gemini text
            card = build_results_card(
                ticker=ticker,
                filing_url=url,
                news_id=nid,
                headline=h,
                allow_download=True,
            )

            if card.get("status") == "ok":
                parsed_card = card
                method_used = card.get("extraction_method", "regex")
                print(f"  Passed on attachment {nid[:8]} via {method_used}!")
                break
            else:
                # If regex and text failed, try vision on garbled pages
                dl = download_filing_pdf(url)
                if dl:
                    vis_data = run_vision_extraction(dl[0])
                    if vis_data and vis_data.get("found"):
                        # compute deltas in Python
                        from backend.services.results_card import _compute_card_from_extracted
                        card = _compute_card_from_extracted(ticker, vis_data, url, h)
                        if card.get("status") == "ok":
                            card["extraction_method"] = "gemini_vision"
                            card["model_used"] = "gemini-3.5-flash-lite"
                            parsed_card = card
                            method_used = "gemini_vision"
                            # cache under news_id
                            (RESULTS_DIR / f"{nid}.json").write_text(json.dumps(card), encoding="utf-8")
                            print(f"  Passed on attachment {nid[:8]} via gemini_vision!")
                            break

        if parsed_card:
            if method_used == "regex":
                regex_pass_count += 1
            else:
                gemini_pass_count += 1
            
            # Save card for ALL news_ids in this thread so digest finds it whichever attachment is displayed
            for att in atts:
                nid = att.get("news_id")
                (RESULTS_DIR / f"{nid}.json").write_text(json.dumps(parsed_card), encoding="utf-8")
            
            thread_results.append({
                "ticker": ticker,
                "date": dt,
                "status": "PASS",
                "method": method_used,
                "period": parsed_card.get("period_current"),
                "basis": parsed_card.get("basis"),
                "attachments_count": len(atts),
            })
        else:
            failed_threads += 1
            thread_results.append({
                "ticker": ticker,
                "date": dt,
                "status": "UNAVAILABLE",
                "method": "none",
                "period": "-",
                "basis": "-",
                "attachments_count": len(atts),
            })
            print(f"  Thread failed across all {len(atts)} attachments.")

    print("\n================ THREAD EVALUATION SUMMARY ================")
    print(f"Total Threads: {len(threads)}")
    print(f"Passed: {len(threads) - failed_threads} / {len(threads)} ({(len(threads)-failed_threads)/len(threads)*100:.1f}%)")
    print(f"  - Regex Pass: {regex_pass_count}")
    print(f"  - Gemini Text/Vision Pass: {gemini_pass_count}")
    print(f"Unavailable Threads: {failed_threads}")

    with open("cache/results/_thread_evaluation.json", "w", encoding="utf-8") as f:
        json.dump(thread_results, f, indent=2)

if __name__ == "__main__":
    main()
