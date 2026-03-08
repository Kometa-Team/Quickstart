/* global $, showSpinner, hideSpinner */

function refreshValidationCallout () {
  if (window.QSValidationCallouts && typeof window.QSValidationCallouts.refresh === 'function') {
    window.QSValidationCallouts.refresh('github_validated')
  }
}

function setToggleButtonIcon (button, showPlainText) {
  if (!button) return
  const icon = document.createElement('i')
  icon.className = showPlainText ? 'fas fa-eye-slash' : 'fas fa-eye'
  button.replaceChildren(icon)
}

const validatedAtInput = document.getElementById('github_validated_at')

$(document).ready(function () {
  const apiKeyInput = document.getElementById('github_token')
  const validateButton = document.getElementById('validateButton')
  const toggleButton = document.getElementById('toggleApikeyVisibility')
  const isValidated = document.getElementById('github_validated').value.toLowerCase() === 'true'
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
  validateButton.disabled = isValidated

  // Reset validation status when user types
  apiKeyInput.addEventListener('input', function () {
    document.getElementById('github_validated').value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    validateButton.disabled = false
    refreshValidationCallout()
  })
})

document.getElementById('toggleApikeyVisibility').addEventListener('click', function () {
  const apikeyInput = document.getElementById('github_token')
  const currentType = apikeyInput.getAttribute('type')
  apikeyInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  setToggleButtonIcon(this, currentType === 'password')
})

document.getElementById('validateButton').addEventListener('click', function () {
  const apiKey = document.getElementById('github_token').value
  const statusMessage = document.getElementById('statusMessage')

  if (!apiKey) {
    statusMessage.textContent = 'Please enter a GitHub Personal Access Token.'
    statusMessage.style.color = '#ea868f'
    statusMessage.style.display = 'block'
    return
  }

  showSpinner('validate')

  fetch('/validate_github', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ github_token: apiKey })
  })
    .then(response => response.json())
    .then(data => {
      if (data.valid) {
        hideSpinner('validate')
        statusMessage.textContent = data.message
        statusMessage.style.color = '#75b798'
        document.getElementById('validateButton').disabled = true
        document.getElementById('github_validated').value = 'true'
        if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
        refreshValidationCallout()
      } else {
        statusMessage.textContent = data.message
        statusMessage.style.color = '#ea868f'
        document.getElementById('github_validated').value = 'false'
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout()
      }
      statusMessage.style.display = 'block'
    })
    .catch(error => {
      hideSpinner('validate')
      console.log(error)
      statusMessage.textContent = 'Error validating GitHub token.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      document.getElementById('github_validated').value = 'false'
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout()
    })
})

document.getElementById('configForm').addEventListener('submit', function () {
  const apiKeyInput = document.getElementById('github_token')
  if (!apiKeyInput.value) {
    apiKeyInput.value = ''
  }
})
