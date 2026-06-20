import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// Backend the dev server proxies to. Override with VITE_API_TARGET to point at
// a backend on another port/host without editing this file.
const API_TARGET = process.env.VITE_API_TARGET || 'http://127.0.0.1:8001'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // New builds activate immediately; hashed asset names avoid stale content.
      registerType: 'autoUpdate',
      // External registration script (the strict CSP forbids inline scripts).
      injectRegister: 'script',
      // Keep the existing hand-written public/manifest.webmanifest.
      manifest: false,
      includeManifestIcons: false,
      workbox: {
        // Precache the app shell only. The big Pyodide WASM/stdlib are cached at
        // runtime on first use (below), so installing the SW stays lightweight.
        globPatterns: ['**/*.{js,css,html,svg,webmanifest}'],
        globIgnores: ['**/pyodide/**'],
        // Inline Workbox so the SW makes no extra same-origin importScripts call.
        inlineWorkboxRuntime: true,
        // SPA: serve index.html for navigations, but never for the API/admin.
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api/, /^\/admin/, /^\/static/, /^\/media/],
        runtimeCaching: [
          {
            // Self-hosted Python runtime — large and immutable, cache-first so
            // the in-browser runner works offline after the first run.
            urlPattern: ({ url }) => url.pathname.startsWith('/pyodide/'),
            handler: 'CacheFirst',
            options: {
              cacheName: 'pyodide-runtime',
              expiration: { maxEntries: 40, maxAgeSeconds: 60 * 60 * 24 * 30 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': API_TARGET,
      '/admin': API_TARGET,
      '/static': API_TARGET,
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
