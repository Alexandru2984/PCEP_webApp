import axios from 'axios'

// In production, nginx proxies /api to Django. In dev, Vite proxies (see vite.config.js).
const api = axios.create({
  baseURL: '/api',
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
})

export const fetchQuizSet = (
  { count = 30, module = '', difficulty = '', ids = [] } = {},
  options = {}
) => {
  const params = new URLSearchParams({ count: String(count) })
  if (module) params.set('module', module)
  if (difficulty) params.set('difficulty', difficulty)
  if (ids.length) params.set('ids', ids.join(','))
  return api.get(`/quiz-set/?${params.toString()}`, options).then((r) => r.data)
}

export const fetchQuestionStats = (options = {}) =>
  api.get('/stats/', options).then((r) => r.data)

export const submitAnswer = (questionId, choiceId, options = {}) =>
  api
    .post(`/questions/${questionId}/answer/`, { choice_id: choiceId }, options)
    .then((r) => r.data)

// answers: [{ question_id, choice_id|null }] — grades a whole exam in one call.
export const gradeAnswers = (answers, options = {}) =>
  api.post('/grade/', { answers }, options).then((r) => r.data)

export function apiErrorMessage(error, fallback = 'The request failed. Please retry.') {
  if (error?.response?.status === 429) {
    const wait = Number(error.response.headers?.['retry-after'])
    return `Too many requests. ${wait > 0 ? `Try again in ${Math.ceil(wait)} seconds.` : 'Please wait a moment and retry.'}`
  }
  if (error?.code === 'ECONNABORTED' || error?.code === 'ETIMEDOUT')
    return 'The request timed out. Your answers are kept; please retry.'
  if (typeof navigator !== 'undefined' && navigator.onLine === false)
    return 'You are offline. Your answers are kept; reconnect and retry.'
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (error?.response?.status >= 500)
    return 'The server is temporarily unavailable. Your answers are kept; please retry.'
  return error?.message || fallback
}

export default api
