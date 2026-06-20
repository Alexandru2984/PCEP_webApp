import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import FeedbackBox from './FeedbackBox'

describe('FeedbackBox', () => {
  it('shows both the wrong-pick reason and the correct-answer concept on a miss', () => {
    render(
      <FeedbackBox
        feedback={{
          is_correct: false,
          explanation: 'Lists are mutable, so this raises no error.',
          correct_explanation: 'Tuples are immutable; assignment fails.',
        }}
        onNext={() => {}}
        isLast={false}
      />
    )
    expect(screen.getByText(/Why your answer is wrong/i)).toBeInTheDocument()
    expect(screen.getByText(/Lists are mutable/)).toBeInTheDocument()
    expect(screen.getByText(/Why the correct answer is right/i)).toBeInTheDocument()
    expect(screen.getByText(/Tuples are immutable/)).toBeInTheDocument()
  })

  it('shows a single explanation block on a correct answer', () => {
    render(
      <FeedbackBox
        feedback={{
          is_correct: true,
          explanation: 'Correct — integers are immutable.',
          correct_explanation: 'Correct — integers are immutable.',
        }}
        onNext={() => {}}
        isLast={false}
      />
    )
    expect(screen.getByText('Correct!')).toBeInTheDocument()
    expect(screen.queryByText(/Why the correct answer is right/i)).not.toBeInTheDocument()
  })

  it('does not duplicate the block when the correct explanation matches the pick', () => {
    render(
      <FeedbackBox
        feedback={{
          is_correct: false,
          explanation: 'Same text.',
          correct_explanation: 'Same text.',
        }}
        onNext={() => {}}
        isLast={false}
      />
    )
    expect(screen.queryByText(/Why the correct answer is right/i)).not.toBeInTheDocument()
  })

  it('labels the button differently on the last question and fires onNext', () => {
    const onNext = vi.fn()
    render(
      <FeedbackBox
        feedback={{ is_correct: true, explanation: 'ok' }}
        onNext={onNext}
        isLast
      />
    )
    const button = screen.getByRole('button', { name: /See Results/i })
    fireEvent.click(button)
    expect(onNext).toHaveBeenCalledOnce()
  })
})
