// Minimal capability bridge hosted on the isolated runner origin. The parent
// receives a private MessagePort; the untrusted Python worker never receives it.
;(() => {
  'use strict'

  const PROTOCOL = 'pcep-python-v1'
  const PARENT_ORIGINS = new Set([
    'https://pcep.micutu.com',
    'http://localhost:4173',
    'http://localhost:5173',
  ])
  const MAX_CODE = 20000
  const MAX_OUTPUT = 10000
  let port = null
  let worker = null
  let pendingId = null

  function boundedResult(message) {
    let remaining = MAX_OUTPUT
    const output = []
    let truncated = message.truncated === true
    if (Array.isArray(message.output)) {
      const chunks = message.output.slice(0, 1000)
      if (chunks.length < message.output.length) truncated = true
      for (const chunk of chunks) {
        if (!remaining) {
          truncated = true
          break
        }
        if (!chunk || typeof chunk.text !== 'string') {
          truncated = true
          continue
        }
        const text = chunk.text.slice(0, remaining)
        output.push({ stream: chunk.stream === 'stderr' ? 'stderr' : 'stdout', text })
        remaining -= text.length
        if (text.length < chunk.text.length) truncated = true
      }
    }
    const error =
      typeof message.error === 'string' ? message.error.slice(0, MAX_OUTPUT) : null
    if (error && error.length < message.error.length) truncated = true
    return { output, error, truncated }
  }

  function send(message) {
    port?.postMessage({ protocol: PROTOCOL, ...message })
  }

  function stopWorker() {
    try {
      worker?.terminate()
    } catch {
      // The worker already stopped.
    }
    worker = null
    pendingId = null
  }

  function fatal(error) {
    send({
      type: 'fatal',
      error: String(error || 'Python runner failed.').slice(0, MAX_OUTPUT),
    })
    stopWorker()
  }

  function startWorker() {
    try {
      const instance = new Worker('/py-worker.js')
      worker = instance
      instance.onmessage = ({ data: message = {} }) => {
        if (worker !== instance || typeof message !== 'object') return
        if (message.type === 'ready') {
          send({ type: 'ready' })
        } else if (message.type === 'fatal') {
          fatal(message.error)
        } else if (message.type === 'result' && message.id === pendingId) {
          const result = boundedResult(message)
          const id = pendingId
          pendingId = null
          send({ type: 'result', id, ...result })
        }
      }
      instance.onerror = (event) => {
        event.preventDefault?.()
        if (worker === instance)
          fatal(event.message || 'Python worker crashed. Run again to retry.')
      }
      instance.onmessageerror = () => {
        if (worker === instance)
          fatal('Python returned unreadable output. Run again to retry.')
      }
      instance.postMessage({ type: 'init' })
    } catch (error) {
      fatal(error && error.message ? error.message : error)
    }
  }

  function handlePortMessage({ data: message = {} }) {
    if (message.protocol !== PROTOCOL) return
    if (message.type === 'terminate') {
      stopWorker()
      port?.close()
      port = null
      return
    }
    if (
      message.type !== 'run' ||
      !worker ||
      pendingId !== null ||
      !Number.isSafeInteger(message.id) ||
      message.id <= 0
    )
      return
    if (typeof message.code !== 'string' || message.code.length > MAX_CODE) {
      send({
        type: 'result',
        id: message.id,
        output: [],
        error: 'Code is too large.',
        truncated: false,
      })
      return
    }
    pendingId = message.id
    try {
      worker.postMessage({ type: 'run', id: message.id, code: message.code })
    } catch (error) {
      fatal(error && error.message ? error.message : error)
    }
  }

  function connect(event) {
    const message = event.data || {}
    if (
      port ||
      event.source !== parent ||
      !PARENT_ORIGINS.has(event.origin) ||
      message.protocol !== PROTOCOL ||
      message.type !== 'connect' ||
      event.ports.length !== 1
    )
      return
    port = event.ports[0]
    port.onmessage = handlePortMessage
    port.onmessageerror = () => fatal('Parent sent an unreadable request.')
    port.start()
    window.removeEventListener('message', connect)
    startWorker()
  }

  window.addEventListener('message', connect)
  for (const origin of PARENT_ORIGINS)
    parent.postMessage({ protocol: PROTOCOL, type: 'bridge-ready' }, origin)
})()
