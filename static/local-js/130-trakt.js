/* global $, showSpinner, hideSpinner */

$(document).ready(function () {
  const isValidated = document.getElementById('trakt_validated').value

  console.log('Validated: ' + isValidated)

  // if (isValidated) {
  // }
})

document.getElementById('toggleClientSecretVisibility').addEventListener('click', function () {
  const apikeyInput = document.getElementById('trakt_client_secret')
  const currentType = apikeyInput.getAttribute('type')
  apikeyInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  this.innerHTML = currentType === 'password' ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>'
})

/* eslint-disable no-unused-vars, camelcase */
function updateTraktURL () {
  const trakt_client_id = document.getElementById('trakt_client_id').value
  let myURL = ''
  if (trakt_client_id.length === 64) {
    document.getElementById('trakt_validated').value = 'false'
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
    statusMessage.textContent = 'ID, secret, and PIN and all required.'
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
      } else {
        hideSpinner('validate')
        document.getElementById('trakt_validated').value = 'false'
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
    })
})
