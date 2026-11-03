# FINN — Project Documentation

> This file is maintained continuously throughout the build. Updated after every major step.

**Project:** FINN — Financial Investment Agent  
**Challenge:** ENAM Holdings AI Engineer Build Challenge  
**Date:** November 2026  
**Interaction model:** card-first, every feed item expands in place to its filing, results table and bio; research is a tap away from the same ticker.

---

## System Architecture Overview

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

## Build Log & Phase Milestones

### Phase 1 & 2: Push Engine & Results Extraction
- Scope: Feed, windowed digest, priority tiers (high/medium/low), exchange scraping via `curl_cffi`, price history & volume surges.
- Deterministic Results Extractor:
  - 34 filings parsed directly from financial statements.
  - Extracted metrics: Revenue, EBITDA, PBT, PAT with QoQ and YoY % deltas computed in Python.
  - Bank-specific logic: Total Income and NII extracted; EBITDA marked `not_applicable`.
- Security Architecture:
  - Strict key isolation: `GEMINI_API_KEY` read strictly via `os.environ`.
  - Zero `.env` files or secret values in repo.
  - Pre-commit secret scanning hook and logger redaction filter installed.

---

### Phase 3: Task A — Remove "Ask FINN" Chatbot ✅
- **Frontend**:
  - Deleted `ChatScreen.tsx` and removed `/chat` route.
  - Updated navigation: 3 tabs on mobile (`Feed`, `Alerts`, `Research`), responsive side rail on desktop (`>= 1024px`).
  - Removed all "Ask FINN" buttons across feed cards; replaced with direct `"Research →"` link passing `?ticker=XYZ`.
  - Removed chat-related methods and state plumbing from `api.ts`.
- **Backend**:
  - Deleted `/chat` router and removed router registration from `main.py`.
  - Removed `ChatMessage`, `ChatRequest`, and `ChatResponse` schemas from `backend/models/schemas.py`.
- **Docs**:
  - Updated `README.md` and `PROJECT_DOCS.md` to remove all chatbot claims and document the card-first interaction model.

---

### Phase 3: Task B — Research Tab Real Data (Two-Layer Architecture) ✅
- **Baseline Layer (Zero LLM Required, Instant Cache)**:
  - Created `GET /pull/overview/{ticker}` reading exclusively from local cache.
  - **Latest Results Card**: Displays Revenue, EBITDA derived or bank NII/Total Income, PBT, PAT with QoQ and YoY deltas, basis, period, and direct PDF link.
  - **Price & Volume**: Last close, 1-day %, SVG sparkline of 123 trading days, volume vs. 20-day average.
  - **Primary Documents**: Document links from `cache/documents/<ticker>/links.json`.
  - **Recent Priority Filings**: Last 5 high/medium priority threads with category badges and attachment links.
  - **Ticker Picker**: Quick chips for showcase tickers (`RELIANCE`, `PERSISTENT`, `HDFCBANK`, `DMART`, `BAJFINANCE`, `TRENT`, `INFY`, `TCS`) + search input + URL query param support (`?ticker=XYZ`).
- **Analysis Layer (Primary Source Fundamental Research)**:
  - Renders 5 structured research cards when cached (`snapshot`, `trajectory`, `guidance`, `promised_vs_delivered`, `bull_bear`).
  - Provenance badge displaying model used and source citations.
  - Calm empty state with `"Generate Deep Research Brief"` button when not yet pre-generated.
  - Rate-capped on-demand generation (`MAX_DAILY_RESEARCH_GENERATIONS=3`) with mutex queue and user-friendly error messages on limit exhaustion.

---

### Phase 3: Task C — Backend Keepalive & Cold-Start Resilience ✅
- **Fast Keepalive Route**:
  - Implemented `@app.api_route("/health", methods=["GET", "HEAD"])` answering in < 5ms without disk, network, or LLM overhead.
  - Commented that `/health/llm` is reserved for diagnostics and NEVER for keepalive pings.
- **GitHub Actions Keepalive**:
  - Added `.github/workflows/keepalive.yml` with a 10-minute cron pinging `${{ vars.BACKEND_URL }}/health`.
- **Frontend Cold-Start Handling**:
  - Non-blocking `/health` warm-up ping initiated on frontend launch.
  - Fetch client with exponential backoff on HTTP 502/503/504 errors.
  - Subtle `"Waking up the backend server..."` banner shown only if backend response exceeds 1.5 seconds.
- **UptimeRobot Documentation**:
  - Documented 5-minute HTTP GET/HEAD monitor setup targeting `/health`.
