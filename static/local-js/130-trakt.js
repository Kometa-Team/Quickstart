import { createOauthValidator } from './modules/createOauthValidator.js'

// Trakt OAuth PIN flow. Migrated to the shared createOauthValidator
// factory in #1334 Step 6 PR 2.
//
// Trakt-specific quirks preserved from the pre-factory implementation:
//   - client_id length is 64 chars before the authorization URL is built
//   - authorization URL format is Trakt's oob (out-of-band) redirect
//   - validate endpoint returns 6 authorization fields to copy
//   - Check Token endpoint may rotate the token set via data.authorization
//   - After success, the PIN input and URL field are cleared, both
//     PIN-flow buttons are disabled, and the Check Token button becomes
//     enabled.

const TRAKT_CLIENT_ID_LENGTH = 64

createOauthValidator({
  serviceName: 'Trakt',
  validatedFieldId: 'trakt_validated',
  validatedAtFieldId: 'trakt_validated_at',
  clientIdFieldId: 'trakt_client_id',
  clientSecretFieldId: 'trakt_client_secret',
  authorizeButtonId: 'trakt_open_url',
  validateButtonId: 'validate_trakt_pin',
  checkTokenButtonId: 'trakt_check_token',
  urlFieldId: 'trakt_url',
  expectedClientIdLength: TRAKT_CLIENT_ID_LENGTH,
  buildAuthorizationURL: (clientId) =>
    `https://trakt.tv/oauth/authorize?response_type=code&client_id=${clientId}&redirect_uri=urn:ietf:wg:oauth:2.0:oob`,
  secondaryValueFieldId: 'trakt_pin',
  validateEndpoint: '/validate_trakt',
  validateSpinnerKey: 'validate',
  buildValidatePayload: ({ clientId, clientSecret, secondaryValue }) => ({
    trakt_client_id: clientId,
    trakt_client_secret: clientSecret,
    trakt_pin: secondaryValue
  }),
  messages: {
    validateMissingFields: 'ID, secret, and PIN are all required.'
  },
  applyValidateSuccess: (data, ctx) => {
    document.getElementById('access_token').value = data.trakt_authorization_access_token
    document.getElementById('token_type').value = data.trakt_authorization_token_type
    document.getElementById('expires_in').value = data.trakt_authorization_expires_in
    document.getElementById('refresh_token').value = data.trakt_authorization_refresh_token
    document.getElementById('scope').value = data.trakt_authorization_scope
    document.getElementById('created_at').value = data.trakt_authorization_created_at
    ctx.secondaryValueInput.value = ''
    ctx.urlField.value = ''
    ctx.authorizeButton.disabled = true
    ctx.validateButton.disabled = true
    if (ctx.checkTokenButton) ctx.checkTokenButton.disabled = false
  },
  checkTokenEndpoint: '/validate_trakt_token',
  checkTokenSpinnerKey: 'check_trakt',
  buildCheckTokenPayload: ({ accessToken, clientId, clientSecret, refreshToken }) => ({
    access_token: accessToken,
    client_id: clientId,
    client_secret: clientSecret,
    refresh_token: refreshToken,
    debug: true
  }),
  checkTokenPreflight: ({ accessToken, clientId }) => {
    // Trakt requires both accessToken AND clientId to be present
    // before hitting the server (server would reject otherwise).
    if (!accessToken.trim() || !clientId.trim()) {
      return 'Missing access token or client ID.'
    }
    return null
  },
  applyCheckTokenSuccess: (data) => {
    // Trakt-specific: response may rotate the token set. Copy the
    // rotated fields when the server sent them.
    if (data.authorization) {
      const auth = data.authorization
      if (auth.access_token) document.getElementById('access_token').value = auth.access_token
      if (auth.token_type) document.getElementById('token_type').value = auth.token_type
      if (auth.expires_in) document.getElementById('expires_in').value = auth.expires_in
      if (auth.refresh_token) document.getElementById('refresh_token').value = auth.refresh_token
      if (auth.scope) document.getElementById('scope').value = auth.scope
      if (auth.created_at) document.getElementById('created_at').value = auth.created_at
    }
  }
})
