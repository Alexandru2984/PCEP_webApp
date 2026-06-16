import { useState } from 'react'

const MODULE_LABELS = {
  module1: 'M1 · Fundamentals',
  module2: 'M2 · Control Flow',
  module3: 'M3 · Data Collections',
  module4: 'M4 · Functions & Exceptions',
}

function ReviewItem({ index, item }) {
  const { question, pickedChoiceId, feedback } = item
  const ok = feedback?.is_correct
  const correctId = feedback?.correct_choice_id
  const skipped = pickedChoiceId == null

  return (
    <li className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
        <span>Q{index + 1}</span>
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
            {MODULE_LABELS[question.module] ?? question.module}
          </span>
          <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 uppercase tracking-wide">
            {question.difficulty}
          </span>
          <span
            className={`px-2 py-0.5 rounded-full font-semibold ${
              skipped
                ? 'bg-slate-200 text-slate-700'
                : ok
                  ? 'bg-green-100 text-green-800'
                  : 'bg-red-100 text-red-800'
            }`}
          >
            {skipped ? 'skipped' : ok ? '✓ correct' : '✗ wrong'}
          </span>
        </div>
      </div>

      <p className="font-semibold text-slate-900">{question.text}</p>
      {question.code_snippet && (
        <pre className="mt-2 bg-slate-900 text-slate-100 rounded-lg p-3 overflow-x-auto text-sm">
          <code>{question.code_snippet}</code>
        </pre>
      )}

      <ul className="mt-3 space-y-1.5">
        {question.choices.map((c, i) => {
          const isCorrect = c.id === correctId
          const isPicked = c.id === pickedChoiceId
          let cls = 'border-slate-200 text-slate-700'
          if (isCorrect) cls = 'border-green-500 bg-green-50 text-green-900'
          else if (isPicked) cls = 'border-red-500 bg-red-50 text-red-900'
          return (
            <li
              key={c.id}
              className={`border rounded-lg px-3 py-2 text-sm flex items-start gap-2 ${cls}`}
            >
              <span className="font-mono text-slate-500">
                {String.fromCharCode(65 + i)}.
              </span>
              <span className="flex-1">{c.text}</span>
              {isCorrect && (
                <span className="text-green-700 text-xs font-semibold">correct</span>
              )}
              {isPicked && !isCorrect && (
                <span className="text-red-700 text-xs font-semibold">your pick</span>
              )}
            </li>
          )
        })}
      </ul>

      {feedback?.explanation && (
        <div className="mt-3 text-sm text-slate-700 bg-slate-50 border border-slate-200 rounded-lg p-3 whitespace-pre-wrap">
          <span className="font-semibold">Why: </span>
          {feedback.explanation}
        </div>
      )}
    </li>
  )
}

export default function ReviewScreen({ items, score, total, onRestart }) {
  const [filter, setFilter] = useState('wrong')
  const wrong = items.filter((i) => !i.feedback?.is_correct)
  const shown = filter === 'wrong' ? wrong : items

  const pct = total > 0 ? Math.round((score / total) * 100) : 0
  const passed = pct >= 70

  return (
    <div>
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-slate-900">Quiz complete</h2>
            <p className="text-slate-700 mt-1">
              <span className="font-semibold">{score}</span> of{' '}
              <span className="font-semibold">{total}</span> correct —{' '}
              <span
                className={`font-bold ${passed ? 'text-green-600' : 'text-orange-600'}`}
              >
                {pct}%
              </span>
              {passed ? ' · passing' : ' · below 70% PCEP threshold'}
            </p>
          </div>
          <button
            onClick={onRestart}
            className="bg-slate-900 hover:bg-slate-700 text-white px-5 py-2.5 rounded-lg font-medium transition-colors"
          >
            New quiz
          </button>
        </div>

        <div className="mt-5 flex gap-2 text-sm">
          <button
            onClick={() => setFilter('wrong')}
            className={`px-3 py-1.5 rounded-full border ${
              filter === 'wrong'
                ? 'bg-slate-900 text-white border-slate-900'
                : 'bg-white text-slate-700 border-slate-300 hover:border-slate-500'
            }`}
          >
            Wrong only ({wrong.length})
          </button>
          <button
            onClick={() => setFilter('all')}
            className={`px-3 py-1.5 rounded-full border ${
              filter === 'all'
                ? 'bg-slate-900 text-white border-slate-900'
                : 'bg-white text-slate-700 border-slate-300 hover:border-slate-500'
            }`}
          >
            All ({total})
          </button>
        </div>
      </div>

      {shown.length === 0 ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center text-green-800 font-medium">
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
