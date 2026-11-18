'use strict';
/* Polymarket Signal Analyser — front end. No framework, no build step: hash router + template strings.
   Data comes from server.py (/api/*); all numbers are computed server-side in src/views.py. */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const money = n => n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `$${Math.round(n / 1e6)}M` : n >= 1e3 ? `$${Math.round(n / 1e3)}K` : `$${Math.round(n)}`;
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
const enc = encodeURIComponent;
const ago = iso => {
  if (!iso) return '';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  return s < 90 ? 'just now' : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} hr ago` : `${Math.floor(s / 86400)} d ago`;
};

/* ---------- conviction colour: tradytics-style ramp, brick → amber → green → teal over 5..10 (red stays reserved for urgency) ---------- */
const RAMPS = { dark: ['#a24a3a', '#8f6a2a', '#2f8f6a', '#26beaf'], light: ['#9a3f30', '#8a5f14', '#1f7a55', '#0f8a7d'] };
const STOPS = [0, .32, .6, 1];
const theme = () => document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
function conv(score) {
  if (score == null || score < 5) return 'var(--muted)';
  const t = Math.min(1, (score - 5) / 5), R = RAMPS[theme()];
  let k = 0; while (k < 2 && t > STOPS[k + 1]) k++;
  const f = (t - STOPS[k]) / (STOPS[k + 1] - STOPS[k]), a = hex(R[k]), b = hex(R[k + 1]);
  return '#' + a.map((v, i) => Math.round(v + (b[i] - v) * f).toString(16).padStart(2, '0')).join('');
}
const scPill = s => `<span class="sc${s < 5 ? ' zero' : ''}" style="--c:${conv(s)}">${s}</span>`;

/* ---------- api / toast / tooltip ---------- */
const inflight = new Map();
function api(path, opts = {}) {  // identical GETs already in flight share one request (boot + Today both asked for /api/screen)
  if (opts.method && opts.method !== 'GET') return apiRaw(path, opts);
  if (!inflight.has(path)) inflight.set(path, apiRaw(path, opts).finally(() => inflight.delete(path)));
  return inflight.get(path);
}
async function apiRaw(path, opts = {}) {
  const r = await fetch(path, { method: opts.method || 'GET', headers: opts.body ? { 'Content-Type': 'application/json' } : {},
                                body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (!r.ok) {
    let m = r.statusText;
    try { m = (await r.json()).detail || m; } catch (e) { /* non-JSON error body */ }
    throw new Error(typeof m === 'string' ? m : 'Something went wrong.');
  }
  return r.json();
}
let toastT;
function toast(msg, isErr) {
  const t = $('#toast'); t.textContent = msg; t.className = 'toast on' + (isErr ? ' err' : '');
  clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('on'), 3400);
}
const tip = $('#tip');
document.addEventListener('mousemove', e => {
  const el = e.target.closest && e.target.closest('[data-tip]');
  if (!el) return tip.classList.remove('on');
  tip.textContent = el.dataset.tip; tip.classList.add('on');
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = e.clientX + 14, y = e.clientY + 16;
  if (x + w > innerWidth - 8) x = e.clientX - w - 14;
  if (y + h > innerHeight - 8) y = e.clientY - h - 14;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
});
addEventListener('scroll', () => tip.classList.remove('on'), { passive: true });

/* ---------- thinking orb: rotating dot-sphere loader (canvas, no deps) ---------- */
function orb(canvas, size, speed = .75) {
  const dpr = devicePixelRatio || 1;
  canvas.width = canvas.height = size * dpr; canvas.style.width = canvas.style.height = size + 'px';
  const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr);
  const N = Math.round(60 + size * 1.2), pts = [];
  for (let i = 0; i < N; i++) {
    const y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y), a = i * Math.PI * (3 - Math.sqrt(5));
    pts.push([Math.cos(a) * r, y, Math.sin(a) * r]);
  }
  const color = getComputedStyle(document.documentElement).getPropertyValue('--teal').trim() || '#26beaf';
  let t = Math.random() * 6;
  (function frame() {
    if (!canvas.isConnected) return;
    t += .016 * speed; ctx.clearRect(0, 0, size, size);
    const R = size * .45, c = size / 2, cA = Math.cos(t), sA = Math.sin(t), cB = Math.cos(t * .6), sB = Math.sin(t * .6);
    pts.map(([x, y, z]) => { const x1 = x * cA - z * sA, z1 = x * sA + z * cA; return [x1, y * cB - z1 * sB, y * sB + z1 * cB]; })
       .sort((a, b) => a[2] - b[2])
       .forEach(([x, y, z]) => {
         const s = (z + 1.6) / 2.6; ctx.globalAlpha = .18 + .82 * s; ctx.fillStyle = color;
         ctx.beginPath(); ctx.arc(c + x * R, c + y * R, (size / 64) * 1.25 * s + .45, 0, 6.2832); ctx.fill();
       });
    requestAnimationFrame(frame);
  })();
}
const orbHTML = (size, label) => `<span class="orbw"><canvas data-orb="${size}"></canvas>${label ? `<span>${esc(label)}</span>` : ''}</span>`;
const mountOrbs = (root = document) => $$('canvas[data-orb]:not([data-on])', root).forEach(c => { c.dataset.on = 1; orb(c, +c.dataset.orb); });

/* ---------- tiny markdown (escape first, then a safe subset) ---------- */
const inline = s => s.replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>').replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
function md(src) {
  let out = '', list = null, para = [];
  const flush = () => { if (para.length) { out += `<p>${inline(para.join(' '))}</p>`; para = []; } };
  const close = () => { if (list) { out += `</${list}>`; list = null; } };
  for (const raw of esc(src).split('\n')) {
    const l = raw.trimEnd(); let m;
    if (!l.trim()) { flush(); close(); continue; }
    if ((m = l.match(/^(#{1,4})\s+(.*)/))) { flush(); close(); out += `<h${m[1].length + 1}>${inline(m[2])}</h${m[1].length + 1}>`; continue; }
    if ((m = l.match(/^\s*[-*]\s+(.*)/))) { flush(); if (list !== 'ul') { close(); out += '<ul>'; list = 'ul'; } out += `<li>${inline(m[1])}</li>`; continue; }
    if ((m = l.match(/^\s*\d+[.)]\s+(.*)/))) { flush(); if (list !== 'ol') { close(); out += '<ol>'; list = 'ol'; } out += `<li>${inline(m[1])}</li>`; continue; }
    if (/^---+$/.test(l)) { flush(); close(); out += '<hr>'; continue; }
    close(); para.push(l.trim());
  }
  flush(); close(); return out;
}

/* ---------- state ---------- */
const FDEF = { sector: [], ticker: [], min: 5, q: '', sort: 'score', dir: -1, shown: 40 };
const S = { data: null, news: null, newsAll: false, briefs: null, chat: [], f: { ...FDEF }, open: new Set(), asking: false, ro: null, route: '' };
const view = $('#view');

async function loadState(force) {
  if (force) await api('/api/reload', { method: 'POST' });
  S.data = await api('/api/state');
  chrome();
}

/* top-bar freshness chip + ticker tape */
const PULSE = [['World', 'VWCE.DE'], ['S&P 500', 'SXR8.DE'], ['Nasdaq 100', 'SXRV.DE'], ['Europe 600', 'EXSA.DE'], ['DAX', 'EXS1.DE'],
               ['Emerging', 'IS3N.DE'], ['Nifty 50', 'NIFTYBEES.NS'], ['Gold', '4GLD.DE'], ['Global bonds', 'VAGF.DE']];
function chrome() {
  const d = S.data;
  if (d && d.models) $('#models').textContent = d.models.score === d.models.smart ? d.models.score : `${d.models.score} (scoring) + ${d.models.smart} (analyst)`;
  if (!S.screen) return;
  const by = Object.fromEntries(S.screen.rows.map(r => [r.t, r]));
  const items = PULSE.filter(([, t]) => by[t]).map(([l, t]) => `<a class="ti" href="#/i/${enc(t)}"><u>${l}</u><b class="${tone(by[t].m.r1d)}">${pc(by[t].m.r1d)}</b></a>`).join('');
  $('#tape').innerHTML = items ? `<div class="tape-track" style="--dur:60s">${items.repeat(4)}</div>` : '';  // 4 copies: seamless at any width
}
setInterval(() => { if (S.data) chrome(); }, 30000);

let pollT;
function pollRescan() {
  clearInterval(pollT);
  if (!S.data || !S.data.rescanning) return;
  pollT = setInterval(async () => {
    try {
      const was = S.data.rescanning; const d = await api('/api/state');
      if (was && !d.rescanning) {
        clearInterval(pollT); toast('Rescan finished — refreshing the data.');
        await loadState(true); route(true);
      } else { S.data.rescanning = d.rescanning; chrome(); }
    } catch (e) { /* transient — try again next tick */ }
  }, 8000);
}

/* ---------- router ---------- */
const ROUTES = { today: vToday, discover: vDiscover, search: vSearch, screener: vScreener, i: vInstrument, portfolio: vPortfolio, compare: vCompare, plan: vPlan, alerts: vAlerts, ipos: vIpos, overview: vOverview, signals: vSignals, news: vNews, ask: vAsk, brief: vBrief };
const NEEDS_SIGNALS = new Set(['overview', 'signals', 'brief']);  // views that read the Polymarket database
const TITLES = { today: 'Today', discover: 'Discover', search: 'Search', screener: 'Screener', portfolio: 'Portfolio', compare: 'Compare', plan: 'Savings plan', alerts: 'Alerts', ipos: 'IPOs', overview: 'Predictions', signals: 'Signals', news: 'News', ask: 'Ask', brief: 'Brief' };
function parseHash() {
  const [p0, qs = ''] = location.hash.replace(/^#\/?/, '').split('?');
  const [p, ...rest] = p0.split('/');
  return { path: ROUTES[p] ? p : 'today', arg: decodeURIComponent(rest.join('/')), q: new URLSearchParams(qs) };
}
async function route(keepScroll) {
  const { path, arg, q } = parseHash();
  const navKey = { i: 'screener', search: 'screener', signals: 'overview', news: 'overview', brief: 'overview' }[path] || path;
  $$('#nav a').forEach(a => a.classList.toggle('on', a.dataset.r === navKey));
  closeCmd();
  if (S.ro) { S.ro.disconnect(); S.ro = null; }
  if (NEEDS_SIGNALS.has(path) && !S.data && S.statePromise && !S.stateErr) {  // still loading in the background: wait here, only on these pages
    view.innerHTML = `<div class="loading">${orbHTML(64, 'Loading prediction signals…')}</div>`; mountOrbs(view);
    await S.statePromise;
    if (parseHash().path !== path) return;
  }
  if (NEEDS_SIGNALS.has(path) && !S.data) {  // the screener never needs the signals database — don't let it take the app down
    view.innerHTML = `<div class="err-card fade"><h2>Prediction signals are offline</h2><p>${esc(S.stateErr || 'Still loading…')} The screener works without them.</p><a class="btn primary" href="#/screener">Open the screener</a></div>`;
    S.route = path; return;
  }
  if (path === 'signals' && [...q.keys()].length) {
    S.f = { ...FDEF, sector: (q.get('sector') || '').split(',').filter(Boolean), ticker: (q.get('ticker') || '').split(',').filter(Boolean),
            min: q.has('min') ? +q.get('min') : FDEF.min, q: q.get('q') || '', sort: q.get('sort') || FDEF.sort, dir: q.has('dir') ? +q.get('dir') : FDEF.dir };
  }
  view.innerHTML = ''; view.onclick = null;  // each view installs its own delegated handler
  await ROUTES[path](q, arg);
  mountOrbs(view);
  if (!keepScroll && S.route !== path) scrollTo({ top: 0, behavior: 'instant' });
  S.route = path;
  document.title = (path === 'i' ? arg : TITLES[path]) + ' · My Financial Scanner';
}
addEventListener('hashchange', () => route());

/* ---------- predictions: one section, four tabs ---------- */
const predNav = a => `<div class="subnav">${[['overview', 'Overview'], ['signals', 'Signals'], ['news', 'News'], ['brief', 'Brief']]
  .map(([r, l]) => `<a href="#/${r}" class="${a === r ? 'on' : ''}">${l}</a>`).join('')}
  <span class="subnav-r">${S.data && S.data.asOf ? `<span class="hint">scanned ${ago(S.data.asOf)}</span>` : ''}<button class="btn sm" id="open-wl" type="button">Prediction watchlist</button></span></div>`;
document.addEventListener('click', e => { if (e.target.closest('#open-wl')) S.data ? openDrawer() : toast('The prediction watchlist needs the signals database.', true); });

/* ---------- overview ---------- */
const sigLink = (o) => '#/signals?' + Object.entries(o).map(([k, v]) => `${k}=${enc(v)}`).join('&');
function countUp(el) {
  const to = +el.dataset.to, f = { int: v => Math.round(v).toLocaleString('en-US'), money, dec: v => v.toFixed(1) }[el.dataset.fmt];
  if (reduceMotion) { el.innerHTML = f(to) + (el.dataset.sfx || ''); return; }
  const t0 = performance.now();
  (function step(t) {
    const p = Math.min(1, (t - t0) / 900), e = 1 - Math.pow(1 - p, 3);
    el.innerHTML = f(to * e) + (el.dataset.sfx || ''); if (p < 1) requestAnimationFrame(step);
  })(t0);
}

function vOverview() {
  const d = S.data, k = d.kpis, hot = d.hot, active = d.signals.filter(r => r.score >= 5);
  if (!d.signals.length) {
    view.innerHTML = predNav('overview') + `<div class="err-card fade"><h2>No signals yet</h2><p>The scanner hasn't scored any markets. Run <code>python3 -m src.scheduler --once</code> to fetch and score them.</p></div>`;
    return;
  }
  const top = hot[0];
  const hero = top ? `
    <h1 class="display"><span class="hl">${esc(top.sector)}</span> is running hottest.</h1>
    <p class="lede">${plural(top.n, 'live signal')} and <b>${money(top.volume)}</b> of money behind them, peaking at <b>${top.peak}/10</b>.
      ${top.soon != null ? `The nearest one closes in <b>${plural(top.soon, 'day')}</b>.` : ''}</p>
    <div class="cta"><a class="btn primary lg" href="${sigLink({ sector: top.sector })}">Open these signals →</a>
      <a class="btn lg" href="#/brief">Read today’s brief</a></div>`
    : `<h1 class="display">Nothing is running hot yet.</h1><p class="lede">No sector has a signal scoring 5 or above right now.</p>`;
  const cells = [...active].sort((a, b) => b.score - a.score || b.volume - a.volume).slice(0, 48);

  view.innerHTML = predNav('overview') + `
  <section class="hero fade">
    <div><div class="eyebrow">Right now</div>${hero}</div>
    <div class="waffle-wrap">
      <div class="waffle">${cells.map((r, i) => `<a href="${sigLink({ q: r.market.slice(0, 70) })}" style="--c:${conv(r.score)};--i:${i}"
        data-tip="${esc(`${r.score}/10 · ${r.tickers[0] || r.sector} · ${money(r.volume)}\n${r.market}`)}" aria-label="${esc(r.market)}"></a>`).join('')}</div>
      <div class="waffle-cap"><span>Each square is a live signal</span><span>brighter = stronger</span></div>
    </div>
  </section>

  <div class="sh"><h2>Big bets</h2></div>
  <p class="sub">The prediction markets that would move prices the most if they came true, whether or not they touch your watchlist: regulation, rates, trade wars, approvals. The percentage is the crowd's odds today.</p>
  ${betsHTML(d)}

  <section class="kpis fade">
    ${[['Markets scanned', k.markets, 'int', ''], ['Active signals', k.active, 'int', ''], ['High conviction', k.high, 'int', ''],
       ['Money behind them', k.volume, 'money', ''], ['Avg conviction', k.avg, 'dec', '<small>/10</small>']]
      .map(([l, v, f, s]) => `<div class="kpi"><div class="v" data-to="${v}" data-fmt="${f}" data-sfx="${esc(s)}">0</div><div class="l">${l}</div></div>`).join('')}
  </section>

  <div class="sh"><h2>Hot topics</h2></div>
  <p class="sub">Segments ranked by heat — how much conviction <em>and</em> money is stacked on them right now. Start at the top. The arrow shows how a segment's heat changed against about a week ago.</p>
  <div class="lb">${hot.map((h, i) => `
    <a class="lb-row" href="${sigLink({ sector: h.sector })}">
      <span class="lb-rank">${String(i + 1).padStart(2, '0')}</span>
      <span><span class="lb-name">${esc(h.sector)}</span>${trendChip(d.trends && d.trends.sectors[h.sector])}<span class="lb-lead">${esc(h.lead)}</span></span>
      <span class="lb-bar" style="--c:${conv(5 + h.heat / 20)}"><span class="track"><i class="fill" data-w="${h.heat}"></i></span><b>${h.heat}</b></span>
      <span class="lb-stat"><b>${plural(h.n, 'signal')}</b> · ${money(h.volume)}<br>peak ${h.peak}/10${h.soon != null && h.soon <= 14
        ? ` · <span class="soon">closes in ${h.soon}d</span>` : ` · ${esc(h.tickers.slice(0, 3).join(' ') || 'macro')}`}</span>
      <span class="go">→</span>
    </a>`).join('') || '<div class="empty">Nothing ranked yet.</div>'}</div>

  <div class="sh"><h2>Odds that moved</h2></div>
  <p class="sub">Markets whose yes-probability changed most since about a day ago: where the crowd changed its mind. A big move on a high-conviction market is the thing to read first.</p>
  ${moversHTML(d.trends)}

  <div class="sh"><h2>Where the money is</h2></div>
  <p class="sub">Every active signal as a tile, grouped by the stock it affects. Bigger = more money traded (square-root scaled so one giant market doesn’t hide the rest); greener = higher conviction.</p>
  <div class="tm" id="tm"></div>
  <div class="legend" style="--r0:${RAMPS[theme()][0]};--r1:${RAMPS[theme()][1]};--r2:${RAMPS[theme()][2]};--r3:${RAMPS[theme()][3]}">
    <span>weak · 5</span><span class="ramp"></span><span>10 · direct hit</span></div>

  <div class="sh"><h2>Your watchlist</h2><a class="more" href="#" id="edit-wl">Edit watchlist →</a></div>
  <div class="grid2" style="margin-top:18px">
    <div class="card"><h3>Exposure</h3><p class="sub">How many live signals mention each stock; the pill is the strongest one. Many signals and a high peak means the most is brewing.</p>
      ${(() => { const mx = Math.max(1, ...d.exposure.map(e => e.n)); return d.exposure.map(e => `
        <a class="exp-row" href="${sigLink({ ticker: e.ticker })}"><span class="exp-t">${esc(e.ticker)}</span>
          <span><div class="exp-d">${esc(e.desc)}</div><div class="exp-track"><i style="width:${e.n / mx * 100}%"></i></div></span>
          <span class="exp-n">${e.n}</span>${e.peak ? scPill(e.peak) : '<span class="sc zero">—</span>'}</a>`).join(''); })()}
    </div>
    <div class="card"><h3>Closing soon</h3><p class="sub">What resolves next, soonest first. When a row closes, the real-world answer lands.</p>${catalysts(active)}</div>
  </div>

  <div class="sh"><h2>How conviction and pricing spread</h2></div>
  <div class="grid2" style="margin-top:18px">
    <div class="card"><h3>Sector conviction</h3><p class="sub">Average conviction per segment; the number after the dot is how many signals.</p>${sectorBars(active)}</div>
    <div class="card"><h3>Market pricing</h3><p class="sub">Yes-probability of each active signal, bucketed — where the crowd has already made up its mind.</p>${histogram(active)}</div>
  </div>
  <div class="card" style="margin-top:28px"><h3>Signal map</h3>
    <p class="sub">One dot per market — higher matters more, further right has more money riding on it. The top-right corner is where to look.</p>
    <svg class="scatter" id="sc" role="img" aria-label="Scatter of conviction versus money traded"></svg></div>`;

  $$('.kpi .v', view).forEach(countUp);
  requestAnimationFrame(() => $$('.fill', view).forEach(f => { f.style.width = f.dataset.w + '%'; }));
  $('#edit-wl', view).onclick = e => { e.preventDefault(); openDrawer(); };
  const draw = () => { drawTreemap(active); drawScatter(active); };
  draw();
  S.ro = new ResizeObserver(() => { clearTimeout(S.rt); S.rt = setTimeout(draw, 120); });
  S.ro.observe($('#tm'));
}

