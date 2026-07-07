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
// Test scope for THIS PR (deliberately narrow):
//   - toggleLibraryVisibility           (simple DOM)
//   - hasCheckedTemplateGroupToggle     (pure predicate)
//   - hasLibraryFileEntries             (pure predicate)
//   - highlightParentAccordions         (ancestor walker)
//   - removeHighlightIfEmpty            (recursive cleanup)
//   - updateAccordionHighlights         (top-level integrator, sampled)
//
// Explicitly out of scope for THIS PR:
//   - attachLibraryListeners  (500+ lines of DOM wiring across many
//     wizard shapes; needs a dedicated PR with realistic fixtures)
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
    for (const method of [
      'attachLibraryListeners',
      'toggleLibraryVisibility',
      'hasCheckedTemplateGroupToggle',
      'hasLibraryFileEntries',
      'updateAccordionHighlights',
      'highlightParentAccordions',
      'removeHighlightIfEmpty'
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

describe('EventHandler.hasCheckedTemplateGroupToggle', () => {
  it('returns null when accordionBody is null/undefined', () => {
    expect(window.EventHandler.hasCheckedTemplateGroupToggle(null)).toBeNull()
    expect(window.EventHandler.hasCheckedTemplateGroupToggle(undefined)).toBeNull()
  })

  it('returns null when the body has no template-group toggles', () => {
    document.body.innerHTML = `<div id="body"><input type="text"></div>`
    const body = document.getElementById('body')
    expect(window.EventHandler.hasCheckedTemplateGroupToggle(body)).toBeNull()
  })

  it('returns true when at least one template-group toggle is checked', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="checkbox" data-template-group>
        <input type="checkbox" data-template-group checked>
        <input type="checkbox" data-template-group>
      </div>
    `
    const body = document.getElementById('body')
    expect(window.EventHandler.hasCheckedTemplateGroupToggle(body)).toBe(true)
  })

  it('returns false when template-group toggles exist but none are checked', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="checkbox" data-template-group>
        <input type="checkbox" data-template-group>
      </div>
    `
    const body = document.getElementById('body')
    expect(window.EventHandler.hasCheckedTemplateGroupToggle(body)).toBe(false)
  })

  it('only considers checkboxes with the data-template-group attribute', () => {
    // A checked checkbox WITHOUT data-template-group should not count
    document.body.innerHTML = `
      <div id="body">
        <input type="checkbox" checked>
        <input type="checkbox" data-template-group>
      </div>
    `
    const body = document.getElementById('body')
    expect(window.EventHandler.hasCheckedTemplateGroupToggle(body)).toBe(false)
  })
})

describe('EventHandler.hasLibraryFileEntries', () => {
  it('returns false when accordionBody is null/undefined', () => {
    expect(window.EventHandler.hasLibraryFileEntries(null)).toBe(false)
    expect(window.EventHandler.hasLibraryFileEntries(undefined)).toBe(false)
  })

  it('returns false when no matching hidden input is present', () => {
    document.body.innerHTML = `<div id="body"><input type="text"></div>`
    const body = document.getElementById('body')
    expect(window.EventHandler.hasLibraryFileEntries(body)).toBe(false)
  })

  it('returns true for a non-empty *-metadata_files hidden input', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="hidden" name="mov-library_1-metadata_files" value='["file1.yml"]'>
      </div>
    `
    const body = document.getElementById('body')
    expect(window.EventHandler.hasLibraryFileEntries(body)).toBe(true)
  })

  it('returns true for a non-empty *-collection_files hidden input', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="hidden" name="mov-library_1-collection_files" value='["coll.yml"]'>
      </div>
    `
    const body = document.getElementById('body')
    expect(window.EventHandler.hasLibraryFileEntries(body)).toBe(true)
  })

  it('returns true for a non-empty *-overlay_files hidden input', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="hidden" name="sho-library_1-overlay_files" value='["ov.yml"]'>
      </div>
    `
    const body = document.getElementById('body')
    expect(window.EventHandler.hasLibraryFileEntries(body)).toBe(true)
  })

  it('returns false for an empty string value', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="hidden" name="mov-library_1-metadata_files" value="">
      </div>
    `
    const body = document.getElementById('body')
    expect(window.EventHandler.hasLibraryFileEntries(body)).toBe(false)
  })

  it('returns false for the literal empty-array sentinel "[]"', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="hidden" name="mov-library_1-metadata_files" value="[]">
      </div>
    `
    const body = document.getElementById('body')
    expect(window.EventHandler.hasLibraryFileEntries(body)).toBe(false)
  })

  it('returns false for a whitespace-only value', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="hidden" name="mov-library_1-metadata_files" value="   ">
      </div>
    `
    const body = document.getElementById('body')
    expect(window.EventHandler.hasLibraryFileEntries(body)).toBe(false)
  })
})

