import { useEffect, useState, lazy, Suspense } from 'react'
import { fetchQuestionStats, apiErrorMessage } from '../api'
import {
  loadAdaptivePlan,
  loadBookmarks,
  loadHistory,
  loadMistakes,
  loadStudySummary,
} from '../storage'
import useQuizSession from '../useQuizSession'
import { ignoreShortcut, nativeActivation } from '../shortcuts'
import { formatClock, formatElapsed } from '../format'
import { getStreakStats } from '../streak'
import { bucharestDateKey } from '../daily'
import QuestionCard from './QuestionCard'
import FeedbackBox from './FeedbackBox'
import QuizSetup from './QuizSetup'

// Loaded on demand: none of these are on the first-paint (setup) path, so they
// ship as separate chunks and stay out of the initial bundle.
const ReviewScreen = lazy(() => import('./ReviewScreen'))
const ExamView = lazy(() => import('./ExamView'))
const FlashcardView = lazy(() => import('./FlashcardView'))
const Dashboard = lazy(() => import('./Dashboard'))

function LoadingCard() {
  return (
    <div
      className="rounded-xl border border-slate-200 bg-white p-8 text-center dark:border-slate-700 dark:bg-slate-800"
      role="status"
      aria-live="polite"
    >
      <p className="text-slate-600 dark:text-slate-400">Loading…</p>
    </div>
  )
}

function SavedExamCard({ exam, onResume, onDiscard }) {
  const answered = Object.keys(exam.answers).length
  const [remaining] = useState(() =>
    Math.max(0, Math.ceil((exam.deadline - Date.now()) / 1000))
  )
  const expired = remaining === 0
  return (
    <section
      aria-labelledby="saved-exam-heading"
      className="rounded-xl border border-sky-300 bg-sky-50 p-5 shadow-sm dark:border-sky-800 dark:bg-sky-950/30"
    >
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-sky-700 dark:text-sky-300">
        Exam recovery
      </p>
      <h2 id="saved-exam-heading" className="text-xl font-semibold">
        Resume saved exam
      </h2>
      <p className="mt-2 text-slate-700 dark:text-slate-200">
        {answered}/{exam.questions.length} answered.{' '}
        {expired
          ? 'Time has expired; resume to grade the answers that were saved.'
          : `${formatClock(remaining)} remaining.`}
      </p>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
        This recovery copy stays in this browser and contains public questions and your
        selections, never the answer key.
      </p>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          onClick={onResume}
          className="rounded-lg bg-slate-900 px-4 py-2.5 font-medium text-white hover:bg-slate-700 dark:bg-sky-700 dark:hover:bg-sky-800"
        >
          Resume exam
        </button>
        <button
          type="button"
          onClick={onDiscard}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 font-medium text-slate-700 hover:border-slate-500 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
        >
          Discard and start new
        </button>
      </div>
    </section>
  )
}

