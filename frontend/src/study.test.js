import { describe, expect, it } from 'vitest'
import {
  DAY_MS,
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
})
