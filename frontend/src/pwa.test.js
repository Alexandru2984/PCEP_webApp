import { describe, expect, it } from 'vitest'
import { pwaOptions } from '../pwa.config'

describe('public-only service worker policy', () => {
  const { workbox } = pwaOptions
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
  it('caches only successful same-origin Python runtime requests', () => {
    expect(workbox.runtimeCaching).toHaveLength(1)
    const rule = workbox.runtimeCaching[0]
    for (const path of ['/api/grade/', '/api/questions/1/answer/', '/u/api/send'])
      expect(
        rule.urlPattern({ url: new URL(path, 'https://pcep.test'), sameOrigin: true })
      ).toBe(false)
    expect(
      rule.urlPattern({
        url: new URL('https://evil.test/pyodide/a.js'),
        sameOrigin: false,
      })
    ).toBe(false)
    expect(
      rule.urlPattern({
        url: new URL('https://pcep.test/pyodide/pyodide.js'),
        sameOrigin: true,
      })
    ).toBe(true)
    expect(rule.options.cacheableResponse.statuses).toEqual([200])
    expect(rule.options.cacheName).toContain('0.29.4')
  })
})
