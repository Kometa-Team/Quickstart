// Section-header rollup badges for the Kometa page.
//
// The Kometa configuration page uses Bootstrap accordions. Each
// accordion header displays a small "rollup" badge summarizing the
// state of its section -- e.g. "Friendly", "3 libraries", "Times
// needed", "Invalid times". This module owns the badge functions that
// read the current UI + kometaState and set the appropriate badge
// text + color class.
//
// EXPORTS (grouped by dependency):
//
//   Pure DOM-reading helpers (no kometaState reads):
//
//     setHeaderRollupBadge         -- generic setter used by all badges
//     prettifyFlag                 -- helper for CLI flag -> label
//     updateSectionStyleHeaderBadge
//     updateModeHeaderBadge
//     updateRunOptionHeaderBadge
//     updateModeFlagsHeaderBadge
//     updateLogFlagsHeaderBadge
//     updateOtherFlagsHeaderBadge
//
//   State-consulting helpers (read kometaState + maybe DOM):
//
//     updateConfigOutputHeaderBadges  -- reads showYAML
//     updateRunCommandHeaderBadge     -- reads showYAML + kometaValidated
//                                        + kometaValidationInProgress
//                                        + kometaUpdating + kometaStatus
//                                        + isRunCommandValid()
//     updateLogscanHeaderBadge        -- reads lastLogscanPayload
//
//   Orchestrator:
//
//     syncFinalAccordionRollups({ syncKometaBranchRollupBadge })
//                                     -- one call to refresh every
//                                        badge on the page. Takes a
//                                        callbacks bag for functions
//                                        that still live in
//                                        900-kometa.js.
//
// COLOR CLASSES:
//
//   Every rollup badge lives in a single .qs-validation-rollup-badge
//   element that gets exactly one modifier class:
//
//     --unknown  neutral / not-yet-evaluated
//     --ok       everything looks good
//     --warn     user attention needed but not broken
//     --error    broken; must be fixed to proceed
//
//   setHeaderRollupBadge accepts any string; unknown values fall back
//   to 'unknown' to keep the badge visually consistent.

import { formatHeaderStyleLabel, isValidTimesFormat, computeYamlLineCount } from './_util.js'
import { kometaState } from './_state.js'
import { isRunCommandValid } from './_runCommand.js'

// ---------------------------------------------------------------------
// Core primitives
// ---------------------------------------------------------------------

/**
 * Update a single rollup badge in-place: sets its text and swaps
 * exactly one color-modifier class.
 *
 * No-op if the target element is missing (badges can be legitimately
 * absent when the enclosing accordion isn't rendered).
 *
 * @param {string} id       DOM id of the badge element
 * @param {string} state    one of 'unknown' | 'ok' | 'warn' | 'error'
 *                          (falls back to 'unknown' for any other value)
 * @param {string} label    Text to display in the badge
 */
export function setHeaderRollupBadge (id, state, label) {
  const badge = document.getElementById(id)
  if (!badge) return
  badge.textContent = label
  badge.classList.remove(
    'qs-validation-rollup-badge--unknown',
    'qs-validation-rollup-badge--ok',
    'qs-validation-rollup-badge--warn',
    'qs-validation-rollup-badge--error'
  )
  const normalized = ['unknown', 'ok', 'warn', 'error'].includes(state) ? state : 'unknown'
  badge.classList.add(`qs-validation-rollup-badge--${normalized}`)
}

/**
 * Human-readable form of a CLI-style flag value.
 *
 *   ''             -> 'Default'
 *   '--dry-run'    -> 'dry run'
 *   'foo-bar'      -> 'foo bar'
 *
 * Used by the flag-radio-group badges (mode, log, other) where the
 * <input value="--xxx"> is a CLI flag but we want to display it in
 * a human-friendly form.
 *
 * @param {*} value  the flag value; coerced to string, trimmed
 * @returns {string}
 */
export function prettifyFlag (value) {
  const raw = String(value || '').trim()
  if (!raw) return 'Default'
  const noPrefix = raw.replace(/^--/, '')
  return noPrefix.replace(/-/g, ' ')
}

// ---------------------------------------------------------------------
// Individual section badges
// ---------------------------------------------------------------------

/**
 * "Section style" is the header-look-and-feel picker. The badge
 * mirrors the currently-selected style name.
 */
export function updateSectionStyleHeaderBadge (value) {
  const label = formatHeaderStyleLabel(value)
  setHeaderRollupBadge('header-style-rollup-badge', 'ok', label || 'Active')
}

/**
 * "Mode" == the friendly-vs-CLI toggle. Two states: 'CLI labels' or
 * 'Friendly'. Always 'ok' color because either choice is valid.
 */
