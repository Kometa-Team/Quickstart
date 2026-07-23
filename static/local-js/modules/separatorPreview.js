// Separator/preview cluster for the library overlay wizard.
//
// This module owns the "use_separator" dropdown lifecycle: the
// user picks a separator style (chart / award / etc.), and this
// code updates the corresponding hidden inputs, dependent toggles,
// preview image, and placeholder-field visibility. Extracted from
// overlayHandler.js as part of #1346 step 2f completion so
// eventHandler.js can consume the entry points via a direct import
// instead of `OverlayHandler.initializeOverlays` / `updateHiddenInputs`.
//
// Public API (imported by eventHandler.js and by overlayHandler.js
// itself for the bootstrap path):
//
//   initializeOverlays(libraryId, isMovie)
//     Attach change listeners to the separator dropdown and the
//     placeholder-source dropdown. Runs the initial sync on page load.
//     Idempotent -- dataset.listenerAdded guards against re-binding.
//
//   updateHiddenInputs(libraryId, isMovie)
//     Ensure the hidden form fields tracking `use_separator` and
//     `sep_style` exist on the form, and set their values based on
//     the current dropdown selection. Also enables/disables the
//     award and chart separator toggles accordingly.
//
//   syncSeparatorPlaceholderFields(wrapper, options)
//     Reconcile the placeholder wrapper's visible fields against
//     the selected source (imdb / tmdb_movie / tvdb_show). Called
//     by initializeOverlays' change listener, updateHiddenInputs
//     (when disabling), and overlayHandler.js's bootstrap.
//
// Internal helpers (module-scoped, not exported):
//   updateSeparatorToggles         -- flip award/chart toggle disabled state
//   updateSeparatorPreview         -- swap the preview image src
//   getSeparatorPlaceholderWrapper -- selector wrapper for a given library
//   toggleSeparatorPlaceholder     -- thin dispatch to syncSeparatorPlaceholderFields

import { updateAccordionHighlights } from './accordionHighlights.js'

/**
 * Enable/disable award + chart separator toggles based on whether
 * a separator style is selected. Kept as a mutator on the toggle
 * elements rather than a state-return so callers don't have to
 * re-query the DOM.
 */
function updateSeparatorToggles (libraryId, isEnabled) {
  console.log(`[DEBUG] Updating Separator Toggles for ${libraryId} - Enabled: ${isEnabled}`)

  const awardToggle = document.getElementById(`${libraryId}-collection_separator_award`)
  const chartToggle = document.getElementById(`${libraryId}-collection_separator_chart`)

  if (awardToggle) {
    awardToggle.disabled = !isEnabled
    awardToggle.checked = isEnabled
    console.log(`[DEBUG] Award Separator Toggle is now ${isEnabled ? 'ENABLED' : 'DISABLED'}`)
  }

  if (chartToggle) {
    chartToggle.disabled = !isEnabled
    chartToggle.checked = isEnabled
    console.log(`[DEBUG] Chart Separator Toggle is now ${isEnabled ? 'ENABLED' : 'DISABLED'}`)
  }
}

/**
 * Update the preview <img> src to point at the selected separator's
 * chart preview on the Default-Images repo. Shows/hides the preview
 * container based on whether a real style is selected.
 * `fieldId` looks like `<libraryId>-template_variables[use_separator]`
 * and gets transformed into container/image element IDs by escaping
 * the brackets.
 */
function updateSeparatorPreview (fieldId, selectedStyle) {
  console.log(`[DEBUG] Updating Separator Preview for ${fieldId} - Style: ${selectedStyle}`)

  const safeId = fieldId.replace('[', '_').replace(']', '')
  const containerId = `${safeId}-separatorPreviewContainer`
  const imageId = `${safeId}-separatorPreviewImage`

  const separatorPreviewContainer = document.getElementById(containerId)
  const separatorPreviewImage = document.getElementById(imageId)

  if (!separatorPreviewContainer || !separatorPreviewImage) {
    console.error(`[ERROR] Separator preview elements missing for ${fieldId}`)
    return
  }

  if (selectedStyle && selectedStyle !== 'none') {
    const imageUrl = `https://github.com/Kometa-Team/Default-Images/blob/master/separators/${selectedStyle}/chart.jpg?raw=true`
    separatorPreviewImage.src = imageUrl
    separatorPreviewContainer.style.display = 'block'
    console.log(`[DEBUG] Separator preview updated to: ${imageUrl}`)
  } else {
    separatorPreviewContainer.style.display = 'none'
  }
}

