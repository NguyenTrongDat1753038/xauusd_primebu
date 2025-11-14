/**
 * Service Worker for TradeBot Hub PWA
 * Enables offline support, caching, and background sync
 */

const CACHE_NAME = 'tradebot-hub-v1';
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/app.js',
    '/manifest.json',
    'https://cdn.tailwindcss.com',
    'https://cdn.jsdelivr.net/npm/daisyui@3.9.4/dist/full.css',
    'https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js',
    'https://cdn.jsdelivr.net/npm/chart.js',
    'https://cdn.jsdelivr.net/npm/apexcharts@latest/dist/apexcharts.umd.js',
    'https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css',
    'https://cdn.jsdelivr.net/npm/flatpickr',
    'https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js'
];

// Install Event - Cache static assets
self.addEventListener('install', (event) => {
    console.log('Service Worker: Install event');
    
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('Service Worker: Caching static assets');
            return cache.addAll(STATIC_ASSETS).catch((error) => {
                console.warn('Some assets could not be cached:', error);
                // Don't fail the install if some assets can't be cached
            });
        })
    );
    
    self.skipWaiting();
});

// Activate Event - Clean up old caches
self.addEventListener('activate', (event) => {
    console.log('Service Worker: Activate event');
    
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log(`Service Worker: Deleting old cache ${cacheName}`);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    
    self.clients.claim();
});

// Fetch Event - Network first, fall back to cache
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);
    
    // Skip cross-origin requests and non-GET requests
    if (request.method !== 'GET' || url.origin !== self.location.origin) {
        return;
    }
    
    // Network first strategy for API calls
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(request)
                .then((response) => {
                    if (response.ok) {
                        // Cache successful API responses
                        const cache = caches.open(CACHE_NAME);
                        cache.then((c) => c.put(request, response.clone()));
                    }
                    return response;
                })
                .catch(() => {
                    // Fall back to cached response
                    return caches.match(request).then((response) => {
                        if (response) {
                            console.log(`Service Worker: Serving cached API response for ${request.url}`);
                            return response;
                        }
                        
                        // Return offline response
                        return new Response(
                            JSON.stringify({
                                error: 'Offline',
                                message: 'Unable to fetch data. You are offline.'
                            }),
                            {
                                status: 503,
                                statusText: 'Service Unavailable',
                                headers: { 'Content-Type': 'application/json' }
                            }
                        );
                    });
                })
        );
    } else {
        // Cache first strategy for static assets
        event.respondWith(
            caches.match(request).then((response) => {
                if (response) {
                    return response;
                }
                
                return fetch(request)
                    .then((response) => {
                        if (!response || response.status !== 200 || response.type === 'error') {
                            return response;
                        }
                        
                        // Cache successful responses
                        const cache = caches.open(CACHE_NAME);
                        cache.then((c) => c.put(request, response.clone()));
                        
                        return response;
                    })
                    .catch(() => {
                        // Return offline page for navigation requests
                        if (request.mode === 'navigate') {
                            return caches.match('/index.html');
                        }
                        
                        return new Response('Offline', {
                            status: 503,
                            statusText: 'Service Unavailable'
                        });
                    });
            })
        );
    }
});

// Handle messages from clients
self.addEventListener('message', (event) => {
    console.log('Service Worker: Message received', event.data);
    
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
    
    if (event.data && event.data.type === 'CLEAR_CACHE') {
        caches.delete(CACHE_NAME).then(() => {
            event.ports[0].postMessage({ success: true });
        });
    }
});

// Background Sync for offline actions
self.addEventListener('sync', (event) => {
    console.log('Service Worker: Background sync event', event.tag);
    
    if (event.tag === 'sync-logs') {
        event.waitUntil(
            // Sync pending logs to server
            syncLogs()
        );
    }
    
    if (event.tag === 'sync-reports') {
        event.waitUntil(
            // Sync pending report requests
            syncReports()
        );
    }
});

async function syncLogs() {
    try {
        const db = await openIndexedDB();
        const logs = await getAllLogs(db);
        
        const response = await fetch('/api/logs/sync', {
            method: 'POST',
            body: JSON.stringify({ logs }),
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            await clearSyncedLogs(db);
        }
    } catch (error) {
        console.error('Failed to sync logs:', error);
        throw error;
    }
}

async function syncReports() {
    try {
        const db = await openIndexedDB();
        const reports = await getPendingReports(db);
        
        for (const report of reports) {
            const response = await fetch('/api/reports/sync', {
                method: 'POST',
                body: JSON.stringify(report),
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (response.ok) {
                await markReportSynced(db, report.id);
            }
        }
    } catch (error) {
        console.error('Failed to sync reports:', error);
        throw error;
    }
}

// IndexedDB utilities
function openIndexedDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('TradeBot Hub', 1);
        
        request.onerror = () => reject(request.error);
        request.onsuccess = () => resolve(request.result);
        
        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            
            if (!db.objectStoreNames.contains('logs')) {
                db.createObjectStore('logs', { keyPath: 'id', autoIncrement: true });
            }
            
            if (!db.objectStoreNames.contains('reports')) {
                db.createObjectStore('reports', { keyPath: 'id' });
            }
        };
    });
}

async function getAllLogs(db) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction('logs', 'readonly');
        const store = transaction.objectStore('logs');
        const request = store.getAll();
        
        request.onerror = () => reject(request.error);
        request.onsuccess = () => resolve(request.result);
    });
}

async function clearSyncedLogs(db) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction('logs', 'readwrite');
        const store = transaction.objectStore('logs');
        const request = store.clear();
        
        request.onerror = () => reject(request.error);
        request.onsuccess = () => resolve();
    });
}

async function getPendingReports(db) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction('reports', 'readonly');
        const store = transaction.objectStore('reports');
        const request = store.getAll();
        
        request.onerror = () => reject(request.error);
        request.onsuccess = () => resolve(request.result);
    });
}

async function markReportSynced(db, reportId) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction('reports', 'readwrite');
        const store = transaction.objectStore('reports');
        const request = store.delete(reportId);
        
        request.onerror = () => reject(request.error);
        request.onsuccess = () => resolve();
    });
}

// Push Notifications
self.addEventListener('push', (event) => {
    console.log('Service Worker: Push notification received', event);
    
    const data = event.data ? event.data.json() : {};
    
    const options = {
        body: data.body || 'New notification from TradeBot Hub',
        icon: '/icons/icon-192x192.png',
        badge: '/icons/badge-72x72.png',
        tag: data.tag || 'notification',
        requireInteraction: data.requireInteraction || false,
        data: {
            url: data.url || '/',
            ...data
        }
    };
    
    event.waitUntil(
        self.registration.showNotification(data.title || 'TradeBot Hub', options)
    );
});

// Handle notification clicks
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    
    event.waitUntil(
        clients.matchAll({ type: 'window' }).then((clientList) => {
            // Check if there's already a window/tab open with the target URL
            for (let client of clientList) {
                if (client.url === event.notification.data.url && 'focus' in client) {
                    return client.focus();
                }
            }
            
            // If not, open a new window/tab with the target URL
            if (clients.openWindow) {
                return clients.openWindow(event.notification.data.url);
            }
        })
    );
});

console.log('Service Worker: Loaded and ready');
