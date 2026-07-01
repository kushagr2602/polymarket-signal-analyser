from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import database

# ── tactical-HUD palette: space navy, cyan structure, conviction heats cool→hot ──
BG, PANEL, LINE = "#060A12", "#0B121C", "#18324A"
TXT, MUTED, TEAL, AMBER, HOT = "#C8D6E5", "#5E7388", "#3FE0C5", "#FFB23E", "#FF5A47"

HOLDINGS = {"HIMS": "HEALTH-TECH", "HOOD": "FINTECH", "RDDT": "AI · DATA", "IREN": "AI-INFRA · CRYPTO"}


def heat(score: int) -> str:  # dim-blue → teal → amber → hot, i.e. conviction "temperature"
    return HOT if score >= 8 else AMBER if score >= 5 else TEAL if score >= 3 else "#3A5068"


def tier(score: int) -> str:
    return ("DIRECT CATALYST" if score >= 8 else "SECTOR IMPACT" if score >= 5
            else "MACRO SIGNAL" if score >= 3 else "WEAK")


def agenda_html(up) -> str:
    """Render upcoming signals as a grouped schedule (soonest first)."""
    up = up.drop_duplicates("Market").sort_values("Days to expiry").head(14)
    order = ["THIS WEEK", "THIS MONTH", "NEXT 3 MONTHS", "LATER"]
    groups: dict[str, list] = {}
    for _, r in up.iterrows():
        d = r["Days to expiry"]
        h = "THIS WEEK" if d <= 7 else "THIS MONTH" if d <= 31 else "NEXT 3 MONTHS" if d <= 93 else "LATER"
        groups.setdefault(h, []).append(r)
    html = '<div class="agenda">'
    for h in order:
        if h not in groups:
            continue
        html += f'<div class="ag-h">{h} · {len(groups[h])}</div>'
        for r in groups[h]:
            d = int(r["Days to expiry"])
            when = "TODAY" if d == 0 else f"IN {d}D"
            tk = r["Tickers"][0] if r["Tickers"] else "—"
            html += (f'<div class="ag-row"><span class="ag-when">{when}</span>'
                     f'<span class="ag-q">{r["Market"][:56]}</span>'
                     f'<span class="ag-tk">{tk}</span>'
                     f'<span class="ag-s" style="color:{heat(r["Score"])}">{r["Score"]}</span></div>')
    return html + "</div>"