describe('EventHandler.highlightParentAccordions', () => {
  it('adds .selected to the closest ancestor .accordion-header', () => {
    // Note the .accordion-item deepest wrapper needs its OWN header too,
    // because the code does parentAccordion.querySelector('.accordion-header')
    // and dereferences the result without a null check.
    document.body.innerHTML = `
      <div class="accordion-item" id="outer">
        <div class="accordion-header">Outer Header</div>
        <div class="accordion-item" id="inner">
          <div class="accordion-header" id="inner-header">Inner Header</div>
          <div class="accordion-item" id="deepest">
            <div class="accordion-header" id="deepest-header">Deepest</div>
            <input id="trigger">
          </div>
        </div>
      </div>
    `
    const trigger = document.getElementById('trigger')
    window.EventHandler.highlightParentAccordions(trigger)
    // The walker adds .selected up through the ancestor chain.
    expect(document.getElementById('deepest-header').classList.contains('selected')).toBe(true)
    expect(document.getElementById('inner-header').classList.contains('selected')).toBe(true)
    expect(document.querySelector('#outer > .accordion-header').classList.contains('selected')).toBe(true)
  })

  it('stops immediately at data-qs-minimal-yaml="false" parent', () => {
    document.body.innerHTML = `
      <div class="accordion-item" id="outer">
        <div class="accordion-header" id="outer-header">Outer</div>
        <div class="accordion-item" id="inner" data-qs-minimal-yaml="false">
          <div class="accordion-header" id="inner-header">Inner</div>
          <div class="accordion-item" id="deepest">
            <div class="accordion-header" id="deepest-header">Deepest</div>
            <input id="trigger">
          </div>
        </div>
      </div>
    `
    const trigger = document.getElementById('trigger')
    window.EventHandler.highlightParentAccordions(trigger)
    // Inner should be selected (it's the minimal-yaml=false stopper)
    expect(document.getElementById('inner-header').classList.contains('selected')).toBe(true)
    // Outer should NOT be reached because we stop at the qs-minimal-yaml=false parent
    expect(document.getElementById('outer-header').classList.contains('selected')).toBe(false)
  })

  it('skips Preview Overlays parent (does not add .selected)', () => {
    document.body.innerHTML = `
      <div class="accordion-item" id="preview">
        <div class="accordion-header" id="preview-header">Preview Overlays</div>
        <div class="accordion-item" id="child">
          <div class="accordion-header" id="child-header">Child</div>
          <input id="trigger">
        </div>
      </div>
    `
    const trigger = document.getElementById('trigger')
    window.EventHandler.highlightParentAccordions(trigger)
    expect(document.getElementById('preview-header').classList.contains('selected')).toBe(false)
  })

  it('does nothing when there is no .accordion-item ancestor', () => {
    document.body.innerHTML = `<div><input id="trigger"></div>`
    const trigger = document.getElementById('trigger')
    // Should not throw
    expect(() => window.EventHandler.highlightParentAccordions(trigger)).not.toThrow()
  })

  it('does not inherit highlight from a bare "Overlays" parent unless a valid child is checked', () => {
    document.body.innerHTML = `
      <div class="accordion-item" id="overlays">
        <div class="accordion-header" id="overlays-header">Overlays</div>
        <div class="accordion-item" id="preview-child">
          <div class="accordion-header" id="preview-child-header">Preview Overlays</div>
        </div>
        <div class="accordion-item" id="triggerHost">
          <div class="accordion-header" id="triggerhost-header">Trigger Host</div>
          <input id="trigger" type="text">
        </div>
      </div>
    `
    // No .accordion-item child has a checked non-template-child-toggle input
    const trigger = document.getElementById('trigger')
    window.EventHandler.highlightParentAccordions(trigger)
    // The outer Overlays header should NOT get .selected because only
    // the Preview Overlays child exists (no valid non-preview checked child)
    expect(document.getElementById('overlays-header').classList.contains('selected')).toBe(false)
  })

  it('does inherit highlight from an "Overlays" parent when a valid non-preview child has a checked input', () => {
    document.body.innerHTML = `
      <div class="accordion-item" id="overlays">
        <div class="accordion-header" id="overlays-header">My Overlays</div>
        <div class="accordion-item" id="validChild">
          <div class="accordion-header" id="valid-child-header">Valid Child</div>
          <input type="checkbox" checked>
        </div>
        <div class="accordion-item" id="triggerHost">
          <div class="accordion-header" id="triggerhost-header">Trigger Host</div>
          <input id="trigger" type="text">
        </div>
      </div>
    `
    const trigger = document.getElementById('trigger')
    window.EventHandler.highlightParentAccordions(trigger)
    expect(document.getElementById('overlays-header').classList.contains('selected')).toBe(true)
  })
})

