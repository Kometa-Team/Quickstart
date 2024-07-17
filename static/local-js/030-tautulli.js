/* global $, showSpinner, hideSpinner */

$(document).ready(function () {
  const isValidated = document.getElementById('tautulli_validated').value.toLowerCase()
  const validateButton = document.getElementById('validateButton')

  console.log('Validated: ' + isValidated)

  if (isValidated === 'true') {
    validateButton.disabled = true
  } else {
    validateButton.disabled = false
  }

  document.getElementById('tautulli_apikey').addEventListener('input', function () {
    document.getElementById('tautulli_validated').value = 'false'
    validateButton.disabled = false
  })

  document.getElementById('tautulli_url').addEventListener('input', function () {
    document.getElementById('tautulli_validated').value = 'false'
    validateButton.disabled = false
  })
})

document.getElementById('toggleApikeyVisibility').addEventListener('click', function () {
  const apikeyInput = document.getElementById('tautulli_apikey')
  const currentType = apikeyInput.getAttribute('type')
  apikeyInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  this.innerHTML = currentType === 'password' ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>'
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
        statusMessage.textContent = 'Tautulli server validated successfully!'
        statusMessage.style.color = '#75b798'
        document.getElementById('validateButton').disabled = true
      } else {
        document.getElementById('tautulli_validated').value = 'false'
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
    })
    .finally(() => {
      hideSpinner('validate')
    })
})

document.getElementById('configForm').addEventListener('submit', function (event) {
  const apiKeyInput = document.getElementById('tautulli_apikey')
  const urlInput = document.getElementById('tautulli_url')
  if (!apiKeyInput.value) {
    apiKeyInput.value = ''
  }
  if (!urlInput.value) {
    urlInput.value = 'http://'
  }
})
