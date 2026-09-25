import { describe, expect, it } from 'vitest'
import { bucharestDateKey, validDateKey } from './daily'

describe('daily challenge dates', () => {
  it('validates real calendar date keys', () => {
    expect(validDateKey('2028-02-29')).toBe(true)
    expect(validDateKey('2026-02-29')).toBe(false)
    expect(validDateKey('2026-9-24')).toBe(false)
  })

  it('uses the production challenge timezone at the day boundary', () => {
    expect(bucharestDateKey(new Date('2026-09-24T20:59:59Z'))).toBe('2026-09-24')
    expect(bucharestDateKey(new Date('2026-09-24T21:00:00Z'))).toBe('2026-09-25')
  })
})
