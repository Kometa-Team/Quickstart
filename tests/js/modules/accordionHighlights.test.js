// Contract tests for static/local-js/modules/accordionHighlights.js
//
// The exhaustive behavior tests live in tests/js/eventHandler.test.js --
// those exercise the same functions via `window.EventHandler`, since
// eventHandler.js re-exports them onto the EventHandler object.
//
// The tests here are narrower: they prove the MODULE (importable
// standalone, no window/EventHandler pollution required) exposes the
// expected names as callable functions, and that each one runs
// end-to-end on a minimal DOM fixture. This is the "does the module
// contract work" smoke test that unlocks other consumers importing
// from it directly.

import { afterEach, describe, expect, it, vi } from 'vitest'
import * as accordionHighlights from '../../../static/local-js/modules/accordionHighlights.js'

// Silence chatty debug output from updateAccordionHighlights /
// highlightParentAccordions / removeHighlightIfEmpty.
vi.spyOn(console, 'log').mockImplementation(() => {})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('accordionHighlights module surface', () => {
  it('exports hasCheckedTemplateGroupToggle as a function', () => {
    expect(typeof accordionHighlights.hasCheckedTemplateGroupToggle).toBe('function')
  })

  it('exports hasLibraryFileEntries as a function', () => {
    expect(typeof accordionHighlights.hasLibraryFileEntries).toBe('function')
  })

  it('exports highlightParentAccordions as a function', () => {
    expect(typeof accordionHighlights.highlightParentAccordions).toBe('function')
  })

  it('exports removeHighlightIfEmpty as a function', () => {
    expect(typeof accordionHighlights.removeHighlightIfEmpty).toBe('function')
  })

  it('exports updateAccordionHighlights as a function', () => {
    expect(typeof accordionHighlights.updateAccordionHighlights).toBe('function')
  })

  it('does not export anything else at the top level (guards accidental leaks)', () => {
    // Named exports show up as own properties of the namespace object.
    // ES module namespaces are frozen, so we're just asserting on shape.
    const keys = Object.keys(accordionHighlights).sort()
    expect(keys).toEqual([
      'hasCheckedTemplateGroupToggle',
      'hasLibraryFileEntries',
      'highlightParentAccordions',
      'removeHighlightIfEmpty',
      'updateAccordionHighlights'
    ])
  })
})

describe('accordionHighlights: standalone smoke tests', () => {
  // Each test builds the minimum DOM the function needs and asserts
  // one visible behavior. Exhaustive coverage is in eventHandler.test.js;
  // these prove the module works without needing eventHandler.js loaded.

  it('hasCheckedTemplateGroupToggle: returns null on empty body', () => {
    const body = document.createElement('div')
    expect(accordionHighlights.hasCheckedTemplateGroupToggle(body)).toBe(null)
  })

  it('hasCheckedTemplateGroupToggle: returns true when a template-group toggle is checked', () => {
    const body = document.createElement('div')
    body.innerHTML = '<input type="checkbox" data-template-group="foo" checked>'
    expect(accordionHighlights.hasCheckedTemplateGroupToggle(body)).toBe(true)
  })

  it('hasLibraryFileEntries: returns false on empty body', () => {
    const body = document.createElement('div')
    expect(accordionHighlights.hasLibraryFileEntries(body)).toBe(false)
  })

  it('hasLibraryFileEntries: returns true when a populated hidden input is present', () => {
    const body = document.createElement('div')
    body.innerHTML = '<input type="hidden" name="foo-metadata_files" value="[\\"a.yml\\"]">'
    expect(accordionHighlights.hasLibraryFileEntries(body)).toBe(true)
  })

  it('highlightParentAccordions: walks up and adds .selected', () => {
    document.body.innerHTML = `
      <div class="accordion-item" data-qs-minimal-yaml="true">
        <div class="accordion-header">Outer</div>
        <div class="accordion-body">
          <div class="accordion-item" data-qs-minimal-yaml="true">
            <div class="accordion-header" id="inner">Inner</div>
          </div>
        </div>
      </div>
    `
    const inner = document.getElementById('inner')
    accordionHighlights.highlightParentAccordions(inner)
    const outer = document.body.querySelector('.accordion-item > .accordion-header')
    expect(outer.classList.contains('selected')).toBe(true)
  })

  it('removeHighlightIfEmpty: strips .selected on an empty accordion body', () => {
    document.body.innerHTML = `
      <div class="accordion-item">
        <div class="accordion-header selected" id="hdr">Empty</div>
        <div class="accordion-body"></div>
      </div>
    `
    const hdr = document.getElementById('hdr')
    accordionHighlights.removeHighlightIfEmpty(hdr)
    expect(hdr.classList.contains('selected')).toBe(false)
  })

  it('updateAccordionHighlights: adds .selected when a body checkbox is checked', () => {
    document.body.innerHTML = `
      <div class="accordion-item">
        <div class="accordion-header">Foo</div>
        <div class="accordion-body">
          <input type="checkbox" checked>
        </div>
      </div>
    `
    accordionHighlights.updateAccordionHighlights()
    const hdr = document.querySelector('.accordion-header')
    expect(hdr.classList.contains('selected')).toBe(true)
  })

  it('updateAccordionHighlights: runs on empty DOM without throwing', () => {
    expect(() => accordionHighlights.updateAccordionHighlights()).not.toThrow()
  })
})
