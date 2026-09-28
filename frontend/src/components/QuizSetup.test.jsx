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
      objective: '',
      difficulty: '',
      count: 30,
      preset: 'pcep-30-02',
    })
  })

  it('starts a quiz scoped to a syllabus objective and available difficulty', () => {
    const onStart = vi.fn()
    const stats = {
      total: 2,
      by_module: { module3: 2 },
      by_difficulty: { hard: 1, medium: 1 },
      by_objective: { 3.3: 2 },
      matrix: { module3: { easy: 0, medium: 1, hard: 1 } },
      objective_matrix: { 3.3: { easy: 0, medium: 1, hard: 1 } },
      modules: [
        {
          value: 'module3',
          label: 'Module 3 — Data Collections',
          total: 2,
          easy: 0,
          medium: 1,
          hard: 1,
        },
      ],
    }
    render(
      <QuizSetup {...baseProps} stats={stats} statsLoading={false} onStart={onStart} />
    )

    fireEvent.change(screen.getByLabelText('Module'), {
      target: { value: 'module3' },
    })
    expect(screen.queryByRole('option', { name: /1\.4 ·/ })).toBeNull()
    fireEvent.change(screen.getByLabelText('Syllabus objective'), {
      target: { value: '3.3' },
    })
    fireEvent.change(screen.getByLabelText('Difficulty'), {
      target: { value: 'hard' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Start practice with 1' }))

    expect(onStart).toHaveBeenCalledWith({
      mode: 'practice',
      module: 'module3',
      objective: '3.3',
      difficulty: 'hard',
      count: 1,
    })
  })

  it('clears an objective when the learner switches to another module', () => {
    render(<QuizSetup {...baseProps} />)
    fireEvent.change(screen.getByLabelText('Module'), {
      target: { value: 'module3' },
    })
    fireEvent.change(screen.getByLabelText('Syllabus objective'), {
      target: { value: '3.1' },
    })
    fireEvent.change(screen.getByLabelText('Module'), {
      target: { value: 'module4' },
    })
    expect(screen.getByLabelText('Syllabus objective')).toHaveValue('')
  })

  it('offers a retry when the question-bank snapshot fails', () => {
    const onRetryStats = vi.fn()
    render(
      <QuizSetup
        {...baseProps}
        statsLoading={false}
        statsError="Stats unavailable."
        onRetryStats={onRetryStats}
      />
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Stats unavailable.')
    fireEvent.click(screen.getByRole('button', { name: 'Retry snapshot' }))
    expect(onRetryStats).toHaveBeenCalledOnce()
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

  it('starts due reviews as practice or flashcards with a visible count', () => {
    const onPracticeDueReviews = vi.fn()
    const onFlashcardDueReviews = vi.fn()
    render(
      <QuizSetup
        {...baseProps}
        dueReviewCount={7}
        onPracticeDueReviews={onPracticeDueReviews}
        onFlashcardDueReviews={onFlashcardDueReviews}
      />
    )
    expect(screen.getByRole('heading', { name: 'Review what is due' })).toBeVisible()
    expect(screen.getByText('7')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Practice due questions' }))
    expect(onPracticeDueReviews).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Review due as flashcards' }))
    expect(onFlashcardDueReviews).toHaveBeenCalledOnce()
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
