/* CyberRisk AI voice PWA — minimal cache-first service worker.
 *
 * Caches only the static shell (HTML/JS/CSS/manifest/icons) so the app loads
 * offline once visited.  It deliberately NEVER caches /api responses: chat
 * conversations and risk assessments are private and must always round-trip
 * to the backend.  Bump `CACHE` to invalidate stale assets on deploy.
 */
const CACHE = 'voice-cache-v1';
const PRECACHE = ['/', '/voice.html', '/manifest.webmanifest', '/apple-touch-icon.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Never touch the API — privacy.  Also skip non-GET and cross-origin.
  if (url.pathname.startsWith('/api') || request.method !== 'GET' || url.origin !== self.location.origin) {
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        // Cache successful same-origin GETs; stream opaque errors through.
        if (response && response.ok) {
          const copy = response.clone();
          void caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    }),
  );
});
