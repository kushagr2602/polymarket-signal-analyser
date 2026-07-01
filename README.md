# BIT Capital — Polymarket Signal Scanner

Scans [Polymarket](https://polymarket.com) prediction markets, filters them for
relevance to BIT Capital's tech-equity portfolio with an LLM, stores the signals
in Postgres (Supabase), and serves them through a Streamlit UI.

## What it does

```
Polymarket Gamma API  →  markets (Postgres)
        →  LLM filter (OpenAI, scores 0–10 + sector + tickers + reasoning)
        →  signals (Postgres)
        →  LLM report generator (daily brief)
        →  reports (Postgres)
        →  Streamlit UI
```

The filtering contract (what counts as "relevant" — Fed decisions, AI/crypto
regulation, FDA approvals, tariffs, company catalysts for HIMS/HOOD/RDDT/IREN)
lives in [PLAN.md](PLAN.md).

## Setup

1. **Install deps**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create the database tables** — paste [schema.sql](schema.sql) into the
   Supabase SQL Editor and run it.

3. **Configure secrets** — copy `.env.example` to `.env` and fill in:
   ```
   SUPABASE_URL=...
   SUPABASE_KEY=...        # service_role for writes, or anon with RLS disabled
   OPENAI_API_KEY=...
   ```

## Usage

```bash
# one full pass: fetch → filter → report
python3 -m src.scheduler --once

# run on a schedule (ingest+filter every 6h, report nightly)
python3 -m src.scheduler

# launch the UI
streamlit run app.py
```

Individual stages are runnable too: `python3 -m src.polymarket` (fetch),
`python3 -m src.filter` (score one test market), `python3 -m src.reports`
(generate a brief from stored signals).

## Layout

| File | Role |
|------|------|
| `src/polymarket.py` | Fetch top markets by volume (paginated past Gamma's 100/request cap) |
| `src/filter.py`     | LLM relevance scoring (the core 40%) |
| `src/reports.py`    | LLM daily brief from top signals |
| `src/news.py`       | Free-RSS world/holding news, LLM-scored for portfolio impact |
| `src/chat.py`       | "Ask the Desk" — grounded Q&A over stored signals + brief |
| `src/database.py`   | Supabase CRUD |
| `src/scheduler.py`  | Pipeline orchestration + APScheduler |
| `app.py`            | Streamlit dashboard (Signal Desk · World News · Ask the Desk · Brief) |
| `schema.sql`        | Postgres schema |

## Notes

- Polymarket's Gamma API caps each request at 100 markets, so `fetch_markets`
  pages by `offset` to reach past the high-volume sports markets into the
  macro/crypto/regulation markets that actually matter.
- The LLM *is* the filter — there's no brittle keyword pre-filter. At
  `gpt-4o-mini` prices, scoring a few hundred markets per run costs ~1–2 cents.
- **Ask the Desk** uses retrieval-augmented Q&A, but deliberately *not* a vector
  store: the corpus is a few hundred short signal rows, so retrieval is a
  keyword-ranked DB pull stuffed into context. Swap to pgvector embeddings only
  if the signal table grows past ~5k rows.
