// Tests for static/local-js/modules/kometa/_prepareState.js
//
// Single export:
//   setKometaPrepareRunningState(isRunning)
//
// COVERAGE:
//
//   Missing DOM (3):
//     - no-op when the whole page is empty
//     - no-op when accordion exists but collapse missing
//     - no-op when accordion exists but toggle missing
//     - (accordion missing but the rest present: opacity toggle
//        skipped, rest still runs)
//
//   Running=true (5):
//     - adds .opacity-50 to accordion
//     - adds .collapsed to toggle
//     - sets aria-expanded="false" on toggle
//     - sets title attribute with the locked message
//     - disables toggle + adds .disabled class
//     - collapses an open accordion via Bootstrap when available
//     - skips bootstrap.Collapse.hide() when accordion already collapsed
//     - skips bootstrap.Collapse.hide() when Bootstrap global unavailable
//
//   Running=false (4):
//     - removes .opacity-50 from accordion
//     - removes title attribute
//     - enables toggle + removes .disabled class
//     - leaves aria-expanded / .collapsed alone (Bootstrap handles those
//       via its own toggle click handler; the module deliberately
//       doesn't touch them on the "released" path)

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  setKometaPrepareRunningState
} from '../../../static/local-js/modules/kometa/_prepareState.js'

function installAccordionDom () {
  document.body.innerHTML = `
    <div id="kometa-actions-accordion">
      <button id="kometa-actions-toggle" aria-expanded="true">Prepare</button>
      <div id="kometa-actions-collapse" class="collapse show"></div>
    </div>
  `
}

function tearDown () {
  document.body.innerHTML = ''
  delete global.bootstrap
  vi.restoreAllMocks()
}

// ---------------------------------------------------------------------
// Missing DOM
// ---------------------------------------------------------------------

describe('setKometaPrepareRunningState (missing DOM)', () => {
  afterEach(tearDown)

  it('no-ops when the page is empty', () => {
    document.body.innerHTML = ''
    expect(() => setKometaPrepareRunningState(true)).not.toThrow()
    expect(() => setKometaPrepareRunningState(false)).not.toThrow()
  })

  it('no-ops (except opacity) when the collapse is missing', () => {
    document.body.innerHTML = `
      <div id="kometa-actions-accordion"></div>
      <button id="kometa-actions-toggle"></button>
    `
    setKometaPrepareRunningState(true)
    // Accordion opacity still toggled (that check happens first)
    expect(document.getElementById('kometa-actions-accordion').classList.contains('opacity-50')).toBe(true)
    // Toggle NOT disabled (function returned before reaching that block)
    expect(document.getElementById('kometa-actions-toggle').disabled).toBe(false)
  })

  it('no-ops (except opacity) when the toggle is missing', () => {
    document.body.innerHTML = `
      <div id="kometa-actions-accordion"></div>
      <div id="kometa-actions-collapse" class="collapse show"></div>
    `
    expect(() => setKometaPrepareRunningState(true)).not.toThrow()
    expect(document.getElementById('kometa-actions-accordion').classList.contains('opacity-50')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// isRunning === true
// ---------------------------------------------------------------------

describe('setKometaPrepareRunningState (isRunning=true)', () => {
  beforeEach(installAccordionDom)
  afterEach(tearDown)

  it('adds .opacity-50 to the accordion wrapper', () => {
    setKometaPrepareRunningState(true)
    expect(document.getElementById('kometa-actions-accordion').classList.contains('opacity-50')).toBe(true)
  })

  it('adds .collapsed class to the toggle', () => {
    setKometaPrepareRunningState(true)
    expect(document.getElementById('kometa-actions-toggle').classList.contains('collapsed')).toBe(true)
  })

  it('sets aria-expanded="false" on the toggle', () => {
    setKometaPrepareRunningState(true)
    expect(document.getElementById('kometa-actions-toggle').getAttribute('aria-expanded')).toBe('false')
  })

  it('sets the "locked" title attr on the toggle', () => {
    setKometaPrepareRunningState(true)
    expect(document.getElementById('kometa-actions-toggle').getAttribute('title'))
      .toBe('Kometa is running. Prepare Kometa is locked until the run finishes.')
  })

  it('disables the toggle + adds .disabled class', () => {
    setKometaPrepareRunningState(true)
    const toggle = document.getElementById('kometa-actions-toggle')
    expect(toggle.disabled).toBe(true)
    expect(toggle.classList.contains('disabled')).toBe(true)
  })

  it('calls Bootstrap Collapse.hide() when accordion is open and Bootstrap is loaded', () => {
    const hideSpy = vi.fn()
    global.bootstrap = {
      Collapse: {
        getOrCreateInstance: vi.fn(() => ({ hide: hideSpy }))
      }
    }
    setKometaPrepareRunningState(true)
    expect(global.bootstrap.Collapse.getOrCreateInstance).toHaveBeenCalled()
    expect(hideSpy).toHaveBeenCalled()
  })

  it('skips Collapse.hide() when accordion is already collapsed', () => {
    // Remove .show to simulate a closed accordion
    document.getElementById('kometa-actions-collapse').classList.remove('show')
    const hideSpy = vi.fn()
    global.bootstrap = {
      Collapse: {
        getOrCreateInstance: vi.fn(() => ({ hide: hideSpy }))
      }
    }
    setKometaPrepareRunningState(true)
    expect(hideSpy).not.toHaveBeenCalled()
  })

  it('skips Collapse.hide() when Bootstrap global is not available', () => {
    // Ensure no bootstrap global
    delete global.bootstrap
    expect(() => setKometaPrepareRunningState(true)).not.toThrow()
    // Toggle should still be locked
    expect(document.getElementById('kometa-actions-toggle').disabled).toBe(true)
  })
})

// ---------------------------------------------------------------------
// isRunning === false
// ---------------------------------------------------------------------

describe('setKometaPrepareRunningState (isRunning=false)', () => {
  beforeEach(() => {
    installAccordionDom()
    // Start in the running/locked state so we can verify the release
    document.getElementById('kometa-actions-accordion').classList.add('opacity-50')
    const toggle = document.getElementById('kometa-actions-toggle')
    toggle.disabled = true
    toggle.classList.add('disabled')
    toggle.setAttribute('title', 'Kometa is running. Prepare Kometa is locked until the run finishes.')
  })
  afterEach(tearDown)

  it('removes .opacity-50 from the accordion wrapper', () => {
    setKometaPrepareRunningState(false)
    expect(document.getElementById('kometa-actions-accordion').classList.contains('opacity-50')).toBe(false)
  })

  it('removes the title attribute from the toggle', () => {
    setKometaPrepareRunningState(false)
    expect(document.getElementById('kometa-actions-toggle').hasAttribute('title')).toBe(false)
  })

  it('re-enables the toggle + removes .disabled class', () => {
    setKometaPrepareRunningState(false)
    const toggle = document.getElementById('kometa-actions-toggle')
    expect(toggle.disabled).toBe(false)
    expect(toggle.classList.contains('disabled')).toBe(false)
  })

  it('does not touch .collapsed / aria-expanded on release', () => {
    // Set them to values that indicate "collapsed" so we can verify
    // the function doesn't reset them (Bootstrap owns those attrs on
    // release; our module deliberately doesn't touch them so the
    // user's expand/collapse click won't be double-toggled).
    const toggle = document.getElementById('kometa-actions-toggle')
    toggle.classList.add('collapsed')
    toggle.setAttribute('aria-expanded', 'false')

    setKometaPrepareRunningState(false)

    expect(toggle.classList.contains('collapsed')).toBe(true)
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
  })
})
