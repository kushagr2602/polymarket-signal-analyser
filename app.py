import os
import sys
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

# On Streamlit Cloud secrets live in st.secrets, not env vars; mirror them so the
# env-based src modules work unchanged. Locally (.env) this is a harmless no-op.
try:
    for _k in ("SUPABASE_URL", "SUPABASE_KEY", "OPENAI_API_KEY"):
        if _k in st.secrets:
            os.environ.setdefault(_k, str(st.secrets[_k]))
except Exception:
    pass

from src import database

from src import config as wcfg

WATCHLIST = wcfg.get_watchlist()
HOLDINGS = WATCHLIST["tickers"]  # ticker → description, user-configurable in the sidebar

# Two palettes; the sidebar Theme toggle picks one. CSS reads these as custom properties,
# charts + inline styles read the same values from Python. Conviction stays a blue ramp;
# in light mode it darkens (deeper blue = higher) so it reads on paper.
PALETTES = {
    "Dark": dict(bg="#151515", surface="#1B1B1B", line="#2C2C2C", line2="#242424", hair2="#434343",
                 text="#FDFDFD", muted="#918A7C", soft="#BDBAB6", accent="#5BC5F2", sand="#CDC6B5",
                 red="#EA384C", rule="#FDFDFD", heat=("#5BC5F2", "#4391B4", "#235165", "#434343"),
                 bar="#4391B4", scale=[[0, "#434343"], [0.4, "#235165"], [0.7, "#4391B4"], [1, "#5BC5F2"]]),
    "Light": dict(bg="#F4F2EC", surface="#ECEAE2", line="#DCD8CE", line2="#E6E2D8", hair2="#C9C4B8",
                  text="#1A1A17", muted="#6B665E", soft="#55504A", accent="#17698F", sand="#6B665E",
                  red="#B23B2E", rule="#1A1A17", heat=("#0C447C", "#185FA5", "#4391B4", "#B4B2A9"),
                  bar="#185FA5", scale=[[0, "#B4B2A9"], [0.4, "#4391B4"], [0.7, "#185FA5"], [1, "#0C447C"]]),
}
C = PALETTES["Dark"]  # rebound below once the theme is read (after set_page_config)


def heat(score: int) -> str:  # conviction as blue intensity (theme-aware via C)
    h = C["heat"]
    return h[0] if score >= 8 else h[1] if score >= 5 else h[2] if score >= 3 else h[3]


def tier(score: int) -> str:
    return ("Direct catalyst" if score >= 8 else "Sector impact" if score >= 5
            else "Macro signal" if score >= 3 else "Weak")


def agenda_html(up) -> str:
    """Upcoming signals as a grouped schedule, soonest first."""
    up = up.drop_duplicates("Market").sort_values("Days to expiry").head(14)
    order = ["This week", "This month", "Next 3 months", "Later"]
    groups: dict[str, list] = {}
    for _, r in up.iterrows():
        d = r["Days to expiry"]
        h = order[0] if d <= 7 else order[1] if d <= 31 else order[2] if d <= 93 else order[3]
        groups.setdefault(h, []).append(r)
    html = '<div class="agenda">'
    for h in order:
        if h not in groups:
            continue
        html += f'<div class="ag-h">{h} · {len(groups[h])}</div>'
        for r in groups[h]:
            d = int(r["Days to expiry"])
            when = "today" if d == 0 else f"{d}d"
            tk = r["Tickers"][0] if r["Tickers"] else "—"
            html += (f'<div class="ag-row"><span class="ag-when">{when}</span>'
                     f'<span class="ag-q">{r["Market"][:58]}</span>'
                     f'<span class="ag-tk">{tk}</span>'
                     f'<span class="ag-s" style="color:{heat(r["Score"])}">{r["Score"]}</span></div>')
    return html + "</div>"


st.set_page_config(page_title="Polymarket Signal Analyser", page_icon="◆",
                   layout="wide", initial_sidebar_state="expanded")

THEME = st.session_state.get("theme", "Dark")
C = PALETTES[THEME]
BG, LINE, LINE2, TXT, MUTED, BLUE, RED = C["bg"], C["line"], C["line2"], C["text"], C["muted"], C["accent"], C["red"]

_root = (":root{" + "".join(f"--{k}:{C[k]};" for k in
         ("bg", "surface", "line", "line2", "hair2", "text", "muted", "soft", "accent", "sand", "rule")) + "}")

