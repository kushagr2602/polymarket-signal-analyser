import os
import re
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
# None on a keyless checkout (e.g. CI / fresh clone) so imports and offline tests still work
client = OpenAI() if os.getenv("OPENAI_API_KEY") else None

MODEL = "gpt-4o-mini"  # ponytail: cheap+capable for scoring; bump to gpt-4o if scores look shallow

TICKERS = {"HIMS", "HOOD", "RDDT", "IREN"}  # LLM sometimes invents tickers ("IRD") — enforce the book

# Hard-zero guard: sports/esports markets are never relevant, per the filtering contract.
# Catching them here also skips the LLM call entirely.
SPORTS_RE = re.compile(
    r"\b(vs\.?|spread:|o/u|moneyline|world cup|fifa|uefa|premier league|bundesliga|la liga|serie a|"
    r"nba|nfl|nhl|mlb|ncaa|ufc|boxing|f1|grand prix|motogp|olympi\w*|wimbledon|atp|wta|grand slam|"
    r"map \d|odd/even total|first blood|kills\??)\b",
    re.IGNORECASE,
)

PROMPT = """You are an equity analyst at BIT Capital, a tech-focused investment fund.
BIT Capital's current holdings include: HIMS (health-tech), HOOD (fintech/retail investing),
RDDT (AI data licensing), IREN (AI infrastructure/Bitcoin mining).
BIT Capital's focus sectors: AI Infrastructure, Health-Tech, Fintech, E-Commerce, Adtech, Biotech, Crypto.

Evaluate this Polymarket prediction market for relevance to BIT Capital's equity portfolio:

Market: {question}
Current probability: {probability}
Volume: ${volume_usd}
Category: {category}
Expiry: {expiry_date}

Return JSON:
{{
  "relevance_score": <0-10>,
  "sector": "<most relevant BIT sector or null>",
  "affected_tickers": ["<ticker>", ...],
  "reasoning": "<one paragraph: why this market matters or doesn't, what it implies for the portfolio>"
}}

Score rubric:
8-10: Direct catalyst for a specific holding — company-specific events (earnings, FDA decisions,
      M&A, data-licensing deals, regulation aimed at that company) or the price of an asset the
      company's business directly depends on (e.g. Bitcoin for a miner)
5-7: Sector-level impact
3-4: Macro signal with broad portfolio implications (rates, recession, tariffs)
1-2: Weak/indirect connection; demographic or social statistics with no tradable equity path
0: Not relevant to any position or sector

Hard rules:
- Sports, esports, celebrity, and entertainment outcomes are ALWAYS relevance_score 0 with no tickers.
- affected_tickers may only contain: HIMS, HOOD, RDDT, IREN. Never invent tickers."""


def score_market(market: dict) -> dict:
    """Score one market. Returns a signal dict (schema columns only)."""
    q = market.get("question", "")
    if SPORTS_RE.search(q):
        return {
            "market_id": market["market_id"],
            "relevance_score": 0,
            "sector": None,
            "affected_tickers": [],
            "reasoning": "Sports/entertainment market — outside BIT Capital's mandate by contract.",
        }
    prompt = PROMPT.format(
        question=q,
        probability=market.get("probability"),
        volume_usd=market.get("volume_usd"),
        category=market.get("category", ""),
        expiry_date=market.get("expiry_date"),
    )
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    out = json.loads(resp.choices[0].message.content)
    return {
        "market_id": market["market_id"],
        "relevance_score": int(out.get("relevance_score", 0)),
        "sector": out.get("sector") or None,
        "affected_tickers": [t for t in (out.get("affected_tickers") or []) if t in TICKERS],
        "reasoning": out.get("reasoning", ""),
    }


if __name__ == "__main__":
    # Offline check: sports guard needs no API key.
    s = score_market({"market_id": "t1", "question": "Will USA win the 2026 FIFA World Cup?"})
    assert s["relevance_score"] == 0 and s["affected_tickers"] == [], s
    # Live check: shape of an LLM-scored signal.
    s = score_market({
        "market_id": "t2",
        "question": "Will the Fed cut interest rates in September 2026?",
        "probability": 0.62, "volume_usd": 1_000_000,
        "category": "Economy", "expiry_date": "2026-09-30",
    })
    assert 0 <= s["relevance_score"] <= 10, s
    assert all(t in TICKERS for t in s["affected_tickers"]), s
    print(json.dumps(s, indent=2))
