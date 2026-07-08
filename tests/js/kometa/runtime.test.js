// Tests for static/local-js/modules/kometa/_runtime.js
//
// The module has seven pure DOM readers. All read from the hidden
// #run-command-output element's dataset. Tests build a fresh element
// in beforeEach with the desired data-* attributes and inspect the
// return value.
//
// Coverage strategy:
//
//   getConfiguredKometaInstallMode
//     - default 'managed' when element missing or attr missing
//     - reads 'managed' | 'existing' | 'external'
//     - falls back to 'managed' for unknown values
//     - lowercases + trims the raw attribute value
//
//   getConfiguredKometaRootPosix
//     - reads selected first, falls back to default
//     - returns configDir instead when mode is 'external'
//     - empty string when nothing is set
//     - empty string when element is missing
//
//   getConfiguredKometaRootDisplay
//     - reads *Display variants first, falls back to *Default variants
//     - falls back to POSIX version when nothing display-specific
//     - returns configDirDisplay when mode is 'external'
//
//   kometaCanLaunch / kometaCanProbeRuntime / kometaCanReadLogs
//     - true for 'true' (case-insensitive), false otherwise
//     - false when element or attr missing
//
//   kometaCanCheckUpdateStatus
//     - false when mode is 'external'
//     - depends on kometaCanProbeRuntime otherwise

import { afterEach, describe, expect, it } from 'vitest'
import {
  getConfiguredKometaInstallMode,
  getConfiguredKometaRootPosix,
  getConfiguredKometaRootDisplay,
  kometaCanLaunch,
  kometaCanCheckUpdateStatus,
  kometaCanProbeRuntime,
  kometaCanReadLogs
} from '../../../static/local-js/modules/kometa/_runtime.js'

// ---------------------------------------------------------------------
// Fixture DOM helpers
// ---------------------------------------------------------------------

/**
 * Install a #run-command-output element with the given dataset. Pass
 * `null` for `dataset` to install NO element (missing-element case).
 * Pass `{}` for an empty element.
 */
function installRuntimeDom (dataset) {
  if (dataset === null) {
    document.body.innerHTML = ''
    return
  }
  const el = document.createElement('div')
  el.id = 'run-command-output'
  Object.entries(dataset).forEach(([key, value]) => {
    el.dataset[key] = value
  })
  document.body.innerHTML = ''
  document.body.appendChild(el)
}

afterEach(() => {
  document.body.innerHTML = ''
})

// ---------------------------------------------------------------------
// getConfiguredKometaInstallMode
// ---------------------------------------------------------------------

describe('getConfiguredKometaInstallMode', () => {
  it("defaults to 'managed' when the element is missing", () => {
    installRuntimeDom(null)
    expect(getConfiguredKometaInstallMode()).toBe('managed')
  })

  it("defaults to 'managed' when the attribute is missing", () => {
    installRuntimeDom({})
    expect(getConfiguredKometaInstallMode()).toBe('managed')
  })

  it("returns 'managed' when explicitly set", () => {
    installRuntimeDom({ kometaInstallMode: 'managed' })
    expect(getConfiguredKometaInstallMode()).toBe('managed')
  })

  it("returns 'existing' when set", () => {
    installRuntimeDom({ kometaInstallMode: 'existing' })
    expect(getConfiguredKometaInstallMode()).toBe('existing')
  })

  it("returns 'external' when set", () => {
    installRuntimeDom({ kometaInstallMode: 'external' })
    expect(getConfiguredKometaInstallMode()).toBe('external')
  })

  it('lowercases the attribute value', () => {
    installRuntimeDom({ kometaInstallMode: 'EXTERNAL' })
    expect(getConfiguredKometaInstallMode()).toBe('external')
  })

  it('trims whitespace around the attribute value', () => {
    installRuntimeDom({ kometaInstallMode: '  existing  ' })
    expect(getConfiguredKometaInstallMode()).toBe('existing')
  })

  it("falls back to 'managed' for unknown values", () => {
    installRuntimeDom({ kometaInstallMode: 'docker' })
    expect(getConfiguredKometaInstallMode()).toBe('managed')
  })
})

