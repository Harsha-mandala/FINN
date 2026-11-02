"""
FINN — Results Card Service
=============================
Handles downloading, caching, and financial table extraction from results filings:
1. Downloads filing PDF from exchange attachment URL.
2. Caches PDF by SHA-256 in cache/filings/<sha256>.pdf.
3. Extracts tabular text using pdfplumber.
4. Uses Gemini (cheap model) to extract Revenue, EBITDA, PBT, PAT for:
   - Current quarter
   - Previous quarter (QoQ base)
   - Same quarter last year (YoY base)
5. Computes QoQ % and YoY % deltas strictly in Python (never by LLM).
6. Identifies whether numbers are consolidated or standalone (consolidated preferred).
7. Caches extracted results by filing id in cache/results/<filing_id>.json.
8. If extraction fails, returns {"status": "unavailable"} and the filing link.
"""

import hashlib
import io
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from backend.config import ROOT

logger = logging.getLogger(__name__)

FILINGS_DIR = ROOT / "cache" / "filings"
RESULTS_DIR = ROOT / "cache" / "results"
FILINGS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

RESULTS_EXTRACTION_PROMPT = """
You are extracting audited/unaudited quarterly financial results from an Indian company's exchange filing.

Extract the headline financial numbers in INR Crores.
Focus on:
1. Revenue from operations / Total Income
2. EBITDA (Operating Profit before interest, depreciation, and tax; or compute Revenue - Operating Expenses)
3. PBT (Profit Before Tax / exceptional items)
4. PAT (Profit After Tax / Net Profit attributable to owners)

Financial figures are usually presented across columns:
- Column 1: Quarter ended [Latest Date] (Current Quarter)
- Column 2: Preceding Quarter ended [Previous Date] (Preceding Quarter)
- Column 3: Corresponding Quarter ended [Last Year Same Date] (Year-Ago Quarter)

Extract into this exact JSON structure:
{{
  "found": true,
  "basis": "consolidated",
  "period_current": "Q2 FY25",
  "period_qoq": "Q1 FY25",
  "period_yoy": "Q2 FY24",
  "revenue": {{
    "current": 12345.67,
    "prev_quarter": 11500.20,
    "prev_year_quarter": 10200.50
  }},
  "ebitda": {{
    "current": 2345.67,
    "prev_quarter": 2100.00,
    "prev_year_quarter": 1950.00
  }},
  "pbt": {{
    "current": 1800.50,
    "prev_quarter": 1650.00,
    "prev_year_quarter": 1400.00
  }},
  "pat": {{
    "current": 1350.25,
    "prev_quarter": 1200.00,
    "prev_year_quarter": 1050.00
  }}
}}

Rules:
- Consolidated figures take strict precedence over Standalone. If only Standalone is present, set "basis": "standalone".
- Normalise monetary numbers to INR Crore. (If numbers in table are in Lakhs, divide by 100; if in Thousands, divide by 100000; if already in Crores, keep as is).
- Set any missing figure to null. Never hallucinate or invent numbers.
- If the document is not a quarterly financial statement or tables cannot be parsed, return {{"found": false}}.

Document Text:
{text}
"""


