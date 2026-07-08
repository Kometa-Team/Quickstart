// Tests for static/local-js/modules/kometa/_headerGrid.js
//
// The module has three exported functions and two private helpers.
// Tests build a fresh fixture DOM in beforeEach and inspect the
// resulting DOM state after each call.
//
// Coverage strategy:
//
//   updateHeaderStyleLabel   -- happy path, missing label element,
//                               delegates to updateSectionStyleHeaderBadge
//                               (which we verify via the badge DOM)
//
//   setActiveGridCard        -- toggles .active on exactly one card,
//                               empty grid no-op, unknown font clears
//                               all actives, normalizes the input
//
//   loadHeaderGridSamples    -- empty fonts list (renders "No fonts"),
//                               happy path with a mocked fetch that
//                               returns previews in chunks, fetch
//                               failure fallback ("Preview unavailable"),
//                               the BUG-FIX assertion (card contains
//                               the title as a DOM node, not the
//                               literal "[object HTMLDivElement]"),
//                               clicking a card updates the select
//                               and the label

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  updateHeaderStyleLabel,
  setActiveGridCard,
  loadHeaderGridSamples
} from '../../../static/local-js/modules/kometa/_headerGrid.js'

// ---------------------------------------------------------------------
// Fixture DOM helpers
// ---------------------------------------------------------------------
//
// The full grid page shape:
//   #header-style-label       -- small text label above the accordion
//   #header-style-grid        -- container for the cards; carries
//                                data-fonts JSON array
//   #header-style-grid-status -- status text ("Loading N of M")
//   #header-style-grid-progress + child .progress-bar -- progress UI
//   #header-style               -- the underlying <select> element
//   #header-style-rollup-badge  -- the accordion header badge that
//                                  updateSectionStyleHeaderBadge writes
//                                  to (from _headerBadges.js)

function installGridDom ({ fonts = [], selected = '' } = {}) {
  document.body.innerHTML = `
    <span id="header-style-label"></span>
    <span id="header-style-rollup-badge" class="qs-validation-rollup-badge qs-validation-rollup-badge--unknown"></span>
    <select id="header-style">
      ${fonts.map(f => `<option value="${f}" ${f === selected ? 'selected' : ''}>${f}</option>`).join('')}
    </select>
    <div id="header-style-grid" data-fonts='${JSON.stringify(fonts)}'></div>
    <div id="header-style-grid-status"></div>
    <div id="header-style-grid-progress" class="d-none">
      <div class="progress-bar" style="width: 0%"></div>
    </div>
  `
}

// Build a card manually (mimics what loadHeaderGridSamples produces,
// without the async fetch). Useful for testing setActiveGridCard in
// isolation.
function installCard (fontName, activeInitially = false) {
  const grid = document.getElementById('header-style-grid')
  const card = document.createElement('button')
  card.type = 'button'
  card.className = 'header-style-card'
  if (activeInitially) card.classList.add('active')
  card.dataset.font = fontName
  grid.appendChild(card)
  return card
}

afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------
// updateHeaderStyleLabel
// ---------------------------------------------------------------------

describe('updateHeaderStyleLabel', () => {
  beforeEach(() => {
    installGridDom()
  })

  it('sets the label element text via formatHeaderStyleLabel', () => {
    updateHeaderStyleLabel('ansi_shadow')
    const label = document.getElementById('header-style-label')
    // formatHeaderStyleLabel replaces _ with space and title-cases
    expect(label.textContent).toBe('Ansi Shadow')
  })

  it('is a no-op when the label element is missing', () => {
    document.getElementById('header-style-label').remove()
    expect(() => updateHeaderStyleLabel('anything')).not.toThrow()
  })

  it('also updates the section-style rollup badge (via headerBadges)', () => {
    updateHeaderStyleLabel('big')
    const badge = document.getElementById('header-style-rollup-badge')
    expect(badge.textContent).toBe('Big')
    expect(badge.classList.contains('qs-validation-rollup-badge--ok')).toBe(true)
  })

  it('handles empty input (uses the util\'s fallback: "Single line")', () => {
    updateHeaderStyleLabel('')
    const label = document.getElementById('header-style-label')
    expect(label.textContent).toBe('Single line')
  })
})

// ---------------------------------------------------------------------
// setActiveGridCard
// ---------------------------------------------------------------------