// ---------------------------------------------------------------------
// getConfiguredKometaRootPosix
// ---------------------------------------------------------------------

describe('getConfiguredKometaRootPosix', () => {
  it('returns empty string when element is missing', () => {
    installRuntimeDom(null)
    expect(getConfiguredKometaRootPosix()).toBe('')
  })

  it('returns empty string when no attrs are set', () => {
    installRuntimeDom({})
    expect(getConfiguredKometaRootPosix()).toBe('')
  })

  it('returns kometaRootSelected when set', () => {
    installRuntimeDom({
      kometaRootSelected: '/opt/kometa-user',
      kometaRootDefault: '/opt/kometa-default'
    })
    expect(getConfiguredKometaRootPosix()).toBe('/opt/kometa-user')
  })

  it('falls back to kometaRootDefault when selected is empty', () => {
    installRuntimeDom({ kometaRootDefault: '/opt/kometa-default' })
    expect(getConfiguredKometaRootPosix()).toBe('/opt/kometa-default')
  })

  it("returns configDir when mode is 'external' (ignores selected/default)", () => {
    installRuntimeDom({
      kometaInstallMode: 'external',
      kometaRootSelected: '/ignored/selected',
      kometaRootDefault: '/ignored/default',
      kometaConfigDir: '/mnt/config'
    })
    expect(getConfiguredKometaRootPosix()).toBe('/mnt/config')
  })

  it("returns empty when mode='external' but configDir is missing", () => {
    installRuntimeDom({ kometaInstallMode: 'external' })
    expect(getConfiguredKometaRootPosix()).toBe('')
  })

  it('trims whitespace on the selected value', () => {
    installRuntimeDom({ kometaRootSelected: '   /opt/kometa   ' })
    expect(getConfiguredKometaRootPosix()).toBe('/opt/kometa')
  })
})

// ---------------------------------------------------------------------
// getConfiguredKometaRootDisplay
// ---------------------------------------------------------------------

describe('getConfiguredKometaRootDisplay', () => {
  it('returns kometaRootSelectedDisplay when set', () => {
    installRuntimeDom({
      kometaRootSelectedDisplay: 'C:\\Users\\me\\Kometa',
      kometaRootSelected: '/mnt/c/Users/me/Kometa'
    })
    expect(getConfiguredKometaRootDisplay()).toBe('C:\\Users\\me\\Kometa')
  })

  it('falls back to kometaRootDefaultDisplay when *Selected* variants missing', () => {
    installRuntimeDom({
      kometaRootDefaultDisplay: 'D:\\Default'
    })
    expect(getConfiguredKometaRootDisplay()).toBe('D:\\Default')
  })

  it('falls back to POSIX root when no Display variants exist', () => {
    installRuntimeDom({ kometaRootDefault: '/opt/kometa' })
    expect(getConfiguredKometaRootDisplay()).toBe('/opt/kometa')
  })

  it("returns configDirDisplay when mode is 'external'", () => {
    installRuntimeDom({
      kometaInstallMode: 'external',
      kometaConfigDirDisplay: 'C:\\Configs',
      kometaConfigDir: '/mnt/c/Configs'
    })
    expect(getConfiguredKometaRootDisplay()).toBe('C:\\Configs')
  })

  it("falls back to POSIX configDir when mode='external' and no Display", () => {
    installRuntimeDom({
      kometaInstallMode: 'external',
      kometaConfigDir: '/mnt/c/Configs'
    })
    expect(getConfiguredKometaRootDisplay()).toBe('/mnt/c/Configs')
  })

  it('returns empty when element missing', () => {
    installRuntimeDom(null)
    expect(getConfiguredKometaRootDisplay()).toBe('')
  })
})

// ---------------------------------------------------------------------
// kometaCanLaunch
// ---------------------------------------------------------------------

