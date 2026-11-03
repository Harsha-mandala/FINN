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

import os
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
Extract guidance items and key qualitative points from this earnings-call transcript.

Return a JSON object:
{
  "guidance_items": [
    {
      "metric": "Revenue / EBITDA margin / EBIT margin / Capex / etc.",
      "direction": "grow|maintain|reduce|target|other",
      "value": "specific number or range if stated, else null",
      "unit": "% / Cr / x / bps / USD / other",
      "horizon": "FY25 / H2 FY25 / FY27 / etc.",
      "verbatim_quote": "exact substring from the transcript",
      "speaker": "Name, Title (if available)",
      "confidence": "explicit if a specific number was given, implied if directional only"
    }
  ],
  "catalysts": [
    {
      "point": "growth driver, deal win, market demand, or competitive advantage",
      "verbatim_quote": "exact substring from transcript",
      "speaker": "Name, Title"
    }
  ],
  "risks": [
    {
      "point": "headwind, margin drag, macro risk, attrition, or client budget pressure",
      "verbatim_quote": "exact substring from transcript",
      "speaker": "Name, Title"
    }
  ]
}

Rules:
- verbatim_quote must be an exact substring of the source text — copy-paste, do not paraphrase.
- Include only forward-looking statements or explicit strategic drivers/risks.
- If no items found for a category, return empty list [].

Transcript (may be truncated):
{transcript}
"""

_AR_EXTRACT_SYSTEM = """
You are extracting structured financial data from an Indian company annual report.
Return ONLY valid JSON — no prose, no markdown.
"""

_AR_EXTRACT_PROMPT = """
Extract the following from this financial statement or annual report text:

1. segment_mix: list of {segment, revenue_cr, revenue_pct, period} — most recent period
2. financials: list of {period, metric, value, unit} — extract Revenue, EBITDA (or Operating Profit / PBT if EBITDA not explicitly stated), PAT, Capex for ALL periods/columns present in the statement table (e.g. Q2 FY27, Q1 FY27, Q2 FY26, FY26, etc. - include at least 3-4 historical periods so multi-period trajectory can be tracked).
3. key_ratios: latest values for ROE, ROCE, D/E, current ratio, interest coverage (or NIM, GNPA, NNPA for banks/NBFCs)
4. growth_drivers: list of strategic initiatives, order wins, capacity additions mentioned
5. risks_and_challenges: list of headwinds, margin pressures, debt/interest burdens, litigation, or regulatory issues mentioned
6. contingent_liabilities: any material items disclosed (text description, amount if given)
7. business_segments: brief description of each segment (1-2 sentences)

Return JSON:
{
  "segment_mix": [...],
  "financials": [...],
  "key_ratios": {...},
  "growth_drivers": [...],
  "risks_and_challenges": [...],
  "contingent_liabilities": [...],
  "business_segments": [...]
}

Rules:
- Only include data that appears explicitly in the text. Set null for anything absent.
- Standardise monetary values to INR crore (Cr). If figures in statement are in ₹ Lakhs, divide by 100. If in ₹ Millions, divide by 10. If in ₹ Crore, keep as is.
- If this is a bank/NBFC, include NIM, GNPA, NNPA, ROA, CAR instead of D/E and capex.

Financial report text (may be truncated to key sections):
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
3. trajectory.series: build multi-period series for Revenue and PAT/EBITDA from the available periods in the extraction. Each series must have at least 2 points.
4. guidance: only items with verbatim_quote present in extraction. Include speaker and horizon.
5. promised_vs_delivered:
   - For guidance from older periods where the actual result is reported in a subsequent filing, extract the pair, compute delta_computed, and assign verdict: "met" | "partial" | "missed".
   - If guidance was given for a future period (e.g. FY27 exit) and the result is not yet available, set actual_value = null, delta_computed = null, and verdict = "pending".
   - If an item was guided for a past period but the actual result is missing from the filings, set verdict = "insufficient_data".
   - Never guess numbers or verdicts without primary-source backing.
