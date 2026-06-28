import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

createApiKeyValidator({
  fieldId: 'mdblist_apikey',
  validatedFieldId: 'mdblist_validated',
  validatedAtFieldId: 'mdblist_validated_at',
  endpoint: '/validate_mdblist',
  buildPayload: (apiKey) => ({ mdblist_apikey: apiKey }),
  messages: {
    failure: 'Failed to validate MDBList server. Please check your API Key.'
  }
})
