// Accordion-highlight state for the config-form workspace.
//
// This module owns the `.selected` class on `.accordion-header` elements
// across the page. When a user checks a toggle, types a value, or clicks
// a template swatch, the surrounding accordion (and its ancestors) needs
// to reflect that "something in here is active".
//
// Extracted from eventHandler.js as part of #1346 step 2f -- these
// functions were the shared surface between eventHandler.js and its
// consumers (025-libraries.js, overlayHandler.js), and were the root
// of the eventHandler <-> overlayHandler circular reference that
// blocked the rest of the ES-modules migration.
//
// Public API:
//   updateAccordionHighlights()   -- Repaint .selected across the whole page.
//   hasCheckedTemplateGroupToggle(body) -- Predicate. Returns true / false / null.
//   hasLibraryFileEntries(body)   -- Predicate. Returns boolean.
//   highlightParentAccordions(el) -- Walk ancestors adding .selected.
//   removeHighlightIfEmpty(el)    -- Walk ancestors removing .selected.
//
// The functions are exported as named exports so consumers can import
// exactly what they need. eventHandler.js still monkey-patches these
// onto `window.EventHandler` for now to preserve the existing public
// contract; new code should prefer the imports.

/**
 * Returns true when the accordion body has at least one enabled
 * `[data-template-group]` toggle checked. Returns false when toggles
 * exist but none are checked. Returns null when no toggles are present.
 * The tri-state return matters -- callers use `=== false` to detect
 * "toggles exist and are all off", which is stronger than falsy.
 */
export function hasCheckedTemplateGroupToggle (accordionBody) {
  if (!accordionBody) return null
  const toggles = Array.from(accordionBody.querySelectorAll("input[type='checkbox'][data-template-group]"))
  if (!toggles.length) return null
  return toggles.some(toggle => toggle.checked)
}

/**
 * Returns true when the accordion body contains a populated hidden
 * input tracking library-file selections (metadata_files,
 * collection_files, or overlay_files). Empty string and the literal
 * '[]' both count as empty. Used to decide whether an accordion
 * should highlight even though it contains no direct form inputs.
 */
export function hasLibraryFileEntries (accordionBody) {
  if (!accordionBody) return false
  const hidden = accordionBody.querySelector(
    'input[type="hidden"][name$="-metadata_files"], input[type="hidden"][name$="-collection_files"], input[type="hidden"][name$="-overlay_files"]'
  )
  if (!hidden) return false
  const raw = String(hidden.value || '').trim()
  return Boolean(raw && raw !== '[]')
}

/**
 * Walk up the ancestor chain from `element` adding `.selected` to each
 * `.accordion-header` we pass through. Stops early on:
 *   - A parent marked `data-qs-minimal-yaml="false"` (adds highlight
 *     to that parent then returns; those parents don't cascade further).
 *   - A "Preview Overlays" parent (never inherits highlight).
 *   - A bare "Overlays" parent whose only checked descendants are
 *     Preview Overlays children (also never inherits).
 *
 * Otherwise, adds `.selected` to the parent header and continues one
 * level further up.
 */
export function highlightParentAccordions (element) {
  while (element) {
    const parentAccordion = element.closest('.accordion-item')
    if (!parentAccordion) break
    if (parentAccordion.dataset.qsMinimalYaml === 'false') {
      parentAccordion.querySelector('.accordion-header')?.classList.add('selected')
      return
    }

    const parentHeader = parentAccordion.querySelector('.accordion-header')
    const parentText = parentHeader ? parentHeader.textContent.trim() : ''
    const isPreviewOverlay = parentText.toLowerCase().includes('preview overlays')
    const isOverlaysSection = parentText.toLowerCase().includes('overlays')

    if (isPreviewOverlay) {
      console.log(`\u{1F6AB} [DEBUG] Skipping parent highlight for Preview Overlays: ${parentText}`)
      return
    }

    if (isOverlaysSection) {
      const hasValidChild = Array.from(parentAccordion.querySelectorAll('.accordion-item')).some(child => {
        const childHeader = child.querySelector('.accordion-header')
        const childText = childHeader ? childHeader.textContent.trim() : ''
        const isPreviewChild = childText.toLowerCase().includes('preview overlays')

        return !isPreviewChild && child.querySelector('input:checked:not(.template-child-toggle)')
      })

      if (!hasValidChild) {
        console.log(`\u{1F6AB} [DEBUG] Preventing Overlays from inheriting highlight due to only Preview Overlays: ${parentText}`)
        return
      }
    }

    console.log(`\u{1F3AF} [DEBUG] Adding highlight to parent: ${parentText}`)
    parentHeader.classList.add('selected')

    element = parentAccordion.parentElement.closest('.accordion-item')?.querySelector('.accordion-header')
  }
}

