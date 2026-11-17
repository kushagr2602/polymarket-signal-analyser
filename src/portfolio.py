"""Your portfolio: trades in, positions and a plain-English health check out.

Trades live in data/trades.json on this machine only — data/ is gitignored, and server.py refuses portfolio
requests that don't come from localhost. Positions use the average-cost method (what most broker apps show).
German tax uses FIFO, so this is an understanding tool, not a tax tool.
"""
import csv
import io
import json
import os
import re
import uuid
from datetime import date

from . import market

PATH = os.path.join(market.ROOT, "data", "trades.json")
TICKER = re.compile(r"[A-Z0-9][A-Z0-9.&\-]{0,19}")  # & for NSE names like M&M.NS
SIDES = {"buy": "buy", "b": "buy", "kauf": "buy", "purchase": "buy", "sell": "sell", "s": "sell", "verkauf": "sell", "sale": "sell"}
ALIASES = {  # CSV header → field (lower-cased match); covers common English/German broker exports
    "date": ("date", "datum", "trade date", "datetime", "time"),
    "ticker": ("ticker", "symbol", "instrument", "wertpapier", "asset"),
    "side": ("side", "type", "action", "direction", "transaction", "typ", "art"),
    "qty": ("qty", "quantity", "shares", "units", "anzahl", "stück", "stueck"),
    "price": ("price", "kurs", "preis", "unit price", "price per share"),
    "fees": ("fees", "fee", "commission", "gebühr", "gebuehr", "kosten", "costs"),
    "note": ("note", "notes", "comment"),
    "ccy": ("currency", "ccy", "währung", "waehrung"),
}


# ---------------------------------------------------------------- parsing + validation (pure)

def num(x) -> float:
    """'1.234,56' (German) and '1,234.56' (English) both → 1234.56."""
    s = str(x).strip().replace("€", "").replace(" ", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def pdate(x) -> date:
    s = str(x).strip()[:10]
    m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)  # European day-first: 14.03.2025
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    if re.fullmatch(r"\d{8}", s[:8]) and not s[8:9].isdigit():  # IBKR Flex: 20250314
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    return date.fromisoformat(s)


def clean(t: dict) -> dict:
    """One trade, validated. Raises ValueError with a message a person can act on."""
    try:
        d = pdate(t["date"])
    except (ValueError, TypeError, KeyError):
        raise ValueError("Date must look like 2025-03-14 or 14.03.2025.")
    if d > date.today():
        raise ValueError("That date is in the future.")
    tk = str(t.get("ticker", "")).strip().upper()
    if not TICKER.fullmatch(tk):
        raise ValueError(f"'{tk}' doesn't look like a ticker (e.g. VWCE.DE, AAPL).")
    side = SIDES.get(str(t.get("side") or "buy").strip().lower())
    if not side:
        raise ValueError("Side must be buy or sell.")
    try:
        qty, price, fees = num(t["qty"]), num(t["price"]), num(t.get("fees") or 0)
    except (ValueError, TypeError, KeyError):
        raise ValueError("Quantity, price and fees must be numbers.")
    if qty <= 0 or price <= 0 or fees < 0:
        raise ValueError("Quantity and price must be above 0, and fees can't be negative.")
    ccy = str(t.get("ccy") or "EUR").strip()
    ccy = "GBp" if ccy in ("GBp", "GBX") else ccy.upper()
    if ccy not in market.FX and ccy != "EUR":
        raise ValueError(f"Currency {ccy} isn't supported yet (supported: EUR, {', '.join(sorted(set(market.FX) - {'GBp'}))}).")
    return {"id": t.get("id") or uuid.uuid4().hex[:10], "date": d.isoformat(), "ticker": tk, "side": side,
            "qty": qty, "price": price, "fees": fees, "ccy": ccy, "broker": str(t.get("broker") or "manual")[:12],
            "note": str(t.get("note") or "")[:80]}


