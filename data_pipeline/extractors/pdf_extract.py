"""
FINN — PDF Text Extractor
Extracts text from PDFs using pdfplumber (primary) with Gemini as fallback.
Caches output keyed by file hash — no document is processed twice.

Output: cache/research/<TICKER>/<file_hash>_extract.json
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

import pdfplumber

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
RESEARCH_CACHE = ROOT / "cache" / "research"
RESEARCH_CACHE.mkdir(parents=True, exist_ok=True)


def file_hash(path: Path) -> str:
    """SHA-256 hash of file contents — used as cache key."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]  # 16 chars is enough for uniqueness


def extract_with_pdfplumber(pdf_path: Path, max_pages: int = 150) -> str:
    """
    Extract text from PDF using pdfplumber.
    Limits to max_pages to keep token counts reasonable.
    Returns extracted text string.
    """
    text_parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_to_read = min(len(pdf.pages), max_pages)
            for i, page in enumerate(pdf.pages[:pages_to_read]):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    text_parts.append(f"--- Page {i+1} ---\n{page_text.strip()}")
    except Exception as e:
        print(f"  [pdfplumber ERROR] {pdf_path.name}: {e}")
        return ""

    return "\n\n".join(text_parts)


def extract_with_gemini(pdf_path: Path, api_key: str) -> str:
    """
    Fallback: use Gemini 1.5 Flash with native PDF input to extract text.
    Uses the file upload API for large PDFs.
    """
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
        print(f"  [Gemini] Extracting {pdf_path.name} ({file_size_mb:.1f} MB)...")

        # Upload file to Gemini
        uploaded = genai.upload_file(str(pdf_path), mime_type="application/pdf")

        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(
            [
                uploaded,
                (
                    "Extract all text from this PDF document. "
                    "Preserve the structure: section headers, tables (as plain text), "
                    "and paragraph breaks. Do not summarise — output the full text."
                ),
            ]
        )
        return response.text
    except Exception as e:
        print(f"  [Gemini fallback ERROR] {pdf_path.name}: {e}")
        return ""


def extract_pdf(
    pdf_path: Path,
    ticker: str,
    doc_type: str = "document",
    gemini_api_key: Optional[str] = None,
    force: bool = False,
) -> dict:
    """
    Main extraction function. Checks cache first, then extracts.
    Returns dict with text and metadata.
    """
    fhash = file_hash(pdf_path)
    cache_dir = RESEARCH_CACHE / ticker
    cache_dir.mkdir(exist_ok=True)
    cache_path = cache_dir / f"{fhash}_extract.json"

    # ── Cache hit ─────────────────────────────────────────────────────────────
    if cache_path.exists() and not force:
        with open(cache_path) as f:
            cached = json.load(f)
        if cached.get("text"):
            print(f"  [CACHE] {pdf_path.name}")
            return cached

    # ── Extract ───────────────────────────────────────────────────────────────
    print(f"  [EXTRACT] {pdf_path.name}")
    text = extract_with_pdfplumber(pdf_path)

    # If pdfplumber got < 500 chars, try Gemini
    if len(text) < 500 and gemini_api_key:
        print(f"  [WARN] pdfplumber got only {len(text)} chars, trying Gemini...")
        text = extract_with_gemini(pdf_path, gemini_api_key)

    result = {
        "ticker": ticker,
        "doc_type": doc_type,
        "file_name": pdf_path.name,
        "file_hash": fhash,
        "file_path": str(pdf_path),
        "char_count": len(text),
        "text": text,
        "extraction_method": "pdfplumber" if text else "failed",
    }

    # ── Cache write ───────────────────────────────────────────────────────────
    with open(cache_path, "w") as f:
        json.dump(result, f, indent=2)

    if not text:
        print(f"  [ERROR] Failed to extract text from {pdf_path.name}")
    else:
        print(f"  ✓ Extracted {len(text):,} chars from {pdf_path.name}")

    return result


def extract_all_for_ticker(
    ticker: str,
    gemini_api_key: Optional[str] = None,
) -> list[dict]:
    """
    Extract text from all PDFs in cache/documents/<TICKER>/.
    Returns list of extraction results.
    """
    ticker_doc_dir = ROOT / "cache" / "documents" / ticker
    if not ticker_doc_dir.exists():
        print(f"  [WARN] No document directory for {ticker}")
        return []

    # Load links.json to get doc_type metadata
    links_path = ticker_doc_dir / "links.json"
    doc_types = {}
    if links_path.exists():
        with open(links_path) as f:
            links_data = json.load(f)
        for doc in links_data.get("selected", []):
            if doc.get("local_path"):
                fname = Path(doc["local_path"]).name
                doc_types[fname] = doc.get("type", "document")

    results = []
    for pdf_path in sorted(ticker_doc_dir.glob("*.pdf")):
        doc_type = doc_types.get(pdf_path.name, "document")
        result = extract_pdf(pdf_path, ticker, doc_type, gemini_api_key)
        results.append(result)

    return results


if __name__ == "__main__":
    import sys
    api_key = os.getenv("GEMINI_API_KEY")
    ticker = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE.NS"
    results = extract_all_for_ticker(ticker, gemini_api_key=api_key)
    print(f"\n✅ Extracted {len(results)} documents for {ticker}")
