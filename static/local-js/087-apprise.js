import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

createApiKeyValidator({
  fieldId: 'apprise_location',
  validatedFieldId: 'apprise_validated',
  validatedAtFieldId: 'apprise_validated_at',
  endpoint: '/validate_apprise',
  buildPayload: (location) => ({ apprise_location: location }),
  messages: {
    empty: 'Please enter an Apprise YAML path or URL.',
    success: 'Apprise location validated successfully!',
    // Apprise server returns the actual failure reason in data.error
    failure: (data) => data.error,
    networkError: 'An error occurred while validating the Apprise location.'
  }
})
