/* global showSpinner, hideSpinner */

document.addEventListener('DOMContentLoaded', function () {
  const validateButton = document.getElementById('validateButton')
  const apiKeyInput = document.getElementById('tmdb_apikey')
  const toggleButton = document.getElementById('toggleApikeyVisibility')
  const tmdbValidatedInput = document.getElementById('tmdb_validated')
  const statusMessage = document.getElementById('statusMessage')
  const languageDropdown = document.getElementById('tmdb_language')
  const languageStatusMessage = document.getElementById('languageStatusMessage')
  const regionDropdown = document.getElementById('tmdb_region')
  const regionStatusMessage = document.getElementById('regionStatusMessage')
  const nextButton = document.querySelector('button[onclick*="next"]')
  const jumpToButton = document.querySelector('.dropdown-toggle')

  console.log('Validated: ' + tmdbValidatedInput.value)

  // Set initial visibility based on API key value
  if (apiKeyInput.value.trim() === '') {
    apiKeyInput.setAttribute('type', 'text') // Show placeholder text
    toggleButton.innerHTML = '<i class="fas fa-eye-slash"></i>' // Set eye-slash icon
  } else {
    apiKeyInput.setAttribute('type', 'password') // Hide actual key
    toggleButton.innerHTML = '<i class="fas fa-eye"></i>' // Set eye icon
  }

  // Disable validate button if already validated
  validateButton.disabled = tmdbValidatedInput.value.toLowerCase() === 'true'

  // Check if API key is validated
  const isApiKeyValidated = () => tmdbValidatedInput.value.toLowerCase() === 'true'

  // Update API key validation message
  function updateApiKeyStatusMessage () {
    if (isApiKeyValidated()) {
      statusMessage.textContent = 'API key is valid!'
      statusMessage.style.color = '#75b798' // Green
    } else {
      statusMessage.textContent = 'API key is invalid or not validated.'
      statusMessage.style.color = '#ea868f' // Red
    }
    statusMessage.style.display = 'block'
  }

  // Update navigation buttons (Next and JumpTo)
  function updateNavigationState () {
    const isLanguageValid = !!languageDropdown.value
    const isRegionValid = !!regionDropdown.value
    const isFormValid = isApiKeyValidated() && isLanguageValid && isRegionValid

    nextButton.disabled = !isFormValid
    jumpToButton.disabled = !isFormValid

    // Update status messages for language and region
    languageStatusMessage.textContent = isLanguageValid
      ? 'Language is valid.'
      : 'Please select a valid language.'
    languageStatusMessage.style.color = isLanguageValid ? '#75b798' : '#ea868f'
    languageStatusMessage.style.display = 'block'

    regionStatusMessage.textContent = isRegionValid
      ? 'Region is valid.'
      : 'Please select a valid region.'
    regionStatusMessage.style.color = isRegionValid ? '#75b798' : '#ea868f'
    regionStatusMessage.style.display = 'block'
  }

  // Validate TMDb API key
  function validateApiKey () {
    const apiKey = apiKeyInput.value.trim()

    if (!apiKey) {
      statusMessage.textContent = 'API key cannot be empty.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      return
    }

    // Show spinner and disable the validate button
    showSpinner('validate')
    validateButton.disabled = true

    fetch('/validate_tmdb', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tmdb_apikey: apiKey })
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.valid) {
          tmdbValidatedInput.value = 'true'
          statusMessage.textContent = 'API key is valid!'
          statusMessage.style.color = '#75b798' // Green
        } else {
          tmdbValidatedInput.value = 'false'
          statusMessage.textContent = 'Failed to validate TMDb. Please check your API Key.'
          statusMessage.style.color = '#ea868f' // Red
        }
        updateNavigationState()
      })
      .catch((error) => {
        console.error('Error validating TMDb API:', error)
        statusMessage.textContent = 'An error occurred. Please try again.'
        statusMessage.style.color = '#ea868f' // Red
      })
      .finally(() => {
        hideSpinner('validate')
        statusMessage.style.display = 'block'
      })
  }

  // Toggle visibility of the API key input
  toggleButton.addEventListener('click', function () {
    const currentType = apiKeyInput.getAttribute('type')
    apiKeyInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
    this.innerHTML = currentType === 'password'
      ? '<i class="fas fa-eye-slash"></i>'
      : '<i class="fas fa-eye"></i>'
  })

  // Event listener for API key input changes
  apiKeyInput.addEventListener('input', function () {
    tmdbValidatedInput.value = 'false' // Mark API key as invalid
    validateButton.disabled = false // Re-enable the validate button
    statusMessage.style.display = 'none' // Hide validation message
    updateNavigationState() // Disable Next and JumpTo
  })

  // Event listeners for dropdown changes
  languageDropdown.addEventListener('change', updateNavigationState)
  regionDropdown.addEventListener('change', updateNavigationState)

  // Initialize navigation state on page load
  if (isApiKeyValidated()) {
    validateButton.disabled = true // Disable validate button if already validated
  }
  updateApiKeyStatusMessage()
  updateNavigationState()

  // Attach validation function to the validate button
  validateButton.addEventListener('click', validateApiKey)
})
