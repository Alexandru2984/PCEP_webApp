import { useEffect, useState } from 'react'
import { fetchQuizSet, submitAnswer, gradeAnswers, fetchQuestionStats } from '../api'
import { loadSettings, saveSettings, appendAttempt, loadHistory } from '../storage'
import { formatElapsed } from '../format'
import { getStreakStats } from '../streak'
import QuestionCard from './QuestionCard'
import FeedbackBox from './FeedbackBox'
import ReviewScreen from './ReviewScreen'
import QuizSetup from './QuizSetup'
import ExamView from './ExamView'
import Dashboard from './Dashboard'

export default function QuizContainer() {
  const [phase, setPhase] = useState('setup')
  const [questions, setQuestions] = useState([])
  const [index, setIndex] = useState(0)
  const [selectedChoiceId, setSelectedChoiceId] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [history, setHistory] = useState([])
  const [lastConfig, setLastConfig] = useState(loadSettings)
  const [startedAt, setStartedAt] = useState(0)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [view, setView] = useState('setup')
  const [questionStats, setQuestionStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(true)
  const [statsError, setStatsError] = useState(null)

  const score = history.filter((h) => h.feedback?.is_correct).length
  const streak = getStreakStats(history)

  const recordAttempt = (items, total, elapsed) => {
    const correct = items.filter((i) => i.feedback?.is_correct).length
    const attemptStreak = getStreakStats(items)
    appendAttempt({
      date: new Date().toISOString(),
      mode: lastConfig?.mode ?? 'practice',
      module: lastConfig?.module ?? '',
      difficulty: lastConfig?.difficulty ?? '',
      score: correct,
      total,
      pct: total > 0 ? Math.round((correct / total) * 100) : 0,
      elapsedMs: elapsed,
      bestStreak: attemptStreak.best,
    })
  }

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
      setStartedAt(Date.now())
      setPhase(config.mode === 'exam' ? 'exam' : 'answering')
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

  const finish = (items, total) => {
    const elapsed = Date.now() - startedAt
    setElapsedMs(elapsed)
    recordAttempt(items, total, elapsed)
    setHistory(items)
    setPhase('done')
  }

  const handleNext = () => {
    if (index + 1 >= questions.length) {
      finish(history, questions.length)
      return
    }
    setIndex((i) => i + 1)
    setSelectedChoiceId(null)
    setFeedback(null)
    setPhase('answering')
  }

  const handleExamSubmit = async (answers) => {
    setSubmitting(true)
    setError(null)
    const payload = questions.map((q) => ({
      question_id: q.id,
      choice_id: answers[q.id] ?? null,
    }))
    try {
      const data = await gradeAnswers(payload)
      const byQuestion = new Map(data.results.map((r) => [r.question_id, r]))
      const items = questions.map((q) => {
        const r = byQuestion.get(q.id)
        return {
          question: q,
          pickedChoiceId: r?.choice_id ?? null,
          feedback: {
            is_correct: r?.is_correct ?? false,
            correct_choice_id: r?.correct_choice_id ?? null,
            explanation: r?.explanation ?? '',
          },
        }
      })
      finish(items, questions.length)
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to grade exam.')
      setPhase('error')
    } finally {
      setSubmitting(false)
    }
  }

  const resetToSetup = () => {
    setPhase('setup')
    setError(null)
  }

  useEffect(() => {
    let active = true

    const loadStats = async () => {
      setStatsLoading(true)
      setStatsError(null)
      try {
        const data = await fetchQuestionStats()
        if (!active) return
        setQuestionStats(data)
      } catch (e) {
        if (!active) return
        setStatsError(
          e?.response?.data?.detail || e?.message || 'Could not load question-bank stats.'
        )
      } finally {
        if (active) setStatsLoading(false)
      }
    }

    loadStats()
    return () => {
      active = false
    }
  }, [])

  // Keyboard shortcuts for practice mode: 1–4 / A–D to answer, Enter/→ to advance.
  useEffect(() => {
    if (phase !== 'answering' && phase !== 'reviewing') return
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      // Don't hijack digits/letters while the learner is typing in the code editor.
      const t = e.target
      if (t?.tagName === 'TEXTAREA' || t?.tagName === 'INPUT' || t?.isContentEditable)
        return
      if (phase === 'answering') {
        const choices = questions[index]?.choices ?? []
        const n = Number.parseInt(e.key, 10)
        const idx = Number.isNaN(n) ? 'abcd'.indexOf(e.key.toLowerCase()) : n - 1
        if (idx >= 0 && idx < choices.length) {
          e.preventDefault()
          handleSelect(choices[idx].id)
        }
      } else if (e.key === 'Enter' || e.key === 'ArrowRight') {
        e.preventDefault()
        handleNext()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, index, questions])

  if (phase === 'setup') {
    const attemptCount = loadHistory().length
    const tab = (active) =>
      `rounded-lg px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400 dark:focus:ring-slate-500 ${
        active
          ? 'bg-slate-900 text-white dark:bg-sky-600'
          : 'bg-white text-slate-600 hover:bg-slate-100 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
      }`
    return (
      <div>
        <div className="mb-4 flex gap-2" role="tablist" aria-label="Quiz workspace">
          <button
            type="button"
            role="tab"
            aria-selected={view === 'setup'}
            onClick={() => setView('setup')}
            className={tab(view === 'setup')}
          >
            New quiz
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === 'progress'}
            onClick={() => setView('progress')}
            className={tab(view === 'progress')}
          >
            Progress{attemptCount > 0 ? ` (${attemptCount})` : ''}
          </button>
        </div>
        {view === 'progress' ? (
          <Dashboard />
        ) : (
          <QuizSetup
            onStart={startQuiz}
            initial={lastConfig}
            stats={questionStats}
            statsLoading={statsLoading}
            statsError={statsError}
          />
        )}
      </div>
    )
  }

  if (phase === 'loading') {
    return (
      <div
        className="rounded-xl border border-slate-200 bg-white p-8 text-center dark:border-slate-700 dark:bg-slate-800"
        role="status"
        aria-live="polite"
      >
        <p className="text-slate-600 dark:text-slate-400">Loading quiz…</p>
      </div>
    )
  }

  if (phase === 'error') {
    return (
      <div
        className="rounded-xl border border-red-200 bg-white p-6 dark:border-red-900 dark:bg-slate-800"
        role="alert"
      >
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

  if (phase === 'exam') {
    return (
      <ExamView
        questions={questions}
        onSubmit={handleExamSubmit}
        onQuit={resetToSetup}
        submitting={submitting}
      />
    )
  }

  if (phase === 'done') {
    return (
      <ReviewScreen
        items={history}
        score={score}
        total={questions.length}
        onRestart={resetToSetup}
        elapsedLabel={elapsedMs ? `in ${formatElapsed(elapsedMs)}` : ''}
        streakStats={getStreakStats(history)}
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
      <div className="mb-3 flex items-center justify-between gap-3 text-sm">
        <div className="flex flex-wrap items-center gap-2 text-slate-500 dark:text-slate-400">
          <span>
            Score:{' '}
            <span className="font-semibold text-slate-700 dark:text-slate-200">
              {score}
            </span>
          </span>
          <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
            Streak {streak.current}
          </span>
          {streak.best > 1 && (
            <span className="rounded-full border border-green-200 bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700 dark:border-green-800 dark:bg-green-950/40 dark:text-green-300">
              Best {streak.best}
            </span>
          )}
        </div>
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
        runnable
      />
      {feedback ? (
        <FeedbackBox
          feedback={feedback}
          onNext={handleNext}
          isLast={index + 1 >= questions.length}
        />
      ) : (
        <p className="mt-3 text-center text-xs text-slate-500 dark:text-slate-400">
          Tip: press <kbd className="font-mono">1</kbd>–<kbd className="font-mono">4</kbd>{' '}
          to answer, <kbd className="font-mono">Enter</kbd> for next
        </p>
      )}
    </div>
  )
}
