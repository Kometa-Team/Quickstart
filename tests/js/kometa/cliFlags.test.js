// Tests for static/local-js/modules/kometa/_cliFlags.js
//
// Three exports:
//   - KOMETA_CLI_FLAGS (frozen catalog)
//   - updateFlagLabels(showCli, opts)
//   - updateLibraryVisibility(mainOption)
//
// COVERAGE:
//
//   KOMETA_CLI_FLAGS (4):
//     - contains all 24 documented flags
//     - each entry has label + description
//     - labels are non-empty strings
//     - object is frozen (immutability guard)
//
//   updateFlagLabels (10):
//     - renders friendly label when showCli=false
//     - renders raw --flag when showCli=true
//     - injects Bootstrap tooltip attributes
//     - includes description in tooltip title
//     - skips labels with no matching <label for="...">
//     - calls onInitTooltips(document) after rendering
//     - calls onLabelsUpdated() after rendering
//     - both callbacks are optional (no throw when omitted)
//     - renders run-option, mode, log, and other flag groups
//     - unknown flag falls back to raw flag as content
//
//   updateLibraryVisibility (4):
//     - no-ops when library-multiselect missing
//     - shows the .mb-2 wrapper when mainOption is --run-libraries
//     - hides the .mb-2 wrapper for other options
//     - toggles correctly across sequential calls

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  KOMETA_CLI_FLAGS,
  updateFlagLabels,
  updateLibraryVisibility
} from '../../../static/local-js/modules/kometa/_cliFlags.js'

// ---------------------------------------------------------------------
// KOMETA_CLI_FLAGS
// ---------------------------------------------------------------------

describe('KOMETA_CLI_FLAGS', () => {
  it('contains all 24 documented flags', () => {
    const expected = [
      '--run', '--run-libraries', '--times',
      '--operations-only', '--metadata-only', '--collections-only',
      '--playlists-only', '--overlays-only',
      '--debug', '--trace', '--log-requests',
      '--delete-collections', '--delete-labels', '--read-only-config',
      '--low-priority', '--no-report', '--no-missing', '--no-countdown',
      '--ignore-ghost', '--ignore-schedules', '--no-verify-ssl',
      '--tests', '--timeout', '--divider', '--width'
    ]
    expect(Object.keys(KOMETA_CLI_FLAGS).sort()).toEqual(expected.sort())
  })

  it('each entry has label + description', () => {
    for (const [flag, spec] of Object.entries(KOMETA_CLI_FLAGS)) {
      expect(spec, `flag ${flag} missing label`).toHaveProperty('label')
      expect(spec, `flag ${flag} missing description`).toHaveProperty('description')
    }
  })

  it('labels are non-empty strings', () => {
    for (const [flag, spec] of Object.entries(KOMETA_CLI_FLAGS)) {
      expect(typeof spec.label, `flag ${flag} label not string`).toBe('string')
      expect(spec.label.length, `flag ${flag} label empty`).toBeGreaterThan(0)
    }
  })

  it('the catalog is frozen (Object.freeze)', () => {
    expect(Object.isFrozen(KOMETA_CLI_FLAGS)).toBe(true)
  })
})

// ---------------------------------------------------------------------
// updateFlagLabels
// ---------------------------------------------------------------------