describe('EventHandler.removeHighlightIfEmpty', () => {
  it('no-ops on null/undefined element', () => {
    expect(() => window.EventHandler.removeHighlightIfEmpty(null)).not.toThrow()
    expect(() => window.EventHandler.removeHighlightIfEmpty(undefined)).not.toThrow()
  })

  it('no-ops when the element has no .accordion-item ancestor', () => {
    document.body.innerHTML = `<div class="accordion-header selected" id="orphan">Orphan</div>`
    const header = document.getElementById('orphan')
    window.EventHandler.removeHighlightIfEmpty(header)
    // Because there is no .accordion-item ancestor, the class stays
    expect(header.classList.contains('selected')).toBe(true)
  })

  it('removes .selected when the accordion body has no active selections', () => {
    document.body.innerHTML = `
      <div class="accordion-item" id="item">
        <div class="accordion-header selected" id="head">Head</div>
        <div class="accordion-body">
          <input type="text" value="">
        </div>
      </div>
    `
    const header = document.getElementById('head')
    window.EventHandler.removeHighlightIfEmpty(header)
    expect(header.classList.contains('selected')).toBe(false)
  })

  it('keeps .selected when at least one checkbox is checked in the body', () => {
    document.body.innerHTML = `
      <div class="accordion-item" id="item">
        <div class="accordion-header selected" id="head">Head</div>
        <div class="accordion-body">
          <input type="checkbox" checked>
        </div>
      </div>
    `
    const header = document.getElementById('head')
    window.EventHandler.removeHighlightIfEmpty(header)
    expect(header.classList.contains('selected')).toBe(true)
  })

  it('keeps .selected when a *-metadata_files hidden input is populated', () => {
    document.body.innerHTML = `
      <div class="accordion-item" id="item">
        <div class="accordion-header selected" id="head">Head</div>
        <div class="accordion-body">
          <input type="hidden" name="mov-library_1-metadata_files" value='["f.yml"]'>
        </div>
      </div>
    `
    const header = document.getElementById('head')
    window.EventHandler.removeHighlightIfEmpty(header)
    expect(header.classList.contains('selected')).toBe(true)
  })

  it('removes .selected even for checked checkboxes when NO template-group toggle is on (and toggles exist)', () => {
    // The "template group off" override: if the section has collection
    // toggles and none are enabled, force removal even if child inputs
    // are checked.
    document.body.innerHTML = `
      <div class="accordion-item" id="item">
        <div class="accordion-header selected" id="head">Head</div>
        <div class="accordion-body">
          <input type="checkbox" data-template-group>
          <input type="checkbox" checked>
        </div>
      </div>
    `
    const header = document.getElementById('head')
    window.EventHandler.removeHighlightIfEmpty(header)
    expect(header.classList.contains('selected')).toBe(false)
  })

  it('skips Preview Overlays sections (never removes .selected)', () => {
    document.body.innerHTML = `
      <div class="accordion-item" id="mov-library_1-previewOverlays">
        <div class="accordion-header selected" id="head">Preview Overlays</div>
        <div class="accordion-body"></div>
      </div>
    `
    const header = document.getElementById('head')
    window.EventHandler.removeHighlightIfEmpty(header)
    expect(header.classList.contains('selected')).toBe(true)
  })

  it('recurses to parent accordion header', () => {
    document.body.innerHTML = `
      <div class="accordion-item" id="outer">
        <div class="accordion-header selected" id="outerHead">Outer</div>
        <div class="accordion-body">
          <div class="accordion-item" id="inner">
            <div class="accordion-header selected" id="innerHead">Inner</div>
            <div class="accordion-body">
              <input type="text" value="">
            </div>
          </div>
        </div>
      </div>
    `
    const innerHead = document.getElementById('innerHead')
    window.EventHandler.removeHighlightIfEmpty(innerHead)
    // Inner is cleared
    expect(innerHead.classList.contains('selected')).toBe(false)
    // Outer is also cleared via recursion (its body only contains the
    // now-cleared inner, no direct active inputs)
    expect(document.getElementById('outerHead').classList.contains('selected')).toBe(false)
  })
})