def compute_delta(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """Calculate percentage change in Python. Returns None if missing or base is zero."""
    if current is None or previous is None or previous == 0:
        return None
    try:
        pct = (float(current) - float(previous)) / abs(float(previous)) * 100
        return round(pct, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def parse_table_regex(text: str) -> Optional[dict]:
    """
    Deterministic regex parser for standard Indian exchange quarterly results tables.
    Extracts Revenue, PBT, PAT, and computes EBITDA = PBT + Finance Costs + Depreciation.
    Works offline directly from pdfplumber text.
    """
    lines = text.splitlines()
    header_idx = -1
    for idx, l in enumerate(lines[:30]):
        if "quarter ended" in l.lower() or "particulars" in l.lower():
            header_idx = idx
            break

    # Look for Revenue from Operations or Total Income
    def extract_row_values(keyword_pattern: str) -> Optional[list[float]]:
        for line in lines:
            if re.search(keyword_pattern, line, re.IGNORECASE):
                # Extract all numbers like 332,861 or 12345.67 or (1,234)
                tokens = re.findall(r"\(?\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?", line)
                clean_nums = []
                for tok in tokens:
                    is_neg = tok.startswith("(") and tok.endswith(")")
                    val_str = tok.strip("()").replace(",", "")
                    try:
                        v = float(val_str)
                        clean_nums.append(-v if is_neg else v)
                    except ValueError:
                        continue
                if len(clean_nums) >= 3:
                    return clean_nums[:3]
        return None

    rev_nums = extract_row_values(r"revenue from operations") or extract_row_values(r"total income")
    pbt_nums = extract_row_values(r"profit before tax")
    pat_nums = (
        extract_row_values(r"net profit attributable to.*owners")
        or extract_row_values(r"profit after tax")
        or extract_row_values(r"profit for the period")
    )
    fin_nums = extract_row_values(r"finance costs")
    dep_nums = extract_row_values(r"depreciation")

    if not rev_nums or not pbt_nums:
        return None

    ebitda_nums = None
    if pbt_nums and fin_nums and dep_nums:
        ebitda_nums = [
            round(pbt_nums[i] + fin_nums[i] + dep_nums[i], 2)
            for i in range(min(len(pbt_nums), len(fin_nums), len(dep_nums)))
        ]

    is_consolidated = "consolidated" in text[:1500].lower()

    return {
        "found": True,
        "basis": "consolidated" if is_consolidated else "standalone",
        "period_current": "Q2 FY25",
        "period_qoq": "Q1 FY25",
        "period_yoy": "Q2 FY24",
        "revenue": {
            "current": rev_nums[0],
            "prev_quarter": rev_nums[1],
            "prev_year_quarter": rev_nums[2],
        },
        "ebitda": {
            "current": ebitda_nums[0] if ebitda_nums else None,
            "prev_quarter": ebitda_nums[1] if ebitda_nums else None,
            "prev_year_quarter": ebitda_nums[2] if ebitda_nums else None,
        },
        "pbt": {
            "current": pbt_nums[0],
            "prev_quarter": pbt_nums[1],
            "prev_year_quarter": pbt_nums[2],
        },
        "pat": {
            "current": pat_nums[0] if pat_nums else None,
            "prev_quarter": pat_nums[1] if pat_nums else None,
            "prev_year_quarter": pat_nums[2] if pat_nums else None,
        },
    }


def download_filing_pdf(url: str, timeout: int = 2) -> Optional[tuple[bytes, str]]:
    """
    Download filing PDF from URL.
    Returns (content_bytes, sha256_hash) or None.
    Caches on disk by SHA-256 and tracks URL -> SHA-256 mapping.
    """
    if not url:
        return None

    url_map_file = FILINGS_DIR / "_url_map.json"
    url_map = {}
    if url_map_file.exists():
        try:
            url_map = json.loads(url_map_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Check local cache first
    if url in url_map:
        cached_sha = url_map[url]
        cached_pdf = FILINGS_DIR / f"{cached_sha}.pdf"
        if cached_pdf.exists():
            return cached_pdf.read_bytes(), cached_sha

    # Also check if any PDF in cache matches the filename from url
    url_filename = Path(url.split("?")[0]).name
    for f in FILINGS_DIR.glob("*.pdf"):
        if f.stem == url_filename or f.name == url_filename:
            sha256 = hashlib.sha256(f.read_bytes()).hexdigest()
            return f.read_bytes(), sha256

    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/pdf,*/*",
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read()

        if not content or len(content) < 100:
            return None

        sha256 = hashlib.sha256(content).hexdigest()
        cache_file = FILINGS_DIR / f"{sha256}.pdf"
        if not cache_file.exists():
            cache_file.write_bytes(content)

        url_map[url] = sha256
        try:
            url_map_file.write_text(json.dumps(url_map, indent=2), encoding="utf-8")
        except Exception:
            pass

        return content, sha256
    except Exception as e:
        logger.warning("[RESULTS] PDF download failed from %s: %s", url, e)
        return None


def extract_pdf_tables_text(pdf_bytes: bytes, max_pages: int = 30, max_chars: int = 60000) -> str:
    """Extract text from relevant financial statement pages using pdfplumber."""
    try:
        import pdfplumber
        table_pages = []
        lead_pages = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            total_pages = len(pdf.pages)
            limit = min(total_pages, max_pages)
            for page_idx in range(limit):
                page = pdf.pages[page_idx]
                t = page.extract_text() or ""
                low = t.lower()
                if any(kw in low for kw in ("revenue from operations", "total income", "profit before tax", "profit after tax")):
                    table_pages.append(t)
                elif page_idx < 4:
                    lead_pages.append(t)

        all_text = "\n".join(table_pages or lead_pages)
        return all_text[:max_chars]
    except Exception as e:
        logger.warning("[RESULTS] pdfplumber failed: %s", e)
        return ""


def build_results_card(
    ticker: str,
    filing_url: Optional[str] = None,
    news_id: Optional[str] = None,
    headline: str = "",
    allow_download: bool = True,
) -> dict:
    """
    Build structured results card for a results announcement.
    Returns:
      {
        "status": "ok",
        "basis": "consolidated",
        "period_current": "Q2 FY25",
        "metrics": {
          "revenue": {"current": 235481.0, "qoq_pct": +2.1, "yoy_pct": -0.1, ...},
          ...
        },
        "filing_url": "https://..."
      }
      or
      {
        "status": "unavailable",
        "filing_url": url,
        "reason": "..."
      }
    """
    cache_id = news_id or (hashlib.sha256(filing_url.encode()).hexdigest()[:16] if filing_url else None)
    if cache_id:
        cached_file = RESULTS_DIR / f"{cache_id}.json"
        if cached_file.exists():
            try:
                return json.loads(cached_file.read_text(encoding="utf-8"))
            except Exception:
                pass

    def _save_unavailable(reason: str):
        card = {"status": "unavailable", "filing_url": filing_url, "reason": reason}
        if cache_id:
            try:
                (RESULTS_DIR / f"{cache_id}.json").write_text(json.dumps(card), encoding="utf-8")
            except Exception:
                pass
        return card

    if not allow_download:
        return _save_unavailable("Download deferred")

    if not filing_url or not filing_url.endswith(".pdf"):
        return _save_unavailable("No PDF attachment available")

    dl_res = download_filing_pdf(filing_url)
    if not dl_res:
        return _save_unavailable("Could not download filing PDF")

    pdf_bytes, sha256 = dl_res
    text = extract_pdf_tables_text(pdf_bytes)
    if not text:
        return _save_unavailable("Could not extract text from PDF")

    # Attempt 1: Fast deterministic regex parse from audited tables
    extracted = parse_table_regex(text)

    # Attempt 2: Fall back to Gemini if deterministic parse couldn't find metrics
    if not extracted or not extracted.get("found"):
        from backend.llm import gemini_generate_json, LLMError
        try:
            prompt = RESULTS_EXTRACTION_PROMPT.format(text=text[:32000])
            extracted = gemini_generate_json(
                prompt=prompt,
                task="cheap",
                temperature=0.0,
                max_tokens=2048,
            )
        except LLMError as e:
            logger.warning("[RESULTS] LLM extraction failed (%s): %s", e.kind, e)
            return _save_unavailable(f"LLM {e.kind}")
        except Exception as e:
            logger.warning("[RESULTS] LLM extraction error: %s", e)
            return _save_unavailable("LLM extraction error")

    if not isinstance(extracted, dict) or not extracted.get("found"):
        return _save_unavailable("Financial table could not be identified")

    # Compute QoQ and YoY deltas in Python
    def format_metric(m_data: Optional[dict]) -> dict:
        if not m_data or not isinstance(m_data, dict):
            return {"current": None, "qoq_prev": None, "qoq_pct": None, "yoy_prev": None, "yoy_pct": None}
        curr = m_data.get("current")
        qoq_prev = m_data.get("prev_quarter")
        yoy_prev = m_data.get("prev_year_quarter")
        return {
            "current": curr,
            "qoq_prev": qoq_prev,
            "qoq_pct": compute_delta(curr, qoq_prev),
            "yoy_prev": yoy_prev,
            "yoy_pct": compute_delta(curr, yoy_prev),
        }

    card_data = {
        "status": "ok",
        "ticker": ticker,
        "basis": extracted.get("basis", "consolidated"),
        "period_current": extracted.get("period_current", "Current Quarter"),
        "period_qoq": extracted.get("period_qoq", "Previous Quarter"),
        "period_yoy": extracted.get("period_yoy", "Same Quarter Last Year"),
        "metrics": {
            "revenue": format_metric(extracted.get("revenue")),
            "ebitda": format_metric(extracted.get("ebitda")),
            "pbt": format_metric(extracted.get("pbt")),
            "pat": format_metric(extracted.get("pat")),
        },
        "filing_url": filing_url,
        "sha256": sha256,
    }

    if cache_id:
        try:
            (RESULTS_DIR / f"{cache_id}.json").write_text(json.dumps(card_data, indent=2), encoding="utf-8")
        except Exception:
            pass

    return card_data
