// Header-style font grid + sample loading.
//
// The Kometa config page has a "Header style" section where the user
// picks the ASCII-art font used in generated section headers. The
// section header opens up a Bootstrap collapse containing a GRID of
// cards -- one per available font -- each showing a live preview
// rendered by the backend.
//
// This module owns:
//
//   updateHeaderStyleLabel   -- keep the small text label in sync
//                               with the currently-selected font
//   setActiveGridCard        -- toggle the .active class on the
//                               correct card
//   loadHeaderGridSamples    -- lazy-load preview text for every
//                               font, in chunks, updating a status
//                               line + progress bar as it goes
//
// The two private helpers `updateGridStatus` and `updateGridProgress`
// are also here but not exported -- they're only used by
// loadHeaderGridSamples.
//
// DESIGN NOTES:
//
//   1. DOM refs are resolved LAZILY inside each function (not cached
//      at module init) so that:
//        - Import order doesn't matter (the module can be imported
//          before DOMContentLoaded)
//        - Tests can install a fresh DOM in each beforeEach without
//          re-importing the module
//        - The extra getElementById cost is negligible (nanoseconds)
//
//   2. The chunked fetch call in loadHeaderGridSamples is designed
//      for pagination + progressive UI: 12 fonts per POST to
//      /header-style-previews. This is a deliberate tradeoff --
//      one giant fetch would be simpler but leave the user staring
//      at "Loading..." placeholders longer.
//
//   3. loadHeaderGridSamples takes an optional `fetchImpl` param
//      that defaults to global `fetch`. Solely for testability --
//      lets vitest inject a mock without stubbing globals.
//
// BUG FIX INCLUDED (see PR):
//
//   The pre-extraction code had:
//     card.insertAdjacentHTML('beforeend', title, preview)
//
//   That's a mistake -- insertAdjacentHTML takes a STRING, not DOM
//   elements. `title` (a <div>) got string-coerced to
//   '[object HTMLDivElement]', which appeared literally in every
//   card. And `preview` was silently ignored (extra args are dropped).
//
//   The fix is to use card.append(title, preview) which correctly
//   appends DOM nodes.

import { formatHeaderStyleLabel } from './_util.js'
import { updateSectionStyleHeaderBadge } from './_headerBadges.js'

// ---------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------

function getStatusEl () {
  return document.getElementById('header-style-grid-status')
}

function getProgressEl () {
  return document.getElementById('header-style-grid-progress')
}

function getProgressBarEl () {
  const wrapper = getProgressEl()
  return wrapper ? wrapper.querySelector('.progress-bar') : null
}

function updateGridStatus (message) {
  const el = getStatusEl()
  if (el) el.textContent = message || ''
}

function updateGridProgress (loaded, total) {
  const wrapper = getProgressEl()
  const bar = getProgressBarEl()
  if (!wrapper || !bar) return
  if (!total) {
    wrapper.classList.add('d-none')
    bar.style.width = '0%'
    return
  }
  const pct = Math.min(100, Math.round((loaded / total) * 100))
  wrapper.classList.remove('d-none')
  bar.style.width = `${pct}%`
}

// ---------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------

/**
 * Sync the small `<span id="header-style-label">` and the accordion
 * header badge with the currently-selected font.
 *
 * @param {string} value  Font name (e.g. 'ansi_shadow'). Empty/undefined
 *                        falls back to whatever formatHeaderStyleLabel
 *                        returns for empty input ('Single line' today).
 */
export function updateHeaderStyleLabel (value) {
  const el = document.getElementById('header-style-label')
  if (!el) return
  el.textContent = formatHeaderStyleLabel(value)
  updateSectionStyleHeaderBadge(value)
}

/**
 * Highlight exactly one card in the grid, matched by its data-font
 * attribute. Removes the active class from all other cards.
 *
 * No-op if the grid isn't in the DOM (Bootstrap collapse hasn't been
 * expanded yet, or we're on a page that doesn't render the grid).
 *
 * @param {string} fontName  The font to mark active. Compared as a
 *                           raw string against each card's data-font
 *                           attribute (no normalization) -- both
 *                           sides originate from the same backend
 *                           enumeration, so they already match
 *                           character-for-character.
 *
 *                           Note: pre-fix, this function passed the
 *                           input through normalizeFontName which
 *                           replaces underscores with spaces. That
 *                           meant a font like 'ansi_shadow' compared
 *                           to card.dataset.font='ansi_shadow' as
 *                           'ansi shadow' !== 'ansi_shadow' -- so
 *                           any underscored font never activated.
 *                           The bundled fonts happen to be underscore-
 *                           free (big, doom, standard, ...) so the
 *                           bug was invisible with default config.
 */
