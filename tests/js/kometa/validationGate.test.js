// Tests for static/local-js/modules/kometa/_validationGate.js
//
// Two exported functions:
//   getFinalGateState   -- reads #final-gate-state data-* attrs
//   updateValidationGate -- big orchestration: reads gate state +
//                          per-page validation flags, mutates
//                          kometaState.showYAML, toggles a swarm of
//                          .d-none classes, calls the two extension
//                          callbacks.
//
// COVERAGE STRATEGY:
//
//   For getFinalGateState:
//     - missing element -> conservative default
//     - populated element -> reads all fields correctly
//     - defaults when data-* attrs are missing
//     - boolean fields interpret 'true' string as true
//
//   For updateValidationGate we test each BRANCH of the gate:
//     Path A: stage='todo'      -> everything hidden, showYAML=false
//     Path B: stage='freshness' -> same as todo
//     Path C: stage='config' + configValid=true -> everything shown
//     Path D: stage='config' + all 5 flags true -> everything shown
//     Path E: stage='config' + some flags missing -> validation msgs
//     Path F: stage='config' + configValid + msg element missing (soft)
//     Path G: callbacks are always invoked exactly once
//     Path H: kometaState.showYAML is correctly toggled per branch
//     Path I: run-now button label defaults to 'Run Now' in all branches

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import {
  getFinalGateState,
  updateValidationGate
} from '../../../static/local-js/modules/kometa/_validationGate.js'

// ---------------------------------------------------------------------
// Fixture DOM helpers
// ---------------------------------------------------------------------

/**
 * Build a DOM matching the pieces updateValidationGate touches. All
 * optional; omit for a bare-page test.
 *
 * gate options mirror the data-* attrs on #final-gate-state.
 * flags optional per-page validation flags:
 *   { plex, tmdb, libs, sett, yaml } -- boolean each
 *
 * Also installs the toggle-target elements the gate flips:
 *   #validation-messages, #run-controls-container, #run-now,
 *   #run-now-label, warning ids, download ids, yaml ids.
 */
function installGateDom ({
  gate = {},
  flags = {},
  omit = []
} = {}) {
  const {
    stage = 'config',
    todoCount = 0,
    autoValidate = false,
    configValid = false,
    bulkFresh = false
  } = gate

  const has = id => !omit.includes(id)

  const parts = []
  parts.push(`
    <div id="final-gate-state"
         data-stage="${stage}"
         data-todo-count="${todoCount}"
         data-auto-validate="${autoValidate}"
         data-config-valid="${configValid}"
         data-bulk-fresh="${bulkFresh}"></div>
  `)

  // Per-page validation flags: hidden data-carrying elements
  const flagMap = [
    ['plex_valid', 'plex-valid', flags.plex],
    ['tmdb_valid', 'tmdb-valid', flags.tmdb],
    ['libs_valid', 'libs-valid', flags.libs],
    ['sett_valid', 'sett-valid', flags.sett],
    ['yaml_valid', 'yaml-valid', flags.yaml]
  ]
  flagMap.forEach(([id, attr, val]) => {
    if (has(id)) parts.push(`<div id="${id}" data-${attr}="${val ? 'True' : 'False'}"></div>`)
  })

  if (has('validation-messages')) parts.push('<div id="validation-messages" class="d-none"></div>')
  if (has('run-controls-container')) parts.push('<div id="run-controls-container" class="d-none"></div>')
  if (has('run-now')) parts.push('<button id="run-now" disabled></button>')
  if (has('run-now-label')) parts.push('<span id="run-now-label">Different Label</span>')

  const warningIds = ['no-validation-warning', 'yaml-warnings', 'yaml-warning-msg', 'validation-error']
  warningIds.forEach(id => { if (has(id)) parts.push(`<div id="${id}" class="d-none"></div>`) })

  const downloadIds = ['download-btn', 'download-redacted-btn']
  downloadIds.forEach(id => { if (has(id)) parts.push(`<div id="${id}"></div>`) })

  const yamlIds = ['yaml-content', 'final-yaml']
  yamlIds.forEach(id => { if (has(id)) parts.push(`<div id="${id}" class="d-none"></div>`) })

  document.body.innerHTML = parts.join('\n')
}

// Standard spy callbacks bundle -- shared shape across tests
function makeCallbacks () {
  return {
    updateRunNowState: vi.fn(),
    syncFinalAccordionRollups: vi.fn()
  }
}