st.set_page_config(page_title="BIT CAPITAL · SIGNAL DESK", page_icon="◆", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
html, body, [class*="css"] { font-family:'JetBrains Mono', monospace; color:#C8D6E5; }
#MainMenu, header, footer { visibility:hidden; }
.stApp {
  background:
    radial-gradient(1200px 620px at 72% -8%, rgba(63,224,197,.07), transparent 60%),
    radial-gradient(900px 500px at 10% 110%, rgba(255,178,62,.05), transparent 60%),
    #060A12;
}
.stApp::before {  /* faint tactical grid */
  content:''; position:fixed; inset:0; pointer-events:none; z-index:0;
  background-image:linear-gradient(rgba(63,224,197,.035) 1px, transparent 1px),
                   linear-gradient(90deg, rgba(63,224,197,.035) 1px, transparent 1px);
  background-size:42px 42px;
}
.block-container { padding-top:1.4rem; padding-bottom:3rem; max-width:1320px; position:relative; z-index:1; }

/* HUD panel with corner brackets */
.hud { position:relative; border:1px solid #18324A; background:rgba(11,18,28,.72); }
.hud::before, .hud::after { content:''; position:absolute; width:11px; height:11px; border:2px solid #3FE0C5; }
.hud::before { top:-1px; left:-1px; border-right:0; border-bottom:0; }
.hud::after { bottom:-1px; right:-1px; border-left:0; border-top:0; }

/* masthead */
.mh { display:flex; align-items:center; justify-content:space-between; padding:.8rem 1.1rem; margin-bottom:.4rem; }
.mh .name { font-family:'Chakra Petch', sans-serif; font-weight:700; font-size:1.7rem; letter-spacing:.04em; color:#E6F1F5; }
.mh .name b { color:#3FE0C5; }
.mh .live { color:#46E08B; animation:pulse 1.8s ease-in-out infinite; margin-right:.5rem; }
@keyframes pulse { 0%,100%{opacity:.35} 50%{opacity:1} }
.mh .meta { font-size:.66rem; letter-spacing:.13em; color:#5E7388; text-align:right; line-height:1.7; }
.dek { font-family:'Chakra Petch', sans-serif; font-size:.92rem; letter-spacing:.02em; color:#7E93A8; margin:.5rem .2rem 1.2rem; }

/* lede stat cells */
.kpi-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:.6rem; margin-bottom:.4rem; }
.kpi { padding:.8rem .9rem; }
.kpi .v { font-family:'Chakra Petch', sans-serif; font-weight:600; font-size:1.7rem; line-height:1.1; color:#E6F1F5; text-shadow:0 0 14px rgba(63,224,197,.25); }
.kpi .v.teal { color:#3FE0C5; } .kpi .v.hot { color:#FF5A47; text-shadow:0 0 14px rgba(255,90,71,.3); }
.kpi .l { font-size:.58rem; letter-spacing:.15em; color:#5E7388; margin-top:.3rem; }

/* section header + terminal-style hint */
.sec-h { font-family:'Chakra Petch', sans-serif; font-size:.74rem; font-weight:600; letter-spacing:.2em; color:#3FE0C5; margin:1.7rem 0 .15rem; }
.sec-h::before { content:'// '; color:#3A5068; }
.hint { font-size:.74rem; letter-spacing:.02em; color:#7E93A8; margin:.35rem 0 .85rem; }
.hint::before { content:'› '; color:#3FE0C5; }

/* portfolio exposure */
.pos-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:.6rem; }
.pos { padding:.7rem .95rem .85rem; }
.pos .tkr { font-family:'Chakra Petch', sans-serif; font-weight:700; font-size:1.3rem; color:#E6F1F5; letter-spacing:.03em; }
.pos .sec { font-size:.56rem; letter-spacing:.12em; color:#5E7388; }
.pos .row { display:flex; justify-content:space-between; align-items:baseline; margin-top:.55rem; }
.pos .n { font-family:'Chakra Petch', sans-serif; font-weight:600; font-size:1.5rem; color:var(--c); text-shadow:0 0 12px color-mix(in srgb, var(--c) 35%, transparent); }
.pos .mx { font-size:.64rem; color:var(--c); }

/* news wire */
.news { display:flex; gap:.85rem; align-items:flex-start; padding:.7rem .2rem; border-bottom:1px solid #142336; }
.news .imp { font-family:'Chakra Petch', sans-serif; font-weight:700; font-size:1.35rem; line-height:1; color:var(--c); min-width:1.4rem; text-align:center; text-shadow:0 0 12px color-mix(in srgb, var(--c) 40%, transparent); }
.news .ttl { color:#D6E2EF; font-size:.92rem; line-height:1.4; }
.news .ttl a { color:inherit; text-decoration:none; border-bottom:1px solid #244055; }
.news .ttl a:hover { color:#3FE0C5; border-color:#3FE0C5; }
.news .meta { margin-top:.3rem; font-size:.64rem; letter-spacing:.04em; color:#5E7388; }
.news .stance { color:var(--c); font-weight:600; }
.news .note { color:#8499AD; }

/* agenda / schedule */
.agenda { border:1px solid #18324A; border-radius:2px; overflow:hidden; }
.ag-h { font-family:'JetBrains Mono', monospace; font-size:.6rem; letter-spacing:.15em; color:#5E7388; background:rgba(63,224,197,.05); padding:.4rem .85rem; }
.ag-row { display:flex; align-items:center; gap:.75rem; padding:.5rem .85rem; border-top:1px solid #142336; }
.ag-when { font-family:'JetBrains Mono', monospace; font-size:.62rem; letter-spacing:.03em; color:#7E93A8; min-width:52px; }
.ag-q { flex:1; font-size:.86rem; color:#D6E2EF; line-height:1.3; }
.ag-tk { font-family:'JetBrains Mono', monospace; font-size:.6rem; color:#8FA6BC; background:#0E1A28; padding:.12rem .45rem; border-radius:3px; }
.ag-s { font-family:'Chakra Petch', sans-serif; font-weight:700; font-size:1.05rem; min-width:20px; text-align:center; }

.stTabs [data-baseweb="tab"] { font-family:'Chakra Petch', sans-serif; font-size:.74rem; letter-spacing:.12em; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=120)
def load():
    db = database.get_client()
    sig = database._all_rows("signals", "market_id,relevance_score,sector,affected_tickers,reasoning,created_at,"
                             "markets(question,probability,volume_usd,expiry_date,fetched_at)")
    rep = db.table("reports").select("*").order("report_date", desc=True).limit(60).execute().data
    n_markets = db.table("markets").select("market_id", count="exact").execute().count
    return sig, rep, n_markets


@st.cache_data(ttl=1800)
def load_news():
    from src import news
    return news.assess_news()


def to_df(sig: list[dict]) -> pd.DataFrame:
    rows, now = [], datetime.now(timezone.utc)
    for s in sig:
        m = s.get("markets") or {}
        exp, days = m.get("expiry_date"), None
        if exp:
            try:
                days = (datetime.fromisoformat(exp.replace("Z", "+00:00")) - now).days
            except Exception:
                days = None
        rows.append({
            "MarketId": s.get("market_id"),
            "Score": s["relevance_score"], "Tier": tier(s["relevance_score"]),
            "Sector": s.get("sector") or "—", "Tickers": s.get("affected_tickers") or [],
            "Market": m.get("question", ""), "Prob": m.get("probability"),
            "Volume": m.get("volume_usd") or 0, "Days to expiry": days,
            "Expired": days is not None and days < 0,
            "Reasoning": s.get("reasoning", ""), "Scanned": (s.get("created_at") or "")[:10],
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # dedupe leftover DB duplicates (keep highest conviction per market) so the dashboard is clean
    # without needing the manual SQL cleanup; drop already-resolved markets from the live view.
    df = df.sort_values("Score", ascending=False).drop_duplicates("MarketId")
    return df[~df.Expired].reset_index(drop=True)


sig, rep, n_markets = load()
df = to_df(sig)
last_scan = max((s.get("markets") or {}).get("fetched_at", "") for s in sig) if sig else ""
stamp = last_scan[:16].replace("T", " ") + "Z" if last_scan else "NO SCANS"
today = datetime.now(timezone.utc).strftime("%Y.%m.%d").upper()

st.markdown(f"""
<div class="mh hud">
  <div class="name"><span class="live">●</span><b>BIT</b> CAPITAL <b>/</b> SIGNAL DESK</div>
  <div class="meta">POLYMARKET FEED · {today}<br>LAST SCAN · {stamp}</div>
</div>
<div class="dek">Prediction markets, swept for what could move the book — HIMS · HOOD · RDDT · IREN.</div>
""", unsafe_allow_html=True)

if df.empty:
    st.info("No signals yet. Run `python3 -m src.scheduler --once` to scan.")
    st.stop()

active = df[df.Score >= 5]
high = df[df.Score >= 8]

st.markdown(f"""
<div class="kpi-grid">
  <div class="kpi hud"><div class="v">{n_markets:,}</div><div class="l">MARKETS SCANNED</div></div>
  <div class="kpi hud"><div class="v teal">{len(active)}</div><div class="l">ACTIVE SIGNALS · ≥5</div></div>
  <div class="kpi hud"><div class="v hot">{len(high)}</div><div class="l">HIGH CONVICTION · ≥8</div></div>
  <div class="kpi hud"><div class="v">${df.Volume.sum()/1e6:,.0f}M</div><div class="l">VOLUME TRACKED</div></div>
  <div class="kpi hud"><div class="v">{active.Score.mean() if len(active) else 0:.1f}</div><div class="l">AVG CONVICTION</div></div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="sec-h">PORTFOLIO EXPOSURE</div>', unsafe_allow_html=True)
st.markdown('<div class="hint">Live signals touching each holding + the strongest one. More signals and a higher peak = more brewing for that stock.</div>', unsafe_allow_html=True)
cards = ""
for tkr, sec in HOLDINGS.items():
    hit = active[active.Tickers.apply(lambda ts: tkr in ts)]
    mx = int(hit.Score.max()) if len(hit) else 0
    c = heat(mx) if len(hit) else "#3A5068"
    cards += (f'<div class="pos hud" style="--c:{c}"><div class="tkr">{tkr}</div>'
              f'<div class="sec">{sec}</div><div class="row">'
              f'<span class="n">{len(hit)}</span><span class="mx">PEAK {mx}/10</span></div></div>')
st.markdown(f'<div class="pos-grid">{cards}</div>', unsafe_allow_html=True)


def style_fig(fig, h=300):
    fig.update_layout(
        height=h, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED, family="JetBrains Mono", size=11),
        margin=dict(l=10, r=10, t=34, b=10), showlegend=False,
        title=dict(font=dict(color=TEAL, size=13, family="Chakra Petch")),
    )
    fig.update_xaxes(gridcolor="#10202F", zeroline=False, linecolor=LINE)
    fig.update_yaxes(gridcolor="#10202F", zeroline=False, linecolor=LINE)
    return fig


desk, news_tab, ask, brief = st.tabs(["◆  SIGNAL DESK", "⊹  WORLD NEWS", "✦  ASK THE DESK", "▤  DAILY BRIEF"])

with desk:
    left, right = st.columns([1, 1.15])
    with left:
        st.markdown('<div class="hint">Which themes are loaded with signals — longer bar = stronger average conviction; number after the dot = how many signals.</div>', unsafe_allow_html=True)
        by_sec = active.groupby("Sector").Score.agg(["mean", "count"]).sort_values("mean")
        bar = go.Figure(go.Bar(
            x=by_sec["mean"], y=by_sec.index, orientation="h",
            marker=dict(color=[heat(round(v)) for v in by_sec["mean"]]),
            text=[f"{m:.1f} · {int(c)}" for m, c in zip(by_sec["mean"], by_sec["count"])],
            textposition="outside", textfont=dict(color=MUTED),
            hovertemplate="%{y}<br>avg conviction %{x:.1f}<extra></extra>",
        ))
        bar.update_layout(title="CONVICTION BY SECTOR")
        bar.update_xaxes(range=[0, 10])
        st.plotly_chart(style_fig(bar), use_container_width=True)
    with right:
        st.markdown('<div class="hint">Each dot is a market. Up = matters more to BIT. Right = more money traded. Top-right corner is your watchlist.</div>', unsafe_allow_html=True)
        sc = go.Figure(go.Scatter(
            x=active.Volume.clip(lower=1), y=active.Score, mode="markers",
            marker=dict(size=(active.Volume.clip(lower=1) ** 0.22) * 4 + 6,
                        color=active.Score, colorscale=[[0, "#3A5068"], [0.4, TEAL], [0.7, AMBER], [1, HOT]],
                        cmin=0, cmax=10, line=dict(width=0.5, color=BG), opacity=0.92),
            customdata=active[["Market", "Tier"]],
            hovertemplate="<b>%{customdata[1]}</b> · %{y}/10<br>%{customdata[0]}<br>$%{x:,.0f}<extra></extra>",
        ))
        sc.update_layout(title="SIGNAL MAP · VOLUME × CONVICTION")
        sc.update_xaxes(type="log", title="volume (USD, log)")
        sc.update_yaxes(range=[0, 10.5], title="conviction")
        st.plotly_chart(style_fig(sc), use_container_width=True)

    left2, right2 = st.columns([1, 1])
    with left2:
        st.markdown('<div class="sec-h" style="margin-top:.2rem">UPCOMING CATALYSTS</div>', unsafe_allow_html=True)
        st.markdown('<div class="hint">Your schedule of what resolves next, soonest first. The number on the right is conviction — when a row lands, that\'s when the catalyst hits.</div>', unsafe_allow_html=True)
        upcoming = active[active["Days to expiry"].notna() & (active["Days to expiry"] >= 0)]
        if upcoming.empty:
            st.caption("No upcoming signals with a future expiry date yet.")
        else:
            st.markdown(agenda_html(upcoming), unsafe_allow_html=True)

        st.markdown('<div class="hint">How the market prices high-conviction bets — clustered low means the market expects the bad outcome not to happen.</div>', unsafe_allow_html=True)
        buckets = pd.cut(active.Prob.dropna(), bins=[0, .2, .4, .6, .8, 1.0],
                          labels=["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"], include_lowest=True)
        counts = buckets.value_counts().reindex(["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"], fill_value=0)
        hist = go.Figure(go.Bar(x=counts.index, y=counts.values, marker=dict(color=TEAL),
                                 text=counts.values, textposition="outside", textfont=dict(color=MUTED),
                                 hovertemplate="%{x}<br>%{y} signals<extra></extra>"))
        hist.update_layout(title="PROBABILITY DISTRIBUTION · ACTIVE SIGNALS")
        st.plotly_chart(style_fig(hist, h=260), use_container_width=True)

    with right2:
        st.markdown('<div class="hint">Where the active signals sit across your four holdings — a glance version of the exposure cards above.</div>', unsafe_allow_html=True)
        exp_counts = {t: int(active.Tickers.apply(lambda ts: t in ts).sum()) for t in HOLDINGS}
        exp_counts = {k: v for k, v in exp_counts.items() if v > 0}
        if not exp_counts:
            st.caption("No ticker-tagged signals yet.")
        else:
            donut = go.Figure(go.Pie(
                labels=list(exp_counts.keys()), values=list(exp_counts.values()), hole=.62,
                marker=dict(colors=[heat(int(active[active.Tickers.apply(lambda ts: t in ts)].Score.max())) for t in exp_counts],
                            line=dict(color=BG, width=2)),
                textfont=dict(color=TXT), hovertemplate="%{label}: %{value} signals<extra></extra>",
            ))
            donut.update_layout(title="TICKER BREAKDOWN")
            st.plotly_chart(style_fig(donut, h=300), use_container_width=True)

        st.markdown('<div class="hint">Average conviction per scan day. Rising = the market\'s getting hotter for BIT; needs a few days of scans to mean much.</div>', unsafe_allow_html=True)
        by_day = active.groupby("Scanned").Score.mean().sort_index()
        if len(by_day) < 2:
            st.caption("Not enough scan history yet — check back after a few days of scanning.")
        else:
            trend = go.Figure(go.Scatter(
                x=by_day.index, y=by_day.values, mode="lines+markers",
                line=dict(color=AMBER, width=2), marker=dict(size=7, color=AMBER, line=dict(color=BG, width=1)),
                fill="tozeroy", fillcolor="rgba(255,178,62,.08)",
                hovertemplate="%{x}<br>avg conviction %{y:.1f}<extra></extra>",
            ))
            trend.update_layout(title="CONVICTION OVER TIME")
            trend.update_yaxes(range=[0, 10])
            st.plotly_chart(style_fig(trend, h=280), use_container_width=True)

    st.markdown('<div class="sec-h">SIGNALS</div>', unsafe_allow_html=True)
    st.markdown('<div class="hint">Every relevant market, hottest first. 8–10 = direct hit on a holding · 5–7 = sector · 3–4 = macro. Filter, then watch the ones expiring soon.</div>', unsafe_allow_html=True)
    fc = st.columns([1.4, 1.4, 1, 1.2])
    sectors = fc[0].multiselect("SECTOR", sorted(df.Sector.unique()))
    tickers = fc[1].multiselect("TICKER", list(HOLDINGS))
    min_score = fc[2].slider("MIN CONVICTION", 0, 10, 5)
    sort_by = fc[3].selectbox("SORT BY", ["Conviction", "Volume", "Days to expiry"])

    view = df[df.Score >= min_score]
    if sectors:
        view = view[view.Sector.isin(sectors)]
    if tickers:
        view = view[view.Tickers.apply(lambda ts: any(t in ts for t in tickers))]
    view = view.sort_values(
        {"Conviction": "Score", "Volume": "Volume", "Days to expiry": "Days to expiry"}[sort_by],
        ascending=(sort_by == "Days to expiry"))

    show = view.assign(Tickers=view.Tickers.apply(lambda ts: ", ".join(ts) if ts else "—"))
    styler = (show[["Score", "Tier", "Sector", "Tickers", "Market", "Prob", "Volume", "Days to expiry"]]
              .style
              .map(lambda v: f"color:{heat(v)}; font-weight:700", subset=["Score"])
              .format({"Prob": "{:.0%}", "Volume": "${:,.0f}", "Days to expiry": "{:.0f}d"}, na_rep="—"))
    st.dataframe(styler, use_container_width=True, hide_index=True, height=460,
                 column_config={"Market": st.column_config.TextColumn(width="large")})
    st.caption(f"{len(view)} signals shown · {n_markets:,} markets scanned")

with news_tab:
    st.markdown('<div class="sec-h">WORLD NEWS · PORTFOLIO READ-THROUGH</div>', unsafe_allow_html=True)
    st.markdown('<div class="hint">Today\'s headlines, each scored 0–5 for how much it moves a holding. Green = good for the stock, red = bad, grey = noise. Number = size of the effect.</div>', unsafe_allow_html=True)
    stance_c = {"bullish": "#46E08B", "bearish": HOT, "neutral": MUTED}
    with st.spinner("READING THE WIRES…"):
        wires = load_news()
    if not wires:
        st.info("Couldn't fetch headlines right now. Try again shortly.")
    else:
        only_relevant = st.toggle("Portfolio-relevant only (impact ≥ 2)", value=True)
        shown = [w for w in wires if w["impact"] >= 2] if only_relevant else wires
        for w in shown:
            c = stance_c.get(w["stance"], MUTED) if w["impact"] else "#3A5068"
            tk = " · " + ", ".join(w["tickers"]) if w["tickers"] else ""
            link = f'<a href="{w["link"]}" target="_blank">{w["title"]}</a>' if w["link"] else w["title"]
            note = f' — <span class="note">{w["note"]}</span>' if w.get("note") else ""
            st.markdown(
                f'<div class="news" style="--c:{c}"><div class="imp">{w["impact"]}</div>'
                f'<div><div class="ttl">{link}</div>'
                f'<div class="meta"><span class="stance">{w["stance"].upper()}{tk}</span>{note}</div></div></div>',
                unsafe_allow_html=True)
        st.caption(f"{len(shown)} headlines · scored for effect on BIT holdings · refreshes every 30 min")

with ask:
    st.markdown('<div class="sec-h">ASK THE DESK</div>', unsafe_allow_html=True)
    st.markdown('<div class="hint">Plain-English questions — answers come only from the scanned signals and latest brief, never the open web. It says so when it doesn\'t know.</div>', unsafe_allow_html=True)
    if "chat" not in st.session_state:
        st.session_state.chat = []
    for m in st.session_state.chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    if q := st.chat_input("e.g. Which signals threaten IREN? What's the Fed read-through for HOOD?"):
        st.session_state.chat.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("CONSULTING THE DESK…"):
                from src import chat as deskchat
                a = deskchat.answer(q, st.session_state.chat[-7:-1])
            st.markdown(a)
        st.session_state.chat.append({"role": "assistant", "content": a})

with brief:
    st.markdown('<div class="sec-h">DAILY BRIEF</div>', unsafe_allow_html=True)
    st.markdown('<div class="hint">The day\'s top signals written up as an analyst note — lead catalyst, then implications by sector.</div>', unsafe_allow_html=True)
    if not rep:
        st.info("No briefs yet. Run `python3 -m src.reports` after scoring signals.")
    else:
        pick = st.selectbox("BRIEF DATE", [r["report_date"] for r in rep])
        st.markdown(next(r["content"] for r in rep if r["report_date"] == pick))
