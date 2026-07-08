// Kometa run-command builder and active-command state management.
//
// The "run command" is the exact CLI Quickstart shows in the UI --
// the one users can copy-paste to launch Kometa manually, or that
// Quickstart itself invokes on "Run Now". It's assembled from:
//
//   - the venv python + kometa.py paths (from #run-command-output dataset)
//   - the currently-selected run option (radio: default, --times,
//     --run-libraries, --collections-only, etc.)
//   - mode / log flag radios
//   - a bunch of independent option checkboxes (--delete-collections,
//     --read-only-config, ...)
//   - optional numeric fields (--timeout, --width, --divider) each
//     with their own validation rules
//   - the config filename (appended as --config)
//
// This module owns:
//
//   buildCommand                     -- the big assembler (~120 lines).
//                                        Returns true/false/undefined
//                                        depending on validation state.
//
// NOTE: isRunCommandValid moved to _util.js in PR #1572 to break a
// cycle. Import from './_util.js' if you need it.
//
//   getRunCommandModeLabel           -- label above the command panel
//   getRunCommandModeBadgeLabel      -- text of the mode indicator badge
//   getRunCommandModeBadgeClass      -- Bootstrap text-bg-* class for
//                                        the mode indicator badge
//
//   applyActiveRunCommandState       -- freeze the command panel at a
//                                        specific command + mode (writes
//                                        kometaState.activeRunCommand*)
//   clearActiveRunCommandState       -- reset to live-build mode (clears
//                                        kometaState.activeRunCommand*)
//
// Design notes:
//
//   1. buildCommand imports updateRunNowState (from _runControls.js)
//      and syncFinalAccordionRollups (from _headerBadges.js) directly.
//      These were callback parameters pre-#1572 to avoid a cycle with
//      _runControls.js (which needed isRunCommandValid from here).
//      Moving isRunCommandValid to _util.js in #1572 broke the cycle.
//
//   2. isWindowsPlatform is computed lazily via a private helper
//      each call rather than cached at module load. Trivial cost,
//      makes tests trivially controllable.
//
//   3. Validation error paths in buildCommand write to
//      runCmdOutput.textContent AND to specific error <div>s
//      (times-error, timeout-error, width-error, divider-error).
//      This dual-signal was pre-existing behavior: the top-line
//      command panel shows a friendly warning, and the field-level
//      error div shows the exact rule that was violated.

import { kometaState } from './_state.js'
import { quoteIfNeeded, isValidTimesFormat } from './_util.js'
import { toggleTimesInputVisibility, checkMaintenanceWarning } from './_maintenanceWindow.js'
import { updateRunNowState } from './_runControls.js'
import { syncFinalAccordionRollups } from './_headerBadges.js'

// ---------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------

/**
 * Lazily reads the `#qs-env` element's `data-running-on` attribute and
 * returns true iff the runtime is Windows. Called on every buildCommand
 * invocation -- getElementById is trivially fast and this way tests
 * can flip the env without a module reload.
 *
 * @returns {boolean}
 */
function isWindowsPlatform () {
  const envEl = document.getElementById('qs-env')
  const runningOn = (envEl && envEl.dataset.runningOn) || ''
  return typeof runningOn === 'string' && runningOn.includes('Windows')
}

// A "normalize the mode string" helper used by both the label
// look-ups and the state setters. Small enough to duplicate at each
// site would be OK, but centralizing makes it obvious the same
// normalization rule applies everywhere.
function normalizeMode (mode) {
  return String(mode || 'current').trim().toLowerCase() || 'current'
}

// ---------------------------------------------------------------------
// Command validity + labels
// ---------------------------------------------------------------------

/**
 * The user-facing label above the run-command panel. Matches the
 * "which command are we showing?" mode indicator.
 *
 * @param {string} mode
 * @returns {'Command' | 'Recovery Command' | 'Last Logged Command'}
 */
export function getRunCommandModeLabel (mode) {
  const normalized = normalizeMode(mode)
  if (normalized === 'recovery') return 'Recovery Command'
  if (normalized === 'logged') return 'Last Logged Command'
  return 'Command'
}

/**
 * The text of the mode indicator badge next to the run-command label.
 *
 * @param {string} mode
 * @returns {'Current Active' | 'Recovery Active' | 'Logged Active'}
 */
export function getRunCommandModeBadgeLabel (mode) {
  const normalized = normalizeMode(mode)
  if (normalized === 'recovery') return 'Recovery Active'
  if (normalized === 'logged') return 'Logged Active'
  return 'Current Active'
}

/**
 * The Bootstrap `text-bg-*` class to paint the mode indicator badge.
 *
 * @param {string} mode
 * @returns {'text-bg-warning' | 'text-bg-secondary' | 'text-bg-primary'}
 */
