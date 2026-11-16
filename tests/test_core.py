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


def test_broker_imports_and_currency():
    from src import portfolio as pf
    revolut = ("Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate\n"
               "2025-01-06T14:32:10.123Z,,CASH TOP-UP,,,USD 500,USD,1.04\n"
               "2025-01-07T15:01:00.000Z,AAPL,BUY - MARKET,2,USD 150.1,USD 300.21,USD,1.04\n"
               "2025-02-10T10:00:00.000Z,AAPL,DIVIDEND,,,USD 0.48,USD,1.05\n"
               "2025-03-03T16:20:00.000Z,AAPL,SELL - MARKET,1,USD 170,USD 170,USD,1.06\n")
    t, e, fmt, skipped = pf.parse_import(revolut)
    assert fmt == "Revolut statement" and not e and skipped == 2, (fmt, e, skipped)
    assert [x["side"] for x in t] == ["buy", "sell"] and t[0]["ccy"] == "USD" and abs(t[0]["price"] - 150.105) < 1e-9  # from the total
    ibkr = ("Statement,Header,Field Name,Field Value\nStatement,Data,Title,Activity Statement\n"
            "Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,Realized P/L,MTM P/L,Code\n"
            'Trades,Data,Order,Stocks,EUR,VWCE,"2025-02-03, 09:12:01",10,120.5,121,-1205,-1.25,1206.25,0,5,O\n'
            'Trades,Data,Order,Stocks,USD,BRK B,"2025-02-04, 15:30:00",-2,480,481,960,-0.35,900,59.65,2,C\n'
            "Trades,SubTotal,,Stocks,EUR,VWCE,,10,,,-1205,-1.25,,,,\n"
            'Trades,Data,Order,Forex,USD,EUR.USD,"2025-02-04, 15:31:00",-960,1.03,,,0,,,,\n'
            "Financial Instrument Information,Header,Asset Category,Symbol,Description,Conid,Security ID,Listing Exch,Multiplier,Type,Code\n"
            "Financial Instrument Information,Data,Stocks,VWCE,VANGUARD FTSE ALL-WORLD,1,IE00BK5BQT80,IBIS2,1,ETF,\n"
            "Financial Instrument Information,Data,Stocks,BRK B,BERKSHIRE HATH-CL B,2,US0846707026,NYSE,1,COMMON,\n")
    t, e, fmt, skipped = pf.parse_import(ibkr)
    assert fmt.startswith("Interactive Brokers") and not e and skipped == 1, (fmt, e, skipped)  # the forex row
    assert [(x["ticker"], x["side"], x["ccy"], x["fees"]) for x in t] == [("VWCE.DE", "buy", "EUR", 1.25), ("BRK-B", "sell", "USD", .35)], t
    zerodha = ("symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,trade_id,order_id,order_execution_time\n"
               "RELIANCE,INE002A01018,2025-04-10,NSE,EQ,EQ,buy,false,5,1210.5,1,1,2025-04-10T10:01:00\n"
               "M&M,INE101A01026,2025-04-11,BSE,EQ,EQ,buy,false,1,3000,2,2,2025-04-11T10:01:00\n")
    t, e, fmt, _ = pf.parse_import(zerodha)
    assert fmt == "Zerodha tradebook" and not e and [x["ticker"] for x in t] == ["RELIANCE.NS", "M&M.BO"] and t[0]["ccy"] == "INR", (t, e)
    # cost basis in EUR at the trade date's rate; a currency with no rate is reported, not guessed
    conv, missing = pf.to_eur([{**t[0], "ccy": "USD", "price": 125.0, "fees": 1.25}], {"EURUSD=X": [["2025-01-01", 1.25]]})
    assert abs(conv[0]["price"] - 100) < 1e-9 and abs(conv[0]["fees"] - 1) < 1e-9 and not missing
    _, missing = pf.to_eur([{**t[0], "ccy": "INR"}], {})
    assert missing == {"INR"}


