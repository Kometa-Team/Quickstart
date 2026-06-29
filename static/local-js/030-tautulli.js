import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

createApiKeyValidator({
  fieldId: 'tautulli_apikey',
  additionalFieldIds: ['tautulli_url'],
  validatedFieldId: 'tautulli_validated',
  validatedAtFieldId: 'tautulli_validated_at',
  endpoint: '/validate_tautulli',
  buildPayload: (apiKey, extras) => ({
    tautulli_url: extras.tautulli_url,
    tautulli_apikey: apiKey
  }),
  messages: {
    empty: 'Please enter both Tautulli URL and API Key.',
    success: 'Tautulli server validated successfully!',
    failure: 'Failed to validate Tautulli server. Please check your URL and API Key.',
    networkError: 'An error occurred while validating Tautulli server.'
  }
})
