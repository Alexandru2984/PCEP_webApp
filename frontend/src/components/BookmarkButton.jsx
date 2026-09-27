import { useState } from 'react'
import { loadBookmarks, toggleBookmark } from '../storage'
import useProgressSync from '../useProgressSync'

export default function BookmarkButton({ question }) {
  useProgressSync()
  const saved = loadBookmarks().some((q) => q.id === question.id)
  const [error, setError] = useState(null)
  const toggle = () => {
    try {
      toggleBookmark(question)
      setError(null)
    } catch (error) {
      setError(error.message)
    }
  }
  return (
    <div>
      <button
        type="button"
        aria-pressed={saved}
        onClick={toggle}
        className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
      >
        {saved ? '★ Bookmarked' : '☆ Bookmark'}
      </button>
      {error && (
        <p role="alert" className="mt-1 text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      )}
    </div>
  )
}
