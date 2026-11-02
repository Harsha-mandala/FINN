import sys
import os
import json
from pathlib import Path
import pdfplumber

sys.path.insert(0, os.path.abspath("."))

with open("cache/filings/_url_map.json", "r", encoding="utf-8") as f:
    url_map = json.load(f)

targets = [
    {
        "name": "INFY bbfbd1a4 (Consolidated)",
        "url": "https://www.bseindia.com/xml-data/corpfiling/AttachLive/7a7cacec-6e60-4f88-9c95-ad60962ad4d4.pdf",
        "page_target": 18,
    },
    {
        "name": "TCS 47fe4353 (Consolidated)",
        "url": "https://www.bseindia.com/xml-data/corpfiling/AttachLive/2b021530-bbc2-4590-8375-cefc205a7132.pdf",
        "page_target": 8,
    },
    {
        "name": "ICICI Bank 2871e7ba (Bank)",
        "url": "https://www.bseindia.com/xml-data/corpfiling/AttachLive/cbd56dbf-e0e2-444e-9793-b261a8e0e05e.pdf",
        "page_target": None,
    },
    {
        "name": "ideaForge e55bc95f (Small-cap)",
        "url": "https://www.bseindia.com/xml-data/corpfiling/AttachLive/c389a59c-42c7-43bd-8222-3b190444ab64.pdf",
        "page_target": None,
    },
    {
        "name": "CAMS 122ce105 (Small/Mid-cap)",
        "url": "https://www.bseindia.com/xml-data/corpfiling/AttachLive/171f774c-b53f-49d0-9aa7-d7dd92c5943c.pdf",
        "page_target": None,
    },
]

for t in targets:
    url = t["url"]
    h = url_map.get(url)
    p = Path("cache/filings") / f"{h}.pdf" if h else None
    print(f"\n=======================================================")
    print(f"HOLD-OUT AUDIT: {t['name']}")
    print(f"URL: {url}")
    print(f"PDF Path: {p} (exists: {p.exists() if p else False})")
    if not p or not p.exists():
        continue
    with pdfplumber.open(p) as pdf:
        print(f"Total Pages: {len(pdf.pages)}")
        pages_to_check = [t["page_target"] - 1] if t["page_target"] else range(len(pdf.pages))
        for idx in pages_to_check:
            page = pdf.pages[idx]
            txt = page.extract_text() or ""
            if any(k in txt.lower() for k in ["statement of", "revenue from operations", "total income", "interest earned", "net interest income"]):
                lines = txt.splitlines()
                print(f"--- [Page {idx+1}] Header Lines ---")
                for l in lines[:10]:
                    print("  ", repr(l))
                print(f"--- [Page {idx+1}] Key Financial Metric Lines ---")
                for l in lines:
                    if any(m in l.lower() for m in [
                        "revenue from operations", "total income", "interest earned", "net interest income",
                        "profit before tax", "profit before exceptional", "profit for the period", "net profit",
                        "operating profit", "depreciation"
                    ]):
                        print("  ", repr(l))
                if t["page_target"] is None:
                    break
