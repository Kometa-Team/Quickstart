// Tests for static/local-js/modules/kometa/_ui.js
//
// The module exports three functions:
//
//   initBootstrapTooltips   -- creates/replaces Bootstrap tooltip
//                              instances within a scope. Depends on
//                              window.bootstrap.Tooltip.
//   disposeBootstrapTooltips -- disposes existing tooltip instances.
//   showCopyButtonSuccess    -- two-phase icon/text animation.
//
// The tooltip helpers are tested by stubbing a fake window.bootstrap
// object (Vitest's jsdom doesn't ship Bootstrap). The stub tracks
// getInstance / getOrCreateInstance / dispose calls so we can prove
// the right lifecycle happened.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  initBootstrapTooltips,
  disposeBootstrapTooltips,
  showCopyButtonSuccess
} from '../../../static/local-js/modules/kometa/_ui.js'

// ---------------------------------------------------------------------
// Bootstrap.Tooltip stub
// ---------------------------------------------------------------------
//
// A minimal fake tracking:
//   - which elements have "instances"
//   - dispose / create call counts per element
// so tests can assert on the sequence.

class FakeTooltip {
  constructor (el, opts) {
    this.el = el
    this.opts = opts
    this.disposed = false
    FakeTooltip._instances.set(el, this)
    FakeTooltip.createCalls.push({ el, opts })
  }

  dispose () {
    this.disposed = true
    FakeTooltip._instances.delete(this.el)
    FakeTooltip.disposeCalls.push(this.el)
  }

  static getInstance (el) {
    return FakeTooltip._instances.get(el) || null
  }

  static getOrCreateInstance (el, opts) {
    const existing = FakeTooltip._instances.get(el)
    if (existing) return existing
    return new FakeTooltip(el, opts)
  }

  static reset () {
    FakeTooltip._instances = new Map()
    FakeTooltip.createCalls = []
    FakeTooltip.disposeCalls = []
  }
}
FakeTooltip.reset()

function installFakeBootstrap () {
  FakeTooltip.reset()
  globalThis.bootstrap = { Tooltip: FakeTooltip }
}

function removeBootstrap () {
  delete globalThis.bootstrap
}

// ---------------------------------------------------------------------
// initBootstrapTooltips
// ---------------------------------------------------------------------

