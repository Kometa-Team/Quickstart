// Tests for EventHandler.attachLibraryListeners.
//
// This is the ~322-line beast excluded from eventHandler.test.js in
// PR #1548 (see the scope note there). It walks the wizard DOM and
// wires up listeners for library card visibility, image dropdowns,
// overlay toggles, rating validators, list-based custom-add flows,
// and the bubble/highlight/validation delegation.
//
// Testing strategy: rather than build one giant fixture that models
// the entire wizard, we cover each concern with a minimal focused
// fixture and only add the DOM the specific code path needs. This
// keeps each test readable and its failure mode obvious.
//
// Covered clusters (in test order):
//   1. Setup / idempotency
//   2. Library checkbox visibility wiring
//   3. Type detection (movie vs show)
//   4. Image dropdown listener wiring
//   5. Upload / fetch / delete / rename button wiring
//   6. Overlay checkbox change wiring
//   7. Overlay preview trigger (.overlay-toggle)
//   8. Separator dropdown wiring
//   9. List-based custom-add flow (mass_genre_update etc.)
//  10. Rating range validation (0-10)
//  11. Bubble handler (change/input across the library card)
//
// Deliberately NOT covered here (would need dedicated PRs):
//   - The internal expandCheckedChildToggleSections() call at the
//     end of attachLibraryListeners (walks all `.child-toggle-section`
//     elements — orthogonal concern).
//   - MutationObserver on document.body that re-runs attachLibraryListeners.
//   - The mapping list handler.
//   - installRatingSubmitGuard.

import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

beforeAll(async () => {
  // Silence chatty console output (attachLibraryListeners logs a LOT).
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'debug').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})

  // Stub the global handlers the module reaches for. We capture the mock
  // fns so tests can assert against them.
  window.ValidationHandler = {
    restoreSelectedLibraries: vi.fn(),
    updateValidationState: vi.fn()
  }
  window.ImageHandler = {
    loadAvailableImages: vi.fn(),
    uploadLibraryImage: vi.fn(),
    generateSinglePreview: vi.fn(),
    toggleDeleteButton: vi.fn(),
    deleteCustomImage: vi.fn(),
    openRenameModal: vi.fn(),
    fetchLibraryImage: vi.fn()
  }
  window.OverlayHandler = {
    updateHiddenInputs: vi.fn(),
    initializeOverlays: vi.fn()
  }
  window.showToast = vi.fn()

  document.body.innerHTML = ''
  await import('../../static/local-js/eventHandler.js')
})

beforeEach(() => {
  document.body.innerHTML = ''
  // Reset call counts on each test so we can assert clean.
  Object.values(window.ImageHandler).forEach(fn => fn.mockClear?.())
  Object.values(window.OverlayHandler).forEach(fn => fn.mockClear?.())
  Object.values(window.ValidationHandler).forEach(fn => fn.mockClear?.())
})

afterEach(() => {
  vi.restoreAllMocks()
  // Re-install the silent console spies since restoreAllMocks nukes them.
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'debug').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  // Clean up any offsetParent shim installed by rating-validation tests
  // so it doesn't leak into subsequent tests that need the jsdom default
  // (null for detached elements).
  delete HTMLElement.prototype.offsetParent
})

// -----------------------------------------------------------------------
// Fixture builders
// -----------------------------------------------------------------------

/**
 * Build a bare library card container element pair:
 *   <input class="library-checkbox" id="<libraryId>-library" [checked]>
 *   <div id="<libraryId>-card-container">...</div>
 */
function buildLibraryCard ({ libraryId, checked = true, innerHTML = '' }) {
  const wrap = document.createElement('div')
  wrap.innerHTML = `
    <input type="checkbox" class="library-checkbox"
           id="${libraryId}-library"${checked ? ' checked' : ''}>
    <div id="${libraryId}-card-container">${innerHTML}</div>
  `
  document.body.appendChild(wrap)
  return {
    checkbox: document.getElementById(`${libraryId}-library`),
    container: document.getElementById(`${libraryId}-card-container`)
  }
}

// -----------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------

describe('EventHandler.attachLibraryListeners: setup', () => {
  it('is a function exposed on window.EventHandler', () => {
    expect(typeof window.EventHandler.attachLibraryListeners).toBe('function')
  })

  it('is safe to call against an empty DOM', () => {
    document.body.innerHTML = ''
    expect(() => window.EventHandler.attachLibraryListeners()).not.toThrow()
  })
})

