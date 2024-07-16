/* global $, showSpinner, hideSpinner */

$(document).ready(function () {
  const isValidated = document.getElementById('tmdb_validated').value.toLowerCase()
  const validateButton = document.getElementById('validateButton')

  console.log('Validated: ' + isValidated)

  if (isValidated === 'true') {
    validateButton.disabled = true
  } else {
    validateButton.disabled = false
  }

  document.getElementById('tmdb_apikey').addEventListener('input', function () {
    document.getElementById('tmdb_validated').value = 'false'
    validateButton.disabled = false
  })

  document.getElementById('validateButton').addEventListener('click', function () {
    const apiKey = document.getElementById('tmdb_apikey').value
    const statusMessage = document.getElementById('statusMessage')

    if (!apiKey) {
      statusMessage.textContent = 'Please enter an API key.'
      statusMessage.style.display = 'block'
      return
    }

    showSpinner('validate')

    fetch('/validate_tmdb', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ tmdb_apikey: apiKey })
    })
      .then(response => response.json())
      .then(data => {
        if (data.valid) {
          console.log('valid')
          hideSpinner('validate')
          document.getElementById('tmdb_validated').value = 'true'
          statusMessage.textContent = 'API key is valid!'
          statusMessage.style.color = '#75b798'
          document.getElementById('validateButton').disabled = true
        } else {
          console.log('NOT valid')
          document.getElementById('tmdb_validated').value = 'false'
          statusMessage.textContent = 'Failed to validate Tautulli server. Please check your URL and API Key.'
          statusMessage.style.color = '#ea868f'
        }
        statusMessage.style.display = 'block'
      })
      .catch(error => {
        console.error('Error validating TMDb server:', error)
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
    const apikeyInput = document.getElementById('tmdb_apikey')
    const currentType = apikeyInput.getAttribute('type')
    apikeyInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
    this.innerHTML = currentType === 'password' ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>'
  })
})