st.markdown(f"<style>{_root}" + """
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=JetBrains+Mono:wght@400;500&display=swap');
html, body, [class*="css"] { font-family:'Archivo', Helvetica, Arial, sans-serif; color:var(--text); }
#MainMenu, footer { visibility:hidden; }
[data-testid="stHeader"] { background:transparent; }
.stApp { background:var(--bg); }
[data-testid="stSidebar"] { background:var(--surface); border-right:1px solid var(--line); }
.block-container { padding-top:2.2rem; padding-bottom:4rem; max-width:1280px; }

.mh { border-top:2px solid var(--rule); border-bottom:1px solid var(--line); padding:1.05rem 0 1rem;
      display:flex; align-items:baseline; justify-content:space-between; }
.mh .name { font-weight:700; font-size:1.12rem; letter-spacing:.22em; color:var(--text); }
.mh .name b { color:var(--accent); font-weight:700; }
.mh .name .sub { color:var(--muted); font-weight:500; }
.mh .meta { font-family:'JetBrains Mono', monospace; font-size:.65rem; letter-spacing:.06em; color:var(--muted); }
.mh .meta .fresh { color:var(--accent); }
.dek { font-family:'Newsreader', serif; font-style:italic; font-size:1.02rem; color:var(--soft); margin:.85rem 0 2rem; }

.kpi-grid { display:grid; grid-template-columns:repeat(5,1fr); border-top:1px solid var(--line);
            border-bottom:1px solid var(--line); margin-bottom:2.2rem; }
.kpi { padding:1.05rem 1.15rem; border-left:1px solid var(--line); }
.kpi:first-child { border-left:none; padding-left:0; }
.kpi .v { font-family:'Newsreader', serif; font-weight:500; font-size:1.9rem; line-height:1;
          color:var(--text); font-variant-numeric:lining-nums tabular-nums; }
.kpi .v.blue { color:var(--accent); }
.kpi .l { font-family:'JetBrains Mono', monospace; font-size:.6rem; letter-spacing:.14em;
          text-transform:uppercase; color:var(--muted); margin-top:.5rem; }

.sec-h { font-family:'JetBrains Mono', monospace; font-size:.66rem; font-weight:500; letter-spacing:.2em;
         text-transform:uppercase; color:var(--text); border-bottom:1px solid var(--line);
         padding-bottom:.45rem; margin:2.4rem 0 .3rem; }
.sec-h em { color:var(--accent); font-style:normal; }
.hint { font-size:.78rem; color:var(--muted); margin:.45rem 0 1rem; line-height:1.5; }

.pos-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:1.4rem; }
.pos { border-top:2px solid var(--c); padding-top:.7rem; }
.pos .tkr { font-weight:700; font-size:1.18rem; letter-spacing:.04em; color:var(--text); }
.pos .sec { font-family:'JetBrains Mono', monospace; font-size:.6rem; letter-spacing:.1em;
            text-transform:uppercase; color:var(--muted); margin-top:.1rem; }
.pos .row { display:flex; justify-content:space-between; align-items:baseline; margin-top:.85rem; }
.pos .n { font-family:'Newsreader', serif; font-weight:500; font-size:1.75rem; line-height:1; color:var(--c); }
.pos .nl { font-family:'JetBrains Mono', monospace; font-size:.62rem; letter-spacing:.04em; color:var(--muted); margin-left:.3rem; }
.pos .mx { font-family:'JetBrains Mono', monospace; font-size:.62rem; color:var(--muted); }

.news { display:flex; gap:1rem; align-items:flex-start; padding:.85rem 0; border-bottom:1px solid var(--line2); }
.news .imp { font-family:'Newsreader', serif; font-weight:500; font-size:1.45rem; line-height:1.1;
             color:var(--c); min-width:1.3rem; text-align:center; }
.news .ttl { font-size:.94rem; line-height:1.45; color:var(--text); }
.news .ttl a { color:inherit; text-decoration:none; border-bottom:1px solid var(--hair2); }
.news .ttl a:hover { color:var(--accent); border-color:var(--accent); }
.news .meta { margin-top:.35rem; font-family:'JetBrains Mono', monospace; font-size:.63rem;
              letter-spacing:.04em; color:var(--muted); }
.news .stance { color:var(--c); font-weight:500; text-transform:uppercase; }
.news .note { color:var(--soft); }

.agenda { border:1px solid var(--line); }
.ag-h { font-family:'JetBrains Mono', monospace; font-size:.6rem; letter-spacing:.14em;
        text-transform:uppercase; color:var(--muted); background:var(--surface); padding:.45rem .9rem; }
.ag-row { display:flex; align-items:center; gap:.85rem; padding:.55rem .9rem; border-top:1px solid var(--line2); }
.ag-when { font-family:'JetBrains Mono', monospace; font-size:.63rem; color:var(--muted); min-width:44px; text-align:right; }
.ag-q { flex:1; font-size:.88rem; line-height:1.35; color:var(--text); }
.ag-tk { font-family:'JetBrains Mono', monospace; font-size:.6rem; color:var(--sand); }
.ag-s { font-family:'Newsreader', serif; font-weight:500; font-size:1.1rem; min-width:20px; text-align:center; }

.stTabs [data-baseweb="tab-list"] { gap:1.6rem; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"] { font-family:'JetBrains Mono', monospace; font-size:.68rem;
                               letter-spacing:.16em; text-transform:uppercase; color:var(--muted);
                               padding-left:0; padding-right:0; }
.stTabs [aria-selected="true"] { color:var(--text); }

/* dataframe follows the theme (glide-data-grid custom props) */
[data-testid="stDataFrame"] { --gdg-bg-cell:var(--bg); --gdg-bg-cell-medium:var(--surface);
    --gdg-text-dark:var(--text); --gdg-text-medium:var(--muted); --gdg-text-light:var(--muted);
    --gdg-bg-header:var(--surface); --gdg-bg-header-hovered:var(--line); --gdg-bg-header-has-focus:var(--line);
    --gdg-border-color:var(--line); --gdg-horizontal-border-color:var(--line2); --gdg-text-header:var(--muted); }

/* ---- sidebar + filter controls: square hairline inputs, mono labels, quiet tags ---- */
[data-testid="stSidebarContent"] { padding:1.2rem 1.25rem 2rem; }
[data-testid="stSidebar"] hr { display:none; }
.sb-h { font-family:'JetBrains Mono', monospace; font-size:.66rem; font-weight:500; letter-spacing:.2em;
        text-transform:uppercase; color:var(--text); border-bottom:1px solid var(--line);
        padding-bottom:.45rem; margin:1.7rem 0 .6rem; }
.sb-h.first { margin-top:.4rem; }
[data-testid="stWidgetLabel"] p { font-family:'JetBrains Mono', monospace; font-size:.6rem; font-weight:500;
        letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }
[data-testid="stCaptionContainer"] { color:var(--muted); font-size:.74rem; line-height:1.5; }
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div:first-child {
    background:var(--bg) !important; border:1px solid var(--line) !important; border-radius:2px !important;
    box-shadow:none !important; }
[data-baseweb="base-input"] { background:transparent !important; border:none !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within,
[data-baseweb="select"] > div:first-child:focus-within { border-color:var(--accent) !important; }
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea, [data-baseweb="select"] input {
    color:var(--text) !important; font-size:.86rem; }
[data-baseweb="tag"] { background:transparent !important; border:1px solid var(--hair2); border-radius:2px !important;
    margin:2px 4px 2px 0 !important; height:1.5rem; }
[data-baseweb="tag"] span { color:var(--text) !important; font-family:'JetBrains Mono', monospace;
    font-size:.66rem; letter-spacing:.04em; }
[data-baseweb="tag"] svg { fill:var(--muted); }
[data-baseweb="tag"]:hover { border-color:var(--accent); }
[data-testid="stSidebar"] [data-baseweb="select"] > div:first-child { max-height:8.2rem; overflow-y:auto; }
[data-baseweb="popover"] [data-baseweb="menu"] { background:var(--surface) !important; border:1px solid var(--line); border-radius:2px; }
[data-baseweb="popover"] li { color:var(--text); font-size:.84rem; }
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"] { width:100%; border-radius:2px; box-shadow:none; min-height:0; padding:.55rem .8rem;
    background:transparent; color:var(--text); border:1px solid var(--hair2); }
[data-testid="stBaseButton-secondary"] p, [data-testid="stBaseButton-primary"] p { font-family:'JetBrains Mono', monospace; font-size:.64rem; letter-spacing:.14em;
    text-transform:uppercase; }
[data-testid="stBaseButton-secondary"]:hover:not(:disabled) { border-color:var(--accent); color:var(--accent); background:transparent; }
[data-testid="stBaseButton-primary"] { background:var(--text); color:var(--bg); border-color:var(--text); }
[data-testid="stBaseButton-primary"]:hover:not(:disabled) { background:var(--accent); border-color:var(--accent); color:var(--bg); }
[data-testid="stBaseButton-secondary"]:disabled, [data-testid="stBaseButton-primary"]:disabled { opacity:.38; }
[data-testid="stSidebar"] .stButton { margin-top:.35rem; }
/* native widgets inherit the dark base config's white text — pin them to the active palette */
[data-baseweb="radio"] p, [data-testid="stExpander"] summary, [data-testid="stExpander"] summary p,
[data-testid="stToolbar"], [data-testid="stToolbar"] button, [data-testid="stToolbar"] span,
[data-testid="stSidebarCollapseButton"] button, [data-testid="stSlider"] [data-testid="stTickBarMin"],
[data-testid="stSlider"] [data-testid="stTickBarMax"], [data-testid="stSliderThumbValue"] { color:var(--text) !important; }
[data-testid="stExpander"] details { border:1px solid var(--line); border-radius:2px; }
::placeholder { color:var(--muted) !important; opacity:1; }
.hot { border-top:2px solid var(--c); padding-top:.7rem; min-height:12.2rem; }
.hot .top { display:flex; justify-content:space-between; font-family:'JetBrains Mono', monospace;
            font-size:.6rem; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }
.hot .top .soon { color:var(--red); }
.hot .nm { font-weight:700; font-size:1.08rem; margin-top:.4rem; color:var(--text); }
.hot .bar { height:3px; background:var(--line); margin:.65rem 0 .5rem; }
.hot .bar i { display:block; height:100%; background:var(--c); }
.hot .st { font-family:'JetBrains Mono', monospace; font-size:.62rem; color:var(--muted); }
.hot .lead { font-size:.84rem; line-height:1.4; color:var(--soft); margin:.65rem 0 .4rem; }
.hot .tk { font-family:'JetBrains Mono', monospace; font-size:.6rem; color:var(--sand); }
.st-key-filters { border-top:1px solid var(--line); border-bottom:1px solid var(--line);
    padding:1rem 0 .4rem; margin-bottom:1.1rem; }
</style>""", unsafe_allow_html=True)


