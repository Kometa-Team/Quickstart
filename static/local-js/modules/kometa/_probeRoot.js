// probeKometaRoot: hit the server's /probe-kometa-root endpoint to
// discover whether the currently-configured Kometa root has an
// installed Kometa, and if so, what its version + venv Python are.
//
// This is called by runKometaStatusPass (still in 900-kometa.js for
// now) as the FIRST step of any Kometa status refresh. Its job is:
//   1. Ask the server "is Kometa installed at this path?"
//   2. If yes, cache the display paths + venv python on the
//      #run-command-output element (as data attrs) so the run-command
//      builder can grab them later.
//   3. Show or hide the run-command section accordingly.
//
// Errors do NOT reject the promise -- they fall through to the same
// state-clearing path as an "install not found" response. Callers
// don't need to attach a .catch; the promise always resolves.
//
// EXPORT:
//
//   probeKometaRoot()
//     -- Returns a Promise. Resolves to:
//        - null if no Kometa root is configured (silent, appends
//          error line to status log)
//        - the raw server response object on success or on server
//          error (both are handled internally)
//        - null on network / fetch reject
//
// SERVER CONTRACT:
//
//   POST /probe-kometa-root
//   Body: { path: string, install_mode: 'managed' | 'existing' | 'external' }
//   Response: {
//     kometa_installed: boolean,
//     kometa_root?: string,          // POSIX path (canonical)
//     kometa_root_display?: string,  // native path (for display)
//     venv_python?: string,          // POSIX venv python
//     venv_python_display?: string,  // native venv python
//     kometa_version?: string,       // e.g. 'v1.2.3' or 'Unknown'
//     log?: string[],                // lines to feed into status log
//     error?: string                 // present on failure
//   }

import { kometaState } from './_state.js'
import {
  getConfiguredKometaRootPosix,
  getConfiguredKometaRootDisplay,
  getConfiguredKometaInstallMode
} from './_runtime.js'
import { syncKometaSourceStatus } from './_kometaBranch.js'
import { appendKometaStatusLine } from './_updatePhase.js'
import {
  syncUpdateButtonLabel,
  syncKometaRollupBadge
} from './_updateRollup.js'
import { hideRunCommandSectionUntilValidated } from './_runCommandSection.js'

/**
 * Ask the server whether Kometa is installed at the configured path.
 * See module docstring for full contract.
 *
 * @returns {Promise<object | null>}
 */
export function probeKometaRoot () {
  const out = document.getElementById('run-command-output')
  const configuredRootPosix = getConfiguredKometaRootPosix()
  const configuredRootDisplay = getConfiguredKometaRootDisplay()
  const configuredInstallMode = getConfiguredKometaInstallMode()

  if (!configuredRootPosix) {
    appendKometaStatusLine('\u274c No Kometa install path is selected for this config yet.')
    return Promise.resolve(null)
  }

  // Success handler: server confirmed we can talk to the path. Note
  // this runs even for a "Kometa NOT installed" response -- the
  // server successfully responded, so the probe was technically
  // successful; the payload just tells us "no install found".
  const handleProbeSuccess = (res) => {
    kometaState.kometaLocalCheckCompleted = true
    kometaState.kometaInstalled = !!res.kometa_installed
    if (Array.isArray(res.log)) res.log.forEach(line => appendKometaStatusLine(line))

    // Cache the display paths + venv python on the run-command-output
    // element as data attrs. The run-command builder reads these
    // later to compose the actual `kometa.py` invocation.
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

    syncKometaSourceStatus({ localVersion: res.kometa_version || 'Unknown' })

    // If Kometa isn't installed, the previously-cached "validated"
    // flag is stale -- clear it and hide the run-command section
    // until a real install happens.
    if (!kometaState.kometaInstalled) {
      kometaState.kometaValidated = false
      hideRunCommandSectionUntilValidated()
    }

    syncUpdateButtonLabel()
    syncKometaRollupBadge()
  }

  // Error handler: server returned !ok, OR fetch itself rejected
  // (network error). Both cases funnel here so callers only see one
  // failure mode.
  const handleProbeError = (msg) => {
    kometaState.kometaLocalCheckCompleted = true
    kometaState.kometaInstalled = false
    kometaState.kometaValidated = false
    const errMsg = msg || 'Unable to probe the Kometa path.'
    appendKometaStatusLine(`\u274c ${errMsg}`)
    syncKometaSourceStatus({ localVersion: 'Unknown' })
    hideRunCommandSectionUntilValidated()
    syncUpdateButtonLabel()
    syncKometaRollupBadge()
  }

  return fetch('/probe-kometa-root', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      path: configuredRootPosix,
      install_mode: configuredInstallMode
    })
  })
    .then(async (resp) => {
      // .catch(() => ({})) so a non-JSON body doesn't crash the
      // pipeline -- the empty object flows into handleProbeError
      // which supplies a generic fallback message.
      const data = await resp.json().catch(() => ({}))
      if (resp.ok) handleProbeSuccess(data)
      else handleProbeError(data && data.error)
      return data
    })
    .catch(() => {
      handleProbeError(null)
      return null
    })
}
