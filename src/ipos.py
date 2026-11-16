"""IPO tracker: upcoming listings from Finnhub's documented IPO calendar (your own free key, FINNHUB_API_KEY),
plus a private watch list for IPOs you hear about elsewhere (India, Europe) stored in data/ipo_watch.json.

No scraping: exchanges' websites aren't APIs. normalize / describe / clean_watch are pure and unit-tested.
"""
import json
import os
import uuid
from datetime import date, timedelta

from . import market

WATCH = os.path.join(market.ROOT, "data", "ipo_watch.json")
API = "https://finnhub.io/api/v1/calendar/ipo"


def fetch(days_back: int = 14, days_ahead: int = 90) -> list[dict]:
    import requests
    key = os.getenv("FINNHUB_API_KEY")
    if not key:
        raise LookupError("no key")
    today = date.today()
    r = requests.get(API, params={"from": (today - timedelta(days=days_back)).isoformat(),
                                  "to": (today + timedelta(days=days_ahead)).isoformat(), "token": key}, timeout=15)
    r.raise_for_status()
    return normalize(r.json(), today)


def _money(v) -> str:
    v = float(v or 0)
    return f"${v / 1e9:.1f}B" if v >= 1e9 else f"${v / 1e6:.0f}M" if v >= 1e6 else f"${v:,.0f}" if v else ""


def describe(i: dict, today: date) -> str:
    """One plain sentence a beginner can read."""
    when = date.fromisoformat(i["date"]) if i.get("date") else None
    d = f"{when.day} {when.strftime('%b')}" if when else "a date not set yet"
    price = f" at ${i['price'].replace('-', '–$')} a share" if i.get("price") else ""
    raise_ = f", raising about {_money(i['value'])}" if i.get("value") else ""
    venue = f" on {i['exchange']}" if i.get("exchange") else ""
    if i["status"] == "priced" or (when and when <= today and i["status"] != "filed"):
        return f"Listed{venue} on {d}{price}{raise_}. It now trades like any stock, so first-weeks swings can be large."
    if i["status"] == "filed":
        return f"Has filed to go public{venue}; no date or price set yet{raise_}."
    return f"Expected to list{venue} on {d}{price}{raise_}."


def normalize(raw: dict, today: date) -> list[dict]:
    """Finnhub's ipoCalendar → sorted rows: upcoming first (soonest first), then recently listed. Withdrawn dropped."""
    out = []
    for x in (raw or {}).get("ipoCalendar") or []:
        status = (x.get("status") or "").lower()
        if status == "withdrawn" or not x.get("name"):
            continue
        i = {"date": x.get("date") or None, "name": x["name"].strip(), "symbol": x.get("symbol") or "",
             "exchange": x.get("exchange") or "", "price": str(x.get("price") or "").strip(),
             "shares": x.get("numberOfShares"), "value": x.get("totalSharesValue"), "status": status or "expected"}
        i["upcoming"] = i["status"] in ("expected", "filed") and (not i["date"] or i["date"] >= today.isoformat())
        i["text"] = describe(i, today)
        out.append(i)
    up = sorted((i for i in out if i["upcoming"]), key=lambda i: i["date"] or "9999")       # soonest first, undated last
    done = sorted((i for i in out if not i["upcoming"]), key=lambda i: i["date"] or "", reverse=True)  # newest first
    return up + done


def clean_watch(w: dict) -> dict:
    name = str(w.get("name") or "").strip()
    if not 2 <= len(name) <= 80:
        raise ValueError("Give the company a name (2–80 characters).")
    d = str(w.get("date") or "").strip()
    if d:
        try:
            date.fromisoformat(d)
        except ValueError:
            raise ValueError("Date must look like 2026-12-04, or leave it empty.")
    link = str(w.get("link") or "").strip()
    if link and not link.startswith(("https://", "http://")):
        raise ValueError("The link must start with https://")
    return {"id": w.get("id") or uuid.uuid4().hex[:10], "name": name, "date": d or None,
            "exchange": str(w.get("exchange") or "").strip()[:30], "note": str(w.get("note") or "").strip()[:200], "link": link[:300]}


def load_watch() -> list[dict]:
    return json.load(open(WATCH)) if os.path.exists(WATCH) else []


def save_watch(items: list[dict]) -> None:
    os.makedirs(os.path.dirname(WATCH), exist_ok=True)
    tmp = WATCH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(items, f, indent=1)
    os.replace(tmp, WATCH)
