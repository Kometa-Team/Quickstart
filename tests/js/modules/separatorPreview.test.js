// Contract tests for static/local-js/modules/separatorPreview.js
//
// Behavior tests for the cluster's individual functions previously
// lived attached to window.OverlayHandler and were exercised through
// eventHandler tests; those tests still cover the wiring
// (attachLibraryListeners calls initializeOverlays, etc.). The tests
// here are narrower: they prove the MODULE (importable standalone,
// no OverlayHandler pollution required) exposes the expected exports
// and that each one runs end-to-end on a minimal DOM fixture.
//
// This is the "does the module contract work" smoke test that
// unlocks other consumers importing from it directly.

import { afterEach, describe, expect, it, vi } from 'vitest'
import * as separatorPreview from '../../../static/local-js/modules/separatorPreview.js'

// Silence chatty debug output from the DOM manipulators.
vi.spyOn(console, 'log').mockImplementation(() => {})
vi.spyOn(console, 'error').mockImplementation(() => {})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('separatorPreview module surface', () => {
  it('exports initializeOverlays as a function', () => {
    expect(typeof separatorPreview.initializeOverlays).toBe('function')
  })

  it('exports updateHiddenInputs as a function', () => {
    expect(typeof separatorPreview.updateHiddenInputs).toBe('function')
  })

  it('exports syncSeparatorPlaceholderFields as a function', () => {
    expect(typeof separatorPreview.syncSeparatorPlaceholderFields).toBe('function')
  })

  it('does not export the internal helpers (updateSeparatorToggles etc. stay module-scoped)', () => {
    // Namespace-keys assertion catches accidental leaks. The
    // separator-preview helpers are internal because they only exist
    // to be composed by initializeOverlays / updateHiddenInputs; if
    // they leak we lose the encapsulation benefit of the module.
    const keys = Object.keys(separatorPreview).sort()
    expect(keys).toEqual([
      'initializeOverlays',
      'syncSeparatorPlaceholderFields',
      'updateHiddenInputs'
    ])
  })
})

describe('separatorPreview: smoke tests', () => {
  // Each test builds the minimum DOM the function needs and asserts
  // one visible behavior. Exhaustive behavior coverage is elsewhere;
  // these prove the module works without needing overlayHandler.js.

  it('initializeOverlays: no-ops when the separator dropdown is missing', () => {
    document.body.innerHTML = ''
    expect(() => separatorPreview.initializeOverlays('mov-library_1', true)).not.toThrow()
  })

  it('initializeOverlays: attaches listener + marks dataset.listenerAdded on first call', () => {
    document.body.innerHTML = `
      <form id="configForm">
        <select name="mov-library_1-template_variables[use_separator]"></select>
      </form>
    `
    separatorPreview.initializeOverlays('mov-library_1', true)
    const dropdown = document.querySelector('select')
    expect(dropdown.dataset.listenerAdded).toBe('true')
  })

  it('updateHiddenInputs: creates hidden inputs when missing', () => {
    document.body.innerHTML = `
      <form id="configForm">
        <select name="mov-library_1-template_variables[use_separator]">
          <option value="line" selected>line</option>
        </select>
      </form>
    `
    separatorPreview.updateHiddenInputs('mov-library_1', true)
    const use = document.getElementById('mov-library_1-template_variables_use_separator')
    const sty = document.getElementById('mov-library_1-template_variables_sep_style')
    expect(use).not.toBeNull()
    expect(sty).not.toBeNull()
    expect(sty.value).toBe('line')
  })

  it('updateHiddenInputs: clears sep_style when the dropdown is "none"', () => {
    document.body.innerHTML = `
      <form id="configForm">
        <select name="mov-library_1-template_variables[use_separator]">
          <option value="none" selected>none</option>
        </select>
      </form>
    `
    separatorPreview.updateHiddenInputs('mov-library_1', true)
    const sty = document.getElementById('mov-library_1-template_variables_sep_style')
    expect(sty.value).toBe('')
  })

  it('updateHiddenInputs: no-ops when the config form is missing', () => {
    document.body.innerHTML = ''
    // Does not create form; guarded early return.
    expect(() => separatorPreview.updateHiddenInputs('mov-library_1', true)).not.toThrow()
    expect(document.getElementById('configForm')).toBeNull()
  })

  it('syncSeparatorPlaceholderFields: no-ops on null wrapper', () => {
    expect(() => separatorPreview.syncSeparatorPlaceholderFields(null)).not.toThrow()
  })

  it('syncSeparatorPlaceholderFields: toggles visually-hidden based on show option', () => {
    document.body.innerHTML = `
      <div id="wrapper" data-library-type="movie">
        <select class="separator-placeholder-source">
          <option value="imdb" selected>imdb</option>
        </select>
        <input data-separator-placeholder-input="imdb" value="tt123">
      </div>
    `
    const wrapper = document.getElementById('wrapper')
    separatorPreview.syncSeparatorPlaceholderFields(wrapper, { show: false })
    expect(wrapper.classList.contains('visually-hidden')).toBe(true)

    separatorPreview.syncSeparatorPlaceholderFields(wrapper, { show: true })
    expect(wrapper.classList.contains('visually-hidden')).toBe(false)
  })

  it('syncSeparatorPlaceholderFields: falls back to imdb when the selection is not in the allowed set', () => {
    document.body.innerHTML = `
      <div id="wrapper" data-library-type="movie">
        <select class="separator-placeholder-source">
          <option value="tvdb_show">tvdb_show</option>
          <option value="imdb">imdb</option>
          <option value="tmdb_movie">tmdb_movie</option>
        </select>
        <input data-separator-placeholder-input="imdb" value="">
      </div>
    `
    const wrapper = document.getElementById('wrapper')
    const select = wrapper.querySelector('select')
    select.value = 'tvdb_show' // not allowed for movie library
    separatorPreview.syncSeparatorPlaceholderFields(wrapper, { show: true })
    expect(select.value).toBe('imdb')
  })
})
