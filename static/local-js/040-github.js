/* global $, showSpinner, hideSpinner */

$(document).ready(function () {
  const isValidated = document.getElementById('github_validated').value.toLowerCase() === 'true'
  const validateButton = document.getElementById('validateButton')

  console.log('Validated: ' + isValidated)

  if (isValidated) {
    validateButton.disabled = true
  } else {
    validateButton.disabled = false
  }

  document.getElementById('github_token').addEventListener('input', function () {
    document.getElementById('github_validated').value = 'false'
    validateButton.disabled = false
  })
})

document.getElementById('toggleApikeyVisibility').addEventListener('click', function () {
  const apikeyInput = document.getElementById('github_token')
  const currentType = apikeyInput.getAttribute('type')
  apikeyInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  this.innerHTML = currentType === 'password' ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>'
})

document.getElementById('validateButton').addEventListener('click', function () {
  const apiKey = document.getElementById('github_token').value
  const statusMessage = document.getElementById('statusMessage')

  if (!apiKey) {
    statusMessage.textContent = 'Please enter a GitHub Personal Access Token.'
    statusMessage.style.color = '#ea868f'
    statusMessage.style.display = 'block'
    return
  }

  showSpinner('validate')

  fetch('/validate_github', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ github_token: apiKey })
  })
    .then(response => response.json())
    .then(data => {
      if (data.valid) {
        hideSpinner('validate')
        statusMessage.textContent = data.message
        statusMessage.style.color = '#75b798'
        document.getElementById('validateButton').disabled = true
        document.getElementById('github_validated').value = 'true'
      } else {
        statusMessage.textContent = data.message
        statusMessage.style.color = '#ea868f'
      }
      statusMessage.style.display = 'block'
    })
    .catch(error => {
      hideSpinner('validate')
      console.log(error)
      statusMessage.textContent = 'Error validating GitHub token.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      document.getElementById('github_validated').value = 'false'
    })
})

document.getElementById('configForm').addEventListener('submit', function (event) {
  const apiKeyInput = document.getElementById('github_token')
  if (!apiKeyInput.value) {
    apiKeyInput.value = ''
  }
})
