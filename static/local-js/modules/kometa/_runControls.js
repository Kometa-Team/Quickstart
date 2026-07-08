// Run controls: the "Run Now" button and the "Recovery Command" button.
//
// This module owns the two functions that decide whether these
// buttons should be enabled / clickable, based on the current
// kometaState:
//
//   updateRunNowState        -- enables/disables the primary Run Now
//                               button based on the six-flag state
//                               machine (validation + install +
//                               running-status + run-command validity)
//
//   syncIncompleteRunActions -- shows/hides the recovery button and
//                               sets a helpful title tooltip based on
//                               why it's disabled (if disabled)
//
// Plus two trivial DOM-reader helpers used by both this module and
// 900-kometa.js callers that need the current command text:
//
//   getCurrentRunCommand     -- text of the main run-command panel
//   getRecoveryRunCommand    -- text of the recovery panel
//
// STATE FLOW:
//
//   validation + install + running-status flags live in kometaState.
//   This module reads them via imports; never writes them.
//
//   The two "update button" functions get called from many places
//   in 900-kometa.js (event handlers, polling callbacks, validation
//   completion, etc.) -- all of which currently pass through the
//   default kometaState. Once every caller is either extracted or
//   uses kometaState directly, this module is fully self-contained.

import { kometaState } from './_state.js'
import { updateRunCommandHeaderBadge } from './_headerBadges.js'
import { isRunCommandValid } from './_runCommand.js'

// ---------------------------------------------------------------------
// Command-text readers (trivial DOM accessors)
// ---------------------------------------------------------------------

/**
 * The exact command shown in the main run-command panel. Trimmed of
 * leading/trailing whitespace. Empty string if the panel is missing.
 *
 * @returns {string}
 */
export function getCurrentRunCommand () {
  const el = document.getElementById('run-command-output')
  return el ? el.textContent.trim() : ''
}

/**
 * The command shown in the recovery panel (only visible when an
 * interrupted run left recoverable state behind).
 *
 * @returns {string}
 */
export function getRecoveryRunCommand () {
  const el = document.getElementById('recovery-command-output')
  return el ? el.textContent.trim() : ''
}

// ---------------------------------------------------------------------
// Run Now button
// ---------------------------------------------------------------------

/**
 * Update the Run Now button's disabled state based on current
 * validation + install + running-status flags.
 *
 * Disable rules (any one triggers disable):
 *   - showYAML is false (config not passing)
 *   - kometaValidationInProgress
 *   - kometaUpdating
 *   - kometaStatus === 'running'
 *   - !kometaValidated
 *   - !isRunCommandValid() (command panel shows a placeholder)
 *
 * Enabled only when every one of the above is favorable.
 *
 * Side effect: always refreshes the run-command header badge + the
 * recovery button state (in one pass), so any caller of this function
 * gets a consistent UI update.
 *
 * No-op DOM path (button missing): still refreshes badge + recovery
 * so pages without the primary button still get their subsidiary
 * UI updated.
 */
export function updateRunNowState () {
  const runNow = document.getElementById('run-now')

  // Even when the button is absent, keep the badge and recovery
  // button in sync -- some pages / test fixtures render one but not
  // the other.
  if (!runNow) {
    updateRunCommandHeaderBadge()
    syncIncompleteRunActions()
    return
  }

  // The five "disable because state isn't ready" conditions.
  // Kept as separate booleans to preserve the original short-circuit
  // ordering (in case future changes need to distinguish which flag
  // triggered).
  const notReady = (
    !kometaState.showYAML ||
    kometaState.kometaValidationInProgress ||
    kometaState.kometaUpdating ||
    kometaState.kometaStatus === 'running' ||
    !kometaState.kometaValidated
  )

  if (notReady) {
    runNow.disabled = true
  } else if (!isRunCommandValid()) {
    // State is ready but the command panel is showing '??' or empty.
    runNow.disabled = true
  } else {
    runNow.disabled = false
  }

  updateRunCommandHeaderBadge()
  syncIncompleteRunActions()
}

// ---------------------------------------------------------------------
// Recovery button
// ---------------------------------------------------------------------

/**
 * Show/hide the recovery-command button and set its tooltip to
 * explain why it's disabled (when disabled).
 *
 * The button is:
 *   - Hidden entirely (via .d-none) when there's no incomplete-run
 *     recovery alert visible (i.e. nothing to recover).
 *   - Visible but disabled when a recovery is possible in principle
 *     but blocked by transient state (updating / running / pending).
 *   - Enabled when a recovery command exists AND no blocker is active.
 *
 * The title attribute is set to a specific message for each disabled
 * case so users get a clear reason why they can't click.
 */
export function syncIncompleteRunActions () {
  const runRecovery = document.getElementById('run-recovery-command')
  if (!runRecovery) return

  const incompleteAlert = document.getElementById('incomplete-run-alert')
  const recoveryCommand = getRecoveryRunCommand()
  const alertVisible = Boolean(incompleteAlert) && !incompleteAlert.classList.contains('d-none')
  const recoveryRunnable = Boolean(recoveryCommand) &&
    alertVisible &&
    !kometaState.kometaValidationInProgress &&
    !kometaState.kometaUpdating &&
    !kometaState.kometaPendingStart &&
    kometaState.kometaStatus !== 'running'

  runRecovery.classList.toggle('d-none', !alertVisible)
  runRecovery.disabled = !recoveryRunnable

  // Tooltip: only one of these applies at a time (checked in
  // priority order). Priority order preserved from the pre-extraction
  // version.
  if (recoveryRunnable) {
    runRecovery.removeAttribute('title')
  } else if (!alertVisible) {
    runRecovery.setAttribute('title', 'Recovery actions are only available when an incomplete-run recovery command is visible.')
  } else if (kometaState.kometaValidationInProgress) {
    runRecovery.setAttribute('title', 'Wait for Kometa validation to finish before starting a recovery run.')
  } else if (kometaState.kometaUpdating) {
    runRecovery.setAttribute('title', 'Wait for the Kometa update to finish before starting a recovery run.')
  } else if (kometaState.kometaPendingStart) {
    runRecovery.setAttribute('title', 'A Kometa start is already queued for the next Plex maintenance window.')
  } else if (kometaState.kometaStatus === 'running') {
    runRecovery.setAttribute('title', 'Kometa is already running.')
  } else {
    // Alert is visible, no blockers, but no recovery command in the
    // panel. Unusual state (server said recovery is possible but the
    // command wasn't populated).
    runRecovery.setAttribute('title', 'No recovery command is available for this incomplete run.')
  }
}
