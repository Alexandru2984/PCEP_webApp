import { useState } from 'react'
import { fetchQuizSet, submitAnswer } from '../api'
import { loadSettings, saveSettings } from '../storage'
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
  const [lastConfig, setLastConfig] = useState(loadSettings)
  const [error, setError] = useState(null)

  const score = history.filter((h) => h.feedback?.is_correct).length

  const startQuiz = async (config) => {
    setPhase('loading')
    setError(null)
    setLastConfig(config)
    saveSettings(config)
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
      <div className="rounded-xl border border-slate-200 bg-white p-8 text-center dark:border-slate-700 dark:bg-slate-800">
        <p className="text-slate-600 dark:text-slate-400">Loading quiz…</p>
      </div>
    )
  }

  if (phase === 'error') {
    return (
      <div className="rounded-xl border border-red-200 bg-white p-6 dark:border-red-900 dark:bg-slate-800">
        <p className="mb-2 font-semibold text-red-700 dark:text-red-400">
          Something went wrong.
        </p>
        <p className="mb-4 text-slate-700 dark:text-slate-300">{error}</p>
        <button
          type="button"
          onClick={resetToSetup}
          className="rounded-lg bg-slate-900 px-4 py-2 text-white hover:bg-slate-700 dark:bg-sky-600 dark:hover:bg-sky-500"
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
  const progress = Math.round((index / questions.length) * 100)
  return (
    <div>
      <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        <div
          className="h-full rounded-full bg-slate-900 transition-all dark:bg-sky-500"
          style={{ width: `${progress}%` }}
        />
      </div>
      <div className="mb-3 flex items-center justify-between text-sm">
        <span className="text-slate-500 dark:text-slate-400">
          Score:{' '}
          <span className="font-semibold text-slate-700 dark:text-slate-200">
            {score}
          </span>
        </span>
        <button
          type="button"
          onClick={resetToSetup}
          className="text-slate-500 underline underline-offset-2 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
        >
          Quit
        </button>
      </div>

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
