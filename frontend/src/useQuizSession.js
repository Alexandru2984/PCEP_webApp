import { useEffect, useReducer, useRef } from 'react'
import { apiErrorMessage, fetchQuizSet, gradeAnswers, submitAnswer } from './api'
import {
  appendAttempt,
  clearActiveExam,
  loadActiveExam,
  loadBookmarks,
  loadDueReviews,
  loadMistakes,
  loadSettings,
  saveActiveExam,
  saveSettings,
  updateMistakes,
  updateStudyProgress,
} from './storage'
import { publicQuestion, validateFeedback } from './questionData'
import { getStreakStats } from './streak'

const EXAM_SECONDS_PER_QUESTION = 80

function emptyState(lastConfig = null, resumableExam = null) {
  return {
    phase: 'setup',
    questions: [],
    index: 0,
    selectedChoiceId: null,
    feedback: null,
    history: [],
    lastConfig,
    resumableExam,
    examProgress: null,
    startedAt: 0,
    elapsedMs: 0,
    submitting: false,
    error: null,
  }
}
function initialState() {
  return emptyState(loadSettings(), loadActiveExam())
}

export function sessionReducer(state, event) {
  switch (event.type) {
    case 'loading':
      return { ...emptyState(event.config), phase: 'loading' }
    case 'start':
      return {
        ...emptyState(event.config),
        questions: event.questions,
        startedAt: event.now,
        examProgress: event.examProgress,
        phase:
          event.config.mode === 'exam'
            ? 'exam'
            : event.config.mode === 'flashcards'
              ? 'flashcards'
              : 'answering',
      }
    case 'resume':
      return {
        ...emptyState(event.exam.config),
        phase: 'exam',
        questions: event.exam.questions,
        startedAt: event.exam.startedAt,
        examProgress: {
          index: event.exam.index,
          answers: event.exam.answers,
          flagged: event.exam.flagged,
          deadline: event.exam.deadline,
        },
      }
    case 'discard-resume':
      return { ...state, resumableExam: null }
    case 'load-error':
      return { ...state, phase: 'error', error: event.error }
    case 'answering':
      return state.phase === 'answering'
        ? {
            ...state,
            phase: 'submitting-answer',
            selectedChoiceId: event.choiceId,
            error: null,
          }
        : state
    case 'feedback':
      return state.phase === 'submitting-answer'
        ? {
            ...state,
            phase: 'reviewing',
            feedback: event.feedback,
            history: [...state.history, event.item],
          }
        : state
    case 'answer-error':
      return { ...state, phase: 'answering', error: event.error }
    case 'next':
      return state.phase === 'reviewing'
        ? {
            ...state,
            phase: 'answering',
            index: state.index + 1,
            feedback: null,
            selectedChoiceId: null,
          }
        : state
    case 'grading':
      return { ...state, submitting: true, error: null }
    case 'grade-error':
      return { ...state, submitting: false, error: event.error }
    case 'done':
      return {
        ...state,
        phase: 'done',
        submitting: false,
        history: event.items,
        elapsedMs: event.elapsed,
        error: null,
      }
    case 'reset':
      return emptyState(state.lastConfig)
    default:
      return state
  }
}

