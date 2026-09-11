// callUpdateKometa: THE BOSS FIGHT.
//
// The main "update Kometa" entry point. Users hit this by clicking the
// #update-kometa-btn button. It has FIVE distinct execution paths:
//
//   1. External mode short-circuit
//        Kometa lives outside Quickstart's control -- show a toast
//        and bail. Quickstart can only sync config in this mode.
//
//   2. Existing mode branch
//        User pointed Quickstart at their own Kometa install. We
//        can *check* for updates but NOT apply them (that's their
//        job manually). Runs runKometaStatusPass, shows toast based
//        on result, updates a note element if update is available.
//
//   3. Running short-circuit
//        Kometa is currently running (mid-run). Show a toast and
//        bail -- we can't update a live install.
//
//   4. Already-installed-no-force branch
//        Kometa is installed and user didn't tick 'force update'
//        and we don't already know an update is available. Just
//        runs runKometaStatusPass to check remote version, showing
//        toast based on result. Doesn't actually apply anything.
//
//   5. The full update path (the main event)
//        Sets phase 'queued', disables buttons, shows inline progress,
//        POSTs /update-kometa with background=true, then
//        polls /kometa-update-progress via pollKometaUpdateProgress
//        on a setInterval. When the job completes, calls
//        validateKometaRoot to re-verify the install.
//
// EXPORT:
//
//   callUpdateKometa()
//     -- Returns undefined (fire-and-forget UI action).
//        All observable outcomes are DOM writes, toasts, and state
//        transitions handled internally.
//
// DOM ELEMENT DEPENDENCIES:
//
//   Looked up lazily on each call (not cached) so the module remains
//   importable in test contexts where the DOM might be rebuilt
//   between tests:
//
//     #update-kometa-btn       -- main trigger button
//     #force-kometa-update     -- checkbox (Force Update toggle)
//     #kometa-branch-override  -- select (branch override dropdown)
//     #kometa-validation-log   -- <pre> for status log
//     #run-now, #stop-now      -- run controls
//     #run-command-box         -- the wrapper that dims during update
//     #kometa-update-box       -- rollup badge box (hidden on success)
//     #kometa-update-box-note  -- inline update note (existing mode)
//
// GLOBALS:
//
//   showToast() is a global function from 000-base.js. Declared in
//   eslint.config.js quickstartGlobals as readonly. Not imported
//   because it isn't exported by any module.

import { kometaState } from './_state.js'
import {
  getConfiguredKometaInstallMode,
  getConfiguredKometaRootPosix
} from './_runtime.js'
import { getKometaBranchOverride } from './_kometaBranch.js'
import {
  setKometaUpdatePhaseBadge,
  appendKometaStatusLine
} from './_updatePhase.js'
import {
  syncKometaRollupBadge,
  syncUpdateButtonLabel
} from './_updateRollup.js'
import { hideRunCommandSectionUntilValidated } from './_runCommandSection.js'
import { syncFinalAccordionRollups } from './_headerBadges.js'
import {
  stopKometaUpdatePolling,
  pollKometaUpdateProgress
} from './_updatePolling.js'
import { validateKometaRoot } from './_validateRoot.js'
import { updateRunNowState } from './_runControls.js'
import { runKometaStatusPass } from './_statusPass.js'

/**
 * Lazy DOM lookup helper. Returns the current live element (not a
 * cached reference) so we play nicely with tests that swap the body.
 */
function el (id) {
  return document.getElementById(id)
}

function getUpdateButton () {
  return el('update-kometa-btn') || el('update-kometa')
}

function getForceUpdateToggle () {
  return el('force-kometa-update') || el('force-update')
}

