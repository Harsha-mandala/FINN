# FINN — Agent Context File

> **Every AI agent / LLM session working on this project MUST read this file first.**
> Keep this file updated as decisions are made.

---

## What we're building

**FINN** — a mobile-first financial investment agent for Indian public-market investors.

Two interaction modes:
- **Push**: proactively surfaces corporate filings, announcements, and price/volume alerts across a portfolio. Filters and prioritises so the investor sees only what matters.
- **Pull**: on-demand deep research on any NSE ticker, grounded exclusively in primary sources (annual reports + concall transcripts). No broker notes, no news, no model's outside knowledge.

Submitted for: **ENAM Holdings AI Engineer Build Challenge** (deadline: Nov 1, 2026)

---

## Stack decisions (final)

| Layer | Technology |
|---|---|
| Data pipeline | Python scripts |
| Backend | FastAPI (Python) |
| Frontend | React (Vite) + Tailwind CSS + shadcn/ui — deployed as PWA on Vercel |
| Database / cache | SQLite (via `sqlite3` / `aiosqlite`) + JSON file cache |
| PDF extraction | `pdfplumber` (primary), Gemini PDF input (fallback) |
| Price data | `yfinance` (.NS tickers) |
| Announcements | BSE/NSE unofficial JSON endpoints → snapshot to disk |
| Fundamentals | screener.in scraping → download PDFs → cache |
| Deployment | Backend: Render (free tier), Frontend: Vercel |

---

## Model routing (enforce this)

| Task | Model | Reason |
|---|---|---|
| Announcement classification (bulk) | Gemini 1.5 Flash | Free tier, fast, 20-30 items/call |
| One-line announcement summaries | Gemini 1.5 Flash | Same |
| PDF text extraction / structuring | Gemini 1.5 Flash | Long context, native PDF input |
| Results headline extraction (Revenue/EBITDA/PBT/PAT) | Gemini 1.5 Flash | Structured JSON output |
| Management bio enrichment | Gemini 1.5 Flash + Search grounding | Search needed |
| Analysis: Promised vs. Delivered, Trajectory, Narrative | Claude (claude-3-5-sonnet or claude-3-opus) | Reasoning-heavy |
| Bull vs. Bear | Claude | Reasoning-heavy |
| Chat copilot responses | Claude | Quality matters |

**Key rule:** QoQ/YoY percentages MUST be computed in Python code, NOT by the LLM. LLM returns raw numbers; code computes deltas.

---

## Primary-source discipline (CRITICAL)

**Pull side (research) system prompts MUST include:**
```
You are analysing a company using only the documents provided to you.
Do NOT use any outside knowledge, news, broker reports, or your training data about this company.
If a piece of information is not found in the provided documents, say "Not found in source documents."
Every claim you make must cite its source document and approximate location (e.g., "FY24 Annual Report, MD&A section").
```

Push-side enrichment (e.g., management bios) may use search grounding — that is explicitly permitted.

---

## Portfolio — 18 NSE tickers

| Ticker | Company | Sector | Size |
|---|---|---|---|
| RELIANCE.NS | Reliance Industries | Conglomerate | Large |
| HDFCBANK.NS | HDFC Bank | Banking | Large |
| INFY.NS | Infosys | IT Services | Large |
| TCS.NS | Tata Consultancy Services | IT Services | Large |
| ICICIBANK.NS | ICICI Bank | Banking | Large |
| SUNPHARMA.NS | Sun Pharma | Pharma | Large |
| TRENT.NS | Trent (Tata Retail) | Retail | Mid |
| POLYCAB.NS | Polycab India | Cables & Wires | Mid |
| DIXON.NS | Dixon Technologies | Electronics Mfg | Mid |
| HBLPOWER.NS | HBL Power Systems | Power Electronics | Mid-Small |
| KALYANKJIL.NS | Kalyan Jewellers | Jewellery Retail | Mid |
| CAMS.NS | Computer Age Mgmt Services | Fintech | Mid |
| LALPATHLAB.NS | Dr Lal PathLabs | Healthcare | Mid |
| ASTRAL.NS | Astral Ltd | Pipes & Adhesives | Mid |
| ZOMATO.NS | Zomato | Consumer Internet | Mid |
| IRCTC.NS | IRCTC | Travel/Tourism | Mid |
| CDSL.NS | CDSL | Capital Markets | Mid-Small |
| IDEAFORGE.NS | ideaForge Technology | Drones | Small |

**Ad-hoc research tickers (4, some outside portfolio):**

