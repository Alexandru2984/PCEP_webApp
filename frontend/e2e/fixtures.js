// --- Fixtures ---------------------------------------------------------------
function q(id, module, difficulty, code = 'print(1)') {
  return {
    id,
    text: 'What is the output?',
    code_snippet: code,
    module,
    difficulty,
    choices: [1, 2, 3, 4].map((n) => ({ id: id * 10 + n, text: `option ${n}` })),
  }
}

export const QUESTIONS = [
  q(1, 'module1', 'easy'),
  q(2, 'module1', 'hard', 'print(bool(0), bool(-1), bool(""), bool(" "))'),
  q(3, 'module2', 'medium'),
  q(4, 'module3', 'medium'),
]

const STATS = {
  total: 301,
  by_module: { module1: 73, module2: 73, module3: 85, module4: 70 },
  by_difficulty: { easy: 102, medium: 122, hard: 77 },
  matrix: {
    module1: { easy: 27, medium: 26, hard: 20 },
    module2: { easy: 22, medium: 34, hard: 17 },
    module3: { easy: 34, medium: 32, hard: 19 },
    module4: { easy: 19, medium: 30, hard: 21 },
  },
  modules: [
    { value: 'module1', label: 'Module 1 — Fundamentals', total: 73 },
    { value: 'module2', label: 'Module 2 — Control Flow', total: 73 },
    { value: 'module3', label: 'Module 3 — Data Collections', total: 85 },
    { value: 'module4', label: 'Module 4 — Functions & Exceptions', total: 70 },
  ],
  pass_threshold: 70,
}

const bucharestParts = Object.fromEntries(
  new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Bucharest',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
    .formatToParts(new Date())
    .map(({ type, value }) => [type, value])
)
export const DAILY_DATE = `${bucharestParts.year}-${bucharestParts.month}-${bucharestParts.day}`

// The first choice of each question is the correct one in this mock.
export const correctId = (questionId) => questionId * 10 + 1

// Intercept every /api call so the suite needs no backend.
export async function mockApi(page) {
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    if (path.endsWith('/api/stats/')) return route.fulfill({ json: STATS })
    if (path.endsWith('/api/daily/'))
      return route.fulfill({
        json: { date: DAILY_DATE, count: QUESTIONS.length, questions: QUESTIONS },
      })
    if (path.endsWith('/api/search/')) {
      const query = url.searchParams.get('q')?.toLowerCase() ?? ''
      const results = QUESTIONS.filter(
        (question) =>
          question.text.toLowerCase().includes(query) ||
          question.code_snippet.toLowerCase().includes(query)
      ).map(({ id, text, code_snippet, module, difficulty }) => ({
        id,
        text,
        code_snippet,
        module,
        difficulty,
      }))
      return route.fulfill({ json: { count: results.length, results } })
    }
    if (path.includes('/api/quiz-set')) {
      const ids = url.searchParams.get('ids')
      const questions = ids
        ? QUESTIONS.filter((question) => ids.split(',').map(Number).includes(question.id))
        : QUESTIONS
      return route.fulfill({ json: { count: questions.length, questions } })
    }

    const answer = path.match(/\/api\/questions\/(\d+)\/answer\/$/)
    if (answer) {
      const id = Number(answer[1])
      const body = req.postDataJSON()
      return route.fulfill({
        json: {
          is_correct: body.choice_id === correctId(id),
          correct_choice_id: correctId(id),
          explanation: 'this option is wrong because ...',
          correct_explanation: 'the right answer is right because ...',
        },
      })
    }

    if (path.endsWith('/api/grade/')) {
      const body = req.postDataJSON()
      const results = body.answers.map((a) => ({
        question_id: a.question_id,
        choice_id: a.choice_id,
        is_correct: a.choice_id === correctId(a.question_id),
        correct_choice_id: correctId(a.question_id),
        explanation: '',
        correct_explanation: 'the right answer is right because ...',
      }))
      return route.fulfill({
        json: {
          count: results.length,
          score: results.filter((r) => r.is_correct).length,
          results,
        },
      })
    }

    return route.fulfill({ status: 404, json: { detail: 'not mocked' } })
  })
}
