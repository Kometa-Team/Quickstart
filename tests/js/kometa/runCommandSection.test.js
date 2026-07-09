// Tests for static/local-js/modules/kometa/_runCommandSection.js
//
// Five exported functions:
//
//   setRunCommandPlaceholderState        -- populates placeholder
//   clearRunCommandPlaceholderState      -- hides placeholder + reveals box
//   hideRunCommandSectionUntilValidated  -- collapses accordion + shows placeholder
//   revealRunCommandSection              -- expands accordion + fades in box
//   showRunCommandSectionAfterValidated  -- convenience wrapper
//
// COVERAGE STRATEGY:
//
//   setRunCommandPlaceholderState: 8 branches (7 rule conditions + fallback)
//   clearRunCommandPlaceholderState: DOM assertions
//   hideRunCommandSectionUntilValidated: DOM writes + run-now button state
//   revealRunCommandSection: DOM writes + fade-in setTimeout
//   showRunCommandSectionAfterValidated: composition assertions
//
// Collaborators (getConfiguredKometaInstallMode, buildCommand,
// updateRunNowState) are mocked via vi.mock.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../static/local-js/modules/kometa/_runtime.js', () => ({
  getConfiguredKometaInstallMode: vi.fn(() => 'managed')
}))
vi.mock('../../../static/local-js/modules/kometa/_runCommand.js', () => ({
  buildCommand: vi.fn()
}))
vi.mock('../../../static/local-js/modules/kometa/_runControls.js', () => ({
  updateRunNowState: vi.fn()
}))

import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import {
  setRunCommandPlaceholderState,
  clearRunCommandPlaceholderState,
  hideRunCommandSectionUntilValidated,
  revealRunCommandSection,
  showRunCommandSectionAfterValidated
} from '../../../static/local-js/modules/kometa/_runCommandSection.js'
import { getConfiguredKometaInstallMode } from '../../../static/local-js/modules/kometa/_runtime.js'
import { buildCommand } from '../../../static/local-js/modules/kometa/_runCommand.js'
import { updateRunNowState } from '../../../static/local-js/modules/kometa/_runControls.js'

// ---------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------

/**
 * Install the placeholder fixture. This is what
 * setRunCommandPlaceholderState + clearRunCommandPlaceholderState
 * operate on.
 */
function installPlaceholderFixture () {
  document.body.innerHTML = `
    <div id="run-command-panel-message"></div>
    <span id="run-command-panel-title"></span>
    <span id="run-command-panel-text"></span>
    <a id="open-kometa-actions-panel-button"></a>
    <a id="open-kometa-actions-button"></a>
    <div id="run-command-placeholder"></div>
    <div id="run-command-box">
      <label class="form-label"></label>
      <pre></pre>
    </div>
    <button id="copy-command"></button>
  `
}

/**
 * Install the full section fixture including accordion + run-now
 * button. Superset of the placeholder fixture.
 */
function installFullSectionFixture () {
  document.body.innerHTML = `
    <div id="run-command-panel-message"></div>
    <span id="run-command-panel-title"></span>
    <span id="run-command-panel-text"></span>
    <a id="open-kometa-actions-panel-button"></a>
    <a id="open-kometa-actions-button"></a>
    <div id="run-command-placeholder"></div>
    <div id="run-command-output-accordion" class="d-none">
      <div id="run-command-output-heading">
        <button class="accordion-button collapsed" aria-expanded="false"></button>
      </div>
      <div id="run-command-output-collapse">
        <div id="run-command-box" class="d-none">
          <label class="form-label"></label>
          <pre></pre>
        </div>
      </div>
    </div>
    <button id="copy-command"></button>
    <button id="run-now"></button>
  `
}

/**
 * Reset every state field this module reads so tests don't
 * cross-contaminate. Defaults match the "happy validated" path so
 * setRunCommandPlaceholderState hits the fallback branch by default.
 */
function resetState () {
  kometaState.showYAML = true
  kometaState.kometaStatus = 'idle'
  kometaState.kometaUpdating = false
  kometaState.kometaValidationInProgress = false
  kometaState.kometaLocalCheckCompleted = true
  kometaState.kometaInstalled = true
  kometaState.kometaValidated = true
}

