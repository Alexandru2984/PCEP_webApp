import { useState } from 'react'
import { loadHistory, clearHistory } from '../storage'
import { formatElapsed } from '../format'

const MODULE_LABELS = {
  '': 'All modules',
  module1: 'M1 · Fundamentals',
  module2: 'M2 · Control Flow',
  module3: 'M3 · Data Collections',
  module4: 'M4 · Functions & Exceptions',
}

function Stat({ label, value, accent }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-center dark:border-slate-700 dark:bg-slate-900/50">
      <div
        className={`text-2xl font-bold ${accent ?? 'text-slate-900 dark:text-slate-100'}`}
      >
        {value}
      </div>
      <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{label}</div>
    </div>
  )
}

function MasteryBar({ label, pct }) {
  const tone = pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-slate-600 dark:text-slate-300">
        <span>{label}</span>
        <span className="font-semibold">{pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [attempts, setAttempts] = useState(loadHistory)

  if (attempts.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-8 text-center dark:border-slate-700 dark:bg-slate-800">
        <p className="text-slate-600 dark:text-slate-400">
          No attempts yet — finish a quiz and your progress shows up here.
        </p>
      </div>
    )
  }

  const totalAttempts = attempts.length
  const bestPct = Math.max(...attempts.map((a) => a.pct))
  const avgPct = Math.round(attempts.reduce((s, a) => s + a.pct, 0) / totalAttempts)
  const totalAnswered = attempts.reduce((s, a) => s + a.total, 0)
  const bestStreak = Math.max(...attempts.map((a) => a.bestStreak ?? 0))

  // Per-module mastery across every attempt scoped to a single module.
  const byModule = {}
  for (const a of attempts) {
    if (!a.module) continue
    const m = (byModule[a.module] ??= { score: 0, total: 0 })
    m.score += a.score
    m.total += a.total
  }
  const modules = Object.entries(byModule).map(([key, v]) => ({
    key,
    pct: v.total > 0 ? Math.round((v.score / v.total) * 100) : 0,
  }))

  const handleClear = () => {
    if (window.confirm('Clear all saved progress? This cannot be undone.')) {
      clearHistory()
      setAttempts([])
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
        <h2 className="mb-4 text-xl font-semibold text-slate-900 dark:text-slate-100">
          Your progress
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Stat label="Attempts" value={totalAttempts} />
          <Stat
            label="Best score"
            value={`${bestPct}%`}
            accent={bestPct >= 70 ? 'text-green-600 dark:text-green-400' : undefined}
          />
          <Stat label="Average" value={`${avgPct}%`} />
          <Stat label="Questions" value={totalAnswered} />
          <Stat
            label="Best streak"
            value={bestStreak}
            accent={bestStreak >= 5 ? 'text-green-600 dark:text-green-400' : undefined}
          />
        </div>

        {modules.length > 0 && (
          <div className="mt-6 space-y-3">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
              Module mastery
            </h3>
            {modules.map((m) => (
              <MasteryBar key={m.key} label={MODULE_LABELS[m.key] ?? m.key} pct={m.pct} />
            ))}
          </div>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            Recent attempts
          </h3>
          <button
            type="button"
            onClick={handleClear}
            className="text-xs text-slate-400 underline underline-offset-2 hover:text-red-500 dark:text-slate-500"
          >
            Clear history
          </button>
        </div>
        <ul className="divide-y divide-slate-100 dark:divide-slate-700">
          {attempts.slice(0, 10).map((a, i) => (
            <li key={i} className="flex items-center justify-between gap-2 py-2 text-sm">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                      a.mode === 'exam'
                        ? 'bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-300'
                        : 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'
                    }`}
                  >
                    {a.mode === 'exam' ? 'Exam' : 'Practice'}
                  </span>
                  <span className="truncate text-slate-600 dark:text-slate-400">
                    {MODULE_LABELS[a.module] ?? a.module}
                    {a.difficulty ? ` · ${a.difficulty}` : ''}
                  </span>
                </div>
                <div className="text-xs text-slate-400 dark:text-slate-500">
                  {new Date(a.date).toLocaleDateString()}
                  {a.elapsedMs ? ` · ${formatElapsed(a.elapsedMs)}` : ''}
                  {a.bestStreak ? ` · streak ${a.bestStreak}` : ''}
                </div>
              </div>
              <div
                className={`shrink-0 font-bold ${
                  a.pct >= 70
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-orange-600 dark:text-orange-400'
                }`}
              >
                {a.pct}%
                <span className="ml-1 text-xs font-normal text-slate-400">
                  ({a.score}/{a.total})
                </span>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
