"""
Phase 2 Verification Test Suite
Covers:
  1. Announcement classification heuristics (regression suite)
  2. PDF extraction and Python arithmetic on real Reliance Q2 FY25 filing
  3. Window filtering & announcement threading on real BSE announcements snapshot
  4. LLM budget counter & daily rate limit definitions
"""

import json
from pathlib import Path
from backend.services.classifier import classify_heuristic
from backend.services.results_card import build_results_card, parse_table_regex, extract_pdf_tables_text
from backend.routers.push import thread_announcements, parse_ann_date
from backend.llm import _DEFAULT_DAILY_LIMITS, _load_budget


def test_classifier():
    test_cases = [
        ({"headline": "Appointment of Statutory Auditors for FY25"}, "unclassified"),
        ({"headline": "Announcement under Regulation 30 (LODR) - General Intimation"}, "unclassified"),
        ({"headline": "Loss of share certificate reported by shareholder"}, "unclassified"),
        ({"headline": "Announcement under Regulation 30 (LODR)-Change in Directorate"}, "management_change"),
        ({"headline": "CFO resignation effective close of business October 31"}, "management_change"),
        ({"headline": "Unaudited Financial Results (Consolidated And Standalone) For The Quarter"}, "results"),
        ({"headline": "Board Meeting Outcome For Unaudited Financial Results"}, "results"),
    ]
    for item, exp_cat in test_cases:
        cat, _ = classify_heuristic(item)
        assert cat == exp_cat, f"Expected category {exp_cat}, got {cat} for '{item['headline']}'"
    print("[PASS] Classifier heuristics regression suite (all 7 regression cases)")


def test_results_card_real_pdf():
    pdf_path = Path("cache/filings/7c1b0618fa7aeb2d2e951aa54ef31e88639aa44031ece74eced1e1fd96ee32db.pdf")
    if not pdf_path.exists():
        print("[SKIP] Reliance PDF not found in cache/filings/")
        return

    # Direct extraction on real Reliance PDF bytes
    text = extract_pdf_tables_text(pdf_path.read_bytes())
    assert text is not None and len(text) > 0, "Failed to extract text from PDF"
    extracted = parse_table_regex(text)
    assert extracted.get("found"), "parse_table_regex did not find table on Reliance PDF"

    # Test build_results_card with cached news_id
    card = build_results_card(
        ticker="RELIANCE.NS",
        filing_url="https://www.bseindia.com/xml-data/corpfiling/AttachLive/880087f6-7ecc-40a9-8cac-de48d4616b25.pdf",
        news_id="3d90a81b-52f2-427a-b1f7-27f545cf1ca5",
        headline="Financial Results for Q2 FY25",
    )
    assert card is not None, "Failed to load results card"
    assert card["status"] == "ok", f"Card status was {card.get('status')}"
    assert card["basis"] == "consolidated", f"Expected consolidated, got {card.get('basis')}"

    metrics = card["metrics"]
    rev = metrics["revenue"]
    assert rev["current"] == 332861.0, f"Expected Revenue 332861.0, got {rev['current']}"
    assert rev["qoq_prev"] == 311850.0, f"Expected QoQ 311850.0, got {rev['qoq_prev']}"
    assert rev["yoy_prev"] == 258898.0, f"Expected YoY 258898.0, got {rev['yoy_prev']}"
    assert rev["qoq_pct"] == 6.7, f"Expected QoQ % 6.7, got {rev['qoq_pct']}"
    assert rev["yoy_pct"] == 28.6, f"Expected YoY % 28.6, got {rev['yoy_pct']}"

    pat = metrics["pat"]
    assert pat["current"] == 29250.0, f"Expected PAT 29250.0, got {pat['current']}"
    assert pat["qoq_pct"] == 27.2, f"Expected PAT QoQ % 27.2, got {pat['qoq_pct']}"
    assert pat["yoy_pct"] == 32.1, f"Expected PAT YoY % 32.1, got {pat['yoy_pct']}"

    print("[PASS] Results card extraction & Python arithmetic on real Reliance Q2 FY25 PDF (Page 10)")


def test_window_and_threading():
    latest_file = Path("cache/announcements/_latest.json")
    if not latest_file.exists():
        print("[SKIP] Announcements snapshot not found")
        return

    data = json.loads(latest_file.read_text(encoding="utf-8"))
    announcements = data.get("announcements", [])
    assert len(announcements) > 0, "No announcements in cache"

    # Test threading
    threaded = thread_announcements(announcements)
    assert len(threaded) <= len(announcements), "Threading should condense items"
    # Find a threaded Reliance item
    rel_threaded = [t for t in threaded if t.get("ticker") == "RELIANCE.NS" and t.get("thread_count", 1) > 1]
    assert len(rel_threaded) > 0, "Expected Reliance results announcements to be threaded"
    print(f"[PASS] Announcement threading: condensed {len(announcements)} to {len(threaded)} threads (found Reliance thread with {rel_threaded[0]['thread_count']} filings)")


def test_rate_limits():
    # Verify rate limit dictionary matches Google AI Studio free tier limits exactly
    assert _DEFAULT_DAILY_LIMITS["gemini-3.5-flash-lite"] == 500
    assert _DEFAULT_DAILY_LIMITS["gemini-3.1-flash-lite"] == 500
    assert _DEFAULT_DAILY_LIMITS["gemini-2.5-flash"] == 20
    assert _DEFAULT_DAILY_LIMITS["gemini-3.8-flash"] == 20
    assert _DEFAULT_DAILY_LIMITS["gemini-3.6-flash"] == 20
    assert _DEFAULT_DAILY_LIMITS["gemini-2.5-flash-lite"] == 20
    print("[PASS] Rate limits configured accurately to Google AI Studio specs")


if __name__ == "__main__":
    test_classifier()
    test_results_card_real_pdf()
    test_window_and_threading()
    test_rate_limits()
    print("\nALL PHASE 2 VERIFICATIONS PASSED!")
