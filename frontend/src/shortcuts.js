export function ignoreShortcut(event) {
  return (
    event.defaultPrevented ||
    event.repeat ||
    event.isComposing ||
    event.metaKey ||
    event.ctrlKey ||
    event.altKey ||
    !!event.target?.closest?.(
      'input, textarea, select, [contenteditable]:not([contenteditable="false"])'
    )
  )
}

export function nativeActivation(event) {
  return (
    (event.key === 'Enter' || event.key === ' ') &&
    !!event.target?.closest?.('button, a, summary')
  )
}
