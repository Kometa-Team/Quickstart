import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

createApiKeyValidator({
  fieldId: 'notifiarr_apikey',
  validatedFieldId: 'notifiarr_validated',
  validatedAtFieldId: 'notifiarr_validated_at',
  endpoint: '/validate_notifiarr',
  buildPayload: (apiKey) => ({ notifiarr_apikey: apiKey }),
  messages: {
    empty: 'Please enter a Notifiarr API key.',
    success: 'Notifiarr API key is valid.',
    failure: 'Notifiarr API key is invalid.'
  }
})
