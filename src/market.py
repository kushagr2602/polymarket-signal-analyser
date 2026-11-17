"""Screener: European ETFs and large stocks, analysed from a euro investor's point of view.

Prices come from Yahoo Finance via yfinance — free, unofficial, end-of-day. Fine for a personal screener,
not a trading feed. Every series is converted to EUR first, so a US stock and a German ETF are compared
like-for-like (and currency moves show up as part of the return, which is what a euro investor actually gets).

metrics / score / why / explain are pure and unit-tested; fetch / load do the I/O and cache to data/market.json.
"""
import bisect
import json
import math
import os
import threading
import time
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIVERSE = json.load(open(os.path.join(ROOT, "universe.json")))["items"]
# Serverless hosts (Vercel sets VERCEL=1) may not offer a writable project folder: keep caches in /tmp there.
DATA = os.getenv("DATA_DIR") or ("/tmp/fs-data" if os.getenv("VERCEL") else os.path.join(ROOT, "data"))
CACHE = os.path.join(DATA, "market.json")
# PRICE_CACHE=supabase: read the 5-year price file the hourly job uploads to Supabase Storage, instead of
# downloading it from Yahoo on every cold start (slow, and cloud IPs get rate-limited).
REMOTE = os.getenv("PRICE_CACHE") == "supabase"
BUCKET, OBJECT = "cache", "market.json.gz"
TTL = 6 * 3600  # end-of-day data; refreshing more often buys nothing
FX = {"USD": "EURUSD=X", "GBp": "EURGBP=X", "GBP": "EURGBP=X", "CHF": "EURCHF=X", "DKK": "EURDKK=X", "INR": "EURINR=X",
      "SEK": "EURSEK=X", "NOK": "EURNOK=X", "CAD": "EURCAD=X", "JPY": "EURJPY=X", "HKD": "EURHKD=X", "AUD": "EURAUD=X"}
_lock = threading.Lock()


# ---------------------------------------------------------------- data

def to_eur(series: list, ccy: str, fx: list | None) -> list:
    """[[date, price_in_ccy]] → [[date, price_in_EUR]]. fx = [[date, units of ccy per 1 EUR]], forward-filled."""
    if ccy == "EUR":
        return series
    if not fx:
        return []  # can't compare it fairly without the exchange rate — leave it out rather than guess
    fd, fv = [d for d, _ in fx], [v for _, v in fx]
    pence = 100 if ccy == "GBp" else 1  # London quotes in pence
    out = []
    for d, p in series:
        i = bisect.bisect_right(fd, d) - 1
        if i >= 0 and fv[i]:
            out.append([d, p / pence / fv[i]])
    return out


def eur_at(fx: dict, ccy: str, day: str, amount: float) -> float | None:
    """amount in `ccy` on `day` → EUR, using the last known rate on or before that day. None if no rate."""
    if ccy == "EUR":
        return amount
    s = fx.get(FX.get(ccy, ""))
    if not s:
        return None
    i = bisect.bisect_right([d for d, _ in s], day) - 1
    i = i if i >= 0 else 0  # trade older than our FX history: use the earliest rate we have
    return amount / (100 if ccy == "GBp" else 1) / s[i][1] if s[i][1] else None


def fetch() -> dict:
    import yfinance as yf
    fxs = sorted(set(FX.values()))
    df = yf.download([i["t"] for i in UNIVERSE] + fxs, period="5y", interval="1d",
                     auto_adjust=True, progress=False, threads=True)["Close"]  # auto_adjust: dividends reinvested
    raw = {c: [[d.strftime("%Y-%m-%d"), float(v)] for d, v in df[c].dropna().items()] for c in df.columns}
    closes = {}
    for it in UNIVERSE:
        s = raw.get(it["t"]) or []
        closes[it["t"]] = [[d, round(p, 4)] for d, p in to_eur(s, it["ccy"], raw.get(FX.get(it["ccy"], "")))]
    return {"fetched": time.time(), "closes": closes, "fx": {p: raw.get(p, []) for p in fxs}}


_mem: dict | None = None  # parsed copy of the price data: re-parsing 3.5 MB on every API call cost ~60-100 ms each


