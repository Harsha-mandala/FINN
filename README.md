# FINN — Financial Investment Agent
### Mobile-First Intelligence Layer for Public-Markets Investors
**ENAM Holdings — AI Engineer Build Challenge Submission**

---

## 🎯 Executive Summary & Philosophy

Modern public-markets investors are drowning in information: price ticks, stock exchange filings, earnings transcripts, and macro noise. Most information aggregated by financial terminals does not move investment conviction. 

**FINN** is built on a simple conviction:
> *The scarce skill is not aggregating information. It is filtering it: surfacing the few things that actually matter and burying everything else, beautifully.*

Interaction model: **card-first, every feed item expands in place to its filing, results table and bio; research is a tap away from the same ticker.**

FINN is a mobile-first financial intelligence agent designed for daily investor workflows across two complementary interaction modes:
1. **Push**: The app proactively reaches out to tell the investor what changed and why they should care (windowed digest, triggered volume/price alerts, mini QoQ/YoY results cards, and executive transition bios).
2. **Pull**: On-demand deep research on any NSE-listed company, featuring our hero accountability engine: **Promised vs. Delivered** (tracking management guidance vs. actual delivery across quarters).

---

## 🏗️ System Architecture

```
┌────────────────────────────────────────────────────────┐
│               FINN Frontend (Mobile PWA)               │
│       React 18 + Vite + TypeScript + Tailwind CSS      │
│   • Feed (Digest)    • Alerts    • Research Dossier    │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP / REST
┌───────────────────────────▼────────────────────────────┐
│                FINN Backend (FastAPI)                  │
│   • SafeJSONResponse (NaN sanitizer)  • CORS Middleware │
│   • Routers: /push (digest/alerts)  /pull  /health     │
│   • Lightweight /health keepalive endpoint (GET & HEAD)│
└─────────────┬────────────────────────────┬─────────────┘
              │                            │
┌─────────────▼──────────────┐   ┌─────────▼─────────────┐
│       Data Pipeline        │   │     AI Model Router   │
│ • yfinance: 6M EOD History │   │ • Cheap Chain:        │
│ • BSE API via curl_cffi    │   │   gemini-3.5-flash-lite│
│   (TLS Chrome 120 bypass)  │   │   batch classification│
│ • screener.in: Filings &   │   │ • Reasoning Chain:    │
│   Concall Transcript Links │   │   gemini-2.5-flash    │
└─────────────┬──────────────┘   │   fundamental research│
              │                  └───────────────────────┘
┌─────────────▼──────────────┐
│     JSON Cache Layer       │
│ • cache/prices/            │
│ • cache/announcements/     │
│ • cache/results/           │
│ • cache/research/          │
│ • cache/documents/         │
└────────────────────────────┘
```

---

## 🔑 Core Features & Innovations

### 1. Push: Windowed Digest & Intelligent Triage
- **Exchange Scraping with TLS Impersonation**: Uses `curl_cffi` to bypass Cloudflare/Akamai anti-bot barriers on stock exchanges, extracting real-time corporate filings.
- **17-Category Domain Taxonomy**: Classifies filings into high conviction buckets (`results`, `M&A`, `management_change`, `fund_raise`, `litigation`, etc.).
- **Three-Tier Priority Filter**:
  - **High (Needs Attention)**: Results, takeovers, CEO/CFO exits.
  - **Medium (Also Today)**: Dividends, capacity expansion, credit ratings.
  - **Low (Routine Paperwork)**: ESOP allotments, routine compliance certificates (collapsed by default).
- **Primary Source Arithmetic Rule**: Financial deltas (QoQ and YoY %) are calculated deterministically in Python code—**never delegated to LLMs**.

### 2. Push: Triggered Alerts Engine
- Proactively flags market anomalies against configurable investor thresholds:
  - **Volume Surges**: Flags when volume exceeds 2× the 20-day moving average (e.g. SUNPHARMA 3.43× volume).
  - **Price Breaks**: Flags price movements crossing ±5.0% (e.g. TRENT +5.44% move).
  - **Material Category Watchlist**: Instant alerts for corporate takeovers and leadership departures.

### 3. Pull: Research Tab (Two-Layer Architecture)
- **Baseline Layer (100% Deterministic Cache, Zero LLM)**:
  - **Latest Results Card**: Extracted directly from quarterly financial statements (Revenue, EBITDA derived or bank Total Income/NII, PBT, PAT with QoQ and YoY deltas, reporting basis, and direct link to the filing PDF).
  - **Price & Volume**: Last close, 1-day %, 6-month SVG sparkline (~125 trading days), and volume vs. 20-day average.
  - **Primary Documents**: Categorized direct links to concall transcripts, results filings, and annual reports.
  - **Recent Priority Filings**: Last 5 high/medium priority threads with category badges and PDF links.