def test_compare_and_correlation():
    from datetime import date, timedelta
    from src import market
    days = [(date(2023, 1, 2) + timedelta(days=i)).isoformat() for i in range(1200)]
    a, p = [], 100.0
    for i, d in enumerate(days):  # wobbly but rising
        p *= 1.012 if i % 3 else .985
        a.append([d, p])
    same = [[d, v * 2] for d, v in a]                       # same moves, different price level
    opposite = [[d, 1e4 / v] for d, v in a]                 # every up day is a down day
    assert abs(market.correlation(a, same) - 1) < 1e-9
    assert abs(market.correlation(a, opposite) + 1) < 1e-9
    c = market.compare({"closes": {"VWCE.DE": a, "EUNL.DE": opposite}}, ["VWCE.DE", "EUNL.DE", "NOPE"])
    assert [i["t"] for i in c["items"]] == ["VWCE.DE", "EUNL.DE"]  # unknown tickers dropped
    assert c["summary"][0].startswith("Grew the most: Vanguard") and "often move differently" in c["pairs"][0]["plain"], c
    assert market.compare({"closes": {"VWCE.DE": a}}, ["VWCE.DE"]) is None  # one instrument isn't a comparison


def test_savings_plan_math():
    from datetime import date, timedelta
    from src import market
    days = [(date(2022, 1, 1) + timedelta(days=i)).isoformat() for i in range(3 * 365)]
    flat = market.savings_plan([[d, 50.0] for d in days], 100, "2022-01-01", fee=1)
    n = flat["months"]
    assert n == 36 and abs(flat["paid"] - 3600) < 1e-9 and abs(flat["value"] - 99 * n) < 1e-6, flat
    assert abs(flat["avg_price"] - 50) < 1e-9 and flat["xirr"] < 0  # fees are the only change
    grow = [[d, 100 * 1.12 ** (i / 365)] for i, d in enumerate(days)]  # exactly +12 %/yr
    g = market.savings_plan(grow, 100, "2022-01-01")
    assert abs(g["xirr"] - .12) < 1e-4 and g["value"] > g["paid"] and g["avg_price"] < g["price"], g["xirr"]
    crash = [[d, 100.0 if i < 180 else 50.0] for i, d in enumerate(days)]
    w = market.savings_plan(crash, 100, "2022-01-01")["worst"]
    assert w["pct"] < -.4 and w["date"] >= days[180], w
    assert abs(market.project(1000, 0, 10, .05) - 1000 * 1.05 ** 10) < 1e-6
    assert abs(market.project(0, 100, 5, 0) - 6000) < 1e-9
    assert market.savings_plan([[d, 50.0] for d in days[:10]], 100, days[0]) is None  # too little history


def test_price_alerts():
    from datetime import date, timedelta
    from src import alerts
    days = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(120)]
    px = [100 + i for i in range(60)] + [159 * .85] * 60          # climbs to 159, then drops 15% and stays
    s = {"X": [[d, p] for d, p in zip(days, px)]}
    mk = lambda kind, v, created="2026-01-01": alerts.clean({"ticker": "X", "kind": kind, "value": v, "created": created}, {"X"})
    r = {a["kind"] + str(a["value"]): a for a in alerts.evaluate([mk("drop", 10), mk("drop", 20), mk("below", 140), mk("move", 10)], s, {"X": "Ex"})}
    assert r["drop10.0"]["triggered"] and r["drop10.0"]["first"] == days[60], r["drop10.0"]
    assert not r["drop20.0"]["triggered"] and r["drop20.0"]["first"] is None
    assert r["below140.0"]["triggered"] and "below your €140.00 line" in r["below140.0"]["text"]
    assert not r["move10.0"]["triggered"] and r["move10.0"]["first"] == days[60]  # the 15% one-day drop fired once, then calm
    late = alerts.evaluate([mk("move", 10, created=days[90])], s, {})[0]
    assert late["first"] is None  # a move before the alert existed doesn't count
    for bad in ({"ticker": "NOPE", "kind": "drop", "value": 10}, {"ticker": "X", "kind": "drop", "value": 0}, {"ticker": "X", "kind": "?", "value": 5}):
        try:
            alerts.clean(bad, {"X"})
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass


