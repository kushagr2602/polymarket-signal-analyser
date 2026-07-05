# Polymarket Signal Analyser
### An agentic pipeline that reads prediction markets for equity signals

*Capstone — Google × Kaggle AI Agents Intensive (Vibe Coding edition, June 2026)*
*Track: **Agents for Business** (insights generation for equity research)*
*Kushagr Gupta · [repo link] · [video link]*

## Course concepts demonstrated (requirement: ≥3)

1. **Tool-using agent** — `src/agent.py`: a function-calling loop that plans and
   chains typed tools (`query_signals`, `portfolio_exposure`, `get_latest_brief`),
   with the tool trace surfaced in the UI.
2. **MCP server** — `src/mcp_server.py`: the same tools exposed over the Model
   Context Protocol (stdio), so any MCP client — Claude Desktop, an ADK agent —
   can query the signal database. One implementation, two front-ends.
3. **Security features** — deterministic guardrails around the LLM: regex
   hard-zero for out-of-mandate markets *before* any model call, a ticker
   allowlist that blocks hallucinated symbols, a hard tool-call budget on the
   agent loop, and grounding rules that force "I don't know" over invention.
4. **Agent evaluation** — `tests/eval_filter.py`: a 14-case labeled regression
   gate over the scoring behaviour, which caught two real calibration failures
   on its first run.
5. **Spec-driven development** — the filtering contract was written before the
   code; the eval set is that spec made executable.

## Rationale

Prediction markets price real-world events — Fed decisions, regulation, FDA
rulings, crypto moves — in real time, but almost all of that volume is sports
and entertainment noise. The question this project answers for an equity
analyst: **which of the ~1,000 most-traded Polymarket markets actually matter
to the stocks I cover, and why?** The watchlist is fully user-configurable —
tickers, descriptions, and focus sectors are edited in the dashboard sidebar,
and every prompt in the system (filter, news, brief, agent) is built from that
config at call time. Ships with an example set (NVDA, TSLA, COIN, LLY).

## What it does

Hourly, the pipeline ingests the top ~1,000 markets from Polymarket's Gamma
API, scores each 0–10 for equity relevance with an LLM against an explicit
filtering contract, and stores markets/signals/reports in Supabase Postgres.
A nightly LLM brief writes up the top signals like an analyst note. The
Streamlit dashboard shows top signals with full reasoning, portfolio exposure,
an upcoming-catalyst agenda, and click-through to every market. An **analyst
agent** answers questions by planning tool calls over the database.

```
Gamma API ─(hourly)→ markets ─→ LLM filter (0-10 + tickers + reasoning) ─→ signals
                                                     │
                    dashboard ← agent (tool loop) ← ─┤─ → nightly brief
```

## The agentic parts (course concepts in production)

- **Function-calling agent loop** (Day 2 — tools): `src/agent.py` gives the
  model three typed tools — `query_signals`, `portfolio_exposure`,
  `get_latest_brief` — and lets it plan. Ask "which signals threaten IREN and
  how exposed are we?" and it chains a filtered query with an exposure check
  before synthesizing. The UI surfaces the tool trace for transparency.
- **Deterministic guardrails around the LLM** (Day 4 — security/reliability):
  sports/esports markets are hard-zeroed by regex *before* any LLM call
  (the rubric alone let "Spread: United States (-1.5)" score 5/10), and
  `affected_tickers` is validated against an allowlist after the model
  invented a ticker ("IRD"). Lesson: soft instructions are not controls.
- **Eval harness as a regression gate** (Day 4 — evaluation):
  `tests/eval_filter.py` pins 14 labeled markets to expected score bands.
  On its first run it caught two real calibration failures — a direct RDDT
  catalyst under-scored at 5, demographic trivia over-scored at 3. One rubric
  iteration fixed the trivia case and moved the RDDT case to the band edge
  (it now oscillates 5–7 across runs: single-shot scoring variance the
  harness makes visible; median-of-3 scoring is the documented next step).
  Current: 13/14.
- **Spec-driven development** (Day 5): the filtering contract (which event
  types move which holdings, scoring rubric, exclusions) was written in
  PLAN.md before any code, and the eval cases are that spec made executable.
- **Vibe-coding workflow with a harness** (Day 1): the whole system was built
  conversationally with an AI coding agent, but gated by an offline test
  suite wired into a git pre-commit hook — 8 unit tests plus the eval set.

## Engineering learnings (the honest part)

The two-week build surfaced real production lessons: Polymarket's `volume`
sort silently returns junk (`volumeNum` is the real field); each API page
caps at 100 rows and pages overlap while live volume reorders them; settled
markets still report `active=true`; and PostgREST silently caps reads at
1,000 rows — which caused the scanner to re-score everything past row 1,000
and generate 1,126 duplicate signals before a paginated read + UNIQUE
constraint fixed it at the root. Full detail in the repo README.

## Cost

gpt-4o-mini end to end: a full 1,000-market scan ≈ 1–2 cents; the sports
guard removes ~25% of LLM calls outright; steady state only scores new
markets. Retrieval for the agent is a keyword-ranked pull over ~1,000 rows —
deliberately no vector store below ~5k rows.

## Links

- **Code**: [repo link — add after push]
- **Video walkthrough**: [Loom link]
- **Run it**: `pip install -r requirements.txt`, add `.env` keys, run
  `python3 -m src.scheduler --once`, then `streamlit run app.py`.
