import { useState } from 'react'
import {
  loadAdaptivePlan,
  loadBookmarks,
  loadHistory,
  loadMistakes,
  loadStudySummary,
} from '../storage'
import { formatElapsed } from '../format'
import { performanceInsights } from '../progressInsights'
import ProgressTools from './ProgressTools'

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

function MasteryBar({ label, pct, onDrill }) {
  const tone = pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-slate-600 dark:text-slate-300">
        <span>{label}</span>
        <span className="flex items-center gap-2">
          <span className="font-semibold">{pct}%</span>
          {onDrill && (
            <button
              type="button"
              onClick={onDrill}
              className="rounded text-sky-700 underline underline-offset-2 hover:text-sky-800 dark:text-sky-400 dark:hover:text-sky-300"
            >
              Drill
            </button>
          )}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function ScoreTrend({ scores }) {
  if (scores.length < 2) return null
  const description = scores.map(({ score }) => `${score}%`).join(', ')
  return (
    <figure className="mt-5 border-t border-slate-200 pt-5 dark:border-slate-700">
      <figcaption className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-300">
        Last {scores.length} graded scores
      </figcaption>
      <div className="flex gap-3">
        <div
          aria-hidden="true"
          className="flex h-32 flex-col justify-between text-xs text-slate-500 dark:text-slate-400"
        >
          <span>100%</span>
          <span>50%</span>
          <span>0%</span>
        </div>
        <ol
          aria-label={`Graded scores from oldest to newest: ${description}`}
          className="flex h-32 min-w-0 flex-1 items-end gap-1 border-b border-l border-slate-300 px-2 pt-2 dark:border-slate-600 sm:gap-2"
        >
          {scores.map(({ date, score }, index) => (
            <li
              key={`${date}-${index}`}
              className="flex h-full min-w-0 flex-1 items-end"
              aria-label={`${new Date(date).toLocaleDateString()}: ${score}%`}
              title={`${new Date(date).toLocaleDateString()}: ${score}%`}
            >
              <span
                aria-hidden="true"
                className={`w-full rounded-t ${
                  score >= 70
                    ? 'bg-emerald-500 dark:bg-emerald-400'
                    : 'bg-amber-500 dark:bg-amber-400'
                }`}
                style={{ height: `${Math.max(score, 3)}%` }}
              />
            </li>
          ))}
        </ol>
      </div>
    </figure>
  )
}

function StudyMomentum({ attempts }) {
  const insights = performanceInsights(attempts)
  const trend = insights.trend
  const trendValue = trend
    ? trend.delta === 0
      ? '0 pts'
      : `${trend.delta > 0 ? '+' : ''}${trend.delta} pts`
    : '—'
  const trendAccent =
    trend?.direction === 'improving'
      ? 'text-green-700 dark:text-green-400'
      : trend?.direction === 'declining'
        ? 'text-amber-700 dark:text-amber-400'
        : undefined

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
        Study momentum
      </h2>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Current study streak" value={`${insights.current}d`} />
        <Stat label="Longest study streak" value={`${insights.longest}d`} />
        <Stat
          label="Average time / question"
          value={
            insights.averageMsPerQuestion === null
              ? '—'
              : formatElapsed(insights.averageMsPerQuestion)
          }
        />
        <Stat label="Recent score trend" value={trendValue} accent={trendAccent} />
      </div>
      {trend ? (
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
          Your latest {trend.windowSize} graded sessions average {trend.recent}%, compared
          with {trend.previous}% in the previous {trend.windowSize}.
        </p>
      ) : (
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
          Complete at least four graded sessions to compare recent performance.
        </p>
      )}
      {insights.confidence.rated > 0 && (
        <div className="mt-3 rounded-lg border border-violet-200 bg-violet-50 p-3 text-sm text-violet-950 dark:border-violet-800 dark:bg-violet-950/30 dark:text-violet-100">
          <span className="font-semibold">Confidence calibration: </span>
          {insights.confidence.highTotal > 0
            ? `${Math.round((insights.confidence.highCorrect / insights.confidence.highTotal) * 100)}% accuracy when highly confident; ${insights.confidence.highMisses} confident miss${insights.confidence.highMisses === 1 ? '' : 'es'}.`
            : 'Rate more answers with high confidence to measure calibration.'}{' '}
          {insights.confidence.lowCorrect > 0
            ? `${insights.confidence.lowCorrect} low-confidence answer${insights.confidence.lowCorrect === 1 ? ' was' : 's were'} correct.`
            : ''}
        </div>
      )}
      <ScoreTrend scores={insights.scores} />
      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
        Study streaks use local calendar days and stay active until the end of the day
        after your last session. Score trends and pace exclude self-rated flashcards.
        {insights.measuredResponseTime
          ? ' Pace uses measured time to first answer.'
          : ' Older sessions use total session time for pace.'}
      </p>
    </section>
  )
}

