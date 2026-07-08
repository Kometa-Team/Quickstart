// Tests for static/local-js/modules/kometa/_kometaBranch.js
//
// Coverage strategy per exported function:
//
//   getKometaBranchOverride      -- <select> read, valid/invalid values
//   getQuickstartBranch          -- data-qs-branch attribute read
//   getAutoKometaBranch          -- resolves through getQuickstartBranch
//   getEffectiveKometaBranch     -- override wins over auto
//   getKometaVersionSourceUrlValue / getKometaZipSourceUrlValue
//                                -- URL building, pure
//   loadSavedKometaBranchOverride -- localStorage read + validation
//   saveKometaBranchOverride     -- localStorage write / remove
//   syncKometaSourceStatus       -- kometaState writes + DOM updates
//   syncKometaBranchRollupBadge  -- badge text + class swap
//   syncKometaBranchOverrideWarning -- visibility toggle
//
// localStorage is stubbed via a fresh in-memory Map so tests don't
// pollute the real one and don't depend on jsdom's mock semantics.
// We swap window.localStorage wholesale with a fake object that
// mirrors the getItem / setItem / removeItem surface backed by a Map,
// then restore the original after each test.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import {
  getKometaBranchOverride,
  getQuickstartBranch,
  getAutoKometaBranch,
  getEffectiveKometaBranch,
  getKometaVersionSourceUrlValue,
  getKometaZipSourceUrlValue,
  loadSavedKometaBranchOverride,
  saveKometaBranchOverride,
  syncKometaSourceStatus,
  syncKometaBranchRollupBadge,
  syncKometaBranchOverrideWarning,
  KOMETA_BRANCH_OVERRIDE_STORAGE_KEY
} from '../../../static/local-js/modules/kometa/_kometaBranch.js'

// ---------------------------------------------------------------------
// Fake localStorage
// ---------------------------------------------------------------------

let storage
let originalLocalStorage

/**
 * Build a fresh Map-backed fake localStorage and swap it in.
 * Optionally the getItem/setItem/removeItem functions can throw --
 * useful for testing the private-browsing / quota-exceeded paths.
 */
function installFakeLocalStorage ({ throwOnGet = false, throwOnSet = false } = {}) {
  storage = new Map()
  originalLocalStorage = window.localStorage
  const fake = {
    getItem: (k) => {
      if (throwOnGet) throw new Error('quota exceeded')
      return storage.get(k) ?? null
    },
    setItem: (k, v) => {
      if (throwOnSet) throw new Error('quota exceeded')
      storage.set(k, String(v))
    },
    removeItem: (k) => { storage.delete(k) },
    clear: () => storage.clear(),
    key: (i) => Array.from(storage.keys())[i] || null,
    get length () { return storage.size }
  }
  Object.defineProperty(window, 'localStorage', {
    value: fake,
    writable: true,
    configurable: true
  })
}

function restoreLocalStorage () {
  if (originalLocalStorage) {
    Object.defineProperty(window, 'localStorage', {
      value: originalLocalStorage,
      writable: true,
      configurable: true
    })
  }
}

// ---------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------

function installBranchDom (opts = {}) {
  const { qsBranch = 'master', overrideValue = '' } = opts
  document.body.innerHTML = `
    <button id="update-kometa-btn" data-qs-branch="${qsBranch}"></button>
    <select id="kometa-branch-override">
      <option value=""></option>
      <option value="master">master</option>
      <option value="develop">develop</option>
      <option value="nightly">nightly</option>
    </select>
    <span id="kometa-branch-selection"></span>
    <span id="kometa-effective-branch"></span>
    <span id="kometa-local-version-status"></span>
    <span id="kometa-remote-version-status"></span>
    <span id="kometa-version-source-url"></span>
    <span id="kometa-zip-source-url"></span>
    <span id="kometa-branch-rollup-badge"></span>
    <div id="kometa-branch-override-warning" class="d-none"></div>
  `
  const sel = document.getElementById('kometa-branch-override')
  sel.value = overrideValue
}

beforeEach(() => {
  installFakeLocalStorage()
})

afterEach(() => {
  document.body.innerHTML = ''
  restoreLocalStorage()
  vi.restoreAllMocks()
  // Reset state fields this module writes to
  kometaState.kometaLocalVersionStatus = 'Unknown'
  kometaState.kometaRemoteVersionStatus = ''
  kometaState.kometaRemoteVersionChecked = false
  kometaState.kometaRemoteVersionSkipped = false
})

