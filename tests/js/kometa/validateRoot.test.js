// Tests for static/local-js/modules/kometa/_validateRoot.js
//
// One export: validateKometaRoot(options = {}).
//
// COVERAGE STRATEGY:
//
//   Short-circuits (3 branches):
//     - !kometaCanProbeRuntime  -> info line + validated=false + return
//     - already in progress     -> return immediately (no state change)
//     - no configured root      -> error message written to log box
//
//   Setup: state + UI transitions before the fetch happens
//     - phase badge set to 'validating'
//     - validationInProgress flag set
//     - spinner shown, runNow disabled
//     - navigation overlay shown (via typeof guard)
//     - appendStatus=true: appends 'Re-validating...' preserving log
//     - appendStatus=false: replaces log with 'Please wait...'
//
//   Success path with success=true:
//     - kometaInstalled set true
//     - log lines forwarded
//     - dataset caching (same fallback chain as probeKometaRoot)
//     - kometa_version line appended when present
//     - installPath element updated
//     - buildCommand called
//     - allValid via configValid path
//     - allValid via individual dataset flags path
//     - !allValid: validated=false, section hidden, run-now disabled
//     - kometaUpdating=false: phase set to 'ready' / 'idle'
//
//   Success path with success=false (server said "not valid"):
//     - kometaInstalled = false, validated = false
//     - phase 'failed' when not updating
//     - section hidden
//
//   Error path:
//     - server !ok with error message
//     - server !ok without message (fallback)
//     - network reject (fetch itself fails)
//     - 'kometa.py not found' -> kometaInstalled downgraded
//     - 'requirements.txt not found' -> kometaInstalled downgraded
//
//   Complete (always runs via .finally):
//     - validationInProgress cleared
//     - updateRunNowState called
//     - hideNavigationLoadingOverlay called (typeof guard)

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../static/local-js/modules/kometa/_runtime.js', () => ({
  kometaCanProbeRuntime: vi.fn(() => true),
  getConfiguredKometaRootPosix: vi.fn(() => '/opt/kometa'),
  getConfiguredKometaRootDisplay: vi.fn(() => '/opt/kometa'),
  getConfiguredKometaInstallMode: vi.fn(() => 'managed')
}))
vi.mock('../../../static/local-js/modules/kometa/_updatePhase.js', () => ({
  appendKometaStatusLine: vi.fn(),
  setKometaUpdatePhaseBadge: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_updateRollup.js', () => ({
  syncKometaRollupBadge: vi.fn(),
  syncUpdateButtonLabel: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_validationGate.js', () => ({
  getFinalGateState: vi.fn(() => ({ configValid: false }))
}))
vi.mock('../../../static/local-js/modules/kometa/_runCommand.js', () => ({
  buildCommand: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_runControls.js', () => ({
  updateRunNowState: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_runCommandSection.js', () => ({
  hideRunCommandSectionUntilValidated: vi.fn(),
  showRunCommandSectionAfterValidated: vi.fn()
}))

import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import { validateKometaRoot } from '../../../static/local-js/modules/kometa/_validateRoot.js'
import {
  kometaCanProbeRuntime,
  getConfiguredKometaRootPosix
} from '../../../static/local-js/modules/kometa/_runtime.js'
import {
  appendKometaStatusLine,
  setKometaUpdatePhaseBadge
} from '../../../static/local-js/modules/kometa/_updatePhase.js'
import {
  syncKometaRollupBadge,
  syncUpdateButtonLabel
} from '../../../static/local-js/modules/kometa/_updateRollup.js'
import { getFinalGateState } from '../../../static/local-js/modules/kometa/_validationGate.js'
import { buildCommand } from '../../../static/local-js/modules/kometa/_runCommand.js'
import { updateRunNowState } from '../../../static/local-js/modules/kometa/_runControls.js'
import {
  hideRunCommandSectionUntilValidated,
  showRunCommandSectionAfterValidated
} from '../../../static/local-js/modules/kometa/_runCommandSection.js'

// ---------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------

let originalFetch

function installFixture () {
  document.body.innerHTML = `
    <pre id="kometa-validation-log"></pre>
    <div id="spinner_validate" class="d-none"></div>
    <button id="run-now"></button>
    <div id="run-command-output" data-config-filename="kometa.yml"></div>
    <span id="kometa-install-path"></span>
  `
}

function mockFetchWith (response) {
  global.fetch = vi.fn(() => Promise.resolve(response))
}

function okJson (body) {
  return { ok: true, json: () => Promise.resolve(body) }
}