def _complete(c: dict | None) -> bool:
    return bool(c) and set(FX.values()) <= set(c.get("fx", {})) and {i["t"] for i in UNIVERSE} <= set(c["closes"])


def _fresh(c: dict | None) -> bool:
    return _complete(c) and time.time() - c["fetched"] < TTL


def _from_storage() -> dict | None:
    import gzip
    from . import database
    try:
        return json.loads(gzip.decompress(database.get_client().storage.from_(BUCKET).download(OBJECT)))
    except Exception:
        return None  # not uploaded yet, or Supabase unreachable — callers fall back to Yahoo


def save_to_storage(data: dict) -> int:
    """Upload the price data (gzipped, ~1 MB) for hosted instances to read. Creates the private bucket on first use."""
    import gzip
    from . import database
    store = database.get_client().storage
    if BUCKET not in {b.name for b in store.list_buckets()}:
        store.create_bucket(BUCKET, options={"public": False})
    blob = gzip.compress(json.dumps(data, separators=(",", ":")).encode())
    store.from_(BUCKET).upload(OBJECT, blob, {"content-type": "application/gzip", "upsert": "true"})
    return len(blob)


def load(force: bool = False) -> dict:
    """Price data, freshest available: memory → Supabase Storage (hosted) → local file → Yahoo.
    If every source is stale and Yahoo is down, the last good copy is served rather than an error."""
    global _mem
    with _lock:  # single-flight: two requests on a cold cache must not both download 5 years of prices
        if not force and _fresh(_mem):
            return _mem
        options = [_mem]
        if REMOTE and not force:
            options.append(_from_storage())
        if _mem is None and os.path.exists(CACHE):
            try:
                with open(CACHE) as f:
                    options.append(json.load(f))
            except (OSError, ValueError):
                pass
        best = max((c for c in options if c), key=lambda c: c["fetched"], default=None)
        if not force and _fresh(best):
            _mem = best
            return best
        try:
            data = fetch()
        except Exception:
            if best:
                _mem = best
                return best
            raise
        _mem = data
        try:
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            with open(CACHE, "w") as f:
                json.dump(data, f)
        except OSError:
            pass  # read-only disk (serverless): memory is enough for this instance
        return data


EXTRA = os.path.join(DATA, "extra.json")


KINDS = {"EQUITY": "stock", "ETF": "etf", "MUTUALFUND": "fund"}  # what the terminal covers; indices, crypto, futures are "other"


def extra(tickers: list[str], data: dict) -> dict:
    """EUR closes for symbols outside the screener universe (fetched on demand in parallel, cached with their names)."""
    import yfinance as yf
    from concurrent.futures import ThreadPoolExecutor

    def fetch_one(t):
        try:
            tk = yf.Ticker(t)
            h = tk.history(period="5y", auto_adjust=True)["Close"].dropna()
            ccy = tk.fast_info.get("currency") or "EUR"
            try:
                info = tk.info
                name, kind = info.get("longName") or info.get("shortName") or "", KINDS.get(info.get("quoteType"), "other")
            except Exception:
                name, kind = "", "other"
            s = [[d.strftime("%Y-%m-%d"), float(v)] for d, v in h.items()]
            return t, {"fetched": time.time(), "ccy": ccy, "name": name, "kind": kind,
                       "closes": [[d, round(p, 4)] for d, p in to_eur(s, ccy, data.get("fx", {}).get(FX.get(ccy, "")))]}
        except Exception:
            return t, {"fetched": time.time(), "ccy": None, "name": "", "kind": "other", "closes": []}  # unknown symbol: don't refetch every request

    with _lock:
        cache = json.load(open(EXTRA)) if os.path.exists(EXTRA) else {}
    todo = [t for t in dict.fromkeys(tickers)
            if not (cache.get(t) and time.time() - cache[t]["fetched"] < TTL and "kind" in cache[t])]
    if todo:
        with ThreadPoolExecutor(max_workers=6) as ex:
            got = dict(ex.map(fetch_one, todo))
        with _lock:
            cache = json.load(open(EXTRA)) if os.path.exists(EXTRA) else {}
            cache.update(got)
            try:
                os.makedirs(os.path.dirname(EXTRA), exist_ok=True)
                json.dump(cache, open(EXTRA, "w"))
            except OSError:
                pass  # read-only disk: this request still gets its prices, they just aren't kept
    return {t: cache[t]["closes"] for t in tickers if t in cache}


