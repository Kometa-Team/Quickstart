// Tests for static/local-js/modules/kometa/_updateCheck.js
//
// One export: checkKometaUpdate(forceRefresh = false).
//
// COVERAGE STRATEGY:
//
//   Short circuits (2 branches):
//     - kometaCanCheckUpdateStatus() false -> synthetic 'skipped' resolve
//     - no configuredRootPosix -> null resolve
//
//   Fetch request:
//     - correct URL / method / headers / body construction
//     - forceRefresh forwarded as `force`
//
//   Success path (many state writes + DOM effects):
//     - kometaState fields updated from response flags
//     - server log lines forwarded to appendKometaStatusLine
//     - syncKometaSourceStatus called with the right shape
//     - #kometa-update-box shown when local + remote + available all set
//     - #kometa-update-box hidden otherwise (3 variants)
//     - syncUpdateButtonLabel + syncKometaRollupBadge called
//
//   Error path:
//     - !res.ok -> rejects with server error message
//     - !res.ok + no server message -> rejects with fallback
//     - network reject propagates
//     - error handler appends red-X line, clears source status, re-throws

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Mock every collaborator so this module's behavior is testable in
// isolation. The signatures match what _updateCheck.js imports.
vi.mock('../../../static/local-js/modules/kometa/_runtime.js', () => ({
  kometaCanCheckUpdateStatus: vi.fn(() => true),
  getConfiguredKometaRootPosix: vi.fn(() => '/opt/kometa'),
  getConfiguredKometaInstallMode: vi.fn(() => 'managed')
}))
vi.mock('../../../static/local-js/modules/kometa/_kometaBranch.js', () => ({
  getKometaBranchOverride: vi.fn(() => 'auto'),
  syncKometaSourceStatus: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_updatePhase.js', () => ({
  appendKometaStatusLine: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_updateRollup.js', () => ({
  syncUpdateButtonLabel: vi.fn(),
  syncKometaRollupBadge: vi.fn()
}))

import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import { checkKometaUpdate } from '../../../static/local-js/modules/kometa/_updateCheck.js'
import {
  kometaCanCheckUpdateStatus,
  getConfiguredKometaRootPosix
} from '../../../static/local-js/modules/kometa/_runtime.js'
import {
  getKometaBranchOverride,
  syncKometaSourceStatus
} from '../../../static/local-js/modules/kometa/_kometaBranch.js'
import { appendKometaStatusLine } from '../../../static/local-js/modules/kometa/_updatePhase.js'
import {
  syncUpdateButtonLabel,
  syncKometaRollupBadge
} from '../../../static/local-js/modules/kometa/_updateRollup.js'

// ---------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------

let originalFetch

function mockFetchWith (response) {
  global.fetch = vi.fn(() => Promise.resolve(response))
}

function okJson (body) {
  return { ok: true, json: () => Promise.resolve(body) }
}

function errJson (status, body) {
  return { ok: false, status, json: () => Promise.resolve(body) }
}

function installUpdateBox () {
  document.body.innerHTML = `
    <div id="kometa-update-box" class="d-none"></div>
    <span id="kometa-local-version"></span>
    <span id="kometa-remote-version"></span>
  `
}

function resetState () {
  kometaState.kometaLocalCheckCompleted = false
  kometaState.kometaInstalled = false
  kometaState.kometaUpdateCheckCompleted = false
  kometaState.kometaUpdateCheckSkipped = false
  kometaState.kometaUpdateAvailable = false
  kometaState.kometaLocalVersionStatus = 'Unknown'
}

beforeEach(() => {
  kometaCanCheckUpdateStatus.mockReset()
  kometaCanCheckUpdateStatus.mockReturnValue(true)
  getConfiguredKometaRootPosix.mockReset()
  getConfiguredKometaRootPosix.mockReturnValue('/opt/kometa')
  getKometaBranchOverride.mockReset()
  getKometaBranchOverride.mockReturnValue('auto')
  syncKometaSourceStatus.mockClear()
  appendKometaStatusLine.mockClear()
  syncUpdateButtonLabel.mockClear()
  syncKometaRollupBadge.mockClear()

  originalFetch = global.fetch
  resetState()
})

afterEach(() => {
  global.fetch = originalFetch
  document.body.innerHTML = ''
})

// ---------------------------------------------------------------------
// Short-circuit branches
// ---------------------------------------------------------------------

