import { useEffect, useState } from 'react'

export default function RuntimeStatus() {
  const [offline, setOffline] = useState(() => navigator.onLine === false)
  const [updated, setUpdated] = useState(false)
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
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    window.addEventListener('pcep-storage-warning', warn)
    serviceWorker?.addEventListener('controllerchange', updateAvailable)
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
      window.removeEventListener('pcep-storage-warning', warn)
      serviceWorker?.removeEventListener('controllerchange', updateAvailable)
    }
  }, [])
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
