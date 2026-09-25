import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

  it('keeps flashcard self-ratings separate from graded pass semantics', async () => {
    const clipboard = vi.fn().mockResolvedValue(undefined)
    const descriptor = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: clipboard },
    })
    const items = [
      reviewItem(1, { correct: true, responseMs: undefined }),
      reviewItem(2, { correct: false, responseMs: undefined }),
    ]
    items[1].pickedChoiceId = null
    items[1].feedback.explanation = ''
    try {
      render(
        <ReviewScreen
          items={items}
          score={1}
          total={2}
          mode="flashcards"
          onRestart={vi.fn()}
        />
      )

      expect(
        screen.getByRole('heading', { name: 'Flashcards complete' }).nextElementSibling
      ).toHaveTextContent('1 of 2 marked “Got it”')
      expect(screen.queryByText(/PCEP threshold/)).toBeNull()
      expect(screen.queryByRole('button', { name: /Needs review/ })).toBeNull()
      expect(screen.getByRole('button', { name: 'Review later (1)' })).toHaveAttribute(
        'aria-pressed',
        'true'
      )
      expect(screen.getByText('Review later', { selector: 'span' })).toBeVisible()

      fireEvent.click(screen.getByRole('button', { name: 'Copy result' }))
      await waitFor(() => expect(clipboard).toHaveBeenCalledOnce())
      expect(clipboard.mock.calls[0][0]).toContain(
        'reviewed 2 PCEP flashcards and marked 1 (50%) “Got it”'
      )
      expect(screen.getByRole('status')).toHaveTextContent('copied to clipboard')
    } finally {
      if (descriptor) Object.defineProperty(navigator, 'clipboard', descriptor)
      else delete navigator.clipboard
    }
  })

  it('identifies and shares a completed full mock without answer details', async () => {
    const clipboard = vi.fn().mockResolvedValue(undefined)
    const descriptor = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: clipboard },
    })
    try {
      render(
        <ReviewScreen
          items={[reviewItem(1, { correct: false, responseMs: 1000 })]}
          score={0}
          total={1}
          mode="exam"
          preset="pcep-30-02"
          onRestart={vi.fn()}
        />
      )
      expect(screen.getByText('Full PCEP-30-02 mock')).toBeVisible()
      fireEvent.click(screen.getByRole('button', { name: 'Copy result' }))
      await waitFor(() => expect(clipboard).toHaveBeenCalledOnce())
      expect(clipboard.mock.calls[0][0]).toContain('on a full PCEP-30-02 mock')
      expect(clipboard.mock.calls[0][0]).not.toMatch(/choice|explanation|Question 1/)
    } finally {
      if (descriptor) Object.defineProperty(navigator, 'clipboard', descriptor)
      else delete navigator.clipboard
    }
  })
})
