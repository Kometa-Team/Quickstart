// Narrow helpers shared by the OAuth-PIN wizards (130-trakt and 140-mal).
//
// These two wizards implement variations on the same flow:
//
//     1. User enters Client ID + Client Secret (+ optional verifier).
//     2. JS derives an authorization URL and shows an "Open" button.
//     3. User clicks Open, completes OAuth in a new tab, gets back a
//        PIN (Trakt) or localhost-redirect URL (MAL).
//     4. User pastes the PIN/URL into a field and clicks Validate.
//     5. Server returns access_token + refresh_token + metadata, which
//        the wizard copies into hidden form inputs.
//     6. A separate "Check Token" button can re-validate the saved
//        token without re-doing the OAuth flow.
//
// They share ~70% of the surface area but each has irreducible
// wizard-specific glue (URL construction, gating button logic,
// inline-handler exposures bound to oninput="..." attributes in the
// templates). Rather than a mega-factory with 20 config options, this
// module exports 4 narrow helpers; the wizards orchestrate them.
//
// (Contrast createApiKeyValidator -- that pattern repeated 10+ times
// and the factory pays off. OAuth-PIN is N=2; helpers win on cohesion.)

import { setToggleButtonIcon, refreshValidationCallout } from './validationPageBase.js'

export const STATUS_COLOR_SUCCESS = '#75b798'
export const STATUS_COLOR_ERROR = '#ea868f'

/**
 * Treat a token-shaped string as "blank" if it's empty, whitespace-only,
 * or the literal strings "none" / "null" (case-insensitive). Both
 * wizards normalize stored token fields to these sentinels when reset,
 * and the Check Token button should stay disabled in that state.
 */
export function isBlankTokenValue (value) {
  if (!value) return true
  const trimmed = value.trim()
  if (!trimmed) return true
  const lowered = trimmed.toLowerCase()
  return lowered === 'none' || lowered === 'null'
}

/**
 * Show/hide password toggle for the Client Secret field. Mirrors the
 * pattern createApiKeyValidator uses internally, but standalone here
 * because OAuth wizards don't use that factory.
 *
 * @param {HTMLInputElement} secretInput
 * @param {HTMLButtonElement} toggleButton
 */
export function wireSecretToggle (secretInput, toggleButton) {
  if (!secretInput || !toggleButton) return
  if (secretInput.value.trim() === '') {
    secretInput.setAttribute('type', 'text')
    setToggleButtonIcon(toggleButton, true)
  } else {
    secretInput.setAttribute('type', 'password')
    setToggleButtonIcon(toggleButton, false)
  }
  toggleButton.addEventListener('click', function () {
    const currentType = secretInput.getAttribute('type')
    secretInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
    setToggleButtonIcon(this, currentType === 'password')
  })
}

/**
 * Wire input listeners that reset the validated state when the user
 * edits any credential field. Both Trakt and MAL do this for the same
 * reason: editing a credential invalidates whatever token was previously
 * stored, so the validate button should re-enable and the check-token
 * button should disable until a new round-trip succeeds.
 *
 * @param {object} config
 * @param {string[]} config.fieldIds          IDs of inputs to listen on.
 * @param {HTMLElement} config.validatedField Hidden field storing the
 *                                            validated state ('true'/'false').
 * @param {HTMLElement} [config.validatedAtField] Optional timestamp field.
 * @param {HTMLButtonElement} config.validateButton Becomes enabled again.
 * @param {HTMLButtonElement} [config.checkTokenButton] Becomes disabled.
 * @param {string} config.validatedFieldId    Passed to refreshValidationCallout.
 */
export function wireCredentialResetListeners (config) {
  const {
    fieldIds,
    validatedField,
    validatedAtField,
    validateButton,
    checkTokenButton,
    validatedFieldId
  } = config
  fieldIds.forEach((fieldId) => {
    const input = document.getElementById(fieldId)
    if (!input) {
      console.warn(`Warning: Element with ID '${fieldId}' not found.`)
      return
    }
    input.addEventListener('input', function () {
      if (validatedField) validatedField.value = 'false'
      if (validatedAtField) validatedAtField.value = ''
      if (validateButton) validateButton.disabled = false
      if (checkTokenButton) checkTokenButton.disabled = true
      refreshValidationCallout(validatedFieldId)
    })
  })
}

/**
 * Sets a status message element with the configured text + color and
 * makes it visible. No-op if the element is missing.
 *
 * @param {HTMLElement} statusElement
 * @param {string} text
 * @param {string} color  Use the STATUS_COLOR_* constants.
 */
export function showStatusMessage (statusElement, text, color) {
  if (!statusElement) return
  statusElement.textContent = text
  statusElement.style.color = color
  statusElement.style.display = 'block'
}

/**
 * POSTs JSON to an endpoint and routes the response through
 * success/failure/error callbacks. Manages the spinner + status
 * message in a uniform way, so each wizard's click handler is
 * just orchestration. Returns the underlying fetch promise so
 * callers can await it if they want.
 *
 * The callbacks receive the parsed response data (success/failure)
 * or the thrown error (error). They are responsible for setting
 * validatedField + validatedAtField + side effects -- this helper
 * deliberately does not touch those, because the success path for
 * Trakt populates 6 access-token fields while MAL populates 4, and
 * baking those differences in here would re-create the mega-factory
 * problem this module is trying to avoid.
 *
 * @param {object} config
 * @param {string} config.endpoint            URL to POST to.
 * @param {object} config.payload             JSON body.
 * @param {string} config.spinnerKey          Passed to showSpinner/hideSpinner.
 * @param {HTMLElement} config.statusElement  Receives status text.
 * @param {(data: object) => void} config.onSuccess
 *                                            Called when data.valid is truthy.
 * @param {(data: object) => void} config.onFailure
 *                                            Called when data.valid is falsy.
 * @param {(error: Error) => void} [config.onError]
 *                                            Called when fetch rejects.
 * @returns {Promise<void>}
 */
export function performValidationRequest (config) {
  const { endpoint, payload, spinnerKey, statusElement, onSuccess, onFailure, onError } = config
  showSpinner(spinnerKey)
  return fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
    .then((response) => response.json())
    .then((data) => {
      hideSpinner(spinnerKey)
      if (data.valid) {
        onSuccess(data)
      } else {
        onFailure(data)
        showStatusMessage(statusElement, data.error || 'Validation failed.', STATUS_COLOR_ERROR)
      }
    })
    .catch((error) => {
      hideSpinner(spinnerKey)
      console.error(`Error from ${endpoint}:`, error)
      if (typeof onError === 'function') onError(error)
    })
}
