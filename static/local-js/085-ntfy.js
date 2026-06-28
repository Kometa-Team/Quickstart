import { setToggleButtonIcon, refreshValidationCallout } from './modules/validationPageBase.js'

const validatedAtInput = document.getElementById('ntfy_validated_at')

const tokenInput = document.getElementById('ntfy_token')
const toggleButton = document.getElementById('toggleTokenVisibility')
const isValidated = document.getElementById('ntfy_validated').value.toLowerCase()
const validateButton = document.getElementById('validateButton')

console.log('Validated: ' + isValidated)

// Set initial visibility based on API key value
if (tokenInput.value.trim() === '') {
  tokenInput.setAttribute('type', 'text') // Show placeholder text
  setToggleButtonIcon(toggleButton, true)
} else {
  tokenInput.setAttribute('type', 'password') // Hide actual key
  setToggleButtonIcon(toggleButton, false)
}

if (isValidated === 'true') {
  validateButton.disabled = true
} else {
  validateButton.disabled = false
}

tokenInput.addEventListener('input', function () {
  document.getElementById('ntfy_validated').value = 'false'
  if (validatedAtInput) validatedAtInput.value = ''
  validateButton.disabled = false
  refreshValidationCallout('ntfy_validated')
})

document.getElementById('ntfy_url').addEventListener('input', function () {
  document.getElementById('ntfy_validated').value = 'false'
  if (validatedAtInput) validatedAtInput.value = ''
  validateButton.disabled = false
  refreshValidationCallout('ntfy_validated')
})

document.getElementById('ntfy_topic').addEventListener('input', function () {
  document.getElementById('ntfy_validated').value = 'false'
  if (validatedAtInput) validatedAtInput.value = ''
  validateButton.disabled = false
  refreshValidationCallout('ntfy_validated')
})

// Function to toggle API key visibility
document.getElementById('toggleTokenVisibility').addEventListener('click', function () {
  const currentType = tokenInput.getAttribute('type')
  tokenInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  setToggleButtonIcon(this, currentType === 'password')
})

// Event listener for the validate button
document.getElementById('validateButton').addEventListener('click', function () {
  const ntfyUrl = document.getElementById('ntfy_url').value
  const ntfyToken = document.getElementById('ntfy_token').value
  const ntfyTopic = document.getElementById('ntfy_topic').value
  const statusMessage = document.getElementById('statusMessage')

  if (!ntfyUrl || !ntfyToken || !ntfyTopic) {
    statusMessage.textContent = 'Please enter ntfy URL, Token and Topic.'
    statusMessage.style.color = '#ea868f'
    statusMessage.style.display = 'block'
    return
  }

  showSpinner('validate')

  fetch('/validate_ntfy', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      ntfy_url: ntfyUrl,
      ntfy_token: ntfyToken,
      ntfy_topic: ntfyTopic
    })
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.valid) {
        hideSpinner('validate')
        document.getElementById('ntfy_validated').value = 'true'
        if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
        refreshValidationCallout('ntfy_validated')
        statusMessage.textContent = 'ntfy credentials validated successfully! Ensure you are subscribed to topic to see test message.'
        statusMessage.style.color = '#75b798'
      } else {
        hideSpinner('validate')
        document.getElementById('ntfy_validated').value = 'false'
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout('ntfy_validated')
        statusMessage.textContent = data.error
        statusMessage.style.color = '#ea868f'
      }
      document.getElementById('validateButton').disabled = data.valid
      statusMessage.style.display = 'block'
    })
    .catch((error) => {
      hideSpinner('validate')
      console.error('Error validating ntfy credentials:', error)
      statusMessage.textContent = 'An error occurred while validating ntfy credentials.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout('ntfy_validated')
    })
})