def lookup(tickers: list[str], data: dict) -> dict:
    """{symbol: {name, closes, verified}} for any Yahoo symbol. Screener tickers are pre-verified; others fetched on demand."""
    uni = {i["t"]: i for i in UNIVERSE}
    out = {t: {"name": uni[t]["name"], "kind": uni[t]["kind"], "ccy": uni[t]["ccy"], "closes": data["closes"].get(t) or [], "verified": True}
           for t in tickers if t in uni}
    rest = [t for t in tickers if t not in uni]
    if rest:
        closes = extra(rest, data)
        with _lock:
            cache = json.load(open(EXTRA)) if os.path.exists(EXTRA) else {}
        out.update({t: {"name": (cache.get(t) or {}).get("name") or "", "kind": (cache.get(t) or {}).get("kind") or "other",
                        "ccy": (cache.get(t) or {}).get("ccy") or "EUR", "closes": closes.get(t) or []} for t in rest})
    return out


# ---------------------------------------------------------------- analysis (pure)

def metrics(series: list) -> dict | None:
    """Everything the screener shows, from one EUR price series [[YYYY-MM-DD, price], ...]."""
    if len(series) < 60:
        return None
    dates, px = [d for d, _ in series], [p for _, p in series]
    last, p = date.fromisoformat(dates[-1]), px[-1]

    def back(days):  # price `days` ago; None if the history doesn't reach that far (10-day grace for holidays)
        d = last - timedelta(days=days)
        if d.isoformat() < dates[0]:
            return px[0] if (date.fromisoformat(dates[0]) - d).days <= 10 else None
        return px[bisect.bisect_right(dates, d.isoformat()) - 1]

    def window(days):
        return px[bisect.bisect_left(dates, (last - timedelta(days=days)).isoformat()):]

    def vol(w):  # annualised standard deviation of daily log returns
        r = [math.log(b / a) for a, b in zip(w, w[1:]) if a > 0 and b > 0]
        if len(r) < 20:
            return None
        m = sum(r) / len(r)
        return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)

    def maxdd(w):  # worst peak-to-trough fall
        peak, worst = w[0], 0.0
        for v in w:
            peak = max(peak, v)
            worst = min(worst, v / peak - 1)
        return worst

    def chg(days):
        b = back(days)
        return p / b - 1 if b else None

    p3, p5 = back(3 * 365), back(5 * 365)
    short = p3 is None
    w1, w3 = window(365), window(3 * 365)
    ytd_i = bisect.bisect_right(dates, f"{last.year - 1}-12-31") - 1
    years = {}
    for y in range(int(dates[0][:4]), last.year + 1):
        a = bisect.bisect_right(dates, f"{y - 1}-12-31") - 1
        b = bisect.bisect_right(dates, f"{y}-12-31") - 1
        if a >= 0 and b > a:
            years[str(y)] = px[b] / px[a] - 1  # calendar-year return (current year = year to date)
    m = {
        "price": p, "asof": dates[-1], "r1d": p / px[-2] - 1,
        "r1m": chg(30), "r3m": chg(91), "r6m": chg(182), "r1y": chg(365),
        "ytd": p / px[ytd_i] - 1 if ytd_i >= 0 else None,
        "cagr3": (p / p3) ** (1 / 3) - 1 if p3 else None,
        "cagr5": (p / p5) ** (1 / 5) - 1 if p5 else None,
        "vol": vol(w1), "vol3": vol(w3) if not short else None,
        "mdd": maxdd(w3 if not short else px),
        "off_high": p / max(w1) - 1,
        "short": short, "years": years,
    }
    growth, risk = (m["cagr3"], m["vol3"]) if not short else (m["r1y"], m["vol"])
    m["growth"] = growth
    m["rpr"] = growth / risk if growth is not None and risk else None
    return m


# The score: how an instrument compares with the others of its kind *in this list* (0–100, percentile-based).
COMPONENTS = [  # key, weight, label for "why" text
    ("rpr", .35, "return for the risk"),
    ("growth", .25, "growth per year"),
    ("mdd", .20, "how small its worst fall was"),
    ("r1y", .20, "the last 12 months"),
]


