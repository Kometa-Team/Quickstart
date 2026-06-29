import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

// TMDB is the credential-validation factory plus one wizard-specific
// concern: the Next + JumpTo buttons are gated LIVE by the combination
// of (api key validated) AND (language dropdown chosen) AND (region
// dropdown chosen). Changes to any of the three update the buttons
// immediately, not on form submit.
//
// The dropdown gating concern is N=1 across the whole wizard suite
// (Radarr/Sonarr use a different "block on form submit" pattern; Plex
// has no such gating). Keeping it in this file rather than promoting
// to the factory.

const apiKeyInput = document.getElementById('tmdb_apikey')
const validatedField = document.getElementById('tmdb_validated')
const statusMessage = document.getElementById('statusMessage')
const languageDropdown = document.getElementById('tmdb_language')
const languageStatusMessage = document.getElementById('languageStatusMessage')
const regionDropdown = document.getElementById('tmdb_region')
const regionStatusMessage = document.getElementById('regionStatusMessage')
const nextButton = document.querySelector('button[onclick*="next"]')
const jumpToButton = document.querySelector('.dropdown-toggle')

const STATUS_COLOR_ERROR = '#ea868f'
const STATUS_COLOR_SUCCESS = '#75b798'

function isApiKeyValidated () {
  return validatedField && validatedField.value.toLowerCase() === 'true'
}

// Updates the per-dropdown status callout and the Next/JumpTo button
// disabled state. Reads the latest validatedField + dropdown values
// each time -- safe to call from input handlers, validation callbacks,
// or page-load init code.
function updateNavigationState () {
  const isLanguageValid = !!languageDropdown.value
  const isRegionValid = !!regionDropdown.value
  const isFormValid = isApiKeyValidated() && isLanguageValid && isRegionValid

  if (nextButton) nextButton.disabled = !isFormValid
  if (jumpToButton) jumpToButton.disabled = !isFormValid

  if (languageStatusMessage) {
    languageStatusMessage.textContent = isLanguageValid
      ? 'Language is valid.'
      : 'Please select a valid language.'
    languageStatusMessage.style.color = isLanguageValid ? STATUS_COLOR_SUCCESS : STATUS_COLOR_ERROR
    languageStatusMessage.style.display = 'block'
  }

  if (regionStatusMessage) {
    regionStatusMessage.textContent = isRegionValid
      ? 'Region is valid.'
      : 'Please select a valid region.'
    regionStatusMessage.style.color = isRegionValid ? STATUS_COLOR_SUCCESS : STATUS_COLOR_ERROR
    regionStatusMessage.style.display = 'block'
  }
}

// Initial API-key status message reflects the persisted validatedField.
// Unlike the post-validate flow (which uses the factory's success/failure
// messages), this is just the "what state did this page load in" message.
function showInitialApiKeyStatusMessage () {
  if (!statusMessage) return
  if (isApiKeyValidated()) {
    statusMessage.textContent = 'API key is valid!'
    statusMessage.style.color = STATUS_COLOR_SUCCESS
  } else {
    statusMessage.textContent = 'API key is invalid or not validated.'
    statusMessage.style.color = STATUS_COLOR_ERROR
  }
  statusMessage.style.display = 'block'
}

createApiKeyValidator({
  fieldId: 'tmdb_apikey',
  validatedFieldId: 'tmdb_validated',
  validatedAtFieldId: 'tmdb_validated_at',
  endpoint: '/validate_tmdb',
  buildPayload: (apiKey) => ({ tmdb_apikey: apiKey }),
  messages: {
    empty: 'API key cannot be empty.',
    success: 'API key is valid!',
    failure: 'Failed to validate TMDb. Please check your API Key.',
    networkError: 'An error occurred. Please try again.'
  },
  // After every validate response (success or failure) the dropdown-
  // gating state needs to be re-evaluated because validatedField just
  // changed.
  onValidationSuccess: updateNavigationState,
  onValidationFailure: updateNavigationState
})

// Wizard-specific extras layered on top of the factory:
//
// 1. Extra input listener on apiKey -- the factory's internal listener
//    already resets validatedField + button + callout. This second
//    listener hides the statusMessage (so the stale "API key is valid"
//    callout doesn't linger while the user retypes) and re-runs the
//    Next-button gating.
if (apiKeyInput) {
  apiKeyInput.addEventListener('input', function () {
    if (statusMessage) statusMessage.style.display = 'none'
    updateNavigationState()
  })
}

// 2. Dropdown change listeners -- gate the Next button live.
if (languageDropdown) languageDropdown.addEventListener('change', updateNavigationState)
if (regionDropdown) regionDropdown.addEventListener('change', updateNavigationState)

// 3. Initial page state.
showInitialApiKeyStatusMessage()
updateNavigationState()