describe('setActiveGridCard', () => {
  beforeEach(() => {
    installGridDom()
  })

  it('marks the matching card active and no others', () => {
    installCard('ansi_shadow')
    installCard('big')
    installCard('block')
    setActiveGridCard('big')
    const cards = document.querySelectorAll('.header-style-card')
    expect(cards[0].classList.contains('active')).toBe(false)
    expect(cards[1].classList.contains('active')).toBe(true)
    expect(cards[2].classList.contains('active')).toBe(false)
  })

  it('BUG FIX: matches underscored font names against raw data-font (no normalization)', () => {
    // Pre-fix, this function passed the input through normalizeFontName
    // which converts underscores to spaces. So 'ansi_shadow' compared
    // against card.dataset.font='ansi_shadow' as 'ansi shadow' !==
    // 'ansi_shadow' -- underscored font names never activated.
    installCard('ansi_shadow')
    installCard('big')
    setActiveGridCard('ansi_shadow')
    const cards = document.querySelectorAll('.header-style-card')
    expect(cards[0].classList.contains('active')).toBe(true)
    expect(cards[1].classList.contains('active')).toBe(false)
  })

  it('trims whitespace around the input', () => {
    installCard('big')
    setActiveGridCard('  big  ')
    expect(document.querySelector('.header-style-card').classList.contains('active')).toBe(true)
  })

  it('clears active from a previously-active card when switching', () => {
    installCard('a', true) // pre-active
    installCard('b')
    setActiveGridCard('b')
    const cards = document.querySelectorAll('.header-style-card')
    expect(cards[0].classList.contains('active')).toBe(false)
    expect(cards[1].classList.contains('active')).toBe(true)
  })

  it('clears active from all cards when the font matches none', () => {
    installCard('a', true)
    installCard('b', true)
    setActiveGridCard('nonexistent')
    const cards = document.querySelectorAll('.header-style-card')
    expect(cards[0].classList.contains('active')).toBe(false)
    expect(cards[1].classList.contains('active')).toBe(false)
  })

  it('is a no-op when the grid element is missing', () => {
    document.getElementById('header-style-grid').remove()
    expect(() => setActiveGridCard('anything')).not.toThrow()
  })

  it('handles an empty grid (no cards installed)', () => {
    // Grid exists but has no card children
    expect(() => setActiveGridCard('anything')).not.toThrow()
  })
})

// ---------------------------------------------------------------------
// loadHeaderGridSamples
// ---------------------------------------------------------------------

