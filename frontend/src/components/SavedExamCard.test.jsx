import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SavedExamCard from './SavedExamCard'

const exam = (deadline) => ({
  deadline,
  answers: { 1: 11 },
  questions: [{ id: 1 }, { id: 2 }],
})

afterEach(() => vi.useRealTimers())

describe('SavedExamCard', () => {
  it('keeps the recovery countdown accurate until it expires', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-25T10:00:00Z'))
    render(<SavedExamCard exam={exam(Date.now() + 65_000)} onResume={() => {}} />)
    expect(screen.getByRole('timer')).toHaveAccessibleName('Time remaining: 1:05')

    act(() => vi.advanceTimersByTime(65_000))
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(/time has expired/i)
    expect(screen.getByRole('button', { name: 'Grade saved answers' })).toBeVisible()
  })

  it('shows the grading action immediately for an already expired attempt', () => {
    render(<SavedExamCard exam={exam(Date.now() - 1)} onResume={() => {}} />)
    expect(screen.getByRole('button', { name: 'Grade saved answers' })).toBeVisible()
    expect(screen.getByText('1/2 answered.', { exact: false })).toBeVisible()
  })

  it('requires an explicit confirmation before deleting recovery data', () => {
    const onDiscard = vi.fn()
    render(
      <SavedExamCard
        exam={exam(Date.now() + 60_000)}
        onResume={() => {}}
        onDiscard={onDiscard}
      />
    )
    const discard = screen.getByRole('button', { name: 'Discard and start new' })
    fireEvent.click(discard)
    expect(onDiscard).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Delete attempt' })).toHaveFocus()

    fireEvent.click(screen.getByRole('button', { name: 'Keep exam' }))
    expect(onDiscard).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Discard and start new' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete attempt' }))
    expect(onDiscard).toHaveBeenCalledOnce()
  })
})
