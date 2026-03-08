/* global $, showSpinner, hideSpinner */

function refreshValidationCallout () {
  if (window.QSValidationCallouts && typeof window.QSValidationCallouts.refresh === 'function') {
    window.QSValidationCallouts.refresh('trakt_validated')
  }
}

function setToggleButtonIcon (button, showPlainText) {
  if (!button) return
  const icon = document.createElement('i')
  icon.className = showPlainText ? 'fas fa-eye-slash' : 'fas fa-eye'
  button.replaceChildren(icon)
}

const validatedAtInput = document.getElementById('trakt_validated_at')

$(document).ready(function () {
  const traktClientSecretInput = document.getElementById('trakt_client_secret')
  const toggleButton = document.getElementById('toggleClientSecretVisibility')
  const validateButton = document.getElementById('validate_trakt_pin')
  const checkTokenButton = document.getElementById('trakt_check_token')
  const isValidatedElement = document.getElementById('trakt_validated')
  const isValidated = isValidatedElement.value.toLowerCase()
  console.log('Validated:', isValidated)
  const isBlankTokenValue = (value) => {
    if (!value) return true
    const trimmed = value.trim()
    if (!trimmed) return true
    return trimmed.toLowerCase() === 'none' || trimmed.toLowerCase() === 'null'
  }

  // Set initial visibility based on Client Secret value
  if (traktClientSecretInput.value.trim() === '') {
    traktClientSecretInput.setAttribute('type', 'text') // Show placeholder text
    setToggleButtonIcon(toggleButton, true)
  } else {
    traktClientSecretInput.setAttribute('type', 'password') // Hide actual secret
    setToggleButtonIcon(toggleButton, false)
  }

  // Disable validate button if already validated
  validateButton.disabled = isValidated === 'true'
  if (checkTokenButton) {
    const accessToken = document.getElementById('access_token')?.value || ''
    checkTokenButton.disabled = isBlankTokenValue(accessToken)
  }

  // Reset validation status when user types
  const inputFields = ['trakt_client_id', 'trakt_client_secret', 'trakt_pin']
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
  const traktClientSecretInput = document.getElementById('trakt_client_secret')
  const currentType = traktClientSecretInput.getAttribute('type')
  traktClientSecretInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  setToggleButtonIcon(this, currentType === 'password')
})

/* eslint-disable no-unused-vars, camelcase */
function updateTraktURL () {
  const trakt_client_id = document.getElementById('trakt_client_id').value
  let myURL = ''
  if (trakt_client_id.length === 64) {
    document.getElementById('trakt_validated').value = 'false'
    const validatedAtInput = document.getElementById('trakt_validated_at')
    if (validatedAtInput) validatedAtInput.value = ''
    refreshValidationCallout()
    myURL = 'https://trakt.tv/oauth/authorize?response_type=code&client_id=' + trakt_client_id + '&redirect_uri=urn:ietf:wg:oauth:2.0:oob'
  }
  console.log('updateTraktURL: ' + myURL)
  document.getElementById('trakt_url').value = myURL
  checkURLStart()
}
/* eslint-enable camelcase */

function openTraktUrl () {
  const url = document.getElementById('trakt_url').value
  if (url) {
    showSpinner('retrieve')
    window.open(url, '_blank').focus()
  }
}

function checkPinField () {
  const pin = document.getElementById('trakt_pin').value
  const pinButton = document.getElementById('validate_trakt_pin')
  pinButton.disabled = (pin === '')
}
/* eslint-enable no-unused-vars */

function checkURLStart () {
  const url = document.getElementById('trakt_url').value
  const urlButton = document.getElementById('trakt_open_url')
  urlButton.disabled = url === ''
}

/* eslint-disable camelcase */
window.onload = function () {
  const trakt_url_text = document.getElementById('trakt_url')
  document.getElementById('trakt_open_url').disabled = true
  document.getElementById('validate_trakt_pin').disabled = true
  checkURLStart(trakt_url_text)
}
/* eslint-enable camelcase */

