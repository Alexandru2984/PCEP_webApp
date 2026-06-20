// Adds jest-dom matchers (toBeInTheDocument, toHaveTextContent, ...) and runs
// React Testing Library's cleanup after every test so the jsdom document and
// localStorage don't leak between cases.
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
  localStorage.clear()
})
