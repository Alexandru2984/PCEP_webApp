import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { Buffer } from 'node:buffer'

import { QUESTIONS, correctId, mockApi } from './fixtures'

// --- Tests ------------------------------------------------------------------
test('setup screen loads and shows the question-bank snapshot', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /Start a new quiz/i })).toBeVisible()
  await expect(page.getByText('Question-bank snapshot')).toBeVisible()
})

test('practice run produces a report with a one-click module drill', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: '10', exact: true }).click()
  await page.getByRole('button', { name: /Start practice/ }).click()
  await page.getByText(/Tip: press/).waitFor()

  // Answer every question with option 2 — wrong in the mock — so the report
  // has a sub-70% module and surfaces the focus-area drill.
  for (let i = 0; i < QUESTIONS.length; i++) {
    await page.keyboard.press('2')
    const next = page.getByRole('button', { name: /Next Question|See Results/ })
    await next.waitFor()
    await page.keyboard.press('Enter')
    if (i < QUESTIONS.length - 1) await next.waitFor({ state: 'detached' })
  }

  await expect(page.getByText('Performance breakdown')).toBeVisible()
  const drill = page.getByRole('button', { name: /Practice this module/i })
  await expect(drill).toBeVisible()
  await drill.click()
  // Drilling launches a fresh practice session.
  await expect(page.getByText(/Tip: press/)).toBeVisible()
})

test('new quiz returns to setup after a drill launched from progress', async ({
  page,
}) => {
  await mockApi(page)
  await page.addInitScript(() => {
    localStorage.setItem(
      'pcep.history',
      JSON.stringify([
        {
          date: new Date().toISOString(),
          mode: 'practice',
          module: 'module1',
          difficulty: '',
          score: 5,
          total: 10,
          pct: 50,
          elapsedMs: 100_000,
          bestStreak: 2,
        },
      ])
    )
  })
  await page.goto('/')
  await page.getByRole('button', { name: /Progress/ }).click()
  await page.getByRole('button', { name: 'Drill' }).click()

  for (let i = 0; i < QUESTIONS.length; i++) {
    await page.getByRole('button', { name: /option 1/ }).click()
    await page.getByRole('button', { name: /Next Question|See Results/ }).click()
  }
  await page.getByRole('button', { name: 'New quiz' }).click()

  await expect(page.getByRole('heading', { name: 'Start a new quiz' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Your progress' })).toHaveCount(0)
})

test('flashcards reveal shows the answer and self-marking advances the deck', async ({
  page,
}) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: /Flashcards/ }).click()
  await page.getByRole('button', { name: /Start flashcards/ }).click()

  await page.getByRole('button', { name: /Reveal answer/i }).click()
  await expect(page.getByText(/the right answer is right because/i)).toBeVisible()

  await page.getByRole('button', { name: /Got it/i }).click()
  // Advancing resets the card, so the reveal control is back for card 2.
  await expect(page.getByRole('button', { name: /Reveal answer/i })).toBeVisible()
})

test('exam preserves answers through a throttled grading request and retries once', async ({
  page,
}) => {
  await mockApi(page)
  const submissions = []
  await page.route('**/api/grade/', async (route) => {
    const answers = route.request().postDataJSON().answers
    submissions.push(answers)
    if (submissions.length === 1)
      return route.fulfill({
        status: 429,
        headers: { 'Retry-After': '1' },
        json: { detail: 'Throttled' },
      })
    const results = answers.map((a) => ({
      ...a,
      is_correct: a.choice_id === correctId(a.question_id),
      correct_choice_id: correctId(a.question_id),
      explanation: '',
      correct_explanation: 'Review this concept.',
    }))
    return route.fulfill({
      json: { count: results.length, score: results.length, results },
    })
  })
  await page.goto('/')
  await page.getByRole('button', { name: /Exam simulation/ }).click()
  await page.getByRole('button', { name: /Start exam/ }).click()
  for (let i = 0; i < QUESTIONS.length; i++) {
    await page.getByRole('button', { name: /option 1/ }).click()
    if (i < QUESTIONS.length - 1)
      await page.getByRole('button', { name: /Next →/ }).click()
  }
  await page.getByRole('button', { name: 'Submit exam', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Too many requests')
  await expect(page.getByRole('button', { name: /option 1/ })).toHaveAttribute(
    'aria-pressed',
    'true'
  )
  await page.getByRole('button', { name: 'Retry grading' }).click()
  await expect(page.getByRole('heading', { name: 'Quiz complete' })).toBeVisible()
  expect(submissions).toHaveLength(2)
  expect(submissions[1]).toEqual(submissions[0])
})

test('bookmarks persist across reload and start a targeted drill', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: /Start practice/ }).click()
  await page.getByRole('button', { name: '☆ Bookmark' }).click()
  await page.reload()
  const drill = page.getByRole('button', { name: /Practice bookmarks/ })
  await expect(drill).toBeVisible()
  await drill.click()
  await expect(page.getByRole('button', { name: '★ Bookmarked' })).toBeVisible()
})

