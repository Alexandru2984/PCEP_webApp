// Applies the saved theme before first paint to avoid a flash of the wrong
// color scheme. Kept external (not inline) so the page can ship a strict
// Content-Security-Policy without allowing inline scripts.
try {
  var t = JSON.parse(localStorage.getItem('pcep.theme'))
  var dark = t === 'dark' || (!t && matchMedia('(prefers-color-scheme: dark)').matches)
  if (dark) document.documentElement.classList.add('dark')
} catch {
  /* storage unavailable — ignore */
}
