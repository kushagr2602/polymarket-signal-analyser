"""Web server: a thin JSON API over the existing pipeline modules + the static front end in web/.

    uvicorn server:app --reload          # local
    uvicorn server:app --host 0.0.0.0 --port $PORT   # hosted (see render.yaml)

All logic lives in src/ (database, filter, agent, news, views); this file only wires it to HTTP.
"""
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src import config, database, llm, views

ROOT = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="Polymarket Signal Analyser", docs_url=None, redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1024)

@app.middleware("http")
async def revalidate_static(request: Request, call_next):
    """Static assets revalidate (ETag) on every load so a redeploy is never served stale; the API is uncached."""
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else "no-cache"
    return resp


# ponytail: in-process TTL cache + lock; fine for one instance, move to Redis if this ever scales out.
_cache: dict = {}
_lock = threading.Lock()


def cached(key: str, ttl: int, fn):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    val = fn()
    with _lock:
        _cache[key] = (time.time(), val)
    return val


# Cost control at the trust boundary: these endpoints spend the owner's OpenAI budget.
# ponytail: per-process, per-IP sliding window — swap for a shared store if run on >1 instance.
_hits: dict = {}


def limit(request: Request, bucket: str, n: int, per: int = 3600):
    ip = (request.headers.get("x-forwarded-for") or request.client.host).split(",")[0].strip()
    now = time.time()
    with _lock:
        q = [t for t in _hits.get((bucket, ip), []) if now - t < per]
        if len(q) >= n:
            raise HTTPException(429, "Easy there — try again in a bit.")
        _hits[(bucket, ip)] = q + [now]


def _load():
    db = database.get_client()
    sig = database.get_signals()  # deduped + expired-dropped in the shared layer
    reps = db.table("reports").select("*").order("report_date", desc=True).limit(60).execute().data
    n = db.table("markets").select("market_id", count="exact").execute().count
    return sig, reps, n


def _rescanning() -> bool:
    from src.scheduler import RESCAN_LOCK
    return os.path.exists(RESCAN_LOCK)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/state")
def state():
    sig, _, n_markets = cached("load", 600, _load)
    rows = views.to_rows(sig)
    wl = config.get_watchlist()
    last = max(((s.get("markets") or {}).get("fetched_at", "") for s in sig), default="")
    return {"asOf": last or None, "now": datetime.now(timezone.utc).isoformat(),
            "rescanning": _rescanning(), "watchlist": wl, "models": {r: llm.active(r) for r in llm.ROLES},
            "kpis": views.kpis(rows, n_markets), "signals": rows,
            "exposure": views.exposure(rows, wl["tickers"]), "hot": views.hot_topics(rows)}


@app.get("/api/news")
def news_feed():
    from src import news
    return cached("news", 1800, news.assess_news)


@app.get("/api/briefs")
def briefs():
    _, reps, _ = cached("load", 600, _load)
    return [{"date": r["report_date"], "content": r["content"]} for r in reps]


class Ask(BaseModel):
    question: str
    history: list[dict] = []


@app.post("/api/ask")
def ask(body: Ask, request: Request):
    limit(request, "ask", 20)
    from src import agent
    q = body.question.strip()[:600]
    if not q:
        raise HTTPException(400, "Ask something.")
    hist = [{"role": m["role"], "content": str(m["content"])[:2000]} for m in body.history[-6:]
            if m.get("role") in ("user", "assistant")]
    answer, trace = agent.run(q, hist, private=is_local(request))  # portfolio tool only on your own machine
    return {"answer": answer, "trace": trace}


@app.get("/api/suggest")
def suggest(industry: str, request: Request):
    limit(request, "suggest", 30)
    industry = industry.strip()[:60]
    if not industry:
        return {}

    def go():
        import json
        if llm.client is None:
            return {}
        prompt = (f'List up to 8 liquid, US-listed public-company stock tickers most central to "{industry}". '
                  'No ETFs or funds. Return JSON {"tickers": {"TICKER": "3-5 word business description"}}.')
        try:
            r = llm.chat("smart", messages=[{"role": "user", "content": prompt}],
                         response_format={"type": "json_object"})
            return {k.upper(): str(v)[:80] for k, v in json.loads(r.choices[0].message.content).get("tickers", {}).items()}
        except Exception:
            return {}
    return cached(f"suggest:{industry.lower()}", 3600, go)


class Watchlist(BaseModel):
    tickers: dict[str, str]
    sectors: list[str]


@app.post("/api/watchlist")
def save_watchlist(body: Watchlist, request: Request):
    limit(request, "watchlist", 15)
    tickers = {t.strip().upper(): d.strip()[:80] for t, d in body.tickers.items()}
    sectors = [s.strip()[:40] for s in body.sectors if s.strip()]
    if not (1 <= len(tickers) <= 25 and 1 <= len(sectors) <= 12):
        raise HTTPException(400, "Keep 1–25 tickers and 1–12 sectors.")
    if not all(re.fullmatch(r"[A-Z][A-Z.\-]{0,5}", t) for t in tickers):
        raise HTTPException(400, "Tickers must look like NVDA or BRK-B.")
    config.save_watchlist(tickers, sectors)
    return {"ok": True}


@app.post("/api/rescan")
def rescan(request: Request):
    if _rescanning():
        raise HTTPException(409, "A rescan is already running.")
    limit(request, "rescan", 3)
    subprocess.Popen([sys.executable, "-m", "src.scheduler", "--rescore"], cwd=ROOT,
                     stdout=open(os.path.join(tempfile.gettempdir(), "rescan.log"), "a"),
                     stderr=subprocess.STDOUT)
    return {"ok": True}


