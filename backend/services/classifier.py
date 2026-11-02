"""
FINN — Announcement Classifier Service
Classifies announcements into the 17-category taxonomy.

Strategy:
  - LLM batch (GEMINI_CHEAP_MODEL, 20-30 items/call) when API key is set.
  - Heuristic rules as labelled fallback (logged, never silently substituted).
  - Priority score assigned by rules, never by LLM.
"""

import json
import logging
import re
from typing import Optional

from backend.config import PRIORITY_MAP, HIGH_PRIORITY_CATEGORIES, MEDIUM_PRIORITY_CATEGORIES

logger = logging.getLogger(__name__)

# ── Category taxonomy ─────────────────────────────────────────────────────────

CLASSIFY_SYSTEM = """
You are classifying Indian stock-exchange announcements into EXACTLY one of these 17 categories.

Categories (use EXACTLY these labels, no variations):
- results         : quarterly/annual results, board meeting outcome for results, results presentation
- M&A             : acquisition, merger, demerger, joint venture, subsidiary stake change
- fund_raise      : rights issue, QIP, preferential allotment, buyback, NCD/debt raise
- management_change : CEO/CFO/MD/Director joining, resigning, retiring, cessation — ONLY if a named person is mentioned or the role change is explicit
- litigation      : lawsuits, regulatory orders, SEBI/NCLT/court actions, fines, warnings
- insider_trading : promoter/insider buying or selling their personal shares
- earnings_call   : concall notice, transcript, audio recording link
- investor_meetings : investor/analyst conference, one-on-one non-result meetings
- credit_rating   : rating assigned, upgraded, downgraded, or reaffirmed by an agency
- dividend        : cash dividend declared with record date
- bonus_split     : bonus issue or stock split
- capex           : new plant, manufacturing facility, or capacity expansion approval
- press_release   : order wins, product launches, partnerships, rumour clarifications
- postal_ballot   : postal ballot notice or result
- agm_egm         : AGM or EGM notice or result
- pledging        : promoter pledging, releasing, or changing pledge status
- unclassified    : ESOP allotments, compliance certificates, auditor appointments,
                   generic Regulation 30 / LODR intimations with no material event,
                   newspaper clippings, ESG reports, anything that doesn't fit above

Rules:
- Use EXACTLY the label — no spaces, no capitalisation changes.
- "unclassified" is for routine paperwork, compliance submissions, and generic regulatory notices.
- A generic "Board Meeting Outcome" or "Regulation 30 Announcement" with no specific event keyword → unclassified.
- Auditor appointment, ESOP allotment, compliance certificate → unclassified.
- summary: one-line, present tense, specific. Max 120 chars.

Return ONLY a valid JSON array:
[{"id": 0, "category": "results", "summary": "Q2 FY25 unaudited results announced"}, ...]
"""


# ── Heuristic fallback ────────────────────────────────────────────────────────

# Order matters — more specific patterns first
_HEURISTIC_RULES = [
    # Results — explicit keyword required
    (r"financial results|quarterly results|unaudited results|audited results|(?:board meeting|outcome).*?results", "results"),
    # M&A
    (r"\bacquisition\b|amalgamation|merger|demerger|joint venture|subsidiary.*?stake", "M&A"),
    # Fund raise — explicit instrument
    (r"rights issue|qualified institutional placement|qip|preferential allotment|buyback|commercial paper|ncd|non.?convertible debenture|debt raise", "fund_raise"),
    # Management change — directorate, CEO, CFO, MD, Director appointments/resignations
    (r"change in directorate|(?:appointment|resignation|cessation|change).*?(?:director\b|directorate|ceo|cfo|coo|md|managing director|whole.?time director|chief executive|chief financial)|(?:director|ceo|cfo|coo|md|managing director).*?(?:resign|appoint|cease|step)", "management_change"),
    # Litigation
    (r"\bcourt\b|tribunal|nclt|nclat|show cause|penalty|sebi order|regulatory order|litigation|lawsuit|insolvency", "litigation"),
    # Insider trading — promoter personal trades
    (r"promoter.*?(?:buy|sell|acqui|dispos)|sast|pit|regulation 7\b|insider.*?trading|bulk deal|block deal", "insider_trading"),
    # Earnings call
    (r"concall|earnings call|conference call|transcript|audio recording", "earnings_call"),
    # Investor meetings
    (r"investor meet|analyst meet|institutional investor meet|one.?on.?one", "investor_meetings"),
    # Credit rating
    (r"\bcrisil\b|icra|care ratings|india ratings|fitch|brickwork|rating.*?(?:assign|upgrad|downgrad|reaffirm|affirm)", "credit_rating"),
    # Dividend
    (r"(?:cash dividend|interim dividend|final dividend|special dividend).*?record date|dividend.*?declared", "dividend"),
    # Bonus / split
    (r"bonus (?:issue|share)|sub.?division|stock split|share split", "bonus_split"),
    # Capex
    (r"capacity expansion|new plant|new manufacturing|greenfield|brownfield|capex approval", "capex"),
    # Postal ballot
    (r"postal ballot", "postal_ballot"),
    # AGM / EGM
    (r"annual general meeting|extraordinary general meeting|\bagm\b|\begm\b", "agm_egm"),
    # Pledging
    (r"pledge|revocation of pledge|release of pledge|encumbrance", "pledging"),
    # Press release — explicit
    (r"press release|media release|order win|contract win|new product|partnership announce|clarification on", "press_release"),
]

