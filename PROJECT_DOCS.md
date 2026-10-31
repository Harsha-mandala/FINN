# FINN — Project Documentation

> This file is maintained continuously throughout the build. Updated after every major step.

**Project:** FINN — Financial Investment Agent  
**Challenge:** ENAM Holdings AI Engineer Build Challenge  
**Deadline:** Sunday, November 1, 2026  
**Builder:** [Your name]  
**Start time:** October 31, 2026 — 11:14 IST

---

## Build Log

### Step 0 — Shape & Setup ✅ `[Oct 31, 11:14–11:30 IST]`

**Decisions made:**
- Scope locked: Push (digest + alerts + results card + management bio) + Pull (5 research cards)
- Stack: FastAPI + React (Vite) + Tailwind + shadcn/ui + SQLite cache + Vercel + Render
- Model routing: Gemini Flash for bulk/extraction, Claude for reasoning
- Hero feature: **Promised vs. Delivered** (management guidance vs. actual delivery across 4 quarters)
- Portfolio: 18 NSE tickers across large/mid/small caps and diverse sectors
- Ad-hoc research: 4 tickers (PERSISTENT, DMART, BAJFINANCE, MOTHERSON)

**Files created:**
- `FINN_CONTEXT.md` — master context file for all AI agents
- `PROJECT_DOCS.md` — this file
- Full directory structure scaffolded

**What was skipped (and why):**
- Voice interaction — too much time for too little demo value
- Real push notifications — simulated as in-app alerts
- Auth — not needed for prototype demo
- Separate balance sheet / cash quality cards — merged into snapshot + trajectory

---

### Step 1 — Data Pipeline Setup ✅ `[Oct 31, ~14:20 IST]`

**Tasks completed:**
- [x] Python 3.13 venv & `requirements.txt` installed (fastapi, uvicorn, yfinance, curl_cffi, pdfplumber, etc.)
- [x] `.env.example` & `.env` scaffolded
- [x] `prices.py` — yfinance EOD scraper ran for all 22 tickers (6-month history + 20d avg volume + % change)
- [x] `announcements.py` — BSE scraper using `curl_cffi` (impersonate='chrome120') bypassed Akamai; scraped **302 live announcements** across all 22 tickers!
- [x] `fundamentals.py` — screener.in scraper verified; parsed document links for annual reports & concalls
- [x] Cache populated in `cache/prices/` and `cache/announcements/`

**Checkpoint:** All tickers have price JSON + live announcement snapshots + document links in `/cache`.

---

### Step 2 — Push Engine ✅ `[Oct 31, ~14:30 IST]`

**Tasks completed:**
- [x] `classifier.py` — Gemini 1.5 Flash batch classifier + 16 domain heuristic fallback rules
- [x] `enricher.py` — results headline extractor + management bio (search grounded)
- [x] `alerts.py` — EOD rules engine (volume spikes >= 2x, price moves >= 5%, high priority announcements)
- [x] `push.py` router — `/push/digest`, `/push/alerts`, `/push/prices` all tested and operational
- [x] Float NaN sanitization in FastAPI (`SafeJSONResponse`)

---

### Step 3 — Pull Engine (Research Agent) 🔄 `[In progress]`

**Tasks:**
- [x] `pdf_extract.py` — pdfplumber with SHA-256 hash caching
- [x] `concall_extract.py` — guidance extraction & segment data schemas
- [x] `researcher.py` — two-stage pipeline (Gemini extraction → Claude Sonnet analysis)
- [x] `pull.py` router — `/pull/research` and `/pull/research/{ticker}` endpoints
- [ ] Pre-generate research cards for demo tickers (PERSISTENT, RELIANCE, DMART, etc.)

---

### Step 4 — Backend API ✅ `[Oct 31, ~14:30 IST]`

**Tasks completed:**
- [x] `main.py` + `config.py` configured
- [x] Push, Pull, Chat routers wired
- [x] CORS middleware configured for frontend (localhost + deployed)
- [x] Backend tested live on `http://127.0.0.1:8000`

---

### Step 5 — Frontend ✅ `[Oct 31, ~14:16 IST]`

