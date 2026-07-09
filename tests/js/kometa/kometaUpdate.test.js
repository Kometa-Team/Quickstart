// Tests for static/local-js/modules/kometa/_kometaUpdate.js
//
// One export: callUpdateKometa().
//
// The boss. This function has FIVE distinct execution paths:
//   1. External mode -> toast + bail
//   2. Existing mode -> handleExistingModeCheck
//   3. Kometa running -> toast + bail
//   4. Already installed + no force + no update -> handleAlreadyInstalledNoForceCheck
//   5. Full update path (the main event)
//
// COVERAGE STRATEGY:
//
//   Path 1-3 (short circuits):
//     - external mode toast content
//     - existing mode: check triggered, toast content varies by response
//     - running mode: toast + bail
//
//   Path 4 (already-installed-no-force):
//     - runKometaStatusPass called with true
//     - buttons disabled during check, re-enabled in .finally
//     - toast content varies by response
//
//   Path 5 (full update):
//     - state flags flipped, phase 'queued', section hidden
//     - button labels vary by (forceUpdate, installed) combination
//     - fetch called with right body
//     - heartbeat toast fires immediately + every 30s
//     - 409 response: warning toast, phase 'failed', doesn't throw
//     - success + job_id: kicks off polling
//     - synchronous success with up_to_date: 'up to date' path
//     - synchronous success without up_to_date: 'completed in Xs'
//     - synchronous failure: error toast
//     - fetch throws: catch handler
//
//   cleanupUI (indirectly via completion):
//     - clears heartbeat, stops polling, resets buttons
//     - postUpdateLabel sets button HTML + schedules reset
//
//   finalize (indirectly via completed job polling):
//     - progress.done=false -> keep polling
//     - progress.done=true + update_success -> success path
//     - progress.done=true + up_to_date -> 'up to date' variant
//     - progress.done=true + !update_success -> failure path

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../static/local-js/modules/kometa/_runtime.js', () => ({
  getConfiguredKometaInstallMode: vi.fn(() => 'managed'),
  getConfiguredKometaRootPosix: vi.fn(() => '/opt/kometa')
}))
vi.mock('../../../static/local-js/modules/kometa/_kometaBranch.js', () => ({
  getKometaBranchOverride: vi.fn(() => '')
}))
vi.mock('../../../static/local-js/modules/kometa/_updatePhase.js', () => ({
  setKometaUpdatePhaseBadge: vi.fn(),
  appendKometaStatusLine: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_updateRollup.js', () => ({
  syncKometaRollupBadge: vi.fn(),
  syncUpdateButtonLabel: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_runCommandSection.js', () => ({
  hideRunCommandSectionUntilValidated: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_headerBadges.js', () => ({
  syncFinalAccordionRollups: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_updatePolling.js', () => ({
  stopKometaUpdatePolling: vi.fn(),
  pollKometaUpdateProgress: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_util.js', () => ({
  formatElapsed: vi.fn((ms) => `${Math.floor(ms / 1000)}s`)
}))
vi.mock('../../../static/local-js/modules/kometa/_validateRoot.js', () => ({
  validateKometaRoot: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_runControls.js', () => ({
  updateRunNowState: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_statusPass.js', () => ({
  runKometaStatusPass: vi.fn()
}))

import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import { callUpdateKometa } from '../../../static/local-js/modules/kometa/_kometaUpdate.js'
import {
  getConfiguredKometaInstallMode,
  getConfiguredKometaRootPosix
} from '../../../static/local-js/modules/kometa/_runtime.js'
import { getKometaBranchOverride } from '../../../static/local-js/modules/kometa/_kometaBranch.js'
import {
  setKometaUpdatePhaseBadge,
  appendKometaStatusLine
} from '../../../static/local-js/modules/kometa/_updatePhase.js'
import {
  syncKometaRollupBadge,
  syncUpdateButtonLabel
} from '../../../static/local-js/modules/kometa/_updateRollup.js'
import { hideRunCommandSectionUntilValidated } from '../../../static/local-js/modules/kometa/_runCommandSection.js'
import { syncFinalAccordionRollups } from '../../../static/local-js/modules/kometa/_headerBadges.js'
import {
  stopKometaUpdatePolling,
  pollKometaUpdateProgress
} from '../../../static/local-js/modules/kometa/_updatePolling.js'
import { validateKometaRoot } from '../../../static/local-js/modules/kometa/_validateRoot.js'
import { updateRunNowState } from '../../../static/local-js/modules/kometa/_runControls.js'
import { runKometaStatusPass } from '../../../static/local-js/modules/kometa/_statusPass.js'

