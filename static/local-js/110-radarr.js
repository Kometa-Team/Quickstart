import { createApiKeyValidator } from './modules/createApiKeyValidator.js'
import { populateArrDropdown, buildArrPreSubmit } from './modules/arrPageBase.js'

// Radarr wizard — uses createApiKeyValidator for the credential flow,
// arrPageBase helpers for the dropdown-populate and form-submit gate.
//
// See modules/arrPageBase.js for the shared shape between this file
// and 120-sonarr.js.

function populateRadarrDropdowns (data) {
  populateArrDropdown('radarr_root_folder_path', data.root_folders, 'path', 'path', 'initialRadarrRootFolderPath')
  populateArrDropdown('radarr_quality_profile', data.quality_profiles, 'name', 'name', 'initialRadarrQualityProfile')
}

const validateRadarrPage = buildArrPreSubmit({
  validatedFieldId: 'radarr_validated',
  dropdowns: [
    { elementId: 'radarr_root_folder_path', errorMessage: 'Please select a valid Root Folder Path.' },
    { elementId: 'radarr_quality_profile', errorMessage: 'Please select a valid Quality Profile.' }
  ],
  skipWhenUnvalidated: true  // Radarr: an unvalidated user can skip the page cleanly.
})

createApiKeyValidator({
  fieldId: 'radarr_token',
  additionalFieldIds: ['radarr_url'],
  validatedFieldId: 'radarr_validated',
  validatedAtFieldId: 'radarr_validated_at',
  endpoint: '/validate_radarr',
  buildPayload: (token, extras) => ({
    radarr_url: extras.radarr_url,
    radarr_token: token
  }),
  messages: {
    empty: 'Please enter both Radarr URL and Token.',
    success: 'Radarr API key is valid.',
    failure: 'Failed to validate Radarr server. Please check your URL and Token.',
    networkError: 'Error validating Radarr'
  },
  onValidationSuccess: populateRadarrDropdowns,
  onPreSubmit: validateRadarrPage,
  revalidateOnLoad: true
})