describe('EventHandler.attachLibraryListeners: idempotency', () => {
  it('marks a library-checkbox with data-listener-added="true" after wiring', () => {
    const { checkbox } = buildLibraryCard({ libraryId: 'mov-library_1' })
    window.EventHandler.attachLibraryListeners()
    expect(checkbox.dataset.listenerAdded).toBe('true')
  })

  it('does not double-wire when called twice (change fires once per user action)', () => {
    const { checkbox } = buildLibraryCard({ libraryId: 'mov-library_1', checked: true })
    window.EventHandler.attachLibraryListeners()
    window.EventHandler.attachLibraryListeners()

    // Trigger a single user change; validateState should fire exactly once.
    checkbox.checked = false
    checkbox.dispatchEvent(new Event('change'))
    expect(window.ValidationHandler.updateValidationState).toHaveBeenCalledTimes(1)
  })

  it('marks dropdowns with data-listener-added on first pass', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <select id="mov-library_1-movie-image-dropdown"></select>
      `
    })
    window.EventHandler.attachLibraryListeners()
    const dropdown = document.getElementById('mov-library_1-movie-image-dropdown')
    expect(dropdown.dataset.listenerAdded).toBe('true')
  })
})

describe('EventHandler.attachLibraryListeners: library visibility wiring', () => {
  it('hides an unchecked library container on first attach', () => {
    const { container } = buildLibraryCard({
      libraryId: 'mov-library_1',
      checked: false
    })
    window.EventHandler.attachLibraryListeners()
    expect(container.style.display).toBe('none')
  })

  it('leaves a checked library container alone on first attach', () => {
    const { container } = buildLibraryCard({
      libraryId: 'mov-library_1',
      checked: true
    })
    window.EventHandler.attachLibraryListeners()
    // No explicit style applied for a checked library.
    expect(container.style.display).toBe('')
  })

  it('toggles the container visibility when the checkbox changes', () => {
    const { checkbox, container } = buildLibraryCard({
      libraryId: 'mov-library_1',
      checked: true
    })
    window.EventHandler.attachLibraryListeners()

    // User unchecks -> hidden
    checkbox.checked = false
    checkbox.dispatchEvent(new Event('change'))
    expect(container.style.display).toBe('none')

    // User re-checks -> visible
    checkbox.checked = true
    checkbox.dispatchEvent(new Event('change'))
    expect(container.style.display).toBe('block')
  })

  it('calls ValidationHandler.updateValidationState when the checkbox changes', () => {
    const { checkbox } = buildLibraryCard({ libraryId: 'mov-library_1', checked: true })
    window.EventHandler.attachLibraryListeners()
    checkbox.dispatchEvent(new Event('change'))
    expect(window.ValidationHandler.updateValidationState).toHaveBeenCalled()
  })
})

describe('EventHandler.attachLibraryListeners: type detection (movie vs show)', () => {
  it('loads only movie images for mov-library_* IDs', () => {
    buildLibraryCard({ libraryId: 'mov-library_1' })
    window.EventHandler.attachLibraryListeners()
    // Movie libraries load ONE type: movie
    const types = window.ImageHandler.loadAvailableImages.mock.calls.map(c => c[1])
    expect(types).toEqual(['movie'])
  })

  it('loads show/season/episode images for sho-library_* IDs', () => {
    buildLibraryCard({ libraryId: 'sho-library_1' })
    window.EventHandler.attachLibraryListeners()
    const types = window.ImageHandler.loadAvailableImages.mock.calls.map(c => c[1])
    // Show libraries load THREE types
    expect(types).toEqual(['show', 'season', 'episode'])
  })

  it('initializes overlays with the correct isMovie flag', () => {
    buildLibraryCard({ libraryId: 'mov-library_1' })
    buildLibraryCard({ libraryId: 'sho-library_1' })
    window.EventHandler.attachLibraryListeners()
    // Two calls, one per library, isMovie flag reflects the prefix
    const calls = window.OverlayHandler.initializeOverlays.mock.calls
    const movCall = calls.find(c => c[0] === 'mov-library_1')
    const shoCall = calls.find(c => c[0] === 'sho-library_1')
    expect(movCall).toEqual(['mov-library_1', true])
    expect(shoCall).toEqual(['sho-library_1', false])
  })
})

describe('EventHandler.attachLibraryListeners: image dropdown listener', () => {
  it('wires the dropdown change to updateSinglePreview + toggleDeleteButton', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <select id="mov-library_1-movie-image-dropdown">
          <option value="default">default</option>
          <option value="custom.png">custom.png</option>
        </select>
        <input type="hidden" id="mov-library_1-movie_selected_image" value="">
      `
    })
    window.EventHandler.attachLibraryListeners()

    const dropdown = document.getElementById('mov-library_1-movie-image-dropdown')
    dropdown.value = 'custom.png'
    dropdown.dispatchEvent(new Event('change'))

    expect(window.ImageHandler.generateSinglePreview)
      .toHaveBeenCalledWith('mov-library_1', 'movie')
    expect(window.ImageHandler.toggleDeleteButton)
      .toHaveBeenCalledWith('mov-library_1', 'movie')
  })

  it('mirrors the dropdown value into the hidden _selected_image input', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <select id="mov-library_1-movie-image-dropdown">
          <option value="default">default</option>
          <option value="foo.png">foo.png</option>
        </select>
        <input type="hidden" id="mov-library_1-movie_selected_image" value="">
      `
    })
    window.EventHandler.attachLibraryListeners()

    const dropdown = document.getElementById('mov-library_1-movie-image-dropdown')
    dropdown.value = 'foo.png'
    dropdown.dispatchEvent(new Event('change'))

    const hidden = document.getElementById('mov-library_1-movie_selected_image')
    expect(hidden.value).toBe('foo.png')
  })

  it('falls back to "default" when the dropdown value is empty', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <select id="mov-library_1-movie-image-dropdown">
          <option value="">empty</option>
        </select>
        <input type="hidden" id="mov-library_1-movie_selected_image" value="foo.png">
      `
    })
    window.EventHandler.attachLibraryListeners()

    const dropdown = document.getElementById('mov-library_1-movie-image-dropdown')
    dropdown.value = ''
    dropdown.dispatchEvent(new Event('change'))

    const hidden = document.getElementById('mov-library_1-movie_selected_image')
    expect(hidden.value).toBe('default')
  })
})

