import { useEffect, useRef, useState } from 'react'
import QuestionCard from './QuestionCard'
import { formatClock } from '../format'

const SECONDS_PER_QUESTION = 80 // mirrors the official PCEP pace (~30 Q / 40 min)

export default function ExamView({ questions, onSubmit, onQuit, submitting }) {
  const total = questions.length
  const [index, setIndex] = useState(0)
  const [answers, setAnswers] = useState({})
  const [flagged, setFlagged] = useState(() => new Set())
  const [timeLeft, setTimeLeft] = useState(total * SECONDS_PER_QUESTION)
  const [confirming, setConfirming] = useState(false)
  const submittedRef = useRef(false)

  const answeredCount = Object.keys(answers).length

  const submit = () => {
    if (submittedRef.current) return
    submittedRef.current = true
    onSubmit(answers)
  }

  // Countdown — auto-submits when it reaches zero.
  useEffect(() => {
    if (timeLeft <= 0) {
      submit()
      return
    }
    const id = setTimeout(() => setTimeLeft((t) => t - 1), 1000)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeLeft])

  const current = questions[index]
  const pick = (choiceId) => setAnswers((a) => ({ ...a, [current.id]: choiceId }))

  const toggleFlag = () =>
    setFlagged((f) => {
      const next = new Set(f)
      next.has(current.id) ? next.delete(current.id) : next.add(current.id)
      return next
    })

  const go = (i) => setIndex(Math.max(0, Math.min(total - 1, i)))
  const lowOnTime = timeLeft <= 60

  const navState = (q, i) => {
    if (i === index) return 'current'
    if (flagged.has(q.id)) return 'flagged'
    if (answers[q.id] != null) return 'answered'
    return 'blank'
  }
  const navClass = {
    current: 'bg-sky-600 text-white border-sky-600',
    answered:
      'bg-green-100 text-green-800 border-green-300 dark:bg-green-900/50 dark:text-green-300 dark:border-green-700',
    flagged:
      'bg-amber-100 text-amber-800 border-amber-400 dark:bg-amber-900/50 dark:text-amber-300 dark:border-amber-600',
    blank:
      'bg-white text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-600',
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-800">
        <div className="flex items-center gap-3 text-sm">
          <span className="rounded-md bg-slate-900 px-2 py-1 font-semibold uppercase tracking-wide text-white dark:bg-sky-600">
            Exam
          </span>
          <span className="text-slate-500 dark:text-slate-400">
            {answeredCount}/{total} answered
          </span>
        </div>
        <div
          role="timer"
          aria-live="off"
          className={`font-mono text-lg font-bold tabular-nums ${
            lowOnTime
              ? 'text-red-600 dark:text-red-400'
              : 'text-slate-700 dark:text-slate-200'
          }`}
        >
          ⏱ {formatClock(timeLeft)}
        </div>
      </div>

      <QuestionCard
        question={current}
        questionNumber={index + 1}
        totalQuestions={total}
        onAnswerSelect={pick}
        selectedChoiceId={answers[current.id] ?? null}
        feedback={null}
        disabled={submitting}
      />

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => go(index - 1)}
            disabled={index === 0}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-slate-700 transition-colors hover:border-slate-500 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300"
          >
            ← Prev
          </button>
          <button
            type="button"
            onClick={() => go(index + 1)}
            disabled={index === total - 1}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-slate-700 transition-colors hover:border-slate-500 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300"
          >
            Next →
          </button>
        </div>
        <button
          type="button"
          onClick={toggleFlag}
          aria-pressed={flagged.has(current.id)}
          className={`rounded-lg border px-4 py-2 transition-colors ${
            flagged.has(current.id)
              ? 'border-amber-400 bg-amber-100 text-amber-800 dark:border-amber-600 dark:bg-amber-900/50 dark:text-amber-300'
              : 'border-slate-300 bg-white text-slate-700 hover:border-slate-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300'
          }`}
        >
          {flagged.has(current.id) ? '⚑ Flagged' : '⚐ Flag'}
        </button>
      </div>

      <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Question navigator
        </div>
        <div className="grid grid-cols-8 gap-2 sm:grid-cols-10">
          {questions.map((q, i) => (
            <button
              key={q.id}
              type="button"
              onClick={() => go(i)}
              aria-label={`Go to question ${i + 1}${answers[q.id] != null ? ', answered' : ''}${flagged.has(q.id) ? ', flagged' : ''}`}
              aria-current={i === index ? 'true' : undefined}
              className={`rounded-md border py-1.5 text-sm font-medium transition-colors ${navClass[navState(q, i)]}`}
            >
              {i + 1}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <button
          type="button"
          onClick={onQuit}
          className="text-sm text-slate-500 underline underline-offset-2 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
        >
          Quit exam
        </button>

        {confirming ? (
          <div className="flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm dark:border-amber-700 dark:bg-amber-950/40">
            <span className="text-amber-800 dark:text-amber-300">
              {total - answeredCount} unanswered. Submit anyway?
            </span>
            <button
              type="button"
              onClick={submit}
              disabled={submitting}
              className="rounded-md bg-slate-900 px-3 py-1 font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-sky-600"
            >
              Yes, submit
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="rounded-md border border-slate-300 px-3 py-1 dark:border-slate-600"
            >
              Keep going
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => (answeredCount < total ? setConfirming(true) : submit())}
            disabled={submitting}
            className="rounded-lg bg-green-600 px-6 py-2.5 font-medium text-white transition-colors hover:bg-green-500 disabled:opacity-50"
          >
            {submitting ? 'Grading…' : 'Submit exam'}
          </button>
        )}
      </div>
    </div>
  )
}
