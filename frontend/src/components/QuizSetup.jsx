import { useState } from 'react'
import { getScopeTotal } from '../questionStats'
import QuestionBankStats from './QuestionBankStats'

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
]

export default function QuizSetup({ onStart, initial, stats, statsLoading, statsError }) {
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
  const startLabel = mode === 'exam' ? 'Start exam' : 'Start practice'

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <h2 className="mb-1 text-xl font-semibold text-slate-900 dark:text-slate-100">
        Start a new quiz
      </h2>
      <p className="mb-5 text-sm text-slate-600 dark:text-slate-400">
        Pick a mode and scope. Leave filters on defaults for a full mixed-bag PCEP run.
      </p>

      <div className="mb-5 grid grid-cols-1 gap-2 sm:grid-cols-2">
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
                    ? 'border-slate-900 bg-slate-900 text-white dark:border-sky-600 dark:bg-sky-600'
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
        className="mt-6 w-full rounded-lg bg-slate-900 px-6 py-3 font-medium text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 dark:bg-sky-600 dark:hover:bg-sky-500 dark:disabled:bg-slate-700 dark:disabled:text-slate-400"
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
    </div>
  )
}
