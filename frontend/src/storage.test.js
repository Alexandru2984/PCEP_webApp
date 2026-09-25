import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  loadHistory,
  appendAttempt,
  clearHistory,
  saveSettings,
  loadSettings,
  loadMistakes,
  updateMistakes,
  clearMistakes,
  loadBookmarks,
  toggleBookmark,
  exportProgress,
  parseProgressBackup,
  importProgress,
  loadActiveExam,
  saveActiveExam,
  clearActiveExam,
  clearStudyProgress,
  loadDueReviews,
  loadAdaptivePlan,
  loadStudyProgress,
  loadStudySummary,
  updateStudyProgress,
  loadNotes,
  loadNote,
  saveNote,
  clearNotes,
} from './storage'

const question = (id) => ({
  id,
  text: 'Question?',
  code_snippet: '',
  module: 'module1',
  difficulty: 'easy',
  choices: [
    { id: id * 10 + 1, text: 'One' },
    { id: id * 10 + 2, text: 'Two' },
  ],
})
const attempt = (id, score = 0, extras = {}) => ({
  id: String(id),
  date: '2026-09-18T12:00:00.000Z',
  mode: 'practice',
  module: '',
  difficulty: '',
  score,
  total: 10,
  pct: score * 10,
  elapsedMs: 0,
  bestStreak: 0,
  ...extras,
})
const wrong = (id) => ({ question: question(id), feedback: { is_correct: false } })
const right = (id) => ({ question: question(id), feedback: { is_correct: true } })
const activeExam = (override = {}) => {
  const startedAt = Date.now()
  return {
    config: { mode: 'exam', module: '', difficulty: '', count: 10 },
    questions: [question(1), question(2)],
    startedAt,
    deadline: startedAt + 160_000,
    index: 1,
    answers: { 1: 11 },
    flagged: [2],
    ...override,
  }
}

// localStorage is reset by the global afterEach in src/test/setup.js, but reset
// here too so each case is independent regardless of run order.
beforeEach(() => localStorage.clear())

describe('history', () => {
  it('starts empty', () => {
    expect(loadHistory()).toEqual([])
  })

  it('prepends the newest attempt first', () => {
    appendAttempt(attempt('a'))
    appendAttempt(attempt('b'))
    expect(loadHistory().map((a) => a.id)).toEqual(['b', 'a'])
  })

  it('persists across reads (round-trips through localStorage)', () => {
    appendAttempt(attempt('a', 8))
    expect(loadHistory()).toEqual([attempt('a', 8)])
  })

  it('caps the history at 100 entries, dropping the oldest', () => {
    for (let i = 0; i < 120; i++) appendAttempt(attempt(i))
    const history = loadHistory()
    expect(history).toHaveLength(100)
    expect(history[0].id).toBe('119') // newest kept
    expect(history.at(-1).id).toBe('20') // oldest 20 dropped
  })

  it('clearHistory empties the store', () => {
    appendAttempt(attempt('a'))
    clearHistory()
    expect(loadHistory()).toEqual([])
  })

  it('falls back to [] when the stored value is corrupt', () => {
    localStorage.setItem('pcep.history', '{not valid json')
    expect(loadHistory()).toEqual([])
  })

  it('validates confidence summaries and measured response timing', () => {
    appendAttempt(
      attempt('calibrated', 7, {
        byConfidence: {
          low: { score: 2, total: 3 },
          high: { score: 5, total: 6 },
        },
        responseMsTotal: 90_000,
        responseCount: 9,
      })
    )
    expect(loadHistory()[0]).toMatchObject({
      byConfidence: {
        low: { score: 2, total: 3 },
        high: { score: 5, total: 6 },
      },
      responseMsTotal: 90_000,
      responseCount: 9,
    })
  })

  it('round-trips only valid daily challenge dates', () => {
    appendAttempt(attempt('daily', 8, { challengeDate: '2026-09-24' }))
    appendAttempt(attempt('invalid-date', 8, { challengeDate: '2026-02-29' }))
    expect(loadHistory()).toHaveLength(1)
    expect(loadHistory()[0].challengeDate).toBe('2026-09-24')
  })

  it('round-trips only the exact full-mock preset on matching exam attempts', () => {
    appendAttempt(
      attempt('mock', 24, {
        mode: 'exam',
        total: 30,
        pct: 80,
        preset: 'pcep-30-02',
      })
    )
    appendAttempt(attempt('wrong-mode', 8, { preset: 'pcep-30-02' }))
    appendAttempt(attempt('wrong-preset', 8, { mode: 'exam', preset: 'pcep-unknown' }))
    expect(loadHistory()).toHaveLength(1)
    expect(loadHistory()[0]).toMatchObject({
      mode: 'exam',
      total: 30,
      score: 24,
      preset: 'pcep-30-02',
    })
    expect(parseProgressBackup(exportProgress()).history[0].preset).toBe('pcep-30-02')
  })

  it.each([
    { byConfidence: { high: { score: 0, total: 1 } } },
    { responseMsTotal: 3 * 60 * 60 * 1000 + 1, responseCount: 1 },
  ])('rejects inconsistent confidence or response aggregates: %j', (extras) => {
    appendAttempt(attempt('invalid', 10, extras))
    expect(loadHistory()).toEqual([])
  })
})

