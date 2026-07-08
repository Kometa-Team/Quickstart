// Tests for static/local-js/modules/kometa/_runCommand.js
//
// The module exports seven functions. Coverage strategy:
//
//   isRunCommandValid            trivial DOM read, 4 tests
//   getRunCommandModeLabel       pure fn, 3 tests
//   getRunCommandModeBadgeLabel  pure fn, 3 tests
//   getRunCommandModeBadgeClass  pure fn, 3 tests
//   applyActiveRunCommandState   writes state + DOM, 5 tests
//   clearActiveRunCommandState   inverse, 3 tests
//   buildCommand                 big one, 25+ tests covering every
//                                validation branch

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import {
  buildCommand,
  isRunCommandValid,
  getRunCommandModeLabel,
  getRunCommandModeBadgeLabel,
  getRunCommandModeBadgeClass,
  applyActiveRunCommandState,
  clearActiveRunCommandState
} from '../../../static/local-js/modules/kometa/_runCommand.js'

// ---------------------------------------------------------------------
// Fixture DOM helpers
// ---------------------------------------------------------------------

/**
 * Build the minimal DOM that buildCommand consults. Every option
 * is disabled/unchecked by default; individual tests flip the ones
 * they need.
 *
 * @param {{
 *   platform?: 'Linux' | 'Windows' | 'Docker',
 *   configFilename?: string,
 *   venvPython?: string,
 *   kometaRoot?: string,
 *   runOption?: string,
 *   modeFlag?: string,
 *   logFlag?: string
 * }} [opts]
 */
function installRunCommandDom (opts = {}) {
  const {
    platform = 'Linux',
    configFilename = 'config.yml',
    venvPython = '/venv/bin/python',
    kometaRoot = '/opt/kometa',
    runOption = '',
    modeFlag = '',
    logFlag = ''
  } = opts

  document.body.innerHTML = `
    <div id="qs-env" data-running-on="${platform}"></div>
    <div id="run-command-output"
         data-config-filename="${configFilename}"
         data-venv-python="${venvPython}"
         data-kometa-root="${kometaRoot}"></div>
    <div id="run-command-label"></div>
    <div id="run-command-active-badge" class="d-none"></div>

    <input type="radio" name="run-option" value="" ${runOption === '' ? 'checked' : ''}>
    <input type="radio" name="run-option" value="--collections-only" ${runOption === '--collections-only' ? 'checked' : ''}>
    <input type="radio" name="run-option" value="--times" ${runOption === '--times' ? 'checked' : ''}>
    <input type="radio" name="run-option" value="--run-libraries" ${runOption === '--run-libraries' ? 'checked' : ''}>

    <input id="times-input" value="">
    <div id="times-error" class="d-none"></div>

    <select id="library-multiselect" multiple>
      <option value="Movies">Movies</option>
      <option value="TV Shows">TV Shows</option>
    </select>

    <input type="radio" name="mode-flag" value="" ${modeFlag === '' ? 'checked' : ''}>
    <input type="radio" name="mode-flag" value="--dry-run" ${modeFlag === '--dry-run' ? 'checked' : ''}>

    <input type="radio" name="log-flag" value="" ${logFlag === '' ? 'checked' : ''}>
    <input type="radio" name="log-flag" value="--debug" ${logFlag === '--debug' ? 'checked' : ''}>

    <input type="checkbox" id="opt-delete-collections">
    <input type="checkbox" id="opt-delete-labels">
    <input type="checkbox" id="opt-read-only-config">
    <input type="checkbox" id="opt-low-priority">
    <input type="checkbox" id="opt-no-report">
    <input type="checkbox" id="opt-no-missing">
    <input type="checkbox" id="opt-no-countdown">
    <input type="checkbox" id="opt-ignore-ghost">
    <input type="checkbox" id="opt-ignore-schedules">
    <input type="checkbox" id="opt-no-verify-ssl">
    <input type="checkbox" id="opt-tests">

    <input type="checkbox" id="opt-timeout">
    <input id="opt-timeout-val" value="">
    <div id="timeout-error" class="d-none"></div>

    <input type="checkbox" id="opt-width">
    <input id="opt-width-val" value="">
    <div id="width-error" class="d-none"></div>

    <input type="checkbox" id="opt-divider">
    <input id="opt-divider-val" value="">
    <div id="divider-error" class="d-none"></div>

    <!-- Maintenance-window helpers (unused for most tests but must
         exist for toggleTimesInputVisibility + checkMaintenanceWarning
         to work as no-ops when the run-option is --times) -->
    <div id="times-input-container" class="d-none"></div>
    <div id="times-warning" class="d-none"></div>
    <div id="maintenance-warning" class="d-none"></div>
    <div id="plex-maintenance-window" data-window=""></div>
  `
}

