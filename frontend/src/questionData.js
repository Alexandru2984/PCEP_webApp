export const MODULES = ['module1', 'module2', 'module3', 'module4']
export const DIFFICULTIES = ['easy', 'medium', 'hard']
export const validId = (value) => Number.isSafeInteger(value) && value > 0
const text = (value, max, empty = false) =>
  typeof value === 'string' && value.length <= max && (empty || value.trim().length > 0)

// A whitelist also prevents answer metadata entering local question backups.
export function publicQuestion(q) {
  if (
    !q ||
    !validId(q.id) ||
    !text(q.text, 5000) ||
    !text(q.code_snippet ?? '', 20_000, true) ||
    !MODULES.includes(q.module) ||
    !DIFFICULTIES.includes(q.difficulty) ||
    !Array.isArray(q.choices) ||
    q.choices.length < 2 ||
    q.choices.length > 6
  )
    return null
  if (q.choices.some((c) => !c || !validId(c.id) || !text(c.text, 500))) return null
  if (new Set(q.choices.map((c) => c.id)).size !== q.choices.length) return null
  return {
    id: q.id,
    text: q.text,
    code_snippet: q.code_snippet ?? '',
    module: q.module,
    difficulty: q.difficulty,
    choices: q.choices.map(({ id, text }) => ({ id, text })),
  }
}

export function validateFeedback(data, question) {
  if (
    !data ||
    typeof data.is_correct !== 'boolean' ||
    !question.choices.some((c) => c.id === data.correct_choice_id) ||
    !text(data.explanation ?? '', 20_000, true) ||
    !text(data.correct_explanation ?? '', 20_000, true)
  )
    throw new Error('The server returned invalid feedback. Please retry.')
  return data
}
