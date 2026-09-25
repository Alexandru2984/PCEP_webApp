import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import RuntimeStatus from './RuntimeStatus'
import ErrorBoundary from './ErrorBoundary'

describe('application recovery', () => {
  it('announces failed persistence', () => {
    render(<RuntimeStatus />)
    fireEvent(window, new CustomEvent('pcep-storage-warning'))
    expect(screen.getByRole('alert')).toHaveTextContent('Progress could not be saved')
  })
  it('announces a worker update without reloading an active session', () => {
    const serviceWorker = new EventTarget()
    serviceWorker.controller = {}
    const previous = Object.getOwnPropertyDescriptor(navigator, 'serviceWorker')
    Object.defineProperty(navigator, 'serviceWorker', {
      value: serviceWorker,
      configurable: true,
    })
    try {
      render(<RuntimeStatus />)
      fireEvent(serviceWorker, new Event('controllerchange'))
      expect(screen.getByRole('status')).toHaveTextContent(
        'Finish your session before reloading'
      )
      expect(screen.getByRole('button', { name: 'Reload app' })).toBeVisible()
    } finally {
      if (previous) Object.defineProperty(navigator, 'serviceWorker', previous)
      else delete navigator.serviceWorker
    }
  })
  it('offers the browser install prompt with accurate offline scope', async () => {
    const prompt = vi.fn().mockResolvedValue(undefined)
    const event = new Event('beforeinstallprompt', { cancelable: true })
    Object.defineProperties(event, {
      prompt: { value: prompt },
      userChoice: { value: Promise.resolve({ outcome: 'accepted' }) },
    })
    render(<RuntimeStatus />)

    fireEvent(window, event)
    expect(event.defaultPrevented).toBe(true)
    expect(screen.getByRole('heading', { name: 'Install PCEP Quiz' })).toBeVisible()
    expect(screen.getByText(/answer feedback still require a connection/i)).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: 'Install app' }))
    await waitFor(() => expect(prompt).toHaveBeenCalledOnce())
    expect(screen.queryByRole('heading', { name: 'Install PCEP Quiz' })).toBeNull()
  })
  it('keeps a dismissed install suggestion hidden for the tab session', () => {
    const installEvent = () => {
      const event = new Event('beforeinstallprompt', { cancelable: true })
      Object.defineProperties(event, {
        prompt: { value: vi.fn() },
        userChoice: { value: Promise.resolve({ outcome: 'dismissed' }) },
      })
      return event
    }
    const view = render(<RuntimeStatus />)
    fireEvent(window, installEvent())
    fireEvent.click(screen.getByRole('button', { name: 'Not now' }))
    view.unmount()

    render(<RuntimeStatus />)
    fireEvent(window, installEvent())
    expect(screen.queryByRole('heading', { name: 'Install PCEP Quiz' })).toBeNull()
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
