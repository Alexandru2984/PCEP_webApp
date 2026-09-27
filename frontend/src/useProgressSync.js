import { useEffect, useReducer } from 'react'

const PROGRESS_KEYS = new Set([
  'pcep.progress',
  'pcep.history',
  'pcep.mistakes',
  'pcep.bookmarks',
])

export default function useProgressSync() {
  const [revision, refresh] = useReducer((value) => value + 1, 0)

  useEffect(() => {
    const changedHere = () => refresh()
    const changedElsewhere = (event) => {
      if (event.key === null || PROGRESS_KEYS.has(event.key)) refresh()
    }
    window.addEventListener('pcep-progress-change', changedHere)
    window.addEventListener('storage', changedElsewhere)
    return () => {
      window.removeEventListener('pcep-progress-change', changedHere)
      window.removeEventListener('storage', changedElsewhere)
    }
  }, [])

  return revision
}
