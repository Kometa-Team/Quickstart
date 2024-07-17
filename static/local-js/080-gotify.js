/* global $, showSpinner, hideSpinner */

$(document).ready(function () {
  const isValidated = document.getElementById('gotify_validated').value.toLowerCase()
  const validateButton = document.getElementById('validateButton')

  console.log('Validated: ' + isValidated)

  if (isValidated === 'true') {
    validateButton.disabled = true
  } else {
    validateButton.disabled = false
  }

  document.getElementById('gotify_token').addEventListener('input', function () {
    document.getElementById('gotify_validated').value = 'false'
    validateButton.disabled = false
  })

  document.getElementById('gotify_url').addEventListener('input', function () {
    document.getElementById('gotify_validated').value = 'false'
    validateButton.disabled = false
  })
})

// Function to toggle API key visibility
document.getElementById('toggleTokenVisibility').addEventListener('click', function () {
  const tokenInput = document.getElementById('gotify_token')
  const currentType = tokenInput.getAttribute('type')
  tokenInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  this.innerHTML = currentType === 'password' ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>'
})

/* eslint-disable no-unused-vars */
// Function to validate Gotify API key
async function validateGotifyToken (url, token) {
  const apiUrl = `${url}/version?token=${token}`
  try {
    const response = await fetch(apiUrl)
    if (response.ok) {
      const data = await response.json()
      console.log('API Response:', data)
      return true
    } else {
      const error = await response.json()
      console.log('Invalid Gotify API key. Error:', error)
      return false
    }
  } catch (error) {
    console.error('Error validating Gotify token:', error)
    return false
  }
}
/* eslint-enable no-unused-vars */

/* eslint-disable camelcase */
// Event listener for the validate button
document.getElementById('validateButton').addEventListener('click', function () {
  const gotify_url = document.getElementById('gotify_url').value
  const gotify_token = document.getElementById('gotify_token').value
  const statusMessage = document.getElementById('statusMessage')

  if (!gotify_url || !gotify_token) {
    statusMessage.textContent = 'Please enter both Gotify URL and Token.'
    statusMessage.style.color = '#ea868f'
    return
  }

  showSpinner('validate')

  fetch('/validate_gotify', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      gotify_url,
      gotify_token
    })
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.valid) {
        hideSpinner('validate')
        document.getElementById('gotify_validated').value = 'true'
        statusMessage.textContent = 'Gotify credentials validated successfully!'
        statusMessage.style.color = 'green'
      } else {
        hideSpinner('validate')
        document.getElementById('gotify_validated').value = 'false'
        statusMessage.textContent = data.error
        statusMessage.style.color = 'red'
      }
      document.getElementById('validateButton').disabled = data.valid
      statusMessage.style.display = 'block'
    })
    .catch((error) => {
      hideSpinner('validate')
      console.error('Error validating Gotify credentials:', error)
      statusMessage.textContent = 'An error occurred while validating Gotify credentials.'
      statusMessage.style.color = 'red'
      statusMessage.style.display = 'block'
    })
})
/* eslint-enable camelcase */
