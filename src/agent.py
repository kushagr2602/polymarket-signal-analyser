"""Function-calling analyst agent over the signal database.

The LLM plans which tools to call, executes them, and synthesizes an answer —
an agent loop, not single-shot RAG. Tool trace is returned for transparency.
"""
import json

from . import config, database, llm

MAX_TURNS = 5  # ponytail: hard cap on the loop; raise if tasks legitimately need more hops


def _system() -> str:
    return f"""You are an equity analyst agent.
{config.holdings_block()}
Answer using your tools — never invent markets, probabilities, or scores.
If the data doesn't contain the answer, say so. Tight, concrete analyst tone."""

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
        "name": "get_latest_brief",
        "description": "Fetch the most recent daily analyst brief (markdown).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "portfolio_exposure",
        "description": "Per-ticker summary: how many active signals touch each holding and the peak score.",
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


_IMPL = {"query_signals": query_signals, "get_latest_brief": get_latest_brief,
         "portfolio_exposure": portfolio_exposure}


def run(question: str, history: list[dict] | None = None) -> tuple[str, list[str]]:
    """Agent loop: plan → call tools → synthesize. Returns (answer, tool_trace)."""
    msgs = [{"role": "system", "content": _system()}] + (history or []) + [{"role": "user", "content": question}]
    trace = []
    for _ in range(MAX_TURNS):
        resp = llm.chat("smart", messages=msgs, tools=TOOLS)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content or "", trace
        msgs.append({"role": "assistant", "content": msg.content,
                     "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
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
