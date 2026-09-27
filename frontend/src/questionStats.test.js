import { describe, it, expect } from 'vitest'
import { getScopeTotal, normalizeQuestionStats } from './questionStats'
import { OBJECTIVE_VALUES } from './syllabus'

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

const emptyDifficulties = () => ({ easy: 0, medium: 0, hard: 0 })
const snapshot = {
  total: 4,
  by_module: { module1: 1, module2: 1, module3: 1, module4: 1 },
  by_difficulty: { easy: 2, medium: 1, hard: 1 },
  by_objective: Object.fromEntries(OBJECTIVE_VALUES.map((value) => [value, 0])),
  objective_matrix: Object.fromEntries(
    OBJECTIVE_VALUES.map((value) => [value, emptyDifficulties()])
  ),
  matrix: {
    module1: { easy: 1, medium: 0, hard: 0 },
    module2: { easy: 0, medium: 1, hard: 0 },
    module3: { easy: 0, medium: 0, hard: 1 },
    module4: { easy: 1, medium: 0, hard: 0 },
  },
  modules: [
    { value: 'module1', label: 'Module 1', total: 1, easy: 1, medium: 0, hard: 0 },
    { value: 'module2', label: 'Module 2', total: 1, easy: 0, medium: 1, hard: 0 },
    { value: 'module3', label: 'Module 3', total: 1, easy: 0, medium: 0, hard: 1 },
    { value: 'module4', label: 'Module 4', total: 1, easy: 1, medium: 0, hard: 0 },
  ],
  pass_threshold: 70,
}
snapshot.by_objective['1.1'] = 1
snapshot.by_objective['2.1'] = 1
snapshot.by_objective['3.1'] = 1
snapshot.by_objective['4.1'] = 1
snapshot.objective_matrix['1.1'].easy = 1
snapshot.objective_matrix['2.1'].medium = 1
snapshot.objective_matrix['3.1'].hard = 1
snapshot.objective_matrix['4.1'].easy = 1

describe('normalizeQuestionStats', () => {
  it('accepts a complete internally consistent snapshot', () => {
    expect(normalizeQuestionStats(snapshot)).toEqual(snapshot)
  })

  it.each([
    (value) => {
      value.total = 5
    },
    (value) => {
      value.modules[0].hard = 1
    },
    (value) => {
      delete value.objective_matrix['4.4']
    },
    (value) => {
      value.by_module.module5 = 0
    },
    (value) => {
      value.pass_threshold = 101
    },
  ])('rejects malformed or inconsistent aggregate data', (mutate) => {
    const invalid = structuredClone(snapshot)
    mutate(invalid)
    expect(normalizeQuestionStats(invalid)).toBeNull()
  })
})

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
