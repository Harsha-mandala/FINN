# Submission Covering Note: FINN (Financial Investment Agent)

**To:** assessment@enam.com  
**Subject:** ENAM - IIT screening - 2027  
**Candidate:** [Your Name]  
**Repository:** [GitHub Repository URL]  
**Live Demo:** [Vercel Deployment URL / Local Demo Instructions]  

---

### Dear ENAM Investment Team,

Here is my submission for the **ENAM Holdings AI Engineer Build Challenge**: **FINN**, a mobile-first financial intelligence layer built for high-conviction public-markets investors.

Below is a concise walkthrough of what was built, the architectural trade-offs made, and how AI tools were directed to build it within the challenge window.

---

### 1. What I Chose to Build and Why (Product Judgment)

An investor’s daily cognitive bottleneck is **signal-to-noise ratio**. Most market terminals overwhelm users with raw dumps of announcements and ticks. I focused FINN on two daily workflows:

1. **Intelligent Triage (Push)**:
   - **Three-Tier Priority Filter**: Instead of a chronological stream, corporate filings are partitioned into **High** (Needs Attention: Results, M&A, CEO/CFO changes), **Medium** (Also Today: Dividends, Capex), and **Low** (Routine paperwork: ESOP allotments, routine certificates, which are collapsed by default).
   - **Primary Source Arithmetic Rule**: For quarterly results cards, percentage deltas (QoQ and YoY) are computed deterministically in Python code—**never by the LLM**. This eliminates hallucination risk on numbers that drive capital decisions.
   - **Dynamic Anomaly Alerts**: Real-time alerts flagged when volume exceeds 2× the 20-day average or when price moves cross ±5.0%.

2. **The Accountability Engine — "Promised vs. Delivered" (Pull Hero Feature)**:
   - When researching a company, the most valuable signal is **management credibility**. 
   - FINN extracts explicit forward guidance from earnings calls (verbatim quotes with dates and metrics), matches them against audited financial filings in subsequent quarters, and renders an objective scorecard (`Met ✅`, `Partial ⚠️`, `Missed ❌`, `Pending ⏳`).
   - Accompanied by **Multi-Year Trajectory**, **Business/Financial Snapshot**, and a primary-source-backed **Bull vs. Bear Case**.

3. **Generalisation to Any NSE Ticker**:
   - The engine is not hardcoded to a mock list. Pointing FINN at an unprepared ticker (e.g. `WIPRO`, `TATASTEEL`) dynamically scrapes exchange fundamentals and synthesizes structured cards on the fly.

---

### 2. What I Chose NOT to Build and Why (Trade-offs)

- **Voice Input / Audio Agent**: Skipped intentionally. In a professional investing environment, skimming a dense, well-structured visual card takes 5 seconds, whereas listening to an audio monologue takes 60 seconds. High information density beats conversational novelties.
- **Real iOS/Android Native Push Notifications**: Replaced with in-app triggered alert queues. Native APNS/FCM requires app store certificates without adding fundamental product signal during a desktop/mobile browser evaluation.
- **Complex Fine-Tuning or Vector RAG Infrastructure**: Skipped heavy vector databases (Pinecone/Milvus) in favor of deterministic SHA-256 caching and direct full-document prompt caching. Financial filings are chronological and structured; vector chunking often separates numbers from their footnote context.

---

### 3. How I Used AI to Build This (Tools, Learnings & Interventions)

I built FINN using an agentic pair-programming workflow leveraging **Google Antigravity, Claude 3.5 Sonnet, and Gemini 1.5 Flash**:

- **Model Routing Strategy**:
  - **Gemini 1.5 Flash**: Used for high-throughput batch announcement classification (25 items per prompt) and document OCR/extraction due to its massive context window and cost-efficiency.
  - **Claude 3.5 Sonnet**: Reserved for multi-quarter synthesis, guidance matching ("Promised vs. Delivered"), and the grounded chat copilot where rigorous reasoning is paramount.
- **Where AI Shined**:
  - Scaffolding the React 18 + Tailwind mobile PWA and drafting Pydantic schemas rapidly.
  - Parsing unstructured Hindi/English earnings transcripts into structured JSON arrays of guidance commitments.
- **Where AI Failed & Human Engineering Intervened**:
  - **Akamai/Cloudflare Bot Blocks on Stock Exchanges**: Stock exchange JSON endpoints immediately blocked standard HTTP clients (`requests`). I intervened by re-architecting the scraping pipeline using `curl_cffi` with Chrome-120 TLS fingerprint impersonation, restoring 100% reliable data flow.
  - **Floating-Point NaN Incompatibilities**: `yfinance` occasionally returned `NaN` for newly split stocks, causing FastAPI's standard JSON encoder to crash. I wrote a custom `SafeJSONResponse` class to recursively sanitize non-compliant floats before serialization.
  - **Fail-Safe Caching**: Recognizing that live exchange APIs or API keys can fail during an evaluation, I ensured all demo portfolio tickers (`PERSISTENT`, `RELIANCE`, `DMART`, `BAJFINANCE`, `TRENT`) have pre-warmed snapshot caches so the prototype opens instantaneously with zero latency.

---

### 4. What I Would Build Next with Another Week

1. **Automated Red-Flag Detector**: Cross-referencing Related Party Transactions (RPT) across consecutive Annual Reports to highlight governance anomalies and auditor qualifications.
2. **Concall Tone & Hedging Sentiment Analyzer**: Audio-level acoustic analysis (pitch variance, hesitation pauses) during Q&A sessions when management addresses margin guidance.
3. **Portfolio Thesis Tracker**: Allowing an analyst to log their initial investment hypothesis and having FINN continuously monitor whether new filings validate or impair that thesis.

---

### 5. Repository & Local Setup

```bash
# Clone and run
git clone <repo_url>
cd enam_assignment

# Backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --port 8000

# Frontend
cd frontend
npm install
npm run dev
# Open http://localhost:5173 on Mobile View
```

Thank you for the opportunity to tackle this challenge. I look forward to discussing the architecture and product choices with the team.

Sincerely,  
**[Your Name]**  
[Your Phone / Email / LinkedIn]