def score(rows: list[dict]) -> None:
    """Adds row["score"] (0–100) and row["parts"] {key: percentile 0–1} in place. Rank within the same kind."""
    for kind in {r["kind"] for r in rows}:
        grp = [r for r in rows if r["kind"] == kind]
        for r in grp:
            r["parts"] = {}
        for key, _, _ in COMPONENTS:
            vals = sorted(r["m"][key] for r in grp if r["m"].get(key) is not None)
            for r in grp:
                v = r["m"].get(key)
                if v is None or len(vals) < 2:
                    r["parts"][key] = .5  # unknown → neutral, never a hidden penalty
                else:  # share of peers it beats (mdd is negative, so a smaller fall = higher value = better)
                    r["parts"][key] = bisect.bisect_left(vals, v) / (len(vals) - 1)
        for r in grp:
            r["score"] = round(100 * sum(w * r["parts"][k] for k, w, _ in COMPONENTS))


def _pct(x, plus=True):
    return "—" if x is None else (f"{x:+.0%}" if plus else f"{x:.0%}")


def why(r: dict) -> str:
    """One plain-English line: the strongest reason it ranks where it does, and its weakest point."""
    m, parts = r["m"], r["parts"]
    good = {"rpr": "it grew steadily for how much it swings", "growth": f"strong long-run growth ({_pct(m['growth'])} a year)",
            "mdd": f"it held up well in sell-offs (worst fall {_pct(m['mdd'], False)})", "r1y": f"a strong last 12 months ({_pct(m['r1y'])})"}
    bad = {"rpr": "it's a bumpy ride for the return", "growth": f"weak long-run growth ({_pct(m['growth'])} a year)",
           "mdd": f"deep falls ({_pct(m['mdd'], False)} at worst)", "r1y": f"a weak last 12 months ({_pct(m['r1y'])})"}
    top = max(parts, key=parts.get)
    low = min(parts, key=parts.get)
    head = "Ranks high" if r["score"] >= 67 else "Mid-table" if r["score"] >= 34 else "Ranks low"
    if parts[top] < .5:  # nothing it's good at — lead with the weakness
        return f"{head}: {bad[low]}."
    tail = f", but {bad[low]}" if parts[low] < .34 and low != top else ""
    return f"{head}: {good[top]}{tail}."


def tags(m: dict) -> list[str]:
    t = []
    if m["vol"] is not None:
        t.append("Calm" if m["vol"] < .08 else "Bumpy" if m["vol"] > .32 else None)
    t.append("Near its high" if m["off_high"] > -.03 else f"{m['off_high']:.0%} off its high" if m["off_high"] < -.2 else None)
    if m["short"]:
        t.append("Under 3 yrs of data")
    return [x for x in t if x]