export function updateModeHeaderBadge () {
  const cliToggle = document.getElementById('show-cli-toggle')
  const showCli = Boolean(cliToggle && cliToggle.checked)
  setHeaderRollupBadge('heading-mode-rollup-badge', showCli ? 'ok' : 'unknown', showCli ? 'CLI labels' : 'Friendly')
}

/**
 * "Run option" is the top-level radio group: --run, --run-libraries,
 * --times, or scheduled default. Badge state depends on both the
 * selection AND its dependent inputs (libraries or times).
 */
export function updateRunOptionHeaderBadge () {
  const mainOption = (document.querySelector('input[name="run-option"]:checked') || {}).value || ''
  const libSelect = document.getElementById('library-multiselect')
  const selectedLibs = libSelect ? Array.from(libSelect.selectedOptions || []).map(o => o.value) : []
  if (mainOption === '--run-libraries') {
    if (!selectedLibs.length) {
      setHeaderRollupBadge('heading-runopt-rollup-badge', 'warn', 'Libraries needed')
    } else {
      setHeaderRollupBadge('heading-runopt-rollup-badge', 'ok', `${selectedLibs.length} libraries`)
    }
    return
  }
  if (mainOption === '--times') {
    const timesInput = document.getElementById('times-input').value.trim()
    if (!timesInput) {
      setHeaderRollupBadge('heading-runopt-rollup-badge', 'warn', 'Times needed')
      return
    }
    setHeaderRollupBadge('heading-runopt-rollup-badge', isValidTimesFormat(timesInput) ? 'ok' : 'error', isValidTimesFormat(timesInput) ? 'Times set' : 'Invalid times')
    return
  }
  if (mainOption === '--run') {
    setHeaderRollupBadge('heading-runopt-rollup-badge', 'ok', 'Run now')
    return
  }
  setHeaderRollupBadge('heading-runopt-rollup-badge', 'unknown', 'Scheduled')
}

/**
 * "Mode flags" == the collections/overlays/operations/libraries-first
 * radio group. Badge shows the human-friendly flag name.
 */
export function updateModeFlagsHeaderBadge () {
  const modeFlag = (document.querySelector('input[name="mode-flag"]:checked') || {}).value || ''
  setHeaderRollupBadge('heading-modeflags-rollup-badge', modeFlag ? 'ok' : 'unknown', prettifyFlag(modeFlag))
}

/**
 * "Log flags" == the debug/trace radio group. Same shape as mode flags.
 */
export function updateLogFlagsHeaderBadge () {
  const logFlag = (document.querySelector('input[name="log-flag"]:checked') || {}).value || ''
  setHeaderRollupBadge('heading-logflags-rollup-badge', logFlag ? 'ok' : 'unknown', prettifyFlag(logFlag))
}

/**
 * "Other flags" == the checkbox grid of boolean CLI flags plus the
 * three "with-value" extras (timeout, divider, width). Badge shows
 * a count of enabled flags.
 *
 * The core-flags list is hardcoded here because it maps 1:1 to the
 * checkbox DOM ids in the template; keeping it inline is more
 * readable than pushing it to a config file.
 */
export function updateOtherFlagsHeaderBadge () {
  const isChecked = (id) => {
    const el = document.getElementById(id)
    return Boolean(el && el.checked)
  }
  const coreCount = [
    'delete-collections', 'delete-labels', 'read-only-config', 'low-priority',
    'no-report', 'no-missing', 'no-countdown', 'ignore-ghost',
    'ignore-schedules', 'no-verify-ssl', 'tests'
  ].filter(opt => isChecked(`opt-${opt}`)).length
  const extrasCount = (isChecked('opt-timeout') ? 1 : 0) +
    (isChecked('opt-divider') ? 1 : 0) +
    (isChecked('opt-width') ? 1 : 0)
  const total = coreCount + extrasCount
  if (!total) {
    setHeaderRollupBadge('heading-otherflags-rollup-badge', 'unknown', 'Default')
    return
  }
  setHeaderRollupBadge('heading-otherflags-rollup-badge', 'ok', `${total} enabled`)
}

// ---------------------------------------------------------------------
// State-consulting badges (read kometaState)
// ---------------------------------------------------------------------

/**
 * Config-output section rollup: shows YAML line count + a Validated /
 * Needs-fixes badge driven by kometaState.showYAML.
 *
 * DOM contract:
 *   - #final-yaml           <textarea> holding the generated YAML.
 *                            If absent or empty, the rollup badge
 *                            reports 'No YAML'.
 *   - #config-output-lines-badge   count-of-lines badge
 *   - #config-output-rollup-badge  overall pass/fail badge
 */
