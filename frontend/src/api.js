import axios from 'axios'

// In production, nginx proxies /api to Django. In dev, Vite proxies (see vite.config.js).
const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

export const fetchQuizSet = (count = 30) =>
  api.get(`/quiz-set/?count=${count}`).then((r) => r.data)

export const submitAnswer = (questionId, choiceId) =>
  api
    .post(`/questions/${questionId}/answer/`, { choice_id: choiceId })
    .then((r) => r.data)

export default api