function spark(pts) {
  if (!pts || pts.length < 3) return '';
  const lo = Math.min(...pts), hi = Math.max(...pts), W = 64, H = 18, X = i => i / (pts.length - 1) * W, Y = v => H - 2 - (hi - lo ? (v - lo) / (hi - lo) : .5) * (H - 4);
  return `<svg class="spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-hidden="true"><polyline points="${pts.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' ')}" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>`;
}
function trendChip(tr) {
  if (!tr || tr.change == null) return '';
  const up = tr.change >= 0, flat = Math.abs(tr.change) < .03;
  return `<span class="trend ${flat ? '' : up ? 'up' : 'down'}" data-tip="Heat now vs ${tr.vs_days} day${tr.vs_days === 1 ? '' : 's'} ago">${flat ? '→' : up ? '▲' : '▼'} ${pc(Math.abs(tr.change), false)} ${spark(tr.spark)}</span>`;
}
const IMPACT_L = i => i >= 9 ? 'Moves all markets' : 'Moves a sector';
function betMove(d, r) { const m = d.trends && d.trends.movers && d.trends.movers.find(x => x.id === r.id); return m ? `<b class="${m.delta > 0 ? 'up' : 'down'}">${m.delta > 0 ? '+' : '−'}${Math.round(Math.abs(m.delta) * 100)} pts today</b>` : ''; }
function betsHTML(d) {
  const b = d.bets || [];
  if (!b.length) return `<div class="empty">No big bets scored yet. Each scan rates how much every market would move prices; they show up here after the next one.</div>`;
  return `<div class="bets">${b.map(r => `<a class="bet" href="${sigLink({ q: r.market.slice(0, 70), min: 0 })}">
    <span class="bet-p"><b>${r.prob == null ? '—' : Math.round(r.prob * 100) + '%'}</b><small>chance</small></span>
    <span class="bet-b"><span class="bet-q">${esc(r.market)}</span>
      ${r.angle ? `<span class="bet-a">${esc(r.angle)}</span>` : ''}
      <span class="bet-m"><span class="bet-i${r.impact >= 9 ? ' hi' : ''}">${IMPACT_L(r.impact)}</span>${betMove(d, r)}<span>${money(r.volume)} bet</span>${r.days != null ? `<span>closes in ${plural(r.days, 'day')}</span>` : ''}${r.tickers.length ? `<span>${esc(r.tickers.join(' · '))}</span>` : ''}</span></span></a>`).join('')}</div>`;
}

function moversHTML(t) {
  if (!t) return '<div class="empty">Trends need one table in your database: run the <code>snapshots</code> SQL at the bottom of <code>schema.sql</code> in Supabase once. The scanner fills it from then on.</div>';
  if (!t.since) return `<div class="empty">Not enough history yet. The scanner saves a snapshot about every 6 hours${t.snapshots ? ` (${plural(t.snapshots, 'so far')})` : ''}; movers appear once one is a day old.</div>`;
  if (!t.movers.length) return `<div class="empty">Nothing moved more than 3 points since ${fmtDate(t.since.slice(0, 10), true)}. Calm day.</div>`;
  return `<div class="tl">${t.movers.map(m => `<a class="mv" href="${sigLink({ q: m.market.slice(0, 70) })}">
    <span class="mv-d ${m.delta > 0 ? 'up' : 'down'}">${m.delta > 0 ? '+' : '−'}${Math.round(Math.abs(m.delta) * 100)} pts</span>
    <span class="mv-q">${esc(m.market)}<small>${esc(m.tickers.join(' · '))}</small></span>
    <span class="mv-p">${Math.round(m.from * 100)}% → <b>${Math.round(m.to * 100)}%</b></span>${scPill(m.score)}</a>`).join('')}</div>`;
}

function catalysts(active) {
  const seen = new Set(), up = active.filter(r => r.days != null && r.days >= 0).sort((a, b) => a.days - b.days)
    .filter(r => !seen.has(r.market) && seen.add(r.market)).slice(0, 12);
  if (!up.length) return '<div class="empty">No signals with a future expiry yet.</div>';
  const G = [['This week', 7], ['This month', 31], ['Next 3 months', 93], ['Later', 1e9]], buckets = G.map(() => []);
  up.forEach(r => buckets[G.findIndex(g => r.days <= g[1])].push(r));
  return buckets.map((b, i) => b.length ? `<div class="cat-h">${G[i][0]} · ${b.length}</div>` + b.map(r => `
    <a class="cat-row" href="${sigLink({ q: r.market.slice(0, 70) })}"><span class="cat-d${r.days <= 7 ? ' hot' : ''}">${r.days}d</span>
      <span class="cat-q">${esc(r.market)}</span><span class="cat-t">${esc(r.tickers[0] || '')}</span>${scPill(r.score)}</a>`).join('') : '').join('');
}

function sectorBars(active) {
  const g = {}; active.forEach(r => (g[r.sector] ??= []).push(r.score));
  const rows = Object.entries(g).map(([s, v]) => [s, v.reduce((a, b) => a + b, 0) / v.length, v.length]).sort((a, b) => b[1] - a[1]);
  return rows.map(([s, avg, n]) => `<a class="hb" href="${sigLink({ sector: s })}"><span class="hb-l">${esc(s === '—' ? 'Unsorted' : s)}</span>
    <span class="hb-t"><i style="width:${avg * 7.6}%;--c:${conv(avg)}"></i><span>${avg.toFixed(1)} · ${n}</span></span></a>`).join('') || '<div class="empty">Nothing yet.</div>';
}

function histogram(active) {
  const L = ['0–20%', '20–40%', '40–60%', '60–80%', '80–100%'], c = [0, 0, 0, 0, 0];
  active.forEach(r => { if (r.prob != null) c[Math.min(4, Math.floor(r.prob * 5))]++; });
  const mx = Math.max(1, ...c);
  return `<div class="hist">${c.map((n, i) => `<div class="col"><b>${n}</b><i style="height:${n / mx * 78}%"></i><span>${L[i]}</span></div>`).join('')}</div>`;
}

/* squarified treemap (Bruls et al.): lays `items` (sorted desc by .v) into the rect with near-square tiles */
function squarify(items, x, y, w, h) {
  const out = [], total = items.reduce((a, b) => a + b.v, 0);
  if (!total || w <= 0 || h <= 0) return out;
  const scale = (w * h) / total, worst = (areas, side) => {
    const sum = areas.reduce((a, b) => a + b, 0);
    return Math.max(...areas.map(a => Math.max(side * side * a / (sum * sum), sum * sum / (side * side * a))));
  };
  let rest = items.slice();
  while (rest.length) {
    const side = Math.min(w, h); let areas = [rest[0].v * scale], i = 1;
    while (i < rest.length) {
      const next = [...areas, rest[i].v * scale];
      if (worst(next, side) <= worst(areas, side)) { areas = next; i++; } else break;
    }
    const sum = areas.reduce((a, b) => a + b, 0), row = rest.slice(0, i);
    if (w >= h) { const cw = sum / h; let cy = y; row.forEach((it, j) => { const ch = areas[j] / cw; out.push({ ...it, x, y: cy, w: cw, h: ch }); cy += ch; }); x += cw; w -= cw; }
    else { const rh = sum / w; let cx = x; row.forEach((it, j) => { const cw = areas[j] / rh; out.push({ ...it, x: cx, y, w: cw, h: rh }); cx += cw; }); y += rh; h -= rh; }
    rest = rest.slice(i);
  }
  return out;
}

function drawTreemap(active) {
  const el = $('#tm'); if (!el) return;
  const W = el.clientWidth, H = el.clientHeight, groups = {};
  active.forEach(r => (groups[r.tickers[0] || 'Macro'] ??= []).push(r));
  const gItems = Object.entries(groups).map(([t, rows]) => ({ t, rows, v: rows.reduce((a, r) => a + Math.sqrt(Math.max(r.volume, 1)), 0) })).sort((a, b) => b.v - a.v);
  let html = '';
  squarify(gItems, 0, 0, W, H).forEach(g => {
    const lab = g.h > 46 && g.w > 64 ? 22 : 0, pad = 3;
    html += `<a class="glabel" href="${sigLink({ ticker: g.t })}" style="left:${g.x + pad}px;top:${g.y}px;width:${g.w - pad * 2}px">${esc(g.t)} · ${g.rows.length}</a>`;
    const kids = g.rows.map(r => ({ r, v: Math.sqrt(Math.max(r.volume, 1)) })).sort((a, b) => b.v - a.v);
    squarify(kids, g.x + pad, g.y + lab, g.w - pad * 2, g.h - lab - pad).forEach(c => {
      const big = c.w > 92 && c.h > 52;
      html += `<a class="tile" href="${sigLink({ q: c.r.market.slice(0, 70) })}" style="left:${c.x}px;top:${c.y}px;width:${c.w}px;height:${c.h}px;--c:${conv(c.r.score)}"
        data-tip="${esc(`${c.r.score}/10 · ${g.t} · ${money(c.r.volume)}\n${c.r.market}`)}">${big ? `<span class="n">${c.r.score}</span><span class="q">${esc(c.r.market)}</span>` : ''}</a>`;
    });
  });
  el.innerHTML = html;
}

function drawScatter(active) {
  const svg = $('#sc'); if (!svg || !active.length) return;
  const W = svg.clientWidth, H = svg.clientHeight, m = { l: 44, r: 16, t: 14, b: 34 };
  if (W < 120 || H < 80) return;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const lv = active.map(r => Math.log10(Math.max(r.volume, 1))), lo = Math.floor(Math.min(...lv)), hi = Math.ceil(Math.max(...lv));
  const X = v => m.l + (Math.log10(Math.max(v, 1)) - lo) / (hi - lo || 1) * (W - m.l - m.r), Y = s => H - m.b - (s - 4.6) / 5.8 * (H - m.t - m.b);
  const lab = n => n >= 9 ? `$${10 ** (n - 9)}B` : n >= 6 ? `$${10 ** (n - 6)}M` : `$${10 ** (n - 3)}K`;
  let s = '';
  for (let sc = 5; sc <= 10; sc++) s += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(sc)}" y2="${Y(sc)}" stroke="var(--line2)"/><text x="${m.l - 10}" y="${Y(sc) + 4}" text-anchor="end">${sc}</text>`;
  for (let n = lo; n <= hi; n++) s += `<line y1="${m.t}" y2="${H - m.b}" x1="${X(10 ** n)}" x2="${X(10 ** n)}" stroke="var(--line2)"/><text x="${X(10 ** n)}" y="${H - 12}" text-anchor="middle">${n >= 3 ? lab(n) : '$' + 10 ** n}</text>`;
  [...active].sort((a, b) => a.score - b.score).forEach(r => {
    const rad = 3 + Math.max(0, Math.log10(Math.max(r.volume, 1)) - 4) * 1.7;
    s += `<a href="${sigLink({ q: r.market.slice(0, 70) })}"><circle class="dot" cx="${X(r.volume)}" cy="${Y(r.score) + ((r.market.length * 7) % 9 - 4)}" r="${rad.toFixed(1)}" fill="${conv(r.score)}" opacity=".78"
      data-tip="${esc(`${r.score}/10 · ${r.tickers[0] || r.sector} · ${money(r.volume)}\n${r.market}`)}"/></a>`;
  });
  svg.innerHTML = s;
}

/* ---------- signals ---------- */
const SORTS = { score: r => r.score, volume: r => r.volume, prob: r => r.prob ?? -1, days: r => r.days ?? 1e9, market: r => r.market.toLowerCase() };
function filtered() {
  const f = S.f, q = f.q.trim().toLowerCase();
  const rows = S.data.signals.filter(r => r.score >= f.min && (!f.sector.length || f.sector.includes(r.sector)) &&
    (!f.ticker.length || r.tickers.some(t => f.ticker.includes(t))) &&
    (!q || (r.market + ' ' + r.sector + ' ' + r.tickers.join(' ') + ' ' + r.reasoning).toLowerCase().includes(q)));
  const key = SORTS[f.sort] || SORTS.score;
  return rows.sort((a, b) => { const x = key(a), y = key(b); return (x < y ? -1 : x > y ? 1 : 0) * f.dir || b.score - a.score; });
}
function syncHash() {
  const f = S.f, p = [];
  if (f.sector.length) p.push('sector=' + enc(f.sector.join(',')));
  if (f.ticker.length) p.push('ticker=' + enc(f.ticker.join(',')));
  if (f.min !== FDEF.min) p.push('min=' + f.min);
  if (f.q) p.push('q=' + enc(f.q));
  if (f.sort !== FDEF.sort) p.push('sort=' + f.sort + '&dir=' + f.dir);
  history.replaceState(null, '', '#/signals' + (p.length ? '?' + p.join('&') : ''));
}

function vSignals() {
  const d = S.data, f = S.f;
  view.innerHTML = `
  ${predNav('signals')}
  <div class="page-h fade"><div class="eyebrow">Signals</div><h1>Every scored market</h1>
    <p>8–10 is a direct hit on a stock you watch · 5–7 hits its sector · 3–4 moves the whole market a little. Filter, then watch what closes soon.</p></div>
  <div class="fbar">
    <div class="frow">
      <label class="search"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="7" cy="7" r="5"/><path d="m11 11 3.5 3.5"/></svg>
        <input class="in" id="q" type="search" placeholder="Search markets, tickers, reasoning" value="${esc(f.q)}" autocomplete="off" aria-label="Search signals"><kbd>/</kbd></label>
      <div class="seg" id="min" role="group" aria-label="Minimum conviction">${[0, 3, 5, 8].map(v => `<button type="button" data-v="${v}" class="${f.min === v ? 'on' : ''}">${v ? v + '+' : 'Any'}</button>`).join('')}</div>
      <button class="btn" id="clear" type="button">Clear</button>
    </div>
    <div class="chips" id="sec-chips"></div><div class="chips" id="tk-chips"></div>
  </div>
  <div class="res-meta"><span id="count"></span><span></span></div>
  <div class="tbl" id="res"></div>`;

  const sectors = Object.entries(d.signals.reduce((a, r) => (a[r.sector] = (a[r.sector] || 0) + (r.score >= f.min), a), {})).sort((a, b) => b[1] - a[1]);
  $('#sec-chips').innerHTML = `<span class="lab">Sector</span>` + sectors.map(([s, n]) => `<button class="cf${f.sector.includes(s) ? ' on' : ''}" data-sector="${esc(s)}" type="button">${esc(s === '—' ? 'Unsorted' : s)} <small>${n}</small></button>`).join('');
  const tc = {}; d.signals.forEach(r => r.tickers.forEach(t => { tc[t] = (tc[t] || 0) + (r.score >= f.min); }));
  Object.keys(d.watchlist.tickers).forEach(t => { tc[t] ??= 0; });
  const tks = Object.entries(tc).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 16);
  $('#tk-chips').innerHTML = `<span class="lab">Ticker</span>` + tks.map(([t, n]) => `<button class="cf${f.ticker.includes(t) ? ' on' : ''}" data-ticker="${esc(t)}" type="button">${esc(t)} <small>${n}</small></button>`).join('');

  $('#q').oninput = e => { f.q = e.target.value; f.shown = FDEF.shown; syncHash(); list(); };
  $('#min').onclick = e => { const b = e.target.closest('button'); if (!b) return; f.min = +b.dataset.v; f.shown = FDEF.shown; syncHash(); vSignals(); };
  $('#clear').onclick = () => { S.f = { ...FDEF }; syncHash(); vSignals(); };
  view.onclick = e => {
    const c = e.target.closest('.cf');
    if (c) { const [k, v] = c.dataset.sector !== undefined ? ['sector', c.dataset.sector] : ['ticker', c.dataset.ticker];
             f[k] = f[k].includes(v) ? f[k].filter(x => x !== v) : [...f[k], v]; f.shown = FDEF.shown; syncHash(); return vSignals(); }
    const th = e.target.closest('[data-sort]');
    if (th) { const k = th.dataset.sort; f.dir = f.sort === k ? -f.dir : (k === 'days' || k === 'market' ? 1 : -1); f.sort = k; syncHash(); return list(); }
    if (e.target.closest('#more')) { f.shown += 40; return list(); }
    const row = e.target.closest('.tr[data-k]');
    if (row && !e.target.closest('.why')) { const k = row.dataset.k; S.open.has(k) ? S.open.delete(k) : S.open.add(k); list(); }
  };
  list();
}