function getRequiredUpdateElements () {
  const elements = {
    btn: getUpdateButton(),
    logBox: el('kometa-validation-log'),
    runNow: el('run-now'),
    stopNow: el('stop-now'),
    runBox: el('run-command-box'),
    forceUpdateToggle: getForceUpdateToggle(),
    kometaBranchOverrideSel: el('kometa-branch-override')
  }
  const missing = Object.entries(elements)
    .filter(([, node]) => !node)
    .map(([key]) => key)

  if (!missing.length) return elements

  console.error('Missing Kometa update controls:', missing)
  showToast('error', 'Kometa update controls are unavailable on this page. Refresh and try again.')
  return null
}

/**
 * The 'existing' mode branch: user pointed Quickstart at their own
 * Kometa install. Check for updates via runKometaStatusPass; show
 * toast based on result. Do NOT actually apply anything (that's the
 * user's job outside Quickstart).
 */
function handleExistingModeCheck () {
  const btn = getUpdateButton()
  if (!btn) {
    console.error('Missing Kometa update button for existing-mode status check.')
    showToast('error', 'Kometa update button is unavailable on this page. Refresh and try again.')
    return
  }
  btn.disabled = true
  btn.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i> Checking...'
  runKometaStatusPass(true)
    .then((data) => {
      if (!data) return
      if (data.kometa_update_available) {
        showToast(
          'warning',
          `Kometa update available: ${data.local_version} \u2192 ${data.remote_version}. Update this existing install manually outside Quickstart.`
        )
        const noteEl = el('kometa-update-box-note')
        if (noteEl) {
          noteEl.textContent = 'Update this existing Kometa install manually outside Quickstart before running.'
        }
      } else if (!data.kometa_update_check_skipped) {
        showToast('success', 'Existing Kometa install checked. No newer version was detected.')
      }
    })
    .catch(() => {
      showToast('error', 'Failed to check existing Kometa status.')
    })
    .finally(() => {
      btn.disabled = false
      syncUpdateButtonLabel()
    })
}

/**
 * The "already installed, no force, no known update" branch. Kometa
 * is installed, user didn't tick force, we don't already know there's
 * an update -- do a status-only pass, show a toast, no install work.
 */
function handleAlreadyInstalledNoForceCheck () {
  const required = getRequiredUpdateElements()
  if (!required) return
  const { btn, forceUpdateToggle, kometaBranchOverrideSel } = required
  btn.disabled = true
  btn.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i> Checking...'
  forceUpdateToggle.disabled = true
  kometaBranchOverrideSel.disabled = true
  runKometaStatusPass(true)
    .then((data) => {
      if (!data) return
      if (data.kometa_update_available) {
        showToast('warning', `Kometa update available: ${data.local_version} \u2192 ${data.remote_version}.`)
      } else if (!data.kometa_update_check_skipped) {
        showToast('success', 'Kometa is already up to date.')
      }
    })
    .catch(() => {
      showToast('error', 'Failed to check Kometa update status.')
    })
    .finally(() => {
      btn.disabled = false
      forceUpdateToggle.disabled = false
      kometaBranchOverrideSel.disabled = false
      syncUpdateButtonLabel()
    })
}

/**
 * Main entry. See module docstring for the five execution paths.
 */
