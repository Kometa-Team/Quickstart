// Tests for static/local-js/eventHandler.js (#1335 Step 8 - coverage push).
//
// eventHandler.js is a classic script with heavy side effects at import:
//   - Attaches ImageHandler-driven listeners to `.library-checkbox` and
//     `[id$='-card-container']` (attachLibraryListeners)
//   - Creates a MutationObserver on document.body that re-runs
//     attachLibraryListeners on any DOM addition matching certain rules
//   - Runs installRatingSubmitGuard on document.forms
//   - Restores template-variable-select values from data-selected
//   - Runs updateAccordionHighlights + expandCheckedChildToggleSections
//
// Approach: same side-effect-import pattern as validationHandler and
// imageHandler tests. Seed globals + empty DOM before import so the
// initial cascade is a no-op, then exercise EventHandler methods with
// per-test DOM fixtures.
//
// The MutationObserver installed on document.body IS still active
// during tests. That's fine because attachLibraryListeners uses
// dataset.listenerAdded flags for idempotency, and the fixtures we
// build for these tests don't include library-checkbox or card-
// container elements that would trigger re-attachment.
//
// Test scope for THIS FILE:
//   - EventHandler: module registration      (window.EventHandler surface check)
//   - EventHandler.toggleLibraryVisibility   (simple DOM)
//
// The accordion-highlight helpers previously exercised here
// (updateAccordionHighlights, hasCheckedTemplateGroupToggle,
// hasLibraryFileEntries, highlightParentAccordions, removeHighlightIfEmpty)
// moved to tests/js/modules/accordionHighlights.test.js in #1346 step 2f
// when the compat shim was removed. They're tested there against a
// direct module import instead of via window.EventHandler.
//
// attachLibraryListeners lives in tests/js/eventHandlerAttachLibraryListeners.test.js.
//
// Explicitly out of scope for THIS FILE:
//   - The MutationObserver callback itself
//   - The mapping list handler (genre_mapper etc.)
//   - installRatingSubmitGuard
//   - expandCheckedChildToggleSections

import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

beforeAll(async () => {
  // Silence chatty console output during tests (log/debug/warn all fire
  // multiple times per method).
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'debug').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})

  // Stub globals the module (and its dependencies) reach for.
  window.ValidationHandler = {
    restoreSelectedLibraries: vi.fn(),
    updateValidationState: vi.fn()
  }
  // ImageHandler is referenced inside attachLibraryListeners; the loops
  // that call it iterate over empty selectors at import time, so we can
  // provide a minimal shim.
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

  // Seed an EMPTY DOM so the module's initial attachLibraryListeners,
  // updateAccordionHighlights, and expandCheckedChildToggleSections
  // walk empty NodeLists.
  document.body.innerHTML = ''

  await import('../../static/local-js/eventHandler.js')
})

beforeEach(() => {
  document.body.innerHTML = ''
})

afterEach(() => {
  vi.restoreAllMocks()
  // Re-spy on console methods after restoreAllMocks nukes them.
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'debug').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('EventHandler: module registration', () => {
  it('attaches EventHandler to window', () => {
    expect(window.EventHandler).toBeDefined()
    expect(typeof window.EventHandler.toggleLibraryVisibility).toBe('function')
  })

  it('exposes the expected method surface', () => {
    // Accordion-highlight methods (updateAccordionHighlights, hasCheckedTemplateGroupToggle,
    // hasLibraryFileEntries, highlightParentAccordions, removeHighlightIfEmpty)
    // are NOT on this surface anymore -- they were migrated to
    // static/local-js/modules/accordionHighlights.js in #1346 step 2f
    // and the compat shim was removed. See tests/js/modules/accordionHighlights.test.js.
    for (const method of [
      'attachLibraryListeners',
      'toggleLibraryVisibility'
    ]) {
      expect(typeof window.EventHandler[method]).toBe('function')
    }
  })
})

describe('EventHandler.toggleLibraryVisibility', () => {
  it('sets display:block when isVisible=true', () => {
    document.body.innerHTML = `<div id="mov-library_1-card-container" style="display: none"></div>`
    window.EventHandler.toggleLibraryVisibility('mov-library_1', true)
    expect(document.getElementById('mov-library_1-card-container').style.display).toBe('block')
  })

  it('sets display:none when isVisible=false', () => {
    document.body.innerHTML = `<div id="mov-library_1-card-container" style="display: block"></div>`
    window.EventHandler.toggleLibraryVisibility('mov-library_1', false)
    expect(document.getElementById('mov-library_1-card-container').style.display).toBe('none')
  })

  it('warns and no-ops when the container element is missing', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    // No matching element in DOM
    window.EventHandler.toggleLibraryVisibility('nonexistent', true)
    expect(warnSpy).toHaveBeenCalled()
    expect(warnSpy.mock.calls[0][0]).toContain('nonexistent-card-container')
  })

  it('toggles cleanly across successive calls', () => {
    document.body.innerHTML = `<div id="sho-library_1-card-container"></div>`
    const el = document.getElementById('sho-library_1-card-container')
    window.EventHandler.toggleLibraryVisibility('sho-library_1', true)
    expect(el.style.display).toBe('block')
    window.EventHandler.toggleLibraryVisibility('sho-library_1', false)
    expect(el.style.display).toBe('none')
    window.EventHandler.toggleLibraryVisibility('sho-library_1', true)
    expect(el.style.display).toBe('block')
  })
})
