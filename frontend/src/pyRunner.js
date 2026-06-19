// Main-thread manager for the in-browser Python runner.
//
// One Pyodide worker is shared by every CodeRunner on the page (the 12 MB runtime
// loads once). Runs are serialized — a single interpreter can only do one thing at
// a time — and each run is guarded by an execution timeout that *terminates* the
// worker to kill a runaway `while True:`. The one-time WASM load is awaited
// separately so it never eats into a snippet's execution budget.

const WORKER_URL = '/py-worker.js'

let worker = null
let status = 'idle' // idle | loading | ready | error
let statusError = null
let readyPromise = null
let readyResolve = null
let pending = null // { id, resolve, timer }
let seq = 0
let queue = Promise.resolve()
const listeners = new Set()

function setStatus(next, err = null) {
  status = next
  statusError = err
  for (const fn of listeners) fn(status, statusError)
}

export function getStatus() {
  return status
}

// React components subscribe to load-state changes (idle → loading → ready/error).
export function subscribeStatus(fn) {
  listeners.add(fn)
  fn(status, statusError)
  return () => listeners.delete(fn)
}

function spawn() {
  // Classic worker — it uses importScripts() to pull in pyodide.js.
  worker = new Worker(WORKER_URL)
  worker.onmessage = (event) => {
    const msg = event.data || {}
    if (msg.type === 'ready') {
      setStatus('ready')
      readyResolve?.()
      return
    }
    if (msg.type === 'fatal') {
      setStatus('error', msg.error)
      readyResolve?.() // unblock waiters; runOne checks status afterwards
      return
    }
    if (msg.type === 'result' && pending && msg.id === pending.id) {
      clearTimeout(pending.timer)
      const p = pending
      pending = null
      p.resolve({ output: msg.output || [], error: msg.error || null, timedOut: false })
    }
  }
  worker.onerror = (event) => {
    setStatus('error', event.message || 'Python worker error')
    readyResolve?.()
    if (pending) {
      clearTimeout(pending.timer)
      const p = pending
      pending = null
      p.resolve({ output: [], error: 'Python worker crashed.', timedOut: false })
    }
  }
}

function startLoading() {
  setStatus('loading')
  spawn()
  worker.postMessage({ type: 'init' })
}

// Resolve once Pyodide has finished loading (or failed). Never rejects — callers
// inspect getStatus() afterwards. Safe to call repeatedly / to preload on hover.
export function warmUp() {
  if (status === 'ready') return Promise.resolve()
  if (!readyPromise) {
    readyPromise = new Promise((resolve) => {
      readyResolve = resolve
    })
    startLoading()
  }
  return readyPromise
}

async function runOne(code, timeoutMs) {
  await warmUp()
  if (status === 'error') {
    return {
      output: [],
      error: statusError || 'Python runtime is unavailable.',
      timedOut: false,
    }
  }
  return new Promise((resolve) => {
    const id = ++seq
    const timer = setTimeout(() => {
      if (!pending || pending.id !== id) return
      pending = null
      // Kill the runaway interpreter and start a fresh one for the next run.
      try {
        worker.terminate()
      } catch {
        /* already gone */
      }
      worker = null
      readyPromise = null
      readyResolve = null
      setStatus('idle')
      warmUp() // pre-warm the replacement so the next Run is snappy
      resolve({ output: [], error: null, timedOut: true })
    }, timeoutMs)
    pending = { id, resolve, timer }
    worker.postMessage({ type: 'run', id, code })
  })
}

// Run `code` and resolve with { output: [{stream,text}], error, timedOut }.
// Runs are queued so two snippets never share the interpreter mid-execution.
export function runPython(code, { timeoutMs = 8000 } = {}) {
  const result = queue.then(() => runOne(code, timeoutMs))
  queue = result.catch(() => {})
  return result
}
