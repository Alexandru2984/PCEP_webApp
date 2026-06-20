import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ScoreSummary from './ScoreSummary'

describe('ScoreSummary', () => {
  it('rounds the percentage and reports a passing score at/above 70%', () => {
    render(<ScoreSummary score={7} total={10} onRestart={() => {}} />)
    expect(screen.getByText('70%')).toBeInTheDocument()
    expect(screen.getByText(/Passing score/i)).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
  })

  it('reports a failing score below 70% and names the threshold', () => {
    render(<ScoreSummary score={6} total={10} onRestart={() => {}} />)
    expect(screen.getByText('60%')).toBeInTheDocument()
    expect(screen.getByText(/passing score is 70%/i)).toBeInTheDocument()
  })

  it('shows 0% (no divide-by-zero) for an empty quiz', () => {
    render(<ScoreSummary score={0} total={0} onRestart={() => {}} />)
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('calls onRestart when the new-quiz button is clicked', () => {
    const onRestart = vi.fn()
    render(<ScoreSummary score={5} total={10} onRestart={onRestart} />)
    fireEvent.click(screen.getByRole('button', { name: /start a new quiz/i }))
    expect(onRestart).toHaveBeenCalledOnce()
  })
})
