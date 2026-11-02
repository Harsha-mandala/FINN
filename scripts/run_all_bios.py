import sys
import os
import json
import io
import pdfplumber

sys.path.insert(0, os.path.abspath("."))
import backend.config
from backend.services.results_card import download_filing_pdf
from backend.services.enricher import get_management_bio, _extract_person_hint

def main():
    with open("cache/announcements/_classified_2026-11-02.json", "r", encoding="utf-8") as f:
        items = json.load(f)

    mgmt_items = [it for it in items if it.get("category") == "management_change"]
    print(f"Total management_change announcements: {len(mgmt_items)}")

    report = []
    for idx, it in enumerate(mgmt_items):
        ticker = it.get("ticker")
        headline = it.get("headline")
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
                        # Extract first 3 pages
                        pdf_text = "\n".join([p.extract_text() or "" for p in pdf.pages[:3]])
                except Exception as e:
                    print(f"  Error reading PDF: {e}")
        
        # Combine headline + filing text
        combined_text = f"{headline}\n{pdf_text}".strip()
        print(f"  Combined text length: {len(combined_text)} chars")

        bio = get_management_bio(
            company=ticker.replace(".NS", ""),
            filing_text=combined_text[:1200],
            allow_network=True,
        )

        status = "GENERATED" if bio else "NO_PERSON_IDENTIFIED"
        entry = {
            "idx": idx + 1,
            "ticker": ticker,
            "headline": headline,
            "status": status,
            "bio": bio,
        }
        report.append(entry)
        if bio:
            print(f"  SUCCESS: {bio.get('person_name')} - {bio.get('role')}")
            print(f"  Sources: {bio.get('sources')}")
        else:
            print(f"  NO BIO (Cleanly omitted)")

    with open("cache/research/_bios_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

if __name__ == "__main__":
    main()