/**
 * DOM selector helper. Finds the placeholder wrapper for a given
 * library prefix. Split out from the callers because two functions
 * need it and re-typing the selector twice invited drift.
 */
function getSeparatorPlaceholderWrapper (libraryId) {
  return document.querySelector(`[data-separator-placeholder-wrapper="true"][data-library-prefix="${libraryId}"]`)
}

const separatorPlaceholderPicklistCache = new Map()

function placeholderValueKey (source) {
  if (source === 'tmdb_movie') return 'tmdb_movie'
  if (source === 'tvdb_show') return 'tvdb_show'
  return 'imdb_id'
}

function placeholderValueLabel (source) {
  if (source === 'tmdb_movie') return 'TMDb'
  if (source === 'tvdb_show') return 'TVDb'
  return 'IMDb'
}

function itemValueForSource (item, source) {
  const value = item?.[placeholderValueKey(source)]
  if (value) return String(value).trim()
  if (source === 'imdb' && String(item?.id || '').trim().startsWith('tt')) {
    return String(item.id).trim()
  }
  return ''
}

function optionTextForItem (item, source, value) {
  const title = String(item?.title || 'Untitled').trim()
  const label = placeholderValueLabel(source)
  return `${title} — ${label} ${value}`
}

function writeSeparatorLookupLabel (select) {
  if (!select?.id) return
  const hidden = document.getElementById(`${select.id}__lookup_labels`)
  if (!hidden) return
  const value = String(select.value || '').trim()
  const selectedOption = select.selectedOptions?.[0]
  const label = String(selectedOption?.dataset?.lookupLabel || '').trim()
  hidden.value = value && label ? JSON.stringify({ [value]: label }) : '{}'
  hidden.dispatchEvent(new Event('change', { bubbles: true }))
}

function setPlaceholderPicklistOptions (select, items) {
  if (!select) return
  const source = String(select.dataset.separatorPlaceholderInput || '').trim()
  const savedValue = String(select.dataset.separatorPlaceholderValue || select.value || '').trim()
  const options = []
  const seen = new Set()

  items.forEach(item => {
    const value = itemValueForSource(item, source)
    if (!value || seen.has(value)) return
    seen.add(value)
    options.push({
      value,
      text: optionTextForItem(item, source, value),
      label: String(item?.title || '').trim()
    })
  })

  select.replaceChildren()
  const blank = document.createElement('option')
  blank.value = ''
  blank.textContent = options.length ? '-- Choose a top audience-rated item --' : `No top items with ${placeholderValueLabel(source)} IDs found`
  select.appendChild(blank)

  if (savedValue && !seen.has(savedValue)) {
    const saved = document.createElement('option')
    saved.value = savedValue
    saved.textContent = `Saved ${placeholderValueLabel(source)} ID: ${savedValue}`
    saved.dataset.lookupLabel = ''
    select.appendChild(saved)
  }

  options.slice(0, 10).forEach(item => {
    const option = document.createElement('option')
    option.value = item.value
    option.textContent = item.text
    option.dataset.lookupLabel = item.label
    select.appendChild(option)
  })

  select.value = savedValue || ''
  if (select.value !== savedValue) {
    select.value = ''
  }
  writeSeparatorLookupLabel(select)
}

function setPlaceholderPicklistLoading (wrapper, loading) {
  wrapper.querySelectorAll('.separator-placeholder-picklist').forEach(select => {
    if (loading) {
      const currentValue = String(select.value || select.dataset.separatorPlaceholderValue || '').trim()
      select.replaceChildren()
      const option = document.createElement('option')
      option.value = currentValue
      option.textContent = 'Loading top audience-rated items...'
      select.appendChild(option)
      select.value = currentValue
    }
  })
}

function loadSeparatorPlaceholderPicklists (wrapper) {
  if (!wrapper || wrapper.classList.contains('visually-hidden')) return
  const libraryName = String(wrapper.dataset.libraryId || '').trim()
  const libraryType = String(wrapper.dataset.libraryType || 'movie').trim().toLowerCase()
  if (!libraryName) return

  const cacheKey = `${libraryType}:${libraryName}`
  let request = separatorPlaceholderPicklistCache.get(cacheKey)
  if (!request) {
    setPlaceholderPicklistLoading(wrapper, true)
    request = fetch(`/get_top_imdb_items/${encodeURIComponent(libraryName)}?type=${encodeURIComponent(libraryType)}`, {
      credentials: 'same-origin'
    })
      .then(response => {
        if (!response.ok) throw new Error(`Top item lookup failed (${response.status})`)
        return response.json()
      })
      .then(data => Array.isArray(data?.items) ? data.items : [])
      .catch(error => {
        console.error('[Separator Placeholder] Failed to load top items:', error)
        return []
      })
    separatorPlaceholderPicklistCache.set(cacheKey, request)
  }

  request.then(items => {
    wrapper.querySelectorAll('.separator-placeholder-picklist').forEach(select => {
      setPlaceholderPicklistOptions(select, items)
    })
  })
}

