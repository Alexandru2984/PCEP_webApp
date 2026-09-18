import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
let runner
const workers = []
class FakeWorker {
  constructor() {
    workers.push(this)
  }
  postMessage = vi.fn()
  terminate = vi.fn()
  emit(data) {
    this.onmessage({ data })
  }
}
const flush = async () => {
  for (let i = 0; i < 12; i++) await Promise.resolve()
}
beforeEach(async () => {
  vi.resetModules()
  vi.useFakeTimers()
  vi.stubGlobal('Worker', FakeWorker)
  workers.length = 0
  runner = await import('./pyRunner')
})
afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
const ready = async () => {
  await flush()
  workers.at(-1).emit({ type: 'ready' })
  await flush()
}
const result = (worker, output = []) => {
  const run = worker.postMessage.mock.calls.findLast(([msg]) => msg.type === 'run')[0]
  worker.emit({ type: 'result', id: run.id, output })
}
describe('Python worker lifecycle', () => {
  it('shares one startup and serializes multiple runs', async () => {
    const first = runner.runPython('print(1)')
    const second = runner.runPython('print(2)')
    await ready()
    expect(workers).toHaveLength(1)
    expect(workers[0].postMessage).toHaveBeenCalledTimes(2)
    result(workers[0], [{ stream: 'stdout', text: '1' }])
    expect((await first).output[0].text).toBe('1')
    await flush()
    result(workers[0], [{ stream: 'stdout', text: '2' }])
    expect((await second).output[0].text).toBe('2')
  })
  it('terminates a timed out run and starts a fresh worker on the next run', async () => {
    const first = runner.runPython('while True: pass', { timeoutMs: 100 })
    await ready()
    await vi.advanceTimersByTimeAsync(100)
    expect((await first).timedOut).toBe(true)
    expect(workers[0].terminate).toHaveBeenCalledOnce()
    const second = runner.runPython('print(2)')
    await ready()
    expect(workers).toHaveLength(2)
    result(workers[1])
    expect((await second).error).toBeNull()
  })
  it('bounds startup and permits a later retry', async () => {
    const first = runner.runPython('print(1)')
    await flush()
    await vi.advanceTimersByTimeAsync(30_000)
    expect((await first).error).toMatch(/startup timed out/)
    const second = runner.runPython('print(2)')
    await ready()
    result(workers[1])
    expect((await second).error).toBeNull()
  })
  it('recovers from a fatal runtime initialization failure', async () => {
    const first = runner.runPython('print(1)')
    await flush()
    workers[0].emit({ type: 'fatal', error: 'Runtime offline' })
    expect((await first).error).toBe('Runtime offline')
    const second = runner.runPython('print(2)')
    await ready()
    result(workers[1])
    expect((await second).error).toBeNull()
  })
  it('resolves constructor and execution crash errors without leaving pending runs', async () => {
    vi.stubGlobal(
      'Worker',
      class {
        constructor() {
          throw new Error('Blocked worker')
        }
      }
    )
    expect((await runner.runPython('print(1)')).error).toBe('Blocked worker')
    vi.stubGlobal('Worker', FakeWorker)
    const next = runner.runPython('print(2)')
    await ready()
    workers[0].onerror({ message: 'Crashed' })
    expect((await next).error).toBe('Crashed')
    expect(workers[0].terminate).toHaveBeenCalledOnce()
  })
  it('rejects oversized code and bounds queued executions', async () => {
    expect((await runner.runPython('x'.repeat(20_001))).error).toMatch(/20,000/)
    const runs = Array.from({ length: 4 }, () => runner.runPython('print(1)'))
    expect((await runner.runPython('print(1)')).error).toMatch(/busy/)
    await ready()
    for (const promise of runs) {
      result(workers[0])
      await promise
      await flush()
    }
  })
  it('bounds unexpected oversized output from the worker', async () => {
    const run = runner.runPython('print(1)')
    await ready()
    result(workers[0], [{ stream: 'stdout', text: 'x'.repeat(20000) }])
    expect((await run).output[0].text).toHaveLength(10000)
  })
})
