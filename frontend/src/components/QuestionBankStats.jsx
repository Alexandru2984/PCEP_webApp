const DIFFICULTY_LABELS = {
  easy: 'Easy',
  medium: 'Medium',
  hard: 'Hard',
}

function getScopeTotal(stats, selectedModule, selectedDifficulty) {
  if (!stats) return 0
  if (selectedModule && selectedDifficulty) {
    return stats.matrix?.[selectedModule]?.[selectedDifficulty] ?? 0
  }
  if (selectedModule) return stats.by_module?.[selectedModule] ?? 0
  if (selectedDifficulty) return stats.by_difficulty?.[selectedDifficulty] ?? 0
  return stats.total ?? 0
}

export default function QuestionBankStats({
  stats,
  loading,
  error,
  selectedModule,
  selectedDifficulty,
}) {
  if (loading) {
    return (
      <section
        className="mt-6 border-t border-slate-200 pt-5 dark:border-slate-700"
        aria-live="polite"
      >
        <div className="h-4 w-40 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {[0, 1, 2].map((item) => (
            <div
              key={item}
              className="h-16 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-900"
            />
          ))}
        </div>
      </section>
    )
  }

  if (error) {
    return (
      <section className="mt-6 border-t border-slate-200 pt-5 dark:border-slate-700">
        <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
          Question-bank snapshot
        </p>
        <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">{error}</p>
      </section>
    )
  }

  if (!stats) return null

  const scopeTotal = getScopeTotal(stats, selectedModule, selectedDifficulty)
  const hardTotal = stats.by_difficulty?.hard ?? 0
  const passThreshold = stats.pass_threshold ?? 70
  const maxModuleTotal = Math.max(...stats.modules.map((m) => m.total), 1)

  return (
    <section className="mt-6 border-t border-slate-200 pt-5 dark:border-slate-700">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
            Question-bank snapshot
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Live coverage from the production database.
          </p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
            {scopeTotal}
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400">available in scope</p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700">
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Total</p>
          <p className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-100">
            {stats.total}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700">
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Hard</p>
          <p className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-100">
            {hardTotal}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700">
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">
            Pass target
          </p>
          <p className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-100">
            {passThreshold}%
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        {stats.modules.map((module) => (
          <div key={module.value}>
            <div className="mb-1 flex items-center justify-between gap-3 text-xs">
              <span className="truncate text-slate-600 dark:text-slate-300">
                {module.label}
              </span>
              <span className="shrink-0 font-medium text-slate-700 dark:text-slate-200">
                {module.total}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-900">
              <div
                className="h-full rounded-full bg-sky-500"
                style={{ width: `${(module.total / maxModuleTotal) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {Object.entries(DIFFICULTY_LABELS).map(([value, label]) => (
          <span
            key={value}
            className="rounded-full border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300"
          >
            {label}: {stats.by_difficulty?.[value] ?? 0}
          </span>
        ))}
      </div>
    </section>
  )
}
