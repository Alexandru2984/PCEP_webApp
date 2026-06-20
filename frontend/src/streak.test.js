import { describe, it, expect } from 'vitest'
import { getStreakStats } from './streak'

const correct = { feedback: { is_correct: true } }
const wrong = { feedback: { is_correct: false } }

describe('getStreakStats', () => {
  it('returns zeros for an empty history', () => {
    expect(getStreakStats([])).toEqual({ current: 0, best: 0 })
  })

  it('counts a clean run of correct answers', () => {
    expect(getStreakStats([correct, correct, correct])).toEqual({ current: 3, best: 3 })
  })

  it('resets the current streak on a wrong answer but remembers the best', () => {
    const items = [correct, correct, wrong, correct]
    expect(getStreakStats(items)).toEqual({ current: 1, best: 2 })
  })

  it('keeps best from earlier when the run ends on a miss', () => {
    const items = [correct, correct, correct, wrong]
    expect(getStreakStats(items)).toEqual({ current: 0, best: 3 })
  })

  it('treats a missing feedback object as not correct', () => {
    expect(getStreakStats([correct, {}, correct])).toEqual({ current: 1, best: 1 })
  })
})