function list() {
  const f = S.f, rows = filtered(), shown = rows.slice(0, f.shown);
  $('#count').textContent = `${rows.length} of ${S.data.signals.length} signals · ${S.data.kpis.markets.toLocaleString('en-US')} markets scanned`;
  const th = (k, label, cls = '') => `<span class="${cls}"><button data-sort="${k}" class="${f.sort === k ? 'on' : ''}" type="button">${label}${f.sort === k ? (f.dir < 0 ? ' ↓' : ' ↑') : ''}</button></span>`;
  $('#res').innerHTML = `<div class="tr th">${th('score', 'Score')}${th('market', 'Market')}<span class="col-sec">Sector</span><span class="tk-col">Tickers</span>${th('prob', 'Prob', 'col-prob num')}${th('volume', 'Volume', 'col-vol num')}${th('days', 'Expires', 'num')}</div>` +
    (shown.map(r => {
      const open = S.open.has(r.market), p = r.prob == null ? null : Math.round(r.prob * 100);
      return `<div class="tr${open ? ' open' : ''}" data-k="${esc(r.market)}">
        <span>${scPill(r.score)}</span><span class="mk">${esc(r.market)}</span><span class="sec col-sec">${esc(r.sector === '—' ? 'Unsorted' : r.sector)}</span>
        <span class="tk tk-col">${esc(r.tickers.join(' · ') || '—')}</span>
        <span class="num col-prob">${p == null ? '—' : p + '%'}${p == null ? '' : `<div class="pbar"><i style="width:${p}%"></i></div>`}</span>
        <span class="num col-vol">${money(r.volume)}</span><span class="num days${r.days != null && r.days <= 7 ? ' hot' : ''}">${r.days == null ? '—' : r.days + 'd'}</span>
        ${open ? `<div class="why">${esc(r.reasoning || 'No reasoning stored.')}<span class="m">${esc(r.tier)} · ${esc(r.sector)} · ${p == null ? 'no price' : p + '% yes'} · ${money(r.volume)} traded</span></div>` : ''}
      </div>`;
    }).join('') || '<div class="empty">No signals match these filters. Try lowering the minimum conviction or clearing a chip.</div>') +
    (rows.length > shown.length ? `<div class="res-meta"><span></span><button id="more" type="button">Show ${Math.min(40, rows.length - shown.length)} more ↓</button></div>` : '');
}

/* ---------- news ---------- */
async function vNews() {
  view.innerHTML = predNav('news') + `<div class="page-h fade"><div class="eyebrow">World news</div><h1>Headlines, read through your watchlist</h1>
    <p>Each headline is scored 0–5 for its effect on a stock you hold. Teal is supportive, red is adverse, grey is noise.</p></div><div class="news" id="nw"><div class="loading sm">${orbHTML(56, 'Reading the wires…')}</div></div>`;
  mountOrbs(view);
  if (!S.news) { try { S.news = await api('/api/news'); } catch (e) { S.news = []; } }
  if (S.route !== 'news' && parseHash().path !== 'news') return;
  const el = $('#nw'); if (!el) return;
  const paint = () => {
    const shown = S.newsAll ? S.news : S.news.filter(w => w.impact >= 2);
    el.innerHTML = `<label class="switch" style="margin:22px 0 6px"><input type="checkbox" ${S.newsAll ? '' : 'checked'}> Portfolio-relevant only (impact ≥ 2)</label>` +
      (shown.map(w => { const c = !w.impact ? 'var(--muted)' : w.stance === 'bullish' ? 'var(--teal)' : w.stance === 'bearish' ? 'var(--red)' : 'var(--muted)';
        return `<div class="nw" style="--c:${c}"><div class="imp">${w.impact}</div><div>
          ${w.link ? `<a href="${esc(w.link)}" target="_blank" rel="noopener">${esc(w.title)}</a>` : esc(w.title)}
          <div class="meta"><b>${esc(w.stance)}</b>${w.tickers && w.tickers.length ? ' · ' + esc(w.tickers.join(', ')) : ''}${w.note ? `<span>${esc(w.note)}</span>` : ''}</div></div></div>`; }).join('')
        || '<div class="empty">Couldn’t fetch headlines right now — try again shortly.</div>') +
      (shown.length ? `<div class="res-meta"><span>${shown.length} headlines · refreshed every 30 min</span><span></span></div>` : '');
    $('input', el).onchange = e => { S.newsAll = !e.target.checked; paint(); };
  };
  paint();
}

/* ---------- ask the desk ---------- */
function chatHTML() {
  return S.chat.map(m => m.role === 'user'
    ? `<div class="msg"><div class="who">You</div><div class="body">${esc(m.content)}</div></div>`
    : `<div class="msg bot"><div class="who">Desk</div>${m.trace && m.trace.length ? `<div class="trace">${m.trace.map(t => `<span>${esc(t)}</span>`).join('')}</div>` : ''}<div class="prose">${md(m.content)}</div></div>`).join('') +
    (S.asking ? `<div class="thinking">${orbHTML(36)}<span>Agent planning tool calls…</span></div>` : '');
}
function vAsk(q) {
  view.innerHTML = `<div class="page-h fade"><div class="eyebrow">Ask</div><h1>Ask about your money</h1>
    <p>Ask in plain words about your portfolio, any fund or stock in the screener, or the prediction signals. It looks the numbers up (and shows you which lookups it ran), explains the jargon, and never tells you to buy or sell. Your portfolio is only visible to it when the app runs on your own computer.</p></div>
  <div class="chat"><div class="prompts">${['Am I too exposed to tech?', 'What is my riskiest holding, in plain English?', 'Which world ETFs are the calmest?',
      'Explain what a 20% worst fall would mean for my portfolio', 'How does VWCE compare with an S&P 500 fund?']
    .map(p => `<button class="cf" type="button" data-p="${esc(p)}">${esc(p)}</button>`).join('')}</div>
    <div id="log">${chatHTML()}</div>
    <form class="ask-box" id="askf"><input class="in" id="askq" placeholder="e.g. Is my portfolio spread out enough?" autocomplete="off" maxlength="600" aria-label="Your question"><button class="btn primary" type="submit">Ask</button></form></div>`;
  const send = async q => {
    q = q.trim(); if (!q || S.asking) return;
    const hist = S.chat.slice(-6).map(({ role, content }) => ({ role, content }));
    S.chat.push({ role: 'user', content: q }); S.asking = true; $('#askq').value = ''; $('#log').innerHTML = chatHTML(); mountOrbs(view);
    try { const r = await api('/api/ask', { method: 'POST', body: { question: q, history: hist } }); S.chat.push({ role: 'assistant', content: r.answer, trace: r.trace }); }
    catch (e) { S.chat.push({ role: 'assistant', content: 'Sorry — ' + e.message }); }
    S.asking = false; if ($('#log')) { $('#log').innerHTML = chatHTML(); $('#askq').focus(); }
  };
  $('#askf').onsubmit = e => { e.preventDefault(); send($('#askq').value); };
  $$('.prompts .cf', view).forEach(b => b.onclick = () => send(b.dataset.p));
  const pre = q && q.get('q');
  if (pre) { history.replaceState(null, '', '#/ask'); send(pre); }
}

/* ---------- brief ---------- */
async function vBrief() {
  view.innerHTML = predNav('brief') + `<div class="page-h fade"><div class="eyebrow">Daily brief</div><h1>The day, as an analyst note</h1>
    <p>The top signals written up — lead catalyst first, then implications by sector.</p></div><div id="bf"><div class="loading sm">${orbHTML(56, 'Loading briefs…')}</div></div>`;
  mountOrbs(view);
  if (!S.briefs) { try { S.briefs = await api('/api/briefs'); } catch (e) { S.briefs = []; } }
  const el = $('#bf'); if (!el) return;
  if (!S.briefs.length) { el.innerHTML = '<div class="empty">No briefs yet. Run <code>python3 -m src.reports</code> after scoring signals.</div>'; return; }
  const paint = i => { el.innerHTML = `<div class="frow" style="margin:22px 0 8px"><select class="in" id="bsel" aria-label="Brief date">${S.briefs.map((b, j) => `<option value="${j}"${j === i ? ' selected' : ''}>${esc(b.date)}</option>`).join('')}</select></div>
    <article class="prose">${md(S.briefs[i].content)}</article>`; $('#bsel').onchange = e => paint(+e.target.value); };
  paint(0);
}

/* ---------- screener: ETFs + stocks, explained ---------- */
const KW = { etf: 'etf index fund', fund: 'active fund', stock: 'stock share company' }, KIND_L = { stock: 'Stock', etf: 'ETF', fund: 'Fund' };
// every word of the query appears in the name, ticker, nicknames, group or kind — so "bitcap tech fund" finds BIT's fund
const matchQ = (r, q) => { const hay = `${r.name} ${r.t} ${r.aka || ''} ${r.group} ${r.kind} ${KW[r.kind] || ''}`.toLowerCase(); const w = q.toLowerCase().split(/\s+/).filter(Boolean); return w.length > 0 && w.every(x => hay.includes(x)); };
async function findAny(text) {  // screener list first, then any stock/ETF/fund Yahoo knows
  const v = (text || '').trim(), vl = v.toLowerCase(); if (!v) return null;
  const rows = S.screen ? S.screen.rows : [];
  const local = rows.find(r => r.t.toLowerCase() === vl) || rows.find(r => r.t.toLowerCase().split('.')[0] === vl) || rows.find(r => matchQ(r, v));
  if (local) return local;
  try { return (await api('/api/search?q=' + enc(v)))[0] || null; } catch (e) { return null; }
}
const SDEF = { kind: 'etf', group: '', sort: 'score', dir: -1, q: '' };
S.sc = { ...SDEF }; S.screen = null; S.inst = {};
const pc = (x, signed = true) => x == null ? '—' : (signed && x > 0 ? '+' : '') + (x * 100).toFixed(Math.abs(x) < .1 ? 1 : 0) + '%';
const tone = x => x == null ? '' : x > 0 ? 'up' : x < 0 ? 'down' : '';
const fmtPrice = v => v >= 1000 ? Math.round(v).toLocaleString('en-US') : v.toFixed(2);
const fmtDate = (d, long) => new Date(d + 'T12:00:00').toLocaleDateString('en-GB', long ? { day: 'numeric', month: 'short', year: 'numeric' } : { month: 'short', year: 'numeric' });
const PART_LABEL = { rpr: 'Return for the risk', growth: 'Growth per year', mdd: 'Smaller worst fall', r1y: 'Last 12 months' };
const SC_SORTS = [['score', 'Overall score', -1], ['r1y', 'Last 12 months', -1], ['growth', 'Growth per year', -1], ['rpr', 'Return for the risk', -1],
                  ['mdd', 'Smallest worst fall', -1], ['vol', 'Calmest (lowest swing)', 1], ['r6m', 'Hot lately (6 months)', -1]];
const LEARN = [
  ['ETF vs stock', 'An ETF is one share that holds hundreds or thousands of companies, so one company failing barely matters. A stock is a single company: more upside, and more can go wrong.'],
  ['Growth per year', 'The average yearly increase, with dividends reinvested. +8% a year turns €1,000 into about €1,470 after 5 years. Three years or more says far more than any single year.'],
  ['Swing (volatility)', 'How much the price typically jumps around in a year. A world fund swings ~15%, bonds ~5%, a single tech stock 40%+. Bigger swings mean a bumpier ride, not necessarily a worse investment.'],
  ['Worst fall (drawdown)', 'The biggest drop from a high to the low that followed. −30% means €1,000 briefly became €700. The real question: would you have held on, or sold at the bottom?'],
  ['Active fund vs index ETF', 'An index ETF copies a list of companies for a tiny fee (about 0.1–0.3% a year). An active fund, like BIT Capital’s, has a manager picking stocks for a bigger fee (often 1–2%). It’s only worth it if it beats the index by more than that, and each fund page shows whether it has.'],
  ['Return for the risk', 'Growth divided by swing: how much reward you got per unit of bumpiness. Above 1 is excellent, below 0.5 is a lot of stress for the reward. Professionals call a version of this the Sharpe ratio.'],
];

async function vScreener(q) {
  if (q && [...q.keys()].length) S.sc = { ...SDEF, kind: q.get('kind') || SDEF.kind, group: q.get('group') || '', q: q.get('q') || '' };
  let learnOpen = true; try { learnOpen = localStorage.getItem('learn') !== 'closed'; } catch (e) { /* private mode */ }
  view.innerHTML = `
  <div class="page-h fade"><div class="eyebrow">Screener</div><h1>Funds and stocks, ranked and explained</h1>
    <p>Ranked on what matters to a long-term investor: steady growth, growth per year, how deep it fell, and the last 12 months. Everything is in euros. A starting point for your own research, not advice.</p></div>
  <details class="learn"${learnOpen ? ' open' : ''}><summary>New to this? The numbers, in plain English</summary>
    <div class="learn-grid">${LEARN.map(([h, b]) => `<div><h4>${h}</h4><p>${b}</p></div>`).join('')}</div>
    <p class="learn-score"><b>The score (0–100)</b> ranks each one against the others of its type in this list, using growth, swing, worst fall and the last year. 80 means it beat about 80% of them. Bonds and gold are built to be steady rather than to grow fast, so compare them with each other using the group filter.</p></details>
  <div class="fbar" id="sbar"></div>
  <div class="res-meta"><span id="count"></span><span id="asof"></span></div>
  <div id="res"><div class="loading sm">${orbHTML(56, 'Fetching 5 years of prices…')}</div></div>`;
  mountOrbs(view);
  $('details.learn', view).ontoggle = e => { try { localStorage.setItem('learn', e.target.open ? 'open' : 'closed'); } catch (_) { /* fine */ } };
  if (!S.screen) {
    try { S.screen = await api('/api/screen'); }
    catch (e) { if ($('#res')) $('#res').innerHTML = `<div class="empty">Couldn’t load market data: ${esc(e.message)}</div>`; return; }
  }
  if (!$('#res')) return;  // navigated away while loading
  scBar(); scList();
  view.onclick = e => {
    const k = e.target.closest('#kind button'); if (k) { S.sc = { ...S.sc, kind: k.dataset.k, group: '' }; scBar(); return scList(); }
    const g = e.target.closest('[data-g]'); if (g) { S.sc.group = g.dataset.g; scBar(); return scList(); }
  };
}

function scBar() {
  const s = S.sc, rows = S.screen.rows, mine = rows.filter(r => r.kind === s.kind), groups = {};
  mine.forEach(r => { groups[r.group] = (groups[r.group] || 0) + 1; });
  $('#sbar').innerHTML = `<div class="frow">
      <div class="seg" id="kind" role="group" aria-label="Type">${[['etf', 'ETFs & ETCs'], ['stock', 'Stocks'], ['fund', 'Active funds']].map(([k, l]) => `<button type="button" data-k="${k}" class="${s.kind === k ? 'on' : ''}">${l} <small>${rows.filter(r => r.kind === k).length}</small></button>`).join('')}</div>
      <label class="search"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="7" cy="7" r="5"/><path d="m11 11 3.5 3.5"/></svg>
        <input class="in" id="q" type="search" placeholder="Search by name or ticker (Enter = all markets)" value="${esc(s.q)}" autocomplete="off" aria-label="Search"><kbd>/</kbd></label>
      <select class="in" id="sort" aria-label="Sort by">${SC_SORTS.map(([k, l]) => `<option value="${k}"${s.sort === k ? ' selected' : ''}>Sort: ${l}</option>`).join('')}</select>
    </div>
    <div class="chips"><span class="lab">Group</span><button class="cf${!s.group ? ' on' : ''}" data-g="" type="button">All <small>${mine.length}</small></button>${Object.entries(groups).map(([g, n]) => `<button class="cf${s.group === g ? ' on' : ''}" data-g="${esc(g)}" type="button">${esc(g)} <small>${n}</small></button>`).join('')}</div>`;
  $('#q').oninput = e => { s.q = e.target.value; scList(); };
  $('#q').onkeydown = e => { if (e.key === 'Enter' && s.q.trim()) location.hash = '#/search?q=' + enc(s.q.trim()); };
  $('#sort').onchange = e => { const x = SC_SORTS.find(z => z[0] === e.target.value); s.sort = x[0]; s.dir = x[2]; scList(); };
}

