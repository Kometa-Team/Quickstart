// Kometa branch/version management.
//
// Kometa can be tracked on one of three upstream branches:
//
//   master   -- stable releases
//   develop  -- pre-release / testing
//   nightly  -- daily builds against develop
//
// By default we pick a branch based on Quickstart's OWN branch:
//
//   Quickstart on master   -> Kometa on master  ('stable follows stable')
//   Quickstart on anything -> Kometa on nightly ('bleeding-edge follows
//                                                bleeding-edge')
//
// The user can override that mapping via the #kometa-branch-override
// <select>. The override persists in localStorage across page loads.
//
// This module owns the whole story: reading the override, resolving
// the effective branch, computing the remote source URLs, persisting
// choices, and rendering the associated UI (source status panel,
// rollup badge, warning banner).
//
// EXPORTS:
//
//   getKometaBranchOverride()   -- current override selection
//                                    ('' means 'auto')
//   getQuickstartBranch()       -- our own branch, from a data-attr
//   getAutoKometaBranch()       -- what auto-mode resolves to
//   getEffectiveKometaBranch()  -- override || auto
//   getKometaVersionSourceUrlValue(branch)
//                               -- raw.githubusercontent URL for VERSION
//   getKometaZipSourceUrlValue(branch)
//                               -- codeload.github ZIP URL
//   loadSavedKometaBranchOverride()
//                               -- restore from localStorage on boot
//   saveKometaBranchOverride()  -- persist current selection
//   syncKometaSourceStatus(options)
//                               -- update kometaState + repaint the
//                                    source-status panel
//   syncKometaBranchRollupBadge()
//                               -- update the rollup badge
//   syncKometaBranchOverrideWarning()
//                               -- show/hide the 'override active'
//                                    banner
//
// All DOM lookups are lazy (per-call). Zero cross-module callbacks;
// everything the module needs is either in kometaState or the DOM.

import { kometaState } from './_state.js'

// ---------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------

/**
 * localStorage key for the branch override selection. Keep in sync
 * with any place a user might clear their local Kometa state.
 */
export const KOMETA_BRANCH_OVERRIDE_STORAGE_KEY = 'qs-kometa-branch-override'

/**
 * Valid branch names the override <select> accepts. Anything else in
 * localStorage or the <select>.value gets coerced to '' (auto).
 */
const VALID_BRANCHES = ['master', 'develop', 'nightly']

// ---------------------------------------------------------------------
// Branch resolution
// ---------------------------------------------------------------------

/**
 * Current value of the branch-override <select>, normalized to one of
 * 'master' | 'develop' | 'nightly' or '' (meaning 'let auto decide').
 *
 * @returns {'' | 'master' | 'develop' | 'nightly'}
 */
export function getKometaBranchOverride () {
  const el = document.getElementById('kometa-branch-override')
  if (!el) return ''
  const raw = (el.value || '').toString().trim().toLowerCase()
  return VALID_BRANCHES.includes(raw) ? raw : ''
}

/**
 * Quickstart's OWN branch, read from the update button's data-attr.
 * Defaults to 'master' if the attr is missing.
 *
 * @returns {string}
 */
export function getQuickstartBranch () {
  const btn = document.getElementById('update-kometa-btn')
  return ((btn && btn.dataset.qsBranch) || 'master').toString().trim().toLowerCase()
}

/**
 * What auto-mode resolves to right now: 'master' iff Quickstart itself
 * is on master, otherwise 'nightly'. (There's no 'develop' auto-mode
 * -- develop is override-only.)
 *
 * @returns {'master' | 'nightly'}
 */
export function getAutoKometaBranch () {
  return getQuickstartBranch() === 'master' ? 'master' : 'nightly'
}

/**
 * The branch actually being used right now: the override if set,
 * else the auto-resolved value.
 *
 * @returns {'master' | 'develop' | 'nightly'}
 */
export function getEffectiveKometaBranch () {
  return getKometaBranchOverride() || getAutoKometaBranch()
}

// ---------------------------------------------------------------------
// Remote source URLs
// ---------------------------------------------------------------------

/**
 * raw.githubusercontent URL for the VERSION file on the given branch.
 * @param {string} branch
 * @returns {string}
 */
export function getKometaVersionSourceUrlValue (branch) {
  return `https://raw.githubusercontent.com/Kometa-Team/Kometa/${branch}/VERSION`
}

/**
 * codeload.github ZIP URL for the given branch. Used by the update
 * download step.
 * @param {string} branch
 * @returns {string}
 */
export function getKometaZipSourceUrlValue (branch) {
  return `https://codeload.github.com/kometa-team/Kometa/zip/refs/heads/${branch}`
}

// ---------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------

/**
 * Restore the branch override from localStorage on page load. If the
 * stored value isn't a valid branch (or localStorage throws for any
 * reason), coerce to '' (auto).
 */
export function loadSavedKometaBranchOverride () {
  const el = document.getElementById('kometa-branch-override')
  if (!el) return
  try {
    const saved = window.localStorage.getItem(KOMETA_BRANCH_OVERRIDE_STORAGE_KEY) || ''
    el.value = VALID_BRANCHES.includes(saved) ? saved : ''
  } catch {
    el.value = ''
  }
}

