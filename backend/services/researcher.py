"""
FINN — Research Agent Service (Gemini-only)
============================================
Two-stage pipeline for Pull (on-demand research):

  Stage 1 (GEMINI_CHEAP_MODEL, cached by document hash):
    Extracts structured JSON from each document:
    - concall  → guidance items {metric, direction, value, horizon, verbatim_quote, page}
    - annual report → segment mix, 3-5yr financials, key ratios

  Stage 2 (GEMINI_MODEL, ONE call per ticker, returns all cards):
    Takes ONLY Stage 1 JSON (not raw PDFs) and produces all 5 research cards
    as a single structured JSON object.

Output schema: 5 cards with structured data and provenance.
If the pipeline cannot produce a card, returns {"status":"insufficient_data","missing":[...]}.
Never uses template content, yfinance snapshots, or model memory for facts.
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import DOCUMENTS_CACHE, RESEARCH_CACHE

logger = logging.getLogger(__name__)


# ── Stage 1 prompts ───────────────────────────────────────────────────────────

_CONCALL_EXTRACT_SYSTEM = """
You are extracting structured data from an Indian company earnings-call (concall) transcript.
Return ONLY valid JSON — no prose, no markdown.
"""

_CONCALL_EXTRACT_PROMPT = """
Extract guidance items from this earnings-call transcript.

For each distinct forward-looking management statement, output one object:
{
  "metric": "Revenue / EBITDA margin / NIM / GNPA / etc.",
  "direction": "grow|maintain|reduce|target|other",
  "value": "specific number/range if stated, else null",
  "unit": "% / Cr / x / bps / other",
  "horizon": "FY25 / H2 FY25 / 12 months / etc.",
  "verbatim_quote": "exact substring from the transcript",
  "speaker": "Name, Title (if available)",
  "confidence": "explicit if a specific number was given, implied if directional only"
}

Rules:
- verbatim_quote must be an exact substring of the source text — copy-paste, do not paraphrase.
- Include only forward-looking statements. Exclude historical fact statements.
- Return a JSON array: [{"metric": ..., ...}, ...]
- If no guidance items found, return [].

Transcript (may be truncated):
{transcript}
"""

_AR_EXTRACT_SYSTEM = """
You are extracting structured financial data from an Indian company annual report.
Return ONLY valid JSON — no prose, no markdown.
"""

_AR_EXTRACT_PROMPT = """
Extract the following from this annual report text:

1. segment_mix: list of {{segment, revenue_cr, revenue_pct, period}} — most recent year
2. financials: list of {{year, metric, value, unit}} — cover Revenue, EBITDA, PAT, EBITDA_margin, ROE, ROCE, D_E, CFO, Capex, Working_capital_days for each year available (up to 5 years)
3. key_ratios: latest values for ROE, ROCE, D/E, current ratio, interest coverage
4. contingent_liabilities: any material items disclosed (text description, amount if given)
5. business_segments: brief description of each segment (1-2 sentences)

Return JSON:
{{
  "segment_mix": [...],
  "financials": [...],
  "key_ratios": {{...}},
  "contingent_liabilities": [...],
  "business_segments": [...]
}}

Rules:
- Only include data that appears explicitly in the text. Set null for anything absent.
- Use INR crore as the unit for monetary values (convert if needed, note conversion).
- If this is a bank/NBFC, include NIM, GNPA, NNPA, ROA, CAR instead of D/E and capex.

Annual report text (may be truncated to key sections):
{ar_text}
"""


# ── Stage 2 prompt ────────────────────────────────────────────────────────────

_STAGE2_SYSTEM = """
You are a rigorous financial analyst. You will produce structured research cards from primary-source data only.
You must NOT use any knowledge about this company beyond what is provided in the input JSON below.
If a fact is not in the input, say so explicitly — do not fill gaps.
Return ONLY valid JSON exactly matching the schema described.
"""

_STAGE2_PROMPT = """
Company: {ticker}
Is Bank/NBFC: {is_financial}

Primary-source extracted data (from annual reports and concall transcripts):
{extractions_json}

Produce all 5 research cards in a single JSON object with this exact structure:

