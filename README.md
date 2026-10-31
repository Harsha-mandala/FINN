# FINN — Financial Investment Agent
### Mobile-First Intelligence Layer for Public-Markets Investors
**ENAM Holdings — AI Engineer Build Challenge Submission**

---

## 🎯 Executive Summary & Philosophy

Modern public-markets investors are drowning in information: price ticks, stock exchange filings, earnings transcripts, and macro noise. Most information aggregated by financial terminals does not move investment conviction. 

**FINN** is built on a simple conviction:
> *The scarce skill is not aggregating information. It is filtering it: surfacing the few things that actually matter and burying everything else, beautifully.*

FINN is a mobile-first financial intelligence agent designed for daily investor workflows across two complementary interaction modes:
1. **Push**: The app proactively reaches out to tell the investor what changed and why they should care (windowed digest, triggered volume/price alerts, mini QoQ/YoY results cards, and executive transition bios).
2. **Pull**: On-demand deep research on any NSE-listed company, featuring our hero accountability engine: **Promised vs. Delivered** (tracking management guidance vs. actual delivery across quarters).

---

## 🏗️ System Architecture

```
┌────────────────────────────────────────────────────────┐
│               FINN Frontend (Mobile PWA)               │
│       React 18 + Vite + TypeScript + Tailwind CSS      │
│   • Feed (Digest)  • Alerts  • Research  • Copilot     │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP / REST
┌───────────────────────────▼────────────────────────────┐
│                FINN Backend (FastAPI)                  │
│   • SafeJSONResponse (NaN sanitizer)  • CORS Middleware │
│   • Routers: /push (digest/alerts)  /pull  /chat       │
└─────────────┬────────────────────────────┬─────────────┘
              │                            │
┌─────────────▼──────────────┐   ┌─────────▼─────────────┐
│       Data Pipeline        │   │     AI Model Router   │
│ • yfinance: 6M EOD History │   │ • Gemini 1.5 Flash:   │
│ • BSE API via curl_cffi    │   │   Batch classification│
│   (TLS Chrome 120 bypass)  │   │   and PDF extraction  │
│ • screener.in: Filings &   │   │ • Claude 3.5 Sonnet:  │
│   Concall Transcript Links │   │   Guidance synthesis  │
└─────────────┬──────────────┘   │   and Chat Copilot    │
              │                  └───────────────────────┘
┌─────────────▼──────────────┐
│     JSON Cache Layer       │
│ • cache/prices/            │
│ • cache/announcements/     │
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

### 3. Pull: On-Demand Research & "Promised vs. Delivered"
- **5 Structured Research Cards**:
  1. **Business & Financial Snapshot**: Segment revenue mix, operating margin, ROE, and leverage.
  2. **Multi-Year Trajectory**: Growth compounding drivers and margin trends.
  3. **Management Guidance**: Explicit forward statements quoted directly from earnings calls.
  4. **Promised vs. Delivered (Hero Feature)**: Accountability matrix comparing verbatim guidance against subsequent financial reports with explicit verdicts (`Met ✅`, `Partial ⚠️`, `Missed ❌`, `Pending ⏳`).
  5. **Bull vs. Bear Case**: Balanced, evidence-backed investment thesis grounded in primary disclosures.
- **Generalised Engine**: Works out-of-the-box for **any NSE ticker** (not just the demo set) via dynamic extraction and fundamental synthesis.

### 4. Interactive Copilot (FINN Chat)
- Grounded conversational assistant equipped with full research context for the active company.
- Strict primary-source discipline: system prompts explicitly forbid outside speculation or hallucinations.

---

## 📂 Demo Portfolio & Coverage

### Core Portfolio (18 Tickers Across Market Caps & Sectors)
- **Mega / Large Caps**: `RELIANCE.NS`, `HDFCBANK.NS`, `INFY.NS`, `TCS.NS`, `ICICIBANK.NS`, `SUNPHARMA.NS`, `TRENT.NS`
- **Mid Caps**: `POLYCAB.NS`, `DIXON.NS`, `HBLPOWER.NS`, `KALYANKJIL.NS`, `CAMS.NS`, `LALPATHLAB.NS`, `ASTRAL.NS`
- **Growth / Tech / Small Caps**: `ZOMATO.NS`, `IRCTC.NS`, `CDSL.NS`, `IDEAFORGE.NS`

### Ad-Hoc On-Demand Showcase Tickers
- `PERSISTENT.NS` (Persistent Systems — IT Midcap)
- `DMART.NS` (Avenue Supermarts — Retail)
- `BAJFINANCE.NS` (Bajaj Finance — NBFC / Financials)
- `MOTHERSON.NS` (Samvardhana Motherson — Auto Ancillary)

---

## ⚡ Quickstart Guide

### 1. Prerequisites
- **Python**: Version 3.11+
- **Node.js**: Version 18+ (tested on v22.11.0)

### 2. Backend Setup
```bash
# Navigate to project root
cd d:/enam_assignment

# Activate virtual environment
.venv\Scripts\activate   # On Windows
# source .venv/bin/activate  # On Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Start FastAPI backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation will be available at: `http://localhost:8000/docs`

### 3. Frontend Setup
```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Start Vite dev server
npm run dev
```
Open your browser at: `http://localhost:5173` *(Switch to Mobile Device View / iPhone in DevTools for the intended mobile-first experience).*

### 4. Configuration (.env)
Create or edit `.env` in the root folder:
```env
GEMINI_API_KEY=your_gemini_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
BACKEND_URL=http://localhost:8000
FRONTEND_URL=http://localhost:5173
```
*(Note: FINN includes comprehensive cached snapshots and domain heuristic fallbacks, ensuring the entire prototype functions smoothly even without live API keys).*

---

## 🧪 Verification & Demo Checklist

- [x] **Price Pipeline**: 22 tickers fetched with 6-month historical data and 20-day moving average volumes.
- [x] **Announcements**: 302 real BSE announcements classified and filtered into priority tiers.
- [x] **Active Alerts**: Live alerts triggered on price moves (TRENT) and volume surges (SUNPHARMA).
- [x] **Research Showcase**: Pre-warmed 5-card research views loaded for `PERSISTENT`, `RELIANCE`, `DMART`, `BAJFINANCE`, and `TRENT`.
- [x] **Generalisation**: Dynamic on-demand research tested and verified on un-prepared tickers (e.g. `WIPRO.NS`).
- [x] **PWA Production Build**: Vite production build compiled cleanly (`npm run build`).

---

## 👥 Built for ENAM Holdings
Developed as part of the **ENAM Holdings AI Engineer Build Challenge**. Designed to illustrate how modern AI engineering, rigorous data plumbing, and thoughtful product instincts combine into a daily investor tool.
