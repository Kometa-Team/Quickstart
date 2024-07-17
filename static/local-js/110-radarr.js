/* global $, validateButton, showSpinner, hideSpinner */

$(document).ready(function () {
  const isValidated = document.getElementById('radarr_validated').value.toLowerCase()

  console.log('Validated: ' + isValidated)

  if (isValidated === 'true') {
    document.getElementById('validateButton').disabled = true
  } else {
    document.getElementById('validateButton').disabled = false
  }
})

document.addEventListener('DOMContentLoaded', function () {
  document.getElementById('validateButton').addEventListener('click', validateRadarrApi)
  document.getElementById('toggleApikeyVisibility').addEventListener('click', toggleApiKeyVisibility)
})

document.getElementById('radarr_token').addEventListener('input', function () {
  document.getElementById('radarr_validated').value = 'false'
  validateButton.disabled = false
})

document.getElementById('radarr_url').addEventListener('input', function () {
  document.getElementById('radarr_validated').value = 'false'
  validateButton.disabled = false
})

/* eslint-disable camelcase */
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
      if (data.valid) {
        hideSpinner('validate')
        document.getElementById('radarr_validated').value = 'true'
        statusMessage.textContent = 'Radarr API key is valid.'
        statusMessage.style.color = '#75b798'
        statusMessage.style.display = 'block'
        document.getElementById('validateButton').disabled = true

        populateDropdown('radarr_root_folder_path', data.root_folders, 'path', 'path')
        populateDropdown('radarr_quality_profile', data.quality_profiles, 'name', 'name')
      } else {
        hideSpinner('validate')
        document.getElementById('radarr_validated').value = 'false'
        console.log('Invalid Radarr API key. Error:', data.message)
        statusMessage.textContent = 'Radarr API key is invalid.'
        statusMessage.style.color = '#ea868f'
        statusMessage.style.display = 'block'
      }
    })
    .catch(error => {
      hideSpinner('validate')
      console.error('Error validating Radarr API key:', error)
      statusMessage.textContent = 'Error validating Radarr API key.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      document.getElementById('radarr_validated').value = 'false'
    })
}
/* eslint-enable camelcase */

function populateDropdown (elementId, data, valueField, textField) {
  const dropdown = document.getElementById(elementId)
  dropdown.innerHTML = '<option value="">Select an option</option>'

  data.forEach(item => {
    const option = document.createElement('option')
    option.value = item[valueField]
    option.textContent = item[textField]
    dropdown.appendChild(option)
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
