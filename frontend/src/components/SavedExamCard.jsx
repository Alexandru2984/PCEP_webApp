import { useEffect, useRef, useState } from 'react'
import { formatClock } from '../format'
import useDeadlineCountdown from '../useDeadlineCountdown'

export default function SavedExamCard({ exam, onResume, onDiscard }) {
  const answered = Object.keys(exam.answers).length
  const remaining = useDeadlineCountdown(exam.deadline)
  const expired = remaining === 0
  const [confirmingDiscard, setConfirmingDiscard] = useState(false)
  const discardButton = useRef(null)
  const confirmButton = useRef(null)

  useEffect(() => {
    if (confirmingDiscard) confirmButton.current?.focus()
  }, [confirmingDiscard])

  const keepExam = () => {
    setConfirmingDiscard(false)
    requestAnimationFrame(() => discardButton.current?.focus())
  }

  return (
    <section
      aria-labelledby="saved-exam-heading"
      className="rounded-xl border border-sky-300 bg-sky-50 p-5 shadow-sm dark:border-sky-800 dark:bg-sky-950/30"
    >
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-sky-700 dark:text-sky-300">
        Exam recovery
      </p>
      <h2 id="saved-exam-heading" className="text-xl font-semibold">
        Resume saved exam
      </h2>
      <p className="mt-2 text-slate-700 dark:text-slate-200">
        {answered}/{exam.questions.length} answered.{' '}
        {expired ? (
          <span role="status">Time has expired; grade the answers that were saved.</span>
        ) : (
          <span
            role="timer"
            aria-live="off"
            aria-label={`Time remaining: ${formatClock(remaining)}`}
          >
            {formatClock(remaining)} remaining.
          </span>
        )}
      </p>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
        This recovery copy stays in this browser and contains public questions and your
        selections, never the answer key.
      </p>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <button
          type="button"
          onClick={onResume}
          className="rounded-lg bg-slate-900 px-4 py-2.5 font-medium text-white hover:bg-slate-700 dark:bg-sky-700 dark:hover:bg-sky-800"
        >
          {expired ? 'Grade saved answers' : 'Resume exam'}
        </button>
        {confirmingDiscard ? (
          <div
            role="group"
            aria-label="Confirm saved exam deletion"
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
              onClick={keepExam}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-slate-700 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
            >
              Keep exam
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
