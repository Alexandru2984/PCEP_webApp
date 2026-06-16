import { useState } from 'react'

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

export default function QuizSetup({ onStart, initial }) {
  const [module, setModule] = useState(initial?.module ?? '')
  const [difficulty, setDifficulty] = useState(initial?.difficulty ?? '')
  const [count, setCount] = useState(initial?.count ?? 30)

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <h2 className="mb-1 text-xl font-semibold text-slate-900 dark:text-slate-100">
        Start a new quiz
      </h2>
      <p className="mb-6 text-sm text-slate-600 dark:text-slate-400">
        Pick a scope and question count. Leave filters on defaults for a full mixed-bag
        PCEP run.
      </p>

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
        </div>
      </div>

      <button
        type="button"
        onClick={() => onStart({ module, difficulty, count })}
        className="mt-6 w-full rounded-lg bg-slate-900 px-6 py-3 font-medium text-white transition-colors hover:bg-slate-700 dark:bg-sky-600 dark:hover:bg-sky-500"
      >
        Start quiz
      </button>
    </div>
  )
}
