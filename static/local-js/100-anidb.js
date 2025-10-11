/* global $, showSpinner, hideSpinner */

$(document).ready(function () {
  const passwordInput = document.getElementById('anidb_password')
  const toggleButton = document.getElementById('togglePasswordVisibility')
  const validateButton = document.getElementById('validateButton')
  const isValidatedElement = document.getElementById('anidb_validated')
  const isValidated = isValidatedElement.value.toLowerCase()

  console.log('Validated:', isValidated)

  // After DOM ready (you can put this inside your existing $(document).ready)
  const anidbClientInput = document.getElementById('anidb_client')

  if (anidbClientInput) {
  // Force lowercase as the user types
    anidbClientInput.addEventListener('input', (e) => {
      const el = e.target
      const start = el.selectionStart
      const end = el.selectionEnd
      const lower = el.value.toLowerCase()
      if (el.value !== lower) {
        el.value = lower
        // restore caret/selection
        el.setSelectionRange(start, end)
      }
    })

    // Ensure pasted text is lowercased too
    anidbClientInput.addEventListener('paste', (e) => {
      e.preventDefault()
      const el = e.target
      const pasted = (e.clipboardData || window.clipboardData).getData('text') || ''
      const start = el.selectionStart
      const end = el.selectionEnd
      const before = el.value.slice(0, start)
      const after = el.value.slice(end)
      const insert = pasted.toLowerCase()
      el.value = before + insert + after
      const caret = before.length + insert.length
      el.setSelectionRange(caret, caret)
      // fire input so your existing listeners (validation reset) still run
      el.dispatchEvent(new Event('input', { bubbles: true }))
    })

    // Optional: visual cue in the UI (purely cosmetic)
    anidbClientInput.style.textTransform = 'lowercase'
  }

  // Set initial visibility based on password value
  if (passwordInput.value.trim() === '') {
    passwordInput.setAttribute('type', 'text') // Show placeholder text
    toggleButton.innerHTML = '<i class="fas fa-eye-slash"></i>' // Show eye-slash
  } else {
    passwordInput.setAttribute('type', 'password') // Hide actual password
    toggleButton.innerHTML = '<i class="fas fa-eye"></i>' // Show eye
  }

  // Disable validate button if already validated
  validateButton.disabled = isValidated === 'true'

  // Reset validation status when user types
  const inputFields = ['anidb_client', 'anidb_version', 'anidb_username', 'anidb_password']
  inputFields.forEach(field => {
    const inputElement = document.getElementById(field)
    if (inputElement) {
      inputElement.addEventListener('input', function () {
        isValidatedElement.value = 'false'
        validateButton.disabled = false
      })
    } else {
      console.warn(`Warning: Element with ID '${field}' not found.`)
    }
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
  const validateButton = document.getElementById('validateButton')

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
        statusMessage.textContent = 'AniDB credentials are valid.'
        statusMessage.style.color = '#75b798'
        validateButton.disabled = true
      } else {
        document.getElementById('anidb_validated').value = 'false'
        statusMessage.textContent = `Error: ${data.error}`
        statusMessage.style.color = '#ea868f'
        validateButton.disabled = false
      }
      statusMessage.style.display = 'block'
    })
    .catch((error) => {
      hideSpinner('validate')
      console.error('Error:', error)
      statusMessage.textContent = 'Error validating AniDB credentials.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
      validateButton.disabled = false
    })
})