function scList() {
  const s = S.sc, q = s.q.trim().toLowerCase(), val = r => s.sort === 'score' ? r.score : r.m[s.sort];
  const rows = S.screen.rows.filter(r => q ? matchQ(r, q) : r.kind === s.kind && (!s.group || r.group === s.group))
    .sort((a, b) => { const x = val(a), y = val(b); return x == null ? 1 : y == null ? -1 : (x - y) * s.dir || b.score - a.score; });
  $('#count').textContent = q ? `${rows.length} in the ranked list match “${s.q.trim()}”` : `${rows.length} ${s.kind === 'stock' ? 'stocks' : s.kind === 'fund' ? 'active funds' : 'funds'} · ${SC_SORTS.find(z => z[0] === s.sort)[1].toLowerCase()}`;
  $('#asof').textContent = `Prices as of ${fmtDate(S.screen.asOf, true)} · Yahoo Finance`;
  const h = (l, tip, cls = '') => `<span class="num ${cls}" data-tip="${esc(tip)}">${l}</span>`;
  $('#res').innerHTML = `<div class="sr sr-h"><span>#</span><span>Name</span><span data-tip="0–100: how it compares with the others of its type in this list. Hover a row's numbers for what they mean.">Score</span>
      ${h('1 yr', 'Change over the last 12 months, in euros.')}${h('Per yr', 'Average growth per year over 3 years (* = less history, last 12 months used).', 'col-g')}
      ${h('Swing', 'Volatility: how much it typically moves in a year. ~15% is like the whole stock market.', 'col-v')}${h('Worst fall', 'Biggest drop from a high in the last 3 years.', 'col-d')}
      ${h('Ret/risk', 'Growth per unit of swing. Above 1 excellent, below 0.5 a bumpy ride for the reward.', 'col-r')}</div>` +
    (rows.map((r, i) => `<a class="sr" href="#/i/${enc(r.t)}">
      <span class="sr-rank">${i + 1}</span>
      <span class="sr-name"><b>${esc(r.name)}</b><span class="sr-meta">${esc(r.t)} · ${esc(r.group)}${r.tags.map(t => ` · <i>${esc(t)}</i>`).join('')}</span><span class="sr-why">${esc(r.why)}</span></span>
      <span class="sr-score"><span class="track"><i style="width:${r.score}%;--c:${conv(5 + r.score / 20)}"></i></span><b>${r.score}</b></span>
      <span class="num ${tone(r.m.r1y)}">${pc(r.m.r1y)}</span>
      <span class="num col-g ${tone(r.m.growth)}">${pc(r.m.growth)}${r.m.short ? '*' : ''}</span>
      <span class="num col-v">${pc(r.m.vol, false)}</span><span class="num col-d">${pc(r.m.mdd)}</span>
      <span class="num col-r">${r.m.rpr == null ? '—' : r.m.rpr.toFixed(2)}</span></a>`).join('') || '<div class="empty">Nothing in the ranked list matches.</div>') +
    (q ? `<a class="allm" href="#/search?q=${enc(s.q.trim())}">Not what you’re after? Search all markets for “${esc(s.q.trim())}” →</a>` : '');
}

async function vInstrument(q, t) {
  view.innerHTML = `<div class="loading sm">${orbHTML(56, 'Loading…')}</div>`; mountOrbs(view);
  let r = S.inst[t];
  if (!r) {
    try { r = S.inst[t] = await api('/api/instrument/' + enc(t)); }
    catch (e) { view.innerHTML = `<div class="err-card fade"><h2>Couldn’t load ${esc(t)}</h2><p>${esc(e.message)}</p><a class="btn primary" href="#/screener">Back to the screener</a></div>`; return; }
  }
  if (parseHash().arg !== t) return;
  const m = r.m, kindL = r.kind === 'stock' ? 'Stock' : r.kind === 'fund' ? 'Active fund' : r.group === 'Gold' ? 'ETC' : 'ETF',
    noun = r.kind === 'stock' ? 'stocks' : r.kind === 'fund' ? 'active funds' : 'funds';
  const parts = Object.entries(r.parts).map(([k, v]) => `<div class="pp"><div class="pp-l"><span>${PART_LABEL[k]}</span><b>beats ${Math.round(v * 100)}%</b></div>
    <div class="pp-t"><i style="width:${Math.max(2, v * 100)}%;--c:${conv(5 + v * 5)}"></i></div></div>`).join('');
  view.innerHTML = `
  <a class="back" href="#/screener">← Screener</a>
  <div class="ih fade">
    <div><div class="eyebrow">${esc(r.group)} · ${kindL} · ${esc(r.t)}</div><h1>${esc(r.name)}</h1>
      <p class="ih-sub"><b>€${fmtPrice(m.price)}</b> <span class="${tone(m.r1d)}">${pc(m.r1d)} on the day</span> · as of ${fmtDate(m.asof, true)}${r.ccy !== 'EUR' ? ` · converted from ${r.ccy === 'GBp' ? 'GBP' : esc(r.ccy)}` : ''}</p>
      <p class="ih-why">${esc(r.why)}</p>
      ${r.outside ? '<p class="hint">This one isn’t in the ranked screener list, so its score shows how it compares with the ones that are.</p>' : ''}
      <div class="cta" style="margin-top:16px"><a class="btn" href="#/compare?t=${enc([r.t, r.bench].filter(Boolean).join(','))}">Compare with others →</a>
        <a class="btn" href="#/plan?t=${enc(r.t)}">Simulate a monthly plan →</a></div></div>
    <div class="ih-score"><div class="big" style="color:${conv(5 + r.score / 20)}">${r.score}</div><div class="l">score / 100</div><div class="rk">${r.outside ? `would rank #${r.rank} among the ${r.of} ${noun} in the screener` : `#${r.rank} of ${r.of} ${noun} here`}</div></div>
  </div>
  <div class="card chart-card"><div class="chart-top"><div class="readout" id="ro"></div>
    <div class="seg" id="rng" role="group" aria-label="Chart range">${['6M', '1Y', '3Y', '5Y'].map(x => `<button type="button" data-r="${x}" class="${x === '3Y' ? 'on' : ''}">${x}</button>`).join('')}</div></div>
    <svg class="pchart" id="pc" role="img" aria-label="Price chart in euros"></svg></div>
  <div class="grid2" style="margin-top:28px">
    <div class="card"><h3>Year by year</h3><p class="sub">Each calendar year's return in euros (${new Date().getFullYear()} = so far this year). Real investments zig-zag; this is what that looks like.</p>${yearBars(m.years)}</div>
    <div class="card"><h3>Why it scores ${r.score}</h3><p class="sub">Each bar is the share of the other ${noun} in this list that it beats on that measure.</p>${parts}</div>
  </div>
  <div class="sh"><h2>The numbers, in plain English</h2></div>
  <div class="xcards">${r.cards.map(c => `<div class="xc ${c.tone}"><div class="xc-top"><span>${esc(c.label)}</span><b>${esc(c.value)}</b></div><p>${esc(c.plain)}</p></div>`).join('')}</div>
  ${r.similar && r.similar.length ? `<div class="sh"><h2>${r.kind === 'stock' ? 'Stocks that move like this' : 'Similar funds to look at'}</h2><a class="more" href="#/compare?t=${enc([r.t, ...r.similar.slice(0, 3).map(x => x.t)].join(','))}">Compare them side by side →</a></div>
  <p class="sub">From the ranked list, the ones whose price moves most like this one (1.00 = identical). A similar ride with a calmer swing or lower fees is worth a look.</p>
  <div class="card">${r.similar.map(x => `<a class="tdm" href="#/i/${enc(x.t)}"><span>${esc(x.name)}<small>${esc(x.t)} · ${esc(x.group)} · score ${x.score} · ${esc(x.note)}</small></span><b>${x.corr.toFixed(2)}</b></a>`).join('')}</div>` : ''}
  <div class="card" style="margin-top:28px"><h3>Explain it like I’m new</h3><p class="sub">An AI write-up from only the numbers on this page: what it is, how it behaved, the main risk, and who it usually suits.</p>
    <div id="ai">${r.ai ? aiHTML(r.ai) : '<button class="btn primary" id="ai-go" type="button">Explain this for me</button>'}</div></div>
  <p class="disc">Past performance doesn’t predict future returns. This page helps you understand an investment; it isn’t a recommendation to buy or sell.</p>`;
  let range = '3Y';
  const draw = () => priceChart(r.series, range);
  draw();
  S.ro = new ResizeObserver(() => { clearTimeout(S.rt); S.rt = setTimeout(draw, 100); }); S.ro.observe($('#pc'));
  $('#rng').onclick = e => { const b = e.target.closest('button'); if (!b) return; range = b.dataset.r; $$('#rng button').forEach(x => x.classList.toggle('on', x === b)); draw(); };
  const go = $('#ai-go');
  if (go) go.onclick = async () => {
    const box = $('#ai'); box.innerHTML = `<div class="thinking">${orbHTML(36)}<span>Writing a plain-English explanation…</span></div>`; mountOrbs(box);
    try { r.ai = await api('/api/explain/' + enc(t), { method: 'POST' }); if ($('#ai')) $('#ai').innerHTML = aiHTML(r.ai); }
    catch (e) { if ($('#ai')) $('#ai').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  };
}
const aiHTML = x => `<div class="prose">${md(x.text)}</div><div class="hint">Written by ${esc(x.model)} from the numbers on this page.</div>`;

function yearBars(years) {
  const e = Object.entries(years || {});
  if (!e.length) return '<div class="empty">Not enough history yet.</div>';
  const mx = Math.max(.01, ...e.map(([, v]) => Math.abs(v)));
  return `<div class="yb">${e.map(([y, v]) => `<div class="yb-c"><span class="yb-v ${tone(v)}">${pc(v)}</span>
    <div class="yb-t"><i class="${v >= 0 ? 'pos' : 'neg'}" style="height:${Math.abs(v) / mx * 50}%"></i></div><span class="yb-y">${y}</span></div>`).join('')}</div>`;
}

function priceChart(series, range) {
  const svg = $('#pc'); if (!svg || series.length < 2) return;
  const days = { '6M': 182, '1Y': 365, '3Y': 1095, '5Y': 1830 }[range];
  const start = new Date(new Date(series[series.length - 1][0]) - days * 864e5).toISOString().slice(0, 10);
  let pts = series.filter(p => p[0] >= start); if (pts.length < 2) pts = series;
  const step = Math.ceil(pts.length / 500); if (step > 1) pts = pts.filter((_, i) => i % step === 0 || i === pts.length - 1);
  const W = svg.clientWidth, H = svg.clientHeight, M = { l: 6, r: 62, t: 14, b: 26 };
  if (W < 140 || H < 80) return;  // hidden or mid-navigation: nothing sensible to draw
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const ys = pts.map(p => p[1]); let lo = Math.min(...ys), hi = Math.max(...ys); const pad = (hi - lo) * .08 || 1; lo -= pad; hi += pad;
  const X = i => M.l + i / (pts.length - 1) * (W - M.l - M.r), Y = v => M.t + (hi - v) / (hi - lo) * (H - M.t - M.b);
  const base = pts[0][1], last = pts[pts.length - 1][1], up = last >= base, col = up ? 'var(--teal)' : 'var(--red)';
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(p[1]).toFixed(1)}`).join('');
  let g = '';
  for (let k = 0; k <= 3; k++) { const v = lo + (hi - lo) * (k + .5) / 4; g += `<line x1="${M.l}" x2="${W - M.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line2)"/><text x="${W - M.r + 10}" y="${Y(v) + 4}">€${fmtPrice(v)}</text>`; }
  [0, Math.floor((pts.length - 1) / 2), pts.length - 1].forEach((i, k) => { g += `<text x="${X(i)}" y="${H - 6}" text-anchor="${['start', 'middle', 'end'][k]}">${fmtDate(pts[i][0])}</text>`; });
  svg.innerHTML = `<defs><linearGradient id="pg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" style="stop-color:${col};stop-opacity:.22"/><stop offset="1" style="stop-color:${col};stop-opacity:0"/></linearGradient></defs>${g}
    <line x1="${M.l}" x2="${W - M.r}" y1="${Y(base)}" y2="${Y(base)}" stroke="var(--muted)" stroke-dasharray="2 4" opacity=".6"/>
    <path d="${line}L${X(pts.length - 1)},${H - M.b}L${X(0)},${H - M.b}Z" fill="url(#pg)"/><path d="${line}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round"/>
    <line id="cx" y1="${M.t}" y2="${H - M.b}" stroke="var(--muted)" stroke-dasharray="3 3" opacity="0"/><circle id="cd" r="4.5" fill="${col}" stroke="var(--surface)" stroke-width="2" opacity="0"/>
    <rect id="hit" x="${M.l}" y="0" width="${W - M.l - M.r}" height="${H}" fill="transparent"/>`;
  const ro = $('#ro'), cx = $('#cx', svg), cd = $('#cd', svg), eur = p => `€${Math.round(1000 * p / base).toLocaleString('en-US')}`;
  const rest = () => { cx.setAttribute('opacity', 0); cd.setAttribute('opacity', 0);
    ro.innerHTML = `€1,000 put in on ${fmtDate(pts[0][0], true)} is worth <b class="${tone(last / base - 1)}">${eur(last)}</b> today <span class="${tone(last / base - 1)}">(${pc(last / base - 1)})</span>`; };
  rest();
  const hit = $('#hit', svg);
  hit.onmousemove = e => {
    const b = svg.getBoundingClientRect(), x = (e.clientX - b.left) * (W / b.width);
    const i = Math.max(0, Math.min(pts.length - 1, Math.round((x - M.l) / (W - M.l - M.r) * (pts.length - 1)))), p = pts[i];
    cx.setAttribute('x1', X(i)); cx.setAttribute('x2', X(i)); cx.setAttribute('opacity', 1);
    cd.setAttribute('cx', X(i)); cd.setAttribute('cy', Y(p[1])); cd.setAttribute('opacity', 1);
    ro.innerHTML = `<b>${fmtDate(p[0], true)}</b> · €${fmtPrice(p[1])} · €1,000 from the start of this chart → <b class="${tone(p[1] / base - 1)}">${eur(p[1])}</b>`;
  };
  hit.onmouseleave = rest;
}

