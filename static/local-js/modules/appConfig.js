// App-level config accessors (#1334 Step 5, Phase B).
//
// Replaces the 11 `window.QS_*` globals that used to be sprayed across
// the template via individual `<script>` tags in
// `templates/000-base.html`. The data is still inline (server-rendered
// for synchronous startup access), but it lives behind a single object
// at `window.QS_AppConfig` and is read through these helpers.
//
// Why a thin wrapper instead of just reading `window.QS_AppConfig.QS_FOO`
// directly: centralising the access pattern means future refactors
// (e.g. moving to a fetched bootstrap, or wrapping in a reactive
// Proxy for component frameworks) only need to change this file. The
// indirection is cheap and the call sites get clearer.
//
// In-place updates: the settings save flow still mutates the object so
// other handlers see fresh values without a page reload. The shape of
// the mutation contract is identical to the old `window.QS_FOO = value`
// pattern, just routed through `setAppConfig({ QS_FOO: value })`.

// The object the template populates. Bridging back to window keeps
// classic (non-module) scripts working without an import.
const NAMESPACE = 'QS_AppConfig'

function getNamespace () {
  if (typeof window === 'undefined') return {}
  if (!window[NAMESPACE] || typeof window[NAMESPACE] !== 'object') {
    window[NAMESPACE] = {}
  }
  return window[NAMESPACE]
}

/**
 * Read a single app-level config value. Returns `fallback` (default
 * `undefined`) when the key is missing or the namespace hasn't been
 * populated yet.
 */
export function getAppConfig (key, fallback) {
  const ns = getNamespace()
  return Object.prototype.hasOwnProperty.call(ns, key) ? ns[key] : fallback
}

/**
 * Merge `patch` into the app-level config namespace. Mutates in place
 * so any code that captured a reference to `window.QS_AppConfig` still
 * sees the new values. Returns the (mutated) namespace for chaining.
 */
export function setAppConfig (patch) {
  if (!patch || typeof patch !== 'object') return getNamespace()
  const ns = getNamespace()
  for (const [key, value] of Object.entries(patch)) {
    ns[key] = value
  }
  return ns
}

/**
 * Re-hydrate the namespace from `GET /api/app-config`. The settings
 * save flow can call this after a write to be extra-safe that the
 * client view matches the server, but it isn't required for the
 * normal flow because `setAppConfig` already keeps the namespace in
 * sync with the server response.
 *
 * Returns the fresh namespace on success, or the existing one on
 * failure (we never want a transient fetch error to wipe the values
 * the page started with).
 */
export async function refreshAppConfig () {
  try {
    const res = await fetch('/api/app-config', { headers: { Accept: 'application/json' } })
    if (!res.ok) return getNamespace()
    const data = await res.json()
    if (data && typeof data === 'object') {
      const ns = getNamespace()
      // Replace every known key but don't blow away any unknown keys
      // someone might have added; merge wins over wholesale replace
      // for forward compatibility.
      for (const [key, value] of Object.entries(data)) {
        ns[key] = value
      }
    }
  } catch {
    // Network failure or invalid JSON. Keep what we had.
  }
  return getNamespace()
}
