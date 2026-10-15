"""View-models: raw signal rows → what the dashboard renders. Pure functions, no I/O (unit-tested)."""
import math
from datetime import datetime, timezone


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
            "score": s["relevance_score"], "market": m.get("question", ""),
            "sector": s.get("sector") or "—", "tickers": s.get("affected_tickers") or [],
            "prob": m.get("probability"), "volume": m.get("volume_usd") or 0, "days": days,
            "tier": tier(s["relevance_score"]), "reasoning": s.get("reasoning", ""),
        })
    return out


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


def hot_topics(rows: list[dict], n: int = 6) -> list[dict]:
    """Rank sectors by heat = Σ (conviction − 4) × log10(volume) over active signals, scaled so the
    top sector is 100. Current concentration only — the schema keeps no history, so this is not
    week-over-week momentum."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        if r["score"] >= 5 and r["sector"] != "—":
            groups.setdefault(r["sector"], []).append(r)
    out = []
    for sec, sub in groups.items():
        lead = max(sub, key=lambda r: (r["score"], r["volume"]))
        days = [r["days"] for r in sub if r["days"] is not None and r["days"] >= 0]
        out.append({"sector": sec, "n": len(sub), "volume": sum(r["volume"] for r in sub),
                    "peak": max(r["score"] for r in sub), "lead": lead["market"],
                    "tickers": sorted({t for r in sub for t in r["tickers"]})[:4],
                    "soon": min(days) if days else None,
                    "w": sum((r["score"] - 4) * math.log10(max(r["volume"], 0) + 10) for r in sub)})
    top = max((o["w"] for o in out), default=0)
    for o in out:
        o["heat"] = round(100 * o.pop("w") / top)
    return sorted(out, key=lambda o: -o["heat"])[:n]