def parse_csv(text: str) -> tuple[list[dict], list[str]]:
    try:
        dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.DictReader(io.StringIO(text.strip()), dialect=dialect))
    if not rows:
        return [], ["The file is empty."]
    col = {}
    for key, names in ALIASES.items():
        col.update({key: h for h in rows[0] if h and h.strip().lower() in names and key not in col})
    missing = [k for k in ("date", "ticker", "qty", "price") if k not in col]
    if missing:
        return [], [f"Couldn't find the column(s): {', '.join(missing)}. Use the template headers: date,ticker,side,qty,price,fees."]
    out, errs = [], []
    for n, r in enumerate(rows, start=2):  # row 1 is the header
        try:
            raw = {k: r.get(h) for k, h in col.items()}
            q = num(raw["qty"])
            if "side" not in col:  # some exports mark sells with a negative quantity
                raw["side"] = "sell" if q < 0 else "buy"
            raw["qty"] = abs(q)
            out.append(clean(raw))
        except (ValueError, TypeError) as e:
            errs.append(f"Row {n}: {e}")
    return out, errs


# ---------------------------------------------------------------- broker exports
# Formats from public import guides, not official specs — so every parser reads the file's own header row and
# reports what it skipped. Unknown layouts fall back to the generic date/ticker/qty/price importer.

IB_EXCH = {"IBIS": ".DE", "IBIS2": ".DE", "XETRA": ".DE", "FWB": ".F", "FWB2": ".F", "AEB": ".AS", "SBF": ".PA", "ENEXT.BE": ".BR",
           "LSE": ".L", "LSEETF": ".L", "EBS": ".SW", "SWX": ".SW", "BVME": ".MI", "BVME.ETF": ".MI", "BM": ".MC", "SFB": ".ST",
           "CPH": ".CO", "OSE": ".OL", "NSE": ".NS", "TSE": ".TO", "SEHK": ".HK", "ASX": ".AX"}


def _money(x) -> float:
    """'USD 1,234.56' / '€12,50' / '-3.2' → float."""
    return num(re.sub(r"[^\d,.\-]", "", str(x)) or "0")


def _rows(text: str) -> list[dict]:
    try:
        dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return list(csv.DictReader(io.StringIO(text.strip()), dialect=dialect))


def _ib_ticker(sym: str, exch: str | None) -> str:
    return sym.strip().replace(" ", "-") + IB_EXCH.get((exch or "").upper(), "")  # US venues need no suffix; "BRK B" → BRK-B


def _collect(raw_rows, make) -> tuple[list[dict], list[str], int]:
    out, errs, skipped = [], [], 0
    for n, r in raw_rows:
        try:
            t = make(r)
            if t is None:
                skipped += 1  # dividends, top-ups, fees, FX conversions, subtotal rows — not trades
                continue
            out.append(clean(t))
        except (ValueError, TypeError, KeyError) as e:
            errs.append(f"Row {n}: {e}")
    return out, errs, skipped


def _revolut(rows):
    def make(r):
        typ = (r.get("Type") or "").upper()
        side = "buy" if "BUY" in typ else "sell" if "SELL" in typ else None
        if not side:
            return None
        qty, total = abs(num(r["Quantity"])), abs(_money(r.get("Total Amount") or 0))
        price = total / qty if total and qty else _money(r["Price per share"])  # the shown price can be rounded
        return {"date": r["Date"], "ticker": r["Ticker"], "side": side, "qty": qty, "price": price,
                "ccy": r.get("Currency") or "USD", "broker": "revolut"}
    return _collect(enumerate(rows, start=2), make)


def _zerodha(rows):
    def make(r):
        sym = r.get("symbol") or r.get("tradingsymbol")
        if (r.get("segment") or "EQ").upper() not in ("EQ", ""):
            return None  # futures/options aren't holdings
        exch = (r.get("exchange") or "NSE").upper()
        return {"date": r["trade_date"], "ticker": f"{sym}.{'BO' if exch == 'BSE' else 'NS'}", "side": r["trade_type"],
                "qty": r["quantity"], "price": r["price"], "ccy": "INR", "broker": "zerodha"}
    return _collect(enumerate(rows, start=2), make)