/**
 * Reconcile a placeholder wrapper's visible fields against the
 * selected source. Which sources are allowed depends on library type
 * (movie -> imdb/tmdb_movie; show -> imdb/tvdb_show). If the current
 * selection isn't allowed, falls back to the first allowed source
 * that has a value, or 'imdb'. Also toggles the whole wrapper's
 * .visually-hidden class based on the `show` option.
 */
export function syncSeparatorPlaceholderFields (wrapper, options = {}) {
  if (!wrapper) return

  const show = options.show !== false
  const libraryType = String(wrapper.dataset.libraryType || '').trim().toLowerCase()
  const allowedSources = libraryType === 'movie' ? ['imdb', 'tmdb_movie'] : ['imdb', 'tvdb_show']
  const sourceSelect = wrapper.querySelector('.separator-placeholder-source')
  const fieldInputs = Array.from(wrapper.querySelectorAll('[data-separator-placeholder-input]'))
  if (!sourceSelect || !fieldInputs.length) return

  const valueBySource = {}
  fieldInputs.forEach(input => {
    valueBySource[input.dataset.separatorPlaceholderInput] = String(input.value || '').trim()
    input.classList.remove('is-invalid')
  })

  let activeSource = String(sourceSelect.value || '').trim()
  if (!allowedSources.includes(activeSource)) {
    activeSource = allowedSources.find(source => valueBySource[source]) || 'imdb'
  }
  sourceSelect.value = activeSource
  sourceSelect.disabled = !show
  sourceSelect.classList.remove('is-invalid')
  wrapper.classList.toggle('visually-hidden', !show)

  fieldInputs.forEach(input => {
    const source = String(input.dataset.separatorPlaceholderInput || '').trim()
    const fieldGroup = input.closest('.separator-placeholder-field')
    const isActive = show && source === activeSource
    if (fieldGroup) fieldGroup.classList.toggle('d-none', !isActive)
    if (!isActive) {
      input.value = ''
      input.dataset.separatorPlaceholderValue = ''
      writeSeparatorLookupLabel(input)
    }
  })
  if (show) loadSeparatorPlaceholderPicklists(wrapper)
}

/**
 * Look up the placeholder wrapper for `libraryId` and delegate to
 * syncSeparatorPlaceholderFields. Kept as a separate helper so
 * callers can use `libraryId` directly without knowing about the
 * data-attribute selector shape.
 */
function toggleSeparatorPlaceholder (libraryId, show) {
  const wrapper = getSeparatorPlaceholderWrapper(libraryId)
  if (!wrapper) {
    console.error(`[ERROR] Separator placeholder block not found for libraryId: ${libraryId}`)
    return
  }
  syncSeparatorPlaceholderFields(wrapper, { show })
}

/**
 * Ensure the hidden form fields tracking use_separator + sep_style
 * exist on the config form (creating them if missing), and set their
 * values based on the current dropdown selection. Also flips the
 * award/chart separator toggles. Called both on initial load (via
 * initializeOverlays) and on every dropdown change.
 *
 * updateSeparatorPreview is called at the end so the preview image
 * stays in sync -- this is the one place where "preview" and "form
 * state" reconcile.
 */
