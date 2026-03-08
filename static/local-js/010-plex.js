/* global $, validateButton, showSpinner, hideSpinner */

function refreshValidationCallout () {
  if (window.QSValidationCallouts && typeof window.QSValidationCallouts.refresh === 'function') {
    window.QSValidationCallouts.refresh('plex_validated')
  }
}

function setToggleButtonIcon (button, showPlainText) {
  if (!button) return
  const icon = document.createElement('i')
  icon.className = showPlainText ? 'fas fa-eye-slash' : 'fas fa-eye'
  button.replaceChildren(icon)
}

$(document).ready(function () {
  const validateButton = document.getElementById('validateButton')
  const isValidated = document.getElementById('plex_validated').value.toLowerCase()
  const validatedAtInput = document.getElementById('plex_validated_at')
  const hiddenSection = document.getElementById('hidden')
  const plexDbCache = document.getElementById('plexDbCache')
  const plexTokenInput = document.getElementById('plex_token')
  const plexUrlInput = document.getElementById('plex_url')
  const toggleButton = document.getElementById('toggleApikeyVisibility')

  validateButton.disabled = (isValidated === 'true')

  console.log('Validated: ' + isValidated)

  if (isValidated === 'true') {
    hiddenSection.style.display = 'block'
    plexDbCache.style.display = 'block'
  }

  // Set initial visibility based on token value
  if (plexTokenInput.value.trim() === '') {
    plexTokenInput.setAttribute('type', 'text') // Show placeholder text
    setToggleButtonIcon(toggleButton, true)
  } else {
    plexTokenInput.setAttribute('type', 'password') // Hide actual token
    setToggleButtonIcon(toggleButton, false)
  }

  // Enable validate button and reset validation when token or URL changes
  plexTokenInput.addEventListener('input', function () {
    validateButton.disabled = false
    document.getElementById('plex_validated').value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    refreshValidationCallout()
  })

  plexUrlInput.addEventListener('input', function () {
    validateButton.disabled = false
    document.getElementById('plex_validated').value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    refreshValidationCallout()
  })
})

// Toggle password visibility
document.getElementById('toggleApikeyVisibility').addEventListener('click', function () {
  const apikeyInput = document.getElementById('plex_token')
  const currentType = apikeyInput.getAttribute('type')
  apikeyInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  setToggleButtonIcon(this, currentType === 'password')
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
  const validatedAtInput = document.getElementById('plex_validated_at')
  if (validatedAtInput) validatedAtInput.value = ''
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
      const passSuccess = document.getElementById('plex-pass-status-success')
      const passWarning = document.getElementById('plex-pass-status-warning')

      console.log('has_plex_pass:', data.has_plex_pass)
      console.log('success div:', passSuccess)
      console.log('warning div:', passWarning)

      if (data.has_plex_pass) {
        passSuccess.classList.remove('d-none')
        passSuccess.style.display = 'block'

        passWarning.classList.add('d-none')
        passWarning.style.display = 'none'
      } else {
        passSuccess.classList.add('d-none')
        passSuccess.style.display = 'none'

        passWarning.classList.remove('d-none')
        passWarning.style.display = 'block'
      }

      if (data.validated) {
        hideSpinner('validate')
        validateButton.disabled = true
        const serverDbCache = data.db_cache
        plexDbCache.textContent = 'Database cache value retrieved from server is: ' + serverDbCache + ' MB'
        plexDbCache.style.color = '#75b798'

        document.getElementById('plex_validated').value = 'true'
        if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
        refreshValidationCallout()

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
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout()
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
      const validatedAtInput = document.getElementById('plex_validated_at')
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout()
    })
})