def _ibkr_flex(rows):
    def make(r):
        if (r.get("AssetClass") or "STK").upper() not in ("STK", "ETF", ""):
            return None
        q = num(r["Quantity"])
        side = (r.get("Buy/Sell") or ("SELL" if q < 0 else "BUY")).lower()
        return {"date": r.get("TradeDate") or r.get("DateTime"), "ticker": _ib_ticker(r["Symbol"], r.get("ListingExchange")),
                "side": side, "qty": abs(q), "price": r["TradePrice"], "fees": abs(num(r.get("IBCommission") or 0)),
                "ccy": r.get("CurrencyPrimary") or r.get("Currency") or "USD", "broker": "ibkr"}
    return _collect(enumerate(rows, start=2), make)


def _ibkr_statement(text):
    """Activity Statement: many sections in one file; column 2 says Header or Data."""
    hdr, sec = {}, {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) > 2 and row[1] == "Header":
            hdr[row[0]] = row[2:]
        elif len(row) > 2 and row[1] == "Data" and row[0] in hdr:
            sec.setdefault(row[0], []).append(dict(zip(hdr[row[0]], row[2:])))
    exch = {r.get("Symbol"): r.get("Listing Exch") for r in sec.get("Financial Instrument Information", [])}

    def make(r):
        if r.get("DataDiscriminator", "Order") not in ("Order", "Trade") or r.get("Asset Category", "Stocks") != "Stocks":
            return None  # SubTotal/Total rows, forex conversions, options
        q = num(r["Quantity"])
        return {"date": r["Date/Time"], "ticker": _ib_ticker(r["Symbol"], exch.get(r["Symbol"])), "side": "sell" if q < 0 else "buy",
                "qty": abs(q), "price": r["T. Price"], "fees": abs(num(r.get("Comm/Fee") or 0)), "ccy": r.get("Currency") or "USD",
                "broker": "ibkr"}
    return _collect(enumerate(sec.get("Trades", []), start=1), make)


def parse_import(text: str) -> tuple[list[dict], list[str], str, int]:
    """Any supported export → (trades, errors, format name, rows skipped as non-trades)."""
    if re.search(r"^Trades,Header,", text, re.M):
        t, e, k = _ibkr_statement(text)
        return t, e, "Interactive Brokers activity statement", k
    rows = _rows(text)
    if not rows:
        return [], ["The file is empty."], "", 0
    h = {k.strip().lower() for k in rows[0] if k}
    if {"ticker", "type", "quantity", "price per share"} <= h:
        t, e, k = _revolut([{kk.strip(): v for kk, v in r.items() if kk} for r in rows])
        return t, e, "Revolut statement", k
    if "trade_type" in h and h & {"symbol", "tradingsymbol"}:
        t, e, k = _zerodha([{kk.strip().lower(): v for kk, v in r.items() if kk} for r in rows])
        return t, e, "Zerodha tradebook", k
    if {"symbol", "tradeprice"} <= h:
        t, e, k = _ibkr_flex([{kk.strip(): v for kk, v in r.items() if kk} for r in rows])
        return t, e, "Interactive Brokers Flex query", k
    t, e = parse_csv(text)
    return t, e, "CSV", 0


def to_eur(trades: list[dict], fx: dict) -> tuple[list[dict], set[str]]:
    """Trade prices/fees → EUR at each trade's own date. Returns (converted, currencies we had no rate for)."""
    out, missing = [], set()
    for t in trades:
        ccy = t.get("ccy", "EUR")
        p, f = market.eur_at(fx, ccy, t["date"], t["price"]), market.eur_at(fx, ccy, t["date"], t["fees"])
        if p is None:
            missing.add(ccy)
            continue
        out.append({**t, "price": p, "fees": f or 0})
    return out, missing