describe('updateFlagLabels', () => {
  beforeEach(() => {
    // Install labels for a representative sample from each group
    document.body.innerHTML = `
      <label for="opt-run">placeholder</label>
      <label for="opt-run-libraries">placeholder</label>
      <label for="opt-debug">placeholder</label>
      <label for="opt-operations-only">placeholder</label>
      <label for="opt-no-verify-ssl">placeholder</label>
    `
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('renders friendly labels when showCli=false', () => {
    updateFlagLabels(false)
    expect(document.querySelector('label[for="opt-run"]').textContent).toContain('Run Immediately')
    expect(document.querySelector('label[for="opt-debug"]').textContent).toContain('Debug Logging')
  })

  it('renders raw --flag names when showCli=true', () => {
    updateFlagLabels(true)
    expect(document.querySelector('label[for="opt-run"]').innerHTML).toContain('--run')
    expect(document.querySelector('label[for="opt-debug"]').innerHTML).toContain('--debug')
  })

  it('injects Bootstrap tooltip attributes', () => {
    updateFlagLabels(false)
    const label = document.querySelector('label[for="opt-run"]')
    expect(label.innerHTML).toContain('data-bs-toggle="tooltip"')
    expect(label.innerHTML).toContain('class="text-info"')
  })

  it('includes the description in the tooltip title attr', () => {
    updateFlagLabels(false)
    const label = document.querySelector('label[for="opt-debug"]')
    expect(label.innerHTML).toContain('title="Enable debug-level logging."')
  })

  it('silently skips flags with no matching <label>', () => {
    // Only opt-run is in the DOM; the rest of the render should still
    // succeed for the ones that ARE present.
    document.body.innerHTML = '<label for="opt-run">placeholder</label>'
    expect(() => updateFlagLabels(false)).not.toThrow()
    expect(document.querySelector('label[for="opt-run"]').textContent).toContain('Run Immediately')
  })

  it('calls onInitTooltips(document) after rendering', () => {
    const spy = vi.fn()
    updateFlagLabels(false, { onInitTooltips: spy })
    expect(spy).toHaveBeenCalledWith(document)
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('calls onLabelsUpdated() after rendering', () => {
    const spy = vi.fn()
    updateFlagLabels(false, { onLabelsUpdated: spy })
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('both callbacks are optional (no throw when omitted)', () => {
    expect(() => updateFlagLabels(false)).not.toThrow()
    expect(() => updateFlagLabels(true)).not.toThrow()
  })

  it('renders labels across all four flag groups', () => {
    // Verify that opt-run (RUN_OPTION), opt-operations-only (MODE),
    // opt-debug (LOG), and opt-no-verify-ssl (OTHER) all get rendered.
    updateFlagLabels(false)
    expect(document.querySelector('label[for="opt-run"]').textContent).toContain('Run Immediately')
    expect(document.querySelector('label[for="opt-operations-only"]').textContent).toContain('Operations Only')
    expect(document.querySelector('label[for="opt-debug"]').textContent).toContain('Debug Logging')
    expect(document.querySelector('label[for="opt-no-verify-ssl"]').textContent).toContain('No Verify SSL')
  })

  it('produces info-icon markup regardless of showCli', () => {
    updateFlagLabels(false)
    const friendly = document.querySelector('label[for="opt-run"]').innerHTML
    expect(friendly).toContain('bi-info-circle-fill')

    updateFlagLabels(true)
    const cliMode = document.querySelector('label[for="opt-run"]').innerHTML
    expect(cliMode).toContain('bi-info-circle-fill')
  })
})

// ---------------------------------------------------------------------
// updateLibraryVisibility
// ---------------------------------------------------------------------

describe('updateLibraryVisibility', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div class="mb-2">
        <select id="library-multiselect"></select>
      </div>
    `
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('no-ops when library-multiselect is missing', () => {
    document.body.innerHTML = ''
    expect(() => updateLibraryVisibility('--run-libraries')).not.toThrow()
  })

  it('shows the wrapper when mainOption is --run-libraries', () => {
    // Start hidden to verify it gets shown
    document.querySelector('.mb-2').classList.add('d-none')
    updateLibraryVisibility('--run-libraries')
    expect(document.querySelector('.mb-2').classList.contains('d-none')).toBe(false)
  })

  it('hides the wrapper for other options', () => {
    // Start shown
    updateLibraryVisibility('--run')
    expect(document.querySelector('.mb-2').classList.contains('d-none')).toBe(true)
  })

  it('toggles correctly across sequential calls', () => {
    updateLibraryVisibility('--run-libraries')
    expect(document.querySelector('.mb-2').classList.contains('d-none')).toBe(false)
    updateLibraryVisibility('--run')
    expect(document.querySelector('.mb-2').classList.contains('d-none')).toBe(true)
    updateLibraryVisibility('--run-libraries')
    expect(document.querySelector('.mb-2').classList.contains('d-none')).toBe(false)
  })
})
