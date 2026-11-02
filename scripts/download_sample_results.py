"""
Download real BSE results PDFs for target benchmark companies:
- INFY.NS (IT)
- TCS.NS (IT)
- TRENT.NS (Retail)
- POLYCAB.NS (Mid-cap Manufacturing)
- HDFCBANK.NS (Banking)
"""

import hashlib
import json
import logging
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

FILINGS_DIR = Path("cache/filings")
FILINGS_DIR.mkdir(parents=True, exist_ok=True)
URL_MAP_FILE = FILINGS_DIR / "_url_map.json"

url_map = {}
if URL_MAP_FILE.exists():
    try:
        url_map = json.loads(URL_MAP_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass

TARGETS = [
    ("INFY.NS", "https://www.bseindia.com/xml-data/corpfiling/AttachLive/26c12463-d44e-4050-bd47-b53cc294b4e0.pdf"),
    ("TCS.NS", "https://www.bseindia.com/xml-data/corpfiling/AttachLive/2b021530-bbc2-4590-8375-cefc205a7132.pdf"),
    ("TRENT.NS", "https://www.bseindia.com/xml-data/corpfiling/AttachLive/386aab9b-d99c-44af-ba52-1bd95d49a60c.pdf"),
    ("POLYCAB.NS", "https://www.bseindia.com/xml-data/corpfiling/AttachLive/4ac93ea0-d4d1-4b85-8849-14a19e0dcceb.pdf"),
    ("HDFCBANK.NS", "https://www.bseindia.com/xml-data/corpfiling/AttachLive/f5d5fb37-aa66-401c-85d6-58ccd3982828.pdf"),
]

for ticker, url in TARGETS:
    if url in url_map and (FILINGS_DIR / f"{url_map[url]}.pdf").exists():
        logging.info("[SKIP] %s already cached as %s.pdf", ticker, url_map[url])
        continue

    logging.info("[DOWNLOAD] Fetching %s results from %s...", ticker, url)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()

        sha256 = hashlib.sha256(content).hexdigest()
        out_file = FILINGS_DIR / f"{sha256}.pdf"
        out_file.write_bytes(content)
        url_map[url] = sha256
        logging.info("[OK] %s saved (%d bytes, SHA: %s)", ticker, len(content), sha256[:12])
    except Exception as e:
        logging.error("[FAIL] %s failed to download: %s", ticker, e)

URL_MAP_FILE.write_text(json.dumps(url_map, indent=2), encoding="utf-8")
print("\nDownload script finished.")
