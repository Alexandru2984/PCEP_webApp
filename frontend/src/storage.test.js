import { describe, it, expect, beforeEach } from 'vitest'
import {
  loadHistory,
  appendAttempt,
  clearHistory,
  saveSettings,
  loadSettings,
  loadMistakes,
  updateMistakes,
  clearMistakes,
} from './storage'

const wrong = (id) => ({ question: { id }, feedback: { is_correct: false } })
const right = (id) => ({ question: { id }, feedback: { is_correct: true } })

// localStorage is reset by the global afterEach in src/test/setup.js, but reset
// here too so each case is independent regardless of run order.
beforeEach(() => localStorage.clear())

describe('history', () => {
  it('starts empty', () => {
    expect(loadHistory()).toEqual([])
  })

  it('prepends the newest attempt first', () => {
    appendAttempt({ id: 'a' })
    appendAttempt({ id: 'b' })
    expect(loadHistory().map((a) => a.id)).toEqual(['b', 'a'])
  })

  it('persists across reads (round-trips through localStorage)', () => {
    appendAttempt({ id: 'a', pct: 80 })
    expect(loadHistory()).toEqual([{ id: 'a', pct: 80 }])
  })

  it('caps the history at 100 entries, dropping the oldest', () => {
    for (let i = 0; i < 120; i++) appendAttempt({ id: i })
    const history = loadHistory()
    expect(history).toHaveLength(100)
    expect(history[0].id).toBe(119) // newest kept
    expect(history.at(-1).id).toBe(20) // oldest 20 dropped
  })

  it('clearHistory empties the store', () => {
    appendAttempt({ id: 'a' })
    clearHistory()
    expect(loadHistory()).toEqual([])
  })

  it('falls back to [] when the stored value is corrupt', () => {
    localStorage.setItem('pcep.history', '{not valid json')
    expect(loadHistory()).toEqual([])
  })
})

describe('settings', () => {
  it('returns null when nothing is saved', () => {
    expect(loadSettings()).toBeNull()
  })

  it('round-trips a settings object', () => {
    const settings = { module: 'module2', difficulty: 'hard', count: 20 }
    saveSettings(settings)
    expect(loadSettings()).toEqual(settings)
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
    updateMistakes(Array.from({ length: 120 }, (_, i) => wrong(i)))
    const ids = loadMistakes().map((q) => q.id)
    expect(ids).toHaveLength(100)
    expect(ids[0]).toBe(119) // newest kept
    expect(ids).toContain(20)
    expect(ids).not.toContain(19) // oldest 20 dropped
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
})
