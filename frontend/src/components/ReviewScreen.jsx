import { useEffect, useState } from 'react'
import CodeRunner from './CodeRunner'
import PerformanceReport from './PerformanceReport'
import { celebrate } from '../confetti'
import { useCountUp } from '../useCountUp'

const MODULE_LABELS = {
  module1: 'M1 · Fundamentals',
  module2: 'M2 · Control Flow',
  module3: 'M3 · Data Collections',
  module4: 'M4 · Functions & Exceptions',
}

const pill =
  'rounded-full px-2 py-0.5 bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'

function ReviewItem({ index, item }) {
  const { question, pickedChoiceId, feedback } = item
  const ok = feedback?.is_correct
  const correctId = feedback?.correct_choice_id
  const skipped = pickedChoiceId == null
  const correctExplanation = feedback?.correct_explanation
  // Show the concept behind the right answer whenever the learner missed it.
  const showCorrectWhy =
    !ok && correctExplanation && correctExplanation !== feedback?.explanation

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-800">
      <div className="mb-2 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
        <span>Q{index + 1}</span>
        <div className="flex items-center gap-2">
          <span className={pill}>
            {MODULE_LABELS[question.module] ?? question.module}
          </span>
          <span className={`${pill} uppercase tracking-wide`}>{question.difficulty}</span>
          <span
            className={`rounded-full px-2 py-0.5 font-semibold ${
              skipped
                ? 'bg-slate-200 text-slate-700 dark:bg-slate-600 dark:text-slate-200'
                : ok
                  ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300'
                  : 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300'
            }`}
          >
            {skipped ? 'skipped' : ok ? '✓ correct' : '✗ wrong'}
          </span>
        </div>
      </div>

      <p className="font-semibold text-slate-900 dark:text-slate-100">{question.text}</p>
      {question.code_snippet && (
        <CodeRunner code={question.code_snippet} className="mt-2" />
      )}

      <ul className="mt-3 space-y-1.5">
        {question.choices.map((c, i) => {
          const isCorrect = c.id === correctId
          const isPicked = c.id === pickedChoiceId
          let cls =
            'border-slate-200 text-slate-700 dark:border-slate-700 dark:text-slate-300'
          if (isCorrect)
            cls =
              'border-green-500 bg-green-50 text-green-900 dark:border-green-600 dark:bg-green-950/40 dark:text-green-200'
          else if (isPicked)
            cls =
              'border-red-500 bg-red-50 text-red-900 dark:border-red-600 dark:bg-red-950/40 dark:text-red-200'
          return (
            <li
              key={c.id}
              className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${cls}`}
            >
              <span className="font-mono text-slate-500">
                {String.fromCharCode(65 + i)}.
              </span>
              <span className="flex-1">{c.text}</span>
              {isCorrect && (
                <span className="text-xs font-semibold text-green-700 dark:text-green-400">
                  correct
                </span>
              )}
              {isPicked && !isCorrect && (
                <span className="text-xs font-semibold text-red-700 dark:text-red-400">
                  your pick
                </span>
              )}
            </li>
          )
        })}
      </ul>

      {feedback?.explanation && (
        <div className="mt-3 whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-300">
          <span className="font-semibold">
            {ok ? 'Why: ' : 'Why your pick is wrong: '}
          </span>
          {feedback.explanation}
        </div>
      )}

      {showCorrectWhy && (
        <div className="mt-2 whitespace-pre-wrap rounded-lg border border-green-300 bg-green-50 p-3 text-sm text-green-900 dark:border-green-800 dark:bg-green-950/40 dark:text-green-200">
          <span className="font-semibold">Why the correct answer is right: </span>
          {correctExplanation}
        </div>
      )}
    </li>
  )
}

export default function ReviewScreen({
  items,
  score,
  total,
  onRestart,
  elapsedLabel,
  streakStats,
}) {
  const [filter, setFilter] = useState('wrong')
  const wrong = items.filter((i) => !i.feedback?.is_correct)
  const shown = filter === 'wrong' ? wrong : items

  const pct = total > 0 ? Math.round((score / total) * 100) : 0
  const passed = pct >= 70
  const animatedPct = useCountUp(pct)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (passed) celebrate()
  }, [passed])

  const share = async () => {
    const text = `I scored ${score}/${total} (${pct}%) on the PCEP practice exam${passed ? ' ✅' : ''} — try it at https://pcep.micutu.com 🐍`
    try {
      if (navigator.share) {
        await navigator.share({ text, url: 'https://pcep.micutu.com' })
      } else if (navigator.clipboard) {
        await navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      }
    } catch {
      /* user dismissed the share sheet — ignore */
    }
  }

  const tab = (active) =>
    `px-3 py-1.5 rounded-full border text-sm transition-colors ${
      active
        ? 'bg-slate-900 text-white border-slate-900 dark:bg-sky-600 dark:border-sky-600'
        : 'bg-white text-slate-700 border-slate-300 hover:border-slate-500 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600'
    }`

  return (
    <div>
      <div className="mb-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
              Quiz complete
            </h2>
            <p className="mt-1 text-slate-700 dark:text-slate-300">
              <span className="font-semibold">{score}</span> of{' '}
              <span className="font-semibold">{total}</span> correct —{' '}
              <span
                className={`font-bold ${passed ? 'text-green-600 dark:text-green-400' : 'text-orange-600 dark:text-orange-400'}`}
              >
                {animatedPct}%
              </span>
              {passed ? ' · passing' : ' · below 70% PCEP threshold'}
              {elapsedLabel ? ` · ${elapsedLabel}` : ''}
            </p>
            {streakStats?.best > 1 && (
              <div className="mt-3 inline-flex rounded-full border border-green-200 bg-green-50 px-3 py-1 text-sm font-medium text-green-700 dark:border-green-800 dark:bg-green-950/40 dark:text-green-300">
                Best streak: {streakStats.best}
              </div>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={share}
              className="rounded-lg border border-slate-300 px-4 py-2.5 font-medium text-slate-700 transition-colors hover:bg-slate-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              {copied ? 'Copied ✓' : 'Share'}
            </button>
            <button
              type="button"
              onClick={onRestart}
              className="rounded-lg bg-slate-900 px-5 py-2.5 font-medium text-white transition-colors hover:bg-slate-700 dark:bg-sky-600 dark:hover:bg-sky-500"
            >
              New quiz
            </button>
          </div>
        </div>

        <div className="mt-5 flex gap-2">
          <button
            type="button"
            onClick={() => setFilter('wrong')}
            className={tab(filter === 'wrong')}
          >
            Wrong only ({wrong.length})
          </button>
          <button
            type="button"
            onClick={() => setFilter('all')}
            className={tab(filter === 'all')}
          >
            All ({total})
          </button>
        </div>
      </div>

      <PerformanceReport items={items} />

      {shown.length === 0 ? (
        <div className="rounded-xl border border-green-200 bg-green-50 p-6 text-center font-medium text-green-800 dark:border-green-800 dark:bg-green-950/40 dark:text-green-300">
          Flawless — no wrong answers to review.
        </div>
      ) : (
        <ul className="space-y-3">
          {shown.map((item) => (
            <ReviewItem key={item.question.id} index={items.indexOf(item)} item={item} />
          ))}
        </ul>
      )}
    </div>
  )
}
