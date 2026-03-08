/* global $, showSpinner, hideSpinner */

function refreshValidationCallout () {
  if (window.QSValidationCallouts && typeof window.QSValidationCallouts.refresh === 'function') {
    window.QSValidationCallouts.refresh('mal_validated')
  }
}

function setToggleButtonIcon (button, showPlainText) {
  if (!button) return
  const icon = document.createElement('i')
  icon.className = showPlainText ? 'fas fa-eye-slash' : 'fas fa-eye'
  button.replaceChildren(icon)
}

const validatedAtInput = document.getElementById('mal_validated_at')

$(document).ready(function () {
  const clientSecretInput = document.getElementById('mal_client_secret')
  const toggleButton = document.getElementById('toggleClientSecretVisibility')
  const validateButton = document.getElementById('validate_mal_url')
  const checkTokenButton = document.getElementById('mal_check_token')
  const isValidatedElement = document.getElementById('mal_validated')
  const isValidated = isValidatedElement ? isValidatedElement.value.toLowerCase() : 'false'
  console.log('Validated:', isValidated)

  // Ensure initial visibility based on input value
  if (clientSecretInput.value.trim() === '') {
    clientSecretInput.setAttribute('type', 'text') // Show placeholder text
    setToggleButtonIcon(toggleButton, true)
  } else {
    clientSecretInput.setAttribute('type', 'password') // Hide actual key
    setToggleButtonIcon(toggleButton, false)
  }

  // Disable validate button if already validated
  if (isValidated === 'true') {
    validateButton.disabled = true
  }
  if (checkTokenButton) {
    const accessToken = document.getElementById('access_token')?.value || ''
    checkTokenButton.disabled = !accessToken.trim()
  }

  // Reset validation status when user types
  const inputFields = ['mal_client_id', 'mal_client_secret', 'mal_code_verifier', 'mal_localhost_url']
  inputFields.forEach(field => {
    const inputElement = document.getElementById(field)
    if (inputElement) {
      inputElement.addEventListener('input', function () {
        isValidatedElement.value = 'false'
        if (validatedAtInput) validatedAtInput.value = ''
        validateButton.disabled = false
        if (checkTokenButton) checkTokenButton.disabled = true
        refreshValidationCallout()
      })
    } else {
      console.warn(`Warning: Element with ID '${field}' not found.`)
    }
  })
})

document.getElementById('toggleClientSecretVisibility').addEventListener('click', function () {
  const clientSecretInput = document.getElementById('mal_client_secret')
  const currentType = clientSecretInput.getAttribute('type')
  clientSecretInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  setToggleButtonIcon(this, currentType === 'password')
})

document.getElementById('mal_get_localhost_url').addEventListener('click', function () {
  const url = document.getElementById('mal_url').value
  if (url) {
    showSpinner('retrieve')
    window.open(url, '_blank').focus()
  }
})

/* eslint-disable no-unused-vars, camelcase */
function updateMALTargetURL () {
  const mal_client_id = document.getElementById('mal_client_id').value
  const code_verifier = document.getElementById('mal_code_verifier').value
  let myURL = ''
  if (mal_client_id.length === 32) {
    document.getElementById('mal_validated').value = 'false'
    const validatedAtInput = document.getElementById('mal_validated_at')
    if (validatedAtInput) validatedAtInput.value = ''
    refreshValidationCallout()
    myURL = 'https://myanimelist.net/v1/oauth2/authorize?response_type=code&client_id=' + mal_client_id + '&code_challenge=' + code_verifier
  }
  console.log('updateMALTargetURL: ' + myURL)
  document.getElementById('mal_url').value = myURL
  enableLocalURLButton()
}

function openMALUrl () {
  const url = document.getElementById('mal_url').value
  if (url) {
    window.open(url, '_blank').focus()
  }
}

function checkURLField () {
  const localURL = document.getElementById('mal_localhost_url').value
  const localURLButton = document.getElementById('validate_mal_url')
  localURLButton.disabled = (localURL === '')
}
/* eslint-enable no-unused-vars, camelcase */

