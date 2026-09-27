import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BookmarkButton from './BookmarkButton'

const question = {
  id: 42,
  text: 'Question?',
  code_snippet: '',
  module: 'module2',
  objective: '2.1',
  difficulty: 'medium',
  choices: [
    { id: 421, text: 'One' },
    { id: 422, text: 'Two' },
  ],
}

describe('BookmarkButton', () => {
  it('reflects a bookmark changed in another tab', () => {
    render(<BookmarkButton question={question} />)
    expect(screen.getByRole('button', { name: '☆ Bookmark' })).toBeVisible()
    localStorage.setItem(
      'pcep.progress',
      JSON.stringify({
        version: 1,
        data: {
          history: [],
          mistakes: [],
          bookmarks: [question],
          study: [],
          notes: [],
        },
      })
    )

    fireEvent(
      window,
      new StorageEvent('storage', {
        key: 'pcep.progress',
        newValue: localStorage.getItem('pcep.progress'),
      })
    )

    expect(screen.getByRole('button', { name: '★ Bookmarked' })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
  })
})
