import { setToggleButtonIcon, refreshValidationCallout } from './modules/validationPageBase.js'

const validatedAtInput = document.getElementById('tautulli_validated_at')

const apiKeyInput = document.getElementById('tautulli_apikey')
const urlInput = document.getElementById('tautulli_url')
const validateButton = document.getElementById('validateButton')
const toggleButton = document.getElementById('toggleApikeyVisibility')
const isValidated = document.getElementById('tautulli_validated').value.toLowerCase()
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
  document.getElementById('tautulli_validated').value = 'false'
  if (validatedAtInput) validatedAtInput.value = ''
  validateButton.disabled = false
  refreshValidationCallout('tautulli_validated')
})

urlInput.addEventListener('input', function () {
  document.getElementById('tautulli_validated').value = 'false'
  if (validatedAtInput) validatedAtInput.value = ''
  validateButton.disabled = false
  refreshValidationCallout('tautulli_validated')
})

document.getElementById('toggleApikeyVisibility').addEventListener('click', function () {
  const apikeyInput = document.getElementById('tautulli_apikey')
  const currentType = apikeyInput.getAttribute('type')
  apikeyInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  setToggleButtonIcon(this, currentType === 'password')
})

// Tautulli validation script
document.getElementById('validateButton').addEventListener('click', function () {
  const tautulliUrl = document.getElementById('tautulli_url').value
  const tautulliApikey = document.getElementById('tautulli_apikey').value
  const statusMessage = document.getElementById('statusMessage')

  if (!tautulliUrl || !tautulliApikey) {
    statusMessage.textContent = 'Please enter both Tautulli URL and API Key.'
    statusMessage.style.display = 'block'
    return
  }
  showSpinner('validate')
  fetch('/validate_tautulli', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      tautulli_url: tautulliUrl,
      tautulli_apikey: tautulliApikey
    })
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.valid) {
        hideSpinner('validate')
        document.getElementById('tautulli_validated').value = 'true'
        if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
        refreshValidationCallout('tautulli_validated')
        statusMessage.textContent = 'Tautulli server validated successfully!'
        statusMessage.style.color = '#75b798'
        document.getElementById('validateButton').disabled = true
      } else {
        document.getElementById('tautulli_validated').value = 'false'
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout('tautulli_validated')
        statusMessage.textContent = 'Failed to validate Tautulli server. Please check your URL and API Key.'
        statusMessage.style.color = '#ea868f'
      }
      statusMessage.style.display = 'block'
    })
    .catch((error) => {
      console.error('Error validating Tautulli server:', error)
      statusMessage.textContent = 'An error occurred while validating Tautulli server.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout('tautulli_validated')
    })
    .finally(() => {
      hideSpinner('validate')
    })
})

document.getElementById('configForm').addEventListener('submit', function () {
  if (!apiKeyInput.value) {
    apiKeyInput.value = ''
  }
  if (!urlInput.value) {
    urlInput.value = ''
  }
})