/* ---------- search all markets ---------- */
async function vSearch(q) {
  const term = (q.get('q') || '').trim();
  view.innerHTML = `<div class="page-h fade"><div class="eyebrow">Search</div><h1>All markets</h1>
    <p>Any stock, ETF or fund, by name or ticker. Ones in the ranked list show their score; everything else opens with the same chart and plain-English numbers.</p></div>
  <form id="sf" class="ask-box th-box"><input class="in" id="q" value="${esc(term)}" placeholder="e.g. Siemens Energy, Coca-Cola, BIT Global Technology" autocomplete="off" maxlength="60" aria-label="Search all markets"><button class="btn primary" type="submit">Search</button></form>
  <div id="sr">${term ? `<div class="loading sm">${orbHTML(48, 'Searching…')}</div>` : '<div class="empty">Type a company, fund or ticker.</div>'}</div>`;
  mountOrbs(view);
  $('#sf').onsubmit = e => { e.preventDefault(); const v = $('#q').value.trim(); if (v) location.hash = '#/search?q=' + enc(v); };
  if (!term) { $('#q').focus(); return; }
  let r;
  try { r = await api('/api/search?q=' + enc(term)); } catch (e) { if ($('#sr')) $('#sr').innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  if (!$('#sr') || (parseHash().q.get('q') || '').trim() !== term) return;
  $('#sr').innerHTML = r.length ? `<div class="tl" style="margin-top:18px">${r.map(x => `<a class="srch" href="#/i/${enc(x.t)}">
      <span><b>${esc(x.name)}</b><small>${esc(x.t)} · ${KIND_L[x.kind] || ''} · ${esc(x.where)}${x.in_list ? ' · in the ranked list' : ''}</small></span>
      ${x.in_list ? `<span class="sc" style="--c:${conv(5 + x.score / 20)}">${x.score}</span>` : '<span class="go">→</span>'}</a>`).join('')}</div>
    <p class="hint" style="margin-top:14px">Covers stocks, ETFs and funds listed on Yahoo Finance. Crypto, indices and single bonds aren’t included yet. The same company can appear on several exchanges: pick the one you’d actually buy on.</p>`
    : `<div class="empty">Nothing found for “${esc(term)}”. Try the ticker symbol or the fund’s exact name.</div>`;
}

/* ---------- compare ---------- */
const CMP_COL = ['var(--teal)', 'var(--accent)', 'var(--violet)', 'var(--rose)'];
const PRESETS = [['World vs S&P 500', 'VWCE.DE,SXR8.DE'], ['Two world ETFs', 'VWCE.DE,EUNL.DE'], ['BIT tech vs index tech', '0P0001MZUC.F,XDWT.DE,SXRV.DE'],
                 ['Active tech funds', '0P0001MZUC.F,0P00015OFP.F,ARKK.MI'], ['India: index vs active', 'NIFTYBEES.NS,0P0000YWL1.BO'], ['Shares vs bonds vs gold', 'VWCE.DE,VAGF.DE,4GLD.DE']];

async function vCompare(q) {
  const ts = [...new Set((q.get('t') || '').split(',').map(x => x.trim().toUpperCase()).filter(Boolean))].slice(0, 4);
  if (!S.screen) { try { S.screen = await api('/api/screen'); } catch (e) { /* the compare call below reports it */ } }
  const rows = S.screen ? S.screen.rows : [], byT = Object.fromEntries(rows.map(r => [r.t, r]));
  const go = list => { location.hash = '#/compare' + (list.length ? '?t=' + enc(list.join(',')) : ''); };
  const one = ts.length === 1 && byT[ts[0]];
  const sugg = one ? rows.filter(r => r.kind === one.kind && r.group === one.group && r.t !== one.t).slice(0, 4).map(r => [r.name, [one.t, r.t].join(',')]) : PRESETS;
  view.innerHTML = `
  <div class="page-h fade"><div class="eyebrow">Compare</div><h1>Side by side</h1>
    <p>Pick 2 to 4 funds or stocks. The chart shows what €1,000 put into each would have become, so different prices compare fairly.</p></div>
  <div class="cmp-pick">${ts.map((t, i) => `<span class="tag"><i class="dot" style="background:${CMP_COL[i]}"></i><span class="nm" data-t="${esc(t)}">${esc(byT[t] ? byT[t].name : t)}</span><button type="button" data-rm="${esc(t)}" aria-label="Remove">✕</button></span>`).join('')}
    ${ts.length < 4 ? `<form id="cmpf" class="cmp-add"><input class="in" id="cmpq" list="cmp-list" placeholder="${ts.length ? 'Add another…' : 'Add any fund or stock (name or ticker)'}" autocomplete="off"><datalist id="cmp-list">${rows.map(r => `<option value="${esc(r.t)}">${esc(r.name)}</option>`).join('')}</datalist></form>` : ''}</div>
  ${ts.length < 2 ? `<div class="chips" style="margin-top:16px"><span class="lab">${one ? 'Compare with' : 'Try'}</span>${sugg.map(([l, v]) => `<a class="cf" href="#/compare?t=${enc(v)}">${esc(l)}</a>`).join('')}</div>` : ''}
  <div id="cmp">${ts.length >= 2 ? `<div class="loading sm">${orbHTML(56, 'Lining them up…')}</div>` : ''}</div>`;
  mountOrbs(view);
  view.onclick = e => { const rm = e.target.closest('[data-rm]'); if (rm) go(ts.filter(t => t !== rm.dataset.rm)); };
  const f = $('#cmpf');
  if (f) f.onsubmit = async e => {
    e.preventDefault();
    const hit = await findAny($('#cmpq').value);
    if (!hit) return toast('Couldn’t find that. Try the ticker symbol.', true);
    go([...ts, hit.t]);
  };
  const cq = $('#cmpq'); if (cq) cq.onchange = () => f.requestSubmit();
  if (ts.length < 2) return;
  let c;
  try { c = await api('/api/compare?t=' + enc(ts.join(','))); }
  catch (e) { if ($('#cmp')) $('#cmp').innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  if (!$('#cmp')) return;
  c.items.forEach(it => { const el = $$('.cmp-pick .nm').find(x => x.dataset.t === it.t); if (el) el.textContent = it.name; });
  const col = Object.fromEntries(c.items.map((it, i) => [it.t, CMP_COL[ts.indexOf(it.t) >= 0 ? ts.indexOf(it.t) : i]]));
  const ROWS = [['Score', it => it.score, v => v, 1], ['Last 12 months', it => it.m.r1y, v => pc(v), 1], ['Growth per year', it => it.m.growth, v => pc(v), 1],
                ['Swing (volatility)', it => it.m.vol, v => pc(v, false), -1], ['Worst fall', it => it.m.mdd, v => pc(v), 1], ['Return for the risk', it => it.m.rpr, v => v == null ? '—' : v.toFixed(2), 1]];
  $('#cmp').innerHTML = `
  <div class="card chart-card" style="margin-top:22px"><div class="chart-top"><div class="readout" id="cro"></div>
    <div class="seg" id="crng" role="group" aria-label="Chart range">${['1Y', '3Y', '5Y'].map(x => `<button type="button" data-r="${x}" class="${x === '3Y' ? 'on' : ''}">${x}</button>`).join('')}</div></div>
    <svg class="pchart" id="cpc" role="img" aria-label="Growth of 1,000 euros in each instrument"></svg></div>
  <div class="grid2" style="margin-top:28px">
    <div class="card"><h3>In plain English</h3><ul class="plain">${c.summary.map(s => `<li>${esc(s)}</li>`).join('')}</ul>
      ${c.pairs.length ? `<h3 style="margin-top:22px">Do they actually spread your risk?</h3><p class="sub">“Moving together” runs from 1 (always rise and fall together) to 0 (unrelated), measured on weekly returns over 3 years. Close to 1 means owning both is almost like owning one.</p>
      ${c.pairs.map(p => `<div class="pair"><b style="color:${p.r >= .9 ? 'var(--red)' : p.r >= .6 ? 'var(--accent)' : 'var(--teal)'}">${p.r.toFixed(2)}</b><span>${esc(p.plain)}</span></div>`).join('')}` : ''}</div>
    <div class="card"><h3>The numbers</h3><table class="ctab"><thead><tr><th></th>${c.items.map(it => `<th><a href="#/i/${enc(it.t)}"><i class="dot" style="background:${col[it.t]}"></i>${esc(it.name)}</a></th>`).join('')}</tr></thead>
      <tbody>${ROWS.map(([l, get, fmt, dir]) => { const vals = c.items.map(get), ok = vals.filter(v => v != null), best = ok.length ? (dir > 0 ? Math.max(...ok) : Math.min(...ok)) : null;
        return `<tr><th>${l}</th>${vals.map(v => `<td class="${v != null && v === best ? 'best' : ''}">${fmt(v)}</td>`).join('')}</tr>`; }).join('')}</tbody></table>
      <p class="hint">Highlighted = best in that row. All in euros; growth per year uses 3 years where available.</p></div>
  </div>
  <p class="disc">Past performance doesn’t predict future returns. Comparing helps you understand the trade-offs; it isn’t a recommendation.</p>`;
  let range = '3Y';
  const draw = () => cmpChart(c, col, range);
  draw();
  S.ro = new ResizeObserver(() => { clearTimeout(S.rt); S.rt = setTimeout(draw, 100); }); S.ro.observe($('#cpc'));
  $('#crng').onclick = e => { const b = e.target.closest('button'); if (!b) return; range = b.dataset.r; $$('#crng button').forEach(x => x.classList.toggle('on', x === b)); draw(); };
}

function cmpChart(c, col, range) {
  const svg = $('#cpc'); if (!svg) return;
  const W = svg.clientWidth, H = svg.clientHeight, M = { l: 6, r: 70, t: 14, b: 26 };
  if (W < 140 || H < 80) return;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const days = { '1Y': 365, '3Y': 1095, '5Y': 1830 }[range];
  const lastAll = c.items.map(it => c.series[it.t].at(-1)[0]).sort()[0];
  let start = new Date(new Date(lastAll) - days * 864e5).toISOString().slice(0, 10);
  start = [start, ...c.items.map(it => c.series[it.t][0][0])].sort().at(-1);  // common start: the youngest series decides
  const lines = c.items.map(it => {
    let pts = c.series[it.t].filter(p => p[0] >= start);
    const step = Math.ceil(pts.length / 400); if (step > 1) pts = pts.filter((_, i) => i % step === 0 || i === pts.length - 1);
    const base = pts[0][1];
    return { it, pts: pts.map(([d, v]) => [d, 1000 * v / base]) };
  });
  const t0 = +new Date(start), t1 = Math.max(...lines.map(l => +new Date(l.pts.at(-1)[0])));
  const ys = lines.flatMap(l => l.pts.map(p => p[1])); let lo = Math.min(...ys, 1000), hi = Math.max(...ys, 1000);
  const pad = (hi - lo) * .08 || 50; lo -= pad; hi += pad;
  const X = d => M.l + (+new Date(d) - t0) / (t1 - t0 || 1) * (W - M.l - M.r), Y = v => M.t + (hi - v) / (hi - lo) * (H - M.t - M.b);
  let g = '';
  for (let k = 0; k <= 3; k++) { const v = lo + (hi - lo) * (k + .5) / 4; g += `<line x1="${M.l}" x2="${W - M.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line2)"/><text x="${W - M.r + 10}" y="${Y(v) + 4}">€${Math.round(v).toLocaleString('en-US')}</text>`; }
  g += `<line x1="${M.l}" x2="${W - M.r}" y1="${Y(1000)}" y2="${Y(1000)}" stroke="var(--muted)" stroke-dasharray="2 4" opacity=".7"/>`;
  [[start, 'start'], [new Date((t0 + t1) / 2).toISOString().slice(0, 10), 'middle'], [new Date(t1).toISOString().slice(0, 10), 'end']].forEach(([d, a]) => { g += `<text x="${X(d)}" y="${H - 6}" text-anchor="${a}">${fmtDate(d)}</text>`; });
  svg.innerHTML = g + lines.map(l => `<path d="${l.pts.map((p, i) => `${i ? 'L' : 'M'}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join('')}" fill="none" stroke="${col[l.it.t]}" stroke-width="2" stroke-linejoin="round"/>`).join('') +
    `<line id="ccx" y1="${M.t}" y2="${H - M.b}" stroke="var(--muted)" stroke-dasharray="3 3" opacity="0"/>${lines.map((l, i) => `<circle id="ccd${i}" r="4" fill="${col[l.it.t]}" stroke="var(--surface)" stroke-width="2" opacity="0"/>`).join('')}
    <rect id="chit" x="${M.l}" y="0" width="${W - M.l - M.r}" height="${H}" fill="transparent"/>`;
  const ro = $('#cro'), at = (pts, d) => { let lo2 = 0, hi2 = pts.length - 1; while (lo2 < hi2) { const m = (lo2 + hi2 + 1) >> 1; if (pts[m][0] <= d) lo2 = m; else hi2 = m - 1; } return pts[lo2]; };
  const say = d => lines.map(l => { const p = at(l.pts, d); return `<span class="lg"><i class="dot" style="background:${col[l.it.t]}"></i>${esc(l.it.name)} <b class="${tone(p[1] / 1000 - 1)}">€${Math.round(p[1]).toLocaleString('en-US')}</b></span>`; }).join('');
  const rest = () => { $('#ccx', svg).setAttribute('opacity', 0); lines.forEach((_, i) => $('#ccd' + i, svg).setAttribute('opacity', 0)); ro.innerHTML = `<span class="lg-h">€1,000 on ${fmtDate(start, true)} → today</span>` + say('9999'); };
  rest();
  const hit = $('#chit', svg);
  hit.onmousemove = e => {
    const b = svg.getBoundingClientRect(), x = (e.clientX - b.left) * (W / b.width);
    const d = new Date(t0 + Math.max(0, Math.min(1, (x - M.l) / (W - M.l - M.r))) * (t1 - t0)).toISOString().slice(0, 10);
    $('#ccx', svg).setAttribute('x1', X(d)); $('#ccx', svg).setAttribute('x2', X(d)); $('#ccx', svg).setAttribute('opacity', 1);
    lines.forEach((l, i) => { const p = at(l.pts, d), dot = $('#ccd' + i, svg); dot.setAttribute('cx', X(p[0])); dot.setAttribute('cy', Y(p[1])); dot.setAttribute('opacity', 1); });
    ro.innerHTML = `<span class="lg-h">${fmtDate(d, true)}</span>` + say(d);
  };
  hit.onmouseleave = rest;
}

/* ---------- savings plan (Sparplan) ---------- */
async function vPlan(q) {
  if (!S.screen) { try { S.screen = await api('/api/screen'); } catch (e) { /* the plan call reports it */ } }
  const rows = S.screen ? S.screen.rows : [], t = (q.get('t') || 'VWCE.DE').toUpperCase(), m = +(q.get('m') || 100), fee = +(q.get('fee') || 0);
  const five = new Date(Date.now() - 5 * 365 * 864e5).toISOString().slice(0, 7), start = q.get('s') || five, nowM = new Date().toISOString().slice(0, 7);
  view.innerHTML = `
  <div class="page-h fade"><div class="eyebrow">Savings plan</div><h1>What if you’d invested every month?</h1>
    <p>A savings plan (Sparplan) buys a fixed amount on the same day every month, whatever the price. This replays real prices, including the scary moments, so you can see how it actually feels.</p></div>
  <form id="pf2" class="tform plan-form">
    <label>Fund or stock<input class="in" name="t" list="pl-list" value="${esc(t)}" required autocomplete="off"><datalist id="pl-list">${rows.map(r => `<option value="${esc(r.t)}">${esc(r.name)}</option>`).join('')}</datalist></label>
    <label>Every month (€)<input class="in" name="m" inputmode="decimal" value="${m}" required></label>
    <label>Starting<input class="in" name="s" type="month" value="${esc(start)}" max="${nowM}"></label>
    <label>Fee per purchase (€)<input class="in" name="fee" inputmode="decimal" value="${fee}"></label>
    <button class="btn primary" type="submit">Run it</button></form>
  <div id="pl"><div class="loading sm">${orbHTML(56, 'Replaying the months…')}</div></div>`;
  mountOrbs(view);
  $('#pf2').onsubmit = async e => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target)), hit = await findAny(f.t);
    if (!hit) return toast('Couldn’t find that. Try the ticker symbol.', true);
    location.hash = `#/plan?t=${enc(hit.t)}&m=${enc(String(f.m).replace(',', '.'))}&s=${enc(f.s)}&fee=${enc(String(f.fee || 0).replace(',', '.'))}`;
  };
  let p;
  try { p = await api(`/api/plan?t=${enc(t)}&monthly=${m}&start=${enc(start + '-01')}&fee=${fee}`); }
  catch (e) { if ($('#pl')) $('#pl').innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  if (!$('#pl')) return;
  const eu = n => '€' + Math.round(n).toLocaleString('en-US'), w = p.worst;
  const cards = [
    ['Like earning', pc(p.xirr) + ' a year', `Because you added money over time, the fairest single number is the yearly return on each euro while it was invested: about ${pc(p.xirr)} a year. (Professionals call this the money-weighted return.)`, p.xirr > .05 ? 'good' : p.xirr < 0 ? 'bad' : 'neutral'],
    ['Worst moment', pc(w.pct), w.pct < 0 ? `On ${fmtDate(w.date, true)} the ${eu(w.paid)} you’d paid in was worth ${eu(w.value)}. That’s the moment many people stop and sell, and miss the recovery that followed.` : 'It never dipped below what you’d paid in. That’s unusual; most plans go through at least one stretch in the red.', w.pct < -.15 ? 'bad' : 'neutral'],
    ['Buying every month', '€' + fmtPrice(p.avg_price) + ' avg', `You’d own ${p.units.toFixed(2)} units bought at an average of €${fmtPrice(p.avg_price)}; today they’re €${fmtPrice(p.price)} each. When prices dip, the same monthly amount buys more units. That’s why steady buying smooths out bad timing.`, 'neutral'],
    ['Fees', eu(p.fees), p.fees ? `${eu(p.fees)} in purchase fees, ${pc(p.fees / p.paid, false)} of what you put in. Small fees add up over many purchases.` : 'Many brokers run savings plans for free, while some charge around €1 per purchase. Try the fee field to see the difference.', 'neutral'],
  ];
  const hz = 10, sc = y => p.scenarios[y];
  $('#pl').innerHTML = `
  <div class="plan-hero fade"><h2>You’d have put in <b>${eu(p.paid)}</b> and have <b class="${tone(p.gain)}">${eu(p.value)}</b> today.</h2>
    <p>${eu(m)} a month into ${esc(p.name)} since ${fmtDate(p.start, true)}: ${p.months} purchases, ${p.gain >= 0 ? 'a gain of' : 'a loss of'} <b class="${tone(p.gain)}">${eu(Math.abs(p.gain))} (${pc(p.gain_pct)})</b>.${p.start > start + '-01' && p.start.slice(0, 7) !== start ? ` Price history starts ${fmtDate(p.first, true)}, so the plan starts there.` : ''}</p></div>
  <div class="card chart-card"><div class="chart-top"><div class="readout" id="plro"></div><div class="legend2"><span><i class="dot" style="background:var(--muted)"></i>Paid in</span><span><i class="dot" style="background:var(--teal)"></i>Worth</span></div></div>
    <svg class="pchart" id="plc" role="img" aria-label="Amount paid in versus value over time"></svg></div>
  <div class="xcards">${cards.map(([l, v, b, tn]) => `<div class="xc ${tn}"><div class="xc-top"><span>${l}</span><b>${esc(v)}</b></div><p>${esc(b)}</p></div>`).join('')}</div>
  <div class="sh"><h2>If you keep going</h2><div class="seg" id="hz">${[5, 10, 20].map(y => `<button type="button" data-y="${y}" class="${y === hz ? 'on' : ''}">${y} years</button>`).join('')}</div></div>
  <p class="sub">Your pot today plus ${eu(m)} a month, if it grew at a steady 2%, 5% or 8% a year. These are illustrations, not forecasts: real returns zig-zag like the chart above, and nothing guarantees any of them.</p>
  <div class="scen" id="scen"></div>
  <p class="disc">Past performance doesn’t predict future returns. Taxes aren’t included.</p>`;
  const paintScen = y => { const paidThen = p.paid + m * 12 * y;
    $('#scen').innerHTML = Object.entries(sc(y)).map(([k, v]) => `<div class="kpi"><div class="v">${eu(v)}</div><div class="l">at ${k} a year · paid in ${eu(paidThen)}</div></div>`).join(''); };
  paintScen(hz);
  $('#hz').onclick = e => { const b = e.target.closest('button'); if (!b) return; $$('#hz button').forEach(x => x.classList.toggle('on', x === b)); paintScen(+b.dataset.y); };
  const draw = () => planChart(p.timeline);
  draw();
  S.ro = new ResizeObserver(() => { clearTimeout(S.rt); S.rt = setTimeout(draw, 100); }); S.ro.observe($('#plc'));
}

