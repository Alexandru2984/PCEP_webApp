import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import FlashcardView from './FlashcardView'
import { submitAnswer } from '../api'

vi.mock('../api', async (original) => ({ ...(await original()), submitAnswer: vi.fn() }))

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
        is_correct: false,
        correct_choice_id: 2,
        explanation: 'first choice',
        correct_explanation: 'first concept',
      })
      .mockResolvedValueOnce({
        is_correct: true,
        correct_choice_id: 3,
        explanation: 'second concept',
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
    expect(screen.getByRole('button', { name: /Review later/i })).toHaveFocus()
    // The reveal POSTs a throwaway guess (the first choice) to learn the key.
    expect(submitAnswer).toHaveBeenCalledWith(
      10,
      1,
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    fireEvent.click(screen.getByRole('button', { name: /Got it/i }))

    // Card 2: flip (proves we advanced), then mark "Review later".
    fireEvent.click(screen.getByRole('button', { name: /Reveal answer/i }))
    expect(await screen.findByText(/second concept/)).toBeInTheDocument()
    expect(submitAnswer).toHaveBeenLastCalledWith(
      20,
      3,
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
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

  it('keeps the answer hidden after a network failure and offers a safe retry', async () => {
    submitAnswer
      .mockRejectedValueOnce(new Error('Network failure'))
      .mockResolvedValueOnce({
        is_correct: false,
        correct_choice_id: 2,
        explanation: 'first choice',
        correct_explanation: 'Recovered concept',
      })
    render(
      <FlashcardView
        questions={[card(10, [1, 2])]}
        onFinish={vi.fn()}
        onQuit={() => {}}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /Reveal answer/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Network failure')
    expect(screen.queryByRole('button', { name: /Got it/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Reveal answer/ }))
    expect(await screen.findByText(/Recovered concept/)).toBeInTheDocument()
  })

  it('rejects incomplete feedback instead of rendering unsafe response data', async () => {
    submitAnswer.mockResolvedValue({
      is_correct: true,
      correct_choice_id: 2,
      correct_explanation: { unexpected: true },
    })
    render(
      <FlashcardView
        questions={[card(10, [1, 2])]}
        onFinish={vi.fn()}
        onQuit={() => {}}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: /Reveal answer/ }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The server returned invalid feedback'
    )
    expect(screen.queryByRole('button', { name: /Got it/ })).not.toBeInTheDocument()
  })

  it('aborts an in-flight reveal before quitting', () => {
    submitAnswer.mockImplementation(() => new Promise(() => {}))
    const onQuit = vi.fn()
    const confirm = vi
      .spyOn(window, 'confirm')
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true)
    render(
      <FlashcardView questions={[card(10, [1, 2])]} onFinish={vi.fn()} onQuit={onQuit} />
    )

    fireEvent.click(screen.getByRole('button', { name: /Reveal answer/ }))
    const signal = submitAnswer.mock.calls[0][2].signal
    expect(signal.aborted).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'Quit' }))
    expect(signal.aborted).toBe(false)
    expect(onQuit).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Quit' }))

    expect(confirm).toHaveBeenCalledTimes(2)
    expect(confirm).toHaveBeenCalledWith(
      'Quit these flashcards? Your current session progress will be discarded.'
    )
    expect(signal.aborted).toBe(true)
    expect(onQuit).toHaveBeenCalledOnce()
  })

  it('reveals and self-rates with discoverable keyboard shortcuts', async () => {
    submitAnswer
      .mockResolvedValueOnce({
        is_correct: false,
        correct_choice_id: 2,
        explanation: 'first choice',
        correct_explanation: 'first concept',
      })
      .mockResolvedValueOnce({
        is_correct: true,
        correct_choice_id: 3,
        explanation: 'second concept',
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

    fireEvent.keyDown(window, { key: ' ' })
    expect(await screen.findByText('first concept')).toBeVisible()
    expect(screen.getByRole('button', { name: /Review later/i })).toHaveAttribute(
      'aria-keyshortcuts',
      '1'
    )
    expect(screen.getByRole('button', { name: /Got it/i })).toHaveAttribute(
      'aria-keyshortcuts',
      '2'
    )
    fireEvent.keyDown(window, { key: '2' })
    expect(screen.getByText(/Flashcard/)).toHaveTextContent('Flashcard 2 of 2')

    fireEvent.keyDown(window, { key: 'Enter' })
    expect(await screen.findByText('second concept')).toBeVisible()
    fireEvent.keyDown(window, { key: '1' })

    expect(onFinish).toHaveBeenCalledOnce()
    expect(onFinish.mock.calls[0][0].map((item) => item.feedback.is_correct)).toEqual([
      true,
      false,
    ])
  })

  it('resumes an already revealed card without repeating the answer request', () => {
    const firstQuestion = card(10, [1, 2])
    const second = card(20, [3, 4])
    const completed = {
      question: firstQuestion,
      pickedChoiceId: 2,
      feedback: {
        is_correct: true,
        correct_choice_id: 2,
        explanation: '',
        correct_explanation: 'first concept',
      },
    }
    const onFinish = vi.fn()
    const onProgress = vi.fn()
    render(
      <FlashcardView
        questions={[firstQuestion, second]}
        initialProgress={{
          index: 1,
          items: [completed],
          revealed: {
            correct_choice_id: 3,
            correct_explanation: 'second concept',
          },
        }}
        onProgress={onProgress}
        onFinish={onFinish}
        onQuit={() => {}}
      />
    )

    expect(screen.getByText(/Flashcard/)).toHaveTextContent('Flashcard 2 of 2')
    expect(screen.getByText('second concept')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Review later' })).toHaveFocus()
    expect(submitAnswer).not.toHaveBeenCalled()
    expect(onProgress).toHaveBeenCalledWith({
      index: 1,
      items: [completed],
      revealed: {
        correct_choice_id: 3,
        correct_explanation: 'second concept',
      },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Review later' }))
    expect(onFinish).toHaveBeenCalledOnce()
    expect(onFinish.mock.calls[0][0]).toHaveLength(2)
  })
})