function makeCallbacks () {
  return {
    updateRunNowState: vi.fn(),
    syncFinalAccordionRollups: vi.fn()
  }
}

afterEach(() => {
  document.body.innerHTML = ''
  kometaState.activeRunCommandOverride = null
  kometaState.activeRunCommandMode = null
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------
// isRunCommandValid
// ---------------------------------------------------------------------

describe('isRunCommandValid', () => {
  it('is true when the run-command-output has real content', () => {
    document.body.innerHTML = '<div id="run-command-output">python kometa.py --config config.yml</div>'
    expect(isRunCommandValid()).toBe(true)
  })

  it("is false when the content starts with '??' placeholder", () => {
    document.body.innerHTML = '<div id="run-command-output">?? no kometa root ??</div>'
    expect(isRunCommandValid()).toBe(false)
  })

  it('is false when the content is empty/whitespace', () => {
    document.body.innerHTML = '<div id="run-command-output">   </div>'
    expect(isRunCommandValid()).toBe(false)
  })

  it('is false when the element is missing', () => {
    document.body.innerHTML = ''
    expect(isRunCommandValid()).toBe(false)
  })
})

// ---------------------------------------------------------------------
// Mode label functions (pure)
// ---------------------------------------------------------------------

describe('getRunCommandModeLabel', () => {
  it("returns 'Recovery Command' for mode='recovery'", () => {
    expect(getRunCommandModeLabel('recovery')).toBe('Recovery Command')
  })

  it("returns 'Last Logged Command' for mode='logged'", () => {
    expect(getRunCommandModeLabel('logged')).toBe('Last Logged Command')
  })

  it("returns 'Command' for anything else (current, null, empty, garbage)", () => {
    expect(getRunCommandModeLabel('current')).toBe('Command')
    expect(getRunCommandModeLabel(null)).toBe('Command')
    expect(getRunCommandModeLabel('')).toBe('Command')
    expect(getRunCommandModeLabel('nope')).toBe('Command')
  })
})

describe('getRunCommandModeBadgeLabel', () => {
  it('returns per-mode active labels', () => {
    expect(getRunCommandModeBadgeLabel('recovery')).toBe('Recovery Active')
    expect(getRunCommandModeBadgeLabel('logged')).toBe('Logged Active')
    expect(getRunCommandModeBadgeLabel('current')).toBe('Current Active')
  })

  it('normalizes case + whitespace on the input', () => {
    expect(getRunCommandModeBadgeLabel('  RECOVERY ')).toBe('Recovery Active')
  })

  it("defaults to 'Current Active' for null / undefined / unknown", () => {
    expect(getRunCommandModeBadgeLabel(null)).toBe('Current Active')
    expect(getRunCommandModeBadgeLabel(undefined)).toBe('Current Active')
    expect(getRunCommandModeBadgeLabel('nope')).toBe('Current Active')
  })
})

describe('getRunCommandModeBadgeClass', () => {
  it('returns per-mode Bootstrap classes', () => {
    expect(getRunCommandModeBadgeClass('recovery')).toBe('text-bg-warning')
    expect(getRunCommandModeBadgeClass('logged')).toBe('text-bg-secondary')
    expect(getRunCommandModeBadgeClass('current')).toBe('text-bg-primary')
  })

  it("defaults to 'text-bg-primary' for unknown values", () => {
    expect(getRunCommandModeBadgeClass('nope')).toBe('text-bg-primary')
  })

  it('normalizes case + whitespace on the input', () => {
    expect(getRunCommandModeBadgeClass('LOGGED')).toBe('text-bg-secondary')
  })
})

// ---------------------------------------------------------------------
// applyActiveRunCommandState / clearActiveRunCommandState
// ---------------------------------------------------------------------

describe('applyActiveRunCommandState', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="run-command-output"></div>
      <div id="run-command-label"></div>
      <div id="run-command-active-badge" class="d-none"></div>
    `
  })

  it("writes the command to kometaState + textContent (mode='recovery')", () => {
    applyActiveRunCommandState('python kometa.py --recovery', 'recovery')
    expect(kometaState.activeRunCommandOverride).toBe('python kometa.py --recovery')
    expect(kometaState.activeRunCommandMode).toBe('recovery')
    expect(document.getElementById('run-command-output').textContent).toBe('python kometa.py --recovery')
  })

  it("updates the label to 'Recovery Command' for mode='recovery'", () => {
    applyActiveRunCommandState('cmd', 'recovery')
    expect(document.getElementById('run-command-label').textContent).toBe('Recovery Command')
  })

  it("updates the badge with the correct class + text (mode='logged')", () => {
    applyActiveRunCommandState('cmd', 'logged')
    const badge = document.getElementById('run-command-active-badge')
    expect(badge.classList.contains('d-none')).toBe(false)
    expect(badge.classList.contains('text-bg-secondary')).toBe(true)
    expect(badge.textContent).toBe('Logged Active')
  })

  it('does NOT overwrite textContent when the command arg is falsy', () => {
    const outEl = document.getElementById('run-command-output')
    outEl.textContent = 'existing content'
    applyActiveRunCommandState(null, 'current')
    expect(outEl.textContent).toBe('existing content')
    // but state should still be cleared/updated
    expect(kometaState.activeRunCommandOverride).toBeNull()
    expect(kometaState.activeRunCommandMode).toBe('current')
  })

  it('normalizes the mode input (case + whitespace)', () => {
    applyActiveRunCommandState('cmd', '  RECOVERY  ')
    expect(kometaState.activeRunCommandMode).toBe('recovery')
  })
})

describe('clearActiveRunCommandState', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="run-command-label">Recovery Command</div>
      <div id="run-command-active-badge" class="text-bg-warning">Recovery Active</div>
    `
    kometaState.activeRunCommandOverride = 'stale command'
    kometaState.activeRunCommandMode = 'recovery'
  })

  it('clears the state fields to null', () => {
    clearActiveRunCommandState()
    expect(kometaState.activeRunCommandOverride).toBeNull()
    expect(kometaState.activeRunCommandMode).toBeNull()
  })

  it("resets the label to 'Command'", () => {
    clearActiveRunCommandState()
    expect(document.getElementById('run-command-label').textContent).toBe('Command')
  })

  it('hides the badge and strips per-mode classes', () => {
    clearActiveRunCommandState()
    const badge = document.getElementById('run-command-active-badge')
    expect(badge.classList.contains('d-none')).toBe(true)
    expect(badge.classList.contains('text-bg-warning')).toBe(false)
    expect(badge.classList.contains('text-bg-secondary')).toBe(false)
    expect(badge.classList.contains('text-bg-primary')).toBe(false)
  })
})

