const DATE_KEY = /^\d{4}-\d{2}-\d{2}$/

export function validDateKey(value) {
  if (typeof value !== 'string' || !DATE_KEY.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}

export function bucharestDateKey(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Bucharest',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now)
  const value = Object.fromEntries(parts.map(({ type, value: part }) => [type, part]))
  return `${value.year}-${value.month}-${value.day}`
}
