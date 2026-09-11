// Tests for static/local-js/modules/kometa/_headerBadges.js
//
// Every function in this module reads exclusively from the DOM and
// writes back into it. So the tests build a fresh fixture DOM in
// beforeEach and inspect textContent + classList after each call.
//
// Coverage strategy per function:
//
//   setHeaderRollupBadge  -- happy path, missing element (no-op),
//                            all 4 valid state values, invalid state
//                            falling back to 'unknown', class swap
//                            not accumulation
//
//   prettifyFlag          -- empty/null/undefined -> 'Default',
//                            single flag stripping, hyphen-to-space,
//                            edge cases (whitespace, non-string)
//
//   updateSectionStyleHeaderBadge  -- delegates to formatHeaderStyleLabel,
//                            fallback to 'Active' when empty
//
//   updateModeHeaderBadge -- both checkbox states, missing element
//
//   updateRunOptionHeaderBadge -- 4 mode branches x their sub-states
//
//   updateModeFlagsHeaderBadge / updateLogFlagsHeaderBadge -- radio
//                            selected vs none, various flag values
//
//   updateValidationFlagsHeaderBadge -- validation mode selected vs
//                            missing dependent file/directory paths
//
//   updateOtherFlagsHeaderBadge -- 0/some/all core flags, extras
//                            (timeout/divider/width) counted separately

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  setHeaderRollupBadge,
  prettifyFlag,
  updateSectionStyleHeaderBadge,
  updateModeHeaderBadge,
  updateRunOptionHeaderBadge,
  updateModeFlagsHeaderBadge,
  updateLogFlagsHeaderBadge,
  updateValidationFlagsHeaderBadge,
  updateOtherFlagsHeaderBadge,
  updateConfigOutputHeaderBadges,
  updateRunCommandHeaderBadge,
  updateLogscanHeaderBadge,
  syncFinalAccordionRollups
} from '../../../static/local-js/modules/kometa/_headerBadges.js'
import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'

// ---------------------------------------------------------------------
// Fixture DOM helpers
// ---------------------------------------------------------------------
//
// installBadge(id) creates a minimal badge span so setHeaderRollupBadge
// has something to mutate. Tests can pre-set the modifier class if
// they want to prove the swap-not-accumulate behavior.

function installBadge (id, initialClass = 'qs-validation-rollup-badge--unknown') {
  const el = document.createElement('span')
  el.id = id
  el.className = `qs-validation-rollup-badge ${initialClass}`
  el.textContent = ''
  document.body.appendChild(el)
  return el
}

afterEach(() => {
  document.body.innerHTML = ''
})

// ---------------------------------------------------------------------
// setHeaderRollupBadge
// ---------------------------------------------------------------------