function planChart(tl) {
  const svg = $('#plc'); if (!svg || tl.length < 2) return;
  const W = svg.clientWidth, H = svg.clientHeight, M = { l: 6, r: 70, t: 14, b: 26 };
  if (W < 140 || H < 80) return;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const hi0 = Math.max(...tl.map(x => Math.max(x[1], x[2]))), hi = hi0 * 1.06;
  const X = i => M.l + i / (tl.length - 1) * (W - M.l - M.r), Y = v => M.t + (hi - v) / hi * (H - M.t - M.b);
  const paid = tl.map((x, i) => `${i ? 'L' + X(i).toFixed(1) + ',' + Y(tl[i - 1][1]).toFixed(1) + 'L' : 'M'}${X(i).toFixed(1)},${Y(x[1]).toFixed(1)}`).join('');
  const val = tl.map((x, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(x[2]).toFixed(1)}`).join('');
  let g = '';
  for (let k = 1; k <= 4; k++) { const v = hi0 * k / 4; g += `<line x1="${M.l}" x2="${W - M.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line2)"/><text x="${W - M.r + 10}" y="${Y(v) + 4}">€${Math.round(v).toLocaleString('en-US')}</text>`; }
  [0, Math.floor((tl.length - 1) / 2), tl.length - 1].forEach((i, k) => { g += `<text x="${X(i)}" y="${H - 6}" text-anchor="${['start', 'middle', 'end'][k]}">${fmtDate(tl[i][0])}</text>`; });
  svg.innerHTML = `<defs><linearGradient id="plg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" style="stop-color:var(--teal);stop-opacity:.22"/><stop offset="1" style="stop-color:var(--teal);stop-opacity:0"/></linearGradient></defs>${g}
    <path d="${val}L${X(tl.length - 1)},${H - M.b}L${X(0)},${H - M.b}Z" fill="url(#plg)"/>
    <path d="${paid}" fill="none" stroke="var(--muted)" stroke-width="1.6" stroke-dasharray="4 3"/>
    <path d="${val}" fill="none" stroke="var(--teal)" stroke-width="2.2" stroke-linejoin="round"/>
    <line id="pcx" y1="${M.t}" y2="${H - M.b}" stroke="var(--muted)" stroke-dasharray="3 3" opacity="0"/><circle id="pcd" r="4.5" fill="var(--teal)" stroke="var(--surface)" stroke-width="2" opacity="0"/>
    <rect id="phit" x="${M.l}" y="0" width="${W - M.l - M.r}" height="${H}" fill="transparent"/>`;
  const ro = $('#plro'), eu = n => '€' + Math.round(n).toLocaleString('en-US');
  const say = i => { const [d, pd, v] = tl[i]; ro.innerHTML = `<b>${fmtDate(d, true)}</b> · paid in ${eu(pd)} · worth <b class="${tone(v - pd)}">${eu(v)}</b> <span class="${tone(v - pd)}">(${pc(pd ? v / pd - 1 : 0)})</span>`; };
  const rest = () => { $('#pcx', svg).setAttribute('opacity', 0); $('#pcd', svg).setAttribute('opacity', 0); say(tl.length - 1); };
  rest();
  const hit = $('#phit', svg);
  hit.onmousemove = e => {
    const b = svg.getBoundingClientRect(), x = (e.clientX - b.left) * (W / b.width), i = Math.max(0, Math.min(tl.length - 1, Math.round((x - M.l) / (W - M.l - M.r) * (tl.length - 1))));
    $('#pcx', svg).setAttribute('x1', X(i)); $('#pcx', svg).setAttribute('x2', X(i)); $('#pcx', svg).setAttribute('opacity', 1);
    $('#pcd', svg).setAttribute('cx', X(i)); $('#pcd', svg).setAttribute('cy', Y(tl[i][2])); $('#pcd', svg).setAttribute('opacity', 1); say(i);
  };
  hit.onmouseleave = rest;
}

/* ---------- price alerts (local only) ---------- */
const AL_UNIT = { drop: '%', move: '%', below: '€', above: '€' };
const AL_LABEL = { drop: 'Falls this far below its 1-year high', below: 'Price falls below', above: 'Price rises above', move: 'Moves this much in one day' };

async function refreshAlerts(data) {
  try { S.al = data || await api('/api/alerts'); } catch (e) { S.al = null; }
  const n = S.al ? S.al.alerts.filter(a => a.triggered).length : 0, b = $('#al-badge');
  if (b) { b.textContent = n; b.hidden = !n; }
  if (!S.al || !('Notification' in window) || Notification.permission !== 'granted') return;
  S.al.alerts.filter(a => a.triggered).forEach(a => {  // once per alert per trading day
    const k = `notified:${a.id}:${a.asof}`;
    try { if (localStorage.getItem(k)) return; localStorage.setItem(k, 1); } catch (e) { return; }
    new Notification('My Financial Scanner', { body: a.text });
  });
}

async function vAlerts() {
  view.innerHTML = `<div class="page-h fade"><div class="eyebrow">Alerts</div><h1>Price alerts</h1>
    <p>Get flagged when something you care about moves. Checked against end-of-day prices whenever this app is open; stored only on this computer.</p></div>
    <div id="al"><div class="loading sm">${orbHTML(56, 'Checking prices…')}</div></div>`;
  mountOrbs(view);
  if (!S.screen) { try { S.screen = await api('/api/screen'); } catch (e) { /* datalist just stays empty */ } }
  await refreshAlerts();
  if (!$('#al')) return;
  if (!S.al) { $('#al').innerHTML = `<div class="err-card"><h2>Alerts are private</h2><p>They only open when the app runs on your own computer.</p></div>`; return; }
  alPaint();
}

function alPaint() {
  const A = S.al.alerts, rows = S.screen ? S.screen.rows : [], perm = 'Notification' in window ? Notification.permission : 'unsupported';
  $('#al').innerHTML = `
  <div class="note info" style="margin-top:24px"><span>i</span><p>A 10–20% fall from a high is a normal pull-back for shares and happens most years. Use alerts to pay attention, not to panic-sell. The worst-fall numbers in the screener show how deep each one has dropped before.</p></div>
  <div class="cta" style="margin-top:18px"><button class="btn" id="al-hold" type="button">Add a 10% drop alert for each holding</button>
    ${perm === 'default' ? '<button class="btn ghost" id="al-perm" type="button">Notify me in this browser</button>' : perm === 'granted' ? '<span class="hint" style="align-self:center">Browser notifications are on.</span>' : ''}</div>
  <div class="card" style="margin-top:22px"><h3>New alert</h3>
    <form id="alf" class="tform al-form">
      <label>Fund or stock<input class="in" name="ticker" list="al-list" placeholder="VWCE.DE" required autocomplete="off"><datalist id="al-list">${rows.map(r => `<option value="${esc(r.t)}">${esc(r.name)}</option>`).join('')}</datalist></label>
      <label>When it…<select class="in" name="kind">${Object.entries(AL_LABEL).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}</select></label>
      <label><span id="al-unit">Percent (%)</span><input class="in" name="value" inputmode="decimal" placeholder="10" required></label>
      <button class="btn primary" type="submit">Add alert</button></form></div>
  <div class="sh"><h2>Your alerts</h2><span class="more">${A.filter(a => a.triggered).length} fired · ${A.length} total</span></div>
  ${A.length ? `<div class="tl">${A.map(a => `<div class="al-r ${a.triggered ? 'hit' : ''}"><span class="al-s">${a.triggered ? 'Fired' : 'Watching'}</span>
      <span><a href="#/i/${enc(a.ticker)}"><b>${esc(a.ticker)}</b></a> · ${esc(AL_LABEL[a.kind].toLowerCase())} ${a.kind === 'below' || a.kind === 'above' ? '€' + a.value : a.value + '%'}<br><small>${esc(a.text)}</small></span>
      <button class="btn sm ghost" data-del="${esc(a.id)}" type="button">Delete</button></div>`).join('')}</div>` : '<div class="empty">No alerts yet. Add one above, or one click for all your holdings.</div>'}`;
  const f = $('#alf');
  f.kind.onchange = () => { $('#al-unit').textContent = AL_UNIT[f.kind.value] === '%' ? 'Percent (%)' : 'Price in euros (€)'; };
  f.onsubmit = async e => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(f)); body.ticker = body.ticker.trim().toUpperCase();
    try { await refreshAlerts(await api('/api/alerts', { method: 'POST', body })); alPaint(); toast(`Alert added for ${body.ticker}.`); }
    catch (err) { toast(err.message, true); }
  };
  $('#al-hold').onclick = async () => {
    try { const r = await api('/api/alerts/holdings', { method: 'POST' }); await refreshAlerts(r); alPaint(); toast(r.added ? `Added ${plural(r.added, 'alert')}.` : 'Every holding already has a drop alert (or you have no holdings yet).'); }
    catch (err) { toast(err.message, true); }
  };
  const pb = $('#al-perm'); if (pb) pb.onclick = async () => { await Notification.requestPermission(); await refreshAlerts(S.al); alPaint(); };
  $$('[data-del]', $('#al')).forEach(b => b.onclick = async () => {
    try { await refreshAlerts(await api('/api/alerts/' + enc(b.dataset.del), { method: 'DELETE' })); alPaint(); toast('Alert deleted.'); }
    catch (err) { toast(err.message, true); }
  });
}

/* ---------- IPOs ---------- */
async function vIpos() {
  view.innerHTML = `<div class="page-h fade"><div class="eyebrow">IPOs</div><h1>Companies about to go public</h1>
    <p>An IPO is when a company first sells shares to the public. Exciting, but read the basics below before you get swept up.</p></div>
    <div class="note info" style="margin-top:22px"><span>i</span><p>As a private investor in Europe you usually can’t buy at the IPO price: you buy once it starts trading, often after a first-day jump. The first weeks can swing wildly, and studies have long found that new listings on average lag the wider market over the following years. Indian IPOs work differently: you apply during a subscription window through your broker (Zerodha, for example) and only get shares if they’re allotted to you.</p></div>
    <div id="ipo"><div class="loading sm">${orbHTML(56, 'Checking the calendar…')}</div></div>`;
  mountOrbs(view);
  try { S.ipo = await api('/api/ipos'); } catch (e) { if ($('#ipo')) $('#ipo').innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  if ($('#ipo')) ipoPaint();
}

function ipoRow(i) {
  return `<div class="ipo-r"><span class="cat-d${i.upcoming && i.date && (new Date(i.date) - Date.now()) / 864e5 <= 7 ? ' hot' : ''}">${i.date ? fmtDate(i.date, true).replace(/ \d{4}$/, '') : 'TBA'}</span>
    <span><b>${esc(i.name)}</b> <small>${esc([i.symbol, i.exchange].filter(Boolean).join(' · '))}</small><br><small class="ipo-t">${esc(i.text)}</small></span>
    <span class="ipo-s ${i.status}">${esc(i.status)}</span></div>`;
}

function ipoPaint() {
  const I = S.ipo, up = I.calendar.filter(i => i.upcoming), done = I.calendar.filter(i => !i.upcoming);
  const keyMsg = `<div class="card" style="margin-top:22px"><h3>Turn on the US IPO calendar</h3><p class="sub" style="margin-bottom:0">It uses Finnhub’s IPO calendar with your own free key: sign up at <a href="https://finnhub.io/register" target="_blank" rel="noopener">finnhub.io</a>, add <code>FINNHUB_API_KEY=…</code> to your <code>.env</code>, and restart the app. Indian and European listings you hear about can go in your watch list below.</p></div>`;
  $('#ipo').innerHTML = (I.error === 'nokey' ? keyMsg : I.error ? `<div class="note warn" style="margin-top:22px"><span>!</span><p>${esc(I.error)}</p></div>` : '') +
    (up.length ? `<div class="sh"><h2>Coming up</h2><span class="more">US listings · Finnhub</span></div><div class="tl">${up.map(ipoRow).join('')}</div>` : (!I.error ? '<div class="empty">No US listings scheduled in the next three months.</div>' : '')) +
    (done.length ? `<div class="sh"><h2>Recently listed</h2></div><div class="tl">${done.slice(0, 12).map(ipoRow).join('')}</div>` : '') +
    (I.watch ? `<div class="sh"><h2>IPOs I’m watching</h2><span class="more">private · this computer only</span></div>
      <p class="sub">For listings the calendar doesn’t cover, like Indian IPOs on NSE/BSE or European ones you read about. Add the expected date and you’ll see the countdown.</p>
      <div class="card"><form id="ipf" class="tform ipo-form">
        <label>Company<input class="in" name="name" required maxlength="80" placeholder="e.g. a company you read about"></label>
        <label>Exchange<input class="in" name="exchange" maxlength="30" placeholder="NSE, Xetra…"></label>
        <label>Expected date<input class="in" name="date" type="date"></label>
        <label>Link (optional)<input class="in" name="link" type="url" placeholder="https://…"></label>
        <button class="btn primary" type="submit">Watch it</button></form></div>
      ${I.watch.length ? `<div class="tl">${I.watch.map(w => { const dd = w.date ? Math.ceil((new Date(w.date) - Date.now()) / 864e5) : null;
        return `<div class="ipo-r"><span class="cat-d${dd != null && dd <= 7 && dd >= 0 ? ' hot' : ''}">${dd == null ? 'TBA' : dd > 0 ? `in ${dd}d` : dd === 0 ? 'today' : 'listed'}</span>
          <span><b>${esc(w.name)}</b> <small>${esc(w.exchange || '')}${w.date ? ' · ' + fmtDate(w.date, true) : ''}</small>${w.link ? `<br><small><a href="${esc(w.link)}" target="_blank" rel="noopener">${esc(w.link.replace(/^https?:\/\//, '').slice(0, 60))} ↗</a></small>` : ''}</span>
          <button class="btn sm ghost" data-del="${esc(w.id)}" type="button">Remove</button></div>`; }).join('')}</div>` : ''}` : '');
  const f = $('#ipf');
  if (f) f.onsubmit = async e => {
    e.preventDefault();
    try { S.ipo = await api('/api/ipos/watch', { method: 'POST', body: Object.fromEntries(new FormData(f)) }); ipoPaint(); toast('Added to your IPO watch list.'); }
    catch (err) { toast(err.message, true); }
  };
  $$('[data-del]', $('#ipo')).forEach(b => b.onclick = async () => {
    try { S.ipo = await api('/api/ipos/watch/' + enc(b.dataset.del), { method: 'DELETE' }); ipoPaint(); toast('Removed.'); }
    catch (err) { toast(err.message, true); }
  });
}

/* ---------- portfolio (local only) ---------- */
const euro = (n, signed) => n == null ? '—' : (signed && n > 0 ? '+' : n < 0 ? '−' : '') + '€' + Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: Math.abs(n) >= 1000 ? 0 : 2, minimumFractionDigits: Math.abs(n) >= 1000 ? 0 : 2 });
const today = () => new Date().toISOString().slice(0, 10);
const ccyFmt = (c, n) => (!c || c === 'EUR') ? '€' + fmtPrice(n) : `${c === 'GBp' ? 'GBp' : c} ${fmtPrice(n)}`;

async function vPortfolio() {
  view.innerHTML = `<div class="page-h fade"><div class="eyebrow">Portfolio</div><h1>Your portfolio, explained</h1>
    <p>Add your trades to see what you own, how it’s doing, and how today’s mix would have behaved, in plain English. Stored only on this computer and never uploaded.</p></div>
    <div id="pf"><div class="loading sm">${orbHTML(56, 'Loading your portfolio…')}</div></div>`;
  mountOrbs(view);
  try { [S.pf] = await Promise.all([api('/api/portfolio'), S.screen ? null : api('/api/screen').then(x => { S.screen = x; }).catch(() => null)]); }
  catch (e) {
    if ($('#pf')) $('#pf').innerHTML = `<div class="err-card"><h2>Portfolio is private</h2><p>${esc(e.message)} Run the app on your laptop (<code>uvicorn server:app</code>) and open it at localhost.</p></div>`;
    return;
  }
  if ($('#pf')) pfPaint();
}

function tradeForm() {
  const opts = (S.screen ? S.screen.rows : []).map(r => `<option value="${esc(r.t)}">${esc(r.name)}</option>`).join('');
  return `<form id="tf" class="tform">
    <label>Date<input class="in" name="date" type="date" value="${today()}" max="${today()}" required></label>
    <label>Ticker<input class="in" name="ticker" list="tk-list" placeholder="VWCE.DE" required autocomplete="off"><datalist id="tk-list">${opts}</datalist></label>
    <label>Buy / sell<select class="in" name="side"><option value="buy">Buy</option><option value="sell">Sell</option></select></label>
    <label>Quantity<input class="in" name="qty" inputmode="decimal" placeholder="10" required></label>
    <label>Price per unit<input class="in" name="price" inputmode="decimal" placeholder="118.40" required></label>
    <label>Currency<select class="in" name="ccy">${['EUR', 'USD', 'INR', 'GBP', 'CHF', 'DKK', 'SEK', 'NOK', 'CAD', 'JPY', 'HKD', 'AUD'].map(c => `<option>${c}</option>`).join('')}</select></label>
    <label>Fees<input class="in" name="fees" inputmode="decimal" placeholder="1.00"></label>
    <button class="btn primary" type="submit">Add trade</button></form>
    <p class="hint">Use the exchange suffix: VWCE.DE (Xetra), ASML.AS (Amsterdam), RELIANCE.NS (NSE India); US stocks need none (AAPL). Enter the price in the currency you paid. It's converted to euros at that day's exchange rate.</p>`;
}

function importBox() {
  return `<div class="imp-box"><label class="btn"><input type="file" id="csvf" accept=".csv,text/csv" hidden>Import a broker export (CSV)</label>
    <a class="btn ghost" href="/api/trades/template.csv">Download the template</a></div>
    <p class="hint">Recognised automatically: <b>Revolut</b> account statement, <b>Interactive Brokers</b> activity statement or Flex query, <b>Zerodha</b> tradebook. Anything else needs date, ticker, quantity and price columns (English or German headers). Dividends, top-ups and fees are skipped, and importing the same file twice won’t double anything.</p><div id="imp-err"></div>`;
}

function pfPaint() {
  const P = S.pf, el = $('#pf'), T = P.totals;
  if (!P.trades.length) {
    el.innerHTML = `<div class="grid2 fade" style="margin-top:28px">
      <div class="card"><h3>Add your first trade</h3><p class="sub">One buy is enough to start. You can add the rest later or import them.</p>${tradeForm()}</div>
      <div class="card"><h3>Or import your history</h3><p class="sub">Most broker apps can export your transactions as a CSV file.</p>${importBox()}</div></div>`;
    return pfWire();
  }
  const maxW = Math.max(...P.holdings.map(h => h.weight || 0), .01);
  el.innerHTML = `
  <section class="kpis fade" style="margin-top:26px">
    <div class="kpi"><div class="v">${euro(T.value)}</div><div class="l">Worth today</div></div>
    <div class="kpi"><div class="v">${euro(T.cost)}</div><div class="l">You put in</div></div>
    <div class="kpi"><div class="v ${tone(T.pnl)}">${euro(T.pnl, true)}</div><div class="l">Profit / loss · ${pc(T.pnl_pct)}</div></div>
    <div class="kpi"><div class="v ${tone(T.day)}">${euro(T.day, true)}</div><div class="l">Last trading day</div></div>
    <div class="kpi"><div class="v">${T.n}</div><div class="l">Holdings${T.realized ? ` · ${euro(T.realized, true)} realised` : ''}</div></div>
  </section>
  ${P.notes.length ? `<div class="sh"><h2>What stands out</h2></div><div class="notes">${P.notes.map(n => `<div class="note ${n.kind}"><span>${n.kind === 'warn' ? '!' : 'i'}</span><p>${esc(n.text)}</p></div>`).join('')}</div>` : ''}
  <div class="sh"><h2>What you own</h2></div>
  <div class="hr hr-h"><span>Holding</span><span>Share of portfolio</span><span class="num">Worth</span><span class="num">Profit / loss</span><span class="num col-avg">Avg cost → now</span><span class="num col-sc" data-tip="Its screener score (0–100), if it's in the screener list.">Score</span></div>
  ${P.holdings.map(h => `<a class="hr" href="${h.price != null ? '#/i/' + enc(h.ticker) : '#/portfolio'}">
      <span class="hr-n"><b>${esc(h.name)}</b><span>${esc(h.ticker)} · ${esc(h.group)} · ${+h.qty.toFixed(4)} units</span></span>
      <span class="hr-w"><span class="track"><i style="width:${(h.weight || 0) / maxW * 100}%"></i></span><b>${h.weight == null ? '—' : pc(h.weight, false)}</b></span>
      <span class="num">${euro(h.value)}</span>
      <span class="num ${tone(h.pnl)}">${euro(h.pnl, true)}<small>${pc(h.pnl_pct)}</small></span>
      <span class="num col-avg">${h.price == null ? 'no price' : `€${fmtPrice(h.avg)} → €${fmtPrice(h.price)}`}</span>
      <span class="num col-sc">${h.score == null ? '—' : `<span class="sc" style="--c:${conv(5 + h.score / 20)}">${h.score}</span>`}</span></a>`).join('')}
  ${P.mix ? `<div class="sh"><h2>If you’d held today’s mix</h2></div>
    <p class="sub">Your current holdings, in today’s amounts, replayed over the past ${P.mix.short ? 'months we have data for' : '3 years'}. It shows how this mix tends to move, not what you actually earned.</p>
    <div class="xcards">${P.mix_cards.map(c => `<div class="xc ${c.tone}"><div class="xc-top"><span>${esc(c.label)}</span><b>${esc(c.value)}</b></div><p>${esc(c.plain)}</p></div>`).join('')}</div>
    <div class="grid2" style="margin-top:28px"><div class="card"><h3>Year by year</h3><p class="sub">How today’s mix did each calendar year, in euros.</p>${yearBars(P.mix.years)}</div>
      <div class="card"><h3>Where your money is</h3><p class="sub">By type and by group. A spread across groups usually means smoother swings.</p>
        ${[...P.alloc.kind.map(([k, w]) => [k === 'etf' ? 'Index funds (ETFs/ETCs)' : k === 'fund' ? 'Active funds' : 'Single stocks', w]), ['', null], ...P.alloc.group].map(([k, w]) => w == null ? '<div style="height:12px"></div>' :
          `<div class="pp"><div class="pp-l"><span>${esc(k)}</span><b>${pc(w, false)}</b></div><div class="pp-t"><i style="width:${w * 100}%;--c:var(--teal)"></i></div></div>`).join('')}</div></div>` : ''}
  <div class="sh"><h2>Your trades</h2><span class="more">${P.trades.length} recorded · fees ${euro(T.fees)}</span></div>
  <div class="grid2" style="margin-top:18px"><div class="card"><h3>Add a trade</h3>${tradeForm()}</div><div class="card"><h3>Import</h3>${importBox()}</div></div>
  <div class="tl">${P.trades.map(t => `<div class="tl-r"><span class="cat-d">${fmtDate(t.date, true)}</span><span class="tl-s ${t.side}">${t.side}</span>
      <span><b>${esc(t.ticker)}</b> ${+t.qty.toFixed(4)} × ${ccyFmt(t.ccy, t.price)}${t.fees ? ` <small>+ ${ccyFmt(t.ccy, t.fees)} fees</small>` : ''} <small>· ${esc(t.broker || 'manual')}${t.note ? ' · ' + esc(t.note) : ''}</small></span>
      <span class="num">${ccyFmt(t.ccy, t.qty * t.price)}</span><button class="btn sm ghost" data-del="${esc(t.id)}" type="button" aria-label="Delete trade">Delete</button></div>`).join('')}</div>`;
  pfWire();
}

function pfWire() {
  const f = $('#tf');
  if (f) f.onsubmit = async e => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(f)); body.ticker = body.ticker.trim().toUpperCase();
    try { S.pf = await api('/api/trades', { method: 'POST', body }); toast(`Added ${body.side} of ${body.ticker}.`); pfPaint(); }
    catch (err) { toast(err.message, true); }
  };
  const file = $('#csvf');
  if (file) file.onchange = async () => {
    const fl = file.files[0]; if (!fl) return;
    try {
      const r = await api('/api/trades/import', { method: 'POST', body: { csv: await fl.text() } });
      S.pf = r.portfolio; pfPaint();
      toast(`${r.format ? `Read as ${r.format}: ` : ''}imported ${plural(r.added, 'trade')}${r.skipped ? `, ${r.skipped} already there` : ''}${r.nontrades ? `, ${r.nontrades} non-trade rows skipped` : ''}.`, !r.added && r.errors.length > 0);
      if (r.errors.length && $('#imp-err')) $('#imp-err').innerHTML = `<div class="note warn"><span>!</span><p>${r.errors.map(esc).join('<br>')}</p></div>`;
    } catch (err) { toast(err.message, true); }
  };
  $$('[data-del]', view).forEach(b => b.onclick = async () => {
    if (!confirm('Delete this trade?')) return;
    try { S.pf = await api('/api/trades/' + enc(b.dataset.del), { method: 'DELETE' }); pfPaint(); toast('Trade deleted.'); }
    catch (err) { toast(err.message, true); }
  });
}

/* ---------- watchlist drawer ---------- */
const drawer = $('#drawer'), scrim = $('#scrim');
let W = null;
function openDrawer() {
  W = { tickers: { ...S.data.watchlist.tickers }, sectors: [...S.data.watchlist.sectors], sugg: {}, busy: false, finding: false };
  paintDrawer(); drawer.classList.add('open'); scrim.classList.add('on'); drawer.setAttribute('aria-hidden', 'false');
  setTimeout(() => $('#ind', drawer) && $('#ind', drawer).focus(), 340);
}
function closeDrawer() { drawer.classList.remove('open'); scrim.classList.remove('on'); drawer.setAttribute('aria-hidden', 'true'); }
function paintDrawer() {
  const scanning = S.data.rescanning, kept = new Set(Object.keys(W.tickers));
  const sugg = Object.entries(W.sugg).filter(([t]) => !kept.has(t));
  drawer.innerHTML = `<button class="btn icon ghost x" id="dx" type="button" aria-label="Close">✕</button>
    <h2>Watchlist</h2><p class="lead">New scans score every market against this list. Existing signals keep the tags they already have until you rescan.</p>
    <div class="dsec"><h3><span>Tracking</span><span>${kept.size}</span></h3>
      <div class="tags">${[...kept].map(t => `<span class="tag" title="${esc(W.tickers[t])}">${esc(t)}<button data-rm="${esc(t)}" type="button" aria-label="Remove ${esc(t)}">✕</button></span>`).join('') || '<span class="hint">Nothing tracked — add a theme below.</span>'}</div></div>
    <div class="dsec"><h3><span>Add by industry or theme</span></h3>
      <form class="row" id="indf"><input class="in" id="ind" placeholder="e.g. semiconductors, biotech, defense" autocomplete="off" maxlength="60"><button class="btn" type="submit"${W.finding ? ' disabled' : ''}>${W.finding ? 'Finding…' : 'Find'}</button></form>
      ${sugg.length ? `<div class="tags" style="margin-top:12px">${sugg.map(([t, dsc]) => `<button class="tag add" data-add="${esc(t)}" type="button">+ ${esc(t)}<small>${esc(dsc)}</small></button>`).join('')}</div>` : '<div class="hint">We’ll suggest liquid US-listed tickers central to the theme.</div>'}</div>
    <div class="dsec"><h3><span>Focus sectors</span><span>one per line</span></h3><textarea class="in" id="sects" rows="6">${esc(W.sectors.join('\n'))}</textarea></div>
    ${S.data.local ? `<div class="dsec"><button class="btn primary lg" id="save" type="button" style="width:100%"${W.busy ? ' disabled' : ''}>Save watchlist</button></div>`
      : '<div class="dsec"><div class="note info"><span>i</span><p>Editing the watchlist and rescanning work when the app runs on your own computer. Here the data refreshes every hour by itself.</p></div></div>'}
    <div class="dsec"><h3><span>Data</span></h3><div class="d-actions">
      ${scanning ? `<div class="scanning">${orbHTML(30)}<span>Rescanning markets… give it a few minutes.</span></div>` : ''}
      ${S.data.local ? `<button class="btn" id="rescan" type="button"${scanning ? ' disabled' : ''}>↻ Rescan markets</button>` : ''}
      <button class="btn" id="reload" type="button">⟳ Reload data</button></div>
      <div class="hint">Rescan re-scores the top ~300 markets against the current list (about 5 minutes, runs in the background).</div></div>`;
  mountOrbs(drawer);
}
drawer.addEventListener('click', async e => {
  const t = e.target;
  if (t.closest('#dx')) return closeDrawer();
  const rm = t.closest('[data-rm]'); if (rm) { delete W.tickers[rm.dataset.rm]; return paintDrawer(); }
  const add = t.closest('[data-add]'); if (add) { W.tickers[add.dataset.add] = W.sugg[add.dataset.add]; return paintDrawer(); }
  if (t.closest('#save')) {
    W.sectors = $('#sects', drawer).value.split('\n').map(s => s.trim()).filter(Boolean); W.busy = true; paintDrawer();
    try { await api('/api/watchlist', { method: 'POST', body: { tickers: W.tickers, sectors: W.sectors } }); await loadState(true); closeDrawer(); route(true);
          toast('Saved — new scans will score against this list.'); }
    catch (err) { toast(err.message, true); W.busy = false; paintDrawer(); }
  }
  if (t.closest('#rescan')) {
    try { await api('/api/rescan', { method: 'POST' }); S.data.rescanning = true; chrome(); pollRescan(); paintDrawer(); toast('Rescan started.'); }
    catch (err) { toast(err.message, true); }
  }
  if (t.closest('#reload')) { try { await loadState(true); route(true); toast('Data reloaded.'); paintDrawer(); } catch (err) { toast(err.message, true); } }
});
drawer.addEventListener('submit', async e => {
  e.preventDefault();
  const q = $('#ind', drawer).value.trim(); if (!q || W.finding) return;
  W.finding = true; paintDrawer();
  try { W.sugg = await api('/api/suggest?industry=' + enc(q)); if (!Object.keys(W.sugg).length) toast('No tickers found — try a broader term.', true); }
  catch (err) { toast(err.message, true); }
  W.finding = false; paintDrawer(); $('#ind', drawer).value = q;
});
scrim.onclick = closeDrawer;
$('#theme').onclick = () => {
  const n = theme() === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = n;
  try { localStorage.setItem('theme', n); } catch (e) { /* private mode */ }
  chrome(); route(true);
};
addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); return $('#cmdk').hidden ? openCmd() : closeCmd(); }
  if (e.key === 'Escape') { closeDrawer(); closeCmd(); }
  if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
    e.preventDefault();
    if ($('#q')) $('#q').focus(); else openCmd();
  }
});

/* ---------- today (home) ---------- */
async function vToday() {
  const day = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' });
  view.innerHTML = `<div class="page-h fade"><div class="eyebrow">${day}</div><h1>Today</h1>
    <p>Your portfolio, the markets and what changed, in one place.<span class="desk-only"> Press <kbd>⌘K</kbd> to jump anywhere.</span></p></div>
    <div id="td"><div class="loading sm">${orbHTML(56, 'Pulling it together…')}</div></div>`;
  mountOrbs(view);
  const [scr, pf, ipo] = await Promise.all([S.screen ? S.screen : api('/api/screen').catch(() => null), api('/api/portfolio').catch(() => null),
                                            api('/api/ipos').catch(() => null), refreshAlerts()]);
  if (scr) { S.screen = scr; chrome(); }
  S.pf = pf; S.ipo = ipo;
  if (!$('#td')) return;
  const rows = scr ? scr.rows : [], by = Object.fromEntries(rows.map(r => [r.t, r])), asof = scr ? fmtDate(scr.asOf, true) : '';
  const T = pf && pf.totals, held = pf ? pf.holdings.filter(h => h.r1d != null) : [];
  const fired = S.al ? S.al.alerts.filter(a => a.triggered) : [];
  const movers = [...rows].filter(r => r.m.r1d != null).sort((a, b) => b.m.r1d - a.m.r1d);
  const soonIpo = ipo ? [...ipo.calendar.filter(i => i.upcoming && i.date && (new Date(i.date) - Date.now()) / 864e5 <= 7),
                         ...(ipo.watch || []).filter(w => w.date && (new Date(w.date) - Date.now()) / 864e5 <= 14 && new Date(w.date) >= Date.now() - 864e5)] : [];
  const mvRow = r => `<a class="tdm" href="#/i/${enc(r.t)}"><span>${esc(r.name)}<small>${esc(r.t)} · ${esc(r.group)}</small></span><b class="${tone(r.m.r1d)}">${pc(r.m.r1d)}</b></a>`;
  $('#td').innerHTML = `
  <div class="td-hero fade">${T && T.n ? `<h2>Your portfolio is worth <b>${euro(T.value)}</b>, <span class="${tone(T.day)}">${euro(T.day, true)}</span> on the last trading day.</h2>
      <p>${euro(T.pnl, true)} (${pc(T.pnl_pct)}) since you bought · prices as of ${asof} · <a href="#/portfolio">Open portfolio →</a></p>`
    : pf ? `<h2>Add your trades to see your day here.</h2><p><a href="#/portfolio">Add a trade or import from your broker →</a></p>`
    : `<h2>Markets as of ${asof}.</h2><p>Your portfolio shows up here when the app runs on your own computer.</p>`}</div>

  <div class="sh" style="margin-top:34px"><h2>Market pulse</h2><span class="more">last trading day · 1 month · this year</span></div>
  <div class="pulse">${PULSE.filter(([, t]) => by[t]).map(([l, t]) => { const m = by[t].m; return `<a class="pl" href="#/i/${enc(t)}"><span>${l}</span>
      <b class="${tone(m.r1d)}">${pc(m.r1d)}</b><small><i class="${tone(m.r1m)}">${pc(m.r1m)}</i> · <i class="${tone(m.ytd)}">${pc(m.ytd)}</i></small></a>`; }).join('') || '<div class="empty">Prices unavailable right now.</div>'}</div>

  <div class="grid2" style="margin-top:28px">
    <div class="card"><h3>${held.length ? 'Your holdings today' : 'Biggest risers'}</h3>
      ${held.length ? [...held].sort((a, b) => Math.abs(b.r1d) - Math.abs(a.r1d)).slice(0, 6).map(h => `<a class="tdm" href="#/i/${enc(h.ticker)}"><span>${esc(h.name)}<small>${euro(h.value)} · ${pc(h.weight, false)} of portfolio</small></span>
        <b class="${tone(h.r1d)}">${pc(h.r1d)}<small>${euro(h.value * h.r1d / (1 + h.r1d), true)}</small></b></a>`).join('') : movers.slice(0, 6).map(mvRow).join('')}</div>
    <div class="card"><h3>${held.length ? 'Biggest moves in the screener' : 'Biggest fallers'}</h3>
      ${held.length ? [...movers.slice(0, 3), ...movers.slice(-3).reverse()].map(mvRow).join('') : movers.slice(-6).reverse().map(mvRow).join('')}</div>
  </div>

  <div class="grid2" style="margin-top:28px">
    <div class="card"><h3>Alerts ${fired.length ? `<span class="badge">${fired.length}</span>` : ''}</h3>
      ${fired.length ? fired.slice(0, 4).map(a => `<p class="td-line"><a href="#/i/${enc(a.ticker)}"><b>${esc(a.ticker)}</b></a> ${esc(a.text)}</p>`).join('') + (fired.length > 4 ? `<a class="more" href="#/alerts">+${fired.length - 4} more →</a>` : '')
        : S.al ? `<p class="td-line">Nothing fired. <a href="#/alerts">${S.al.alerts.length ? `Watching ${plural(S.al.alerts.length, 'alert')} →` : 'Set up price alerts →'}</a></p>` : '<p class="td-line">Alerts work when the app runs on your own computer.</p>'}
      <h3 style="margin-top:22px">IPOs this week</h3>
      ${soonIpo.length ? soonIpo.slice(0, 4).map(i => `<p class="td-line"><b>${esc(i.name)}</b> <span class="hint">${esc(i.exchange || '')} · ${i.date ? fmtDate(i.date, true) : 'TBA'}</span></p>`).join('')
        : `<p class="td-line">None coming up. <a href="#/ipos">See the IPO calendar →</a></p>`}</div>
    <div class="card side-pred" id="pred">${predCard()}</div>
  </div>`;
  if (!S.data && S.statePromise && !S.stateErr) S.statePromise.then(() => { const el = $('#pred'); if (el) el.innerHTML = predCard(); });
}

function predCard() {
  const d = S.data, tr = d && d.trends, hot = d && d.hot && d.hot[0];
  if (!d) return `<h3>Prediction markets</h3><p class="td-line">${S.stateErr ? 'Prediction signals are unavailable right now.' : 'Loading prediction signals…'}</p><a class="more" href="#/overview">Open Predictions →</a>`;
  return `<h3>Prediction markets</h3>
    ${(d.bets || []).slice(0, 3).map(r => `<a class="td-bet" href="${sigLink({ q: r.market.slice(0, 70), min: 0 })}"><b>${r.prob == null ? '—' : Math.round(r.prob * 100) + '%'}</b><span>${esc(r.market)}${betMove(d, r) ? ' ' + betMove(d, r) : ''}</span></a>`).join('')}
    ${hot ? `<p class="td-line"><b>${esc(hot.sector)}</b> is the hottest segment: ${plural(hot.n, 'live signal')}, ${money(hot.volume)} behind them.</p>` : '<p class="td-line">No prediction signals loaded.</p>'}
    ${tr && tr.movers && tr.movers.length ? `<p class="hint" style="margin:14px 0 4px">Odds that moved since yesterday</p>` + tr.movers.slice(0, 3).map(m => `<p class="td-line"><b class="${m.delta > 0 ? 'up' : 'down'}">${m.delta > 0 ? '+' : '−'}${Math.round(Math.abs(m.delta) * 100)} pts</b> ${esc(m.market)}</p>`).join('') : ''}
    <a class="more" href="#/overview" style="display:inline-block;margin-top:12px">Open Predictions →</a>`;
}

/* ---------- discover ---------- */
const THEMES = [['Post-quantum security', 'adv'], ['Quantum computing', 'adv'], ['European defence', 'adv'], ['Nuclear & uranium', 'adv'],
                ['Electricity grid', 'adv'], ['Space', 'adv'], ['Obesity drugs (GLP-1)', 'adv'], ['Indian manufacturing', 'adv'],
                ['Cybersecurity', 'mid'], ['Water infrastructure', 'mid'], ['Robotics', 'mid'],
                ['Reliable dividend payers', 'basic'], ['Low-cost world ETFs', 'basic'], ['Short-term euro bonds', 'basic']];
const FLAG_NUM = { rpr: r => `${r.m.rpr == null ? '—' : r.m.rpr.toFixed(2)} return/risk`, off_high: r => `${pc(r.m.off_high)} off its high`,
                   r3m: r => `${pc(r.m.r3m)} in 3 months`, corr: r => `moves ${r.corr == null ? '—' : r.corr.toFixed(2)} with the world` };

async function vDiscover(q) {
  view.innerHTML = `<div class="page-h fade"><div class="eyebrow">Discover</div><h1>Ideas worth a closer look</h1>
    <p>Flags from the real data, and any theme you’re curious about, from post-quantum firms to plain dividend funds. Every suggestion is checked against real prices. These are leads to research, not recommendations. Looking for one specific fund or company? <a href="#/search" style="color:var(--accent)">Search all markets →</a></p></div>
  <form id="thf" class="ask-box th-box"><input class="in" id="q" placeholder="Explore a theme, e.g. post-quantum security" autocomplete="off" maxlength="80" aria-label="Theme"><button class="btn primary" type="submit">Explore</button></form>
  <div class="chips">${THEMES.map(([t, lvl]) => `<button class="cf th-chip ${lvl}" type="button" data-th="${esc(t)}">${esc(t)}</button>`).join('')}</div>
  <div id="th"></div>
  <div class="sh"><h2>Fund shortlists</h2><span class="more">ranked on real numbers</span></div>
  <p class="sub">Start here if you simply want a fund. Each list opens ranked, with a plain reason on every row; open any fund to see similar ones.</p>
  <div class="chips">${[['Tech & growth funds, like BIT Capital’s', 'kind=fund&group=Tech%20%26%20growth'], ['Global growth funds', 'kind=fund&group=Global%20growth'],
      ['World index ETFs (the simplest start)', 'kind=etf&group=World'], ['Tech ETFs', 'kind=etf&group=Tech'], ['Theme ETFs', 'kind=etf&group=Themes'],
      ['Healthcare', 'kind=etf&group=Healthcare'], ['Dividend ETFs', 'kind=etf&group=Dividend'], ['India', 'kind=etf&group=India'], ['Bonds (steadier)', 'kind=etf&group=Bonds']]
    .map(([l, qs]) => `<a class="cf" href="#/screener?${qs}">${l}</a>`).join('')}</div>
  <div class="sh"><h2>Flagged from the data</h2><span class="more">recomputed daily from real prices</span></div>
  <div id="fl"><div class="loading sm">${orbHTML(48, 'Scanning for patterns…')}</div></div>`;
  mountOrbs(view);
  const run = t => { location.hash = '#/discover?theme=' + enc(t); };
  $('#thf').onsubmit = e => { e.preventDefault(); const t = $('#q').value.trim(); if (t) run(t); };
  view.onclick = e => { const c = e.target.closest('[data-th]'); if (c) run(c.dataset.th); };
  const theme = q && q.get('theme');
  if (theme) { $('#q').value = theme; exploreTheme(theme); }
  try { S.disc = S.disc || await api('/api/discover'); } catch (e) { if ($('#fl')) $('#fl').innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  if (!$('#fl')) return;
  $('#fl').innerHTML = `<div class="grid2">${S.disc.map(f => `<div class="card"><h3>${esc(f.title)}</h3><p class="sub">${esc(f.plain)}</p>
    ${f.rows.length ? f.rows.map(r => `<a class="tdm" href="#/i/${enc(r.t)}"><span>${esc(r.name)}<small>${esc(r.t)} · ${esc(r.group)} · score ${r.score}</small></span><b>${FLAG_NUM[f.show](r)}</b></a>`).join('')
      : '<div class="empty" style="padding:8px 0">Nothing fits this right now.</div>'}</div>`).join('')}</div>`;
}

async function exploreTheme(t) {
  const box = $('#th');
  box.innerHTML = `<div class="thinking" style="margin-top:18px">${orbHTML(36)}<span>Researching “${esc(t)}” and checking every suggestion against real prices…</span></div>`; mountOrbs(box);
  let x;
  try { x = await api('/api/theme?q=' + enc(t)); }
  catch (e) { if ($('#th')) $('#th').innerHTML = `<div class="note warn" style="margin-top:18px"><span>!</span><p>${esc(e.message)}</p></div>`; return; }
  if (!$('#th') || ($('#q') && $('#q').value.trim() !== t)) return;
  $('#th').innerHTML = `<div class="card th-card fade"><h3>${esc(x.theme)}</h3>
    <p class="th-ex">${esc(x.explainer)}</p>
    <div class="note warn"><span>!</span><p><b>What can go wrong:</b> ${esc(x.risks)}</p></div>
    ${x.simple_route ? `<div class="note info" style="margin-top:8px"><span>i</span><p><b>Simplest route:</b> ${esc(x.simple_route)}</p></div>` : ''}
    ${x.candidates.length ? `<div class="th-tab"><div class="th-r th-h"><span>Listed</span><span class="num">1 yr</span><span class="num">Per yr</span><span class="num">Swing</span><span class="num">Worst fall</span></div>
      ${x.candidates.map(c => { const m = c.m || {}; return `<div class="th-r"><span><b>${esc(c.yahoo_name || c.name)}</b> <small>${esc(c.ticker)} · ${esc(c.type || '')}${c.pure_play ? ' · <i>pure play</i>' : ''}${c.speculative ? ' · <i class="spec">speculative</i>' : ''}</small><br><small class="why">${esc(c.why || '')}</small>
        <a class="th-link" href="#/i/${enc(c.ticker)}">Open its page →</a></span>
        <span class="num ${tone(m.r1y)}">${pc(m.r1y)}</span><span class="num ${tone(m.growth)}">${pc(m.growth)}${m.short ? '*' : ''}</span><span class="num">${pc(m.vol, false)}</span><span class="num">${pc(m.mdd)}</span></div>`; }).join('')}</div>
      <p class="hint">All figures in euros. * = less than 3 years of history. “Speculative” = swings over 45% a year or very little history: small, young or volatile.</p>`
      : '<div class="empty">None of the suggestions checked out against real price data. Try a broader theme.</div>'}
    ${x.private && x.private.length ? `<h3 style="margin-top:22px">Private, can’t buy these directly</h3>${x.private.map(p => `<p class="td-line"><b>${esc(p.name)}</b> ${esc(p.why || '')}</p>`).join('')}` : ''}
    ${x.dropped && x.dropped.length ? `<p class="hint" style="margin-top:16px">Dropped ${plural(x.dropped.length, 'suggestion')} that didn’t check out: ${x.dropped.map(d => `${esc(d.name)} (${esc(d.reason)})`).join('; ')}.</p>` : ''}
    <p class="disc" style="margin-top:14px">Researched by ${esc(x.model)}, prices from Yahoo Finance. A theme being promising doesn’t make every company in it a good investment. Past performance doesn’t predict future returns.</p></div>`;
}

/* ---------- command bar (⌘K) ---------- */
const PAGES = [['today', 'Today'], ['discover', 'Discover'], ['screener', 'Screener'], ['portfolio', 'Portfolio'], ['compare', 'Compare'], ['plan', 'Savings plan'], ['ipos', 'IPOs'],
               ['alerts', 'Alerts'], ['ask', 'Ask'], ['overview', 'Predictions'], ['signals', 'Prediction signals'], ['news', 'Prediction news'], ['brief', 'Daily brief']];
let CMD = { items: [], i: 0 };
const CMD_VERB = /^(compare|vs|plan|sparplan|ask|screen|discover|explore|theme)\b/;
function cmdFind(tok) {  // screener match, else treat a ticker-looking word as a symbol to look up
  const rows = S.screen ? S.screen.rows : [], t = tok.toLowerCase();
  return rows.find(r => r.t.toLowerCase() === t || r.t.toLowerCase().split('.')[0] === t) || rows.find(r => r.name.toLowerCase().startsWith(t))
    || (t.length >= 4 && rows.find(r => matchQ(r, t))) || (/^[a-z0-9^][a-z0-9.&=^-]{0,14}$/.test(t) ? { t: tok.toUpperCase(), name: tok.toUpperCase() } : null);
}
function cmdResults(raw) {
  const q = raw.trim(), ql = q.toLowerCase(), rows = S.screen ? S.screen.rows : [], out = [];
  let m;
  if ((m = ql.match(/^(compare|vs)\s+(.+)/))) {
    const ts = [...new Set(m[2].split(/[\s,]+/).filter(Boolean).map(cmdFind).filter(Boolean))];
    if (ts.length) out.push({ label: `Compare ${ts.map(r => r.name).join(' · ')}`, hint: ts.length < 2 ? 'add one more' : '', go: '#/compare?t=' + enc(ts.map(r => r.t).join(',')) });
  }
  if ((m = ql.match(/^(plan|sparplan)\s+(\S+)(?:\s+€?(\d+(?:[.,]\d+)?))?/))) {
    const r = cmdFind(m[2]);
    if (r) out.push({ label: `Savings plan: ${m[3] ? `€${m[3]} a month into ` : ''}${r.name}`, go: `#/plan?t=${enc(r.t)}${m[3] ? '&m=' + m[3].replace(',', '.') : ''}` });
  }
  if ((m = q.match(/^(discover|explore|theme)\s+(.+)/i))) out.push({ label: `Discover: ${m[2]}`, hint: 'theme explorer', go: '#/discover?theme=' + enc(m[2]) });
  if ((m = q.match(/^ask\s+(.+)/i))) out.push({ label: `Ask: “${m[1]}”`, hint: 'AI analyst', go: '#/ask?q=' + enc(m[1]) });
  if ((m = ql.match(/^screen(?:\s+(etfs?|stocks?|funds?))?\s*(.*)$/))) {
    const kind = { etf: 'etf', etfs: 'etf', stock: 'stock', stocks: 'stock', fund: 'fund', funds: 'fund' }[m[1]] || 'etf';
    const g = m[2] && [...new Set(rows.filter(r => r.kind === kind).map(r => r.group))].find(x => x.toLowerCase().startsWith(m[2].trim()));
    out.push({ label: `Screener: ${kind === 'stock' ? 'stocks' : kind === 'fund' ? 'active funds' : 'ETFs'}${g ? ' · ' + g : ''}`, go: `#/screener?kind=${kind}${g ? '&group=' + enc(g) : ''}` });
  }
  if (ql && !CMD_VERB.test(ql)) {
    rows.filter(r => matchQ(r, ql)).slice(0, 5)
      .forEach(r => out.push({ label: r.name, hint: `${r.t} · ${r.group} · score ${r.score}`, go: '#/i/' + enc(r.t) }));
    if (q.length >= 2) out.push({ label: `Search all markets for “${q}”`, hint: 'any stock, ETF or fund', go: '#/search?q=' + enc(q) });
  }
  PAGES.filter(([, l]) => !ql || l.toLowerCase().includes(ql)).slice(0, ql ? 3 : 12).forEach(([r, l]) => out.push({ label: `Go to ${l}`, go: '#/' + r }));
  if (q && !/^ask\b/i.test(q) && !out.some(o => o.go.startsWith('#/i/'))) out.push({ label: `Ask: “${q}”`, hint: 'AI analyst', go: '#/ask?q=' + enc(q) });
  return out.slice(0, 9);
}
function paintCmd() {
  $('#cmdk-list').innerHTML = CMD.items.map((it, k) => `<div class="cmdk-it${k === CMD.i ? ' on' : ''}" data-k="${k}" role="option"><span>${esc(it.label)}</span>${it.hint ? `<small>${esc(it.hint)}</small>` : ''}</div>`).join('')
    || '<div class="cmdk-empty">Nothing matches.</div>';
}
function openCmd() {
  const box = $('#cmdk'); box.hidden = false;
  const inp = $('#cmdk-in'); inp.value = ''; CMD = { items: cmdResults(''), i: 0 }; paintCmd(); setTimeout(() => inp.focus(), 0);
}
function closeCmd() { const box = $('#cmdk'); if (box) box.hidden = true; }
function runCmd(k) { const it = CMD.items[k]; if (!it) return; closeCmd(); location.hash = it.go; }
$('#cmd-open').onclick = openCmd;
$('#cmdk').addEventListener('click', e => { const it = e.target.closest('.cmdk-it'); if (it) return runCmd(+it.dataset.k); if (e.target.id === 'cmdk') closeCmd(); });
let cmdT;
$('#cmdk-in').addEventListener('input', e => {
  const v = e.target.value; CMD = { items: cmdResults(v), i: 0 }; paintCmd();
  clearTimeout(cmdT);
  if (v.trim().length < 2 || CMD_VERB.test(v.trim().toLowerCase())) return;
  cmdT = setTimeout(async () => {  // then anything else Yahoo lists under that name
    let r; try { r = await api('/api/search?q=' + enc(v.trim())); } catch (err) { return; }
    if ($('#cmdk-in').value !== v || $('#cmdk').hidden) return;
    const more = r.filter(x => !x.in_list).slice(0, 5).map(x => ({ label: x.name, hint: `${x.t} · ${x.where}`, go: '#/i/' + enc(x.t) }));
    if (!more.length) return;
    const at = CMD.items.findIndex(it => it.go.startsWith('#/search'));
    CMD.items.splice(at < 0 ? CMD.items.length : at, 0, ...more); CMD.items = CMD.items.slice(0, 12); paintCmd();
  }, 280);
});
$('#cmdk-in').addEventListener('keydown', e => {
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); CMD.i = (CMD.i + (e.key === 'ArrowDown' ? 1 : -1) + CMD.items.length) % Math.max(1, CMD.items.length); paintCmd(); }
  if (e.key === 'Enter') { e.preventDefault(); runCmd(CMD.i); }
});