describe('EventHandler.attachLibraryListeners: upload / fetch / delete / rename', () => {
  it('wires upload input change -> ImageHandler.uploadLibraryImage', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `<input type="file" id="mov-library_1-movie-upload-image">`
    })
    window.EventHandler.attachLibraryListeners()

    const uploadInput = document.getElementById('mov-library_1-movie-upload-image')
    // jsdom can't set FileList directly. Fake it with a getter.
    Object.defineProperty(uploadInput, 'files', {
      configurable: true,
      value: [new Blob(['x'], { type: 'image/png' })]
    })
    uploadInput.dispatchEvent(new Event('change'))
    expect(window.ImageHandler.uploadLibraryImage)
      .toHaveBeenCalledWith('mov-library_1', 'movie')
  })

  it('does NOT call uploadLibraryImage when no file was selected', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `<input type="file" id="mov-library_1-movie-upload-image">`
    })
    window.EventHandler.attachLibraryListeners()

    const uploadInput = document.getElementById('mov-library_1-movie-upload-image')
    Object.defineProperty(uploadInput, 'files', {
      configurable: true,
      value: []
    })
    uploadInput.dispatchEvent(new Event('change'))
    expect(window.ImageHandler.uploadLibraryImage).not.toHaveBeenCalled()
  })

  it('wires the fetch button to ImageHandler.fetchLibraryImage', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `<button id="mov-library_1-movie-fetch-url-btn">Fetch</button>`
    })
    window.EventHandler.attachLibraryListeners()
    document.getElementById('mov-library_1-movie-fetch-url-btn').click()
    expect(window.ImageHandler.fetchLibraryImage)
      .toHaveBeenCalledWith('mov-library_1', 'movie')
  })

  it('wires the delete button to ImageHandler.deleteCustomImage', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `<button id="mov-library_1-movie-delete-image-btn">Delete</button>`
    })
    window.EventHandler.attachLibraryListeners()
    document.getElementById('mov-library_1-movie-delete-image-btn').click()
    expect(window.ImageHandler.deleteCustomImage)
      .toHaveBeenCalledWith('mov-library_1', 'movie')
  })

  it('wires the rename button to ImageHandler.openRenameModal', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `<button id="mov-library_1-movie-rename-image-btn">Rename</button>`
    })
    window.EventHandler.attachLibraryListeners()
    document.getElementById('mov-library_1-movie-rename-image-btn').click()
    expect(window.ImageHandler.openRenameModal)
      .toHaveBeenCalledWith('mov-library_1', 'movie')
  })
})

