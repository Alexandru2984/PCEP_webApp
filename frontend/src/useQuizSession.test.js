import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchDailyChallenge, fetchQuizSet, gradeAnswers, submitAnswer } from './api'
import {
  loadActiveExam,
  loadActiveFlashcards,
  loadActivePractice,
  loadHistory,
  loadStudyProgress,
  saveActiveExam,
  saveActiveFlashcards,
  saveActivePractice,
  toggleBookmark,
  updateMistakes,
  updateStudyProgress,
} from './storage'
import useQuizSession from './useQuizSession'
import { PCEP_30_02_PRESET } from './exam'

vi.mock('./api', async (original) => ({
  ...(await original()),
  fetchQuizSet: vi.fn(),
  fetchDailyChallenge: vi.fn(),
  gradeAnswers: vi.fn(),
  submitAnswer: vi.fn(),
}))
const question = {
  id: 1,
  text: 'Question?',
  code_snippet: '',
  module: 'module1',
  objective: '1.4',
  difficulty: 'easy',
  choices: [
    { id: 11, text: 'One' },
    { id: 12, text: 'Two' },
  ],
}
const secondQuestion = {
  ...question,
  id: 2,
  choices: [
    { id: 21, text: 'One' },
    { id: 22, text: 'Two' },
  ],
}
const feedback = {
  is_correct: true,
  correct_choice_id: 11,
  explanation: 'Why',
  correct_explanation: 'Why',
}
const config = { mode: 'practice', count: 10, module: '', difficulty: '' }
const fullMockQuestions = Object.entries(PCEP_30_02_PRESET.distribution).flatMap(
  ([module, count], moduleIndex) =>
    Array.from({ length: count }, (_, index) => {
      const id = (moduleIndex + 1) * 100 + index + 1
      return {
        ...question,
        id,
        module,
        objective: {
          module1: '1.4',
          module2: '2.1',
          module3: '3.1',
          module4: '4.1',
        }[module],
        choices: [
          { id: id * 10 + 1, text: 'One' },
          { id: id * 10 + 2, text: 'Two' },
        ],
      }
    })
)
const deferred = () => {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { promise, resolve }
}
beforeEach(() => {
  vi.clearAllMocks()
  fetchQuizSet.mockResolvedValue({ questions: [question] })
  fetchDailyChallenge.mockResolvedValue({
    date: '2026-09-24',
    count: 1,
    questions: [question],
  })
})
afterEach(() => vi.useRealTimers())

