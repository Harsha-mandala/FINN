"""
FINN — Announcement Classifier Service
Uses Gemini 1.5 Flash to classify announcements into the 17-category taxonomy.
Batches 20 items per call for efficiency.
Adds priority score via rules (not LLM).
"""

import json
import os
from typing import Optional

try:
    from google import genai
    from google.genai import types as genai_types
    USE_NEW_SDK = True
except ImportError:
    import google.generativeai as genai  # type: ignore
    USE_NEW_SDK = False

from backend.config import PRIORITY_MAP, HIGH_PRIORITY_CATEGORIES, MEDIUM_PRIORITY_CATEGORIES

CLASSIFY_SYSTEM_PROMPT = """
You are classifying Indian stock exchange announcements into one of 17 categories.

Categories (use EXACTLY these labels):
- results: quarterly/annual results, board meeting for results, results deck
- M&A: acquisition, merger, demerger, joint venture, subsidiary stake change
- fund_raise: rights issue, QIP, preferential allotment, buyback, commercial paper, debt raise
- management_change: CEO/CFO/MD/director joining, resigning, retiring
- litigation: lawsuits, regulatory orders, fines, warnings, insolvency
- insider_trading: promoter/insider buying/selling personal shares
- earnings_call: concall notice, transcript, recording link
- investor_meetings: investor conference, one-on-one meetings
- credit_rating: rating assigned, upgraded, downgraded, or reaffirmed
- dividend: cash dividend declared with record date
- bonus_split: bonus issue or stock split
- capex: new plant, facility, or capacity expansion approval
- press_release: order wins, products, partnerships, rumour clarifications
- postal_ballot: postal ballot notice or result
- agm_egm: AGM or EGM notice or result
- pledging: promoter pledging, releasing, or changing pledge status of shares
- unclassified: ESOP allotments, compliance certs, ESG reports, auditor appointments

Return ONLY valid JSON array, one object per announcement:
[
  {"id": 0, "category": "results", "summary": "one-line summary of the announcement"},
  {"id": 1, "category": "management_change", "summary": "CFO John Smith appointed effective Nov 1"}
]

Rules:
- Use exactly the category labels above — no variations
- Summary: concise, specific, present tense (e.g. "Q2 FY25 results announced" not "The company has announced")
- If uncertain between categories, pick the more specific one
- "unclassified" is for genuinely routine paperwork only
"""


def classify_batch(
    items: list[dict],
    api_key: str,
) -> list[dict]:
    """
    Classify a batch of announcements. items is a list of dicts with 'headline' and 'category_raw'.
    Returns list of dicts with 'category' and 'summary' added.
    """
    # Build prompt
    batch_text = "\n".join(
        f'{i}. Headline: "{item["headline"]}" | Exchange category: "{item.get("category_raw", "")}"'
        for i, item in enumerate(items)
    )
    prompt = f"Classify these {len(items)} announcements:\n\n{batch_text}"

    try:
        if USE_NEW_SDK:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=CLASSIFY_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                ),
            )
            results = json.loads(response.text)
        else:
            genai.configure(api_key=api_key)  # type: ignore
            model = genai.GenerativeModel(  # type: ignore
                "gemini-1.5-flash",
                generation_config={"response_mime_type": "application/json"},
                system_instruction=CLASSIFY_SYSTEM_PROMPT,
            )
            response = model.generate_content(prompt)
            results = json.loads(response.text)

        # Ensure it's a list
        if isinstance(results, dict):
            results = list(results.values())
        return results
    except Exception as e:
        print(f"  [ERROR] Classification failed: {e}")
        # Fallback: mark all as unclassified
        return [{"id": i, "category": "unclassified", "summary": items[i]["headline"][:100]}
                for i in range(len(items))]


import re

HEURISTIC_RULES = [
    (r"financial results|quarterly results|unaudited results|audited results|board meeting.*?results", "results"),
    (r"acquisition|amalgamation|merger|demerger|joint venture|subsidiary stake", "M&A"),
    (r"resignation|appointment|cessation|chief executive|chief financial|director|cfo|ceo|md", "management_change"),
    (r"rights issue|qip|preferential allotment|buyback|commercial paper|debt raise", "fund_raise"),
    (r"dividend|interim dividend|final dividend", "dividend"),
    (r"bonus|sub-division|stock split|share split", "bonus_split"),
    (r"concall|earnings call|conference call|transcript|audio recording", "earnings_call"),
    (r"investor meet|analyst meet|institutional investor", "investor_meetings"),
    (r"rating|crisil|icra|care ratings|india ratings", "credit_rating"),
    (r"court|tribunal|nclt|show cause|penalty|sebi order|litigation|lawsuit", "litigation"),
    (r"capacity expansion|new plant|capex|manufacturing facility", "capex"),
    (r"press release|media release", "press_release"),
    (r"postal ballot", "postal_ballot"),
    (r"annual general meeting|extraordinary general meeting|\bagm\b|\begm\b", "agm_egm"),
    (r"pledge|revocation of pledge|release of pledge", "pledging"),
    (r"insider trading|sast|pit|regulation 7", "insider_trading"),
]

def classify_heuristic(item: dict) -> tuple[str, str]:
    text = f"{item.get('headline', '')} {item.get('category_raw', '')} {item.get('subcategory_raw', '')}".lower()
    for pattern, cat in HEURISTIC_RULES:
        if re.search(pattern, text):
            summary = item.get("headline", "")[:120]
            return cat, summary
    return "unclassified", item.get("headline", "")[:100]

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


def classify_announcements(
    announcements: list[dict],
    api_key: Optional[str] = None,
    batch_size: int = 25,
) -> list[dict]:
    """
    Classify all announcements in batches using Gemini Flash if api_key is provided,
    otherwise using fast domain heuristics.
    """
    classified = []

    if not api_key:
        print("  Using rules-based heuristic classification (no GEMINI_API_KEY)...")
        for ann in announcements:
            cat, summary = classify_heuristic(ann)
            priority, tier = assign_priority(cat)
            enriched = {**ann}
            enriched["category"] = cat
            enriched["summary"] = summary
            enriched["priority"] = priority
            enriched["priority_tier"] = tier
            classified.append(enriched)
        return classified

    for batch_start in range(0, len(announcements), batch_size):
        batch = announcements[batch_start : batch_start + batch_size]
        print(f"  Classifying batch {batch_start//batch_size + 1} ({len(batch)} items)...")

        results = classify_batch(batch, api_key)
        result_map = {r["id"]: r for r in results}

        for i, ann in enumerate(batch):
            result = result_map.get(i)
            if not result or result.get("category") == "unclassified":
                cat, summary = classify_heuristic(ann)
            else:
                cat = result.get("category", "unclassified")
                summary = result.get("summary", ann["headline"][:100])

            priority, tier = assign_priority(cat)

            enriched = {**ann}
            enriched["category"] = cat
            enriched["summary"] = summary
            enriched["priority"] = priority
            enriched["priority_tier"] = tier
            classified.append(enriched)

    return classified
