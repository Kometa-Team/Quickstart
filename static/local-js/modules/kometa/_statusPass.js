// runKometaStatusPass: the "one-stop-shop" refresher for Kometa status.
//
// A single call to this function does the full status pipeline:
//   1. Write a header block into the validation-log describing the
//      selected branch mode, effective branch, and source URLs.
//   2. Invalidate any cached update-check result (because we're
//      about to overwrite it).
//   3. Probe the Kometa root (probeKometaRoot) to see if it's installed.
//   4. If external mode: append info line + return.
//   5. If not installed: append info line + return.
//   6. Otherwise: check for updates via checkKometaUpdate.
//   7. Set the phase badge to 'ready' / 'idle' / 'failed' as
//      appropriate, unless an update is currently in progress
//      (updates own the badge during their lifecycle).
//
// This function is the main entry point users hit when they open the
// Kometa wizard step or click "Recheck". It's also called by
// callUpdateKometa in the 'check existing' + 'is-installed-no-force'
// flavors.
//
// EXPORT:
//
//   runKometaStatusPass(forceRefresh = false)
//     -- Returns a Promise. Resolves to whatever the last stage
//        produced (probeKometaRoot response for short-circuit paths,
//        checkKometaUpdate response for the full pipeline).
//     -- .catch swallows errors and resolves to null (still marks
//        the phase as 'failed' if we weren't updating).

import { kometaState } from './_state.js'
import { getConfiguredKometaInstallMode } from './_runtime.js'
import {
  getKometaBranchOverride,
  getEffectiveKometaBranch,
  getKometaVersionSourceUrlValue,
  getKometaZipSourceUrlValue
} from './_kometaBranch.js'
import {
  setKometaStatusLog,
  appendKometaStatusLine,
  setKometaUpdatePhaseBadge
} from './_updatePhase.js'
import { invalidateKometaUpdateStatus } from './_updateRollup.js'
import { probeKometaRoot } from './_probeRoot.js'
import { checkKometaUpdate } from './_updateCheck.js'

/**
 * Run a full Kometa status pass. See module docstring for pipeline.
 *
 * @param {boolean} [forceRefresh=false]  Passed through to
 *                                        checkKometaUpdate to bypass
 *                                        cached update results.
 * @returns {Promise<object | null>}
 */
export function runKometaStatusPass (forceRefresh = false) {
  const selection = getKometaBranchOverride()
  const effective = getEffectiveKometaBranch()
  const lines = [
    '\ud83d\udd04 Refreshing Kometa status...',
    `\u2139\ufe0f Selected Kometa branch mode: ${selection || 'auto'}`,
    `\u2139\ufe0f Effective Kometa branch: ${effective}`,
    `\ud83c\udf10 Remote VERSION source: ${getKometaVersionSourceUrlValue(effective)}`,
    `\ud83d\udce5 Kometa ZIP source: ${getKometaZipSourceUrlValue(effective)}`,
    '',
    '\ud83d\udd0d Checking Kometa path and local install state...'
  ]
  setKometaStatusLog(lines, 'checking')
  invalidateKometaUpdateStatus()

  return probeKometaRoot()
    .then((res) => {
      // External mode never checks remote updates -- Quickstart
      // isn't running the runtime, so there's nothing to update.
      if (getConfiguredKometaInstallMode() === 'external') {
        appendKometaStatusLine('')
        appendKometaStatusLine('\u2139\ufe0f External Kometa mode detected. Quickstart will not perform runtime update checks in this mode.')
        if (!kometaState.kometaUpdating) setKometaUpdatePhaseBadge('idle')
        return res
      }
      // No install -> can't compare local vs remote version.
      if (!res || !res.kometa_installed) {
        appendKometaStatusLine('')
        appendKometaStatusLine('\u2139\ufe0f Remote update check skipped because Kometa is not installed.')
        if (!kometaState.kometaUpdating) setKometaUpdatePhaseBadge('idle')
        return res
      }
      appendKometaStatusLine('')
      appendKometaStatusLine('\ud83d\udd0e Checking Kometa update status...')
      return checkKometaUpdate(forceRefresh)
    })
    .then((result) => {
      // Only set the phase if we're NOT in the middle of an actual
      // update -- updates own the badge during their lifecycle
      // (queued -> downloading -> extracting -> etc.) and we don't
      // want a stray 'ready' from a background status pass to
      // clobber the current in-flight phase.
      if (!kometaState.kometaUpdating) {
        setKometaUpdatePhaseBadge(kometaState.kometaInstalled ? 'ready' : 'idle')
      }
      return result
    })
    .catch(() => {
      if (!kometaState.kometaUpdating) setKometaUpdatePhaseBadge('failed')
      return null
    })
}