describe('kometaCanLaunch', () => {
  it('returns true for exact "true"', () => {
    installRuntimeDom({ kometaCanLaunch: 'true' })
    expect(kometaCanLaunch()).toBe(true)
  })

  it('is case-insensitive on the value', () => {
    installRuntimeDom({ kometaCanLaunch: 'TRUE' })
    expect(kometaCanLaunch()).toBe(true)
  })

  it('returns false for "false"', () => {
    installRuntimeDom({ kometaCanLaunch: 'false' })
    expect(kometaCanLaunch()).toBe(false)
  })

  it('returns false when attribute is missing', () => {
    installRuntimeDom({})
    expect(kometaCanLaunch()).toBe(false)
  })

  it('returns false when element is missing', () => {
    installRuntimeDom(null)
    expect(kometaCanLaunch()).toBe(false)
  })

  it('returns false for random truthy-looking values', () => {
    installRuntimeDom({ kometaCanLaunch: '1' })
    expect(kometaCanLaunch()).toBe(false)
    installRuntimeDom({ kometaCanLaunch: 'yes' })
    expect(kometaCanLaunch()).toBe(false)
  })
})

// ---------------------------------------------------------------------
// kometaCanProbeRuntime
// ---------------------------------------------------------------------

describe('kometaCanProbeRuntime', () => {
  it('reads kometaCanProbeRuntime dataset key', () => {
    installRuntimeDom({ kometaCanProbeRuntime: 'true' })
    expect(kometaCanProbeRuntime()).toBe(true)
  })

  it('returns false for empty string', () => {
    installRuntimeDom({ kometaCanProbeRuntime: '' })
    expect(kometaCanProbeRuntime()).toBe(false)
  })

  it('does NOT confuse with kometaCanLaunch', () => {
    installRuntimeDom({ kometaCanLaunch: 'true' })
    expect(kometaCanProbeRuntime()).toBe(false)
  })
})

// ---------------------------------------------------------------------
// kometaCanReadLogs
// ---------------------------------------------------------------------

describe('kometaCanReadLogs', () => {
  it('reads kometaCanReadLogs dataset key', () => {
    installRuntimeDom({ kometaCanReadLogs: 'true' })
    expect(kometaCanReadLogs()).toBe(true)
  })

  it('does NOT confuse with kometaCanProbeRuntime', () => {
    installRuntimeDom({ kometaCanProbeRuntime: 'true' })
    expect(kometaCanReadLogs()).toBe(false)
  })
})

// ---------------------------------------------------------------------
// kometaCanCheckUpdateStatus (composite)
// ---------------------------------------------------------------------

describe('kometaCanCheckUpdateStatus', () => {
  it("is false when mode is 'external' regardless of probe capability", () => {
    installRuntimeDom({
      kometaInstallMode: 'external',
      kometaCanProbeRuntime: 'true'
    })
    expect(kometaCanCheckUpdateStatus()).toBe(false)
  })

  it("is false when mode is 'managed' but probe capability is false", () => {
    installRuntimeDom({ kometaInstallMode: 'managed' })
    expect(kometaCanCheckUpdateStatus()).toBe(false)
  })

  it("is true when mode is 'managed' AND probe capability is true", () => {
    installRuntimeDom({
      kometaInstallMode: 'managed',
      kometaCanProbeRuntime: 'true'
    })
    expect(kometaCanCheckUpdateStatus()).toBe(true)
  })

  it("is true when mode is 'existing' AND probe capability is true", () => {
    installRuntimeDom({
      kometaInstallMode: 'existing',
      kometaCanProbeRuntime: 'true'
    })
    expect(kometaCanCheckUpdateStatus()).toBe(true)
  })

  it('is false when element is entirely missing', () => {
    installRuntimeDom(null)
    // getConfiguredKometaInstallMode -> 'managed' (default),
    // kometaCanProbeRuntime -> false. So composite = false.
    expect(kometaCanCheckUpdateStatus()).toBe(false)
  })
})