/* ---------- app install + offline cache ---------- */
function registerSW() {
  if (!('serviceWorker' in navigator)) return;
  let on = location.protocol === 'https:';
  try { on = on || localStorage.getItem('sw') === 'on'; } catch (e) { /* private mode */ }  // localhost: off by default, so edits aren't served stale
  if (on) navigator.serviceWorker.register('/sw.js').catch(() => { /* the app works fine without it */ });
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent), standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
  if (ios && !standalone) $('#install-hint').textContent = ' · To install on iPhone: Share → Add to Home Screen.';
}
let installEv = null;
addEventListener('beforeinstallprompt', e => { e.preventDefault(); installEv = e; $('#install').hidden = false; });
addEventListener('appinstalled', () => { installEv = null; $('#install').hidden = true; toast('Installed. Find it in your apps.'); });
$('#install').onclick = async () => { if (!installEv) return; installEv.prompt(); await installEv.userChoice; installEv = null; $('#install').hidden = true; };

/* ---------- boot ---------- */
(async function boot() {
  view.innerHTML = `<div class="loading">${orbHTML(72, 'Loading…')}</div>`; mountOrbs(view);
  registerSW();
  api('/api/screen').then(x => { S.screen = x; chrome(); }).catch(() => { /* screener page will report it */ });
  S.statePromise = loadState().then(pollRescan).catch(e => { S.stateErr = e.message; });  // signals are optional and load in the background
  route();            // first paint no longer waits for the prediction database
  refreshAlerts();    // badge + browser notification for anything that fired (local only; silently skipped when hosted)
})();
