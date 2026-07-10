// Tests for static/local-js/imageHandler.js (#1335 Step 8 - coverage push).
//
// imageHandler.js is an ES module (#1346 Step 2 finish) that also
// attaches `ImageHandler` to `window` for backward compat with the
// eventHandler/overlayHandler consumers. Several side effects run at
// import time:
//   - Reads `document.querySelectorAll('.form-check-input')` to attach a
//     change listener. Empty result when the DOM has no such elements, so
//     we're safe as long as the DOM is empty (or has none of those) at
//     import time.
//   - Calls to `showToast` and `updateFormData` are all inside methods,
//     not at module scope — no globals are called during import itself.
//
// The module references two globals that don't exist in jsdom:
//   - showToast(kind, message)       — normally provided by 000-base.js
//   - updateFormData(inputEl)        — normally provided by 000-base.js
// Tests stub these on window before import so any accidental invocation
// inside a method under test is captured rather than crashing.
//
// Approach: same side-effect-import pattern as validationHandler.test.js:
// seed a minimal DOM before import, then exercise ImageHandler methods.
//
// Test scope: the pure helpers and small DOM-manipulating methods. The
// large `getLibraryOverlays` (350 lines walking many .overlay-group
// subtrees) is out of scope for this PR — that needs its own dedicated
// test file with realistic overlay-group fixtures.

import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

let showToastMock
let updateFormDataMock

beforeAll(async () => {
  // Silence the module's very chatty console output during tests.
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'debug').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})

  // Stub globals the module reaches for. We install them on window
  // (which is `global` in jsdom's default setup) BEFORE the import so
  // the module's top-level closure sees them.
  showToastMock = vi.fn()
  updateFormDataMock = vi.fn()
  window.showToast = showToastMock
  window.updateFormData = updateFormDataMock
  // Some methods reference `showToast` bare (not `window.showToast`),
  // which resolves via the jsdom global scope. Mirror them.
  globalThis.showToast = showToastMock
  globalThis.updateFormData = updateFormDataMock

  // Seed a blank DOM before the module's on-import querySelectorAll runs.
  document.body.innerHTML = ''

  await import('../../static/local-js/imageHandler.js')
})

beforeEach(() => {
  showToastMock.mockClear()
  updateFormDataMock.mockClear()
  document.body.innerHTML = ''
})