describe('settings', () => {
  it('returns null when nothing is saved', () => {
    expect(loadSettings()).toBeNull()
  })

  it('round-trips a settings object', () => {
    const settings = {
      mode: 'practice',
      module: 'module2',
      difficulty: 'hard',
      count: 20,
    }
    saveSettings(settings)
    expect(loadSettings()).toEqual(settings)
  })

  it('preserves a valid full-mock marker for exam recovery', () => {
    const settings = {
      mode: 'exam',
      module: '',
      difficulty: '',
      count: 30,
      preset: 'pcep-30-02',
    }
    saveSettings(settings)
    expect(loadSettings()).toEqual(settings)
  })
})

describe('personal notes', () => {
  it('creates, updates and removes a trimmed note by question ID', () => {
    expect(
      saveNote(1, '  Remember operator precedence.  ', Date.UTC(2026, 8, 20))
    ).toEqual({
      questionId: 1,
      text: 'Remember operator precedence.',
      updatedAt: '2026-09-20T00:00:00.000Z',
    })
    expect(loadNote(1)?.text).toBe('Remember operator precedence.')
    saveNote(1, 'Updated', Date.UTC(2026, 8, 21))
    expect(loadNotes()).toHaveLength(1)
    expect(loadNote(1)?.text).toBe('Updated')
    expect(saveNote(1, '   ')).toBeNull()
    expect(loadNotes()).toEqual([])
  })

  it('bounds note size and total records', () => {
    expect(() => saveNote(1, 'x'.repeat(2001))).toThrow(/2,000/)
    for (let id = 1; id <= 105; id++) saveNote(id, `Note ${id}`, id)
    expect(loadNotes()).toHaveLength(100)
    expect(loadNote(105)?.text).toBe('Note 105')
    expect(loadNote(1)).toBeNull()
  })

  it('clears notes without clearing attempts', () => {
    appendAttempt(attempt('kept'))
    saveNote(1, 'Temporary')
    expect(clearNotes()).toBe(true)
    expect(loadNotes()).toEqual([])
    expect(loadHistory()).toHaveLength(1)
  })
})

describe('active exam recovery', () => {
  it('round-trips only public questions, selections and navigation state', () => {
    const unsafe = activeExam({
      questions: [
        {
          ...question(1),
          correct_choice_id: 11,
          choices: question(1).choices.map((choice) => ({
            ...choice,
            is_correct: true,
            explanation: 'SECRET',
          })),
        },
        question(2),
      ],
    })
    expect(saveActiveExam(unsafe)).toBe(true)
    const raw = localStorage.getItem('pcep.activeExam')
    expect(raw).not.toContain('SECRET')
    expect(raw).not.toContain('is_correct')
    expect(raw).not.toContain('correct_choice_id')
    expect(loadActiveExam()).toEqual({
      ...unsafe,
      config: { mode: 'exam', module: '', difficulty: '', count: 10 },
      questions: [question(1), question(2)],
    })
  })

  it('round-trips bounded confidence and response-time recovery data', () => {
    const exam = activeExam({
      confidences: { 1: 'low', 2: 'high' },
      responseMs: { 1: 12_000, 2: 8_000 },
    })
    expect(saveActiveExam(exam)).toBe(true)
    expect(loadActiveExam()).toMatchObject({
      confidences: { 1: 'low', 2: 'high' },
      responseMs: { 1: 12_000, 2: 8_000 },
    })
  })

  it.each([
    { answers: { 1: 999 } },
    { flagged: [2, 2] },
    { questions: [question(1), question(1)] },
    { correct_choice_id: 11 },
    { confidences: { 1: 'certain' } },
    { confidences: { 999: 'low' } },
    { responseMs: { 1: -1 } },
    { responseMs: { 999: 1000 } },
  ])('rejects malformed recovery data: %j', (override) => {
    expect(saveActiveExam(activeExam(override))).toBe(false)
    expect(loadActiveExam()).toBeNull()
  })

  it('expires abandoned recovery data one day after its deadline', () => {
    const deadline = Date.now() - 24 * 60 * 60 * 1000 - 1
    localStorage.setItem(
      'pcep.activeExam',
      JSON.stringify({
        version: 1,
        data: activeExam({ startedAt: deadline - 160_000, deadline }),
      })
    )
    expect(loadActiveExam()).toBeNull()
    expect(localStorage.getItem('pcep.activeExam')).toBeNull()
  })

  it('clears a saved exam without changing progress history', () => {
    appendAttempt(attempt('kept'))
    saveActiveExam(activeExam())
    expect(clearActiveExam()).toBe(true)
    expect(loadActiveExam()).toBeNull()
    expect(loadHistory()).toEqual([attempt('kept')])
  })
})

