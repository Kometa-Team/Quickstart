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
// All DOM event wiring uses addEventListener -- no inline oninput /
// onclick attributes in the template, no window-exposed functions.
//
// Shape mirrors Trakt (#130) but with three notable differences:
//   - URL build is gated on client_id.length === 32 (Trakt is 64) and
//     incorporates a code_verifier PKCE challenge.
//   - The submission field is a localhost-redirect URL, not a PIN.
//   - The Check Token endpoint only consumes access_token and does
//     not rotate the token set on success.

const VALIDATED_FIELD_ID = 'mal_validated'

const validatedAtInput = document.getElementById('mal_validated_at')
const clientIdInput = document.getElementById('mal_client_id')
const clientSecretInput = document.getElementById('mal_client_secret')
const codeVerifierInput = document.getElementById('mal_code_verifier')
const urlField = document.getElementById('mal_url')
const localhostUrlInput = document.getElementById('mal_localhost_url')
const toggleButton = document.getElementById('toggleClientSecretVisibility')
const authorizeButton = document.getElementById('mal_get_localhost_url')
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

// Build the authorization URL when the client_id reaches the expected
// 32-char length. MAL needs the PKCE code_verifier to be present in
// the URL as the code_challenge query param.
function updateMALTargetURL () {
  const malClientId = clientIdInput.value
  const codeVerifier = codeVerifierInput.value
  let myURL = ''
  if (malClientId.length === 32) {
    isValidatedElement.value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    refreshValidationCallout(VALIDATED_FIELD_ID)
    myURL = 'https://myanimelist.net/v1/oauth2/authorize?response_type=code&client_id=' + malClientId + '&code_challenge=' + codeVerifier
  }
  urlField.value = myURL
  // Listening on the hidden urlField for 'input' events wouldn't work --
  // programmatic .value assignment doesn't fire them. Re-check the
  // Authorize button gate here directly.
  authorizeButton.disabled = urlField.value === ''
}

// Wire updateMALTargetURL to the Client ID only. The legacy template
// wired it to Client Secret too, but updateMALTargetURL doesn't read
// the secret, so the second wiring was a no-op.
clientIdInput.addEventListener('input', updateMALTargetURL)

// The "Authorize" button opens the constructed authorization URL in
// a new tab.
authorizeButton.addEventListener('click', function () {
  const url = urlField.value
  if (url) {
    showSpinner('retrieve')
    window.open(url, '_blank').focus()
  }
})

localhostUrlInput.addEventListener('input', function () {
  validateButton.disabled = localhostUrlInput.value === ''
})

// Initial gating after the page has rendered. Replaces the previous
// `window.onload = ...` block.
validateButton.disabled = true
authorizeButton.disabled = urlField.value === ''

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
  authorizeButton.disabled = true
  validateButton.disabled = true
  if (checkTokenButton) checkTokenButton.disabled = false
}

// Auth completion: POST /validate_mal with id/secret/verifier/url ->
// access tokens.
validateButton.addEventListener('click', function () {
  const statusMessage = document.getElementById('statusMessage')
  const malClient = clientIdInput.value
  const malSecret = clientSecretInput.value
  const malVerifier = codeVerifierInput.value
  const malLocalhostURL = localhostUrlInput.value

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