export function updateHiddenInputs (libraryId, isMovie) {
  console.log(`[DEBUG] Updating hidden inputs for Library: ${libraryId} - ${isMovie ? 'Movies' : 'Shows'}`)

  const form = document.getElementById('configForm')
  if (!form) {
    console.error("[ERROR] Form element 'configForm' not found!")
    return
  }

  const useSeparatorsDropdown = document.querySelector(`[name="${libraryId}-template_variables[use_separator]"]`)
  let useSeparatorsInput = document.getElementById(`${libraryId}-template_variables_use_separator`)
  let sepStyleInput = document.getElementById(`${libraryId}-template_variables_sep_style`)

  const awardSeparatorToggle = document.getElementById(`${libraryId}-collection_separator_award`)
  const chartSeparatorToggle = document.getElementById(`${libraryId}-collection_separator_chart`)

  const selectedValue = useSeparatorsDropdown.value
  const isEnabled = selectedValue !== 'none'

  // Clear separator placeholder values if separator is disabled
  if (!isEnabled) {
    const placeholderWrapper = getSeparatorPlaceholderWrapper(libraryId)
    syncSeparatorPlaceholderFields(placeholderWrapper, { show: false })
  }

  // Create hidden inputs dynamically if missing
  if (!useSeparatorsInput) {
    useSeparatorsInput = document.createElement('input')
    useSeparatorsInput.type = 'hidden'
    useSeparatorsInput.name = `${libraryId}-template_variables[use_separator]`
    useSeparatorsInput.id = `${libraryId}-template_variables_use_separator`
    form.appendChild(useSeparatorsInput)
  }

  if (!sepStyleInput) {
    sepStyleInput = document.createElement('input')
    sepStyleInput.type = 'hidden'
    sepStyleInput.name = `${libraryId}-template_variables[sep_style]`
    sepStyleInput.id = `${libraryId}-template_variables_sep_style`
    form.appendChild(sepStyleInput)
  }
  sepStyleInput.value = isEnabled ? selectedValue : ''

  if (awardSeparatorToggle) {
    // Only depend on sep_style being set to enable/disable
    awardSeparatorToggle.disabled = !isEnabled
    awardSeparatorToggle.checked = isEnabled
  }

  if (chartSeparatorToggle) {
    // Only depend on sep_style being set to enable/disable
    chartSeparatorToggle.disabled = !isEnabled
    chartSeparatorToggle.checked = isEnabled
  }

  const fieldId = `${libraryId}-template_variables[use_separator]`
  updateSeparatorPreview(fieldId, selectedValue)
}

/**
 * Wire up event listeners for a library's separator/preview cluster.
 * Two listeners get attached:
 *
 *   1. The main separator-style dropdown -- on change, cascades
 *      updateSeparatorToggles + updateSeparatorPreview +
 *      toggleSeparatorPlaceholder + updateHiddenInputs, then triggers
 *      an accordion-highlight repaint.
 *
 *   2. The placeholder-source dropdown (imdb / tmdb_movie / etc.) --
 *      on change, resyncs the placeholder fields and triggers
 *      an accordion-highlight repaint.
 *
 * Both listeners are guarded by `dataset.listenerAdded` for
 * idempotency; safe to call this multiple times per libraryId.
 * On initial call, also runs the same cascade once so the DOM
 * reflects the current select value before any user interaction.
 */
export function initializeOverlays (libraryId, isMovie) {
  console.log(`[DEBUG] Initializing overlays for ${libraryId} - ${isMovie ? 'Movie' : 'Show'}`)

  // Attach event listener for separator dropdown
  const fieldId = `${libraryId}-template_variables[use_separator]`
  const separatorDropdown = document.querySelector(`[name="${fieldId}"]`)

  if (separatorDropdown && !separatorDropdown.dataset.listenerAdded) {
    separatorDropdown.addEventListener('change', () => {
      const selectedStyle = separatorDropdown.value !== 'none'
      updateSeparatorToggles(libraryId, selectedStyle)
      updateSeparatorPreview(fieldId, separatorDropdown.value)
      toggleSeparatorPlaceholder(libraryId, selectedStyle)
      updateHiddenInputs(libraryId, isMovie)
      updateAccordionHighlights()
    })

    separatorDropdown.dataset.listenerAdded = true

    // Apply separator logic on initial page load
    const initialSelected = separatorDropdown.value !== 'none'
    updateSeparatorToggles(libraryId, initialSelected)
    updateSeparatorPreview(fieldId, separatorDropdown.value)
    toggleSeparatorPlaceholder(libraryId, initialSelected)
    updateHiddenInputs(libraryId, isMovie)
    updateAccordionHighlights()
  }

  const placeholderWrapper = getSeparatorPlaceholderWrapper(libraryId)
  const sourceSelect = placeholderWrapper?.querySelector('.separator-placeholder-source')
  if (sourceSelect && !sourceSelect.dataset.listenerAdded) {
    sourceSelect.addEventListener('change', () => {
      const separatorsEnabled = separatorDropdown ? separatorDropdown.value !== 'none' : true
      syncSeparatorPlaceholderFields(placeholderWrapper, { show: separatorsEnabled })
      updateAccordionHighlights()
    })
    sourceSelect.dataset.listenerAdded = 'true'
  }

  placeholderWrapper?.querySelectorAll('.separator-placeholder-picklist').forEach(select => {
    if (select.dataset.listenerAdded === 'true') return
    select.addEventListener('change', () => {
      select.dataset.separatorPlaceholderValue = String(select.value || '').trim()
      writeSeparatorLookupLabel(select)
      updateAccordionHighlights()
    })
    select.dataset.listenerAdded = 'true'
  })
}
