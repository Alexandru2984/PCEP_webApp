// --- Fixtures ---------------------------------------------------------------
function q(id, module, difficulty, code = 'print(1)') {
  const objective = {
    module1: '1.4',
    module2: '2.1',
    module3: '3.1',
    module4: '4.1',
  }[module]
  return {
    id,
    text: 'What is the output?',
    code_snippet: code,
    module,
    objective,
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

export const FULL_MOCK_QUESTIONS = [
  ...Array.from({ length: 7 }, (_, index) => q(101 + index, 'module1', 'medium', '')),
  ...Array.from({ length: 8 }, (_, index) => q(201 + index, 'module2', 'medium', '')),
  ...Array.from({ length: 7 }, (_, index) => q(301 + index, 'module3', 'medium', '')),
  ...Array.from({ length: 8 }, (_, index) => q(401 + index, 'module4', 'medium', '')),
]

const STATS = {
  total: 308,
  by_module: { module1: 80, module2: 73, module3: 85, module4: 70 },
  by_difficulty: { easy: 106, medium: 125, hard: 77 },
  by_objective: {
    1.1: 3,
    1.2: 4,
    1.3: 15,
    1.4: 49,
    1.5: 9,
    2.1: 28,
    2.2: 45,
    3.1: 40,
    3.2: 8,
    3.3: 16,
    3.4: 21,
    4.1: 19,
    4.2: 32,
    4.3: 7,
    4.4: 12,
  },
  objective_matrix: {
    1.1: { easy: 2, medium: 1, hard: 0 },
    1.2: { easy: 2, medium: 2, hard: 0 },
    1.3: { easy: 3, medium: 9, hard: 3 },
    1.4: { easy: 17, medium: 16, hard: 16 },
    1.5: { easy: 7, medium: 1, hard: 1 },
    2.1: { easy: 8, medium: 14, hard: 6 },
    2.2: { easy: 14, medium: 20, hard: 11 },
    3.1: { easy: 13, medium: 15, hard: 12 },
    3.2: { easy: 2, medium: 4, hard: 2 },
    3.3: { easy: 9, medium: 4, hard: 3 },
    3.4: { easy: 10, medium: 9, hard: 2 },
    4.1: { easy: 7, medium: 7, hard: 5 },
    4.2: { easy: 5, medium: 16, hard: 11 },
    4.3: { easy: 3, medium: 1, hard: 3 },
    4.4: { easy: 4, medium: 6, hard: 2 },
  },
  matrix: {
    module1: { easy: 31, medium: 29, hard: 20 },
    module2: { easy: 22, medium: 34, hard: 17 },
    module3: { easy: 34, medium: 32, hard: 19 },
    module4: { easy: 19, medium: 30, hard: 21 },
  },
  modules: [
    {
      value: 'module1',
      label: 'Module 1 — Fundamentals',
      total: 80,
      easy: 31,
      medium: 29,
      hard: 20,
    },
    {
      value: 'module2',
      label: 'Module 2 — Control Flow',
      total: 73,
      easy: 22,
      medium: 34,
      hard: 17,
    },
    {
      value: 'module3',
      label: 'Module 3 — Data Collections',
      total: 85,
      easy: 34,
      medium: 32,
      hard: 19,
    },
    {
      value: 'module4',
      label: 'Module 4 — Functions & Exceptions',
      total: 70,
      easy: 19,
      medium: 30,
      hard: 21,
    },
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
export async function mockApi(page, { statsFailures = 0 } = {}) {
  let statsAttempts = 0
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    if (path.endsWith('/api/stats/')) {
      statsAttempts++
      if (statsAttempts <= statsFailures)
        return route.fulfill({ status: 503, json: { detail: 'Stats unavailable.' } })
      return route.fulfill({ json: STATS })
    }
    if (path.endsWith('/api/daily/'))
      return route.fulfill({
        json: { date: DAILY_DATE, count: QUESTIONS.length, questions: QUESTIONS },
      })
    if (path.endsWith('/api/search/')) {
      const query = url.searchParams.get('q')?.toLowerCase() ?? ''
      const module = url.searchParams.get('module')
      const objective = url.searchParams.get('objective')
      const difficulty = url.searchParams.get('difficulty')
      const results = QUESTIONS.filter(
        (question) =>
          (!module || question.module === module) &&
          (!objective || question.objective === objective) &&
          (!difficulty || question.difficulty === difficulty) &&
          (question.text.toLowerCase().includes(query) ||
            question.code_snippet.toLowerCase().includes(query))
      ).map(({ id, text, code_snippet, module, objective, difficulty }) => ({
        id,
        text,
        code_snippet,
        module,
        objective,
        difficulty,
      }))
      return route.fulfill({ json: { count: results.length, results } })
    }
    if (path.includes('/api/quiz-set')) {
      if (url.searchParams.get('preset') === 'pcep-30-02')
        return route.fulfill({
          json: {
            count: FULL_MOCK_QUESTIONS.length,
            preset: 'pcep-30-02',
            questions: FULL_MOCK_QUESTIONS,
          },
        })
      const ids = url.searchParams.get('ids')
      const module = url.searchParams.get('module')
      const objective = url.searchParams.get('objective')
      const difficulty = url.searchParams.get('difficulty')
      const questions = (
        ids
          ? QUESTIONS.filter((question) =>
              ids.split(',').map(Number).includes(question.id)
            )
          : QUESTIONS
      ).filter(
        (question) =>
          (!module || question.module === module) &&
          (!objective || question.objective === objective) &&
          (!difficulty || question.difficulty === difficulty)
      )
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