// ---------------------------------------------------------------------
// buildCommand
// ---------------------------------------------------------------------

describe('buildCommand basic path (no flags)', () => {
  it('assembles python + kometa.py + --config with quoting', () => {
    installRunCommandDom()
    const cb = makeCallbacks()
    const result = buildCommand(cb)
    expect(result).toBe(true)
    const out = document.getElementById('run-command-output')
    expect(out.dataset.builtCommand).toBe('/venv/bin/python /opt/kometa/kometa.py --config /opt/kometa/config/config.yml')
    expect(out.textContent).toBe(out.dataset.builtCommand)
  })

  it('invokes both callbacks exactly once on the success path', () => {
    installRunCommandDom()
    const cb = makeCallbacks()
    buildCommand(cb)
    expect(cb.updateRunNowState).toHaveBeenCalledTimes(1)
    expect(cb.syncFinalAccordionRollups).toHaveBeenCalledTimes(1)
  })

  it('short-circuits (returns undefined) when run-command-output is missing', () => {
    document.body.innerHTML = '<div id="qs-env"></div>' // no run-command-output
    const cb = makeCallbacks()
    const result = buildCommand(cb)
    expect(result).toBeUndefined()
    // Callbacks should NOT have been called
    expect(cb.updateRunNowState).not.toHaveBeenCalled()
  })

  it('quotes paths containing spaces', () => {
    installRunCommandDom({
      venvPython: '/opt/my venv/bin/python',
      kometaRoot: '/opt/my kometa'
    })
    buildCommand(makeCallbacks())
    const out = document.getElementById('run-command-output').dataset.builtCommand
    expect(out).toContain('"/opt/my venv/bin/python"')
    expect(out).toContain('"/opt/my kometa/kometa.py"')
    expect(out).toContain('"/opt/my kometa/config/config.yml"')
  })

  it('converts forward slashes to backslashes on Windows', () => {
    installRunCommandDom({
      platform: 'Windows',
      venvPython: 'C:/venv/Scripts/python.exe',
      kometaRoot: 'C:/Kometa'
    })
    buildCommand(makeCallbacks())
    const out = document.getElementById('run-command-output').dataset.builtCommand
    expect(out).toContain('C:\\venv\\Scripts\\python.exe')
    expect(out).toContain('C:\\Kometa\\kometa.py')
    expect(out).toContain('C:\\Kometa\\config\\config.yml')
    // No forward slashes in the assembled path
    expect(out).not.toContain('C:/venv')
  })

  it('does NOT overwrite textContent when kometaState.activeRunCommandOverride is set', () => {
    installRunCommandDom()
    const out = document.getElementById('run-command-output')
    out.textContent = 'FROZEN COMMAND'
    kometaState.activeRunCommandOverride = 'FROZEN COMMAND'
    buildCommand(makeCallbacks())
    expect(out.textContent).toBe('FROZEN COMMAND')
    // But dataset.builtCommand should still be updated
    expect(out.dataset.builtCommand).toBe('/venv/bin/python /opt/kometa/kometa.py --config /opt/kometa/config/config.yml')
  })

  it('uses default python3 when venv-python attr is missing', () => {
    installRunCommandDom({ venvPython: '' })
    buildCommand(makeCallbacks())
    const out = document.getElementById('run-command-output').dataset.builtCommand
    expect(out.startsWith('python3 ')).toBe(true)
  })
})

