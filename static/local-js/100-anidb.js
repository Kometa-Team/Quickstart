/* global $, showSpinner, hideSpinner */

$(document).ready(function () {
  const isValidated = document.getElementById('anidb_validated').value.toLowerCase()

  console.log('Validated: ' + isValidated)

  if (isValidated === 'true') {
    document.getElementById('validateButton').disabled = true
  } else {
    document.getElementById('validateButton').disabled = false
  }
});

['anidb_client', 'anidb_version', 'anidb_username', 'anidb_password'].forEach(field => {
  document.getElementById(field).addEventListener('input', function () {
    document.getElementById('anidb_validated').value = 'false'
    document.getElementById('validateButton').disabled = false
  })
})

document.getElementById('togglePasswordVisibility').addEventListener('click', function () {
  const passwordInput = document.getElementById('anidb_password')
  const currentType = passwordInput.getAttribute('type')
  passwordInput.setAttribute('type', currentType === 'password' ? 'text' : 'password')
  this.innerHTML = currentType === 'password' ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>'
})

document.getElementById('validateButton').addEventListener('click', function () {
  const username = document.getElementById('anidb_username').value
  const password = document.getElementById('anidb_password').value
  const client = document.getElementById('anidb_client').value
  const clientver = document.getElementById('anidb_version').value
  const statusMessage = document.getElementById('statusMessage')

  if (!username || !password || !client || !clientver) {
    statusMessage.textContent = 'Please enter all required fields.'
    statusMessage.style.color = '#ea868f'
    statusMessage.style.display = 'block'
    return
  }

  showSpinner('validate')
  fetch('/validate_anidb', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ username, password, client, clientver })
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.valid) {
        hideSpinner('validate')
        document.getElementById('anidb_validated').value = 'true'
        statusMessage.textContent = 'AniDb credentials are valid.'
        statusMessage.style.color = '#75b798'
        document.getElementById('validateButton').disabled = 'true'
      } else {
        hideSpinner('validate')
        document.getElementById('anidb_validated').value = 'false'
        statusMessage.textContent = `Error: ${data.error}`
        statusMessage.style.color = '#ea868f'
        document.getElementById('validateButton').disabled = 'false'
      }
      statusMessage.style.display = 'block'
    })
    .catch((error) => {
      hideSpinner('validate')
      console.error('Error:', error)
      statusMessage.textContent = 'Error validating AniDb credentials.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      document.getElementById('validateButton').disabled = false
    })
})
