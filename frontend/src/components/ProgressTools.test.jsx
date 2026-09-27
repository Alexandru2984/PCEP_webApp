import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ProgressTools from './ProgressTools'

describe('ProgressTools', () => {
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
})