afterEach(() => {
  vi.restoreAllMocks()
  // Re-spy on log/debug/warn/error after restoreAllMocks (which nukes them).
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'debug').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('ImageHandler: module registration', () => {
  it('attaches ImageHandler to window', () => {
    expect(window.ImageHandler).toBeDefined()
    expect(typeof window.ImageHandler.isBuiltinPreviewImage).toBe('function')
  })

  it('exposes BUILTIN_PREVIEW_IMAGES as a Set with the two known guide images', () => {
    const set = window.ImageHandler.BUILTIN_PREVIEW_IMAGES
    expect(set).toBeInstanceOf(Set)
    expect(set.has('overlay_alignment_guide.png')).toBe(true)
    expect(set.has('overlay_alignment_guide_episodes.png')).toBe(true)
    expect(set.size).toBe(2)
  })

  it('exposes BUILTIN_PREVIEW_IMAGES_BY_TYPE with the four supported types', () => {
    const map = window.ImageHandler.BUILTIN_PREVIEW_IMAGES_BY_TYPE
    expect(Object.keys(map).sort()).toEqual(['episode', 'movie', 'season', 'show'])
    expect(map.movie).toBeInstanceOf(Set)
  })

  it('maps only the episodes guide to type=episode', () => {
    const map = window.ImageHandler.BUILTIN_PREVIEW_IMAGES_BY_TYPE
    expect(map.episode.has('overlay_alignment_guide_episodes.png')).toBe(true)
    expect(map.episode.has('overlay_alignment_guide.png')).toBe(false)
  })

  it('maps the standard guide to movie/show/season (not episode)', () => {
    const map = window.ImageHandler.BUILTIN_PREVIEW_IMAGES_BY_TYPE
    for (const type of ['movie', 'show', 'season']) {
      expect(map[type].has('overlay_alignment_guide.png')).toBe(true)
      expect(map[type].has('overlay_alignment_guide_episodes.png')).toBe(false)
    }
  })
})

describe('ImageHandler.isBuiltinPreviewImage', () => {
  it('returns true for the known movie/show/season guide', () => {
    expect(window.ImageHandler.isBuiltinPreviewImage('overlay_alignment_guide.png')).toBe(true)
  })

  it('returns true for the known episodes guide', () => {
    expect(window.ImageHandler.isBuiltinPreviewImage('overlay_alignment_guide_episodes.png')).toBe(true)
  })

  it('returns false for an arbitrary custom filename', () => {
    expect(window.ImageHandler.isBuiltinPreviewImage('user_upload.png')).toBe(false)
  })

  it('returns false for the default sentinel', () => {
    expect(window.ImageHandler.isBuiltinPreviewImage('default')).toBe(false)
  })

  it('returns false for empty / undefined input', () => {
    expect(window.ImageHandler.isBuiltinPreviewImage('')).toBe(false)
    expect(window.ImageHandler.isBuiltinPreviewImage(undefined)).toBe(false)
  })
})

describe('ImageHandler.isBuiltinPreviewImageForType', () => {
  it('returns true for the standard guide + movie', () => {
    expect(window.ImageHandler.isBuiltinPreviewImageForType(
      'overlay_alignment_guide.png', 'movie'
    )).toBe(true)
  })

  it('returns true for the standard guide + show', () => {
    expect(window.ImageHandler.isBuiltinPreviewImageForType(
      'overlay_alignment_guide.png', 'show'
    )).toBe(true)
  })

  it('returns true for the standard guide + season', () => {
    expect(window.ImageHandler.isBuiltinPreviewImageForType(
      'overlay_alignment_guide.png', 'season'
    )).toBe(true)
  })

  it('returns false for the standard guide + episode', () => {
    // The episodes-specific guide is only for episode; the standard
    // guide does not apply. This mismatch matters — episode previews
    // use a different aspect ratio.
    expect(window.ImageHandler.isBuiltinPreviewImageForType(
      'overlay_alignment_guide.png', 'episode'
    )).toBe(false)
  })

  it('returns true for the episodes guide + episode', () => {
    expect(window.ImageHandler.isBuiltinPreviewImageForType(
      'overlay_alignment_guide_episodes.png', 'episode'
    )).toBe(true)
  })

  it('returns false for the episodes guide + non-episode types', () => {
    for (const type of ['movie', 'show', 'season']) {
      expect(window.ImageHandler.isBuiltinPreviewImageForType(
        'overlay_alignment_guide_episodes.png', type
      )).toBe(false)
    }
  })

  it('returns false for a custom image regardless of type', () => {
    expect(window.ImageHandler.isBuiltinPreviewImageForType('custom.png', 'movie')).toBe(false)
  })

  it('returns false for an unknown type (safe optional-chaining fallback)', () => {
    expect(window.ImageHandler.isBuiltinPreviewImageForType(
      'overlay_alignment_guide.png', 'ridiculous_type'
    )).toBe(false)
  })
})

describe('ImageHandler.toggleDeleteButton', () => {
  function seedDom ({
    libraryId = 'mov-library_1',
    type = 'movie',
    dropdownValue = 'default',
    dropdownOptions = ['default']
  } = {}) {
    const optionsHtml = dropdownOptions
      .map(v => `<option value="${v}" ${v === dropdownValue ? 'selected' : ''}>${v}</option>`)
      .join('')
    document.body.innerHTML = `
      <select id="${libraryId}-${type}-image-dropdown">${optionsHtml}</select>
      <button id="${libraryId}-${type}-delete-image-btn">Delete</button>
      <button id="${libraryId}-${type}-rename-image-btn">Rename</button>
    `
    return {
      dropdown: document.getElementById(`${libraryId}-${type}-image-dropdown`),
      deleteBtn: document.getElementById(`${libraryId}-${type}-delete-image-btn`),
      renameBtn: document.getElementById(`${libraryId}-${type}-rename-image-btn`)
    }
  }

  it('hides delete + rename when the "default" sentinel is selected', () => {
    const { deleteBtn, renameBtn } = seedDom({ dropdownValue: 'default' })
    window.ImageHandler.toggleDeleteButton('mov-library_1', 'movie')
    expect(deleteBtn.style.display).toBe('none')
    expect(renameBtn.style.display).toBe('none')
  })

  it('hides delete + rename when a builtin preview image is selected', () => {
    const { deleteBtn, renameBtn } = seedDom({
      dropdownValue: 'overlay_alignment_guide.png',
      dropdownOptions: ['default', 'overlay_alignment_guide.png']
    })
    window.ImageHandler.toggleDeleteButton('mov-library_1', 'movie')
    expect(deleteBtn.style.display).toBe('none')
    expect(renameBtn.style.display).toBe('none')
  })

  it('shows delete + rename when a user-uploaded image is selected', () => {
    const { deleteBtn, renameBtn } = seedDom({
      dropdownValue: 'my_poster.png',
      dropdownOptions: ['default', 'my_poster.png']
    })
    window.ImageHandler.toggleDeleteButton('mov-library_1', 'movie')
    expect(deleteBtn.style.display).toBe('block')
    expect(renameBtn.style.display).toBe('block')
  })

  it('hides delete + rename when only the "default" option exists', () => {
    // Edge case: dropdown has just the default sentinel, so even if
    // that IS "selected", we should treat the picker as empty.
    const { deleteBtn, renameBtn } = seedDom({
      dropdownValue: 'default',
      dropdownOptions: ['default']
    })
    window.ImageHandler.toggleDeleteButton('mov-library_1', 'movie')
    expect(deleteBtn.style.display).toBe('none')
    expect(renameBtn.style.display).toBe('none')
  })

  it('defaults type to "movie" when omitted', () => {
    const { deleteBtn } = seedDom({ type: 'movie', dropdownValue: 'x.png', dropdownOptions: ['default', 'x.png'] })
    window.ImageHandler.toggleDeleteButton('mov-library_1') // no type arg
    expect(deleteBtn.style.display).toBe('block')
  })

  it('logs an error and no-ops when any of the three elements is missing', () => {
    // Only the dropdown present, buttons missing entirely.
    document.body.innerHTML = `
      <select id="mov-library_1-movie-image-dropdown"><option value="default">default</option></select>
    `
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    window.ImageHandler.toggleDeleteButton('mov-library_1', 'movie')
    expect(errSpy).toHaveBeenCalled()
    // No throw — the "missing element" branch just returns early.
  })
})

describe('ImageHandler.loadAvailableImages', () => {
  function seedDom (libraryId = 'mov-library_1', type = 'movie') {
    document.body.innerHTML = `
      <select id="${libraryId}-${type}-image-dropdown">
        <option value="stale">stale</option>
      </select>
      <input type="hidden" id="${libraryId}-${type}_selected_image" value="">
    `
    return {
      dropdown: document.getElementById(`${libraryId}-${type}-image-dropdown`),
      hidden: document.getElementById(`${libraryId}-${type}_selected_image`)
    }
  }

  it('no-ops silently when the dropdown is missing', async () => {
    // No fetch call should be made; showToast should not fire.
    const fetchSpy = vi.fn(); vi.stubGlobal("fetch", fetchSpy)
    window.ImageHandler.loadAvailableImages('nope-library', 'movie')
    expect(fetchSpy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('populates the dropdown with the default option + fetched images', async () => {
    const { dropdown } = seedDom()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({
        status: 'success',
        images: ['first.png', 'second.png']
      })
    })))

    window.ImageHandler.loadAvailableImages('mov-library_1', 'movie')
    // Let the fetch/then microtasks flush
    await new Promise(resolve => setTimeout(resolve, 0))

    const values = Array.from(dropdown.options).map(o => o.value)
    expect(values).toEqual(['default', 'first.png', 'second.png'])
    // First option is the "Select Uploaded Image" placeholder
    expect(dropdown.options[0].textContent).toBe('Select Uploaded Image')

    vi.unstubAllGlobals()
  })

  it('shows an error toast when the server returns status != success', async () => {
    seedDom()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ status: 'error', message: 'nope' })
    })))

    window.ImageHandler.loadAvailableImages('mov-library_1', 'movie')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(showToastMock).toHaveBeenCalledWith('error', 'nope')

    vi.unstubAllGlobals()
  })

  it('shows a generic error toast when the fetch itself rejects', async () => {
    seedDom()
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('boom'))))

    // Silence the error log that the .catch emits.
    vi.spyOn(console, 'error').mockImplementation(() => {})

    window.ImageHandler.loadAvailableImages('mov-library_1', 'movie')
    // Two microtask flushes: .then chain -> .catch
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(showToastMock).toHaveBeenCalledWith('error', 'Could not load image list.')

    vi.unstubAllGlobals()
  })

  it('requests /list_uploaded_images with the right type query param', async () => {
    seedDom('mov-library_1', 'show')
    const fetchMock = vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ status: 'success', images: [] })
    }))
    vi.stubGlobal('fetch', fetchMock)

    window.ImageHandler.loadAvailableImages('mov-library_1', 'show')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(fetchMock).toHaveBeenCalledWith('/list_uploaded_images?type=show')
    vi.unstubAllGlobals()
  })
})