def thinking_orb(label: str, size: int = 64, speed: float = 0.75, height: int = 90):
    """Rotating dot-sphere loading indicator (self-contained canvas — no JS deps),
    in the spirit of https://orbs.jakubantalik.com/'s ThinkingOrb."""
    components.html(f"""
    <div style="display:flex;align-items:center;gap:14px;height:{size}px;
                font-family:inherit;">
      <canvas id="orb" width="{size * 2}" height="{size * 2}"
              style="width:{size}px;height:{size}px;"></canvas>
      <span style="color:{C['text']};font-size:14px;letter-spacing:.02em;opacity:.8;">{label}</span>
    </div>
    <script>
    (function() {{
        const canvas = document.getElementById("orb");
        const ctx = canvas.getContext("2d");
        const size = {size}, dpr = window.devicePixelRatio || 1;
        canvas.width = size * 2 * dpr; canvas.height = size * 2 * dpr;
        ctx.scale(dpr, dpr);
        const N = 130, pts = [];
        for (let i = 0; i < N; i++) {{
            const y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y);
            const theta = i * Math.PI * (3 - Math.sqrt(5));
            pts.push([Math.cos(theta) * r, y, Math.sin(theta) * r]);
        }}
        let t = 0;
        const speed = {speed}, color = "{C['accent']}";
        (function frame() {{
            t += 0.016 * speed;
            ctx.clearRect(0, 0, size * 2, size * 2);
            const cx = size, cy = size, R = size * 0.82;
            const cosA = Math.cos(t), sinA = Math.sin(t);
            const cosB = Math.cos(t * 0.6), sinB = Math.sin(t * 0.6);
            const proj = pts.map(([x, y, z]) => {{
                const x1 = x * cosA - z * sinA, z1 = x * sinA + z * cosA;
                const y1 = y * cosB - z1 * sinB, z2 = y * sinB + z1 * cosB;
                return [x1, y1, z2];
            }}).sort((a, b) => a[2] - b[2]);
            for (const [x, y, z] of proj) {{
                const s = (z + 1.6) / 2.6;
                ctx.beginPath();
                ctx.globalAlpha = 0.2 + 0.8 * s;
                ctx.fillStyle = color;
                ctx.arc(cx + x * R, cy + y * R, 1.1 * s + 0.3, 0, Math.PI * 2);
                ctx.fill();
            }}
            requestAnimationFrame(frame);
        }})();
    }})();
    </script>
    """, height=height)


