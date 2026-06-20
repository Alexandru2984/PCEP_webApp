import { describe, it, expect } from 'vitest'
import { getScopeTotal } from './questionStats'

const stats = {
  total: 217,
  by_module: { module1: 52, module2: 52 },
  by_difficulty: { easy: 77, medium: 88, hard: 52 },
  matrix: {
    module1: { easy: 20, medium: 19, hard: 13 },
  },
}

describe('getScopeTotal', () => {
  it('returns 0 when stats are missing', () => {
    expect(getScopeTotal(null, '', '')).toBe(0)
    expect(getScopeTotal(undefined, 'module1', 'hard')).toBe(0)
  })

  it('returns the grand total when nothing is selected', () => {
    expect(getScopeTotal(stats, '', '')).toBe(217)
  })

  it('scopes by module alone', () => {
    expect(getScopeTotal(stats, 'module1', '')).toBe(52)
  })

  it('scopes by difficulty alone', () => {
    expect(getScopeTotal(stats, '', 'hard')).toBe(52)
  })

  it('uses the module/difficulty matrix when both are selected', () => {
    expect(getScopeTotal(stats, 'module1', 'hard')).toBe(13)
  })

  it('falls back to 0 for an out-of-range combination', () => {
    expect(getScopeTotal(stats, 'module4', 'hard')).toBe(0)
    expect(getScopeTotal(stats, 'module1', 'easy')).toBe(20)
    expect(getScopeTotal(stats, 'module9', '')).toBe(0)
  })
})
