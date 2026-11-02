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


def parse_period_from_text(text: str) -> tuple[str, str, str]:
    """
    Dynamically extract fiscal quarter and year from document text.
    Indian Fiscal Year: April 1 to March 31.
    e.g. Quarter ended 30-Sep-2026 -> Q2 FY27 (ended 30-Sep-2026, FY 2026-27).
    """
    # Attempt 1: Explicit contiguous phrase (e.g. 'quarter ended 30th September, 2026')
    m = re.search(
        r"(?:quarter|three\s+months)[\s/\w]*ended\s*[:\-\s]*([0-9]{1,2}(?:st|nd|rd|th)?[\s\-\./,]+[a-zA-Z]+[\s\-\./,]+[0-9]{4}|[a-zA-Z]+[\s\-\./,]+[0-9]{1,2}(?:st|nd|rd|th)?[\s\-\./,]+[0-9]{4}|[0-9]{1,2}[\-\./][0-9]{1,2}[\-\./][0-9]{4})",
        text,
        re.IGNORECASE,
    )
    date_str = m.group(1).lower() if m else ""
    if not date_str:
        # Attempt 2: Numeric date column header like 30.09.2026 or 30-09-2026
        m2 = re.search(r"\b(3[01][\-\./](?:09|06|12|03)[\-\./](20\d\d))\b", text)
        if m2:
            date_str = m2.group(1).lower()

    if date_str:
        year_m = re.search(r"(20\d\d)", date_str)
        if year_m:
            cal_year = int(year_m.group(1))
            if any(k in date_str for k in ["jun", "06"]):
                fy = cal_year + 1
                return f"Q1 FY{str(fy)[-2:]}", f"Q4 FY{str(cal_year)[-2:]}", f"Q1 FY{str(cal_year)[-2:]}"
            elif any(k in date_str for k in ["sep", "09"]):
                fy = cal_year + 1
                return f"Q2 FY{str(fy)[-2:]}", f"Q1 FY{str(fy)[-2:]}", f"Q2 FY{str(cal_year)[-2:]}"
            elif any(k in date_str for k in ["dec", "12"]):
                fy = cal_year + 1
                return f"Q3 FY{str(fy)[-2:]}", f"Q2 FY{str(fy)[-2:]}", f"Q3 FY{str(cal_year)[-2:]}"
            elif any(k in date_str for k in ["mar", "03"]):
                fy = cal_year
                return f"Q4 FY{str(fy)[-2:]}", f"Q3 FY{str(fy)[-2:]}", f"Q4 FY{str(cal_year-1)[-2:]}"

    # Attempt 3: Split table headers (e.g. TCS where months are on one row and years on the next)
    m_year = re.search(r"\b(202[4-9])\b", text)
    if m_year:
        cal_year = int(m_year.group(1))
        m_month = re.search(r"\b(sep(?:tember)?|jun(?:e)?|dec(?:ember)?|mar(?:ch)?)\b", text, re.IGNORECASE)
        if m_month:
            month = m_month.group(1).lower()
            if "jun" in month:
                fy = cal_year + 1
                return f"Q1 FY{str(fy)[-2:]}", f"Q4 FY{str(cal_year)[-2:]}", f"Q1 FY{str(cal_year)[-2:]}"
            elif "sep" in month:
                fy = cal_year + 1
                return f"Q2 FY{str(fy)[-2:]}", f"Q1 FY{str(fy)[-2:]}", f"Q2 FY{str(cal_year)[-2:]}"
            elif "dec" in month:
                fy = cal_year + 1
                return f"Q3 FY{str(fy)[-2:]}", f"Q2 FY{str(fy)[-2:]}", f"Q3 FY{str(cal_year)[-2:]}"
            elif "mar" in month:
                fy = cal_year
                return f"Q4 FY{str(fy)[-2:]}", f"Q3 FY{str(fy)[-2:]}", f"Q4 FY{str(cal_year-1)[-2:]}"

    return "Current Quarter", "Previous Quarter", "Same Quarter Last Year"


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
    Works offline directly from extracted pdfplumber text.
    Handles unit conversions (INR Million -> Crore), OCR ligatures, banking layouts,
    and strips formula brackets.
    """
    lines = text.splitlines()

    # Detect entity type: Bank vs Corporate
    is_bank = False
    lower_lead = "\n".join(lines[:60]).lower()
    if ("interest earned" in lower_lead or "deposits" in lower_lead) and ("advances" in lower_lead or "bank" in lower_lead):
        is_bank = True

    # Detect unit multiplier (Crore vs Million vs Lakh)
    multiplier = 1.0
    if re.search(r"(?:rs\.?|inr|₹)\s*(?:in\s+)?millions?", lower_lead):
        multiplier = 0.1  # 10 Million = 1 Crore
    elif re.search(r"(?:rs\.?|inr|₹)\s*(?:in\s+)?lakhs?", lower_lead):
        multiplier = 0.01  # 100 Lakhs = 1 Crore

    def extract_row(keyword_patterns: list[str]) -> Optional[list[float]]:
        for line in lines:
            clean_l = re.sub(r"pro[1lf\s]*t", "profit", line, flags=re.IGNORECASE)
            # Strip footnote formulas like (1)+(2) or (3-4) before tokenization
            clean_l = re.sub(r"\(\s*[\d\s\+\-\*/]+\s*\)", " ", clean_l)
            # Clean up leading indices e.g. '3 Total Income' or '1) Interest' or '10 Profit'
            clean_l = re.sub(r"^\s*[\(\[]?[A-Za-z0-9]+[\)\]\.]\s*", " ", clean_l)
            clean_l = re.sub(r"^\s*\d+\s+(?=[A-Za-z])", " ", clean_l)
            # Handle OCR commas replacing decimal points e.g. 79362,78 -> 79362.78
            clean_l = re.sub(r"(\d+),(\d{2})\b", r"\1.\2", clean_l)
            for pat in keyword_patterns:
                if re.search(pat, clean_l, re.IGNORECASE):
                    tokens = re.findall(r"\(?\b\d+(?:,\d+)*(?:\.\d+)?\)?", clean_l)
                    clean_nums = []
                    for tok in tokens:
                        is_neg = tok.startswith("(") and tok.endswith(")")
                        val_str = tok.strip("()").replace(",", "")
                        try:
                            v = float(val_str) * multiplier
                            clean_nums.append(round(-v if is_neg else v, 2))
                        except ValueError:
                            continue
                    if len(clean_nums) >= 3:
                        if clean_nums[0] < 50 and len(clean_nums) >= 4 and abs(clean_nums[1]) > 100:
                            clean_nums = clean_nums[1:]
                        return clean_nums[:3]
        return None

    period_curr, period_qoq, period_yoy = parse_period_from_text(lower_lead)
    is_consolidated = "consolidated" in lower_lead

    if is_bank:
        # Bank specific items
        total_income = extract_row([r"total income\b", r"total income \("])
        int_earned = extract_row([r"interest earned"])
        int_expended = extract_row([r"interest expended"])
        nii = extract_row([r"net interest income"])
        if not nii and int_earned and int_expended:
            nii = [round(int_earned[i] - int_expended[i], 2) for i in range(min(len(int_earned), len(int_expended)))]

        pbt_nums = extract_row([r"profit before tax", r"profit.*before.*tax"])
        pat_nums = extract_row([r"net profit.*for the period", r"profit after tax", r"profit for the period"])

        if not total_income or not pbt_nums:
            return None

        return {
            "found": True,
            "is_bank": True,
            "basis": "consolidated" if is_consolidated else "standalone",
            "period_current": period_curr,
            "period_qoq": period_qoq,
            "period_yoy": period_yoy,
            "total_income": {
                "current": total_income[0],
                "prev_quarter": total_income[1],
                "prev_year_quarter": total_income[2],
            },
            "nii": {
                "current": nii[0] if nii else None,
                "prev_quarter": nii[1] if nii else None,
                "prev_year_quarter": nii[2] if nii else None,
            },
            "revenue": {
                "current": total_income[0],
                "prev_quarter": total_income[1],
                "prev_year_quarter": total_income[2],
            },
            "ebitda": None,  # Not applicable for banks
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

    # Non-bank corporate results
    rev_nums = extract_row([r"revenue from operations", r"net sales"]) or extract_row([r"total income"])
    pbt_nums = extract_row([r"profit before exceptional", r"profit before tax", r"profit.*before.*tax"])
    pat_nums = (
        extract_row([r"net profit attributable to.*owners"])
        or extract_row([r"profit for the period", r"profit after tax"])
    )
    fin_nums = extract_row([r"finance costs"])
    dep_nums = extract_row([r"depreciation"])

    if not rev_nums or not pbt_nums:
        return None

    ebitda_nums = None
    if pbt_nums and fin_nums and dep_nums:
        ebitda_nums = [
            round(pbt_nums[i] + fin_nums[i] + dep_nums[i], 2)
            for i in range(min(len(pbt_nums), len(fin_nums), len(dep_nums)))
        ]

    return {
        "found": True,
        "is_bank": False,
        "basis": "consolidated" if is_consolidated else "standalone",
        "period_current": period_curr,
        "period_qoq": period_qoq,
        "period_yoy": period_yoy,
        "revenue": {
            "current": rev_nums[0],
            "prev_quarter": rev_nums[1],
            "prev_year_quarter": rev_nums[2],
        },
        "ebitda": {
            "current": ebitda_nums[0] if ebitda_nums else None,
            "prev_quarter": ebitda_nums[1] if ebitda_nums else None,
            "prev_year_quarter": ebitda_nums[2] if ebitda_nums else None,
        } if ebitda_nums else None,
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
                cached_data = json.loads(cached_file.read_text(encoding="utf-8"))
                # If allow_download is requested, bypass transient "deferred" placeholders
                if not (allow_download and cached_data.get("reason") == "Download deferred"):
                    return cached_data
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

    is_bank = extracted.get("is_bank", False)
    metrics_dict = {
        "revenue": format_metric(extracted.get("revenue")),
        "ebitda": (
            {"current": None, "qoq_prev": None, "qoq_pct": None, "yoy_prev": None, "yoy_pct": None, "not_applicable": True}
            if is_bank
            else format_metric(extracted.get("ebitda"))
        ),
        "pbt": format_metric(extracted.get("pbt")),
        "pat": format_metric(extracted.get("pat")),
    }
    if is_bank:
        metrics_dict["total_income"] = format_metric(extracted.get("total_income"))
        metrics_dict["nii"] = format_metric(extracted.get("nii"))

    card_data = {
        "status": "ok",
        "ticker": ticker,
        "is_bank": is_bank,
        "basis": extracted.get("basis", "consolidated"),
        "period_current": extracted.get("period_current", "Current Quarter"),
        "period_qoq": extracted.get("period_qoq", "Previous Quarter"),
        "period_yoy": extracted.get("period_yoy", "Same Quarter Last Year"),
        "metrics": metrics_dict,
        "filing_url": filing_url,
        "sha256": sha256,
    }

    if cache_id:
        try:
            (RESULTS_DIR / f"{cache_id}.json").write_text(json.dumps(card_data, indent=2), encoding="utf-8")
        except Exception:
            pass

    return card_data
