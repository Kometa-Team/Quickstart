/* global $, showSpinner, hideSpinner */

$(document).ready(function () {
  const apiKeyInput = document.getElementById('mdblist_apikey')
  const validateButton = document.getElementById('validateButton')
  const toggleButton = document.getElementById('toggleApikeyVisibility')
  const isValidated = document.getElementById('mdblist_validated').value.toLowerCase()

  console.log('Validated: ' + isValidated)

  // Set initial visibility based on API key value
  if (apiKeyInput.value.trim() === '') {
    apiKeyInput.setAttribute('type', 'text') // Show placeholder text
    toggleButton.innerHTML = '<i class="fas fa-eye-slash"></i>' // Ensure eye-slash icon
  } else {
    apiKeyInput.setAttribute('type', 'password') // Hide actual key
    toggleButton.innerHTML = '<i class="fas fa-eye"></i>' // Ensure eye icon
  }

  // Disable validate button if already validated
  validateButton.disabled = isValidated === 'true'

  // Reset validation status when user types
  apiKeyInput.addEventListener('input', function () {
    document.getElementById('mdblist_validated').value = 'false'
    validateButton.disabled = false
  })

  document.getElementById('validateButton').addEventListener('click', function () {
    const apiKey = apiKeyInput.value
    const statusMessage = document.getElementById('statusMessage')

    if (!apiKey) {
      statusMessage.textContent = 'Please enter an API key.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      return
    }

    showSpinner('validate')

    fetch('/validate_mdblist', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ mdblist_apikey: apiKey })
    })
      .then(response => response.json())
      .then(data => {
        if (data.valid) {
          console.log('valid')
          hideSpinner('validate')
          document.getElementById('mdblist_validated').value = 'true'
          statusMessage.textContent = 'API key is valid!'
          statusMessage.style.color = '#75b798'
          validateButton.disabled = true
        } else {
          console.log('NOT valid')
          document.getElementById('mdblist_validated').value = 'false'
          statusMessage.textContent = 'Failed to validate MDBList server. Please check your API Key.'
          statusMessage.style.color = '#ea868f'
        }
        statusMessage.style.display = 'block'
      })
      .catch(error => {
        console.error('Error validating MDBList server:', error)
        statusMessage.textContent = 'An error occurred. Please try again.'
        statusMessage.style.color = '#ea868f'
        statusMessage.style.display = 'block'
      })
      .finally(() => {
        hideSpinner('validate')
        statusMessage.style.display = 'block'
      })
  })

  document.getElementById('toggleApikeyVisibility').addEventListener('click', function () {
    const currentType = apiKeyInput.getAttribute('type')
    apiKeyInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
    this.innerHTML = currentType === 'password' ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>'
  })
})

document.getElementById('configForm').addEventListener('submit', function () {
  const apiKeyInput = document.getElementById('mdblist_apikey')
  const cacheExpiration = document.getElementById('mdblist_cache_expiration')
  if (!apiKeyInput.value) {
    apiKeyInput.value = ''
    cacheExpiration.value = '1'
  }
})
