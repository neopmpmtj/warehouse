{% load static %}

const CACHE_NAME = "centcompras-shell-v5";

const APP_SHELL = [
    "/",
    "{% static 'products/js/db.js' %}",
    "{% static 'products/js/product_list.js' %}",
    "{% static 'products/js/register_sw.js' %}"
];


self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(APP_SHELL))
    );

    self.skipWaiting();
});


self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames
                    .filter((name) => name !== CACHE_NAME)
                    .map((name) => caches.delete(name))
            );
        })
    );

    self.clients.claim();
});


self.addEventListener("fetch", (event) => {

    // Let API calls behave normally.
    // If offline, they will fail and product_list.js
    // will read the products from IndexedDB.
    if (event.request.url.includes("/api/")) {
        return;
    }

    event.respondWith(
        caches.match(event.request)
            .then((cachedResponse) => {
                return cachedResponse || fetch(event.request);
            })
    );
});