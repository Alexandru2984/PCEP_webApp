export const SESSION_COUNTS = Object.freeze([5, 10, 20, 30, 50])
export const DEFAULT_SESSION_COUNT = 30

export const preferredSessionCount = (value) =>
  SESSION_COUNTS.includes(value) ? value : DEFAULT_SESSION_COUNT
