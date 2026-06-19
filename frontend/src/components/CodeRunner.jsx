import { useEffect, useRef, useState } from 'react'
import CodeBlock from './CodeBlock'
import { runPython, subscribeStatus } from '../pyRunner'

// A code snippet the learner can actually run — and edit and re-run — in the
// browser via a self-hosted Pyodide worker. Defaults to the syntax-highlighted
// read-only view; clicking "Edit" swaps in a textarea. Output (stdout/stderr,
// tracebacks, timeouts) renders in a panel below.
export default function CodeRunner({ code, className = '' }) {
  const [source, setSource] = useState(code)
  const [editing, setEditing] = useState(false)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null) // { output, error, timedOut } | null
  const [status, setStatus] = useState('idle') // pyodide load state
  const textareaRef = useRef(null)

  // State resets across questions via a `key` on the element (set by the parent),
  // so no effect is needed to sync `source` when `code` changes.
  useEffect(() => subscribeStatus((s) => setStatus(s)), [])

  const edited = source !== code

  const run = async () => {
    if (running) return
    setRunning(true)
    setResult(null)
    const res = await runPython(source)
    setResult(res)
    setRunning(false)
  }

  const reset = () => {
    setSource(code)
    setResult(null)
    if (editing) textareaRef.current?.focus()
  }

  const onEditorKeyDown = (e) => {
    // Ctrl/Cmd+Enter runs without leaving the editor.
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      run()
    }
  }

  const loading = status === 'loading'
  const lineCount = source.split('\n').length

  return (
    <div className={className}>
      {editing ? (
        <div className="overflow-hidden rounded-lg bg-slate-900 ring-1 ring-slate-700">
          <textarea
            ref={textareaRef}
            value={source}
            onChange={(e) => setSource(e.target.value)}
            onKeyDown={onEditorKeyDown}
            spellCheck={false}
            autoComplete="off"
            autoCapitalize="off"
            aria-label="Editable Python code"
            rows={Math.min(Math.max(lineCount, 2), 20)}
            className="block w-full resize-y bg-transparent p-4 font-mono text-sm leading-relaxed text-slate-100 focus:outline-none"
          />
        </div>
      ) : (
        <CodeBlock code={source} />
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={run}
          disabled={running}
          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {running ? (
            <>
              <Spinner />
              {loading ? 'Loading Python…' : 'Running…'}
            </>
          ) : (
            <>
              <span aria-hidden="true">▸</span> Run
            </>
          )}
        </button>

        <button
          type="button"
          onClick={() => setEditing((v) => !v)}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
        >
          {editing ? 'Done editing' : 'Edit'}
        </button>

        {edited && (
          <button
            type="button"
            onClick={reset}
            className="rounded-lg px-2 py-1.5 text-sm font-medium text-slate-500 underline underline-offset-2 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
          >
            Reset
          </button>
        )}

        {running && loading && (
          <span className="text-xs text-slate-500 dark:text-slate-400">
            first run downloads the Python runtime (~12&nbsp;MB, cached after)
          </span>
        )}
        {!running && (
          <span className="ml-auto text-xs text-slate-500 dark:text-slate-400">
            runs in your browser · <kbd className="font-mono">Ctrl</kbd>+
            <kbd className="font-mono">Enter</kbd>
          </span>
        )}
      </div>

      {result && <OutputPanel result={result} />}
    </div>
  )
}

function OutputPanel({ result }) {
  const { output, error, timedOut } = result

  if (timedOut) {
    return (
      <Panel tone="error" label="Timed out">
        Execution timed out (possible infinite loop). The interpreter was reset.
      </Panel>
    )
  }

  const hasOutput = output && output.length > 0
  if (!hasOutput && !error) {
    return (
      <Panel tone="muted" label="Output">
        (no output)
      </Panel>
    )
  }

  return (
    <Panel tone={error ? 'error' : 'ok'} label="Output">
      {hasOutput && (
        <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-relaxed">
          {output.map((chunk, i) => (
            <span
              key={i}
              className={chunk.stream === 'stderr' ? 'text-red-300' : 'text-slate-100'}
            >
              {chunk.text}
            </span>
          ))}
        </pre>
      )}
      {error && (
        <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-sm leading-relaxed text-red-300">
          {error}
        </pre>
      )}
    </Panel>
  )
}

function Panel({ tone, label, children }) {
  const ring =
    tone === 'error'
      ? 'ring-red-800'
      : tone === 'muted'
        ? 'ring-slate-700'
        : 'ring-emerald-800'
  const labelColor =
    tone === 'error'
      ? 'text-red-400'
      : tone === 'muted'
        ? 'text-slate-500'
        : 'text-emerald-400'
  return (
    <div className={`mt-2 rounded-lg bg-slate-900 p-3 ring-1 ${ring}`}>
      <div className={`mb-1 text-xs font-semibold uppercase tracking-wide ${labelColor}`}>
        {label}
      </div>
      <div className="text-slate-100">{children}</div>
    </div>
  )
}

function Spinner() {
  return (
    <svg
      className="h-3.5 w-3.5 animate-spin"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z"
      />
    </svg>
  )
}
