// OAuth-shaped wizard factory. Layered on top of oauthValidationHelpers.
//
// Trakt and MAL follow the same 5-phase flow:
//   1. Toggle secret visibility on the client-secret input.
//   2. Reset validated=false whenever any credential input changes.
//   3. When the client_id reaches a wizard-specific length, build an
//      authorization URL (opened in a new tab via the "authorize" button).
//   4. Validate by POSTing the credentials + a secondary value (PIN or
//      localhost URL) to the wizard's endpoint. On success, copy
//      response fields into hidden form inputs.
//   5. Optionally re-validate an already-saved access token via a
//      separate check-token endpoint. May rotate the token set.
//
// Each of those phases is expressed via a small config block. The
// factory wires the DOM listeners and delegates to oauthValidationHelpers
// for the network + status-message primitives.
//
// The two callers today (130-trakt, 140-mal) shrink from ~200 lines
// each to ~60 lines of pure config.

import { refreshValidationCallout } from './validationPageBase.js'
import {
  STATUS_COLOR_SUCCESS,
  STATUS_COLOR_ERROR,
  isBlankTokenValue,
  wireSecretToggle,
  wireCredentialResetListeners,
  showStatusMessage,
  performValidationRequest
} from './oauthValidationHelpers.js'

const DEFAULT_STATUS_MESSAGE_ID = 'statusMessage'
const DEFAULT_ACCESS_TOKEN_FIELD_ID = 'access_token'

/**
 * Register an OAuth-shaped wizard on the current page.
 *
 * @param {object} config - see JSDoc keys below.
 *
 * REQUIRED:
 * @param {string} config.serviceName            Human-readable label used in status
 *                                               messages (e.g. "Trakt", "MyAnimeList").
 * @param {string} config.validatedFieldId       Hidden input tracking validated=true|false.
 * @param {string} config.clientIdFieldId        Input id for the OAuth client_id.
 * @param {string} config.clientSecretFieldId    Input id for the OAuth client_secret.
 * @param {string} config.authorizeButtonId      Button that opens the authorization URL.
 * @param {string} config.validateButtonId       Button that submits the validation flow.
 * @param {string} config.urlFieldId             Hidden input holding the constructed URL.
 * @param {number} config.expectedClientIdLength Trigger for building the auth URL.
 * @param {(clientId: string, extras: object) => string} config.buildAuthorizationURL
 *                                               Function producing the URL. `extras`
 *                                               carries values from `extraCredentialFieldIds`
 *                                               keyed by field id.
 * @param {string[]} config.extraCredentialFieldIds
 *                                               Additional credential input ids to
 *                                               wire (reset-on-input + reset-validation
 *                                               + optionally used inside URL builder
 *                                               and payload builders).
 * @param {string} config.secondaryValueFieldId  Input id whose non-empty value gates
 *                                               validateButton (e.g. `trakt_pin`,
 *                                               `mal_localhost_url`).
 * @param {string} config.validateEndpoint       URL for the validation POST.
 * @param {(payload: {clientId, clientSecret, extras, secondaryValue}) => object}
 *                                               config.buildValidatePayload
 * @param {string} config.validateSpinnerKey     Spinner key for the validate flow.
 * @param {(data: object, ctx: OauthValidatorContext) => void}
 *                                               config.applyValidateSuccess
 *                                               Called with the response body after
 *                                               a successful validation. The wizard
 *                                               copies response fields into hidden
 *                                               inputs here.
 *
 * OPTIONAL:
 * @param {string} [config.validatedAtFieldId]   Hidden input tracking the ISO
 *                                               timestamp of the last successful
 *                                               validation.
 * @param {string} [config.toggleButtonId='toggleClientSecretVisibility']
 *                                               Button toggling client_secret visibility.
 * @param {string} [config.checkTokenButtonId]   If present, wires the check-token flow.
 * @param {string} [config.checkTokenEndpoint]   URL for the check-token POST.
 * @param {(payload: {accessToken, clientId, clientSecret, refreshToken}) => object}
 *                                               [config.buildCheckTokenPayload]
 * @param {(payload: {accessToken, clientId, clientSecret, refreshToken}) => string|null}
 *                                               [config.checkTokenPreflight]
 *                                               Optional guard run before the check-token
 *                                               request. Return a non-empty string to
 *                                               abort with a status-message error; return
 *                                               null/undefined/empty to proceed. Defaults
 *                                               to blocking only on a blank access token.
 * @param {string} [config.checkTokenSpinnerKey='check']
 * @param {string} [config.accessTokenFieldId='access_token']
 * @param {string} [config.refreshTokenFieldId='refresh_token']
 * @param {(data: object, ctx: OauthValidatorContext) => void}
 *                                               [config.applyCheckTokenSuccess]
 *                                               Called with the response body on
 *                                               successful check-token; default is
 *                                               a no-op beyond marking validated.
 * @param {string} [config.statusMessageId='statusMessage']
 * @param {object} [config.messages]             Optional overrides for user-facing
 *                                               copy. Keys: `validateSuccess`,
 *                                               `validateError`, `validateMissingFields`,
 *                                               `checkTokenSuccess`, `checkTokenError`,
 *                                               `checkTokenMissingFields`.
 */
