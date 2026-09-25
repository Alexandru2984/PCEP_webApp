import { useEffect, useState } from 'react'

const INSTALL_DISMISSED_KEY = 'pcep.install-dismissed'

export default function RuntimeStatus() {
  const [offline, setOffline] = useState(() => navigator.onLine === false)
  const [updated, setUpdated] = useState(false)
  const [installPrompt, setInstallPrompt] = useState(null)
  const [installDismissed, setInstallDismissed] = useState(() => {
    try {
      return sessionStorage.getItem(INSTALL_DISMISSED_KEY) === '1'
    } catch {
      return false
    }
  })
  const [storageWarning, setStorageWarning] = useState(() => {
    try {
      localStorage.getItem('pcep.progress')
      return false
    } catch {
      return true
    }
  })
  useEffect(() => {
    const update = () => setOffline(navigator.onLine === false)
    const warn = () => setStorageWarning(true)
    const serviceWorker = navigator.serviceWorker
    let controlled = !!serviceWorker?.controller
    const updateAvailable = () => {
      if (controlled) setUpdated(true)
      controlled = true
    }
    const offerInstall = (event) => {
      event.preventDefault()
      setInstallPrompt(event)
    }
    const installed = () => setInstallPrompt(null)
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    window.addEventListener('pcep-storage-warning', warn)
    window.addEventListener('beforeinstallprompt', offerInstall)
    window.addEventListener('appinstalled', installed)
    serviceWorker?.addEventListener('controllerchange', updateAvailable)
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
      window.removeEventListener('pcep-storage-warning', warn)
      window.removeEventListener('beforeinstallprompt', offerInstall)
      window.removeEventListener('appinstalled', installed)
      serviceWorker?.removeEventListener('controllerchange', updateAvailable)
    }
  }, [])

  const installApp = async () => {
    const event = installPrompt
    if (!event) return
    // A browser install prompt can only be used once, regardless of the choice.
    setInstallPrompt(null)
    try {
      await event.prompt()
      await event.userChoice
    } catch {
      // The browser owns this UI; a rejected prompt needs no application error.
    }
  }

  const dismissInstall = () => {
    setInstallDismissed(true)
    try {
      sessionStorage.setItem(INSTALL_DISMISSED_KEY, '1')
    } catch {
      // Dismissal persistence is optional when browser storage is unavailable.
    }
  }

  return (
    <div className="space-y-3" aria-live="polite">
      {updated && (
        <div
          role="status"
          className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-sky-300 bg-sky-50 p-3 text-sm text-sky-900 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-200"
        >
          <span>An app update is ready. Finish your session before reloading.</span>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-lg border border-sky-700 px-3"
          >
            Reload app
          </button>
        </div>
      )}
      {installPrompt && !installDismissed && (
        <section
          aria-labelledby="install-app-title"
          className="mb-4 rounded-lg border border-sky-200 bg-sky-50 p-4 text-sm text-sky-950 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-100"
        >
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <div>
              <h2 id="install-app-title" className="font-semibold">
                Install PCEP Quiz
              </h2>
              <p className="mt-1 text-sky-900 dark:text-sky-200">
                Add it to your device for quick access and the offline app shell. New
                questions and answer feedback still require a connection.
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <button
                type="button"
                onClick={dismissInstall}
                className="min-h-11 rounded-lg px-3 font-medium text-sky-800 hover:bg-sky-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 dark:text-sky-200 dark:hover:bg-sky-900"
              >
                Not now
              </button>
              <button
                type="button"
                onClick={installApp}
                className="min-h-11 rounded-lg bg-sky-700 px-4 font-semibold text-white hover:bg-sky-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2 dark:bg-sky-600 dark:hover:bg-sky-500 dark:focus-visible:ring-offset-slate-950"
              >
                Install app
              </button>
            </div>
          </div>
        </section>
      )}
      {offline && (
        <p
          role="status"
          className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
        >
          You are offline. New quizzes and answer feedback need a connection. Keep your
          exam open and retry grading when you reconnect.
        </p>
      )}
      {storageWarning && (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
        >
          Progress could not be saved on this device. Check browser storage permissions
          and space. Export a backup from Progress before clearing any browser data.
        </p>
      )}
    </div>
  )
}
