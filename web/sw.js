/* Service worker: instant repeat loads and a last-known-data fallback when the connection drops.
   Stores ONLY the app files and public market data. Everything else (portfolio, alerts, IPO watch list, trades,
   Ask, AI explainers, any non-GET) goes straight to the network and is never kept. */
const V = 'fs-v1';
const SHELL = ['/', '/app.css', '/app.js', '/manifest.webmanifest', '/icons/icon-192.png'];
const PUBLIC_API = /^\/api\/(screen|state|instrument\/|discover|news|briefs|compare|plan)/;

self.addEventListener('install', e => e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener('activate', e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim())));

const stash = (req, res) => { if (res && res.status === 200) { const copy = res.clone(); caches.open(V).then(c => c.put(req, copy)); } return res; };

function staleWhileRevalidate(req) {
  return caches.open(V).then(c => c.match(req, { ignoreSearch: true }).then(hit => {
    const net = fetch(req).then(res => stash(req, res)).catch(() => hit);
    return hit || net;  // cached copy now, refreshed in the background for next time
  }));
}

function networkFirst(req) {
  const fromCache = () => caches.match(req).then(hit => hit || new Response(JSON.stringify({ detail: 'You\'re offline and this hasn\'t been opened before.' }),
    { status: 503, headers: { 'Content-Type': 'application/json' } }));
  return new Promise(resolve => {
    const t = setTimeout(() => fromCache().then(r => r.status === 200 && resolve(r)), 6000);  // slow phone connection: show what we have
    fetch(req).then(res => { clearTimeout(t); resolve(stash(req, res)); }).catch(() => { clearTimeout(t); fromCache().then(resolve); });
  });
}

self.addEventListener('fetch', e => {
  const req = e.request, u = new URL(req.url);
  if (req.method !== 'GET') return;
  if (u.origin === location.origin) {
    if (u.pathname.startsWith('/api/')) { if (PUBLIC_API.test(u.pathname)) e.respondWith(networkFirst(req)); return; }
    return e.respondWith(staleWhileRevalidate(req));
  }
  if (/^fonts\.(googleapis|gstatic)\.com$/.test(u.hostname)) e.respondWith(staleWhileRevalidate(req));
});
