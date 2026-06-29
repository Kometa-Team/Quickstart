import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

createApiKeyValidator({
  fieldId: 'gotify_token',
  additionalFieldIds: ['gotify_url'],
  validatedFieldId: 'gotify_validated',
  validatedAtFieldId: 'gotify_validated_at',
  toggleButtonId: 'toggleTokenVisibility',
  endpoint: '/validate_gotify',
  buildPayload: (token, extras) => ({
    gotify_url: extras.gotify_url,
    gotify_token: token
  }),
  messages: {
    empty: 'Please enter both Gotify URL and Token.',
    success: 'Gotify credentials validated successfully!',
    // Gotify server returns the actual failure reason in data.error
    failure: (data) => data.error,
    networkError: 'An error occurred while validating Gotify credentials.'
  }
})
