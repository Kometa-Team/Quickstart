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
vi.spyOn(console, 'warn').mockImplementation(() => {})

afterEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

async function flushAsyncWork () {
  for (let index = 0; index < 5; index += 1) {
    await Promise.resolve()
  }
  await new Promise(resolve => setTimeout(resolve, 0))
}

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
  it.each([
    ['mov', 'movie', 'imdb', 'imdb_id', 'tt0133093', 'The Matrix'],
    ['mov', 'movie', 'tmdb_movie', 'tmdb_movie', '603', 'The Matrix'],
    ['sho', 'show', 'imdb', 'imdb_id', 'tt0944947', 'Game of Thrones'],
    ['sho', 'show', 'tvdb_show', 'tvdb_show', '121361', 'Game of Thrones']
  ])('submits the selected %s/%s/%s ID and title with the inactive source empty', async (kind, type, source, key, value, title) => {
    const prefix = `${kind}-library_selection`
    const libraryName = `${type} & ${source}`
    const secondary = type === 'movie' ? 'tmdb_movie' : 'tvdb_show'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'success', items: [{ title, [key]: value }] })
    }))
    document.body.innerHTML = `
      <form id="configForm">
        <select name="${prefix}-template_variables[use_separator]">
          <option value="gray" selected>Gray</option>
        </select>
        <div data-separator-placeholder-wrapper="true" data-library-id="${libraryName}" data-library-prefix="${prefix}" data-library-type="${type}">
          <select class="separator-placeholder-source">
            <option value="imdb" selected>IMDb</option>
            <option value="${secondary}">${secondary}</option>
          </select>
          ${['imdb', secondary].map(optionSource => {
            const optionKey = optionSource === 'imdb' ? 'imdb_id' : optionSource
            const name = `${prefix}-attribute_template_variables[placeholder_${optionKey}]`
            return `
              <div class="separator-placeholder-field" data-placeholder-source="${optionSource}">
                <select id="${optionSource}_selection" name="${name}" class="separator-placeholder-picklist" data-separator-placeholder-input="${optionSource}"></select>
                <input type="hidden" id="${optionSource}_selection__lookup_labels" name="${name}__lookup_labels">
              </div>`
          }).join('')}
        </div>
      </form>`

    separatorPreview.initializeOverlays(prefix, type === 'movie')
    await flushAsyncWork()
    const sourceSelect = document.querySelector('.separator-placeholder-source')
    sourceSelect.value = source
    sourceSelect.dispatchEvent(new Event('change'))
    await flushAsyncWork()
    const picklist = document.getElementById(`${source}_selection`)
    expect(Array.from(picklist.options).map(option => option.value)).toContain(value)
    picklist.value = value
    picklist.dispatchEvent(new Event('change'))

    const form = new FormData(document.getElementById('configForm'))
    const field = `${prefix}-attribute_template_variables[placeholder_${key}]`
    expect(form.get(field)).toBe(value)
    expect(JSON.parse(form.get(`${field}__lookup_labels`))).toEqual({ [value]: title })
    const inactiveKey = source === 'imdb' ? secondary : 'imdb_id'
    expect(form.get(`${prefix}-attribute_template_variables[placeholder_${inactiveKey}]`)).toBe('')
    expect(fetch).toHaveBeenCalledWith(`/get_top_imdb_items/${encodeURIComponent(libraryName)}?type=${type}`, { credentials: 'same-origin' })
  })

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

  it('initializeOverlays: populates separator placeholder picklists from Plex top audience-rated items', async () => {
    const items = Array.from({ length: 12 }, (_, index) => ({
      title: `Movie ${index + 1}`,
      imdb_id: `tt123456${index}`,
      tmdb_movie: `${600 + index}`
    }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'success', items })
    }))
    document.body.innerHTML = `
      <form id="configForm">
        <select name="mov-library_1-template_variables[use_separator]">
          <option value="gold" selected>gold</option>
        </select>
        <div data-separator-placeholder-wrapper="true" data-library-id="Movies" data-library-prefix="mov-library_1" data-library-type="movie">
          <select class="separator-placeholder-source">
            <option value="imdb" selected>IMDb ID</option>
            <option value="tmdb_movie">TMDb Movie ID</option>
          </select>
          <div class="separator-placeholder-field" data-placeholder-source="imdb">
            <select id="imdb_picklist" class="separator-placeholder-picklist" data-separator-placeholder-input="imdb" data-separator-placeholder-value=""></select>
            <input type="hidden" id="imdb_picklist__lookup_labels">
          </div>
          <div class="separator-placeholder-field d-none" data-placeholder-source="tmdb_movie">
            <select id="tmdb_picklist" class="separator-placeholder-picklist" data-separator-placeholder-input="tmdb_movie" data-separator-placeholder-value=""></select>
            <input type="hidden" id="tmdb_picklist__lookup_labels">
          </div>
        </div>
      </form>
    `

    separatorPreview.initializeOverlays('mov-library_1', true)
    await flushAsyncWork()

    expect(fetch).toHaveBeenCalledWith('/get_top_imdb_items/Movies?type=movie', { credentials: 'same-origin' })
    const imdbOptions = Array.from(document.getElementById('imdb_picklist').querySelectorAll('option')).map(option => option.value).filter(Boolean)
    expect(imdbOptions).toHaveLength(10)
    expect(imdbOptions[0]).toBe('tt1234560')
    expect(imdbOptions[9]).toBe('tt1234569')
  })

  it('initializeOverlays: rebuilds the active picklist for the selected placeholder source', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        status: 'success',
        items: [{ title: 'The Matrix', imdb_id: 'tt0133093', tmdb_movie: '603' }]
      })
    }))
    document.body.innerHTML = `
      <form id="configForm">
        <select name="mov-library_1-template_variables[use_separator]">
          <option value="gold" selected>gold</option>
        </select>
        <div data-separator-placeholder-wrapper="true" data-library-id="Movies" data-library-prefix="mov-library_1" data-library-type="movie">
          <select class="separator-placeholder-source">
            <option value="imdb" selected>IMDb ID</option>
            <option value="tmdb_movie">TMDb Movie ID</option>
          </select>
          <div class="separator-placeholder-field" data-placeholder-source="imdb">
            <select id="imdb_picklist" class="separator-placeholder-picklist" data-separator-placeholder-input="imdb" data-separator-placeholder-value=""></select>
            <input type="hidden" id="imdb_picklist__lookup_labels">
          </div>
          <div class="separator-placeholder-field d-none" data-placeholder-source="tmdb_movie">
            <select id="tmdb_picklist" class="separator-placeholder-picklist" data-separator-placeholder-input="tmdb_movie" data-separator-placeholder-value=""></select>
            <input type="hidden" id="tmdb_picklist__lookup_labels">
          </div>
        </div>
      </form>
    `

    separatorPreview.initializeOverlays('mov-library_1', true)
    await flushAsyncWork()

    const source = document.querySelector('.separator-placeholder-source')
    source.value = 'tmdb_movie'
    source.dispatchEvent(new Event('change'))
    await flushAsyncWork()

    const imdbField = document.querySelector('[data-placeholder-source="imdb"]')
    const tmdbField = document.querySelector('[data-placeholder-source="tmdb_movie"]')
    expect(imdbField.classList.contains('d-none')).toBe(true)
    expect(tmdbField.classList.contains('d-none')).toBe(false)
    const tmdbOptions = Array.from(document.getElementById('tmdb_picklist').querySelectorAll('option')).map(option => option.value)
    expect(tmdbOptions).toContain('603')
  })

  it('initializeOverlays: keeps saved picklist value when top item lookup is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        status: 'lookup_unavailable',
        items: [],
        message: 'Unable to load top audience-rated Plex items.'
      })
    }))
    document.body.innerHTML = `
      <form id="configForm">
        <select name="mov-library_1-template_variables[use_separator]">
          <option value="gold" selected>gold</option>
        </select>
        <div data-separator-placeholder-wrapper="true" data-library-id="Unavailable Movies" data-library-prefix="mov-library_1" data-library-type="movie">
          <select class="separator-placeholder-source">
            <option value="imdb" selected>IMDb ID</option>
            <option value="tmdb_movie">TMDb Movie ID</option>
          </select>
          <div class="separator-placeholder-field" data-placeholder-source="imdb">
            <select id="imdb_picklist" class="separator-placeholder-picklist" data-separator-placeholder-input="imdb" data-separator-placeholder-value="tt0108052"></select>
            <input type="hidden" id="imdb_picklist__lookup_labels">
          </div>
        </div>
      </form>
    `

    separatorPreview.initializeOverlays('mov-library_1', true)
    await flushAsyncWork()

    const select = document.getElementById('imdb_picklist')
    const options = Array.from(select.querySelectorAll('option')).map(option => option.textContent)
    expect(select.value).toBe('tt0108052')
    expect(options[0]).toBe('Unable to load top audience-rated Plex items.')
    expect(options[1]).toContain('not revalidated')
  })
})
