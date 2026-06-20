import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import FlashcardView from './FlashcardView'
import { submitAnswer } from '../api'

vi.mock('../api', () => ({ submitAnswer: vi.fn() }))

const card = (id, choiceIds) => ({
  id,
  text: 'What is the output?',
  code_snippet: 'print(1)',
  module: 'module1',
  difficulty: 'easy',
  choices: choiceIds.map((cid) => ({ id: cid, text: `choice ${cid}` })),
})

beforeEach(() => vi.clearAllMocks())

describe('FlashcardView', () => {
  it('reveals the answer from the API and records self-marks across the deck', async () => {
    submitAnswer
      .mockResolvedValueOnce({
        correct_choice_id: 2,
        correct_explanation: 'first concept',
      })
      .mockResolvedValueOnce({
        correct_choice_id: 3,
        correct_explanation: 'second concept',
      })
    const onFinish = vi.fn()
    render(
      <FlashcardView
        questions={[card(10, [1, 2]), card(20, [3, 4])]}
        onFinish={onFinish}
        onQuit={() => {}}
      />
    )

    // Card 1: flip, then mark "Got it".
    fireEvent.click(screen.getByRole('button', { name: /Reveal answer/i }))
    expect(await screen.findByText(/first concept/)).toBeInTheDocument()
    // The reveal POSTs a throwaway guess (the first choice) to learn the key.
    expect(submitAnswer).toHaveBeenCalledWith(10, 1)
    fireEvent.click(screen.getByRole('button', { name: /Got it/i }))

    // Card 2: flip (proves we advanced), then mark "Review later".
    fireEvent.click(screen.getByRole('button', { name: /Reveal answer/i }))
    expect(await screen.findByText(/second concept/)).toBeInTheDocument()
    expect(submitAnswer).toHaveBeenLastCalledWith(20, 3)
    fireEvent.click(screen.getByRole('button', { name: /Review later/i }))

    expect(onFinish).toHaveBeenCalledOnce()
    const items = onFinish.mock.calls[0][0]
    expect(items).toHaveLength(2)
    expect(items[0]).toMatchObject({
      question: { id: 10 },
      feedback: { is_correct: true, correct_choice_id: 2 },
    })
    expect(items[1]).toMatchObject({
      question: { id: 20 },
      feedback: { is_correct: false, correct_choice_id: 3 },
    })
  })

  it('hides the mark buttons until the card is revealed', () => {
    submitAnswer.mockResolvedValue({ correct_choice_id: 2, correct_explanation: 'x' })
    render(
      <FlashcardView
        questions={[card(10, [1, 2])]}
        onFinish={() => {}}
        onQuit={() => {}}
      />
    )
    expect(screen.getByRole('button', { name: /Reveal answer/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Got it/i })).not.toBeInTheDocument()
  })
})