export default function QuizContainer() {
  const {
    phase,
    questions,
    index,
    selectedChoiceId,
    confidence,
    feedback,
    history,
    lastConfig,
    elapsedMs,
    submitting,
    error,
    resumableExam,
    examProgress,
    startQuiz,
    handleSelect,
    handleConfidence,
    handleNext,
    handleExamSubmit,
    finish,
    resetToSetup,
    resumeExam,
    discardSavedExam,
    saveExamProgress,
    startMistakesQuiz,
    startBookmarksQuiz,
    startDueReviewsQuiz,
    startAdaptiveQuiz,
    startSearchDrill,
    startDailyChallenge,
    startModuleDrill,
  } = useQuizSession()
  const [view, setView] = useState('setup')
  const returnToSetup = () => {
    setView('setup')
    resetToSetup()
  }
  const [questionStats, setQuestionStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(true)
  const [statsError, setStatsError] = useState(null)
  const score = history.filter((h) => h.feedback?.is_correct).length
  const streak = getStreakStats(history)

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
        setStatsError(apiErrorMessage(e, 'Could not load question-bank stats.'))
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
      if (ignoreShortcut(e) || nativeActivation(e)) return
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
    if (resumableExam)
      return (
        <SavedExamCard
          exam={resumableExam}
          onResume={resumeExam}
          onDiscard={discardSavedExam}
        />
      )
    const attempts = loadHistory()
    const attemptCount = attempts.length
    const dailyCompletion = attempts.find(
      (attempt) => attempt.challengeDate === bucharestDateKey()
    )
    const tab = (active) =>
      `rounded-lg px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400 dark:focus:ring-slate-500 ${
        active
          ? 'bg-slate-900 text-white dark:bg-sky-700'
          : 'bg-white text-slate-600 hover:bg-slate-100 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
      }`
    return (
      <div>
        <nav className="mb-4 flex gap-2" aria-label="Quiz workspace">
          <button
            type="button"
            aria-pressed={view === 'setup'}
            onClick={() => setView('setup')}
            className={tab(view === 'setup')}
          >
            New quiz
          </button>
          <button
            type="button"
            aria-pressed={view === 'progress'}
            onClick={() => setView('progress')}
            className={tab(view === 'progress')}
          >
            Progress{attemptCount > 0 ? ` (${attemptCount})` : ''}
          </button>
        </nav>
        {view === 'progress' ? (
          <Suspense fallback={<LoadingCard />}>
            <Dashboard
              onDrill={startModuleDrill}
              onBookmarks={startBookmarksQuiz}
              onMistakes={startMistakesQuiz}
              onDueReviews={startDueReviewsQuiz}
              onAdaptivePractice={startAdaptiveQuiz}
            />
          </Suspense>
        ) : (
          <QuizSetup
            onStart={startQuiz}
            onPracticeMistakes={startMistakesQuiz}
            mistakesCount={loadMistakes().length}
            bookmarksCount={loadBookmarks().length}
            onPracticeBookmarks={startBookmarksQuiz}
            dueReviewCount={loadStudySummary().due}
            onPracticeDueReviews={startDueReviewsQuiz}
            adaptivePlan={loadAdaptivePlan()}
            onAdaptivePractice={startAdaptiveQuiz}
            onDailyChallenge={startDailyChallenge}
            dailyCompletion={dailyCompletion}
            onSearchDrill={startSearchDrill}
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
          onClick={returnToSetup}
          className="rounded-lg bg-slate-900 px-4 py-2 text-white hover:bg-slate-700 dark:bg-sky-700 dark:hover:bg-sky-800"
        >
          Back to setup
        </button>
      </div>
    )
  }

  if (phase === 'exam') {
    return (
      <Suspense fallback={<LoadingCard />}>
        <ExamView
          questions={questions}
          onSubmit={handleExamSubmit}
          onQuit={returnToSetup}
          onProgress={saveExamProgress}
          initialProgress={examProgress}
          submitting={submitting}
          error={error}
        />
      </Suspense>
    )
  }

  if (phase === 'flashcards') {
    return (
      <Suspense fallback={<LoadingCard />}>
        <FlashcardView
          questions={questions}
          onFinish={(items) => finish(items, questions.length)}
          onQuit={returnToSetup}
        />
      </Suspense>
    )
  }

  if (phase === 'done') {
    return (
      <Suspense fallback={<LoadingCard />}>
        <ReviewScreen
          items={history}
          score={score}
          total={questions.length}
          onRestart={returnToSetup}
          onDrillModule={startModuleDrill}
          elapsedLabel={elapsedMs ? `in ${formatElapsed(elapsedMs)}` : ''}
          streakStats={getStreakStats(history)}
          mode={lastConfig?.mode}
          challengeDate={lastConfig?.challengeDate}
        />
      </Suspense>
    )
  }

  const current = questions[index]
  const progress = Math.round((index / questions.length) * 100)
  return (
    <div>
      {error && (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200"
        >
          {error} Select an answer to retry.
        </p>
      )}
      {phase === 'submitting-answer' && (
        <p role="status" className="mb-3 text-sm text-slate-600 dark:text-slate-300">
          Checking your answer…
        </p>
      )}
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
          onClick={returnToSetup}
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
        confidence={confidence}
        onConfidenceChange={handleConfidence}
        feedback={feedback}
        disabled={phase !== 'answering'}
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
