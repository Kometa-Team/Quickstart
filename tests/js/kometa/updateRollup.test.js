// Tests for static/local-js/modules/kometa/_updateRollup.js
//
// Six exported functions:
//
//   getKometaRollupStatus     -- PURE, 8-branch state machine
//   syncKometaRollupBadge     -- writes to DOM
//   syncKometaUpdateAttention -- toggles class on accordion header
//   getUpdateButtonLabel      -- PURE-ish (reads DOM for force toggle)
//   syncUpdateButtonLabel     -- writes button innerHTML
//   invalidateKometaUpdateStatus -- resets state + refreshes UI
//
// COVERAGE STRATEGY:
//
//   getKometaRollupStatus: one test per branch (8 branches).
//   getUpdateButtonLabel:  one test per label (6 labels for managed +
//                          2 for 'existing' mode).
//   syncKometaRollupBadge / syncUpdateButtonLabel: DOM assertions
//                          after calling with representative states.
//   syncKometaUpdateAttention: 4 branches
//                          (element missing / collapsed+available /
//                           expanded+available / collapsed+unavailable).
//   invalidateKometaUpdateStatus: state fields reset, box hidden,
//                                 collaborators called.
//
// Collaborators (_kometaBranch.js syncKometaSourceStatus,
// _runtime.js getConfiguredKometaInstallMode) are mocked with vi.mock
// so this module's behavior is tested in isolation.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Mock collaborators BEFORE importing _updateRollup.js. vi.mock is
// hoisted so the position of these calls doesn't matter, but keeping
// them near the imports for readability.
vi.mock('../../../static/local-js/modules/kometa/_kometaBranch.js', () => ({
  syncKometaSourceStatus: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_runtime.js', () => ({
  getConfiguredKometaInstallMode: vi.fn(() => 'managed')  // default: managed
}))

import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import {
  getKometaRollupStatus,
  syncKometaRollupBadge,
  syncKometaUpdateAttention,
  getUpdateButtonLabel,
  syncUpdateButtonLabel,
  invalidateKometaUpdateStatus
} from '../../../static/local-js/modules/kometa/_updateRollup.js'
import { syncKometaSourceStatus } from '../../../static/local-js/modules/kometa/_kometaBranch.js'
import { getConfiguredKometaInstallMode } from '../../../static/local-js/modules/kometa/_runtime.js'

// ---------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------

/**
 * Reset every kometaState field this module reads/writes to sensible
 * defaults so tests don't cross-contaminate.
 */
function resetState () {
  kometaState.kometaUpdating = false
  kometaState.kometaValidationInProgress = false
  kometaState.kometaLocalCheckCompleted = true
  kometaState.kometaInstalled = true
  kometaState.kometaValidated = true
  kometaState.kometaUpdateCheckCompleted = true
  kometaState.kometaUpdateCheckSkipped = false
  kometaState.kometaUpdateAvailable = false
  kometaState.kometaRemoteVersionStatus = ''
  kometaState.kometaRemoteVersionChecked = false
  kometaState.kometaRemoteVersionSkipped = false
}

function installRollupBadge () {
  document.body.innerHTML = '<span id="kometa-update-rollup-badge"></span>'
  return document.getElementById('kometa-update-rollup-badge')
}

function installAccordion (opts = {}) {
  const { collapsed = true } = opts
  document.body.innerHTML = `
    <div id="kometa-actions-heading" class=""></div>
    <button id="kometa-actions-toggle" class="${collapsed ? 'collapsed' : ''}"></button>
    <span id="kometa-update-rollup-badge"></span>
  `
}

function installUpdateButton () {
  document.body.innerHTML = `
    <button id="update-kometa-btn"></button>
    <input type="checkbox" id="force-kometa-update">
  `
  return document.getElementById('update-kometa-btn')
}

function installInvalidateFixture () {
  document.body.innerHTML = `
    <div id="kometa-update-box"></div>
    <button id="update-kometa-btn"></button>
    <input type="checkbox" id="force-kometa-update">
    <span id="kometa-update-rollup-badge"></span>
  `
}

