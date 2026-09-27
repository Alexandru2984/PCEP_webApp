import { describe, expect, it } from 'vitest'
import { normalizeReleaseVersion } from './release'

describe('normalizeReleaseVersion', () => {
  it.each(['abc123def456', 'v1.2.3', 'abc123-dirty'])(
    'accepts a bounded release identifier: %s',
    (value) => expect(normalizeReleaseVersion(value)).toBe(value)
  )

  it.each(['', ' leading', 'line\nbreak', 'x'.repeat(65), null, 123])(
    'uses the safe development label for malformed values: %j',
    (value) => expect(normalizeReleaseVersion(value)).toBe('development')
  )
})
