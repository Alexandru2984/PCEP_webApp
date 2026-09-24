export const CONFIDENCE_LEVELS = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
]

export const CONFIDENCE_VALUES = CONFIDENCE_LEVELS.map(({ value }) => value)
export const validConfidence = (value) => CONFIDENCE_VALUES.includes(value)
export const MAX_RESPONSE_MS = 3 * 60 * 60 * 1000
