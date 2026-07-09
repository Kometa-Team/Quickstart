// Shared helpers for the Radarr and Sonarr wizards.
//
// These two wizards share the same shape:
//
//   1. User enters URL + Token, clicks Validate.
//   2. Server returns dropdown data (root folders, quality profiles,
//      language profiles).
//   3. Wizard populates 2 or 3 dropdowns from the response, pre-
//      selecting values from window-level "initial*" globals injected
//      by the rendered template.
//   4. On form submit, block navigation if the user has validated AND
//      any required dropdown is empty, OR if any path field is invalid.
//
// The wizard-specific glue (dropdown IDs, field-name mappings, and the
// error-message wording) lives in the wizard file. THIS module owns
// the two mechanical patterns that repeated verbatim across both:
//
//   populateArrDropdown  — safe-read of `initial*` global + populate
//   buildArrPreSubmit    — the "validated OR skip + collect errors"
//                          form-submit gate builder
//
// BEHAVIOR NOTE — Sonarr asymmetry preserved verbatim
//
//   Radarr short-circuits (`return true`) when the wizard isn't
//   validated, letting the user skip the page without a path-check.
//   Sonarr does NOT short-circuit; its path check runs even for
//   unvalidated users. This pre-existing asymmetry is a known bug
//   (#1584) that predates the Step 6 factory work. buildArrPreSubmit
//   supports both shapes via the `skipWhenUnvalidated` option so the
//   extract is behavior-preserving. Fix #1584 will flip Sonarr's
//   option to true.

import { populateDropdown, setStatusMessageLines } from './dropdownHelpers.js'

const STATUS_COLOR_ERROR = '#ea868f'

/**
 * Populate a single arr-wizard dropdown, pre-selecting the value from
 * a template-injected window global. Wraps populateDropdown with the
 * `typeof initial !== 'undefined'` safety dance that both wizards did
 * verbatim.
 *
 * The `initialGlobalName` string is looked up via `window[name]` at
 * call time so a globalName that was never injected (e.g. the user's
 * first visit) reads as `undefined` and falls through to empty-string.
 *
 * @param {string} elementId          Dropdown <select> element id.
 * @param {Array}  data                Options data from the validate response.
 * @param {string} valueField          Object key for <option> value.
 * @param {string} textField           Object key for <option> textContent.
 * @param {string} initialGlobalName   Name of the window global holding the
 *                                     currently-persisted selection, if any.
 */
export function populateArrDropdown (elementId, data, valueField, textField, initialGlobalName) {
  const initial = (initialGlobalName && typeof window[initialGlobalName] !== 'undefined')
    ? window[initialGlobalName]
    : ''
  populateDropdown(elementId, data, valueField, textField, initial)
}

/**
 * Build the form-submit gate for an arr wizard.
 *
 * Returns a function suitable for passing to createApiKeyValidator's
 * `onPreSubmit`. When called, it:
 *
 *   1. Reads validatedField's current value.
 *   2. If NOT validated AND skipWhenUnvalidated is true -> return true
 *      (allow navigation; user is skipping the page).
 *   3. If validated -> collect one error per required dropdown that
 *      is empty.
 *   4. Add the path-validation error if PathValidation is loaded AND
 *      any path field failed.
 *   5. If any errors: render them via setStatusMessageLines and return
 *      false (block navigation).
 *   6. Otherwise: hide the status message and return true.
 *
 * @param {object} config
 * @param {string} config.validatedFieldId   Element id of the hidden validated flag.
 * @param {string} config.statusMessageId    Element id of the status callout.
 *                                            Defaults to 'statusMessage'.
 * @param {Array<{elementId: string, errorMessage: string}>} config.dropdowns
 *   Ordered list of required dropdowns. Each entry says which element
 *   to check and what to say if it's empty. Order matters — errors
 *   render in the order given.
 * @param {boolean} [config.skipWhenUnvalidated=false]  When true, an
 *   unvalidated wizard skips ALL checks (dropdowns + path). Preserves
 *   the Radarr behavior. Sonarr passes false (see BEHAVIOR NOTE above);
 *   fix in issue #1584.
 * @param {string} [config.pathErrorMessage]  Override the path-error
 *   text. Defaults to the phrasing both wizards used verbatim.
 * @returns {() => boolean}
 */
export function buildArrPreSubmit (config) {
  const {
    validatedFieldId,
    statusMessageId = 'statusMessage',
    dropdowns,
    skipWhenUnvalidated = false,
    pathErrorMessage = 'Please fix invalid path fields before continuing.'
  } = config

  if (!validatedFieldId) throw new Error('buildArrPreSubmit: validatedFieldId is required')
  if (!Array.isArray(dropdowns)) throw new Error('buildArrPreSubmit: dropdowns must be an array')

  return function validateArrPage () {
    const validatedEl = document.getElementById(validatedFieldId)
    const validated = validatedEl && validatedEl.value.toLowerCase() === 'true'

    // Radarr-style skip: unvalidated user can leave the page without
    // any further checks. Sonarr opts OUT of this (see #1584).
    if (skipWhenUnvalidated && !validated) return true

    const pathsValid = (typeof window.PathValidation !== 'undefined' && window.PathValidation.validateAll)
      ? window.PathValidation.validateAll()
      : true

    const errors = []
    // Dropdown checks only apply when the wizard is validated — an
    // unvalidated user (in the Sonarr-style non-short-circuiting mode)
    // has no dropdown data to select from yet.
    if (validated) {
      for (const { elementId, errorMessage } of dropdowns) {
        const el = document.getElementById(elementId)
        if (!el || !el.value) errors.push(errorMessage)
      }
    }
    if (!pathsValid) errors.push(pathErrorMessage)

    const statusMessage = document.getElementById(statusMessageId)
    if (errors.length) {
      if (statusMessage) {
        setStatusMessageLines(statusMessage, errors)
        statusMessage.style.color = STATUS_COLOR_ERROR
        statusMessage.style.display = 'block'
      }
      return false
    }
    if (statusMessage) statusMessage.style.display = 'none'
    return true
  }
}
