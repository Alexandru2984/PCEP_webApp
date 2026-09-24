import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import QuestionCard from './QuestionCard'

const question = {
  id: 1,
  text: 'Question?',
  code_snippet: '',
  difficulty: 'easy',
  choices: [
    { id: 11, text: 'One' },
    { id: 12, text: 'Two' },
  ],
}

describe('QuestionCard confidence', () => {
  it('selects and clears an optional confidence rating', () => {
    const onConfidenceChange = vi.fn()
    const { rerender } = render(
      <QuestionCard
        question={question}
        questionNumber={1}
        totalQuestions={1}
        onAnswerSelect={() => {}}
        onConfidenceChange={onConfidenceChange}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Low' }))
    expect(onConfidenceChange).toHaveBeenCalledWith('low')

    rerender(
      <QuestionCard
        question={question}
        questionNumber={1}
        totalQuestions={1}
        onAnswerSelect={() => {}}
        confidence="low"
        onConfidenceChange={onConfidenceChange}
      />
    )
    expect(screen.getByRole('button', { name: 'Low' })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
    fireEvent.click(screen.getByRole('button', { name: 'Low' }))
    expect(onConfidenceChange).toHaveBeenLastCalledWith(null)
  })

  it('locks confidence controls with the answer choices', () => {
    render(
      <QuestionCard
        question={question}
        questionNumber={1}
        totalQuestions={1}
        onAnswerSelect={() => {}}
        onConfidenceChange={() => {}}
        disabled
      />
    )
    expect(screen.getByRole('button', { name: 'High' })).toBeDisabled()
  })
})
