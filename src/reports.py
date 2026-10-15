import json
from datetime import date

from . import config, database, llm

REPORT_PROMPT = """You are a senior equity analyst writing the daily Polymarket signal brief.
{holdings}

Below are today's top prediction-market signals relevant to the watchlist.

Signals (JSON):
{signals}

Write a concise markdown brief:
- Lead with the single most actionable signal and what it implies for a specific watched stock.
- Group the rest by sector. For each, state the implied probability shift and the equity read-through.
- Be specific and analyst-grade. No filler, no restating the question verbatim.
- End with a one-line "Watch next" list of tickers to monitor.
"""

def generate_report(limit: int = 20) -> dict | None:
    """Build today's report from top signals. Returns the inserted report dict, or None if no signals."""
    signals = database.get_top_signals(limit)
    if not signals:
        return None
    prompt = REPORT_PROMPT.format(holdings=config.holdings_block(),
                                  signals=json.dumps(signals, indent=2, default=str))
    resp = llm.chat("smart", messages=[{"role": "user", "content": prompt}])
    content = resp.choices[0].message.content
    report = {
        "report_date": date.today().isoformat(),
        "content": content,
        "top_signals": signals,
    }
    database.insert_report(report)
    return report


if __name__ == "__main__":
    r = generate_report()
    print(r["content"] if r else "No signals yet — run the filter first.")
