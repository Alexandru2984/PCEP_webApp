import { describe, it, expect } from 'vitest'
import { getScopeTotal } from './questionStats'

const stats = {
  total: 217,
  by_module: { module1: 52, module2: 52 },
  by_difficulty: { easy: 77, medium: 88, hard: 52 },
  matrix: {
    module1: { easy: 20, medium: 19, hard: 13 },
  },
  by_objective: { 1.4: 42, 3.1: 18 },
  objective_matrix: {
    1.4: { easy: 15, medium: 17, hard: 10 },
    3.1: { easy: 7, medium: 8, hard: 3 },
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

  it('scopes by syllabus objective independently of the module selection', () => {
    expect(getScopeTotal(stats, '', '', '3.1')).toBe(18)
    expect(getScopeTotal(stats, 'module3', '', '3.1')).toBe(18)
  })

  it('uses the objective/difficulty matrix for a precise study scope', () => {
    expect(getScopeTotal(stats, 'module1', 'hard', '1.4')).toBe(10)
    expect(getScopeTotal(stats, '', 'medium', '3.1')).toBe(8)
  })

  it('falls back to 0 for an out-of-range combination', () => {
    expect(getScopeTotal(stats, 'module4', 'hard')).toBe(0)
    expect(getScopeTotal(stats, 'module1', 'easy')).toBe(20)
    expect(getScopeTotal(stats, 'module9', '')).toBe(0)
  })
})