@st.cache_data(ttl=600, show_spinner=False)
def load():
    db = database.get_client()
    sig = database.get_signals()  # deduped + expired-dropped in the shared layer
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
            "Score": s["relevance_score"], "Sector": s.get("sector") or "—",
            "Tickers": s.get("affected_tickers") or [], "Market": m.get("question", ""),
            "Prob": m.get("probability"), "Volume": m.get("volume_usd") or 0,
            "Days to expiry": days, "Tier": tier(s["relevance_score"]),
            "Reasoning": s.get("reasoning", ""),
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600, show_spinner=False)
def suggest_tickers(industry: str) -> dict:
    """LLM → up to 8 liquid, US-listed tickers central to an industry/theme, with short labels."""
    import json
    from src import llm
    if llm.client is None or not industry.strip():
        return {}
    prompt = (f'List up to 8 liquid, US-listed public-company stock tickers most central to "{industry}". '
              'No ETFs or funds. Return JSON {"tickers": {"TICKER": "3-5 word business description"}}.')
    try:
        r = llm.chat("smart", messages=[{"role": "user", "content": prompt}],
                     response_format={"type": "json_object"})
        return {k.upper(): v for k, v in json.loads(r.choices[0].message.content).get("tickers", {}).items()}
    except Exception:
        return {}