beforeEach(() => {
  syncKometaSourceStatus.mockClear()
  getConfiguredKometaInstallMode.mockClear()
  getConfiguredKometaInstallMode.mockReturnValue('managed')
  resetState()
})

afterEach(() => {
  document.body.innerHTML = ''
})

// ---------------------------------------------------------------------
// getKometaRollupStatus (pure, 8 branches)
// ---------------------------------------------------------------------

describe('getKometaRollupStatus -- state machine', () => {
  it("returns 'Updating...' when kometaUpdating", () => {
    kometaState.kometaUpdating = true
    expect(getKometaRollupStatus()).toEqual({ state: 'unknown', label: 'Updating...' })
  })

  it("returns 'Checking...' when kometaValidationInProgress", () => {
    kometaState.kometaValidationInProgress = true
    expect(getKometaRollupStatus()).toEqual({ state: 'unknown', label: 'Checking...' })
  })

  it("returns 'Not checked' when localCheck not completed", () => {
    kometaState.kometaLocalCheckCompleted = false
    expect(getKometaRollupStatus()).toEqual({ state: 'unknown', label: 'Not checked' })
  })

  it("returns 'Install needed' when !kometaInstalled", () => {
    kometaState.kometaInstalled = false
    expect(getKometaRollupStatus()).toEqual({ state: 'error', label: 'Install needed' })
  })

  it("returns 'Prepared' (ok) when validated but no update check", () => {
    kometaState.kometaUpdateCheckCompleted = false
    kometaState.kometaValidated = true
    expect(getKometaRollupStatus()).toEqual({ state: 'ok', label: 'Prepared' })
  })

  it("returns 'Prepare needed' (warn) when !validated and no update check", () => {
    kometaState.kometaUpdateCheckCompleted = false
    kometaState.kometaValidated = false
    expect(getKometaRollupStatus()).toEqual({ state: 'warn', label: 'Prepare needed' })
  })

  it("returns 'Skipped while running' when update check was skipped", () => {
    kometaState.kometaUpdateCheckSkipped = true
    expect(getKometaRollupStatus()).toEqual({ state: 'unknown', label: 'Skipped while running' })
  })

  it("returns 'Update available' (warn) when update is available", () => {
    kometaState.kometaUpdateAvailable = true
    expect(getKometaRollupStatus()).toEqual({ state: 'warn', label: 'Update available' })
  })

  it("returns 'Up to date' (ok) as the fallback", () => {
    // All flags in the 'happy' state via resetState()
    expect(getKometaRollupStatus()).toEqual({ state: 'ok', label: 'Up to date' })
  })

  it('priority: kometaUpdating wins over everything else', () => {
    kometaState.kometaUpdating = true
    kometaState.kometaValidationInProgress = true
    kometaState.kometaUpdateAvailable = true
    expect(getKometaRollupStatus().label).toBe('Updating...')
  })
})

// ---------------------------------------------------------------------
// syncKometaRollupBadge (DOM writer)
// ---------------------------------------------------------------------

