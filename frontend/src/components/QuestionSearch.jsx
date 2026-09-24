import { useEffect, useRef, useState } from 'react'
import { apiErrorMessage, searchQuestions } from '../api'
import { publicQuestionSummary } from '../questionData'

const MODULE_LABELS = {
  module1: 'Module 1',
  module2: 'Module 2',
  module3: 'Module 3',
  module4: 'Module 4',
}

export default function QuestionSearch({ module = '', difficulty = '', onStart }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [selected, setSelected] = useState(() => new Set())
  const [searched, setSearched] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const request = useRef(null)

  useEffect(
    () => () => {
      request.current?.abort()
      request.current = null
    },
    []
  )

  const search = async (event) => {
    event.preventDefault()
    const term = query.trim()
    if (term.length < 2 || term.length > 80 || loading) return
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setLoading(true)
    setError('')
    try {
      const data = await searchQuestions(
        { query: term, module, difficulty, limit: 20 },
        { signal: controller.signal }
      )
      if (request.current !== controller || controller.signal.aborted) return
      const previews = Array.isArray(data?.results)
        ? data.results.map(publicQuestionSummary)
        : []
      if (
        !Number.isInteger(data?.count) ||
        data.count !== previews.length ||
        previews.length > 20 ||
        previews.some((result) => !result) ||
        new Set(previews.map((result) => result.id)).size !== previews.length
      )
        throw new Error('The server returned invalid search results. Please retry.')
      setResults(previews)
      setSelected(new Set())
      setSearched(true)
    } catch (searchError) {
      if (request.current === controller && !controller.signal.aborted) {
        setError(apiErrorMessage(searchError, 'Search failed. Please retry.'))
        setResults([])
        setSelected(new Set())
        setSearched(true)
      }
    } finally {
      if (request.current === controller) {
        request.current = null
        setLoading(false)
      }
    }
  }

  const toggle = (id) => {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const scope = [module && MODULE_LABELS[module], difficulty].filter(Boolean).join(', ')

  return (
    <section
      aria-labelledby="question-search-heading"
      className="mt-6 border-t border-slate-200 pt-6 dark:border-slate-700"
    >
      <h3
        id="question-search-heading"
        className="font-semibold text-slate-900 dark:text-slate-100"
      >
        Build a focused drill
      </h3>
      <p
        id="question-search-help"
        className="mt-1 text-sm text-slate-600 dark:text-slate-400"
      >
        Search question text or Python code, choose up to 20 matches, then practise them.
        {scope ? ` Current scope: ${scope}.` : ''}
      </p>
      <form onSubmit={search} className="mt-3 flex min-w-0 flex-col gap-2 sm:flex-row">
        <label htmlFor="question-search" className="sr-only">
          Search question text or code
        </label>
        <input
          id="question-search"
          type="search"
          minLength={2}
          maxLength={80}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-describedby="question-search-help"
          placeholder="Search question text or code"
          className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-400"
        />
        <button
          type="submit"
          disabled={loading || query.trim().length < 2}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 font-medium text-slate-800 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
        >
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {error && (
        <p
          role="alert"
          className="mt-3 text-sm font-medium text-red-700 dark:text-red-400"
        >
          {error}
        </p>
      )}
      {!error && searched && results.length === 0 && (
        <p role="status" className="mt-3 text-sm text-slate-600 dark:text-slate-400">
          No questions matched this search and scope.
        </p>
      )}
      {results.length > 0 && (
        <div className="mt-4 min-w-0">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p role="status" className="text-sm text-slate-600 dark:text-slate-400">
              {results.length} result{results.length === 1 ? '' : 's'} · {selected.size}{' '}
              selected
            </p>
            <button
              type="button"
              onClick={() =>
                setSelected(
                  selected.size === results.length
                    ? new Set()
                    : new Set(results.map((result) => result.id))
                )
              }
              className="rounded text-sm font-medium text-sky-700 underline-offset-2 hover:underline dark:text-sky-300"
            >
              {selected.size === results.length
                ? 'Clear selection'
                : 'Select all results'}
            </button>
          </div>
          <fieldset className="min-w-0 space-y-2">
            <legend className="sr-only">Question search results</legend>
            {results.map((result) => (
              <label
                key={result.id}
                className="flex min-w-0 cursor-pointer gap-3 rounded-lg border border-slate-200 p-3 hover:border-slate-400 dark:border-slate-700 dark:hover:border-slate-500"
              >
                <input
                  type="checkbox"
                  checked={selected.has(result.id)}
                  onChange={() => toggle(result.id)}
                  className="mt-1 h-4 w-4 shrink-0 accent-sky-700"
                />
                <span className="min-w-0">
                  <span className="block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    {MODULE_LABELS[result.module]} · {result.difficulty}
                  </span>
                  <span className="mt-1 block text-sm text-slate-800 dark:text-slate-200">
                    {result.text}
                  </span>
                  {result.code_snippet && (
                    <code
                      tabIndex={0}
                      aria-label="Question code preview"
                      className="mt-2 block max-h-24 overflow-auto whitespace-pre rounded bg-slate-100 p-2 text-xs text-slate-800 dark:bg-slate-950 dark:text-slate-200"
                    >
                      {result.code_snippet}
                    </code>
                  )}
                </span>
              </label>
            ))}
          </fieldset>
          <button
            type="button"
            disabled={selected.size === 0}
            onClick={() => onStart([...selected])}
            className="mt-3 w-full rounded-lg bg-sky-700 px-4 py-2.5 font-medium text-white hover:bg-sky-800 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 dark:disabled:bg-slate-700 dark:disabled:text-slate-400"
          >
            Start selected ({selected.size})
          </button>
        </div>
      )}
    </section>
  )
}
