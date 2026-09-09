// validateKometaRoot: hit the server's /validate-kometa-root endpoint
// to run the full-fat validation of a Kometa install (folder structure,
// Python environment, importable modules, kometa.py present, etc.).
//
// This is the "am I actually ready to run Kometa?" check. It's called
// after successful updates, after user-triggered "Prepare Kometa"
// clicks, and on wizard step entry when we need to know whether the
// run-command section should be revealed.
//
// EXPORT:
//
//   validateKometaRoot(options)
//     options: {
//       appendStatus?: boolean   // when true, append '\n Re-validating...'
//                                // to the log instead of clearing it.
//                                // Used after updates so users can see
//                                // the update + revalidation history.
//     }
//     -- Returns undefined (fire-and-forget). Server response is
//        handled internally; state updates + DOM writes are the
//        observable outcome.
//
//        Short-circuits (no fetch):
//          - external mode: appends info line, clears validated flag,
//            refreshes rollup, returns.
//          - already in progress: returns without touching anything.
//          - no configured path: writes an explanatory message to the
//            log box, clears validated + spinner, disables run-now,
//            refreshes rollup, returns.
//
// SERVER CONTRACT:
//
//   POST /validate-kometa-root
//   Body: { path, config_name, install_mode }
//   Response: {
//     success: boolean,
//     error?: string,
//     log?: string[],
//     kometa_version?: string,
//     kometa_root?: string,           // POSIX
//     kometa_root_display?: string,   // native
//     venv_python?: string,           // POSIX
//     venv_python_display?: string    // native
//   }

import { kometaState } from './_state.js'
import {
  kometaCanProbeRuntime,
  getConfiguredKometaRootPosix,
  getConfiguredKometaRootDisplay,
  getConfiguredKometaInstallMode
} from './_runtime.js'
import { appendKometaStatusLine, setKometaUpdatePhaseBadge } from './_updatePhase.js'
import { syncKometaRollupBadge, syncUpdateButtonLabel } from './_updateRollup.js'
import { getFinalGateState } from './_validationGate.js'
import { buildCommand } from './_runCommand.js'
import { updateRunNowState } from './_runControls.js'
import {
  hideRunCommandSectionUntilValidated,
  showRunCommandSectionAfterValidated
} from './_runCommandSection.js'

/**
 * Read a data-* attribute off an element by id, returning '' if the
 * element is missing. Used for the four validation flag lookups
 * (plex_valid / tmdb_valid / libs_valid / sett_valid / yaml_valid).
 * Kept as a small helper so the callsite stays readable.
 */
function readValidationFlag (id, key) {
  const el = document.getElementById(id)
  return el ? el.dataset[key] : ''
}

function refreshSidebarAppReadiness () {
  if (typeof window !== 'undefined' && typeof window.QS_refreshAppReadiness === 'function') {
    window.QS_refreshAppReadiness({ fetch: true })
  }
}

/**
 * Check whether Kometa is validated. See module docstring for full
 * contract.
 *
 * @param {object} [options]
 * @param {boolean} [options.appendStatus=false]
 */
