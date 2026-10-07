import { describe, expect, it, vi } from 'vitest'
import { purgeLegacyRunnerCaches } from './runnerIsolation'

describe('legacy same-origin runner cleanup', () => {
  it('deletes only the retired Pyodide runtime cache', async () => {
    const cacheStorage = { delete: vi.fn(async () => true) }
    expect(await purgeLegacyRunnerCaches(cacheStorage)).toBe(true)
    expect(cacheStorage.delete).toHaveBeenCalledOnce()
    expect(cacheStorage.delete).toHaveBeenCalledWith('pyodide-runtime-0.29.4')
  })

  it('fails closed without disrupting application startup', async () => {
    expect(await purgeLegacyRunnerCaches(null)).toBe(false)
    expect(
      await purgeLegacyRunnerCaches({
        delete: vi.fn(async () => {
          throw new Error('blocked')
        }),
      })
    ).toBe(false)
  })
})
