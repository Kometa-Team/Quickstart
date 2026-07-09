// Tests for static/local-js/modules/arrPageBase.js
//
// Two exports:
//   - populateArrDropdown(elementId, data, valueField, textField, initialGlobalName)
//     Thin wrapper over populateDropdown that safely reads a window
//     global for pre-selection.
//
//   - buildArrPreSubmit({ validatedFieldId, statusMessageId, dropdowns,
//                          skipWhenUnvalidated, pathErrorMessage })
//     Returns a form-submit gate function.
//
// COVERAGE STRATEGY:
//
//   populateArrDropdown (7):
//     - passes through to populateDropdown correctly
//     - safe when initialGlobalName is missing / undefined / empty
//     - uses global value when set
//     - handles null/undefined data (from populateDropdown)
//     - doesn't crash on missing element
//     - handles non-string initialGlobalName gracefully
//     - each call reads global at call time (not cached)
//
//   buildArrPreSubmit (many, grouped):
//
//     Config validation (2):
//       - throws without validatedFieldId
//       - throws without dropdowns array
//
//     skipWhenUnvalidated=true (Radarr shape) (3):
//       - unvalidated + invalid paths -> returns true (skip)
//       - unvalidated + missing dropdowns -> returns true (skip)
//       - validated -> proceeds with normal checks
//
//     skipWhenUnvalidated=false (escape-hatch shape, historically Sonarr) (3):
//       - unvalidated + invalid paths -> returns false (blocks)
//       - unvalidated + empty dropdowns -> returns true (dropdowns
//         only checked when validated)
//       - validated -> proceeds with normal checks
//
//     Dropdown checks (4):
//       - all filled -> no dropdown errors
//       - one empty -> one error in correct order
//       - all empty -> errors in declaration order
//       - missing element treated as empty
//
//     Path validation (4):
//       - PathValidation missing entirely -> passes
//       - PathValidation.validateAll missing -> passes
//       - validateAll returns true -> no error
//       - validateAll returns false -> error added
//
//     Status message rendering (3):
//       - status message shown with combined errors
//       - status message hidden when no errors
//       - graceful when status element missing
//
//     Custom overrides (3):
//       - custom statusMessageId used
//       - custom pathErrorMessage used
//       - defaults applied when overrides omitted

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  populateArrDropdown,
  buildArrPreSubmit
} from '../../../static/local-js/modules/arrPageBase.js'

// ---------------------------------------------------------------------
// populateArrDropdown
// ---------------------------------------------------------------------

describe('populateArrDropdown', () => {
  beforeEach(() => {
    document.body.innerHTML = '<select id="d"></select>'
    delete window.testInitialValue
    delete window.otherGlobal
  })

  afterEach(() => {
    document.body.innerHTML = ''
    delete window.testInitialValue
    delete window.otherGlobal
  })

  it("populates the dropdown from data and pre-selects the global value", () => {
    window.testInitialValue = '/b'
    populateArrDropdown('d', [{ p: '/a' }, { p: '/b' }, { p: '/c' }], 'p', 'p', 'testInitialValue')
    expect(document.getElementById('d').value).toBe('/b')
  })

  it("falls back to empty string when the global is undefined", () => {
    populateArrDropdown('d', [{ p: '/a' }], 'p', 'p', 'neverDefined')
    // Value stays as placeholder (empty)
    expect(document.getElementById('d').value).toBe('')
    // But the option is present
    expect(document.getElementById('d').children.length).toBe(2)
  })

  it("falls back to empty string when initialGlobalName is empty string", () => {
    populateArrDropdown('d', [{ p: '/a' }], 'p', 'p', '')
    expect(document.getElementById('d').value).toBe('')
  })

  it("falls back to empty string when initialGlobalName is undefined", () => {
    populateArrDropdown('d', [{ p: '/a' }], 'p', 'p', undefined)
    expect(document.getElementById('d').value).toBe('')
  })

  it("handles null data (passes through to populateDropdown)", () => {
    // Should not throw; leaves just the placeholder.
    expect(() => populateArrDropdown('d', null, 'p', 'p', 'testInitialValue')).not.toThrow()
    expect(document.getElementById('d').children.length).toBe(1)
  })

  it("does not throw when the element is missing", () => {
    expect(() => populateArrDropdown('nonexistent', [{ p: 'x' }], 'p', 'p', 'testInitialValue')).not.toThrow()
  })

  it("reads the global at call time, not at import time", () => {
    // Call once with global unset:
    populateArrDropdown('d', [{ p: '/a' }, { p: '/b' }], 'p', 'p', 'testInitialValue')
    expect(document.getElementById('d').value).toBe('')

    // Now set it and re-populate:
    window.testInitialValue = '/b'
    populateArrDropdown('d', [{ p: '/a' }, { p: '/b' }], 'p', 'p', 'testInitialValue')
    expect(document.getElementById('d').value).toBe('/b')
  })
})

