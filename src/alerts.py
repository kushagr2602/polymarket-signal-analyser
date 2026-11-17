"""Price alerts, checked against end-of-day EUR prices. Stored in data/alerts.json on this machine only.

Kinds:  drop  — falls `value`% below its 1-year high      below / above — EUR price crosses `value`
        move  — moves `value`% or more in a single day
evaluate() is pure and unit-tested; the server only loads, saves and calls it.
"""
import bisect
import json
import os
import uuid
from datetime import date, timedelta

from . import market

PATH = os.path.join(market.ROOT, "data", "alerts.json")
KINDS = {"drop": "falls % below its 1-year high", "below": "price falls below €", "above": "price rises above €", "move": "moves % in one day"}


def clean(a: dict, known: set[str]) -> dict:
    t = str(a.get("ticker", "")).strip().upper()
    if t not in known:
        raise ValueError(f"Couldn't find price data for {t or 'that symbol'}.")
    kind = a.get("kind")
    if kind not in KINDS:
        raise ValueError("Pick an alert type.")
    try:
        v = float(str(a.get("value")).replace(",", "."))
    except ValueError:
        raise ValueError("The alert needs a number.")
    if kind in ("drop", "move") and not 1 <= v <= 90:
        raise ValueError("Use a percentage between 1 and 90.")
    if kind in ("below", "above") and v <= 0:
        raise ValueError("The price must be above 0.")
    return {"id": a.get("id") or uuid.uuid4().hex[:10], "ticker": t, "kind": kind, "value": v,
            "created": a.get("created") or date.today().isoformat()}


def _state(kind: str, v: float, series: list, i: int, yr_start: int) -> tuple[bool, float]:
    """(condition true on day i, the measured number) — drop: % off the trailing 1-year high, move: day change."""
    p = series[i][1]
    if kind == "drop":
        off = p / max(x[1] for x in series[yr_start:i + 1]) - 1
        return off <= -v / 100, off
    if kind == "move":
        ch = p / series[i - 1][1] - 1 if i else 0.0
        return abs(ch) >= v / 100, ch
    return (p < v, p) if kind == "below" else (p > v, p)


def evaluate(alerts: list[dict], closes: dict, names: dict) -> list[dict]:
    """Each alert with: triggered now?, first day it fired since it was created, and a plain-English line."""
    out = []
    for a in alerts:
        s = closes.get(a["ticker"]) or []
        nm = names.get(a["ticker"], a["ticker"])
        if len(s) < 2:
            out.append({**a, "triggered": False, "first": None, "now": None, "text": f"No prices for {nm} yet."})
            continue
        dates = [d for d, _ in s]
        first, start = None, bisect.bisect_left(dates, a["created"])
        yr = lambda i: bisect.bisect_left(dates, (date.fromisoformat(dates[i]) - timedelta(days=365)).isoformat())
        for i in range(max(start, 1), len(s)):
            if _state(a["kind"], a["value"], s, i, yr(i))[0]:
                first = dates[i]
                break
        hit, now = _state(a["kind"], a["value"], s, len(s) - 1, yr(len(s) - 1))
        v = a["value"]
        if a["kind"] == "drop":
            text = (f"{nm} is {abs(now):.0%} below its 1-year high — past your {v:g}% line." if hit else
                    f"{nm} is {abs(now):.1%} below its 1-year high. You'll hear at {v:g}%.")
        elif a["kind"] == "move":
            text = (f"{nm} moved {now:+.1%} on the last trading day — at least your {v:g}% line." if hit else
                    f"{nm} moved {now:+.1%} on the last trading day. You'll hear at ±{v:g}%.")
        else:
            word = "below" if a["kind"] == "below" else "above"
            text = (f"{nm} is at €{now:,.2f}, {word} your €{v:,.2f} line." if hit else
                    f"{nm} is at €{now:,.2f}. You'll hear when it goes {word} €{v:,.2f}.")
        if first and not hit:
            text += f" (It crossed on {first}, then came back.)"
        out.append({**a, "triggered": hit, "first": first, "now": now, "asof": dates[-1], "text": text})
    return sorted(out, key=lambda x: (not x["triggered"], x["ticker"]))


def load() -> list[dict]:
    return json.load(open(PATH)) if os.path.exists(PATH) else []


def save(alerts: list[dict]) -> None:
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(alerts, f, indent=1)
    os.replace(tmp, PATH)
