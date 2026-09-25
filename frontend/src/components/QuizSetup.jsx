import { useState } from 'react'
import { getScopeTotal } from '../questionStats'
import QuestionBankStats from './QuestionBankStats'
import QuestionSearch from './QuestionSearch'

const MODULES = [
  { value: '', label: 'All modules' },
  { value: 'module1', label: 'Module 1 — Fundamentals' },
  { value: 'module2', label: 'Module 2 — Control Flow' },
  { value: 'module3', label: 'Module 3 — Data Collections' },
  { value: 'module4', label: 'Module 4 — Functions & Exceptions' },
]

const DIFFICULTIES = [
  { value: '', label: 'Any' },
  { value: 'easy', label: 'Easy' },
  { value: 'medium', label: 'Medium' },
  { value: 'hard', label: 'Hard' },
]

const COUNTS = [10, 20, 30, 50]

const selectClass =
  'rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:focus:ring-slate-500'

const MODES = [
  {
    value: 'practice',
    title: 'Practice',
    subtitle: 'Instant feedback & explanation after every answer',
  },
  {
    value: 'exam',
    title: 'Exam simulation',
    subtitle: 'Timed, no hints, graded at the end like the real PCEP',
  },
  {
    value: 'flashcards',
    title: 'Flashcards',
    subtitle: 'Flip-card drill: reveal the answer, mark what you know',
  },
]

