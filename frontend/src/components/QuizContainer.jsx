import { useState } from 'react'
import { fetchQuizSet, submitAnswer } from '../api'
import QuestionCard from './QuestionCard'
import FeedbackBox from './FeedbackBox'
import ReviewScreen from './ReviewScreen'
import QuizSetup from './QuizSetup'

export default function QuizContainer() {
  const [phase, setPhase] = useState('setup')
  const [questions, setQuestions] = useState([])
  const [index, setIndex] = useState(0)
  const [selectedChoiceId, setSelectedChoiceId] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [history, setHistory] = useState([])
  const [lastConfig, setLastConfig] = useState(null)
  const [error, setError] = useState(null)

  const score = history.filter((h) => h.feedback?.is_correct).length

  const startQuiz = async (config) => {
    setPhase('loading')
    setError(null)
    setLastConfig(config)
    try {
      const data = await fetchQuizSet(config)
      if (!data.questions || data.questions.length === 0) {
        throw new Error('No questions match these filters. Try loosening them.')
      }
      setQuestions(data.questions)
      setIndex(0)
      setSelectedChoiceId(null)
      setFeedback(null)
      setHistory([])
      setPhase('answering')
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to load quiz.')
      setPhase('error')
    }
  }

  const handleSelect = async (choiceId) => {
    if (phase !== 'answering') return
    setSelectedChoiceId(choiceId)
    try {
      const data = await submitAnswer(questions[index].id, choiceId)
      setFeedback(data)
      setHistory((h) => [
        ...h,
        { question: questions[index], pickedChoiceId: choiceId, feedback: data },
      ])
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

  const resetToSetup = () => {
    setPhase('setup')
    setError(null)
  }

  if (phase === 'setup') {
    return <QuizSetup onStart={startQuiz} initial={lastConfig} />
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
          onClick={resetToSetup}
          className="bg-slate-900 hover:bg-slate-700 text-white px-4 py-2 rounded-lg"
        >
          Back to setup
        </button>
      </div>
    )
  }

  if (phase === 'done') {
    return (
      <ReviewScreen
        items={history}
        score={score}
        total={questions.length}
        onRestart={resetToSetup}
      />
    )
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
