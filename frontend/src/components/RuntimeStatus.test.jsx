import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import RuntimeStatus from './RuntimeStatus'
import ErrorBoundary from './ErrorBoundary'

describe('application recovery', () => {
  it('announces failed persistence', () => {
    render(<RuntimeStatus />)
    fireEvent(window, new CustomEvent('pcep-storage-warning'))
    expect(screen.getByRole('alert')).toHaveTextContent('Progress could not be saved')
  })
  it('offers reload after a lazy screen/render failure', () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    const expectedError = (event) => {
      if (event.error?.message === 'Failed to fetch dynamically imported module')
        event.preventDefault()
    }
    window.addEventListener('error', expectedError)
    function BrokenScreen() {
      throw new Error('Failed to fetch dynamically imported module')
    }
    try {
      render(
        <ErrorBoundary>
          <BrokenScreen />
        </ErrorBoundary>
      )
      expect(screen.getByRole('alert')).toHaveTextContent('This screen could not load')
      expect(screen.getByRole('button', { name: 'Reload app' })).toBeVisible()
      expect(screen.getByRole('alert')).toHaveTextContent(
        'An unsubmitted session may be lost'
      )
    } finally {
      window.removeEventListener('error', expectedError)
      errors.mockRestore()
    }
  })
})