describe('quiz session requests', () => {
  it('starts the server-defined daily set and records its challenge date', async () => {
    submitAnswer.mockResolvedValue(feedback)
    const { result } = renderHook(useQuizSession)

    await act(async () => result.current.startDailyChallenge())
    expect(fetchDailyChallenge).toHaveBeenCalledOnce()
    expect(fetchQuizSet).not.toHaveBeenCalled()
    expect(result.current.lastConfig).toMatchObject({
      source: 'daily',
      challengeDate: '2026-09-24',
      count: 1,
    })
    await act(async () => result.current.handleSelect(11))
    act(() => result.current.handleNext())
    expect(loadHistory()[0]).toMatchObject({
      mode: 'practice',
      challengeDate: '2026-09-24',
      byObjective: { 1.4: { score: 1, total: 1 } },
    })
    act(() => result.current.resetToSetup())
    expect(result.current.lastConfig).toBeNull()
  })

  it('rejects malformed daily challenge metadata', async () => {
    fetchDailyChallenge.mockResolvedValueOnce({
      date: '2026-02-29',
      count: 1,
      questions: [question],
    })
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startDailyChallenge())
    expect(result.current.phase).toBe('error')
    expect(result.current.error).toMatch(/invalid daily challenge/i)
  })

  it('rejects a mislabeled or incomplete full-mock response', async () => {
    const { result } = renderHook(useQuizSession)
    await act(async () =>
      result.current.startQuiz({
        mode: 'exam',
        module: '',
        difficulty: '',
        count: 30,
        preset: 'pcep-30-02',
      })
    )
    expect(result.current.phase).toBe('error')
    expect(result.current.error).toMatch(/invalid full mock/i)
  })

  it('preserves a completed full mock in recovery and attempt history', async () => {
    fetchQuizSet.mockResolvedValueOnce({
      preset: PCEP_30_02_PRESET.value,
      count: PCEP_30_02_PRESET.count,
      questions: fullMockQuestions,
    })
    gradeAnswers.mockResolvedValueOnce({
      results: fullMockQuestions.map((item) => ({
        question_id: item.id,
        choice_id: null,
        is_correct: false,
        correct_choice_id: item.choices[0].id,
        explanation: '',
        correct_explanation: 'Why',
      })),
    })
    const fullConfig = {
      mode: 'exam',
      module: '',
      difficulty: '',
      count: 30,
      preset: 'pcep-30-02',
    }
    const { result } = renderHook(useQuizSession)

    await act(async () => result.current.startQuiz(fullConfig))
    expect(loadActiveExam()?.config.preset).toBe('pcep-30-02')
    await act(async () => result.current.handleExamSubmit({}))
    expect(result.current.phase).toBe('done')
    expect(loadHistory()[0]).toMatchObject({
      mode: 'exam',
      total: 30,
      preset: 'pcep-30-02',
    })
  })

  it('blocks duplicate starts and duplicate answer requests synchronously', async () => {
    const loading = deferred()
    fetchQuizSet.mockReturnValueOnce(loading.promise)
    const { result } = renderHook(useQuizSession)
    let start
    act(() => {
      start = result.current.startQuiz(config)
      result.current.startQuiz(config)
    })
    expect(fetchQuizSet).toHaveBeenCalledTimes(1)
    await act(async () => {
      loading.resolve({ questions: [question] })
      await start
    })
    const answer = deferred()
    submitAnswer.mockReturnValueOnce(answer.promise)
    let answering
    act(() => {
      answering = result.current.handleSelect(11)
      result.current.handleSelect(12)
    })
    expect(submitAnswer).toHaveBeenCalledTimes(1)
    expect(result.current.phase).toBe('submitting-answer')
    await act(async () => {
      answer.resolve(feedback)
      await answering
    })
    expect(result.current.history).toHaveLength(1)
    act(() => {
      result.current.handleNext()
      result.current.handleNext()
    })
    expect(result.current.phase).toBe('done')
    expect(loadHistory()).toHaveLength(1)
    expect(loadStudyProgress()).toMatchObject([
      { questionId: 1, attempts: 1, correct: 1, intervalDays: 1 },
    ])
  })

  it('still shows completed results when browser storage rejects the snapshot', async () => {
    submitAnswer.mockResolvedValue(feedback)
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startQuiz(config))
    await act(async () => result.current.handleSelect(11))
    const warning = vi.fn()
    window.addEventListener('pcep-storage-warning', warning)
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Quota', 'QuotaExceededError')
    })

    act(() => result.current.handleNext())
    expect(result.current.phase).toBe('done')
    expect(result.current.history).toHaveLength(1)
    expect(loadHistory()).toEqual([])
    expect(loadStudyProgress()).toEqual([])
    expect(warning).toHaveBeenCalledOnce()

    setItem.mockRestore()
    window.removeEventListener('pcep-storage-warning', warning)
  })

  it('keeps exam recovery until the completed snapshot is safely stored', async () => {
    gradeAnswers.mockResolvedValue({
      results: [{ ...feedback, question_id: 1, choice_id: 11 }],
    })
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startQuiz({ ...config, mode: 'exam' }))
    expect(loadActiveExam()).not.toBeNull()
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Quota', 'QuotaExceededError')
    })

    await act(async () => result.current.handleExamSubmit({ 1: 11 }))
    expect(result.current.phase).toBe('done')
    expect(loadHistory()).toEqual([])
    expect(loadActiveExam()).not.toBeNull()

    setItem.mockRestore()
  })

  it('cancels loading on reset and ignores stale responses', async () => {
    const loading = deferred()
    fetchQuizSet.mockReturnValueOnce(loading.promise)
    const { result } = renderHook(useQuizSession)
    let start
    act(() => {
      start = result.current.startQuiz(config)
    })
    const signal = fetchQuizSet.mock.calls[0][1].signal
    act(() => result.current.resetToSetup())
    expect(signal.aborted).toBe(true)
    await act(async () => {
      loading.resolve({ questions: [question] })
      await start
    })
    expect(result.current.phase).toBe('setup')
    expect(result.current.questions).toEqual([])
  })

  it('keeps practice question and history on a failed answer, then retries', async () => {
    submitAnswer
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce(feedback)
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startQuiz(config))
    await act(async () => result.current.handleSelect(11))
    expect(result.current.phase).toBe('answering')
    expect(result.current.questions).toHaveLength(1)
    expect(result.current.error).toMatch(/temporarily unavailable/)
    expect(result.current.history).toEqual([])
    await act(async () => result.current.handleSelect(11))
    expect(result.current.phase).toBe('reviewing')
  })

  it('recovers practice at the submitted feedback and completes it exactly once', async () => {
    fetchQuizSet.mockResolvedValueOnce({ questions: [question, secondQuestion] })
    submitAnswer
      .mockResolvedValueOnce(feedback)
      .mockResolvedValueOnce({ ...feedback, correct_choice_id: 21 })
    const first = renderHook(useQuizSession)

    await act(async () => first.result.current.startQuiz(config))
    act(() => first.result.current.handleConfidence('high'))
    await act(async () => first.result.current.handleSelect(11))
    expect(loadActivePractice()).toMatchObject({
      index: 0,
      phase: 'reviewing',
      history: [{ pickedChoiceId: 11, confidence: 'high' }],
    })
    first.unmount()

    const resumed = renderHook(useQuizSession)
    expect(resumed.result.current.resumablePractice).toMatchObject({
      index: 0,
      phase: 'reviewing',
    })
    act(() => resumed.result.current.resumePractice())
    expect(resumed.result.current.phase).toBe('reviewing')
    expect(resumed.result.current.feedback).toMatchObject({ correct_choice_id: 11 })
    act(() => resumed.result.current.handleNext())
    expect(resumed.result.current.index).toBe(1)
    await act(async () => resumed.result.current.handleSelect(21))
    act(() => resumed.result.current.handleNext())

    expect(resumed.result.current.phase).toBe('done')
    expect(loadActivePractice()).toBeNull()
    expect(loadHistory()).toHaveLength(1)
    expect(loadHistory()[0]).toMatchObject({ score: 2, total: 2 })
  })

  it('keeps future practice answer keys out of recovery and clears it on quit', async () => {
    fetchQuizSet.mockResolvedValueOnce({
      questions: [
        question,
        {
          ...secondQuestion,
          correct_choice_id: 21,
          choices: secondQuestion.choices.map((choice) => ({
            ...choice,
            is_correct: choice.id === 21,
            explanation: 'UNSUBMITTED_SECRET',
          })),
        },
      ],
    })
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startQuiz(config))

    const raw = localStorage.getItem('pcep.activePractice')
    expect(raw).not.toContain('UNSUBMITTED_SECRET')
    expect(raw).not.toContain('correct_choice_id')
    act(() => result.current.resetToSetup())
    expect(loadActivePractice()).toBeNull()
  })

  it('stops a stale practice tab after another tab claims its recovery copy', async () => {
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startQuiz(config))
    const firstOwner = loadActivePractice()
    const claimed = { ...firstOwner, sessionId: 'practice-in-another-tab' }
    expect(saveActivePractice(claimed, firstOwner.sessionId)).toBe(true)

    act(() =>
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'pcep.activePractice',
          newValue: localStorage.getItem('pcep.activePractice'),
        })
      )
    )

    expect(result.current.phase).toBe('setup')
    expect(result.current.resumablePractice).toMatchObject({
      sessionId: 'practice-in-another-tab',
    })
    expect(loadActivePractice().sessionId).toBe('practice-in-another-tab')
  })

  it('recovers revealed flashcards and completes the deck exactly once', async () => {
    fetchQuizSet.mockResolvedValueOnce({ questions: [question, secondQuestion] })
    const flashcardConfig = { ...config, mode: 'flashcards' }
    const firstItem = {
      question,
      pickedChoiceId: 11,
      feedback: { ...feedback, explanation: '' },
    }
    const secondItem = {
      question: secondQuestion,
      pickedChoiceId: null,
      feedback: {
        is_correct: false,
        correct_choice_id: 21,
        explanation: '',
        correct_explanation: 'Why',
      },
    }
    const first = renderHook(useQuizSession)

    await act(async () => first.result.current.startQuiz(flashcardConfig))
    expect(loadActiveFlashcards()).toMatchObject({
      index: 0,
      items: [],
      revealed: null,
    })
    act(() =>
      expect(
        first.result.current.saveFlashcardProgress({
          index: 1,
          items: [firstItem],
          revealed: {
            correct_choice_id: 21,
            correct_explanation: 'Why',
          },
        })
      ).toBe(true)
    )
    first.unmount()

    const resumed = renderHook(useQuizSession)
    expect(resumed.result.current.resumableFlashcards).toMatchObject({
      index: 1,
      items: [{ question: { id: 1 }, pickedChoiceId: 11 }],
      revealed: { correct_choice_id: 21 },
    })
    act(() => resumed.result.current.resumeFlashcards())
    expect(resumed.result.current.phase).toBe('flashcards')
    expect(resumed.result.current.flashcardProgress).toMatchObject({
      index: 1,
      revealed: { correct_choice_id: 21 },
    })
    act(() => resumed.result.current.finish([firstItem, secondItem], 2))

    expect(resumed.result.current.phase).toBe('done')
    expect(resumed.result.current.finish([firstItem, secondItem], 2)).toBe(false)
    expect(loadActiveFlashcards()).toBeNull()
    expect(loadHistory()).toHaveLength(1)
    expect(loadHistory()[0]).toMatchObject({ mode: 'flashcards', score: 1, total: 2 })
  })

  it('stops a stale flashcard tab after another tab claims its recovery copy', async () => {
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startQuiz({ ...config, mode: 'flashcards' }))
    const firstOwner = loadActiveFlashcards()
    const claimed = { ...firstOwner, sessionId: 'flashcards-in-another-tab' }
    expect(saveActiveFlashcards(claimed, firstOwner.sessionId)).toBe(true)

    act(() =>
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'pcep.activeFlashcards',
          newValue: localStorage.getItem('pcep.activeFlashcards'),
        })
      )
    )

    expect(result.current.phase).toBe('setup')
    expect(result.current.resumableFlashcards).toMatchObject({
      sessionId: 'flashcards-in-another-tab',
    })
    expect(result.current.saveFlashcardProgress({ index: 0 })).toBe(false)
    expect(loadActiveFlashcards().sessionId).toBe('flashcards-in-another-tab')
  })

  it('records optional confidence and time to answer without answer metadata', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-24T12:00:00Z'))
    submitAnswer.mockResolvedValue(feedback)
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startQuiz(config))
    act(() => result.current.handleConfidence('low'))
    await act(async () => vi.advanceTimersByTime(4200))
    await act(async () => result.current.handleSelect(11))
    expect(result.current.history[0]).toMatchObject({
      confidence: 'low',
      responseMs: 4200,
    })
    act(() => result.current.handleNext())
    expect(loadHistory()[0]).toMatchObject({
      byConfidence: { low: { score: 1, total: 1 } },
      responseMsTotal: 4200,
      responseCount: 1,
    })
    expect(JSON.stringify(loadHistory()[0])).not.toMatch(/correct_choice_id|explanation/)
  })

  it('keeps an exam mounted after grading failure and safely retries the same answers', async () => {
    gradeAnswers
      .mockRejectedValueOnce({
        response: { status: 429, headers: { 'retry-after': '12' } },
      })
      .mockResolvedValueOnce({
        results: [{ ...feedback, question_id: 1, choice_id: 11 }],
      })
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startQuiz({ ...config, mode: 'exam' }))
    await act(async () => result.current.handleExamSubmit({ 1: 11 }))
    expect(result.current.phase).toBe('exam')
    expect(result.current.submitting).toBe(false)
    expect(result.current.error).toMatch(/12 seconds/)
    expect(loadHistory()).toEqual([])
    await act(async () => result.current.handleExamSubmit({ 1: 11 }))
    expect(result.current.phase).toBe('done')
    expect(gradeAnswers.mock.calls[0][0]).toEqual(gradeAnswers.mock.calls[1][0])
    expect(loadHistory()).toHaveLength(1)
  })

  it('rejects incomplete grading without recording a score', async () => {
    gradeAnswers.mockResolvedValue({ results: [] })
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startQuiz({ ...config, mode: 'exam' }))
    await act(async () => result.current.handleExamSubmit({ 1: 11 }))
    expect(result.current.phase).toBe('exam')
    expect(result.current.error).toMatch(/incomplete grading/)
    expect(loadHistory()).toEqual([])
  })

  it('persists exam progress and clears it when the learner quits', async () => {
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startQuiz({ ...config, mode: 'exam' }))
    expect(loadActiveExam()).toMatchObject({
      index: 0,
      answers: {},
      flagged: [],
    })
    act(() =>
      result.current.saveExamProgress({
        index: 0,
        answers: { 1: 11 },
        flagged: [1],
        deadline: result.current.examProgress.deadline,
      })
    )
    expect(loadActiveExam()).toMatchObject({ answers: { 1: 11 }, flagged: [1] })
    act(() => result.current.resetToSetup())
    expect(result.current.phase).toBe('setup')
    expect(loadActiveExam()).toBeNull()
  })

  it('resumes a validated exam and removes recovery data after grading', async () => {
    const startedAt = Date.now()
    saveActiveExam({
      config: { ...config, mode: 'exam' },
      questions: [question],
      startedAt,
      deadline: startedAt + 80_000,
      index: 0,
      answers: { 1: 11 },
      flagged: [1],
    })
    gradeAnswers.mockResolvedValue({
      results: [{ ...feedback, question_id: 1, choice_id: 11 }],
    })
    const { result } = renderHook(useQuizSession)
    expect(result.current.resumableExam).toMatchObject({ answers: { 1: 11 } })
    act(() => result.current.resumeExam())
    expect(result.current.phase).toBe('exam')
    expect(result.current.examProgress).toMatchObject({
      answers: { 1: 11 },
      flagged: [1],
    })
    await act(async () => result.current.handleExamSubmit({ 1: 11 }))
    expect(result.current.phase).toBe('done')
    expect(loadActiveExam()).toBeNull()
  })

  it('stops a stale tab after another tab claims its active exam', async () => {
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startQuiz({ ...config, mode: 'exam' }))
    const firstOwner = loadActiveExam()
    const claimed = { ...firstOwner, sessionId: 'session-in-another-tab' }
    expect(saveActiveExam(claimed, firstOwner.sessionId)).toBe(true)

    act(() =>
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'pcep.activeExam',
          newValue: localStorage.getItem('pcep.activeExam'),
        })
      )
    )

    expect(result.current.phase).toBe('setup')
    expect(result.current.examProgress).toBeNull()
    expect(result.current.resumableExam).toMatchObject({
      sessionId: 'session-in-another-tab',
    })
    expect(result.current.saveExamProgress({ index: 0 })).toBe(false)
    expect(loadActiveExam().sessionId).toBe('session-in-another-tab')
  })

  it('aborts in-flight grading when another tab claims the exam', async () => {
    const grading = deferred()
    gradeAnswers.mockReturnValueOnce(grading.promise)
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startQuiz({ ...config, mode: 'exam' }))
    let submission
    act(() => {
      submission = result.current.handleExamSubmit({ 1: 11 })
    })
    const signal = gradeAnswers.mock.calls[0][1].signal
    const firstOwner = loadActiveExam()
    const claimed = { ...firstOwner, sessionId: 'grading-in-another-tab' }

    act(() => {
      localStorage.setItem(
        'pcep.activeExam',
        JSON.stringify({ version: 1, data: claimed })
      )
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'pcep.activeExam',
          newValue: localStorage.getItem('pcep.activeExam'),
        })
      )
    })
    expect(signal.aborted).toBe(true)
    expect(result.current.phase).toBe('setup')

    let submitted
    await act(async () => {
      grading.resolve({
        results: [{ ...feedback, question_id: 1, choice_id: 11 }],
      })
      submitted = await submission
    })
    expect(submitted).toBe(false)
    expect(result.current.phase).toBe('setup')
    expect(loadHistory()).toEqual([])
    expect(loadActiveExam().sessionId).toBe('grading-in-another-tab')
  })

  it('checks exam ownership before persisting grading when no event arrives', async () => {
    gradeAnswers.mockResolvedValue({
      results: [{ ...feedback, question_id: 1, choice_id: 11 }],
    })
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startQuiz({ ...config, mode: 'exam' }))
    const firstOwner = loadActiveExam()
    const claimed = { ...firstOwner, sessionId: 'silent-owner-change' }
    localStorage.setItem('pcep.activeExam', JSON.stringify({ version: 1, data: claimed }))

    let submitted
    await act(async () => {
      submitted = await result.current.handleExamSubmit({ 1: 11 })
    })

    expect(submitted).toBe(false)
    expect(result.current.phase).toBe('setup')
    expect(loadHistory()).toEqual([])
    expect(loadActiveExam().sessionId).toBe('silent-owner-change')
  })

  it('starts a due-review drill from current public question ids', async () => {
    updateStudyProgress(
      [{ question, feedback: { is_correct: false } }],
      Date.now() - 1000
    )
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startDueReviewsQuiz())
    expect(fetchQuizSet).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'practice',
        source: 'due-reviews',
        ids: [1],
        count: 1,
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(result.current.phase).toBe('answering')
  })

  it('starts due reviews as a recoverable flashcard deck', async () => {
    updateStudyProgress(
      [{ question, feedback: { is_correct: false } }],
      Date.now() - 1000
    )
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startDueReviewsFlashcards())
    expect(fetchQuizSet).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'flashcards',
        source: 'due-reviews',
        ids: [1],
        count: 1,
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(result.current.phase).toBe('flashcards')
    expect(loadActiveFlashcards()).toMatchObject({
      config: { mode: 'flashcards', count: 1 },
      questions: [{ id: 1 }],
      index: 0,
      revealed: null,
    })
  })

  it.each([
    [
      'mistakes',
      () => updateMistakes([{ question, feedback: { is_correct: false } }]),
      'startMistakesFlashcards',
    ],
    ['bookmarks', () => toggleBookmark(question), 'startBookmarksFlashcards'],
  ])(
    'starts saved %s as a recoverable flashcard deck',
    async (source, seed, startMethod) => {
      seed()
      const { result } = renderHook(useQuizSession)

      await act(async () => result.current[startMethod]())

      expect(fetchQuizSet).toHaveBeenCalledWith(
        expect.objectContaining({
          mode: 'flashcards',
          source,
          ids: [1],
          count: 1,
        }),
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      )
      expect(result.current.phase).toBe('flashcards')
      expect(loadActiveFlashcards()).toMatchObject({
        config: { mode: 'flashcards', count: 1 },
        questions: [{ id: 1 }],
        index: 0,
        revealed: null,
      })
    }
  )

  it('starts a transparent adaptive drill from the ranked local plan', async () => {
    updateStudyProgress(
      [{ question, feedback: { is_correct: false } }],
      Date.now() - 1000
    )
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startAdaptiveQuiz())
    expect(fetchQuizSet).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'practice',
        source: 'adaptive',
        ids: [1],
        count: 1,
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(result.current.phase).toBe('answering')
  })

  it('starts the ranked adaptive plan as recoverable flashcards', async () => {
    updateStudyProgress(
      [{ question, feedback: { is_correct: false } }],
      Date.now() - 1000
    )
    const { result } = renderHook(useQuizSession)

    await act(async () => result.current.startAdaptiveFlashcards())

    expect(fetchQuizSet).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'flashcards',
        source: 'adaptive',
        ids: [1],
        count: 1,
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(result.current.phase).toBe('flashcards')
    expect(loadActiveFlashcards()).toMatchObject({
      config: { mode: 'flashcards', count: 1 },
      questions: [{ id: 1 }],
      index: 0,
      revealed: null,
    })
  })

  it('starts a search drill from unique valid IDs', async () => {
    const { result } = renderHook(useQuizSession)
    await act(async () => result.current.startSearchDrill([1, 1, 0, null]))
    expect(fetchQuizSet).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'practice',
        source: 'search',
        ids: [1],
        count: 1,
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(result.current.phase).toBe('answering')
  })

  it('starts a selected search set as recoverable flashcards', async () => {
    const { result } = renderHook(useQuizSession)

    await act(async () => result.current.startSearchDrill([1], 'flashcards'))

    expect(fetchQuizSet).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'flashcards',
        source: 'search',
        ids: [1],
        count: 1,
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(result.current.phase).toBe('flashcards')
    expect(loadActiveFlashcards()).toMatchObject({
      config: { mode: 'flashcards', count: 1 },
      questions: [{ id: 1 }],
      index: 0,
      revealed: null,
    })
  })

  it.each([
    ['practice', 'answering'],
    ['flashcards', 'flashcards'],
  ])('starts the focused session review as %s in exact order', async (mode, phase) => {
    const { result } = renderHook(useQuizSession)

    await act(async () => result.current.startSessionReview([1, 1, 0], mode))

    expect(fetchQuizSet).toHaveBeenCalledWith(
      expect.objectContaining({
        mode,
        source: 'session-review',
        ids: [1],
        count: 1,
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(result.current.phase).toBe(phase)
    if (mode === 'practice')
      expect(loadActivePractice()).toMatchObject({
        config: { mode: 'practice', source: 'session-review', count: 1 },
        questions: [{ id: 1 }],
      })
  })

  it('starts an objective drill and rejects a response outside that scope', async () => {
    const scopedQuestion = {
      ...question,
      module: 'module3',
      objective: '3.1',
    }
    fetchQuizSet.mockResolvedValueOnce({ questions: [scopedQuestion] })
    const { result } = renderHook(useQuizSession)

    await act(async () => result.current.startObjectiveDrill('3.1'))
    expect(fetchQuizSet).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'practice',
        module: '',
        objective: '3.1',
        count: 20,
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(result.current.phase).toBe('answering')

    act(() => result.current.resetToSetup())
    fetchQuizSet.mockResolvedValueOnce({ questions: [question] })
    await act(async () => result.current.startObjectiveDrill('3.1'))
    expect(result.current.phase).toBe('error')
    expect(result.current.error).toMatch(/invalid questions/i)
  })
})
