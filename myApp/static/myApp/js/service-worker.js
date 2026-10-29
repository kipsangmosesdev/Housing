const CACHE_PREFIX = "xbomaswift-pwa-";
const CACHE_NAME = `${CACHE_PREFIX}v1`;
const OFFLINE_URL = "/static/myApp/offline.html";
const CORE_ASSETS = [
  OFFLINE_URL,
  "/static/myApp/manifest.webmanifest",
  "/static/myApp/images/pwa-icon-192.png",
  "/static/myApp/images/pwa-icon-512.png",
  "/static/myApp/images/pwa-icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(CORE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const requestUrl = new URL(request.url);
  if (requestUrl.origin !== self.location.origin) return;

  // Always ask the server for page content; never retain authenticated or dynamic HTML.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async () =>
        (await caches.match(OFFLINE_URL)) || Response.error()
      )
    );
    return;
  }

  // Cache only app static assets. User uploads, API responses, and account data stay network-only.
  if (!requestUrl.pathname.startsWith("/static/")) return;

  event.respondWith(
    fetch(request).then((response) => {
      if (response.ok && response.type === "basic") {
        const responseCopy = response.clone();
        event.waitUntil(
          caches.open(CACHE_NAME)
            .then((cache) => cache.put(request, responseCopy))
            .catch(() => {})
        );
      }
      return response;
    }).catch(async () =>
      (await caches.match(request)) || Response.error()
    )
  );
});