beforeEach(() => {
  getConfiguredKometaInstallMode.mockReset()
  getConfiguredKometaInstallMode.mockReturnValue('managed')
  buildCommand.mockClear()
  updateRunNowState.mockClear()
  resetState()
})

afterEach(() => {
  document.body.innerHTML = ''
  vi.useRealTimers()
})

// ---------------------------------------------------------------------
// setRunCommandPlaceholderState -- 8 branches (7 rules + fallback)
// ---------------------------------------------------------------------

describe('setRunCommandPlaceholderState -- rule priority', () => {
  it("is a no-op when the placeholder panel is missing", () => {
    document.body.innerHTML = ''
    expect(() => setRunCommandPlaceholderState()).not.toThrow()
  })

  it("Rule 1: !showYAML -> 'Fix validation before...'", () => {
    installPlaceholderFixture()
    kometaState.showYAML = false
    setRunCommandPlaceholderState()
    expect(document.getElementById('run-command-panel-title').textContent).toContain('Fix validation')
    // showButton: false -> panel button hidden
    expect(document.getElementById('open-kometa-actions-panel-button').classList.contains('d-none')).toBe(true)
  })

  it("Rule 2: kometaStatus='running' -> 'Kometa is currently running'", () => {
    installPlaceholderFixture()
    kometaState.kometaStatus = 'running'
    setRunCommandPlaceholderState()
    expect(document.getElementById('run-command-panel-title').textContent).toBe('Kometa is currently running')
    expect(document.getElementById('open-kometa-actions-panel-button').classList.contains('d-none')).toBe(true)
  })

  it("Rule 3: kometaUpdating -> 'Kometa update in progress'", () => {
    installPlaceholderFixture()
    kometaState.kometaUpdating = true
    setRunCommandPlaceholderState()
    expect(document.getElementById('run-command-panel-title').textContent).toBe('Kometa update in progress')
    // showButton: true (default)
    expect(document.getElementById('open-kometa-actions-panel-button').classList.contains('d-none')).toBe(false)
  })

  it("Rule 4: kometaValidationInProgress -> 'Preparing Kometa'", () => {
    installPlaceholderFixture()
    kometaState.kometaValidationInProgress = true
    setRunCommandPlaceholderState()
    expect(document.getElementById('run-command-panel-title').textContent).toBe('Preparing Kometa')
  })

  it("Rule 5: !localCheckCompleted -> 'Checking Kometa state'", () => {
    installPlaceholderFixture()
    kometaState.kometaLocalCheckCompleted = false
    setRunCommandPlaceholderState()
    expect(document.getElementById('run-command-panel-title').textContent).toBe('Checking Kometa state')
    expect(document.getElementById('open-kometa-actions-panel-button').classList.contains('d-none')).toBe(true)
  })

  it("Rule 6: !kometaInstalled -> 'Install Kometa to build...'", () => {
    installPlaceholderFixture()
    kometaState.kometaInstalled = false
    setRunCommandPlaceholderState()
    expect(document.getElementById('run-command-panel-title').textContent).toContain('Install Kometa')
  })

  it("Rule 7: !kometaValidated -> 'Validate Kometa to build...'", () => {
    installPlaceholderFixture()
    kometaState.kometaValidated = false
    setRunCommandPlaceholderState()
    expect(document.getElementById('run-command-panel-title').textContent).toContain('Validate Kometa')
  })

  it("Fallback: managed mode -> 'Run command is not ready yet' with managed message", () => {
    installPlaceholderFixture()
    // All state is 'happy' -> falls through to default
    setRunCommandPlaceholderState()
    expect(document.getElementById('run-command-panel-title').textContent).toBe('Run command is not ready yet')
    expect(document.getElementById('run-command-panel-text').textContent).toContain('install, validate, or update')
  })

  it("Fallback: existing mode -> different default message", () => {
    installPlaceholderFixture()
    getConfiguredKometaInstallMode.mockReturnValue('existing')
    setRunCommandPlaceholderState()
    expect(document.getElementById('run-command-panel-title').textContent).toBe('Run command is not ready yet')
    expect(document.getElementById('run-command-panel-text').textContent).toContain('validate the existing Kometa setup')
  })

  it('Priority: !showYAML wins over other conditions', () => {
    installPlaceholderFixture()
    kometaState.showYAML = false
    kometaState.kometaStatus = 'running'  // would match rule 2
    kometaState.kometaInstalled = false   // would match rule 6
    setRunCommandPlaceholderState()
    expect(document.getElementById('run-command-panel-title').textContent).toContain('Fix validation')
  })

  it('side effects: panel shown, box hidden, fade-in removed', () => {
    installPlaceholderFixture()
    const box = document.getElementById('run-command-box')
    box.classList.add('fade-in')
    setRunCommandPlaceholderState()
    expect(document.getElementById('run-command-panel-message').classList.contains('d-none')).toBe(false)
    expect(box.classList.contains('d-none')).toBe(true)
    expect(box.classList.contains('fade-in')).toBe(false)
  })
})

