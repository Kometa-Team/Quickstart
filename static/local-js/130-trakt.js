import { refreshValidationCallout } from './modules/validationPageBase.js'
import {
  STATUS_COLOR_SUCCESS,
  STATUS_COLOR_ERROR,
  isBlankTokenValue,
  wireSecretToggle,
  wireCredentialResetListeners,
  showStatusMessage,
  performValidationRequest
} from './modules/oauthValidationHelpers.js'

// Trakt OAuth-PIN flow. Layered on top of oauthValidationHelpers.
// All DOM event wiring uses addEventListener -- no inline oninput /
// onclick attributes in the template, no window-exposed functions.
// Module-local everything, the way it should be.

const VALIDATED_FIELD_ID = 'trakt_validated'

const validatedAtInput = document.getElementById('trakt_validated_at')
const clientIdInput = document.getElementById('trakt_client_id')
const clientSecretInput = document.getElementById('trakt_client_secret')
const pinInput = document.getElementById('trakt_pin')
const urlField = document.getElementById('trakt_url')
const toggleButton = document.getElementById('toggleClientSecretVisibility')
const openUrlButton = document.getElementById('trakt_open_url')
const validateButton = document.getElementById('validate_trakt_pin')
const checkTokenButton = document.getElementById('trakt_check_token')
const isValidatedElement = document.getElementById('trakt_validated')

wireSecretToggle(clientSecretInput, toggleButton)

// Initial button enable/disable from persisted state.
validateButton.disabled = isValidatedElement.value.toLowerCase() === 'true'
if (checkTokenButton) {
  const accessToken = document.getElementById('access_token')?.value || ''
  checkTokenButton.disabled = isBlankTokenValue(accessToken)
}

wireCredentialResetListeners({
  fieldIds: ['trakt_client_id', 'trakt_client_secret', 'trakt_pin'],
  validatedField: isValidatedElement,
  validatedAtField: validatedAtInput,
  validateButton,
  checkTokenButton,
  validatedFieldId: VALIDATED_FIELD_ID
})

// Build the authorization URL when the client_id reaches the expected
// 64-char length. Editing the credential also invalidates the saved
// validated state (wireCredentialResetListeners already handles the
// reset; this also clears the validatedAt and refreshes the callout
// for symmetry with the legacy behavior).
function updateTraktURL () {
  const traktClientId = clientIdInput.value
  let myURL = ''
  if (traktClientId.length === 64) {
    isValidatedElement.value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    refreshValidationCallout(VALIDATED_FIELD_ID)
    myURL = 'https://trakt.tv/oauth/authorize?response_type=code&client_id=' + traktClientId + '&redirect_uri=urn:ietf:wg:oauth:2.0:oob'
  }
  urlField.value = myURL
  // The URL is built from credentials, so re-check the open-URL gate
  // here directly. Listening on the hidden urlField for 'input' events
  // wouldn't work -- programmatic .value assignment doesn't fire them.
  openUrlButton.disabled = urlField.value === ''
}

// Wire updateTraktURL to the Client ID only. The legacy template wired
// it to Client Secret too, but updateTraktURL doesn't read the secret,
// so the second wiring was a no-op.
clientIdInput.addEventListener('input', updateTraktURL)

openUrlButton.addEventListener('click', function () {
  const url = urlField.value
  if (url) {
    showSpinner('retrieve')
    window.open(url, '_blank').focus()
  }
})

pinInput.addEventListener('input', function () {
  validateButton.disabled = pinInput.value === ''
})

// Initial gating after the page has rendered. Replaces the previous
// `window.onload = ...` block.
openUrlButton.disabled = true
validateButton.disabled = true