def test_signal_trends_from_snapshots():
    import math
    from datetime import datetime, timedelta, timezone
    from src import views
    now = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
    row = lambda i, sec, score, vol, prob: {"id": i, "score": score, "sector": sec, "volume": vol, "prob": prob, "market": i, "tickers": [], "days": 5}
    rows = [row("m1", "Crypto", 9, 1e6, .60), row("m2", "Crypto", 6, 1e4, .42), row("m3", "Macro", 5, 1e5, .3)]
    live_w = views.sector_weights(rows)["Crypto"]["w"]
    assert abs(live_w - (5 * math.log10(1e6 + 10) + 2 * math.log10(1e4 + 10))) < 1e-9
    snap = lambda days, w, probs: {"taken_at": (now - timedelta(days=days)).isoformat(), "sectors": [{"sector": "Crypto", "w": w}],
                                   "markets": {k: [v, 1] for k, v in probs.items()}}
    snaps = [snap(8, live_w / 1.5, {"m1": .40, "m2": .41}), snap(2, live_w / 1.2, {"m1": .45, "m2": .41}), snap(.2, live_w, {"m1": .59})]
    t = views.trends(snaps, rows, now)
    c = t["sectors"]["Crypto"]
    assert abs(c["change"] - .5) < 1e-9 and c["vs_days"] == 8 and len(c["spark"]) == 4, c   # vs ~a week ago, not the 2-day one
    assert t["sectors"]["Macro"]["change"] is None                                         # never in a snapshot → no fake trend
    assert [m["market"] for m in t["movers"]] == ["m1"] and abs(t["movers"][0]["delta"] - .15) < 1e-9, t["movers"]  # vs 2 days ago; m2's 1pt wiggle ignored
    assert views.trends([], rows, now)["movers"] == [] and views.trends([], rows, now)["sectors"]["Crypto"]["change"] is None
    s = views.snapshot(rows)
    assert s["markets"]["m1"] == [.6, 1000000] and {x["sector"] for x in s["sectors"]} == {"Crypto", "Macro"}


def test_ipo_calendar():
    from datetime import date
    from src import ipos
    today = date(2026, 11, 16)
    raw = {"ipoCalendar": [  # Finnhub's documented shape
        {"date": "2026-12-04", "exchange": "NASDAQ", "name": "Later Co", "numberOfShares": 1e7, "price": "18-20", "status": "expected", "symbol": "LATR", "totalSharesValue": 2.5e8},
        {"date": "2026-11-20", "exchange": "NYSE", "name": "Soon Inc", "numberOfShares": None, "price": "", "status": "expected", "symbol": "SOON", "totalSharesValue": None},
        {"date": "2026-11-10", "exchange": "NASDAQ", "name": "Done Ltd", "price": "12", "status": "priced", "symbol": "DONE", "totalSharesValue": 9e7},
        {"date": "2026-11-25", "exchange": "NYSE", "name": "Gone Corp", "status": "withdrawn", "symbol": "GONE"},
        {"date": None, "exchange": "NASDAQ", "name": "Someday Bio", "status": "filed", "symbol": ""}]}
    rows = ipos.normalize(raw, today)
    assert [r["name"] for r in rows] == ["Soon Inc", "Later Co", "Someday Bio", "Done Ltd"], [r["name"] for r in rows]
    assert rows[1]["text"] == "Expected to list on NASDAQ on 4 Dec at $18–$20 a share, raising about $250M."
    assert rows[2]["text"].startswith("Has filed to go public on NASDAQ") and rows[3]["text"].startswith("Listed on NASDAQ on 10 Nov at $12")
    assert ipos.normalize({}, today) == [] and ipos.normalize(None, today) == []
    assert ipos.clean_watch({"name": "Lenskart", "exchange": "NSE", "date": "2026-12-01"})["date"] == "2026-12-01"
    for bad in ({"name": "x"}, {"name": "Ok Co", "date": "soon"}, {"name": "Ok Co", "link": "javascript:alert(1)"}):
        try:
            ipos.clean_watch(bad)
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass


if __name__ == "__main__":
    tests =[v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"\n{len(tests)} passed")
