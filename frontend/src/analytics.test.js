import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ANALYTICS_CONSENT_EVENT,
  ANALYTICS_CONSENT_KEY,
  ANALYTICS_SCRIPT_ID,
  doNotTrackEnabled,
  loadConsentedAnalytics,
  readAnalyticsConsent,
  writeAnalyticsConsent,
} from './analytics'

const INTEGRITY =
  'sha384-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'

function addConfig(overrides = {}) {
  const template = document.createElement('template')
  template.id = 'pcep-analytics-config'
  Object.assign(template.dataset, {
    consent: 'required',
    src: '/u/script.js',
    integrity: INTEGRITY,
    websiteId: 'b37781f1-2c12-4d98-88f7-48cf10f000fd',
    domains: 'pcep.micutu.com',
    ...overrides,
  })
  document.head.append(template)
  return template
}

describe('consent-gated analytics', () => {
  beforeEach(() => {
    document.getElementById('pcep-analytics-config')?.remove()
    document.getElementById(ANALYTICS_SCRIPT_ID)?.remove()
  })

  it('does not load a tracker before explicit consent', () => {
    addConfig()
    expect(readAnalyticsConsent()).toBeNull()
    expect(loadConsentedAnalytics()).toBe(false)
    expect(document.getElementById(ANALYTICS_SCRIPT_ID)).toBeNull()
  })

  it('loads only the pinned same-origin tracker after consent', () => {
    addConfig()
    localStorage.setItem(ANALYTICS_CONSENT_KEY, 'granted')

    expect(loadConsentedAnalytics()).toBe(true)
    const script = document.getElementById(ANALYTICS_SCRIPT_ID)
    expect(script).toHaveAttribute('src', '/u/script.js')
    expect(script).toHaveAttribute('integrity', INTEGRITY)
    expect(script).toHaveAttribute('crossorigin', 'anonymous')
    expect(script.dataset).toMatchObject({
      doNotTrack: 'true',
      excludeSearch: 'true',
      excludeHash: 'true',
      domains: 'pcep.micutu.com',
      websiteId: 'b37781f1-2c12-4d98-88f7-48cf10f000fd',
    })
  })

  it('fails closed for drifted configuration or Do Not Track', () => {
    addConfig({ src: 'https://analytics.example/script.js' })
    localStorage.setItem(ANALYTICS_CONSENT_KEY, 'granted')
    expect(loadConsentedAnalytics()).toBe(false)
    expect(loadConsentedAnalytics({ navigatorObject: { doNotTrack: '1' } })).toBe(false)
    expect(doNotTrackEnabled({ doNotTrack: 'yes' })).toBe(true)
  })

  it('stores only bounded choices and announces updates', () => {
    const listener = vi.fn()
    window.addEventListener(ANALYTICS_CONSENT_EVENT, listener)

    expect(writeAnalyticsConsent('denied')).toBe(true)
    expect(readAnalyticsConsent()).toBe('denied')
    expect(listener).toHaveBeenCalledOnce()
    expect(listener.mock.calls[0][0].detail).toEqual({ choice: 'denied' })
    expect(() => writeAnalyticsConsent('later')).toThrow('Invalid analytics choice')

    window.removeEventListener(ANALYTICS_CONSENT_EVENT, listener)
  })
})
