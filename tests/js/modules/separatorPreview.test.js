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

const placeholderSources = [
  ['mov', 'movie', 'imdb', 'imdb_id', 'tt0133093', 'The Matrix'],
  ['mov', 'movie', 'tmdb_movie', 'tmdb_movie', '603', 'The Matrix'],
  ['sho', 'show', 'imdb', 'imdb_id', 'tt0944947', 'Game of Thrones'],
  ['sho', 'show', 'tvdb_show', 'tvdb_show', '121361', 'Game of Thrones']
]

function savedPlaceholderForm (kind, type, source, value, title, libraryName) {
  const prefix = `${kind}-library_saved`
  const secondary = type === 'movie' ? 'tmdb_movie' : 'tvdb_show'
  document.body.innerHTML = `
    <form id="configForm">
      <select id="${prefix}-template_variables_use_separator" name="${prefix}-template_variables[use_separator]">
        <option value="gray" selected>Gray</option>
        <option value="gold">Gold</option>
        <option value="none">None</option>
      </select>
      <div data-separator-placeholder-wrapper="true" data-library-id="${libraryName}" data-library-prefix="${prefix}" data-library-type="${type}">
        <select class="separator-placeholder-source">
          <option value="imdb">IMDb</option>
          <option value="${secondary}">${secondary}</option>
        </select>
        ${['imdb', secondary].map(optionSource => `
          <div class="separator-placeholder-field" data-placeholder-source="${optionSource}">
            <select id="${optionSource}_saved" class="separator-placeholder-picklist" data-separator-placeholder-input="${optionSource}" data-separator-placeholder-value="${optionSource === source ? value : ''}">
              <option value="${optionSource === source ? value : ''}" selected>Saved ID</option>
            </select>
            <input type="hidden" id="${optionSource}_saved__lookup_labels" value="{}">
          </div>`).join('')}
      </div>
    </form>`
  document.querySelector('.separator-placeholder-source').value = source
  document.getElementById(`${source}_saved__lookup_labels`).value = JSON.stringify({ [value]: title })
  return prefix
}

describe('separator selection persistence', () => {
  it.each(placeholderSources.flatMap(row => ['available', 'below-top-ten', 'missing', 'unavailable'].map(scenario => [...row, scenario])))(
    'preserves %s/%s/%s (field %s, ID %s, title %s) when %s',
    async (kind, type, source, key, value, title, scenario) => {
      const items = scenario === 'available'
        ? [{ title, [key]: value }]
        : scenario === 'below-top-ten'
          ? [...Array.from({ length: 10 }, (_, index) => ({ title: `Other ${index}`, [key]: key === 'imdb_id' ? `tt900000${index}` : `${1000 + index}` })), { title, [key]: value }]
          : []
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ status: scenario === 'unavailable' ? 'lookup_unavailable' : 'success', items })
      }))
      const prefix = savedPlaceholderForm(kind, type, source, value, title, `${type} ${source} ${scenario}`)
      separatorPreview.initializeOverlays(prefix, type === 'movie')
      await flushAsyncWork()

      const picklist = document.getElementById(`${source}_saved`)
      const labels = document.getElementById(`${source}_saved__lookup_labels`)
      expect(picklist.value).toBe(value)
      expect(picklist.selectedOptions[0].dataset.lookupLabel).toBe(title)
      expect(JSON.parse(labels.value)).toEqual({ [value]: title })
      expect(picklist.options.length).toBeLessThanOrEqual(12)

      // A repeated sync must retain the selection; explicitly clearing it must not.
      separatorPreview.syncSeparatorPlaceholderFields(document.querySelector('[data-separator-placeholder-wrapper]'))
      await flushAsyncWork()
      expect(picklist.value).toBe(value)
      expect(JSON.parse(labels.value)).toEqual({ [value]: title })
      picklist.value = ''
      picklist.dispatchEvent(new Event('change'))
      separatorPreview.syncSeparatorPlaceholderFields(document.querySelector('[data-separator-placeholder-wrapper]'))
      await flushAsyncWork()
      expect(picklist.value).toBe('')
      expect(JSON.parse(labels.value)).toEqual({})
    }
  )

  it.each(['movie', 'show'])('switches independently between IMDb and the %s source', async type => {
    const kind = type === 'movie' ? 'mov' : 'sho'
    const source = type === 'movie' ? 'tmdb_movie' : 'tvdb_show'
    const numericId = type === 'movie' ? '603' : '121361'
    const imdbId = type === 'movie' ? 'tt0133093' : 'tt0944947'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'success', items: [{ title: 'Selected title', imdb_id: imdbId, [source]: numericId }] })
    }))
    const prefix = savedPlaceholderForm(kind, type, source, numericId, 'Selected title', `${type} switching`)
    separatorPreview.initializeOverlays(prefix, type === 'movie')
    await flushAsyncWork()
    const sourceSelect = document.querySelector('.separator-placeholder-source')
    for (const [active, selectedId, inactive] of [['imdb', imdbId, source], [source, numericId, 'imdb']]) {
      sourceSelect.value = active
      sourceSelect.dispatchEvent(new Event('change'))
      await flushAsyncWork()
      const picklist = document.getElementById(`${active}_saved`)
      picklist.value = selectedId
      picklist.dispatchEvent(new Event('change'))
      separatorPreview.updateHiddenInputs(prefix, type === 'movie')
      expect(picklist.value).toBe(selectedId)
      expect(JSON.parse(document.getElementById(`${active}_saved__lookup_labels`).value)).toEqual({ [selectedId]: 'Selected title' })
      expect(document.getElementById(`${inactive}_saved`).value).toBe('')
      expect(JSON.parse(document.getElementById(`${inactive}_saved__lookup_labels`).value)).toEqual({})
    }
  })
})