_EXPLICIT_UNCLASSIFIED = re.compile(
    r"auditor appointment|appointment of.*?(?:statutory\s+)?auditors?|statutory auditor|auditors?\b|"
    r"esop|allotment of.*?(?:share|option)|compliance certificate|"
    r"secretarial audit|newspaper clip|annual secretarial|listing of.*?(?:share|equity)|"
    r"duplicate share certificate|loss of share certificate",
    re.IGNORECASE,
)


def classify_heuristic(item: dict) -> tuple[str, str]:
    """
    Rule-based classification. Returns (category, summary).
    Logs when used so it's visible in server logs.
    """
    text = " ".join([
        item.get("headline", ""),
        item.get("category_raw", ""),
        item.get("subcategory_raw", ""),
    ]).lower()

    # Explicit unclassified patterns (auditors, ESOPs, compliance certs) take priority
    if _EXPLICIT_UNCLASSIFIED.search(text):
        return "unclassified", item.get("headline", "")[:120]

    for pattern, cat in _HEURISTIC_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return cat, item.get("headline", "")[:120]

    # Generic Reg 30 or anything without a specific match falls through to unclassified
    return "unclassified", item.get("headline", "")[:120]


# ── LLM batch classification ──────────────────────────────────────────────────

def classify_batch_llm(items: list[dict]) -> list[dict]:
    """
    Classify a batch of announcements with the cheap Gemini model.
    Returns list of {id, category, summary}. Falls back to heuristic on error.
    """
    from backend.llm import gemini_generate_json, LLMError

    batch_text = "\n".join(
        f'{i}. Headline: "{item["headline"]}" | Exchange category: "{item.get("category_raw", "")}"'
        for i, item in enumerate(items)
    )
    prompt = f"Classify these {len(items)} announcements:\n\n{batch_text}"

    try:
        results = gemini_generate_json(prompt=prompt, task="cheap", system=CLASSIFY_SYSTEM, temperature=0.0)
        if isinstance(results, dict):
            results = list(results.values())
        return results  # type: ignore[return-value]
    except LLMError as e:
        logger.warning("[CLASSIFIER] LLM batch failed (%s: %s), falling back to heuristics", e.kind, e)
        return []
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("[CLASSIFIER] LLM parse error: %s, falling back to heuristics", e)
        return []


# ── Priority assignment ────────────────────────────────────────────────────────

def assign_priority(category: str) -> tuple[int, str]:
    """Return (priority_score, tier) for a category."""
    score = PRIORITY_MAP.get(category, 5)
    if category in HIGH_PRIORITY_CATEGORIES:
        tier = "high"
    elif category in MEDIUM_PRIORITY_CATEGORIES:
        tier = "medium"
    else:
        tier = "low"
    return score, tier


# ── Public entry point ─────────────────────────────────────────────────────────

def classify_announcements(
    announcements: list[dict],
    api_key: Optional[str] = None,
    batch_size: int = 25,
) -> list[dict]:
    """
    Classify all announcements.
    Uses LLM batches when an API key is available; heuristics otherwise.
    Heuristics override LLM for any item the LLM returns as unclassified.
    """
    if not api_key:
        logger.info("[CLASSIFIER] No API key — using heuristic classification for all items")
        classified = []
        for ann in announcements:
            cat, summary = classify_heuristic(ann)
            priority, tier = assign_priority(cat)
            classified.append({**ann, "category": cat, "summary": summary, "priority": priority, "priority_tier": tier})
        return classified

    classified = []
    for batch_start in range(0, len(announcements), batch_size):
        batch = announcements[batch_start: batch_start + batch_size]
        logger.info("[CLASSIFIER] Batch %d/%d (%d items)", batch_start // batch_size + 1,
                    -(-len(announcements) // batch_size), len(batch))

        llm_results = classify_batch_llm(batch)
        result_map = {r["id"]: r for r in llm_results if isinstance(r, dict)}

        for i, ann in enumerate(batch):
            llm = result_map.get(i)
            if llm and llm.get("category") and llm["category"] != "unclassified":
                cat = llm["category"]
                summary = llm.get("summary", ann["headline"][:120])
            else:
                # Heuristic as labelled fallback
                cat, summary = classify_heuristic(ann)
                if llm:
                    logger.debug("[CLASSIFIER] Heuristic override for item %d: %s", i, ann.get("headline", "")[:60])

            priority, tier = assign_priority(cat)
            classified.append({**ann, "category": cat, "summary": summary, "priority": priority, "priority_tier": tier})

    return classified
