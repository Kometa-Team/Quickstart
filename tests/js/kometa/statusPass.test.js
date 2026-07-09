// Tests for static/local-js/modules/kometa/_statusPass.js
//
// One export: runKometaStatusPass(forceRefresh = false).
//
// COVERAGE STRATEGY:
//
//   Setup (header block + invalidation):
//     - status log gets the 7-line header
//     - phase badge set to 'checking'
//     - invalidateKometaUpdateStatus called
//
//   Pipeline branches (based on probe result + install mode):
//     - probe rejects -> catch, phase 'failed', resolves null
//     - external mode -> info line, phase 'idle', no update check
//     - !res or !res.kometa_installed -> info line, phase 'idle',
//       no update check
//     - installed + not external -> checkKometaUpdate called
//
//   Post-pipeline (phase badge based on state):
//     - installed -> phase 'ready'
//     - !installed -> phase 'idle'
//     - kometaUpdating -> no badge touch (updates own it)
//
//   Force refresh forwarding:
//     - forceRefresh=true is passed to checkKometaUpdate
//
//   Return value:
//     - resolves to probe result on short-circuit paths
//     - resolves to checkKometaUpdate result on full pipeline
//     - resolves to null on catch

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../static/local-js/modules/kometa/_runtime.js', () => ({
  getConfiguredKometaInstallMode: vi.fn(() => 'managed')
}))
vi.mock('../../../static/local-js/modules/kometa/_kometaBranch.js', () => ({
  getKometaBranchOverride: vi.fn(() => ''),
  getEffectiveKometaBranch: vi.fn(() => 'master'),
  getKometaVersionSourceUrlValue: vi.fn(() => 'https://example.com/VERSION'),
  getKometaZipSourceUrlValue: vi.fn(() => 'https://example.com/master.zip')
}))
vi.mock('../../../static/local-js/modules/kometa/_updatePhase.js', () => ({
  setKometaStatusLog: vi.fn(),
  appendKometaStatusLine: vi.fn(),
  setKometaUpdatePhaseBadge: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_updateRollup.js', () => ({
  invalidateKometaUpdateStatus: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_probeRoot.js', () => ({
  probeKometaRoot: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_updateCheck.js', () => ({
  checkKometaUpdate: vi.fn()
}))

import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import { runKometaStatusPass } from '../../../static/local-js/modules/kometa/_statusPass.js'
import { getConfiguredKometaInstallMode } from '../../../static/local-js/modules/kometa/_runtime.js'
import { getKometaBranchOverride } from '../../../static/local-js/modules/kometa/_kometaBranch.js'
import {
  setKometaStatusLog,
  appendKometaStatusLine,
  setKometaUpdatePhaseBadge
} from '../../../static/local-js/modules/kometa/_updatePhase.js'
import { invalidateKometaUpdateStatus } from '../../../static/local-js/modules/kometa/_updateRollup.js'
import { probeKometaRoot } from '../../../static/local-js/modules/kometa/_probeRoot.js'
import { checkKometaUpdate } from '../../../static/local-js/modules/kometa/_updateCheck.js'

// ---------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------

