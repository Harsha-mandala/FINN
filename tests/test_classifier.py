"""
Tests for Announcement Classification & Heuristics
Verifies the required regression test cases:
1. "Appointment of Statutory Auditors" -> unclassified
2. generic "Regulation 30 intimation" -> unclassified
3. "Change in Directorate" -> management_change
4. "CFO resignation" -> management_change
5. "Unaudited Financial Results" -> results
6. "Board Meeting Outcome for Results" -> results
"""

from backend.services.classifier import classify_heuristic


def test_auditor_appointment_is_unclassified():
    item = {"headline": "Appointment of Statutory Auditors for FY25"}
    cat, _ = classify_heuristic(item)
    assert cat == "unclassified", f"Expected unclassified, got {cat}"

    item2 = {"headline": "Outcome of Board Meeting - Re-appointment of Statutory Auditor"}
    cat2, _ = classify_heuristic(item2)
    assert cat2 == "unclassified", f"Expected unclassified, got {cat2}"


def test_generic_regulation_30_is_unclassified():
    item = {"headline": "Announcement under Regulation 30 (LODR) - General Intimation"}
    cat, _ = classify_heuristic(item)
    assert cat == "unclassified", f"Expected unclassified, got {cat}"

    item2 = {"headline": "Disclosure Under Regulation 30 Of SEBI LODR Regulations"}
    cat2, _ = classify_heuristic(item2)
    assert cat2 == "unclassified", f"Expected unclassified, got {cat2}"


def test_change_in_directorate_is_management_change():
    item = {"headline": "Announcement under Regulation 30 (LODR)-Change in Directorate"}
    cat, _ = classify_heuristic(item)
    assert cat == "management_change", f"Expected management_change, got {cat}"

    item2 = {"headline": "Change in Directorate - Resignation of Independent Director"}
    cat2, _ = classify_heuristic(item2)
    assert cat2 == "management_change", f"Expected management_change, got {cat2}"


def test_cfo_resignation_is_management_change():
    item = {"headline": "CFO resignation effective close of business October 31"}
    cat, _ = classify_heuristic(item)
    assert cat == "management_change", f"Expected management_change, got {cat}"

    item2 = {"headline": "Appointment of Chief Financial Officer (CFO)"}
    cat2, _ = classify_heuristic(item2)
    assert cat2 == "management_change", f"Expected management_change, got {cat2}"


def test_unaudited_financial_results_is_results():
    item = {"headline": "Unaudited Financial Results (Consolidated And Standalone) For The Quarter"}
    cat, _ = classify_heuristic(item)
    assert cat == "results", f"Expected results, got {cat}"


def test_board_meeting_for_results_is_results():
    item = {"headline": "Board Meeting Outcome For Unaudited Financial Results"}
    cat, _ = classify_heuristic(item)
    assert cat == "results", f"Expected results, got {cat}"


if __name__ == "__main__":
    test_auditor_appointment_is_unclassified()
    test_generic_regulation_30_is_unclassified()
    test_change_in_directorate_is_management_change()
    test_cfo_resignation_is_management_change()
    test_unaudited_financial_results_is_results()
    test_board_meeting_for_results_is_results()
    print("All classifier regression tests passed successfully!")
