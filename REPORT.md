# Final Report — Polymarket Signal Scanner

Kushagr Gupta · BIT Capital AI Engineering Intern case study · July 2026

## What was built

A pipeline that ingests the top ~1,000 Polymarket markets by volume on a schedule,
scores each one 0–10 for relevance to BIT Capital's portfolio with an LLM, stores
markets/signals/reports in Supabase Postgres, generates a daily analyst brief, and
serves everything through a Streamlit dashboard in BIT's brand. Two additions beyond
the brief: a world-news tab (free RSS, LLM-scored for portfolio impact) and "Ask the
Desk", a grounded Q&A over the stored signals.

```
Polymarket Gamma API ─(hourly)→ markets ─→ LLM filter ─→ signals ─→ nightly brief ─→ reports
                                   └────────────── Streamlit dashboard ──────────────┘
```

## The filtering logic (the 40%)

The filter is a single LLM call per market against an explicit contract written
before any code: which event types move which holdings (Fed → HOOD and growth-tech
broadly, crypto price/regulation → IREN, FDA → HIMS, AI regulation/antitrust →
RDDT/IREN), a 0–10 rubric tied to portfolio impact (8–10 direct catalyst for a
holding, 5–7 sector, 3–4 macro), and explicit exclusions. Two things I learned to
enforce *outside* the prompt, because the model alone is not reliable enough:

- **Hard rules beat soft instructions.** The rubric said sports = 0, yet a market
  literally named "Spread: United States (-1.5)" scored 5. Sports/esports now hit a
  regex guard before the LLM call — deterministic, and it skips the API call.
- **Validate structured output.** The model occasionally invented tickers ("IRD"
  for IREN). `affected_tickers` is now intersected with the actual book.

The judgment call I'd defend hardest: the LLM *is* the filter. A keyword pre-filter
would be cheaper but silently drops things like "AI bubble burst in 2026?" that
keywords don't anticipate. At gpt-4o-mini prices a full scan costs ~1–2 cents, so
spending tokens to keep recall was the right trade.

## What actually went wrong (and what I learned)

These were the real engineering lessons of the two weeks:

1. **Polymarket's API lies politely.** `order=volume` silently returns junk ordering;
   the real field is `volumeNum`. Each request caps at 100 rows regardless of
   `limit`, so "top 1,000" requires offset paging — and pages overlap while live
   volume reorders them, so ingestion dedupes by `market_id`. Markets that already
   resolved still return `active=true` while awaiting settlement; without an expiry
   check they pollute every downstream number.
2. **PostgREST caps every read at 1,000 rows — silently.** Once the signals table
   crossed 1,000, the "already scored?" check only saw the first 1,000, so the
   scanner re-scored everything past that on every tick: 1,126 duplicate rows before
   I caught it. Fix: paginate all reads, and a `UNIQUE(market_id)` constraint so the
   failure mode is structurally impossible.
3. **Fix data at the source, not per consumer.** My first cleanup deduped only the
   dashboard's read path — the daily brief and the chat were still reading the raw
   table. The lesson is old but real: one clean read function in the database layer,
   every consumer goes through it.
4. **Charts can be confidently wrong.** A "conviction over time" line looked great
   but actually measured *scan-batch composition* (early scans hit sports-heavy
   pages), not market movement. Deleted. A chart that misleads is worse than no
   chart.
5. **Match cadence to the product.** I initially scanned every 2 minutes (~7,000
   requests/day) for a product whose output is a daily brief. Hourly loses nothing.

## Cost engineering

gpt-4o-mini for scoring (~$0.15/1M input tokens): a full 1,000-market scan ≈ 1–2
cents; steady state only scores new markets, effectively free. The sports guard
removes ~25% of calls outright. One deliberate simplification: "Ask the Desk" uses
keyword-ranked retrieval + context stuffing instead of a vector store — at ~1,000
short rows, pgvector is infrastructure without payoff (the README documents the
switch point, ~5k rows).

On the Gemini hint: the EU has no Gemini free tier and my AI Studio project's
prepaid balance was empty, so I switched to OpenAI mid-build. The provider is one
file (`src/filter.py`); swapping back is a ~10-line change.

## Honest limitations

- **RLS is disabled** on the three tables — acceptable for a demo with a private
  key, not for production. Right fix: re-enable RLS, use the `service_role` key in
  the pipeline, and keep the anon key read-only for the UI.
- Scoring is single-shot per market; no self-consistency or eval harness yet. Next
  step would be a small labeled set (~20 markets with expected scores) as a
  regression gate on prompt changes.
- Sector/stock configuration is code-level (one dict + one prompt block), not
  UI-level — a deliberate scope cut given the 5% UI weighting.

## What I'd build next

Per-holding alerting (signal ≥8 on a holding → Slack/email), probability *change*
tracking between scans (the delta is often the signal, not the level), and the eval
harness above.
