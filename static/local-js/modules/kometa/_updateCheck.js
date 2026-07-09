// checkKometaUpdate: hit the server's /check-kometa-update endpoint,
// interpret the response, and update kometaState + UI accordingly.
//
// This is the "check for updates" half of the update flow. The other
// half -- actually PERFORMING the update (callUpdateKometa) -- lives
// in 900-kometa.js for now and will be extracted separately.
//
// EXPORT:
//
//   checkKometaUpdate(forceRefresh = false)
//     -- Runs the update check. Returns a Promise that resolves to
//        the server's response data (or null when there's no
//        configured Kometa root, or a synthetic 'skipped' object when
//        the current mode can't be checked at all).
//
//        Side effects on success:
//          - Updates kometaState.kometa{LocalCheckCompleted,
//            Installed, UpdateCheckCompleted, UpdateCheckSkipped,
//            UpdateAvailable}
//          - Appends each server-supplied log line via
//            appendKometaStatusLine
//          - Syncs source-status panel with local/remote versions
//          - Shows/hides #kometa-update-box based on whether an
//            update is actually available (both versions known AND
//            update flag set)
//          - Refreshes update button label + rollup badge
//
//        Side effects on failure:
//          - Appends a red-X error line to the status log
//          - Clears source-status panel back to 'never checked'
//          - Refreshes button label + rollup badge
//          - Re-throws the error so callers can attach their own
//            fallback UI
//
// SERVER CONTRACT:
//
//   POST /check-kometa-update
//   Body: {
//     path: string,             // configured Kometa root (POSIX)
//     install_mode: string,     // 'managed' | 'existing' (never
//                                 'external' -- see canCheck below)
//     force: boolean,           // if true, skip cache and re-check
//     branch_override: string   // 'auto' | 'master' | 'develop' | ...
//   }
//   Response: {
//     kometa_installed: boolean,
//     update_check_completed: boolean,
//     kometa_update_check_skipped: boolean,
//     kometa_update_available: boolean,
//     local_version?: string,
//     remote_version?: string,
//     log?: string[]
//   }

import { kometaState } from './_state.js'
import {
  kometaCanCheckUpdateStatus,
  getConfiguredKometaRootPosix,
  getConfiguredKometaInstallMode
} from './_runtime.js'
import { getKometaBranchOverride, syncKometaSourceStatus } from './_kometaBranch.js'
import { appendKometaStatusLine } from './_updatePhase.js'
import { syncUpdateButtonLabel, syncKometaRollupBadge } from './_updateRollup.js'

/**
 * Run the update check. See module docstring for full behavior.
 *
 * @param {boolean} [forceRefresh=false]  Ask the server to bypass any
 *                                        cached result and re-check.
 * @returns {Promise<object | null>}
 */
export function checkKometaUpdate (forceRefresh = false) {
  // External mode can't be update-checked; return a synthetic
  // 'skipped' response so callers don't need to special-case it.
  if (!kometaCanCheckUpdateStatus()) {
    appendKometaStatusLine('\u2139\ufe0f Update checks are not available in external Kometa mode.')
    return Promise.resolve({
      success: true,
      update_check_completed: false,
      kometa_update_check_skipped: true,
      kometa_update_available: false
    })
  }

  const configuredRootPosix = getConfiguredKometaRootPosix()
  const configuredInstallMode = getConfiguredKometaInstallMode()
  const branchOverride = getKometaBranchOverride()

  // No path selected yet -- silently resolve to null. Callers that
  // wanted a check will see the null and know they need to prompt
  // for a path first.
  if (!configuredRootPosix) return Promise.resolve(null)

  return fetch('/check-kometa-update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      path: configuredRootPosix,
      install_mode: configuredInstallMode,
      force: forceRefresh,
      branch_override: branchOverride
    })
  })
    .then(async res => {
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed to check Kometa update status.')
      return data
    })
    .then(data => {
      // Fold the response into kometaState so the rest of the UI
      // (button labels, rollup badge, source status) reflects it.
      kometaState.kometaLocalCheckCompleted = true
      kometaState.kometaInstalled = !!data.kometa_installed
      kometaState.kometaUpdateCheckCompleted = !!data.update_check_completed
      kometaState.kometaUpdateCheckSkipped = !!data.kometa_update_check_skipped
      kometaState.kometaUpdateAvailable = !!data.kometa_update_available

      if (Array.isArray(data.log)) data.log.forEach(line => appendKometaStatusLine(line))

      syncKometaSourceStatus({
        localVersion: data.local_version || kometaState.kometaLocalVersionStatus,
        remoteVersion: data.remote_version || '',
        checked: Boolean(data.update_check_completed),
        skipped: Boolean(data.kometa_update_check_skipped)
      })

      // Show the update-info box only when we have BOTH versions AND
      // an update is actually available. In every other case
      // (up-to-date, install missing, skipped) it stays hidden.
      // NOTE: original didn't null-check any of these getElementById
      // calls -- preserved verbatim (every page that reaches this
      // path also renders the box).
      if (data.local_version && data.remote_version && data.kometa_update_available) {
        document.getElementById('kometa-update-box').classList.remove('d-none')
        document.getElementById('kometa-local-version').textContent = data.local_version
        document.getElementById('kometa-remote-version').textContent = data.remote_version
      } else {
        document.getElementById('kometa-update-box').classList.add('d-none')
      }

      syncUpdateButtonLabel()
      syncKometaRollupBadge()
      return data
    })
    .catch(err => {
      appendKometaStatusLine(`\u274c ${err.message || 'Failed to check Kometa update status.'}`)
      syncKometaSourceStatus({ checked: false, skipped: false, remoteVersion: '' })
      syncUpdateButtonLabel()
      syncKometaRollupBadge()
      throw err
    })
}
