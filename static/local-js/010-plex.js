/* global $, validateButton, showSpinner, hideSpinner */

$(document).ready(function () {
  const validateButton = document.getElementById('validateButton')
  const isValidated = document.getElementById('plex_validated').value.toLowerCase()
  const hiddenSection = document.getElementById('hidden')
  const plexDbCache = document.getElementById('plexDbCache')

  validateButton.disabled = (isValidated === 'true')

  console.log('Validated: ' + isValidated)

  if (isValidated === 'true') {
    hiddenSection.style.display = 'block'
    plexDbCache.style.display = 'block'
  }

  // Enable the validate button and set plex_validated to false if the Plex token or URL is changed
  const plexTokenInput = document.getElementById('plex_token')
  const plexUrlInput = document.getElementById('plex_url')

  plexTokenInput.addEventListener('input', function () {
    validateButton.disabled = false
    document.getElementById('plex_validated').value = 'false'
  })

  plexUrlInput.addEventListener('input', function () {
    validateButton.disabled = false
    document.getElementById('plex_validated').value = 'false'
  })
})

document.getElementById('toggleApikeyVisibility').addEventListener('click', function () {
  const apikeyInput = document.getElementById('plex_token')
  const currentType = apikeyInput.getAttribute('type')
  apikeyInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  this.innerHTML = currentType === 'password' ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>'
})

// Plex validation script
document.getElementById('validateButton').addEventListener('click', function () {
  const plexUrl = document.getElementById('plex_url').value
  const plexToken = document.getElementById('plex_token').value
  const statusMessage = document.getElementById('statusMessage')
  const plexDbCache = document.getElementById('plexDbCache')
  const currentDbCache = document.getElementById('plex_db_cache').value

  if (!plexUrl || !plexToken) {
    statusMessage.textContent = 'Please enter both Plex URL and Token.'
    statusMessage.style.display = 'block'
    return
  }

  document.getElementById('plex_validated').value = ''
  showSpinner('validate')
  validateButton.disabled = true

  fetch('/validate_plex', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ plex_url: plexUrl, plex_token: plexToken })
  })
    .then(response => response.json())
    .then(data => {
      if (data.validated) {
        hideSpinner('validate')
        validateButton.disabled = true
        const serverDbCache = data.db_cache
        plexDbCache.textContent = 'Database cache value retrieved from server is: ' + serverDbCache + ' MB'
        plexDbCache.style.color = '#75b798'

        document.getElementById('plex_validated').value = 'true'

        statusMessage.textContent = 'Plex server validated successfully!'
        statusMessage.style.color = '#75b798'
        const hiddenSection = document.getElementById('hidden')
        hiddenSection.style.display = 'block'

        if (Number(currentDbCache) !== serverDbCache) {
          plexDbCache.textContent += '.\nWarning: The value in the input box (' + currentDbCache + ' MB) does not match the value retrieved from the server (' + serverDbCache + ' MB).'
          plexDbCache.style.color = '#ea868f'
        }

        // Update the input field to match the server's db_cache value
        document.getElementById('plex_db_cache').value = serverDbCache
        document.getElementById('tmp_user_list').value = data.user_list
        document.getElementById('tmp_music_libraries').value = data.music_libraries
        document.getElementById('tmp_movie_libraries').value = data.movie_libraries
        document.getElementById('tmp_show_libraries').value = data.show_libraries
      } else {
        hideSpinner('validate')
        validateButton.disabled = false
        document.getElementById('plex_validated').value = false
        statusMessage.textContent = 'Failed to validate Plex server. Please check your URL and Token.'
        statusMessage.style.color = '#ea868f'
      }
      statusMessage.style.display = 'block'
    })
    .catch(error => {
      hideSpinner('validate')
      console.error('Error:', error)
      validateButton.disabled = false
      statusMessage.textContent = 'Error occurred during validation.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
    })
})
