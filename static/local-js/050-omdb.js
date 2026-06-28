import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

createApiKeyValidator({
  fieldId: 'omdb_apikey',
  validatedFieldId: 'omdb_validated',
  validatedAtFieldId: 'omdb_validated_at',
  endpoint: '/validate_omdb',
  buildPayload: (apiKey) => ({ omdb_apikey: apiKey }),
  messages: {
    empty: 'Please enter an OMDb API key.',
    success: 'OMDb API key is valid.',
    failure: 'OMDb API key is invalid.',
    networkError: 'Error validating OMDb API key.'
  }
})
