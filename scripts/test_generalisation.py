"""
Test results card extraction across 5 diverse benchmark filings:
1. RELIANCE.NS (Conglomerate / Energy & Retail)
2. TCS.NS (IT Services)
3. INFY.NS (IT Services)
4. TRENT.NS (Retail)
5. POLYCAB.NS (Mid-cap Manufacturing)
6. HDFCBANK.NS (Banking)
"""

import io
import json
import re
from pathlib import Path
import pdfplumber

def parse_period_from_text(text: str) -> tuple[str, str, str]:
    """Dynamically determine quarter and FY from filing text."""
    low = text.lower()
    m = re.search(r"ended\s+(?:on\s+)?(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4}|\d{2}[./-]\d{2}[./-]\d{4})", low)
    date_str = m.group(1) if m else ""
    
    # Check for September 2026 / 30.09.2026
    if "sep" in date_str or "09" in date_str or "september" in low[:1500]:
        return "Q2 FY27 (Ended 30-Sep-2026)", "Q1 FY27 (Ended 30-Jun-2026)", "Q2 FY26 (Ended 30-Sep-2025)"
    elif "jun" in date_str or "06" in date_str or "june" in low[:1500]:
        return "Q1 FY27 (Ended 30-Jun-2026)", "Q4 FY26 (Ended 31-Mar-2026)", "Q1 FY26 (Ended 30-Jun-2025)"
    elif "dec" in date_str or "12" in date_str or "december" in low[:1500]:
        return "Q3 FY27 (Ended 31-Dec-2026)", "Q2 FY27 (Ended 30-Sep-2026)", "Q3 FY26 (Ended 31-Dec-2025)"
    elif "mar" in date_str or "03" in date_str or "march" in low[:1500]:
        return "Q4 FY26 (Ended 31-Mar-2026)", "Q3 FY26 (Ended 31-Dec-2025)", "Q4 FY25 (Ended 31-Mar-2025)"
    return "Quarter Ended September 30, 2026", "Preceding Quarter", "Year-Ago Quarter"


def compute_delta(curr, prev):
    if curr is None or prev is None or prev == 0:
        return None
    return round((float(curr) - float(prev)) / abs(float(prev)) * 100, 1)


