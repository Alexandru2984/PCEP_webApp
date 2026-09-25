import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ReviewScreen from './ReviewScreen'

function reviewItem(id, { correct, confidence, responseMs }) {
  return {
    question: {
      id,
      text: `Question ${id}`,
      code_snippet: '',
      module: 'module1',
      difficulty: 'medium',
      choices: [
        { id: id * 10 + 1, text: 'Correct option' },
        { id: id * 10 + 2, text: 'Wrong option' },
      ],
    },
    pickedChoiceId: id * 10 + (correct ? 1 : 2),
    confidence,
    responseMs,
    feedback: {
      is_correct: correct,
      correct_choice_id: id * 10 + 1,
      explanation: correct ? 'Correct.' : 'That option is wrong.',
      correct_explanation: 'This is why the correct answer works.',
    },
  }
}

describe('ReviewScreen focused review', () => {
  it('starts with misses and low-confidence correct answers, including context', () => {
    const items = [
      reviewItem(1, { correct: false, confidence: 'high', responseMs: 9000 }),
      reviewItem(2, { correct: true, confidence: 'low', responseMs: 3200 }),
      reviewItem(3, { correct: true, confidence: 'medium', responseMs: 2000 }),
    ]
    render(
      <ReviewScreen
        items={items}
        score={2}
        total={3}
        onRestart={vi.fn()}
        streakStats={{ best: 2 }}
      />
    )

    expect(screen.getByRole('button', { name: 'Needs review (2)' })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
    const list = screen.getByRole('list', { name: 'Question review' })
    expect(within(list).getByText('Question 1')).toBeVisible()
    expect(within(list).getByText('Question 2')).toBeVisible()
    expect(within(list).queryByText('Question 3')).toBeNull()
    expect(within(list).getByText('Low confidence')).toBeVisible()
    expect(within(list).getByText('3s response')).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: 'Wrong only (1)' }))
    expect(within(list).getByText('Question 1')).toBeVisible()
    expect(within(list).queryByText('Question 2')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'All (3)' }))
    expect(within(list).getByText('Question 3')).toBeVisible()
  })
})
