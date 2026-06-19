// rackd service worker — app shell for offline use.
// Network-first for our own assets (so edits + live API data show immediately, while
// still working offline from cache). The cross-origin API is never intercepted.
const C = 'rackd-v2';
const ASSETS = ['./', './index.html', './manifest.webmanifest', './icon-192.png', './icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(C).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== C).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return; // API / cross-origin: straight to network

  // network-first: fresh when online, cached fallback when offline
  e.respondWith(
    fetch(e.request).then(resp => {
      const cp = resp.clone();
      caches.open(C).then(c => c.put(e.request, cp));
      return resp;
    }).catch(() => caches.match(e.request).then(r => r || caches.match('./index.html')))
  );
});
