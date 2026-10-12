import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ANALYTICS_CONSENT_KEY, ANALYTICS_SCRIPT_ID } from '../analytics'
import AnalyticsConsent from './AnalyticsConsent'
import PrivacyPage from './PrivacyPage'

describe('privacy controls', () => {
  it('explains the controller, data boundary and bounded retention', () => {
    render(<PrivacyPage />)

    expect(screen.getByRole('heading', { name: 'Privacy & data' })).toBeVisible()
    expect(screen.getByText(/Dragne Alexandru Mihai/)).toBeVisible()
    expect(screen.getByRole('link', { name: 'alex_mihai984@yahoo.com' })).toHaveAttribute(
      'href',
      'mailto:alex_mihai984@yahoo.com'
    )
    expect(screen.getByText(/automatically removed after 180 days/)).toBeVisible()
    expect(screen.getByText(/does not create learner accounts/)).toBeVisible()
    expect(screen.getByRole('link', { name: 'ANSPDCP' })).toHaveAttribute(
      'href',
      'https://www.dataprotection.ro/'
    )
  })

  it('defaults to no tracker and persists refusal without limiting the page', () => {
    render(<AnalyticsConsent />)

    expect(screen.getByRole('complementary', { name: 'Analytics choice' })).toBeVisible()
    expect(document.getElementById(ANALYTICS_SCRIPT_ID)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'No thanks' }))
    expect(localStorage.getItem(ANALYTICS_CONSENT_KEY)).toBe('denied')
    expect(screen.queryByRole('complementary', { name: 'Analytics choice' })).toBeNull()
    expect(document.getElementById(ANALYTICS_SCRIPT_ID)).toBeNull()
  })
})
