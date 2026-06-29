import { createApiKeyValidator } from './modules/createApiKeyValidator.js'
import { populateDropdown, setStatusMessageLines } from './modules/dropdownHelpers.js'

// Per-wizard helpers: populate the three dropdowns from a validate response.
// initialSonarrRootFolderPath/QualityProfile/LanguageProfile are window
// globals injected by the rendered template (current selections from the
// saved config), used to pre-select after dropdown population.
function populateSonarrDropdowns (data) {
  populateDropdown(
    'sonarr_root_folder_path', data.root_folders, 'path', 'path',
    typeof initialSonarrRootFolderPath !== 'undefined' ? initialSonarrRootFolderPath : ''
  )
  populateDropdown(
    'sonarr_quality_profile', data.quality_profiles, 'name', 'name',
    typeof initialSonarrQualityProfile !== 'undefined' ? initialSonarrQualityProfile : ''
  )
  populateDropdown(
    'sonarr_language_profile', data.language_profiles, 'name', 'name',
    typeof initialSonarrLanguageProfile !== 'undefined' ? initialSonarrLanguageProfile : ''
  )
}

// Pre-submit guard: navigation is allowed only if the user has either
// (a) never validated Sonarr or (b) validated AND selected all three
// dropdowns. Path validation from PathValidation (set up elsewhere)
// also blocks if any path field is invalid.
function validateSonarrPage () {
  const validated = document.getElementById('sonarr_validated').value.toLowerCase() === 'true'
  const rootFolderPath = document.getElementById('sonarr_root_folder_path').value
  const qualityProfile = document.getElementById('sonarr_quality_profile').value
  const languageProfile = document.getElementById('sonarr_language_profile').value
  const pathsValid = (typeof PathValidation !== 'undefined' && PathValidation.validateAll)
    ? PathValidation.validateAll()
    : true

  const errors = []
  if (validated) {
    if (!rootFolderPath) errors.push('Please select a valid Root Folder Path.')
    if (!qualityProfile) errors.push('Please select a valid Quality Profile.')
    if (!languageProfile) errors.push('Please select a valid Language Profile.')
  }
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