describe('EventHandler.attachLibraryListeners: overlay preview trigger', () => {
  it('calls generateSinglePreview when a movie overlay-toggle checkbox changes', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <input type="checkbox" class="overlay-toggle"
               id="mov-library_1-movie-overlay_ribbon">
      `
    })
    window.EventHandler.attachLibraryListeners()

    const cbx = document.getElementById('mov-library_1-movie-overlay_ribbon')
    cbx.dispatchEvent(new Event('change'))

    expect(window.ImageHandler.generateSinglePreview)
      .toHaveBeenCalledWith('mov-library_1', 'movie')
  })

  it('extracts the type from the input id (season / episode / show)', () => {
    buildLibraryCard({
      libraryId: 'sho-library_1',
      innerHTML: `
        <input type="checkbox" class="overlay-toggle"
               id="sho-library_1-episode-overlay_ribbon">
      `
    })
    window.EventHandler.attachLibraryListeners()

    const cbx = document.getElementById('sho-library_1-episode-overlay_ribbon')
    cbx.dispatchEvent(new Event('change'))

    expect(window.ImageHandler.generateSinglePreview)
      .toHaveBeenCalledWith('sho-library_1', 'episode')
  })

  it('falls back to library-level type when the id lacks the -<type>-overlay_ pattern', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <input type="checkbox" class="overlay-toggle"
               id="mov-library_1-something-else">
      `
    })
    window.EventHandler.attachLibraryListeners()

    const cbx = document.getElementById('mov-library_1-something-else')
    cbx.dispatchEvent(new Event('change'))

    // isMovie=true -> falls back to 'movie'
    expect(window.ImageHandler.generateSinglePreview)
      .toHaveBeenCalledWith('mov-library_1', 'movie')
  })

  it('is idempotent (does not double-fire preview on repeat attachment)', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <input type="checkbox" class="overlay-toggle"
               id="mov-library_1-movie-overlay_ribbon">
      `
    })
    window.EventHandler.attachLibraryListeners()
    window.EventHandler.attachLibraryListeners()

    const cbx = document.getElementById('mov-library_1-movie-overlay_ribbon')
    // Clear the initializeOverlays call counts that happened during attach.
    window.ImageHandler.generateSinglePreview.mockClear()
    cbx.dispatchEvent(new Event('change'))
    expect(window.ImageHandler.generateSinglePreview).toHaveBeenCalledTimes(1)
  })
})

describe('EventHandler.attachLibraryListeners: separator dropdown', () => {
  it('wires the separator dropdown change to OverlayHandler.updateHiddenInputs', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <select id="mov-library_1-attribute_use_separator">
          <option value="none">none</option>
          <option value="line">line</option>
        </select>
      `
    })
    window.EventHandler.attachLibraryListeners()
    // Clear the "run once during attach" call:
    window.OverlayHandler.updateHiddenInputs.mockClear()

    const dropdown = document.getElementById('mov-library_1-attribute_use_separator')
    dropdown.value = 'line'
    dropdown.dispatchEvent(new Event('change'))

    expect(window.OverlayHandler.updateHiddenInputs)
      .toHaveBeenCalledWith('mov-library_1', true)
  })

  it('calls updateHiddenInputs once immediately during attach (initial sync)', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <select id="mov-library_1-attribute_use_separator"></select>
      `
    })
    window.EventHandler.attachLibraryListeners()
    // Once for the immediate call inside attach.
    expect(window.OverlayHandler.updateHiddenInputs)
      .toHaveBeenCalledWith('mov-library_1', true)
  })
})

describe('EventHandler.attachLibraryListeners: list-based custom add flow', () => {
  it('restores saved items from the hidden JSON input on attach', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <button id="mov-library_1-mass_genre_update_custom_add">Add</button>
        <ul id="mov-library_1-mass_genre_update_custom_list"></ul>
        <input type="hidden" id="mov-library_1-mass_genre_update_custom_hidden"
               value='["Action","Drama"]'>
        <input type="text" id="mov-library_1-mass_genre_update_custom_input">
      `
    })
    window.EventHandler.attachLibraryListeners()

    const list = document.getElementById('mov-library_1-mass_genre_update_custom_list')
    const items = Array.from(list.children).map(li => li.firstChild.textContent)
    expect(items).toEqual(['Action', 'Drama'])
  })

  it('appends a new item when the add button is clicked with input value', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <button id="mov-library_1-mass_genre_update_custom_add">Add</button>
        <ul id="mov-library_1-mass_genre_update_custom_list"></ul>
        <input type="hidden" id="mov-library_1-mass_genre_update_custom_hidden" value="[]">
        <input type="text" id="mov-library_1-mass_genre_update_custom_input">
      `
    })
    window.EventHandler.attachLibraryListeners()

    const input = document.getElementById('mov-library_1-mass_genre_update_custom_input')
    input.value = 'Comedy'
    document.getElementById('mov-library_1-mass_genre_update_custom_add').click()

    const list = document.getElementById('mov-library_1-mass_genre_update_custom_list')
    expect(list.children).toHaveLength(1)
    expect(list.firstChild.textContent).toContain('Comedy')

    // Input should be cleared
    expect(input.value).toBe('')

    // Hidden JSON should be updated
    const hidden = document.getElementById('mov-library_1-mass_genre_update_custom_hidden')
    expect(JSON.parse(hidden.value)).toEqual(['Comedy'])
  })

  it('ignores add clicks when input is empty or whitespace', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <button id="mov-library_1-mass_genre_update_custom_add">Add</button>
        <ul id="mov-library_1-mass_genre_update_custom_list"></ul>
        <input type="hidden" id="mov-library_1-mass_genre_update_custom_hidden" value="[]">
        <input type="text" id="mov-library_1-mass_genre_update_custom_input" value="   ">
      `
    })
    window.EventHandler.attachLibraryListeners()

    document.getElementById('mov-library_1-mass_genre_update_custom_add').click()

    const list = document.getElementById('mov-library_1-mass_genre_update_custom_list')
    expect(list.children).toHaveLength(0)
  })

  it('removes an item and updates the hidden input when the remove button is clicked', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <button id="mov-library_1-mass_genre_update_custom_add">Add</button>
        <ul id="mov-library_1-mass_genre_update_custom_list"></ul>
        <input type="hidden" id="mov-library_1-mass_genre_update_custom_hidden"
               value='["Action","Drama"]'>
        <input type="text" id="mov-library_1-mass_genre_update_custom_input">
      `
    })
    window.EventHandler.attachLibraryListeners()

    // Click the remove button on the first item ("Action").
    const list = document.getElementById('mov-library_1-mass_genre_update_custom_list')
    const firstRemoveBtn = list.firstChild.querySelector('button')
    firstRemoveBtn.click()

    // Only "Drama" should remain.
    const remaining = Array.from(list.children).map(li => li.firstChild.textContent)
    expect(remaining).toEqual(['Drama'])

    const hidden = document.getElementById('mov-library_1-mass_genre_update_custom_hidden')
    expect(JSON.parse(hidden.value)).toEqual(['Drama'])
  })

  it('gracefully handles malformed JSON in the hidden input (resets to [])', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <button id="mov-library_1-mass_genre_update_custom_add">Add</button>
        <ul id="mov-library_1-mass_genre_update_custom_list"></ul>
        <input type="hidden" id="mov-library_1-mass_genre_update_custom_hidden"
               value='not-valid-json'>
        <input type="text" id="mov-library_1-mass_genre_update_custom_input">
      `
    })
    // Should NOT throw despite the malformed input.
    expect(() => window.EventHandler.attachLibraryListeners()).not.toThrow()
    const hidden = document.getElementById('mov-library_1-mass_genre_update_custom_hidden')
    expect(hidden.value).toBe('[]')
  })
})

