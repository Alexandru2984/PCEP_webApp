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
})
