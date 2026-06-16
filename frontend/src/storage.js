// Thin, fail-safe wrapper around localStorage. Every read falls back to a
// default and never throws (private-mode / disabled storage stays usable).

const KEYS = {
  settings: 'pcep.settings',
  theme: 'pcep.theme',
  history: 'pcep.history',
}

const HISTORY_LIMIT = 100

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