export function callUpdateKometa () {
  const installMode = getConfiguredKometaInstallMode()

  // ---- Path 1: external mode ------------------------------------
  if (installMode === 'external') {
    showToast('info', 'External Kometa mode cannot update the runtime. Quickstart can only sync config and optional logs in this mode.')
    return
  }

  // ---- Path 2: existing mode ------------------------------------
  if (installMode === 'existing') {
    handleExistingModeCheck()
    return
  }

  // ---- Path 3: Kometa running or scheduler waiting ---------------
  if (kometaState.kometaStatus === 'running' || kometaState.kometaStatus === 'scheduled_waiting') {
    const message = kometaState.kometaStatus === 'scheduled_waiting'
      ? 'Kometa scheduler is waiting; stop it before updating.'
      : 'Kometa is currently running; update skipped.'
    showToast('info', message)
    return
  }

  // ---- Path 4: already installed, no force, no update needed ----
  const required = getRequiredUpdateElements()
  if (!required) return
  const {
    btn,
    logBox,
    runNow,
    stopNow,
    runBox,
    forceUpdateToggle,
    kometaBranchOverrideSel
  } = required
  const qsBranch = btn.dataset.qsBranch || 'master'
  const branchOverride = getKometaBranchOverride()
  const configuredRootPosix = getConfiguredKometaRootPosix()
  const configuredInstallMode = getConfiguredKometaInstallMode()
  const forceUpdate = forceUpdateToggle.checked

  if (kometaState.kometaInstalled && !forceUpdate && !kometaState.kometaUpdateAvailable) {
    handleAlreadyInstalledNoForceCheck()
    return
  }

  // ---- Path 5: THE FULL UPDATE PATH -----------------------------

  // Flip state flags first so any concurrent status pass knows we
  // own the badge / phase lifecycle from this point on.
  kometaState.kometaUpdating = true
  kometaState.kometaValidated = false
  kometaState.kometaUpdateCheckSkipped = false
  kometaState.kometaUpdateCheckCompleted = false
  setKometaUpdatePhaseBadge('queued')
  syncKometaRollupBadge()
  hideRunCommandSectionUntilValidated()
  syncFinalAccordionRollups()

  // Snapshot run-now state so we can restore in cleanupUI. We want
  // to restore, not force-reset, because if the user had a specific
  // command queued we don't want to lose it silently.
  const prevRunNowHtml = runNow.innerHTML
  const prevRunNowDisabled = runNow.disabled

  runBox.classList.add('opacity-50', 'position-relative')
  runNow.disabled = true
  runNow.innerHTML = '<i class="bi bi-hourglass me-1"></i> Updating...'
  stopNow.disabled = true

  const inProgressLabel = forceUpdate
    ? (kometaState.kometaInstalled ? 'Force Updating...' : 'Force Installing...')
    : (kometaState.kometaInstalled ? 'Checking for updates...' : 'Installing...')
  btn.disabled = true
  btn.innerHTML = `<i class="bi bi-arrow-repeat me-1"></i> ${inProgressLabel}`
  forceUpdateToggle.disabled = true
  kometaBranchOverrideSel.disabled = true

  logBox.insertAdjacentHTML('beforeend', '\nInitializing/Updating Kometa...\n')
  if (logBox) logBox.scrollTop = logBox.scrollHeight

  // ---- Heartbeat toast (every 30s) ------------------------------
  //
  // postUpdateLabel is set in the success handler and consumed by
  // cleanupUI to briefly show a checkmark before the button resets.
  let postUpdateLabel = null

  const cleanupUI = () => {
    stopKometaUpdatePolling()
    kometaState.kometaUpdateJobId = null
    kometaState.kometaUpdateLogIndex = 0
    kometaState.kometaUpdating = false
    runBox.classList.remove('opacity-50', 'position-relative')
    runNow.disabled = prevRunNowDisabled
    runNow.innerHTML = prevRunNowHtml
    stopNow.disabled = false
    btn.disabled = false
    forceUpdateToggle.disabled = false
    kometaBranchOverrideSel.disabled = false
    syncUpdateButtonLabel()
    updateRunNowState()
    syncFinalAccordionRollups()
    if (postUpdateLabel) {
      btn.innerHTML = postUpdateLabel
      // Reset the "success" label back to its dynamic form after 6s
      // so a user glancing at the button later doesn't see a stale
      // 'Up to date' badge.
      setTimeout(syncUpdateButtonLabel, 6000)
    }
  }

  // ---- The fetch pipeline ---------------------------------------
  //
  // Server semantics:
  //   200 with { success: true, job_id }   -> background job started
  //     -> poll via pollKometaUpdateProgress until done
  //   200 with { success: true } (no job)  -> synchronous success
  //   200 with { success: false }          -> synchronous failure
  //   409                                   -> Kometa is running,
  //                                            update blocked
  //   other !ok                             -> throw

  fetch('/update-kometa', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      branch: qsBranch,
      branch_override: branchOverride,
      path: configuredRootPosix,
      install_mode: configuredInstallMode,
      force: forceUpdate,
      background: true
    })
  })
    .then(async res => {
      const data = await res.json()
      if (res.status === 409) {
        const message = data.error || 'Update blocked: Kometa running.'
        setKometaUpdatePhaseBadge('failed')
        appendKometaStatusLine(message)
        return { success: false, log: data.log || [], blocked: true }
      }
      if (!res.ok) {
        throw new Error(data.error || 'Kometa update failed to start.')
      }
      return data
    })
    .then(data => {
      if (!data) return

      // ---- Background job path (has job_id) ----
      if (data.success && data.job_id) {
        kometaState.kometaUpdateJobId = data.job_id
        kometaState.kometaUpdateLogIndex = 0
        stopKometaUpdatePolling()

        // finalize: called each time we get a progress update.
        // Returns true when the job is done and we shouldn't schedule
        // another poll; false when we need to keep polling.
        const finalize = (progress) => {
          if (!progress || !progress.done) return false
          kometaState.kometaLocalCheckCompleted = false
          kometaState.kometaUpdateAvailable = false
          const updateBox = el('kometa-update-box')
          if (updateBox) updateBox.classList.add('d-none')
          syncUpdateButtonLabel()
          // Server may report success under 'update_success' (newer
          // servers) or 'success' (older). Use nullish coalescing so
          // 'update_success: false' takes precedence over 'success: true'.
          const updateSucceeded = progress.update_success ?? progress.success
          if (updateSucceeded) {
            if (progress.up_to_date) {
              postUpdateLabel = '<i class="bi bi-check-circle me-1"></i> Up to date'
              appendKometaStatusLine('Kometa is already up to date.')
              setKometaUpdatePhaseBadge('ready')
            } else {
              appendKometaStatusLine('Kometa update completed successfully.')
              setKometaUpdatePhaseBadge('validating')
            }
            validateKometaRoot({ appendStatus: true })
          } else {
            appendKometaStatusLine('Kometa update failed.')
            setKometaUpdatePhaseBadge('failed')
            // We still validate on failure so the user sees WHY it
            // failed (missing kometa.py, broken venv, etc.).
            validateKometaRoot({ appendStatus: true })
          }
          cleanupUI()
          syncKometaRollupBadge()
          return true
        }

        // Do one immediate poll to catch super-fast completions,
        // then schedule the recurring poll if we're not already done.
        return pollKometaUpdateProgress()
          .then(progress => {
            if (finalize(progress)) return
            kometaState.kometaUpdatePollInterval = setInterval(() => {
              pollKometaUpdateProgress()
                .then(finalize)
                .catch(err => {
                  console.error(err)
                  appendKometaStatusLine(`\u274c ${err.message || 'Failed to fetch Kometa update progress.'}`)
                  setKometaUpdatePhaseBadge('failed')
                  stopKometaUpdatePolling()
                  cleanupUI()
                  syncKometaRollupBadge()
                })
            }, 800)
          })
      }

      // ---- Synchronous failure path (success=false, not 409) ----
      //
      // NOTE: since we always send background=true, the endpoint's
      // success path always includes a job_id and goes through the
      // 'success && job_id' branch above. The `else if` here fires
      // ONLY when data.success is false AND data.blocked isn't set --
      // i.e. the server returned 200 with success=false (which the
      // current endpoint doesn't do). Kept as a defensive fallback
      // for future endpoint changes.
      if (!data.success && !data.blocked) {
        appendKometaStatusLine(data.error || 'Kometa update failed.')
        setKometaUpdatePhaseBadge('failed')
        validateKometaRoot({ appendStatus: true })
      }
    })
    .catch(err => {
      console.error(err)
      appendKometaStatusLine(`Error occurred during Kometa update: ${err.message || 'Unknown error.'}`)
      setKometaUpdatePhaseBadge('failed')
      cleanupUI()
      syncKometaRollupBadge()
    })
}
