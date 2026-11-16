"""Function-calling analyst agent: screener, your portfolio, and prediction-market signals.

The LLM plans which tools to call, executes them, and synthesizes an answer —
an agent loop, not single-shot RAG. Tool trace is returned for transparency.
The portfolio tool is only offered (and only executable) when the request comes from this machine.
"""
import json

from . import config, database, llm

MAX_TURNS = 5  # ponytail: hard cap on the loop; raise if tasks legitimately need more hops


def _system(private: bool) -> str:
    return f"""You are the analyst inside "My Financial Scanner", talking to a beginner investor who finds financial concepts hard.
Through your tools you can see: a screener of European ETFs and large stocks (prices in EUR, 5 years, scored 0-100 against others
of the same type){", the user's own portfolio (the trades they entered)" if private else ""}, and prediction-market signals for this watchlist:
{config.holdings_block()}
Rules:
- Get every number from a tool. Never invent prices, returns, scores, holdings or probabilities. If the data can't answer it, say so.
- Lead with a direct answer in one or two sentences, then the 2-4 facts behind it. Keep it short.
- Explain any financial term in plain words the first time you use it, with a EUR example where it helps (e.g. "a -30% worst fall means EUR 1,000 briefly became EUR 700").
- Never tell the user to buy or sell. You may point out facts (concentration, overlap, higher swing) and name instruments worth researching, saying why.
- When you discuss specific investments, end with one line: past performance doesn't predict future returns."""

TOOLS = [
    {"type": "function", "function": {
        "name": "query_signals",
        "description": "Search scored prediction-market signals. Returns market question, relevance score 0-10, sector, affected tickers, implied probability, volume, reasoning.",
        "parameters": {"type": "object", "properties": {
            "min_score": {"type": "integer", "description": "Minimum relevance score, default 5"},
            "ticker": {"type": "string", "description": "Filter to one ticker, e.g. IREN"},
            "keyword": {"type": "string", "description": "Substring match on the market question, e.g. 'bitcoin'"},
            "limit": {"type": "integer", "description": "Max rows, default 15"},
        }}}},
    {"type": "function", "function": {
        "name": "screen_instruments",
        "description": "Ranked screener of European ETFs/ETCs and large stocks (all figures in EUR). Returns ticker, name, group, score 0-100, a one-line reason, last-12-month return, growth per year (3y), swing (volatility), worst fall, return-for-risk.",
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["etf", "stock", "fund"], "description": "etf (index ETFs/ETCs), stock, or fund (actively managed funds such as BIT Capital's); default etf"},
            "group": {"type": "string", "description": "Optional group: World, US, Tech, Europe, Emerging, India, Small caps, Dividend, Themes, Bonds, Gold (ETFs); Europe, US, India (stocks); Tech & growth, Crypto, India (active funds)"},
            "sort": {"type": "string", "enum": ["score", "r1y", "growth", "vol", "mdd", "rpr"], "description": "score (default), r1y, growth, vol (calmest first), mdd (smallest worst fall first), rpr"},
            "query": {"type": "string", "description": "Optional name/ticker substring, e.g. 'nasdaq' or 'VWCE'"},
            "limit": {"type": "integer", "description": "Max rows, default 10"},
        }}}},
    {"type": "function", "function": {
        "name": "get_instrument",
        "description": "Everything about one screener instrument: score, rank, reason, each metric with a plain-English explanation, and calendar-year returns.",
        "parameters": {"type": "object", "properties": {"ticker": {"type": "string", "description": "e.g. VWCE.DE, ASML.AS, NVDA"}},
                       "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "get_latest_brief",
        "description": "Fetch the most recent daily analyst brief (markdown).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "portfolio_exposure",
        "description": "Prediction-market watchlist: per watched ticker, how many active signals touch it and the peak score.",
        "parameters": {"type": "object", "properties": {}}}},
]


def query_signals(min_score: int = 5, ticker: str = "", keyword: str = "", limit: int = 15) -> list[dict]:
    rows = database.get_signals(min_score=min_score)
    if ticker:
        rows = [r for r in rows if ticker.upper() in (r.get("affected_tickers") or [])]
    if keyword:
        rows = [r for r in rows if keyword.lower() in ((r.get("markets") or {}).get("question") or "").lower()]
    out = []
    for r in rows[:limit]:
        m = r.get("markets") or {}
        out.append({"question": m.get("question"), "score": r["relevance_score"],
                    "sector": r.get("sector"), "tickers": r.get("affected_tickers"),
                    "probability": m.get("probability"), "volume_usd": m.get("volume_usd"),
                    "reasoning": r.get("reasoning")})
    return out


def get_latest_brief() -> str:
    db = database.get_client()
    rep = db.table("reports").select("content").order("report_date", desc=True).limit(1).execute().data
    return rep[0]["content"] if rep else "No brief generated yet."


def portfolio_exposure() -> dict:
    rows = database.get_signals(min_score=5)
    out = {}
    for tkr in config.get_watchlist()["tickers"]:
        hits = [r["relevance_score"] for r in rows if tkr in (r.get("affected_tickers") or [])]
        out[tkr] = {"signals": len(hits), "peak_score": max(hits, default=0)}
    return out