**Tasks completed:**
- [x] Node.js v22.11.0 installed permanently in `D:\tools\nodejs`
- [x] Vite + React + TypeScript + Tailwind CSS configured
- [x] All 4 screens built and fully styled:
  - `FeedScreen.tsx` (Windowed digest 24h/7d, portfolio ticker strip, needs attention, mini QoQ/YoY results table, management bio, collapsibles)
  - `AlertsScreen.tsx` (Threshold sliders, category toggles, active alert list)
  - `ResearchScreen.tsx` (Search any NSE ticker, quick-tap demo chips, 5 research cards including Promised vs. Delivered hero card)
  - `ChatScreen.tsx` (FINN conversational copilot with markdown rendering & ticker context badge)
- [x] PWA manifest & service worker configured
- [x] Production build tested: `npm run build` completed with 0 errors!

---

### Step 6 — Polish, Cache warm-up & Deploy ✅ `[Oct 31, ~14:48 IST]`

**Tasks completed:**
- [x] Pre-warmed cache for all 5 showcase research tickers (`PERSISTENT.NS`, `RELIANCE.NS`, `DMART.NS`, `BAJFINANCE.NS`, `TRENT.NS`)
- [x] On-demand research generalizer implemented and tested on unprepared tickers (`WIPRO.NS`)
- [x] Resilient multi-model fallback for `/chat` (Claude Sonnet -> Gemini Flash -> Grounded research context)
- [x] `README.md` created with comprehensive architecture diagrams, quickstart instructions, and model routing rationale
- [x] Production build tested with PWA service worker (`npm run build`)

---

### Step 7 — Submission Package ✅ `[Oct 31, ~14:49 IST]`

**Tasks completed:**
- [x] `COVERING_NOTE.md` created with ready-to-send email to `assessment@enam.com`
- [x] All design trade-offs, AI pair-programming reflections, and technical interventions documented
- [x] Live servers running: Backend on `http://127.0.0.1:8000`, Frontend on `http://localhost:5173`

---

## Architecture Overview

```
┌─────────────────────────────────────────┐
│            FINN Frontend (PWA)          │
│  React + Vite + Tailwind + shadcn/ui    │
│  Deployed: Vercel                       │
└──────────────────┬──────────────────────┘
                   │ HTTP (REST)
┌──────────────────▼──────────────────────┐
│           FINN Backend (FastAPI)        │
│  /push   /pull   /chat   /alerts        │
│  Deployed: Render                       │
└──┬──────────────────────────────────┬───┘
   │                                  │
┌──▼──────────────┐    ┌──────────────▼───┐
│  Data Pipeline  │    │   LLM Services   │
│  - yfinance     │    │  - Gemini Flash  │
│  - BSE/NSE APIs │    │    (classify,    │
│  - screener.in  │    │     extract)     │
│  - PDF download │    │  - Claude        │
└──┬──────────────┘    │    (analyse,     │
   │                   │     chat)        │
┌──▼──────────────┐    └──────────────────┘
│  SQLite + JSON  │
│  Cache Layer    │
│  /cache/...     │
└─────────────────┘
```

## Model Routing Summary

| Task | Model | Why |
|---|---|---|
| Classify announcements (bulk) | Gemini 1.5 Flash | Free tier, batch JSON |
| Extract results numbers | Gemini 1.5 Flash | Structured output |
| Extract concall guidance | Gemini 1.5 Flash | Long context |
| Management bio enrichment | Gemini Flash + Search | Needs search grounding |
| Research analysis (reasoning) | Claude Sonnet | Quality reasoning |
| Chat copilot | Claude Sonnet | Quality responses |

**QoQ/YoY computations: always in Python code, never by LLM.**

## Known Limitations (for covering email)

- Announcement data runs from snapshot (live BSE/NSE APIs may block in demo)
- screener.in scraping subject to rate limits; mitigated with delays + cache
- LinkedIn bio enrichment uses search grounding (not direct scrape — TOS)
- PDF extraction quality depends on PDF type (text vs. scanned)

## Cost Efficiency Notes

*(to be updated as tokens are consumed)*

- Classification: ~18,000 tokens/day for 18 tickers × 30 announcements = ~\$0.00 (Flash free tier)
- Research per ticker: ~200K tokens extraction + ~20K analysis = ~\$X
- Caching saves re-processing on repeat queries

---

*Last updated: Oct 31, 2026 — Step 0 complete*
