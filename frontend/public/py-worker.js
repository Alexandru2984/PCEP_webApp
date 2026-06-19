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

function pushOutput(stream, text) {
  if (truncated) return
  const remaining = MAX_OUTPUT - outBuf.reduce((n, c) => n + c.text.length, 0)
  if (remaining <= 0) {
    truncated = true
    outBuf.push({ stream: 'stderr', text: '\n… output truncated …' })
    return
  }
  outBuf.push({ stream, text: text.length > remaining ? text.slice(0, remaining) : text })
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
  let ns
  let error = null
  try {
    ns = pyodide.runPython('dict()')
    await pyodide.runPythonAsync(code, { globals: ns })
  } catch (err) {
    // Pyodide surfaces the Python traceback in err.message.
    error = String(err && err.message ? err.message : err)
  } finally {
    if (ns && typeof ns.destroy === 'function') ns.destroy()
  }

  self.postMessage({ type: 'result', id, output: outBuf, error })
}
