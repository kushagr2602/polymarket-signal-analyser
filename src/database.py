import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_client():
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"]
        )
    return _client

def insert_markets(markets: list[dict]) -> int:
    db = get_client()
    if not markets:
        return 0
    res = db.table("markets").upsert(markets, on_conflict="market_id").execute()
    return len(res.data)

def insert_signal(signal: dict):
    db = get_client()
    db.table("signals").insert(signal).execute()

def insert_report(report: dict):
    db = get_client()
    db.table("reports").insert(report).execute()

def _all_rows(table: str, select: str, order: str | None = None) -> list[dict]:
    """Fetch every row, paging past PostgREST's 1000-row-per-request cap."""
    db, out, off = get_client(), [], 0
    while True:
        q = db.table(table).select(select)
        if order:
            q = q.order(order, desc=True)
        page = q.range(off, off + 999).execute().data
        out += page
        if len(page) < 1000:
            return out
        off += 1000


def get_unfiltered_markets(limit: int = 100) -> list[dict]:
    # complete seen-set (NOT capped at 1000, or already-scored markets get re-scored → duplicate signals)
    seen = {r["market_id"] for r in _all_rows("signals", "market_id")}
    markets = _all_rows("markets", "*", order="volume_usd")  # highest-volume first
    return [m for m in markets if m["market_id"] not in seen][:limit]

def get_top_signals(limit: int = 20) -> list[dict]:
    db = get_client()
    res = (
        db.table("signals")
        .select("*, markets(question, probability, volume_usd, expiry_date)")
        .gte("relevance_score", 5)
        .order("relevance_score", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data
