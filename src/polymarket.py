import json
import requests
from datetime import datetime, timezone

GAMMA_API = "https://gamma-api.polymarket.com"
PAGE = 100  # Gamma caps each request at 100


def _is_expired(m: dict, now=None) -> bool:
    """True if the market's resolution date is already in the past. Pure — testable offline.
    Polymarket returns settled-but-not-closed markets as active; those are dead signals."""
    end = m.get("endDate")
    if not end:
        return False
    now = now or datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(end.replace("Z", "+00:00")) < now
    except Exception:
        return False


def _to_record(m: dict) -> dict:
    """Map one raw Gamma market to our schema. Pure — unit-testable offline."""
    prices = m.get("outcomePrices", "[]")
    if isinstance(prices, str):
        prices = json.loads(prices)
    return {
        "market_id": m["id"],
        "question": m.get("question", ""),
        "category": m.get("category", ""),
        "probability": float(prices[0]) if prices else 0.5,  # first outcome = Yes
        "volume_usd": float(m.get("volumeNum") or m.get("volume") or 0),
        "expiry_date": m.get("endDate"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

def fetch_markets(top: int = 1000) -> list[dict]:
    """Fetch the top-`top` active markets by volume, paging past Gamma's 100/request cap.
    Deduped by market_id — pages overlap as live volume reorders them."""
    markets, seen = [], set()
    for offset in range(0, top, PAGE):
        res = requests.get(f"{GAMMA_API}/markets", params={
            "limit": PAGE,
            "offset": offset,
            "active": "true",
            "closed": "false",
            "order": "volumeNum",
            "ascending": "false",
        }, timeout=15)
        res.raise_for_status()
        raw = res.json()
        if not raw:
            break  # ran out of markets
        for m in raw:
            try:
                if m["id"] in seen or _is_expired(m):
                    continue  # skip dupes and already-resolved markets
                seen.add(m["id"])
                markets.append(_to_record(m))
            except Exception:
                continue
    return markets

if __name__ == "__main__":
    markets = fetch_markets(300)
    print(f"fetched {len(markets)} markets")
    for m in markets[:10]:
        print(f"{m['probability']:.0%} | ${m['volume_usd']:,.0f} | {m['question'][:80]}")
