// Run-command section visibility helpers.
//
// The "Run Command" section is the block at the bottom of the Kometa
// wizard step that displays the actual shell command Quickstart will
// run to invoke Kometa. It's hidden until Kometa is validated (so we
// don't tempt users into running with a broken install).
//
// This module owns the show/hide/placeholder state machine for that
// section. Five exported functions form a small ladder:
//
//   Ladder direction: hidden -> placeholder -> revealed
//
//   setRunCommandPlaceholderState()
//     -- populate the placeholder panel with a title + message
//        describing WHY the run command isn't ready yet. Reads a lot
//        of kometaState (running / updating / validating / installed
//        / etc.) to pick the right message.
//
//   clearRunCommandPlaceholderState()
//     -- hide the placeholder panel + reveal the underlying run
//        command box. Called before revealRunCommandSection to hand
//        control from the placeholder to the actual command display.
//
//   hideRunCommandSectionUntilValidated()
//     -- collapse the run-command accordion and swap in the
//        placeholder. Also disables the "Run" button and puts it
//        into a "Waiting..." state. Called from many places (probe
//        errors, install-needed states, update in progress, etc.).
//
//   revealRunCommandSection()
//     -- expand the accordion, remove d-none from the box, and
//        trigger a CSS fade-in via a 10ms setTimeout. The setTimeout
//        is essential: browsers won't animate a transition when the
//        display state changes in the same tick as the class change.
//
//   showRunCommandSectionAfterValidated()
//     -- convenience wrapper that unhides the section, resets the
//        "Run" button label to its default, rebuilds the run
//        command string, and refreshes the button's disabled state.
//
// STATE TOUCHED:
//
//   Reads: kometaState.showYAML, kometaState.kometaStatus,
//          kometaState.kometaUpdating,
//          kometaState.kometaValidationInProgress,
//          kometaState.kometaLocalCheckCompleted,
//          kometaState.kometaInstalled,
//          kometaState.kometaValidated
//   Writes: (none directly; state changes happen via other modules)
//
// DOM ELEMENTS TOUCHED (all lazy per-call):
//
//   #run-command-panel-message   -- the placeholder panel container
//   #run-command-panel-title     -- placeholder title text
//   #run-command-panel-text      -- placeholder body text
//   #open-kometa-actions-panel-button
//                                -- link to Prepare Kometa
//   #run-command-box             -- the actual command display
//   #run-command-placeholder     -- alt placeholder element
//   #open-kometa-actions-button  -- alt link element
//   #run-command-output-accordion
//                                -- the Bootstrap accordion wrapper
//   #run-command-output-collapse -- the accordion collapsable body
//   #run-command-output-heading .accordion-button
//                                -- accordion toggle button
//   #run-now                     -- the "Run" button
//   #copy-command                -- the copy-to-clipboard button
//   #run-command-box .form-label -- the label above the command
//   #run-command-box pre         -- the <pre> that holds the command

import { kometaState } from './_state.js'
import { getConfiguredKometaInstallMode } from './_runtime.js'
import { buildCommand } from './_runCommand.js'
import { updateRunNowState } from './_runControls.js'

// ---------------------------------------------------------------------
// Placeholder show / hide
// ---------------------------------------------------------------------

/**
 * Populate the placeholder panel with a title + message describing
 * WHY the run command isn't ready yet. No-op when the placeholder
 * container is missing (typical of pages that don't render the run
 * command section).
 *
 * Priority order (first match wins):
 *   1. !showYAML             -> "Fix validation before..."
 *   2. running               -> "Kometa is currently running"
 *   3. kometaUpdating        -> "Kometa update in progress"
 *   4. validationInProgress  -> "Preparing Kometa"
 *   5. !localCheckCompleted  -> "Checking Kometa state"
 *   6. !kometaInstalled      -> "Install Kometa to build..."
 *   7. !kometaValidated      -> "Validate Kometa to build..."
 *   8. (fallback)            -> mode-aware default message
 *
 * NOTE: original didn't null-check panelTitle / panelText / panelButton
 * / box either -- preserved verbatim. Every page that renders
 * #run-command-panel-message also renders the other four.
 */
