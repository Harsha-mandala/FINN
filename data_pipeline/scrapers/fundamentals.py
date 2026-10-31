"""
FINN — Fundamentals Scraper (screener.in)
Fetches document links (annual reports, concall transcripts, result PDFs)
for each ticker from screener.in, then downloads the PDFs.

Output: cache/documents/<TICKER>/links.json
        cache/documents/<TICKER>/<filename>.pdf

Strategy:
1. Fetch screener.in company page (HTML)
2. Parse out document links (annual reports, concall transcripts)
3. Download PDFs with polite delays
4. Cache — never re-download a file that already exists

IMPORTANT: Run once; re-running skips already-downloaded files.
"""

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "cache" / "documents"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Screener.in ticker → slug mapping ────────────────────────────────────────
SCREENER_SLUGS = {
    "RELIANCE.NS":   "RELIANCE",
    "HDFCBANK.NS":   "HDFCBANK",
    "INFY.NS":       "INFY",
    "TCS.NS":        "TCS",
    "ICICIBANK.NS":  "ICICIBANK",
    "SUNPHARMA.NS":  "SUNPHARMA",
    "TRENT.NS":      "TRENT",
    "POLYCAB.NS":    "POLYCAB",
    "DIXON.NS":      "DIXON",
    "HBLPOWER.NS":   "HBLPOWER",
    "KALYANKJIL.NS": "KALYANKJIL",
    "CAMS.NS":       "CAMS",
    "LALPATHLAB.NS": "LALPATHLAB",
    "ASTRAL.NS":     "ASTRAL",
    "ZOMATO.NS":     "ZOMATO",
    "IRCTC.NS":      "IRCTC",
    "CDSL.NS":       "CDSL",
    "IDEAFORGE.NS":  "IDEAFORGE",
    "PERSISTENT.NS": "PERSISTENT",
    "DMART.NS":      "DMART",
    "BAJFINANCE.NS": "BAJFINANCE",
    "MOTHERSON.NS":  "MOTHERSON",
}

