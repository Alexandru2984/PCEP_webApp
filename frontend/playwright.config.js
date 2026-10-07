import { defineConfig, devices } from '@playwright/test'

// End-to-end tests drive the real production build (served by `vite preview`)
// with the backend API mocked at the network layer — so they run anywhere,
// including CI, without a Django/Postgres backend. `npm run build` must run
// first; CI does that before `npm run e2e`.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 2,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:4173',
    // Axe must inspect settled colors rather than an intermediate frame of a
    // CSS transition. The app already exposes reduced-motion styles for this
    // user preference, so exercise that accessibility contract in every flow.
    reducedMotion: 'reduce',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'npm run preview -- --port 4173 --strictPort',
      url: 'http://localhost:4173',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: 'npm run preview -- --port 4174 --strictPort',
      url: 'http://localhost:4174/runner.html',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
})
