// Kometa update rollup: the summary badge that lives in the accordion
// header, the "attention" indicator that highlights the collapsed
// header when an update is available, the update-button label sync,
// and the state-invalidation helper called when we need to reset the
// update flow (e.g. after a user action changes install mode).
//
// EXPORTS:
//
//   getKometaRollupStatus()   -- PURE fn: returns { state, label }
//                                describing where in the update flow
//                                we are (updating / checking / not
//                                installed / prepared / up-to-date /
//                                update-available / etc.)
//   syncKometaRollupBadge()   -- write the rollup status onto the
//                                #kometa-update-rollup-badge DOM
//                                element (text + qs-validation-*
//                                class)
//   syncKometaUpdateAttention()
//                             -- toggles the .kometa-update-attention
//                                class on the accordion header when
//                                an update is available AND the
//                                accordion is collapsed. Always
//                                refreshes the rollup badge as a
//                                side effect.
//   getUpdateButtonLabel()    -- builds the innerHTML string for the
//                                #update-kometa-btn based on install
//                                mode + force-toggle + kometaState
//   syncUpdateButtonLabel()   -- write the label to the button (if it
//                                exists), then refresh the attention
//                                indicator
//   invalidateKometaUpdateStatus()
//                             -- reset all kometaState update fields,
//                                hide the update-info box, and
//                                refresh source-status + button label
//                                + rollup badge
//
// DOM ELEMENTS TOUCHED (all lazy per-call):
//
//   #kometa-update-rollup-badge   -- the rollup summary
//   #kometa-actions-heading       -- accordion header (attention)
//   #kometa-actions-toggle        -- accordion toggle button (attention)
//   #update-kometa-btn            -- the primary "Check / Update /
//                                    Install Kometa" button
//   #force-kometa-update          -- the "force" checkbox
//   #kometa-update-box            -- the update-info panel that
//                                    contains version diff + notes
//
// STATE TOUCHED:
//
//   Reads: kometaState.kometaUpdating,
//          kometaState.kometaValidationInProgress,
//          kometaState.kometaLocalCheckCompleted,
//          kometaState.kometaInstalled,
//          kometaState.kometaValidated,
//          kometaState.kometaUpdateAvailable,
//          kometaState.kometaUpdateCheckCompleted,
//          kometaState.kometaUpdateCheckSkipped
//   Writes: kometaState.kometaUpdateAvailable,
//           kometaState.kometaUpdateCheckCompleted,
//           kometaState.kometaUpdateCheckSkipped,
//           kometaState.kometaRemoteVersionStatus,
//           kometaState.kometaRemoteVersionChecked,
//           kometaState.kometaRemoteVersionSkipped
//   (invalidateKometaUpdateStatus is the only writer)

import { kometaState } from './_state.js'
import { getConfiguredKometaInstallMode } from './_runtime.js'
import { syncKometaSourceStatus } from './_kometaBranch.js'

// ---------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------

/**
 * All four qs-validation-rollup-badge--* classes. Removed en masse
 * before adding the current state's class so the badge only has ONE
 * status class at a time regardless of prior render.
 */
const ROLLUP_BADGE_CLASSES = [
  'qs-validation-rollup-badge--unknown',
  'qs-validation-rollup-badge--ok',
  'qs-validation-rollup-badge--warn',
  'qs-validation-rollup-badge--error'
]

// ---------------------------------------------------------------------
// Rollup status (pure) + badge sync
// ---------------------------------------------------------------------

/**
 * Return the current rollup status as { state, label }.
 *
 * PURE FUNCTION -- only reads kometaState, no DOM, no side effects.
 * Priority order (first-match wins):
 *
 *   1. kometaUpdating          -> 'unknown' / 'Updating...'
 *   2. kometaValidationInProgress -> 'unknown' / 'Checking...'
 *   3. !kometaLocalCheckCompleted -> 'unknown' / 'Not checked'
 *   4. !kometaInstalled           -> 'error'   / 'Install needed'
 *   5. !kometaUpdateCheckCompleted -> depends on kometaValidated:
 *         validated   -> 'ok'   / 'Prepared'
 *         !validated  -> 'warn' / 'Prepare needed'
 *   6. kometaUpdateCheckSkipped  -> 'unknown' / 'Skipped while running'
 *   7. kometaUpdateAvailable     -> 'warn'    / 'Update available'
 *   8. (fallback)                -> 'ok'      / 'Up to date'
 *
 * @returns {{state: 'unknown' | 'ok' | 'warn' | 'error', label: string}}
 */
export function getKometaRollupStatus () {
  if (kometaState.kometaUpdating) return { state: 'unknown', label: 'Updating...' }
  if (kometaState.kometaValidationInProgress) return { state: 'unknown', label: 'Checking...' }
  if (!kometaState.kometaLocalCheckCompleted) return { state: 'unknown', label: 'Not checked' }
  if (!kometaState.kometaInstalled) return { state: 'error', label: 'Install needed' }
  if (!kometaState.kometaUpdateCheckCompleted) {
    return {
      state: kometaState.kometaValidated ? 'ok' : 'warn',
      label: kometaState.kometaValidated ? 'Prepared' : 'Prepare needed'
    }
  }
  if (kometaState.kometaUpdateCheckSkipped) return { state: 'unknown', label: 'Skipped while running' }
  if (kometaState.kometaUpdateAvailable) return { state: 'warn', label: 'Update available' }
  return { state: 'ok', label: 'Up to date' }
}