beforeEach(() => {
  getConfiguredKometaInstallMode.mockReset()
  getConfiguredKometaInstallMode.mockReturnValue('managed')
  getKometaBranchOverride.mockReset()
  getKometaBranchOverride.mockReturnValue('')
  setKometaStatusLog.mockClear()
  appendKometaStatusLine.mockClear()
  setKometaUpdatePhaseBadge.mockClear()
  invalidateKometaUpdateStatus.mockClear()
  probeKometaRoot.mockReset()
  checkKometaUpdate.mockReset()

  kometaState.kometaUpdating = false
  kometaState.kometaInstalled = false
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------
// Setup phase
// ---------------------------------------------------------------------

describe('runKometaStatusPass -- setup phase', () => {
  it("writes the 7-line header block to the status log with phase 'checking'", async () => {
    probeKometaRoot.mockResolvedValue({ kometa_installed: false })
    await runKometaStatusPass()
    expect(setKometaStatusLog).toHaveBeenCalledTimes(1)
    const [lines, phase] = setKometaStatusLog.mock.calls[0]
    expect(Array.isArray(lines)).toBe(true)
    expect(lines.length).toBe(7)
    expect(phase).toBe('checking')
    // Sanity: some expected content in the header
    expect(lines.join(' ')).toContain('Refreshing Kometa status')
    expect(lines.join(' ')).toContain('Selected Kometa branch mode')
  })

  it("calls invalidateKometaUpdateStatus at the start", async () => {
    probeKometaRoot.mockResolvedValue({ kometa_installed: false })
    await runKometaStatusPass()
    expect(invalidateKometaUpdateStatus).toHaveBeenCalledTimes(1)
  })

  it("shows selected branch mode as 'auto' when getKometaBranchOverride returns empty", async () => {
    getKometaBranchOverride.mockReturnValue('')
    probeKometaRoot.mockResolvedValue({ kometa_installed: false })
    await runKometaStatusPass()
    const lines = setKometaStatusLog.mock.calls[0][0]
    expect(lines.some(l => l.includes('Selected Kometa branch mode: auto'))).toBe(true)
  })

  it("shows selected branch mode when getKometaBranchOverride returns a value", async () => {
    getKometaBranchOverride.mockReturnValue('develop')
    probeKometaRoot.mockResolvedValue({ kometa_installed: false })
    await runKometaStatusPass()
    const lines = setKometaStatusLog.mock.calls[0][0]
    expect(lines.some(l => l.includes('Selected Kometa branch mode: develop'))).toBe(true)
  })
})

// ---------------------------------------------------------------------
// Pipeline branches
// ---------------------------------------------------------------------

describe('runKometaStatusPass -- pipeline branches', () => {
  it("skips update check in external mode (appends info line + phase 'idle')", async () => {
    getConfiguredKometaInstallMode.mockReturnValue('external')
    probeKometaRoot.mockResolvedValue({ kometa_installed: true })
    await runKometaStatusPass()
    expect(checkKometaUpdate).not.toHaveBeenCalled()
    expect(appendKometaStatusLine).toHaveBeenCalledWith(expect.stringContaining('External Kometa mode detected'))
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('idle')
  })

  it("skips update check when probe returns null", async () => {
    probeKometaRoot.mockResolvedValue(null)
    await runKometaStatusPass()
    expect(checkKometaUpdate).not.toHaveBeenCalled()
    expect(appendKometaStatusLine).toHaveBeenCalledWith(expect.stringContaining('Kometa is not installed'))
  })

  it("skips update check when Kometa is not installed", async () => {
    probeKometaRoot.mockResolvedValue({ kometa_installed: false })
    await runKometaStatusPass()
    expect(checkKometaUpdate).not.toHaveBeenCalled()
    expect(appendKometaStatusLine).toHaveBeenCalledWith(expect.stringContaining('Kometa is not installed'))
  })

  it("calls checkKometaUpdate when installed + not external", async () => {
    probeKometaRoot.mockResolvedValue({ kometa_installed: true })
    checkKometaUpdate.mockResolvedValue({ update_check_completed: true })
    await runKometaStatusPass()
    expect(checkKometaUpdate).toHaveBeenCalledTimes(1)
    expect(appendKometaStatusLine).toHaveBeenCalledWith(expect.stringContaining('Checking Kometa update status'))
  })
})

// ---------------------------------------------------------------------
// Force refresh forwarding
// ---------------------------------------------------------------------

describe('runKometaStatusPass -- forceRefresh forwarding', () => {
  it("forwards forceRefresh=true to checkKometaUpdate", async () => {
    probeKometaRoot.mockResolvedValue({ kometa_installed: true })
    checkKometaUpdate.mockResolvedValue({})
    await runKometaStatusPass(true)
    expect(checkKometaUpdate).toHaveBeenCalledWith(true)
  })

  it("defaults forceRefresh to false when omitted", async () => {
    probeKometaRoot.mockResolvedValue({ kometa_installed: true })
    checkKometaUpdate.mockResolvedValue({})
    await runKometaStatusPass()
    expect(checkKometaUpdate).toHaveBeenCalledWith(false)
  })
})

// ---------------------------------------------------------------------
// Post-pipeline phase badge
// ---------------------------------------------------------------------

describe('runKometaStatusPass -- post-pipeline phase badge', () => {
  it("sets phase 'ready' when installed after pipeline", async () => {
    probeKometaRoot.mockResolvedValue({ kometa_installed: true })
    checkKometaUpdate.mockImplementation(async () => {
      kometaState.kometaInstalled = true
      return {}
    })
    await runKometaStatusPass()
    // Final phase call should be 'ready'
    const badgeCalls = setKometaUpdatePhaseBadge.mock.calls.map(c => c[0])
    expect(badgeCalls[badgeCalls.length - 1]).toBe('ready')
  })

  it("sets phase 'idle' when NOT installed after pipeline", async () => {
    kometaState.kometaInstalled = false
    probeKometaRoot.mockResolvedValue({ kometa_installed: true })
    checkKometaUpdate.mockImplementation(async () => {
      kometaState.kometaInstalled = false
      return {}
    })
    await runKometaStatusPass()
    const badgeCalls = setKometaUpdatePhaseBadge.mock.calls.map(c => c[0])
    expect(badgeCalls[badgeCalls.length - 1]).toBe('idle')
  })

  it("does NOT touch phase badge when kometaUpdating=true", async () => {
    kometaState.kometaUpdating = true
    probeKometaRoot.mockResolvedValue({ kometa_installed: true })
    checkKometaUpdate.mockResolvedValue({})
    await runKometaStatusPass()
    // The only phase call is the 'checking' one from setKometaStatusLog,
    // NOT from anywhere in runKometaStatusPass -- statusLog phase is
    // via setKometaStatusLog second arg, not setKometaUpdatePhaseBadge.
    // So setKometaUpdatePhaseBadge should not have been called at all.
    expect(setKometaUpdatePhaseBadge).not.toHaveBeenCalled()
  })

  it("does NOT touch phase badge on external-mode short-circuit when updating", async () => {
    kometaState.kometaUpdating = true
    getConfiguredKometaInstallMode.mockReturnValue('external')
    probeKometaRoot.mockResolvedValue({ kometa_installed: true })
    await runKometaStatusPass()
    expect(setKometaUpdatePhaseBadge).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------
// Catch path
// ---------------------------------------------------------------------

describe('runKometaStatusPass -- catch path', () => {
  it("resolves null when probeKometaRoot rejects", async () => {
    probeKometaRoot.mockRejectedValue(new Error('probe failed'))
    const result = await runKometaStatusPass()
    expect(result).toBeNull()
  })

  it("sets phase 'failed' on probe error (when not updating)", async () => {
    probeKometaRoot.mockRejectedValue(new Error('probe failed'))
    await runKometaStatusPass()
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('failed')
  })

  it("does NOT touch phase badge on error when updating", async () => {
    kometaState.kometaUpdating = true
    probeKometaRoot.mockRejectedValue(new Error('probe failed'))
    await runKometaStatusPass()
    expect(setKometaUpdatePhaseBadge).not.toHaveBeenCalled()
  })

  it("resolves null when checkKometaUpdate rejects", async () => {
    probeKometaRoot.mockResolvedValue({ kometa_installed: true })
    checkKometaUpdate.mockRejectedValue(new Error('check failed'))
    const result = await runKometaStatusPass()
    expect(result).toBeNull()
  })
})

// ---------------------------------------------------------------------
// Return values
// ---------------------------------------------------------------------

describe('runKometaStatusPass -- return values', () => {
  it("returns probe result on external short-circuit", async () => {
    getConfiguredKometaInstallMode.mockReturnValue('external')
    const probeResult = { kometa_installed: true, custom: 'x' }
    probeKometaRoot.mockResolvedValue(probeResult)
    const result = await runKometaStatusPass()
    expect(result).toEqual(probeResult)
  })

  it("returns probe result on !installed short-circuit", async () => {
    const probeResult = { kometa_installed: false }
    probeKometaRoot.mockResolvedValue(probeResult)
    const result = await runKometaStatusPass()
    expect(result).toEqual(probeResult)
  })

  it("returns checkKometaUpdate result on full pipeline", async () => {
    probeKometaRoot.mockResolvedValue({ kometa_installed: true })
    const checkResult = { kometa_update_available: true, local_version: 'v1.0' }
    checkKometaUpdate.mockResolvedValue(checkResult)
    const result = await runKometaStatusPass()
    expect(result).toEqual(checkResult)
  })
})
