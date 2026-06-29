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
// Wizard-specific glue (kept here, not in the helper module):
//
//   - Authorization URL construction (Trakt-specific URL shape, gated
//     on client_id length === 64).
//   - Six access-token field bookkeeping on validation success.
//   - Pin field + URL button live-gating (inline oninput attributes
//     in the template require these as window-exposed functions).
//   - The Check Token re-validation path, which talks to a different
//     endpoint and consumes a different response shape.

const VALIDATED_FIELD_ID = 'trakt_validated'

const validatedAtInput = document.getElementById('trakt_validated_at')
const traktClientSecretInput = document.getElementById('trakt_client_secret')
const toggleButton = document.getElementById('toggleClientSecretVisibility')
const validateButton = document.getElementById('validate_trakt_pin')
const checkTokenButton = document.getElementById('trakt_check_token')
const isValidatedElement = document.getElementById('trakt_validated')

wireSecretToggle(traktClientSecretInput, toggleButton)

// Initial button enable/disable from persisted state.
const isValidated = isValidatedElement.value.toLowerCase()
validateButton.disabled = isValidated === 'true'
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

function updateTraktURL () {
  const traktClientId = document.getElementById('trakt_client_id').value
  let myURL = ''
  if (traktClientId.length === 64) {
    isValidatedElement.value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    refreshValidationCallout(VALIDATED_FIELD_ID)
    myURL = 'https://trakt.tv/oauth/authorize?response_type=code&client_id=' + traktClientId + '&redirect_uri=urn:ietf:wg:oauth:2.0:oob'
  }
  document.getElementById('trakt_url').value = myURL
  checkURLStart()
}

function openTraktUrl () {
  const url = document.getElementById('trakt_url').value
  if (url) {
    showSpinner('retrieve')
    window.open(url, '_blank').focus()
  }
}

function checkPinField () {
  const pin = document.getElementById('trakt_pin').value
  document.getElementById('validate_trakt_pin').disabled = pin === ''
}

function checkURLStart () {
  const url = document.getElementById('trakt_url').value
  document.getElementById('trakt_open_url').disabled = url === ''
}

// Templates wire these as inline oninput / onclick handlers, so they
// must be on window. (Eliminating inline handlers is HTML cleanup
// work, out of scope for Step 6.)
window.updateTraktURL = updateTraktURL
window.openTraktUrl = openTraktUrl
window.checkPinField = checkPinField
window.checkURLStart = checkURLStart

window.onload = function () {
  document.getElementById('trakt_open_url').disabled = true
  document.getElementById('validate_trakt_pin').disabled = true
  checkURLStart()
}

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
  document.getElementById('trakt_pin').value = ''
  document.getElementById('trakt_url').value = ''
  document.getElementById('trakt_open_url').disabled = true
  document.getElementById('validate_trakt_pin').disabled = true
  if (checkTokenButton) checkTokenButton.disabled = false
}

// PIN flow: POST /validate_trakt with id/secret/pin -> access tokens.
validateButton.addEventListener('click', function () {
  const statusMessage = document.getElementById('statusMessage')
  const traktClient = document.getElementById('trakt_client_id').value
  const traktSecret = document.getElementById('trakt_client_secret').value
  const traktPin = document.getElementById('trakt_pin').value

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
    const clientId = document.getElementById('trakt_client_id')?.value || ''

    if (isBlankTokenValue(accessToken) || isBlankTokenValue(clientId)) {
      showStatusMessage(statusMessage, 'Missing access token or client ID.', STATUS_COLOR_ERROR)
      return
    }

    const clientSecret = document.getElementById('trakt_client_secret')?.value || ''
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
