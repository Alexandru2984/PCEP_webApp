const DAY_MS = 24 * 60 * 60 * 1000
const TREND_WINDOW = 5
const TREND_THRESHOLD = 3

function timestamp(attempt) {
  const value = Date.parse(attempt?.date)
  return Number.isFinite(value) ? value : null
}

function localDay(timestampValue) {
  const date = new Date(timestampValue)
  return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / DAY_MS
}

function byMostRecent(attempts) {
  return attempts
    .map((attempt) => ({ attempt, timestamp: timestamp(attempt) }))
    .filter((entry) => entry.timestamp !== null)
    .sort((a, b) => b.timestamp - a.timestamp)
}

function weightedAccuracy(attempts) {
  const total = attempts.reduce((sum, attempt) => sum + attempt.total, 0)
  if (!total) return 0
  return Math.round(
    (attempts.reduce((sum, attempt) => sum + attempt.score, 0) / total) * 100
  )
}

export function studyStreak(attempts, now = Date.now()) {
  const today = localDay(now)
  const days = [
    ...new Set(
      byMostRecent(attempts)
        .map(({ timestamp: value }) => localDay(value))
        .filter((day) => day <= today)
    ),
  ].sort((a, b) => a - b)

  let longest = 0
  let run = 0
  let previous
  for (const day of days) {
    run = previous === undefined || day === previous + 1 ? run + 1 : 1
    longest = Math.max(longest, run)
    previous = day
  }

  const latest = days.at(-1)
  let current = 0
  if (latest !== undefined && today - latest <= 1) {
    current = 1
    for (let index = days.length - 2; index >= 0; index -= 1) {
      if (days[index] !== days[index + 1] - 1) break
      current += 1
    }
  }

  return { current, longest }
}

export function performanceInsights(attempts, now = Date.now()) {
  const streak = studyStreak(attempts, now)
  const graded = byMostRecent(attempts)
    .map(({ attempt }) => attempt)
    .filter((attempt) => attempt.mode !== 'flashcards')

  const timed = graded.filter((attempt) => attempt.elapsedMs > 0 && attempt.total > 0)
  const timedQuestions = timed.reduce((sum, attempt) => sum + attempt.total, 0)
  const averageMsPerQuestion = timedQuestions
    ? Math.round(
        timed.reduce((sum, attempt) => sum + attempt.elapsedMs, 0) / timedQuestions
      )
    : null

  let trend = null
  if (graded.length >= 4) {
    const windowSize = Math.min(TREND_WINDOW, Math.floor(graded.length / 2))
    const recent = weightedAccuracy(graded.slice(0, windowSize))
    const previous = weightedAccuracy(graded.slice(windowSize, windowSize * 2))
    const delta = recent - previous
    trend = {
      recent,
      previous,
      delta,
      direction:
        delta >= TREND_THRESHOLD
          ? 'improving'
          : delta <= -TREND_THRESHOLD
            ? 'declining'
            : 'steady',
      windowSize,
    }
  }

  const scores = graded
    .slice(0, 10)
    .reverse()
    .map((attempt) => ({ date: attempt.date, score: attempt.pct }))

  return { ...streak, averageMsPerQuestion, trend, scores }
}
