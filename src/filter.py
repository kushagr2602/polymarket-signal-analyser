import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
# None on a keyless checkout (e.g. CI / fresh clone) so imports and offline tests still work
client = OpenAI() if os.getenv("OPENAI_API_KEY") else None

MODEL = "gpt-4o-mini"  # ponytail: cheap+capable for scoring; bump to gpt-4o if scores look shallow

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
8-10: Direct catalyst for a specific holding
5-7: Sector-level impact
3-4: Macro signal with broad portfolio implications
1-2: Weak/indirect connection
0: Not relevant to any BIT Capital position or sector"""


def score_market(market: dict) -> dict:
    """LLM-score one market. Returns a signal dict (schema columns only)."""
    prompt = PROMPT.format(
        question=market.get("question", ""),
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
        "affected_tickers": out.get("affected_tickers") or [],
        "reasoning": out.get("reasoning", ""),
    }


if __name__ == "__main__":
    # Self-check: validate the shape of a scored signal, not the score value.
    s = score_market({
        "market_id": "test",
        "question": "Will the Fed cut interest rates in September 2026?",
        "probability": 0.62, "volume_usd": 1_000_000,
        "category": "Economy", "expiry_date": "2026-09-30",
    })
    assert 0 <= s["relevance_score"] <= 10, s
    assert isinstance(s["affected_tickers"], list), s
    print(json.dumps(s, indent=2))