/**
 * Given an accordion-header element, decide whether the accordion is
 * empty enough to remove `.selected`. Empty means: no checked inputs,
 * no populated hidden library-file input, AND either no template-group
 * toggles OR at least one template-group toggle is checked.
 *
 * If we do remove `.selected`, we recurse to the parent accordion's
 * header -- otherwise a bottom-level clear wouldn't bubble up.
 *
 * Skips `.accordion-item` elements whose id contains `-previewOverlays`.
 */
export function removeHighlightIfEmpty (element) {
  if (!element) return
  const accordionItem = element.closest('.accordion-item')
  if (!accordionItem) return

  const accordionId = accordionItem.id || ''
  const isPreviewOverlay = accordionId.includes('-previewOverlays')

  const accordionBody = accordionItem.querySelector('.accordion-body')

  if (isPreviewOverlay) {
    console.log(`\u{1F6AB} [DEBUG] Preventing highlight removal check for Preview Overlays: ${accordionId}`)
    return
  }

  const hasSelections = accordionBody?.querySelector(
    "input[type='checkbox']:checked:not(.readonly-toggle):not(.template-child-toggle):not([hidden]):not([type='hidden']), " +
    "input[type='radio']:checked:not([hidden]):not([type='hidden']), " +
    "select[data-user-modified='true'] option:checked:not([value='']):not([value='none']), " +
    '.list-group li'
  ) !== null
  const bodyHasLibraryFileEntries = hasLibraryFileEntries(accordionBody)

  // If this accordion has collection toggles and none are enabled, force no highlight.
  const anyTemplateGroupChecked = hasCheckedTemplateGroupToggle(accordionBody)
  const effectiveSelections = (anyTemplateGroupChecked === false) ? false : (hasSelections || bodyHasLibraryFileEntries)

  if (!effectiveSelections) {
    element.classList.remove('selected')
  }

  // Recursively check parents
  const parentAccordionHeader = accordionItem.parentElement.closest('.accordion-item')?.querySelector('.accordion-header')
  removeHighlightIfEmpty(parentAccordionHeader)
}

/**
 * Sweep every `.accordion-item` on the page and repaint the
 * `.selected` class on its `.accordion-header`. This is the top-level
 * entry point called after any state change (checkbox toggled, input
 * edited, template-swatch clicked, library-file list mutated, etc.).
 *
 * Two passes:
 *   1. For every accordion, decide from its own contents whether it
 *      should highlight. If so, cascade up via `highlightParentAccordions`;
 *      otherwise decay via `removeHighlightIfEmpty`.
 *   2. Special-case the bare "Overlays" parent: it should only highlight
 *      when at least one non-preview child has a real selection.
 *
 * Preview-Overlays accordions never highlight themselves.
 */
