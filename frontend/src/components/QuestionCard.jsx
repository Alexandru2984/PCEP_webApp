import { lazy, Suspense } from 'react'
import CodeBlock from './CodeBlock'

// CodeRunner pulls in the Pyodide worker manager — only practice/review need it,
// so load it on demand and show the static (read-only) CodeBlock until it's ready.
const CodeRunner = lazy(() => import('./CodeRunner'))

const DIFFICULTY_BADGE = {
  easy: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  medium: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  hard: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
}

export default function QuestionCard({
  question,
  questionNumber,
  totalQuestions,
  onAnswerSelect,
  selectedChoiceId,
  feedback,
  disabled,
  runnable = false,
}) {
  const getChoiceClass = (choice) => {
    const base =
      'w-full text-left px-4 py-3 rounded-lg border transition-colors flex items-start gap-2'
    if (!feedback) {
      if (selectedChoiceId === choice.id) {
        return `${base} border-blue-500 bg-blue-50 text-blue-900 dark:border-blue-400 dark:bg-blue-950/50 dark:text-blue-100`
      }
      return `${base} border-slate-200 hover:border-slate-400 hover:bg-slate-50 cursor-pointer dark:border-slate-700 dark:hover:border-slate-500 dark:hover:bg-slate-800`
    }
    if (choice.id === feedback.correct_choice_id) {
      return `${base} border-green-500 bg-green-50 text-green-900 dark:border-green-500 dark:bg-green-950/50 dark:text-green-200`
    }
    if (choice.id === selectedChoiceId) {
      return `${base} border-red-500 bg-red-50 text-red-900 dark:border-red-500 dark:bg-red-950/50 dark:text-red-200`
    }
    return `${base} border-slate-200 text-slate-500 dark:border-slate-700 dark:text-slate-500`
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <div className="mb-3 flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
        <span>
          Question{' '}
          <span className="font-semibold text-slate-700 dark:text-slate-200">
            {questionNumber}
          </span>{' '}
          of{' '}
          <span className="font-semibold text-slate-700 dark:text-slate-200">
            {totalQuestions}
          </span>
        </span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium uppercase tracking-wide ${
            DIFFICULTY_BADGE[question.difficulty] ?? 'bg-slate-100 text-slate-600'
          }`}
        >
          {question.difficulty}
        </span>
      </div>

      <h2 className="mb-3 text-lg font-semibold text-slate-900 dark:text-slate-100">
        {question.text}
      </h2>

      {question.code_snippet &&
        (runnable ? (
          <Suspense
            fallback={<CodeBlock code={question.code_snippet} className="mb-4" />}
          >
            <CodeRunner key={question.id} code={question.code_snippet} className="mb-4" />
          </Suspense>
        ) : (
          <CodeBlock code={question.code_snippet} className="mb-4" />
        ))}

      <div className="space-y-2" role="radiogroup" aria-label="Answer choices">
        {question.choices.map((choice, idx) => {
          const selected = selectedChoiceId === choice.id
          return (
            <button
              key={choice.id}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => !disabled && onAnswerSelect(choice.id)}
              disabled={disabled}
              className={getChoiceClass(choice)}
            >
              <span className="font-mono text-slate-500 dark:text-slate-400">
                {String.fromCharCode(65 + idx)}.
              </span>
              <span className="flex-1">{choice.text}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
