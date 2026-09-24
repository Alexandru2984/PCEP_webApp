import { useCallback, useEffect, useRef, useState } from 'react'
import QuestionCard from './QuestionCard'
import { formatClock } from '../format'
import { ignoreShortcut } from '../shortcuts'
import { MAX_RESPONSE_MS, validConfidence } from '../confidence'

const SECONDS_PER_QUESTION = 80 // application simulation pace

export default function ExamView({
  questions,
  onSubmit,
  onQuit,
  onProgress,
  initialProgress,
  submitting,
  error,
}) {
  const total = questions.length
  const [index, setIndex] = useState(() => initialProgress?.index ?? 0)
  const [answers, setAnswers] = useState(() => ({ ...(initialProgress?.answers ?? {}) }))
  const [confidences, setConfidences] = useState(() => ({
    ...(initialProgress?.confidences ?? {}),
  }))
  const [flagged, setFlagged] = useState(() => new Set(initialProgress?.flagged ?? []))
  const [deadline] = useState(
    () => initialProgress?.deadline ?? Date.now() + total * SECONDS_PER_QUESTION * 1000
  )
  const [timeLeft, setTimeLeft] = useState(() =>
    Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
  )
  const [confirming, setConfirming] = useState(false)
  const [locked, setLocked] = useState(false)
  const submittedRef = useRef(false)
  const submission = useRef(null)
  const autoAttempted = useRef(false)
  const expiredAnswers = useRef(null)
  const responseMs = useRef({ ...(initialProgress?.responseMs ?? {}) })
  const answeredOnce = useRef(new Set(Object.keys(answers).map(Number)))
  const [initialEnteredAt] = useState(Date.now)
  const enteredAt = useRef(initialEnteredAt)
  const [navigatorOpen, setNavigatorOpen] = useState(
    () => window.matchMedia?.('(min-width: 640px)').matches ?? false
  )
  const confirmButton = useRef(null)
  const submitButton = useRef(null)
  const current = questions[index]
  const recordCurrentTime = useCallback(() => {
    const now = Date.now()
    if (!answeredOnce.current.has(current.id)) {
      const elapsed = Math.max(0, now - enteredAt.current)
      responseMs.current[current.id] = Math.min(
        MAX_RESPONSE_MS,
        (responseMs.current[current.id] ?? 0) + elapsed
      )
    }
    enteredAt.current = now
    return { ...responseMs.current }
  }, [current.id])
  useEffect(() => {
    if (confirming) confirmButton.current?.focus()
  }, [confirming])
  useEffect(() => {
    onProgress?.({
      index,
      answers,
      flagged: [...flagged],
      deadline,
      confidences,
      responseMs: { ...responseMs.current },
    })
  }, [answers, confidences, deadline, flagged, index, onProgress])

  const answeredCount = Object.keys(answers).length

  const submit = useCallback(async () => {
    if (submittedRef.current) return
    submittedRef.current = true
    setLocked(true)
    if (Date.now() >= deadline && !expiredAnswers.current)
      expiredAnswers.current = { ...answers }
    if (!submission.current) {
      submission.current = {
        answers: { ...(expiredAnswers.current ?? answers) },
        metadata: {
          confidences: { ...confidences },
          responseMs: recordCurrentTime(),
        },
      }
    }
    try {
      const success = await onSubmit(
        submission.current.answers,
        submission.current.metadata
      )
      if (success === false) submittedRef.current = false
    } catch {
      submittedRef.current = false
    }
  }, [answers, confidences, deadline, onSubmit, recordCurrentTime])

  // Use wall-clock time so background-tab timer suspension does not extend an exam.
  useEffect(() => {
    const tick = () => setTimeLeft(Math.max(0, Math.ceil((deadline - Date.now()) / 1000)))
    const id = setInterval(tick, 1000)
    window.addEventListener('focus', tick)
    document.addEventListener('visibilitychange', tick)
    return () => {
      clearInterval(id)
      window.removeEventListener('focus', tick)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [deadline])
  useEffect(() => {
    if (timeLeft <= 0 && !autoAttempted.current) {
      autoAttempted.current = true
      submit()
    }
  }, [timeLeft, submit])

  const pick = (choiceId) => {
    if (
      submitting ||
      submittedRef.current ||
      submission.current ||
      Date.now() >= deadline
    )
      return
    if (!answeredOnce.current.has(current.id)) {
      recordCurrentTime()
      answeredOnce.current.add(current.id)
    }
    setAnswers((a) => ({ ...a, [current.id]: choiceId }))
  }
  const setConfidence = (confidence) => {
    if (
      submitting ||
      submission.current ||
      Date.now() >= deadline ||
      (confidence !== null && !validConfidence(confidence))
    )
      return
    setConfidences((currentValues) => {
      const next = { ...currentValues }
      if (confidence === null) delete next[current.id]
      else next[current.id] = confidence
      return next
    })
  }

  const toggleFlag = () =>
    setFlagged((f) => {
      const next = new Set(f)
      next.has(current.id) ? next.delete(current.id) : next.add(current.id)
      return next
    })

  const go = (i) => {
    recordCurrentTime()
    setIndex(Math.max(0, Math.min(total - 1, i)))
  }
  const jumpTo = (predicate) => {
    const after = questions.findIndex((q, i) => i > index && predicate(q))
    const next = after >= 0 ? after : questions.findIndex(predicate)
    if (next >= 0) go(next)
  }
  const lowOnTime = timeLeft <= 60

  // Keyboard: 1–4 / A–D answer, ← → navigate, F flag.
  useEffect(() => {
    const onKey = (e) => {
      if (
        ignoreShortcut(e) ||
        submitting ||
        submission.current ||
        confirming ||
        timeLeft <= 0
      )
        return
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        return go(index - 1)
      }
      if (e.key === 'ArrowRight') {
        e.preventDefault()
        return go(index + 1)
      }
      if (e.key.toLowerCase() === 'f') {
        e.preventDefault()
        return toggleFlag()
      }
      const n = Number.parseInt(e.key, 10)
      const idx = Number.isNaN(n) ? 'abcd'.indexOf(e.key.toLowerCase()) : n - 1
      if (idx >= 0 && idx < current.choices.length) {
        e.preventDefault()
        pick(current.choices[idx].id)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, questions, submitting, confirming, timeLeft])

  const navState = (q, i) => {
    if (i === index) return 'current'
    if (flagged.has(q.id)) return 'flagged'
    if (answers[q.id] != null) return 'answered'
    return 'blank'
  }
  const navClass = {
    current: 'bg-sky-700 text-white border-sky-600',
    answered:
      'bg-green-100 text-green-800 border-green-300 dark:bg-green-900/50 dark:text-green-300 dark:border-green-700',
    flagged:
      'bg-amber-100 text-amber-800 border-amber-400 dark:bg-amber-900/50 dark:text-amber-300 dark:border-amber-600',
    blank:
      'bg-white text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-600',
  }

  return (
    <div>
      {error && (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200"
        >
          Your exam answers are kept. {error}
        </p>
      )}
      {timeLeft <= 0 && (
        <p
          role="status"
          className="mb-3 text-sm font-medium text-amber-800 dark:text-amber-200"
        >
          Time is up. Your answers are locked.{' '}
          {error ? 'Retry grading to finish.' : 'Submitting your exam…'}
        </p>
      )}
      {lowOnTime && timeLeft > 0 && (
        <p
          role="status"
          className="mb-3 text-sm font-medium text-amber-800 dark:text-amber-200"
        >
          Less than one minute remains.
        </p>
      )}
      <div className="sticky top-2 z-10 mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm dark:border-slate-700 dark:bg-slate-800">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="rounded-md bg-slate-900 px-2 py-1 font-semibold uppercase tracking-wide text-white dark:bg-sky-700">
            Exam
          </span>
          <span className="text-slate-500 dark:text-slate-400">
            {answeredCount}/{total} answered
          </span>
        </div>
        <div
          role="timer"
          aria-live="off"
          aria-label={`Time remaining: ${formatClock(timeLeft)}`}
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
        confidence={confidences[current.id] ?? null}
        onConfidenceChange={setConfidence}
        feedback={null}
        disabled={submitting || locked || timeLeft <= 0}
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
        <button
          type="button"
          onClick={() => setNavigatorOpen((open) => !open)}
          aria-expanded={navigatorOpen}
          aria-controls="exam-navigator"
          className="flex w-full flex-wrap items-center justify-between gap-2 text-left font-medium"
        >
          <span>Question navigator {navigatorOpen ? '▴' : '▾'}</span>
          <span className="text-sm text-slate-600 dark:text-slate-300">
            {total - answeredCount} unanswered · {flagged.size} flagged
          </span>
        </button>
        <div id="exam-navigator" hidden={!navigatorOpen}>
          <div className="my-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={answeredCount === total}
              onClick={() => jumpTo((q) => answers[q.id] == null)}
              className="rounded-lg border border-slate-300 px-3 text-sm disabled:opacity-50 dark:border-slate-600"
            >
              Next unanswered
            </button>
            <button
              type="button"
              disabled={flagged.size === 0}
              onClick={() => jumpTo((q) => flagged.has(q.id))}
              className="rounded-lg border border-slate-300 px-3 text-sm disabled:opacity-50 dark:border-slate-600"
            >
              Next flagged
            </button>
          </div>
          <div className="grid grid-cols-5 gap-2 sm:grid-cols-10">
            {questions.map((q, i) => (
              <button
                key={q.id}
                type="button"
                onClick={() => go(i)}
                aria-label={`Go to question ${i + 1}${answers[q.id] != null ? ', answered' : ''}${flagged.has(q.id) ? ', flagged' : ''}`}
                aria-current={i === index ? 'true' : undefined}
                className={`min-h-11 rounded-md border py-2 text-sm font-medium transition-colors ${navClass[navState(q, i)]}`}
              >
                {i + 1}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <button
          type="button"
          onClick={() => {
            if (
              window.confirm(
                'Quit this exam? Your unsubmitted answers will not be saved.'
              )
            )
              onQuit()
          }}
          className="text-sm text-slate-500 underline underline-offset-2 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
        >
          Quit exam
        </button>

        {confirming ? (
          <div
            role="group"
            aria-label="Confirm exam submission"
            className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm dark:border-amber-700 dark:bg-amber-950/40"
          >
            <span className="text-amber-800 dark:text-amber-300">
              {total - answeredCount} unanswered. Submit anyway?
            </span>
            <button
              ref={confirmButton}
              type="button"
              onClick={submit}
              disabled={submitting}
              className="rounded-md bg-slate-900 px-3 py-1 font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-sky-700"
            >
              Yes, submit
            </button>
            <button
              type="button"
              onClick={() => {
                setConfirming(false)
                requestAnimationFrame(() => submitButton.current?.focus())
              }}
              className="rounded-md border border-slate-300 px-3 py-1 dark:border-slate-600"
            >
              Keep going
            </button>
          </div>
        ) : (
          <button
            ref={submitButton}
            type="button"
            onClick={() => (answeredCount < total ? setConfirming(true) : submit())}
            disabled={submitting}
            className="rounded-lg bg-green-700 px-6 py-2.5 font-medium text-white transition-colors hover:bg-green-800 disabled:opacity-50"
          >
            {submitting ? 'Grading…' : error ? 'Retry grading' : 'Submit exam'}
          </button>
        )}
      </div>
    </div>
  )
}
