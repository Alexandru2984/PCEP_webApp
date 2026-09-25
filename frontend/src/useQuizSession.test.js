import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchDailyChallenge, fetchQuizSet, gradeAnswers, submitAnswer } from './api'
import {
  loadActiveExam,
  loadHistory,
  loadStudyProgress,
  saveActiveExam,
  updateStudyProgress,
} from './storage'
import useQuizSession from './useQuizSession'

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
  difficulty: 'easy',
  choices: [
    { id: 11, text: 'One' },
    { id: 12, text: 'Two' },
  ],
}
const feedback = {
  is_correct: true,
  correct_choice_id: 11,
  explanation: 'Why',
  correct_explanation: 'Why',
}
const config = { mode: 'practice', count: 10, module: '', difficulty: '' }
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
})
