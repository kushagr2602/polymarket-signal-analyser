# BIT Capital — Polymarket Signal Scanner
## Project Plan & Contract

> Build a Polymarket signal scanner that filters prediction markets for equity-relevant signals, stores them in Postgres/Supabase, runs LLM analysis, and serves it via a web UI. 2 weeks.

---

## Company Context
- **BIT Capital** — Germany's largest actively managed tech equity fund. €3B AUM. Berlin.
- Already runs >1B tokens/month through their own AI pipelines — they will see through lazy filtering
- Key holdings: **HIMS** (health-tech), **HOOD** (fintech), **RDDT** (AI data), **IREN** (AI infra/crypto)
- Key sectors: AI Infrastructure, Health-Tech, Fintech, E-Commerce, Adtech, Biotech, Crypto

---

## Priority Breakdown
| Component | Weight | Status |
|-----------|--------|--------|
| LLM filtering pipeline | 40% | 🔴 Not started |
| Signal report generation | 20% | 🔴 Not started |
| Scheduled Polymarket ingestion | 15% | 🔴 Not started |
| Database schema | 10% | 🔴 Not started |
| BIT Capital research | 10% | ✅ Done |
| Web interface | 5% | 🔴 Not started |

---

## The Filtering Contract
> This is the definition of "relevant". The LLM filter is built around this logic.

### A market IS relevant if it could materially move BIT Capital's holdings or sectors:

| Category | Why it matters | BIT holding affected |
|----------|---------------|----------------------|
| Fed rate decisions | Growth tech valuations move on rates | All holdings |
| AI regulation (EU AI Act, US executive orders) | Affects AI infrastructure | IREN, RDDT |
| Crypto regulation | Direct impact on crypto positions | IREN, crypto funds |
| FDA approvals / rejections | Health-tech earnings sensitive | HIMS |
| Tariff outcomes | E-commerce, supply chains | Portfolio broadly |
| Fintech regulation | Affects trading platforms | HOOD |
| Big Tech antitrust | Ecosystem effects | RDDT |
| Company-specific events (earnings, CEO, M&A) | Direct price catalyst | HIMS, HOOD, RDDT, IREN |
| Macro recession / inflation signals | Risk-on/risk-off for growth tech | All holdings |
| IPO / listing events | New tech equity opportunities | Scouts for BIT |

### A market is NOT relevant if:
- Sports outcomes
- Celebrity events
- Elections with no macro/tech policy implication
- Geographies BIT doesn't invest in (unless macro spillover)
- Social/cultural events

### Relevance Score (1-10):
- **8-10**: Direct catalyst for a specific holding (e.g. FDA ruling on HIMS product)
- **5-7**: Sector-level impact (e.g. AI regulation affecting AI infra broadly)
- **3-4**: Macro signal (e.g. Fed rate decision)
- **1-2**: Weak or indirect connection
- **0**: Not relevant

---

## System Architecture

```
Polymarket API (scheduled, every 6h)
        ↓
  Raw markets → Postgres (markets table)
        ↓
  LLM Filter (Claude/Gemini)
  - Score 0-10 relevance
  - Map to BIT sector/holding
  - Explain why
        ↓
  Filtered signals → Postgres (signals table)
        ↓
  LLM Report Generator (nightly)
  - Top signals of the day
  - Implications for specific stocks
  - Analyst-grade insight, not summaries
        ↓
  Reports → Postgres (reports table)
        ↓
  Web UI (Streamlit)
  - Browse signals + relevance scores
  - Configure sectors/stocks to watch
  - View past reports
```

---

## Database Schema

### `markets` table
```sql
id              uuid primary key
market_id       text unique          -- Polymarket market ID
question        text                 -- "Will Fed cut rates in July 2025?"
category        text                 -- Polymarket category
probability     float                -- current implied probability (0-1)
volume_usd      float                -- trading volume
expiry_date     timestamp
fetched_at      timestamp
```

### `signals` table
```sql
id              uuid primary key
market_id       text references markets(market_id)
relevance_score int                  -- 0-10
sector          text                 -- "AI Infrastructure", "Health-Tech", etc.
affected_tickers text[]              -- ["HIMS", "HOOD"]
reasoning       text                 -- LLM explanation
created_at      timestamp
```

### `reports` table
```sql
id              uuid primary key
report_date     date
content         text                 -- full markdown report
top_signals     jsonb                -- structured signal data
created_at      timestamp
```

---

## Tech Stack
- **Language**: Python
- **Database**: Supabase (hosted Postgres, free tier)
- **LLM**: Claude API (primary) or Gemini (free tier fallback)
- **Scheduler**: APScheduler or cron
- **Web UI**: Streamlit
- **Environment**: conda env, `.env` for secrets

---

## Deliverables Checklist
- [ ] Git repo with clear structure + README
- [ ] Working local demo or deployment
- [ ] Supabase DB with schema + sample data
- [ ] Final report with learnings
- [ ] Optional: Loom/video demo

---

## Build Order
1. [ ] Set up project structure + conda env + Supabase
2. [ ] Hit Polymarket API, store raw markets in DB
3. [ ] Build LLM filtering pipeline (the 40%)
4. [ ] Build signal report generator
5. [ ] Add APScheduler for recurring runs
6. [ ] Build Streamlit web UI
7. [ ] Security checklist (RLS, rate limits, env vars)
8. [ ] README + final report
9. [ ] Loom demo

---

## Filtering Prompt (v1 — to refine)
```
You are an equity analyst at BIT Capital, a tech-focused investment fund.
BIT Capital's current holdings include: HIMS (health-tech), HOOD (fintech/retail investing),
RDDT (AI data licensing), IREN (AI infrastructure/Bitcoin mining).
BIT Capital's focus sectors: AI Infrastructure, Health-Tech, Fintech, E-Commerce, Adtech, Biotech, Crypto.

Evaluate this Polymarket prediction market for relevance to BIT Capital's equity portfolio:

Market: {question}
Current probability: {probability}
Volume: ${volume_usd}
Category: {category}
Expiry: {expiry_date}

Return a JSON response:
{
  "relevance_score": <0-10>,
  "sector": "<most relevant BIT sector or null>",
  "affected_tickers": ["<ticker>", ...],
  "reasoning": "<one paragraph: why this market matters or doesn't, what it implies for the portfolio>",
  "signal_type": "<rate_decision|regulation|company_event|macro|tariff|not_relevant>"
}

Score rubric:
8-10: Direct catalyst for a specific holding
5-7: Sector-level impact
3-4: Macro signal with broad portfolio implications
1-2: Weak/indirect connection
0: Not relevant to any BIT Capital position or sector
```

---

## Log
| Date | What happened |
|------|--------------|
| 2026-06-26 | Project started, BIT Capital researched, filtering contract defined |
| 2026-06-29 | PLAN.md written, build order defined |