function StudyPlan({ summary, onDueReviews, adaptivePlan, onAdaptivePractice }) {
  if (!summary.tracked && !adaptivePlan?.count) return null
  return (
    <section className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-5 dark:border-emerald-900 dark:bg-emerald-950/20">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Review plan
          </h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Correct reviews move through 1, 3, 7 and longer day intervals. A miss is due
            again immediately. The recommended set ranks due work, mistakes, low
            confidence, low mastery and tougher questions locally in your browser.
          </p>
        </div>
        <div className="flex shrink-0 flex-col gap-2">
          {adaptivePlan?.count > 0 && onAdaptivePractice && (
            <button
              type="button"
              onClick={onAdaptivePractice}
              className="rounded-lg bg-violet-700 px-4 py-3 font-medium text-white hover:bg-violet-800"
            >
              Start recommended ({adaptivePlan.count})
            </button>
          )}
          {summary.due > 0 && onDueReviews && (
            <button
              type="button"
              onClick={onDueReviews}
              className="rounded-lg border border-emerald-600 bg-white px-4 py-2.5 font-medium text-emerald-800 hover:bg-emerald-100 dark:bg-slate-900 dark:text-emerald-300"
            >
              Review due ({summary.due})
            </button>
          )}
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Due now" value={summary.due} />
        <Stat label="Questions tracked" value={summary.tracked} />
        <Stat label="Strong" value={summary.strong} />
        <Stat label="Average mastery" value={`${summary.averageMastery}%`} />
      </div>
      {summary.due === 0 && summary.nextReview && (
        <p className="mt-3 text-sm text-emerald-900 dark:text-emerald-200">
          Next review: {new Date(summary.nextReview).toLocaleDateString()}.
        </p>
      )}
      {summary.uncertain > 0 && (
        <p className="mt-3 text-sm text-violet-800 dark:text-violet-200">
          {summary.uncertain} question{summary.uncertain === 1 ? '' : 's'} with a latest
          low-confidence rating will stay visible to adaptive practice.
        </p>
      )}
    </section>
  )
}