describe('initBootstrapTooltips', () => {
  beforeEach(() => {
    installFakeBootstrap()
    document.body.innerHTML = `
      <div id="scope">
        <button data-bs-toggle="tooltip" id="a" title="A"></button>
        <button data-bs-toggle="tooltip" id="b" title="B"></button>
        <button id="not-a-tooltip"></button>
      </div>
    `
  })

  afterEach(() => {
    document.body.innerHTML = ''
    removeBootstrap()
  })

  it('is a no-op when Bootstrap is not loaded', () => {
    removeBootstrap()
    // Should NOT throw
    expect(() => initBootstrapTooltips()).not.toThrow()
    expect(FakeTooltip.createCalls).toHaveLength(0)
  })

  it('creates tooltip instances on all matching elements in scope', () => {
    initBootstrapTooltips(document)
    expect(FakeTooltip.createCalls).toHaveLength(2)
    const ids = FakeTooltip.createCalls.map(c => c.el.id).sort()
    expect(ids).toEqual(['a', 'b'])
  })

  it('applies the html:true / sanitize:false defaults', () => {
    initBootstrapTooltips(document)
    for (const call of FakeTooltip.createCalls) {
      expect(call.opts.html).toBe(true)
      expect(call.opts.sanitize).toBe(false)
    }
  })

  it('allows callers to override defaults via options arg', () => {
    initBootstrapTooltips(document, null, { html: false, sanitize: true, placement: 'top' })
    for (const call of FakeTooltip.createCalls) {
      expect(call.opts.html).toBe(false)
      expect(call.opts.sanitize).toBe(true)
      expect(call.opts.placement).toBe('top')
    }
  })

  it('honors a custom selector', () => {
    document.body.innerHTML = `
      <button class="tt" id="a"></button>
      <button class="tt" id="b"></button>
      <button data-bs-toggle="tooltip" id="c"></button>
    `
    initBootstrapTooltips(document, '.tt')
    expect(FakeTooltip.createCalls).toHaveLength(2)
    expect(FakeTooltip.createCalls.map(c => c.el.id).sort()).toEqual(['a', 'b'])
  })

  it('disposes existing instance before creating a new one (re-init)', () => {
    // First call creates
    initBootstrapTooltips(document)
    expect(FakeTooltip.createCalls).toHaveLength(2)
    expect(FakeTooltip.disposeCalls).toHaveLength(0)

    // Second call must dispose then recreate
    initBootstrapTooltips(document)
    expect(FakeTooltip.disposeCalls).toHaveLength(2)
    expect(FakeTooltip.createCalls).toHaveLength(4)
  })

  it('when scope IS a matching element, tooltip applies to scope itself', () => {
    const btn = document.getElementById('a')
    initBootstrapTooltips(btn)
    expect(FakeTooltip.createCalls).toHaveLength(1)
    expect(FakeTooltip.createCalls[0].el).toBe(btn)
  })

  it('deduplicates: scope-matches-selector AND scope-contains-descendant', () => {
    // Structure a matcher that would double-count without the seen-set
    document.body.innerHTML = `
      <div class="wrap" id="parent">
        <div class="wrap" id="child"></div>
      </div>
    `
    const parent = document.getElementById('parent')
    initBootstrapTooltips(parent, '.wrap')
    // parent matches, AND parent.querySelectorAll('.wrap') finds child.
    // Both should be captured exactly once each.
    expect(FakeTooltip.createCalls).toHaveLength(2)
    const ids = FakeTooltip.createCalls.map(c => c.el.id).sort()
    expect(ids).toEqual(['child', 'parent'])
  })

  it('is a no-op when scope has no matching elements', () => {
    document.body.innerHTML = '<div></div>'
    initBootstrapTooltips(document)
    expect(FakeTooltip.createCalls).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------
// disposeBootstrapTooltips
// ---------------------------------------------------------------------

describe('disposeBootstrapTooltips', () => {
  beforeEach(() => {
    installFakeBootstrap()
    document.body.innerHTML = `
      <button data-bs-toggle="tooltip" id="a"></button>
      <button data-bs-toggle="tooltip" id="b"></button>
    `
  })

  afterEach(() => {
    document.body.innerHTML = ''
    removeBootstrap()
  })

  it('is a no-op when Bootstrap is not loaded', () => {
    removeBootstrap()
    expect(() => disposeBootstrapTooltips()).not.toThrow()
  })

  it('disposes all instances within scope', () => {
    initBootstrapTooltips(document)
    expect(FakeTooltip.createCalls).toHaveLength(2)

    disposeBootstrapTooltips(document)
    expect(FakeTooltip.disposeCalls).toHaveLength(2)
    // And the instances are gone
    expect(FakeTooltip.getInstance(document.getElementById('a'))).toBeNull()
    expect(FakeTooltip.getInstance(document.getElementById('b'))).toBeNull()
  })

  it('is a no-op on elements with no existing instance', () => {
    // No init call -- so no instances exist yet
    disposeBootstrapTooltips(document)
    expect(FakeTooltip.disposeCalls).toHaveLength(0)
  })

  it('scoped: only disposes tooltips inside the given scope', () => {
    initBootstrapTooltips(document)
    const scope = document.getElementById('a')
    disposeBootstrapTooltips(scope)
    // Only a was disposed; b still exists
    expect(FakeTooltip.disposeCalls).toHaveLength(1)
    expect(FakeTooltip.disposeCalls[0].id).toBe('a')
    expect(FakeTooltip.getInstance(document.getElementById('b'))).not.toBeNull()
  })
})

// ---------------------------------------------------------------------
// showCopyButtonSuccess
// ---------------------------------------------------------------------

describe('showCopyButtonSuccess', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    document.body.innerHTML = `
      <button>
        <i id="icon" class="bi bi-files"></i>
        <span id="text">Copy</span>
      </button>
    `
  })

  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('phase 1: swaps icon to check2 and text to "Copied"', () => {
    showCopyButtonSuccess('#icon', '#text')
    const icon = document.getElementById('icon')
    const text = document.getElementById('text')
    expect(icon.classList.contains('bi-check2')).toBe(true)
    expect(icon.classList.contains('bi-files')).toBe(false)
    expect(text.textContent).toBe('Copied')
  })

  it('phase 2: after 1.5s, icon reverts to bi-files and text to "Copy"', () => {
    showCopyButtonSuccess('#icon', '#text')

    vi.advanceTimersByTime(1499)
    // Still in phase 1
    expect(document.getElementById('text').textContent).toBe('Copied')

    vi.advanceTimersByTime(1)
    // Now phase 2
    expect(document.getElementById('icon').classList.contains('bi-check2')).toBe(false)
    expect(document.getElementById('icon').classList.contains('bi-files')).toBe(true)
    expect(document.getElementById('text').textContent).toBe('Copy')
  })

  it('also strips bi-clipboard (some buttons use that icon)', () => {
    document.getElementById('icon').className = 'bi bi-clipboard'
    showCopyButtonSuccess('#icon', '#text')
    expect(document.getElementById('icon').classList.contains('bi-clipboard')).toBe(false)
    expect(document.getElementById('icon').classList.contains('bi-check2')).toBe(true)
  })

  it('is a no-op when the icon selector matches nothing', () => {
    expect(() => showCopyButtonSuccess('#nope', '#text')).not.toThrow()
    // Text was NOT changed
    expect(document.getElementById('text').textContent).toBe('Copy')
  })

  it('is a no-op when the text selector matches nothing', () => {
    expect(() => showCopyButtonSuccess('#icon', '#nope')).not.toThrow()
    // Icon was NOT changed
    expect(document.getElementById('icon').classList.contains('bi-check2')).toBe(false)
  })
})
