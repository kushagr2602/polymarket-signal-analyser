"""Eval harness for the LLM filter — a labeled regression set, not unit tests.

Run:  python3 tests/eval_filter.py     (~15 LLM calls ≈ a cent)

Each case pins an expected score BAND, not an exact value: LLM scores wobble
±1, but a sports market scoring 5 or a direct BTC catalyst scoring 2 is a
regression. Run after any prompt change; fail = don't ship the prompt.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.filter import score_market

TICKERS = set(config.get_watchlist()["tickers"])

# Cases assume the default watchlist (NVDA, TSLA, COIN, LLY) — see watchlist.json.
# (question, min_score, max_score, must_include_ticker | None)
CASES = [
    # hard zeros — out of mandate
    ("Will USA win the 2026 FIFA World Cup?",                        0, 0, None),
    ("Spread: Lakers (-4.5) vs Celtics",                             0, 0, None),
    ("Will Taylor Swift announce a tour in 2026?",                   0, 2, None),
    ("Will it snow in New York on Christmas Day?",                   0, 1, None),
    # direct catalysts — must score high and tag the right stock
    ("Will Bitcoin dip to $40,000 by December 31, 2026?",            6, 10, "COIN"),
    ("Will the FDA approve Eli Lilly's next GLP-1 drug in 2026?",    6, 10, "LLY"),
    ("Will the US ban NVIDIA AI chip exports to China in 2026?",     6, 10, "NVDA"),
    ("Will Tesla deliver over 2 million vehicles in 2026?",          6, 10, "TSLA"),
    # sector / macro — mid band
    ("Will the EU AI Act enforcement be delayed to 2027?",           3, 8, None),
    ("Will the Fed cut interest rates in September 2026?",           3, 7, None),
    ("US recession declared in 2026?",                               3, 7, None),
    ("Will China impose new tariffs on US semiconductor imports?",   3, 9, None),
    # weak / indirect — must stay low
    ("Will India's population exceed 1.46 billion in 2026?",         0, 2, None),
    ("Will the next James Bond actor be announced in 2026?",         0, 1, None),
]


def main() -> int:
    failures = []
    for q, lo, hi, ticker in CASES:
        s = score_market({"market_id": "eval", "question": q, "probability": 0.5,
                          "volume_usd": 1_000_000, "category": "", "expiry_date": "2026-12-31"})
        score, tags = s["relevance_score"], s["affected_tickers"]
        ok_score = lo <= score <= hi
        ok_ticker = ticker is None or ticker in tags
        ok_valid = all(t in TICKERS for t in tags)
        status = "ok " if (ok_score and ok_ticker and ok_valid) else "FAIL"
        print(f"{status} [{score}/10 exp {lo}-{hi}] {tags or '—'} | {q[:60]}")
        if status == "FAIL":
            failures.append(q)
    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} passed")
    if failures:
        print("regressions:", *[f"  - {q}" for q in failures], sep="\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
