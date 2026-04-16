export default function QuestionCard({
  question,
  questionNumber,
  totalQuestions,
  onAnswerSelect,
  selectedChoiceId,
  feedback,
  disabled,
}) {
  const getChoiceClass = (choice) => {
    const base = 'w-full text-left px-4 py-3 rounded-lg border transition-colors'
    if (!feedback) {
      if (selectedChoiceId === choice.id) {
        return `${base} border-blue-500 bg-blue-50`
      }
      return `${base} border-slate-200 hover:border-slate-400 hover:bg-slate-50 cursor-pointer`
    }
    if (choice.id === feedback.correct_choice_id) {
      return `${base} border-green-500 bg-green-50 text-green-900`
    }
    if (choice.id === selectedChoiceId) {
      return `${base} border-red-500 bg-red-50 text-red-900`
    }
    return `${base} border-slate-200 text-slate-500`
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
      <div className="flex items-center justify-between text-sm text-slate-500 mb-3">
        <span>
          Question <span className="font-semibold text-slate-700">{questionNumber}</span> of{' '}
          <span className="font-semibold text-slate-700">{totalQuestions}</span>
        </span>
        <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-xs uppercase tracking-wide">
          {question.difficulty}
        </span>
      </div>

      <h2 className="text-lg font-semibold text-slate-900 mb-3">{question.text}</h2>

      {question.code_snippet && (
        <pre className="bg-slate-900 text-slate-100 rounded-lg p-4 mb-4 overflow-x-auto text-sm">
          <code>{question.code_snippet}</code>
        </pre>
      )}

      <div className="space-y-2">
        {question.choices.map((choice, idx) => (
          <button
            key={choice.id}
            onClick={() => !disabled && onAnswerSelect(choice.id)}
            disabled={disabled}
            className={getChoiceClass(choice)}
          >
            <span className="font-mono mr-2 text-slate-500">
              {String.fromCharCode(65 + idx)}.
            </span>
            {choice.text}
          </button>
        ))}
      </div>
    </div>
  )
}