// ---------------------------------------------------------------------
// buildArrPreSubmit
// ---------------------------------------------------------------------

function installArrFixture () {
  document.body.innerHTML = `
    <input type="hidden" id="thing_validated" value="false">
    <select id="dropdown_one"><option value="">--</option></select>
    <select id="dropdown_two"><option value="">--</option></select>
    <select id="dropdown_three"><option value="">--</option></select>
    <div id="statusMessage" style="display:none"></div>
    <div id="customStatus" style="display:none"></div>
  `
}

function setValidated (value) {
  document.getElementById('thing_validated').value = value ? 'true' : 'false'
}

function pickDropdown (id, value) {
  const el = document.getElementById(id)
  const option = document.createElement('option')
  option.value = value
  option.textContent = value
  el.appendChild(option)
  el.value = value
}

const DEFAULT_DROPDOWNS = [
  { elementId: 'dropdown_one', errorMessage: 'Pick one!' },
  { elementId: 'dropdown_two', errorMessage: 'Pick two!' }
]

describe('buildArrPreSubmit -- config validation', () => {
  it("throws without validatedFieldId", () => {
    expect(() => buildArrPreSubmit({ dropdowns: DEFAULT_DROPDOWNS })).toThrow(/validatedFieldId/)
  })

  it("throws when dropdowns is not an array", () => {
    expect(() => buildArrPreSubmit({ validatedFieldId: 'thing_validated', dropdowns: 'nope' })).toThrow(/dropdowns/)
  })
})

describe('buildArrPreSubmit -- skipWhenUnvalidated=true (Radarr shape)', () => {
  beforeEach(installArrFixture)
  afterEach(() => { document.body.innerHTML = ''; delete window.PathValidation })

  it("returns true when unvalidated, ignoring bad paths and empty dropdowns", () => {
    window.PathValidation = { validateAll: () => false }  // paths invalid
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    setValidated(false)
    expect(gate()).toBe(true)
    // Status message NOT shown because we short-circuited entirely.
    expect(document.getElementById('statusMessage').style.display).toBe('none')
  })

  it("returns true when unvalidated even with empty dropdowns", () => {
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    setValidated(false)
    expect(gate()).toBe(true)
  })

  it("proceeds with checks when validated", () => {
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    setValidated(true)
    // Both dropdowns empty -> should block
    expect(gate()).toBe(false)
  })
})

describe('buildArrPreSubmit -- skipWhenUnvalidated=false (escape-hatch shape)', () => {
  beforeEach(installArrFixture)
  afterEach(() => { document.body.innerHTML = ''; delete window.PathValidation })

  it("returns false when unvalidated + paths invalid (path check runs)", () => {
    window.PathValidation = { validateAll: () => false }
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: false
    })
    setValidated(false)
    expect(gate()).toBe(false)  // path check runs regardless of validated flag
    expect(document.getElementById('statusMessage').style.display).toBe('block')
    expect(document.getElementById('statusMessage').textContent).toContain('path')
  })

  it("returns true when unvalidated + valid paths (dropdowns not checked)", () => {
    window.PathValidation = { validateAll: () => true }
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: false
    })
    setValidated(false)
    // Dropdowns empty but not checked because !validated; paths OK -> allow.
    expect(gate()).toBe(true)
  })

  it("proceeds normally when validated (same as Radarr shape)", () => {
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: false
    })
    setValidated(true)
    expect(gate()).toBe(false)  // empty dropdowns -> blocks
  })
})