def explain(m: dict, ccy: str, kind: str) -> list[dict]:
    """The numbers, each with a sentence a beginner can act on. tone: good | bad | neutral."""
    eur = lambda x: f"€{1000 * (1 + x):,.0f}"
    cards = []
    if m["cagr3"] is not None:
        g = m["cagr3"]
        cards.append({"key": "growth", "label": "Growth per year (3 yrs)", "value": _pct(g, True),
                      "plain": f"€1,000 put in 3 years ago is worth about €{1000 * (1 + g) ** 3:,.0f} today. "
                               "That's the average yearly growth, with dividends reinvested.",
                      "tone": "good" if g >= .07 else "bad" if g < 0 else "neutral"})
    if m["r1y"] is not None:
        cards.append({"key": "r1y", "label": "Last 12 months", "value": _pct(m["r1y"]),
                      "plain": f"€1,000 a year ago → {eur(m['r1y'])} today. One year is a short window: it says what's been "
                               "popular lately, not what will happen next.",
                      "tone": "good" if m["r1y"] > .05 else "bad" if m["r1y"] < 0 else "neutral"})
    if m["vol"] is not None:
        v = m["vol"]
        feel = ("calm — bond-like" if v < .07 else "about as bumpy as the overall stock market" if v < .22
                else "bumpier than the overall market" if v < .35 else "very bumpy — big up and down years are normal")
        cards.append({"key": "vol", "label": "Swing (volatility)", "value": _pct(v, False),
                      "plain": f"In a typical year the price moves around ±{v:.0%}: {feel}. For scale, a broad world-stock fund "
                               "swings about 15%, a government-bond fund about 5%.",
                      "tone": "bad" if v > .35 else "good" if v < .1 else "neutral"})
    d = m["mdd"]
    span = "3 years" if not m["short"] else "the data we have"
    rec = ("It has since recovered to near its high." if m["off_high"] > -.03
           else f"It's still {abs(m['off_high']):.0%} below its 1-year high.")
    cards.append({"key": "mdd", "label": f"Worst fall ({'3 yrs' if not m['short'] else 'available data'})", "value": _pct(d, False),
                  "plain": f"At its worst in {span} it was {abs(d):.0%} below its previous peak: €1,000 would have shrunk to "
                           f"{eur(d)} before recovering. Ask yourself whether you'd hold on through that. {rec}",
                  "tone": "bad" if d < -.3 else "good" if d > -.12 else "neutral"})
    if m["rpr"] is not None:
        q = m["rpr"]
        cards.append({"key": "rpr", "label": "Return for the risk", "value": f"{q:.2f}",
                      "plain": f"For each 1% of yearly swing you got {q:.2f}% of yearly growth. Above 1 is excellent, 0.5–1 is "
                               "decent, below 0.5 means a lot of up-and-down for the reward. (A simplified Sharpe ratio.)",
                      "tone": "good" if q >= 1 else "bad" if q < .5 else "neutral"})
    if ccy != "EUR":
        cards.append({"key": "fx", "label": "Currency", "value": ccy.upper() if ccy != "GBp" else "GBP",
                      "plain": f"It trades in {'British pounds' if ccy in ('GBp', 'GBP') else ccy}. Every number here is converted "
                               "to euros, so part of the gain or loss comes from that currency moving against the euro.",
                      "tone": "neutral"})
    if kind == "fund":
        cards.append({"key": "fee", "label": "Fees (active fund)", "value": "in the returns",
                      "plain": "A manager picks the holdings instead of copying an index, which costs more: often 1–2% a year, "
                               "sometimes plus a performance fee. It's taken out automatically, so the returns above are already "
                               "after fees. The exact costs are in the fund's key information document (KID).",
                      "tone": "neutral"})
    if kind == "etf":
        cards.append({"key": "fee", "label": "Fees (TER)", "value": "in the returns",
                      "plain": "An ETF's yearly fee is taken out of the fund automatically, so the returns above are already "
                               "after fees. Two funds tracking the same index mostly differ by that fee — check it on the "
                               "fund's factsheet before choosing between them.",
                      "tone": "neutral"})
    return cards


# ---------------------------------------------------------------- what the API serves

_screen_memo: tuple | None = None


def screen(data: dict) -> list[dict]:
    """Scored rows, best first. Memoised per price refresh: portfolio, alerts, compare and discover all call this, and
    recomputing 99 instruments' metrics on every request was most of their ~0.6 s. Callers treat the rows as read-only."""
    global _screen_memo
    key = data.get("fetched")  # absent in hand-built test data → never memoise those
    if key is not None and _screen_memo and _screen_memo[0] == (key, len(UNIVERSE)):
        return _screen_memo[1]
    rows = _screen(data)
    if key is not None:
        _screen_memo = ((key, len(UNIVERSE)), rows)
    return rows


def _screen(data: dict) -> list[dict]:
    rows = []
    for it in UNIVERSE:
        m = metrics(data["closes"].get(it["t"]) or [])
        if m:
            rows.append({**it, "m": m})
    score(rows)
    for r in rows:
        r["why"], r["tags"] = why(r), tags(r["m"])
    return sorted(rows, key=lambda r: -r["score"])


