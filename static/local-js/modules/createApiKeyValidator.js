// Shared factory for the simplest validation wizard shape: ONE credential
// input (api key or token), one validate button, server endpoint that
// returns { valid: boolean }. Used by all the "just a key" pages —
// 050-omdb, 060-mdblist, 070-notifiarr, etc.
//
// Wizards with extra fields (Tautulli url + key, Gotify url + token, etc.)
// are NOT covered here. PR 2 of #1334 Step 6 will introduce a multi-field
// variant that builds on the same idea.
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
//   Default messages match what 060-mdblist used to say verbatim, so
//   the canary wizard's user-visible text is unchanged.
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
 * Wire up a single-credential validation wizard.
 *
 * @param {object} config
 * @param {string} config.fieldId                Element id of the credential input.
 * @param {string} config.validatedFieldId       Element id of the hidden "<service>_validated" input.
 * @param {string} [config.validatedAtFieldId]   Element id of the hidden "<service>_validated_at" timestamp input.
 * @param {string} [config.toggleButtonId='toggleApikeyVisibility']  Id of the show/hide toggle button.
 * @param {string} [config.validateButtonId='validateButton']        Id of the validate button.
 * @param {string} [config.statusMessageId='statusMessage']          Id of the status callout element.
 * @param {string} [config.formId='configForm']                      Id of the wrapping form (for submit reset).
 * @param {string} config.endpoint               URL the validate button POSTs to.
 * @param {(apiKey: string) => object} config.buildPayload           Builds the JSON body for the POST.
 * @param {string[]} [config.resetOnInputFieldIds=[]]                Extra field ids that should also reset
 *                                                                    validation state on input (e.g. url field
 *                                                                    on Gotify). The main fieldId is always
 *                                                                    reset; this is for additional ones.
 * @param {object} [config.messages]             Override individual status strings (empty/success/failure/networkError).
 *                                               Each value may be a literal string OR a (data) => string function
 *                                               (data is the server response, or `{}` for empty/networkError).
 *                                               Functions let wizards forward server-provided text verbatim
 *                                               (e.g. data.error from apprise, data.message from github).
 * @param {string} [config.spinnerKey='validate'] Argument passed to show/hideSpinner.
 */
export function createApiKeyValidator (config) {
  const {
    fieldId,
    validatedFieldId,
    validatedAtFieldId,
    toggleButtonId = 'toggleApikeyVisibility',
    validateButtonId = 'validateButton',
    statusMessageId = 'statusMessage',
    formId = 'configForm',
    endpoint,
    buildPayload,
    resetOnInputFieldIds = [],
    messages: messageOverrides = {},
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
  for (const extraId of resetOnInputFieldIds) {
    const extra = document.getElementById(extraId)
    if (extra) extra.addEventListener('input', resetValidation)
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

  // ── validate click handler ──────────────────────────────────────────
  validateButton.addEventListener('click', function () {
    const apiKey = apiKeyInput.value
    if (!apiKey) {
      showStatus(resolveMessage(messages.empty, {}), STATUS_COLOR_ERROR)
      return
    }

    // showSpinner/hideSpinner are still globals from 000-base.js.
    // When/if they migrate to a shared module, swap these calls.
    if (typeof showSpinner === 'function') showSpinner(spinnerKey)

    fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPayload(apiKey))
    })
      .then(response => response.json())
      .then(data => {
        if (data.valid) {
          validatedField.value = 'true'
          if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
          refreshValidationCallout(validatedFieldId)
          showStatus(resolveMessage(messages.success, data), STATUS_COLOR_SUCCESS)
          validateButton.disabled = true
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
  // omit the field entirely.
  if (form) {
    form.addEventListener('submit', function () {
      if (!apiKeyInput.value) {
        apiKeyInput.value = ''
      }
    })
  }
}
