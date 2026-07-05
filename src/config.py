"""Watchlist configuration — the single place the watched tickers/sectors live.

Every prompt (filter, news, brief, agent) is built from this at call time, so
editing the watchlist in the UI changes what future scans score against.
Stored as a JSON file so the headless scanner and the Streamlit app share it.
"""
import json
import os

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "watchlist.json")

DEFAULT = {
    "tickers": {
        "NVDA": "AI chips & data-center compute",
        "TSLA": "EVs, autonomy & energy",
        "COIN": "crypto exchange & custody",
        "LLY": "pharma & GLP-1 franchise",
    },
    "sectors": ["AI & Semiconductors", "Crypto & Fintech", "Health & Biotech",
                "EV & Energy", "E-Commerce", "Macro"],
}


def get_watchlist() -> dict:
    try:
        with open(PATH) as f:
            wl = json.load(f)
        assert wl.get("tickers") and wl.get("sectors")
        return wl
    except Exception:
        return DEFAULT


def save_watchlist(tickers: dict, sectors: list) -> None:
    with open(PATH, "w") as f:
        json.dump({"tickers": tickers, "sectors": sectors}, f, indent=2)


def holdings_block() -> str:
    """Prompt-ready description of the watchlist."""
    wl = get_watchlist()
    lines = "\n".join(f"- {t}: {d}" for t, d in wl["tickers"].items())
    return f"Watchlist:\n{lines}\nFocus sectors: {', '.join(wl['sectors'])}"
