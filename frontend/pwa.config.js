// Public app shell only. Feedback is deliberately excluded from all caches.
export const pwaOptions = {
  // Keep a new shell waiting until the learner chooses to reload. Activating a
  // different bundle in the middle of an exam can otherwise break lazy imports.
  registerType: 'prompt',
  injectRegister: 'script',
  manifest: false,
  includeManifestIcons: false,
  workbox: {
    skipWaiting: false,
    // Once the waiting worker is explicitly activated, controllerchange lets the
    // page reload exactly once under the new shell.
    clientsClaim: true,
    globPatterns: ['**/*.{js,css,html,svg,webmanifest}'],
    globIgnores: ['**/pyodide/**'],
    inlineWorkboxRuntime: true,
    cleanupOutdatedCaches: true,
    navigateFallback: '/index.html',
    navigateFallbackDenylist: [
      /^\/api(?:\/|$)/,
      /^\/admin(?:\/|$)/,
      /^\/static(?:\/|$)/,
      /^\/media(?:\/|$)/,
      /^\/practice(?:\/|$)/,
      /^\/u(?:\/|$)/,
      /^\/pyodide(?:\/|$)/,
      /^\/assets(?:\/|$)/,
      /^\/(?:robots\.txt|sitemap\.xml)$/,
    ],
    runtimeCaching: [
      {
        urlPattern: ({ url, sameOrigin }) =>
          sameOrigin && url.pathname.startsWith('/pyodide/'),
        handler: 'CacheFirst',
        options: {
          cacheName: 'pyodide-runtime-0.29.4',
          expiration: { maxEntries: 8, maxAgeSeconds: 60 * 60 * 24 * 30 },
          cacheableResponse: { statuses: [200] },
        },
      },
    ],
  },
  devOptions: { enabled: false },
}