/**
 * Persist the current branch override. Empty value ('' = auto) is
 * stored as a removal so we don't leak stale keys.
 *
 * Wrapped in try/catch because localStorage can throw in private
 * browsing / quota-exceeded scenarios; we're OK silently failing --
 * the setting reverts to auto on next load.
 */
export function saveKometaBranchOverride () {
  try {
    const value = getKometaBranchOverride()
    if (value) window.localStorage.setItem(KOMETA_BRANCH_OVERRIDE_STORAGE_KEY, value)
    else window.localStorage.removeItem(KOMETA_BRANCH_OVERRIDE_STORAGE_KEY)
  } catch {
    // Ignore quota / private-browsing errors.
  }
}

// ---------------------------------------------------------------------
// UI sync
// ---------------------------------------------------------------------

/**
 * Update the source-status panel (branch selection, effective branch,
 * local/remote version, source URLs). Accepts a partial options bag
 * so callers can update just the fields they know about.
 *
 * Options (all optional; unset fields keep their prior kometaState
 * value):
 *   localVersion   string -- writes to kometaLocalVersionStatus
 *   remoteVersion  string -- writes to kometaRemoteVersionStatus
 *   checked        bool   -- writes to kometaRemoteVersionChecked
 *   skipped        bool   -- writes to kometaRemoteVersionSkipped
 *
 * Uses hasOwnProperty (not truthy checks) so a caller passing
 * `{ localVersion: '' }` explicitly clears the field rather than
 * being ignored.
 *
 * @param {{
 *   localVersion?: string,
 *   remoteVersion?: string,
 *   checked?: boolean,
 *   skipped?: boolean
 * }} [options]
 */
export function syncKometaSourceStatus (options = {}) {
  if (Object.prototype.hasOwnProperty.call(options, 'localVersion')) {
    kometaState.kometaLocalVersionStatus = options.localVersion || 'Unknown'
  }
  if (Object.prototype.hasOwnProperty.call(options, 'remoteVersion')) {
    kometaState.kometaRemoteVersionStatus = options.remoteVersion || ''
  }
  if (Object.prototype.hasOwnProperty.call(options, 'checked')) {
    kometaState.kometaRemoteVersionChecked = Boolean(options.checked)
  }
  if (Object.prototype.hasOwnProperty.call(options, 'skipped')) {
    kometaState.kometaRemoteVersionSkipped = Boolean(options.skipped)
  }

  const selected = getKometaBranchOverride()
  const effective = getEffectiveKometaBranch()
  const selectionLabel = selected ? `Override (${selected})` : 'Auto'

  const branchSelection = document.getElementById('kometa-branch-selection')
  const effectiveBranch = document.getElementById('kometa-effective-branch')
  const localVersionEl = document.getElementById('kometa-local-version-status')
  const remoteVersionEl = document.getElementById('kometa-remote-version-status')
  const versionSourceUrl = document.getElementById('kometa-version-source-url')
  const zipSourceUrl = document.getElementById('kometa-zip-source-url')

  if (branchSelection) branchSelection.textContent = selectionLabel
  if (effectiveBranch) effectiveBranch.textContent = effective
  if (localVersionEl) localVersionEl.textContent = kometaState.kometaLocalVersionStatus || 'Unknown'

  if (remoteVersionEl) {
    if (kometaState.kometaRemoteVersionSkipped) {
      remoteVersionEl.textContent = 'Skipped while running'
    } else if (kometaState.kometaRemoteVersionChecked) {
      remoteVersionEl.textContent = kometaState.kometaRemoteVersionStatus || 'Unknown'
    } else {
      remoteVersionEl.textContent = 'Not checked'
    }
  }

  if (versionSourceUrl) versionSourceUrl.textContent = getKometaVersionSourceUrlValue(effective)
  if (zipSourceUrl) zipSourceUrl.textContent = getKometaZipSourceUrlValue(effective)

  syncKometaBranchRollupBadge()
}

/**
 * Update the rollup badge next to the branch selector. Shows the
 * uppercase branch name (or 'AUTO'), and paints it warning-yellow
 * when an override is active vs. secondary-gray for auto.
 */
export function syncKometaBranchRollupBadge () {
  const badge = document.getElementById('kometa-branch-rollup-badge')
  if (!badge) return

  const selected = getKometaBranchOverride()
  const effective = getEffectiveKometaBranch()
  const label = (selected || 'auto').toUpperCase()

  badge.textContent = label
  badge.classList.remove('text-bg-secondary', 'text-bg-warning', 'text-dark')
  if (selected) {
    badge.classList.add('text-bg-warning', 'text-dark')
    badge.setAttribute('title', `Kometa branch override selected: ${selected}. Effective branch: ${effective}.`)
  } else {
    badge.classList.add('text-bg-secondary')
    badge.setAttribute('title', `Kometa branch mode: auto. Effective branch: ${effective}.`)
  }
}

/**
 * Show/hide the 'branch override active' warning banner. When an
 * override is set, we surface a visible reminder that the user is
 * off the auto path.
 */
export function syncKometaBranchOverrideWarning () {
  const warning = document.getElementById('kometa-branch-override-warning')
  if (!warning) return
  warning.classList.toggle('d-none', !getKometaBranchOverride())
}
