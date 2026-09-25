import { describe, expect, it } from 'vitest'
import { examDurationLabel, PCEP_30_02_PRESET, validPcep30_02Set } from './exam'

describe('exam presets', () => {
  it('matches the PCEP-30-02 size, duration and module distribution', () => {
    expect(PCEP_30_02_PRESET.count).toBe(30)
    expect(PCEP_30_02_PRESET.durationSeconds).toBe(2400)
    expect(PCEP_30_02_PRESET.distribution).toEqual({
      module1: 7,
      module2: 8,
      module3: 7,
      module4: 8,
    })
    expect(
      Object.values(PCEP_30_02_PRESET.distribution).reduce(
        (total, count) => total + count,
        0
      )
    ).toBe(PCEP_30_02_PRESET.count)
  })

  it('formats proportional exam timers', () => {
    expect(examDurationLabel(10)).toBe('13m 20s')
    expect(examDurationLabel(30)).toBe('40m')
    expect(examDurationLabel(50)).toBe('1h 6m 40s')
  })

  it('rejects a response whose advertised preset or module mix drifted', () => {
    const questions = Object.entries(PCEP_30_02_PRESET.distribution).flatMap(
      ([module, count]) => Array.from({ length: count }, () => ({ module }))
    )
    const response = { preset: 'pcep-30-02', count: 30 }
    expect(validPcep30_02Set(response, questions)).toBe(true)
    expect(validPcep30_02Set({ ...response, preset: 'other' }, questions)).toBe(false)
    expect(validPcep30_02Set(response, questions.slice(1))).toBe(false)
    expect(
      validPcep30_02Set(response, [...questions.slice(0, -1), { module: 'module1' }])
    ).toBe(false)
  })
})