export function getRunCommandModeBadgeClass (mode) {
  const normalized = normalizeMode(mode)
  if (normalized === 'recovery') return 'text-bg-warning'
  if (normalized === 'logged') return 'text-bg-secondary'
  return 'text-bg-primary'
}

// ---------------------------------------------------------------------
// Active override state
// ---------------------------------------------------------------------

/**
 * Freeze the run-command panel on a specific command + mode.
 * Writes to kometaState.activeRunCommand{Override,Mode} so buildCommand
 * knows not to overwrite the panel on its next call.
 *
 * @param {string|null} command  The command string to display. Falsy
 *                                clears the override.
 * @param {string} mode          'current' | 'recovery' | 'logged'
 */
export function applyActiveRunCommandState (command, mode) {
  const normalizedMode = normalizeMode(mode)
  kometaState.activeRunCommandOverride = command || null
  kometaState.activeRunCommandMode = normalizedMode

  if (command) {
    const outEl = document.getElementById('run-command-output')
    if (outEl) outEl.textContent = command
  }

  const labelEl = document.getElementById('run-command-label')
  if (labelEl) labelEl.textContent = getRunCommandModeLabel(normalizedMode)

  const activeBadge = document.getElementById('run-command-active-badge')
  if (activeBadge) {
    activeBadge.classList.remove('d-none', 'text-bg-warning', 'text-bg-secondary', 'text-bg-primary')
    activeBadge.classList.add(getRunCommandModeBadgeClass(normalizedMode))
    activeBadge.textContent = getRunCommandModeBadgeLabel(normalizedMode)
  }
}

/**
 * Reset to live-build mode. Clears the override state and restores the
 * default "Command" label + hides the mode-indicator badge.
 */
export function clearActiveRunCommandState () {
  kometaState.activeRunCommandOverride = null
  kometaState.activeRunCommandMode = null

  const label = document.getElementById('run-command-label')
  if (label) label.textContent = 'Command'

  const activeBadge = document.getElementById('run-command-active-badge')
  if (activeBadge) {
    activeBadge.classList.add('d-none')
    activeBadge.classList.remove('text-bg-warning', 'text-bg-secondary', 'text-bg-primary')
    activeBadge.textContent = 'Recovery Active'
  }
}

// ---------------------------------------------------------------------
// buildCommand
// ---------------------------------------------------------------------

// Central list of "no-value option" checkboxes. Their id is
// `opt-<name>` and if checked they append `--<name>` to the CLI.
// Kept here as a top-level const so tests can import it if we ever
// want to assert the set.
const CHECKBOX_FLAGS = [
  'delete-collections', 'delete-labels', 'read-only-config', 'low-priority',
  'no-report', 'no-missing', 'no-countdown', 'ignore-ghost',
  'ignore-schedules', 'no-verify-ssl', 'tests'
]

/**
 * Assemble the current run command from the wizard's radios,
 * checkboxes, and text inputs. Writes the result to two places:
 *
 *   run-command-output.dataset.builtCommand -- always, as ground truth
 *   run-command-output.textContent          -- only if there's no
 *                                              active override
 *
 * Returns:
 *   true         -- command built successfully
 *   false        -- validation failed for a specific field
 *                    (times / --run-libraries / timeout / width /
 *                     divider)
 *   undefined    -- no run-command-output in the DOM (short-circuit)
 *
 * Side effects at every non-short-circuit exit:
 *   - updateRunNowState() -- refresh the Run Now button
 *   - syncFinalAccordionRollups() -- refresh header badges
 *
 * @returns {boolean | undefined}
 */
