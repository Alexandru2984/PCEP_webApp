import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import SavedPracticeCard from './SavedPracticeCard'

const practice = {
  index: 2,
  history: [{}, {}],
  questions: [{}, {}, {}, {}],
}

it('describes the saved progress and answer-key boundary', () => {
  render(<SavedPracticeCard practice={practice} onResume={() => {}} />)
  expect(screen.getByRole('heading', { name: 'Resume saved practice' })).toBeVisible()
  expect(screen.getByText(/2\/4 completed/i)).toBeVisible()
  expect(screen.getByText(/unanswered answer keys are never saved/i)).toBeVisible()
})

it('requires confirmation before deleting saved practice', () => {
  const onDiscard = vi.fn()
  render(
    <SavedPracticeCard practice={practice} onResume={() => {}} onDiscard={onDiscard} />
  )
  fireEvent.click(screen.getByRole('button', { name: 'Discard and start new' }))
  expect(onDiscard).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Delete attempt' })).toHaveFocus()
  fireEvent.click(screen.getByRole('button', { name: 'Delete attempt' }))
  expect(onDiscard).toHaveBeenCalledOnce()
})
