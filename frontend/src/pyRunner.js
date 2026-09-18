// Shared, serialized interpreter with separate startup/execution deadlines.
// Termination keeps the UI responsive; it is not a hostile-code sandbox.
const WORKER_URL = '/py-worker.js'
const LOAD_TIMEOUT_MS = 30_000
const MAX_QUEUE = 4
const MAX_CODE = 20_000
const MAX_OUTPUT = 10_000
let worker = null
let status = 'idle'
let statusError = null
let readyPromise = null
let readyResolve = null
let loadTimer = null
let pending = null
let seq = 0
let queue = Promise.resolve()
let scheduled = 0
const listeners = new Set()

function setStatus(next, error = null) {
  status = next
  statusError = error
  for (const listener of listeners) listener(status, statusError)
}
export const getStatus = () => status
export function subscribeStatus(listener) {
  listeners.add(listener)
  listener(status, statusError)
  return () => listeners.delete(listener)
}
function stopWorker() {
  clearTimeout(loadTimer)
  loadTimer = null
  try {
    worker?.terminate()
  } catch {
    /* already stopped */
  }
  worker = null
  readyResolve?.()
  readyResolve = null
  readyPromise = null
}
function fail(error) {
  const active = pending
  pending = null
  if (active) {
    clearTimeout(active.timer)
    active.resolve({ output: [], error, timedOut: false })
  }
  stopWorker()
  setStatus('error', error)
}
function boundedResult(msg) {
  let remaining = MAX_OUTPUT
  const output = []
  if (Array.isArray(msg.output)) {
    for (const chunk of msg.output.slice(0, 1000)) {
      if (!remaining || typeof chunk?.text !== 'string') break
      const text = chunk.text.slice(0, remaining)
      output.push({ stream: chunk.stream === 'stderr' ? 'stderr' : 'stdout', text })
      remaining -= text.length
    }
  }
  return {
    output,
    error: typeof msg.error === 'string' ? msg.error.slice(0, MAX_OUTPUT) : null,
    timedOut: false,
    truncated: msg.truncated === true,
  }
}
export function warmUp() {
  if (status === 'ready') return Promise.resolve()
  if (status === 'loading' && readyPromise) return readyPromise
  const promise = new Promise((resolve) => {
    readyResolve = resolve
  })
  readyPromise = promise
  setStatus('loading')
  try {
    const instance = new Worker(WORKER_URL)
    worker = instance
    loadTimer = setTimeout(
      () => fail('Python startup timed out. Check your connection and run again.'),
      LOAD_TIMEOUT_MS
    )
    instance.onmessage = ({ data: msg = {} }) => {
      if (worker !== instance) return
      if (msg.type === 'ready' && status === 'loading') {
        clearTimeout(loadTimer)
        loadTimer = null
        setStatus('ready')
        readyResolve?.()
        readyResolve = null
      } else if (msg.type === 'fatal') {
        fail(
          typeof msg.error === 'string'
            ? msg.error.slice(0, MAX_OUTPUT)
            : 'Python failed to load. Run again to retry.'
        )
      } else if (msg.type === 'result' && pending?.id === msg.id) {
        clearTimeout(pending.timer)
        const active = pending
        pending = null
        active.resolve(boundedResult(msg))
      }
    }
    instance.onerror = (event) => {
      if (worker === instance)
        fail(event.message || 'Python worker crashed. Run again to retry.')
    }
    instance.onmessageerror = () => {
      if (worker === instance)
        fail('Python returned unreadable output. Run again to retry.')
    }
    instance.postMessage({ type: 'init' })
  } catch (error) {
    fail(error?.message || 'Python worker could not start. Run again to retry.')
  }
  return promise
}
async function runOne(code, timeoutMs) {
  await warmUp()
  if (status !== 'ready' || !worker)
    return {
      output: [],
      error: statusError || 'Python runtime is unavailable. Run again to retry.',
      timedOut: false,
    }
  return new Promise((resolve) => {
    const id = ++seq
    const timer = setTimeout(() => {
      if (pending?.id !== id) return
      pending = null
      stopWorker()
      setStatus('idle')
      resolve({ output: [], error: null, timedOut: true })
    }, timeoutMs)
    pending = { id, resolve, timer }
    try {
      worker.postMessage({ type: 'run', id, code })
    } catch (error) {
      fail(error?.message || 'Python execution could not start. Run again to retry.')
    }
  })
}
export function runPython(code, { timeoutMs = 8000 } = {}) {
  if (typeof code !== 'string' || code.length > MAX_CODE)
    return Promise.resolve({
      output: [],
      error: 'Code must contain at most 20,000 characters.',
      timedOut: false,
    })
  if (scheduled >= MAX_QUEUE)
    return Promise.resolve({
      output: [],
      error: 'Python is busy. Wait for a run to finish, then retry.',
      timedOut: false,
    })
  const timeout = Number.isFinite(timeoutMs)
    ? Math.max(100, Math.min(timeoutMs, 8000))
    : 8000
  scheduled++
  const result = queue
    .then(() => runOne(code, timeout))
    .finally(() => {
      scheduled--
    })
  queue = result.catch(() => {})
  return result
}
