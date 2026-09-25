import { useEffect, useState } from 'react'

export function secondsUntil(deadline, now = Date.now()) {
  if (!Number.isFinite(deadline) || !Number.isFinite(now)) return 0
  return Math.max(0, Math.ceil((deadline - now) / 1000))
}

export default function useDeadlineCountdown(deadline) {
  const [remaining, setRemaining] = useState(() => secondsUntil(deadline))

  useEffect(() => {
    const tick = () => setRemaining(secondsUntil(deadline))
    tick()
    const interval = window.setInterval(tick, 1000)
    window.addEventListener('focus', tick)
    document.addEventListener('visibilitychange', tick)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('focus', tick)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [deadline])

  return remaining
}
