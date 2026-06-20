import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import PerformanceReport from './PerformanceReport'

const item = (module, difficulty, is_correct) => ({
  question: { id: Math.random(), module, difficulty },
  feedback: { is_correct },
})

describe('PerformanceReport', () => {
  it('breaks the score down per module and flags the weakest as the focus area', () => {
    const items = [
      item('module1', 'easy', true),
      item('module1', 'medium', true),
      item('module3', 'hard', true),
      item('module3', 'hard', false),
      item('module3', 'medium', false),
    ]
    render(<PerformanceReport items={items} />)

    // module1: 2/2 = 100%, module3: 1/3 = 33%
    expect(screen.getByText('M1 · Fundamentals')).toBeInTheDocument()
    expect(screen.getByText('2/2 · 100%')).toBeInTheDocument()
    expect(screen.getByText('1/3 · 33%')).toBeInTheDocument()

    const focus = screen.getByText(/Focus area:/i).closest('div')
    expect(focus).toHaveTextContent('M3 · Data Collections')
    expect(focus).toHaveTextContent('33%')
  })

  it('congratulates when every module clears the pass line', () => {
    const items = [
      item('module1', 'easy', true),
      item('module2', 'medium', true),
      item('module2', 'hard', true),
    ]
    render(<PerformanceReport items={items} />)
    expect(screen.getByText(/Strong across the board/i)).toBeInTheDocument()
    expect(screen.queryByText(/Focus area:/i)).not.toBeInTheDocument()
  })

  it('renders nothing for an empty result set', () => {
    const { container } = render(<PerformanceReport items={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