6. bull_bear: cite source_ref for every bull and bear argument directly from the catalysts/risks or financial extractions. Include 2-4 points for bull and 2-4 for bear.
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

    prompt = _CONCALL_EXTRACT_PROMPT.replace("{transcript}", text[:55000])

    try:
        items = gemini_generate_json(
            prompt=prompt,
            task="cheap",
            system=_CONCALL_EXTRACT_SYSTEM,
            temperature=0.0,
            max_tokens=4096,
        )
        if isinstance(items, dict):
            raw_guidance = items.get("guidance_items") or items.get("items") or items.get("guidance") or []
            raw_cats = items.get("catalysts") or []
            raw_risks = items.get("risks") or []
        elif isinstance(items, list):
            raw_guidance = items
            raw_cats = []
            raw_risks = []
        else:
            raw_guidance, raw_cats, raw_risks = [], [], []

        norm_text = " ".join(text.split()).lower()
        validated_guidance = []
        for item in raw_guidance:
            quote = item.get("verbatim_quote", "")
            if quote and " ".join(quote.split()).lower() in norm_text:
                validated_guidance.append(item)
            elif quote:
                logger.debug("[RESEARCHER] Dropped guidance item — quote not found in source: %s", quote[:60])

        validated_cats = []
        for item in raw_cats:
            quote = item.get("verbatim_quote", "")
            if quote and " ".join(quote.split()).lower() in norm_text:
                validated_cats.append(item)

        validated_risks = []
        for item in raw_risks:
            quote = item.get("verbatim_quote", "")
            if quote and " ".join(quote.split()).lower() in norm_text:
                validated_risks.append(item)

        result = {
            "status": "ok",
            "doc": doc_path.name,
            "doc_type": "concall",
            "file_hash": h,
            "extracted_at": datetime.now().isoformat(),
            "guidance_items": validated_guidance,
            "catalysts": validated_cats,
            "risks": validated_risks,
        }
        cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        logger.info("[RESEARCHER] Stage1 concall: %d validated guidance items from %s", len(validated_guidance), doc_path.name)
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

    prompt = _AR_EXTRACT_PROMPT.replace("{ar_text}", text[:55000])

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
    prompt = (
        _STAGE2_PROMPT
        .replace("{ticker}", ticker)
        .replace("{is_financial}", "Yes" if is_financial else "No")
        .replace("{extractions_json}", ext_trimmed)
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
    Format Stage 2 output into the 5 final research cards.
    Enforces contract:
    - Never emit a verdict without both guided and actual values
    - Zero template prose; all bullets must be sourced
    - Generates markdown content for smooth frontend rendering
    """
    raw = stage2.get("cards_raw", {})
    limited_data = stage2.get("limited_data", False)
    provenance_base = {
        "docs_used": docs_used,
        "model_used": stage2.get("model_used", "Gemini"),
        "generated_at": stage2.get("generated_at", datetime.now().isoformat()),
        "status": "live",
    }

    cards = []

    # ── Snapshot ──────────────────────────────────────────────────────────────
    snap_raw = raw.get("snapshot")
    if snap_raw:
        lines = []
        if snap_raw.get("business_summary"):
            lines.append(f"**Business Overview**\n{snap_raw['business_summary']}\n")
        if snap_raw.get("segments"):
            lines.append("**Segment Revenue Mix**")
            for s in snap_raw["segments"]:
                share = f" ({s['revenue_share_pct']}%)" if s.get("revenue_share_pct") else ""
                period = f" [{s.get('period')}]" if s.get("period") else ""
                lines.append(f"- **{s.get('name', 'Segment')}**{share}{period}: {s.get('note', '')}")
            lines.append("")
        if snap_raw.get("key_metrics"):
            lines.append("**Key Operating Metrics**")
            for m in snap_raw["key_metrics"]:
                unit = m.get("unit", "")
                lines.append(f"- **{m.get('name')}**: {m.get('value')} {unit} ({m.get('period')}) — Source: {m.get('source_ref')}")
        snap_content = "\n".join(lines).strip()

        cards.append({
            "card_type": "snapshot",
            "ticker": ticker,
            "company_name": ticker.replace(".NS", "").replace(".BO", ""),
            "generated_at": provenance_base["generated_at"],
            "data": {
                "content": snap_content,
                "business_summary": snap_raw.get("business_summary", ""),
                "segments": snap_raw.get("segments", []),
                "key_metrics": snap_raw.get("key_metrics", []),
            },
            "provenance": provenance_base,
        })

    # ── Trajectory ────────────────────────────────────────────────────────────
    traj_raw = raw.get("trajectory", [])
    if traj_raw:
        lines = []
        for m in traj_raw:
            lines.append(f"**{m.get('metric', 'Metric')} Trajectory**")
            series_str = ", ".join([f"{pt.get('period')}: {pt.get('value')}" for pt in m.get("series", [])])
            if series_str:
                lines.append(f"- Historical: {series_str}")
            if m.get("takeaway"):
                lines.append(f"- Insight: {m['takeaway']}")
            if m.get("source_ref"):
                lines.append(f"- Source: {m['source_ref']}")
            lines.append("")
        traj_content = "\n".join(lines).strip()

        cards.append({
            "card_type": "trajectory",
            "ticker": ticker,
            "company_name": ticker.replace(".NS", "").replace(".BO", ""),
            "generated_at": provenance_base["generated_at"],
            "data": {
                "content": traj_content,
                "series": traj_raw,
            },
            "provenance": provenance_base,
        })

    # ── Guidance ──────────────────────────────────────────────────────────────
    guidance_raw = raw.get("guidance", [])
    if guidance_raw:
        lines = []
        for g in guidance_raw:
            lines.append(f"- **{g.get('metric')}** ({g.get('horizon', 'Outlook')}): {g.get('guided_value', 'Target')}")
            if g.get("verbatim_quote"):
                lines.append(f"  Quote: \"{g['verbatim_quote']}\" ({g.get('speaker', 'Management')})")
            if g.get("source_doc"):
                lines.append(f"  Source: {g['source_doc']}")
        guidance_content = "\n".join(lines).strip()

        cards.append({
            "card_type": "guidance",
            "ticker": ticker,
            "company_name": ticker.replace(".NS", "").replace(".BO", ""),
            "generated_at": provenance_base["generated_at"],
            "data": {
                "content": guidance_content,
                "items": guidance_raw,
            },
            "provenance": provenance_base,
        })

    # ── Promised vs. Delivered ────────────────────────────────────────────────
    pvd_raw = raw.get("promised_vs_delivered", [])
    pvd_clean = []
    commitments = []
    lines = []

    for row in pvd_raw:
        verdict = row.get("verdict", "insufficient_data")
        actual = row.get("actual_value")
        if actual is None and verdict not in ("pending", "insufficient_data"):
            verdict = "insufficient_data"
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
        v_cap = verdict.capitalize() if verdict in ("met", "missed", "partial", "pending") else "Pending"
        stmt = f"{row.get('quarter', '')} {row.get('metric', '')}: Guided \'{row.get('guided_quote', '')}\'"
        note = f"Actual: {actual} ({row.get('actual_period', '')}) | Delta: {delta or row.get('delta_computed', 'N/A')} | Source: {row.get('source_doc', '')}"
        commitments.append({
            "statement": stmt,
            "verdict": v_cap,
            "note": note,
        })
        lines.append(f"- **[{v_cap}]** {stmt}\n  {note}")

    pvd_content = "\n".join(lines).strip() if lines else "No past guidance vs delivered items tracked."

    cards.append({
        "card_type": "promised_vs_delivered",
        "ticker": ticker,
        "company_name": ticker.replace(".NS", "").replace(".BO", ""),
        "generated_at": provenance_base["generated_at"],
        "data": {
            "content": pvd_content,
            "commitments": commitments,
            "rows": pvd_clean,
            "limited_data": limited_data,
        },
        "provenance": provenance_base,
    })

    # ── Bull / Bear ───────────────────────────────────────────────────────────
    bb_raw = raw.get("bull_bear", {})
    if bb_raw:
        lines = []
        lines.append("**Bull Case (Key Catalysts & Strengths)**")
        for b in bb_raw.get("bull", []):
            lines.append(f"- **{b.get('argument')}** — Source: {b.get('source_ref')}")
        lines.append("\n**Bear Case (Key Risks & Headwinds)**")
        for b in bb_raw.get("bear", []):
            lines.append(f"- **{b.get('argument')}** — Source: {b.get('source_ref')}")
        bb_content = "\n".join(lines).strip()

        cards.append({
            "card_type": "bull_bear",
            "ticker": ticker,
            "company_name": ticker.replace(".NS", "").replace(".BO", ""),
            "generated_at": provenance_base["generated_at"],
            "data": {
                "content": bb_content,
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

    # If GEMINI_API_KEY is not set in this session, serve cache or return friendly unavailable
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        if final_cache.exists():
            try:
                cached = json.loads(final_cache.read_text(encoding="utf-8"))
                if cached.get("cards"):
                    logger.info("[RESEARCHER] Returning cached cards for %s (no GEMINI_API_KEY in session)", ticker)
                    return cached
            except Exception:
                pass
        return {
            "status": "temporarily_unavailable",
            "reason": "AI research engine is temporarily unavailable. Please try again shortly.",
            "ticker": ticker,
            "cards": [],
        }

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
        if any(k in name_lower for k in ("concall", "transcript", "earnings_call", "analyst_call")) and not any(k in name_lower for k in ("financial", "result", "balance", "profit", "annual_report")):
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
