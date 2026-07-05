# How to read this dashboard (no finance background needed)

## The one idea behind everything

On [Polymarket](https://polymarket.com), people bet real money on real events —
"Will the Fed cut interest rates?", "Will Bitcoin hit $150k?". The price of each
bet works out to a probability: if a "yes" share costs 70 cents, the crowd
collectively thinks there's about a **70% chance it happens**.

This dashboard asks one question about every big bet out there:
**"If this event happens, does it move any stock on my watchlist?"**
An AI reads each market and answers with a score and a written explanation.

## The two numbers on every signal

They sound similar but answer different questions:

- **Conviction (0–10)** — *does this matter to my stocks?*
  - **8–10** — a direct hit on one specific stock. Example: a Bitcoin crash
    market scores high for a crypto-exchange stock, because its business lives
    and dies with crypto prices.
  - **5–7** — hits a whole sector the watchlist cares about (e.g. AI regulation).
  - **3–4** — moves the entire market a little (interest rates, recession).
  - **0–2** — noise. Sports, celebrities, weather. Ignore.
- **Probability (%)** — *does the crowd think it will happen?* That's the
  market's live betting odds, not the AI's opinion.

Put together: **conviction tells you whether to care, probability tells you
which way to lean, and expiry tells you when you'll know.** A signal with
conviction 8, probability 75%, resolving in 12 days means: something that
directly hits one of your stocks is likely to happen within two weeks.

## What each panel is for

**The number strip (top)** — the day at a glance: how many markets were
scanned, how many are worth attention (≥5), how many are urgent (≥8).

**Watchlist exposure** — one card per stock you watch: how many live signals
touch it, and the strongest one. A card with many signals and a high peak is
the stock with the most brewing. ("From stored signals" means your configured
tickers have no scored data yet — run a scan.)

**Top signals** — the five most important bets right now, with the AI's
explanation of *why* each one matters. If you read only one section, read this.
Click a title to see the actual market on Polymarket.

**Sector conviction (bar chart)** — which themes are hot. Longer bar = that
theme's signals matter more on average; the number after the dot is how many.

**Signal map (dot chart)** — every relevant bet as one dot. Higher = matters
more; further right = more real money riding on it. **Only the top-right
corner matters** — big money on things that hit your stocks.

**Upcoming catalysts** — a schedule. When a bet "resolves", the real-world
answer arrives — that's the moment the news actually lands. Soonest first.

**Market pricing (histogram)** — where the crowd's odds sit across your
signals. Lots of bets near 0–20% = the market thinks those events won't
happen; near 80–100% = the market has already made up its mind.

**All signals (table)** — everything, sortable and filterable. "open ↗" jumps
to the real market.

**World news tab** — today's headlines scored 0–5 for impact on your stocks.
Blue = supportive, red = adverse, grey = noise.

**Ask the desk tab** — ask questions in plain English ("what threatens COIN
this month?"). The agent queries the database and answers only from stored
data — the line above each answer shows which lookups it ran.

**Daily brief tab** — the whole day compressed into a short analyst note.

## The 30-second routine

1. Open the desk → read the **Top signals** explanations.
2. Glance at **exposure cards** — which of your stocks has the most heat?
3. Check **Upcoming catalysts** — anything resolving in the next week or two?
4. Anything ≥8 conviction on a stock you own: click through and read the market.

That's it. Everything else is supporting detail.
