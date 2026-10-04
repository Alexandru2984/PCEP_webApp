import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ProgressTools from './ProgressTools'

describe('ProgressTools', () => {
  const backup = (notes = []) =>
    JSON.stringify({
      type: 'pcep-progress',
      version: 4,
      history: [],
      mistakes: [],
      bookmarks: [],
      study: [],
      notes,
    })

  it('replaces a stale success message when a later reset cannot be saved', () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const onChange = vi.fn()
    render(<ProgressTools onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: 'Clear history' }))
    expect(screen.getByRole('status')).toHaveTextContent('Saved history cleared')

    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Quota', 'QuotaExceededError')
    })
    fireEvent.click(screen.getByRole('button', { name: 'Clear mistakes' }))

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Could not save the change')
    expect(onChange).toHaveBeenCalledOnce()
    expect(confirm).toHaveBeenCalledTimes(2)
  })

  it('reports a browser failure while creating an export', () => {
    const original = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => {
        throw new Error('Unavailable')
      }),
    })
    try {
      render(<ProgressTools onChange={vi.fn()} />)
      fireEvent.click(screen.getByRole('button', { name: 'Export backup' }))
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Could not create the backup file'
      )
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
    } finally {
      if (original) Object.defineProperty(URL, 'createObjectURL', original)
      else delete URL.createObjectURL
    }
  })

  it('keeps the newest backup selection when an older file finishes later', async () => {
    let finishOlder
    const older = {
      name: 'older.json',
      size: 100,
      text: vi.fn(
        () =>
          new Promise((resolve) => {
            finishOlder = resolve
          })
      ),
    }
    const newer = {
      name: 'newer.json',
      size: 100,
      text: vi.fn(() => Promise.resolve(backup())),
    }
    render(<ProgressTools onChange={vi.fn()} />)
    expect(
      screen.getByRole('heading', {
        name: 'Progress backup & review lists',
        level: 2,
      })
    ).toBeInTheDocument()
    const input = screen.getByLabelText('Progress backup file')

    fireEvent.change(input, { target: { files: [older] } })
    expect(screen.getByRole('status')).toHaveTextContent('Reading and validating')
    fireEvent.change(input, { target: { files: [newer] } })

    expect(await screen.findByText(/0 personal notes/)).toBeInTheDocument()
    expect(screen.queryByText(/Reading and validating/)).not.toBeInTheDocument()

    await act(async () => {
      finishOlder(
        backup([
          {
            questionId: 1,
            text: 'This stale preview must never replace the newer file.',
            updatedAt: '2026-10-04T00:00:00.000Z',
          },
        ])
      )
    })

    expect(screen.getByText(/0 personal notes/)).toBeInTheDocument()
    expect(screen.queryByText(/1 personal notes/)).not.toBeInTheDocument()
  })
})