// ---------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------

let originalFetch
let toastCalls

function installFixture () {
  document.body.innerHTML = `
    <button id="update-kometa" data-qs-branch="master"></button>
    <input id="force-update" type="checkbox">
    <select id="kometa-branch-override"></select>
    <pre id="kometa-validation-log"></pre>
    <button id="run-now"></button>
    <button id="stop-now"></button>
    <div id="run-command-box"></div>
    <div id="kometa-update-box"></div>
    <div id="kometa-update-box-note"></div>
  `
}

function mockFetchWith (response) {
  global.fetch = vi.fn(() => Promise.resolve(response))
}

function okJson (body) {
  return { ok: true, status: 200, json: () => Promise.resolve(body) }
}

function errJson (status, body) {
  return { ok: false, status, json: () => Promise.resolve(body) }
}

function resetState () {
  kometaState.kometaUpdating = false
  kometaState.kometaValidated = false
  kometaState.kometaInstalled = false
  kometaState.kometaUpdateAvailable = false
  kometaState.kometaStatus = 'idle'
  kometaState.kometaUpdateCheckSkipped = false
  kometaState.kometaUpdateCheckCompleted = false
  kometaState.kometaUpdateJobId = null
  kometaState.kometaUpdateLogIndex = 0
  kometaState.kometaLocalCheckCompleted = false
}

beforeEach(() => {
  getConfiguredKometaInstallMode.mockReset()
  getConfiguredKometaInstallMode.mockReturnValue('managed')
  getConfiguredKometaRootPosix.mockReset()
  getConfiguredKometaRootPosix.mockReturnValue('/opt/kometa')
  getKometaBranchOverride.mockReset()
  getKometaBranchOverride.mockReturnValue('')
  setKometaUpdatePhaseBadge.mockClear()
  appendKometaStatusLine.mockClear()
  syncKometaRollupBadge.mockClear()
  syncUpdateButtonLabel.mockClear()
  hideRunCommandSectionUntilValidated.mockClear()
  syncFinalAccordionRollups.mockClear()
  stopKometaUpdatePolling.mockClear()
  pollKometaUpdateProgress.mockReset()
  validateKometaRoot.mockClear()
  updateRunNowState.mockClear()
  runKometaStatusPass.mockReset()

  // Track showToast calls -- it's a global, not an ESM import.
  toastCalls = []
  global.showToast = vi.fn((...args) => { toastCalls.push(args) })

  originalFetch = global.fetch
  resetState()
})

afterEach(() => {
  global.fetch = originalFetch
  delete global.showToast
  document.body.innerHTML = ''
  vi.useRealTimers()
})

// Yield to microtasks. Handy because callUpdateKometa returns
// undefined (fire-and-forget) so we can't await it directly.
const flush = () => new Promise(r => setTimeout(r, 10))

// ---------------------------------------------------------------------
// Path 1: External mode short-circuit
// ---------------------------------------------------------------------