export function updateAccordionHighlights () {
  console.log('\u{1F50D} [DEBUG] Updating accordion highlights...')

  document.querySelectorAll('.accordion-item').forEach((accordion) => {
    const accordionHeader = accordion.querySelector('.accordion-header')
    if (!accordionHeader) return

    const headerText = accordionHeader.textContent.trim()
    const isPreviewOverlay = headerText.toLowerCase().includes('preview overlays')
    const accordionBody = accordion.querySelector('.accordion-body')

    // Skip preview overlays
    if (isPreviewOverlay) {
      accordionHeader.classList.remove('selected')
      return
    }

    let isCheckedOrSelected = false
    let hasValue = false

    if (accordionBody) {
      // 1. Check for directly selected inputs (checkboxes, radios, list selections)
      isCheckedOrSelected = accordionBody.querySelector(
        "input[type='checkbox']:checked:not(.readonly-toggle):not(.template-child-toggle):not([hidden]):not([type='hidden']), " +
        "input[type='radio']:checked:not([hidden]):not([type='hidden']), " +
        '.list-group li'
      ) !== null

      // 1b. Any non-empty inputs/selects also count as activity
      // Suppress value-based highlighting for true Collection/Overlay sections,
      // but allow it for "Delete Collections" (so its numeric field bubbles up).
      const headerLower = headerText.toLowerCase()
      const isLibraryFileSection = hasLibraryFileEntries(accordionBody)
      const suppressValueCheck =
        !isLibraryFileSection &&
        (
          headerLower.includes('overlay') ||
          (headerLower.includes('collection') && !headerLower.includes('delete collections'))
        )
      if (isLibraryFileSection) {
        hasValue = true
      } else if (!suppressValueCheck) {
        const textInputs = Array.from(
          accordionBody.querySelectorAll("input[type='text'], input[type='number'], input[type='date']")
        )
        const selects = Array.from(accordionBody.querySelectorAll('select'))
        hasValue = textInputs.some((input) => {
          const v = (input.value || '').trim().toLowerCase()
          return v && v !== 'none'
        }) || selects.some((sel) => {
          const v = (sel.value || '').trim().toLowerCase()
          return v && v !== 'none'
        })
      }

      // 2. Check for modified template selects, but only if toggle is still ON
      if (!isCheckedOrSelected) {
        isCheckedOrSelected = Array.from(
          accordionBody.querySelectorAll('.template-variable-select[data-user-modified="true"]')
        ).some((select) => {
          const group = select.closest('.template-toggle-group')
          const toggle = group?.querySelector('.overlay-toggle')
          return toggle?.checked
        })
      }
    }

    // Collection accordions should not stay highlighted from child values/history
    // when every parent collection toggle is off.
    const anyTemplateGroupChecked = hasCheckedTemplateGroupToggle(accordionBody)
    if (anyTemplateGroupChecked === false) {
      isCheckedOrSelected = false
      hasValue = false
    }

    if (isCheckedOrSelected || hasValue) {
      accordionHeader.classList.add('selected')
      if (accordion.dataset.qsMinimalYaml !== 'false') {
        highlightParentAccordions(accordionHeader)
      }
    } else {
      removeHighlightIfEmpty(accordionHeader)
    }
  })

  // Special case: don't highlight parent "Overlays" if only preview overlays are selected
  document.querySelectorAll('.accordion-item').forEach((accordion) => {
    const accordionHeader = accordion.querySelector('.accordion-header')
    const headerText = accordionHeader?.textContent.trim().toLowerCase()
    if (headerText !== 'overlays') return

    const childItems = accordion.querySelectorAll('.accordion-item')
    const hasNonPreviewSelection = Array.from(childItems).some((child) => {
      const childHeader = child.querySelector('.accordion-header')
      const isPreview = childHeader?.textContent.trim().toLowerCase().includes('preview overlays')

      if (isPreview) return false

      // Only highlight if child toggle is on or has modified select tied to an enabled toggle
      const hasActiveToggle = child.querySelector(
        "input[type='checkbox']:checked:not(.readonly-toggle):not(.template-child-toggle):not([hidden]):not([type='hidden']), " +
        "input[type='radio']:checked:not([hidden]):not([type='hidden']), " +
        '.list-group li'
      )
      if (hasActiveToggle) return true

      const hasModifiedSelectWithToggle = Array.from(
        child.querySelectorAll('.template-variable-select[data-user-modified="true"]')
      ).some((select) => {
        const group = select.closest('.template-toggle-group')
        const toggle = group?.querySelector('.overlay-toggle')
        return toggle?.checked
      })

      return hasModifiedSelectWithToggle
    })

    if (hasNonPreviewSelection) {
      accordionHeader.classList.add('selected')
    } else {
      accordionHeader.classList.remove('selected')
    }
  })
}
