import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import QuizSetup from './QuizSetup'

const baseProps = {
  onStart: () => {},
  stats: null,
  statsLoading: true,
  statsError: null,
}

describe('QuizSetup — practice your mistakes', () => {
  it("starts the daily challenge and shows today's completed score", () => {
    const onDailyChallenge = vi.fn()
    render(
      <QuizSetup
        {...baseProps}
        onDailyChallenge={onDailyChallenge}
        dailyCompletion={{ pct: 80 }}
      />
    )
    const button = screen.getByRole('button', { name: /Daily challenge/i })
    expect(button).toHaveTextContent('80% · Again')
    fireEvent.click(button)
    expect(onDailyChallenge).toHaveBeenCalledOnce()
  })

  it('offers an exact PCEP-30-02 full mock separately from custom exams', () => {
    const onStart = vi.fn()
    render(<QuizSetup {...baseProps} onStart={onStart} />)
    fireEvent.click(screen.getByRole('button', { name: /Exam simulation/ }))

    expect(
      screen.getByText('30 questions · 40 minutes · module mix 7 / 8 / 7 / 8')
    ).toBeVisible()
    expect(screen.getByText(/official exam also includes multiple-select/i)).toBeVisible()
    expect(screen.getByText(/Timer: 40m/)).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Start full mock' }))
    expect(onStart).toHaveBeenCalledWith({
      mode: 'exam',
      module: '',
      difficulty: '',
      count: 30,
      preset: 'pcep-30-02',
    })
  })

  it('offers the mistakes drill with a count and fires the callback', () => {
    const onPracticeMistakes = vi.fn()
    render(
      <QuizSetup
        {...baseProps}
        mistakesCount={3}
        onPracticeMistakes={onPracticeMistakes}
      />
    )
    const button = screen.getByRole('button', { name: /Practice your mistakes/i })
    expect(button).toHaveTextContent('3')
    fireEvent.click(button)
    expect(onPracticeMistakes).toHaveBeenCalledOnce()
  })

  it('hides the drill when there are no saved mistakes', () => {
    render(<QuizSetup {...baseProps} mistakesCount={0} onPracticeMistakes={() => {}} />)
    expect(
      screen.queryByRole('button', { name: /Practice your mistakes/i })
    ).not.toBeInTheDocument()
  })

  it('starts a due-review drill with a visible count', () => {
    const onPracticeDueReviews = vi.fn()
    render(
      <QuizSetup
        {...baseProps}
        dueReviewCount={7}
        onPracticeDueReviews={onPracticeDueReviews}
      />
    )
    const button = screen.getByRole('button', { name: /Review what is due/i })
    expect(button).toHaveTextContent('7')
    fireEvent.click(button)
    expect(onPracticeDueReviews).toHaveBeenCalledOnce()
  })

  it('shows why an adaptive set was recommended and starts it', () => {
    const onAdaptivePractice = vi.fn()
    render(
      <QuizSetup
        {...baseProps}
        adaptivePlan={{
          count: 12,
          signals: { due: 4, mistakes: 6, weak: 9 },
        }}
        onAdaptivePractice={onAdaptivePractice}
      />
    )
    const button = screen.getByRole('button', { name: /Adaptive practice/i })
    expect(button).toHaveTextContent('4 due · 6 mistakes · 9 below-target mastery')
    fireEvent.click(button)
    expect(onAdaptivePractice).toHaveBeenCalledOnce()
  })
})
