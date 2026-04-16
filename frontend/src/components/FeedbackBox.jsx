export default function FeedbackBox({ feedback, onNext, isLast }) {
  const ok = feedback.is_correct
  return (
    <div
      className={`mt-4 rounded-xl border p-5 ${
        ok ? 'border-green-300 bg-green-50' : 'border-red-300 bg-red-50'
      }`}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-2xl font-bold ${ok ? 'text-green-600' : 'text-red-600'}`}>
          {ok ? '✓' : '✗'}
        </span>
        <h3 className={`text-lg font-semibold ${ok ? 'text-green-900' : 'text-red-900'}`}>
          {ok ? 'Correct!' : 'Not quite.'}
        </h3>
      </div>

      <div className="text-slate-800 whitespace-pre-wrap leading-relaxed">
        <span className="font-semibold">Explanation: </span>
        {feedback.explanation}
      </div>

      <div className="mt-4 flex justify-end">
        <button
          onClick={onNext}
          className="bg-slate-900 hover:bg-slate-700 text-white px-5 py-2 rounded-lg font-medium transition-colors"
        >
          {isLast ? 'See Results →' : 'Next Question →'}
        </button>
      </div>
    </div>
  )
}
