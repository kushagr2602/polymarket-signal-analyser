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
    from src import filter as f, llm
    saved, llm.client = llm.client, None  # guard must fire BEFORE any LLM call — no client, no luck
    try:
        for q in ["Will USA win the 2026 FIFA World Cup?", "Spread: United States (-1.5)",
                  "Blockx vs. Zverev: Match O/U 36.5", "Map 2: Odd/Even Total Kills?"]:
            s = f.score_market({"market_id": "x", "question": q})
            assert s["relevance_score"] == 0 and s["affected_tickers"] == [], (q, s)
    finally:
        llm.client = saved


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


def test_llm_degrades_to_fallback_but_does_not_mask_real_errors():
    import httpx, openai
    from src import llm
    req = httpx.Request("POST", "http://x")
    calls, refuse = [], {"err": openai.NotFoundError}

    class C:  # fake OpenAI client: refuses every model except the fallback
        class chat:
            class completions:
                @staticmethod
                def create(model, **kw):
                    calls.append((model, kw.get("reasoning_effort")))
                    if model != llm.FALLBACK:
                        raise refuse["err"]("nope", response=httpx.Response(404, request=req), body=None)
                    return "ok"

    saved, llm.client = llm.client, C
    llm._ok.clear()
    try:
        assert llm.chat("score", messages=[]) == "ok"
        assert calls[-1] == (llm.FALLBACK, None) and llm.active("score") == llm.FALLBACK, calls
        n = len(calls)
        llm.chat("score", messages=[])
        assert len(calls) == n + 1, "a refused model must be remembered, not retried every call"
        llm._ok.clear()
        refuse["err"] = openai.RateLimitError  # a real outage / limit must surface, never silently downgrade
        try:
            llm.chat("score", messages=[])
            raise AssertionError("a rate-limit error must propagate")
        except openai.RateLimitError:
            pass
        assert llm.active("score") == llm.ROLES["score"][0] and calls[-1][0] == llm.ROLES["score"][0], calls
    finally:
        llm.client = saved
        llm._ok.clear()


def test_market_money_math():
    from datetime import date, timedelta
    from src import market
    # currency: USD and London pence both land in euros
    assert abs(market.to_eur([["2026-01-02", 110.0]], "USD", [["2026-01-01", 1.1]])[0][1] - 100) < 1e-9  # fx forward-filled
    assert abs(market.to_eur([["2026-01-02", 1000.0]], "GBp", [["2026-01-02", 0.8]])[0][1] - 12.5) < 1e-9
    assert market.to_eur([["2026-01-02", 1.0]], "USD", None) == []  # no FX → excluded, never guessed

    d0 = date(2022, 1, 1)
    days = [(d0 + timedelta(days=i)).isoformat() for i in range(4 * 365 + 5)]
    steady = [[d, 100 * 1.1 ** (i / 365)] for i, d in enumerate(days)]  # exactly +10 %/yr, never falls
    m = market.metrics(steady)
    assert abs(m["cagr3"] - .10) < 1e-3 and m["mdd"] == 0 and abs(m["r1y"] - .10) < 1e-3, m
    crash = [[d, 100 if i < 400 else 50 if i < 800 else 100] for i, d in enumerate(days)]
    assert abs(market.metrics(crash)["mdd"] + .5) < 1e-9  # halved at the worst point

    rows = [{"kind": "etf", "m": market.metrics(steady)}, {"kind": "etf", "m": market.metrics(crash)}]
    market.score(rows)
    assert rows[0]["score"] > rows[1]["score"], rows  # steady growth beats a crash-and-flat
    assert market.why(rows[0]).startswith("Ranks high")


def test_portfolio_average_cost_and_csv():
    from src import portfolio as pf
    t = lambda d, side, q, p, f=0: pf.clean({"date": d, "ticker": "VWCE.DE", "side": side, "qty": q, "price": p, "fees": f})
    trades = [t("2024-01-02", "buy", 10, 100, 1), t("2024-06-03", "buy", 10, 120, 1), t("2025-01-02", "sell", 5, 150, 1)]
    p = pf.positions(trades)["VWCE.DE"]
    assert abs(p["qty"] - 15) < 1e-9
    avg = (10 * 100 + 1 + 10 * 120 + 1) / 20                       # 110.10 per share, fees included
    assert abs(p["realized"] - (5 * (150 - avg) - 1)) < 1e-9       # sold 5 above average cost, minus the fee
    assert abs(p["cost"] - avg * 15) < 1e-9
    try:
        pf.positions(trades + [t("2025-02-01", "sell", 99, 1)])
        raise AssertionError("selling more than you hold must be refused")
    except ValueError as e:
        assert "only hold" in str(e)
    # German-style export: ; separated, day-first dates, decimal commas, German headers, sells as negative qty
    rows, errs = pf.parse_csv("Datum;Wertpapier;Anzahl;Kurs;Gebühr\n14.03.2025;vwce.de;3;1.234,50;1,00\n15.03.2025;AAPL;-2;180,5;0\n")
    assert not errs, errs
    assert rows[0]["date"] == "2025-03-14" and rows[0]["ticker"] == "VWCE.DE" and rows[0]["price"] == 1234.5 and rows[0]["fees"] == 1.0
    assert rows[1]["side"] == "sell" and rows[1]["qty"] == 2
    _, errs = pf.parse_csv("foo,bar\n1,2\n")
    assert errs and "Couldn't find" in errs[0]
    # today's mix, forward-filled across a day one exchange was closed
    mix = pf.mix_series({"A": 2, "B": 1}, {"A": [["2025-01-01", 10], ["2025-01-02", 11]], "B": [["2025-01-01", 5]]})
    assert mix == [["2025-01-01", 25], ["2025-01-02", 27]], mix


def test_agent_never_runs_the_portfolio_tool_for_remote_requests():
    from types import SimpleNamespace as NS
    from src import agent, llm
    names = lambda private: {t["function"]["name"] for t in agent.tools_for(private)}
    assert "get_my_portfolio" in names(True) and "get_my_portfolio" not in names(False)

    sent, step = [], {"n": 0}

    class TC:  # a tool call the (fake) model makes even though the tool wasn't offered
        id, function = "c1", NS(name="get_my_portfolio", arguments="{}")
        def model_dump(self): return {"id": self.id, "type": "function", "function": {"name": "get_my_portfolio", "arguments": "{}"}}

    class C:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    sent.append(kw)
                    step["n"] += 1
                    msg = NS(tool_calls=[TC()], content=None) if step["n"] == 1 else NS(tool_calls=None, content="done")
                    return NS(choices=[NS(message=msg)], model="fake")

    called = []
    saved, llm.client, real = llm.client, C, agent._IMPL["get_my_portfolio"]
    agent._IMPL["get_my_portfolio"] = lambda: called.append(1) or {"holdings": ["secret"]}
    llm._ok.clear()
    try:
        answer, trace = agent.run("what do I own?", private=False)
        assert not called, "portfolio tool executed for a remote request"
        assert trace == ["get_my_portfolio → error"] and answer == "done", trace
        tool_msg = [m for m in sent[-1]["messages"] if m.get("role") == "tool"][0]
        assert "not available" in tool_msg["content"] and "secret" not in tool_msg["content"]
    finally:
        llm.client, agent._IMPL["get_my_portfolio"] = saved, real
        llm._ok.clear()


if __name__ == "__main__":
    tests =[v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"\n{len(tests)} passed")
