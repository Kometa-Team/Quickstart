/* global $, initialSonarrRootFolderPath, initialSonarrQualityProfile, initialSonarrLanguageProfile, showSpinner, hideSpinner, PathValidation */

function refreshValidationCallout () {
  if (window.QSValidationCallouts && typeof window.QSValidationCallouts.refresh === 'function') {
    window.QSValidationCallouts.refresh('sonarr_validated')
  }
}

const validatedAtInput = document.getElementById('sonarr_validated_at')

function setToggleButtonIcon (button, showPlainText) {
  if (!button) return
  const icon = document.createElement('i')
  icon.className = showPlainText ? 'fas fa-eye-slash' : 'fas fa-eye'
  button.replaceChildren(icon)
}

function setStatusMessageLines (element, messages) {
  if (!element) return
  element.textContent = ''
  messages.forEach((message, index) => {
    if (index > 0) element.appendChild(document.createElement('br'))
    element.appendChild(document.createTextNode(message))
  })
}

function resetDropdown (dropdown, placeholderText) {
  if (!dropdown) return
  const option = document.createElement('option')
  option.value = ''
  option.textContent = placeholderText
  dropdown.replaceChildren(option)
}

$(document).ready(function () {
  const apiKeyInput = document.getElementById('sonarr_token')
  const toggleButton = document.getElementById('toggleApikeyVisibility')
  const validateButton = document.getElementById('validateButton')
  const isValidatedElement = document.getElementById('sonarr_validated')
  const isValidated = isValidatedElement ? isValidatedElement.value.toLowerCase() : 'false'

  console.log('Validated:', isValidated)

  // Set initial visibility based on API key value
  if (apiKeyInput.value.trim() === '') {
    apiKeyInput.setAttribute('type', 'text') // Show placeholder text
    setToggleButtonIcon(toggleButton, true)
  } else {
    apiKeyInput.setAttribute('type', 'password') // Hide actual key
    setToggleButtonIcon(toggleButton, false)
  }

  // Disable validate button if already validated
  if (isValidatedElement) {
    validateButton.disabled = isValidated === 'true'
  }

  if (isValidated === 'true') {
    document.getElementById('validateButton').disabled = true
    fetchDropdownData() // Populate dropdowns if already validated
  } else {
    document.getElementById('validateButton').disabled = false
  }

  // Attach event listeners for input changes
  document.getElementById('sonarr_token').addEventListener('input', function () {
    document.getElementById('sonarr_validated').value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    document.getElementById('validateButton').disabled = false
    refreshValidationCallout()
  })

  document.getElementById('sonarr_url').addEventListener('input', function () {
    document.getElementById('sonarr_validated').value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    document.getElementById('validateButton').disabled = false
    refreshValidationCallout()
  })

  // Attach event listeners for validation and toggle functionality
  document.getElementById('validateButton').addEventListener('click', validateSonarrApi)
  document.getElementById('toggleApikeyVisibility').addEventListener('click', toggleApiKeyVisibility)

  // Add an event listener for form submission
  document.getElementById('configForm').addEventListener('submit', function (event) {
    if (!validateSonarrPage()) {
      event.preventDefault() // Prevent form submission if validation fails
    }
  })
})