describe('callUpdateKometa -- path 1: external mode', () => {
  it("shows info toast and bails when install_mode is 'external'", async () => {
    getConfiguredKometaInstallMode.mockReturnValue('external')
    installFixture()
    global.fetch = vi.fn()
    callUpdateKometa()
    expect(toastCalls[0][0]).toBe('info')
    expect(toastCalls[0][1]).toContain('External Kometa mode cannot update')
    expect(global.fetch).not.toHaveBeenCalled()
    expect(runKometaStatusPass).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------
// Path 2: Existing mode
// ---------------------------------------------------------------------

describe('callUpdateKometa -- path 2: existing mode', () => {
  it('triggers runKometaStatusPass and disables button while checking', async () => {
    getConfiguredKometaInstallMode.mockReturnValue('existing')
    runKometaStatusPass.mockResolvedValue({ kometa_update_available: false })
    installFixture()
    callUpdateKometa()
    // Button should be disabled synchronously
    expect(document.getElementById('update-kometa').disabled).toBe(true)
    expect(runKometaStatusPass).toHaveBeenCalledWith(true)
    await flush()
    // After completion, button re-enabled
    expect(document.getElementById('update-kometa').disabled).toBe(false)
  })

  it("shows warning toast + updates note when existing update available", async () => {
    getConfiguredKometaInstallMode.mockReturnValue('existing')
    runKometaStatusPass.mockResolvedValue({
      kometa_update_available: true,
      local_version: 'v1.0',
      remote_version: 'v2.0'
    })
    installFixture()
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'warning' && c[1].includes('v1.0') && c[1].includes('v2.0'))).toBe(true)
    expect(document.getElementById('kometa-update-box-note').textContent).toContain('Update this existing Kometa install manually')
  })

  it("shows success toast when existing install already up to date", async () => {
    getConfiguredKometaInstallMode.mockReturnValue('existing')
    runKometaStatusPass.mockResolvedValue({
      kometa_update_available: false,
      kometa_update_check_skipped: false
    })
    installFixture()
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'success' && c[1].includes('No newer version'))).toBe(true)
  })

  it("does NOT toast when check was skipped", async () => {
    getConfiguredKometaInstallMode.mockReturnValue('existing')
    runKometaStatusPass.mockResolvedValue({
      kometa_update_available: false,
      kometa_update_check_skipped: true
    })
    installFixture()
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'success')).toBe(false)
  })

  it("shows error toast when runKometaStatusPass rejects", async () => {
    getConfiguredKometaInstallMode.mockReturnValue('existing')
    runKometaStatusPass.mockRejectedValue(new Error('nope'))
    installFixture()
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'error' && c[1].includes('Failed to check'))).toBe(true)
  })
})

// ---------------------------------------------------------------------
// Path 3: Kometa running
// ---------------------------------------------------------------------