export default function useQuizSession() {
  const [state, dispatch] = useReducer(sessionReducer, undefined, initialState)
  const request = useRef(null)
  const mounted = useRef(true)
  const finished = useRef(false)
  const advancing = useRef(false)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      request.current?.abort()
      request.current = null
    }
  }, [])
  useEffect(() => {
    advancing.current = false
  }, [state.index, state.phase])

  const begin = () => {
    if (request.current) return null
    const controller = new AbortController()
    request.current = controller
    return controller
  }
  const current = (controller) =>
    mounted.current && request.current === controller && !controller.signal.aborted
  const release = (controller) => {
    if (request.current === controller) request.current = null
  }

  const startQuiz = async (config) => {
    const controller = begin()
    if (!controller) return
    finished.current = false
    clearActiveExam()
    saveSettings(config)
    dispatch({ type: 'loading', config })
    try {
      const data = await fetchQuizSet(config, { signal: controller.signal })
      if (!current(controller)) return
      if (!Array.isArray(data?.questions) || !data.questions.length)
        throw new Error('No questions match these filters. Try loosening them.')
      const questions = data.questions.map(publicQuestion)
      if (
        questions.length > 100 ||
        questions.some((q) => !q) ||
        new Set(questions.map((q) => q.id)).size !== questions.length
      )
        throw new Error('The server returned invalid questions. Please retry.')
      const now = Date.now()
      const examProgress =
        config.mode === 'exam'
          ? {
              index: 0,
              answers: {},
              flagged: [],
              deadline: now + questions.length * EXAM_SECONDS_PER_QUESTION * 1000,
            }
          : null
      if (examProgress)
        saveActiveExam({
          config,
          questions,
          startedAt: now,
          ...examProgress,
        })
      dispatch({ type: 'start', config, questions, now, examProgress })
    } catch (error) {
      if (current(controller))
        dispatch({ type: 'load-error', error: apiErrorMessage(error) })
    } finally {
      release(controller)
    }
  }

  const handleSelect = async (choiceId) => {
    if (state.phase !== 'answering') return
    const question = state.questions[state.index]
    if (!question.choices.some((c) => c.id === choiceId)) return
    const controller = begin()
    if (!controller) return
    dispatch({ type: 'answering', choiceId })
    try {
      const data = await submitAnswer(question.id, choiceId, {
        signal: controller.signal,
      })
      if (!current(controller)) return
      validateFeedback(data, question)
      dispatch({
        type: 'feedback',
        feedback: data,
        item: { question, pickedChoiceId: choiceId, feedback: data },
      })
    } catch (error) {
      if (current(controller))
        dispatch({ type: 'answer-error', error: apiErrorMessage(error) })
    } finally {
      release(controller)
    }
  }

  const finish = (items, total) => {
    if (finished.current || !mounted.current) return
    finished.current = true
    if (state.lastConfig?.mode === 'exam') clearActiveExam()
    const elapsed = Date.now() - state.startedAt
    const score = items.filter((i) => i.feedback?.is_correct).length
    const breakdown = (key) =>
      items.reduce((groups, item) => {
        const group = (groups[item.question[key]] ??= { score: 0, total: 0 })
        group.total++
        if (item.feedback?.is_correct) group.score++
        return groups
      }, {})
    appendAttempt({
      date: new Date().toISOString(),
      mode: state.lastConfig?.mode ?? 'practice',
      module: state.lastConfig?.module ?? '',
      difficulty: state.lastConfig?.difficulty ?? '',
      score,
      total,
      pct: total ? Math.round((score / total) * 100) : 0,
      elapsedMs: elapsed,
      bestStreak: getStreakStats(items).best,
      byModule: breakdown('module'),
      byDifficulty: breakdown('difficulty'),
    })
    updateMistakes(items)
    updateStudyProgress(items)
    dispatch({ type: 'done', items, elapsed })
  }

  const handleNext = () => {
    if (state.phase !== 'reviewing' || advancing.current) return
    advancing.current = true
    if (state.index + 1 >= state.questions.length)
      finish(state.history, state.questions.length)
    else dispatch({ type: 'next' })
  }

  const handleExamSubmit = async (answers) => {
    if (state.phase !== 'exam') return false
    const controller = begin()
    if (!controller) return false
    dispatch({ type: 'grading' })
    const payload = state.questions.map((q) => ({
      question_id: q.id,
      choice_id: answers[q.id] ?? null,
    }))
    try {
      const data = await gradeAnswers(payload, { signal: controller.signal })
      if (!current(controller)) return false
      if (
        !Array.isArray(data?.results) ||
        data.results.length !== payload.length ||
        new Set(data.results.map((r) => r.question_id)).size !== payload.length
      )
        throw new Error(
          'The server returned incomplete grading. Your answers are kept; please retry.'
        )
      const byQuestion = new Map(data.results.map((r) => [r.question_id, r]))
      const items = state.questions.map((question, i) => {
        const feedback = validateFeedback(byQuestion.get(question.id), question)
        if (feedback.choice_id !== payload[i].choice_id)
          throw new Error(
            'The server returned invalid grading. Your answers are kept; please retry.'
          )
        return { question, pickedChoiceId: feedback.choice_id, feedback }
      })
      finish(items, state.questions.length)
      return true
    } catch (error) {
      if (current(controller))
        dispatch({ type: 'grade-error', error: apiErrorMessage(error) })
      return false
    } finally {
      release(controller)
    }
  }

  const resetToSetup = () => {
    request.current?.abort()
    request.current = null
    clearActiveExam()
    dispatch({ type: 'reset' })
  }
  const resumeExam = () => {
    const exam = loadActiveExam()
    if (!exam) {
      dispatch({ type: 'discard-resume' })
      return
    }
    finished.current = false
    dispatch({ type: 'resume', exam })
  }
  const discardSavedExam = () => {
    clearActiveExam()
    dispatch({ type: 'discard-resume' })
  }
  const saveExamProgress = (progress) => {
    if (state.phase !== 'exam') return false
    return saveActiveExam({
      config: state.lastConfig,
      questions: state.questions,
      startedAt: state.startedAt,
      ...progress,
    })
  }
  const startSavedDrill = (list, source) => {
    if (!list.length) return
    // Fetch current public options so admin edits cannot leave a drill with stale choice IDs.
    const ids = list
      .slice(0, 100)
      .map((item) => item.id ?? item.questionId)
      .filter((id) => Number.isSafeInteger(id) && id > 0)
    if (!ids.length) return
    return startQuiz({
      mode: 'practice',
      module: '',
      difficulty: '',
      count: Math.min(50, ids.length),
      source,
      ids,
    })
  }
  const startMistakesQuiz = () => startSavedDrill(loadMistakes(), 'mistakes')
  const startBookmarksQuiz = () => startSavedDrill(loadBookmarks(), 'bookmarks')
  const startDueReviewsQuiz = () =>
    startSavedDrill(loadDueReviews().slice(0, 20), 'due-reviews')
  return {
    ...state,
    startQuiz,
    handleSelect,
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
    startModuleDrill: (module) =>
      startQuiz({ mode: 'practice', module, difficulty: '', count: 20 }),
  }
}
