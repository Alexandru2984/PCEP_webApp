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
const secondQuestion = {
  ...question,
  id: 2,
  text: 'Second question?',
  choices: [
    { id: 21, text: 'Three' },
    { id: 22, text: 'Four' },
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

  it('restores saved answers, flags, position and deadline', () => {
    const onProgress = vi.fn()
    const deadline = Date.now() + 120_000
    render(
      <ExamView
        questions={[question, secondQuestion]}
        onSubmit={vi.fn()}
        onQuit={() => {}}
        onProgress={onProgress}
        initialProgress={{
          index: 0,
          answers: { 1: 11 },
          flagged: [1],
          deadline,
        }}
      />
    )
    expect(screen.getByRole('button', { name: /One/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
    expect(screen.getByRole('button', { name: '⚑ Flagged' })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
    fireEvent.click(screen.getByRole('button', { name: 'Next →' }))
    expect(screen.getByRole('heading', { name: 'Second question?' })).toBeVisible()
    expect(onProgress).toHaveBeenLastCalledWith({
      index: 1,
      answers: { 1: 11 },
      flagged: [1],
      deadline,
    })
  })

  it('submits saved answers immediately when a resumed deadline has expired', async () => {
    const onSubmit = vi.fn().mockResolvedValue(false)
    render(
      <ExamView
        questions={[question]}
        onSubmit={onSubmit}
        onQuit={() => {}}
        initialProgress={{
          index: 0,
          answers: { 1: 12 },
          flagged: [],
          deadline: Date.now() - 1,
        }}
      />
    )
    await act(async () => {})
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ 1: 12 })
    expect(screen.getByRole('button', { name: /One/ })).toBeDisabled()
  })
})