def positions(trades: list[dict]) -> dict[str, dict]:
    """Average-cost positions. Raises ValueError if a sell exceeds what was held at that date."""
    pos = {}
    for t in sorted(trades, key=lambda t: t["date"]):  # stable: same-day trades keep their entry order
        p = pos.setdefault(t["ticker"], {"qty": 0.0, "cost": 0.0, "realized": 0.0, "fees": 0.0})
        p["fees"] += t["fees"]
        if t["side"] == "buy":
            p["qty"] += t["qty"]
            p["cost"] += t["qty"] * t["price"] + t["fees"]
        else:
            if t["qty"] > p["qty"] + 1e-9:
                raise ValueError(f"On {t['date']} you sell {t['qty']:g} {t['ticker']} but only hold {p['qty']:g} at that point.")
            avg = p["cost"] / p["qty"]
            p["realized"] += t["qty"] * (t["price"] - avg) - t["fees"]
            p["cost"] -= avg * t["qty"]
            p["qty"] -= t["qty"]
    return pos


def mix_series(held: dict[str, float], closes: dict[str, list]) -> list:
    """What today's quantities would have been worth on each past day (forward-filled across exchange holidays)."""
    series = {t: closes[t] for t in held if closes.get(t)}
    if not series:
        return []
    start = max(s[0][0] for s in series.values())  # from the first day every holding has a price
    dates = sorted({d for s in series.values() for d, _ in s if d >= start})
    idx, last, out = {t: 0 for t in series}, {}, []
    for d in dates:
        for t, s in series.items():
            while idx[t] < len(s) and s[idx[t]][0] <= d:
                last[t] = s[idx[t]][1]
                idx[t] += 1
        if len(last) == len(series):
            out.append([d, sum(held[t] * last[t] for t in series)])
    return out


def notes(hold: list[dict], mix: dict | None) -> list[dict]:
    """Plain-English observations about the mix. Educational, never 'buy X'. kind: warn | info."""
    out, val = [], [h for h in hold if h["weight"] is not None]
    stocks = [h for h in val if h["kind"] == "stock"]
    etfs = [h for h in val if h["kind"] == "etf"]
    for h in stocks:
        if h["weight"] > .2:
            out.append({"kind": "warn", "text": f"{h['name']} is {h['weight']:.0%} of your portfolio. One company having a bad year "
                        "would hit your whole portfolio hard; many long-term investors keep any single stock to around 5–10%."})
    sw = sum(h["weight"] for h in stocks)
    if sw > .5 and len(val) > 1:
        out.append({"kind": "warn", "text": f"{sw:.0%} of your money is in individual companies rather than funds, so your result "
                    "depends heavily on a handful of businesses."})
    if stocks and not etfs and len(stocks) <= 5:
        out.append({"kind": "info", "text": f"You hold {len(stocks)} compan{'y' if len(stocks) == 1 else 'ies'} and no funds. "
                    "One world ETF spreads money over thousands of companies in a single purchase — compare a few in the screener."})
    by_group = {}
    for h in etfs:
        by_group.setdefault(h["group"], []).append(h)
    for g, hs in by_group.items():
        if len(hs) > 1 and g in ("World", "US", "Europe", "Emerging", "Tech"):
            names = " and ".join(h["name"] for h in hs[:2])
            out.append({"kind": "info", "text": f"{names} both track {g if g != 'US' else 'large US'} companies, so they largely "
                        "overlap — holding both adds little extra spread."})
    if by_group.get("World") and (by_group.get("US") or by_group.get("Tech")):
        out.append({"kind": "info", "text": "World funds are already roughly 70% US companies, so with a US or tech fund on top "
                    "your US share is higher than it looks."})
    if val and not any(h["group"] in ("Bonds", "Gold") for h in val) and mix and mix.get("mdd") is not None:
        out.append({"kind": "info", "text": f"Everything you hold is shares, so it tends to fall together in a crash — today's mix "
                    f"fell {abs(mix['mdd']):.0%} at its worst in the period we can measure. Normal for long-term investing, "
                    "as long as you won't need the money during a dip."})
    for h in hold:
        if h["price"] is None:
            out.append({"kind": "warn", "text": f"Couldn't find prices for {h['ticker']}. Check the ticker — European listings "
                        "need an exchange suffix, e.g. VWCE.DE (Xetra) or ASML.AS (Amsterdam)."})
    return out