def vs_index(r: dict, b: dict) -> dict | None:
    """The question for any active fund: did it beat a cheap index fund of similar companies, like for like?"""
    m, n = r["m"], b["m"]
    f, g, span = (m["cagr3"], n["cagr3"], "a year over 3 years") if not m["short"] else (m["r1y"], n["r1y"], "over the last 12 months")
    if f is None or g is None:
        return None
    d = f - g
    return {"key": "bench", "label": "Vs a cheap index fund", "value": f"{d:+.0%}" + (" /yr" if not m["short"] else ""),
            "plain": f"It grew {f:+.0%} {span}, against {g:+.0%} for {b['name']}, a low-cost index fund holding similar companies. "
                     f"Its worst fall was {abs(m['mdd']):.0%}, against {abs(n['mdd']):.0%}. An active fund costs more every year, "
                     "so it has to beat the index by more than that cost difference to be worth it.",
            "tone": "good" if d > .02 else "bad" if d < 0 else "neutral"}


def correlation(a: list, b: list, days: int = 3 * 365) -> float | None:
    """How closely two EUR price series move together: Pearson r of WEEKLY returns over the last `days`.
    Weekly, not daily: fund NAVs are published a day late and US/European markets close hours apart, which makes
    daily returns line up wrong (BIT's fund vs a world ETF read 0.17 daily, 0.52 weekly)."""
    def weekly(s):
        w = {}
        for d, p in s:
            y, k, _ = date.fromisoformat(d).isocalendar()
            w[(y, k)] = p  # last price of each ISO week
        return w
    if not a or not b:
        return None
    cut = (date.fromisoformat(min(a[-1][0], b[-1][0])) - timedelta(days=days)).isoformat()
    wa, wb = weekly([x for x in a if x[0] >= cut]), weekly([x for x in b if x[0] >= cut])
    ks = sorted(set(wa) & set(wb))
    pairs = [(math.log(wa[y] / wa[x]), math.log(wb[y] / wb[x])) for x, y in zip(ks, ks[1:])
             if min(wa[x], wa[y], wb[x], wb[y]) > 0]
    if len(pairs) < 26:  # half a year of weeks, minimum
        return None
    ma, mb = sum(p[0] for p in pairs) / len(pairs), sum(p[1] for p in pairs) / len(pairs)
    cov = sum((x - ma) * (y - mb) for x, y in pairs)
    va, vb = sum((x - ma) ** 2 for x, _ in pairs), sum((y - mb) ** 2 for _, y in pairs)
    return cov / math.sqrt(va * vb) if va and vb else None


def compare(data: dict, tickers: list[str]) -> dict | None:
    """2-4 instruments side by side, with a plain-English summary and how much each pair moves together."""
    items = [r for r in (resolve(data, t) for t in list(dict.fromkeys(tickers))[:4]) if r]
    if len(items) < 2:
        return None
    name = lambda r: r["name"]
    def best(key, low=False):
        have = [r for r in items if r["m"].get(key) is not None]
        return (min if low else max)(have, key=lambda r: r["m"][key]) if have else None
    span = "a year (3 yrs)" if not any(r["m"]["short"] for r in items) else "(mixed history lengths — treat with care)"
    summary = []
    if (g := best("growth")):
        summary.append(f"Grew the most: {name(g)}, {g['m']['growth']:+.0%} {span}.")
    if (v := best("vol", low=True)):
        summary.append(f"Calmest ride: {name(v)}, typically swinging about ±{v['m']['vol']:.0%} in a year.")
    if (d := best("mdd")):
        summary.append(f"Held up best in sell-offs: {name(d)}, worst fall {d['m']['mdd']:.0%}.")
    if (q := best("rpr")):
        summary.append(f"Most return for the risk: {name(q)} ({q['m']['rpr']:.2f}).")
    pairs = []
    for i, x in enumerate(items):
        for y in items[i + 1:]:
            r = correlation(series_of(data, x), series_of(data, y))
            if r is None:
                continue
            plain = (f"{name(x)} and {name(y)} move almost in lockstep — owning both adds very little spread." if r >= .9 else
                     f"{name(x)} and {name(y)} move together most of the time — some extra spread, not much." if r >= .6 else
                     f"{name(x)} and {name(y)} often move differently — combining them spreads your risk more.")
            pairs.append({"a": x["t"], "b": y["t"], "r": round(r, 2), "plain": plain})
    return {"items": [{k: r[k] for k in ("t", "name", "kind", "group", "ccy", "score", "why", "m")} for r in items],
            "series": {r["t"]: series_of(data, r) for r in items}, "summary": summary, "pairs": pairs}


