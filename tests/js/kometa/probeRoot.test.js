// Tests for static/local-js/modules/kometa/_probeRoot.js
//
// One export: probeKometaRoot().
//
// COVERAGE STRATEGY:
//
//   Short-circuits (1):
//     - no configured root -> null resolve, error appended
//
//   Request construction (2):
//     - URL / method / headers correct
//     - body has path + install_mode
//
//   Success path (data-attr caching, state updates, DOM writes):
//     - kometaState fields updated
//     - log lines appended
//     - dataset attrs written on #run-command-output
//     - installPath element text set
//     - source status synced
//     - installed=false: validated cleared + hide called
//     - installed=true: no hide-section call
//     - kometaVersion fallback to 'Unknown'
//     - display / posix fallbacks work
//
//   Error path (server + network):
//     - non-ok response with error message
//     - non-ok response without error message (fallback)
//     - network reject
//     - non-JSON body doesn't crash

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../static/local-js/modules/kometa/_runtime.js', () => ({
  getConfiguredKometaRootPosix: vi.fn(() => '/opt/kometa'),
  getConfiguredKometaRootDisplay: vi.fn(() => '/opt/kometa'),
  getConfiguredKometaInstallMode: vi.fn(() => 'managed')
}))
vi.mock('../../../static/local-js/modules/kometa/_kometaBranch.js', () => ({
  syncKometaSourceStatus: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_updatePhase.js', () => ({
  appendKometaStatusLine: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_updateRollup.js', () => ({
  syncUpdateButtonLabel: vi.fn(),
  syncKometaRollupBadge: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_runCommandSection.js', () => ({
  hideRunCommandSectionUntilValidated: vi.fn()
}))

import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import { probeKometaRoot } from '../../../static/local-js/modules/kometa/_probeRoot.js'
import { getConfiguredKometaRootPosix } from '../../../static/local-js/modules/kometa/_runtime.js'
import { syncKometaSourceStatus } from '../../../static/local-js/modules/kometa/_kometaBranch.js'
import { appendKometaStatusLine } from '../../../static/local-js/modules/kometa/_updatePhase.js'
import {
  syncUpdateButtonLabel,
  syncKometaRollupBadge
} from '../../../static/local-js/modules/kometa/_updateRollup.js'
import { hideRunCommandSectionUntilValidated } from '../../../static/local-js/modules/kometa/_runCommandSection.js'

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

function installFixture () {
  document.body.innerHTML = `
    <div id="run-command-output"></div>
    <span id="kometa-install-path"></span>
  `
}

function resetState () {
  kometaState.kometaLocalCheckCompleted = false
  kometaState.kometaInstalled = false
  kometaState.kometaValidated = true
}

beforeEach(() => {
  getConfiguredKometaRootPosix.mockReset()
  getConfiguredKometaRootPosix.mockReturnValue('/opt/kometa')
  syncKometaSourceStatus.mockClear()
  appendKometaStatusLine.mockClear()
  syncUpdateButtonLabel.mockClear()
  syncKometaRollupBadge.mockClear()
  hideRunCommandSectionUntilValidated.mockClear()
  originalFetch = global.fetch
  resetState()
})

afterEach(() => {
  global.fetch = originalFetch
  document.body.innerHTML = ''
})

// ---------------------------------------------------------------------
// Short-circuit
// ---------------------------------------------------------------------