{{
  "snapshot": {{
    "business_summary": "3-4 sentences: what the company does, segments, market position",
    "segments": [
      {{"name": "segment name", "revenue_share_pct": 40.0, "period": "FY24", "note": ""}}
    ],
    "key_metrics": [
      {{"name": "Revenue", "value": 12345.6, "unit": "Cr", "period": "FY24", "source_ref": "FY24 Annual Report"}}
    ]
  }},
  "trajectory": [
    {{"metric": "Revenue", "series": [{{"period": "FY22", "value": 1000.0}}, ...], "takeaway": "...", "source_ref": "FY24 Annual Report"}}
  ],
  "guidance": [
    {{
      "metric": "EBITDA margin",
      "guided_value": "18-20%",
      "horizon": "FY26",
      "verbatim_quote": "exact quote from concall",
      "source_doc": "Q2 FY25 Concall",
      "speaker": "CFO Name"
    }}
  ],
  "promised_vs_delivered": [
    {{
      "quarter": "Q2 FY25",
      "metric": "Revenue growth",
      "guided_quote": "exact quote from past concall",
      "source_doc": "Q1 FY25 Concall",
      "actual_value": 12345.6,
      "actual_period": "Q2 FY25",
      "delta_computed": "+8.3%",
      "verdict": "met"
    }}
  ],
  "bull_bear": {{
    "bull": [
      {{"argument": "...", "source_ref": "FY24 Annual Report, p12"}}
    ],
    "bear": [
      {{"argument": "...", "source_ref": "Q2 FY25 Concall"}}
    ]
  }}
}}

Strict rules:
1. snapshot.business_summary: only facts in the extraction. No memory.
2. key_metrics: only explicitly stated numbers. null for missing.
3. trajectory.series: only years where data is in the extraction. Minimum 2 points or omit the metric.
4. guidance: only items with verbatim_quote present in extraction.
5. promised_vs_delivered:
   - Only rows where BOTH guided_quote (from a past concall) AND actual_value (from a later filing) are present in the extraction.
   - verdict must be one of: "met" | "partial" | "missed" | "pending" | "insufficient_data"
   - "pending": guidance horizon is still in the future.
   - "insufficient_data": either the guided value or actual value is missing — DO NOT guess.
   - delta_computed: if both sides are numeric, compute the % delta. Otherwise null.
   - No verdict may be emitted when actual_value is null.
6. bull_bear: each point must cite source_ref from the extraction. No generic claims.
7. If you have fewer than 2 concall extractions available, set promised_vs_delivered = [] and add "limited_data": true to the root.
8. For banks/NBFCs: replace D/E and capex framing with NIM, GNPA, ROA, CAR where available.

