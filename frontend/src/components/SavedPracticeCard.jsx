import { useEffect, useRef, useState } from 'react'

export default function SavedPracticeCard({ practice, onResume, onDiscard }) {
  const completed = practice.history.length
  const [confirmingDiscard, setConfirmingDiscard] = useState(false)
  const discardButton = useRef(null)
  const confirmButton = useRef(null)

  useEffect(() => {
    if (confirmingDiscard) confirmButton.current?.focus()
  }, [confirmingDiscard])

  const keepPractice = () => {
    setConfirmingDiscard(false)
    requestAnimationFrame(() => discardButton.current?.focus())
  }

  return (
    <section
      aria-labelledby="saved-practice-heading"
      className="rounded-xl border border-violet-300 bg-violet-50 p-5 shadow-sm dark:border-violet-800 dark:bg-violet-950/30"
    >
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-violet-700 dark:text-violet-300">
        Practice recovery
      </p>
      <h2 id="saved-practice-heading" className="text-xl font-semibold">
        Resume saved practice
      </h2>
      <p className="mt-2 text-slate-700 dark:text-slate-200">
        {completed}/{practice.questions.length} completed. Continue from question{' '}
        {practice.index + 1}.
      </p>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
        This recovery copy stays in this browser. It stores feedback only for answers you
        already submitted; unanswered answer keys are never saved.
      </p>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <button
          type="button"
          onClick={onResume}
          className="rounded-lg bg-slate-900 px-4 py-2.5 font-medium text-white hover:bg-slate-700 dark:bg-violet-700 dark:hover:bg-violet-800"
        >
          Resume practice
        </button>
        {confirmingDiscard ? (
          <div
            role="group"
            aria-label="Confirm saved practice deletion"
            className="flex flex-wrap items-center gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm dark:border-red-800 dark:bg-red-950/40"
          >
            <span className="text-red-800 dark:text-red-200">Delete this attempt?</span>
            <button
              ref={confirmButton}
              type="button"
              onClick={onDiscard}
              className="rounded-md bg-red-700 px-3 py-1.5 font-medium text-white hover:bg-red-800"
            >
              Delete attempt
            </button>
            <button
              type="button"
              onClick={keepPractice}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-slate-700 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
            >
              Keep practice
            </button>
          </div>
        ) : (
          <button
            ref={discardButton}
            type="button"
            onClick={() => setConfirmingDiscard(true)}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 font-medium text-slate-700 hover:border-slate-500 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
          >
            Discard and start new
          </button>
        )}
      </div>
    </section>
  )
}
