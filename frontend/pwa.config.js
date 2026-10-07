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
    globIgnores: [
      '**/pyodide/**',
      '**/py-worker.js',
      '**/runner.html',
      '**/runner-bridge.js',
    ],
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
      /^\/(?:py-worker\.js|runner\.html|runner-bridge\.js)$/,
      /^\/assets(?:\/|$)/,
      /^\/(?:robots\.txt|sitemap\.xml)$/,
    ],
    // The hostile-code origin owns the runtime. The learner-origin service
    // worker must never fetch, cache or serve runner files.
    runtimeCaching: [],
  },
  devOptions: { enabled: false },
}
