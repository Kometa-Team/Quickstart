// Commonsense content-rating overlay preview helpers.
//
// Extracted from static/local-js/overlayHandler.js as a proof-of-concept
// for the Step 9 direction. That file is 8500+ lines with a single
// initializeOverlayBoards closure holding 200+ nested helpers -- this
// module carves out the smallest self-contained cluster (7 pure
// cfg->value functions with zero closure dependencies beyond `cfg`)
// so we have a proven pattern for the larger extractions to come.
//
// Every function here takes a `cfg` object shaped like:
//
//   { id: 'overlay_content_rating_commonsense', container: HTMLElement }
//
// and does nothing but query/mutate `cfg.container`. No listeners, no
// module-level state, no callbacks to the outer closure.

/**
 * True when `cfg` describes the Commonsense content-rating overlay.
 * The overlay id is a stable server-rendered token so we identify it
 * by exact string match rather than any structural DOM cue.
 */
export function isCommonsenseContentRatingOverlay (cfg) {
  return String(cfg?.id || '').trim() === 'overlay_content_rating_commonsense'
}

/**
 * The `[name="<template>[text]"]` input inside `cfg.container` that
 * holds the currently-selected commonsense preview value.
 * Returns null when the container is missing or has no overlay
 * template attached.
 */
export function getCommonsensePreviewTextInput (cfg) {
  if (!cfg?.container) return null
  const templateName = cfg.container.dataset.overlayTemplate
  if (!templateName) return null
  return cfg.container.querySelector(`[name="${templateName}[text]"]`)
}

/**
 * Enumerate the `<template>[use_<age>]` checkboxes into a sortable
 * option list of { value, label, enabled, sortValue }.
 *
 * Options are sorted numerically by `<age>` (with NaN pushed to the
 * end via MAX_SAFE_INTEGER) then alphabetically as a tiebreak.
 * Labels are stripped of a leading "Use " prefix so the preview UI
 * shows "13+" instead of "Use 13+".
 */
export function getCommonsensePreviewOptions (cfg) {
  if (!cfg?.container) return []
  const templateName = cfg.container.dataset.overlayTemplate
  if (!templateName) return []
  const options = []
  cfg.container.querySelectorAll(`input[type="checkbox"][name^="${templateName}[use_"]`).forEach((input) => {
    const rawName = String(input.name || '')
    const match = new RegExp(`^${templateName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\[use_(.+)\\]$`).exec(rawName)
    const value = String(match?.[1] || '').trim()
    if (!value) return
    const numericValue = Number(value)
    const labelEl = input.closest('.form-check')?.querySelector('.form-check-label')
    let label = String(labelEl?.textContent || `${value}+`).replace(/\s+/g, ' ').trim()
    if (label.toLowerCase().startsWith('use ')) {
      label = label.slice(4).trim()
    }
    options.push({
      value,
      label,
      enabled: input.checked,
      sortValue: Number.isFinite(numericValue) ? numericValue : Number.MAX_SAFE_INTEGER
    })
  })
  options.sort((a, b) => {
    if (a.sortValue !== b.sortValue) return a.sortValue - b.sortValue
    return a.label.localeCompare(b.label)
  })
  return options
}

/**
 * The first enabled option's value, falling back to the first option
 * overall, falling back to ''. Called when the current preview value
 * is missing or no longer valid.
 */
export function pickDefaultCommonsensePreviewValue (cfg) {
  const options = getCommonsensePreviewOptions(cfg)
  return options.find(option => option.enabled)?.value || options[0]?.value || ''
}

/**
 * The current preview value, self-healing: if the text input holds a
 * value that no option matches, it's rewritten to the default and the
 * default is returned. Callers may therefore assume the input is
 * always consistent with the option list after this call.
 */
export function getCommonsensePreviewValue (cfg) {
  const input = getCommonsensePreviewTextInput(cfg)
  const current = String(input?.value || '').trim()
  const options = getCommonsensePreviewOptions(cfg)
  const values = new Set(options.map(option => option.value))
  if (current && values.has(current)) return current
  const fallback = pickDefaultCommonsensePreviewValue(cfg)
  if (input && fallback) input.value = fallback
  return fallback
}

export function setCommonsensePreviewValue (cfg, value) {
  const input = getCommonsensePreviewTextInput(cfg)
  if (input) {
    input.value = String(value || '').trim()
  }
}

/**
 * Display normalisation for text pulled off the input: trim, and
 * upper-case the special-cased 'nr' sentinel. Everything else passes
 * through unchanged.
 */
export function normalizeCommonsensePreviewText (value) {
  const normalized = String(value || '').trim()
  if (!normalized) return ''
  return normalized.toLowerCase() === 'nr' ? 'NR' : normalized
}
