// Accabox: only used to show bet alerts. No caching, so the app always loads fresh.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(ws => {
    for (const w of ws) if ("focus" in w) { w.navigate && w.navigate("./#mybets"); return w.focus(); }
    return self.clients.openWindow("./#mybets");
  }));
});