export function setActiveGridCard (fontName) {
  const grid = document.getElementById('header-style-grid')
  if (!grid) return
  const target = String(fontName || '').trim()
  grid.querySelectorAll('.header-style-card').forEach(card => {
    card.classList.toggle('active', card.dataset.font === target)
  })
}

/**
 * Lazy-load font previews for every font declared in
 * `#header-style-grid[data-fonts]`. Renders one clickable card per
 * font, then fills in previews from the backend in batches of 12.
 *
 * Called once when the accordion collapse first expands (see the
 * `show.bs.collapse` listener in 900-kometa.js). Should NOT be
 * called on every open -- the caller is expected to gate on a
 * `gridLoaded` flag.
 *
 * @param {typeof fetch} [fetchImpl]  Injectable fetch for testing.
 *                                    Defaults to global fetch.
 * @returns {Promise<void>}
 */
export async function loadHeaderGridSamples (fetchImpl = fetch) {
  const grid = document.getElementById('header-style-grid')
  if (!grid) return
  const fonts = JSON.parse(grid.dataset.fonts || '[]')
  if (!fonts.length) {
    grid.replaceChildren()
    const empty = document.createElement('div')
    empty.className = 'text-muted small'
    empty.textContent = 'No fonts available.'
    grid.appendChild(empty)
    updateGridStatus('')
    updateGridProgress(0, 0)
    return
  }

  updateGridStatus(`Loading ${fonts.length} font previews...`)
  updateGridProgress(0, fonts.length)

  const headerSelect = document.getElementById('header-style')

  grid.replaceChildren()
  fonts.forEach(font => {
    const card = document.createElement('button')
    card.type = 'button'
    card.className = 'header-style-card'
    card.dataset.font = font
    const title = document.createElement('div')
    title.className = 'header-style-card-title'
    title.textContent = font.replace(/_/g, ' ')
    const preview = document.createElement('pre')
    preview.className = 'header-style-card-preview'
    preview.textContent = 'Loading...'
    // FIX: was card.insertAdjacentHTML('beforeend', title, preview),
    // which coerces `title` to '[object HTMLDivElement]' (rendered
    // as literal text) and silently drops `preview`. See docstring.
    card.append(title, preview)
    card.addEventListener('click', () => {
      if (headerSelect) {
        headerSelect.value = font
        headerSelect.dispatchEvent(new Event('change'))
      }
      updateHeaderStyleLabel(font)
      setActiveGridCard(font)
    })
    grid.appendChild(card)
  })

  setActiveGridCard(headerSelect ? headerSelect.value : '')

  const chunkSize = 12
  let loadedCount = 0
  for (let i = 0; i < fonts.length; i += chunkSize) {
    const chunk = fonts.slice(i, i + chunkSize)
    try {
      const res = await fetchImpl('/header-style-previews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fonts: chunk })
      })
      const data = await res.json()
      if (!res.ok || !data.success) {
        throw new Error(data.message || 'Preview unavailable.')
      }
      const previews = data.previews || []
      previews.forEach(entry => {
        const card = grid.querySelector(`.header-style-card[data-font="${entry.font}"]`)
        const pre = card ? card.querySelector('.header-style-card-preview') : null
        if (pre) pre.textContent = entry.preview || ''
      })
    } catch {
      chunk.forEach(font => {
        const card = grid.querySelector(`.header-style-card[data-font="${font}"]`)
        const pre = card ? card.querySelector('.header-style-card-preview') : null
        if (pre) pre.textContent = 'Preview unavailable.'
      })
    }
    loadedCount += chunk.length
    updateGridStatus(`Loaded ${Math.min(loadedCount, fonts.length)} of ${fonts.length} previews`)
    updateGridProgress(Math.min(loadedCount, fonts.length), fonts.length)
  }
  updateGridStatus(`Loaded ${fonts.length} previews`)
  updateGridProgress(fonts.length, fonts.length)
  setTimeout(() => updateGridProgress(0, 0), 800)
}
