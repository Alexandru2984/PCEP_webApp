import { loadTheme, saveTheme } from './storage'

export function getInitialTheme() {
  const saved = loadTheme()
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function applyTheme(theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
  saveTheme(theme)
}
