"""
FINN — Concall Guidance Extractor
Extracts explicit guidance statements from concall transcripts using Gemini Flash.
Used by the "Promised vs. Delivered" hero feature.

Output per transcript:
  - Guidance items: {metric, statement, quarter, page_approx}
  - Management tone summary

Caches by file hash.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
RESEARCH_CACHE = ROOT / "cache" / "research"

GUIDANCE_EXTRACTION_PROMPT = """
You are analysing an earnings call (concall) transcript from an Indian listed company.

Your task: extract ALL explicit forward guidance statements — things management said about
what they EXPECT or PLAN for the future.

Focus on:
- Revenue/sales growth guidance (e.g. "We expect 20% revenue growth next year")
- EBITDA or operating margin guidance (e.g. "We expect margins to improve to 18-20%")
- PAT or net profit guidance
- Capex plans (e.g. "We plan to invest ₹500 crore in capex over next 18 months")
- Volume or capacity guidance
- Any specific numerical targets or ranges mentioned

Return ONLY valid JSON:
{
  "company_name": "<name>",
  "concall_period": "<e.g. Q2 FY25>",
  "concall_date": "<date if found, else null>",
  "guidance_items": [
    {
      "metric": "<what metric: revenue_growth | ebitda_margin | pat | capex | volume | other>",
      "statement": "<exact or near-exact quote from management>",
      "value": "<the guided number/range if stated, else null>",
      "timeframe": "<when: next quarter | FY25 | next 18 months | etc.>",
      "speaker": "<CEO / CFO / MD / other if identifiable>",
      "confidence": "explicit" or "implied"
    }
  ],
  "management_tone": "bullish" or "cautious" or "neutral",
  "key_themes": ["<3-5 key topics discussed on the call>"],
  "analyst_concerns": ["<topics analysts pressed management on>"]
}

Rules:
- Only include statements about FUTURE performance (guidance), not past results
- "confidence": "explicit" means a clear number was given; "implied" means qualitative direction
- If no guidance was given on a metric, omit that metric — do NOT invent items
- Quotes should be as close to verbatim as possible
- If the concall period is not clear from the text, set to null

Transcript text:
{text}
"""

SEGMENT_EXTRACTION_PROMPT = """
You are analysing an Indian company's annual report or concall transcript.

Extract structured information about the company's business:

Return ONLY valid JSON:
{
  "company_name": "<name>",
  "document_type": "annual_report" or "concall_transcript" or "results",
  "fiscal_year": "<FY24 / FY25 / etc.>",
  "business_description": "<2-3 sentence description of what the company does>",
  "segments": [
    {
      "name": "<segment name>",
      "revenue_crore": <number or null>,
      "revenue_pct": <% of total or null>,
      "description": "<brief description>"
    }
  ],
  "financials": {
    "revenue_crore": <number or null>,
    "ebitda_crore": <number or null>,
    "ebitda_margin_pct": <number or null>,
    "pat_crore": <number or null>,
    "pat_margin_pct": <number or null>,
    "roce_pct": <number or null>,
    "roe_pct": <number or null>,
    "debt_equity_ratio": <number or null>,
    "free_cash_flow_crore": <number or null>
  },
  "key_highlights": ["<3-5 bullet points of key developments>"],
  "risks": ["<stated risks>"],
  "management_commentary": "<key management statements on strategy/outlook>"
}

If a value is not found in the document, set it to null — do NOT guess.

Document text:
{text}
"""


def extract_guidance(
    text: str,
    ticker: str,
    file_hash: str,
    api_key: str,
    force: bool = False,
) -> dict:
    """Extract guidance statements from concall transcript."""
    cache_dir = RESEARCH_CACHE / ticker
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{file_hash}_guidance.json"

    if cache_path.exists() and not force:
        with open(cache_path) as f:
            return json.load(f)

    import google.generativeai as genai
    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        generation_config={"response_mime_type": "application/json"},
    )

    # Concalls are usually shorter than ARs; use more of the text
    text_snippet = text[:60000]

    try:
        response = model.generate_content(
            GUIDANCE_EXTRACTION_PROMPT.format(text=text_snippet)
        )
        result = json.loads(response.text)
        result["ticker"] = ticker
        result["file_hash"] = file_hash
    except Exception as e:
        print(f"  [ERROR] Guidance extraction failed: {e}")
        result = {"error": str(e), "ticker": ticker, "file_hash": file_hash}

    with open(cache_path, "w") as f:
        json.dump(result, f, indent=2)

    return result


def extract_segment_data(
    text: str,
    ticker: str,
    file_hash: str,
    doc_type: str,
    api_key: str,
    force: bool = False,
) -> dict:
    """Extract business and financial snapshot from AR or concall."""
    cache_dir = RESEARCH_CACHE / ticker
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{file_hash}_segments.json"

    if cache_path.exists() and not force:
        with open(cache_path) as f:
            return json.load(f)

    import google.generativeai as genai
    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        generation_config={"response_mime_type": "application/json"},
    )

    # For annual reports, focus on key sections
    text_snippet = text[:80000]

    try:
        response = model.generate_content(
            SEGMENT_EXTRACTION_PROMPT.format(text=text_snippet)
        )
        result = json.loads(response.text)
        result["ticker"] = ticker
        result["file_hash"] = file_hash
        result["source_doc_type"] = doc_type
    except Exception as e:
        print(f"  [ERROR] Segment extraction failed: {e}")
        result = {"error": str(e), "ticker": ticker}

    with open(cache_path, "w") as f:
        json.dump(result, f, indent=2)

    return result


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE.NS"
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Set GEMINI_API_KEY")
        sys.exit(1)

    from data_pipeline.extractors.pdf_extract import extract_all_for_ticker
    docs = extract_all_for_ticker(ticker, gemini_api_key=api_key)
    concalls = [d for d in docs if "concall" in d.get("doc_type", "").lower()]

    for doc in concalls[:2]:
        print(f"\nExtracting guidance from: {doc['file_name']}")
        result = extract_guidance(doc["text"], ticker, doc["file_hash"], api_key)
        print(json.dumps(result.get("guidance_items", [])[:3], indent=2))
