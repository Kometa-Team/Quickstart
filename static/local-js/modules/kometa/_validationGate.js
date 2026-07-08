// The "final validation gate" logic that decides whether the user can
// see YAML output + run controls, or whether they need to keep fixing
// upstream steps first.
//
// TWO EXPORTS, ONE INTERNAL STATE MUTATION:
//
//   getFinalGateState()      reads the hidden #final-gate-state element
//                             (which the server populates with the
//                             aggregate stage/todo/config-validity
//                             status). Returns a small object; never
//                             mutates anything.
//
//   updateValidationGate()   the main orchestration function. Called
//                             on page load and whenever a validation
//                             flag changes. Mutates kometaState.showYAML,
//                             toggles a swarm of .d-none classes on
//                             warning/download/YAML/run-controls
//                             elements, populates the validation-messages
//                             element with per-step links, and finally
//                             delegates to two callback-style extension
//                             points (updateRunNowState +
//                             syncFinalAccordionRollups).
//
// EXTENSION POINTS:
//
//   updateValidationGate takes both callbacks as REQUIRED parameters.
//   This is a temporary bridge pattern -- the "real" version once
//   ALL of 900-kometa.js is split will be imports from the modules
//   that own those functions. Until then, callers in 900-kometa.js
//   pass the functions in explicitly.
//
//   Rationale: making the callbacks parameters (rather than importing
//   them here) means _validationGate.js has ZERO imports from
//   900-kometa.js, keeping the dependency graph acyclic. It also makes
//   the module trivially testable -- vitest can pass vi.fn() spies.
//
// PROTOCOL FOR "GATE STAGE":
//
//   The server encodes the wizard's aggregate progress via
//   #final-gate-state's data-* attributes:
//     data-stage        'todo' | 'freshness' | 'config'
//     data-todo-count   number
//     data-auto-validate boolean
//     data-config-valid  boolean
//     data-bulk-fresh    boolean
//
//   When stage is 'todo' OR 'freshness', we hide everything downstream
//   (YAML, run controls, downloads) -- the user has upstream work to
//   do before this section is meaningful. When stage is 'config' (or
//   anything else), we consult the per-page validity flags to decide
//   whether YAML/run should be visible.

import { kometaState } from './_state.js'
import { readMetaFlag } from './_util.js'

/**
 * Read the current gate state from the server-populated
 * #final-gate-state hidden element. Safe to call before DOMContentLoaded:
 * returns a conservative default if the element is missing.
 *
 * @returns {{
 *   stage: 'todo' | 'freshness' | 'config' | string,
 *   todoCount?: number,
 *   autoValidate: boolean,
 *   configValid: boolean,
 *   bulkFresh?: boolean
 * }}
 */
export function getFinalGateState () {
  const el = document.getElementById('final-gate-state')
  if (!el) {
    return {
      stage: 'config',
      autoValidate: false,
      configValid: false
    }
  }
  return {
    stage: String(el.dataset.stage || 'config'),
    todoCount: Number(el.dataset.todoCount || 0),
    autoValidate: el.dataset.autoValidate === 'true',
    configValid: el.dataset.configValid === 'true',
    bulkFresh: el.dataset.bulkFresh === 'true'
  }
}

// Small helper: toggle .d-none on a group of ids in one call. Missing
// elements are silently skipped (matches the pre-extraction behavior).
function toggleGroup (ids, cls, add) {
  ids.forEach(id => {
    const el = document.getElementById(id)
    if (el) el.classList.toggle(cls, add)
  })
}

// Single-source-of-truth for the per-validation link row template.
// The `href` becomes an anchor to the corresponding wizard step;
// clicking it lets the user jump back to fix the missing setting.
function rowFor (label, href) {
  return `
      <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
        <span>${label}</span>
        <a href="${href}" class="ms-2 text-decoration-none">
          Open page
          <i class="bi bi-box-arrow-up-right"></i>
        </a>
      </div>
    `
}

/**
 * The main gate orchestration. Toggles the entire "final YAML +
 * run controls" region visible or hidden based on:
 *   - final-gate-state stage
 *   - the five per-page validation flags
 *
 * MUTATES kometaState.showYAML as a side-effect. Callers should treat
 * kometaState.showYAML as read-only after this returns.
 *
 * @param {{
 *   updateRunNowState: () => void,
 *   syncFinalAccordionRollups: () => void
 * }} callbacks  Extension points, see module docstring. Both are
 *               required; use no-op functions if the caller doesn't
 *               care about a particular hook. Tests should pass
 *               vi.fn() spies to verify orchestration order.
 */
