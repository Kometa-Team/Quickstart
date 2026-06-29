import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

createApiKeyValidator({
  fieldId: 'ntfy_token',
  additionalFieldIds: ['ntfy_url', 'ntfy_topic'],
  validatedFieldId: 'ntfy_validated',
  validatedAtFieldId: 'ntfy_validated_at',
  toggleButtonId: 'toggleTokenVisibility',
  endpoint: '/validate_ntfy',
  buildPayload: (token, extras) => ({
    ntfy_url: extras.ntfy_url,
    ntfy_token: token,
    ntfy_topic: extras.ntfy_topic
  }),
  messages: {
    empty: 'Please enter ntfy URL, Token and Topic.',
    success: 'ntfy credentials validated successfully! Ensure you are subscribed to topic to see test message.',
    // ntfy server returns the actual failure reason in data.error
    failure: (data) => data.error,
    networkError: 'An error occurred while validating ntfy credentials.'
  }
})