export function updateConfigOutputHeaderBadges () {
  const yamlOutput = document.getElementById('final-yaml')
  const yamlText = yamlOutput ? String(yamlOutput.value || '') : ''
  const lineCount = computeYamlLineCount(yamlText)
  setHeaderRollupBadge('config-output-lines-badge', lineCount > 0 ? 'ok' : 'unknown', `${lineCount} lines`)
  if (!yamlText.trim()) {
    setHeaderRollupBadge('config-output-rollup-badge', 'unknown', 'No YAML')
    return
  }
  setHeaderRollupBadge(
    'config-output-rollup-badge',
    kometaState.showYAML ? 'ok' : 'error',
    kometaState.showYAML ? 'Validated' : 'Needs fixes'
  )
}

/**
 * Run-command section rollup: a five-way state machine keyed on
 * validation + install + running-status flags. Prioritized top-down:
 *
 *   showYAML false                    -- config not passing yet:
 *                                        'Fix validation' (error)
 *   kometaValidationInProgress        -- 'Checking Kometa' (unknown)
 *   kometaUpdating                    -- 'Updating Kometa' (unknown)
 *   !kometaValidated                  -- 'Validate Kometa' (warn)
 *   kometaStatus === 'running'        -- 'Run in progress' (warn)
 *   otherwise                         -- isRunCommandValid() ?
 *                                          'Ready' (ok) :
 *                                          'Incomplete' (warn)
 */
export function updateRunCommandHeaderBadge () {
  if (!kometaState.showYAML) {
    setHeaderRollupBadge('run-command-rollup-badge', 'error', 'Fix validation')
    return
  }
  if (kometaState.kometaValidationInProgress) {
    setHeaderRollupBadge('run-command-rollup-badge', 'unknown', 'Checking Kometa')
    return
  }
  if (kometaState.kometaUpdating) {
    setHeaderRollupBadge('run-command-rollup-badge', 'unknown', 'Updating Kometa')
    return
  }
  if (!kometaState.kometaValidated) {
    setHeaderRollupBadge('run-command-rollup-badge', 'warn', 'Validate Kometa')
    return
  }
  if (kometaState.kometaStatus === 'running') {
    setHeaderRollupBadge('run-command-rollup-badge', 'warn', 'Run in progress')
    return
  }
  const valid = isRunCommandValid()
  setHeaderRollupBadge(
    'run-command-rollup-badge',
    valid ? 'ok' : 'warn',
    valid ? 'Ready' : 'Incomplete'
  )
}

/**
 * Logscan section rollup: driven by the most recent /logscan payload.
 * Callers can pass a fresh payload directly (e.g. right after fetch);
 * omitting the arg uses the cached one in kometaState.lastLogscanPayload.
 *
 * @param {object} [data]  Optional payload to render from. Falls back
 *                         to kometaState.lastLogscanPayload.
 */
export function updateLogscanHeaderBadge (data) {
  const source = data || kometaState.lastLogscanPayload
  if (!source) {
    setHeaderRollupBadge('logscan-rollup-badge', 'unknown', 'Pending')
    return
  }
  if (source.error) {
    setHeaderRollupBadge('logscan-rollup-badge', 'error', 'Unavailable')
    return
  }
  const recCount = Array.isArray(source.recommendations) ? source.recommendations.length : 0
  const missingCount = Array.isArray(source.missing_people) ? source.missing_people.length : 0
  const issueCount = recCount + missingCount
  if (!issueCount) {
    setHeaderRollupBadge('logscan-rollup-badge', 'ok', 'No issues')
    return
  }
  setHeaderRollupBadge('logscan-rollup-badge', 'warn', `${issueCount} items`)
}

// ---------------------------------------------------------------------
// Orchestrator
// ---------------------------------------------------------------------

/**
 * Refresh every section-header rollup badge on the page. One call
 * to bring the whole accordion into sync with current state.
 *
 * The `syncKometaBranchRollupBadge` function still lives in
 * 900-kometa.js (it depends on branch-override helpers that haven't
 * been extracted yet), so we take it as a callback. When those
 * helpers migrate to _kometaUpdate.js, this callback retires in favor
 * of a direct import.
 *
 * @param {{ syncKometaBranchRollupBadge: () => void }} [callbacks]
 */
export function syncFinalAccordionRollups (callbacks) {
  updateModeHeaderBadge()
  updateRunOptionHeaderBadge()
  updateModeFlagsHeaderBadge()
  updateLogFlagsHeaderBadge()
  updateOtherFlagsHeaderBadge()
  updateConfigOutputHeaderBadges()
  updateRunCommandHeaderBadge()
  updateLogscanHeaderBadge()
  if (callbacks && typeof callbacks.syncKometaBranchRollupBadge === 'function') {
    callbacks.syncKometaBranchRollupBadge()
  }
}