BASE_URL = "https://www.screener.in/company"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def get_screener_page(slug: str, session: requests.Session) -> BeautifulSoup | None:
    """Fetch and parse the screener.in company page."""
    url = f"{BASE_URL}/{slug}/consolidated/"
    try:
        resp = session.get(url, timeout=20)
        if resp.status_code == 404:
            # Try standalone (non-consolidated)
            url = f"{BASE_URL}/{slug}/"
            resp = session.get(url, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        print(f"  [ERROR] screener.in fetch failed for {slug}: {e}")
        return None


def extract_document_links(soup: BeautifulSoup, slug: str) -> list[dict]:
    """
    Parse screener.in page to extract annual report and concall transcript links.
    Returns list of {type, title, url, year}.
    """
    docs = []

    # ── Annual reports ────────────────────────────────────────────────────────
    # Screener renders these in a section with id="annual-reports"
    ar_section = soup.find("section", {"id": "annual-reports"})
    if ar_section:
        for a_tag in ar_section.find_all("a", href=True):
            href = a_tag["href"]
            if not href.startswith("http"):
                href = urljoin("https://www.screener.in", href)
            title = a_tag.get_text(strip=True)
            year_match = re.search(r"(20\d{2})", title)
            year = year_match.group(1) if year_match else "unknown"
            docs.append({
                "type": "annual_report",
                "title": title,
                "url": href,
                "year": year,
            })

    # ── Concall transcripts ───────────────────────────────────────────────────
    # Usually in a section or div with class containing "documents" or "concalls"
    concall_section = (
        soup.find("section", {"id": "documents"})
        or soup.find("div", {"class": re.compile(r"concall|transcript", re.I)})
    )
    if concall_section:
        for a_tag in concall_section.find_all("a", href=True):
            href = a_tag["href"]
            if not href.startswith("http"):
                href = urljoin("https://www.screener.in", href)
            title = a_tag.get_text(strip=True)
            doc_type = "concall_transcript" if "concall" in title.lower() or "transcript" in title.lower() else "document"
            docs.append({
                "type": doc_type,
                "title": title,
                "url": href,
                "year": None,
            })

    # ── Fallback: scan all PDF-looking links on the page ─────────────────────
    if not docs:
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if ".pdf" in href.lower() or "annual" in href.lower():
                if not href.startswith("http"):
                    href = urljoin("https://www.screener.in", href)
                title = a_tag.get_text(strip=True) or href.split("/")[-1]
                docs.append({
                    "type": "document",
                    "title": title,
                    "url": href,
                    "year": None,
                })

    return docs


def download_pdf(url: str, dest_path: Path, session: requests.Session) -> bool:
    """Download a PDF if it doesn't already exist. Returns True on success."""
    if dest_path.exists():
        print(f"    [SKIP] Already exists: {dest_path.name}")
        return True
    try:
        resp = session.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type and not url.lower().endswith(".pdf"):
            print(f"    [WARN] Not a PDF ({content_type}): {url}")
            return False
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        size_kb = dest_path.stat().st_size // 1024
        print(f"    ✓ {dest_path.name} ({size_kb} KB)")
        return True
    except Exception as e:
        print(f"    [ERROR] Download failed {url}: {e}")
        return False


def safe_filename(url: str, title: str) -> str:
    """Derive a safe filename from URL or title."""
    # Try to get filename from URL
    parsed = urlparse(url)
    name = parsed.path.split("/")[-1]
    if not name.endswith(".pdf"):
        # Derive from title
        name = re.sub(r"[^\w\s-]", "", title)[:60].strip().replace(" ", "_") + ".pdf"
    return name


def run(
    tickers: list[str] | None = None,
    max_annual_reports: int = 2,
    max_concalls: int = 4,
    download_pdfs: bool = True,
):
    """Fetch document links and download PDFs for all tickers."""
    _ALL_TICKERS = list(SCREENER_SLUGS.keys())
    targets = tickers or _ALL_TICKERS
    session = requests.Session()
    session.headers.update(HEADERS)

    master_index = {}

    for ticker in targets:
        slug = SCREENER_SLUGS.get(ticker, ticker.replace(".NS", ""))
        print(f"\n{'='*50}")
        print(f"Processing {ticker} (screener: {slug})")
        ticker_dir = CACHE_DIR / ticker
        ticker_dir.mkdir(exist_ok=True)

        soup = get_screener_page(slug, session)
        time.sleep(2)  # Polite delay

        if soup is None:
            master_index[ticker] = {"error": "scrape_failed", "docs": []}
            continue

        docs = extract_document_links(soup, slug)
        print(f"  Found {len(docs)} document links")

        # Filter and prioritize
        annual_reports = [d for d in docs if d["type"] == "annual_report"][:max_annual_reports]
        concalls = [d for d in docs if d["type"] == "concall_transcript"][:max_concalls]
        other_docs = [d for d in docs if d["type"] == "document"][:2]

        selected_docs = annual_reports + concalls + other_docs

        # Download PDFs
        if download_pdfs:
            for doc in selected_docs:
                filename = safe_filename(doc["url"], doc["title"])
                dest = ticker_dir / filename
                print(f"  Downloading: {doc['title'][:60]}...")
                success = download_pdf(doc["url"], dest, session)
                doc["local_path"] = str(dest) if success else None
                doc["downloaded"] = success
                time.sleep(1.5)  # Polite delay between downloads

        # Write links index
        links_path = ticker_dir / "links.json"
        index_entry = {
            "ticker": ticker,
            "screener_slug": slug,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total_found": len(docs),
            "selected": selected_docs,
        }
        with open(links_path, "w") as f:
            json.dump(index_entry, f, indent=2)

        master_index[ticker] = index_entry
        print(f"  ✓ Links saved to {links_path}")

    # Write master index
    master_path = CACHE_DIR / "_master_index.json"
    with open(master_path, "w") as f:
        json.dump(master_index, f, indent=2)
    print(f"\n✅ Master index written to {master_path}")


if __name__ == "__main__":
    custom = sys.argv[1:] if len(sys.argv) > 1 else None
    run(custom, download_pdfs=True)
