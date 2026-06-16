// Tiny zero-dependency confetti burst. Honors prefers-reduced-motion and
// cleans up its own canvas when the animation ends.
const COLORS = ['#0ea5e9', '#22c55e', '#eab308', '#ef4444', '#a855f7', '#ec4899']

export function celebrate() {
  if (typeof document === 'undefined') return
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return

  const canvas = document.createElement('canvas')
  canvas.style.cssText =
    'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9999'
  canvas.width = window.innerWidth
  canvas.height = window.innerHeight
  document.body.appendChild(canvas)
  const ctx = canvas.getContext('2d')

  const particles = Array.from({ length: 150 }, () => ({
    x: canvas.width / 2 + (Math.random() - 0.5) * 120,
    y: canvas.height / 3,
    vx: (Math.random() - 0.5) * 14,
    vy: Math.random() * -14 - 4,
    size: Math.random() * 6 + 4,
    color: COLORS[(Math.random() * COLORS.length) | 0],
    rot: Math.random() * Math.PI * 2,
    vr: (Math.random() - 0.5) * 0.3,
  }))

  const start = performance.now()
  let raf
  const frame = (t) => {
    const elapsed = t - start
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    for (const p of particles) {
      p.vy += 0.3 // gravity
      p.x += p.vx
      p.y += p.vy
      p.rot += p.vr
      ctx.save()
      ctx.globalAlpha = Math.max(0, 1 - elapsed / 2600)
      ctx.translate(p.x, p.y)
      ctx.rotate(p.rot)
      ctx.fillStyle = p.color
      ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size)
      ctx.restore()
    }
    if (elapsed < 2600) {
      raf = requestAnimationFrame(frame)
    } else {
      cancelAnimationFrame(raf)
      canvas.remove()
    }
  }
  raf = requestAnimationFrame(frame)
}
