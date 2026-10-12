import { useEffect, useState } from 'react'
import {
  ANALYTICS_CONSENT_EVENT,
  doNotTrackEnabled,
  loadConsentedAnalytics,
  readAnalyticsConsent,
  writeAnalyticsConsent,
} from '../analytics'

export function AnalyticsPreferences() {
  const dnt = doNotTrackEnabled()
  const [choice, setChoice] = useState(() => readAnalyticsConsent())

  useEffect(() => {
    const update = (event) => setChoice(event.detail?.choice ?? readAnalyticsConsent())
    window.addEventListener(ANALYTICS_CONSENT_EVENT, update)
    return () => window.removeEventListener(ANALYTICS_CONSENT_EVENT, update)
  }, [])

  const choose = (nextChoice) => {
    const previous = choice
    if (!writeAnalyticsConsent(nextChoice)) return
    setChoice(nextChoice)
    if (nextChoice === 'granted') loadConsentedAnalytics()
    if (previous === 'granted' && nextChoice === 'denied') window.location.reload()
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900">
      <p className="font-semibold text-slate-900 dark:text-slate-100">
        Anonymous analytics: {dnt ? 'blocked by Do Not Track' : choice || 'not chosen'}
      </p>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
        Refusing analytics does not limit any quiz feature. Withdrawing consent reloads
        this page so the tracker stops immediately.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={dnt || choice === 'granted'}
          onClick={() => choose('granted')}
          className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          Enable anonymous analytics
        </button>
        <button
          type="button"
          disabled={choice === 'denied'}
          onClick={() => choose('denied')}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
        >
          Do not allow
        </button>
      </div>
    </div>
  )
}

export default function AnalyticsConsent() {
  const [choice, setChoice] = useState(() => readAnalyticsConsent())
  const dnt = doNotTrackEnabled()

  useEffect(() => {
    if (choice === 'granted') loadConsentedAnalytics()
  }, [choice])

  if (choice || dnt) return null

  const choose = (nextChoice) => {
    if (writeAnalyticsConsent(nextChoice)) setChoice(nextChoice)
  }

  return (
    <aside
      aria-label="Analytics choice"
      className="mx-auto mb-6 max-w-3xl rounded-xl border border-slate-300 bg-white p-4 shadow-sm dark:border-slate-600 dark:bg-slate-900"
    >
      <p className="font-semibold text-slate-900 dark:text-slate-100">
        Optional, anonymous analytics
      </p>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
        PCEP Quiz works without analytics. If you allow it, we record anonymous page usage
        for up to 180 days. No quiz answers, notes, cookies or account identifiers are
        collected.{' '}
        <a className="underline" href="/privacy/">
          Privacy details
        </a>
        .
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => choose('granted')}
          className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white"
        >
          Enable anonymous analytics
        </button>
        <button
          type="button"
          onClick={() => choose('denied')}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
        >
          No thanks
        </button>
      </div>
    </aside>
  )
}
