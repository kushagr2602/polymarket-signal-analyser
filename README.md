# Polymarket Signal Analyser

An agentic pipeline that scans [Polymarket](https://polymarket.com) prediction
markets, scores each one 0–10 for relevance to **your** equity watchlist with an
LLM, stores everything in Postgres (Supabase), writes a daily analyst brief, and
serves it all through a dashboard with a tool-calling analyst agent.

Built for the Google × Kaggle AI Agents Intensive capstone (Agents for Business).

## What it does

```
Polymarket Gamma API ─(hourly)→ markets ─→ LLM filter (0-10 + tickers + reasoning) ─→ signals
                                                        │
             dashboard ← analyst agent (tool loop) ← ───┤── → nightly brief
                              │
                        MCP server (same tools, open protocol)
```

## Configure your watchlist

The watch universe lives in [watchlist.json](watchlist.json) and is editable in
the dashboard sidebar — tickers with one-line descriptions, plus focus sectors.
Every prompt (filter, news, brief, agent) is built from it at call time, so new
scans immediately score against your book. Ships with an example set
(NVDA, TSLA, COIN, LLY).

## Setup

1. `pip install -r requirements.txt`
2. Create a [Supabase](https://supabase.com) project, paste [schema.sql](schema.sql)
   into the SQL editor, run it.
3. Copy `.env.example` → `.env`, fill in `SUPABASE_URL`, `SUPABASE_KEY`,
   `OPENAI_API_KEY`.

## Usage

```bash
python3 -m src.scheduler --once     # one full pass: fetch → filter → report
python3 -m src.scheduler            # hourly scans + nightly brief
streamlit run app.py                # the dashboard
python3 -m src.mcp_server           # expose the tools over MCP (stdio)
python3 tests/eval_filter.py        # eval the filter against the labeled set
```

## Agentic design (course concepts)

- **Tool-calling agent** ([src/agent.py](src/agent.py)) — plans and chains
  `query_signals` / `portfolio_exposure` / `get_latest_brief`; the UI shows the
  tool trace.
- **MCP server** ([src/mcp_server.py](src/mcp_server.py)) — the same tools over
  the Model Context Protocol; config snippet for Claude Desktop in the docstring.
- **Security** — sports/entertainment markets are hard-zeroed by regex *before*
  any LLM call; `affected_tickers` is validated against the watchlist (the model
  once invented a ticker); the agent loop has a hard tool-call budget.
- **Evals** ([tests/eval_filter.py](tests/eval_filter.py)) — 14 labeled markets
  with expected score bands as a regression gate on prompt changes.

## Notes

- Polymarket's Gamma API caps each request at 100 markets; ingestion pages by
  offset, dedupes overlapping pages, and drops already-resolved markets.
- All reads go through one clean path (`database.get_signals`) that dedupes and
  drops expired markets — dashboard, brief, and agent see the same data.
- The LLM *is* the filter — no brittle keyword pre-filter. A full 1,000-market
  scan costs ~1–2 cents on `gpt-4o-mini`; the sports guard skips ~25% of calls.
- Retrieval is a keyword-ranked pull, deliberately not a vector store — swap in
  pgvector if the signal table grows past ~5k rows.
