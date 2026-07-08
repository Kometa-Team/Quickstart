// Small, generic UI helpers used across the Kometa page.
//
// This module holds functions that are:
//   * Pure -- no shared mutable state, no cross-module coupling
//   * Generic -- not specific to Kometa's data model, just DOM/UX
//   * Small -- individually trivial, but centralized here so callers
//     don't reinvent the wheel
//
// EXPORTS:
//
//   initBootstrapTooltips(scope, selector, options)
//   disposeBootstrapTooltips(scope, selector)
//     Bootstrap 5 tooltip lifecycle helpers. Both accept a scope
//     (default: document) and a selector (default: [data-bs-toggle=
//     "tooltip"]) and DTRT for a mix of scope-matches-selector and
//     scope-contains-selector cases.
//
//   showCopyButtonSuccess(iconSelector, textSelector)
//     Two-phase visual feedback for "copied to clipboard" buttons:
//     swap the copy icon for a checkmark, change the label, then
//     revert after 1.5s.
//
// The two tooltip helpers share the same DOM-traversal boilerplate
// (find scope-matches or scope-contained-nodes, dedupe, iterate).
// That shared logic lives in the private forEachTooltipTarget helper.

// ---------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------

/**
 * Walk a scope + selector, calling `fn(el)` on each unique matching
 * element. Handles the common "scope matches selector AND scope
 * contains descendants matching selector" case cleanly.
 *
 * @param {Element | Document | null | undefined} scope
 * @param {string} selector
 * @param {(el: Element) => void} fn
 */
function forEachTooltipTarget (scope, selector, fn) {
  const root = scope || document
  const query = selector || '[data-bs-toggle="tooltip"]'
  const seen = new Set()

  if (root && typeof root.matches === 'function' && root.matches(query)) {
    seen.add(root)
    fn(root)
  }
  if (root && typeof root.querySelectorAll === 'function') {
    root.querySelectorAll(query).forEach(el => {
      if (!el || seen.has(el)) return
      seen.add(el)
      fn(el)
    })
  }
}

/**
 * Returns the global Bootstrap.Tooltip class if it's present, or null
 * if Bootstrap isn't loaded. Both public functions short-circuit on
 * null, so pages that don't include Bootstrap don't blow up.
 *
 * Kept as a helper (rather than inlined) so the "is Bootstrap here?"
 * check is stated in exactly one place.
 *
 * @returns {typeof bootstrap.Tooltip | null}
 */
function getBootstrapTooltipClass () {
  if (typeof bootstrap === 'undefined' || !bootstrap.Tooltip) return null
  return bootstrap.Tooltip
}

// ---------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------

/**
 * Initialize (or re-initialize) Bootstrap tooltips within a scope.
 *
 * If a tooltip instance already exists on an element, it's disposed
 * first so option changes take effect. Every target ends up with a
 * fresh Tooltip instance carrying the merged default + user options.
 *
 * Defaults:
 *   html: true          allow HTML in the tooltip body
 *   sanitize: false     don't strip HTML (we control the content)
 *
 * Callers can override either default via the options argument.
 * Common overrides: `{ html: false, sanitize: true }` for user-
 * generated content that needs escaping.
 *
 * No-op if Bootstrap isn't loaded on the page.
 *
 * @param {Element | Document} [scope=document]
 * @param {string} [selector='[data-bs-toggle="tooltip"]']
 * @param {object} [options]  Merged over the defaults above
 */
export function initBootstrapTooltips (scope, selector, options) {
  const Tooltip = getBootstrapTooltipClass()
  if (!Tooltip) return

  const merged = Object.assign({ html: true, sanitize: false }, options || {})
  forEachTooltipTarget(scope, selector, el => {
    const existing = Tooltip.getInstance(el)
    if (existing) existing.dispose()
    Tooltip.getOrCreateInstance(el, merged)
  })
}

/**
 * Dispose Bootstrap tooltips within a scope. Useful before removing
 * elements from the DOM to avoid leaked tooltip instances still
 * holding references to detached nodes.
 *
 * No-op if Bootstrap isn't loaded, and per-element no-op if the
 * element has no tooltip instance.
 *
 * @param {Element | Document} [scope=document]
 * @param {string} [selector='[data-bs-toggle="tooltip"]']
 */
export function disposeBootstrapTooltips (scope, selector) {
  const Tooltip = getBootstrapTooltipClass()
  if (!Tooltip) return

  forEachTooltipTarget(scope, selector, el => {
    const existing = Tooltip.getInstance(el)
    if (existing) existing.dispose()
  })
}

/**
 * Two-phase "Copied!" feedback on a copy-to-clipboard button:
 *
 *   Phase 1 (immediate): icon swaps to a checkmark, label becomes
 *                        'Copied'.
 *   Phase 2 (1.5s later): icon reverts to bi-files, label reverts
 *                         to 'Copy'.
 *
 * Selector-driven so the same helper works for multiple copy
 * buttons on the page (main run command, recovery command, etc.).
 *
 * No-op if either target selector matches nothing.
 *
 * @param {string} iconSelector  CSS selector for the icon <i>
 * @param {string} textSelector  CSS selector for the label element
 */
export function showCopyButtonSuccess (iconSelector, textSelector) {
  const icon = document.querySelector(iconSelector)
  const text = document.querySelector(textSelector)
  if (!icon || !text) return

  // Some buttons use bi-files (multiple docs), others use bi-clipboard.
  // Strip both to be safe; the revert step below only re-adds bi-files
  // as that's the modal default. If a caller needs bi-clipboard
  // preserved, they should manage that themselves after the timeout.
  icon.classList.remove('bi-files', 'bi-clipboard')
  icon.classList.add('bi-check2')
  text.textContent = 'Copied'
  setTimeout(() => {
    icon.classList.remove('bi-check2')
    icon.classList.add('bi-files')
    text.textContent = 'Copy'
  }, 1500)
}
