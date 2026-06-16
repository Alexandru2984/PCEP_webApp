import { useEffect, useState } from 'react'

const reduced = () =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

export function useCountUp(target, duration = 700) {
  const [value, setValue] = useState(reduced() ? target : 0)

  useEffect(() => {
    if (reduced()) return // initial value already equals the target
    let raf
    const start = performance.now()
    const tick = (t) => {
      const p = Math.min(1, (t - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3) // ease-out cubic
      setValue(Math.round(target * eased))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])

  return reduced() ? target : value
}
