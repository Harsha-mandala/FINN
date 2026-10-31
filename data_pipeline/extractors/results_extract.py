"""
FINN — Results Headline Extractor
Extracts Revenue, EBITDA, PBT, PAT from quarterly results PDFs.
QoQ and YoY % changes are computed in Python — NOT by the LLM.

Model: Gemini 1.5 Flash (structured JSON output)
Caches by file hash.
"""

import json
import os
import re
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
RESEARCH_CACHE = ROOT / "cache" / "research"

EXTRACTION_PROMPT = """
You are extracting financial headline numbers from an Indian company's quarterly results document.

Extract the following metrics (in INR Crores) for each quarter present in the document:
- Revenue (total revenue / net sales / total income from operations)
- EBITDA (earnings before interest, tax, depreciation, amortisation; or operating profit)
- PBT (profit before tax)
- PAT (profit after tax / net profit)

Return ONLY valid JSON in this exact format:
{
  "company_name": "<name>",
  "currency": "INR Crores",
  "basis": "consolidated" or "standalone",
  "quarters": [
    {
      "period": "Q2 FY25",
      "revenue": 12345.67,
      "ebitda": 2345.67,
      "pbt": 1234.56,
      "pat": 987.65,
      "notes": "any caveats or extraction notes"
    }
  ]
}

Rules:
- Include ALL quarters present in the document (usually current + comparison quarters)
- If EBITDA is not directly stated, compute it from operating profit if available, else set to null
- If a number is not found, set it to null — do NOT guess
- Revenue must be the top-line figure (not segmental)
- Use "consolidated" financials if available; fall back to "standalone"
- Period format: "Q1 FY24", "Q2 FY25", "FY24" (annual), etc.

Document text:
{text}
"""


def compute_delta(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """Compute percentage change. Returns None if either value is missing or zero."""
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 1)


def extract_results_numbers(
    text: str,
    ticker: str,
    file_hash: str,
    api_key: str,
    force: bool = False,
) -> dict:
    """
    Use Gemini Flash to extract headline numbers from results text.
    Then compute QoQ/YoY in Python.
    """
    cache_dir = RESEARCH_CACHE / ticker
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{file_hash}_results.json"

    # ── Cache hit ─────────────────────────────────────────────────────────────
    if cache_path.exists() and not force:
        with open(cache_path) as f:
            return json.load(f)

    # ── LLM extraction ────────────────────────────────────────────────────────
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    # Truncate text to avoid token limits (results docs are usually < 50 pages)
    text_snippet = text[:40000]  # ~10K tokens for Flash

    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        generation_config={"response_mime_type": "application/json"},
    )

    prompt = EXTRACTION_PROMPT.format(text=text_snippet)

    try:
        response = model.generate_content(prompt)
        raw = json.loads(response.text)
    except Exception as e:
        print(f"  [ERROR] Gemini extraction failed: {e}")
        return {"error": str(e), "ticker": ticker}

    # ── Compute deltas in Python (never trust LLM for arithmetic) ─────────────
    quarters = raw.get("quarters", [])
    if len(quarters) >= 2:
        # Sort by period — best effort; quarters are usually in reverse chrono order
        # Q index: Q1=1, Q2=2, Q3=3, Q4=4; FY year as secondary sort
        def period_sort_key(q):
            p = q.get("period", "")
            m = re.search(r"Q(\d).*?FY(\d{2,4})", p)
            if m:
                return int(m.group(2)) * 10 + int(m.group(1))
            return 0

        quarters_sorted = sorted(quarters, key=period_sort_key)

        # Most recent = last in sorted list
        current = quarters_sorted[-1]
        prev_q = quarters_sorted[-2] if len(quarters_sorted) >= 2 else None

        # Find YoY: same Q from previous fiscal year
        current_match = re.search(r"Q(\d).*?FY(\d{2,4})", current.get("period", ""))
        yoy_q = None
        if current_match:
            curr_q_num = int(current_match.group(1))
            curr_fy = int(current_match.group(2))
            prev_fy = curr_fy - 1
            for q in quarters_sorted:
                m = re.search(r"Q(\d).*?FY(\d{2,4})", q.get("period", ""))
                if m and int(m.group(1)) == curr_q_num and int(m.group(2)) == prev_fy:
                    yoy_q = q
                    break

        def make_delta_row(metric: str) -> dict:
            curr_val = current.get(metric)
            qoq_val = prev_q.get(metric) if prev_q else None
            yoy_val = yoy_q.get(metric) if yoy_q else None
            return {
                "current": curr_val,
                "qoq_prev": qoq_val,
                "qoq_pct": compute_delta(curr_val, qoq_val),
                "yoy_prev": yoy_val,
                "yoy_pct": compute_delta(curr_val, yoy_val),
            }

        deltas = {
            "period_current": current.get("period"),
            "period_qoq": prev_q.get("period") if prev_q else None,
            "period_yoy": yoy_q.get("period") if yoy_q else None,
            "revenue": make_delta_row("revenue"),
            "ebitda": make_delta_row("ebitda"),
            "pbt": make_delta_row("pbt"),
            "pat": make_delta_row("pat"),
        }
    else:
        deltas = {"note": "Insufficient quarters for comparison"}

    result = {
        "ticker": ticker,
        "extraction": raw,
        "headline": deltas,
    }

    with open(cache_path, "w") as f:
        json.dump(result, f, indent=2)

    return result


if __name__ == "__main__":
    import sys
    from data_pipeline.extractors.pdf_extract import extract_all_for_ticker

    ticker = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE.NS"
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Set GEMINI_API_KEY env var")
        sys.exit(1)

    docs = extract_all_for_ticker(ticker, gemini_api_key=api_key)
    results_docs = [d for d in docs if "result" in d.get("doc_type", "").lower()]

    for doc in results_docs[:2]:
        print(f"\nExtracting results from: {doc['file_name']}")
        result = extract_results_numbers(doc["text"], ticker, doc["file_hash"], api_key)
        print(json.dumps(result.get("headline", {}), indent=2))
