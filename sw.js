// 舊版把 App 放在這一層；現在搬到 app/，把這裡留下的快取和 Service Worker 清掉
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('eat-v')).map(k => caches.delete(k)))).then(() => self.registration.unregister())));
