// Shared factory for credential-validation wizards: ONE primary credential
// input (api key or token), zero or more additional non-secret fields
// (url, topic, etc.), one validate button, server endpoint that returns
// { valid: boolean }. Used by every "fill in a credential then click
// Validate" page in the wizard.
//
// Single-field wizards (just an api key): 040-github, 050-omdb,
// 060-mdblist, 070-notifiarr, 087-apprise.
//
// Multi-field wizards (credential plus url/topic/etc): 030-tautulli,
// 080-gotify, 085-ntfy.
//
// Multi-field + post-validation hooks: 110-radarr, 120-sonarr use the
// onValidationSuccess callback to populate dropdowns from the response,
// the onPreSubmit callback to gate form submission on dropdown values,
// and revalidateOnLoad to refresh those dropdowns when an already-
// validated user returns to the page.
//
// Wizards with OAuth-PIN flows (010-plex, 130-trakt, 140-mal) are NOT
// migrated to this factory; their multi-step flow is fundamentally
// different from the "credential -> validate -> done" shape and they
// belong in a separate helper (Step 6 PR 4 later slices).
//
// DESIGN
//
//   The factory takes a config object describing every per-wizard
//   variable (field ids, endpoint, payload shape, status messages),
//   does all the DOM wiring once, and returns nothing. It is purely
//   side-effectful: the wizard module that imports it calls the factory
//   at module top level and that's it.
//
//   We accept fields by ID rather than passing pre-resolved elements
//   because: (a) all existing wizards lookup by ID, (b) the test suite
//   can populate document.body once per test, (c) the factory can
//   gracefully no-op if an expected element is absent (defence in depth
//   for partial template rendering).
//
//   The PRIMARY field (config.fieldId) is the credential -- it gets
//   the show/hide toggle treatment. ADDITIONAL fields
//   (config.additionalFieldIds) are non-secret accompanying inputs
//   that participate in the empty-validation check, the reset-on-input
//   listener wiring, and the payload builder. The toggle never applies
//   to them.
//
//   STATUS COLORS: the legacy code used hex literals (#ea868f, #75b798).
//   We preserve those exactly to avoid any visual regression.

import { setToggleButtonIcon, refreshValidationCallout } from './validationPageBase.js'

const STATUS_COLOR_ERROR = '#ea868f'
const STATUS_COLOR_SUCCESS = '#75b798'

const DEFAULT_MESSAGES = {
  empty: 'Please enter an API key.',
  success: 'API key is valid!',
  failure: 'API key is invalid.',
  networkError: 'An error occurred. Please try again.'
}

/**
 * Wire up a credential-validation wizard.
 *
 * @param {object} config
 * @param {string} config.fieldId                Element id of the primary credential input.
 *                                               Gets the show/hide toggle treatment.
 * @param {string[]} [config.additionalFieldIds=[]]  Element ids of additional non-secret fields
 *                                                   (e.g. url, topic). All are required for
 *                                                   the empty-validation check, get input
 *                                                   listeners that reset validation, and have
 *                                                   their values passed to buildPayload as the
 *                                                   second argument.
 * @param {string} config.validatedFieldId       Element id of the hidden "<service>_validated" input.
 * @param {string} [config.validatedAtFieldId]   Element id of the hidden "<service>_validated_at" timestamp input.
 * @param {string} [config.toggleButtonId='toggleApikeyVisibility']  Id of the show/hide toggle button.
 * @param {string} [config.validateButtonId='validateButton']        Id of the validate button.
 * @param {string} [config.statusMessageId='statusMessage']          Id of the status callout element.
 * @param {string} [config.formId='configForm']                      Id of the wrapping form (for submit reset).
 * @param {string} config.endpoint               URL the validate button POSTs to.
 * @param {(credentialValue: string, additionalValues: object) => object} config.buildPayload
 *                                               Builds the JSON body for the POST. The first
 *                                               argument is the credential field's value. The
 *                                               second is `{ [id]: value, ... }` for every id
 *                                               in additionalFieldIds (or `{}` if none).
 *                                               Single-field wizards can ignore the second arg.
 * @param {object} [config.messages]             Override individual status strings (empty/success/failure/networkError).
 *                                               Each value may be a literal string OR a (data) => string function
 *                                               (data is the server response, or `{}` for empty/networkError).
 *                                               Functions let wizards forward server-provided text verbatim
 *                                               (e.g. data.error from apprise, data.message from github).
 * @param {(data: object) => void} [config.onValidationSuccess]
 *                                               Called after a successful validate response, with the parsed
 *                                               response data. Runs AFTER the factory has set validatedField,
 *                                               shown the success message, and disabled the button. Used by
 *                                               wizards that need to consume extra fields from the response
 *                                               (e.g. Radarr/Sonarr populate dropdowns from data.root_folders,
 *                                               Plex copies db_cache + library lists into hidden form inputs).
 * @param {() => boolean} [config.onPreSubmit]   Called on form submit BEFORE the normal empty-value
 *                                               normalisation. Return false to call event.preventDefault()
 *                                               and block the submit. Used by wizards that gate navigation
 *                                               on additional state beyond "credential validated" (e.g.
 *                                               Radarr/Sonarr require the populated dropdowns to be filled).
 * @param {boolean} [config.revalidateOnLoad=false]  If true AND validatedField is already 'true' on page
 *                                               load, the factory issues a silent re-POST to the endpoint
 *                                               and invokes onValidationSuccess with the result. Used to
 *                                               repopulate post-validation state (dropdowns etc.) when an
 *                                               already-validated user returns to the page. No user-facing
 *                                               status message is shown for this silent call.
 * @param {string} [config.spinnerKey='validate'] Argument passed to show/hideSpinner.
 */
