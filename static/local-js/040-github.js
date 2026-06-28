import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

createApiKeyValidator({
  fieldId: 'github_token',
  validatedFieldId: 'github_validated',
  validatedAtFieldId: 'github_validated_at',
  endpoint: '/validate_github',
  buildPayload: (token) => ({ github_token: token }),
  messages: {
    empty: 'Please enter a GitHub Personal Access Token.',
    // GitHub server returns custom data.message on both success and failure
    success: (data) => data.message,
    failure: (data) => data.message,
    networkError: 'Error validating GitHub token.'
  }
})