export default function QuizSetup({
  onStart,
  onPracticeMistakes,
  mistakesCount = 0,
  bookmarksCount = 0,
  onPracticeBookmarks,
  dueReviewCount = 0,
  onPracticeDueReviews,
  adaptivePlan,
  onAdaptivePractice,
  onDailyChallenge,
  dailyCompletion,
  onSearchDrill,
  initial,
  stats,
  statsLoading,
  statsError,
}) {
  const [mode, setMode] = useState(initial?.mode ?? 'practice')
  const [module, setModule] = useState(initial?.module ?? '')
  const [difficulty, setDifficulty] = useState(initial?.difficulty ?? '')
  const [count, setCount] = useState(initial?.count ?? 30)
  const canUseStats = stats && !statsLoading && !statsError
  const scopeTotal = canUseStats ? getScopeTotal(stats, module, difficulty) : null
  const effectiveCount =
    scopeTotal && scopeTotal > 0 ? Math.min(count, scopeTotal) : count
  const isEmptyScope = canUseStats && scopeTotal === 0
  const isCappedByScope = canUseStats && scopeTotal > 0 && effectiveCount < count
  const startLabel =
    mode === 'exam'
      ? 'Start exam'
      : mode === 'flashcards'
        ? 'Start flashcards'
        : 'Start practice'

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <h2 className="mb-1 text-xl font-semibold text-slate-900 dark:text-slate-100">
        Start a new quiz
      </h2>
      <p className="mb-5 text-sm text-slate-600 dark:text-slate-400">
        Pick a mode and scope. Leave filters on defaults for a full mixed-bag PCEP run.
      </p>

      {onDailyChallenge && (
        <button
          type="button"
          onClick={onDailyChallenge}
          className="mb-4 flex min-h-14 w-full items-center justify-between gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-left transition-colors hover:border-amber-500 hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/30 dark:hover:border-amber-600 dark:hover:bg-amber-950/50"
        >
          <span>
            <span className="block font-semibold text-amber-950 dark:text-amber-100">
              Daily challenge
            </span>
            <span className="mt-1 block text-xs text-amber-800 dark:text-amber-300">
              Five balanced questions · the same set all day
            </span>
          </span>
          <span className="shrink-0 rounded-full bg-amber-200 px-2.5 py-1 text-sm font-bold text-amber-950 dark:bg-amber-800 dark:text-amber-100">
            {dailyCompletion ? `${dailyCompletion.pct}% · Again` : 'Start'}
          </span>
        </button>
      )}

      {adaptivePlan?.count > 0 && onAdaptivePractice && (
        <button
          type="button"
          onClick={onAdaptivePractice}
          className="mb-5 flex w-full items-center justify-between gap-3 rounded-lg border border-violet-300 bg-violet-50 px-4 py-3 text-left transition-colors hover:bg-violet-100 dark:border-violet-800 dark:bg-violet-950/40 dark:hover:bg-violet-950/60"
        >
          <span>
            <span className="block text-xs font-semibold uppercase tracking-wide text-violet-700 dark:text-violet-300">
              Recommended next
            </span>
            <span className="mt-0.5 block font-semibold text-violet-950 dark:text-violet-100">
              Adaptive practice
            </span>
            <span className="mt-1 block text-xs text-violet-800 dark:text-violet-300/90">
              {adaptivePlan.signals.due} due · {adaptivePlan.signals.mistakes} mistakes ·{' '}
              {adaptivePlan.signals.weak} below-target mastery
              {adaptivePlan.signals.lowConfidence > 0
                ? ` · ${adaptivePlan.signals.lowConfidence} low confidence`
                : ''}
            </span>
          </span>
          <span className="shrink-0 rounded-full bg-violet-200 px-2.5 py-1 text-sm font-bold text-violet-950 dark:bg-violet-800 dark:text-violet-100">
            {adaptivePlan.count}
          </span>
        </button>
      )}

      {dueReviewCount > 0 && onPracticeDueReviews && (
        <button
          type="button"
          onClick={onPracticeDueReviews}
          className="mb-5 flex w-full items-center justify-between gap-3 rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-3 text-left transition-colors hover:bg-emerald-100 dark:border-emerald-800 dark:bg-emerald-950/40 dark:hover:bg-emerald-950/60"
        >
          <span>
            <span className="block font-semibold text-emerald-900 dark:text-emerald-200">
              Review what is due
            </span>
            <span className="mt-0.5 block text-xs text-emerald-800 dark:text-emerald-300/90">
              A focused drill of up to 20 questions from your review schedule.
            </span>
          </span>
          <span className="shrink-0 rounded-full bg-emerald-200 px-2.5 py-1 text-sm font-bold text-emerald-900 dark:bg-emerald-800 dark:text-emerald-100">
            {dueReviewCount}
          </span>
        </button>
      )}

      {mistakesCount > 0 && onPracticeMistakes && (
        <button
          type="button"
          onClick={onPracticeMistakes}
          className="mb-5 flex w-full items-center justify-between gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-left transition-colors hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/40 dark:hover:bg-amber-950/60"
        >
          <span>
            <span className="block font-semibold text-amber-900 dark:text-amber-200">
              🔁 Practice your mistakes
            </span>
            <span className="mt-0.5 block text-xs text-amber-800 dark:text-amber-300/90">
              Re-drill the {mistakesCount} question{mistakesCount === 1 ? '' : 's'} you
              missed — answer one correctly and it drops off the list.
            </span>
          </span>
          <span className="shrink-0 rounded-full bg-amber-200 px-2.5 py-1 text-sm font-bold text-amber-900 dark:bg-amber-800 dark:text-amber-100">
            {mistakesCount}
          </span>
        </button>
      )}

      {bookmarksCount > 0 && onPracticeBookmarks && (
        <button
          type="button"
          onClick={onPracticeBookmarks}
          className="mb-5 w-full rounded-lg border border-sky-300 bg-sky-50 px-4 py-3 text-left font-medium text-sky-900 hover:bg-sky-100 dark:border-sky-700 dark:bg-sky-950/40 dark:text-sky-200"
        >
          ★ Practice bookmarks ({bookmarksCount})
        </button>
      )}

      <div className="mb-5 grid grid-cols-1 gap-2 sm:grid-cols-3">
        {MODES.map((m) => {
          const active = mode === m.value
          return (
            <button
              key={m.value}
              type="button"
              onClick={() => setMode(m.value)}
              aria-pressed={active}
              className={`rounded-lg border p-3 text-left transition-colors ${
                active
                  ? 'border-sky-500 bg-sky-50 dark:border-sky-500 dark:bg-sky-950/40'
                  : 'border-slate-300 bg-white hover:border-slate-400 dark:border-slate-600 dark:bg-slate-900'
              }`}
            >
              <div className="font-semibold text-slate-900 dark:text-slate-100">
                {m.title}
              </div>
              <div className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">
                {m.subtitle}
              </div>
            </button>
          )
        })}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col text-sm">
          <span className="mb-1 font-medium text-slate-700 dark:text-slate-300">
            Module
          </span>
          <select
            value={module}
            onChange={(e) => setModule(e.target.value)}
            className={selectClass}
          >
            {MODULES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col text-sm">
          <span className="mb-1 font-medium text-slate-700 dark:text-slate-300">
            Difficulty
          </span>
          <select
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
            className={selectClass}
          >
            {DIFFICULTIES.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </label>

        <div className="flex flex-col text-sm sm:col-span-2">
          <span className="mb-1 font-medium text-slate-700 dark:text-slate-300">
            Questions: {count}
          </span>
          <div className="flex gap-2">
            {COUNTS.map((n) => (
              <button
                type="button"
                key={n}
                onClick={() => setCount(n)}
                aria-pressed={count === n}
                className={`rounded-lg border px-4 py-2 transition-colors ${
                  count === n
                    ? 'border-slate-900 bg-slate-900 text-white dark:border-sky-600 dark:bg-sky-700'
                    : 'border-slate-300 bg-white text-slate-700 hover:border-slate-500 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300'
                }`}
              >
                {n}
              </button>
            ))}
          </div>
          <p className="mt-2 min-h-5 text-xs text-slate-500 dark:text-slate-400">
            {isCappedByScope
              ? `This scope has ${scopeTotal} questions; the quiz will use all available.`
              : canUseStats
                ? `${scopeTotal} questions match the selected scope.`
                : 'The requested count is clamped by what the question bank can serve.'}
          </p>
        </div>
      </div>

      <button
        type="button"
        disabled={isEmptyScope}
        onClick={() => onStart({ mode, module, difficulty, count: effectiveCount })}
        className="mt-6 w-full rounded-lg bg-slate-900 px-6 py-3 font-medium text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 dark:bg-sky-700 dark:hover:bg-sky-800 dark:disabled:bg-slate-700 dark:disabled:text-slate-400"
      >
        {isEmptyScope
          ? 'No questions in this scope'
          : isCappedByScope
            ? `${startLabel} with ${effectiveCount}`
            : startLabel}
      </button>

      <QuestionBankStats
        stats={stats}
        loading={statsLoading}
        error={statsError}
        selectedModule={module}
        selectedDifficulty={difficulty}
      />

      {onSearchDrill && (
        <QuestionSearch
          key={`${module}:${difficulty}`}
          module={module}
          difficulty={difficulty}
          onStart={onSearchDrill}
        />
      )}
    </div>
  )
}