describe('syncKometaRollupBadge', () => {
  it('is a no-op when the badge element is missing', () => {
    expect(() => syncKometaRollupBadge()).not.toThrow()
  })

  it("writes label + ok class for the 'up to date' state", () => {
    const badge = installRollupBadge()
    syncKometaRollupBadge()
    expect(badge.textContent).toBe('Up to date')
    expect(badge.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it("writes label + warn class for the 'update available' state", () => {
    const badge = installRollupBadge()
    kometaState.kometaUpdateAvailable = true
    syncKometaRollupBadge()
    expect(badge.textContent).toBe('Update available')
    expect(badge.classList.contains('qs-validation-rollup-badge--warn')).toBe(true)
  })

  it("writes label + error class for the 'install needed' state", () => {
    const badge = installRollupBadge()
    kometaState.kometaInstalled = false
    syncKometaRollupBadge()
    expect(badge.textContent).toBe('Install needed')
    expect(badge.classList.contains('qs-validation-rollup-badge--error')).toBe(true)
  })

  it('removes prior state class before adding new one', () => {
    const badge = installRollupBadge()
    badge.classList.add('qs-validation-rollup-badge--error')
    syncKometaRollupBadge()  // will resolve to 'ok' via defaults
    expect(badge.classList.contains('qs-validation-rollup-badge--error')).toBe(false)
    expect(badge.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// syncKometaUpdateAttention
// ---------------------------------------------------------------------

describe('syncKometaUpdateAttention', () => {
  it('is a no-op when accordion elements are missing (still calls rollup)', () => {
    const badge = installRollupBadge()
    kometaState.kometaUpdateAvailable = true
    syncKometaUpdateAttention()
    // Badge should still get refreshed even without accordion
    expect(badge.textContent).toBe('Update available')
  })

  it('adds attention class when update is available AND accordion is collapsed', () => {
    installAccordion({ collapsed: true })
    kometaState.kometaUpdateAvailable = true
    syncKometaUpdateAttention()
    expect(document.getElementById('kometa-actions-heading').classList.contains('kometa-update-attention')).toBe(true)
    expect(document.getElementById('kometa-actions-toggle').classList.contains('kometa-update-attention')).toBe(true)
  })

  it('does NOT add attention class when accordion is expanded', () => {
    installAccordion({ collapsed: false })
    kometaState.kometaUpdateAvailable = true
    syncKometaUpdateAttention()
    expect(document.getElementById('kometa-actions-heading').classList.contains('kometa-update-attention')).toBe(false)
    expect(document.getElementById('kometa-actions-toggle').classList.contains('kometa-update-attention')).toBe(false)
  })

  it('does NOT add attention class when no update is available (even if collapsed)', () => {
    installAccordion({ collapsed: true })
    kometaState.kometaUpdateAvailable = false
    syncKometaUpdateAttention()
    expect(document.getElementById('kometa-actions-heading').classList.contains('kometa-update-attention')).toBe(false)
  })

  it('REMOVES a stale attention class when conditions no longer warrant it', () => {
    installAccordion({ collapsed: false })
    // Pre-set attention (simulates a prior render when it was warranted)
    document.getElementById('kometa-actions-heading').classList.add('kometa-update-attention')
    document.getElementById('kometa-actions-toggle').classList.add('kometa-update-attention')
    kometaState.kometaUpdateAvailable = false
    syncKometaUpdateAttention()
    expect(document.getElementById('kometa-actions-heading').classList.contains('kometa-update-attention')).toBe(false)
  })
})

// ---------------------------------------------------------------------
// getUpdateButtonLabel (branches per install mode + force + state)
// ---------------------------------------------------------------------

describe("getUpdateButtonLabel -- 'existing' install mode", () => {
  beforeEach(() => {
    getConfiguredKometaInstallMode.mockReturnValue('existing')
    document.body.innerHTML = ''  // no force toggle needed in this mode
  })

  it("returns 'Check Existing Status' when no check has completed", () => {
    kometaState.kometaUpdateCheckCompleted = false
    expect(getUpdateButtonLabel()).toContain('Check Existing Status')
  })

  it("returns 'Recheck Existing Status' when a check has completed", () => {
    kometaState.kometaUpdateCheckCompleted = true
    expect(getUpdateButtonLabel()).toContain('Recheck Existing Status')
  })

  it("prefixes the bi-arrow-clockwise icon", () => {
    expect(getUpdateButtonLabel()).toContain('bi-arrow-clockwise')
  })
})

describe('getUpdateButtonLabel -- managed install mode', () => {
  beforeEach(() => {
    // Ensure the force toggle exists but is unchecked by default
    document.body.innerHTML = '<input type="checkbox" id="force-kometa-update">'
    document.getElementById('force-kometa-update').checked = false
  })

  it("returns 'Install Kometa' when not installed and force is off", () => {
    kometaState.kometaInstalled = false
    expect(getUpdateButtonLabel()).toContain('Install Kometa')
  })

  it("returns 'Force Install Kometa' when not installed and force is on", () => {
    kometaState.kometaInstalled = false
    document.getElementById('force-kometa-update').checked = true
    expect(getUpdateButtonLabel()).toContain('Force Install Kometa')
  })

  it("returns 'Force Update Kometa' when installed and force is on", () => {
    document.getElementById('force-kometa-update').checked = true
    expect(getUpdateButtonLabel()).toContain('Force Update Kometa')
  })

  it("returns 'Update Available' when installed, no force, update available", () => {
    kometaState.kometaUpdateAvailable = true
    expect(getUpdateButtonLabel()).toContain('Update Available')
  })

  it("returns 'Up to date' when installed, no force, no update, check completed", () => {
    kometaState.kometaUpdateCheckCompleted = true
    kometaState.kometaUpdateAvailable = false
    expect(getUpdateButtonLabel()).toContain('Up to date')
  })

  it("returns 'Check for Kometa Updates' when installed but no check has run", () => {
    kometaState.kometaUpdateCheckCompleted = false
    expect(getUpdateButtonLabel()).toContain('Check for Kometa Updates')
  })
})

// ---------------------------------------------------------------------
// syncUpdateButtonLabel
// ---------------------------------------------------------------------

describe('syncUpdateButtonLabel', () => {
  it('is a no-op when the button is missing (still refreshes attention/rollup)', () => {
    installRollupBadge()  // ensure rollup can be refreshed
    expect(() => syncUpdateButtonLabel()).not.toThrow()
  })

  it("writes the current label to the button's innerHTML", () => {
    const btn = installUpdateButton()
    // Add a rollup badge too so syncKometaUpdateAttention has something to refresh
    const rollup = document.createElement('span')
    rollup.id = 'kometa-update-rollup-badge'
    document.body.appendChild(rollup)
    syncUpdateButtonLabel()
    expect(btn.innerHTML).toContain('Up to date')
    expect(btn.innerHTML).toContain('bi-arrow-clockwise')
  })
})

// ---------------------------------------------------------------------
// invalidateKometaUpdateStatus
// ---------------------------------------------------------------------

describe('invalidateKometaUpdateStatus', () => {
  it('resets every kometaState update field to defaults', () => {
    installInvalidateFixture()
    // Pre-set every field to 'dirty' values
    kometaState.kometaUpdateAvailable = true
    kometaState.kometaUpdateCheckCompleted = true
    kometaState.kometaUpdateCheckSkipped = true
    kometaState.kometaRemoteVersionStatus = 'v1.2.3'
    kometaState.kometaRemoteVersionChecked = true
    kometaState.kometaRemoteVersionSkipped = true

    invalidateKometaUpdateStatus()

    expect(kometaState.kometaUpdateAvailable).toBe(false)
    expect(kometaState.kometaUpdateCheckCompleted).toBe(false)
    expect(kometaState.kometaUpdateCheckSkipped).toBe(false)
    expect(kometaState.kometaRemoteVersionStatus).toBe('')
    expect(kometaState.kometaRemoteVersionChecked).toBe(false)
    expect(kometaState.kometaRemoteVersionSkipped).toBe(false)
  })

  it('hides the update box', () => {
    installInvalidateFixture()
    const box = document.getElementById('kometa-update-box')
    expect(box.classList.contains('d-none')).toBe(false)  // sanity
    invalidateKometaUpdateStatus()
    expect(box.classList.contains('d-none')).toBe(true)
  })

  it('calls syncKometaSourceStatus and refreshes the rollup badge', () => {
    installInvalidateFixture()
    invalidateKometaUpdateStatus()
    expect(syncKometaSourceStatus).toHaveBeenCalledTimes(1)
    // After invalidation, kometaUpdateCheckCompleted is false and
    // kometaValidated stays true (independent state), so the rollup
    // resolves to 'Prepared' (state=ok). We assert on the badge to
    // prove the refresh happened -- no need to mock our own module's
    // internal exports.
    const badge = document.getElementById('kometa-update-rollup-badge')
    expect(badge.textContent).toBe('Prepared')
  })

  it("preserves kometaLocalCheckCompleted and kometaValidated (they're independent)", () => {
    installInvalidateFixture()
    kometaState.kometaLocalCheckCompleted = true
    kometaState.kometaValidated = true
    invalidateKometaUpdateStatus()
    expect(kometaState.kometaLocalCheckCompleted).toBe(true)
    expect(kometaState.kometaValidated).toBe(true)
  })
})
