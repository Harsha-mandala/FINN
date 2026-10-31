"""
FINN — Enricher Service
Handles push-side enrichment:
1. Results card — QoQ/YoY table for results announcements
2. Management bio — bio of incoming/outgoing executive using Gemini + search grounding
"""

import json
import os
from pathlib import Path
from typing import Optional

import google.generativeai as genai

from backend.config import RESEARCH_CACHE, DOCUMENTS_CACHE

MANAGEMENT_BIO_PROMPT = """
A company has just announced a management change. Find background information about the person mentioned.

Company: {company}
Announcement: {announcement_text}

Write a brief, factual 3-4 line professional bio of the incoming/outgoing executive mentioned.
Include: their previous role(s), professional background, and why this appointment is notable.
Use only publicly available information.
Be specific and factual — no filler phrases.
Format as plain prose, no bullet points.

If the person is not identifiable from the announcement, say "Background information not available."
"""

RESULTS_SUMMARY_PROMPT = """
A company has filed quarterly results. Extract the headline financial numbers.

Company: {company}
Quarter: {period}
Announcement: {announcement_text}

Look for Revenue, EBITDA, PBT, and PAT figures.
If you can identify the numbers from the announcement headline/summary alone, extract them.
Return valid JSON:
{{
  "found": true/false,
  "revenue_crore": number or null,
  "ebitda_crore": number or null,
  "pbt_crore": number or null,
  "pat_crore": number or null,
  "period": "Q2 FY25",
  "note": "any extraction note"
}}
"""


def get_management_bio(
    company: str,
    announcement_text: str,
    api_key: str,
) -> str:
    """Get management bio using Gemini with Google Search grounding."""
    try:
        genai.configure(api_key=api_key)

        # Use search grounding for up-to-date bio
        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            tools=[{"google_search": {}}],
        )

        prompt = MANAGEMENT_BIO_PROMPT.format(
            company=company,
            announcement_text=announcement_text[:500],
        )

        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"  [WARN] Bio enrichment failed: {e}")
        # Fallback: no-search version
        try:
            model_basic = genai.GenerativeModel("gemini-1.5-flash")
            response = model_basic.generate_content(
                MANAGEMENT_BIO_PROMPT.format(
                    company=company,
                    announcement_text=announcement_text[:500],
                )
            )
            return response.text.strip()
        except Exception as e2:
            return f"Background information not available. ({e2})"


def get_results_enrichment(
    company: str,
    period: str,
    announcement_text: str,
    api_key: str,
    ticker: str,
) -> Optional[dict]:
    """
    Try to extract headline numbers from the announcement text.
    Falls back to cached extraction from the actual PDF.
    """
    # First: check if we have cached PDF extraction for this ticker
    ticker_cache = RESEARCH_CACHE / ticker
    if ticker_cache.exists():
        results_files = list(ticker_cache.glob("*_results.json"))
        if results_files:
            # Return the most recently modified results extraction
            latest = max(results_files, key=lambda p: p.stat().st_mtime)
            with open(latest) as f:
                cached = json.load(f)
            if cached.get("headline"):
                return cached["headline"]

    # Fallback: try to extract from announcement text itself
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            generation_config={"response_mime_type": "application/json"},
        )
        prompt = RESULTS_SUMMARY_PROMPT.format(
            company=company,
            period=period,
            announcement_text=announcement_text[:2000],
        )
        response = model.generate_content(prompt)
        data = json.loads(response.text)
        if data.get("found"):
            return data
    except Exception as e:
        print(f"  [WARN] Quick results extraction failed: {e}")

    return None


def enrich_announcement(
    announcement: dict,
    api_key: str,
) -> dict:
    """
    Add enrichment to a high-priority announcement.
    Returns the announcement with 'enrichment' field populated.
    """
    category = announcement.get("category", "")
    ticker = announcement.get("ticker", "")
    company = ticker.replace(".NS", "").replace(".BO", "")
    headline = announcement.get("headline", "")

    enrichment = {}

    if category == "management_change":
        print(f"  [ENRICH] Getting bio for {company}...")
        bio = get_management_bio(company, headline, api_key)
        enrichment = {"type": "management_bio", "bio": bio}

    elif category == "results":
        print(f"  [ENRICH] Getting results numbers for {company}...")
        numbers = get_results_enrichment(
            company=company,
            period="latest",
            announcement_text=headline,
            api_key=api_key,
            ticker=ticker,
        )
        if numbers:
            enrichment = {"type": "results_card", "data": numbers}

    announcement["enrichment"] = enrichment or None
    return announcement