// Plex validation script
document.getElementById('validate_trakt_pin').addEventListener('click', function () {
  const traktClient = document.getElementById('trakt_client_id').value
  const traktSecret = document.getElementById('trakt_client_secret').value
  const traktPin = document.getElementById('trakt_pin').value
  const statusMessage = document.getElementById('statusMessage')

  if (!traktClient || !traktSecret || !traktPin) {
    statusMessage.textContent = 'ID, secret, and PIN are all required.'
    statusMessage.style.display = 'block'
    return
  }

  showSpinner('validate')
  hideSpinner('retrieve')

  fetch('/validate_trakt', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      trakt_client_id: traktClient,
      trakt_client_secret: traktSecret,
      trakt_pin: traktPin
    })
  })
    .then(response => response.json())
    .then(data => {
      if (data.valid) {
        hideSpinner('validate')
        document.getElementById('trakt_validated').value = 'true'
        if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
        refreshValidationCallout()
        statusMessage.textContent = 'Trakt credentials validated successfully!'
        statusMessage.style.color = '#75b798'
        document.getElementById('access_token').value = data.trakt_authorization_access_token
        document.getElementById('token_type').value = data.trakt_authorization_token_type
        document.getElementById('expires_in').value = data.trakt_authorization_expires_in
        document.getElementById('refresh_token').value = data.trakt_authorization_refresh_token
        document.getElementById('scope').value = data.trakt_authorization_scope
        document.getElementById('created_at').value = data.trakt_authorization_created_at
        document.getElementById('trakt_pin').value = ''
        document.getElementById('trakt_url').value = ''
        document.getElementById('trakt_open_url').disabled = true
        document.getElementById('validate_trakt_pin').disabled = true
        const tokenButton = document.getElementById('trakt_check_token')
        if (tokenButton) tokenButton.disabled = false
      } else {
        hideSpinner('validate')
        document.getElementById('trakt_validated').value = 'false'
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout()
        statusMessage.textContent = data.error
        statusMessage.style.color = '#ea868f'
      }
      statusMessage.style.display = 'block'
    })
    .catch(error => {
      hideSpinner('validate')
      console.error('Error validating Trakt credentials:', error)
      statusMessage.textContent = 'An error occurred while validating Trakt credentials.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout()
    })
})

const traktCheckButton = document.getElementById('trakt_check_token')
if (traktCheckButton) {
  traktCheckButton.addEventListener('click', function () {
    const accessToken = document.getElementById('access_token')?.value || ''
    const clientId = document.getElementById('trakt_client_id')?.value || ''
    const statusMessage = document.getElementById('statusMessage')

    const isBlankValue = (value) => {
      if (!value) return true
      const trimmed = value.trim()
      if (!trimmed) return true
      return trimmed.toLowerCase() === 'none' || trimmed.toLowerCase() === 'null'
    }

    if (isBlankValue(accessToken) || isBlankValue(clientId)) {
      statusMessage.textContent = 'Missing access token or client ID.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      return
    }

    const clientSecret = document.getElementById('trakt_client_secret')?.value || ''
    const refreshToken = document.getElementById('refresh_token')?.value || ''
    showSpinner('check_trakt')
    fetch('/validate_trakt_token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        access_token: accessToken,
        client_id: clientId,
        client_secret: clientSecret,
        refresh_token: refreshToken,
        debug: true
      })
    })
      .then(res => res.json())
      .then(data => {
        hideSpinner('check_trakt')
        if (data.valid) {
          if (data.authorization) {
            if (data.authorization.access_token) document.getElementById('access_token').value = data.authorization.access_token
            if (data.authorization.token_type) document.getElementById('token_type').value = data.authorization.token_type
            if (data.authorization.expires_in) document.getElementById('expires_in').value = data.authorization.expires_in
            if (data.authorization.refresh_token) document.getElementById('refresh_token').value = data.authorization.refresh_token
            if (data.authorization.scope) document.getElementById('scope').value = data.authorization.scope
            if (data.authorization.created_at) document.getElementById('created_at').value = data.authorization.created_at
          }
          document.getElementById('trakt_validated').value = 'true'
          if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
          refreshValidationCallout()
          statusMessage.textContent = 'Trakt token is valid.'
          statusMessage.style.color = '#75b798'
        } else {
          document.getElementById('trakt_validated').value = 'false'
          if (validatedAtInput) validatedAtInput.value = ''
          refreshValidationCallout()
          statusMessage.textContent = data.error || 'Trakt token is invalid.'
          statusMessage.style.color = '#ea868f'
        }
        statusMessage.style.display = 'block'
      })
      .catch(error => {
        hideSpinner('check_trakt')
        console.error('Error validating Trakt token:', error)
        statusMessage.textContent = 'An error occurred while validating Trakt token.'
        statusMessage.style.color = '#ea868f'
        statusMessage.style.display = 'block'
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout()
      })
  })
}
