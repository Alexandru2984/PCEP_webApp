import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mockApi } from './fixtures'

test('analytics fails closed when the proxied script does not match SRI', async ({
  page,
}) => {
  await mockApi(page)
  let requests = 0
  await page.route('**/u/script.js', async (route) => {
    requests++
    await route.fulfill({
      contentType: 'application/javascript',
      body: 'window.pcepTamperedAnalyticsExecuted = true',
    })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Start a new quiz' })).toBeVisible()
  expect(requests).toBe(0)
  await page.getByRole('button', { name: 'Enable anonymous analytics' }).click()
  await expect.poll(() => requests).toBe(1)
  expect(await page.evaluate(() => window.pcepTamperedAnalyticsExecuted)).toBeUndefined()
})

test('privacy page exposes a reversible analytics choice', async ({ page }) => {
  await mockApi(page)
  await page.goto('/privacy/')
  await expect(page.getByRole('heading', { name: 'Privacy & data' })).toBeVisible()
  await expect(page.getByText(/Dragne Alexandru Mihai/)).toBeVisible()
  await page.getByRole('button', { name: 'No thanks' }).first().click()
  await expect(page.getByText(/Anonymous analytics: denied/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Return to PCEP Quiz' })).toBeVisible()
  const { violations } = await new AxeBuilder({ page }).analyze()
  expect(violations).toEqual([])
})

test('install suggestion is actionable, accessible and honest about offline use', async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 800 })
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('heading', { name: 'Start a new quiz' }).waitFor()
  const canceled = await page.evaluate(() => {
    window.pcepInstallPromptCalls = 0
    const event = new Event('beforeinstallprompt', { cancelable: true })
    Object.defineProperties(event, {
      prompt: {
        value: async () => {
          window.pcepInstallPromptCalls += 1
        },
      },
      userChoice: { value: Promise.resolve({ outcome: 'accepted' }) },
    })
    window.dispatchEvent(event)
    return event.defaultPrevented
  })

  expect(canceled).toBe(true)
  await expect(page.getByRole('heading', { name: 'Install PCEP Quiz' })).toBeVisible()
  await expect(
    page.getByText(/answer feedback still require a connection/i)
  ).toBeVisible()
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  ).toBe(true)
  const { violations } = await new AxeBuilder({ page }).analyze()
  expect(violations).toEqual([])

  await page.getByRole('button', { name: 'Install app' }).click()
  await expect.poll(() => page.evaluate(() => window.pcepInstallPromptCalls)).toBe(1)
  await expect(page.getByRole('heading', { name: 'Install PCEP Quiz' })).toHaveCount(0)
})

test('offline shell survives reload without caching API or feedback', async ({
  page,
  context,
}) => {
  await mockApi(page)
  await page.goto('/')
  await page.evaluate(() => navigator.serviceWorker.ready)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Start a new quiz' })).toBeVisible()
  const urls = await page.evaluate(async () => {
    const result = []
    for (const name of await caches.keys())
      for (const request of await (await caches.open(name)).keys())
        result.push(new URL(request.url).pathname)
    return result
  })
  expect(urls).toContain('/index.html')
  expect(urls.some((url) => /^\/(?:api|admin|practice|u)\//.test(url))).toBe(false)
  await page.unroute('**/api/**')
  await context.setOffline(true)
  await page.reload()
  await expect(
    page.getByRole('status').filter({ hasText: 'You are offline. New quizzes' })
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Start a new quiz' })).toBeVisible()
  await page.getByRole('button', { name: /Start practice/ }).click()
  await expect(page.getByRole('button', { name: 'Back to setup' })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('offline')
})
