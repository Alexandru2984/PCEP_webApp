import { useEffect, useReducer, useRef } from 'react'
import {
  apiErrorMessage,
  fetchDailyChallenge,
  fetchQuizSet,
  gradeAnswers,
  submitAnswer,
} from './api'
import {
  clearActiveExam,
  clearActiveFlashcards,
  clearActivePractice,
  loadActiveExam,
  loadActiveFlashcards,
  loadActivePractice,
  loadAdaptivePlan,
  loadBookmarks,
  loadDueReviews,
  loadMistakes,
  loadSettings,
  recordCompletedSession,
  saveActiveExam,
  saveActiveFlashcards,
  saveActivePractice,
  saveSettings,
} from './storage'
import { publicApiQuestion, validateFeedback } from './questionData'
import { getStreakStats } from './streak'
import { MAX_RESPONSE_MS, validConfidence } from './confidence'
import { validDateKey } from './daily'
import { EXAM_SECONDS_PER_QUESTION, PCEP_30_02_PRESET, validPcep30_02Set } from './exam'

function emptyState(
  lastConfig = null,
  resumableExam = null,
  resumablePractice = null,
  resumableFlashcards = null
) {
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
    resumablePractice,
    resumableFlashcards,
    examProgress: null,
    flashcardProgress: null,
    practiceSessionId: null,
    startedAt: 0,
    elapsedMs: 0,
    submitting: false,
    error: null,
  }
}
function initialState() {
  return emptyState(
    loadSettings(),
    loadActiveExam(),
    loadActivePractice(),
    loadActiveFlashcards()
  )
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
        practiceSessionId: event.practiceSessionId,
        flashcardProgress: event.flashcardProgress,
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
          sessionId: event.exam.sessionId,
        },
      }
    case 'resume-practice': {
      const currentItem = event.practice.history[event.practice.index]
      return {
        ...emptyState(event.practice.config),
        phase: event.practice.phase,
        questions: event.practice.questions,
        index: event.practice.index,
        selectedChoiceId: currentItem?.pickedChoiceId ?? null,
        confidence:
          event.practice.phase === 'answering'
            ? event.practice.confidence
            : (currentItem?.confidence ?? null),
        feedback: currentItem?.feedback ?? null,
        history: event.practice.history,
        startedAt: event.practice.startedAt,
        practiceSessionId: event.practice.sessionId,
      }
    }
    case 'resume-flashcards':
      return {
        ...emptyState(event.flashcards.config),
        phase: 'flashcards',
        questions: event.flashcards.questions,
        startedAt: event.flashcards.startedAt,
        flashcardProgress: {
          index: event.flashcards.index,
          items: event.flashcards.items,
          revealed: event.flashcards.revealed,
          sessionId: event.flashcards.sessionId,
        },
      }
    case 'discard-resume':
      return { ...state, resumableExam: null }
    case 'discard-practice-resume':
      return { ...state, resumablePractice: null }
    case 'discard-flashcards-resume':
      return { ...state, resumableFlashcards: null }
    case 'storage-conflict':
      return emptyState(state.lastConfig, event.exam)
    case 'practice-storage-conflict':
      return emptyState(state.lastConfig, state.resumableExam, event.practice)
    case 'flashcards-storage-conflict':
      return emptyState(
        state.lastConfig,
        state.resumableExam,
        state.resumablePractice,
        event.flashcards
      )
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
      return emptyState(
        'config' in event ? event.config : state.lastConfig,
        event.exam ?? null,
        event.practice ?? null,
        event.flashcards ?? null
      )
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
  useEffect(() => {
    const sessionId = state.examProgress?.sessionId
    if (state.phase !== 'exam' || !sessionId) return
    const stopStaleExam = () => {
      const currentExam = loadActiveExam()
      if (currentExam?.sessionId === sessionId) return
      request.current?.abort()
      request.current = null
      dispatch({ type: 'storage-conflict', exam: currentExam })
    }
    const changedInAnotherTab = (event) => {
      if (event.key !== 'pcep.activeExam') return
      const currentExam = loadActiveExam()
      if (currentExam?.sessionId === sessionId) return
      window.dispatchEvent(new CustomEvent('pcep-active-exam-conflict'))
    }
    window.addEventListener('storage', changedInAnotherTab)
    window.addEventListener('pcep-active-exam-conflict', stopStaleExam)
    return () => {
      window.removeEventListener('storage', changedInAnotherTab)
      window.removeEventListener('pcep-active-exam-conflict', stopStaleExam)
    }
  }, [state.examProgress?.sessionId, state.phase])
  useEffect(() => {
    const sessionId = state.practiceSessionId
    if (
      !['answering', 'reviewing', 'submitting-answer'].includes(state.phase) ||
      !sessionId
    )
      return
    const stopStalePractice = () => {
      const currentPractice = loadActivePractice()
      if (currentPractice?.sessionId === sessionId) return
      request.current?.abort()
      request.current = null
      dispatch({ type: 'practice-storage-conflict', practice: currentPractice })
    }
    const changedInAnotherTab = (event) => {
      if (event.key !== 'pcep.activePractice') return
      const currentPractice = loadActivePractice()
      if (currentPractice?.sessionId === sessionId) return
      window.dispatchEvent(new CustomEvent('pcep-active-practice-conflict'))
    }
    window.addEventListener('storage', changedInAnotherTab)
    window.addEventListener('pcep-active-practice-conflict', stopStalePractice)
    return () => {
      window.removeEventListener('storage', changedInAnotherTab)
      window.removeEventListener('pcep-active-practice-conflict', stopStalePractice)
    }
  }, [state.phase, state.practiceSessionId])
  useEffect(() => {
    const sessionId = state.flashcardProgress?.sessionId
    if (state.phase !== 'flashcards' || !sessionId) return
    const stopStaleFlashcards = () => {
      const currentFlashcards = loadActiveFlashcards()
      if (currentFlashcards?.sessionId === sessionId) return
      request.current?.abort()
      request.current = null
      dispatch({
        type: 'flashcards-storage-conflict',
        flashcards: currentFlashcards,
      })
    }
    const changedInAnotherTab = (event) => {
      if (event.key !== 'pcep.activeFlashcards') return
      const currentFlashcards = loadActiveFlashcards()
      if (currentFlashcards?.sessionId === sessionId) return
      window.dispatchEvent(new CustomEvent('pcep-active-flashcards-conflict'))
    }
    window.addEventListener('storage', changedInAnotherTab)
    window.addEventListener('pcep-active-flashcards-conflict', stopStaleFlashcards)
    return () => {
      window.removeEventListener('storage', changedInAnotherTab)
      window.removeEventListener('pcep-active-flashcards-conflict', stopStaleFlashcards)
    }
  }, [state.flashcardProgress?.sessionId, state.phase])
  useEffect(() => {
    if (
      !['answering', 'reviewing'].includes(state.phase) ||
      state.lastConfig?.mode !== 'practice' ||
      !state.practiceSessionId
    )
      return
    const saved = saveActivePractice({
      config: state.lastConfig,
      questions: state.questions,
      startedAt: state.startedAt,
      index: state.index,
      phase: state.phase,
      history: state.history,
      confidence: state.phase === 'answering' ? state.confidence : null,
      sessionId: state.practiceSessionId,
    })
    const currentPractice = loadActivePractice()
    if (
      !saved &&
      currentPractice &&
      currentPractice.sessionId !== state.practiceSessionId
    )
      window.dispatchEvent(new CustomEvent('pcep-active-practice-conflict'))
  }, [
    state.confidence,
    state.history,
    state.index,
    state.lastConfig,
    state.phase,
    state.practiceSessionId,
    state.questions,
    state.startedAt,
  ])

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
      const questions = data.questions.map(publicApiQuestion)
      if (
        questions.length > 100 ||
        questions.some((q) => !q) ||
        new Set(questions.map((q) => q.id)).size !== questions.length ||
        questions.some(
          (question) =>
            (config.module && question.module !== config.module) ||
            (config.objective && question.objective !== config.objective) ||
            (config.difficulty && question.difficulty !== config.difficulty)
        )
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
      const sessionConfig = {
        ...config,
        count: questions.length,
        ...(isDaily ? { challengeDate: data.date } : {}),
      }
      const now = Date.now()
      const examProgress =
        sessionConfig.mode === 'exam'
          ? {
              index: 0,
              answers: {},
              flagged: [],
              confidences: {},
              responseMs: {},
              sessionId: crypto.randomUUID(),
              deadline: now + questions.length * EXAM_SECONDS_PER_QUESTION * 1000,
            }
          : null
      const practiceSessionId =
        sessionConfig.mode === 'practice' ? crypto.randomUUID() : null
      const flashcardProgress =
        sessionConfig.mode === 'flashcards'
          ? {
              index: 0,
              items: [],
              revealed: null,
              sessionId: crypto.randomUUID(),
            }
          : null
      if (examProgress) {
        const saved = saveActiveExam({
          config: sessionConfig,
          questions,
          startedAt: now,
          ...examProgress,
        })
        const currentExam = loadActiveExam()
        if (!saved && currentExam && currentExam.sessionId !== examProgress.sessionId) {
          dispatch({ type: 'storage-conflict', exam: currentExam })
          return
        }
      }
      if (flashcardProgress) {
        const saved = saveActiveFlashcards({
          config: sessionConfig,
          questions,
          startedAt: now,
          ...flashcardProgress,
        })
        const currentFlashcards = loadActiveFlashcards()
        if (
          !saved &&
          currentFlashcards &&
          currentFlashcards.sessionId !== flashcardProgress.sessionId
        ) {
          dispatch({
            type: 'flashcards-storage-conflict',
            flashcards: currentFlashcards,
          })
          return
        }
      }
      dispatch({
        type: 'start',
        config: sessionConfig,
        questions,
        now,
        examProgress,
        practiceSessionId,
        flashcardProgress,
      })
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
    if (finished.current || !mounted.current) return false
    if (state.lastConfig?.mode === 'exam') {
      const currentExam = loadActiveExam()
      if (currentExam && currentExam.sessionId !== state.examProgress?.sessionId) {
        window.dispatchEvent(new CustomEvent('pcep-active-exam-conflict'))
        return false
      }
    }
    if (state.lastConfig?.mode === 'practice') {
      const currentPractice = loadActivePractice()
      if (currentPractice && currentPractice.sessionId !== state.practiceSessionId) {
        window.dispatchEvent(new CustomEvent('pcep-active-practice-conflict'))
        return false
      }
    }
    if (state.lastConfig?.mode === 'flashcards') {
      const currentFlashcards = loadActiveFlashcards()
      if (
        currentFlashcards &&
        currentFlashcards.sessionId !== state.flashcardProgress?.sessionId
      ) {
        window.dispatchEvent(new CustomEvent('pcep-active-flashcards-conflict'))
        return false
      }
    }
    finished.current = true
    const completedAt = Date.now()
    const elapsed = completedAt - state.startedAt
    const score = items.filter((i) => i.feedback?.is_correct).length
    const breakdown = (key) =>
      items.reduce((groups, item) => {
        const value = item.question[key]
        if (!value) return groups
        const group = (groups[value] ??= { score: 0, total: 0 })
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
    const saved = recordCompletedSession(
      {
        date: new Date(completedAt).toISOString(),
        mode: state.lastConfig?.mode ?? 'practice',
        module: state.lastConfig?.module ?? '',
        objective: state.lastConfig?.objective ?? '',
        difficulty: state.lastConfig?.difficulty ?? '',
        score,
        total,
        pct: total ? Math.round((score / total) * 100) : 0,
        elapsedMs: elapsed,
        bestStreak: getStreakStats(items).best,
        byModule: breakdown('module'),
        byDifficulty: breakdown('difficulty'),
        byObjective: breakdown('objective'),
        ...(Object.keys(byConfidence).length ? { byConfidence } : {}),
        ...(validDateKey(state.lastConfig?.challengeDate)
          ? { challengeDate: state.lastConfig.challengeDate }
          : {}),
        ...(state.lastConfig?.preset === PCEP_30_02_PRESET.value
          ? { preset: state.lastConfig.preset }
          : {}),
        ...(timedItems.length
          ? {
              responseMsTotal: timedItems.reduce((sum, item) => sum + item.responseMs, 0),
              responseCount: timedItems.length,
            }
          : {}),
      },
      items,
      completedAt
    )
    if (saved && state.lastConfig?.mode === 'exam') {
      const sessionId = state.examProgress?.sessionId
      if (!clearActiveExam(sessionId)) {
        const currentExam = loadActiveExam()
        if (currentExam && currentExam.sessionId !== sessionId) return false
      }
    }
    if (saved && state.lastConfig?.mode === 'practice') {
      const sessionId = state.practiceSessionId
      if (!clearActivePractice(sessionId)) {
        const currentPractice = loadActivePractice()
        if (currentPractice && currentPractice.sessionId !== sessionId) return false
      }
    }
    if (saved && state.lastConfig?.mode === 'flashcards') {
      const sessionId = state.flashcardProgress?.sessionId
      if (!clearActiveFlashcards(sessionId)) {
        const currentFlashcards = loadActiveFlashcards()
        if (currentFlashcards && currentFlashcards.sessionId !== sessionId) return false
      }
    }
    dispatch({ type: 'done', items, elapsed })
    return true
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
      return finish(items, state.questions.length)
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
    if (state.phase === 'exam') clearActiveExam(state.examProgress?.sessionId)
    if (state.practiceSessionId) clearActivePractice(state.practiceSessionId)
    if (state.flashcardProgress?.sessionId)
      clearActiveFlashcards(state.flashcardProgress.sessionId)
    dispatch({
      type: 'reset',
      config: loadSettings(),
      exam: loadActiveExam(),
      practice: loadActivePractice(),
      flashcards: loadActiveFlashcards(),
    })
  }
  const resumeExam = () => {
    const exam = loadActiveExam()
    if (!exam) {
      dispatch({ type: 'discard-resume' })
      return
    }
    const claimed = { ...exam, sessionId: crypto.randomUUID() }
    if (!saveActiveExam(claimed, exam.sessionId)) {
      dispatch({ type: 'storage-conflict', exam: loadActiveExam() })
      return
    }
    finished.current = false
    dispatch({ type: 'resume', exam: claimed })
  }
  const discardSavedExam = () => {
    if (clearActiveExam(state.resumableExam?.sessionId))
      dispatch({ type: 'discard-resume' })
    else dispatch({ type: 'storage-conflict', exam: loadActiveExam() })
  }
  const resumePractice = () => {
    const practice = loadActivePractice()
    if (!practice) {
      dispatch({ type: 'discard-practice-resume' })
      return
    }
    const claimed = { ...practice, sessionId: crypto.randomUUID() }
    if (!saveActivePractice(claimed, practice.sessionId)) {
      dispatch({
        type: 'practice-storage-conflict',
        practice: loadActivePractice(),
      })
      return
    }
    finished.current = false
    dispatch({ type: 'resume-practice', practice: claimed })
  }
  const discardSavedPractice = () => {
    if (clearActivePractice(state.resumablePractice?.sessionId))
      dispatch({ type: 'discard-practice-resume' })
    else
      dispatch({
        type: 'practice-storage-conflict',
        practice: loadActivePractice(),
      })
  }
  const resumeFlashcards = () => {
    const flashcards = loadActiveFlashcards()
    if (!flashcards) {
      dispatch({ type: 'discard-flashcards-resume' })
      return
    }
    const claimed = { ...flashcards, sessionId: crypto.randomUUID() }
    if (!saveActiveFlashcards(claimed, flashcards.sessionId)) {
      dispatch({
        type: 'flashcards-storage-conflict',
        flashcards: loadActiveFlashcards(),
      })
      return
    }
    finished.current = false
    dispatch({ type: 'resume-flashcards', flashcards: claimed })
  }
  const discardSavedFlashcards = () => {
    if (clearActiveFlashcards(state.resumableFlashcards?.sessionId))
      dispatch({ type: 'discard-flashcards-resume' })
    else
      dispatch({
        type: 'flashcards-storage-conflict',
        flashcards: loadActiveFlashcards(),
      })
  }
  const saveExamProgress = (progress) => {
    if (state.phase !== 'exam') return false
    return saveActiveExam({
      config: state.lastConfig,
      questions: state.questions,
      startedAt: state.startedAt,
      sessionId: state.examProgress?.sessionId,
      ...progress,
    })
  }
  const saveFlashcardProgress = (progress) => {
    if (state.phase !== 'flashcards') return false
    return saveActiveFlashcards({
      ...progress,
      config: state.lastConfig,
      questions: state.questions,
      startedAt: state.startedAt,
      sessionId: state.flashcardProgress?.sessionId,
    })
  }
  const startSavedDrill = (list, source, mode = 'practice') => {
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
      mode,
      module: '',
      objective: '',
      difficulty: '',
      count: Math.min(50, ids.length),
      source,
      ids,
    })
  }
  const startMistakesQuiz = () => startSavedDrill(loadMistakes(), 'mistakes')
  const startMistakesFlashcards = () =>
    startSavedDrill(loadMistakes(), 'mistakes', 'flashcards')
  const startBookmarksQuiz = () => startSavedDrill(loadBookmarks(), 'bookmarks')
  const startBookmarksFlashcards = () =>
    startSavedDrill(loadBookmarks(), 'bookmarks', 'flashcards')
  const startDueReviewsQuiz = () =>
    startSavedDrill(loadDueReviews().slice(0, 20), 'due-reviews')
  const startDueReviewsFlashcards = () =>
    startSavedDrill(loadDueReviews().slice(0, 20), 'due-reviews', 'flashcards')
  const startAdaptiveQuiz = () => startSavedDrill(loadAdaptivePlan().ids, 'adaptive')
  const startSearchDrill = (ids, mode = 'practice') =>
    startSavedDrill(ids, 'search', mode === 'flashcards' ? 'flashcards' : 'practice')
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
    resumePractice,
    discardSavedPractice,
    resumeFlashcards,
    discardSavedFlashcards,
    saveExamProgress,
    saveFlashcardProgress,
    startMistakesQuiz,
    startMistakesFlashcards,
    startBookmarksQuiz,
    startBookmarksFlashcards,
    startDueReviewsQuiz,
    startDueReviewsFlashcards,
    startAdaptiveQuiz,
    startSearchDrill,
    startDailyChallenge: () =>
      startQuiz({
        mode: 'practice',
        module: '',
        objective: '',
        difficulty: '',
        count: 5,
        source: 'daily',
      }),
    startModuleDrill: (module) =>
      startQuiz({ mode: 'practice', module, objective: '', difficulty: '', count: 20 }),
    startObjectiveDrill: (objective) =>
      startQuiz({ mode: 'practice', module: '', objective, difficulty: '', count: 20 }),
  }
}
