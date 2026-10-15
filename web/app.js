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
async function api(path, opts = {}) {
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
function chrome() {
  const d = S.data, f = $('#fresh');
  f.classList.toggle('busy', d.rescanning);
  f.classList.toggle('stale', !d.rescanning && d.asOf && Date.now() - new Date(d.asOf) > 6 * 3600e3);
  $('span', f).textContent = d.rescanning ? 'rescanning…' : d.asOf ? `scanned ${ago(d.asOf)}` : 'no scans yet';
  const top = [...d.signals].filter(r => r.score >= 8).sort((a, b) => b.score - a.score || b.volume - a.volume).slice(0, 16);
  const items = top.map(r => `<a class="ti" href="#/signals?q=${enc(r.market.slice(0, 70))}"><b style="--c:${conv(r.score)}">${r.score}</b>` +
    `<u>${esc(r.tickers[0] || r.sector)}</u>${esc(r.market)}</a>`).join('');
  $('#tape').innerHTML = items ? `<div class="tape-track" style="--dur:${Math.max(50, top.length * 8)}s">${items}${items}</div>` : '';
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
const ROUTES = { overview: vOverview, signals: vSignals, news: vNews, ask: vAsk, brief: vBrief };
function parseHash() {
  const [p, qs = ''] = location.hash.replace(/^#\/?/, '').split('?');
  return { path: ROUTES[p] ? p : 'overview', q: new URLSearchParams(qs) };
}
async function route(keepScroll) {
  const { path, q } = parseHash();
  $$('#nav a').forEach(a => a.classList.toggle('on', a.dataset.r === path));
  if (S.ro) { S.ro.disconnect(); S.ro = null; }
  if (!S.data) return;
  if (path === 'signals' && [...q.keys()].length) {
    S.f = { ...FDEF, sector: (q.get('sector') || '').split(',').filter(Boolean), ticker: (q.get('ticker') || '').split(',').filter(Boolean),
            min: q.has('min') ? +q.get('min') : FDEF.min, q: q.get('q') || '', sort: q.get('sort') || FDEF.sort, dir: q.has('dir') ? +q.get('dir') : FDEF.dir };
  }
  view.innerHTML = ''; view.onclick = null;  // each view installs its own delegated handler
  await ROUTES[path](q);
  mountOrbs(view);
  if (!keepScroll && S.route !== path) scrollTo({ top: 0, behavior: 'instant' });
  S.route = path;
  document.title = (path === 'overview' ? '' : path[0].toUpperCase() + path.slice(1) + ' · ') + 'Polymarket Signal Analyser';
}
addEventListener('hashchange', () => route());

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
    view.innerHTML = `<div class="err-card fade"><h2>No signals yet</h2><p>The scanner hasn't scored any markets. Run <code>python3 -m src.scheduler --once</code> to fetch and score them.</p></div>`;
    return;
  }
  const top = hot[0];
  const hero = top ? `
    <h1 class="display"><span class="hl">${esc(top.sector)}</span> is running hottest.</h1>
    <p class="lede">${plural(top.n, 'live signal')} and <b>${money(top.volume)}</b> of money behind them, peaking at <b>${top.peak}/10</b>.
      ${top.soon != null ? `The nearest one closes in <b>${plural(top.soon, 'day')}</b>.` : ''}</p>
    <div class="cta"><a class="btn primary lg" href="${sigLink({ sector: top.sector })}">Open these signals →</a>
      <a class="btn lg" href="#/ask">Ask the desk</a></div>`
    : `<h1 class="display">Nothing is running hot yet.</h1><p class="lede">No sector has a signal scoring 5 or above right now.</p>`;
  const cells = [...active].sort((a, b) => b.score - a.score || b.volume - a.volume).slice(0, 48);

  view.innerHTML = `
  <section class="hero fade">
    <div><div class="eyebrow">Right now</div>${hero}</div>
    <div class="waffle-wrap">
      <div class="waffle">${cells.map((r, i) => `<a href="${sigLink({ q: r.market.slice(0, 70) })}" style="--c:${conv(r.score)};--i:${i}"
        data-tip="${esc(`${r.score}/10 · ${r.tickers[0] || r.sector} · ${money(r.volume)}\n${r.market}`)}" aria-label="${esc(r.market)}"></a>`).join('')}</div>
      <div class="waffle-cap"><span>Each square is a live signal</span><span>brighter = stronger</span></div>
    </div>
  </section>

  <section class="kpis fade">
    ${[['Markets scanned', k.markets, 'int', ''], ['Active signals', k.active, 'int', ''], ['High conviction', k.high, 'int', ''],
       ['Money behind them', k.volume, 'money', ''], ['Avg conviction', k.avg, 'dec', '<small>/10</small>']]
      .map(([l, v, f, s]) => `<div class="kpi"><div class="v" data-to="${v}" data-fmt="${f}" data-sfx="${esc(s)}">0</div><div class="l">${l}</div></div>`).join('')}
  </section>

  <div class="sh"><h2>Hot topics</h2></div>
  <p class="sub">Segments ranked by heat — how much conviction <em>and</em> money is stacked on them right now. Start at the top. This ranks the present, not the trend.</p>
  <div class="lb">${hot.map((h, i) => `
    <a class="lb-row" href="${sigLink({ sector: h.sector })}">
      <span class="lb-rank">${String(i + 1).padStart(2, '0')}</span>
      <span><span class="lb-name">${esc(h.sector)}</span><span class="lb-lead">${esc(h.lead)}</span></span>
      <span class="lb-bar" style="--c:${conv(5 + h.heat / 20)}"><span class="track"><i class="fill" data-w="${h.heat}"></i></span><b>${h.heat}</b></span>
      <span class="lb-stat"><b>${plural(h.n, 'signal')}</b> · ${money(h.volume)}<br>peak ${h.peak}/10${h.soon != null && h.soon <= 14
        ? ` · <span class="soon">closes in ${h.soon}d</span>` : ` · ${esc(h.tickers.slice(0, 3).join(' ') || 'macro')}`}</span>
      <span class="go">→</span>
    </a>`).join('') || '<div class="empty">Nothing ranked yet.</div>'}</div>

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
  view.innerHTML = `<div class="page-h fade"><div class="eyebrow">World news</div><h1>Headlines, read through your watchlist</h1>
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
function vAsk() {
  const t = Object.keys(S.data.watchlist.tickers), a = t[0] || 'NVDA', b = t[1] || a;
  view.innerHTML = `<div class="page-h fade"><div class="eyebrow">Ask the desk</div><h1>Question the data</h1>
    <p>An agent that plans tool calls over the scanned signals and the latest brief. It never searches the open web, and it shows which lookups it ran.</p></div>
  <div class="chat"><div class="prompts">${[`Which signals threaten ${a}?`, `What's the Fed read-through for ${b}?`, 'What closes in the next two weeks?', 'Where is the most money stacked?']
    .map(p => `<button class="cf" type="button" data-p="${esc(p)}">${esc(p)}</button>`).join('')}</div>
    <div id="log">${chatHTML()}</div>
    <form class="ask-box" id="askf"><input class="in" id="askq" placeholder="Ask about signals, exposure or catalysts…" autocomplete="off" maxlength="600" aria-label="Your question"><button class="btn primary" type="submit">Ask</button></form></div>`;
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
}

/* ---------- brief ---------- */
async function vBrief() {
  view.innerHTML = `<div class="page-h fade"><div class="eyebrow">Daily brief</div><h1>The day, as an analyst note</h1>
    <p>The top signals written up — lead catalyst first, then implications by sector.</p></div><div id="bf"><div class="loading sm">${orbHTML(56, 'Loading briefs…')}</div></div>`;
  mountOrbs(view);
  if (!S.briefs) { try { S.briefs = await api('/api/briefs'); } catch (e) { S.briefs = []; } }
  const el = $('#bf'); if (!el) return;
  if (!S.briefs.length) { el.innerHTML = '<div class="empty">No briefs yet. Run <code>python3 -m src.reports</code> after scoring signals.</div>'; return; }
  const paint = i => { el.innerHTML = `<div class="frow" style="margin:22px 0 8px"><select class="in" id="bsel" aria-label="Brief date">${S.briefs.map((b, j) => `<option value="${j}"${j === i ? ' selected' : ''}>${esc(b.date)}</option>`).join('')}</select></div>
    <article class="prose">${md(S.briefs[i].content)}</article>`; $('#bsel').onchange = e => paint(+e.target.value); };
  paint(0);
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
    <div class="dsec"><button class="btn primary lg" id="save" type="button" style="width:100%"${W.busy ? ' disabled' : ''}>Save watchlist</button></div>
    <div class="dsec"><h3><span>Data</span></h3><div class="d-actions">
      ${scanning ? `<div class="scanning">${orbHTML(30)}<span>Rescanning markets… give it a few minutes.</span></div>` : ''}
      <button class="btn" id="rescan" type="button"${scanning ? ' disabled' : ''}>↻ Rescan markets</button>
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
$('#open-wl').onclick = openDrawer;
$('#theme').onclick = () => {
  const n = theme() === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = n;
  try { localStorage.setItem('theme', n); } catch (e) { /* private mode */ }
  chrome(); route(true);
};
addEventListener('keydown', e => {
  if (e.key === 'Escape') closeDrawer();
  if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
    e.preventDefault();
    if (parseHash().path !== 'signals') location.hash = '#/signals';
    setTimeout(() => $('#q') && $('#q').focus(), 60);
  }
});

/* ---------- boot ---------- */
(async function boot() {
  view.innerHTML = `<div class="loading">${orbHTML(72, 'Loading signals…')}</div>`; mountOrbs(view);
  try { await loadState(); pollRescan(); route(); }
  catch (e) {
    view.innerHTML = `<div class="err-card fade"><h2>Couldn’t load the signals</h2><p>${esc(e.message)} Check that the database keys are set, then try again.</p><button class="btn primary" onclick="location.reload()">Retry</button></div>`;
  }
})();
