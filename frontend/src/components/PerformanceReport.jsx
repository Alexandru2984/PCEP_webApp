// End-of-quiz performance report. Pure presentation over the same `items` the
// review list uses — no extra API calls. Breaks the result down by module and
// by difficulty and points the learner at their weakest area.

const MODULE_LABELS = {
  module1: 'M1 · Fundamentals',
  module2: 'M2 · Control Flow',
  module3: 'M3 · Data Collections',
  module4: 'M4 · Functions & Exceptions',
}

const MODULE_ORDER = ['module1', 'module2', 'module3', 'module4']
const DIFFICULTY_ORDER = ['easy', 'medium', 'hard']
const DIFFICULTY_LABELS = { easy: 'Easy', medium: 'Medium', hard: 'Hard' }
const PASS_THRESHOLD = 70

function tally(items, keyFn) {
  const groups = {}
  for (const item of items) {
    const key = keyFn(item)
    const g = (groups[key] ??= { correct: 0, total: 0 })
    g.total += 1
    if (item.feedback?.is_correct) g.correct += 1
  }
  return groups
}

function toRows(groups, order, labels) {
  return order
    .filter((key) => groups[key])
    .map((key) => {
      const { correct, total } = groups[key]
      return {
        key,
        label: labels[key] ?? key,
        correct,
        total,
        pct: total > 0 ? Math.round((correct / total) * 100) : 0,
      }
    })
}

function barTone(pct) {
  return pct >= PASS_THRESHOLD
    ? 'bg-green-500'
    : pct >= 40
      ? 'bg-amber-500'
      : 'bg-red-500'
}

function Breakdown({ title, rows }) {
  if (rows.length === 0) return null
  return (
    <div>
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {title}
      </h4>
      <div className="space-y-2.5">
        {rows.map((row) => (
          <div key={row.key}>
            <div className="mb-1 flex items-center justify-between gap-3 text-xs">
              <span className="truncate text-slate-600 dark:text-slate-300">
                {row.label}
              </span>
              <span className="shrink-0 font-medium text-slate-700 dark:text-slate-200">
                {row.correct}/{row.total} · {row.pct}%
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-900">
              <div
                className={`h-full rounded-full ${barTone(row.pct)}`}
                style={{ width: `${row.pct}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function PerformanceReport({ items, onDrillModule }) {
  if (!items || items.length === 0) return null

  const moduleRows = toRows(
    tally(items, (i) => i.question.module),
    MODULE_ORDER,
    MODULE_LABELS
  )
  const difficultyRows = toRows(
    tally(items, (i) => i.question.difficulty),
    DIFFICULTY_ORDER,
    DIFFICULTY_LABELS
  )

  // Weakest module worth calling out: lowest pct, tie broken by the larger
  // sample so a 0/1 fluke doesn't outrank a 2/6 genuine weak spot.
  const weakest = [...moduleRows].sort((a, b) => a.pct - b.pct || b.total - a.total)[0]
  const hasGap = weakest && weakest.pct < PASS_THRESHOLD

  return (
    <section className="mb-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
        Performance breakdown
      </h3>

      <div className="grid gap-6 sm:grid-cols-2">
        <Breakdown title="By module" rows={moduleRows} />
        <Breakdown title="By difficulty" rows={difficultyRows} />
      </div>

      <div
        className={`mt-5 rounded-lg border p-3 text-sm ${
          hasGap
            ? 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200'
            : 'border-green-300 bg-green-50 text-green-900 dark:border-green-800 dark:bg-green-950/40 dark:text-green-200'
        }`}
      >
        {hasGap ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>
              <span className="font-semibold">Focus area: </span>
              {weakest.label} — {weakest.correct}/{weakest.total} ({weakest.pct}%). Drill
              it next to lift it above the {PASS_THRESHOLD}% pass line.
            </span>
            {onDrillModule && (
              <button
                type="button"
                onClick={() => onDrillModule(weakest.key)}
                className="shrink-0 self-start rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-amber-700 sm:self-auto dark:bg-amber-700 dark:hover:bg-amber-600"
              >
                Practice this module →
              </button>
            )}
          </div>
        ) : (
          <>
            <span className="font-semibold">Strong across the board — </span>
            every module you touched is at or above the {PASS_THRESHOLD}% pass line.
          </>
        )}
      </div>
    </section>
  )
}