export function buildCommand () {
  const notify = () => {
    updateRunNowState()
    syncFinalAccordionRollups()
  }

  const runCmdOutput = document.getElementById('run-command-output')
  if (!runCmdOutput) return
  const configFilename = runCmdOutput.dataset.configFilename || ''

  // Always normalize to forward slashes for internal path assembly,
  // then swap to backslashes at the end only if we're on Windows.
  const pythonBinNorm = (runCmdOutput.dataset.venvPython || 'python3').replace(/\\/g, '/')
  const kometaRootNorm = (runCmdOutput.dataset.kometaRoot || '').replace(/\\/g, '/')

  const fullKometaPy = `${kometaRootNorm}/kometa.py`
  const fullConfigPath = `${kometaRootNorm}/config/${configFilename}`

  const isWin = isWindowsPlatform()
  const finalPythonBin = isWin ? pythonBinNorm.replace(/\//g, '\\') : pythonBinNorm
  const finalKometaPy = isWin ? fullKometaPy.replace(/\//g, '\\') : fullKometaPy
  const finalConfigPath = isWin ? fullConfigPath.replace(/\//g, '\\') : fullConfigPath

  let cli = `${quoteIfNeeded(finalPythonBin)} ${quoteIfNeeded(finalKometaPy)}`

  // ---- Primary run option (one radio in run-option group) ---------
  const mainOption = (document.querySelector('input[name="run-option"]:checked') || {}).value || ''
  const libSelectEl = document.getElementById('library-multiselect')
  const selectedLibs = libSelectEl ? Array.from(libSelectEl.selectedOptions || []).map(o => o.value) : []

  if (mainOption) cli += ` ${mainOption}`

  // ---- --times: validate + append quoted value --------------------
  if (mainOption === '--times') {
    const timesInput = document.getElementById('times-input').value.trim()
    const isValid = isValidTimesFormat(timesInput)
    toggleTimesInputVisibility('--times')
    if (!isValid) {
      document.getElementById('times-error').classList.remove('d-none')
      runCmdOutput.textContent = '⚠️ Invalid time format. Use pipe-separated 24h times like 06:00|15:00.'
      notify()
      return false
    }
    document.getElementById('times-error').classList.add('d-none')
    checkMaintenanceWarning(mainOption)
    cli += ` "${timesInput}"`
  } else {
    toggleTimesInputVisibility(mainOption)
  }

  // ---- --run-libraries: require at least one library selected -----
  if (mainOption === '--run-libraries') {
    if (!selectedLibs.length) {
      runCmdOutput.textContent = '⚠️ Please select at least one library when using --run-libraries.'
      notify()
      return false
    }
    cli += ` "${selectedLibs.join('|')}"`
  }

  // ---- Mode + log flag radios (optional, mutually exclusive) ------
  const modeFlag = (document.querySelector('input[name="mode-flag"]:checked') || {}).value
  if (modeFlag) cli += ` ${modeFlag}`

  const logFlag = (document.querySelector('input[name="log-flag"]:checked') || {}).value
  if (logFlag) cli += ` ${logFlag}`

  // ---- Standalone flag checkboxes ---------------------------------
  CHECKBOX_FLAGS.forEach(opt => {
    const checkbox = document.getElementById(`opt-${opt}`)
    if (checkbox && checkbox.checked) cli += ` --${opt}`
  })

  // Always append --config with the platform-adjusted path
  cli += ` --config ${quoteIfNeeded(finalConfigPath)}`

  // ---- --timeout: positive integer only ---------------------------
  const timeoutCheckbox = document.getElementById('opt-timeout')
  const timeoutChecked = !!(timeoutCheckbox && timeoutCheckbox.checked)
  const timeoutValue = (document.getElementById('opt-timeout-val') || {}).value?.trim?.() || ''
  if (timeoutChecked) {
    const timeoutNum = parseInt(timeoutValue, 10)
    if (!/^\d+$/.test(timeoutValue) || timeoutNum <= 0) {
      document.getElementById('timeout-error').classList.remove('d-none')
      runCmdOutput.textContent = '⚠️ Invalid timeout. Please enter a positive whole number.'
      notify()
      return false
    }
    document.getElementById('timeout-error').classList.add('d-none')
    cli += ` --timeout ${timeoutNum}`
  }

  // ---- --width: integer in [90, 300] ------------------------------
  const widthCheckbox = document.getElementById('opt-width')
  const widthChecked = !!(widthCheckbox && widthCheckbox.checked)
  const widthValue = (document.getElementById('opt-width-val') || {}).value?.trim?.() || ''
  if (widthChecked) {
    const widthNum = parseInt(widthValue, 10)
    if (!/^\d+$/.test(widthValue) || widthNum < 90 || widthNum > 300) {
      document.getElementById('width-error').classList.remove('d-none')
      runCmdOutput.textContent = '⚠️ Width must be a number between 90 and 300.'
      notify()
      return false
    }
    document.getElementById('width-error').classList.add('d-none')
    cli += ` --width ${widthNum}`
  }

  // ---- --divider: exactly one character ---------------------------
  const dividerCheckbox = document.getElementById('opt-divider')
  if (dividerCheckbox && dividerCheckbox.checked) {
    const dividerValue = (document.getElementById('opt-divider-val') || {}).value?.trim?.() || ''
    if (!dividerValue || dividerValue.length !== 1) {
      document.getElementById('divider-error').classList.remove('d-none')
      runCmdOutput.textContent = '⚠️ Divider must be a single character.'
      notify()
      return false
    }
    document.getElementById('divider-error').classList.add('d-none')
    cli += ` --divider "${dividerValue}"`
  }

  // ---- Success path -----------------------------------------------
  runCmdOutput.dataset.builtCommand = cli
  if (!kometaState.activeRunCommandOverride) {
    runCmdOutput.textContent = cli
  }
  notify()
  return true
}
