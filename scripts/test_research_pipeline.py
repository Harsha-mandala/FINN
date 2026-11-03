import sys
import os
import json
import time

sys.path.insert(0, os.path.abspath("."))
import backend.config
from backend.services.researcher import build_research_cards

def test_ticker(ticker: str):
    print(f"\n=======================================================")
    print(f"RUNNING RESEARCH PIPELINE FOR: {ticker}")
    print(f"=======================================================")
    start_t = time.time()
    res = build_research_cards(ticker=ticker, force=True)
    elapsed = time.time() - start_t
    print(f"Pipeline finished in {elapsed:.1f} seconds. Status: {res.get('status')}")
    print(f"Total cards produced: {len(res.get('cards', []))}")
    print(f"Sources used: {res.get('sources_used')}")
    for idx, c in enumerate(res.get("cards", [])):
        print(f"\n[{idx+1}] Card Type: {c.get('card_type')}")
        print(f"    Label: {c.get('company_name')} | Model: {c.get('provenance', {}).get('model_used')}")
        content = c.get("data", {}).get("content", "")
        print(f"    Content Preview:\n{content[:300]}...")
    return res

if __name__ == "__main__":
    for t in ["RELIANCE.NS", "PERSISTENT.NS"]:
        test_ticker(t)