Respond with ONLY the JSON object described. No prose before or after.
"""


# ── Document loading ───────────────────────────────────────────────────────────

def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _load_pdf_text(pdf_path: Path, max_chars: int = 80000) -> str:
    """Extract text from a PDF using pdfplumber."""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
                if sum(len(p) for p in text_parts) > max_chars:
                    break
        return "\n".join(text_parts)[:max_chars]
    except Exception as e:
        logger.error("[RESEARCHER] pdfplumber failed on %s: %s", pdf_path.name, e)
        return ""


_AR_SECTION_KEYWORDS = [
    "management discussion", "md&a", "segment",
    "revenue", "ebitda", "profit after tax", "pat",
    "cash flow", "capital expenditure", "debt", "equity",
    "contingent liabilities", "related party",
]


def _select_ar_pages(pdf_path: Path, max_chars: int = 60000) -> str:
    """
    For annual reports, select only financially relevant pages
    (MD&A, segment info, financial statements, cash-flow, contingent liabilities).
    Falls back to first max_chars of full text.
    """
    try:
        import pdfplumber
        selected: list[str] = []
        total = 0
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                low = t.lower()
                if any(kw in low for kw in _AR_SECTION_KEYWORDS):
                    selected.append(t)
                    total += len(t)
                    if total > max_chars:
                        break
        return "\n".join(selected)[:max_chars] if selected else _load_pdf_text(pdf_path, max_chars)
    except Exception as e:
        logger.warning("[RESEARCHER] AR page selection failed: %s", e)
        return _load_pdf_text(pdf_path, max_chars)


# ── Stage 1: Per-document extraction (cheap model, cached) ────────────────────

def _stage1_concall(doc_path: Path, ticker: str) -> dict:
    """
    Extract guidance items from a concall transcript PDF.
    Cached by file hash.
    """
    from backend.llm import gemini_generate_json, LLMError

    h = _file_hash(doc_path)
    cache_dir = RESEARCH_CACHE / ticker
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"concall_{h}_guidance.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            logger.info("[RESEARCHER] Stage1 cache hit: %s", cache_file.name)
            return data
        except Exception:
            pass

    text = _load_pdf_text(doc_path, max_chars=60000)
    if not text:
        result = {"status": "empty_text", "doc": doc_path.name, "guidance_items": []}
        cache_file.write_text(json.dumps(result), encoding="utf-8")
        return result

    prompt = _CONCALL_EXTRACT_PROMPT.format(transcript=text[:55000])

    try:
        items = gemini_generate_json(
            prompt=prompt,
            task="cheap",
            system=_CONCALL_EXTRACT_SYSTEM,
            temperature=0.0,
            max_tokens=4096,
        )
        if not isinstance(items, list):
            items = []

        # Validate verbatim quotes (drop items whose quote isn't in the source)
        validated = []
        for item in items:
            quote = item.get("verbatim_quote", "")
            if quote and quote in text:
                validated.append(item)
            elif quote:
                logger.debug("[RESEARCHER] Dropped guidance item — quote not found in source: %s", quote[:60])

        result = {
            "status": "ok",
            "doc": doc_path.name,
            "doc_type": "concall",
            "file_hash": h,
            "extracted_at": datetime.now().isoformat(),
            "guidance_items": validated,
        }
        cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        logger.info("[RESEARCHER] Stage1 concall: %d validated guidance items from %s", len(validated), doc_path.name)
        return result

    except LLMError as e:
        logger.error("[RESEARCHER] Stage1 concall LLM error (%s): %s", e.kind, e)
        result = {"status": f"llm_{e.kind}", "doc": doc_path.name, "guidance_items": []}
        cache_file.write_text(json.dumps(result), encoding="utf-8")
        return result
    except Exception as e:
        logger.error("[RESEARCHER] Stage1 concall unexpected error: %s", e)
        return {"status": "error", "doc": doc_path.name, "guidance_items": []}


def _stage1_annual_report(doc_path: Path, ticker: str) -> dict:
    """
    Extract structured financials from an annual report PDF.
    Cached by file hash.
    """
    from backend.llm import gemini_generate_json, LLMError

    h = _file_hash(doc_path)
    cache_dir = RESEARCH_CACHE / ticker
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"ar_{h}_financials.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            logger.info("[RESEARCHER] Stage1 cache hit: %s", cache_file.name)
            return data
        except Exception:
            pass

    text = _select_ar_pages(doc_path, max_chars=60000)
    if not text:
        result = {"status": "empty_text", "doc": doc_path.name}
        cache_file.write_text(json.dumps(result), encoding="utf-8")
        return result

    prompt = _AR_EXTRACT_PROMPT.format(ar_text=text[:55000])

    try:
        data = gemini_generate_json(
            prompt=prompt,
            task="cheap",
            system=_AR_EXTRACT_SYSTEM,
            temperature=0.0,
            max_tokens=4096,
        )
        if not isinstance(data, dict):
            data = {}

        result = {
            "status": "ok",
            "doc": doc_path.name,
            "doc_type": "annual_report",
            "file_hash": h,
            "extracted_at": datetime.now().isoformat(),
            **data,
        }
        cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        logger.info("[RESEARCHER] Stage1 AR done: %s", doc_path.name)
        return result

    except LLMError as e:
        logger.error("[RESEARCHER] Stage1 AR LLM error (%s): %s", e.kind, e)
        result = {"status": f"llm_{e.kind}", "doc": doc_path.name}
        cache_file.write_text(json.dumps(result), encoding="utf-8")
        return result
    except Exception as e:
        logger.error("[RESEARCHER] Stage1 AR error: %s", e)
        return {"status": "error", "doc": doc_path.name}


# ── Stage 2: Synthesis (reasoning model, one call, all cards) ─────────────────

_FINANCIAL_TICKERS = {"BAJFINANCE", "HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN"}


def _stage2_synthesize(ticker: str, extractions: list[dict]) -> dict:
    """
    One Gemini reasoning call → all 5 cards as structured JSON.
    Cached by extraction hash (changes only when documents change).
    """
    from backend.llm import gemini_generate_json, LLMError

    is_financial = ticker.replace(".NS", "").replace(".BO", "") in _FINANCIAL_TICKERS

    # Hash the extractions to detect changes
    ext_str = json.dumps(extractions, sort_keys=True)
    ext_hash = hashlib.sha256(ext_str.encode()).hexdigest()[:16]

    cache_dir = RESEARCH_CACHE / ticker
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"stage2_{ext_hash}.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            logger.info("[RESEARCHER] Stage2 cache hit for %s", ticker)
            return data
        except Exception:
            pass

    # Trim to stay inside TPM limits
    ext_trimmed = json.dumps(extractions, indent=1)[:30000]
    prompt = _STAGE2_PROMPT.format(
        ticker=ticker,
        is_financial="Yes" if is_financial else "No",
        extractions_json=ext_trimmed,
    )

    try:
        cards = gemini_generate_json(
            prompt=prompt,
            task="reasoning",
            system=_STAGE2_SYSTEM,
            temperature=0.1,
            max_tokens=8192,
        )
        if not isinstance(cards, dict):
            raise ValueError(f"Expected dict from Stage 2, got {type(cards)}")

        result = {
            "status": "ok",
            "ticker": ticker,
            "extraction_hash": ext_hash,
            "generated_at": datetime.now().isoformat(),
            "cards_raw": cards,
        }
        cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        logger.info("[RESEARCHER] Stage2 complete for %s", ticker)
        return result

    except LLMError as e:
        logger.error("[RESEARCHER] Stage2 LLM error (%s): %s", e.kind, e)
        return {"status": f"llm_{e.kind}", "ticker": ticker}
    except Exception as e:
        logger.error("[RESEARCHER] Stage2 error: %s", e)
        return {"status": "error", "ticker": ticker, "detail": str(e)[:200]}


# ── Card assembly ──────────────────────────────────────────────────────────────

def _delta_pct(guided: Optional[float], actual: Optional[float]) -> Optional[str]:
    """Compute % delta between guided and actual (Python arithmetic, not LLM)."""
    if guided is None or actual is None:
        return None
    try:
        g = float(guided)
        a = float(actual)
        if g == 0:
            return None
        pct = (a - g) / abs(g) * 100
        return f"{pct:+.1f}%"
    except (TypeError, ValueError):
        return None


def _assemble_cards(ticker: str, stage2: dict, docs_used: list[str]) -> dict:
    """
    Convert Stage 2 raw JSON into the FINN card format.
    Enforces integrity rules: no verdict without both sides, compute deltas in Python.
    """
    raw = stage2.get("cards_raw", {})
    limited_data = stage2.get("cards_raw", {}).get("limited_data", False)

    provenance_base = {
        "docs_used": docs_used,
        "model_used": "Gemini (reasoning)",
        "generated_at": stage2.get("generated_at", datetime.now().isoformat()),
        "status": "limited_data" if limited_data else "live",
    }

    cards = []

    # ── Snapshot ──────────────────────────────────────────────────────────────
    snap_raw = raw.get("snapshot")
    if snap_raw:
        cards.append({
            "card_type": "snapshot",
            "ticker": ticker,
            "company_name": ticker.replace(".NS", "").replace(".BO", ""),
            "generated_at": provenance_base["generated_at"],
            "data": {
                "business_summary": snap_raw.get("business_summary", ""),
                "segments": snap_raw.get("segments", []),
                "key_metrics": snap_raw.get("key_metrics", []),
            },
            "provenance": provenance_base,
        })

    # ── Trajectory ────────────────────────────────────────────────────────────
    traj_raw = raw.get("trajectory", [])
    if traj_raw:
        cards.append({
            "card_type": "trajectory",
            "ticker": ticker,
            "company_name": ticker.replace(".NS", "").replace(".BO", ""),
            "generated_at": provenance_base["generated_at"],
            "data": {"series": traj_raw},
            "provenance": provenance_base,
        })

    # ── Guidance ──────────────────────────────────────────────────────────────
    guidance_raw = raw.get("guidance", [])
    if guidance_raw:
        cards.append({
            "card_type": "guidance",
            "ticker": ticker,
            "company_name": ticker.replace(".NS", "").replace(".BO", ""),
            "generated_at": provenance_base["generated_at"],
            "data": {"items": guidance_raw},
            "provenance": provenance_base,
        })

    # ── Promised vs. Delivered ────────────────────────────────────────────────
    pvd_raw = raw.get("promised_vs_delivered", [])
    pvd_clean = []
    for row in pvd_raw:
        # Enforce: no verdict when actual is missing
        verdict = row.get("verdict", "insufficient_data")
        actual = row.get("actual_value")
        if actual is None and verdict not in ("pending", "insufficient_data"):
            verdict = "insufficient_data"
        # Compute delta in Python
        delta = _delta_pct(
            _try_float(row.get("guided_value")),
            _try_float(actual),
        )
        pvd_clean.append({
            "quarter": row.get("quarter", ""),
            "metric": row.get("metric", ""),
            "guided_quote": row.get("guided_quote", ""),
            "source_doc": row.get("source_doc", ""),
            "actual_value": actual,
            "actual_period": row.get("actual_period", ""),
            "delta_computed": delta or row.get("delta_computed"),
            "verdict": verdict,
        })

    cards.append({
        "card_type": "promised_vs_delivered",
        "ticker": ticker,
        "company_name": ticker.replace(".NS", "").replace(".BO", ""),
        "generated_at": provenance_base["generated_at"],
        "data": {
            "rows": pvd_clean,
            "limited_data": limited_data,
        },
        "provenance": provenance_base,
    })

    # ── Bull / Bear ───────────────────────────────────────────────────────────
    bb_raw = raw.get("bull_bear", {})
    if bb_raw:
        cards.append({
            "card_type": "bull_bear",
            "ticker": ticker,
            "company_name": ticker.replace(".NS", "").replace(".BO", ""),
            "generated_at": provenance_base["generated_at"],
            "data": {
                "bull": bb_raw.get("bull", []),
                "bear": bb_raw.get("bear", []),
            },
            "provenance": provenance_base,
        })

    return {
        "ticker": ticker,
        "company_name": ticker.replace(".NS", "").replace(".BO", ""),
        "generated_at": provenance_base["generated_at"],
        "cards": cards,
        "sources_used": docs_used,
        "status": "limited_data" if limited_data else "ok",
    }


def _try_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ── Document discovery ─────────────────────────────────────────────────────────

def discover_documents(ticker: str) -> list[Path]:
    """
    Return local PDF paths for a ticker from the documents cache.
    Looks in cache/documents/{ticker}/*.pdf
    """
    doc_dir = DOCUMENTS_CACHE / ticker
    if not doc_dir.exists():
        return []
    return sorted(doc_dir.glob("*.pdf"), key=lambda p: p.name)


# ── Public entry point ─────────────────────────────────────────────────────────

def build_research_cards(ticker: str, force: bool = False) -> dict:
    """
    Full two-stage research pipeline for a ticker.

    Returns a dict with 'cards' list or {'status': 'insufficient_data', 'missing': [...]}.
    Never returns template/fabricated content.
    """
    cache_dir = RESEARCH_CACHE / ticker
    cache_dir.mkdir(parents=True, exist_ok=True)
    final_cache = cache_dir / "_research_cards.json"

    # Fast cache path (6h TTL)
    if final_cache.exists() and not force:
        try:
            cached = json.loads(final_cache.read_text(encoding="utf-8"))
            if cached.get("generated_at"):
                gen_time = datetime.fromisoformat(cached["generated_at"])
                age_h = (datetime.now() - gen_time).total_seconds() / 3600
                if age_h < 6:
                    logger.info("[RESEARCHER] Returning cached cards for %s (%.1fh old)", ticker, age_h)
                    return cached
        except Exception:
            pass

    # ── Discover documents ────────────────────────────────────────────────────
    docs = discover_documents(ticker)
    if not docs:
        return {
            "status": "insufficient_data",
            "ticker": ticker,
            "missing": ["No documents found in cache/documents/{ticker}/. Run the document downloader first."],
            "cards": [],
        }

    # ── Stage 1: Extract per document ─────────────────────────────────────────
    extractions: list[dict] = []
    concall_count = 0
    ar_count = 0

    for doc_path in docs:
        name_lower = doc_path.name.lower()
        if any(k in name_lower for k in ("concall", "transcript", "earnings_call", "q1", "q2", "q3", "q4")):
            ext = _stage1_concall(doc_path, ticker)
            if ext.get("status") == "ok":
                concall_count += 1
            extractions.append(ext)
        else:
            ext = _stage1_annual_report(doc_path, ticker)
            if ext.get("status") == "ok":
                ar_count += 1
            extractions.append(ext)

    logger.info(
        "[RESEARCHER] Stage1 complete for %s: %d concalls, %d annual reports, %d docs total",
        ticker, concall_count, ar_count, len(docs)
    )

    if not extractions or all(e.get("status") != "ok" for e in extractions):
        return {
            "status": "insufficient_data",
            "ticker": ticker,
            "missing": ["Stage 1 extraction failed for all documents. Check document quality or LLM quota."],
            "cards": [],
        }

    # ── Stage 2: Synthesize ────────────────────────────────────────────────────
    stage2_result = _stage2_synthesize(ticker, extractions)

    if stage2_result.get("status") not in ("ok", None):
        kind = stage2_result.get("status", "error")
        if "llm_quota" in kind:
            return {
                "status": "temporarily_unavailable",
                "reason": "Daily LLM budget exhausted. Research cards will be available tomorrow.",
                "ticker": ticker,
                "cards": [],
            }
        return {
            "status": "insufficient_data",
            "ticker": ticker,
            "missing": [f"Stage 2 synthesis failed: {kind}"],
            "cards": [],
        }

    # ── Assemble final card output ─────────────────────────────────────────────
    docs_used = [p.name for p in docs]
    result = _assemble_cards(ticker, stage2_result, docs_used)

    # Persist
    final_cache.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("[RESEARCHER] Research cards persisted for %s (%d cards)", ticker, len(result.get("cards", [])))

    return result