afterEach(() => {
  document.body.innerHTML = ''
  // Reset showYAML to its default so tests don't cross-contaminate
  kometaState.showYAML = false
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------
// getFinalGateState
// ---------------------------------------------------------------------

describe('getFinalGateState', () => {
  it('returns conservative default when element is missing', () => {
    // Deliberately no DOM installed
    const state = getFinalGateState()
    expect(state).toEqual({
      stage: 'config',
      autoValidate: false,
      configValid: false
    })
  })

  it('reads all data-* fields when element is populated', () => {
    installGateDom({
      gate: {
        stage: 'todo',
        todoCount: 3,
        autoValidate: true,
        configValid: true,
        bulkFresh: true
      }
    })
    const state = getFinalGateState()
    expect(state).toEqual({
      stage: 'todo',
      todoCount: 3,
      autoValidate: true,
      configValid: true,
      bulkFresh: true
    })
  })

  it('defaults stage to "config" when the attribute is missing', () => {
    document.body.innerHTML = '<div id="final-gate-state"></div>'
    expect(getFinalGateState().stage).toBe('config')
  })

  it('defaults todoCount to 0 when the attribute is missing', () => {
    document.body.innerHTML = '<div id="final-gate-state"></div>'
    expect(getFinalGateState().todoCount).toBe(0)
  })

  it('interprets non-"true" strings as false (autoValidate, configValid, bulkFresh)', () => {
    document.body.innerHTML = `<div id="final-gate-state"
      data-auto-validate="1" data-config-valid="yes" data-bulk-fresh=""></div>`
    const state = getFinalGateState()
    expect(state.autoValidate).toBe(false)
    expect(state.configValid).toBe(false)
    expect(state.bulkFresh).toBe(false)
  })
})

// ---------------------------------------------------------------------
// updateValidationGate: TODO/freshness stage -> everything hidden
// ---------------------------------------------------------------------

describe('updateValidationGate stage=todo', () => {
  it('hides YAML/run controls/downloads and sets showYAML=false', () => {
    installGateDom({ gate: { stage: 'todo' } })
    kometaState.showYAML = true // sanity: even if it was true before
    const cb = makeCallbacks()
    updateValidationGate(cb)
    expect(kometaState.showYAML).toBe(false)
    expect(document.getElementById('validation-messages').classList.contains('d-none')).toBe(true)
    expect(document.getElementById('run-controls-container').classList.contains('d-none')).toBe(true)
    expect(document.getElementById('download-btn').classList.contains('d-none')).toBe(true)
    expect(document.getElementById('run-now').disabled).toBe(true)
    expect(document.getElementById('run-now-label').textContent).toBe('Run Now')
  })

  it('invokes both callbacks exactly once', () => {
    installGateDom({ gate: { stage: 'todo' } })
    const cb = makeCallbacks()
    updateValidationGate(cb)
    expect(cb.updateRunNowState).toHaveBeenCalledTimes(1)
    expect(cb.syncFinalAccordionRollups).toHaveBeenCalledTimes(1)
  })

  it('short-circuits: does not read per-page validation flags', () => {
    // If it DID read them, an unset dataset would default to false.
    // What we want to verify: showYAML doesn't depend on the flags in
    // this branch. Set them all true; still expect showYAML=false.
    installGateDom({
      gate: { stage: 'todo', configValid: true },
      flags: { plex: true, tmdb: true, libs: true, sett: true, yaml: true }
    })
    updateValidationGate(makeCallbacks())
    expect(kometaState.showYAML).toBe(false)
  })
})

describe('updateValidationGate stage=freshness', () => {
  it('behaves identically to stage=todo', () => {
    installGateDom({ gate: { stage: 'freshness' } })
    const cb = makeCallbacks()
    updateValidationGate(cb)
    expect(kometaState.showYAML).toBe(false)
    expect(cb.updateRunNowState).toHaveBeenCalledTimes(1)
    expect(cb.syncFinalAccordionRollups).toHaveBeenCalledTimes(1)
  })
})

// ---------------------------------------------------------------------
// updateValidationGate: config stage happy paths
// ---------------------------------------------------------------------

describe('updateValidationGate stage=config, all flags valid', () => {
  it('sets showYAML=true, shows YAML + run controls, hides warnings', () => {
    installGateDom({
      gate: { stage: 'config', configValid: false },
      flags: { plex: true, tmdb: true, libs: true, sett: true, yaml: true }
    })
    updateValidationGate(makeCallbacks())
    expect(kometaState.showYAML).toBe(true)
    expect(document.getElementById('validation-messages').classList.contains('d-none')).toBe(true)
    expect(document.getElementById('no-validation-warning').classList.contains('d-none')).toBe(true)
    expect(document.getElementById('yaml-content').classList.contains('d-none')).toBe(false)
    expect(document.getElementById('final-yaml').classList.contains('d-none')).toBe(false)
    expect(document.getElementById('run-controls-container').classList.contains('d-none')).toBe(false)
  })

  it('run-now stays disabled (runtime state checks happen later)', () => {
    installGateDom({
      gate: { stage: 'config' },
      flags: { plex: true, tmdb: true, libs: true, sett: true, yaml: true }
    })
    updateValidationGate(makeCallbacks())
    // The gate itself doesn't enable the button -- that's updateRunNowState's job
    expect(document.getElementById('run-now').disabled).toBe(true)
    expect(document.getElementById('run-now-label').textContent).toBe('Run Now')
  })
})

describe('updateValidationGate stage=config, configValid=true (server override)', () => {
  it('sets showYAML=true even when per-page flags are false', () => {
    installGateDom({
      gate: { stage: 'config', configValid: true },
      flags: { plex: false, tmdb: false, libs: false, sett: false, yaml: false }
    })
    updateValidationGate(makeCallbacks())
    expect(kometaState.showYAML).toBe(true)
  })
})

// ---------------------------------------------------------------------
// updateValidationGate: config stage sad paths (validation missing)
// ---------------------------------------------------------------------

describe('updateValidationGate stage=config, some flags missing', () => {
  it('sets showYAML=false and renders validation message rows', () => {
    installGateDom({
      gate: { stage: 'config' },
      flags: { plex: false, tmdb: true, libs: false, sett: true, yaml: true }
    })
    updateValidationGate(makeCallbacks())
    expect(kometaState.showYAML).toBe(false)
    const msg = document.getElementById('validation-messages')
    expect(msg.classList.contains('d-none')).toBe(false)
    expect(msg.innerHTML).toContain('Plex settings')
    expect(msg.innerHTML).toContain('/step/010-plex')
    expect(msg.innerHTML).toContain('Libraries page')
    expect(msg.innerHTML).toContain('/step/025-libraries')
    // Ones that are true should NOT appear
    expect(msg.innerHTML).not.toContain('TMDb settings')
    expect(msg.innerHTML).not.toContain('Settings page')
  })

  it('does not include yaml_valid in the messages (no user-facing text for it)', () => {
    // The yaml_valid flag participates in showYAML AND-logic but has no
    // corresponding "Open page" link -- the yaml is generated internally.
    installGateDom({
      gate: { stage: 'config' },
      flags: { plex: true, tmdb: true, libs: true, sett: true, yaml: false }
    })
    updateValidationGate(makeCallbacks())
    expect(kometaState.showYAML).toBe(false)
    // With all page flags true but yaml false, no rows are pushed -->
    // messages list is empty --> the branch that hides validation-messages
    // when empty should fire.
    const msg = document.getElementById('validation-messages')
    expect(msg.classList.contains('d-none')).toBe(true)
  })

  it('warnings are shown, downloads/YAML are hidden', () => {
    installGateDom({
      gate: { stage: 'config' },
      flags: { plex: false }
    })
    updateValidationGate(makeCallbacks())
    expect(document.getElementById('no-validation-warning').classList.contains('d-none')).toBe(false)
    expect(document.getElementById('download-btn').classList.contains('d-none')).toBe(true)
    expect(document.getElementById('run-controls-container').classList.contains('d-none')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// updateValidationGate: robustness (missing DOM elements)
// ---------------------------------------------------------------------

describe('updateValidationGate robustness', () => {
  it('does not throw when validation-messages is missing', () => {
    installGateDom({
      gate: { stage: 'config' },
      flags: { plex: false },
      omit: ['validation-messages']
    })
    expect(() => updateValidationGate(makeCallbacks())).not.toThrow()
  })

  it('does not throw when run-now / run-now-label are missing', () => {
    installGateDom({
      gate: { stage: 'todo' },
      omit: ['run-now', 'run-now-label']
    })
    expect(() => updateValidationGate(makeCallbacks())).not.toThrow()
  })

  it('does not throw when any warning/download/yaml element is missing', () => {
    installGateDom({
      gate: { stage: 'config' },
      flags: { plex: true, tmdb: true, libs: true, sett: true, yaml: true },
      omit: ['no-validation-warning', 'yaml-warnings', 'download-btn', 'yaml-content']
    })
    expect(() => updateValidationGate(makeCallbacks())).not.toThrow()
  })

  it('handles callbacks being missing (undefined)', () => {
    installGateDom({ gate: { stage: 'todo' } })
    // Pass no callbacks arg at all
    expect(() => updateValidationGate()).not.toThrow()
    // Pass empty object
    expect(() => updateValidationGate({})).not.toThrow()
  })

  it('handles callbacks that are not functions (silently skip)', () => {
    installGateDom({ gate: { stage: 'todo' } })
    expect(() =>
      updateValidationGate({ updateRunNowState: 42, syncFinalAccordionRollups: 'hi' })
    ).not.toThrow()
  })
})