with st.sidebar:
    st.markdown('<div class="sb-h first">Theme</div>', unsafe_allow_html=True)
    st.radio("Theme", ["Dark", "Light"], key="theme", horizontal=True, label_visibility="collapsed")
    st.markdown('<div class="sb-h">Watchlist</div>', unsafe_allow_html=True)
    st.caption("New scans score against this list. Existing signals keep their original tags.")

    picked = dict(WATCHLIST["tickers"])  # {ticker: desc}
    keep = st.multiselect("Tracking", options=list(picked), default=list(picked),
                          help="Deselect a ticker to drop it.")
    picked = {t: picked[t] for t in keep}

    industry = st.text_input("Add by industry or theme", placeholder="e.g. semiconductors, biotech, defense")
    if industry.strip():
        with st.spinner("Finding tickers…"):
            sugg = {t: d for t, d in suggest_tickers(industry.strip()).items() if t not in picked}
        if sugg:
            add = st.multiselect(f"Suggested for “{industry.strip()}”", options=list(sugg),
                                 format_func=lambda t: f"{t} — {sugg[t]}")
            for t in add:
                picked[t] = sugg[t]
        else:
            st.caption("No new tickers found — try a broader term.")

    sect_text = st.text_area("Focus sectors — one per line", "\n".join(WATCHLIST["sectors"]), height=120)
    if st.button("Save watchlist", type="primary", width="stretch"):
        sectors = [s.strip() for s in sect_text.splitlines() if s.strip()]
        if picked and sectors:
            wcfg.save_watchlist(picked, sectors)
            st.cache_data.clear()
            st.rerun()
        else:
            st.error("Keep at least one ticker and one sector.")

    st.markdown('<div class="sb-h">Data</div>', unsafe_allow_html=True)
    from src.scheduler import RESCAN_LOCK
    rescanning = os.path.exists(RESCAN_LOCK)
    if rescanning:
        thinking_orb("Rescanning markets…", size=28, height=44)
        st.caption("Give it a few minutes, then hit Reload.")
    if st.button("↻ Rescan markets", disabled=rescanning, width="stretch",
                 help="Re-score the top markets against the current watchlist. ~5 min; runs in the background."):
        import subprocess
        subprocess.Popen([sys.executable, "-m", "src.scheduler", "--rescore"],
                         cwd=os.path.dirname(os.path.abspath(__file__)),
                         stdout=open("/tmp/rescan.log", "a"), stderr=subprocess.STDOUT)
        st.success("Rescan started — scoring the top markets against your watchlist. Give it a few minutes, then hit Reload.")
    if st.button("⟳ Reload data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

_orb = st.empty()
with _orb.container():
    thinking_orb("Loading signals…")
sig, rep, n_markets = load()
_orb.empty()
df = to_df(sig)
last_scan = max((s.get("markets") or {}).get("fetched_at", "") for s in sig) if sig else ""
stamp = last_scan[:16].replace("T", " ") + " UTC" if last_scan else "no scans"


def _ago(iso: str) -> str:
    if not iso:
        return ""
    try:
        secs = (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds()
    except ValueError:
        return ""
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if secs < 86400:
        h = int(secs // 3600)
        return f"{h} hr ago"
    return f"{int(secs // 86400)} d ago"


ago = _ago(last_scan)
today = datetime.now(timezone.utc).strftime("%d %b %Y")
st_autorefresh(interval=60_000, key="clock")  # rerun each minute so "N min ago" counts up live (data stays cached)

st.markdown(f"""
<div class="mh">
  <span class="name"><b>POLYMARKET</b> <span class="sub">SIGNAL ANALYSER</span></span>
  <span class="meta">{today} · last scan {stamp}{f' · <span class="fresh">{ago}</span>' if ago else ''}</span>
</div>
<div class="dek">An agentic scanner that reads prediction markets for equity signals — watching {", ".join(HOLDINGS)} (edit in the sidebar).</div>
""", unsafe_allow_html=True)

if rescanning:
    thinking_orb("Rescanning markets against your watchlist…", size=40, height=56)

with st.expander("New here? How to read this dashboard"):
    try:
        st.markdown(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "HOW_TO_READ.md")).read())
    except OSError:
        st.caption("HOW_TO_READ.md not found.")

if df.empty:
    st.info("No signals yet. Run `python3 -m src.scheduler --once` to scan.")
    st.stop()

active = df[df.Score >= 5]
high = df[df.Score >= 8]

st.markdown(f"""
<div class="kpi-grid">
  <div class="kpi"><div class="v">{n_markets:,}</div><div class="l">Markets scanned</div></div>
  <div class="kpi"><div class="v blue">{len(active)}</div><div class="l">Active signals ≥5</div></div>
  <div class="kpi"><div class="v">{len(high)}</div><div class="l">High conviction ≥8</div></div>
  <div class="kpi"><div class="v">${active.Volume.sum()/1e6:,.0f}M</div><div class="l">Volume · active</div></div>
  <div class="kpi"><div class="v">{active.Score.mean() if len(active) else 0:.1f}</div><div class="l">Avg conviction</div></div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="sec-h">Watchlist exposure</div>', unsafe_allow_html=True)
st.markdown('<div class="hint">Big number = how many live signals mention this stock. “peak conviction” = the single strongest one\'s score (0–10). Lots of signals <em>and</em> a high peak = the most brewing.</div>', unsafe_allow_html=True)
if not active.Tickers.apply(lambda ts: any(t in HOLDINGS for t in ts)).any():
    st.caption("No signals tagged to your watchlist yet — run `python3 -m src.scheduler --once` against a fresh database to populate it.")
cards = ""
for tkr, sec in HOLDINGS.items():
    hit = active[active.Tickers.apply(lambda ts: tkr in ts)]
    mx = int(hit.Score.max()) if len(hit) else 0
    c = heat(mx) if len(hit) else "#434343"
    cards += (f'<div class="pos" style="--c:{c}"><div class="tkr">{tkr}</div>'
              f'<div class="sec">{sec}</div><div class="row">'
              f'<span><span class="n">{len(hit)}</span><span class="nl">signals</span></span>'
              f'<span class="mx">peak conviction {mx}/10</span></div></div>')
st.markdown(f'<div class="pos-grid">{cards}</div>', unsafe_allow_html=True)


def style_fig(fig, h=300):
    fig.update_layout(
        height=h, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED, family="JetBrains Mono", size=11),
        margin=dict(l=10, r=10, t=12, b=10), showlegend=False,
    )
    fig.update_xaxes(gridcolor=LINE2, zeroline=False, linecolor=LINE)
    fig.update_yaxes(gridcolor=LINE2, zeroline=False, linecolor=LINE)
    return fig


desk, news_tab, ask, brief = st.tabs(["Signal desk", "World news", "Ask the desk", "Daily brief"])

def hot_topics(d: pd.DataFrame, n: int = 6) -> list[dict]:
    """Rank sectors by heat = Σ (conviction − 4) × log10(volume) over active signals.
    Current concentration only — the schema keeps no history, so this is not week-over-week momentum."""
    import math
    a = d[(d.Score >= 5) & (d.Sector != "—")].copy()
    if a.empty:
        return []
    a["w"] = (a.Score - 4) * a.Volume.clip(lower=0).add(10).apply(math.log10)
    out = []
    for sec, sub in a.groupby("Sector"):
        lead = sub.sort_values(["Score", "Volume"], ascending=False).iloc[0]
        days = pd.to_numeric(sub["Days to expiry"], errors="coerce").dropna()
        days = days[days >= 0]
        out.append(dict(sector=sec, w=sub.w.sum(), n=len(sub), vol=sub.Volume.sum(), peak=int(sub.Score.max()),
                        lead=lead.Market, tk=sorted({t for ts in sub.Tickers for t in ts})[:4],
                        soon=int(days.min()) if len(days) else None))
    top = max(r["w"] for r in out)
    for r in out:
        r["heat"] = round(100 * r["w"] / top)
    return sorted(out, key=lambda r: -r["w"])[:n]


def _focus_sector(sector: str):
    st.session_state["f_sector"] = [sector]


with desk:
    st.markdown('<div class="sec-h" style="margin-top:1.2rem">Hot topics</div>', unsafe_allow_html=True)
    st.markdown('<div class="hint">Segments ranked by heat — how much conviction <em>and</em> money is stacked on them right now. '
                'Start with the top row; “Filter table” narrows <a href="#all-signals" style="color:var(--accent)">All signals</a> to that segment.</div>',
                unsafe_allow_html=True)
    import html as _html
    hot = hot_topics(df)
    if not hot:
        st.caption("No active signals to rank yet — run a scan.")
    for row_start in range(0, len(hot), 3):
        cols = st.columns(3, gap="medium")
        for col, (i, r) in zip(cols, enumerate(hot[row_start:row_start + 3], start=row_start)):
            soon = f'<span class="soon">closes in {r["soon"]}d</span>' if r["soon"] is not None and r["soon"] <= 14 else ""
            col.markdown(
                f'<div class="hot" style="--c:{heat(max(3, round(r["heat"] / 10)))}">'
                f'<div class="top"><span>#{i + 1} · heat {r["heat"]}</span>{soon}</div>'
                f'<div class="nm">{_html.escape(r["sector"])}</div>'
                f'<div class="bar"><i style="width:{r["heat"]}%"></i></div>'
                f'<div class="st">{r["n"]} signals · ${r["vol"] / 1e6:,.0f}M · peak {r["peak"]}/10</div>'
                f'<div class="lead">{_html.escape(r["lead"][:90])}</div>'
                f'<div class="tk">{" · ".join(r["tk"]) or "macro"}</div></div>', unsafe_allow_html=True)
            col.button("Filter table →", key=f"hot_{i}", on_click=_focus_sector, args=(r["sector"],), width="stretch")

    st.markdown('<div class="sec-h" style="margin-top:1.2rem">Signal heatmap</div>', unsafe_allow_html=True)
    st.markdown('<div class="hint">Each tile is a market, grouped by the stock it affects. Bigger = more money traded; green = high conviction, red = weak.</div>', unsafe_allow_html=True)
    # tradytics palette: red (weak) → teal-green (strong, their brand #26beaf), near-black tile gaps
    TRADY = [[0, "#b23b3b"], [0.32, "#8a5a2a"], [0.6, "#2f8f6a"], [1, "#26beaf"]]
    hm = active.copy()
    hm["Ticker"] = hm.Tickers.apply(lambda ts: ts[0] if ts else "Macro")
    ids, labels, parents, values, colors, cd = [], [], [], [], [], []
    for t in hm.Ticker.unique():
        sub = hm[hm.Ticker == t]
        ids.append(t); labels.append(t); parents.append(""); values.append(0.0)
        colors.append(float(sub.Score.mean())); cd.append(f"{len(sub)} signals · avg {sub.Score.mean():.1f}")
    for i, (_, r) in enumerate(hm.iterrows()):
        ids.append(f"m{i}"); labels.append(r.Market[:26]); parents.append(r.Ticker)
        values.append(max(float(r.Volume), 1.0)); colors.append(float(r.Score))
        cd.append(f"{r.Score}/10 · ${r.Volume:,.0f}<br>{r.Market}")
    tree = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values, customdata=cd,
        marker=dict(colors=colors, colorscale=TRADY, cmin=5, cmax=10, line=dict(width=2, color="#0b0d0d")),
        textfont=dict(family="Manrope", color="#FDFDFD", size=13), textposition="middle center",
        hovertemplate="<b>%{label}</b><br>%{customdata}<extra></extra>", tiling=dict(pad=3),
    ))
    tree.update_layout(height=400, margin=dict(l=0, r=0, t=6, b=0),
                       paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Manrope"))
    st.plotly_chart(tree, use_container_width=True)

    left, right = st.columns([1, 1.15], gap="large")
    with left:
        st.markdown('<div class="sec-h" style="margin-top:1.2rem">Sector conviction</div>', unsafe_allow_html=True)
        st.markdown('<div class="hint">Average conviction per theme; the count follows the dot.</div>', unsafe_allow_html=True)
        by_sec = active.groupby("Sector").Score.agg(["mean", "count"]).sort_values("mean")
        bar = go.Figure(go.Bar(
            x=by_sec["mean"], y=by_sec.index, orientation="h",
            marker=dict(color=[heat(round(v)) for v in by_sec["mean"]]),
            text=[f"{m:.1f} · {int(c)}" for m, c in zip(by_sec["mean"], by_sec["count"])],
            textposition="outside", textfont=dict(color=MUTED),
            hovertemplate="%{y}<br>avg conviction %{x:.1f}<extra></extra>",
        ))
        bar.update_xaxes(range=[0, 10])
        st.plotly_chart(style_fig(bar, h=280), use_container_width=True)
    with right:
        st.markdown('<div class="sec-h" style="margin-top:1.2rem">Signal map</div>', unsafe_allow_html=True)
        st.markdown('<div class="hint">One dot per market — up = matters more, right = more money traded. Top-right is the watchlist.</div>', unsafe_allow_html=True)
        sc = go.Figure(go.Scatter(
            x=active.Volume.clip(lower=1), y=active.Score, mode="markers",
            marker=dict(size=(active.Volume.clip(lower=1) ** 0.22) * 4 + 6,
                        color=active.Score, colorscale=C["scale"],
                        cmin=0, cmax=10, line=dict(width=0.5, color=BG), opacity=0.92),
            customdata=active[["Market", "Tier"]],
            hovertemplate="<b>%{customdata[1]}</b> · %{y}/10<br>%{customdata[0]}<br>$%{x:,.0f}<extra></extra>",
        ))
        sc.update_xaxes(type="log", title="volume (USD, log)")
        sc.update_yaxes(range=[0, 10.5], title="conviction")
        st.plotly_chart(style_fig(sc, h=280), use_container_width=True)

    left2, right2 = st.columns([1, 1], gap="large")
    with left2:
        st.markdown('<div class="sec-h">Upcoming catalysts</div>', unsafe_allow_html=True)
        st.markdown('<div class="hint">What resolves next, soonest first. The number is conviction — when a row lands, the catalyst hits.</div>', unsafe_allow_html=True)
        upcoming = active[active["Days to expiry"].notna() & (active["Days to expiry"] >= 0)]
        if upcoming.empty:
            st.caption("No upcoming signals with a future expiry date yet.")
        else:
            st.markdown(agenda_html(upcoming), unsafe_allow_html=True)
    with right2:
        st.markdown('<div class="sec-h">Market pricing</div>', unsafe_allow_html=True)
        st.markdown('<div class="hint">Yes-probability of each active signal, bucketed — where the market has already made up its mind.</div>', unsafe_allow_html=True)
        buckets = pd.cut(active.Prob.dropna(), bins=[0, .2, .4, .6, .8, 1.0],
                         labels=["0–20%", "20–40%", "40–60%", "60–80%", "80–100%"], include_lowest=True)
        counts = buckets.value_counts().reindex(["0–20%", "20–40%", "40–60%", "60–80%", "80–100%"], fill_value=0)
        hist = go.Figure(go.Bar(x=counts.index, y=counts.values, marker=dict(color=C["bar"]),
                                text=counts.values, textposition="outside", textfont=dict(color=MUTED),
                                hovertemplate="%{x}<br>%{y} signals<extra></extra>"))
        st.plotly_chart(style_fig(hist, h=300), use_container_width=True)

    st.markdown('<div id="all-signals" class="sec-h">All signals</div>', unsafe_allow_html=True)
    st.markdown('<div class="hint">8–10 direct hit on a holding · 5–7 sector · 3–4 macro. Filter, then watch what expires soon.</div>', unsafe_allow_html=True)
    with st.container(key="filters"):
        fc = st.columns([1.4, 1.4, 1, 1.2], gap="medium")
        sectors = fc[0].multiselect("Sector", sorted(df.Sector.unique()), placeholder="All sectors", key="f_sector")
        ticker_opts = sorted({t for ts in df.Tickers for t in ts} | set(HOLDINGS))
        tickers = fc[1].multiselect("Ticker", ticker_opts, placeholder="All tickers")
        min_score = fc[2].slider("Min conviction", 0, 10, 5)
        sort_by = fc[3].selectbox("Sort by", ["Conviction", "Volume", "Days to expiry"])

    view = df[df.Score >= min_score]
    if sectors:
        view = view[view.Sector.isin(sectors)]
    if tickers:
        view = view[view.Tickers.apply(lambda ts: any(t in ts for t in tickers))]
    view = view.sort_values(
        {"Conviction": "Score", "Volume": "Volume", "Days to expiry": "Days to expiry"}[sort_by],
        ascending=(sort_by == "Days to expiry"))

    show = view.assign(Tickers=view.Tickers.apply(lambda ts: ", ".join(ts) if ts else "—"))
    styler = (show[["Score", "Market", "Sector", "Tickers", "Prob", "Volume", "Days to expiry"]]
              .style
              .map(lambda v: f"color:{heat(v)}; font-weight:700", subset=["Score"])
              .format({"Prob": "{:.0%}", "Volume": "${:,.0f}", "Days to expiry": "{:.0f}d"}, na_rep="—"))
    st.dataframe(styler, use_container_width=True, hide_index=True, height=460,
                 column_config={"Market": st.column_config.TextColumn(width="large")})
    st.caption(f"{len(view)} signals · {n_markets:,} markets scanned")

with news_tab:
    st.markdown('<div class="sec-h" style="margin-top:1.2rem">World news · portfolio read-through</div>', unsafe_allow_html=True)
    st.markdown('<div class="hint">Headlines scored 0–5 for effect on a holding. Blue = supportive, red = adverse, grey = noise.</div>', unsafe_allow_html=True)
    stance_c = {"bullish": BLUE, "bearish": RED, "neutral": MUTED}
    with st.spinner("Reading the wires…"):
        wires = load_news()
    if not wires:
        st.info("Couldn't fetch headlines right now. Try again shortly.")
    else:
        only_relevant = st.toggle("Portfolio-relevant only (impact ≥ 2)", value=True)
        shown = [w for w in wires if w["impact"] >= 2] if only_relevant else wires
        for w in shown:
            c = stance_c.get(w["stance"], MUTED) if w["impact"] else "#434343"
            tk = " · " + ", ".join(w["tickers"]) if w["tickers"] else ""
            link = f'<a href="{w["link"]}" target="_blank">{w["title"]}</a>' if w["link"] else w["title"]
            note = f' — <span class="note">{w["note"]}</span>' if w.get("note") else ""
            st.markdown(
                f'<div class="news" style="--c:{c}"><div class="imp">{w["impact"]}</div>'
                f'<div><div class="ttl">{link}</div>'
                f'<div class="meta"><span class="stance">{w["stance"]}{tk}</span>{note}</div></div></div>',
                unsafe_allow_html=True)
        st.caption(f"{len(shown)} headlines · refreshes every 30 min")

with ask:
    st.markdown('<div class="sec-h" style="margin-top:1.2rem">Ask the desk</div>', unsafe_allow_html=True)
    st.markdown('<div class="hint">Answers come only from the scanned signals and the latest brief — never the open web.</div>', unsafe_allow_html=True)
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
            with st.spinner("Agent planning tool calls…"):
                from src import agent
                a, trace = agent.run(q, st.session_state.chat[-7:-1])
            if trace:
                st.caption("tools called: " + "  →  ".join(trace))
            st.markdown(a)
        st.session_state.chat.append({"role": "assistant", "content": a})

with brief:
    st.markdown('<div class="sec-h" style="margin-top:1.2rem">Daily brief</div>', unsafe_allow_html=True)
    st.markdown('<div class="hint">The day\'s top signals as an analyst note — lead catalyst first, then implications by sector.</div>', unsafe_allow_html=True)
    if not rep:
        st.info("No briefs yet. Run `python3 -m src.reports` after scoring signals.")
    else:
        pick = st.selectbox("Brief date", [r["report_date"] for r in rep])
        st.markdown(next(r["content"] for r in rep if r["report_date"] == pick))