// ---------------------------------------------------------------------
// getKometaBranchOverride
// ---------------------------------------------------------------------

describe('getKometaBranchOverride', () => {
  it("returns '' when the <select> element is missing", () => {
    document.body.innerHTML = ''
    expect(getKometaBranchOverride()).toBe('')
  })

  it("returns '' when the select's value is empty", () => {
    installBranchDom({ overrideValue: '' })
    expect(getKometaBranchOverride()).toBe('')
  })

  it('accepts the three valid branch names', () => {
    for (const branch of ['master', 'develop', 'nightly']) {
      installBranchDom({ overrideValue: branch })
      expect(getKometaBranchOverride()).toBe(branch)
    }
  })

  it('normalizes case and whitespace', () => {
    installBranchDom({ overrideValue: '' })
    document.getElementById('kometa-branch-override').value = '  MASTER  '
    // .value setter through the option list clamps to '' for unknown
    // values, so we set it via a raw <option> match instead:
    const sel = document.getElementById('kometa-branch-override')
    const opt = document.createElement('option')
    opt.value = '  MASTER  '
    sel.appendChild(opt)
    sel.value = '  MASTER  '
    expect(getKometaBranchOverride()).toBe('master')
  })

  it("returns '' for unknown / garbage values", () => {
    installBranchDom({ overrideValue: '' })
    const sel = document.getElementById('kometa-branch-override')
    const opt = document.createElement('option')
    opt.value = 'trunk'
    sel.appendChild(opt)
    sel.value = 'trunk'
    expect(getKometaBranchOverride()).toBe('')
  })
})

// ---------------------------------------------------------------------
// getQuickstartBranch
// ---------------------------------------------------------------------

describe('getQuickstartBranch', () => {
  it("defaults to 'master' when the button is missing", () => {
    document.body.innerHTML = ''
    expect(getQuickstartBranch()).toBe('master')
  })

  it('reads data-qs-branch attribute and normalizes case', () => {
    installBranchDom({ qsBranch: 'DEVELOP' })
    expect(getQuickstartBranch()).toBe('develop')
  })

  it("defaults to 'master' when the attribute is empty", () => {
    installBranchDom({ qsBranch: '' })
    expect(getQuickstartBranch()).toBe('master')
  })
})

// ---------------------------------------------------------------------
// getAutoKometaBranch + getEffectiveKometaBranch
// ---------------------------------------------------------------------

describe('getAutoKometaBranch', () => {
  it("returns 'master' when Quickstart is on master", () => {
    installBranchDom({ qsBranch: 'master' })
    expect(getAutoKometaBranch()).toBe('master')
  })

  it("returns 'nightly' when Quickstart is on anything else", () => {
    installBranchDom({ qsBranch: 'develop' })
    expect(getAutoKometaBranch()).toBe('nightly')
    installBranchDom({ qsBranch: 'feature/xyz' })
    expect(getAutoKometaBranch()).toBe('nightly')
  })
})

describe('getEffectiveKometaBranch', () => {
  it('returns the override when set', () => {
    installBranchDom({ qsBranch: 'master', overrideValue: 'develop' })
    expect(getEffectiveKometaBranch()).toBe('develop')
  })

  it('falls back to the auto-resolved branch when no override', () => {
    installBranchDom({ qsBranch: 'master', overrideValue: '' })
    expect(getEffectiveKometaBranch()).toBe('master')
    installBranchDom({ qsBranch: 'develop', overrideValue: '' })
    expect(getEffectiveKometaBranch()).toBe('nightly')
  })

  it('override wins over auto even when auto would agree', () => {
    // Not a behavior difference, but proves the override is the sole
    // source of truth when set.
    installBranchDom({ qsBranch: 'master', overrideValue: 'master' })
    expect(getEffectiveKometaBranch()).toBe('master')
  })
})

// ---------------------------------------------------------------------
// URL builders (pure)
// ---------------------------------------------------------------------

describe('getKometaVersionSourceUrlValue', () => {
  it('builds the raw.githubusercontent URL for the given branch', () => {
    expect(getKometaVersionSourceUrlValue('master')).toBe(
      'https://raw.githubusercontent.com/Kometa-Team/Kometa/master/VERSION'
    )
    expect(getKometaVersionSourceUrlValue('develop')).toBe(
      'https://raw.githubusercontent.com/Kometa-Team/Kometa/develop/VERSION'
    )
  })
})