export function validateKometaRoot (options = {}) {
  // ---- Short-circuits ---------------------------------------------

  if (!kometaCanProbeRuntime()) {
    appendKometaStatusLine('\u2139\ufe0f Runtime validation is not available in external Kometa mode. Quickstart can sync config and optional logs, but it cannot validate or launch the runtime directly.')
    kometaState.kometaValidationInProgress = false
    kometaState.kometaValidated = false
    syncKometaRollupBadge()
    return
  }

  if (kometaState.kometaValidationInProgress) return

  // ---- Setup: state + UI transitions ------------------------------

  kometaState.kometaValidationInProgress = true
  setKometaUpdatePhaseBadge('validating')
  // showNavigationLoadingOverlay is a global from 000-base.js. The
  // typeof guard is preserved because this module can theoretically
  // be imported in isolation for testing where the global isn't set.
  if (typeof showNavigationLoadingOverlay === 'function') {
    showNavigationLoadingOverlay('kometa-check')
  }
  syncKometaRollupBadge()

  const logBox = document.getElementById('kometa-validation-log')
  const spinner = document.getElementById('spinner_validate')
  const runNow = document.getElementById('run-now')
  const out = document.getElementById('run-command-output')

  const configName = out.dataset.configFilename
  const configuredRootPosix = getConfiguredKometaRootPosix()
  const configuredRootDisplay = getConfiguredKometaRootDisplay()
  const configuredInstallMode = getConfiguredKometaInstallMode()
  const appendStatus = Boolean(options.appendStatus)

  if (!configuredRootPosix) {
    logBox.textContent = '\u274c Quickstart does not have a Kometa install path selected for this config yet.\nOpen the Start page and choose whether this config uses a Quickstart-managed install or an existing install.\n'
    if (spinner) spinner.classList.add('d-none')
    runNow.disabled = true
    kometaState.kometaValidationInProgress = false
    kometaState.kometaValidated = false
    syncKometaRollupBadge()
    return
  }

  if (appendStatus) {
    logBox.insertAdjacentHTML(
      'beforeend',
      '\n\ud83d\udd04 Re-validating Kometa after update...\n' +
      'This may take a few seconds as we verify the folder structure, Python environment, and Kometa information.\n\n'
    )
  } else {
    // NOTE: original had a trailing blank line inside this template
    // (`\n\n` after 'information.'). Preserved verbatim.
    logBox.textContent =
      '\ud83d\udd04 Please wait while we validate your Kometa installation...\n' +
      'This may take a few seconds as we verify the folder structure, Python environment, and Kometa information.\n\n'
  }
  if (spinner) spinner.classList.remove('d-none')
  runNow.disabled = true

  // ---- Response handlers ------------------------------------------

  const handleValidateSuccess = (res) => {
    kometaState.kometaLocalCheckCompleted = true
    if (Array.isArray(res.log)) {
      res.log.forEach(line => logBox.insertAdjacentHTML('beforeend', `${line}\n`))
    }

    if (res.success) {
      kometaState.kometaInstalled = true
      logBox.insertAdjacentHTML('beforeend', '\u2705 Kometa root validated successfully.\n')
      if (res.kometa_version) {
        logBox.insertAdjacentHTML('beforeend', `\ud83d\udce6 Local Kometa version: ${res.kometa_version}\n`)
      }

      // Cache paths + venv Python on #run-command-output for the
      // run-command builder. Same fallback chain as probeKometaRoot.
      const kometaRootDisplay = res.kometa_root_display || res.kometa_root || configuredRootDisplay
      const venvPythonDisplay = res.venv_python_display || res.venv_python || 'python3'
      const kometaRootPosix = res.kometa_root || configuredRootPosix
      const venvPythonPosix = res.venv_python || venvPythonDisplay

      out.dataset.kometaRoot = kometaRootDisplay
      out.dataset.venvPython = venvPythonDisplay
      out.dataset.kometaRootPosix = kometaRootPosix
      out.dataset.venvPythonPosix = venvPythonPosix

      const installPathEl = document.getElementById('kometa-install-path')
      if (installPathEl) installPathEl.textContent = kometaRootDisplay

      // "All validation gates green" check. We reveal the run-command
      // section only when every validation the user MUST clear is
      // green: YAML is being shown, AND either the final-gate says
      // configValid, OR each individual gate's dataset flag reads
      // 'True'. Belt-and-suspenders because final-gate state and
      // individual dataset flags can lag each other by a tick.
      const finalGate = getFinalGateState()
      const allValid = kometaState.showYAML && (finalGate.configValid || (
        readValidationFlag('plex_valid', 'plexValid') === 'True' &&
        readValidationFlag('tmdb_valid', 'tmdbValid') === 'True' &&
        readValidationFlag('libs_valid', 'libsValid') === 'True' &&
        readValidationFlag('sett_valid', 'settValid') === 'True' &&
        readValidationFlag('yaml_valid', 'yamlValid') === 'True'
      ))

      // Clear any stale run-command output before rebuilding, so we
      // don't briefly flash the old command while buildCommand runs.
      const outEl = document.getElementById('run-command-output')
      if (outEl) outEl.textContent = ''
      try { buildCommand() } catch { /* buildCommand may not be ready in every context */ }

      if (allValid) {
        kometaState.kometaValidated = true
        showRunCommandSectionAfterValidated()
      } else {
        kometaState.kometaValidated = false
        hideRunCommandSectionUntilValidated()
        runNow.disabled = true
      }
      if (!kometaState.kometaUpdating) {
        setKometaUpdatePhaseBadge(kometaState.kometaValidated ? 'ready' : 'idle')
      }
    } else {
      kometaState.kometaInstalled = false
      kometaState.kometaValidated = false
      if (!kometaState.kometaUpdating) setKometaUpdatePhaseBadge('failed')
      hideRunCommandSectionUntilValidated()
      runNow.disabled = true
    }

    if (spinner) spinner.classList.add('d-none')
    syncUpdateButtonLabel()
    syncKometaRollupBadge()
  }

  const handleValidateError = (msg) => {
    kometaState.kometaLocalCheckCompleted = true
    const errMsg = msg || 'The Kometa root path is invalid or inaccessible. Please try again.'
    logBox.insertAdjacentHTML('beforeend', `\u274c ${errMsg}\n`)

    // Certain error messages imply the install itself is broken (as
    // opposed to a transient issue). Downgrade kometaInstalled so the
    // rollup badge shows 'Install needed' instead of 'Prepare needed'.
    const lowered = String(errMsg || '').toLowerCase()
    if (lowered.includes('kometa.py not found') || lowered.includes('requirements.txt not found')) {
      kometaState.kometaInstalled = false
    }

    kometaState.kometaValidated = false
    if (!kometaState.kometaUpdating) setKometaUpdatePhaseBadge('failed')
    hideRunCommandSectionUntilValidated()
    runNow.disabled = true
    if (spinner) spinner.classList.add('d-none')
    syncKometaRollupBadge()
  }

  const handleValidateComplete = () => {
    kometaState.kometaValidationInProgress = false
    updateRunNowState()
    syncUpdateButtonLabel()
    syncKometaRollupBadge()
    refreshSidebarAppReadiness()
    if (typeof hideNavigationLoadingOverlay === 'function') {
      hideNavigationLoadingOverlay()
    }
  }

  fetch('/validate-kometa-root', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      path: configuredRootPosix,
      config_name: configName,
      install_mode: configuredInstallMode
    })
  })
    .then(async (resp) => {
      const data = await resp.json().catch(() => ({}))
      if (resp.ok) handleValidateSuccess(data)
      else handleValidateError(data && data.error)
    })
    .catch(() => handleValidateError(null))
    .finally(handleValidateComplete)
}