test('missed questions become due reviews and launch adaptive practice', async ({
  page,
}) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: /Start practice/ }).click()
  for (let i = 0; i < QUESTIONS.length; i++) {
    await page.getByRole('button', { name: /option 2/ }).click()
    await page.getByRole('button', { name: /Next Question|See Results/ }).click()
  }
  await expect(page.getByRole('heading', { name: 'Quiz complete' })).toBeVisible()
  const study = await page.evaluate(
    () => JSON.parse(localStorage.getItem('pcep.progress')).data.study
  )
  expect(study).toHaveLength(QUESTIONS.length)
  expect(JSON.stringify(study)).not.toContain('choice')
  expect(JSON.stringify(study)).not.toContain('is_correct')

  await page.reload()
  await page.setViewportSize({ width: 390, height: 844 })
  const due = page.getByRole('button', { name: /Review what is due/ })
  await expect(due).toContainText(String(QUESTIONS.length))
  const recommended = page.getByRole('button', { name: /Adaptive practice/ })
  await expect(recommended).toContainText(String(QUESTIONS.length))
  const { violations } = await new AxeBuilder({ page }).analyze()
  expect(violations.map((violation) => violation.id)).toEqual([])
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  ).toBe(true)
  const requestPromise = page.waitForRequest((request) => {
    const url = new URL(request.url())
    return url.pathname.endsWith('/api/quiz-set/') && url.searchParams.has('ids')
  })
  await recommended.click()
  const request = await requestPromise
  const params = new URL(request.url()).searchParams
  expect(params.get('count')).toBe(String(QUESTIONS.length))
  expect(
    params
      .get('ids')
      .split(',')
      .map(Number)
      .sort((a, b) => a - b)
  ).toEqual(QUESTIONS.map((question) => question.id))
  await expect(page.getByText(/Tip: press/)).toBeVisible()
})

test('an interrupted exam restores answers, flags, position and deadline', async ({
  page,
}) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: /Exam simulation/ }).click()
  await page.getByRole('button', { name: /Start exam/ }).click()
  await page.getByRole('button', { name: /option 1/ }).click()
  await page.getByRole('button', { name: '⚐ Flag' }).click()
  await page.getByRole('button', { name: 'Next →' }).click()
  await expect
    .poll(() =>
      page.evaluate(() => JSON.parse(localStorage.getItem('pcep.activeExam'))?.data)
    )
    .toMatchObject({ index: 1, answers: { 1: 11 }, flagged: [1] })

  const raw = await page.evaluate(() => localStorage.getItem('pcep.activeExam'))
  expect(raw).not.toContain('is_correct')
  expect(raw).not.toContain('correct_choice_id')
  expect(raw).not.toContain('explanation')

  await page.reload()
  await expect(page.getByRole('heading', { name: 'Resume saved exam' })).toBeVisible()
  await expect(page.getByText('1/4 answered.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Progress' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Start practice/ })).toHaveCount(0)
  const { violations } = await new AxeBuilder({ page }).analyze()
  expect(violations.map((violation) => violation.id)).toEqual([])
  for (const width of [390, 360]) {
    await page.setViewportSize({ width, height: 844 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
    ).toBe(true)
  }
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.getByRole('button', { name: 'Resume exam' }).click()
  await expect(page.getByRole('button', { name: /Go to question 2/ })).toHaveAttribute(
    'aria-current',
    'true'
  )
  await page.getByRole('button', { name: /Go to question 1/ }).click()
  await expect(page.getByRole('button', { name: /option 1/ })).toHaveAttribute(
    'aria-pressed',
    'true'
  )
  await expect(page.getByRole('button', { name: '⚑ Flagged' })).toHaveAttribute(
    'aria-pressed',
    'true'
  )
})

test('progress backup exports and imports with a preview', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: /Progress/ }).click()
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export backup' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/^pcep-progress-/)
  const backup = {
    type: 'pcep-progress',
    version: 1,
    mistakes: [],
    bookmarks: [],
    history: [
      {
        date: '2026-09-18T12:00:00Z',
        mode: 'practice',
        module: 'module2',
        difficulty: 'easy',
        score: 8,
        total: 10,
        pct: 80,
        elapsedMs: 10000,
        bestStreak: 2,
      },
    ],
  }
  await page.getByLabel('Progress backup file').setInputFiles({
    name: 'backup.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(backup)),
  })
  await expect(page.getByText(/Merge 1 attempts/)).toBeVisible()
  await page.getByRole('button', { name: 'Merge backup' }).click()
  await expect(page.getByRole('heading', { name: 'Your progress' })).toBeVisible()
  await expect(
    page.getByText('Backup merged. Existing progress was preserved.')
  ).toBeVisible()
})