describe('EventHandler.attachLibraryListeners: rating validation (0-10)', () => {
  it('marks a rating input invalid when the value is out of range', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <div>
          <input type="number" data-validate="rating" id="rating"
                 min="0" max="10" value="99">
          <div class="invalid-feedback">Bad rating</div>
        </div>
      `
    })
    // Force the element to be visible (offsetParent must be truthy for
    // the validator to actually check). In jsdom offsetParent is null
    // by default; we shim it.
    Object.defineProperty(HTMLElement.prototype, 'offsetParent', {
      configurable: true,
      get () { return document.body }
    })
    window.EventHandler.attachLibraryListeners()

    const rating = document.getElementById('rating')
    expect(rating.classList.contains('is-invalid')).toBe(true)
  })

  it('marks a rating input valid when the value is in range', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <div>
          <input type="number" data-validate="rating" id="rating"
                 min="0" max="10" value="7.5">
        </div>
      `
    })
    Object.defineProperty(HTMLElement.prototype, 'offsetParent', {
      configurable: true,
      get () { return document.body }
    })
    window.EventHandler.attachLibraryListeners()

    const rating = document.getElementById('rating')
    expect(rating.classList.contains('is-invalid')).toBe(false)
  })

  it('skips validation entirely when the input is hidden (offsetParent null)', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <input type="number" data-validate="rating" id="rating"
               min="0" max="10" value="99">
      `
    })
    // offsetParent stays null (jsdom default) -> validator early-returns
    // without marking is-invalid.
    window.EventHandler.attachLibraryListeners()
    const rating = document.getElementById('rating')
    expect(rating.classList.contains('is-invalid')).toBe(false)
  })

  it('restores the min/max attributes from data-saved on attach', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <input type="number" data-validate="rating" id="rating" value="5">
      `
    })
    window.EventHandler.attachLibraryListeners()

    const rating = document.getElementById('rating')
    // Defaults to 0/10 when no min/max were set.
    expect(rating.getAttribute('min')).toBe('0')
    expect(rating.getAttribute('max')).toBe('10')
    expect(rating.dataset.minSaved).toBe('0')
    expect(rating.dataset.maxSaved).toBe('10')
  })
})