def parse_filing_pdf(pdf_path: Path, ticker: str):
    is_bank = "BANK" in ticker.upper()
    with pdfplumber.open(pdf_path) as pdf:
        # Scan pages to find the consolidated statement
        target_page_idx = -1
        full_page_text = ""
        is_consolidated = False

        for idx, page in enumerate(pdf.pages[:25]):
            t = page.extract_text() or ""
            low = t.lower()
            if is_bank and ("interest earned" in low or "total income" in low) and ("quarter ended" in low or "unaudited" in low):
                target_page_idx = idx
                full_page_text = t
                is_consolidated = "consolidated" in low
                break
            elif not is_bank and ("revenue from operations" in low or "total income" in low) and ("quarter ended" in low or "unaudited" in low or "three months" in low):
                # Prefer consolidated
                if "consolidated" in low:
                    target_page_idx = idx
                    full_page_text = t
                    is_consolidated = True
                    break
                elif target_page_idx == -1:
                    target_page_idx = idx
                    full_page_text = t
                    is_consolidated = False

        if target_page_idx == -1:
            return {"status": "unavailable", "reason": "No financial table page found"}

        lines = full_page_text.splitlines()
        low_head = full_page_text[:2000].lower()

        # Multiplier
        mult = 1.0
        unit_str = "INR Crore"
        if "million" in low_head:
            mult = 0.1
            unit_str = "INR Crore (norm. from M)"
        elif "lakh" in low_head:
            mult = 0.01
            unit_str = "INR Crore (norm. from L)"

        # Period
        p_curr, p_qoq, p_yoy = parse_period_from_text(full_page_text[:1500])

        def extract_nums(pattern):
            for l in lines:
                # Clean up OCR quirks in line: 'pro1lt', 'proflt' -> 'profit'
                l_fixed = re.sub(r"pro[1lf\s]*t", "profit", l, flags=re.IGNORECASE)
                if re.search(pattern, l_fixed, re.IGNORECASE):
                    clean_l = re.sub(r"\(refer\s+note\s+\d+\)", " ", l_fixed, flags=re.IGNORECASE)
                    clean_l = re.sub(r"\(\s*[\d\s\+\-\*/]+\s*\)", " ", clean_l)  # strip (1)+(2), (3+4), (7-8-9), (1)
                    clean_l = re.sub(r"^\s*[\(\[]?[A-Za-z0-9]+[\)\]\.]\s*", " ", clean_l)  # strip leading 1) or 5) or (a) or 1.
                    clean_l = re.sub(r"^\s*\d+\s+(?=[A-Za-z])", " ", clean_l)  # strip leading index like '3 Total'
                    
                    # Handle OCR commas replacing decimal points e.g. 79362,78 -> 79362.78
                    clean_l = re.sub(r"(\d+),(\d{2})\b", r"\1.\2", clean_l)
                    toks = re.findall(r"\(?\b\d+(?:,\d+)*(?:\.\d+)?\)?", clean_l)
                    nums = []
                    for tok in toks:
                        is_neg = tok.startswith("(") and tok.endswith(")")
                        val_str = tok.strip("()").replace(",", "")
                        try:
                            v = float(val_str)
                            nums.append(round((-v if is_neg else v) * mult, 2))
                        except ValueError:
                            continue
                    if len(nums) >= 3:
                        # If first number is an isolated row index (like 1, 3, 5, 7, 8, 10, 12) and next numbers are much larger
                        if nums[0] < 50 and len(nums) >= 4 and abs(nums[1]) > 100:
                            return nums[1:4]
                        return nums[:3]
            return None

        if is_bank:
            tot_inc = extract_nums(r"total income\s*\(1\)\+\(2\)|total income")
            int_earned = extract_nums(r"interest earned")
            int_exp = extract_nums(r"interest expended")
            pbt = extract_nums(r"profit.*?before tax")
            pat = extract_nums(r"net profit.*?after tax|net profit for the period|profit after tax")

            nii = None
            if int_earned and int_exp:
                nii = [round(int_earned[i] - int_exp[i], 2) for i in range(3)]

            rev_data = tot_inc or nii
            return {
                "status": "success",
                "ticker": ticker,
                "page": target_page_idx + 1,
                "basis": "consolidated" if is_consolidated else "standalone",
                "period": p_curr,
                "is_bank": True,
                "unit": unit_str,
                "revenue_label": "Total Income" if tot_inc else "Net Interest Income",
                "revenue": {"current": rev_data[0] if rev_data else None, "qoq_prev": rev_data[1] if rev_data else None, "yoy_prev": rev_data[2] if rev_data else None, "qoq_pct": compute_delta(rev_data[0], rev_data[1]) if rev_data else None, "yoy_pct": compute_delta(rev_data[0], rev_data[2]) if rev_data else None},
                "nii": {"current": nii[0] if nii else None, "qoq_prev": nii[1] if nii else None, "yoy_prev": nii[2] if nii else None, "qoq_pct": compute_delta(nii[0], nii[1]) if nii else None, "yoy_pct": compute_delta(nii[0], nii[2]) if nii else None} if nii else None,
                "ebitda": {"current": None, "note": "not applicable (banking entity)"},
                "pbt": {"current": pbt[0] if pbt else None, "qoq_prev": pbt[1] if pbt else None, "yoy_prev": pbt[2] if pbt else None, "qoq_pct": compute_delta(pbt[0], pbt[1]) if pbt else None, "yoy_pct": compute_delta(pbt[0], pbt[2]) if pbt else None},
                "pat": {"current": pat[0] if pat else None, "qoq_prev": pat[1] if pat else None, "yoy_prev": pat[2] if pat else None, "qoq_pct": compute_delta(pat[0], pat[1]) if pat else None, "yoy_pct": compute_delta(pat[0], pat[2]) if pat else None},
            }
        else:
            rev = extract_nums(r"revenue from operations|income from operations") or extract_nums(r"total income")
            pbt = extract_nums(r"profit.*?before\s+tax|profit.*?before\s+exceptional")
            pat = extract_nums(r"net profit attributable to.*owners|profit after tax|profit for the period|net profit")
            fin = extract_nums(r"finance costs|finance cost")
            dep = extract_nums(r"depreciation")

            ebitda = None
            if pbt and fin and dep:
                ebitda = [round(pbt[i] + fin[i] + dep[i], 2) for i in range(min(len(pbt), len(fin), len(dep)))]

            return {
                "status": "success",
                "ticker": ticker,
                "page": target_page_idx + 1,
                "basis": "consolidated" if is_consolidated else "standalone",
                "period": p_curr,
                "is_bank": False,
                "unit": unit_str,
                "revenue_label": "Revenue from Operations",
                "revenue": {"current": rev[0] if rev else None, "qoq_prev": rev[1] if rev else None, "yoy_prev": rev[2] if rev else None, "qoq_pct": compute_delta(rev[0], rev[1]) if rev else None, "yoy_pct": compute_delta(rev[0], rev[2]) if rev else None},
                "ebitda": {"current": ebitda[0] if ebitda else None, "qoq_prev": ebitda[1] if ebitda else None, "yoy_prev": ebitda[2] if ebitda else None, "qoq_pct": compute_delta(ebitda[0], ebitda[1]) if ebitda else None, "yoy_pct": compute_delta(ebitda[0], ebitda[2]) if ebitda else None},
                "pbt": {"current": pbt[0] if pbt else None, "qoq_prev": pbt[1] if pbt else None, "yoy_prev": pbt[2] if pbt else None, "qoq_pct": compute_delta(pbt[0], pbt[1]) if pbt else None, "yoy_pct": compute_delta(pbt[0], pbt[2]) if pbt else None},
                "pat": {"current": pat[0] if pat else None, "qoq_prev": pat[1] if pat else None, "yoy_prev": pat[2] if pat else None, "qoq_pct": compute_delta(pat[0], pat[1]) if pat else None, "yoy_pct": compute_delta(pat[0], pat[2]) if pat else None},
            }