describe('loadHeaderGridSamples', () => {
  // Helper: build a fetch stub that returns the given preview map
  function makeFetchStub (previewsByFont) {
    return vi.fn(async (url, init) => {
      const body = JSON.parse(init.body)
      const previews = body.fonts.map(f => ({
        font: f,
        preview: previewsByFont[f] || `-- preview of ${f} --`
      }))
      return {
        ok: true,
        json: async () => ({ success: true, previews })
      }
    })
  }

  it('renders "No fonts available." when data-fonts is empty', async () => {
    installGridDom({ fonts: [] })
    const fetchStub = vi.fn()
    await loadHeaderGridSamples(fetchStub)
    const grid = document.getElementById('header-style-grid')
    expect(grid.querySelector('.text-muted').textContent).toBe('No fonts available.')
    // fetch should NOT have been called for an empty list
    expect(fetchStub).not.toHaveBeenCalled()
  })

  it('renders one card per font with a normalized title', async () => {
    installGridDom({ fonts: ['ansi_shadow', 'big'] })
    await loadHeaderGridSamples(makeFetchStub({}))
    const cards = document.querySelectorAll('.header-style-card')
    expect(cards).toHaveLength(2)
    const titles = Array.from(document.querySelectorAll('.header-style-card-title'))
    expect(titles[0].textContent).toBe('ansi shadow') // _ -> space
    expect(titles[1].textContent).toBe('big')
  })

  // === THE BUG FIX ASSERTION ===
  it('BUG FIX: card contains the title as a proper DOM node, not "[object HTMLDivElement]" text', async () => {
    // Pre-fix behavior:
    //   card.insertAdjacentHTML('beforeend', title, preview)
    // string-coerced `title` (a <div>) into the literal string
    // "[object HTMLDivElement]" and dropped `preview` entirely.
    //
    // Correct behavior:
    //   card.append(title, preview) appends the DOM nodes directly.
    installGridDom({ fonts: ['ansi_shadow'] })
    await loadHeaderGridSamples(makeFetchStub({ ansi_shadow: 'PREVIEW' }))
    const card = document.querySelector('.header-style-card')
    // 1. There's a real .header-style-card-title child element
    const title = card.querySelector('.header-style-card-title')
    expect(title).not.toBeNull()
    expect(title.tagName).toBe('DIV')
    expect(title.textContent).toBe('ansi shadow')
    // 2. There's a real .header-style-card-preview child element
    const pre = card.querySelector('.header-style-card-preview')
    expect(pre).not.toBeNull()
    expect(pre.tagName).toBe('PRE')
    // 3. The card's textContent does NOT contain the buggy literal
    expect(card.textContent).not.toContain('[object HTMLDivElement]')
    expect(card.textContent).not.toContain('[object HTMLPreElement]')
  })

  it('populates preview text after the fetch resolves', async () => {
    installGridDom({ fonts: ['ansi_shadow'] })
    await loadHeaderGridSamples(makeFetchStub({ ansi_shadow: 'BIG PREVIEW' }))
    const pre = document.querySelector('.header-style-card-preview')
    expect(pre.textContent).toBe('BIG PREVIEW')
  })

  it('chunks fetches in batches of 12', async () => {
    // 15 fonts should produce two POSTs (12 + 3)
    const fonts = Array.from({ length: 15 }, (_, i) => `font${i}`)
    installGridDom({ fonts })
    const fetchStub = makeFetchStub({})
    await loadHeaderGridSamples(fetchStub)
    expect(fetchStub).toHaveBeenCalledTimes(2)
    const firstCall = JSON.parse(fetchStub.mock.calls[0][1].body)
    const secondCall = JSON.parse(fetchStub.mock.calls[1][1].body)
    expect(firstCall.fonts).toHaveLength(12)
    expect(secondCall.fonts).toHaveLength(3)
  })

  it('falls back to "Preview unavailable." when the fetch throws', async () => {
    installGridDom({ fonts: ['a', 'b'] })
    const failingFetch = vi.fn(async () => { throw new Error('network down') })
    await loadHeaderGridSamples(failingFetch)
    const previews = Array.from(document.querySelectorAll('.header-style-card-preview'))
    expect(previews.every(p => p.textContent === 'Preview unavailable.')).toBe(true)
  })

  it('falls back on !res.ok', async () => {
    installGridDom({ fonts: ['a'] })
    const failingFetch = vi.fn(async () => ({
      ok: false,
      json: async () => ({ success: false, message: 'server broke' })
    }))
    await loadHeaderGridSamples(failingFetch)
    const pre = document.querySelector('.header-style-card-preview')
    expect(pre.textContent).toBe('Preview unavailable.')
  })

  it('falls back on !data.success even when res.ok', async () => {
    installGridDom({ fonts: ['a'] })
    const failingFetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ success: false })
    }))
    await loadHeaderGridSamples(failingFetch)
    const pre = document.querySelector('.header-style-card-preview')
    expect(pre.textContent).toBe('Preview unavailable.')
  })

  it('clicking a card updates the select value + fires change + updates label', async () => {
    installGridDom({ fonts: ['ansi_shadow', 'big'], selected: 'ansi_shadow' })
    await loadHeaderGridSamples(makeFetchStub({}))
    const select = document.getElementById('header-style')
    const changeSpy = vi.fn()
    select.addEventListener('change', changeSpy)

    const bigCard = document.querySelector('[data-font="big"]')
    bigCard.click()

    expect(select.value).toBe('big')
    expect(changeSpy).toHaveBeenCalledTimes(1)
    // Label reflects the new selection
    expect(document.getElementById('header-style-label').textContent).toBe('Big')
    // AND the clicked card is now the active one
    expect(bigCard.classList.contains('active')).toBe(true)
    expect(document.querySelector('[data-font="ansi_shadow"]').classList.contains('active')).toBe(false)
  })

  it('is a no-op when the grid element is missing entirely', async () => {
    // No installGridDom() call
    const fetchStub = vi.fn()
    await loadHeaderGridSamples(fetchStub)
    expect(fetchStub).not.toHaveBeenCalled()
  })

  it('sets the initial active card based on the select value', async () => {
    installGridDom({ fonts: ['a', 'b', 'c'], selected: 'b' })
    await loadHeaderGridSamples(makeFetchStub({}))
    const cards = document.querySelectorAll('.header-style-card')
    expect(cards[0].classList.contains('active')).toBe(false)
    expect(cards[1].classList.contains('active')).toBe(true)
    expect(cards[2].classList.contains('active')).toBe(false)
  })

  it('updates the status line to show progress', async () => {
    // Deliberately use 3 fonts so we can inspect intermediate + final
    installGridDom({ fonts: ['a', 'b', 'c'] })
    await loadHeaderGridSamples(makeFetchStub({}))
    const status = document.getElementById('header-style-grid-status')
    // Final message
    expect(status.textContent).toBe('Loaded 3 previews')
  })
})