describe('checkKometaUpdate -- short circuits', () => {
  it("returns a synthetic 'skipped' response when canCheckUpdateStatus is false", async () => {
    kometaCanCheckUpdateStatus.mockReturnValue(false)
    const result = await checkKometaUpdate()
    expect(result).toEqual({
      success: true,
      update_check_completed: false,
      kometa_update_check_skipped: true,
      kometa_update_available: false
    })
    // Should have appended the info line about external mode
    expect(appendKometaStatusLine).toHaveBeenCalledWith(expect.stringContaining('external Kometa mode'))
  })

  it('resolves null when no Kometa root is configured', async () => {
    getConfiguredKometaRootPosix.mockReturnValue('')
    const result = await checkKometaUpdate()
    expect(result).toBeNull()
    // Should NOT have appended anything (silent)
    expect(appendKometaStatusLine).not.toHaveBeenCalled()
  })

  it("null-config short-circuit does NOT hit the network", async () => {
    getConfiguredKometaRootPosix.mockReturnValue('')
    global.fetch = vi.fn()
    await checkKometaUpdate()
    expect(global.fetch).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------
// Fetch request construction
// ---------------------------------------------------------------------

describe('checkKometaUpdate -- request construction', () => {
  it('POSTs to /check-kometa-update with JSON body', async () => {
    installUpdateBox()
    mockFetchWith(okJson({ kometa_installed: true }))
    await checkKometaUpdate()
    expect(global.fetch).toHaveBeenCalledWith('/check-kometa-update', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    }))
  })

  it('forwards path, install_mode, force, branch_override in the body', async () => {
    installUpdateBox()
    getConfiguredKometaRootPosix.mockReturnValue('/custom/path')
    getKometaBranchOverride.mockReturnValue('develop')
    mockFetchWith(okJson({ kometa_installed: true }))
    await checkKometaUpdate(true)
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body).toEqual({
      path: '/custom/path',
      install_mode: 'managed',
      force: true,
      branch_override: 'develop'
    })
  })

  it('defaults force to false when forceRefresh is omitted', async () => {
    installUpdateBox()
    mockFetchWith(okJson({ kometa_installed: true }))
    await checkKometaUpdate()
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body.force).toBe(false)
  })
})

// ---------------------------------------------------------------------
// Success path -- state updates
// ---------------------------------------------------------------------

