/* global $, showSpinner, hideSpinner */

$(document).ready(function () {
  const isValidated = document.getElementById('omdb_validated').value.toLowerCase()
  const validateButton = document.getElementById('validateButton')

  console.log('Validated: ' + isValidated)

  if (isValidated === 'true') {
    validateButton.disabled = true
  } else {
    validateButton.disabled = false
  }

  document.getElementById('omdb_apikey').addEventListener('input', function () {
    document.getElementById('omdb_validated').value = 'false'
    validateButton.disabled = false
  })
})

document.getElementById('toggleApikeyVisibility').addEventListener('click', function () {
  const apikeyInput = document.getElementById('omdb_apikey')
  const currentType = apikeyInput.getAttribute('type')
  apikeyInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  this.innerHTML = currentType === 'password' ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>'
})

document.getElementById('validateButton').addEventListener('click', function () {
  const apiKey = document.getElementById('omdb_apikey').value
  const statusMessage = document.getElementById('statusMessage')

  if (!apiKey) {
    statusMessage.textContent = 'Please enter an OMDb API key.'
    statusMessage.style.color = '#ea868f'
    statusMessage.style.display = 'block'
    return
  }

  showSpinner('validate')

  fetch('/validate_omdb', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ omdb_apikey: apiKey })
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.valid) {
        hideSpinner('validate')
        document.getElementById('omdb_validated').value = 'true'
        statusMessage.textContent = 'OMDb API key is valid.'
        statusMessage.style.color = '#75b798'
        document.getElementById('validateButton').disabled = true
      } else {
        hideSpinner('validate')
        statusMessage.textContent = 'OMDb API key is invalid.'
        statusMessage.style.color = '#ea868f'
      }
      statusMessage.style.display = 'block'
    })
    .catch(error => {
      hideSpinner('validate')
      console.error('Error validating OMDb server:', error)
      statusMessage.textContent = 'Error validating OMDb API key.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      document.getElementById('omdb_validated').value = 'false'
    })
})

document.getElementById('configForm').addEventListener('submit', function (event) {
  const apiKeyInput = document.getElementById('omdb_apikey')
  const cacheExpiration = document.getElementById('omdb_cache_expiration')
  if (!apiKeyInput.value) {
    apiKeyInput.value = ''
    cacheExpiration.value = '1'
  }
})
