/* global $, initialSonarrRootFolderPath, initialSonarrQualityProfile, initialSonarrLanguageProfile, showSpinner, hideSpinner */

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
    toggleButton.innerHTML = '<i class="fas fa-eye-slash"></i>' // Show eye-slash
  } else {
    apiKeyInput.setAttribute('type', 'password') // Hide actual key
    toggleButton.innerHTML = '<i class="fas fa-eye"></i>' // Show eye
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
    document.getElementById('validateButton').disabled = false
  })

  document.getElementById('sonarr_url').addEventListener('input', function () {
    document.getElementById('sonarr_validated').value = 'false'
    document.getElementById('validateButton').disabled = false
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
  dropdown.innerHTML = '<option value="">Select an option</option>'

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

  if (!isValid) {
    statusMessage.innerHTML = validationMessages.join('<br>')
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
      toggleButton.innerHTML = '<i class="fas fa-eye-slash"></i>'
    } else {
      apiKeyInput.type = 'password'
      toggleButton.innerHTML = '<i class="fas fa-eye"></i>'
    }
  }
}
