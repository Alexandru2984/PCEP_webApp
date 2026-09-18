import { test, expect } from '@playwright/test'
import { mockApi } from './fixtures'

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
