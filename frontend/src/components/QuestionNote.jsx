import { useState } from 'react'
import { loadNote, saveNote } from '../storage'

const MAX_LENGTH = 2000

export default function QuestionNote({ questionId, className = '' }) {
  const [note, setNote] = useState(() => loadNote(questionId))
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(() => note?.text ?? '')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const save = () => {
    try {
      const saved = saveNote(questionId, draft)
      setNote(saved)
      setDraft(saved?.text ?? '')
      setEditing(false)
      setError('')
      setMessage(saved ? 'Note saved.' : 'Note removed.')
    } catch (saveError) {
      setError(saveError.message)
      setMessage('')
    }
  }

  const cancel = () => {
    setDraft(note?.text ?? '')
    setEditing(false)
    setError('')
  }

  return (
    <div className={className}>
      {!editing ? (
        <div>
          {note && (
            <p className="mb-2 whitespace-pre-wrap [overflow-wrap:anywhere] rounded-lg border border-violet-200 bg-violet-50 p-3 text-sm text-violet-950 dark:border-violet-800 dark:bg-violet-950/30 dark:text-violet-100">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-violet-700 dark:text-violet-300">
                Personal note
              </span>
              {note.text}
            </p>
          )}
          <button
            type="button"
            onClick={() => {
              setEditing(true)
              setMessage('')
            }}
            className="rounded text-sm font-medium text-violet-700 underline underline-offset-2 hover:text-violet-900 dark:text-violet-300 dark:hover:text-violet-200"
          >
            {note ? 'Edit note' : 'Add note'}
          </button>
        </div>
      ) : (
        <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 dark:border-violet-800 dark:bg-violet-950/30">
          <label
            htmlFor={`question-note-${questionId}`}
            className="text-sm font-medium text-violet-950 dark:text-violet-100"
          >
            Personal note
          </label>
          <textarea
            id={`question-note-${questionId}`}
            value={draft}
            maxLength={MAX_LENGTH}
            rows={4}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Write a reminder in your own words…"
            className="mt-2 block w-full resize-y rounded-lg border border-violet-300 bg-white p-3 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-violet-500 dark:border-violet-700 dark:bg-slate-900 dark:text-slate-100"
          />
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-violet-700 dark:text-violet-300">
              {draft.length.toLocaleString()}/{MAX_LENGTH.toLocaleString()}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={cancel}
                className="rounded-lg border border-violet-300 bg-white px-3 py-2 text-sm font-medium text-violet-900 hover:bg-violet-100 dark:border-violet-700 dark:bg-slate-900 dark:text-violet-100 dark:hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={save}
                className="rounded-lg bg-violet-700 px-3 py-2 text-sm font-medium text-white hover:bg-violet-800"
              >
                {draft.trim() ? 'Save note' : 'Remove note'}
              </button>
            </div>
          </div>
        </div>
      )}
      {message && (
        <p role="status" className="mt-2 text-xs text-emerald-700 dark:text-emerald-300">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-xs text-red-700 dark:text-red-300">
          {error}
        </p>
      )}
    </div>
  )
}
