const LEGACY_RUNNER_CACHES = ['pyodide-runtime-0.29.4']

export async function purgeLegacyRunnerCaches(cacheStorage = globalThis.caches) {
  if (!cacheStorage?.delete) return false
  try {
    const removed = await Promise.all(
      LEGACY_RUNNER_CACHES.map((name) => cacheStorage.delete(name))
    )
    return removed.some(Boolean)
  } catch {
    // Cache cleanup is best-effort; the new app never requests these URLs.
    return false
  }
}