describe('probeKometaRoot -- no configured root', () => {
  it('resolves null when no Kometa root is configured', async () => {
    getConfiguredKometaRootPosix.mockReturnValue('')
    installFixture()
    const result = await probeKometaRoot()
    expect(result).toBeNull()
  })

  it('appends an error line when no root configured', async () => {
    getConfiguredKometaRootPosix.mockReturnValue('')
    installFixture()
    await probeKometaRoot()
    expect(appendKometaStatusLine).toHaveBeenCalledWith(expect.stringContaining('No Kometa install path'))
  })

  it('does NOT hit the network when no root configured', async () => {
    getConfiguredKometaRootPosix.mockReturnValue('')
    installFixture()
    global.fetch = vi.fn()
    await probeKometaRoot()
    expect(global.fetch).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------
// Request construction
// ---------------------------------------------------------------------

describe('probeKometaRoot -- request construction', () => {
  it('POSTs to /probe-kometa-root with JSON body', async () => {
    installFixture()
    mockFetchWith(okJson({ kometa_installed: true }))
    await probeKometaRoot()
    expect(global.fetch).toHaveBeenCalledWith('/probe-kometa-root', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    }))
  })

  it('body includes path and install_mode', async () => {
    installFixture()
    getConfiguredKometaRootPosix.mockReturnValue('/custom/path')
    mockFetchWith(okJson({ kometa_installed: true }))
    await probeKometaRoot()
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body).toEqual({
      path: '/custom/path',
      install_mode: 'managed'
    })
  })
})

// ---------------------------------------------------------------------
// Success path
// ---------------------------------------------------------------------

describe('probeKometaRoot -- success path state', () => {
  it('sets kometaLocalCheckCompleted + kometaInstalled from response', async () => {
    installFixture()
    mockFetchWith(okJson({ kometa_installed: 1 }))  // truthy non-boolean
    await probeKometaRoot()
    expect(kometaState.kometaLocalCheckCompleted).toBe(true)
    expect(kometaState.kometaInstalled).toBe(true)  // coerced via !!
  })

  it('forwards each log line via appendKometaStatusLine', async () => {
    installFixture()
    mockFetchWith(okJson({
      kometa_installed: true,
      log: ['line one', 'line two']
    }))
    await probeKometaRoot()
    expect(appendKometaStatusLine).toHaveBeenCalledWith('line one')
    expect(appendKometaStatusLine).toHaveBeenCalledWith('line two')
  })

  it('handles missing log field gracefully', async () => {
    installFixture()
    mockFetchWith(okJson({ kometa_installed: true }))
    await probeKometaRoot()
    // No log calls
    expect(appendKometaStatusLine).not.toHaveBeenCalled()
  })
})

describe('probeKometaRoot -- data attr caching on #run-command-output', () => {
  it('sets all four dataset attrs from server response when present', async () => {
    installFixture()
    mockFetchWith(okJson({
      kometa_installed: true,
      kometa_root: '/srv/kometa',
      kometa_root_display: 'C:\\srv\\kometa',
      venv_python: '/srv/kometa-venv/bin/python',
      venv_python_display: 'C:\\srv\\kometa-venv\\Scripts\\python.exe'
    }))
    await probeKometaRoot()
    const out = document.getElementById('run-command-output')
    expect(out.dataset.kometaRoot).toBe('C:\\srv\\kometa')
    expect(out.dataset.kometaRootPosix).toBe('/srv/kometa')
    expect(out.dataset.venvPython).toBe('C:\\srv\\kometa-venv\\Scripts\\python.exe')
    expect(out.dataset.venvPythonPosix).toBe('/srv/kometa-venv/bin/python')
  })

  it('falls back to configured display path when kometa_root_display missing', async () => {
    installFixture()
    mockFetchWith(okJson({ kometa_installed: true }))
    await probeKometaRoot()
    const out = document.getElementById('run-command-output')
    expect(out.dataset.kometaRoot).toBe('/opt/kometa')  // from getConfiguredKometaRootDisplay mock
  })

  it("falls back to 'python3' when no venv_python* fields", async () => {
    installFixture()
    mockFetchWith(okJson({ kometa_installed: true }))
    await probeKometaRoot()
    const out = document.getElementById('run-command-output')
    expect(out.dataset.venvPython).toBe('python3')
    // venvPythonPosix falls back to venvPythonDisplay when venv_python missing
    expect(out.dataset.venvPythonPosix).toBe('python3')
  })
})

describe('probeKometaRoot -- installPath element', () => {
  it("writes the display path to #kometa-install-path", async () => {
    installFixture()
    mockFetchWith(okJson({
      kometa_installed: true,
      kometa_root_display: 'C:\\srv\\kometa'
    }))
    await probeKometaRoot()
    expect(document.getElementById('kometa-install-path').textContent).toBe('C:\\srv\\kometa')
  })

  it('handles missing #kometa-install-path gracefully', async () => {
    document.body.innerHTML = '<div id="run-command-output"></div>'  // no install-path element
    mockFetchWith(okJson({ kometa_installed: true }))
    await expect(probeKometaRoot()).resolves.toBeDefined()
  })
})

describe('probeKometaRoot -- source status sync', () => {
  it('passes kometa_version to syncKometaSourceStatus', async () => {
    installFixture()
    mockFetchWith(okJson({
      kometa_installed: true,
      kometa_version: 'v2.0.0'
    }))
    await probeKometaRoot()
    expect(syncKometaSourceStatus).toHaveBeenCalledWith({ localVersion: 'v2.0.0' })
  })

  it("falls back to 'Unknown' when kometa_version missing", async () => {
    installFixture()
    mockFetchWith(okJson({ kometa_installed: true }))
    await probeKometaRoot()
    expect(syncKometaSourceStatus).toHaveBeenCalledWith({ localVersion: 'Unknown' })
  })
})

describe('probeKometaRoot -- installed state branching', () => {
  it("clears kometaValidated and hides run-command section when NOT installed", async () => {
    installFixture()
    kometaState.kometaValidated = true  // start validated
    mockFetchWith(okJson({ kometa_installed: false }))
    await probeKometaRoot()
    expect(kometaState.kometaValidated).toBe(false)
    expect(hideRunCommandSectionUntilValidated).toHaveBeenCalledTimes(1)
  })

  it('does NOT clear kometaValidated when Kometa IS installed', async () => {
    installFixture()
    kometaState.kometaValidated = true
    mockFetchWith(okJson({ kometa_installed: true }))
    await probeKometaRoot()
    expect(kometaState.kometaValidated).toBe(true)
    expect(hideRunCommandSectionUntilValidated).not.toHaveBeenCalled()
  })
})

describe('probeKometaRoot -- UI refresh calls', () => {
  it('calls syncUpdateButtonLabel + syncKometaRollupBadge on success', async () => {
    installFixture()
    mockFetchWith(okJson({ kometa_installed: true }))
    await probeKometaRoot()
    expect(syncUpdateButtonLabel).toHaveBeenCalledTimes(1)
    expect(syncKometaRollupBadge).toHaveBeenCalledTimes(1)
  })

  it('resolves to the server data on success', async () => {
    installFixture()
    const responseData = { kometa_installed: true, custom_field: 'preserved' }
    mockFetchWith(okJson(responseData))
    const result = await probeKometaRoot()
    expect(result).toEqual(responseData)
  })
})

// ---------------------------------------------------------------------
// Error path
// ---------------------------------------------------------------------

describe('probeKometaRoot -- error path', () => {
  it('handles non-ok response with server error message', async () => {
    installFixture()
    mockFetchWith(errJson(500, { error: 'kometa root missing' }))
    await probeKometaRoot()
    expect(appendKometaStatusLine).toHaveBeenCalledWith(expect.stringContaining('kometa root missing'))
    expect(kometaState.kometaInstalled).toBe(false)
    expect(kometaState.kometaValidated).toBe(false)
    expect(hideRunCommandSectionUntilValidated).toHaveBeenCalled()
  })

  it("uses fallback message when server omits data.error", async () => {
    installFixture()
    mockFetchWith(errJson(500, {}))
    await probeKometaRoot()
    expect(appendKometaStatusLine).toHaveBeenCalledWith(expect.stringContaining('Unable to probe'))
  })

  it("uses fallback message when server response isn't JSON parseable", async () => {
    installFixture()
    // Simulate non-JSON body via json() rejection
    global.fetch = vi.fn(() => Promise.resolve({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error('not json'))
    }))
    await probeKometaRoot()
    expect(appendKometaStatusLine).toHaveBeenCalledWith(expect.stringContaining('Unable to probe'))
  })

  it('handles network reject (fetch itself rejects)', async () => {
    installFixture()
    global.fetch = vi.fn(() => Promise.reject(new Error('network fried')))
    const result = await probeKometaRoot()
    expect(result).toBeNull()
    expect(appendKometaStatusLine).toHaveBeenCalledWith(expect.stringContaining('Unable to probe'))
    expect(kometaState.kometaInstalled).toBe(false)
  })

  it('syncs source status with Unknown on error', async () => {
    installFixture()
    mockFetchWith(errJson(500, {}))
    await probeKometaRoot()
    expect(syncKometaSourceStatus).toHaveBeenCalledWith({ localVersion: 'Unknown' })
  })

  it('still refreshes button label + rollup badge on error', async () => {
    installFixture()
    mockFetchWith(errJson(500, {}))
    await probeKometaRoot()
    expect(syncUpdateButtonLabel).toHaveBeenCalledTimes(1)
    expect(syncKometaRollupBadge).toHaveBeenCalledTimes(1)
  })

  it("marks localCheckCompleted true even on error (so UI knows we tried)", async () => {
    installFixture()
    mockFetchWith(errJson(500, {}))
    await probeKometaRoot()
    expect(kometaState.kometaLocalCheckCompleted).toBe(true)
  })
})
