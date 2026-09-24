import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Dashboard from './Dashboard'
import { updateStudyProgress } from '../storage'

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

  it('includes mixed quiz breakdowns and excludes self-rated flashcards', () => {
    seedHistory([
      attempt({
        score: 2,
        total: 4,
        byModule: { module2: { score: 0, total: 2 }, module3: { score: 2, total: 2 } },
        byDifficulty: { easy: { score: 2, total: 4 } },
      }),
      attempt({ mode: 'flashcards', module: 'module2', score: 4, total: 4 }),
    ])
    render(<Dashboard />)
    expect(screen.getByText('Module accuracy')).toBeInTheDocument()
    expect(screen.getByText('Difficulty accuracy')).toBeInTheDocument()
    expect(screen.getByText('0%')).toBeInTheDocument()
    expect(screen.getByText(/self-rated and excluded/)).toBeInTheDocument()
  })

  it('shows accessible study momentum from graded history', () => {
    seedHistory([
      attempt({ date: '2026-09-24T10:00:00.000Z', score: 9, pct: 90 }),
      attempt({ date: '2026-09-23T10:00:00.000Z', score: 8, pct: 80 }),
      attempt({ date: '2026-09-22T10:00:00.000Z', score: 6, pct: 60 }),
      attempt({ date: '2026-09-21T10:00:00.000Z', score: 5, pct: 50 }),
    ])
    render(<Dashboard />)

    expect(screen.getByRole('heading', { name: 'Study momentum' })).toBeInTheDocument()
    expect(screen.getByText('+30 pts')).toBeInTheDocument()
    expect(
      screen.getByRole('list', {
        name: 'Graded scores from oldest to newest: 50%, 60%, 80%, 90%',
      })
    ).toBeInTheDocument()
    expect(screen.getByText(/latest 2 graded sessions average 85%/i)).toBeInTheDocument()
  })

  it('shows due review metrics and starts the scheduled drill', () => {
    const onDueReviews = vi.fn()
    const onAdaptivePractice = vi.fn()
    updateStudyProgress([
      {
        question: {
          id: 42,
          text: 'Question?',
          code_snippet: '',
          module: 'module2',
          difficulty: 'medium',
          choices: [
            { id: 421, text: 'One' },
            { id: 422, text: 'Two' },
          ],
        },
        feedback: { is_correct: false },
      },
    ])
    render(
      <Dashboard onDueReviews={onDueReviews} onAdaptivePractice={onAdaptivePractice} />
    )
    expect(screen.getByRole('heading', { name: 'Review plan' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start recommended (1)' }))
    expect(onAdaptivePractice).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Review due (1)' }))
    expect(onDueReviews).toHaveBeenCalledOnce()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Clear review schedule' }))
    expect(
      screen.queryByRole('button', { name: /Start recommended/ })
    ).not.toBeInTheDocument()
    confirm.mockRestore()
  })
})
