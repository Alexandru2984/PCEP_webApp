import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mockApi } from './fixtures'

async function accessible(page) {
  const { violations } = await new AxeBuilder({ page }).analyze()
  expect(
    violations.map((v) => ({ rule: v.id, nodes: v.nodes.map((n) => n.target) }))
  ).toEqual([])
}
async function fits(page) {
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  ).toBe(true)
}

async function fitsEveryWidth(page) {
  for (const width of [1440, 1280, 1024, 768, 430, 390, 360]) {
    await page.setViewportSize({ width, height: 900 })
    await fits(page)
  }
}

test('mobile exam navigator has touch targets and keyboard focus follows questions', async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 800 })
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: /Exam simulation/ }).click()
  await page.getByRole('button', { name: /Start exam/ }).click()
  const navigator = page.getByRole('button', { name: /Question navigator/ })
  await expect(navigator).toHaveAttribute('aria-expanded', 'false')
  await navigator.click()
  const cells = page.getByRole('button', { name: /Go to question/ })
  for (const cell of await cells.all()) {
    const box = await cell.boundingBox()
    expect(box.width).toBeGreaterThanOrEqual(44)
    expect(box.height).toBeGreaterThanOrEqual(44)
  }
  await page.getByRole('button', { name: /option 1/ }).click()
  await page.getByRole('button', { name: 'Next unanswered' }).click()
  await expect(
    page.getByRole('button', { name: 'Go to question 2', exact: true })
  ).toHaveAttribute('aria-current', 'true')
  await expect(page.getByRole('heading', { name: 'What is the output?' })).toBeFocused()
  await page.getByRole('button', { name: 'Submit exam', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Yes, submit' })).toBeFocused()
  await page.getByRole('button', { name: 'Keep going' }).click()
  await expect(
    page.getByRole('button', { name: 'Submit exam', exact: true })
  ).toBeFocused()
  await fits(page)
})

for (const theme of ['light', 'dark']) {
  test(`${theme} study screens pass axe and fit seven viewport widths`, async ({
    page,
  }) => {
    await mockApi(page)
    await page.addInitScript(
      (value) => localStorage.setItem('pcep.theme', JSON.stringify(value)),
      theme
    )
    for (const width of [1440, 1280, 1024, 768, 430, 390, 360]) {
      await page.setViewportSize({ width, height: 900 })
      await page.goto('/')
      await page.getByRole('heading', { name: 'Start a new quiz' }).waitFor()
      await fits(page)
    }
    await expect(page.locator('html')).toHaveClass(theme === 'dark' ? /dark/ : /^$/)
    await accessible(page)
    await page.getByRole('button', { name: /Start practice/ }).click()
    await page.getByRole('button', { name: /option 1/ }).waitFor()
    await fitsEveryWidth(page)
    await accessible(page)
    await page.getByRole('button', { name: /option 1/ }).click()
    await page.getByRole('button', { name: /Next Question/ }).waitFor()
    await accessible(page)
    await page.reload()
    await page.getByRole('button', { name: /Exam simulation/ }).click()
    await page.getByRole('button', { name: /Start exam/ }).click()
    await page.getByRole('button', { name: /Question navigator/ }).click()
    await fitsEveryWidth(page)
    await accessible(page)
    await page.getByRole('button', { name: 'Submit exam', exact: true }).click()
    await page.getByRole('button', { name: 'Yes, submit' }).click()
    await page.getByRole('heading', { name: 'Quiz complete' }).waitFor()
    await fitsEveryWidth(page)
    await accessible(page)
    await page.getByRole('button', { name: 'New quiz' }).click()
    await page.getByRole('button', { name: /Progress/ }).click()
    await page.getByRole('heading', { name: 'Your progress' }).waitFor()
    await fitsEveryWidth(page)
    await accessible(page)
    await page.getByRole('button', { name: 'New quiz', exact: true }).click()
    await page.getByRole('button', { name: /Flashcards/ }).click()
    await page.getByRole('button', { name: /Start flashcards/ }).click()
    await page.getByRole('button', { name: /Reveal answer/ }).waitFor()
    await fitsEveryWidth(page)
    await accessible(page)
    await page.getByRole('button', { name: /Reveal answer/ }).click()
    await page.getByRole('button', { name: 'Got it' }).waitFor()
    await accessible(page)
  })
}

test('offline and failed storage warnings explain recovery', async ({
  page,
  context,
}) => {
  await mockApi(page)
  await page.goto('/')
  await context.setOffline(true)
  await expect(page.getByText(/You are offline/)).toBeVisible()
  await context.setOffline(false)
  await expect(page.getByText(/You are offline/)).toHaveCount(0)
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('pcep-storage-warning')))
  await expect(page.getByRole('alert')).toContainText('Progress could not be saved')
})