export default function Dashboard({
  onDrill,
  onBookmarks,
  onMistakes,
  onDueReviews,
  onAdaptivePractice,
}) {
  const [attempts, setAttempts] = useState(loadHistory)
  const refresh = () => setAttempts(loadHistory())
  const tools = <ProgressTools key="progress-tools" onChange={refresh} />
  const bookmarks = loadBookmarks().length
  const mistakes = loadMistakes().length
  const study = loadStudySummary()
  const adaptivePlan = loadAdaptivePlan()

  if (attempts.length === 0) {
    return (
      <div className="space-y-4">
        <StudyPlan
          summary={study}
          onDueReviews={onDueReviews}
          adaptivePlan={adaptivePlan}
          onAdaptivePractice={onAdaptivePractice}
        />
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center dark:border-slate-700 dark:bg-slate-800">
          <p className="text-slate-600 dark:text-slate-400">
            No attempts yet — finish a quiz and your progress shows up here.
          </p>
        </div>
        {tools}
      </div>
    )
  }

  const totalAttempts = attempts.length
  const graded = attempts.filter((a) => a.mode !== 'flashcards')
  const bestPct = graded.length ? Math.max(...graded.map((a) => a.pct)) : 0
  const totalAnswered = graded.reduce((s, a) => s + a.total, 0)
  const avgPct = totalAnswered
    ? Math.round((graded.reduce((s, a) => s + a.score, 0) / totalAnswered) * 100)
    : 0
  const bestStreak = graded.length ? Math.max(...graded.map((a) => a.bestStreak ?? 0)) : 0

  // Include mixed sessions; self-rated flashcards are kept separate from graded accuracy.
  const byModule = {}
  const byDifficulty = {}
  for (const a of attempts) {
    if (a.mode === 'flashcards') continue
    const groups =
      a.byModule ?? (a.module ? { [a.module]: { score: a.score, total: a.total } } : {})
    for (const [key, row] of Object.entries(groups)) {
      const m = (byModule[key] ??= { score: 0, total: 0 })
      m.score += row.score
      m.total += row.total
    }
    const levels =
      a.byDifficulty ??
      (a.difficulty ? { [a.difficulty]: { score: a.score, total: a.total } } : {})
    for (const [key, row] of Object.entries(levels)) {
      const level = (byDifficulty[key] ??= { score: 0, total: 0 })
      level.score += row.score
      level.total += row.total
    }
  }
  const modules = Object.entries(byModule).map(([key, v]) => ({
    key,
    pct: v.total > 0 ? Math.round((v.score / v.total) * 100) : 0,
  }))

  return (
    <div className="space-y-4">
      <StudyPlan
        summary={study}
        onDueReviews={onDueReviews}
        adaptivePlan={adaptivePlan}
        onAdaptivePractice={onAdaptivePractice}
      />
      {(bookmarks > 0 || mistakes > 0) && (
        <div className="flex flex-wrap gap-2">
          {mistakes > 0 && onMistakes && (
            <button
              type="button"
              onClick={onMistakes}
              className="rounded-lg bg-amber-700 px-4 py-3 font-medium text-white"
            >
              Practice mistakes ({mistakes})
            </button>
          )}
          {bookmarks > 0 && onBookmarks && (
            <button
              type="button"
              onClick={onBookmarks}
              className="rounded-lg bg-sky-700 px-4 py-3 font-medium text-white"
            >
              Practice bookmarks ({bookmarks})
            </button>
          )}
        </div>
      )}
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
        <h2 className="mb-4 text-xl font-semibold text-slate-900 dark:text-slate-100">
          Your progress
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Stat label="Attempts" value={totalAttempts} />
          <Stat
            label="Best score"
            value={`${bestPct}%`}
            accent={bestPct >= 70 ? 'text-green-700 dark:text-green-400' : undefined}
          />
          <Stat label="Graded accuracy" value={`${avgPct}%`} />
          <Stat label="Graded questions" value={totalAnswered} />
          <Stat
            label="Best streak"
            value={bestStreak}
            accent={bestStreak >= 5 ? 'text-green-700 dark:text-green-400' : undefined}
          />
        </div>
        <p className="mt-3 text-xs text-slate-600 dark:text-slate-300">
          Flashcards are self-rated and excluded from graded accuracy. Breakdowns include
          mixed quizzes completed with this version; older mixed sessions have no topic
          detail.
        </p>

        {modules.length > 0 && (
          <div className="mt-6 space-y-3">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
              Module accuracy
            </h3>
            {modules.map((m) => (
              <MasteryBar
                key={m.key}
                label={MODULE_LABELS[m.key] ?? m.key}
                pct={m.pct}
                onDrill={onDrill && m.key ? () => onDrill(m.key) : undefined}
              />
            ))}
          </div>
        )}
        {Object.keys(byDifficulty).length > 0 && (
          <div className="mt-6 space-y-3">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
              Difficulty accuracy
            </h3>
            {Object.entries(byDifficulty).map(([key, row]) => (
              <MasteryBar
                key={key}
                label={key[0].toUpperCase() + key.slice(1)}
                pct={Math.round((row.score / row.total) * 100)}
              />
            ))}
          </div>
        )}
      </div>

      <StudyMomentum attempts={attempts} />

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            Recent attempts
          </h3>
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
                    {a.mode === 'exam'
                      ? 'Exam'
                      : a.mode === 'flashcards'
                        ? 'Cards'
                        : 'Practice'}
                  </span>
                  <span className="truncate text-slate-600 dark:text-slate-400">
                    {MODULE_LABELS[a.module] ?? a.module}
                    {a.difficulty ? ` · ${a.difficulty}` : ''}
                  </span>
                </div>
                <div className="text-xs text-slate-500 dark:text-slate-400">
                  {new Date(a.date).toLocaleDateString()}
                  {a.elapsedMs ? ` · ${formatElapsed(a.elapsedMs)}` : ''}
                  {a.bestStreak ? ` · streak ${a.bestStreak}` : ''}
                </div>
              </div>
              <div
                className={`shrink-0 font-bold ${
                  a.pct >= 70
                    ? 'text-green-700 dark:text-green-400'
                    : 'text-orange-700 dark:text-orange-400'
                }`}
              >
                {a.pct}%
                <span className="ml-1 text-xs font-normal text-slate-500 dark:text-slate-400">
                  ({a.score}/{a.total})
                </span>
              </div>
            </li>
          ))}
        </ul>
      </div>
      {tools}
    </div>
  )
}
