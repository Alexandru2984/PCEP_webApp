import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

let runner
let createElement
const frames = []
const channels = []

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

class FakeMessageChannel {
  constructor() {
    this.port1 = new FakePort()
    this.port2 = new FakePort()
    channels.push(this)
  }
}

const flush = async () => {
  for (let i = 0; i < 12; i++) await Promise.resolve()
}

function bridgeReady(instance = frames.at(-1), origin = window.location.origin) {
  const event = new MessageEvent('message', {
    data: { protocol: 'pcep-python-v1', type: 'bridge-ready' },
    origin,
  })
  Object.defineProperty(event, 'source', { value: instance.contentWindow })
  window.dispatchEvent(event)
}

async function ready() {
  await flush()
  bridgeReady()
  channels.at(-1).port1.emit({ protocol: 'pcep-python-v1', type: 'ready' })
  await flush()
}

function result(channel, output = []) {
  const run = channel.port1.postMessage.mock.calls.findLast(
    ([message]) => message.type === 'run'
  )[0]
  channel.port1.emit({
    protocol: 'pcep-python-v1',
    type: 'result',
    id: run.id,
    output,
  })
}

beforeEach(async () => {
  vi.resetModules()
  vi.useFakeTimers()
  vi.stubGlobal('MessageChannel', FakeMessageChannel)
  frames.length = 0
  channels.length = 0
  document.body.replaceChildren()
  createElement = document.createElement.bind(document)
  vi.spyOn(document, 'createElement').mockImplementation((tag, options) => {
    const element = createElement(tag, options)
    if (tag === 'iframe') {
      const contentWindow = { postMessage: vi.fn() }
      Object.defineProperty(element, 'contentWindow', { value: contentWindow })
      frames.push(element)
    }
    return element
  })
  runner = await import('./pyRunner')
})

afterEach(() => {
  channels.at(-1)?.port1.emit({
    protocol: 'pcep-python-v1',
    type: 'fatal',
    error: 'test cleanup',
  })
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.body.replaceChildren()
})

describe('isolated Python runner lifecycle', () => {
  it('creates a credentialless frame, authenticates its origin and uses a private port', async () => {
    const run = runner.runPython('print(1)')
    await flush()
    expect(frames).toHaveLength(1)
    expect(frames[0].src).toBe(`${window.location.origin}/runner.html`)
    expect(frames[0].hasAttribute('credentialless')).toBe(true)
    expect(frames[0].referrerPolicy).toBe('no-referrer')

    bridgeReady(frames[0], 'https://attacker.test')
    expect(channels).toHaveLength(0)
    bridgeReady()
    expect(channels).toHaveLength(1)
    expect(frames[0].contentWindow.postMessage).toHaveBeenCalledWith(
      { protocol: 'pcep-python-v1', type: 'connect' },
      window.location.origin,
      [channels[0].port2]
    )
    channels[0].port1.emit({ protocol: 'pcep-python-v1', type: 'ready' })
    await flush()
    result(channels[0], [{ stream: 'stdout', text: '1' }])
    expect((await run).output[0].text).toBe('1')
  })

  it('shares one isolated runtime and serializes multiple runs', async () => {
    const first = runner.runPython('print(1)')
    const second = runner.runPython('print(2)')
    await ready()
    expect(frames).toHaveLength(1)
    result(channels[0], [{ stream: 'stdout', text: '1' }])
    expect((await first).output[0].text).toBe('1')
    await flush()
    result(channels[0], [{ stream: 'stdout', text: '2' }])
    expect((await second).output[0].text).toBe('2')
  })

  it('destroys a timed-out frame and creates a fresh isolated runtime', async () => {
    const first = runner.runPython('while True: pass', { timeoutMs: 100 })
    await ready()
    await vi.advanceTimersByTimeAsync(100)
    expect((await first).timedOut).toBe(true)
    expect(frames[0].isConnected).toBe(false)
    expect(channels[0].port1.close).toHaveBeenCalledOnce()

    const second = runner.runPython('print(2)')
    await ready()
    expect(frames).toHaveLength(2)
    result(channels[1])
    expect((await second).error).toBeNull()
  })

  it('bounds startup and permits a later retry', async () => {
    const first = runner.runPython('print(1)')
    await flush()
    await vi.advanceTimersByTimeAsync(30_000)
    expect((await first).error).toMatch(/startup timed out/)
    expect(frames[0].isConnected).toBe(false)

    const second = runner.runPython('print(2)')
    await ready()
    result(channels[0])
    expect((await second).error).toBeNull()
  })

  it('recovers from fatal bridge failures without leaving pending runs', async () => {
    const first = runner.runPython('print(1)')
    await ready()
    channels[0].port1.emit({
      protocol: 'pcep-python-v1',
      type: 'fatal',
      error: 'Runtime offline',
    })
    expect((await first).error).toBe('Runtime offline')

    const second = runner.runPython('print(2)')
    await ready()
    result(channels[1])
    expect((await second).error).toBeNull()
  })

  it('rejects oversized code and bounds queued executions', async () => {
    expect((await runner.runPython('x'.repeat(20_001))).error).toMatch(/20,000/)
    const runs = Array.from({ length: 4 }, () => runner.runPython('print(1)'))
    expect((await runner.runPython('print(1)')).error).toMatch(/busy/)
    await ready()
    for (const promise of runs) {
      result(channels[0])
      await promise
      await flush()
    }
  })

  it('bounds unexpected oversized output received across the capability channel', async () => {
    const run = runner.runPython('print(1)')
    await ready()
    result(channels[0], [{ stream: 'stdout', text: 'x'.repeat(20_000) }])
    const bounded = await run
    expect(bounded.output[0].text).toHaveLength(10_000)
    expect(bounded.truncated).toBe(true)
  })
})

describe('runner origin validation', () => {
  it('requires a distinct HTTPS origin outside loopback development', () => {
    expect(
      runner.validateRunnerOrigin(
        'https://pcep-runner.micutu.com',
        'https://pcep.micutu.com/'
      )
    ).toBe('https://pcep-runner.micutu.com')
    for (const value of [
      'http://pcep-runner.micutu.com',
      'https://pcep.micutu.com',
      'https://pcep-runner.micutu.com/path',
      'https://user@pcep-runner.micutu.com',
    ])
      expect(() =>
        runner.validateRunnerOrigin(value, 'https://pcep.micutu.com/')
      ).toThrow()
  })

  it('allows an explicit loopback origin for local browser tests', () => {
    expect(
      runner.validateRunnerOrigin('http://localhost:4174', 'http://localhost:4173/')
    ).toBe('http://localhost:4174')
  })
})