describe('independent award and chart separator toggles', () => {
  it.each(['mov', 'sho'])('enables editable %s separator toggles loaded after initialization', kind => {
    const prefix = `${kind}-library_late`
    document.body.innerHTML = `<form id="configForm"><select name="${prefix}-template_variables[use_separator]"><option value="gray">Gray</option><option value="none">None</option></select></form>`
    separatorPreview.initializeOverlays(prefix, kind === 'mov')
    document.getElementById('configForm').insertAdjacentHTML('beforeend', `
      <input type="checkbox" class="readonly-toggle" id="${prefix}-collection_separator_chart" checked disabled>
      <input type="checkbox" class="readonly-toggle" id="${prefix}-collection_separator_award" disabled>`)
    separatorPreview.initializeOverlays(prefix, kind === 'mov')
    const chart = document.getElementById(`${prefix}-collection_separator_chart`)
    const award = document.getElementById(`${prefix}-collection_separator_award`)
    expect([chart.disabled, award.disabled]).toEqual([false, false])
    expect(chart.classList.contains('readonly-toggle')).toBe(false)
    expect(award.classList.contains('readonly-toggle')).toBe(false)
    expect([chart.checked, award.checked]).toEqual([true, false])
    document.querySelector('select').value = 'none'
    separatorPreview.updateHiddenInputs(prefix, kind === 'mov')
    expect([chart.disabled, award.disabled]).toEqual([true, true])
    expect([chart.checked, award.checked]).toEqual([true, false])
  })

  it.each(['mov', 'sho'].flatMap(kind => ['gray', 'none'].flatMap(style => [false, true].flatMap(award => [false, true].map(chart => [kind, style, award, chart])))))(
    'preserves %s saved choices with style=%s, award=%s and chart=%s',
    (kind, style, award, chart) => {
      const prefix = `${kind}-library_toggles`
      document.body.innerHTML = `
        <form id="configForm">
          <select name="${prefix}-template_variables[use_separator]">
            <option value="gray">Gray</option><option value="gold">Gold</option><option value="none">None</option>
          </select>
          <input type="checkbox" id="${prefix}-collection_separator_award" name="${prefix}-collection_separator_award" value="true" ${award ? 'checked' : ''}>
          <input type="hidden" name="${prefix}-collection_separator_award" value="false">
          <input type="checkbox" id="${prefix}-collection_separator_chart" name="${prefix}-collection_separator_chart" value="true" ${chart ? 'checked' : ''}>
          <input type="hidden" name="${prefix}-collection_separator_chart" value="false">
        </form>`
      const dropdown = document.querySelector('select')
      const awardToggle = document.getElementById(`${prefix}-collection_separator_award`)
      const chartToggle = document.getElementById(`${prefix}-collection_separator_chart`)
      dropdown.value = style
      separatorPreview.initializeOverlays(prefix, kind === 'mov')
      expect([awardToggle.checked, chartToggle.checked]).toEqual([award, chart])
      expect([awardToggle.disabled, chartToggle.disabled]).toEqual([style === 'none', style === 'none'])

      // Keep newly chosen, independent states through updates and off/on cycles.
      awardToggle.checked = !award
      chartToggle.checked = !chart
      for (const nextStyle of ['gold', 'none', 'gray']) {
        dropdown.value = nextStyle
        dropdown.dispatchEvent(new Event('change'))
        separatorPreview.updateHiddenInputs(prefix, kind === 'mov')
        separatorPreview.initializeOverlays(prefix, kind === 'mov')
        expect([awardToggle.checked, chartToggle.checked]).toEqual([!award, !chart])
        expect([awardToggle.disabled, chartToggle.disabled]).toEqual([nextStyle === 'none', nextStyle === 'none'])
        if (nextStyle !== 'none') {
          const form = new FormData(document.getElementById('configForm'))
          expect(form.get(`${prefix}-collection_separator_award`)).toBe(award ? 'false' : 'true')
          expect(form.get(`${prefix}-collection_separator_chart`)).toBe(chart ? 'false' : 'true')
        }
      }
    }
  )
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
