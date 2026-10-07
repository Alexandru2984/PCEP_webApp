import { describe, expect, it } from 'vitest'
import { pwaOptions } from '../pwa.config'

describe('public-only service worker policy', () => {
  const { workbox } = pwaOptions
  it('keeps updates waiting until the learner requests activation', () => {
    expect(pwaOptions.registerType).toBe('prompt')
    expect(workbox.skipWaiting).toBe(false)
    expect(workbox.clientsClaim).toBe(true)
  })
  it('never treats API, admin, study pages or analytics as SPA navigation', () => {
    for (const path of [
      '/api/grade/',
      '/api/questions/1/answer/',
      '/admin/',
      '/practice/module1/',
      '/u/api/send',
      '/robots.txt',
      '/sitemap.xml',
      '/assets/missing.js',
    ])
      expect(
        workbox.navigateFallbackDenylist.some((rule) => rule.test(path)),
        path
      ).toBe(true)
  })
  it('never fetches or caches isolated Python runner files', () => {
    expect(workbox.runtimeCaching).toEqual([])
    for (const path of [
      '/pyodide/pyodide.js',
      '/py-worker.js',
      '/runner.html',
      '/runner-bridge.js',
    ])
      expect(
        workbox.navigateFallbackDenylist.some((rule) => rule.test(path)),
        path
      ).toBe(true)
  })
})
