// --- Fixtures ---------------------------------------------------------------
function q(id, module, difficulty) {
  return {
    id,
    text: 'What is the output?',
    code_snippet: 'print(1)',
    module,
    difficulty,
    choices: [1, 2, 3, 4].map((n) => ({ id: id * 10 + n, text: `option ${n}` })),
  }
}

export const QUESTIONS = [
  q(1, 'module1', 'easy'),
  q(2, 'module1', 'hard'),
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

// The first choice of each question is the correct one in this mock.
export const correctId = (questionId) => questionId * 10 + 1

// Intercept every /api call so the suite needs no backend.
export async function mockApi(page) {
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (path.endsWith('/api/stats/')) return route.fulfill({ json: STATS })
    if (path.includes('/api/quiz-set'))
      return route.fulfill({ json: { count: QUESTIONS.length, questions: QUESTIONS } })

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
