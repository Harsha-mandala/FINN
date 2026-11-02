import json
import os
import sys
import hashlib
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import ROOT
from backend.services.results_card import download_filing_pdf, build_results_card

def main():
    ann_file = ROOT / "cache" / "announcements" / "_classified_2026-11-02.json"
    with open(ann_file, encoding="utf-8") as f:
        items = json.load(f)

    results_items = [it for it in items if it.get("category") == "results"]
    print(f"Total results filings to process: {len(results_items)}")

    tuning_tickers = {"RELIANCE.NS", "TCS.NS", "TRENT.NS", "POLYCAB.NS", "HDFCBANK.NS", "INFY.NS"}

    tuning_results = []
    holdout_results = []

    for idx, it in enumerate(results_items):
        ticker = it.get("ticker", "")
        nid = it.get("news_id", "")
        url = it.get("attachment_url", "")
        headline = it.get("headline", "")

        is_tuning = ticker in tuning_tickers and idx in [0, 3, 4, 6, 12, 13]

        print(f"[{idx+1}/{len(results_items)}] Processing {ticker} (news_id: {nid[:8]}...)...")

        card = build_results_card(
            ticker=ticker,
            filing_url=url,
            news_id=nid,
            headline=headline,
            allow_download=True,
        )

        status = card.get("status")
        basis = card.get("basis", "—")
        period = card.get("period_current", "—")
        reason = card.get("reason", "")
        is_pass = (status == "ok")

        entry = {
            "idx": idx + 1,
            "ticker": ticker,
            "news_id": nid,
            "url": url,
            "basis": basis,
            "period": period,
            "status": status,
            "reason": reason,
            "is_pass": is_pass,
            "is_bank": card.get("is_bank", False),
            "metrics": card.get("metrics", {})
        }

        if is_tuning:
            tuning_results.append(entry)
        else:
            holdout_results.append(entry)

    print("\n" + "="*80)
    print("TUNING SET RESULTS:")
    print("="*80)
    for r in tuning_results:
        print(f"{r['ticker']:<12} | {r['news_id'][:8]} | Basis: {r['basis']:<12} | Period: {r['period']:<10} | PASS: {r['is_pass']} ({r['reason']})")

    print("\n" + "="*80)
    print("HOLDOUT SET RESULTS:")
    print("="*80)
    for r in holdout_results:
        print(f"{r['ticker']:<12} | {r['news_id'][:8]} | Basis: {r['basis']:<12} | Period: {r['period']:<10} | PASS: {r['is_pass']} ({r['reason']})")

    tuning_pass = sum(1 for r in tuning_results if r["is_pass"])
    holdout_pass = sum(1 for r in holdout_results if r["is_pass"])
    print("\n" + "="*80)
    print(f"TUNING SET PASS RATE: {tuning_pass}/{len(tuning_results)} ({tuning_pass/max(1, len(tuning_results))*100:.1f}%)")
    print(f"HOLDOUT SET PASS RATE: {holdout_pass}/{len(holdout_results)} ({holdout_pass/max(1, len(holdout_results))*100:.1f}%)")
    print(f"TOTAL PASS RATE: {tuning_pass+holdout_pass}/{len(results_items)} ({(tuning_pass+holdout_pass)/len(results_items)*100:.1f}%)")

if __name__ == "__main__":
    main()
