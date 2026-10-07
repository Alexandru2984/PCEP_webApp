// Shared, serialized interpreter hosted in a capability-free cross-origin frame.
// Termination keeps the UI responsive; origin isolation contains Pyodide's JS bridge.
const DEFAULT_RUNNER_ORIGIN = 'https://pcep-runner.micutu.com'
const RUNNER_PROTOCOL = 'pcep-python-v1'
const LOAD_TIMEOUT_MS = 30_000
const MAX_QUEUE = 4
const MAX_CODE = 20_000
const MAX_OUTPUT = 10_000
let frame = null
let runnerOrigin = null
let port = null
let status = 'idle'
let statusError = null
let readyPromise = null
let readyResolve = null
let loadTimer = null
let pending = null
let seq = 0
let queue = Promise.resolve()
let scheduled = 0
let bridgeListener = null
const listeners = new Set()

function isLoopback(hostname) {
  return (
    hostname === 'localhost' ||
    hostname === '::1' ||
    hostname === '[::1]' ||
    hostname.startsWith('127.')
  )
}

export function validateRunnerOrigin(value, pageUrl = window.location.href) {
  let configured
  let page
  try {
    configured = new URL(value)
    page = new URL(pageUrl)
  } catch {
    throw new Error('Python runner origin is invalid.')
  }
  if (
    configured.username ||
    configured.password ||
    configured.pathname !== '/' ||
    configured.search ||
    configured.hash
  )
    throw new Error('Python runner must be configured as an origin only.')
  if (
    !isLoopback(page.hostname) &&
    (configured.protocol !== 'https:' || configured.origin === page.origin)
  )
    throw new Error('Production Python runner must use a separate HTTPS origin.')
  return configured.origin
}

function configuredRunnerOrigin() {
  const previewOrigin = `http://${window.location.hostname}:4174`
  const configured =
    import.meta.env.VITE_PYTHON_RUNNER_ORIGIN ||
    (import.meta.env.DEV
      ? window.location.origin
      : isLoopback(window.location.hostname)
        ? previewOrigin
        : DEFAULT_RUNNER_ORIGIN)
  return validateRunnerOrigin(configured)
}

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

function stopRunner() {
  clearTimeout(loadTimer)
  loadTimer = null
  if (bridgeListener) window.removeEventListener('message', bridgeListener)
  bridgeListener = null
  try {
    port?.postMessage({ protocol: RUNNER_PROTOCOL, type: 'terminate' })
  } catch {
    /* the isolated frame is already gone */
  }
  if (port) port.onmessage = null
  try {
    port?.close()
  } catch {
    /* the message channel is already closed */
  }
  port = null
  frame?.remove()
  frame = null
  runnerOrigin = null
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
  stopRunner()
  setStatus('error', error)
}

function boundedResult(msg) {
  let remaining = MAX_OUTPUT
  const output = []
  let truncated = msg.truncated === true
  if (Array.isArray(msg.output)) {
    const chunks = msg.output.slice(0, 1000)
    if (chunks.length < msg.output.length) truncated = true
    for (const chunk of chunks) {
      if (!remaining) {
        truncated = true
        break
      }
      if (typeof chunk?.text !== 'string') {
        truncated = true
        continue
      }
      const text = chunk.text.slice(0, remaining)
      output.push({ stream: chunk.stream === 'stderr' ? 'stderr' : 'stdout', text })
      remaining -= text.length
      if (text.length < chunk.text.length) truncated = true
    }
  }
  const error = typeof msg.error === 'string' ? msg.error.slice(0, MAX_OUTPUT) : null
  if (error && error.length < msg.error.length) truncated = true
  return {
    output,
    error,
    timedOut: false,
    truncated,
  }
}

function handleRunnerMessage(msg = {}) {
  if (msg.protocol !== RUNNER_PROTOCOL) return
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

export function warmUp() {
  if (status === 'ready') return Promise.resolve()
  if (status === 'loading' && readyPromise) return readyPromise
  const promise = new Promise((resolve) => {
    readyResolve = resolve
  })
  readyPromise = promise
  setStatus('loading')
  try {
    runnerOrigin = configuredRunnerOrigin()
    const instance = document.createElement('iframe')
    frame = instance
    instance.hidden = true
    instance.tabIndex = -1
    instance.title = 'Isolated Python runner'
    instance.referrerPolicy = 'no-referrer'
    // Chromium makes this a credentialless, ephemeral context. Other browsers
    // safely ignore the attribute; the separate origin remains the boundary.
    instance.setAttribute('credentialless', '')
    instance.src = `${runnerOrigin}/runner.html`
    bridgeListener = (event) => {
      if (
        event.origin !== runnerOrigin ||
        event.source !== instance.contentWindow ||
        event.data?.protocol !== RUNNER_PROTOCOL ||
        event.data?.type !== 'bridge-ready' ||
        port
      )
        return
      const channel = new MessageChannel()
      port = channel.port1
      port.onmessage = ({ data }) => handleRunnerMessage(data)
      port.onmessageerror = () =>
        fail('Python returned unreadable output. Run again to retry.')
      port.start()
      instance.contentWindow.postMessage(
        { protocol: RUNNER_PROTOCOL, type: 'connect' },
        runnerOrigin,
        [channel.port2]
      )
    }
    window.addEventListener('message', bridgeListener)
    document.body.append(instance)
    loadTimer = setTimeout(
      () => fail('Python startup timed out. Check your connection and run again.'),
      LOAD_TIMEOUT_MS
    )
  } catch (error) {
    fail(error?.message || 'Python runner could not start. Run again to retry.')
  }
  return promise
}

async function runOne(code, timeoutMs) {
  await warmUp()
  if (status !== 'ready' || !port)
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
      stopRunner()
      setStatus('idle')
      resolve({ output: [], error: null, timedOut: true })
    }, timeoutMs)
    pending = { id, resolve, timer }
    try {
      port.postMessage({ protocol: RUNNER_PROTOCOL, type: 'run', id, code })
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
