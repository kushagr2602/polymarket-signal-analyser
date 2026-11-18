"""View-models: raw signal rows → what the dashboard renders. Pure functions, no I/O (unit-tested)."""
import math
from datetime import datetime, timedelta, timezone


def tier(score: int) -> str:
    return ("Direct catalyst" if score >= 8 else "Sector impact" if score >= 5
            else "Macro signal" if score >= 3 else "Weak")


def to_rows(sig: list[dict], now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    out = []
    for s in sig:
        m = s.get("markets") or {}
        days = None
        if m.get("expiry_date"):
            try:
                days = (datetime.fromisoformat(m["expiry_date"].replace("Z", "+00:00")) - now).days
            except ValueError:
                pass
        out.append({
            "id": s.get("market_id"), "score": s["relevance_score"], "market": m.get("question", ""),
            "sector": s.get("sector") or "—", "tickers": s.get("affected_tickers") or [],
            "prob": m.get("probability"), "volume": m.get("volume_usd") or 0, "days": days,
            "tier": tier(s["relevance_score"]), "reasoning": s.get("reasoning", ""),
            "impact": s.get("impact") or 0, "angle": s.get("angle") or "",
        })
    return out


BIG = 7  # impact at which a market counts as a big bet


def big_bets(rows: list[dict], n: int = 8) -> list[dict]:
    """The most market-moving live bets, watchlist or not: highest impact, then most money behind them."""
    live = (r for r in rows if r["impact"] >= BIG and r["prob"] is not None and .02 <= r["prob"] <= .98)  # settled odds aren't bets
    return sorted(live, key=lambda r: (-r["impact"], -r["volume"]))[:n]


def kpis(rows: list[dict], n_markets: int) -> dict:
    active = [r for r in rows if r["score"] >= 5]
    return {"markets": n_markets, "active": len(active),
            "high": sum(r["score"] >= 8 for r in rows),
            "volume": sum(r["volume"] for r in active),
            "avg": round(sum(r["score"] for r in active) / len(active), 1) if active else 0}


def exposure(rows: list[dict], tickers: dict) -> list[dict]:
    """Per watchlist ticker: how many live signals mention it, and the strongest one."""
    active = [r for r in rows if r["score"] >= 5]
    out = []
    for t, desc in tickers.items():
        hit = [r for r in active if t in r["tickers"]]
        out.append({"ticker": t, "desc": desc, "n": len(hit), "peak": max((r["score"] for r in hit), default=0)})
    return out


def sector_weights(rows: list[dict]) -> dict[str, dict]:
    """Raw heat per sector: Σ (conviction − 4) × log10(volume) over active signals, plus counts. Not normalised,
    so two snapshots can be compared (the 0–100 heat is re-scaled every time and can't show change)."""
    out = {}
    for r in rows:
        if r["score"] >= 5 and r["sector"] != "—":
            g = out.setdefault(r["sector"], {"w": 0.0, "n": 0, "volume": 0.0, "peak": 0})
            g["w"] += (r["score"] - 4) * math.log10(max(r["volume"], 0) + 10)
            g["n"] += 1
            g["volume"] += r["volume"]
            g["peak"] = max(g["peak"], r["score"])
    return out


def hot_topics(rows: list[dict], n: int = 6) -> list[dict]:
    """Rank sectors by heat (see sector_weights), scaled so the top sector is 100. Current concentration only;
    trends() compares against saved snapshots."""
    weights = sector_weights(rows)
    out = []
    for sec, wt in weights.items():
        sub = [r for r in rows if r["score"] >= 5 and r["sector"] == sec]
        lead = max(sub, key=lambda r: (r["score"], r["volume"]))
        days = [r["days"] for r in sub if r["days"] is not None and r["days"] >= 0]
        out.append({"sector": sec, "n": wt["n"], "volume": wt["volume"], "peak": wt["peak"], "lead": lead["market"],
                    "tickers": sorted({t for r in sub for t in r["tickers"]})[:4],
                    "soon": min(days) if days else None, "w": wt["w"]})
    top = max((o["w"] for o in out), default=0)
    for o in out:
        o["heat"] = round(100 * o.pop("w") / top)
    return sorted(out, key=lambda o: -o["heat"])[:n]


def snapshot(rows: list[dict]) -> dict:
    """What the scanner saves after a scan: raw sector heat and the odds of every active market."""
    return {"sectors": [{"sector": s, **{k: round(v, 3) if isinstance(v, float) else v for k, v in w.items()}}
                        for s, w in sector_weights(rows).items()],
            "markets": {r["id"]: [r["prob"], round(r["volume"])] for r in rows if (r["score"] >= 5 or r.get("impact", 0) >= BIG) and r.get("id") and r["prob"] is not None}}


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def trends(snaps: list[dict], rows: list[dict], now: datetime | None = None) -> dict:
    """Per sector: heat change vs ~a week ago (or the oldest snapshot older than a day) + a sparkline.
    Movers: active markets whose yes-probability moved most since ~a day ago."""
    now = now or datetime.now(timezone.utc)
    snaps = sorted(snaps, key=lambda s: s["taken_at"])
    live = sector_weights(rows)
    sectors = {}
    for sec, wt in live.items():
        hist = [(s["taken_at"], next((x["w"] for x in s["sectors"] if x["sector"] == sec), 0.0)) for s in snaps]
        older = [(t, w) for t, w in hist if now - _ts(t) >= timedelta(hours=20)]
        week = [(t, w) for t, w in older if now - _ts(t) >= timedelta(days=6, hours=12)]
        base = (week or older)[-1] if (week or older) else None
        sectors[sec] = {"spark": [round(w, 2) for _, w in hist[-30:]] + [round(wt["w"], 2)],
                        "change": (wt["w"] / base[1] - 1) if base and base[1] else None,
                        "vs_days": round((now - _ts(base[0])).total_seconds() / 86400) if base else None}
    day_ago = [s for s in snaps if now - _ts(s["taken_at"]) >= timedelta(hours=20)]
    movers = []
    if day_ago:
        ref = day_ago[-1]
        for r in rows:
            was = (ref["markets"].get(r.get("id")) or [None])[0]
            if (r["score"] >= 5 or r.get("impact", 0) >= BIG) and r["prob"] is not None and was is not None and abs(r["prob"] - was) >= .03:
                movers.append({"id": r.get("id"), "market": r["market"], "tickers": r["tickers"], "score": r["score"], "from": was, "to": r["prob"],
                               "delta": r["prob"] - was})
        movers.sort(key=lambda m: -abs(m["delta"]))
    return {"sectors": sectors, "movers": movers[:8], "since": day_ago[-1]["taken_at"] if day_ago else None, "snapshots": len(snaps)}
