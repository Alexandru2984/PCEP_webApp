const PASS_THRESHOLD = 70

export default function ScoreSummary({ score, total, onRestart }) {
  const pct = total > 0 ? Math.round((score / total) * 100) : 0
  const passed = pct >= PASS_THRESHOLD

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
      <h2 className="text-2xl font-bold text-slate-900 mb-2">Quiz complete</h2>

      <div className={`text-6xl font-bold my-6 ${passed ? 'text-green-600' : 'text-orange-600'}`}>
        {pct}%
      </div>

      <p className="text-lg text-slate-700 mb-1">
        You answered <span className="font-semibold">{score}</span> of{' '}
        <span className="font-semibold">{total}</span> correctly.
      </p>
      <p
        className={`text-lg font-semibold mb-6 ${
          passed ? 'text-green-600' : 'text-orange-600'
        }`}
      >
        {passed
          ? 'Passing score! Great job.'
          : `PCEP passing score is ${PASS_THRESHOLD}% — keep practicing.`}
      </p>

      <button
        onClick={onRestart}
        className="bg-slate-900 hover:bg-slate-700 text-white px-6 py-3 rounded-lg font-medium transition-colors"
      >
        Start a new quiz
      </button>
    </div>
  )
}
