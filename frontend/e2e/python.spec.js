import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mockApi } from './fixtures'

test('real Python handles errors bounded output and timeout recovery', async ({
  page,
  context,
}) => {
  test.setTimeout(60_000)
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: /Start practice/ }).click()
  const run = page.getByRole('button', { name: 'Run', exact: true })
  await run.click()
  const output = page.getByRole('region', { name: 'Python output' })
  await expect(output).toContainText('1', { timeout: 35_000 })
  await page.getByRole('button', { name: 'Edit', exact: true }).click()
  const editor = page.getByRole('textbox', { name: 'Editable Python code' })
  await editor.fill('print(')
  await editor.press('Control+Enter')
  await expect(output).toContainText('SyntaxError')
  await editor.fill('1 / 0')
  await run.click()
  await expect(output).toContainText('ZeroDivisionError')
  await editor.fill('print("x" * 20000)')
  await run.click()
  await expect(output).toContainText('10,000-character limit')
  expect((await output.innerText()).length).toBeLessThan(10200)
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  ).toBe(true)
  await editor.fill('while True: pass')
  await run.click()
  await expect(output).toContainText('Execution timed out', { timeout: 12_000 })
  await editor.fill('print("recovered")')
  await run.click()
  await expect(output).toContainText('recovered', { timeout: 35_000 })
  await editor.fill('pass')
  await run.click()
  await expect(output).toContainText('(no output)')
  const { violations } = await new AxeBuilder({ page }).analyze()
  expect(
    violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) }))
  ).toEqual([])
  await page.evaluate(() => navigator.serviceWorker.ready)
  await context.setOffline(true)
  await editor.fill('while True: pass')
  await run.click()
  await expect(output).toContainText('Execution timed out', { timeout: 12_000 })
  await editor.fill('print("offline recovery")')
  await run.click()
  await expect(output).toContainText('offline recovery', { timeout: 35_000 })
})