describe('mistakes', () => {
  it('starts empty', () => {
    expect(loadMistakes()).toEqual([])
  })

  it('records missed (and skipped) questions, newest first', () => {
    updateMistakes([wrong(1), wrong(2)])
    expect(loadMistakes().map((q) => q.id)).toEqual([2, 1])
  })

  it('drops a question once it is answered correctly', () => {
    updateMistakes([wrong(1), wrong(2)])
    updateMistakes([right(1)])
    expect(loadMistakes().map((q) => q.id)).toEqual([2])
  })

  it('dedupes by id and moves a re-missed question to the front', () => {
    updateMistakes([wrong(1), wrong(2)])
    updateMistakes([wrong(1)])
    expect(loadMistakes().map((q) => q.id)).toEqual([1, 2])
  })

  it('caps the store at 100, keeping the newest misses', () => {
    updateMistakes(Array.from({ length: 120 }, (_, i) => wrong(i + 1)))
    const ids = loadMistakes().map((q) => q.id)
    expect(ids).toHaveLength(100)
    expect(ids[0]).toBe(120) // newest kept
    expect(ids).toContain(21)
    expect(ids).not.toContain(20) // oldest 20 dropped
  })

  it('ignores items without a question id', () => {
    updateMistakes([{ feedback: { is_correct: false } }, wrong(5)])
    expect(loadMistakes().map((q) => q.id)).toEqual([5])
  })

  it('clearMistakes empties the store', () => {
    updateMistakes([wrong(1)])
    clearMistakes()
    expect(loadMistakes()).toEqual([])
  })

  it('preserves recency of untouched mistakes across updates', () => {
    updateMistakes([wrong(1), wrong(2), wrong(3)])
    updateMistakes([wrong(4)])
    expect(loadMistakes().map((q) => q.id)).toEqual([4, 3, 2, 1])
    updateMistakes([right(4)])
    expect(loadMistakes().map((q) => q.id)).toEqual([3, 2, 1])
  })
})

describe('study progress', () => {
  it('persists a bounded review schedule without choices or answer keys', () => {
    const now = Date.UTC(2026, 8, 20, 12)
    updateStudyProgress([right(1), wrong(2)], now)
    expect(loadStudyProgress()).toHaveLength(2)
    expect(loadDueReviews(now).map((record) => record.questionId)).toEqual([2])
    expect(loadStudySummary(now)).toMatchObject({ tracked: 2, due: 1 })
    const raw = localStorage.getItem('pcep.progress')
    expect(raw).not.toContain('choice')
    expect(raw).not.toContain('is_correct')
    expect(raw).not.toContain('explanation')
  })

  it('clears only the review schedule', () => {
    appendAttempt(attempt('kept'))
    updateStudyProgress([wrong(1)])
    expect(clearStudyProgress()).toBe(true)
    expect(loadStudyProgress()).toEqual([])
    expect(loadHistory()).toHaveLength(1)
  })

  it('builds an adaptive queue from validated local progress', () => {
    updateStudyProgress([right(1), wrong(2)], Date.now() - 1000)
    updateMistakes([wrong(2)])
    expect(loadAdaptivePlan().ids).toEqual([2, 1])
    expect(loadAdaptivePlan().signals).toMatchObject({ due: 1, mistakes: 1 })
  })
})

