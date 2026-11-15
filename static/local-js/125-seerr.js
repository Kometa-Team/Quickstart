import { createApiKeyValidator } from './modules/createApiKeyValidator.js'
import { setToggleButtonIcon } from './modules/validationPageBase.js'

createApiKeyValidator({
  fieldId: 'seerr_apikey',
  additionalFieldIds: ['seerr_url'],
  validatedFieldId: 'seerr_validated',
  validatedAtFieldId: 'seerr_validated_at',
  endpoint: '/validate_seerr',
  buildPayload: (key, extras) => ({ seerr_url: extras.seerr_url, seerr_apikey: key }),
  messages: {
    empty: 'Enter both a Seerr URL and API key.',
    success: 'Seerr authentication succeeded. No media requests were created.',
    failure: data => data.error || 'Unable to authenticate with Seerr.',
    networkError: 'Unable to reach Quickstart to validate Seerr.'
  }
})

// Keep newly entered keys masked too; the shared validator reveals empty fields.
document.getElementById('seerr_apikey')?.setAttribute('type', 'password')
setToggleButtonIcon(document.getElementById('toggleApikeyVisibility'), false)

document.getElementById('seerr_tmp_enabled')?.addEventListener('change', () => {
  document.getElementById('seerr_validated').value = 'false'
  document.getElementById('seerr_validated_at').value = ''
})
