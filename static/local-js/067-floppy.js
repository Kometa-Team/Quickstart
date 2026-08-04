import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

const floppyTokenRequired = Array.isArray(window.QS_FLOPPY_REQUIREMENT_REASONS) &&
  window.QS_FLOPPY_REQUIREMENT_REASONS.length > 0

createApiKeyValidator({
  fieldId: 'floppy_url',
  additionalFieldIds: floppyTokenRequired ? ['floppy_token'] : [],
  optionalFieldIds: floppyTokenRequired ? [] : ['floppy_token'],
  validatedFieldId: 'floppy_validated',
  validatedAtFieldId: 'floppy_validated_at',
  endpoint: '/validate_floppy',
  maskPrimaryField: false,
  buildPayload: (url, extras) => ({
    floppy_url: url,
    floppy_token: extras.floppy_token,
    floppy_require_token: floppyTokenRequired
  }),
  messages: {
    empty: floppyTokenRequired
      ? 'Please enter your Floppy URL and API token. A token is required by your selected ratings features.'
      : 'Please enter your Floppy URL.',
    success: (data) => data.message || 'Floppy connection validated.',
    failure: (data) => data.error || data.message || 'Floppy connection validation failed.',
    networkError: 'An error occurred while validating Floppy.'
  }
})