describe('callUpdateKometa -- path 3: Kometa running', () => {
  it("shows info toast and bails when kometaStatus is 'running'", async () => {
    kometaState.kometaStatus = 'running'
    installFixture()
    global.fetch = vi.fn()
    callUpdateKometa()
    expect(toastCalls[0][0]).toBe('info')
    expect(toastCalls[0][1]).toContain('Kometa is currently running')
    expect(global.fetch).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------
// Path 4: Already-installed-no-force
// ---------------------------------------------------------------------

describe('callUpdateKometa -- path 4: already installed, no force, no update', () => {
  it("triggers status check + disables all controls", () => {
    kometaState.kometaInstalled = true
    kometaState.kometaUpdateAvailable = false
    installFixture()
    document.getElementById('force-update').checked = false
    runKometaStatusPass.mockResolvedValue({})
    callUpdateKometa()
    expect(document.getElementById('update-kometa').disabled).toBe(true)
    expect(document.getElementById('force-update').disabled).toBe(true)
    expect(document.getElementById('kometa-branch-override').disabled).toBe(true)
    expect(runKometaStatusPass).toHaveBeenCalledWith(true)
  })

  it("re-enables controls in .finally", async () => {
    kometaState.kometaInstalled = true
    installFixture()
    document.getElementById('force-update').checked = false
    runKometaStatusPass.mockResolvedValue({})
    callUpdateKometa()
    await flush()
    expect(document.getElementById('update-kometa').disabled).toBe(false)
    expect(document.getElementById('force-update').disabled).toBe(false)
    expect(document.getElementById('kometa-branch-override').disabled).toBe(false)
  })

  it("shows 'update available' toast", async () => {
    kometaState.kometaInstalled = true
    installFixture()
    document.getElementById('force-update').checked = false
    runKometaStatusPass.mockResolvedValue({
      kometa_update_available: true,
      local_version: 'v1.0',
      remote_version: 'v2.0'
    })
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'warning' && c[1].includes('v1.0'))).toBe(true)
  })

  it("shows 'already up to date' toast", async () => {
    kometaState.kometaInstalled = true
    installFixture()
    document.getElementById('force-update').checked = false
    runKometaStatusPass.mockResolvedValue({
      kometa_update_available: false,
      kometa_update_check_skipped: false
    })
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'success' && c[1].includes('already up to date'))).toBe(true)
  })

  it("shows error toast when status pass rejects", async () => {
    kometaState.kometaInstalled = true
    installFixture()
    document.getElementById('force-update').checked = false
    runKometaStatusPass.mockRejectedValue(new Error('nope'))
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'error' && c[1].includes('Failed to check Kometa update'))).toBe(true)
  })

  it("skips path 4 when forceUpdate is checked (falls through to path 5)", async () => {
    kometaState.kometaInstalled = true
    installFixture()
    document.getElementById('force-update').checked = true  // force!
    mockFetchWith(okJson({ success: true, up_to_date: false }))
    callUpdateKometa()
    // Path 5 flipped kometaUpdating
    expect(kometaState.kometaUpdating).toBe(true)
    // fetch was called (path 5) rather than just runKometaStatusPass
    expect(global.fetch).toHaveBeenCalled()
    await flush()
  })

  it("skips path 4 when kometaUpdateAvailable=true", async () => {
    kometaState.kometaInstalled = true
    kometaState.kometaUpdateAvailable = true
    installFixture()
    document.getElementById('force-update').checked = false
    mockFetchWith(okJson({ success: true }))
    callUpdateKometa()
    expect(kometaState.kometaUpdating).toBe(true)
    await flush()
  })
})

// ---------------------------------------------------------------------
// Path 5: Full update -- setup
// ---------------------------------------------------------------------

