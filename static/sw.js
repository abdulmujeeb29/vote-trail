// Service worker: offline shell. Uploads are queued in IndexedDB by the page and retried
// on reconnect; this worker keeps the app shell available with no signal.
const CACHE = "votetrail-shell-v5";
const SHELL = ["/capture/", "/demo/", "/static/css/app.css", "/static/css/landing.css", "/static/js/ui.js", "/static/js/scene3d.js", "/static/js/landing.js", "/static/js/capture.js",
  "/static/js/offline-queue.js", "/static/js/demo.js", "/static/js/nearby.js", "/static/demo/wall-ec8a.jpg", "/static/demo/irev-ec8a.jpg",
  "/static/demo/relocation-pcm.mp3"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  // Only handle our own pages and files; fonts and other sites go straight to the network.
  if (req.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  e.respondWith(fetch(req, { cache: "no-cache" }).then((res) => {
    if (res.ok && new URL(req.url).origin === self.location.origin) {
      const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy));
    }
    return res;
  }).catch(() => caches.match(req)));
});