describe('checkKometaUpdate -- success path state updates', () => {
  it('folds response flags into kometaState (all boolean coerced)', async () => {
    installUpdateBox()
    mockFetchWith(okJson({
      kometa_installed: 1,       // truthy non-boolean
      update_check_completed: true,
      kometa_update_check_skipped: false,
      kometa_update_available: 'yes'  // truthy non-boolean
    }))
    await checkKometaUpdate()
    expect(kometaState.kometaLocalCheckCompleted).toBe(true)
    expect(kometaState.kometaInstalled).toBe(true)
    expect(kometaState.kometaUpdateCheckCompleted).toBe(true)
    expect(kometaState.kometaUpdateCheckSkipped).toBe(false)
    expect(kometaState.kometaUpdateAvailable).toBe(true)
  })

  it('forwards every log line to appendKometaStatusLine', async () => {
    installUpdateBox()
    mockFetchWith(okJson({
      kometa_installed: true,
      log: ['line one', 'line two']
    }))
    await checkKometaUpdate()
    expect(appendKometaStatusLine).toHaveBeenCalledWith('line one')
    expect(appendKometaStatusLine).toHaveBeenCalledWith('line two')
  })

  it('handles missing log field gracefully (no appends)', async () => {
    installUpdateBox()
    mockFetchWith(okJson({ kometa_installed: true }))
    await checkKometaUpdate()
    expect(appendKometaStatusLine).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------
// Success path -- source-status sync
// ---------------------------------------------------------------------

describe('checkKometaUpdate -- syncKometaSourceStatus payload', () => {
  it('passes local_version + remote_version + checked + skipped', async () => {
    installUpdateBox()
    mockFetchWith(okJson({
      kometa_installed: true,
      update_check_completed: true,
      kometa_update_check_skipped: false,
      local_version: 'v1.0.0',
      remote_version: 'v1.1.0'
    }))
    await checkKometaUpdate()
    expect(syncKometaSourceStatus).toHaveBeenCalledWith({
      localVersion: 'v1.0.0',
      remoteVersion: 'v1.1.0',
      checked: true,
      skipped: false
    })
  })

  it('falls back to kometaLocalVersionStatus when local_version is missing', async () => {
    installUpdateBox()
    kometaState.kometaLocalVersionStatus = 'v0.9.0-fallback'
    mockFetchWith(okJson({
      kometa_installed: true,
      remote_version: 'v1.1.0'
    }))
    await checkKometaUpdate()
    expect(syncKometaSourceStatus.mock.calls[0][0].localVersion).toBe('v0.9.0-fallback')
  })

  it("passes empty string for remoteVersion when missing", async () => {
    installUpdateBox()
    mockFetchWith(okJson({ kometa_installed: true }))
    await checkKometaUpdate()
    expect(syncKometaSourceStatus.mock.calls[0][0].remoteVersion).toBe('')
  })
})

// ---------------------------------------------------------------------
// Success path -- update-box visibility
// ---------------------------------------------------------------------

describe('checkKometaUpdate -- update box visibility', () => {
  it('shows the update box when local + remote + available all set', async () => {
    installUpdateBox()
    mockFetchWith(okJson({
      kometa_installed: true,
      kometa_update_available: true,
      local_version: 'v1.0.0',
      remote_version: 'v1.1.0'
    }))
    await checkKometaUpdate()
    const box = document.getElementById('kometa-update-box')
    expect(box.classList.contains('d-none')).toBe(false)
    expect(document.getElementById('kometa-local-version').textContent).toBe('v1.0.0')
    expect(document.getElementById('kometa-remote-version').textContent).toBe('v1.1.0')
  })

  it('hides the update box when no update is available', async () => {
    installUpdateBox()
    document.getElementById('kometa-update-box').classList.remove('d-none')  // start visible
    mockFetchWith(okJson({
      kometa_installed: true,
      kometa_update_available: false,
      local_version: 'v1.0.0',
      remote_version: 'v1.0.0'
    }))
    await checkKometaUpdate()
    expect(document.getElementById('kometa-update-box').classList.contains('d-none')).toBe(true)
  })

  it('hides the update box when local_version is missing', async () => {
    installUpdateBox()
    mockFetchWith(okJson({
      kometa_installed: true,
      kometa_update_available: true,
      remote_version: 'v1.1.0'
    }))
    await checkKometaUpdate()
    expect(document.getElementById('kometa-update-box').classList.contains('d-none')).toBe(true)
  })

  it('hides the update box when remote_version is missing', async () => {
    installUpdateBox()
    mockFetchWith(okJson({
      kometa_installed: true,
      kometa_update_available: true,
      local_version: 'v1.0.0'
    }))
    await checkKometaUpdate()
    expect(document.getElementById('kometa-update-box').classList.contains('d-none')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// Success path -- UI refresh calls
// ---------------------------------------------------------------------

describe('checkKometaUpdate -- UI refresh after success', () => {
  it('calls syncUpdateButtonLabel and syncKometaRollupBadge', async () => {
    installUpdateBox()
    mockFetchWith(okJson({ kometa_installed: true }))
    await checkKometaUpdate()
    expect(syncUpdateButtonLabel).toHaveBeenCalledTimes(1)
    expect(syncKometaRollupBadge).toHaveBeenCalledTimes(1)
  })

  it('resolves to the server data', async () => {
    installUpdateBox()
    const responseData = { kometa_installed: true, custom_field: 'preserved' }
    mockFetchWith(okJson(responseData))
    const result = await checkKometaUpdate()
    expect(result).toEqual(responseData)
  })
})

// ---------------------------------------------------------------------
// Error path
// ---------------------------------------------------------------------

describe('checkKometaUpdate -- error path', () => {
  it('rejects with server error message when !res.ok', async () => {
    installUpdateBox()
    mockFetchWith(errJson(500, { error: 'server exploded' }))
    await expect(checkKometaUpdate()).rejects.toThrow('server exploded')
  })

  it('rejects with fallback message when server omits data.error', async () => {
    installUpdateBox()
    mockFetchWith(errJson(500, {}))
    await expect(checkKometaUpdate()).rejects.toThrow('Failed to check Kometa update status.')
  })

  it('propagates network errors', async () => {
    installUpdateBox()
    global.fetch = vi.fn(() => Promise.reject(new Error('network fried')))
    await expect(checkKometaUpdate()).rejects.toThrow('network fried')
  })

  it('appends a red-X line on error', async () => {
    installUpdateBox()
    mockFetchWith(errJson(500, { error: 'boom' }))
    await expect(checkKometaUpdate()).rejects.toThrow()
    const lastCall = appendKometaStatusLine.mock.calls.at(-1)?.[0]
    expect(lastCall).toContain('boom')
    expect(lastCall).toContain('\u274c')  // red X emoji
  })

  it('clears source status on error', async () => {
    installUpdateBox()
    mockFetchWith(errJson(500, {}))
    await expect(checkKometaUpdate()).rejects.toThrow()
    expect(syncKometaSourceStatus).toHaveBeenCalledWith({
      checked: false,
      skipped: false,
      remoteVersion: ''
    })
  })

  it('still refreshes button label + rollup badge on error', async () => {
    installUpdateBox()
    mockFetchWith(errJson(500, {}))
    await expect(checkKometaUpdate()).rejects.toThrow()
    expect(syncUpdateButtonLabel).toHaveBeenCalledTimes(1)
    expect(syncKometaRollupBadge).toHaveBeenCalledTimes(1)
  })
})
