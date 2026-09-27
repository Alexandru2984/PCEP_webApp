import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { loadNote, saveNote } from '../storage'
import QuestionNote from './QuestionNote'

beforeEach(() => localStorage.clear())

describe('QuestionNote', () => {
  it('saves escaped local text and shows it without HTML injection', () => {
    render(<QuestionNote questionId={7} />)
    fireEvent.click(screen.getByRole('button', { name: 'Add note' }))
    fireEvent.change(screen.getByLabelText('Personal note'), {
      target: { value: '<img src=x onerror=alert(1)>\nReview slicing.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save note' }))

    expect(screen.getByRole('status')).toHaveTextContent('Note saved')
    expect(screen.getByText(/<img src=x onerror=alert/)).toBeInTheDocument()
    expect(document.querySelector('img')).toBeNull()
    expect(loadNote(7)?.text).toContain('Review slicing.')
  })

  it('edits and removes an existing note explicitly', () => {
    saveNote(7, 'Old note')
    render(<QuestionNote questionId={7} />)
    fireEvent.click(screen.getByRole('button', { name: 'Edit note' }))
    const editor = screen.getByLabelText('Personal note')
    fireEvent.change(editor, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Remove note' }))

    expect(screen.getByRole('status')).toHaveTextContent('Note removed')
    expect(screen.getByRole('button', { name: 'Add note' })).toBeVisible()
    expect(loadNote(7)).toBeNull()
  })

  it('keeps the editor open when browser storage rejects the write', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Quota', 'QuotaExceededError')
    })
    render(<QuestionNote questionId={7} />)
    fireEvent.click(screen.getByRole('button', { name: 'Add note' }))
    fireEvent.change(screen.getByLabelText('Personal note'), {
      target: { value: 'Keep this draft' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save note' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Could not save the note')
    expect(screen.getByLabelText('Personal note')).toHaveValue('Keep this draft')
    spy.mockRestore()
  })

  it('refreshes a note changed outside the mounted component', () => {
    saveNote(7, 'Original note', Date.UTC(2026, 8, 27, 10))
    render(<QuestionNote questionId={7} />)
    expect(screen.getByText('Original note')).toBeVisible()

    act(() => saveNote(7, 'Updated elsewhere', Date.UTC(2026, 8, 27, 11)))

    expect(screen.getByText('Updated elsewhere')).toBeVisible()
    expect(screen.queryByText('Original note')).toBeNull()
  })

  it('preserves a draft instead of silently overwriting a newer note', () => {
    saveNote(7, 'Original note', Date.UTC(2026, 8, 27, 10))
    render(<QuestionNote questionId={7} />)
    fireEvent.click(screen.getByRole('button', { name: 'Edit note' }))
    fireEvent.change(screen.getByLabelText('Personal note'), {
      target: { value: 'My draft' },
    })
    act(() => saveNote(7, 'Newer note', Date.UTC(2026, 8, 27, 11)))

    fireEvent.click(screen.getByRole('button', { name: 'Save note' }))

    expect(screen.getByRole('alert')).toHaveTextContent('changed in another tab')
    expect(screen.getByLabelText('Personal note')).toHaveValue('My draft')
    expect(loadNote(7)?.text).toBe('Newer note')

    fireEvent.click(screen.getByRole('button', { name: 'Save note' }))
    expect(screen.getByRole('status')).toHaveTextContent('Note saved')
    expect(loadNote(7)?.text).toBe('My draft')
  })
})
