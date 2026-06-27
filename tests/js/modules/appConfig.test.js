// Tests for static/local-js/modules/appConfig.js (#1334 Step 5, Phase B).
//
// These tests don't currently run in CI because Vitest is on a separate
// branch (PR #1357) that hasn't merged yet. Once it lands, this file
// is automatically picked up by the include glob in vite.config.js
// (`tests/js/**/*.test.js`) and runs with everything else.
//
// Coverage of the contract that 000-base.js depends on:
//
//   - getAppConfig returns the value when the key exists, the fallback
//     when it doesn't, and `undefined` when no fallback is given.
//   - setAppConfig merges into the namespace and mutates in place
//     (so other code that captured a reference to window.QS_AppConfig
//     sees the new values).
//   - refreshAppConfig hits /api/app-config, merges the response, and
//     swallows network errors gracefully.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getAppConfig,
  refreshAppConfig,
  setAppConfig
} from '../../../static/local-js/modules/appConfig.js'

describe('getAppConfig', () => {
  beforeEach(() => {
    delete window.QS_AppConfig
  })

  it('returns undefined when the namespace is missing and no fallback given', () => {
    expect(getAppConfig('QS_DEBUG')).toBeUndefined()
  })

  it('returns the fallback when the namespace is missing', () => {
    expect(getAppConfig('QS_DEBUG', 'fallback-value')).toBe('fallback-value')
  })

  it('returns the live value when the key is present', () => {
    window.QS_AppConfig = { QS_DEBUG: true, QS_THEME: 'dracula' }
    expect(getAppConfig('QS_DEBUG')).toBe(true)
    expect(getAppConfig('QS_THEME')).toBe('dracula')
  })

  it('returns the fallback when the key is missing from a populated namespace', () => {
    window.QS_AppConfig = { QS_THEME: 'kometa' }
    expect(getAppConfig('QS_DEBUG', false)).toBe(false)
  })

  it('distinguishes between falsy values and missing keys', () => {
    // A common bug: `||` collapses both. The helper uses hasOwnProperty
    // so falsy values come through unchanged.
    window.QS_AppConfig = { QS_DEBUG: false, QS_KOMETA_LOG_KEEP: 0, QS_THEME: '' }
    expect(getAppConfig('QS_DEBUG', true)).toBe(false)
    expect(getAppConfig('QS_KOMETA_LOG_KEEP', 99)).toBe(0)
    expect(getAppConfig('QS_THEME', 'kometa')).toBe('')
  })
})

describe('setAppConfig', () => {
  beforeEach(() => {
    delete window.QS_AppConfig
  })

  it('creates the namespace when it does not exist', () => {
    expect(window.QS_AppConfig).toBeUndefined()
    setAppConfig({ QS_DEBUG: true })
    expect(window.QS_AppConfig).toEqual({ QS_DEBUG: true })
  })

  it('merges into an existing namespace without dropping other keys', () => {
    window.QS_AppConfig = { QS_DEBUG: false, QS_THEME: 'kometa' }
    setAppConfig({ QS_THEME: 'dracula' })
    expect(window.QS_AppConfig).toEqual({ QS_DEBUG: false, QS_THEME: 'dracula' })
  })

  it('mutates in place so captured references see the new values', () => {
    window.QS_AppConfig = { QS_DEBUG: false }
    const captured = window.QS_AppConfig
    setAppConfig({ QS_DEBUG: true, QS_THEME: 'dracula' })
    // captured is the same object reference; the settings save flow
    // relies on this so other handlers that have already read
    // window.QS_AppConfig still see live values.
    expect(captured).toBe(window.QS_AppConfig)
    expect(captured.QS_DEBUG).toBe(true)
    expect(captured.QS_THEME).toBe('dracula')
  })

  it('is a no-op when patch is null or not an object', () => {
    window.QS_AppConfig = { QS_DEBUG: true }
    setAppConfig(null)
    setAppConfig(undefined)
    setAppConfig('not an object')
    expect(window.QS_AppConfig).toEqual({ QS_DEBUG: true })
  })

  it('returns the namespace for convenience', () => {
    const result = setAppConfig({ QS_DEBUG: true })
    expect(result).toBe(window.QS_AppConfig)
  })
})

describe('refreshAppConfig', () => {
  beforeEach(() => {
    delete window.QS_AppConfig
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches /api/app-config and merges the response', async () => {
    window.QS_AppConfig = { QS_DEBUG: false }
    const fetchMock = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ QS_DEBUG: true, QS_THEME: 'dracula' })
    }))
    vi.stubGlobal('fetch', fetchMock)

    await refreshAppConfig()

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/app-config',
      { headers: { Accept: 'application/json' } }
    )
    expect(window.QS_AppConfig.QS_DEBUG).toBe(true)
    expect(window.QS_AppConfig.QS_THEME).toBe('dracula')
  })

  it('preserves keys not present in the response (forward compat)', async () => {
    window.QS_AppConfig = { QS_DEBUG: false, EXOTIC_FUTURE_KEY: 'sentinel' }
    vi.stubGlobal('fetch', () => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ QS_DEBUG: true })
    }))

    await refreshAppConfig()

    expect(window.QS_AppConfig.QS_DEBUG).toBe(true)
    expect(window.QS_AppConfig.EXOTIC_FUTURE_KEY).toBe('sentinel')
  })

  it('keeps the existing namespace intact on HTTP failure', async () => {
    window.QS_AppConfig = { QS_DEBUG: true }
    vi.stubGlobal('fetch', () => Promise.resolve({
      ok: false,
      json: () => Promise.resolve({ QS_DEBUG: 'oh no' })
    }))

    await refreshAppConfig()

    expect(window.QS_AppConfig.QS_DEBUG).toBe(true)
  })

  it('keeps the existing namespace intact on network error', async () => {
    window.QS_AppConfig = { QS_DEBUG: true }
    vi.stubGlobal('fetch', () => Promise.reject(new Error('network down')))

    await refreshAppConfig()

    expect(window.QS_AppConfig.QS_DEBUG).toBe(true)
  })

  it('keeps the existing namespace intact on invalid JSON', async () => {
    window.QS_AppConfig = { QS_DEBUG: true }
    vi.stubGlobal('fetch', () => Promise.resolve({
      ok: true,
      json: () => Promise.reject(new Error('not JSON'))
    }))

    await refreshAppConfig()

    expect(window.QS_AppConfig.QS_DEBUG).toBe(true)
  })
})
