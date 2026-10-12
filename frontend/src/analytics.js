export const ANALYTICS_CONSENT_KEY = 'pcep.analyticsConsent'
export const ANALYTICS_SCRIPT_ID = 'pcep-analytics-script'
export const ANALYTICS_CONSENT_EVENT = 'pcep:analytics-consent'

const VALID_CHOICES = new Set(['granted', 'denied'])
const EXPECTED_SOURCE = '/u/script.js'
const EXPECTED_DOMAIN = 'pcep.micutu.com'
const SHA384_SRI = /^sha384-[A-Za-z0-9+/]{64}$/

export function doNotTrackEnabled(navigatorObject = globalThis.navigator) {
  return [
    navigatorObject?.doNotTrack,
    globalThis.doNotTrack,
    navigatorObject?.msDoNotTrack,
  ].some((value) => value === '1' || value === 'yes')
}

export function readAnalyticsConsent(storage = globalThis.localStorage) {
  try {
    const value = storage?.getItem(ANALYTICS_CONSENT_KEY)
    return VALID_CHOICES.has(value) ? value : null
  } catch {
    return null
  }
}

export function writeAnalyticsConsent(
  choice,
  storage = globalThis.localStorage,
  eventTarget = globalThis.window
) {
  if (!VALID_CHOICES.has(choice)) throw new TypeError('Invalid analytics choice.')
  try {
    storage?.setItem(ANALYTICS_CONSENT_KEY, choice)
  } catch {
    return false
  }
  eventTarget?.dispatchEvent?.(
    new CustomEvent(ANALYTICS_CONSENT_EVENT, { detail: { choice } })
  )
  return true
}

function analyticsConfig(documentObject) {
  const config = documentObject?.getElementById('pcep-analytics-config')
  const values = {
    consent: config?.dataset.consent,
    src: config?.dataset.src,
    integrity: config?.dataset.integrity,
    websiteId: config?.dataset.websiteId,
    domains: config?.dataset.domains,
  }
  if (
    values.consent !== 'required' ||
    values.src !== EXPECTED_SOURCE ||
    !SHA384_SRI.test(values.integrity ?? '') ||
    !/^[0-9a-f-]{36}$/.test(values.websiteId ?? '') ||
    values.domains !== EXPECTED_DOMAIN
  )
    return null
  return values
}

export function loadConsentedAnalytics({
  documentObject = globalThis.document,
  navigatorObject = globalThis.navigator,
  storage = globalThis.localStorage,
} = {}) {
  if (doNotTrackEnabled(navigatorObject) || readAnalyticsConsent(storage) !== 'granted')
    return false
  if (documentObject?.getElementById(ANALYTICS_SCRIPT_ID)) return true

  const config = analyticsConfig(documentObject)
  if (!config) return false
  const script = documentObject.createElement('script')
  script.id = ANALYTICS_SCRIPT_ID
  script.src = config.src
  script.async = true
  script.setAttribute('integrity', config.integrity)
  script.setAttribute('crossorigin', 'anonymous')
  script.dataset.doNotTrack = 'true'
  script.dataset.excludeSearch = 'true'
  script.dataset.excludeHash = 'true'
  script.dataset.websiteId = config.websiteId
  script.dataset.domains = config.domains
  documentObject.head.append(script)
  return true
}