describe('callUpdateKometa -- path 5: full update setup', () => {
  it("flips state flags + phase 'queued' + hides section", () => {
    installFixture()
    mockFetchWith(okJson({ success: true }))
    callUpdateKometa()
    expect(kometaState.kometaUpdating).toBe(true)
    expect(kometaState.kometaValidated).toBe(false)
    expect(kometaState.kometaUpdateCheckSkipped).toBe(false)
    expect(kometaState.kometaUpdateCheckCompleted).toBe(false)
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('queued')
    expect(hideRunCommandSectionUntilValidated).toHaveBeenCalled()
  })

  it("disables buttons and updates run/stop/main labels", () => {
    installFixture()
    mockFetchWith(okJson({ success: true }))
    callUpdateKometa()
    expect(document.getElementById('run-now').disabled).toBe(true)
    expect(document.getElementById('run-now').innerHTML).toContain('Updating')
    expect(document.getElementById('stop-now').disabled).toBe(true)
    expect(document.getElementById('update-kometa').disabled).toBe(true)
    expect(document.getElementById('force-update').disabled).toBe(true)
    expect(document.getElementById('kometa-branch-override').disabled).toBe(true)
  })

  it("main button label: 'Installing...' when not installed + not forced", () => {
    kometaState.kometaInstalled = false
    installFixture()
    document.getElementById('force-update').checked = false
    mockFetchWith(okJson({ success: true }))
    callUpdateKometa()
    expect(document.getElementById('update-kometa').innerHTML).toContain('Installing...')
  })

  it("main button label: 'Checking for updates...' when installed + not forced", () => {
    kometaState.kometaInstalled = true
    kometaState.kometaUpdateAvailable = true  // skip path 4
    installFixture()
    document.getElementById('force-update').checked = false
    mockFetchWith(okJson({ success: true }))
    callUpdateKometa()
    expect(document.getElementById('update-kometa').innerHTML).toContain('Checking for updates...')
  })

  it("main button label: 'Force Installing...' when not installed + forced", () => {
    kometaState.kometaInstalled = false
    installFixture()
    document.getElementById('force-update').checked = true
    mockFetchWith(okJson({ success: true }))
    callUpdateKometa()
    expect(document.getElementById('update-kometa').innerHTML).toContain('Force Installing...')
  })

  it("main button label: 'Force Updating...' when installed + forced", () => {
    kometaState.kometaInstalled = true
    installFixture()
    document.getElementById('force-update').checked = true
    mockFetchWith(okJson({ success: true }))
    callUpdateKometa()
    expect(document.getElementById('update-kometa').innerHTML).toContain('Force Updating...')
  })

  it("appends 'Initializing/Updating' line + scrolls to bottom", () => {
    installFixture()
    mockFetchWith(okJson({ success: true }))
    callUpdateKometa()
    expect(document.getElementById('kometa-validation-log').textContent).toContain('Initializing/Updating Kometa')
  })

  it("fetches /update-kometa with right body", async () => {
    installFixture()
    document.getElementById('update-kometa').dataset.qsBranch = 'develop'
    document.getElementById('force-update').checked = true
    getKometaBranchOverride.mockReturnValue('feature-xyz')
    getConfiguredKometaRootPosix.mockReturnValue('/srv/kometa')
    getConfiguredKometaInstallMode.mockReturnValue('managed')
    mockFetchWith(okJson({ success: true }))
    callUpdateKometa()
    expect(global.fetch).toHaveBeenCalledWith('/update-kometa', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    }))
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body).toEqual({
      branch: 'develop',
      branch_override: 'feature-xyz',
      path: '/srv/kometa',
      install_mode: 'managed',
      force: true,
      background: true
    })
    await flush()
  })

  it("shows initial heartbeat toast immediately", () => {
    installFixture()
    mockFetchWith(okJson({ success: true }))
    callUpdateKometa()
    expect(toastCalls.some(c => c[0] === 'info' && c[1].includes('Still working on Kometa'))).toBe(true)
  })
})

// ---------------------------------------------------------------------
// Path 5: Heartbeat interval
// ---------------------------------------------------------------------

describe('callUpdateKometa -- heartbeat toast', () => {
  it("fires additional heartbeat toasts every 30 seconds", async () => {
    vi.useFakeTimers()
    installFixture()
    // Never-resolving fetch so cleanup doesn't fire during our tick
    global.fetch = vi.fn(() => new Promise(() => {}))
    callUpdateKometa()
    const startCount = toastCalls.filter(c => c[1].includes('Still working')).length
    expect(startCount).toBe(1)  // initial
    vi.advanceTimersByTime(30000)
    expect(toastCalls.filter(c => c[1].includes('Still working')).length).toBe(2)
    vi.advanceTimersByTime(30000)
    expect(toastCalls.filter(c => c[1].includes('Still working')).length).toBe(3)
  })
})

// ---------------------------------------------------------------------
// Path 5: 409 response
// ---------------------------------------------------------------------

describe('callUpdateKometa -- 409 response (Kometa running)', () => {
  it("shows warning + phase 'failed' + doesn't throw", async () => {
    installFixture()
    mockFetchWith(errJson(409, { error: 'Kometa is running' }))
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'warning' && c[1].includes('Kometa is running'))).toBe(true)
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('failed')
    // .blocked path -- so should NOT trigger the else-branch's error toast
    expect(toastCalls.some(c => c[0] === 'error' && c[1].includes('failed'))).toBe(false)
  })

  it("uses default message when 409 has no error field", async () => {
    installFixture()
    mockFetchWith(errJson(409, {}))
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'warning' && c[1].includes('Kometa is running'))).toBe(true)
  })
})