/* eslint-disable camelcase */
function validateSonarrApi () {
  const sonarr_url = document.getElementById('sonarr_url').value
  const sonarr_token = document.getElementById('sonarr_token').value
  const statusMessage = document.getElementById('statusMessage')

  showSpinner('validate')

  fetch('/validate_sonarr', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ sonarr_url, sonarr_token })
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.valid) {
        hideSpinner('validate')
        document.getElementById('sonarr_validated').value = 'true'
        if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
        refreshValidationCallout()
        statusMessage.textContent = 'Sonarr API key is valid.'
        statusMessage.style.color = '#75b798'
        statusMessage.style.display = 'block'
        document.getElementById('validateButton').disabled = true

        populateDropdown('sonarr_root_folder_path', data.root_folders, 'path', 'path', initialSonarrRootFolderPath)
        populateDropdown('sonarr_quality_profile', data.quality_profiles, 'name', 'name', initialSonarrQualityProfile)
        populateDropdown('sonarr_language_profile', data.language_profiles, 'name', 'name', initialSonarrLanguageProfile)
      } else {
        hideSpinner('validate')
        document.getElementById('sonarr_validated').value = 'false'
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout()
        console.error('Error validating Sonarr', data.message)
        statusMessage.textContent = 'Failed to validate Sonarr server. Please check your URL and Token.'
        statusMessage.style.color = '#ea868f'
        statusMessage.style.display = 'block'
      }
    })
    .catch(error => {
      hideSpinner('validate')
      console.error('Error validating Sonarr:', error)
      statusMessage.textContent = 'Error validating Sonarr.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      document.getElementById('sonarr_validated').value = 'false'
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout()
    })
}

function fetchDropdownData () {
  // Fetch the stored dropdown data and populate the dropdowns
  const sonarr_url = document.getElementById('sonarr_url').value
  const sonarr_token = document.getElementById('sonarr_token').value

  fetch('/validate_sonarr', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ sonarr_url, sonarr_token })
  })
    .then((response) => response.json())
    .then((data) => {
      populateDropdown('sonarr_root_folder_path', data.root_folders, 'path', 'path', initialSonarrRootFolderPath)
      populateDropdown('sonarr_quality_profile', data.quality_profiles, 'name', 'name', initialSonarrQualityProfile)
      populateDropdown('sonarr_language_profile', data.language_profiles, 'name', 'name', initialSonarrLanguageProfile)
    })
    .catch(error => {
      console.error('Error fetching Sonarr dropdown data:', error)
    })
}
/* eslint-enable camelcase */
function populateDropdown (elementId, data, valueField, textField, selectedValue = '') {
  const dropdown = document.getElementById(elementId)
  resetDropdown(dropdown, 'Select an option')

  data.forEach(item => {
    const option = document.createElement('option')
    option.value = item[valueField]
    option.textContent = item[textField]
    dropdown.appendChild(option)
  })

  if (selectedValue) {
    dropdown.value = selectedValue
  }
}

function validateSonarrPage () {
  const rootFolderPath = document.getElementById('sonarr_root_folder_path').value
  const qualityProfile = document.getElementById('sonarr_quality_profile').value
  const languageProfile = document.getElementById('sonarr_language_profile').value
  const statusMessage = document.getElementById('statusMessage')
  let isValid = true
  const validationMessages = []
  const pathsValid = (typeof PathValidation !== 'undefined' && PathValidation.validateAll)
    ? PathValidation.validateAll()
    : true

  const isValidated = document.getElementById('sonarr_validated').value.toLowerCase() === 'true'

  if (isValidated) {
    if (!rootFolderPath) {
      validationMessages.push('Please select a valid Root Folder Path.')
      isValid = false
    }

    if (!qualityProfile) {
      validationMessages.push('Please select a valid Quality Profile.')
      isValid = false
    }

    if (!languageProfile) {
      validationMessages.push('Please select a valid Language Profile.')
      isValid = false
    }
  }

  if (!pathsValid) {
    validationMessages.push('Please fix invalid path fields before continuing.')
    isValid = false
  }

  if (!isValid) {
    setStatusMessageLines(statusMessage, validationMessages)
    statusMessage.style.color = '#ea868f'
    statusMessage.style.display = 'block'
  } else {
    statusMessage.style.display = 'none'
  }

  return isValid
}

function toggleApiKeyVisibility () {
  const apiKeyInput = document.getElementById('sonarr_token')
  const toggleButton = document.getElementById('toggleApikeyVisibility')
  if (apiKeyInput && toggleButton) {
    if (apiKeyInput.type === 'password') {
      apiKeyInput.type = 'text'
      setToggleButtonIcon(toggleButton, true)
    } else {
      apiKeyInput.type = 'password'
      setToggleButtonIcon(toggleButton, false)
    }
  }
}
