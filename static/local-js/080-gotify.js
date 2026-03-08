/* global $, showSpinner, hideSpinner */

function refreshValidationCallout () {
  if (window.QSValidationCallouts && typeof window.QSValidationCallouts.refresh === 'function') {
    window.QSValidationCallouts.refresh('gotify_validated')
  }
}

function setToggleButtonIcon (button, showPlainText) {
  if (!button) return
  const icon = document.createElement('i')
  icon.className = showPlainText ? 'fas fa-eye-slash' : 'fas fa-eye'
  button.replaceChildren(icon)
}

const validatedAtInput = document.getElementById('gotify_validated_at')

$(document).ready(function () {
  const gotifyTokenInput = document.getElementById('gotify_token')
  const validateButton = document.getElementById('validateButton')
  const toggleButton = document.getElementById('toggleTokenVisibility')
  const isValidated = document.getElementById('gotify_validated').value.toLowerCase()

  console.log('Validated: ' + isValidated)

  // Set initial visibility based on API key value
  if (gotifyTokenInput.value.trim() === '') {
    gotifyTokenInput.setAttribute('type', 'text') // Show placeholder text
    setToggleButtonIcon(toggleButton, true)
  } else {
    gotifyTokenInput.setAttribute('type', 'password') // Hide actual key
    setToggleButtonIcon(toggleButton, false)
  }

  // Disable validate button if already validated
  validateButton.disabled = isValidated === 'true'

  // Reset validation status when user types
  gotifyTokenInput.addEventListener('input', function () {
    document.getElementById('gotify_validated').value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    validateButton.disabled = false
    refreshValidationCallout()
  })

  document.getElementById('gotify_url').addEventListener('input', function () {
    document.getElementById('gotify_validated').value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    validateButton.disabled = false
    refreshValidationCallout()
  })
})

// Function to toggle API key visibility
document.getElementById('toggleTokenVisibility').addEventListener('click', function () {
  const tokenInput = document.getElementById('gotify_token')
  const currentType = tokenInput.getAttribute('type')
  tokenInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  setToggleButtonIcon(this, currentType === 'password')
})

/* eslint-disable camelcase */
// Event listener for the validate button
document.getElementById('validateButton').addEventListener('click', function () {
  const gotify_url = document.getElementById('gotify_url').value
  const gotify_token = document.getElementById('gotify_token').value
  const statusMessage = document.getElementById('statusMessage')

  if (!gotify_url || !gotify_token) {
    statusMessage.textContent = 'Please enter both Gotify URL and Token.'
    statusMessage.style.color = '#ea868f'
    statusMessage.style.display = 'block'
    return
  }

  showSpinner('validate')

  fetch('/validate_gotify', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      gotify_url,
      gotify_token
    })
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.valid) {
        hideSpinner('validate')
        document.getElementById('gotify_validated').value = 'true'
        if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
        refreshValidationCallout()
        statusMessage.textContent = 'Gotify credentials validated successfully!'
        statusMessage.style.color = '#75b798'
      } else {
        hideSpinner('validate')
        document.getElementById('gotify_validated').value = 'false'
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout()
        statusMessage.textContent = data.error
        statusMessage.style.color = '#ea868f'
      }
      document.getElementById('validateButton').disabled = data.valid
      statusMessage.style.display = 'block'
    })
    .catch((error) => {
      hideSpinner('validate')
      console.error('Error validating Gotify credentials:', error)
      statusMessage.textContent = 'An error occurred while validating Gotify credentials.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout()
    })
})
/* eslint-enable camelcase */