// ---------------------------------------------------------------------
// clearRunCommandPlaceholderState
// ---------------------------------------------------------------------

describe('clearRunCommandPlaceholderState', () => {
  it('hides placeholder + placeholder-lite + open-actions-button', () => {
    installPlaceholderFixture()
    clearRunCommandPlaceholderState()
    expect(document.getElementById('run-command-panel-message').classList.contains('d-none')).toBe(true)
    expect(document.getElementById('run-command-placeholder').classList.contains('d-none')).toBe(true)
    expect(document.getElementById('open-kometa-actions-button').classList.contains('d-none')).toBe(true)
  })

  it('reveals the run-command box + its label + pre + copy button', () => {
    installPlaceholderFixture()
    // Start with things hidden
    document.getElementById('run-command-box').classList.add('d-none')
    document.querySelector('#run-command-box .form-label').classList.add('d-none')
    document.querySelector('#run-command-box pre').classList.add('d-none')
    document.getElementById('copy-command').classList.add('d-none')

    clearRunCommandPlaceholderState()

    expect(document.getElementById('run-command-box').classList.contains('d-none')).toBe(false)
    expect(document.querySelector('#run-command-box .form-label').classList.contains('d-none')).toBe(false)
    expect(document.querySelector('#run-command-box pre').classList.contains('d-none')).toBe(false)
    expect(document.getElementById('copy-command').classList.contains('d-none')).toBe(false)
  })
})

// ---------------------------------------------------------------------
// hideRunCommandSectionUntilValidated
// ---------------------------------------------------------------------

describe('hideRunCommandSectionUntilValidated', () => {
  it("removes d-none from the accordion so it's visible (in placeholder mode)", () => {
    installFullSectionFixture()
    document.getElementById('run-command-output-accordion').classList.add('d-none')
    hideRunCommandSectionUntilValidated()
    expect(document.getElementById('run-command-output-accordion').classList.contains('d-none')).toBe(false)
  })

  it('collapses the accordion body', () => {
    installFullSectionFixture()
    document.getElementById('run-command-output-collapse').classList.add('show')
    hideRunCommandSectionUntilValidated()
    expect(document.getElementById('run-command-output-collapse').classList.contains('show')).toBe(false)
  })

  it('marks the accordion button as collapsed', () => {
    installFullSectionFixture()
    const btn = document.querySelector('#run-command-output-heading .accordion-button')
    btn.classList.remove('collapsed')
    btn.setAttribute('aria-expanded', 'true')
    hideRunCommandSectionUntilValidated()
    expect(btn.classList.contains('collapsed')).toBe(true)
    expect(btn.getAttribute('aria-expanded')).toBe('false')
  })

  it('disables the run-now button and swaps in a Waiting... label', () => {
    installFullSectionFixture()
    hideRunCommandSectionUntilValidated()
    const btn = document.getElementById('run-now')
    expect(btn.disabled).toBe(true)
    expect(btn.innerHTML).toContain('Waiting')
    expect(btn.innerHTML).toContain('bi-hourglass-split')
  })

  it('invokes setRunCommandPlaceholderState to populate the placeholder', () => {
    installFullSectionFixture()
    kometaState.kometaInstalled = false  // rule 6
    hideRunCommandSectionUntilValidated()
    expect(document.getElementById('run-command-panel-title').textContent).toContain('Install Kometa')
  })

  it('handles missing accordion / collapse / heading gracefully (partial fixtures)', () => {
    // Minimal fixture: just the placeholder + run-now button
    installPlaceholderFixture()
    document.body.appendChild(Object.assign(document.createElement('button'), { id: 'run-now' }))
    expect(() => hideRunCommandSectionUntilValidated()).not.toThrow()
  })

  it('handles missing run-now button gracefully', () => {
    installFullSectionFixture()
    document.getElementById('run-now').remove()
    expect(() => hideRunCommandSectionUntilValidated()).not.toThrow()
  })
})