PORTFOLIO_TOOL = {"type": "function", "function": {
    "name": "get_my_portfolio",
    "description": "The user's own portfolio from the trades they entered: totals, each holding (weight, value, profit/loss, screener score), allocation by type and group, how today's mix behaved over 3 years, and plain-English notes on concentration and overlap.",
    "parameters": {"type": "object", "properties": {}}}}


def _screen():
    from . import market
    data = market.load()
    return data, market.screen(data)


def screen_instruments(kind: str = "etf", group: str = "", sort: str = "score", query: str = "", limit: int = 10) -> list[dict]:
    _, rows = _screen()
    rows = [r for r in rows if r["kind"] == kind and (not group or r["group"].lower() == group.lower())
            and (not query or query.lower() in (r["name"] + " " + r["t"]).lower())]
    key = {"score": lambda r: -r["score"], "vol": lambda r: r["m"]["vol"] if r["m"]["vol"] is not None else 9,
           "mdd": lambda r: -(r["m"]["mdd"] or -9)}.get(sort, lambda r: -(r["m"].get(sort) if r["m"].get(sort) is not None else -9))
    r2 = lambda x: None if x is None else round(x, 3)
    return [{"ticker": r["t"], "name": r["name"], "group": r["group"], "score": r["score"], "why": r["why"],
             "last_12m": r2(r["m"]["r1y"]), "growth_per_year": r2(r["m"]["growth"]), "swing": r2(r["m"]["vol"]),
             "worst_fall": r2(r["m"]["mdd"]), "return_for_risk": r2(r["m"]["rpr"])} for r in sorted(rows, key=key)[:max(1, min(limit, 30))]]


def get_instrument(ticker: str) -> dict:
    from . import market
    data, _ = _screen()
    r = market.instrument(data, ticker.strip().upper())
    if not r:
        return {"error": f"{ticker} isn't in the screener list."}
    return {"ticker": r["t"], "name": r["name"], "kind": r["kind"], "group": r["group"], "score": r["score"],
            "rank": f"{r['rank']} of {r['of']}", "why": r["why"], "year_returns": {y: round(v, 3) for y, v in r["m"]["years"].items()},
            "facts": [{"label": c["label"], "value": c["value"], "plain": c["plain"]} for c in r["cards"]]}


def get_my_portfolio() -> dict:
    from . import portfolio
    data, rows = _screen()
    p = portfolio.analyse(portfolio.load(), data, rows)
    if not p["holdings"]:
        return {"empty": True, "note": "No trades entered yet — the user can add them on the Portfolio page."}
    r2 = lambda x: None if x is None else round(x, 3)
    return {"totals": {k: r2(v) for k, v in p["totals"].items()},
            "holdings": [{"ticker": h["ticker"], "name": h["name"], "type": h["kind"], "group": h["group"], "weight": r2(h["weight"]),
                          "value_eur": r2(h["value"]), "profit_eur": r2(h["pnl"]), "profit_pct": r2(h["pnl_pct"]), "score": h["score"]}
                         for h in p["holdings"]],
            "allocation": {k: [[n, r2(w)] for n, w in v] for k, v in p["alloc"].items()},
            "todays_mix_history": p["mix"] and {k: r2(p["mix"][k]) for k in ("growth", "r1y", "vol", "mdd", "rpr")},
            "notes": [n["text"] for n in p["notes"]]}


_IMPL = {"query_signals": query_signals, "get_latest_brief": get_latest_brief, "portfolio_exposure": portfolio_exposure,
         "screen_instruments": screen_instruments, "get_instrument": get_instrument, "get_my_portfolio": get_my_portfolio}


def tools_for(private: bool) -> list[dict]:
    return TOOLS + ([PORTFOLIO_TOOL] if private else [])


def run(question: str, history: list[dict] | None = None, private: bool = False) -> tuple[str, list[str]]:
    """Agent loop: plan → call tools → synthesize. Returns (answer, tool_trace).
    private=True only for requests from this machine: it unlocks the user's portfolio."""
    tools = tools_for(private)
    allowed = {t["function"]["name"] for t in tools}
    msgs = [{"role": "system", "content": _system(private)}] + (history or []) + [{"role": "user", "content": question}]
    trace = []
    for _ in range(MAX_TURNS):
        resp = llm.chat("smart", messages=msgs, tools=tools)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content or "", trace
        msgs.append({"role": "assistant", "content": msg.content,
                     "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                if name not in allowed:  # the model asked for a tool it wasn't offered — never execute it
                    raise PermissionError(f"{name} is not available here")
                args = json.loads(tc.function.arguments or "{}")
                result = _IMPL[name](**args)
                trace.append(f"{name}({', '.join(f'{k}={v}' for k, v in args.items())})")
            except Exception as e:  # bad args or tool failure — tell the model, let it recover
                result = {"error": str(e)}
                trace.append(f"{name} → error")
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)})
    return "I hit my tool-call budget before finishing — try a narrower question.", trace


if __name__ == "__main__":
    answer, trace = run("Which signals threaten IREN right now, and how exposed are we overall?")
    print("TOOLS CALLED:", trace)
    print(answer)
    assert trace, "agent should have called at least one tool"
