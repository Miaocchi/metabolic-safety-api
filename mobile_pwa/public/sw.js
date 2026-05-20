const SHELL_CACHE = "metabolic-mobile-shell-v1";
const RUNTIME_CACHE = "metabolic-mobile-runtime-v1";
const SHELL_URLS = ["/", "/manifest.webmanifest", "/icons/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_URLS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => ![SHELL_CACHE, RUNTIME_CACHE].includes(key)).map((key) => caches.delete(key))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).then((response) => {
      const copy = response.clone();
      caches.open(SHELL_CACHE).then((cache) => cache.put("/", copy));
      return response;
    }).catch(() => caches.match("/") || Response.error()));
    return;
  }

  if (url.origin === self.location.origin && (url.pathname.startsWith("/assets/") || SHELL_URLS.includes(url.pathname))) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {
        const copy = response.clone();
        caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy));
        return response;
      })),
    );
  }
});
