import { validObjective } from './syllabus'

export const MODULES = ['module1', 'module2', 'module3', 'module4']
export const DIFFICULTIES = ['easy', 'medium', 'hard']
export const validId = (value) => Number.isSafeInteger(value) && value > 0
const text = (value, max, empty = false) =>
  typeof value === 'string' && value.length <= max && (empty || value.trim().length > 0)

// A whitelist also prevents answer metadata entering local question backups.
export function publicQuestion(q) {
  const objective = q?.objective
  if (
    !q ||
    !validId(q.id) ||
    !text(q.text, 5000) ||
    !text(q.code_snippet ?? '', 20_000, true) ||
    !MODULES.includes(q.module) ||
    !DIFFICULTIES.includes(q.difficulty) ||
    (objective !== undefined && !validObjective(objective, q.module)) ||
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
    ...(objective ? { objective } : {}),
    choices: q.choices.map(({ id, text }) => ({ id, text })),
  }
}

export function publicApiQuestion(q) {
  const question = publicQuestion(q)
  return question?.objective ? question : null
}

export function publicQuestionSummary(q) {
  const allowed = new Set([
    'id',
    'text',
    'code_snippet',
    'module',
    'difficulty',
    'objective',
  ])
  if (
    !q ||
    Object.keys(q).some((key) => !allowed.has(key)) ||
    !validId(q.id) ||
    !text(q.text, 5000) ||
    !text(q.code_snippet ?? '', 20_000, true) ||
    !MODULES.includes(q.module) ||
    !DIFFICULTIES.includes(q.difficulty) ||
    !validObjective(q.objective, q.module)
  )
    return null
  return {
    id: q.id,
    text: q.text,
    code_snippet: q.code_snippet ?? '',
    module: q.module,
    difficulty: q.difficulty,
    objective: q.objective,
  }
}

export function validateFeedback(data, question, pickedChoiceId) {
  const allowed = new Set([
    'question_id',
    'choice_id',
    'is_correct',
    'correct_choice_id',
    'explanation',
    'correct_explanation',
  ])
  const hasQuestionId = Object.prototype.hasOwnProperty.call(data ?? {}, 'question_id')
  const hasChoiceId = Object.prototype.hasOwnProperty.call(data ?? {}, 'choice_id')
  if (
    !data ||
    typeof data !== 'object' ||
    Array.isArray(data) ||
    Object.keys(data).some((key) => !allowed.has(key)) ||
    !Array.isArray(question?.choices) ||
    (pickedChoiceId !== null &&
      !question.choices.some((choice) => choice.id === pickedChoiceId)) ||
    hasQuestionId !== hasChoiceId ||
    (hasQuestionId && data.question_id !== question.id) ||
    (hasChoiceId && data.choice_id !== pickedChoiceId) ||
    typeof data.is_correct !== 'boolean' ||
    !question.choices.some((c) => c.id === data.correct_choice_id) ||
    data.is_correct !==
      (pickedChoiceId !== null && pickedChoiceId === data.correct_choice_id) ||
    !text(data.explanation, 20_000, true) ||
    !text(data.correct_explanation, 20_000, true)
  )
    throw new Error('The server returned invalid feedback. Please retry.')
  return {
    is_correct: data.is_correct,
    correct_choice_id: data.correct_choice_id,
    explanation: data.explanation,
    correct_explanation: data.correct_explanation,
  }
}
