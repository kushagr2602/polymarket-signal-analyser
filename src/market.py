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
CACHE = os.path.join(ROOT, "data", "market.json")
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


def load(force: bool = False) -> dict:
    """Cached closes; refetch when stale. If Yahoo is down, keep serving the last good copy."""
    with _lock:  # single-flight: two requests on a cold cache must not both download 5 years of prices
        cached = None
        if os.path.exists(CACHE):
            with open(CACHE) as f:
                cached = json.load(f)
            if not force and time.time() - cached["fetched"] < TTL and set(FX.values()) <= set(cached.get("fx", {})):
                return cached
        try:
            data = fetch()
        except Exception:
            if cached:
                return cached
            raise
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w") as f:
            json.dump(data, f)
        return data


EXTRA = os.path.join(ROOT, "data", "extra.json")


def extra(tickers: list[str], data: dict) -> dict:
    """EUR closes for holdings outside the screener universe (fetched on demand, cached like the rest)."""
    import yfinance as yf
    with _lock:
        cache = json.load(open(EXTRA)) if os.path.exists(EXTRA) else {}
        changed = False
        for t in tickers:
            hit = cache.get(t)
            if hit and time.time() - hit["fetched"] < TTL:
                continue
            try:
                tk = yf.Ticker(t)
                h = tk.history(period="5y", auto_adjust=True)["Close"].dropna()
                ccy = tk.fast_info.get("currency") or "EUR"
                s = [[d.strftime("%Y-%m-%d"), float(v)] for d, v in h.items()]
                cache[t] = {"fetched": time.time(), "ccy": ccy,
                            "closes": [[d, round(p, 4)] for d, p in to_eur(s, ccy, data.get("fx", {}).get(FX.get(ccy, "")))]}
            except Exception:
                cache[t] = {"fetched": time.time(), "ccy": None, "closes": []}  # unknown ticker — don't refetch every request
            changed = True
        if changed:
            os.makedirs(os.path.dirname(EXTRA), exist_ok=True)
            json.dump(cache, open(EXTRA, "w"))
        return {t: cache[t]["closes"] for t in tickers if t in cache}


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
    if kind == "etf":
        cards.append({"key": "fee", "label": "Fees (TER)", "value": "in the returns",
                      "plain": "An ETF's yearly fee is taken out of the fund automatically, so the returns above are already "
                               "after fees. Two funds tracking the same index mostly differ by that fee — check it on the "
                               "fund's factsheet before choosing between them.",
                      "tone": "neutral"})
    return cards


# ---------------------------------------------------------------- what the API serves

def screen(data: dict) -> list[dict]:
    rows = []
    for it in UNIVERSE:
        m = metrics(data["closes"].get(it["t"]) or [])
        if m:
            rows.append({**it, "m": m})
    score(rows)
    for r in rows:
        r["why"], r["tags"] = why(r), tags(r["m"])
    return sorted(rows, key=lambda r: -r["score"])


def instrument(data: dict, ticker: str) -> dict | None:
    rows = {r["t"]: r for r in screen(data)}
    r = rows.get(ticker)
    if not r:
        return None
    peers = [x for x in rows.values() if x["kind"] == r["kind"]]
    return {**r, "cards": explain(r["m"], r["ccy"], r["kind"]), "series": data["closes"][ticker],
            "rank": sorted(peers, key=lambda x: -x["score"]).index(r) + 1, "of": len(peers)}