describe('schema migration and portability', () => {
  it.each([null, {}, 'text', 3])('ignores invalid legacy shapes: %j', (value) => {
    localStorage.setItem('pcep.history', JSON.stringify(value))
    localStorage.setItem('pcep.mistakes', JSON.stringify(value))
    expect(loadHistory()).toEqual([])
    expect(loadMistakes()).toEqual([])
  })

  it('preserves valid legacy records and migrates on the next successful write', () => {
    localStorage.setItem('pcep.history', JSON.stringify([attempt('legacy')]))
    localStorage.setItem('pcep.mistakes', JSON.stringify([question(1)]))
    toggleBookmark(question(2))
    expect(loadHistory()).toEqual([attempt('legacy')])
    expect(loadMistakes()).toEqual([question(1)])
    expect(JSON.parse(localStorage.getItem('pcep.progress')).version).toBe(1)
    expect(localStorage.getItem('pcep.history')).toBeNull()
  })

  it('strips answer metadata from saved questions and backups', () => {
    const q = {
      ...question(1),
      correct_choice_id: 11,
      choices: question(1).choices.map((c) => ({
        ...c,
        is_correct: true,
        explanation: 'SECRET',
      })),
    }
    toggleBookmark(q)
    const backup = exportProgress()
    expect(backup).not.toContain('SECRET')
    expect(backup).not.toContain('is_correct')
    expect(loadBookmarks()).toEqual([question(1)])
  })

  it('merges and deduplicates a valid backup without losing existing progress', () => {
    appendAttempt(attempt('existing'))
    toggleBookmark(question(1))
    updateStudyProgress([wrong(1)], Date.UTC(2026, 8, 20))
    const backup = parseProgressBackup(exportProgress())
    expect(backup.study).toHaveLength(1)
    backup.history.push(attempt('imported'))
    importProgress(backup)
    importProgress(backup)
    expect(loadHistory()).toHaveLength(2)
    expect(loadBookmarks()).toHaveLength(1)
    expect(loadStudyProgress()).toHaveLength(1)
  })

  it('exports notes and keeps the newest note when backups merge', () => {
    saveNote(1, 'Local is newer', Date.UTC(2026, 8, 22))
    const exported = parseProgressBackup(exportProgress())
    expect(exported.notes).toEqual([
      {
        questionId: 1,
        text: 'Local is newer',
        updatedAt: '2026-09-22T00:00:00.000Z',
      },
    ])
    importProgress({
      history: [],
      mistakes: [],
      bookmarks: [],
      study: [],
      notes: [
        {
          questionId: 1,
          text: 'Imported is older',
          updatedAt: '2026-09-21T00:00:00.000Z',
        },
      ],
    })
    expect(loadNote(1)?.text).toBe('Local is newer')
  })

  it('accepts version 2 backups without inventing notes', () => {
    const backup = parseProgressBackup(
      JSON.stringify({
        type: 'pcep-progress',
        version: 2,
        history: [],
        mistakes: [],
        bookmarks: [],
        study: [],
      })
    )
    expect(backup.notes).toEqual([])
  })

  it('rejects duplicate or malformed notes in version 3 backups', () => {
    const base = {
      type: 'pcep-progress',
      version: 3,
      history: [],
      mistakes: [],
      bookmarks: [],
      study: [],
    }
    expect(() =>
      parseProgressBackup(
        JSON.stringify({
          ...base,
          notes: [
            { questionId: 1, text: 'A', updatedAt: '2026-09-20T00:00:00Z' },
            { questionId: 1, text: 'B', updatedAt: '2026-09-21T00:00:00Z' },
          ],
        })
      )
    ).toThrow(/duplicate note/)
    expect(() =>
      parseProgressBackup(
        JSON.stringify({
          ...base,
          notes: [{ questionId: 1, text: 'x'.repeat(2001), updatedAt: 'bad' }],
        })
      )
    ).toThrow(/invalid or duplicate note/)
  })

  it('imports legacy version 1 backups with an empty review schedule', () => {
    const backup = parseProgressBackup(
      JSON.stringify({
        type: 'pcep-progress',
        version: 1,
        history: [],
        mistakes: [],
        bookmarks: [],
      })
    )
    expect(backup.study).toEqual([])
  })

  it.each([{ version: 2 }, { history: {} }, { mistakes: [{ id: 1 }] }, { extra: true }])(
    'rejects invalid backups: %j',
    (override) => {
      const backup = {
        type: 'pcep-progress',
        version: 1,
        history: [],
        mistakes: [],
        bookmarks: [],
        ...override,
      }
      expect(() => parseProgressBackup(JSON.stringify(backup))).toThrow()
    }
  )

  it('rejects answer metadata in imported questions', () => {
    const backup = {
      type: 'pcep-progress',
      version: 1,
      history: [],
      mistakes: [],
      bookmarks: [{ ...question(1), is_correct: true }],
    }
    expect(() => parseProgressBackup(JSON.stringify(backup))).toThrow(/answer metadata/)
  })

  it('preserves existing progress when an import exceeds storage quota', () => {
    appendAttempt(attempt('existing'))
    const before = localStorage.getItem('pcep.progress')
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Quota', 'QuotaExceededError')
    })
    expect(() =>
      importProgress({ history: [attempt('new')], mistakes: [], bookmarks: [] })
    ).toThrow(/Existing progress was kept/)
    expect(localStorage.getItem('pcep.progress')).toBe(before)
    spy.mockRestore()
  })
})