// ---------------------------------------------------------------------
// Path 5: Synchronous success (no job_id)
// ---------------------------------------------------------------------

describe('callUpdateKometa -- synchronous success', () => {
  it("shows 'up to date' info when up_to_date=true", async () => {
    // NOTE: original code has a latent bug in the sync-success path
    // (no job_id) -- it sets `postUpdateLabel` but NEVER calls
    // cleanupUI. In production the server always returns job_id, so
    // this path is effectively dead. We test what the original does:
    // toast + validateKometaRoot call. The button label doesn't get
    // the 'Up to date' text because that only happens inside cleanupUI.
    installFixture()
    mockFetchWith(okJson({ success: true, up_to_date: true }))
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'info' && c[1].includes('already up to date'))).toBe(true)
  })

  it("shows success 'completed' when up_to_date=false", async () => {
    installFixture()
    mockFetchWith(okJson({ success: true, up_to_date: false }))
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'success' && c[1].includes('completed'))).toBe(true)
  })

  it("hides kometa-update-box + clears updateAvailable", async () => {
    installFixture()
    kometaState.kometaUpdateAvailable = true
    mockFetchWith(okJson({ success: true }))
    callUpdateKometa()
    await flush()
    expect(document.getElementById('kometa-update-box').classList.contains('d-none')).toBe(true)
    expect(kometaState.kometaUpdateAvailable).toBe(false)
  })

  it("calls validateKometaRoot with appendStatus=true", async () => {
    installFixture()
    mockFetchWith(okJson({ success: true }))
    callUpdateKometa()
    await flush()
    expect(validateKometaRoot).toHaveBeenCalledWith({ appendStatus: true })
  })
})

// ---------------------------------------------------------------------
// Path 5: Synchronous failure
// ---------------------------------------------------------------------

describe('callUpdateKometa -- synchronous failure', () => {
  it("shows error toast when success=false and NOT blocked", async () => {
    installFixture()
    mockFetchWith(okJson({ success: false, error: 'boom' }))
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'error' && c[1].includes('boom'))).toBe(true)
    expect(validateKometaRoot).toHaveBeenCalledWith({ appendStatus: true })
  })

  it("uses default message when no error field", async () => {
    installFixture()
    mockFetchWith(okJson({ success: false }))
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'error' && c[1].includes('Kometa update failed'))).toBe(true)
  })
})

// ---------------------------------------------------------------------
// Path 5: Fetch reject (network error)
// ---------------------------------------------------------------------

describe('callUpdateKometa -- fetch reject', () => {
  it("shows error toast + phase 'failed' + cleans up", async () => {
    installFixture()
    global.fetch = vi.fn(() => Promise.reject(new Error('network down')))
    // Silence expected console.error from the catch handler
    const originalErr = console.error
    console.error = vi.fn()
    callUpdateKometa()
    await flush()
    console.error = originalErr
    expect(toastCalls.some(c => c[0] === 'error' && c[1].includes('Error during Kometa update'))).toBe(true)
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('failed')
    // Cleanup: state flag flipped back
    expect(kometaState.kometaUpdating).toBe(false)
  })
})

// ---------------------------------------------------------------------
// Path 5: Background job polling
// ---------------------------------------------------------------------

