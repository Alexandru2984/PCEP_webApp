export function getStreakStats(items) {
  let current = 0
  let best = 0

  for (const item of items) {
    if (item.feedback?.is_correct) {
      current += 1
      best = Math.max(best, current)
    } else {
      current = 0
    }
  }

  return { current, best }
}
