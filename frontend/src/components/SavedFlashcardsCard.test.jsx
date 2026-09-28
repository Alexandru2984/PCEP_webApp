import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import SavedFlashcardsCard from './SavedFlashcardsCard'

const flashcards = {
  index: 2,
  items: [{}, {}],
  revealed: { correct_choice_id: 31 },
  questions: [{}, {}, {}, {}],
}

it('describes saved progress and the answer-key boundary', () => {
  render(<SavedFlashcardsCard flashcards={flashcards} onResume={() => {}} />)
  expect(screen.getByRole('heading', { name: 'Resume saved flashcards' })).toBeVisible()
  expect(screen.getByText(/2\/4 rated/i)).toHaveTextContent(
    'Continue from card 3. The current answer is already revealed.'
  )
  expect(screen.getByText(/future answer keys are never saved/i)).toBeVisible()
})

it('requires confirmation before deleting saved flashcards', () => {
  const onDiscard = vi.fn()
  render(
    <SavedFlashcardsCard
      flashcards={flashcards}
      onResume={() => {}}
      onDiscard={onDiscard}
    />
  )
  fireEvent.click(screen.getByRole('button', { name: 'Discard and start new' }))
  expect(onDiscard).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Delete attempt' })).toHaveFocus()
  fireEvent.click(screen.getByRole('button', { name: 'Delete attempt' }))
  expect(onDiscard).toHaveBeenCalledOnce()
})