describe('EventHandler.attachLibraryListeners: bubble handler', () => {
  it('marks every non-hidden input/select/textarea in the card with data-highlight-listener', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <input type="text" id="a">
        <input type="hidden" id="b">
        <select id="c"><option>x</option></select>
        <textarea id="d"></textarea>
      `
    })
    window.EventHandler.attachLibraryListeners()

    expect(document.getElementById('a').dataset.highlightListener).toBe('true')
    // Hidden inputs are NOT wired
    expect(document.getElementById('b').dataset.highlightListener).toBeUndefined()
    expect(document.getElementById('c').dataset.highlightListener).toBe('true')
    expect(document.getElementById('d').dataset.highlightListener).toBe('true')
  })

  it('marks the library container with data-highlight-delegate="true"', () => {
    const { container } = buildLibraryCard({ libraryId: 'mov-library_1' })
    window.EventHandler.attachLibraryListeners()
    expect(container.dataset.highlightDelegate).toBe('true')
  })

  it('bubbles a change event to updateValidationState', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `<input type="text" id="thing">`
    })
    window.EventHandler.attachLibraryListeners()
    window.ValidationHandler.updateValidationState.mockClear()

    const thing = document.getElementById('thing')
    thing.dispatchEvent(new Event('change', { bubbles: true }))
    expect(window.ValidationHandler.updateValidationState).toHaveBeenCalled()
  })

  it('skips inputs marked data-skip-library-input-bubble="true"', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <input type="text" id="thing" data-skip-library-input-bubble="true">
      `
    })
    window.EventHandler.attachLibraryListeners()
    window.ValidationHandler.updateValidationState.mockClear()

    document.getElementById('thing').dispatchEvent(new Event('change', { bubbles: true }))
    expect(window.ValidationHandler.updateValidationState).not.toHaveBeenCalled()
  })

  it('skips inputs inside a [data-overlay-source-editor="true"] ancestor', () => {
    buildLibraryCard({
      libraryId: 'mov-library_1',
      innerHTML: `
        <div data-overlay-source-editor="true">
          <input type="text" id="thing">
        </div>
      `
    })
    window.EventHandler.attachLibraryListeners()
    window.ValidationHandler.updateValidationState.mockClear()

    document.getElementById('thing').dispatchEvent(new Event('change', { bubbles: true }))
    expect(window.ValidationHandler.updateValidationState).not.toHaveBeenCalled()
  })
})
