import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { searchQuestions } from '../api'
import QuestionSearch from './QuestionSearch'

vi.mock('../api', async (original) => ({
  ...(await original()),
  searchQuestions: vi.fn(),
}))

const results = [
  {
    id: 7,
    text: 'Which slice creates a copy?',
    code_snippet: 'items[:]',
    module: 'module3',
    objective: '3.1',
    difficulty: 'easy',
  },
  {
    id: 9,
    text: 'What does this slicing expression return?',
    code_snippet: 'items[1:3]',
    module: 'module3',
    objective: '3.1',
    difficulty: 'medium',
  },
]

const deferred = () => {
  let resolve
  const promise = new Promise((done) => {
    resolve = done
  })
  return { promise, resolve }
}

beforeEach(() => {
  vi.clearAllMocks()
  searchQuestions.mockResolvedValue({ count: results.length, results })
})

describe('QuestionSearch', () => {
  it('searches the current scope and starts a drill from selected IDs', async () => {
    const onStart = vi.fn()
    render(<QuestionSearch module="module3" difficulty="medium" onStart={onStart} />)

    const input = screen.getByLabelText('Search question text or code')
    fireEvent.change(input, { target: { value: 'slice' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))

    await screen.findByText('Which slice creates a copy?')
    expect(searchQuestions).toHaveBeenCalledWith(
      {
        query: 'slice',
        module: 'module3',
        objective: '',
        difficulty: 'medium',
        limit: 20,
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    fireEvent.click(screen.getByLabelText(/Which slice creates a copy/))
    fireEvent.click(screen.getByLabelText(/What does this slicing expression return/))
    fireEvent.click(screen.getByRole('button', { name: 'Practice selected (2)' }))
    expect(onStart).toHaveBeenCalledWith([7, 9], 'practice')
    fireEvent.click(screen.getByRole('button', { name: 'Flashcards selected (2)' }))
    expect(onStart).toHaveBeenLastCalledWith([7, 9], 'flashcards')
  })

  it('selects and clears every result without losing the search', async () => {
    render(<QuestionSearch onStart={() => {}} />)
    fireEvent.change(screen.getByLabelText('Search question text or code'), {
      target: { value: 'slice' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))

    const selectAll = await screen.findByRole('button', {
      name: 'Select all results',
    })
    fireEvent.click(selectAll)
    expect(screen.getByRole('button', { name: 'Practice selected (2)' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Flashcards selected (2)' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Clear selection' }))
    expect(screen.getByRole('button', { name: 'Practice selected (0)' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Flashcards selected (0)' })).toBeDisabled()
  })

  it('rejects unexpected answer metadata in a search response', async () => {
    searchQuestions.mockResolvedValue({
      count: 1,
      results: [{ ...results[0], is_correct: true }],
    })
    render(<QuestionSearch onStart={() => {}} />)
    fireEvent.change(screen.getByLabelText('Search question text or code'), {
      target: { value: 'slice' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('invalid search results')
    expect(screen.queryByText('Which slice creates a copy?')).not.toBeInTheDocument()
  })

  it('keeps errors recoverable and disables an undersized search', async () => {
    searchQuestions
      .mockRejectedValueOnce(new Error('Network unavailable'))
      .mockResolvedValueOnce({ count: 0, results: [] })
    render(<QuestionSearch onStart={() => {}} />)
    const input = screen.getByLabelText('Search question text or code')
    fireEvent.change(input, { target: { value: 'x' } })
    expect(screen.getByRole('button', { name: 'Search' })).toBeDisabled()
    fireEvent.change(input, { target: { value: 'loops' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Network unavailable')

    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('No questions matched')
    )
  })

  it('uses a synchronous guard against duplicate search submissions', () => {
    searchQuestions.mockImplementation(() => new Promise(() => {}))
    render(<QuestionSearch onStart={() => {}} />)
    fireEvent.change(screen.getByLabelText('Search question text or code'), {
      target: { value: 'slice' },
    })
    const form = screen.getByLabelText('Search question text or code').closest('form')

    act(() => {
      fireEvent.submit(form)
      fireEvent.submit(form)
    })

    expect(searchQuestions).toHaveBeenCalledOnce()
  })

  it('aborts and clears stale results when the search term changes', async () => {
    const pending = deferred()
    searchQuestions.mockReturnValueOnce(pending.promise)
    render(<QuestionSearch onStart={() => {}} />)
    const input = screen.getByLabelText('Search question text or code')
    fireEvent.change(input, { target: { value: 'slice' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    const firstSignal = searchQuestions.mock.calls[0][1].signal

    fireEvent.change(input, { target: { value: 'loops' } })
    expect(firstSignal.aborted).toBe(true)
    expect(screen.getByRole('button', { name: 'Search' })).toBeEnabled()

    await act(async () => pending.resolve({ count: results.length, results }))
    expect(screen.queryByText('Which slice creates a copy?')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    await screen.findByText('Which slice creates a copy?')
    expect(searchQuestions).toHaveBeenLastCalledWith(
      expect.objectContaining({ query: 'loops' }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )

    fireEvent.click(screen.getByLabelText(/Which slice creates a copy/))
    fireEvent.change(input, { target: { value: 'exceptions' } })
    expect(screen.queryByText('Which slice creates a copy?')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /selected \(1\)/i })
    ).not.toBeInTheDocument()
  })
})