describe('buildArrPreSubmit -- dropdown checks (validated user)', () => {
  beforeEach(() => {
    installArrFixture()
    setValidated(true)
  })
  afterEach(() => { document.body.innerHTML = ''; delete window.PathValidation })

  it("no errors when all dropdowns filled", () => {
    pickDropdown('dropdown_one', '/first')
    pickDropdown('dropdown_two', '/second')
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    expect(gate()).toBe(true)
  })

  it("one empty dropdown -> one error", () => {
    pickDropdown('dropdown_one', '/first')
    // dropdown_two stays empty
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    expect(gate()).toBe(false)
    const status = document.getElementById('statusMessage')
    expect(status.textContent).toContain('Pick two!')
    expect(status.textContent).not.toContain('Pick one!')
  })

  it("errors render in declaration order", () => {
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: [
        { elementId: 'dropdown_one', errorMessage: 'ALPHA' },
        { elementId: 'dropdown_two', errorMessage: 'BETA' },
        { elementId: 'dropdown_three', errorMessage: 'GAMMA' }
      ],
      skipWhenUnvalidated: true
    })
    expect(gate()).toBe(false)
    const text = document.getElementById('statusMessage').textContent
    // ALPHA appears before BETA appears before GAMMA
    expect(text.indexOf('ALPHA')).toBeLessThan(text.indexOf('BETA'))
    expect(text.indexOf('BETA')).toBeLessThan(text.indexOf('GAMMA'))
  })

  it("missing dropdown element counts as empty (error added)", () => {
    document.getElementById('dropdown_two').remove()
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    // dropdown_one still empty + dropdown_two missing -> 2 errors
    expect(gate()).toBe(false)
    const text = document.getElementById('statusMessage').textContent
    expect(text).toContain('Pick one!')
    expect(text).toContain('Pick two!')
  })
})

describe('buildArrPreSubmit -- path validation', () => {
  beforeEach(() => {
    installArrFixture()
    setValidated(true)
    pickDropdown('dropdown_one', '/x')
    pickDropdown('dropdown_two', '/y')
  })
  afterEach(() => { document.body.innerHTML = ''; delete window.PathValidation })

  it("PathValidation missing entirely -> passes (no error)", () => {
    delete window.PathValidation
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    expect(gate()).toBe(true)
  })

  it("PathValidation without validateAll -> passes (no error)", () => {
    window.PathValidation = {}  // no validateAll fn
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    expect(gate()).toBe(true)
  })

  it("validateAll=true -> no error", () => {
    window.PathValidation = { validateAll: () => true }
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    expect(gate()).toBe(true)
  })

  it("validateAll=false -> path error added", () => {
    window.PathValidation = { validateAll: () => false }
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    expect(gate()).toBe(false)
    expect(document.getElementById('statusMessage').textContent).toContain('path')
  })
})

describe('buildArrPreSubmit -- status message rendering', () => {
  beforeEach(() => {
    installArrFixture()
    setValidated(true)
  })
  afterEach(() => { document.body.innerHTML = '' })

  it("shows message with combined errors and red color", () => {
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    expect(gate()).toBe(false)
    const status = document.getElementById('statusMessage')
    expect(status.style.display).toBe('block')
    expect(status.style.color).toBe('rgb(234, 134, 143)')  // #ea868f
  })

  it("hides message when no errors", () => {
    pickDropdown('dropdown_one', '/x')
    pickDropdown('dropdown_two', '/y')
    const status = document.getElementById('statusMessage')
    status.style.display = 'block'  // stale from a previous submit
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    expect(gate()).toBe(true)
    expect(status.style.display).toBe('none')
  })

  it("no crash when status element missing", () => {
    document.getElementById('statusMessage').remove()
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    // Should still return false; just can't render the message.
    expect(() => gate()).not.toThrow()
    expect(gate()).toBe(false)
  })
})

describe('buildArrPreSubmit -- custom overrides', () => {
  beforeEach(() => {
    installArrFixture()
    setValidated(true)
  })
  afterEach(() => { document.body.innerHTML = '' })

  it("uses custom statusMessageId", () => {
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      statusMessageId: 'customStatus',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    expect(gate()).toBe(false)
    expect(document.getElementById('customStatus').style.display).toBe('block')
    expect(document.getElementById('statusMessage').style.display).toBe('none')  // untouched
  })

  it("uses custom pathErrorMessage", () => {
    window.PathValidation = { validateAll: () => false }
    pickDropdown('dropdown_one', '/x')
    pickDropdown('dropdown_two', '/y')
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true,
      pathErrorMessage: 'CUSTOM PATH WARNING'
    })
    expect(gate()).toBe(false)
    expect(document.getElementById('statusMessage').textContent).toContain('CUSTOM PATH WARNING')
    delete window.PathValidation
  })

  it("uses default statusMessageId and pathErrorMessage when omitted", () => {
    window.PathValidation = { validateAll: () => false }
    pickDropdown('dropdown_one', '/x')
    pickDropdown('dropdown_two', '/y')
    const gate = buildArrPreSubmit({
      validatedFieldId: 'thing_validated',
      dropdowns: DEFAULT_DROPDOWNS,
      skipWhenUnvalidated: true
    })
    expect(gate()).toBe(false)
    expect(document.getElementById('statusMessage').textContent).toContain('Please fix invalid path fields')
    delete window.PathValidation
  })
})