def xirr(flows: list[tuple[str, float]]) -> float | None:
    """Money-weighted yearly return of dated cash flows (negative = paid in, positive = value out). Bisection."""
    if not flows or not any(v < 0 for _, v in flows) or not any(v > 0 for _, v in flows):
        return None
    d0 = date.fromisoformat(flows[0][0])
    t = [(date.fromisoformat(d) - d0).days / 365 for d, _ in flows]
    npv = lambda r: sum(v / (1 + r) ** ti for (_, v), ti in zip(flows, t))
    lo, hi = -.99, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def savings_plan(series: list, monthly: float, start: str, fee: float = 0.0) -> dict | None:
    """Buy `monthly` EUR (minus `fee`) of fractional units on the first trading day of every month from `start`."""
    s = [x for x in series if x[0] >= start]
    if len(s) < 25:
        return None
    buys, seen = [], set()
    for d, p in s:
        if d[:7] not in seen:  # first trading day of each month
            seen.add(d[:7])
            buys.append((d, p))
    units = paid = 0.0
    timeline, flows, bi = [], [], 0
    worst = (0.0, s[0][0], 0.0, 0.0)  # (value/paid - 1, date, paid, value) at the lowest point
    for d, p in s:
        while bi < len(buys) and buys[bi][0] <= d:
            units += max(monthly - fee, 0) / buys[bi][1]
            paid += monthly
            flows.append((buys[bi][0], -monthly))
            bi += 1
        value = units * p
        if paid and value / paid - 1 < worst[0]:
            worst = (value / paid - 1, d, paid, value)
        if not timeline or timeline[-1][0][:7] != d[:7] or d == s[-1][0]:
            timeline.append([d, round(paid, 2), round(value, 2)])
        else:
            timeline[-1] = [d, round(paid, 2), round(value, 2)]
    last_d, last_p = s[-1]
    value = units * last_p
    return {"start": buys[0][0], "end": last_d, "months": len(buys), "paid": paid, "value": value, "gain": value - paid,
            "gain_pct": value / paid - 1 if paid else None, "units": units, "avg_price": (paid - fee * len(buys)) / units if units else None,
            "price": last_p, "xirr": xirr(flows + [(last_d, value)]), "fees": fee * len(buys),
            "worst": {"pct": worst[0], "date": worst[1], "paid": worst[2], "value": worst[3]}, "timeline": timeline}


def project(value: float, monthly: float, years: int, rate: float) -> float:
    """Future value: today's pot plus the same monthly amount, growing at a steady yearly `rate` (an illustration)."""
    rm, n = (1 + rate) ** (1 / 12) - 1, 12 * years
    return value * (1 + rate) ** years + (monthly * ((1 + rm) ** n - 1) / rm if rm else monthly * n)


def series_of(data: dict, r: dict) -> list:
    return r.get("series") or data["closes"][r["t"]]


def resolve(data: dict, ticker: str) -> dict | None:
    """A scored row for ANY Yahoo symbol. Screener instruments come from the ranked list; anything else is fetched on
    demand and scored against the screener's instruments of the same kind (where it *would* rank). None if unknown,
    not a stock/ETF/fund, in an unsupported currency, or with under 60 days of prices."""
    rows = screen(data)
    hit = next((r for r in rows if r["t"] == ticker), None)
    if hit:
        return hit
    f = lookup([ticker], data).get(ticker) or {}
    m = metrics(f.get("closes") or [])
    if not m or f.get("kind") not in ("stock", "etf", "fund"):
        return None
    peers = [r for r in rows if r["kind"] == f["kind"]]
    parts = {}
    for key, _, _ in COMPONENTS:
        vals = sorted(p["m"][key] for p in peers if p["m"].get(key) is not None)
        parts[key] = bisect.bisect_left(vals, m[key]) / len(vals) if m.get(key) is not None and vals else .5
    r = {"t": ticker, "kind": f["kind"], "group": "All markets", "name": f["name"] or ticker, "ccy": f["ccy"], "m": m, "parts": parts,
         "score": round(100 * sum(w * parts[k] for k, w, _ in COMPONENTS)), "outside": True, "series": f["closes"]}
    r["why"], r["tags"] = why(r), tags(m)
    r["rank"], r["of"] = 1 + sum(p["score"] > r["score"] for p in peers), len(peers)
    return r


