import { useEffect, useReducer, useRef } from 'react'
import {
  apiErrorMessage,
  fetchDailyChallenge,
  fetchQuizSet,
  gradeAnswers,
  submitAnswer,
} from './api'
import {
  appendAttempt,
  clearActiveExam,
  loadActiveExam,
  loadAdaptivePlan,
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
import { MAX_RESPONSE_MS, validConfidence } from './confidence'
import { validDateKey } from './daily'
import { EXAM_SECONDS_PER_QUESTION, PCEP_30_02_PRESET, validPcep30_02Set } from './exam'

function emptyState(lastConfig = null, resumableExam = null) {
  return {
    phase: 'setup',
    questions: [],
    index: 0,
    selectedChoiceId: null,
    confidence: null,
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
          confidences: event.exam.confidences ?? {},
          responseMs: event.exam.responseMs ?? {},
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
    case 'set-confidence':
      return state.phase === 'answering' &&
        (event.confidence === null || validConfidence(event.confidence))
        ? { ...state, confidence: event.confidence }
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
            confidence: null,
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
      return emptyState('config' in event ? event.config : state.lastConfig)
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
  const questionStartedAt = useRef(0)

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
  useEffect(() => {
    if (state.phase === 'answering') questionStartedAt.current = Date.now()
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
    const isDaily = config.source === 'daily'
    if (!config.source) saveSettings(config)
    dispatch({ type: 'loading', config })
    try {
      const data = isDaily
        ? await fetchDailyChallenge({ signal: controller.signal })
        : await fetchQuizSet(config, { signal: controller.signal })
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
      if (
        config.preset === PCEP_30_02_PRESET.value &&
        !validPcep30_02Set(data, questions)
      )
        throw new Error('The server returned an invalid full mock. Please retry.')
      if (
        isDaily &&
        (!validDateKey(data.date) ||
          data.count !== questions.length ||
          questions.length > 5)
      )
        throw new Error('The server returned an invalid daily challenge. Please retry.')
      const sessionConfig = isDaily
        ? { ...config, count: questions.length, challengeDate: data.date }
        : config
      const now = Date.now()
      const examProgress =
        sessionConfig.mode === 'exam'
          ? {
              index: 0,
              answers: {},
              flagged: [],
              confidences: {},
              responseMs: {},
              deadline: now + questions.length * EXAM_SECONDS_PER_QUESTION * 1000,
            }
          : null
      if (examProgress)
        saveActiveExam({
          config: sessionConfig,
          questions,
          startedAt: now,
          ...examProgress,
        })
      dispatch({ type: 'start', config: sessionConfig, questions, now, examProgress })
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
    const confidence = state.confidence
    const responseMs = Math.min(
      MAX_RESPONSE_MS,
      Math.max(0, Date.now() - questionStartedAt.current)
    )
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
        item: {
          question,
          pickedChoiceId: choiceId,
          feedback: data,
          confidence,
          responseMs,
        },
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
    const byConfidence = items.reduce((groups, item) => {
      if (!validConfidence(item.confidence)) return groups
      const group = (groups[item.confidence] ??= { score: 0, total: 0 })
      group.total++
      if (item.feedback?.is_correct) group.score++
      return groups
    }, {})
    const timedItems = items.filter(
      (item) =>
        Number.isSafeInteger(item.responseMs) &&
        item.responseMs >= 0 &&
        item.responseMs <= MAX_RESPONSE_MS
    )
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
      ...(Object.keys(byConfidence).length ? { byConfidence } : {}),
      ...(validDateKey(state.lastConfig?.challengeDate)
        ? { challengeDate: state.lastConfig.challengeDate }
        : {}),
      ...(timedItems.length
        ? {
            responseMsTotal: timedItems.reduce((sum, item) => sum + item.responseMs, 0),
            responseCount: timedItems.length,
          }
        : {}),
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

  const handleExamSubmit = async (answers, metadata = {}) => {
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
        const confidence = metadata.confidences?.[question.id]
        const responseMs = metadata.responseMs?.[question.id]
        return {
          question,
          pickedChoiceId: feedback.choice_id,
          feedback,
          confidence: validConfidence(confidence) ? confidence : null,
          responseMs:
            Number.isSafeInteger(responseMs) &&
            responseMs >= 0 &&
            responseMs <= MAX_RESPONSE_MS
              ? responseMs
              : null,
        }
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
    dispatch({ type: 'reset', config: loadSettings() })
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
    const ids = [
      ...new Set(
        list
          .slice(0, 100)
          .map((item) =>
            Number.isSafeInteger(item) ? item : (item?.id ?? item?.questionId)
          )
          .filter((id) => Number.isSafeInteger(id) && id > 0)
      ),
    ]
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
  const startAdaptiveQuiz = () => startSavedDrill(loadAdaptivePlan().ids, 'adaptive')
  const startSearchDrill = (ids) => startSavedDrill(ids, 'search')
  return {
    ...state,
    startQuiz,
    handleSelect,
    handleConfidence: (confidence) => dispatch({ type: 'set-confidence', confidence }),
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
    startDailyChallenge: () =>
      startQuiz({
        mode: 'practice',
        module: '',
        difficulty: '',
        count: 5,
        source: 'daily',
      }),
    startModuleDrill: (module) =>
      startQuiz({ mode: 'practice', module, difficulty: '', count: 20 }),
  }
}
