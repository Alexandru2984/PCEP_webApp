import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Dashboard from './Dashboard'

// Dashboard reads attempt history straight from localStorage on mount.
function seedHistory(attempts) {
  localStorage.setItem('pcep.history', JSON.stringify(attempts))
}

const attempt = (overrides) => ({
  date: new Date().toISOString(),
  mode: 'practice',
  module: '',
  difficulty: '',
  score: 0,
  total: 10,
  pct: 0,
  elapsedMs: 1000,
  bestStreak: 0,
  ...overrides,
})

describe('Dashboard', () => {
  it('shows the empty state with no attempts', () => {
    render(<Dashboard />)
    expect(screen.getByText(/No attempts yet/i)).toBeInTheDocument()
  })

  it('drills the module from its mastery row', () => {
    const onDrill = vi.fn()
    seedHistory([attempt({ module: 'module2', score: 1, total: 4, pct: 25 })])
    render(<Dashboard onDrill={onDrill} />)

    // Only one module was attempted, so there is exactly one "Drill" control.
    fireEvent.click(screen.getByRole('button', { name: 'Drill' }))
    expect(onDrill).toHaveBeenCalledWith('module2')
  })

  it('omits the drill control when no callback is provided', () => {
    seedHistory([attempt({ module: 'module2', score: 1, total: 4, pct: 25 })])
    render(<Dashboard />)
    expect(screen.queryByRole('button', { name: 'Drill' })).not.toBeInTheDocument()
  })
})
