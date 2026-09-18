import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ExamView from './ExamView'

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
afterEach(() => vi.useRealTimers())

describe('exam recovery and timing', () => {
  it('uses the deadline after background suspension and freezes expired answers', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-18T12:00:00Z'))
    const onSubmit = vi.fn().mockResolvedValue(false)
    render(<ExamView questions={[question]} onSubmit={onSubmit} onQuit={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /One/ }))
    vi.setSystemTime(new Date('2026-09-18T12:02:00Z'))
    await act(async () => fireEvent(window, new Event('focus')))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ 1: 11 })
    expect(screen.getByRole('button', { name: /Two/ })).toBeDisabled()
    await act(async () => vi.advanceTimersByTime(5000))
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('permits retry after a failed submit while blocking double clicks', async () => {
    const onSubmit = vi.fn().mockResolvedValue(false)
    render(
      <ExamView
        questions={[question]}
        onSubmit={onSubmit}
        onQuit={() => {}}
        error="Try again"
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /One/ }))
    const button = screen.getByRole('button', { name: /Retry grading/ })
    await act(async () => {
      fireEvent.click(button)
      fireEvent.click(button)
    })
    expect(onSubmit).toHaveBeenCalledTimes(1)
    await act(async () => fireEvent.click(button))
    expect(onSubmit).toHaveBeenCalledTimes(2)
    expect(onSubmit).toHaveBeenLastCalledWith({ 1: 11 })
  })

  it('ignores shortcuts in editable fields and while submitting', () => {
    const { rerender } = render(
      <>
        <ExamView questions={[question]} onSubmit={vi.fn()} onQuit={() => {}} />
        <input aria-label="Notes" />
      </>
    )
    fireEvent.keyDown(screen.getByLabelText('Notes'), { key: '1' })
    expect(screen.getByRole('button', { name: /One/ })).toHaveAttribute(
      'aria-pressed',
      'false'
    )
    rerender(
      <ExamView questions={[question]} onSubmit={vi.fn()} onQuit={() => {}} submitting />
    )
    fireEvent.keyDown(window, { key: '1' })
    expect(screen.getByRole('button', { name: /One/ })).toHaveAttribute(
      'aria-pressed',
      'false'
    )
  })
})
