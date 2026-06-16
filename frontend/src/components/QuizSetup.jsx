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

export default function QuizSetup({ onStart, initial }) {
  const [module, setModule] = useState(initial?.module ?? '')
  const [difficulty, setDifficulty] = useState(initial?.difficulty ?? '')
  const [count, setCount] = useState(initial?.count ?? 30)

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
      <h2 className="text-xl font-semibold text-slate-900 mb-1">Start a new quiz</h2>
      <p className="text-slate-600 text-sm mb-6">
        Pick a scope and question count. Leave filters on defaults for a full mixed-bag PCEP run.
      </p>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col text-sm">
          <span className="font-medium text-slate-700 mb-1">Module</span>
          <select
            value={module}
            onChange={(e) => setModule(e.target.value)}
            className="border border-slate-300 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            {MODULES.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col text-sm">
          <span className="font-medium text-slate-700 mb-1">Difficulty</span>
          <select
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
            className="border border-slate-300 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            {DIFFICULTIES.map((d) => (
              <option key={d.value} value={d.value}>{d.label}</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col text-sm sm:col-span-2">
          <span className="font-medium text-slate-700 mb-1">Questions: {count}</span>
          <div className="flex gap-2">
            {COUNTS.map((n) => (
              <button
                type="button"
                key={n}
                onClick={() => setCount(n)}
                className={`px-4 py-2 rounded-lg border transition-colors ${
                  count === n
                    ? 'bg-slate-900 text-white border-slate-900'
                    : 'bg-white text-slate-700 border-slate-300 hover:border-slate-500'
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </label>
      </div>

      <button
        onClick={() => onStart({ module, difficulty, count })}
        className="mt-6 w-full bg-slate-900 hover:bg-slate-700 text-white px-6 py-3 rounded-lg font-medium transition-colors"
      >
        Start quiz
      </button>
    </div>
  )
}
