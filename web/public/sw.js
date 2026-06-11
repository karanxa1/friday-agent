// Kill-switch service worker.
// otpgod.com previously served a different app (Vercel) that may have
// registered a service worker. That stale worker can intercept navigations and
// serve cached/404 responses. This replacement unregisters itself, clears all
// caches, and reloads open tabs so the live site is served directly.
self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      try {
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
      } catch (e) {}
      await self.registration.unregister();
      const clients = await self.clients.matchAll({ type: "window" });
      clients.forEach((client) => client.navigate(client.url));
    })()
  );
});
