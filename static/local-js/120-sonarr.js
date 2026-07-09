import { createApiKeyValidator } from './modules/createApiKeyValidator.js'
import { populateArrDropdown, buildArrPreSubmit } from './modules/arrPageBase.js'

// Sonarr wizard -- uses createApiKeyValidator for the credential flow,
// arrPageBase helpers for the dropdown-populate and form-submit gate.
//
// skipWhenUnvalidated=true matches Radarr: an unvalidated user can
// navigate away from the Sonarr page without a path check blocking
// them. Previously Sonarr ran the path check unconditionally, which
// stranded users with any invalid path field elsewhere on the page
// (bug #1584 -- pre-existed the Step 6 factory migration by years).

function populateSonarrDropdowns (data) {
  populateArrDropdown('sonarr_root_folder_path', data.root_folders, 'path', 'path', 'initialSonarrRootFolderPath')
  populateArrDropdown('sonarr_quality_profile', data.quality_profiles, 'name', 'name', 'initialSonarrQualityProfile')
  populateArrDropdown('sonarr_language_profile', data.language_profiles, 'name', 'name', 'initialSonarrLanguageProfile')
}

const validateSonarrPage = buildArrPreSubmit({
  validatedFieldId: 'sonarr_validated',
  dropdowns: [
    { elementId: 'sonarr_root_folder_path', errorMessage: 'Please select a valid Root Folder Path.' },
    { elementId: 'sonarr_quality_profile', errorMessage: 'Please select a valid Quality Profile.' },
    { elementId: 'sonarr_language_profile', errorMessage: 'Please select a valid Language Profile.' }
  ],
  skipWhenUnvalidated: true  // Matches Radarr; fixes #1584.
})

createApiKeyValidator({
  fieldId: 'sonarr_token',
  additionalFieldIds: ['sonarr_url'],
  validatedFieldId: 'sonarr_validated',
  validatedAtFieldId: 'sonarr_validated_at',
  endpoint: '/validate_sonarr',
  buildPayload: (token, extras) => ({
    sonarr_url: extras.sonarr_url,
    sonarr_token: token
  }),
  messages: {
    empty: 'Please enter both Sonarr URL and Token.',
    success: 'Sonarr API key is valid.',
    failure: 'Failed to validate Sonarr server. Please check your URL and Token.',
    networkError: 'Error validating Sonarr.'
  },
  onValidationSuccess: populateSonarrDropdowns,
  onPreSubmit: validateSonarrPage,
  revalidateOnLoad: true
})