describe('ImageHandler.deleteCustomImage', () => {
  function seedDom ({
    libraryId = 'mov-library_1',
    type = 'movie',
    dropdownValue = 'my_custom.png'
  } = {}) {
    document.body.innerHTML = `
      <select id="${libraryId}-${type}-image-dropdown">
        <option value="default">default</option>
        <option value="my_custom.png" ${dropdownValue === 'my_custom.png' ? 'selected' : ''}>my_custom.png</option>
      </select>
      <input type="hidden" id="${libraryId}-${type}-hidden" value="${dropdownValue}">
      <button id="${libraryId}-${type}-delete-image-btn"></button>
      <button id="${libraryId}-${type}-rename-image-btn"></button>
    `
    if (dropdownValue === 'default') {
      document.querySelector(`#${libraryId}-${type}-image-dropdown`).value = 'default'
    }
    return {
      dropdown: document.getElementById(`${libraryId}-${type}-image-dropdown`),
      hidden: document.getElementById(`${libraryId}-${type}-hidden`)
    }
  }

  it('warns and no-ops when nothing is selected', () => {
    document.body.innerHTML = `
      <select id="mov-library_1-movie-image-dropdown">
        <option value="" selected></option>
      </select>
    `
    const fetchSpy = vi.fn(); vi.stubGlobal("fetch", fetchSpy)
    window.ImageHandler.deleteCustomImage('mov-library_1', 'movie')
    expect(showToastMock).toHaveBeenCalledWith('warning', 'Please select an image to delete.')
    expect(fetchSpy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('warns when the "default" sentinel is selected', () => {
    seedDom({ dropdownValue: 'default' })
    const fetchSpy = vi.fn(); vi.stubGlobal("fetch", fetchSpy)
    window.ImageHandler.deleteCustomImage('mov-library_1', 'movie')
    expect(showToastMock).toHaveBeenCalledWith('warning', 'Please select an image to delete.')
    expect(fetchSpy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('warns when a builtin preview image is selected (they are not deletable)', () => {
    document.body.innerHTML = `
      <select id="mov-library_1-movie-image-dropdown">
        <option value="overlay_alignment_guide.png" selected>overlay_alignment_guide.png</option>
      </select>
    `
    const fetchSpy = vi.fn(); vi.stubGlobal("fetch", fetchSpy)
    window.ImageHandler.deleteCustomImage('mov-library_1', 'movie')
    expect(showToastMock).toHaveBeenCalledWith('warning', 'Please select an image to delete.')
    expect(fetchSpy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('sends a DELETE and resets state on success', async () => {
    const { dropdown, hidden } = seedDom({ dropdownValue: 'my_custom.png' })
    const fetchMock = vi.fn()
      // First call: /delete_library_image
      .mockImplementationOnce(() => Promise.resolve({
        json: () => Promise.resolve({ status: 'success', message: 'Deleted!' })
      }))
      // Subsequent call from loadAvailableImages inside the success branch
      .mockImplementation(() => Promise.resolve({
        json: () => Promise.resolve({ status: 'success', images: [] })
      }))
    vi.stubGlobal('fetch', fetchMock)

    window.ImageHandler.deleteCustomImage('mov-library_1', 'movie')
    await new Promise(resolve => setTimeout(resolve, 0))
    // Also let the inner loadAvailableImages chain flush
    await new Promise(resolve => setTimeout(resolve, 0))

    // First fetch call was the DELETE with the encoded filename
    expect(fetchMock.mock.calls[0][0]).toBe('/delete_library_image/my_custom.png?type=movie')
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE')

    // Success toast fired
    expect(showToastMock).toHaveBeenCalledWith('success', 'Deleted!')

    // Dropdown reset to default, hidden cleared to 'default'
    expect(dropdown.value).toBe('default')
    expect(hidden.value).toBe('default')

    vi.unstubAllGlobals()
  })

  it('URL-encodes filenames that contain spaces', async () => {
    document.body.innerHTML = `
      <select id="mov-library_1-movie-image-dropdown">
        <option value="my file.png" selected>my file.png</option>
      </select>
      <button id="mov-library_1-movie-delete-image-btn"></button>
      <button id="mov-library_1-movie-rename-image-btn"></button>
    `
    const fetchMock = vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ status: 'success', message: 'ok' })
    }))
    vi.stubGlobal('fetch', fetchMock)

    window.ImageHandler.deleteCustomImage('mov-library_1', 'movie')
    await new Promise(resolve => setTimeout(resolve, 0))

    // %20 or + depending on encodeURIComponent; it's %20
    expect(fetchMock.mock.calls[0][0]).toBe('/delete_library_image/my%20file.png?type=movie')
    vi.unstubAllGlobals()
  })

  it('shows an error toast when server responds with status != success', async () => {
    seedDom()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ status: 'error', message: 'no perms' })
    })))
    window.ImageHandler.deleteCustomImage('mov-library_1', 'movie')
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(showToastMock).toHaveBeenCalledWith('error', 'no perms')
    vi.unstubAllGlobals()
  })

  it('shows a generic error toast when the fetch rejects', async () => {
    seedDom()
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('offline'))))
    vi.spyOn(console, 'error').mockImplementation(() => {})
    window.ImageHandler.deleteCustomImage('mov-library_1', 'movie')
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(showToastMock).toHaveBeenCalledWith('error', 'Image deletion failed.')
    vi.unstubAllGlobals()
  })
})