describe('callUpdateKometa -- background job polling', () => {
  it("stores job_id and calls pollKometaUpdateProgress", async () => {
    installFixture()
    mockFetchWith(okJson({ success: true, job_id: 'JOB-123' }))
    pollKometaUpdateProgress.mockResolvedValue({ done: false })
    callUpdateKometa()
    await flush()
    expect(kometaState.kometaUpdateJobId).toBe('JOB-123')
    expect(pollKometaUpdateProgress).toHaveBeenCalled()
    expect(stopKometaUpdatePolling).toHaveBeenCalled()  // called before setting new interval
  })

  it("finalize immediately on done=true + update_success=true + up_to_date=true", async () => {
    installFixture()
    mockFetchWith(okJson({ success: true, job_id: 'JOB-1' }))
    pollKometaUpdateProgress.mockResolvedValue({
      done: true,
      update_success: true,
      up_to_date: true
    })
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'info' && c[1].includes('already up to date'))).toBe(true)
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('ready')
    expect(appendKometaStatusLine).toHaveBeenCalledWith('Kometa is already up to date.')
    expect(validateKometaRoot).toHaveBeenCalledWith({ appendStatus: true })
  })

  it("finalize on done=true + update_success=true (update, not up-to-date)", async () => {
    installFixture()
    mockFetchWith(okJson({ success: true, job_id: 'JOB-2' }))
    pollKometaUpdateProgress.mockResolvedValue({
      done: true,
      update_success: true,
      up_to_date: false
    })
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'success' && c[1].includes('completed'))).toBe(true)
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('validating')
    expect(appendKometaStatusLine).toHaveBeenCalledWith('Kometa update completed successfully.')
  })

  it("finalize on done=true + update_success=false (failure)", async () => {
    installFixture()
    mockFetchWith(okJson({ success: true, job_id: 'JOB-3' }))
    pollKometaUpdateProgress.mockResolvedValue({
      done: true,
      update_success: false
    })
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'error' && c[1].includes('Kometa update failed'))).toBe(true)
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('failed')
    expect(validateKometaRoot).toHaveBeenCalledWith({ appendStatus: true })
  })

  it("prefers 'update_success' over 'success' when both present", async () => {
    // Old servers used 'success', new servers use 'update_success'.
    // If both present, update_success wins via ?? coalescing.
    installFixture()
    mockFetchWith(okJson({ success: true, job_id: 'JOB-4' }))
    pollKometaUpdateProgress.mockResolvedValue({
      done: true,
      update_success: false,   // authoritative
      success: true            // legacy
    })
    callUpdateKometa()
    await flush()
    expect(toastCalls.some(c => c[0] === 'error')).toBe(true)  // failure path
  })

  it("falls back to 'success' when 'update_success' is undefined", async () => {
    installFixture()
    mockFetchWith(okJson({ success: true, job_id: 'JOB-5' }))
    pollKometaUpdateProgress.mockResolvedValue({
      done: true,
      // no update_success
      success: true
    })
    callUpdateKometa()
    await flush()
    // Success path taken
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('validating')
  })

  it("schedules setInterval polling when initial poll returns done=false", async () => {
    vi.useFakeTimers()
    installFixture()
    mockFetchWith(okJson({ success: true, job_id: 'JOB-6' }))
    pollKometaUpdateProgress.mockResolvedValue({ done: false })
    callUpdateKometa()
    // Flush initial poll -- can't use flush() with fake timers
    await vi.advanceTimersByTimeAsync(0)
    await Promise.resolve()
    // Now setInterval should be scheduled at 800ms
    expect(kometaState.kometaUpdatePollInterval).toBeTruthy()
  })

  it("handles polling error via catch (phase 'failed', cleanup)", async () => {
    vi.useFakeTimers()
    installFixture()
    mockFetchWith(okJson({ success: true, job_id: 'JOB-7' }))
    // First poll succeeds with done=false to trigger interval
    pollKometaUpdateProgress
      .mockResolvedValueOnce({ done: false })
      // Second poll (via interval) rejects
      .mockRejectedValueOnce(new Error('poll fail'))
    // Silence console.error for this test only
    const originalErr = console.error
    console.error = vi.fn()
    callUpdateKometa()
    await vi.advanceTimersByTimeAsync(0)
    await Promise.resolve()
    // Trigger the interval poll
    await vi.advanceTimersByTimeAsync(800)
    await Promise.resolve()
    await Promise.resolve()
    console.error = originalErr
    // Cleanup ran
    expect(kometaState.kometaUpdating).toBe(false)
  })
})

