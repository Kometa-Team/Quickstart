// Tests for static/local-js/modules/accordionHighlights.js
//
// This is the exhaustive test suite for the accordion-highlight
// module. It was originally split across:
//   - tests/js/eventHandler.test.js (40 tests via window.EventHandler)
//   - tests/js/modules/accordionHighlights.test.js (14 smoke tests)
//
// After #1346 step 2f completed and the compat shims were removed,
// both sets moved here as direct imports of the module functions.
// The eventHandler.js side still exercises attachLibraryListeners
// and the other genuinely eventHandler-owned surface -- but the
// accordion helpers now live only in the module.
//
// Test scope: the 5 exported functions, one describe block each.

import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import {
  hasCheckedTemplateGroupToggle,
  hasLibraryFileEntries,
  highlightParentAccordions,
  removeHighlightIfEmpty,
  updateAccordionHighlights
} from '../../../static/local-js/modules/accordionHighlights.js'
import * as accordionHighlights from '../../../static/local-js/modules/accordionHighlights.js'

beforeAll(() => {
  // Silence chatty debug output from updateAccordionHighlights,
  // highlightParentAccordions, and removeHighlightIfEmpty. All three
  // console.log every branch as they walk the DOM.
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'debug').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('accordionHighlights: module surface', () => {
  it('exports exactly the 5 expected functions (guards accidental leaks)', () => {
    // Named exports show up as own properties of the namespace object.
    // ES module namespaces are frozen; asserting on the sorted key
    // list catches both leaks (new export appearing) and regressions
    // (an export disappearing).
    const keys = Object.keys(accordionHighlights).sort()
    expect(keys).toEqual([
      'hasCheckedTemplateGroupToggle',
      'hasLibraryFileEntries',
      'highlightParentAccordions',
      'removeHighlightIfEmpty',
      'updateAccordionHighlights'
    ])
  })

  it('each export is a function', () => {
    expect(typeof hasCheckedTemplateGroupToggle).toBe('function')
    expect(typeof hasLibraryFileEntries).toBe('function')
    expect(typeof highlightParentAccordions).toBe('function')
    expect(typeof removeHighlightIfEmpty).toBe('function')
    expect(typeof updateAccordionHighlights).toBe('function')
  })
})

describe('hasCheckedTemplateGroupToggle', () => {
  it('returns null when accordionBody is null/undefined', () => {
    expect(hasCheckedTemplateGroupToggle(null)).toBeNull()
    expect(hasCheckedTemplateGroupToggle(undefined)).toBeNull()
  })

  it('returns null when the body has no template-group toggles', () => {
    document.body.innerHTML = `<div id="body"><input type="text"></div>`
    const body = document.getElementById('body')
    expect(hasCheckedTemplateGroupToggle(body)).toBeNull()
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
    expect(hasCheckedTemplateGroupToggle(body)).toBe(true)
  })

  it('returns false when template-group toggles exist but none are checked', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="checkbox" data-template-group>
        <input type="checkbox" data-template-group>
      </div>
    `
    const body = document.getElementById('body')
    expect(hasCheckedTemplateGroupToggle(body)).toBe(false)
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
    expect(hasCheckedTemplateGroupToggle(body)).toBe(false)
  })
})

describe('hasLibraryFileEntries', () => {
  it('returns false when accordionBody is null/undefined', () => {
    expect(hasLibraryFileEntries(null)).toBe(false)
    expect(hasLibraryFileEntries(undefined)).toBe(false)
  })

  it('returns false when no matching hidden input is present', () => {
    document.body.innerHTML = `<div id="body"><input type="text"></div>`
    const body = document.getElementById('body')
    expect(hasLibraryFileEntries(body)).toBe(false)
  })

  it('returns true for a non-empty *-metadata_files hidden input', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="hidden" name="mov-library_1-metadata_files" value='["file1.yml"]'>
      </div>
    `
    const body = document.getElementById('body')
    expect(hasLibraryFileEntries(body)).toBe(true)
  })

  it('returns true for a non-empty *-collection_files hidden input', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="hidden" name="mov-library_1-collection_files" value='["coll.yml"]'>
      </div>
    `
    const body = document.getElementById('body')
    expect(hasLibraryFileEntries(body)).toBe(true)
  })

  it('returns true for a non-empty *-overlay_files hidden input', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="hidden" name="sho-library_1-overlay_files" value='["ov.yml"]'>
      </div>
    `
    const body = document.getElementById('body')
    expect(hasLibraryFileEntries(body)).toBe(true)
  })

  it('returns false for an empty string value', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="hidden" name="mov-library_1-metadata_files" value="">
      </div>
    `
    const body = document.getElementById('body')
    expect(hasLibraryFileEntries(body)).toBe(false)
  })

  it('returns false for the literal empty-array sentinel "[]"', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="hidden" name="mov-library_1-metadata_files" value="[]">
      </div>
    `
    const body = document.getElementById('body')
    expect(hasLibraryFileEntries(body)).toBe(false)
  })

  it('returns false for a whitespace-only value', () => {
    document.body.innerHTML = `
      <div id="body">
        <input type="hidden" name="mov-library_1-metadata_files" value="   ">
      </div>
    `
    const body = document.getElementById('body')
    expect(hasLibraryFileEntries(body)).toBe(false)
  })
})

describe('highlightParentAccordions', () => {
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
    highlightParentAccordions(trigger)
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
    highlightParentAccordions(trigger)
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
    highlightParentAccordions(trigger)
    expect(document.getElementById('preview-header').classList.contains('selected')).toBe(false)
  })

  it('does nothing when there is no .accordion-item ancestor', () => {
    document.body.innerHTML = `<div><input id="trigger"></div>`
    const trigger = document.getElementById('trigger')
    // Should not throw
    expect(() => highlightParentAccordions(trigger)).not.toThrow()
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
    highlightParentAccordions(trigger)
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
    highlightParentAccordions(trigger)
    expect(document.getElementById('overlays-header').classList.contains('selected')).toBe(true)
  })
})

describe('removeHighlightIfEmpty', () => {
  it('no-ops on null/undefined element', () => {
    expect(() => removeHighlightIfEmpty(null)).not.toThrow()
    expect(() => removeHighlightIfEmpty(undefined)).not.toThrow()
  })

  it('no-ops when the element has no .accordion-item ancestor', () => {
    document.body.innerHTML = `<div class="accordion-header selected" id="orphan">Orphan</div>`
    const header = document.getElementById('orphan')
    removeHighlightIfEmpty(header)
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
    removeHighlightIfEmpty(header)
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
    removeHighlightIfEmpty(header)
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
    removeHighlightIfEmpty(header)
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
    removeHighlightIfEmpty(header)
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
    removeHighlightIfEmpty(header)
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
    removeHighlightIfEmpty(innerHead)
    // Inner is cleared
    expect(innerHead.classList.contains('selected')).toBe(false)
    // Outer is also cleared via recursion (its body only contains the
    // now-cleared inner, no direct active inputs)
    expect(document.getElementById('outerHead').classList.contains('selected')).toBe(false)
  })
})

describe('updateAccordionHighlights (integration surface)', () => {
  it('runs to completion on an empty DOM without throwing', () => {
    document.body.innerHTML = ''
    expect(() => updateAccordionHighlights()).not.toThrow()
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
    updateAccordionHighlights()
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
    updateAccordionHighlights()
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
    updateAccordionHighlights()
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
    updateAccordionHighlights()
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
    updateAccordionHighlights()
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
    updateAccordionHighlights()
    expect(document.querySelector('.accordion-header').classList.contains('selected')).toBe(true)
  })
})
