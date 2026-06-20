import { describe, it, expect } from 'vitest'
import { formatClock, formatElapsed } from './format'

describe('formatClock', () => {
  it('formats whole minutes and zero-pads seconds', () => {
    expect(formatClock(0)).toBe('0:00')
    expect(formatClock(5)).toBe('0:05')
    expect(formatClock(65)).toBe('1:05')
    expect(formatClock(600)).toBe('10:00')
  })

  it('floors fractional seconds', () => {
    expect(formatClock(59.9)).toBe('0:59')
  })

  it('clamps negative input to zero (timer never shows a negative clock)', () => {
    expect(formatClock(-10)).toBe('0:00')
  })
})

describe('formatElapsed', () => {
  it('shows only seconds under a minute', () => {
    expect(formatElapsed(0)).toBe('0s')
    expect(formatElapsed(4200)).toBe('4s')
  })

  it('shows minutes and seconds past a minute', () => {
    expect(formatElapsed(65_000)).toBe('1m 5s')
    expect(formatElapsed(125_000)).toBe('2m 5s')
  })

  it('rounds milliseconds to the nearest second', () => {
    expect(formatElapsed(1500)).toBe('2s')
  })
})