// ---------------------------------------------------------------------
// revealRunCommandSection
// ---------------------------------------------------------------------

describe('revealRunCommandSection', () => {
  it('reveals the accordion + collapse + box (no fade-in yet)', () => {
    installFullSectionFixture()
    revealRunCommandSection()
    expect(document.getElementById('run-command-output-accordion').classList.contains('d-none')).toBe(false)
    expect(document.getElementById('run-command-output-collapse').classList.contains('show')).toBe(true)
    expect(document.getElementById('run-command-box').classList.contains('d-none')).toBe(false)
    // fade-in is added via setTimeout(10) -- not yet applied
    expect(document.getElementById('run-command-box').classList.contains('fade-in')).toBe(false)
  })

  it('marks the accordion button as expanded', () => {
    installFullSectionFixture()
    revealRunCommandSection()
    const btn = document.querySelector('#run-command-output-heading .accordion-button')
    expect(btn.classList.contains('collapsed')).toBe(false)
    expect(btn.getAttribute('aria-expanded')).toBe('true')
  })

  it('adds the fade-in class after a 10ms delay (via setTimeout)', () => {
    vi.useFakeTimers()
    installFullSectionFixture()
    revealRunCommandSection()
    const box = document.getElementById('run-command-box')
    expect(box.classList.contains('fade-in')).toBe(false)
    vi.advanceTimersByTime(15)
    expect(box.classList.contains('fade-in')).toBe(true)
  })

  it('calls clearRunCommandPlaceholderState first (via side effects)', () => {
    installFullSectionFixture()
    // Give the placeholder something visible so we can verify it got cleared
    document.getElementById('run-command-panel-message').classList.remove('d-none')
    revealRunCommandSection()
    expect(document.getElementById('run-command-panel-message').classList.contains('d-none')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// showRunCommandSectionAfterValidated
// ---------------------------------------------------------------------

describe('showRunCommandSectionAfterValidated', () => {
  it("resets the run-now button to the default Run Now state", () => {
    installFullSectionFixture()
    showRunCommandSectionAfterValidated()
    const btn = document.getElementById('run-now')
    expect(btn.innerHTML).toContain('Run Now')
    expect(btn.innerHTML).toContain('bi-play-fill')
  })

  it('invokes buildCommand() and updateRunNowState()', () => {
    installFullSectionFixture()
    showRunCommandSectionAfterValidated()
    expect(buildCommand).toHaveBeenCalledTimes(1)
    expect(updateRunNowState).toHaveBeenCalledTimes(1)
  })

  it('swallows errors from buildCommand()', () => {
    installFullSectionFixture()
    buildCommand.mockImplementationOnce(() => { throw new Error('build failed') })
    expect(() => showRunCommandSectionAfterValidated()).not.toThrow()
    // updateRunNowState should still be called (comes after buildCommand)
    expect(updateRunNowState).toHaveBeenCalledTimes(1)
  })

  it("reveals the section (accordion visible, placeholder hidden)", () => {
    installFullSectionFixture()
    document.getElementById('run-command-output-accordion').classList.add('d-none')
    showRunCommandSectionAfterValidated()
    expect(document.getElementById('run-command-output-accordion').classList.contains('d-none')).toBe(false)
    expect(document.getElementById('run-command-panel-message').classList.contains('d-none')).toBe(true)
  })
})
