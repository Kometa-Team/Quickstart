import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

createApiKeyValidator({
  fieldId: 'serializd_password',
  additionalFieldIds: ['serializd_email', 'serializd_timeout'],
  validatedFieldId: 'serializd_validated',
  validatedAtFieldId: 'serializd_validated_at',
  toggleButtonId: 'togglePasswordVisibility',
  endpoint: '/validate_serializd',
  buildPayload: (password, extras) => ({
    serializd_email: extras.serializd_email,
    serializd_password: password,
    serializd_timeout: extras.serializd_timeout
  }),
  messages: {
    empty: 'Please enter your Serializd email and password.',
    success: (data) => data.message || 'Serializd credentials are valid.',
    failure: (data) => data.error || data.message || 'Serializd credentials are invalid.',
    networkError: 'An error occurred while validating Serializd credentials.'
  }
})
