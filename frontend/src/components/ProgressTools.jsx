import { useRef, useState } from 'react'
import {
  clearBookmarks,
  clearHistory,
  clearMistakes,
  clearNotes,
  clearStudyProgress,
  exportProgress,
  importProgress,
  parseProgressBackup,
} from '../storage'

const buttonClass =
  'rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-700'

export default function ProgressTools({ onChange }) {
  const [preview, setPreview] = useState(null)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)
  const input = useRef(null)
  const exportBackup = () => {
    const url = URL.createObjectURL(
      new Blob([exportProgress()], { type: 'application/json' })
    )
    const link = document.createElement('a')
    link.href = url
    link.download = `pcep-progress-${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    setMessage('Backup downloaded. Keep it somewhere safe.')
    setError(null)
  }
  const readBackup = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setError(null)
    setMessage(null)
    setPreview(null)
    try {
      if (file.size > 8 * 1024 * 1024)
        throw new Error('Backup must be smaller than 8 MB.')
      setPreview(parseProgressBackup(await file.text()))
    } catch (error) {
      setError(error.message)
    }
  }
  const mergeBackup = () => {
    try {
      importProgress(preview)
      setPreview(null)
      onChange()
      setMessage('Backup merged. Existing progress was preserved.')
      setError(null)
    } catch (error) {
      setError(error.message)
    }
  }
  const reset = (label, clear) => {
    if (
      !window.confirm(
        `Clear saved ${label}? Export a backup first if you want to keep them.`
      )
    )
      return
    if (clear()) {
      onChange()
      setMessage(`Saved ${label} cleared.`)
      setError(null)
    } else setError('Could not save the change. Browser storage is unavailable or full.')
  }
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-800">
      <h3 className="font-semibold">Progress backup &amp; review lists</h3>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
        Your progress stays in this browser. Export a backup to move it to another device.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={exportBackup} className={buttonClass}>
          Export backup
        </button>
        <button
          type="button"
          onClick={() => input.current?.click()}
          className={buttonClass}
        >
          Import backup
        </button>
        <input
          ref={input}
          type="file"
          accept="application/json,.json"
          onChange={readBackup}
          className="hidden"
          aria-label="Progress backup file"
        />
        <button
          type="button"
          onClick={() => reset('mistakes', clearMistakes)}
          className={buttonClass}
        >
          Clear mistakes
        </button>
        <button
          type="button"
          onClick={() => reset('bookmarks', clearBookmarks)}
          className={buttonClass}
        >
          Clear bookmarks
        </button>
        <button
          type="button"
          onClick={() => reset('history', clearHistory)}
          className={buttonClass}
        >
          Clear history
        </button>
        <button
          type="button"
          onClick={() => reset('review schedule', clearStudyProgress)}
          className={buttonClass}
        >
          Clear review schedule
        </button>
        <button
          type="button"
          onClick={() => reset('personal notes', clearNotes)}
          className={buttonClass}
        >
          Clear notes
        </button>
      </div>
      {preview && (
        <div className="mt-3 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm dark:border-sky-800 dark:bg-sky-950/40">
          <p>
            Merge {preview.history.length} attempts, {preview.mistakes.length} mistakes
            and {preview.bookmarks.length} bookmarks, plus {preview.study.length} study
            records and {preview.notes.length} personal notes? Duplicates are merged;
            review history keeps up to 1,000 questions.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button type="button" className={buttonClass} onClick={mergeBackup}>
              Merge backup
            </button>
            <button
              type="button"
              className={buttonClass}
              onClick={() => setPreview(null)}
            >
              Cancel import
            </button>
          </div>
        </div>
      )}
      {message && (
        <p role="status" className="mt-3 text-sm text-emerald-800 dark:text-emerald-300">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-800 dark:text-red-300">
          {error}
        </p>
      )}
    </section>
  )
}