describe('ImageHandler.uploadLibraryImage', () => {
  function seedDom (libraryId = 'mov-library_1', type = 'movie', withFile = true) {
    document.body.innerHTML = `
      <input type="file" id="${libraryId}-${type}-upload-image">
      <select id="${libraryId}-${type}-image-dropdown"><option value="default">default</option></select>
      <button id="${libraryId}-${type}-delete-image-btn"></button>
      <button id="${libraryId}-${type}-rename-image-btn"></button>
    `
    if (withFile) {
      // Attach a fake FileList via Object.defineProperty (jsdom's file
      // input doesn't accept programmatic assignment normally).
      const fileInput = document.getElementById(`${libraryId}-${type}-upload-image`)
      const fakeFile = new File(['contents'], 'poster.png', { type: 'image/png' })
      Object.defineProperty(fileInput, 'files', {
        value: [fakeFile],
        configurable: true
      })
    }
  }

  it('warns and no-ops when no file input is present', () => {
    const fetchSpy = vi.fn(); vi.stubGlobal("fetch", fetchSpy)
    window.ImageHandler.uploadLibraryImage('nope', 'movie')
    expect(showToastMock).toHaveBeenCalledWith('warning', 'Please select an image file.')
    expect(fetchSpy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('warns and no-ops when file input has no files selected', () => {
    seedDom('mov-library_1', 'movie', false)
    const fetchSpy = vi.fn(); vi.stubGlobal("fetch", fetchSpy)
    window.ImageHandler.uploadLibraryImage('mov-library_1', 'movie')
    expect(showToastMock).toHaveBeenCalledWith('warning', 'Please select an image file.')
    expect(fetchSpy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('POSTs to /upload_library_image with a FormData body', async () => {
    seedDom('mov-library_1', 'movie', true)
    const fetchMock = vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ status: 'success', message: 'uploaded', filename: 'poster.png' })
    }))
    vi.stubGlobal('fetch', fetchMock)

    window.ImageHandler.uploadLibraryImage('mov-library_1', 'movie')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(fetchMock).toHaveBeenCalled()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/upload_library_image')
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    vi.unstubAllGlobals()
  })
})
