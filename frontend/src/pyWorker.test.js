import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { cwd } from 'node:process'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

const source = readFileSync(resolve(cwd(), 'public/py-worker.js'), 'utf8')
function worker(execute) {
  let stdout
  const namespace = { destroy: vi.fn() }
  const context = {
    self: { postMessage: vi.fn() },
    importScripts: vi.fn(),
    loadPyodide: async () => ({
      setStdout: ({ batched }) => {
        stdout = batched
      },
      setStderr: vi.fn(),
      runPython: () => namespace,
      runPythonAsync: async () => execute(stdout),
    }),
  }
  runInNewContext(source, context)
  return { context, namespace }
}
describe('Python worker output limits', () => {
  it('bounds huge output, reports truncation and destroys the run namespace', async () => {
    const { context, namespace } = worker((stdout) => {
      for (let i = 0; i < 1000; i++) stdout('x'.repeat(100))
    })
    await context.self.onmessage({ data: { type: 'run', id: 1, code: 'print(1)' } })
    const result = context.self.postMessage.mock.calls.at(-1)[0]
    expect(
      result.output.reduce((n, chunk) => n + chunk.text.length, 0)
    ).toBeLessThanOrEqual(10000)
    expect(result.truncated).toBe(true)
    expect(namespace.destroy).toHaveBeenCalledOnce()
  })
  it('bounds errors and rejects oversized code before loading Python', async () => {
    const { context } = worker(() => {
      throw new Error('x'.repeat(20000))
    })
    await context.self.onmessage({ data: { type: 'run', id: 1, code: 'print(1)' } })
    expect(context.self.postMessage.mock.calls.at(-1)[0].error).toHaveLength(10000)
    const other = worker(vi.fn()).context
    await other.self.onmessage({ data: { type: 'run', id: 2, code: 'x'.repeat(20001) } })
    expect(other.importScripts).not.toHaveBeenCalled()
    expect(other.self.postMessage.mock.calls.at(-1)[0].error).toMatch(/too large/)
  })
})