- **Analysis Layer (Primary Source Synthesis)**:
  - **5 Structured Research Cards**:
    1. **Business & Financial Snapshot**: Segment revenue mix, operating margin, and key metrics.
    2. **Multi-Year Trajectory**: Growth compounding drivers and multi-period financial trends.
    3. **Management Guidance**: Explicit forward statements quoted verbatim from earnings calls.
    4. **Promised vs. Delivered (Hero Feature)**: Accountability matrix comparing verbatim guidance against subsequent financial reports with explicit verdicts (`Met ✅`, `Partial ⚠️`, `Missed ❌`, `Pending ⏳`).
    5. **Bull vs. Bear Case**: Balanced, evidence-backed investment thesis citing primary disclosures.
  - Provenance badges: Model used, generation date, and audited source citations.
  - On-Demand Generation: Rate-capped mutex queue (default 3/day) to prevent quota exhaustion.

---

## 🔒 Security Architecture & API Key Management

The Gemini API key is **never written to disk or committed to the repository**:
- `backend/config.py` reads `GEMINI_API_KEY` exclusively from process environment variables (`os.environ.get("GEMINI_API_KEY")`).
- No `.env` files are loaded by Python (`python-dotenv` is removed).
- The repo includes automated secret scanning (`scripts/scan_secrets.py`) attached to pre-commit git hooks, rejecting any staged commits containing API keys.
- Logging filters automatically mask any accidental keys matching `(AQ\.[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{20,})`.
- If `GEMINI_API_KEY` is not set, the web app and all cached baseline data (results cards, prices, filings, documents) continue to serve instantly; batch generation scripts exit cleanly with:
  `"GEMINI_API_KEY is not set in this terminal session. See README, 'Running snapshot jobs'."`

### Running Snapshot Jobs Locally
When updating snapshots or running batch generation, set the key in your terminal session memory without leaving shell history:

**PowerShell (Windows):**
```powershell
$env:GEMINI_API_KEY = Read-Host -Prompt "Enter GEMINI_API_KEY" -AsSecureString | [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($_))

# Run your snapshot jobs:
cmd.exe /c .\.venv\Scripts\python.exe scripts\refresh_snapshot.py
```

**Bash / Zsh (Linux / macOS):**
```bash
read -s GEMINI_API_KEY
export GEMINI_API_KEY

python scripts/refresh_snapshot.py
```

---

## ⏱️ Keeping the Backend Awake (Zero Cold Starts)

Render free instances spin down after 15 minutes of inactivity. To ensure the mobile app loads immediately for judges and users:

1. **Lightweight Keepalive Route**:
   `GET /health` and `HEAD /health` respond in < 5ms with zero disk, network, or LLM overhead.
   *(Note: Never use `/health/llm` for keepalive pings; it makes live Gemini API calls and consumes quota).*
2. **UptimeRobot Setup (Primary)**:
   - Create a free HTTP(s) monitor at [UptimeRobot.com](https://uptimerobot.com)
   - URL: `https://<your-render-app-url>/health`
   - Monitoring Interval: `5 minutes`
   - HTTP Method: `GET` or `HEAD`
3. **GitHub Actions Backup**:
   - FINN includes `.github/workflows/keepalive.yml` which pings every 10 minutes.
   - Add your backend URL under **GitHub → Settings → Secrets and variables → Actions → Variables → `BACKEND_URL`** (e.g., `https://finn-backend.onrender.com`).
4. **Frontend Cold-Start Resilience**:
   - The frontend issues a non-blocking `/health` warm-up call on application mount.
   - API requests feature automatic exponential backoff on HTTP 502/503/504.
   - If the server is spinning up (>1.5s), a subtle banner notifies the user while all cached filings and prices remain immediately viewable.

---

## ⚡ Quickstart Guide

### 1. Prerequisites
- **Python**: Version 3.11+
- **Node.js**: Version 18+

### 2. Backend Setup
```bash
# Navigate to project root
cd d:/enam_assignment

# Start FastAPI backend
cmd.exe /c .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation: `http://localhost:8000/docs`

### 3. Frontend Setup
```bash
cd frontend

# Install dependencies
npm install

# Start Vite dev server
npm run dev
```
Open `http://localhost:5173` *(Switch to Mobile Device View in DevTools for the intended mobile-first experience, or expand the window to view the desktop side-rail interface).*

---

## 🧪 Verification & Real-vs-Mock Status

| Component | Status | Data Source |
| :--- | :--- | :--- |
| **Price & Sparklines** | **REAL** | 22 tickers scraped via `yfinance` with 6-month historical closes |
| **BSE Announcements** | **REAL** | 302 live filings fetched with `curl_cffi` TLS bypass |
| **Quarterly Results Cards** | **REAL** | 34 parsed filings with deterministic deltas; bank accounts handle NII/Total Income |
| **Primary Documents** | **REAL** | Concall and results URLs extracted from Screener/BSE |
| **Deep Research (5 Cards)** | **REAL** | Synthesized via Gemini Flash from primary transcripts for `RELIANCE` and `PERSISTENT` |
| **Secret Scanning** | **PASS** | `scripts/scan_secrets.py` verified across working tree and git pre-commit hook |
| **Frontend PWA Build** | **PASS** | Production Vite build compiled cleanly with zero errors |

---

## 👥 Built for ENAM Holdings
Developed as part of the **ENAM Holdings AI Engineer Build Challenge**.