export function updateValidationGate (callbacks) {
  const { updateRunNowState, syncFinalAccordionRollups } = callbacks || {}

  const validationMsgEl = document.getElementById('validation-messages')
  const runControls = document.getElementById('run-controls-container')
  const runNowEl = document.getElementById('run-now')
  const runNowLabelEl = document.getElementById('run-now-label')
  const warningIds = ['no-validation-warning', 'yaml-warnings', 'yaml-warning-msg', 'validation-error']
  const downloadIds = ['download-btn', 'download-redacted-btn']
  const yamlIds = ['yaml-content', 'final-yaml', 'download-btn', 'download-redacted-btn']

  const finalGate = getFinalGateState()
  if (finalGate.stage === 'todo' || finalGate.stage === 'freshness') {
    // Upstream work pending. Hide EVERYTHING downstream and short-circuit.
    kometaState.showYAML = false
    if (validationMsgEl) validationMsgEl.classList.add('d-none')
    toggleGroup(warningIds, 'd-none', true)
    toggleGroup(downloadIds, 'd-none', true)
    if (runControls) runControls.classList.add('d-none')
    if (runNowEl) runNowEl.disabled = true
    if (runNowLabelEl) runNowLabelEl.textContent = 'Run Now'
    if (typeof updateRunNowState === 'function') updateRunNowState()
    if (typeof syncFinalAccordionRollups === 'function') syncFinalAccordionRollups()
    return
  }

  // stage === 'config' (or fallback). Consult per-page flags.
  const plexValid = readMetaFlag('plex_valid', 'plexValid', 'plex-valid')
  const tmdbValid = readMetaFlag('tmdb_valid', 'tmdbValid', 'tmdb-valid')
  const libsValid = readMetaFlag('libs_valid', 'libsValid', 'libs-valid')
  const settValid = readMetaFlag('sett_valid', 'settValid', 'sett-valid')
  const yamlValid = readMetaFlag('yaml_valid', 'yamlValid', 'yaml-valid')

  // Two paths to a "yes, show it" verdict:
  //   1. Server-side config validation said 'yes' (finalGate.configValid)
  //   2. ALL five client-side per-page flags say 'yes'
  kometaState.showYAML = finalGate.configValid ||
    (plexValid && tmdbValid && libsValid && settValid && yamlValid)

  const validationMessages = []
  if (!plexValid) validationMessages.push(rowFor('Plex settings have not been validated successfully.', '/step/010-plex'))
  if (!tmdbValid) validationMessages.push(rowFor('TMDb settings have not been validated successfully.', '/step/020-tmdb'))
  if (!libsValid) validationMessages.push(rowFor('Libraries page settings have not been validated successfully.', '/step/025-libraries'))
  if (!settValid) validationMessages.push(rowFor('Settings page values have likely been skipped.', '/step/150-settings'))

  if (runNowEl) runNowEl.disabled = true
  if (runNowLabelEl) runNowLabelEl.textContent = 'Run Now'

  if (!kometaState.showYAML) {
    // Show validation messages if any, else just hide the panel
    if (validationMessages.length && validationMsgEl) {
      validationMsgEl.innerHTML = validationMessages.join('<br>')
      validationMsgEl.classList.remove('d-none')
    } else if (validationMsgEl) {
      validationMsgEl.classList.add('d-none')
    }
    toggleGroup(warningIds, 'd-none', false)
    toggleGroup(downloadIds, 'd-none', true)
    if (runControls) runControls.classList.add('d-none')
  } else {
    if (validationMsgEl) validationMsgEl.classList.add('d-none')
    toggleGroup(warningIds, 'd-none', true)
    toggleGroup(yamlIds, 'd-none', false)
    if (runControls) runControls.classList.remove('d-none')
    // NOTE: runNowEl.disabled stays true here -- the actual "enable
    // Run Now" call happens later in updateRunNowState after checking
    // the runtime-state (Kometa installed?, not currently running?, etc.)
  }

  if (typeof updateRunNowState === 'function') updateRunNowState()
  if (typeof syncFinalAccordionRollups === 'function') syncFinalAccordionRollups()
}
