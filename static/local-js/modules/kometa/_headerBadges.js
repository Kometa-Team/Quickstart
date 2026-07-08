// Section-header rollup badges for the Kometa page.
//
// The Kometa configuration page uses Bootstrap accordions. Each
// accordion header displays a small "rollup" badge summarizing the
// state of its section -- e.g. "Friendly", "3 libraries", "Times
// needed", "Invalid times". This module owns the pure-DOM-reading
// badge functions that read the current UI state and set the
// appropriate badge text + color class.
//
// SCOPE OF THIS FILE (as of this PR):
//
//   Only the badge helpers that read exclusively from the DOM (no
//   shared module-level state). Concretely:
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
//   Three sibling badge functions stay in 900-kometa.js FOR NOW:
//
//     updateConfigOutputHeaderBadges  -- needs the `showYAML` bool
//     updateRunCommandHeaderBadge     -- needs 4 KOMETA_* flags,
//                                        KOMETA_STATUS, showYAML,
//                                        isRunCommandValid()
//     updateLogscanHeaderBadge        -- needs lastLogscanPayload
//
//   And the orchestrator:
//
//     syncFinalAccordionRollups       -- calls both extracted and
//                                        stay-behind functions
//
//   These will move here in follow-up PRs after the state they depend
//   on migrates to _state.js (which is #1557's foundational work).
//   Extracting the pure helpers first keeps the diff small and safe.
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

import { formatHeaderStyleLabel, isValidTimesFormat } from './_util.js'

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
