export default function FeedbackBox({ feedback, onNext, isLast }) {
  const ok = feedback.is_correct
  return (
    <div
      role="status"
      aria-live="polite"
      className={`mt-4 rounded-xl border p-5 ${
        ok
          ? 'border-green-300 bg-green-50 dark:border-green-800 dark:bg-green-950/40'
          : 'border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/40'
      }`}
    >
      <div className="mb-2 flex items-center gap-2">
        <span
          className={`text-2xl font-bold ${ok ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}
        >
          {ok ? '✓' : '✗'}
        </span>
        <h3
          className={`text-lg font-semibold ${ok ? 'text-green-900 dark:text-green-200' : 'text-red-900 dark:text-red-200'}`}
        >
          {ok ? 'Correct!' : 'Not quite.'}
        </h3>
      </div>

      <div className="whitespace-pre-wrap leading-relaxed text-slate-800 dark:text-slate-200">
        <span className="font-semibold">Explanation: </span>
        {feedback.explanation}
      </div>

      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={onNext}
          className="rounded-lg bg-slate-900 px-5 py-2 font-medium text-white transition-colors hover:bg-slate-700 dark:bg-sky-600 dark:hover:bg-sky-500"
        >
          {isLast ? 'See Results →' : 'Next Question →'}
        </button>
      </div>
    </div>
  )
}