describe('buildCommand mainOption --times', () => {
  it('appends quoted times string when valid', () => {
    installRunCommandDom({ runOption: '--times' })
    document.getElementById('times-input').value = '06:00|15:00'
    buildCommand(makeCallbacks())
    const out = document.getElementById('run-command-output').dataset.builtCommand
    expect(out).toContain('--times "06:00|15:00"')
  })

  it("returns false and shows 'Invalid time format' on bad input", () => {
    installRunCommandDom({ runOption: '--times' })
    document.getElementById('times-input').value = 'not a time'
    const cb = makeCallbacks()
    const result = buildCommand(cb)
    expect(result).toBe(false)
    expect(document.getElementById('times-error').classList.contains('d-none')).toBe(false)
    expect(document.getElementById('run-command-output').textContent).toContain('Invalid time format')
    // Callbacks should still fire on the failure path (so run-now
    // gets disabled and the accordion rollup updates)
    expect(cb.updateRunNowState).toHaveBeenCalledTimes(1)
    expect(cb.syncFinalAccordionRollups).toHaveBeenCalledTimes(1)
  })

  it('hides the times-error div when the value becomes valid', () => {
    installRunCommandDom({ runOption: '--times' })
    document.getElementById('times-input').value = '06:00'
    document.getElementById('times-error').classList.remove('d-none') // stale
    buildCommand(makeCallbacks())
    expect(document.getElementById('times-error').classList.contains('d-none')).toBe(true)
  })
})

describe('buildCommand mainOption --run-libraries', () => {
  it('appends quoted pipe-joined selection', () => {
    installRunCommandDom({ runOption: '--run-libraries' })
    const sel = document.getElementById('library-multiselect')
    Array.from(sel.options).forEach(o => { o.selected = true })
    buildCommand(makeCallbacks())
    const out = document.getElementById('run-command-output').dataset.builtCommand
    expect(out).toContain('--run-libraries "Movies|TV Shows"')
  })

  it('returns false with a warning when no libraries are selected', () => {
    installRunCommandDom({ runOption: '--run-libraries' })
    // Nothing selected
    const result = buildCommand(makeCallbacks())
    expect(result).toBe(false)
    expect(document.getElementById('run-command-output').textContent).toContain('Please select at least one library')
  })
})

describe('buildCommand mode/log flags', () => {
  it('appends the selected mode flag', () => {
    installRunCommandDom({ modeFlag: '--dry-run' })
    buildCommand(makeCallbacks())
    expect(document.getElementById('run-command-output').dataset.builtCommand).toContain('--dry-run')
  })

  it('appends the selected log flag', () => {
    installRunCommandDom({ logFlag: '--debug' })
    buildCommand(makeCallbacks())
    expect(document.getElementById('run-command-output').dataset.builtCommand).toContain('--debug')
  })
})