if __name__ == "__main__":
    test_files = {
        "RELIANCE.NS": list(Path("cache/filings").glob("7c1b*.pdf"))[0],
        "TCS.NS": list(Path("cache/filings").glob("038ef*.pdf"))[0],
        "TRENT.NS": list(Path("cache/filings").glob("3d23*.pdf"))[0],
        "POLYCAB.NS": list(Path("cache/filings").glob("79e9*.pdf"))[0],
        "HDFCBANK.NS": list(Path("cache/filings").glob("1a25*.pdf"))[0],
    }
    for ticker, path in test_files.items():
        res = parse_filing_pdf(path, ticker)
        print(f"\n=======================================================")
        print(f"TICKER: {ticker} (Page {res.get('page')}, Basis: {res.get('basis')}, Unit: {res.get('unit')})")
        print(f"Period: {res.get('period')}")
        rev = res.get("revenue")
        print(f"{res.get('revenue_label')}: Curr={rev['current']}, QoQ_prev={rev['qoq_prev']} ({rev['qoq_pct']}%), YoY_prev={rev['yoy_prev']} ({rev['yoy_pct']}%)")
        eb = res.get("ebitda")
        if res.get("is_bank"):
            print(f"EBITDA: NOT APPLICABLE ({eb.get('note')})")
            if res.get("nii"):
                nii = res["nii"]
                print(f"NII:    Curr={nii['current']}, QoQ_prev={nii['qoq_prev']} ({nii['qoq_pct']}%), YoY_prev={nii['yoy_prev']} ({nii['yoy_pct']}%)")
        else:
            print(f"EBITDA: Curr={eb['current']}, QoQ_prev={eb['qoq_prev']} ({eb['qoq_pct']}%), YoY_prev={eb['yoy_prev']} ({eb['yoy_pct']}%)")
        pbt = res.get("pbt")
        print(f"PBT:    Curr={pbt['current']}, QoQ_prev={pbt['qoq_prev']} ({pbt['qoq_pct']}%), YoY_prev={pbt['yoy_prev']} ({pbt['yoy_pct']}%)")
        pat = res.get("pat")
        print(f"PAT:    Curr={pat['current']}, QoQ_prev={pat['qoq_prev']} ({pat['qoq_pct']}%), YoY_prev={pat['yoy_prev']} ({pat['yoy_pct']}%)")
