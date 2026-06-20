export default function FeedbackBox({ feedback, onNext, isLast }) {
  const ok = feedback.is_correct
  // On a wrong pick we have two distinct things to teach: why the chosen option
  // is wrong, and why the right one is right. Show both. When the correct
  // explanation is missing or identical to the pick's, fall back to one block.
  const correctExplanation = feedback.correct_explanation
  const showCorrect =
    !ok && correctExplanation && correctExplanation !== feedback.explanation

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

      {feedback.explanation && (
        <div className="leading-relaxed whitespace-pre-wrap text-slate-800 dark:text-slate-200">
          <span className="font-semibold">
            {ok ? 'Explanation: ' : 'Why your answer is wrong: '}
          </span>
          {feedback.explanation}
        </div>
      )}

      {showCorrect && (
        <div className="mt-3 rounded-lg border border-green-300 bg-green-100/60 p-3 leading-relaxed whitespace-pre-wrap text-green-900 dark:border-green-800 dark:bg-green-950/60 dark:text-green-200">
          <span className="font-semibold">Why the correct answer is right: </span>
          {correctExplanation}
        </div>
      )}

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
