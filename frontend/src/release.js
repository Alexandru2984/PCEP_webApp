const RELEASE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/

export function normalizeReleaseVersion(value) {
  return typeof value === 'string' && RELEASE_PATTERN.test(value) ? value : 'development'
}

export const RELEASE_VERSION = normalizeReleaseVersion(import.meta.env.VITE_PCEP_RELEASE)
export const RELEASE_LABEL =
  RELEASE_VERSION === 'development' ? 'local' : RELEASE_VERSION.slice(0, 12)
