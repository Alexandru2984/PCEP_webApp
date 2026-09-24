import { describe, expect, it } from 'vitest'
import {
  DAY_MS,
  adaptivePracticePlan,
  masteryPercent,
  normalizeStudyRecord,
  studySummary,
  updateStudyRecords,
} from './study'

const question = (id = 1) => ({
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
const item = (correct, id = 1) => ({
  question: question(id),
  feedback: { is_correct: correct },
})

describe('study schedule', () => {
  it('uses simple 1, 3, 7, 14 day intervals for consecutive correct reviews', () => {
    let records = []
    const start = Date.UTC(2026, 8, 20, 12)
    for (const [index, interval] of [1, 3, 7, 14].entries()) {
      const now = start + index * DAY_MS
      records = updateStudyRecords(records, [item(true)], now)
      expect(records[0]).toMatchObject({
        attempts: index + 1,
        correct: index + 1,
        streak: index + 1,
        intervalDays: interval,
      })
      expect(Date.parse(records[0].nextReview)).toBe(now + interval * DAY_MS)
    }
  })

  it('makes a missed question due immediately and restarts its interval', () => {
    const now = Date.UTC(2026, 8, 20, 12)
    let records = updateStudyRecords([], [item(true)], now)
    records = updateStudyRecords(records, [item(false)], now + DAY_MS)
    expect(records[0]).toMatchObject({
      attempts: 2,
      correct: 1,
      streak: 0,
      intervalDays: 0,
    })
    expect(Date.parse(records[0].nextReview)).toBe(now + DAY_MS)
    expect(studySummary(records, now + DAY_MS).due).toBe(1)
  })

  it('tracks multiple questions without storing choices or answer metadata', () => {
    const records = updateStudyRecords([], [item(true, 1), item(false, 2)])
    expect(records.map((record) => record.questionId).sort()).toEqual([1, 2])
    expect(JSON.stringify(records)).not.toContain('choice')
    expect(JSON.stringify(records)).not.toContain('is_correct')
  })

  it('rejects inconsistent schedules and computes bounded mastery', () => {
    const [record] = updateStudyRecords([], [item(true)], Date.UTC(2026, 8, 20))
    expect(
      normalizeStudyRecord({ ...record, nextReview: record.lastAttempted })
    ).toBeNull()
    expect(masteryPercent(record)).toBeGreaterThan(0)
    expect(masteryPercent(record)).toBeLessThanOrEqual(100)
  })

  it('prioritizes due work and current mistakes over strong future reviews', () => {
    const now = Date.UTC(2026, 8, 20, 12)
    const due = updateStudyRecords([], [item(false, 1)], now - 1000)[0]
    const strong = {
      questionId: 3,
      module: 'module1',
      difficulty: 'hard',
      attempts: 4,
      correct: 4,
      streak: 4,
      intervalDays: 14,
      lastAttempted: new Date(now).toISOString(),
      nextReview: new Date(now + 14 * DAY_MS).toISOString(),
    }
    const plan = adaptivePracticePlan([strong, due], [question(2)], now, 2)
    expect(plan.ids).toEqual([2, 1])
    expect(plan.signals).toEqual({ due: 2, mistakes: 1, weak: 2 })
  })

  it('uses difficulty then age as deterministic priority tie-breakers', () => {
    const now = Date.UTC(2026, 8, 20, 12)
    const record = (questionId, difficulty, age) => ({
      questionId,
      module: 'module1',
      difficulty,
      attempts: 5,
      correct: 3,
      streak: 2,
      intervalDays: 3,
      lastAttempted: new Date(now - age).toISOString(),
      nextReview: new Date(now - age + 3 * DAY_MS).toISOString(),
    })
    const plan = adaptivePracticePlan(
      [
        record(1, 'easy', DAY_MS),
        record(2, 'hard', DAY_MS),
        record(3, 'hard', 2 * DAY_MS),
      ],
      [],
      now,
      3
    )
    expect(plan.ids).toEqual([3, 2, 1])
  })

  it('does not invent a recommendation when every tracked question is strong', () => {
    const now = Date.UTC(2026, 8, 20, 12)
    const strong = {
      questionId: 1,
      module: 'module1',
      difficulty: 'hard',
      attempts: 5,
      correct: 5,
      streak: 5,
      intervalDays: 30,
      lastAttempted: new Date(now).toISOString(),
      nextReview: new Date(now + 30 * DAY_MS).toISOString(),
    }
    expect(adaptivePracticePlan([strong], [], now)).toEqual({
      ids: [],
      count: 0,
      signals: { due: 0, mistakes: 0, weak: 0 },
    })
  })
})
