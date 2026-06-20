// Thin, fail-safe wrapper around localStorage. Every read falls back to a
// default and never throws (private-mode / disabled storage stays usable).

const KEYS = {
  settings: 'pcep.settings',
  theme: 'pcep.theme',
  history: 'pcep.history',
  mistakes: 'pcep.mistakes',
}

const HISTORY_LIMIT = 100
const MISTAKES_LIMIT = 100

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw == null ? fallback : JSON.parse(raw)
  } catch {
    return fallback
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage unavailable — ignore */
  }
}

export const loadSettings = () => read(KEYS.settings, null)
export const saveSettings = (settings) => write(KEYS.settings, settings)

export const loadTheme = () => read(KEYS.theme, null)
export const saveTheme = (theme) => write(KEYS.theme, theme)

export const loadHistory = () => read(KEYS.history, [])

export function appendAttempt(attempt) {
  const history = [attempt, ...loadHistory()].slice(0, HISTORY_LIMIT)
  write(KEYS.history, history)
  return history
}

export const clearHistory = () => write(KEYS.history, [])

// --- Missed-question store (powers "Practice your mistakes") --------------
// Holds the full question objects the learner got wrong, newest first, so a
// targeted practice session can be built without hitting the API.

export const loadMistakes = () => read(KEYS.mistakes, [])

// Fold a finished quiz's items into the store: questions answered wrong (or
// skipped) are added/refreshed to the front, questions answered correctly are
// removed (mastered). Returns the updated list, newest first, capped.
export function updateMistakes(items) {
  const byId = new Map(loadMistakes().map((q) => [q.id, q]))
  for (const item of items) {
    const question = item?.question
    if (!question || question.id == null) continue
    byId.delete(question.id) // drop first so a re-miss moves to the front
    if (!item.feedback?.is_correct) byId.set(question.id, question)
  }
  // Map keeps insertion order (oldest first); reverse to get newest first.
  const list = [...byId.values()].reverse().slice(0, MISTAKES_LIMIT)
  write(KEYS.mistakes, list)
  return list
}

export const clearMistakes = () => write(KEYS.mistakes, [])
