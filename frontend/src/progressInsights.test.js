import { describe, expect, it } from 'vitest'
import { performanceInsights, studyStreak } from './progressInsights'

const atLocalNoon = (year, month, day) => new Date(year, month, day, 12).toISOString()
const attempt = (overrides = {}) => ({
  date: atLocalNoon(2026, 8, 24),
  mode: 'practice',
  score: 7,
  total: 10,
  pct: 70,
  elapsedMs: 100_000,
  ...overrides,
})

describe('studyStreak', () => {
  it('counts unique consecutive local study days and includes flashcards', () => {
    const attempts = [
      attempt(),
      attempt({ date: atLocalNoon(2026, 8, 24), mode: 'flashcards' }),
      attempt({ date: atLocalNoon(2026, 8, 23) }),
      attempt({ date: atLocalNoon(2026, 8, 22) }),
      attempt({ date: atLocalNoon(2026, 8, 19) }),
    ]

    expect(studyStreak(attempts, new Date(2026, 8, 24, 18).getTime())).toEqual({
      current: 3,
      longest: 3,
    })
  })

  it('keeps a current streak alive through the day after the last session', () => {
    const attempts = [
      attempt({ date: atLocalNoon(2026, 8, 23) }),
      attempt({ date: atLocalNoon(2026, 8, 22) }),
    ]
    expect(studyStreak(attempts, new Date(2026, 8, 24, 18).getTime()).current).toBe(2)
  })

  it('expires the current streak after a missed calendar day', () => {
    const attempts = [
      attempt({ date: atLocalNoon(2026, 8, 21) }),
      attempt({ date: atLocalNoon(2026, 8, 20) }),
    ]
    expect(studyStreak(attempts, new Date(2026, 8, 24, 18).getTime())).toMatchObject({
      current: 0,
      longest: 2,
    })
  })
})

describe('performanceInsights', () => {
  it('compares equally sized recent windows with question-weighted accuracy', () => {
    const attempts = [
      attempt({ date: atLocalNoon(2026, 8, 21), score: 1, total: 2, pct: 50 }),
      attempt({ date: atLocalNoon(2026, 8, 24), score: 9, total: 10, pct: 90 }),
      attempt({ date: atLocalNoon(2026, 8, 22), score: 1, total: 2, pct: 50 }),
      attempt({ date: atLocalNoon(2026, 8, 23), score: 8, total: 10, pct: 80 }),
    ]

    expect(performanceInsights(attempts).trend).toEqual({
      recent: 85,
      previous: 50,
      delta: 35,
      direction: 'improving',
      windowSize: 2,
    })
  })

  it('treats changes smaller than three points as steady', () => {
    const attempts = [
      attempt({ date: atLocalNoon(2026, 8, 24), score: 81, total: 100, pct: 81 }),
      attempt({ date: atLocalNoon(2026, 8, 23), score: 80, total: 100, pct: 80 }),
      attempt({ date: atLocalNoon(2026, 8, 22), score: 79, total: 100, pct: 79 }),
      attempt({ date: atLocalNoon(2026, 8, 21), score: 78, total: 100, pct: 78 }),
    ]
    expect(performanceInsights(attempts).trend.direction).toBe('steady')
  })

  it('requires four graded sessions before presenting a trend', () => {
    const attempts = [attempt(), attempt({ mode: 'flashcards' }), attempt()]
    expect(performanceInsights(attempts).trend).toBeNull()
  })

  it('calculates pace across timed graded questions only', () => {
    const attempts = [
      attempt({ total: 10, elapsedMs: 100_000 }),
      attempt({ total: 5, elapsedMs: 50_000 }),
      attempt({ total: 10, elapsedMs: 0 }),
      attempt({ mode: 'flashcards', total: 10, elapsedMs: 900_000 }),
    ]
    expect(performanceInsights(attempts).averageMsPerQuestion).toBe(10_000)
  })

  it('prefers measured response timing and aggregates confidence calibration', () => {
    const attempts = [
      attempt({
        responseMsTotal: 30_000,
        responseCount: 3,
        byConfidence: {
          low: { score: 1, total: 1 },
          high: { score: 1, total: 2 },
        },
      }),
      attempt({ elapsedMs: 900_000 }),
    ]
    const insights = performanceInsights(attempts)
    expect(insights.averageMsPerQuestion).toBe(10_000)
    expect(insights.measuredResponseTime).toBe(true)
    expect(insights.confidence).toEqual({
      rated: 3,
      highTotal: 2,
      highCorrect: 1,
      highMisses: 1,
      lowCorrect: 1,
    })
  })

  it('returns the ten most recent graded scores in chronological chart order', () => {
    const attempts = Array.from({ length: 12 }, (_, index) =>
      attempt({
        date: atLocalNoon(2026, 8, index + 1),
        score: index,
        total: 20,
        pct: index * 5,
      })
    )
    const scores = performanceInsights(attempts).scores
    expect(scores).toHaveLength(10)
    expect(scores.map(({ score }) => score)).toEqual([
      10, 15, 20, 25, 30, 35, 40, 45, 50, 55,
    ])
  })
})
