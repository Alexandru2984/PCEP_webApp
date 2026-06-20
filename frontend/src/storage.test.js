import { describe, it, expect, beforeEach } from 'vitest'
import {
  loadHistory,
  appendAttempt,
  clearHistory,
  saveSettings,
  loadSettings,
} from './storage'

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
