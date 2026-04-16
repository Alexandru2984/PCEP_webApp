import { useEffect, useState } from 'react'
import { fetchQuizSet, submitAnswer } from '../api'
import QuestionCard from './QuestionCard'
import FeedbackBox from './FeedbackBox'
import ScoreSummary from './ScoreSummary'

const QUIZ_COUNT = 30

export default function QuizContainer() {
  const [questions, setQuestions] = useState([])
  const [index, setIndex] = useState(0)
  const [selectedChoiceId, setSelectedChoiceId] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [score, setScore] = useState(0)
  const [phase, setPhase] = useState('loading')
  const [error, setError] = useState(null)

  const loadQuiz = async () => {
    setPhase('loading')
    setError(null)
    try {
      const data = await fetchQuizSet(QUIZ_COUNT)
      if (!data.questions || data.questions.length === 0) {
        throw new Error('No questions available. Seed the database first.')
      }
      setQuestions(data.questions)
      setIndex(0)
      setSelectedChoiceId(null)
      setFeedback(null)
      setScore(0)
      setPhase('answering')
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to load quiz.')
      setPhase('error')
    }
  }

  useEffect(() => {
    loadQuiz()
  }, [])

  const handleSelect = async (choiceId) => {
    if (phase !== 'answering') return
    setSelectedChoiceId(choiceId)
    try {
      const data = await submitAnswer(questions[index].id, choiceId)
      setFeedback(data)
      if (data.is_correct) setScore((s) => s + 1)
      setPhase('reviewing')
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to submit answer.')
      setPhase('error')
    }
  }

  const handleNext = () => {
    if (index + 1 >= questions.length) {
      setPhase('done')
      return
    }
    setIndex((i) => i + 1)
    setSelectedChoiceId(null)
    setFeedback(null)
    setPhase('answering')
  }

  if (phase === 'loading') {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
        <p className="text-slate-600">Loading quiz…</p>
      </div>
    )
  }

  if (phase === 'error') {
    return (
      <div className="bg-white rounded-xl border border-red-200 p-6">
        <p className="text-red-700 font-semibold mb-2">Something went wrong.</p>
        <p className="text-slate-700 mb-4">{error}</p>
        <button
          onClick={loadQuiz}
          className="bg-slate-900 hover:bg-slate-700 text-white px-4 py-2 rounded-lg"
        >
          Try again
        </button>
      </div>
    )
  }

  if (phase === 'done') {
    return <ScoreSummary score={score} total={questions.length} onRestart={loadQuiz} />
  }

  const current = questions[index]
  return (
    <div>
      <QuestionCard
        question={current}
        questionNumber={index + 1}
        totalQuestions={questions.length}
        onAnswerSelect={handleSelect}
        selectedChoiceId={selectedChoiceId}
        feedback={feedback}
        disabled={phase === 'reviewing'}
      />
      {feedback && (
        <FeedbackBox
          feedback={feedback}
          onNext={handleNext}
          isLast={index + 1 >= questions.length}
        />
      )}
    </div>
  )
}