function enableLocalURLButton () {
  const url = document.getElementById('mal_url').value
  const urlButton = document.getElementById('mal_get_localhost_url')
  urlButton.disabled = url === ''
}

/* eslint-disable camelcase */
window.onload = function () {
  const mal_url_text = document.getElementById('mal_url')
  document.getElementById('validate_mal_url').disabled = true
  document.getElementById('validate_mal_url').disabled = true
  enableLocalURLButton(mal_url_text)
}

document.getElementById('validate_mal_url').addEventListener('click', function () {
  const malClient = document.getElementById('mal_client_id').value
  const malSecret = document.getElementById('mal_client_secret').value
  const malVerifier = document.getElementById('mal_code_verifier').value
  const malLocalhostURL = document.getElementById('mal_localhost_url').value
  const statusMessage = document.getElementById('statusMessage')

  if (!malClient || !malSecret || !malVerifier || !malLocalhostURL) {
    statusMessage.textContent = 'ID, secret, and localhost URL are all required.'
    statusMessage.style.display = 'block'
    return
  }

  showSpinner('validate')
  hideSpinner('retrieve')

  fetch('/validate_mal', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      mal_client_id: malClient,
      mal_client_secret: malSecret,
      mal_code_verifier: malVerifier,
      mal_localhost_url: malLocalhostURL
    })
  })
    .then(response => response.json())
    .then(data => {
      if (data.valid) {
        hideSpinner('validate')
        document.getElementById('mal_validated').value = 'true'
        if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
        refreshValidationCallout()
        statusMessage.textContent = 'MyAnimeList credentials validated successfully!'
        statusMessage.style.color = '#75b798'
        document.getElementById('access_token').value = data.mal_authorization_access_token
        document.getElementById('token_type').value = data.mal_authorization_token_type
        document.getElementById('expires_in').value = data.mal_authorization_expires_in
        document.getElementById('refresh_token').value = data.mal_authorization_refresh_token
        document.getElementById('mal_get_localhost_url').disabled = true
        document.getElementById('validate_mal_url').disabled = true
        const tokenButton = document.getElementById('mal_check_token')
        if (tokenButton) tokenButton.disabled = false
      } else {
        hideSpinner('validate')
        document.getElementById('mal_validated').value = 'false'
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout()
        statusMessage.textContent = data.error
        statusMessage.style.color = '#ea868f'
      }
      statusMessage.style.display = 'block'
    })
    .catch(error => {
      hideSpinner('validate')
      console.error('Error validating MAL credentials:', error)
      statusMessage.textContent = 'An error occurred while validating MAL credentials.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout()
    })
})
/* eslint-enable camelcase */

const malCheckButton = document.getElementById('mal_check_token')
if (malCheckButton) {
  malCheckButton.addEventListener('click', function () {
    const accessToken = document.getElementById('access_token')?.value || ''
    const statusMessage = document.getElementById('statusMessage')

    if (!accessToken.trim()) {
      statusMessage.textContent = 'Missing access token.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      return
    }

    showSpinner('check_mal')
    fetch('/validate_mal_token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: accessToken, debug: true })
    })
      .then(res => res.json())
      .then(data => {
        hideSpinner('check_mal')
        if (data.valid) {
          document.getElementById('mal_validated').value = 'true'
          if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
          refreshValidationCallout()
          statusMessage.textContent = 'MyAnimeList token is valid.'
          statusMessage.style.color = '#75b798'
        } else {
          document.getElementById('mal_validated').value = 'false'
          if (validatedAtInput) validatedAtInput.value = ''
          refreshValidationCallout()
          statusMessage.textContent = data.error || 'MyAnimeList token is invalid.'
          statusMessage.style.color = '#ea868f'
        }
        statusMessage.style.display = 'block'
      })
      .catch(error => {
        hideSpinner('check_mal')
        console.error('Error validating MyAnimeList token:', error)
        statusMessage.textContent = 'An error occurred while validating MyAnimeList token.'
        statusMessage.style.color = '#ea868f'
        statusMessage.style.display = 'block'
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout()
      })
  })
}
