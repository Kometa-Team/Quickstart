import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

createApiKeyValidator({
  fieldId: 'yamtrack_password',
  additionalFieldIds: ['yamtrack_url', 'yamtrack_username'],
  validatedFieldId: 'yamtrack_validated',
  validatedAtFieldId: 'yamtrack_validated_at',
  toggleButtonId: 'togglePasswordVisibility',
  endpoint: '/validate_yamtrack',
  buildPayload: (password, extras) => ({
    yamtrack_url: extras.yamtrack_url,
    yamtrack_username: extras.yamtrack_username,
    yamtrack_password: password
  }),
  messages: {
    empty: 'Please enter Yamtrack URL, username and password.',
    success: (data) => data.version
      ? `Yamtrack credentials validated successfully! Version: ${data.version}`
      : 'Yamtrack credentials validated successfully!',
    failure: (data) => data.error || data.message || 'Yamtrack credentials are invalid.',
    networkError: 'An error occurred while validating Yamtrack credentials.'
  }
})
