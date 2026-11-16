"""Discover: flags from the data, and any theme you type — every suggestion checked against real prices.

flags() and validate() are pure and unit-tested. explore() asks the analyst model for candidates, then keeps only the ones
that have real price history AND whose Yahoo name matches what the model claimed (catches invented tickers).
Leads to research, not recommendations.
"""
import json
import re

from . import market

STOP = {"inc", "corp", "corporation", "co", "company", "holdings", "holding", "group", "plc", "ltd", "limited", "sa", "se", "ag",
        "nv", "the", "and", "etf", "ucits", "fund", "class", "shares", "acc", "dist", "technologies", "technology", "international"}


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) >= 3 and w not in STOP}


def flags(rows: list[dict], world: str = "VWCE.DE", corr: dict | None = None) -> list[dict]:
    """Rule-based flags over screener rows. corr = {ticker: weekly correlation with the world ETF} (optional)."""
    m = lambda r, k: r["m"].get(k)
    def pick(cond, key, rev=True, n=6):
        hits = [r for r in rows if r["t"] != world and cond(r)]
        return sorted(hits, key=lambda r: m(r, key) if m(r, key) is not None else 0, reverse=rev)[:n]
    out = [
        {"key": "compounders", "title": "Quiet compounders",
         "plain": "Grew well for three years without big swings: at least +10% a year, a typical swing under 18%, and good return for the risk. "
                  "The boring kind of good: these are the ones people tend to hold for years.",
         "rows": pick(lambda r: (m(r, "cagr3") or 0) >= .10 and (m(r, "vol") or 1) <= .18 and (m(r, "rpr") or 0) >= 1.2 and not m(r, "short"), "rpr"),
         "show": "rpr"},
        {"key": "beaten", "title": "Strong record, now beaten down",
         "plain": "Grew at least +12% a year over three years but sits 20% or more below its 1-year high. Sometimes that's a sale; "
                  "sometimes the price is falling for a real reason. Read what happened before deciding anything.",
         "rows": pick(lambda r: (m(r, "cagr3") or 0) >= .12 and (m(r, "off_high") or 0) <= -.20, "off_high", rev=False), "show": "off_high"},
        {"key": "waking", "title": "Waking up",
         "plain": "Up 10% or more in the last 3 months after a flat or negative year. Early momentum can keep going, or fade fast. "
                  "Worth watching, not chasing.",
         "rows": pick(lambda r: (m(r, "r3m") or 0) >= .10 and (m(r, "r1y") or 1) <= .05, "r3m"), "show": "r3m"},
    ]
    if corr:
        out.append({"key": "diversifiers", "title": "Moves differently from the world",
                    "plain": "Barely follows a world stock ETF (weekly correlation under 0.3) and still grew. Owning something like this "
                             "next to a world fund is the basic way to spread risk, usually bonds, gold or very different markets.",
                    "rows": pick(lambda r: r.get("kind") != "stock" and corr.get(r["t"]) is not None and corr[r["t"]] < .3  # funds only: a single
                                 and (m(r, "growth") or 0) > 0, "growth"),                                   # stock is its own risk
                    "show": "corr"})
        for f in out:
            for r in f["rows"]:
                r.setdefault("corr", corr.get(r["t"]))
    return out


def validate(cands: list[dict], found: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """found = {ticker: {"name": Yahoo name, "closes": [...]}}. Keep a candidate only if it has 60+ days of prices and
    its Yahoo name shares a real word with the name the model gave. Returns (kept, dropped with a reason)."""
    kept, dropped = [], []
    for c in cands:
        t = str(c.get("ticker") or "").strip().upper()
        f = found.get(t) or {}
        if not t or len(f.get("closes") or []) < 60:
            dropped.append({**c, "ticker": t, "reason": "no price data (private, delisted or wrong symbol)"})
        elif not f.get("verified") and not (_words(c.get("name")) & _words(f.get("name"))):
            dropped.append({**c, "ticker": t, "reason": f"symbol belongs to {f.get('name') or 'something else'}"})
        else:
            kept.append({**c, "ticker": t, "yahoo_name": f["name"]})
    return kept, dropped


PROMPT = """You help a beginner investor explore an investment theme: "{theme}".
Return JSON only:
{{"explainer": "2-3 plain sentences: what this theme is and why people think it could grow",
 "risks": "1-2 plain sentences: what can go wrong for investors in it",
 "simple_route": "one sentence on the simplest, most diversified way to get exposure (e.g. a broad or thematic ETF), or say there isn't a clean one",
 "candidates": [{{"name": "official company or fund name", "ticker": "Yahoo Finance symbol with exchange suffix for non-US listings, e.g. IFX.DE, 6758.T, RELIANCE.NS", "type": "stock or etf", "why": "one line: which part of the theme it covers", "pure_play": true or false}}],
 "private": [{{"name": "notable private company in this theme", "why": "one line"}}]}}
Rules: up to 10 candidates, only companies/ETFs currently listed on a public exchange; mix established leaders and smaller pure plays,
and include a relevant ETF if one exists. Up to 4 private companies (they can't be bought directly). Never recommend buying or selling."""


def explore(theme: str, data: dict) -> dict:
    from . import llm
    resp = llm.chat("smart", messages=[{"role": "user", "content": PROMPT.format(theme=theme)}], response_format={"type": "json_object"})
    out = json.loads(resp.choices[0].message.content)
    cands = [c for c in (out.get("candidates") or [])[:12] if isinstance(c, dict)]
    found = market.lookup([str(c.get("ticker") or "").strip().upper() for c in cands if c.get("ticker")], data)
    kept, dropped = validate(cands, found)
    for c in kept:
        mm = market.metrics(found[c["ticker"]]["closes"])
        c["m"] = mm and {k: mm[k] for k in ("r1y", "growth", "cagr3", "vol", "mdd", "rpr", "off_high", "short")}
        c["tags"] = market.tags(mm) if mm else []
        c["speculative"] = bool(mm and ((mm["vol"] or 0) > .45 or mm["short"]))
    return {"theme": theme, "explainer": out.get("explainer", ""), "risks": out.get("risks", ""), "simple_route": out.get("simple_route", ""),
            "candidates": kept, "dropped": dropped, "private": (out.get("private") or [])[:4], "model": llm.active("smart")}