export function createApiKeyValidator (config) {
  const {
    fieldId,
    additionalFieldIds = [],
    validatedFieldId,
    validatedAtFieldId,
    toggleButtonId = 'toggleApikeyVisibility',
    validateButtonId = 'validateButton',
    statusMessageId = 'statusMessage',
    formId = 'configForm',
    endpoint,
    buildPayload,
    messages: messageOverrides = {},
    onValidationSuccess,
    onPreSubmit,
    revalidateOnLoad = false,
    spinnerKey = 'validate'
  } = config

  if (!fieldId) throw new Error('createApiKeyValidator: fieldId is required')
  if (!validatedFieldId) throw new Error('createApiKeyValidator: validatedFieldId is required')
  if (!endpoint) throw new Error('createApiKeyValidator: endpoint is required')
  if (typeof buildPayload !== 'function') {
    throw new Error('createApiKeyValidator: buildPayload must be a function')
  }

  const messages = { ...DEFAULT_MESSAGES, ...messageOverrides }

  const apiKeyInput = document.getElementById(fieldId)
  const validatedField = document.getElementById(validatedFieldId)
  const validatedAtInput = validatedAtFieldId ? document.getElementById(validatedAtFieldId) : null
  const validateButton = document.getElementById(validateButtonId)
  const toggleButton = document.getElementById(toggleButtonId)
  const form = document.getElementById(formId)

  // If the credential or validate button isn't on the page, this wizard
  // isn't fully rendered — bail. Other helpers tolerate missing optional
  // elements, but these two are load-bearing.
  if (!apiKeyInput || !validatedField || !validateButton) return

  // Resolve additional field elements once. Missing ones are silently
  // dropped from listener-wiring, empty-check, and payload-building --
  // same defence-in-depth posture as the optional toggle button.
  const additionalElements = additionalFieldIds
    .map(id => ({ id, el: document.getElementById(id) }))
    .filter(entry => entry.el)

  // ── initial visibility of the credential field ──────────────────────
  if (apiKeyInput.value.trim() === '') {
    apiKeyInput.setAttribute('type', 'text') // show placeholder text
    if (toggleButton) setToggleButtonIcon(toggleButton, true)
  } else {
    apiKeyInput.setAttribute('type', 'password')
    if (toggleButton) setToggleButtonIcon(toggleButton, false)
  }

  // ── initial button state ────────────────────────────────────────────
  validateButton.disabled = validatedField.value.toLowerCase() === 'true'

  // ── reset validation state when the user types ──────────────────────
  function resetValidation () {
    validatedField.value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    validateButton.disabled = false
    refreshValidationCallout(validatedFieldId)
  }

  apiKeyInput.addEventListener('input', resetValidation)
  for (const { el } of additionalElements) {
    el.addEventListener('input', resetValidation)
  }

  // ── status message helpers ──────────────────────────────────────────
  function showStatus (text, color) {
    const statusMessage = document.getElementById(statusMessageId)
    if (!statusMessage) return
    statusMessage.textContent = text
    statusMessage.style.color = color
    statusMessage.style.display = 'block'
  }

  // Message values can be either a literal string or a (data) => string
  // function. Functions let the wizard show server-provided text
  // verbatim (e.g. apprise returns data.error, github returns
  // data.message) without forcing the factory to know which fields
  // matter for each service.
  function resolveMessage (messageValue, data) {
    if (typeof messageValue === 'function') return messageValue(data || {})
    return messageValue
  }

  function collectAdditionalValues () {
    const out = {}
    for (const { id, el } of additionalElements) {
      out[id] = el.value
    }
    return out
  }

  // ── validate click handler ──────────────────────────────────────────
  validateButton.addEventListener('click', function () {
    const credentialValue = apiKeyInput.value
    const additionalValues = collectAdditionalValues()

    // Every additional field is required alongside the credential.
    const additionalAllPresent = additionalElements.every(
      ({ id }) => additionalValues[id]
    )
    if (!credentialValue || !additionalAllPresent) {
      showStatus(resolveMessage(messages.empty, {}), STATUS_COLOR_ERROR)
      return
    }

    // showSpinner/hideSpinner are still globals from 000-base.js.
    // When/if they migrate to a shared module, swap these calls.
    if (typeof showSpinner === 'function') showSpinner(spinnerKey)

    fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPayload(credentialValue, additionalValues))
    })
      .then(response => response.json())
      .then(data => {
        if (data.valid) {
          validatedField.value = 'true'
          if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
          refreshValidationCallout(validatedFieldId)
          showStatus(resolveMessage(messages.success, data), STATUS_COLOR_SUCCESS)
          validateButton.disabled = true
          if (typeof onValidationSuccess === 'function') onValidationSuccess(data)
        } else {
          validatedField.value = 'false'
          if (validatedAtInput) validatedAtInput.value = ''
          refreshValidationCallout(validatedFieldId)
          showStatus(resolveMessage(messages.failure, data), STATUS_COLOR_ERROR)
        }
      })
      .catch(() => {
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout(validatedFieldId)
        showStatus(resolveMessage(messages.networkError, {}), STATUS_COLOR_ERROR)
      })
      .finally(() => {
        if (typeof hideSpinner === 'function') hideSpinner(spinnerKey)
      })
  })

  // ── silent re-validate on page load (optional) ──────────────────
  // When a user returns to a previously-validated page, the persisted
  // validatedField is 'true' but any post-validation server state
  // (Radarr/Sonarr dropdown choices, etc.) was never re-fetched. If
  // the wizard opts in with revalidateOnLoad, hit the endpoint silently
  // and invoke onValidationSuccess so the wizard can repopulate.
  //
  // "Silent" means: no spinner, no status message, no button state
  // changes. Pure side-channel to refresh data. Failures are swallowed
  // -- if the server can't be reached on page load the dropdowns stay
  // empty until the user re-clicks Validate, which is the correct
  // degraded behaviour (rather than spuriously flipping validatedField
  // to false based on a transient network issue).
  if (revalidateOnLoad &&
      validatedField.value.toLowerCase() === 'true' &&
      typeof onValidationSuccess === 'function') {
    const credentialValue = apiKeyInput.value
    const additionalValues = collectAdditionalValues()
    const additionalAllPresent = additionalElements.every(
      ({ id }) => additionalValues[id]
    )
    if (credentialValue && additionalAllPresent) {
      fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload(credentialValue, additionalValues))
      })
        .then(response => response.json())
        .then(data => {
          if (data.valid) onValidationSuccess(data)
        })
        .catch(() => { /* swallowed; see comment above */ })
    }
  }

  // ── show/hide toggle for the credential field ───────────────────────
  if (toggleButton) {
    toggleButton.addEventListener('click', function () {
      const currentType = apiKeyInput.getAttribute('type')
      apiKeyInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
      setToggleButtonIcon(this, currentType === 'password')
    })
  }

  // ── on form submit, normalise an absent value to empty string ───────
  // Preserved verbatim from the legacy wizards — when the field is
  // entirely empty the form should still post an empty string, not
  // omit the field entirely. Applies to the primary credential AND
  // every additional field.
  //
  // If onPreSubmit is provided and returns false, the submit is
  // blocked via event.preventDefault(). The empty-value normalisation
  // still runs regardless, so the guard sees the same form state the
  // server would have.
  if (form) {
    form.addEventListener('submit', function (event) {
      if (!apiKeyInput.value) apiKeyInput.value = ''
      for (const { el } of additionalElements) {
        if (!el.value) el.value = ''
      }
      if (typeof onPreSubmit === 'function' && onPreSubmit() === false) {
        event.preventDefault()
      }
    })
  }
}
