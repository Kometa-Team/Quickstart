/* global $, showSpinner, hideSpinner */

function refreshValidationCallout () {
  if (window.QSValidationCallouts && typeof window.QSValidationCallouts.refresh === 'function') {
    window.QSValidationCallouts.refresh('mdblist_validated')
  }
}

function setToggleButtonIcon (button, showPlainText) {
  if (!button) return
  const icon = document.createElement('i')
  icon.className = showPlainText ? 'fas fa-eye-slash' : 'fas fa-eye'
  button.replaceChildren(icon)
}

$(document).ready(function () {
  const apiKeyInput = document.getElementById('mdblist_apikey')
  const validateButton = document.getElementById('validateButton')
  const toggleButton = document.getElementById('toggleApikeyVisibility')
  const isValidated = document.getElementById('mdblist_validated').value.toLowerCase()
  const validatedAtInput = document.getElementById('mdblist_validated_at')

  console.log('Validated: ' + isValidated)

  // Set initial visibility based on API key value
  if (apiKeyInput.value.trim() === '') {
    apiKeyInput.setAttribute('type', 'text') // Show placeholder text
    setToggleButtonIcon(toggleButton, true)
  } else {
    apiKeyInput.setAttribute('type', 'password') // Hide actual key
    setToggleButtonIcon(toggleButton, false)
  }

  // Disable validate button if already validated
  validateButton.disabled = isValidated === 'true'

  // Reset validation status when user types
  apiKeyInput.addEventListener('input', function () {
    document.getElementById('mdblist_validated').value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    validateButton.disabled = false
    refreshValidationCallout()
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
          if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
          refreshValidationCallout()
          statusMessage.textContent = 'API key is valid!'
          statusMessage.style.color = '#75b798'
          validateButton.disabled = true
        } else {
          console.log('NOT valid')
          document.getElementById('mdblist_validated').value = 'false'
          if (validatedAtInput) validatedAtInput.value = ''
          refreshValidationCallout()
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
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout()
      })
      .finally(() => {
        hideSpinner('validate')
        statusMessage.style.display = 'block'
      })
  })

  document.getElementById('toggleApikeyVisibility').addEventListener('click', function () {
    const currentType = apiKeyInput.getAttribute('type')
    apiKeyInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
    setToggleButtonIcon(this, currentType === 'password')
  })
})

document.getElementById('configForm').addEventListener('submit', function () {
  const apiKeyInput = document.getElementById('mdblist_apikey')
  if (!apiKeyInput.value) {
    apiKeyInput.value = ''
  }
})
