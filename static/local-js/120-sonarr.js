/* global $, initialSonarrRootFolderPath, initialSonarrQualityProfile, initialSonarrLanguageProfile, showSpinner, hideSpinner */

$(document).ready(function () {
  const isValidated = document.getElementById('sonarr_validated').value.toLowerCase()

  console.log('Validated: ' + isValidated)

  if (isValidated === 'true') {
    document.getElementById('validateButton').disabled = true
    // Populate the dropdowns with the stored data if they are available
    fetchDropdownData()
  } else {
    document.getElementById('validateButton').disabled = false
  }
})

document.addEventListener('DOMContentLoaded', function () {
  document.getElementById('validateButton').addEventListener('click', validateSonarrApi)
  document.getElementById('toggleApikeyVisibility').addEventListener('click', toggleApiKeyVisibility)
})

document.getElementById('sonarr_token').addEventListener('input', function () {
  document.getElementById('sonarr_validated').value = 'false'
  document.getElementById('validateButton').disabled = false
})

document.getElementById('sonarr_url').addEventListener('input', function () {
  document.getElementById('sonarr_validated').value = 'false'
  document.getElementById('validateButton').disabled = false
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
        console.log('Invalid Sonarr API key. Error:', data.message)
        statusMessage.textContent = 'Sonarr API key is invalid.'
        statusMessage.style.color = '#ea868f'
        statusMessage.style.display = 'block'
      }
    })
    .catch(error => {
      hideSpinner('validate')
      console.error('Error validating Sonarr API key:', error)
      statusMessage.textContent = 'Error validating Sonarr API key.'
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
