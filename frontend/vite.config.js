import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import { pwaOptions } from './pwa.config'

// Backend the dev server proxies to. Override with VITE_API_TARGET to point at
// a backend on another port/host without editing this file.
const API_TARGET = process.env.VITE_API_TARGET || 'http://127.0.0.1:8001'

export default defineConfig({
  plugins: [react(), tailwindcss(), VitePWA(pwaOptions)],
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