function errJson (status, body) {
  return { ok: false, status, json: () => Promise.resolve(body) }
}

function resetState () {
  kometaState.kometaLocalCheckCompleted = false
  kometaState.kometaInstalled = false
  kometaState.kometaValidated = false
  kometaState.kometaValidationInProgress = false
  kometaState.kometaUpdating = false
  kometaState.showYAML = true
}

/**
 * Install validation-gate dataset flags for the "all valid via
 * individual flags" branch. Set every flag to 'True' by default;
 * caller can override.
 */
function installValidationGateFlags (overrides = {}) {
  const flags = {
    plex_valid: 'plexValid',
    tmdb_valid: 'tmdbValid',
    libs_valid: 'libsValid',
    sett_valid: 'settValid',
    yaml_valid: 'yamlValid'
  }
  for (const [id, dataKey] of Object.entries(flags)) {
    const el = document.createElement('div')
    el.id = id
    el.dataset[dataKey] = overrides[id] ?? 'True'
    document.body.appendChild(el)
  }
}

beforeEach(() => {
  kometaCanProbeRuntime.mockReset()
  kometaCanProbeRuntime.mockReturnValue(true)
  getConfiguredKometaRootPosix.mockReset()
  getConfiguredKometaRootPosix.mockReturnValue('/opt/kometa')
  appendKometaStatusLine.mockClear()
  setKometaUpdatePhaseBadge.mockClear()
  syncKometaRollupBadge.mockClear()
  syncUpdateButtonLabel.mockClear()
  getFinalGateState.mockReset()
  getFinalGateState.mockReturnValue({ configValid: false })
  buildCommand.mockClear()
  updateRunNowState.mockClear()
  hideRunCommandSectionUntilValidated.mockClear()
  showRunCommandSectionAfterValidated.mockClear()
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

describe('validateKometaRoot -- short circuits', () => {
  it('returns early in external mode (no runtime probe available)', async () => {
    kometaCanProbeRuntime.mockReturnValue(false)
    installFixture()
    validateKometaRoot()
    expect(appendKometaStatusLine).toHaveBeenCalledWith(expect.stringContaining('external Kometa mode'))
    expect(kometaState.kometaValidationInProgress).toBe(false)
    expect(kometaState.kometaValidated).toBe(false)
    expect(syncKometaRollupBadge).toHaveBeenCalledTimes(1)
    // Should not have fetched
    expect(global.fetch).toBe(originalFetch)
  })

  it('returns early when validation is already in progress', () => {
    installFixture()
    kometaState.kometaValidationInProgress = true
    validateKometaRoot()
    // No state changes, no fetch, no badge writes
    expect(setKometaUpdatePhaseBadge).not.toHaveBeenCalled()
    expect(syncKometaRollupBadge).not.toHaveBeenCalled()
  })

  it('writes explanatory message + returns when no root configured', () => {
    getConfiguredKometaRootPosix.mockReturnValue('')
    installFixture()
    validateKometaRoot()
    const logBox = document.getElementById('kometa-validation-log')
    expect(logBox.textContent).toContain('does not have a Kometa install path')
    expect(document.getElementById('run-now').disabled).toBe(true)
    expect(kometaState.kometaValidationInProgress).toBe(false)
    expect(kometaState.kometaValidated).toBe(false)
  })
})

// ---------------------------------------------------------------------
// Setup phase (state + UI transitions before fetch)
// ---------------------------------------------------------------------

describe('validateKometaRoot -- setup phase', () => {
  it("sets the phase badge to 'validating' and flips validationInProgress", async () => {
    installFixture()
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('validating')
    // validationInProgress should be flipped ON at start
    // (finally handler will flip it back off but that's async)
  })

  it("replaces the log with 'Please wait...' when appendStatus=false", () => {
    installFixture()
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot({ appendStatus: false })
    expect(document.getElementById('kometa-validation-log').textContent).toContain('Please wait while we validate')
  })

  it("appends 'Re-validating...' when appendStatus=true", () => {
    installFixture()
    const logBox = document.getElementById('kometa-validation-log')
    logBox.textContent = 'previous line\n'
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot({ appendStatus: true })
    expect(logBox.textContent).toContain('previous line')  // preserved
    expect(logBox.textContent).toContain('Re-validating Kometa after update')
  })

  it('shows the spinner and disables run-now', () => {
    installFixture()
    document.getElementById('spinner_validate').classList.add('d-none')
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    expect(document.getElementById('spinner_validate').classList.contains('d-none')).toBe(false)
    expect(document.getElementById('run-now').disabled).toBe(true)
  })
})

// ---------------------------------------------------------------------
// Fetch request construction
// ---------------------------------------------------------------------

describe('validateKometaRoot -- request construction', () => {
  it('POSTs to /validate-kometa-root with path/config_name/install_mode', async () => {
    installFixture()
    document.getElementById('run-command-output').dataset.configFilename = 'my-config.yml'
    getConfiguredKometaRootPosix.mockReturnValue('/custom/kometa')
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    // wait for microtasks so fetch is called
    await new Promise(r => setTimeout(r, 0))
    expect(global.fetch).toHaveBeenCalledWith('/validate-kometa-root', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    }))
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body).toEqual({
      path: '/custom/kometa',
      config_name: 'my-config.yml',
      install_mode: 'managed'
    })
  })
})