describe('buildCommand no-value checkboxes', () => {
  it('appends each checked flag', () => {
    installRunCommandDom()
    document.getElementById('opt-delete-collections').checked = true
    document.getElementById('opt-read-only-config').checked = true
    document.getElementById('opt-no-verify-ssl').checked = true
    buildCommand(makeCallbacks())
    const out = document.getElementById('run-command-output').dataset.builtCommand
    expect(out).toContain('--delete-collections')
    expect(out).toContain('--read-only-config')
    expect(out).toContain('--no-verify-ssl')
    // Not checked -> not in command
    expect(out).not.toContain('--delete-labels')
    expect(out).not.toContain('--tests')
  })

  it('is silent when a checkbox element is missing (no throw)', () => {
    installRunCommandDom()
    document.getElementById('opt-tests').remove()
    expect(() => buildCommand(makeCallbacks())).not.toThrow()
  })
})

describe('buildCommand --timeout validation', () => {
  it('appends --timeout N when checked with a valid positive integer', () => {
    installRunCommandDom()
    document.getElementById('opt-timeout').checked = true
    document.getElementById('opt-timeout-val').value = '60'
    buildCommand(makeCallbacks())
    expect(document.getElementById('run-command-output').dataset.builtCommand).toContain('--timeout 60')
  })

  it('rejects a non-integer timeout', () => {
    installRunCommandDom()
    document.getElementById('opt-timeout').checked = true
    document.getElementById('opt-timeout-val').value = 'abc'
    expect(buildCommand(makeCallbacks())).toBe(false)
    expect(document.getElementById('timeout-error').classList.contains('d-none')).toBe(false)
  })

  it('rejects a zero or negative timeout', () => {
    installRunCommandDom()
    document.getElementById('opt-timeout').checked = true
    document.getElementById('opt-timeout-val').value = '0'
    expect(buildCommand(makeCallbacks())).toBe(false)
  })

  it('is a no-op when the timeout checkbox is unchecked', () => {
    installRunCommandDom()
    document.getElementById('opt-timeout').checked = false
    document.getElementById('opt-timeout-val').value = 'garbage but should be ignored'
    expect(buildCommand(makeCallbacks())).toBe(true)
    expect(document.getElementById('run-command-output').dataset.builtCommand).not.toContain('--timeout')
  })
})

describe('buildCommand --width validation', () => {
  it('appends --width N in [90, 300]', () => {
    installRunCommandDom()
    document.getElementById('opt-width').checked = true
    document.getElementById('opt-width-val').value = '120'
    buildCommand(makeCallbacks())
    expect(document.getElementById('run-command-output').dataset.builtCommand).toContain('--width 120')
  })

  it('rejects widths under 90', () => {
    installRunCommandDom()
    document.getElementById('opt-width').checked = true
    document.getElementById('opt-width-val').value = '80'
    expect(buildCommand(makeCallbacks())).toBe(false)
  })

  it('rejects widths over 300', () => {
    installRunCommandDom()
    document.getElementById('opt-width').checked = true
    document.getElementById('opt-width-val').value = '400'
    expect(buildCommand(makeCallbacks())).toBe(false)
  })

  it('accepts boundary values 90 and 300', () => {
    installRunCommandDom()
    document.getElementById('opt-width').checked = true
    document.getElementById('opt-width-val').value = '90'
    expect(buildCommand(makeCallbacks())).toBe(true)

    installRunCommandDom()
    document.getElementById('opt-width').checked = true
    document.getElementById('opt-width-val').value = '300'
    expect(buildCommand(makeCallbacks())).toBe(true)
  })
})

describe('buildCommand --divider validation', () => {
  it('appends --divider "X" for a single-character value', () => {
    installRunCommandDom()
    document.getElementById('opt-divider').checked = true
    document.getElementById('opt-divider-val').value = '='
    buildCommand(makeCallbacks())
    expect(document.getElementById('run-command-output').dataset.builtCommand).toContain('--divider "="')
  })

  it('rejects multi-character dividers', () => {
    installRunCommandDom()
    document.getElementById('opt-divider').checked = true
    document.getElementById('opt-divider-val').value = '=='
    expect(buildCommand(makeCallbacks())).toBe(false)
  })

  it('rejects empty divider even when checkbox is checked', () => {
    installRunCommandDom()
    document.getElementById('opt-divider').checked = true
    document.getElementById('opt-divider-val').value = ''
    expect(buildCommand(makeCallbacks())).toBe(false)
  })
})

describe('buildCommand robustness (missing callbacks)', () => {
  it('does not throw when callbacks are undefined', () => {
    installRunCommandDom()
    expect(() => buildCommand()).not.toThrow()
  })

  it('does not throw when callbacks are non-functions', () => {
    installRunCommandDom()
    expect(() =>
      buildCommand({ updateRunNowState: 42, syncFinalAccordionRollups: 'hi' })
    ).not.toThrow()
  })
})