// ---------------------------------------------------------------------
// cleanupUI (via job_id + done=true completion)
// ---------------------------------------------------------------------
//
// IMPORTANT: cleanupUI is only invoked via the background-job path
// (fetch returns job_id, then poll returns done=true) OR the fetch
// catch handler. The synchronous-success path in the original code
// SETS postUpdateLabel but never calls cleanupUI -- a latent bug we
// preserve. All cleanup tests go through the job_id + done=true path.

describe('callUpdateKometa -- cleanupUI', () => {
  it("clears state flags + re-enables buttons on completion", async () => {
    installFixture()
    mockFetchWith(okJson({ success: true, job_id: 'JOB-C1' }))
    pollKometaUpdateProgress.mockResolvedValue({
      done: true,
      update_success: true,
      up_to_date: true
    })
    callUpdateKometa()
    await flush()
    expect(kometaState.kometaUpdating).toBe(false)
    expect(kometaState.kometaUpdateJobId).toBeNull()
    expect(document.getElementById('run-now').disabled).toBe(false)
    expect(document.getElementById('stop-now').disabled).toBe(false)
    expect(document.getElementById('update-kometa').disabled).toBe(false)
    expect(document.getElementById('force-update').disabled).toBe(false)
    expect(document.getElementById('kometa-branch-override').disabled).toBe(false)
  })

  it("restores run-now's previous HTML + disabled state", async () => {
    installFixture()
    const runNow = document.getElementById('run-now')
    runNow.innerHTML = '<i>Original Label</i>'
    runNow.disabled = false
    mockFetchWith(okJson({ success: true, job_id: 'JOB-C2' }))
    pollKometaUpdateProgress.mockResolvedValue({
      done: true,
      update_success: true
    })
    callUpdateKometa()
    // Snapshot taken; button now shows "Updating..."
    expect(runNow.innerHTML).toContain('Updating')
    await flush()
    // Restored
    expect(runNow.innerHTML).toBe('<i>Original Label</i>')
    expect(runNow.disabled).toBe(false)
  })

  it("sets postUpdateLabel on 'up to date' branch and schedules reset via setTimeout", async () => {
    vi.useFakeTimers()
    installFixture()
    mockFetchWith(okJson({ success: true, job_id: 'JOB-C3' }))
    pollKometaUpdateProgress.mockResolvedValue({
      done: true,
      update_success: true,
      up_to_date: true
    })
    callUpdateKometa()
    // Advance microtasks for fetch chain
    await vi.advanceTimersByTimeAsync(0)
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
    expect(document.getElementById('update-kometa').innerHTML).toContain('Up to date')
    // The setTimeout to reset button label is scheduled at 6000ms
    syncUpdateButtonLabel.mockClear()
    await vi.advanceTimersByTimeAsync(6000)
    expect(syncUpdateButtonLabel).toHaveBeenCalled()
  })

  it("calls updateRunNowState + syncFinalAccordionRollups in cleanup", async () => {
    installFixture()
    mockFetchWith(okJson({ success: true, job_id: 'JOB-C4' }))
    pollKometaUpdateProgress.mockResolvedValue({
      done: true,
      update_success: true
    })
    callUpdateKometa()
    await flush()
    expect(updateRunNowState).toHaveBeenCalled()
    // syncFinalAccordionRollups is called at least twice: once during
    // setup, once during cleanup.
    expect(syncFinalAccordionRollups.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it("stops the heartbeat interval on cleanup", async () => {
    vi.useFakeTimers()
    installFixture()
    mockFetchWith(okJson({ success: true, job_id: 'JOB-C5' }))
    pollKometaUpdateProgress.mockResolvedValue({
      done: true,
      update_success: true
    })
    callUpdateKometa()
    // Flush the fetch + poll chain
    await vi.advanceTimersByTimeAsync(0)
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
    // Heartbeat should now be cleared. Advancing 60s shouldn't add new toasts.
    const before = toastCalls.filter(c => c[1].includes('Still working')).length
    await vi.advanceTimersByTimeAsync(60000)
    const after = toastCalls.filter(c => c[1].includes('Still working')).length
    expect(after).toBe(before)
  })
})
