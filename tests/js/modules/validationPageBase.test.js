// Tests for static/local-js/modules/validationPageBase.js
//
// First Vitest suite in the repo (PR for #1334 Step 8). The functions
// under test are tiny, but they're imported by 16 wizard pages and
// touched by every credential-style flow, so locking down their
// contract has outsized value.
//
// Why these two functions are good kick-off targets:
//   - setToggleButtonIcon: pure-ish DOM manipulation, easy to assert
//     against without mocking anything. Exercises jsdom integration.
//   - refreshValidationCallout: pure delegation to a global. Exercises
//     the window-global mocking pattern we'll need for most UI code.
//
// Patterns established here (followed by future suites):
//   - beforeEach resets document.body and any window globals we set
//   - one describe block per exported function
//   - one assertion per behaviour, not one assertion per test

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  refreshValidationCallout,
  setToggleButtonIcon
} from '../../../static/local-js/modules/validationPageBase.js'

describe('setToggleButtonIcon', () => {
  let button

  beforeEach(() => {
    document.body.innerHTML = ''
    button = document.createElement('button')
    document.body.appendChild(button)
  })

  it('does nothing when the button argument is null', () => {
    // Defensive guard: the function returns early on falsy input. We
    // assert no throw rather than asserting on side effects.
    expect(() => setToggleButtonIcon(null, true)).not.toThrow()
    expect(() => setToggleButtonIcon(undefined, false)).not.toThrow()
  })

  it('renders an eye-slash icon when showing plain text', () => {
    setToggleButtonIcon(button, true)
    const icon = button.querySelector('i')
    expect(icon).not.toBeNull()
    expect(icon.className).toBe('fas fa-eye-slash')
  })

  it('renders a plain eye icon when value is hidden', () => {
    setToggleButtonIcon(button, false)
    const icon = button.querySelector('i')
    expect(icon).not.toBeNull()
    expect(icon.className).toBe('fas fa-eye')
  })

  it('replaces previous children rather than appending', () => {
    // Pre-seed the button with stale icons to confirm replaceChildren
    // is doing what we expect, not appending.
    button.appendChild(document.createElement('i'))
    button.appendChild(document.createElement('i'))
    button.appendChild(document.createElement('span'))
    setToggleButtonIcon(button, true)
    expect(button.children).toHaveLength(1)
    expect(button.firstElementChild.tagName).toBe('I')
  })
})

describe('refreshValidationCallout', () => {
  afterEach(() => {
    delete window.QSValidationCallouts
  })

  it('is a no-op when window.QSValidationCallouts is undefined', () => {
    // Make sure the deletion in afterEach took.
    expect(window.QSValidationCallouts).toBeUndefined()
    expect(() => refreshValidationCallout('plex_token')).not.toThrow()
  })

  it('is a no-op when QSValidationCallouts has no refresh function', () => {
    window.QSValidationCallouts = { somethingElse: 'irrelevant' }
    expect(() => refreshValidationCallout('plex_token')).not.toThrow()
  })

  it('is a no-op when refresh is present but not callable', () => {
    // The function checks typeof refresh === 'function'; non-functions
    // should be ignored without error.
    window.QSValidationCallouts = { refresh: 'not a function' }
    expect(() => refreshValidationCallout('plex_token')).not.toThrow()
  })

  it('forwards the field name to QSValidationCallouts.refresh when available', () => {
    const refresh = vi.fn()
    window.QSValidationCallouts = { refresh }
    refreshValidationCallout('plex_token')
    expect(refresh).toHaveBeenCalledExactlyOnceWith('plex_token')
  })

  it('calls refresh once per invocation', () => {
    const refresh = vi.fn()
    window.QSValidationCallouts = { refresh }
    refreshValidationCallout('a')
    refreshValidationCallout('b')
    refreshValidationCallout('c')
    expect(refresh).toHaveBeenCalledTimes(3)
    expect(refresh.mock.calls).toEqual([['a'], ['b'], ['c']])
  })
})
