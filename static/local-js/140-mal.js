import { createOauthValidator } from './modules/createOauthValidator.js'

// MyAnimeList OAuth PKCE flow. Migrated to the shared createOauthValidator
// factory in #1334 Step 6 PR 2.
//
// MAL-specific quirks preserved from the pre-factory implementation:
//   - client_id length is 32 chars before the authorization URL is built
//   - authorization URL uses PKCE (code_challenge = code_verifier)
//   - the "secondary value" is a localhost URL, not a PIN
//   - validate endpoint returns 4 authorization fields to copy
//   - Check Token endpoint doesn't rotate tokens; only marks valid
//   - After success, both authorize + validate buttons are disabled
//     and the Check Token button becomes enabled

const MAL_CLIENT_ID_LENGTH = 32

createOauthValidator({
  serviceName: 'MyAnimeList',
  validatedFieldId: 'mal_validated',
  validatedAtFieldId: 'mal_validated_at',
  clientIdFieldId: 'mal_client_id',
  clientSecretFieldId: 'mal_client_secret',
  authorizeButtonId: 'mal_get_localhost_url',
  validateButtonId: 'validate_mal_url',
  checkTokenButtonId: 'mal_check_token',
  urlFieldId: 'mal_url',
  expectedClientIdLength: MAL_CLIENT_ID_LENGTH,
  extraCredentialFieldIds: ['mal_code_verifier'],
  buildAuthorizationURL: (clientId, extras) =>
    `https://myanimelist.net/v1/oauth2/authorize?response_type=code&client_id=${clientId}&code_challenge=${extras.mal_code_verifier}`,
  secondaryValueFieldId: 'mal_localhost_url',
  validateEndpoint: '/validate_mal',
  validateSpinnerKey: 'validate',
  buildValidatePayload: ({ clientId, clientSecret, secondaryValue, extras }) => ({
    mal_client_id: clientId,
    mal_client_secret: clientSecret,
    mal_code_verifier: extras.mal_code_verifier,
    mal_localhost_url: secondaryValue
  }),
  messages: {
    validateMissingFields: 'ID, secret, and localhost URL are all required.'
  },
  applyValidateSuccess: (data, ctx) => {
    document.getElementById('access_token').value = data.mal_authorization_access_token
    document.getElementById('token_type').value = data.mal_authorization_token_type
    document.getElementById('expires_in').value = data.mal_authorization_expires_in
    document.getElementById('refresh_token').value = data.mal_authorization_refresh_token
    ctx.authorizeButton.disabled = true
    ctx.validateButton.disabled = true
    if (ctx.checkTokenButton) ctx.checkTokenButton.disabled = false
  },
  checkTokenEndpoint: '/validate_mal_token',
  checkTokenSpinnerKey: 'check_mal',
  buildCheckTokenPayload: ({ accessToken }) => ({
    access_token: accessToken,
    debug: true
  })
  // No applyCheckTokenSuccess -- MAL's check-token doesn't rotate tokens
  // (unlike Trakt). Just marking validated is enough.
})
