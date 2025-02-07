/* global $, initialRadarrRootFolderPath, initialRadarrQualityProfile, showSpinner, hideSpinner */

$(document).ready(function () {
  const apiKeyInput = document.getElementById('radarr_token')
  const toggleButton = document.getElementById('toggleApikeyVisibility')
  const validateButton = document.getElementById('validateButton')
  const isValidated = document.getElementById('radarr_validated').value.toLowerCase()

  console.log('Validated: ' + isValidated)

  // Set initial visibility based on API key value
  if (apiKeyInput.value.trim() === '') {
    apiKeyInput.setAttribute('type', 'text') // Show placeholder text
    toggleButton.innerHTML = '<i class="fas fa-eye-slash"></i>' // Show eye-slash
  } else {
    apiKeyInput.setAttribute('type', 'password') // Hide actual key
    toggleButton.innerHTML = '<i class="fas fa-eye"></i>' // Show eye
  }

  // Disable validate button if already validated
  validateButton.disabled = isValidated === 'true'

  if (isValidated === 'true') {
    document.getElementById('validateButton').disabled = true
    // Populate the dropdowns with the stored data if they are available
    fetchDropdownData()
  } else {
    document.getElementById('validateButton').disabled = false
  }

  // Attach event listeners for input changes
  document.getElementById('radarr_token').addEventListener('input', function () {
    document.getElementById('radarr_validated').value = 'false'
    document.getElementById('validateButton').disabled = false
  })

  document.getElementById('radarr_url').addEventListener('input', function () {
    document.getElementById('radarr_validated').value = 'false'
    document.getElementById('validateButton').disabled = false
  })

  // Attach event listeners for validation and toggle functionality
  document.getElementById('validateButton').addEventListener('click', validateRadarrApi)
  document.getElementById('toggleApikeyVisibility').addEventListener('click', toggleApiKeyVisibility)

  // Add an event listener for form submission
  document.getElementById('configForm').addEventListener('submit', function (event) {
    if (!validateRadarrPage()) {
      event.preventDefault() // Prevent form submission if validation fails
    }
  })
})

/* eslint-disable camelcase */
function fetchDropdownData () {
  // Fetch the stored dropdown data and populate the dropdowns
  const radarr_url = document.getElementById('radarr_url').value
  const radarr_token = document.getElementById('radarr_token').value

  fetch('/validate_radarr', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ radarr_url, radarr_token })
  })
    .then((response) => response.json())
    .then((data) => {
      populateDropdown('radarr_root_folder_path', data.root_folders, 'path', 'path', initialRadarrRootFolderPath)
      populateDropdown('radarr_quality_profile', data.quality_profiles, 'name', 'name', initialRadarrQualityProfile)
    })
    .catch((error) => {
      console.error('Error fetching Radarr dropdown data:', error)
    })
}

function populateDropdown (elementId, data, valueField, textField, selectedValue = '') {
  const dropdown = document.getElementById(elementId)
  dropdown.innerHTML = '<option value="">Select an option</option>'

  data.forEach((item) => {
    const option = document.createElement('option')
    option.value = item[valueField]
    option.textContent = item[textField]
    dropdown.appendChild(option)
  })

  if (selectedValue) {
    dropdown.value = selectedValue
  }
}

// Validate Radarr page fields
function validateRadarrPage () {
  const isValidated = document.getElementById('radarr_validated').value.toLowerCase()
  const rootFolderPath = document.getElementById('radarr_root_folder_path').value
  const qualityProfile = document.getElementById('radarr_quality_profile').value
  const statusMessage = document.getElementById('statusMessage')
  let isValid = true
  const validationMessages = []

  // Skip validation if Radarr is not validated
  if (isValidated !== 'true') {
    return true // Allow navigation
  }

  // Validate Root Folder Path
  if (!rootFolderPath) {
    validationMessages.push('Please select a valid Root Folder Path.')
    isValid = false
  }

  // Validate Quality Profile
  if (!qualityProfile) {
    validationMessages.push('Please select a valid Quality Profile.')
    isValid = false
  }

  // Display validation messages
  if (!isValid) {
    statusMessage.innerHTML = validationMessages.join('<br>')
    statusMessage.style.color = '#ea868f' // Warning color
    statusMessage.style.display = 'block'
  } else {
    statusMessage.style.display = 'none'
  }

  return isValid
}

function validateRadarrApi () {
  const radarr_url = document.getElementById('radarr_url').value
  const radarr_token = document.getElementById('radarr_token').value
  const statusMessage = document.getElementById('statusMessage')

  showSpinner('validate')

  fetch('/validate_radarr', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ radarr_url, radarr_token })
  })
    .then((response) => response.json())
    .then((data) => {
      hideSpinner('validate')

      if (data.valid) {
        document.getElementById('radarr_validated').value = 'true'
        statusMessage.textContent = 'Radarr API key is valid.'
        statusMessage.style.color = '#75b798'
        statusMessage.style.display = 'block'
        document.getElementById('validateButton').disabled = true

        populateDropdown('radarr_root_folder_path', data.root_folders, 'path', 'path', initialRadarrRootFolderPath)
        populateDropdown('radarr_quality_profile', data.quality_profiles, 'name', 'name', initialRadarrQualityProfile)
      } else {
        document.getElementById('radarr_validated').value = 'false'
        console.log('Error validating Radarr', data.message)
        statusMessage.textContent = 'Failed to validate Radarr server. Please check your URL and Token.'
        statusMessage.style.color = '#ea868f'
        statusMessage.style.display = 'block'
      }
    })
    .catch((error) => {
      hideSpinner('validate')
      console.error('Error validating Radarr:', error)
      statusMessage.textContent = 'Error validating Radarr'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      document.getElementById('radarr_validated').value = 'false'
    })
}

function toggleApiKeyVisibility () {
  const apiKeyInput = document.getElementById('radarr_token')
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