export function createOauthValidator (config) {
  const {
    serviceName,
    validatedFieldId,
    validatedAtFieldId,
    clientIdFieldId,
    clientSecretFieldId,
    toggleButtonId = 'toggleClientSecretVisibility',
    authorizeButtonId,
    validateButtonId,
    checkTokenButtonId,
    urlFieldId,
    expectedClientIdLength,
    buildAuthorizationURL,
    extraCredentialFieldIds = [],
    secondaryValueFieldId,
    validateEndpoint,
    buildValidatePayload,
    validateSpinnerKey,
    applyValidateSuccess,
    checkTokenEndpoint,
    buildCheckTokenPayload,
    checkTokenPreflight,
    checkTokenSpinnerKey = 'check',
    accessTokenFieldId = DEFAULT_ACCESS_TOKEN_FIELD_ID,
    refreshTokenFieldId = 'refresh_token',
    applyCheckTokenSuccess,
    statusMessageId = DEFAULT_STATUS_MESSAGE_ID,
    messages: messageOverrides = {}
  } = config

  requireConfig(config, [
    'serviceName',
    'validatedFieldId',
    'clientIdFieldId',
    'clientSecretFieldId',
    'authorizeButtonId',
    'validateButtonId',
    'urlFieldId',
    'expectedClientIdLength',
    'buildAuthorizationURL',
    'secondaryValueFieldId',
    'validateEndpoint',
    'buildValidatePayload',
    'validateSpinnerKey',
    'applyValidateSuccess'
  ])

  const messages = {
    validateSuccess: `${serviceName} credentials validated successfully!`,
    validateError: `An error occurred while validating ${serviceName} credentials.`,
    validateMissingFields: 'ID, secret, and secondary value are all required.',
    checkTokenSuccess: `${serviceName} token is valid.`,
    checkTokenError: `An error occurred while validating ${serviceName} token.`,
    checkTokenMissingFields: 'Missing access token.',
    ...messageOverrides
  }

  const clientIdInput = document.getElementById(clientIdFieldId)
  const clientSecretInput = document.getElementById(clientSecretFieldId)
  const validatedField = document.getElementById(validatedFieldId)
  const validatedAtInput = validatedAtFieldId ? document.getElementById(validatedAtFieldId) : null
  const authorizeButton = document.getElementById(authorizeButtonId)
  const validateButton = document.getElementById(validateButtonId)
  const secondaryValueInput = document.getElementById(secondaryValueFieldId)
  const urlField = document.getElementById(urlFieldId)
  const toggleButton = document.getElementById(toggleButtonId)
  const checkTokenButton = checkTokenButtonId ? document.getElementById(checkTokenButtonId) : null

  // If the load-bearing elements aren't on the page, this wizard isn't
  // fully rendered — bail. Matches createApiKeyValidator posture.
  if (!clientIdInput || !clientSecretInput || !validatedField ||
      !authorizeButton || !validateButton || !urlField || !secondaryValueInput) {
    return
  }

  wireSecretToggle(clientSecretInput, toggleButton)

  // Resolve extra credential inputs once. Missing entries are silently
  // dropped from listener wiring + URL/payload extras.
  const extraCredentialElements = extraCredentialFieldIds
    .map(id => ({ id, el: document.getElementById(id) }))
    .filter(entry => entry.el)

  // Initial button gating from persisted state.
  validateButton.disabled = validatedField.value.toLowerCase() === 'true'
  if (checkTokenButton) {
    const accessToken = document.getElementById(accessTokenFieldId)?.value || ''
    checkTokenButton.disabled = isBlankTokenValue(accessToken)
  }

  wireCredentialResetListeners({
    fieldIds: [clientIdFieldId, clientSecretFieldId, ...extraCredentialFieldIds, secondaryValueFieldId],
    validatedField,
    validatedAtField: validatedAtInput,
    validateButton,
    checkTokenButton,
    validatedFieldId
  })

  // Build the authorization URL when client_id reaches the expected length.
  function updateAuthorizationURL () {
    const clientId = clientIdInput.value
    let myURL = ''
    if (clientId.length === expectedClientIdLength) {
      validatedField.value = 'false'
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout(validatedFieldId)
      const extras = collectExtras(extraCredentialElements)
      myURL = buildAuthorizationURL(clientId, extras)
    }
    urlField.value = myURL
    // Programmatic .value assignment doesn't fire 'input' events, so
    // the authorize button gate is checked here directly.
    authorizeButton.disabled = urlField.value === ''
  }

  clientIdInput.addEventListener('input', updateAuthorizationURL)

  authorizeButton.addEventListener('click', function () {
    const url = urlField.value
    if (url) {
      showSpinner('retrieve')
      window.open(url, '_blank').focus()
    }
  })

  secondaryValueInput.addEventListener('input', function () {
    validateButton.disabled = secondaryValueInput.value === ''
  })

  // Initial gating after the page has rendered.
  authorizeButton.disabled = urlField.value === ''
  validateButton.disabled = validateButton.disabled || secondaryValueInput.value === ''

  // Context passed to the success callbacks so they can mutate the DOM
  // consistently without re-querying the same elements.
  const ctx = {
    clientIdInput,
    clientSecretInput,
    secondaryValueInput,
    validatedField,
    validatedAtInput,
    urlField,
    authorizeButton,
    validateButton,
    checkTokenButton,
    extras: extraCredentialElements,
    markValidated: () => {
      validatedField.value = 'true'
      if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
      refreshValidationCallout(validatedFieldId)
    }
  }

  validateButton.addEventListener('click', function () {
    const statusMessage = document.getElementById(statusMessageId)
    const clientId = clientIdInput.value
    const clientSecret = clientSecretInput.value
    const secondaryValue = secondaryValueInput.value
    const extras = collectExtras(extraCredentialElements)

    if (!clientId || !clientSecret || !secondaryValue ||
        extraCredentialElements.some(({ el }) => !el.value)) {
      showStatusMessage(statusMessage, messages.validateMissingFields, STATUS_COLOR_ERROR)
      return
    }

    hideSpinner('retrieve')
    performValidationRequest({
      endpoint: validateEndpoint,
      payload: buildValidatePayload({ clientId, clientSecret, secondaryValue, extras }),
      spinnerKey: validateSpinnerKey,
      statusElement: statusMessage,
      onSuccess: (data) => {
        ctx.markValidated()
        applyValidateSuccess(data, ctx)
        showStatusMessage(statusMessage, messages.validateSuccess, STATUS_COLOR_SUCCESS)
      },
      onFailure: () => {
        validatedField.value = 'false'
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout(validatedFieldId)
      },
      onError: () => {
        showStatusMessage(statusMessage, messages.validateError, STATUS_COLOR_ERROR)
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout(validatedFieldId)
      }
    })
  })

  if (checkTokenButton && checkTokenEndpoint && buildCheckTokenPayload) {
    checkTokenButton.addEventListener('click', function () {
      const statusMessage = document.getElementById(statusMessageId)
      const accessToken = document.getElementById(accessTokenFieldId)?.value || ''
      const clientId = clientIdInput?.value || ''
      const clientSecret = clientSecretInput?.value || ''
      const refreshToken = refreshTokenFieldId
        ? (document.getElementById(refreshTokenFieldId)?.value || '')
        : ''

      // Preflight guard. Wizards can plug in their own check (Trakt
      // requires both accessToken AND clientId to be present); default
      // is accessToken-only.
      const guardFn = typeof checkTokenPreflight === 'function'
        ? checkTokenPreflight
        : ({ accessToken: at }) => (isBlankTokenValue(at) ? messages.checkTokenMissingFields : null)
      const guardError = guardFn({ accessToken, clientId, clientSecret, refreshToken })
      if (guardError) {
        showStatusMessage(statusMessage, guardError, STATUS_COLOR_ERROR)
        return
      }

      performValidationRequest({
        endpoint: checkTokenEndpoint,
        payload: buildCheckTokenPayload({ accessToken, clientId, clientSecret, refreshToken }),
        spinnerKey: checkTokenSpinnerKey,
        statusElement: statusMessage,
        onSuccess: (data) => {
          if (typeof applyCheckTokenSuccess === 'function') {
            applyCheckTokenSuccess(data, ctx)
          }
          ctx.markValidated()
          showStatusMessage(statusMessage, messages.checkTokenSuccess, STATUS_COLOR_SUCCESS)
        },
        onFailure: () => {
          validatedField.value = 'false'
          if (validatedAtInput) validatedAtInput.value = ''
          refreshValidationCallout(validatedFieldId)
        },
        onError: () => {
          showStatusMessage(statusMessage, messages.checkTokenError, STATUS_COLOR_ERROR)
          if (validatedAtInput) validatedAtInput.value = ''
          refreshValidationCallout(validatedFieldId)
        }
      })
    })
  }
}

function collectExtras (extraCredentialElements) {
  const extras = {}
  for (const { id, el } of extraCredentialElements) {
    extras[id] = el.value
  }
  return extras
}

function requireConfig (config, keys) {
  for (const key of keys) {
    const value = config[key]
    const missing = value === undefined || value === null ||
      (typeof value === 'string' && value === '')
    if (missing) {
      throw new Error(`createOauthValidator: ${key} is required`)
    }
  }
}
