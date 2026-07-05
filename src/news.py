import json
import urllib.request
import xml.etree.ElementTree as ET

from . import config
from .filter import client, MODEL

# Free RSS, no API key. Macro themes mirror the filtering contract; Yahoo covers the watchlist directly.
MACRO = ("https://news.google.com/rss/search?q="
         "Federal+Reserve+OR+interest+rates+OR+inflation+OR+recession+OR+crypto+OR+bitcoin+"
         "OR+FDA+OR+tariff+OR+%22AI+regulation%22+OR+antitrust+when:1d&hl=en-US&gl=US&ceid=US:en")


def _ticker_feed() -> str:
    tickers = ",".join(config.get_watchlist()["tickers"])
    return f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={tickers}&region=US&lang=en-US"


ASSESS_PROMPT = """You are an equity analyst.
{holdings}

For each numbered headline, judge its likely effect on the watchlist. Return a JSON object
{{"items": [{{"i": <index>, "stance": "bullish|bearish|neutral", "impact": <0-5>,
"tickers": ["<ticker>"...], "note": "<one sentence: the read-through to the watchlist>"}}]}}.
impact 0 = irrelevant to the watchlist; 5 = direct, material catalyst for a watched stock.
Most world news is 0-1. tickers may only contain watchlist tickers.

Headlines:
{headlines}"""


def _parse_rss(raw: bytes, limit: int) -> list[dict]:
    """Parse RSS bytes → [{title, link}]. Pure — unit-testable offline."""
    root = ET.fromstring(raw)
    out = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        if title:
            out.append({"title": title, "link": item.findtext("link") or ""})
    return out


def _rss(url: str, limit: int) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return _parse_rss(urllib.request.urlopen(req, timeout=15).read(), limit)


def fetch_headlines(macro: int = 18, ticker: int = 12) -> list[dict]:
    """Pull recent macro + watchlist-specific headlines, deduped by title."""
    seen, items = set(), []
    for url, n in ((MACRO, macro), (_ticker_feed(), ticker)):
        try:
            for h in _rss(url, n):
                key = h["title"].lower()
                if key not in seen:
                    seen.add(key)
                    items.append(h)
        except Exception:
            continue  # one dead feed shouldn't kill the page
    return items


def assess_news() -> list[dict]:
    """Headlines + LLM portfolio impact, sorted most-impactful first. One LLM call."""
    items = fetch_headlines()
    if not items:
        return []
    numbered = "\n".join(f"{i}. {h['title']}" for i, h in enumerate(items))
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": ASSESS_PROMPT.format(holdings=config.holdings_block(), headlines=numbered)}],
        response_format={"type": "json_object"},
    )
    by_i = {a["i"]: a for a in json.loads(resp.choices[0].message.content).get("items", [])}
    for i, h in enumerate(items):
        a = by_i.get(i, {})
        h["stance"] = a.get("stance", "neutral")
        h["impact"] = int(a.get("impact", 0))
        h["tickers"] = a.get("tickers", []) or []
        h["note"] = a.get("note", "")
    return sorted(items, key=lambda h: h["impact"], reverse=True)


if __name__ == "__main__":
    rows = assess_news()
    assert rows and all(0 <= r["impact"] <= 5 for r in rows), "impact out of range"
    for r in rows[:10]:
        print(f"[{r['impact']}] {r['stance']:7} {r['tickers']} | {r['title'][:70]}")