// Trakt-specific success bookkeeping: copy 6 authorization fields into
// hidden form inputs, clear the PIN + URL, disable PIN-flow buttons,
// enable the Check Token button.
function applyTraktPinSuccess (data) {
  isValidatedElement.value = 'true'
  if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
  refreshValidationCallout(VALIDATED_FIELD_ID)
  document.getElementById('access_token').value = data.trakt_authorization_access_token
  document.getElementById('token_type').value = data.trakt_authorization_token_type
  document.getElementById('expires_in').value = data.trakt_authorization_expires_in
  document.getElementById('refresh_token').value = data.trakt_authorization_refresh_token
  document.getElementById('scope').value = data.trakt_authorization_scope
  document.getElementById('created_at').value = data.trakt_authorization_created_at
  pinInput.value = ''
  urlField.value = ''
  openUrlButton.disabled = true
  validateButton.disabled = true
  if (checkTokenButton) checkTokenButton.disabled = false
}

// PIN flow: POST /validate_trakt with id/secret/pin -> access tokens.
validateButton.addEventListener('click', function () {
  const statusMessage = document.getElementById('statusMessage')
  const traktClient = clientIdInput.value
  const traktSecret = clientSecretInput.value
  const traktPin = pinInput.value

  if (!traktClient || !traktSecret || !traktPin) {
    showStatusMessage(statusMessage, 'ID, secret, and PIN are all required.', STATUS_COLOR_ERROR)
    return
  }

  hideSpinner('retrieve')
  performValidationRequest({
    endpoint: '/validate_trakt',
    payload: { trakt_client_id: traktClient, trakt_client_secret: traktSecret, trakt_pin: traktPin },
    spinnerKey: 'validate',
    statusElement: statusMessage,
    onSuccess: (data) => {
      applyTraktPinSuccess(data)
      showStatusMessage(statusMessage, 'Trakt credentials validated successfully!', STATUS_COLOR_SUCCESS)
    },
    onFailure: () => {
      isValidatedElement.value = 'false'
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout(VALIDATED_FIELD_ID)
    },
    onError: () => {
      showStatusMessage(statusMessage, 'An error occurred while validating Trakt credentials.', STATUS_COLOR_ERROR)
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout(VALIDATED_FIELD_ID)
    }
  })
})

// Check Token re-validation: POST /validate_trakt_token using the
// already-saved access_token. On success, may rotate the token set
// (server returns an `authorization` block when a refresh happened).
if (checkTokenButton) {
  checkTokenButton.addEventListener('click', function () {
    const statusMessage = document.getElementById('statusMessage')
    const accessToken = document.getElementById('access_token')?.value || ''
    const clientId = clientIdInput?.value || ''

    if (isBlankTokenValue(accessToken) || isBlankTokenValue(clientId)) {
      showStatusMessage(statusMessage, 'Missing access token or client ID.', STATUS_COLOR_ERROR)
      return
    }

    const clientSecret = clientSecretInput?.value || ''
    const refreshToken = document.getElementById('refresh_token')?.value || ''

    performValidationRequest({
      endpoint: '/validate_trakt_token',
      payload: {
        access_token: accessToken,
        client_id: clientId,
        client_secret: clientSecret,
        refresh_token: refreshToken,
        debug: true
      },
      spinnerKey: 'check_trakt',
      statusElement: statusMessage,
      onSuccess: (data) => {
        if (data.authorization) {
          const auth = data.authorization
          if (auth.access_token) document.getElementById('access_token').value = auth.access_token
          if (auth.token_type) document.getElementById('token_type').value = auth.token_type
          if (auth.expires_in) document.getElementById('expires_in').value = auth.expires_in
          if (auth.refresh_token) document.getElementById('refresh_token').value = auth.refresh_token
          if (auth.scope) document.getElementById('scope').value = auth.scope
          if (auth.created_at) document.getElementById('created_at').value = auth.created_at
        }
        isValidatedElement.value = 'true'
        if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
        refreshValidationCallout(VALIDATED_FIELD_ID)
        showStatusMessage(statusMessage, 'Trakt token is valid.', STATUS_COLOR_SUCCESS)
      },
      onFailure: () => {
        isValidatedElement.value = 'false'
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout(VALIDATED_FIELD_ID)
      },
      onError: () => {
        showStatusMessage(statusMessage, 'An error occurred while validating Trakt token.', STATUS_COLOR_ERROR)
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout(VALIDATED_FIELD_ID)
      }
    })
  })
}