| Ticker | Company |
|---|---|
| PERSISTENT.NS | Persistent Systems |
| DMART.NS | Avenue Supermarts |
| BAJFINANCE.NS | Bajaj Finance |
| MOTHERSON.NS | Samvardhana Motherson |

---

## Announcement category taxonomy

Use exactly these labels (from the brief's reference doc):

`results`, `M&A`, `fund_raise`, `management_change`, `litigation`, `insider_trading`,
`earnings_call`, `investor_meetings`, `credit_rating`, `dividend`, `bonus_split`,
`capex`, `press_release`, `postal_ballot`, `agm_egm`, `pledging`, `unclassified`

**Priority rules (rules-based, applied after LLM classification):**
- HIGH (80-100): `results`, `M&A`, `management_change`, `litigation`, `fund_raise`
- MEDIUM (40-79): `credit_rating`, `dividend`, `capex`, `press_release`, `pledging`, `insider_trading`
- LOW (0-39): `bonus_split`, `postal_ballot`, `agm_egm`, `investor_meetings`, `earnings_call`, `unclassified`

---

## Research outputs (Pull) — what we're building

Pick 5 of 8:
1. ✅ **Business + Financial snapshot** (combined card)
2. ✅ **Trajectory** (multi-year trend: what's growing, what's compressing)
3. ✅ **Guidance** (explicit forward guidance from concalls)
4. ✅ **Promised vs. Delivered** ← HERO FEATURE (last 4 concalls, guided → actual → verdict)
5. ✅ **Bull vs. Bear** (tight case each way)

Skipping: Balance sheet (standalone), Cash quality (standalone), Narrative vs. numbers (merged into Promised vs. Delivered)

---

## Repo structure

```
finn/
├── FINN_CONTEXT.md          ← this file (read first)
├── PROJECT_DOCS.md          ← project documentation and build log
├── .env.example             ← env vars template (never commit .env)
├── data-pipeline/
│   ├── scrapers/
│   │   ├── prices.py        ← yfinance EOD price/volume
│   │   ├── announcements.py ← BSE/NSE announcement fetch + snapshot
│   │   └── fundamentals.py  ← screener.in document links + PDF download
│   └── extractors/
│       ├── pdf_extract.py   ← pdfplumber + Gemini fallback
│       ├── results_extract.py ← Revenue/EBITDA/PBT/PAT from results PDFs
│       └── concall_extract.py ← guidance extraction from transcripts
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── routers/
│   │   ├── push.py          ← digest and alerts endpoints
│   │   ├── pull.py          ← research endpoint
│   │   └── chat.py          ← chat copilot endpoint
│   ├── services/
│   │   ├── classifier.py    ← Gemini Flash announcement classifier
│   │   ├── enricher.py      ← management bio, results card
│   │   ├── researcher.py    ← pull research pipeline
│   │   └── alerts.py        ← rules engine for EOD alerts
│   └── models/
│       └── schemas.py       ← Pydantic models
├── frontend/
│   ├── src/
│   │   ├── screens/         ← Home, Research, Alerts, Chat, Item Detail
│   │   ├── components/      ← shared UI components
│   │   ├── hooks/           ← data fetching hooks
│   │   └── lib/             ← API client, utils
│   └── ...
├── cache/
│   ├── prices/              ← price snapshots by ticker
│   ├── announcements/       ← announcement snapshots by ticker + date
│   ├── documents/           ← downloaded PDFs
│   └── research/            ← cached research outputs by ticker
├── prompts/
│   ├── classify.txt         ← announcement classification prompt
│   ├── results_extract.txt  ← results headline extraction prompt
│   ├── guidance_extract.txt ← concall guidance extraction prompt
│   └── research_analysis.txt ← analysis stage prompts
└── docs/
    ├── build-history/       ← exported AI conversations
    └── architecture.md
```

---

## Key constraints to remember

1. **Never commit `.env`** — API keys in environment variables only
2. **Cache aggressively** — every PDF, every LLM response (keyed by file hash), every API response
3. **Demo from cache** — live fetches are bonuses; cache is the baseline
4. **No hallucination** — structured JSON output from LLMs, numbers computed in code
5. **Primary sources only for Pull** — enforced in system prompts
6. **Mobile-first** — test on actual phone via mobile data before submission
7. **Generalise** — `research(ticker)` must work for any NSE ticker, not just the demo set

---

## Environment variables needed

```
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=        # optional, for second opinion
BACKEND_URL=           # set after deployment
```
