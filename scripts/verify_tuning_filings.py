import pdfplumber

def verify_filing(name, pdf_path, page_num, keywords):
    print("=" * 70)
    print(f"VERIFICATION: {name} (PDF: {pdf_path}, Page: {page_num})")
    print("=" * 70)
    with pdfplumber.open(pdf_path) as pdf:
        text = pdf.pages[page_num - 1].extract_text()
        lines = text.splitlines()
        # Print top 15 lines (headers)
        print("--- HEADERS / PERIOD LINES ---")
        for l in lines[:15]:
            l_clean = l.encode('ascii', errors='replace').decode('ascii')
            if any(h in l_clean.lower() for h in ['quarter', 'particulars', 'ended', 'result', 'crore', 'million', 'unaudited', 'audited']):
                print("  ", l_clean)
        print("\n--- METRIC LINES ---")
        for l in lines:
            l_clean = l.encode('ascii', errors='replace').decode('ascii')
            for kw in keywords:
                if kw.lower() in l_clean.lower():
                    print(f"   [{kw}] -> {l_clean}")
                    break

def main():
    verify_filing(
        "RELIANCE.NS",
        "cache/filings/7c1b0618fa7aeb2d2e951aa54ef31e88639aa44031ece74eced1e1fd96ee32db.pdf",
        10,
        ["Revenue from Operations", "Profit Before Tax", "Finance Costs", "Depreciation", "Profit for the period"]
    )
    verify_filing(
        "TCS.NS",
        "cache/filings/038ef1c48011691a344e0c051d68ec515097938e15300a2fd22d7ebbdcfc9419.pdf",
        8,
        ["Revenue from operations", "Profit before tax", "Finance costs", "Depreciation", "Profit for the period"]
    )
    verify_filing(
        "TRENT.NS",
        "cache/filings/3d238861f122612281c0ce4ccd21b8b9cfda3f4f09b8473d7cf87d884aafa568.pdf",
        10,
        ["Revenue from Operations", "Profit / (Loss) Before Tax", "Profit Before Tax", "Finance Costs", "Depreciation", "Profit / (Loss) for the period", "Profit for the period"]
    )
    verify_filing(
        "POLYCAB.NS",
        "cache/filings/79e9770fac27e6a469ed0d29890f42e357535595cf91b3f3423eeaa5b1411d69.pdf",
        4,
        ["Revenue from operations", "Total income", "Profit before tax", "Depreciation", "Finance costs", "Profit for the period"]
    )
    verify_filing(
        "HDFCBANK.NS",
        "cache/filings/1a25f460842bbd8e3632a000cdbc625d7aa1ec2934d3b0d8b60d270bb33e3bdf.pdf",
        2,
        ["Interest earned", "Other Income", "Total Income", "Interest expended", "Profit from ordinary", "Net Profit for the period"]
    )
    verify_filing(
        "INFY.NS (Standalone)",
        "cache/filings/65e459d2b8bc4ed1e754d15250e209f68db29d06e0b98593c7a023d29b6ef151.pdf",
        22,
        ["Revenue from operations", "Profit before tax", "Finance cost", "Depreciation", "Profit for the period"]
    )

if __name__ == "__main__":
    main()