def similar(data: dict, r: dict, n: int = 4) -> list[dict]:
    """Screener instruments that move most like this one (weekly correlation ≥ 0.5), each with a plain reason to look."""
    pool = [p for p in screen(data) if p["t"] != r["t"] and (p["kind"] == "stock") == (r["kind"] == "stock")]
    mine, out = series_of(data, r), []
    for p in pool:
        c = correlation(mine, data["closes"][p["t"]])
        if c is not None and c >= .5:
            out.append((c, p))
    res = []
    for c, p in sorted(out, key=lambda x: -x[0])[:n]:
        a, b, notes = r["m"], p["m"], []
        if r["kind"] == "fund" and p["kind"] == "etf":
            notes.append("index fund, usually much lower fees")
        if a.get("vol") and b.get("vol") and b["vol"] < a["vol"] * .85:
            notes.append(f"calmer (swing {b['vol']:.0%} vs {a['vol']:.0%})")
        if a.get("growth") is not None and b.get("growth") is not None and b["growth"] > a["growth"] + .02:
            notes.append(f"grew more ({b['growth']:+.0%} vs {a['growth']:+.0%} a year)")
        if a.get("mdd") is not None and b.get("mdd") is not None and b["mdd"] > a["mdd"] + .05:
            notes.append(f"smaller worst fall ({b['mdd']:.0%} vs {a['mdd']:.0%})")
        res.append({"t": p["t"], "name": p["name"], "kind": p["kind"], "group": p["group"], "score": p["score"], "corr": round(c, 2),
                    "note": "; ".join(notes[:2]) or "similar ride, similar results"})
    return res


def instrument(data: dict, ticker: str) -> dict | None:
    r = resolve(data, ticker)
    if not r:
        return None
    rows = {x["t"]: x for x in screen(data)}
    cards = explain(r["m"], r["ccy"], r["kind"])
    if r.get("bench") in rows and (c := vs_index(r, rows[r["bench"]])):
        cards.insert(0, c)
    if r.get("also"):
        cards.append({"key": "also", "label": "Other listing", "value": "ETF class", "plain": r["also"], "tone": "neutral"})
    out = {**r, "cards": cards, "series": series_of(data, r), "similar": similar(data, r)}
    if not r.get("outside"):
        peers = [x for x in rows.values() if x["kind"] == r["kind"]]
        out["rank"], out["of"] = sorted(peers, key=lambda x: -x["score"]).index(r) + 1, len(peers)
    return out


def matches(q: str, item: dict) -> bool:
    """Every word of the query appears in the instrument's name, ticker, nicknames, group or kind ("bitcap tech fund")."""
    hay = " ".join([item["name"], item["t"], item.get("aka", ""), item["group"], item["kind"],
                    {"etf": "etf index fund", "fund": "active fund", "stock": "stock share company"}[item["kind"]]]).lower()
    words = q.lower().split()
    return bool(words) and all(w in hay for w in words)


def search(q: str, data: dict) -> list[dict]:
    """Screener matches first (with their score), then anything Yahoo knows by that name or symbol."""
    rows = screen(data)
    out = [{"t": r["t"], "name": r["name"], "kind": r["kind"], "where": r["group"], "in_list": True, "score": r["score"]}
           for r in rows if matches(q, r)][:8]
    seen = {o["t"] for o in out}
    try:
        import yfinance as yf
        for x in yf.Search(q, max_results=12).quotes:
            t, kind = x.get("symbol"), KINDS.get(x.get("quoteType"))
            if t and kind and t not in seen:
                seen.add(t)
                out.append({"t": t, "name": x.get("longname") or x.get("shortname") or t, "kind": kind,
                            "where": x.get("exchDisp") or x.get("exchange") or "", "in_list": False, "score": None})
    except Exception:
        pass  # Yahoo unreachable: screener matches are still useful
    return out


if __name__ == "__main__":
    import sys
    if "--refresh-storage" in sys.argv:  # run by the hourly GitHub job
        d = load(force=True)
        print(f"prices: {sum(1 for v in d['closes'].values() if v)} series fetched; uploaded {save_to_storage(d) / 1e6:.2f} MB to Supabase Storage")
