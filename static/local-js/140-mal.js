import { refreshValidationCallout } from './modules/validationPageBase.js'
import {
  STATUS_COLOR_SUCCESS,
  STATUS_COLOR_ERROR,
  wireSecretToggle,
  wireCredentialResetListeners,
  showStatusMessage,
  performValidationRequest
} from './modules/oauthValidationHelpers.js'

// MyAnimeList OAuth flow. Layered on top of oauthValidationHelpers.
// Shape mirrors Trakt (#130) but with three notable differences:
//   - URL build is gated on client_id.length === 32 (Trakt is 64) and
//     incorporates a code_verifier PKCE challenge.
//   - The submission field is a localhost-redirect URL, not a PIN.
//   - The Check Token endpoint only consumes access_token and does
//     not rotate the token set on success.

const VALIDATED_FIELD_ID = 'mal_validated'

const validatedAtInput = document.getElementById('mal_validated_at')
const clientSecretInput = document.getElementById('mal_client_secret')
const toggleButton = document.getElementById('toggleClientSecretVisibility')
const validateButton = document.getElementById('validate_mal_url')
const checkTokenButton = document.getElementById('mal_check_token')
const isValidatedElement = document.getElementById('mal_validated')

wireSecretToggle(clientSecretInput, toggleButton)

// Initial button enable/disable from persisted state.
const isValidated = isValidatedElement ? isValidatedElement.value.toLowerCase() : 'false'
if (isValidated === 'true') validateButton.disabled = true
if (checkTokenButton) {
  const accessToken = document.getElementById('access_token')?.value || ''
  checkTokenButton.disabled = !accessToken.trim()
}

wireCredentialResetListeners({
  fieldIds: ['mal_client_id', 'mal_client_secret', 'mal_code_verifier', 'mal_localhost_url'],
  validatedField: isValidatedElement,
  validatedAtField: validatedAtInput,
  validateButton,
  checkTokenButton,
  validatedFieldId: VALIDATED_FIELD_ID
})

// The "Authorize" button opens the constructed authorization URL in
// a new tab. The legacy code wired this directly rather than via
// window-exposed function, so keep the same shape.
document.getElementById('mal_get_localhost_url').addEventListener('click', function () {
  const url = document.getElementById('mal_url').value
  if (url) {
    showSpinner('retrieve')
    window.open(url, '_blank').focus()
  }
})

function updateMALTargetURL () {
  const malClientId = document.getElementById('mal_client_id').value
  const codeVerifier = document.getElementById('mal_code_verifier').value
  let myURL = ''
  if (malClientId.length === 32) {
    isValidatedElement.value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    refreshValidationCallout(VALIDATED_FIELD_ID)
    myURL = 'https://myanimelist.net/v1/oauth2/authorize?response_type=code&client_id=' + malClientId + '&code_challenge=' + codeVerifier
  }
  document.getElementById('mal_url').value = myURL
  enableLocalURLButton()
}

function openMALUrl () {
  const url = document.getElementById('mal_url').value
  if (url) window.open(url, '_blank').focus()
}

function checkURLField () {
  const localURL = document.getElementById('mal_localhost_url').value
  document.getElementById('validate_mal_url').disabled = localURL === ''
}

function enableLocalURLButton () {
  const url = document.getElementById('mal_url').value
  document.getElementById('mal_get_localhost_url').disabled = url === ''
}

// Templates wire these as inline oninput handlers, so they must be on
// window. (Eliminating inline handlers is HTML cleanup, out of scope.)
window.updateMALTargetURL = updateMALTargetURL
window.openMALUrl = openMALUrl
window.checkURLField = checkURLField
window.enableLocalURLButton = enableLocalURLButton

window.onload = function () {
  document.getElementById('validate_mal_url').disabled = true
  enableLocalURLButton()
}

// MAL-specific success bookkeeping: copy 4 authorization fields into
// hidden form inputs and disable both auth-flow buttons.
function applyMALAuthSuccess (data) {
  isValidatedElement.value = 'true'
  if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
  refreshValidationCallout(VALIDATED_FIELD_ID)
  document.getElementById('access_token').value = data.mal_authorization_access_token
  document.getElementById('token_type').value = data.mal_authorization_token_type
  document.getElementById('expires_in').value = data.mal_authorization_expires_in
  document.getElementById('refresh_token').value = data.mal_authorization_refresh_token
  document.getElementById('mal_get_localhost_url').disabled = true
  document.getElementById('validate_mal_url').disabled = true
  if (checkTokenButton) checkTokenButton.disabled = false
}

// Auth completion: POST /validate_mal with id/secret/verifier/url ->
// access tokens.
validateButton.addEventListener('click', function () {
  const statusMessage = document.getElementById('statusMessage')
  const malClient = document.getElementById('mal_client_id').value
  const malSecret = document.getElementById('mal_client_secret').value
  const malVerifier = document.getElementById('mal_code_verifier').value
  const malLocalhostURL = document.getElementById('mal_localhost_url').value

  if (!malClient || !malSecret || !malVerifier || !malLocalhostURL) {
    showStatusMessage(statusMessage, 'ID, secret, and localhost URL are all required.', STATUS_COLOR_ERROR)
    return
  }

  hideSpinner('retrieve')
  performValidationRequest({
    endpoint: '/validate_mal',
    payload: {
      mal_client_id: malClient,
      mal_client_secret: malSecret,
      mal_code_verifier: malVerifier,
      mal_localhost_url: malLocalhostURL
    },
    spinnerKey: 'validate',
    statusElement: statusMessage,
    onSuccess: (data) => {
      applyMALAuthSuccess(data)
      showStatusMessage(statusMessage, 'MyAnimeList credentials validated successfully!', STATUS_COLOR_SUCCESS)
    },
    onFailure: () => {
      isValidatedElement.value = 'false'
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout(VALIDATED_FIELD_ID)
    },
    onError: () => {
      showStatusMessage(statusMessage, 'An error occurred while validating MAL credentials.', STATUS_COLOR_ERROR)
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout(VALIDATED_FIELD_ID)
    }
  })
})

// Check Token: POST /validate_mal_token with the saved access token.
if (checkTokenButton) {
  checkTokenButton.addEventListener('click', function () {
    const statusMessage = document.getElementById('statusMessage')
    const accessToken = document.getElementById('access_token')?.value || ''

    if (!accessToken.trim()) {
      showStatusMessage(statusMessage, 'Missing access token.', STATUS_COLOR_ERROR)
      return
    }

    performValidationRequest({
      endpoint: '/validate_mal_token',
      payload: { access_token: accessToken, debug: true },
      spinnerKey: 'check_mal',
      statusElement: statusMessage,
      onSuccess: () => {
        isValidatedElement.value = 'true'
        if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
        refreshValidationCallout(VALIDATED_FIELD_ID)
        showStatusMessage(statusMessage, 'MyAnimeList token is valid.', STATUS_COLOR_SUCCESS)
      },
      onFailure: () => {
        isValidatedElement.value = 'false'
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout(VALIDATED_FIELD_ID)
      },
      onError: () => {
        showStatusMessage(statusMessage, 'An error occurred while validating MyAnimeList token.', STATUS_COLOR_ERROR)
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout(VALIDATED_FIELD_ID)
      }
    })
  })
}