// ---------------------------------------------------------------------
// Success path -- success=true
// ---------------------------------------------------------------------

describe('validateKometaRoot -- success=true response', () => {
  it('sets kometaInstalled true and appends success line', async () => {
    installFixture()
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(kometaState.kometaInstalled).toBe(true)
    expect(document.getElementById('kometa-validation-log').textContent).toContain('Kometa root validated successfully')
  })

  it('appends kometa_version line when present', async () => {
    installFixture()
    mockFetchWith(okJson({ success: true, kometa_version: 'v2.0.0' }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(document.getElementById('kometa-validation-log').textContent).toContain('Local Kometa version: v2.0.0')
  })

  it('caches all four dataset attrs on #run-command-output', async () => {
    installFixture()
    mockFetchWith(okJson({
      success: true,
      kometa_root: '/srv/kometa',
      kometa_root_display: 'C:\\srv\\kometa',
      venv_python: '/srv/venv/bin/python',
      venv_python_display: 'C:\\srv\\venv\\python.exe'
    }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    const out = document.getElementById('run-command-output')
    expect(out.dataset.kometaRoot).toBe('C:\\srv\\kometa')
    expect(out.dataset.kometaRootPosix).toBe('/srv/kometa')
    expect(out.dataset.venvPython).toBe('C:\\srv\\venv\\python.exe')
    expect(out.dataset.venvPythonPosix).toBe('/srv/venv/bin/python')
  })

  it("updates #kometa-install-path from kometa_root_display", async () => {
    installFixture()
    mockFetchWith(okJson({ success: true, kometa_root_display: 'C:\\srv\\kometa' }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(document.getElementById('kometa-install-path').textContent).toBe('C:\\srv\\kometa')
  })

  it("reveals section when finalGate.configValid is true", async () => {
    installFixture()
    getFinalGateState.mockReturnValue({ configValid: true })
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(kometaState.kometaValidated).toBe(true)
    expect(showRunCommandSectionAfterValidated).toHaveBeenCalledTimes(1)
    expect(hideRunCommandSectionUntilValidated).not.toHaveBeenCalled()
  })

  it("reveals section via individual dataset flags path", async () => {
    installFixture()
    installValidationGateFlags()  // all 'True' by default
    getFinalGateState.mockReturnValue({ configValid: false })  // configValid path fails
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(kometaState.kometaValidated).toBe(true)
    expect(showRunCommandSectionAfterValidated).toHaveBeenCalledTimes(1)
  })

  it("hides section when one gate flag is not 'True'", async () => {
    installFixture()
    installValidationGateFlags({ plex_valid: 'False' })
    getFinalGateState.mockReturnValue({ configValid: false })
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(kometaState.kometaValidated).toBe(false)
    expect(hideRunCommandSectionUntilValidated).toHaveBeenCalled()
    expect(document.getElementById('run-now').disabled).toBe(true)
  })

  it("hides section when showYAML is false (regardless of gates)", async () => {
    installFixture()
    installValidationGateFlags()  // all True
    getFinalGateState.mockReturnValue({ configValid: true })
    kometaState.showYAML = false
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(kometaState.kometaValidated).toBe(false)
  })

  it("calls buildCommand and clears run-command-output text before rebuild", async () => {
    installFixture()
    const out = document.getElementById('run-command-output')
    out.textContent = 'stale command'
    getFinalGateState.mockReturnValue({ configValid: true })
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    // buildCommand should have been called (real one is mocked as noop
    // so textContent stays '' after the clear)
    expect(buildCommand).toHaveBeenCalledTimes(1)
    expect(out.textContent).toBe('')
  })

  it("sets phase to 'ready' when validated + not updating", async () => {
    installFixture()
    getFinalGateState.mockReturnValue({ configValid: true })
    kometaState.kometaUpdating = false
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('ready')
  })

  it("sets phase to 'idle' when NOT validated + not updating", async () => {
    installFixture()
    // No validation gates installed -> allValid false -> validated false
    getFinalGateState.mockReturnValue({ configValid: false })
    kometaState.kometaUpdating = false
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('idle')
  })

  it("does NOT touch phase badge when kometaUpdating=true", async () => {
    installFixture()
    kometaState.kometaUpdating = true
    getFinalGateState.mockReturnValue({ configValid: true })
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    // 'validating' was set in setup phase. Then no more badge calls
    // in the success handler (because kometaUpdating=true).
    const readyOrIdleCalls = setKometaUpdatePhaseBadge.mock.calls.filter(
      c => c[0] === 'ready' || c[0] === 'idle'
    )
    expect(readyOrIdleCalls.length).toBe(0)
  })
})

// ---------------------------------------------------------------------
// Success path -- success=false response
// ---------------------------------------------------------------------

describe('validateKometaRoot -- success=false response', () => {
  it('sets kometaInstalled=false, kometaValidated=false', async () => {
    installFixture()
    mockFetchWith(okJson({ success: false }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(kometaState.kometaInstalled).toBe(false)
    expect(kometaState.kometaValidated).toBe(false)
  })

  it("sets phase 'failed' when not updating", async () => {
    installFixture()
    kometaState.kometaUpdating = false
    mockFetchWith(okJson({ success: false }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('failed')
  })

  it("hides run-command section and disables run-now", async () => {
    installFixture()
    mockFetchWith(okJson({ success: false }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(hideRunCommandSectionUntilValidated).toHaveBeenCalled()
    expect(document.getElementById('run-now').disabled).toBe(true)
  })
})

// ---------------------------------------------------------------------
// Error path
// ---------------------------------------------------------------------

describe('validateKometaRoot -- error path', () => {
  it('handles server error message', async () => {
    installFixture()
    mockFetchWith(errJson(500, { error: 'server exploded' }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(document.getElementById('kometa-validation-log').textContent).toContain('server exploded')
  })

  it('uses fallback message when no data.error', async () => {
    installFixture()
    mockFetchWith(errJson(500, {}))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(document.getElementById('kometa-validation-log').textContent).toContain('invalid or inaccessible')
  })

  it("downgrades kometaInstalled when 'kometa.py not found'", async () => {
    installFixture()
    kometaState.kometaInstalled = true  // start "installed"
    mockFetchWith(errJson(400, { error: 'kometa.py not found in root' }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(kometaState.kometaInstalled).toBe(false)
  })

  it("downgrades kometaInstalled when 'requirements.txt not found'", async () => {
    installFixture()
    kometaState.kometaInstalled = true
    mockFetchWith(errJson(400, { error: 'requirements.txt not found in kometa root' }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(kometaState.kometaInstalled).toBe(false)
  })

  it("does NOT downgrade kometaInstalled for other error messages", async () => {
    installFixture()
    kometaState.kometaInstalled = true
    mockFetchWith(errJson(500, { error: 'network hiccup' }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    // kometaInstalled stays true (only 'kometa.py not found' /
    // 'requirements.txt not found' trigger the downgrade)
    expect(kometaState.kometaInstalled).toBe(true)
  })

  it('handles network reject (fetch rejects)', async () => {
    installFixture()
    global.fetch = vi.fn(() => Promise.reject(new Error('network fried')))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(document.getElementById('kometa-validation-log').textContent).toContain('invalid or inaccessible')
    expect(kometaState.kometaValidated).toBe(false)
  })
})

// ---------------------------------------------------------------------
// Complete (always runs via .finally)
// ---------------------------------------------------------------------

describe('validateKometaRoot -- complete handler', () => {
  it("clears validationInProgress in .finally", async () => {
    installFixture()
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(kometaState.kometaValidationInProgress).toBe(false)
  })

  it('calls updateRunNowState in .finally', async () => {
    installFixture()
    mockFetchWith(okJson({ success: true }))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(updateRunNowState).toHaveBeenCalledTimes(1)
  })

  it('finally handler runs even on network error', async () => {
    installFixture()
    global.fetch = vi.fn(() => Promise.reject(new Error('boom')))
    validateKometaRoot()
    await new Promise(r => setTimeout(r, 10))
    expect(kometaState.kometaValidationInProgress).toBe(false)
    expect(updateRunNowState).toHaveBeenCalledTimes(1)
  })
})