/**
 * Write the rollup status onto the #kometa-update-rollup-badge
 * element (text content + one of the four qs-validation-rollup-badge--*
 * classes). No-op when the badge is missing.
 */
export function syncKometaRollupBadge () {
  const badge = document.getElementById('kometa-update-rollup-badge')
  if (!badge) return
  const { state, label } = getKometaRollupStatus()
  badge.textContent = label
  badge.classList.remove(...ROLLUP_BADGE_CLASSES)
  badge.classList.add(`qs-validation-rollup-badge--${state}`)
}

// ---------------------------------------------------------------------
// Attention indicator
// ---------------------------------------------------------------------

/**
 * Toggle the .kometa-update-attention class on the accordion header
 * and toggle button when:
 *   - An update is available AND
 *   - The accordion is currently collapsed
 *
 * Rationale: when the accordion is open the user can already see the
 * update state, so the pulsing attention indicator is redundant. Only
 * highlight when collapsed.
 *
 * Always refreshes the rollup badge as a side effect -- callers that
 * want to update BOTH the badge and the attention state can call
 * this and get both in one shot.
 *
 * No-op when the heading or toggle element is missing (typical of
 * pages other than the /kometa step).
 */
export function syncKometaUpdateAttention () {
  const heading = document.getElementById('kometa-actions-heading')
  const toggle = document.getElementById('kometa-actions-toggle')
  if (heading && toggle) {
    const isCollapsed = toggle.classList.contains('collapsed')
    const needsAttention = kometaState.kometaUpdateAvailable && isCollapsed
    heading.classList.toggle('kometa-update-attention', needsAttention)
    toggle.classList.toggle('kometa-update-attention', needsAttention)
  }
  syncKometaRollupBadge()
}

// ---------------------------------------------------------------------
// Update-button label
// ---------------------------------------------------------------------

/**
 * Build the innerHTML string for the primary #update-kometa-btn.
 *
 * Two flavors:
 *   - 'existing' install mode: 'Check' or 'Recheck Existing Status'
 *     depending on whether we've already run a check this session.
 *   - default (managed) install mode: 5-way state machine driven by
 *     force-toggle + kometaInstalled + kometaUpdateAvailable +
 *     kometaUpdateCheckCompleted. Force wins over everything.
 *
 * All labels include the bi-arrow-clockwise icon prefix.
 *
 * @returns {string} HTML string for the button's innerHTML
 */
export function getUpdateButtonLabel () {
  const installMode = getConfiguredKometaInstallMode()
  if (installMode === 'existing') {
    const label = kometaState.kometaUpdateCheckCompleted
      ? 'Recheck Existing Status'
      : 'Check Existing Status'
    return `<i class="bi bi-arrow-clockwise me-1"></i> ${label}`
  }

  // NOTE: the original code does `forceUpdateToggle.checked` without
  // a null check. On pages where #force-kometa-update is absent that
  // would throw a TypeError -- but every page that renders the
  // update button also renders the force toggle, so it never fires
  // in practice. Preserving the strict-lookup behavior verbatim; the
  // hardening (Boolean(el && el.checked)) belongs in a follow-up.
  const forceToggle = document.getElementById('force-kometa-update')
  const force = forceToggle.checked

  let label
  if (force) {
    label = kometaState.kometaInstalled ? 'Force Update Kometa' : 'Force Install Kometa'
  } else if (!kometaState.kometaInstalled) {
    label = 'Install Kometa'
  } else if (kometaState.kometaUpdateAvailable) {
    label = 'Update Available'
  } else if (kometaState.kometaUpdateCheckCompleted) {
    label = 'Up to date'
  } else {
    label = 'Check for Kometa Updates'
  }
  return `<i class="bi bi-arrow-clockwise me-1"></i> ${label}`
}

/**
 * Write the current label to the update button (if it exists) and
 * refresh the attention indicator + rollup badge.
 *
 * No-op DOM path when the button is missing; still refreshes the
 * attention indicator (which itself is a no-op when the accordion
 * elements aren't present).
 */
export function syncUpdateButtonLabel () {
  const btn = document.getElementById('update-kometa-btn')
  if (btn) btn.innerHTML = getUpdateButtonLabel()
  syncKometaUpdateAttention()
}

// ---------------------------------------------------------------------
// Update-status invalidation
// ---------------------------------------------------------------------

/**
 * Reset every kometaState update field to its pre-check default and
 * hide the update-info box. Refreshes the source-status panel, the
 * update button label, and the rollup badge so the UI reflects the
 * cleared state.
 *
 * Called when we know the update-check result is stale -- e.g. after
 * the user switches install modes, or after a force-update kicks off
 * and we want the "check" flow to restart from scratch.
 *
 * Note: does NOT reset kometaLocalCheckCompleted or kometaValidated
 * -- those track "have we ever probed the local install?" which is
 * independent of "is the remote update check current?".
 */
export function invalidateKometaUpdateStatus () {
  kometaState.kometaUpdateAvailable = false
  kometaState.kometaUpdateCheckCompleted = false
  kometaState.kometaUpdateCheckSkipped = false
  kometaState.kometaRemoteVersionStatus = ''
  kometaState.kometaRemoteVersionChecked = false
  kometaState.kometaRemoteVersionSkipped = false
  // NOTE: original didn't null-check #kometa-update-box either --
  // preserved verbatim. Every page that reaches this code path also
  // renders the box.
  document.getElementById('kometa-update-box').classList.add('d-none')
  syncKometaSourceStatus()
  syncUpdateButtonLabel()
  syncKometaRollupBadge()
}
