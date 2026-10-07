import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { cwd } from 'node:process'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

const source = readFileSync(resolve(cwd(), 'public/runner-bridge.js'), 'utf8')

class FakePort {
  postMessage = vi.fn()
  close = vi.fn()
  start = vi.fn()
  onmessage = null
  onmessageerror = null

  emit(data) {
    this.onmessage?.({ data })
  }
}

function bridge() {
  let connect
  const parent = { postMessage: vi.fn() }
  const workers = []
  class FakeWorker {
    constructor(url) {
      this.url = url
      this.postMessage = vi.fn()
      this.terminate = vi.fn()
      workers.push(this)
    }

    emit(data) {
      this.onmessage({ data })
    }
  }
  const window = {
    addEventListener: vi.fn((type, listener) => {
      if (type === 'message') connect = listener
    }),
    removeEventListener: vi.fn(),
  }
  runInNewContext(source, { window, parent, Worker: FakeWorker })
  return { connect, parent, window, workers }
}

describe('isolated runner capability bridge', () => {
  it('accepts one private port only from the exact production parent', () => {
    const isolated = bridge()
    const attackerPort = new FakePort()
    isolated.connect({
      source: isolated.parent,
      origin: 'https://attacker.test',
      data: { protocol: 'pcep-python-v1', type: 'connect' },
      ports: [attackerPort],
    })
    expect(isolated.workers).toHaveLength(0)

    const port = new FakePort()
    isolated.connect({
      source: isolated.parent,
      origin: 'https://pcep.micutu.com',
      data: { protocol: 'pcep-python-v1', type: 'connect' },
      ports: [port],
    })
    expect(isolated.workers).toHaveLength(1)
    expect(isolated.workers[0].url).toBe('/py-worker.js')
    expect(isolated.workers[0].postMessage).toHaveBeenCalledWith({ type: 'init' })
    expect(port.start).toHaveBeenCalledOnce()
    expect(isolated.window.removeEventListener).toHaveBeenCalledOnce()
  })

  it('never gives the worker the parent port and bounds untrusted worker messages', () => {
    const isolated = bridge()
    const port = new FakePort()
    isolated.connect({
      source: isolated.parent,
      origin: 'https://pcep.micutu.com',
      data: { protocol: 'pcep-python-v1', type: 'connect' },
      ports: [port],
    })
    const worker = isolated.workers[0]
    port.emit({ protocol: 'pcep-python-v1', type: 'run', id: 7, code: 'print(1)' })
    expect(worker.postMessage).toHaveBeenLastCalledWith({
      type: 'run',
      id: 7,
      code: 'print(1)',
    })
    expect(worker.postMessage.mock.calls.flat()).not.toContain(port)

    worker.emit({
      type: 'result',
      id: 7,
      output: [{ stream: 'made-up', text: 'x'.repeat(20_000) }],
      error: null,
    })
    const message = port.postMessage.mock.calls.at(-1)[0]
    expect(message.protocol).toBe('pcep-python-v1')
    expect(message.output).toEqual([{ stream: 'stdout', text: 'x'.repeat(10_000) }])
    expect(message.truncated).toBe(true)
  })

  it('rejects malformed, concurrent and oversized run requests', () => {
    const isolated = bridge()
    const port = new FakePort()
    isolated.connect({
      source: isolated.parent,
      origin: 'https://pcep.micutu.com',
      data: { protocol: 'pcep-python-v1', type: 'connect' },
      ports: [port],
    })
    const worker = isolated.workers[0]
    port.emit({ protocol: 'wrong', type: 'run', id: 1, code: 'print(1)' })
    port.emit({
      protocol: 'pcep-python-v1',
      type: 'run',
      id: 1,
      code: 'x'.repeat(20_001),
    })
    expect(worker.postMessage).toHaveBeenCalledTimes(1)
    expect(port.postMessage.mock.calls.at(-1)[0].error).toMatch(/too large/)

    port.emit({ protocol: 'pcep-python-v1', type: 'run', id: 2, code: 'pass' })
    port.emit({ protocol: 'pcep-python-v1', type: 'run', id: 3, code: 'pass' })
    expect(worker.postMessage).toHaveBeenCalledTimes(2)
  })
})
