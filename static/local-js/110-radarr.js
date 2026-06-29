import { createApiKeyValidator } from './modules/createApiKeyValidator.js'
import { populateDropdown, setStatusMessageLines } from './modules/dropdownHelpers.js'

// Per-wizard helpers: populate the two dropdowns from a validate response.
// initialRadarrRootFolderPath and initialRadarrQualityProfile are window
// globals injected by the rendered template (current selections from the
// saved config), used to pre-select after dropdown population.
function populateRadarrDropdowns (data) {
  populateDropdown(
    'radarr_root_folder_path', data.root_folders, 'path', 'path',
    typeof initialRadarrRootFolderPath !== 'undefined' ? initialRadarrRootFolderPath : ''
  )
  populateDropdown(
    'radarr_quality_profile', data.quality_profiles, 'name', 'name',
    typeof initialRadarrQualityProfile !== 'undefined' ? initialRadarrQualityProfile : ''
  )
}

// Pre-submit guard: navigation is allowed only if the user has either
// (a) never validated Radarr (page is being skipped) or (b) validated
// AND selected a root folder + quality profile. Path validation from
// PathValidation (set up elsewhere) also blocks if any path field is
// invalid.
function validateRadarrPage () {
  const validated = document.getElementById('radarr_validated').value.toLowerCase() === 'true'
  if (!validated) return true // unvalidated user can skip the page

  const rootFolderPath = document.getElementById('radarr_root_folder_path').value
  const qualityProfile = document.getElementById('radarr_quality_profile').value
  const pathsValid = (typeof PathValidation !== 'undefined' && PathValidation.validateAll)
    ? PathValidation.validateAll()
    : true

  const errors = []
  if (!rootFolderPath) errors.push('Please select a valid Root Folder Path.')
  if (!qualityProfile) errors.push('Please select a valid Quality Profile.')
  if (!pathsValid) errors.push('Please fix invalid path fields before continuing.')

  const statusMessage = document.getElementById('statusMessage')
  if (errors.length) {
    setStatusMessageLines(statusMessage, errors)
    statusMessage.style.color = '#ea868f'
    statusMessage.style.display = 'block'
    return false
  }
  statusMessage.style.display = 'none'
  return true
}

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
