import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import useDeadlineCountdown, { secondsUntil } from './useDeadlineCountdown'

afterEach(() => vi.useRealTimers())

describe('deadline countdown', () => {
  it('uses ceiling seconds and clamps expired or invalid deadlines', () => {
    expect(secondsUntil(10_001, 10_000)).toBe(1)
    expect(secondsUntil(11_001, 10_000)).toBe(2)
    expect(secondsUntil(9_000, 10_000)).toBe(0)
    expect(secondsUntil(Number.NaN, 10_000)).toBe(0)
  })

  it('tracks wall-clock changes on interval, focus and visibility events', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-25T10:00:00Z'))
    const deadline = Date.now() + 65_000
    const { result } = renderHook(() => useDeadlineCountdown(deadline))
    expect(result.current).toBe(65)

    act(() => vi.advanceTimersByTime(6000))
    expect(result.current).toBe(59)

    vi.setSystemTime(new Date('2026-09-25T10:02:00Z'))
    act(() => window.dispatchEvent(new Event('focus')))
    expect(result.current).toBe(0)

    act(() => document.dispatchEvent(new Event('visibilitychange')))
    expect(result.current).toBe(0)
  })
})