@app.post("/api/reload")
def reload():
    with _lock:
        _cache.clear()
    return {"ok": True}


# ---------------------------------------------------------------- screener (ETFs + stocks)

@app.get("/api/screen")
def screen():
    from src import market

    def go():
        data = market.load()
        rows = market.screen(data)
        return {"asOf": max((r["m"]["asof"] for r in rows), default=None), "fetched": data["fetched"],
                "rows": [{k: r[k] for k in ("t", "kind", "group", "name", "ccy", "score", "parts", "why", "tags")}
                         | {"m": {k: v for k, v in r["m"].items() if k != "years"}} for r in rows]}
    return cached("screen", 600, go)


@app.get("/api/instrument/{ticker}")
def instrument(ticker: str):
    from src import market
    r = market.instrument(market.load(), ticker.upper())
    if not r:
        raise HTTPException(404, "Not in the screener universe.")
    return r


@app.post("/api/explain/{ticker}")
def explain(ticker: str, request: Request):
    """Beginner-friendly write-up of one instrument, from the computed numbers only (cached per day)."""
    from src import market
    r = market.instrument(market.load(), ticker.upper())
    if not r:
        raise HTTPException(404, "Not in the screener universe.")
    if llm.client is None:
        raise HTTPException(503, "No OpenAI key configured.")
    limit(request, "explain", 20)

    def go():
        facts = "\n".join(f"- {c['label']}: {c['value']} — {c['plain']}" for c in r["cards"])
        prompt = (f"You explain investments to a complete beginner who finds financial concepts hard.\n"
                  f"Instrument: {r['name']} ({r['t']}), a {'fund (ETF)' if r['kind'] == 'etf' else 'single company stock'}, "
                  f"category: {r['group']}. Screener score {r['score']}/100 (rank {r['rank']} of {r['of']} {r['kind']}s here): {r['why']}\n"
                  f"Facts, all in euros:\n{facts}\n\n"
                  "Write at most 150 words in plain English, in four short parts with bold lead-ins: **What it is**, "
                  "**How it has behaved**, **The main risk**, **Who it usually suits**. Explain any term you use. "
                  "Use only the facts given. Never tell the reader to buy or sell, and end with one sentence reminding "
                  "them that past performance doesn't predict future returns.")
        resp = llm.chat("smart", messages=[{"role": "user", "content": prompt}])
        return {"text": resp.choices[0].message.content, "model": llm.active("smart")}
    return cached(f"explain:{r['t']}:{r['m']['asof']}", 86400, go)


# ---------------------------------------------------------------- portfolio (local only)

def is_local(request: Request) -> bool:
    """A direct request from this machine. A hosted deploy sits behind a proxy, which always adds X-Forwarded-For."""
    host = request.client.host if request.client else ""
    return not request.headers.get("x-forwarded-for") and host in ("127.0.0.1", "::1")


def local_only(request: Request):
    """Your trades never leave this machine: refuse anything that isn't a direct localhost request."""
    if not is_local(request):
        raise HTTPException(403, "Your portfolio only opens when the app runs on your own computer.")


def _portfolio():
    from src import market, portfolio
    data = market.load()
    return portfolio.analyse(portfolio.load(), data, market.screen(data))


@app.get("/api/portfolio")
def get_portfolio(request: Request):
    local_only(request)
    return _portfolio()


class Trade(BaseModel):
    date: str
    ticker: str
    side: str = "buy"
    qty: str | float
    price: str | float
    fees: str | float = 0
    note: str = ""


@app.post("/api/trades")
def add_trade(body: Trade, request: Request):
    local_only(request)
    from src import portfolio
    try:
        portfolio.save(portfolio.load() + [portfolio.clean(body.model_dump())])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _portfolio()


@app.delete("/api/trades/{tid}")
def delete_trade(tid: str, request: Request):
    local_only(request)
    from src import portfolio
    try:
        portfolio.save([t for t in portfolio.load() if t["id"] != tid])
    except ValueError as e:  # e.g. deleting a buy that a later sell depends on
        raise HTTPException(400, f"Can't delete that trade: {e}")
    return _portfolio()


class CsvImport(BaseModel):
    csv: str


@app.post("/api/trades/import")
def import_trades(body: CsvImport, request: Request):
    local_only(request)
    if len(body.csv) > 2_000_000:
        raise HTTPException(413, "That file is too large.")
    from src import portfolio
    rows, errs = portfolio.parse_csv(body.csv)
    have = portfolio.load()
    key = lambda t: (t["date"], t["ticker"], t["side"], round(t["qty"], 8), round(t["price"], 6))
    seen = {key(t) for t in have}
    new = [t for t in rows if key(t) not in seen]  # re-importing the same export must not double your holdings
    if new:
        try:
            portfolio.save(have + new)
        except ValueError as e:
            raise HTTPException(400, str(e))
    return {"added": len(new), "skipped": len(rows) - len(new), "errors": errs[:20], "portfolio": _portfolio()}


@app.get("/api/trades/template.csv")
def trades_template():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("date,ticker,side,qty,price,fees,note\n2025-01-15,VWCE.DE,buy,10,118.40,1.00,monthly plan\n"
                             "2025-03-03,ASML.AS,buy,2,640.00,1.00,\n", media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=trades-template.csv"})


app.mount("/", StaticFiles(directory=os.path.join(ROOT, "web"), html=True), name="web")