describe('getKometaZipSourceUrlValue', () => {
  it('builds the codeload ZIP URL for the given branch', () => {
    expect(getKometaZipSourceUrlValue('nightly')).toBe(
      'https://codeload.github.com/kometa-team/Kometa/zip/refs/heads/nightly'
    )
  })
})

// ---------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------

describe('loadSavedKometaBranchOverride', () => {
  it('restores a valid branch from localStorage', () => {
    installBranchDom({ overrideValue: '' })
    storage.set(KOMETA_BRANCH_OVERRIDE_STORAGE_KEY, 'develop')
    loadSavedKometaBranchOverride()
    expect(document.getElementById('kometa-branch-override').value).toBe('develop')
  })

  it('coerces an invalid stored value to empty (auto)', () => {
    installBranchDom({ overrideValue: 'develop' })
    storage.set(KOMETA_BRANCH_OVERRIDE_STORAGE_KEY, 'trunk-xyz')
    loadSavedKometaBranchOverride()
    expect(document.getElementById('kometa-branch-override').value).toBe('')
  })

  it('is a no-op when the <select> is missing', () => {
    document.body.innerHTML = ''
    expect(() => loadSavedKometaBranchOverride()).not.toThrow()
  })

  it('handles localStorage throwing (private browsing / quota)', () => {
    installBranchDom({ overrideValue: 'develop' })
    installFakeLocalStorage({ throwOnGet: true })  // re-swap with throwing fake
    loadSavedKometaBranchOverride()
    // Should coerce to '' rather than crash
    expect(document.getElementById('kometa-branch-override').value).toBe('')
  })
})

describe('saveKometaBranchOverride', () => {
  it('writes a valid selection to localStorage', () => {
    installBranchDom({ overrideValue: 'nightly' })
    saveKometaBranchOverride()
    expect(storage.get(KOMETA_BRANCH_OVERRIDE_STORAGE_KEY)).toBe('nightly')
  })

  it('removes the key when the selection is empty (auto)', () => {
    installBranchDom({ overrideValue: '' })
    storage.set(KOMETA_BRANCH_OVERRIDE_STORAGE_KEY, 'stale-value')
    saveKometaBranchOverride()
    expect(storage.has(KOMETA_BRANCH_OVERRIDE_STORAGE_KEY)).toBe(false)
  })

  it('silently ignores localStorage errors', () => {
    installBranchDom({ overrideValue: 'master' })
    installFakeLocalStorage({ throwOnSet: true })  // re-swap with throwing fake
    expect(() => saveKometaBranchOverride()).not.toThrow()
  })
})

// ---------------------------------------------------------------------
// syncKometaSourceStatus
// ---------------------------------------------------------------------