export function setRunCommandPlaceholderState () {
  const panel = document.getElementById('run-command-panel-message')
  const panelTitle = document.getElementById('run-command-panel-title')
  const panelText = document.getElementById('run-command-panel-text')
  const panelButton = document.getElementById('open-kometa-actions-panel-button')
  const box = document.getElementById('run-command-box')

  if (!panel) return

  const installMode = getConfiguredKometaInstallMode()
  let title = 'Run command is not ready yet'
  let message = installMode === 'existing'
    ? 'Open Prepare Kometa to validate the existing Kometa setup and check whether it needs a manual update before running.'
    : 'Open Prepare Kometa to install, validate, or update the local Kometa setup before running.'
  let showButton = true

  if (!kometaState.showYAML) {
    title = 'Fix validation before building the run command'
    message = 'Resolve the current validation issues first. The run command will appear after the config validates cleanly.'
    showButton = false
  } else if (kometaState.kometaStatus === 'running') {
    title = 'Kometa is currently running'
    message = 'Run output and stop controls are active below. Prepare Kometa is locked until the current run finishes.'
    showButton = false
  } else if (kometaState.kometaUpdating) {
    title = 'Kometa update in progress'
    message = 'Wait for the current install or update to finish. The run command will appear automatically afterward.'
  } else if (kometaState.kometaValidationInProgress) {
    title = 'Preparing Kometa'
    message = 'Quickstart is validating the Kometa folder and environment now. The run command will appear automatically when ready.'
  } else if (!kometaState.kometaLocalCheckCompleted) {
    title = 'Checking Kometa state'
    message = 'Quickstart is probing the local Kometa path. Wait for that check to finish, then prepare Kometa if needed.'
    showButton = false
  } else if (!kometaState.kometaInstalled) {
    title = 'Install Kometa to build the run command'
    message = 'Kometa is not installed in the selected path yet. Open Prepare Kometa to install it first.'
  } else if (!kometaState.kometaValidated) {
    title = 'Validate Kometa to build the run command'
    message = 'Next step: open Prepare Kometa, let Quickstart validate the Kometa folder and environment, then this command will be generated here.'
  }

  panelTitle.textContent = title
  panelText.textContent = message
  panelButton.classList.toggle('d-none', !showButton)
  panel.classList.remove('d-none')
  box.classList.add('d-none')
  box.classList.remove('fade-in')
}

/**
 * Hide the placeholder + reveal the underlying run command box.
 * Called before revealRunCommandSection to hand control from the
 * placeholder to the actual command display.
 *
 * NOTE: original didn't null-check any of these -- preserved verbatim.
 */
export function clearRunCommandPlaceholderState () {
  document.getElementById('run-command-panel-message').classList.add('d-none')
  document.getElementById('run-command-placeholder').classList.add('d-none')
  document.getElementById('open-kometa-actions-button').classList.add('d-none')
  document.getElementById('run-command-box').classList.remove('d-none')
  document.querySelector('#run-command-box .form-label').classList.remove('d-none')
  document.querySelector('#run-command-box pre').classList.remove('d-none')
  document.getElementById('copy-command').classList.remove('d-none')
}

// ---------------------------------------------------------------------
// Full section show / hide
// ---------------------------------------------------------------------

/**
 * Collapse the run-command accordion and swap in the placeholder.
 * Also disables the "Run" button and puts it into a "Waiting..."
 * state (so a distracted user can't click it while validation is
 * pending).
 *
 * Every DOM lookup here IS null-checked (the accordion + collapse +
 * heading + run-now button are optional per-page), which is why this
 * helper is safer than the reveal side that assumes everything exists.
 */
export function hideRunCommandSectionUntilValidated () {
  const accordion = document.getElementById('run-command-output-accordion')
  if (accordion) accordion.classList.remove('d-none')
  const collapse = document.getElementById('run-command-output-collapse')
  if (collapse) collapse.classList.remove('show')
  const headingBtn = document.querySelector('#run-command-output-heading .accordion-button')
  if (headingBtn) {
    headingBtn.classList.add('collapsed')
    headingBtn.setAttribute('aria-expanded', 'false')
  }
  setRunCommandPlaceholderState()

  const runNowBtn = document.getElementById('run-now')
  if (runNowBtn) {
    runNowBtn.disabled = true
    runNowBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i> Waiting...'
  }
}

/**
 * Expand the accordion, remove d-none from the box, and trigger a
 * CSS fade-in via a 10ms setTimeout.
 *
 * The setTimeout is essential: browsers won't animate a transition
 * when the display state changes in the same tick as the class
 * change. The 10ms delay gives the browser a chance to register
 * the display change before we add the 'fade-in' class.
 *
 * NOTE: assumes the accordion / collapse / heading elements exist
 * (original code did too). Only defensively looks up #run-command-box
 * because the fade-in adds a class.
 */
export function revealRunCommandSection () {
  const accordion = document.getElementById('run-command-output-accordion')
  const box = document.getElementById('run-command-box')

  clearRunCommandPlaceholderState()
  accordion.classList.remove('d-none')
  document.getElementById('run-command-output-collapse').classList.add('show')
  document.querySelector('#run-command-output-heading .accordion-button').classList.remove('collapsed')
  document.querySelector('#run-command-output-heading .accordion-button').setAttribute('aria-expanded', 'true')
  box.classList.remove('d-none') // Reveal element (opacity still 0)
  setTimeout(() => {
    box.classList.add('fade-in') // Let browser register change, then fade in
  }, 10)
}

/**
 * Convenience wrapper that unhides the section, resets the "Run"
 * button label to its default, rebuilds the run command string, and
 * refreshes the button's disabled state.
 *
 * Called after successful validation to hand the UI over to the
 * "ready to run" state.
 */
export function showRunCommandSectionAfterValidated () {
  clearRunCommandPlaceholderState()
  revealRunCommandSection()
  const runNowEl = document.getElementById('run-now')
  if (runNowEl) {
    runNowEl.innerHTML = '<i class="bi bi-play-fill me-1"></i> <span id="run-now-label">Run</span>'
  }
  try { buildCommand() } catch { /* swallow -- caller may not need a rebuild */ }
  updateRunNowState()
}