describe('setHeaderRollupBadge', () => {
  it('sets textContent and applies the ok modifier class', () => {
    const el = installBadge('test-badge')
    setHeaderRollupBadge('test-badge', 'ok', '3 libraries')
    expect(el.textContent).toBe('3 libraries')
    expect(el.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('is a no-op when the target element is missing', () => {
    // Should not throw
    expect(() => setHeaderRollupBadge('does-not-exist', 'ok', 'label')).not.toThrow()
  })

  it('accepts all four canonical state values', () => {
    const states = ['unknown', 'ok', 'warn', 'error']
    for (const state of states) {
      const el = installBadge(`badge-${state}`)
      setHeaderRollupBadge(`badge-${state}`, state, `label-${state}`)
      expect(el.classList.contains(`qs-validation-rollup-badge--${state}`)).toBe(true)
    }
  })

  it('falls back to unknown for any non-canonical state value', () => {
    const el = installBadge('test-badge')
    setHeaderRollupBadge('test-badge', 'purple-monkey-dishwasher', 'label')
    expect(el.classList.contains('qs-validation-rollup-badge--unknown')).toBe(true)
    // AND the other modifiers are not set
    expect(el.classList.contains('qs-validation-rollup-badge--ok')).toBe(false)
    expect(el.classList.contains('qs-validation-rollup-badge--warn')).toBe(false)
    expect(el.classList.contains('qs-validation-rollup-badge--error')).toBe(false)
  })

  it('SWAPS the modifier class rather than accumulating', () => {
    // A previous call set the badge to warn -- switching to ok must
    // strip warn, not leave both classes present.
    const el = installBadge('test-badge', 'qs-validation-rollup-badge--warn')
    setHeaderRollupBadge('test-badge', 'ok', 'now green')
    expect(el.classList.contains('qs-validation-rollup-badge--warn')).toBe(false)
    expect(el.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('preserves the base .qs-validation-rollup-badge class', () => {
    // The base class carries font/size/padding rules; the modifier
    // only supplies color. Losing the base would collapse the badge.
    const el = installBadge('test-badge')
    setHeaderRollupBadge('test-badge', 'ok', 'label')
    expect(el.classList.contains('qs-validation-rollup-badge')).toBe(true)
  })

  it('overwrites the text on repeated calls (not appends)', () => {
    const el = installBadge('test-badge')
    setHeaderRollupBadge('test-badge', 'ok', 'first')
    setHeaderRollupBadge('test-badge', 'ok', 'second')
    expect(el.textContent).toBe('second')
  })
})

// ---------------------------------------------------------------------
// prettifyFlag
// ---------------------------------------------------------------------

describe('prettifyFlag', () => {
  it('returns "Default" for empty string', () => {
    expect(prettifyFlag('')).toBe('Default')
  })

  it('returns "Default" for null', () => {
    expect(prettifyFlag(null)).toBe('Default')
  })

  it('returns "Default" for undefined', () => {
    expect(prettifyFlag(undefined)).toBe('Default')
  })

  it('returns "Default" for whitespace-only input', () => {
    expect(prettifyFlag('   ')).toBe('Default')
  })

  it('strips leading -- prefix', () => {
    expect(prettifyFlag('--collections')).toBe('collections')
  })

  it('converts single hyphen to space', () => {
    expect(prettifyFlag('read-only-config')).toBe('read only config')
  })

  it('handles a CLI-style flag with hyphens', () => {
    expect(prettifyFlag('--read-only-config')).toBe('read only config')
  })

  it('handles values without the -- prefix', () => {
    // Even though these are radio-button values that typically DO
    // have the prefix, the function should be resilient.
    expect(prettifyFlag('overlays')).toBe('overlays')
  })

  it('coerces non-strings to strings', () => {
    // Defensive: DOM values are always strings, but callers might
    // pass numbers or booleans by accident.
    expect(prettifyFlag(42)).toBe('42')
  })
})

// ---------------------------------------------------------------------
// updateSectionStyleHeaderBadge
// ---------------------------------------------------------------------

describe('updateSectionStyleHeaderBadge', () => {
  it('renders the formatted label from formatHeaderStyleLabel', () => {
    const el = installBadge('header-style-rollup-badge')
    // formatHeaderStyleLabel('kometa') => 'Kometa' (see _util.js tests)
    updateSectionStyleHeaderBadge('kometa')
    expect(el.textContent).toBe('Kometa')
    expect(el.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('renders the underlying util\'s empty-input fallback', () => {
    // formatHeaderStyleLabel('') returns 'Single line' (not empty),
    // so the || 'Active' fallback in the badge function is actually
    // dead code today. Documenting the observed behavior anyway so
    // if the util's fallback ever changes we notice here.
    const el = installBadge('header-style-rollup-badge')
    updateSectionStyleHeaderBadge('')
    expect(el.textContent).toBe('Single line')
  })
})

// ---------------------------------------------------------------------
// updateModeHeaderBadge
// ---------------------------------------------------------------------

describe('updateModeHeaderBadge', () => {
  it('shows "CLI labels" (ok) when the show-cli-toggle is checked', () => {
    document.body.innerHTML = '<input type="checkbox" id="show-cli-toggle" checked />'
    const badge = installBadge('heading-mode-rollup-badge')
    updateModeHeaderBadge()
    expect(badge.textContent).toBe('CLI labels')
    expect(badge.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('shows "Friendly" (unknown) when the toggle is unchecked', () => {
    document.body.innerHTML = '<input type="checkbox" id="show-cli-toggle" />'
    const badge = installBadge('heading-mode-rollup-badge')
    updateModeHeaderBadge()
    expect(badge.textContent).toBe('Friendly')
    expect(badge.classList.contains('qs-validation-rollup-badge--unknown')).toBe(true)
  })

  it('shows "Friendly" (unknown) when the toggle element is missing', () => {
    const badge = installBadge('heading-mode-rollup-badge')
    updateModeHeaderBadge()
    expect(badge.textContent).toBe('Friendly')
  })
})

// ---------------------------------------------------------------------
// updateRunOptionHeaderBadge
// ---------------------------------------------------------------------

describe('updateRunOptionHeaderBadge', () => {
  // Helper: build the DOM shape this function reads (a radio group +
  // a library <select> + a times <input>).
  function installRunOptionDom (checkedValue, libraryValues = [], timesValue = '') {
    document.body.innerHTML = `
      <input type="radio" name="run-option" value="--run" ${checkedValue === '--run' ? 'checked' : ''} />
      <input type="radio" name="run-option" value="--run-libraries" ${checkedValue === '--run-libraries' ? 'checked' : ''} />
      <input type="radio" name="run-option" value="--times" ${checkedValue === '--times' ? 'checked' : ''} />
      <input type="radio" name="run-option" value="" ${checkedValue === '' ? 'checked' : ''} />
      <select id="library-multiselect" multiple>
        <option value="Movies">Movies</option>
        <option value="TV Shows">TV Shows</option>
        <option value="Anime">Anime</option>
      </select>
      <input type="text" id="times-input" value="${timesValue}" />
      <div id="plex-maintenance-window" data-window=""></div>
    `
    const select = document.getElementById('library-multiselect')
    libraryValues.forEach(v => {
      const opt = Array.from(select.options).find(o => o.value === v)
      if (opt) opt.selected = true
    })
    installBadge('heading-runopt-rollup-badge')
  }

  it('--run: shows "Run now" (ok)', () => {
    installRunOptionDom('--run')
    updateRunOptionHeaderBadge()
    const badge = document.getElementById('heading-runopt-rollup-badge')
    expect(badge.textContent).toBe('Run now')
    expect(badge.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('--run-libraries with no libraries selected: shows "Libraries needed" (warn)', () => {
    installRunOptionDom('--run-libraries', [])
    updateRunOptionHeaderBadge()
    const badge = document.getElementById('heading-runopt-rollup-badge')
    expect(badge.textContent).toBe('Libraries needed')
    expect(badge.classList.contains('qs-validation-rollup-badge--warn')).toBe(true)
  })

  it('--run-libraries with 2 libraries: shows count (ok)', () => {
    installRunOptionDom('--run-libraries', ['Movies', 'TV Shows'])
    updateRunOptionHeaderBadge()
    const badge = document.getElementById('heading-runopt-rollup-badge')
    expect(badge.textContent).toBe('2 libraries')
    expect(badge.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('--times with empty input: shows "Times needed" (warn)', () => {
    installRunOptionDom('--times', [], '')
    updateRunOptionHeaderBadge()
    const badge = document.getElementById('heading-runopt-rollup-badge')
    expect(badge.textContent).toBe('Times needed')
    expect(badge.classList.contains('qs-validation-rollup-badge--warn')).toBe(true)
  })

  it('--times with valid input: shows "Times set" (ok)', () => {
    installRunOptionDom('--times', [], '05:00|17:00')
    updateRunOptionHeaderBadge()
    const badge = document.getElementById('heading-runopt-rollup-badge')
    expect(badge.textContent).toBe('Times set')
    expect(badge.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('--times inside maintenance: shows "Maintenance overlap" (error)', () => {
    installRunOptionDom('--times', [], '05:00|17:00')
    document.getElementById('plex-maintenance-window').dataset.window = '04:00–06:00'
    updateRunOptionHeaderBadge()
    const badge = document.getElementById('heading-runopt-rollup-badge')
    expect(badge.textContent).toBe('Maintenance overlap')
    expect(badge.classList.contains('qs-validation-rollup-badge--error')).toBe(true)
  })

  it('--times with garbage input: shows "Invalid times" (error)', () => {
    installRunOptionDom('--times', [], 'not-a-time')
    updateRunOptionHeaderBadge()
    const badge = document.getElementById('heading-runopt-rollup-badge')
    expect(badge.textContent).toBe('Invalid times')
    expect(badge.classList.contains('qs-validation-rollup-badge--error')).toBe(true)
  })

  it('scheduled default (empty option): shows "Scheduled" (unknown)', () => {
    installRunOptionDom('')
    updateRunOptionHeaderBadge()
    const badge = document.getElementById('heading-runopt-rollup-badge')
    expect(badge.textContent).toBe('Scheduled')
    expect(badge.classList.contains('qs-validation-rollup-badge--unknown')).toBe(true)
  })

  it('scheduled default inside maintenance: shows "Maintenance overlap" (error)', () => {
    installRunOptionDom('')
    document.getElementById('plex-maintenance-window').dataset.window = '04:00–06:00'
    updateRunOptionHeaderBadge()
    const badge = document.getElementById('heading-runopt-rollup-badge')
    expect(badge.textContent).toBe('Maintenance overlap')
    expect(badge.classList.contains('qs-validation-rollup-badge--error')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// updateModeFlagsHeaderBadge  +  updateLogFlagsHeaderBadge
// ---------------------------------------------------------------------
//
// These two functions have the same shape (radio group -> prettified
// label) so we test them side-by-side to keep the tests DRY.

describe('updateModeFlagsHeaderBadge', () => {
  it('shows the prettified flag name (ok) when a radio is checked', () => {
    document.body.innerHTML = `
      <input type="radio" name="mode-flag" value="--collections" checked />
      <input type="radio" name="mode-flag" value="--overlays" />
    `
    installBadge('heading-modeflags-rollup-badge')
    updateModeFlagsHeaderBadge()
    const badge = document.getElementById('heading-modeflags-rollup-badge')
    expect(badge.textContent).toBe('collections')
    expect(badge.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('shows "Default" (unknown) when no radio has value or none selected', () => {
    document.body.innerHTML = `
      <input type="radio" name="mode-flag" value="" checked />
    `
    installBadge('heading-modeflags-rollup-badge')
    updateModeFlagsHeaderBadge()
    const badge = document.getElementById('heading-modeflags-rollup-badge')
    expect(badge.textContent).toBe('Default')
    expect(badge.classList.contains('qs-validation-rollup-badge--unknown')).toBe(true)
  })
})

describe('updateLogFlagsHeaderBadge', () => {
  it('shows the prettified flag name (ok) when debug is selected', () => {
    document.body.innerHTML = `
      <input type="radio" name="log-flag" value="--debug" checked />
    `
    installBadge('heading-logflags-rollup-badge')
    updateLogFlagsHeaderBadge()
    const badge = document.getElementById('heading-logflags-rollup-badge')
    expect(badge.textContent).toBe('debug')
    expect(badge.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('shows "Default" (unknown) with no selection', () => {
    installBadge('heading-logflags-rollup-badge')
    updateLogFlagsHeaderBadge()
    const badge = document.getElementById('heading-logflags-rollup-badge')
    expect(badge.textContent).toBe('Default')
  })
})

// ---------------------------------------------------------------------
// updateValidationFlagsHeaderBadge
// ---------------------------------------------------------------------

describe('updateValidationFlagsHeaderBadge', () => {
  function installValidationFlagsDom (mode = '', filePath = '', dirPath = '') {
    document.body.innerHTML = `
      <input type="radio" name="validate-mode" value="" ${mode === '' ? 'checked' : ''}>
      <input type="radio" name="validate-mode" value="--validate" ${mode === '--validate' ? 'checked' : ''}>
      <input type="radio" name="validate-mode" value="--validate-file" ${mode === '--validate-file' ? 'checked' : ''}>
      <input type="radio" name="validate-mode" value="--validate-dir" ${mode === '--validate-dir' ? 'checked' : ''}>
      <input id="opt-validate-file-val" value="${filePath}">
      <input id="opt-validate-dir-val" value="${dirPath}">
    `
    installBadge('heading-validationflags-rollup-badge')
  }

  it('shows Default when no validation mode is selected', () => {
    installValidationFlagsDom('')
    updateValidationFlagsHeaderBadge()
    const badge = document.getElementById('heading-validationflags-rollup-badge')
    expect(badge.textContent).toBe('Default')
    expect(badge.classList.contains('qs-validation-rollup-badge--unknown')).toBe(true)
  })

  it('shows Validate Config when config validation is selected', () => {
    installValidationFlagsDom('--validate')
    updateValidationFlagsHeaderBadge()
    const badge = document.getElementById('heading-validationflags-rollup-badge')
    expect(badge.textContent).toBe('Validate Config')
    expect(badge.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('warns when validate-file is selected without a path', () => {
    installValidationFlagsDom('--validate-file')
    updateValidationFlagsHeaderBadge()
    const badge = document.getElementById('heading-validationflags-rollup-badge')
    expect(badge.textContent).toBe('File needed')
    expect(badge.classList.contains('qs-validation-rollup-badge--warn')).toBe(true)
  })

  it('shows Validate Directory when validate-dir has a path', () => {
    installValidationFlagsDom('--validate-dir', '', '/data/configs')
    updateValidationFlagsHeaderBadge()
    const badge = document.getElementById('heading-validationflags-rollup-badge')
    expect(badge.textContent).toBe('Validate Directory')
    expect(badge.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// updateOtherFlagsHeaderBadge
// ---------------------------------------------------------------------

describe('updateOtherFlagsHeaderBadge', () => {
  // Helper: build the checkbox grid this function walks
  function installOtherFlagsDom (opts = {}) {
    const flags = [
      'delete-collections', 'delete-labels', 'read-only-config', 'low-priority',
      'no-report', 'no-missing', 'no-countdown', 'ignore-ghost',
      'ignore-schedules', 'no-verify-ssl', 'tests',
      'timeout', 'divider', 'width'
    ]
    const html = flags.map(f =>
      `<input type="checkbox" id="opt-${f}" ${opts[f] ? 'checked' : ''} />`
    ).join('')
    document.body.innerHTML = html
    installBadge('heading-otherflags-rollup-badge')
  }

  it('shows "Default" (unknown) when no flags are checked', () => {
    installOtherFlagsDom({})
    updateOtherFlagsHeaderBadge()
    const badge = document.getElementById('heading-otherflags-rollup-badge')
    expect(badge.textContent).toBe('Default')
    expect(badge.classList.contains('qs-validation-rollup-badge--unknown')).toBe(true)
  })

  it('counts a single core flag correctly', () => {
    installOtherFlagsDom({ 'delete-collections': true })
    updateOtherFlagsHeaderBadge()
    const badge = document.getElementById('heading-otherflags-rollup-badge')
    expect(badge.textContent).toBe('1 enabled')
    expect(badge.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('counts multiple core flags', () => {
    installOtherFlagsDom({
      'delete-collections': true,
      'no-report': true,
      'ignore-schedules': true
    })
    updateOtherFlagsHeaderBadge()
    const badge = document.getElementById('heading-otherflags-rollup-badge')
    expect(badge.textContent).toBe('3 enabled')
  })

  it('counts extras (timeout/divider/width) alongside core flags', () => {
    installOtherFlagsDom({
      'delete-collections': true,
      timeout: true,
      divider: true
    })
    updateOtherFlagsHeaderBadge()
    const badge = document.getElementById('heading-otherflags-rollup-badge')
    expect(badge.textContent).toBe('3 enabled')
  })

  it('counts all three extras when nothing else is set', () => {
    installOtherFlagsDom({
      timeout: true,
      divider: true,
      width: true
    })
    updateOtherFlagsHeaderBadge()
    const badge = document.getElementById('heading-otherflags-rollup-badge')
    expect(badge.textContent).toBe('3 enabled')
  })

  it('counts all 11 core flags + 3 extras when everything is on', () => {
    // Full-house: verifies the two counting paths sum correctly
    installOtherFlagsDom({
      'delete-collections': true, 'delete-labels': true, 'read-only-config': true,
      'low-priority': true, 'no-report': true, 'no-missing': true,
      'no-countdown': true, 'ignore-ghost': true, 'ignore-schedules': true,
      'no-verify-ssl': true, tests: true,
      timeout: true, divider: true, width: true
    })
    updateOtherFlagsHeaderBadge()
    const badge = document.getElementById('heading-otherflags-rollup-badge')
    expect(badge.textContent).toBe('14 enabled')
  })
})

// ---------------------------------------------------------------------
// State-consulting: updateConfigOutputHeaderBadges
// ---------------------------------------------------------------------

describe('updateConfigOutputHeaderBadges', () => {
  beforeEach(() => {
    kometaState.showYAML = false
  })

  it('shows "No YAML" when the textarea is missing', () => {
    installBadge('config-output-lines-badge')
    installBadge('config-output-rollup-badge')
    updateConfigOutputHeaderBadges()
    expect(document.getElementById('config-output-rollup-badge').textContent).toBe('No YAML')
    expect(document.getElementById('config-output-rollup-badge').classList.contains('qs-validation-rollup-badge--unknown')).toBe(true)
  })

  it('shows "No YAML" when the textarea has only whitespace', () => {
    const t = document.createElement('textarea')
    t.id = 'final-yaml'
    t.value = '   \n  \t  '
    document.body.appendChild(t)
    installBadge('config-output-lines-badge')
    installBadge('config-output-rollup-badge')
    updateConfigOutputHeaderBadges()
    expect(document.getElementById('config-output-rollup-badge').textContent).toBe('No YAML')
  })

  it('shows line count + "Validated" (ok) when showYAML is true', () => {
    const t = document.createElement('textarea')
    t.id = 'final-yaml'
    t.value = 'libraries:\n  Movies:\n    metadata_path: []'
    document.body.appendChild(t)
    installBadge('config-output-lines-badge')
    installBadge('config-output-rollup-badge')
    kometaState.showYAML = true
    updateConfigOutputHeaderBadges()
    expect(document.getElementById('config-output-lines-badge').textContent).toBe('3 lines')
    expect(document.getElementById('config-output-rollup-badge').textContent).toBe('Validated')
    expect(document.getElementById('config-output-rollup-badge').classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('shows "Needs fixes" (error) when YAML present but showYAML is false', () => {
    const t = document.createElement('textarea')
    t.id = 'final-yaml'
    t.value = 'broken:\n  yaml'
    document.body.appendChild(t)
    installBadge('config-output-lines-badge')
    installBadge('config-output-rollup-badge')
    kometaState.showYAML = false
    updateConfigOutputHeaderBadges()
    expect(document.getElementById('config-output-rollup-badge').textContent).toBe('Needs fixes')
    expect(document.getElementById('config-output-rollup-badge').classList.contains('qs-validation-rollup-badge--error')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// State-consulting: updateRunCommandHeaderBadge (five-way state machine)
// ---------------------------------------------------------------------

describe('updateRunCommandHeaderBadge', () => {
  // Reset the whole state slice this function reads. beforeEach
  // matters here because tests intentionally flip one flag at a time.
  beforeEach(() => {
    kometaState.showYAML = false
    kometaState.kometaValidated = false
    kometaState.kometaValidationInProgress = false
    kometaState.kometaUpdating = false
    kometaState.kometaStatus = null
    installBadge('run-command-rollup-badge')
  })

  it('shows "Fix validation" (error) when showYAML is false [highest priority]', () => {
    // All other flags could be favorable; showYAML=false still wins.
    kometaState.kometaValidated = true
    kometaState.kometaStatus = 'idle'
    updateRunCommandHeaderBadge()
    const b = document.getElementById('run-command-rollup-badge')
    expect(b.textContent).toBe('Fix validation')
    expect(b.classList.contains('qs-validation-rollup-badge--error')).toBe(true)
  })

  it('shows "Checking Kometa" (unknown) when validationInProgress is true', () => {
    kometaState.showYAML = true
    kometaState.kometaValidationInProgress = true
    updateRunCommandHeaderBadge()
    expect(document.getElementById('run-command-rollup-badge').textContent).toBe('Checking Kometa')
  })

  it('shows "Updating Kometa" (unknown) when kometaUpdating is true', () => {
    kometaState.showYAML = true
    kometaState.kometaUpdating = true
    updateRunCommandHeaderBadge()
    expect(document.getElementById('run-command-rollup-badge').textContent).toBe('Updating Kometa')
  })

  it('shows "Validate Kometa" (warn) when validated is false [and no in-progress]', () => {
    kometaState.showYAML = true
    kometaState.kometaValidated = false
    updateRunCommandHeaderBadge()
    const b = document.getElementById('run-command-rollup-badge')
    expect(b.textContent).toBe('Validate Kometa')
    expect(b.classList.contains('qs-validation-rollup-badge--warn')).toBe(true)
  })

  it("shows \"Run in progress\" (warn) when kometaStatus is 'running'", () => {
    kometaState.showYAML = true
    kometaState.kometaValidated = true
    kometaState.kometaStatus = 'running'
    updateRunCommandHeaderBadge()
    expect(document.getElementById('run-command-rollup-badge').textContent).toBe('Run in progress')
  })

  it('shows "Ready" (ok) when everything passes and run command is valid', () => {
    kometaState.showYAML = true
    kometaState.kometaValidated = true
    // Install a valid run-command-output so isRunCommandValid() returns true
    const out = document.createElement('div')
    out.id = 'run-command-output'
    out.textContent = 'python kometa.py --config config.yml'
    document.body.appendChild(out)
    updateRunCommandHeaderBadge()
    const b = document.getElementById('run-command-rollup-badge')
    expect(b.textContent).toBe('Ready')
    expect(b.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('shows "Incomplete" (warn) when everything passes but run command is placeholder', () => {
    kometaState.showYAML = true
    kometaState.kometaValidated = true
    const out = document.createElement('div')
    out.id = 'run-command-output'
    out.textContent = '?? no root ??'
    document.body.appendChild(out)
    updateRunCommandHeaderBadge()
    expect(document.getElementById('run-command-rollup-badge').textContent).toBe('Incomplete')
  })
})

// ---------------------------------------------------------------------
// State-consulting: updateLogscanHeaderBadge
// ---------------------------------------------------------------------

describe('updateLogscanHeaderBadge', () => {
  beforeEach(() => {
    kometaState.lastLogscanPayload = null
    installBadge('logscan-rollup-badge')
  })

  it('shows "Pending" (unknown) when no data available', () => {
    updateLogscanHeaderBadge()
    const b = document.getElementById('logscan-rollup-badge')
    expect(b.textContent).toBe('Pending')
    expect(b.classList.contains('qs-validation-rollup-badge--unknown')).toBe(true)
  })

  it('reads from kometaState.lastLogscanPayload when no arg is passed', () => {
    kometaState.lastLogscanPayload = { recommendations: [1, 2], missing_people: [] }
    updateLogscanHeaderBadge()
    expect(document.getElementById('logscan-rollup-badge').textContent).toBe('2 items')
  })

  it('passed data arg WINS over kometaState.lastLogscanPayload', () => {
    kometaState.lastLogscanPayload = { recommendations: [1, 2, 3] }
    updateLogscanHeaderBadge({ recommendations: [], missing_people: [] })
    expect(document.getElementById('logscan-rollup-badge').textContent).toBe('No issues')
  })

  it('shows "Unavailable" (error) when payload has an error field', () => {
    updateLogscanHeaderBadge({ error: 'boom' })
    const b = document.getElementById('logscan-rollup-badge')
    expect(b.textContent).toBe('Unavailable')
    expect(b.classList.contains('qs-validation-rollup-badge--error')).toBe(true)
  })

  it('shows "No issues" (ok) for empty recs+missing arrays', () => {
    updateLogscanHeaderBadge({ recommendations: [], missing_people: [] })
    const b = document.getElementById('logscan-rollup-badge')
    expect(b.textContent).toBe('No issues')
    expect(b.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('sums recommendations + missing_people counts', () => {
    updateLogscanHeaderBadge({ recommendations: [1, 2, 3], missing_people: [4, 5] })
    expect(document.getElementById('logscan-rollup-badge').textContent).toBe('5 items')
  })

  it('handles missing/non-array recommendations gracefully', () => {
    updateLogscanHeaderBadge({ missing_people: [1] })
    expect(document.getElementById('logscan-rollup-badge').textContent).toBe('1 items')
  })
})

// ---------------------------------------------------------------------
// Orchestrator: syncFinalAccordionRollups
// ---------------------------------------------------------------------

describe('syncFinalAccordionRollups', () => {
  beforeEach(() => {
    // Install all badges the orchestrator touches
    installBadge('heading-style-rollup-badge')
    installBadge('heading-mode-rollup-badge')
    installBadge('heading-runopt-rollup-badge')
    installBadge('heading-modeflags-rollup-badge')
    installBadge('heading-logflags-rollup-badge')
    installBadge('heading-validationflags-rollup-badge')
    installBadge('heading-otherflags-rollup-badge')
    installBadge('config-output-lines-badge')
    installBadge('config-output-rollup-badge')
    installBadge('run-command-rollup-badge')
    installBadge('logscan-rollup-badge')
    // The branch rollup badge is written by syncKometaBranchRollupBadge
    // (imported from _kometaBranch.js). The DOM contract there requires
    // BOTH the badge element AND the #kometa-branch-override <select>
    // to exist (the badge reads the current override).
    const badgeEl = document.createElement('span')
    badgeEl.id = 'kometa-branch-rollup-badge'
    document.body.appendChild(badgeEl)
    const overrideSel = document.createElement('select')
    overrideSel.id = 'kometa-branch-override'
    const emptyOpt = document.createElement('option')
    emptyOpt.value = ''
    overrideSel.appendChild(emptyOpt)
    overrideSel.value = ''
    document.body.appendChild(overrideSel)
  })

  it('takes no arguments (retired callbacks-bag API)', () => {
    // Post-#1569 the orchestrator no longer accepts callbacks;
    // syncKometaBranchRollupBadge is imported directly from
    // _kometaBranch.js. Passing an argument should be harmless
    // (ignored) but the canonical call is no-args.
    expect(() => syncFinalAccordionRollups()).not.toThrow()
  })

  it('refreshes every rollup badge on the page (touches all 11 ids)', () => {
    // Pre-mark every badge with a sentinel string. After the call,
    // every badge must have been rewritten (i.e. not equal to the
    // sentinel).
    const ids = [
      'heading-mode-rollup-badge',
      'heading-runopt-rollup-badge',
      'heading-modeflags-rollup-badge',
      'heading-logflags-rollup-badge',
      'heading-validationflags-rollup-badge',
      'heading-otherflags-rollup-badge',
      'config-output-lines-badge',
      'config-output-rollup-badge',
      'run-command-rollup-badge',
      'logscan-rollup-badge',
      'kometa-branch-rollup-badge'
    ]
    for (const id of ids) document.getElementById(id).textContent = 'SENTINEL'
    syncFinalAccordionRollups()
    for (const id of ids) {
      expect(document.getElementById(id).textContent).not.toBe('SENTINEL')
    }
  })
})