describe('syncKometaSourceStatus', () => {
  it("writes options fields to kometaState (skipping unset ones)", () => {
    installBranchDom()
    syncKometaSourceStatus({ localVersion: 'v1.2.3' })
    expect(kometaState.kometaLocalVersionStatus).toBe('v1.2.3')
    // Others unchanged
    expect(kometaState.kometaRemoteVersionStatus).toBe('')
    expect(kometaState.kometaRemoteVersionChecked).toBe(false)
    expect(kometaState.kometaRemoteVersionSkipped).toBe(false)
  })

  it('uses hasOwnProperty check (empty-string option clears field)', () => {
    installBranchDom()
    kometaState.kometaLocalVersionStatus = 'v1.2.3'  // pre-set
    // Explicit '' should reset to 'Unknown' via the `|| 'Unknown'`
    syncKometaSourceStatus({ localVersion: '' })
    expect(kometaState.kometaLocalVersionStatus).toBe('Unknown')
  })

  it("renders selection label 'Auto' when no override", () => {
    installBranchDom({ overrideValue: '' })
    syncKometaSourceStatus()
    expect(document.getElementById('kometa-branch-selection').textContent).toBe('Auto')
  })

  it("renders selection label 'Override (nightly)' when override set", () => {
    installBranchDom({ overrideValue: 'nightly' })
    syncKometaSourceStatus()
    expect(document.getElementById('kometa-branch-selection').textContent).toBe('Override (nightly)')
  })

  it("renders effective branch computed from override", () => {
    installBranchDom({ qsBranch: 'master', overrideValue: 'develop' })
    syncKometaSourceStatus()
    expect(document.getElementById('kometa-effective-branch').textContent).toBe('develop')
  })

  it("shows 'Not checked' remote status when checked=false and not skipped", () => {
    installBranchDom()
    syncKometaSourceStatus({ remoteVersion: 'v1.2.4', checked: false })
    expect(document.getElementById('kometa-remote-version-status').textContent).toBe('Not checked')
  })

  it("shows 'Skipped while running' remote status when skipped=true", () => {
    installBranchDom()
    syncKometaSourceStatus({ remoteVersion: 'v1.2.4', checked: true, skipped: true })
    expect(document.getElementById('kometa-remote-version-status').textContent).toBe('Skipped while running')
  })

  it("shows the remote version verbatim when checked=true", () => {
    installBranchDom()
    syncKometaSourceStatus({ remoteVersion: 'v1.2.4', checked: true, skipped: false })
    expect(document.getElementById('kometa-remote-version-status').textContent).toBe('v1.2.4')
  })

  it("writes the effective-branch VERSION and ZIP URLs", () => {
    installBranchDom({ qsBranch: 'master', overrideValue: 'develop' })
    syncKometaSourceStatus()
    expect(document.getElementById('kometa-version-source-url').textContent).toContain('/develop/VERSION')
    expect(document.getElementById('kometa-zip-source-url').textContent).toContain('/heads/develop')
  })

  it('also refreshes the branch rollup badge (side effect)', () => {
    installBranchDom({ qsBranch: 'master', overrideValue: 'nightly' })
    syncKometaSourceStatus()
    const badge = document.getElementById('kometa-branch-rollup-badge')
    expect(badge.textContent).toBe('NIGHTLY')
    expect(badge.classList.contains('text-bg-warning')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// syncKometaBranchRollupBadge
// ---------------------------------------------------------------------

describe('syncKometaBranchRollupBadge', () => {
  it("shows 'AUTO' with secondary style when no override", () => {
    installBranchDom({ overrideValue: '' })
    syncKometaBranchRollupBadge()
    const badge = document.getElementById('kometa-branch-rollup-badge')
    expect(badge.textContent).toBe('AUTO')
    expect(badge.classList.contains('text-bg-secondary')).toBe(true)
    expect(badge.classList.contains('text-bg-warning')).toBe(false)
  })

  it("shows uppercase override name with warning style when set", () => {
    installBranchDom({ overrideValue: 'develop' })
    syncKometaBranchRollupBadge()
    const badge = document.getElementById('kometa-branch-rollup-badge')
    expect(badge.textContent).toBe('DEVELOP')
    expect(badge.classList.contains('text-bg-warning')).toBe(true)
    expect(badge.classList.contains('text-dark')).toBe(true)
    expect(badge.classList.contains('text-bg-secondary')).toBe(false)
  })

  it('sets a title attribute describing the mode + effective branch', () => {
    installBranchDom({ qsBranch: 'master', overrideValue: 'nightly' })
    syncKometaBranchRollupBadge()
    const title = document.getElementById('kometa-branch-rollup-badge').getAttribute('title')
    expect(title).toContain('override selected: nightly')
    expect(title).toContain('Effective branch: nightly')
  })

  it("auto-mode title mentions 'auto' and the effective branch", () => {
    installBranchDom({ qsBranch: 'develop', overrideValue: '' })
    syncKometaBranchRollupBadge()
    const title = document.getElementById('kometa-branch-rollup-badge').getAttribute('title')
    expect(title).toContain('mode: auto')
    expect(title).toContain('Effective branch: nightly')
  })

  it('is a no-op when the badge is missing', () => {
    installBranchDom()
    document.getElementById('kometa-branch-rollup-badge').remove()
    expect(() => syncKometaBranchRollupBadge()).not.toThrow()
  })
})

// ---------------------------------------------------------------------
// syncKometaBranchOverrideWarning
// ---------------------------------------------------------------------

describe('syncKometaBranchOverrideWarning', () => {
  it('hides the warning when no override is set', () => {
    installBranchDom({ overrideValue: '' })
    // Make sure warning was showing to prove the toggle
    document.getElementById('kometa-branch-override-warning').classList.remove('d-none')
    syncKometaBranchOverrideWarning()
    expect(document.getElementById('kometa-branch-override-warning').classList.contains('d-none')).toBe(true)
  })

  it('shows the warning when an override is set', () => {
    installBranchDom({ overrideValue: 'develop' })
    syncKometaBranchOverrideWarning()
    expect(document.getElementById('kometa-branch-override-warning').classList.contains('d-none')).toBe(false)
  })

  it('is a no-op when the warning element is missing', () => {
    installBranchDom()
    document.getElementById('kometa-branch-override-warning').remove()
    expect(() => syncKometaBranchOverrideWarning()).not.toThrow()
  })
})
