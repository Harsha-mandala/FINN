"""
FINN — Enricher Service (Push-side)
Adds structured enrichment to high-priority announcements:
  1. Management bio  — Gemini with Google Search grounding (cached by company+person)
  2. Results card    — placeholder for Phase 2 (PDF-based extraction)

Error handling:
  - All LLM failures are caught and logged server-side.
  - Users see typed status objects, never raw exception strings or infra details.
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

from backend.config import RESEARCH_CACHE
from backend.llm import LLMError, gemini_generate

logger = logging.getLogger(__name__)

# ── Bio enrichment ────────────────────────────────────────────────────────────

_BIO_CACHE_DIR = RESEARCH_CACHE / "_bios"

_BIO_PROMPT = """
A company has just announced a management change. Find publicly available background on the person.

Company: {company}
Filing text: {filing_text}

Task:
1. Identify the person's full name and the role mentioned in the filing.
2. Write a factual 3-4 line professional bio: previous roles, professional background, why this appointment is notable.
3. Include 1-2 public source URLs (news articles, LinkedIn, company website) where this is verified.

Output format — valid JSON only:
{{
  "person_name": "Full Name",
  "role": "CFO / Director / etc.",
  "bio": "3-4 line prose bio here.",
  "sources": ["https://...", "https://..."]
}}

Rules:
- If you cannot identify a specific person's name from the filing text, return {{"status": "no_person_identified"}}.
- Use only publicly verifiable information. Do not speculate.
- Prose only — no bullet points, no markdown headers.
"""

_BIO_FIELDS_RE = re.compile(
    r"(?:appointment|resignation|cessation|change).*?(?:of\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"
    r".*?(?:as|,\s*)([A-Za-z\s/]+(?:Director|CEO|CFO|COO|MD|CTO|President|Officer))",
    re.IGNORECASE,
)


def _extract_person_hint(text: str) -> Optional[str]:
    """Best-effort extraction of person name from a filing headline."""
    m = _BIO_FIELDS_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _bio_cache_key(company: str, filing_text: str) -> str:
    payload = f"{company.lower()}:{filing_text[:200].lower()}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def get_management_bio(
    company: str,
    filing_text: str,
    allow_network: bool = True,
) -> Optional[dict]:
    """
    Return a structured bio dict or None.
    Tries to identify the person first; skips if no person is findable.
    Uses Google Search grounding on GEMINI_MODEL.
    Caches by content hash.

    Returns None (not an error string) on any failure — callers must hide the bio block.
    """
    # Cache lookup first
    _BIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = _bio_cache_key(company, filing_text)
    cache_file = _BIO_CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if data.get("status") != "no_person_identified" and data.get("person_name"):
                return data
            return None
        except Exception:
            pass

    if not allow_network:
        return None

    # Quick check: is there a plausible person name or key management title in the text?
    person_hint = _extract_person_hint(filing_text)
    has_mgmt_title = bool(re.search(r"\b(director|ceo|cfo|coo|md|president|officer)\b", filing_text, re.IGNORECASE))
    if not person_hint and not has_mgmt_title:
        logger.debug("[ENRICHER] No person name or title found in filing, skipping bio: %s", filing_text[:80])
        return None

    # Call LLM with grounding
    prompt = _BIO_PROMPT.format(
        company=company,
        filing_text=filing_text[:600],
    )

    try:
        from backend.llm import gemini_generate_json
        result = gemini_generate_json(
            prompt=prompt,
            task="reasoning",
            temperature=0.3,
            max_tokens=512,
            grounded=True,
        )
        if isinstance(result, dict):
            if result.get("status") == "no_person_identified":
                cache_file.write_text(json.dumps(result), encoding="utf-8")
                return None
            # Validate required fields
            if result.get("bio") and result.get("person_name"):
                cache_file.write_text(json.dumps(result), encoding="utf-8")
                return result
    except LLMError as e:
        # quota/model issues — skip silently, don't surface to user
        logger.warning("[ENRICHER] Bio LLM call failed (%s), skipping bio", e.kind)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("[ENRICHER] Bio parse error: %s, skipping", e)

    return None


# ── Results enrichment (Phase 2 placeholder) ──────────────────────────────────

def get_results_enrichment(
    ticker: str,
    filing_url: Optional[str] = None,
) -> Optional[dict]:
    """
    Extract Revenue/EBITDA/PBT/PAT from a results filing PDF.
    Phase 2 will implement full pdfplumber extraction.
    Returns None when data is unavailable (callers show the filing link instead).
    """
    # Check for cached extraction
    ticker_cache = RESEARCH_CACHE / ticker
    if ticker_cache.exists():
        for f in sorted(ticker_cache.glob("*_results.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("status") == "ok" and data.get("data"):
                    return data["data"]
            except Exception:
                pass
    return None


# ── Main enrichment entry point ───────────────────────────────────────────────

def enrich_announcement(announcement: dict, allow_network: bool = True) -> dict:
    """
    Add enrichment to a high-priority announcement.
    Returns announcement with an 'enrichment' field:
      {"type": "management_bio", "person_name": ..., "bio": ..., "sources": [...]}
      {"type": "results_card", "data": {...}}
      None  — if no enrichment could be produced
    All failures are logged server-side and result in enrichment=None, not error strings.
    """
    category = announcement.get("category", "")
    ticker = announcement.get("ticker", "")
    company = ticker.replace(".NS", "").replace(".BO", "")
    headline = announcement.get("headline", "")
    filing_url = announcement.get("attachment_url")
    news_id = announcement.get("news_id")

    enrichment = None

    if category == "management_change":
        bio_data = get_management_bio(company, headline, allow_network=allow_network)
        if bio_data and bio_data.get("bio"):
            enrichment = {
                "type": "management_bio",
                "person_name": bio_data.get("person_name", ""),
                "role": bio_data.get("role", ""),
                "bio": bio_data.get("bio", ""),
                "sources": bio_data.get("sources", []),
            }

    elif category == "results":
        from backend.services.results_card import build_results_card
        res_card = build_results_card(
            ticker=ticker,
            filing_url=filing_url,
            news_id=news_id,
            headline=headline,
            allow_download=allow_network,
        )
        if res_card and res_card.get("status") == "ok":
            enrichment = {
                "type": "results_card",
                "data": res_card,
            }

    ann = {**announcement}
    ann["enrichment"] = enrichment
    return ann