describe('EventHandler.updateAccordionHighlights (integration surface)', () => {
  it('runs to completion on an empty DOM without throwing', () => {
    document.body.innerHTML = ''
    expect(() => window.EventHandler.updateAccordionHighlights()).not.toThrow()
  })

  it('always removes .selected from Preview Overlays headers', () => {
    document.body.innerHTML = `
      <div class="accordion-item">
        <div class="accordion-header selected">Preview Overlays</div>
        <div class="accordion-body">
          <input type="checkbox" checked>
        </div>
      </div>
    `
    window.EventHandler.updateAccordionHighlights()
    const head = document.querySelector('.accordion-header')
    expect(head.classList.contains('selected')).toBe(false)
  })

  it('adds .selected when a checkbox is checked in the accordion body', () => {
    document.body.innerHTML = `
      <div class="accordion-item">
        <div class="accordion-header">Genres</div>
        <div class="accordion-body">
          <input type="checkbox" checked>
        </div>
      </div>
    `
    window.EventHandler.updateAccordionHighlights()
    expect(document.querySelector('.accordion-header').classList.contains('selected')).toBe(true)
  })

  it('does not add .selected for a text input containing "none"', () => {
    document.body.innerHTML = `
      <div class="accordion-item">
        <div class="accordion-header">Config</div>
        <div class="accordion-body">
          <input type="text" value="none">
        </div>
      </div>
    `
    window.EventHandler.updateAccordionHighlights()
    expect(document.querySelector('.accordion-header').classList.contains('selected')).toBe(false)
  })

  it('adds .selected for a text input with a non-empty non-"none" value', () => {
    document.body.innerHTML = `
      <div class="accordion-item">
        <div class="accordion-header">Config</div>
        <div class="accordion-body">
          <input type="text" value="something">
        </div>
      </div>
    `
    window.EventHandler.updateAccordionHighlights()
    expect(document.querySelector('.accordion-header').classList.contains('selected')).toBe(true)
  })

  it('suppresses value-based highlight for Collections sections', () => {
    // Collections/Overlays headers should NOT trigger .selected purely
    // from populated text inputs (they need a checked checkbox / real
    // selection). This preserves the "unchecked collection" UX.
    document.body.innerHTML = `
      <div class="accordion-item">
        <div class="accordion-header">Movie Collections</div>
        <div class="accordion-body">
          <input type="text" value="something">
        </div>
      </div>
    `
    window.EventHandler.updateAccordionHighlights()
    expect(document.querySelector('.accordion-header').classList.contains('selected')).toBe(false)
  })

  it('allows value-based highlight for Delete Collections (special carve-out)', () => {
    document.body.innerHTML = `
      <div class="accordion-item">
        <div class="accordion-header">Delete Collections</div>
        <div class="accordion-body">
          <input type="number" value="7">
        </div>
      </div>
    `
    window.EventHandler.updateAccordionHighlights()
    expect(document.querySelector('.accordion-header').classList.contains('selected')).toBe(true)
  })
})
