/* eslint-disable */
// Classic Web Worker that runs the in-browser Python interpreter (Pyodide/WASM).
//
// Why a worker: Pyodide is a ~12 MB WASM runtime and a learner's snippet may loop
// forever. Running it off the main thread keeps the UI responsive, and the manager
// (src/pyRunner.js) can terminate this worker to kill a runaway `while True:` —
// something that is impossible on the main thread.
//
// Loaded same-origin from /pyodide/ (self-hosted, see scripts/fetch-pyodide.sh) so
// the page's CSP needs no third-party origin — only 'wasm-unsafe-eval' for WASM.

const PYODIDE_BASE = '/pyodide/'
const MAX_OUTPUT = 10000 // chars; guards against a runaway print loop flooding postMessage

let pyodidePromise = null
let outBuf = []
let truncated = false
let outputSize = 0

function pushOutput(stream, text) {
  if (truncated) return
  const remaining = MAX_OUTPUT - outputSize
  if (remaining <= 0) {
    truncated = true
    return
  }
  const chunk = text.slice(0, remaining)
  outBuf.push({ stream, text: chunk })
  outputSize += chunk.length
  if (text.length > remaining) truncated = true
}

async function getPyodide() {
  if (pyodidePromise) return pyodidePromise
  pyodidePromise = (async () => {
    importScripts(PYODIDE_BASE + 'pyodide.js')
    const pyodide = await loadPyodide({ indexURL: PYODIDE_BASE })
    pyodide.setStdout({ batched: (s) => pushOutput('stdout', s + '\n') })
    pyodide.setStderr({ batched: (s) => pushOutput('stderr', s + '\n') })
    return pyodide
  })()
  return pyodidePromise
}

self.onmessage = async (event) => {
  const { type, id, code } = event.data || {}

  if (type === 'init') {
    try {
      await getPyodide()
      self.postMessage({ type: 'ready' })
    } catch (err) {
      self.postMessage({
        type: 'fatal',
        error: String(err && err.message ? err.message : err),
      })
    }
    return
  }

  if (type !== 'run') return
  if (typeof code !== 'string' || code.length > 20000) {
    self.postMessage({ type: 'result', id, output: [], error: 'Code is too large.' })
    return
  }

  let pyodide
  try {
    pyodide = await getPyodide()
  } catch (err) {
    self.postMessage({
      type: 'result',
      id,
      output: [],
      error:
        'Python runtime failed to load: ' +
        String(err && err.message ? err.message : err),
    })
    return
  }

  // Fresh namespace per run so re-running an edited snippet never sees ghost
  // state from a previous run. CPython injects __builtins__ automatically.
  outBuf = []
  truncated = false
  outputSize = 0
  let ns
  let error = null
  try {
    ns = pyodide.runPython('dict()')
    await pyodide.runPythonAsync(code, { globals: ns })
  } catch (err) {
    // Pyodide surfaces the Python traceback in err.message.
    error = String(err && err.message ? err.message : err).slice(0, MAX_OUTPUT)
  } finally {
    if (ns && typeof ns.destroy === 'function') ns.destroy()
  }

  self.postMessage({ type: 'result', id, output: outBuf, error, truncated })
}
