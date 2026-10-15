"""Offline core tests — no network, no API keys, no DB. Run by the pre-commit hook.
    python3 tests/test_core.py   (or: pytest)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import polymarket, news


def test_probability_from_outcome_prices():
    r = polymarket._to_record({"id": "1", "outcomePrices": '["0.73","0.27"]', "volumeNum": 1000})
    assert r["probability"] == 0.73, r
    assert r["volume_usd"] == 1000.0, r
    assert r["market_id"] == "1"


def test_volume_falls_back_and_default_prob():
    r = polymarket._to_record({"id": "2", "volume": "500"})  # no volumeNum, no prices
    assert r["volume_usd"] == 500.0, r
    assert r["probability"] == 0.5, r  # no outcomePrices → 0.5 default


def test_prices_as_list_not_string():
    r = polymarket._to_record({"id": "3", "outcomePrices": ["0.1", "0.9"]})
    assert r["probability"] == 0.1, r


def test_rss_parse_titles_and_links():
    xml = b'<rss><channel><item><title> Fed cuts rates </title><link>http://x</link></item>' \
          b'<item><title></title></item></channel></rss>'
    items = news._parse_rss(xml, 10)
    assert items == [{"title": "Fed cuts rates", "link": "http://x"}], items  # blank title dropped, trimmed


def test_rss_respects_limit():
    xml = b"<rss><channel>" + b"<item><title>h</title></item>" * 5 + b"</channel></rss>"
    assert len(news._parse_rss(xml, 3)) == 3


def test_expired_market_detection():
    assert polymarket._is_expired({"endDate": "2020-01-01T00:00:00Z"}) is True
    assert polymarket._is_expired({"endDate": "2099-01-01T00:00:00Z"}) is False
    assert polymarket._is_expired({}) is False           # no date → treat as live
    assert polymarket._is_expired({"endDate": "garbage"}) is False  # unparseable → don't drop


def test_sports_guard_zeroes_without_llm():
    from src import filter as f
    saved, f.client = f.client, None  # guard must fire BEFORE any LLM call — no client, no luck
    try:
        for q in ["Will USA win the 2026 FIFA World Cup?", "Spread: United States (-1.5)",
                  "Blockx vs. Zverev: Match O/U 36.5", "Map 2: Odd/Even Total Kills?"]:
            s = f.score_market({"market_id": "x", "question": q})
            assert s["relevance_score"] == 0 and s["affected_tickers"] == [], (q, s)
    finally:
        f.client = saved


def test_sports_guard_leaves_finance_alone():
    from src import filter as f
    for q in ["Will the Fed cut interest rates in September 2026?",
              "Will Bitcoin hit $150k by June 30, 2026?",
              "Will the Democratic Party control the House after the midterms?"]:
        assert not f.SPORTS_RE.search(q), q


def test_hot_topics_rank_by_conviction_and_money():
    from src import views
    r = lambda sec, score, vol, days=30, tk=("X",): dict(score=score, volume=vol, sector=sec, days=days,
                                                          market=f"{sec}{score}", tickers=list(tk))
    rows = [r("Crypto", 9, 5e7, days=3), r("Crypto", 7, 1e6, days=-2), r("Pharma", 6, 1e5),
            r("Macro", 3, 9e9), r("—", 10, 9e9)]  # score<5 and the unsorted "—" bucket never rank
    hot = views.hot_topics(rows)
    assert [h["sector"] for h in hot] == ["Crypto", "Pharma"], hot
    assert hot[0]["heat"] == 100 and 0 < hot[1]["heat"] < 100, hot
    assert hot[0]["soon"] == 3 and hot[0]["peak"] == 9 and hot[0]["lead"] == "Crypto9", hot[0]  # expired (-2d) ignored
    ex = views.exposure(rows, {"X": "x", "Z": "z"})
    assert ex[0]["n"] == 4 and ex[0]["peak"] == 10 and ex[1]["n"] == 0, ex  # exposure ignores sector, counts every active hit


if __name__ == "__main__":
    tests =[v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"\n{len(tests)} passed")