def analyse(trades: list[dict], data: dict, rows: list[dict]) -> dict:
    meta = {r["t"]: r for r in rows}
    eur_trades, no_fx = to_eur(trades, data.get("fx", {}))
    pos = positions(eur_trades)
    held = {t: p for t, p in pos.items() if p["qty"] > 1e-9}
    closes = dict(data["closes"])
    missing = [t for t in held if not closes.get(t)]
    found = market.lookup(missing, data) if missing else {}
    closes.update({t: f["closes"] for t, f in found.items()})
    hold = []
    for t, p in held.items():
        s, r = closes.get(t) or [], meta.get(t) or {k: v for k, v in (found.get(t) or {}).items() if k in ("name", "kind") and v and v != "other"}
        price = s[-1][1] if s else None
        value = p["qty"] * price if price else None
        hold.append({"ticker": t, "name": r.get("name") or t, "group": r.get("group") or "Other", "kind": r.get("kind") or "stock",
                     "qty": p["qty"], "avg": p["cost"] / p["qty"], "cost": p["cost"], "price": price, "value": value,
                     "pnl": value - p["cost"] if value is not None else None,
                     "pnl_pct": value / p["cost"] - 1 if value is not None and p["cost"] else None,
                     "r1d": s[-1][1] / s[-2][1] - 1 if len(s) > 1 else None,
                     "score": r.get("score"), "screened": t in meta})
    total = sum(h["value"] for h in hold if h["value"] is not None)
    for h in hold:
        h["weight"] = h["value"] / total if total and h["value"] is not None else None
    hold.sort(key=lambda h: -(h["value"] or 0))
    cost = sum(h["cost"] for h in hold if h["value"] is not None)
    mix = market.metrics(mix_series({h["ticker"]: h["qty"] for h in hold if h["price"]}, closes))
    alloc = {}
    for key in ("group", "kind"):
        a = {}
        for h in hold:
            if h["weight"]:
                a[h[key]] = a.get(h[key], 0) + h["weight"]
        alloc[key] = sorted(a.items(), key=lambda kv: -kv[1])
    return {
        "trades": sorted(trades, key=lambda t: t["date"], reverse=True), "holdings": hold, "alloc": alloc,
        "totals": {"value": total, "cost": cost, "pnl": total - cost, "pnl_pct": total / cost - 1 if cost else None,
                   "realized": sum(p["realized"] for p in pos.values()), "fees": sum(p["fees"] for p in pos.values()),
                   "n": len(hold), "day": sum(h["value"] * h["r1d"] / (1 + h["r1d"]) for h in hold if h["value"] and h["r1d"] is not None)},
        "mix": mix and {k: mix[k] for k in ("growth", "cagr3", "r1y", "vol", "mdd", "rpr", "short", "years")},
        "mix_cards": [c for c in market.explain(mix, "EUR", "mix") if c["key"] not in ("fee", "fx")] if mix else [],
        "notes": notes(hold, mix) + [{"kind": "warn", "text": f"Trades in {c} were left out: no {c}→EUR exchange rate available yet."}
                                     for c in sorted(no_fx)],
    }


# ---------------------------------------------------------------- storage

def load() -> list[dict]:
    return json.load(open(PATH)) if os.path.exists(PATH) else []


def save(trades: list[dict]) -> None:
    positions(trades)  # refuse to store an impossible history (selling more than you held); quantities don't depend on currency
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(trades, f, indent=1)
    os.replace(tmp, PATH)  # atomic: a crash mid-write never corrupts your trade history
