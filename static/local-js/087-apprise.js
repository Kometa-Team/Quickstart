function refreshValidationCallout () {
  if (window.QSValidationCallouts && typeof window.QSValidationCallouts.refresh === 'function') {
    window.QSValidationCallouts.refresh('apprise_validated')
  }
}

const validatedAtInput = document.getElementById('apprise_validated_at')

$(document).ready(function () {
  const locationInput = document.getElementById('apprise_location')
  const validateButton = document.getElementById('validateButton')
  const isValidated = document.getElementById('apprise_validated').value.toLowerCase()

  validateButton.disabled = isValidated === 'true'

  locationInput.addEventListener('input', function () {
    document.getElementById('apprise_validated').value = 'false'
    if (validatedAtInput) validatedAtInput.value = ''
    validateButton.disabled = false
    refreshValidationCallout()
  })
})

document.getElementById('validateButton').addEventListener('click', function () {
  const appriseLocation = document.getElementById('apprise_location').value.trim()
  const statusMessage = document.getElementById('statusMessage')

  if (!appriseLocation) {
    statusMessage.textContent = 'Please enter an Apprise YAML path or URL.'
    statusMessage.style.color = '#ea868f'
    statusMessage.style.display = 'block'
    return
  }

  showSpinner('validate')

  fetch('/validate_apprise', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      apprise_location: appriseLocation
    })
  })
    .then((response) => response.json())
    .then((data) => {
      hideSpinner('validate')
      if (data.valid) {
        document.getElementById('apprise_validated').value = 'true'
        if (validatedAtInput) validatedAtInput.value = new Date().toISOString()
        refreshValidationCallout()
        statusMessage.textContent = 'Apprise location validated successfully!'
        statusMessage.style.color = '#75b798'
      } else {
        document.getElementById('apprise_validated').value = 'false'
        if (validatedAtInput) validatedAtInput.value = ''
        refreshValidationCallout()
        statusMessage.textContent = data.error
        statusMessage.style.color = '#ea868f'
      }
      document.getElementById('validateButton').disabled = data.valid
      statusMessage.style.display = 'block'
    })
    .catch((error) => {
      hideSpinner('validate')
      console.error('Error validating Apprise location:', error)
      document.getElementById('apprise_validated').value = 'false'
      if (validatedAtInput) validatedAtInput.value = ''
      refreshValidationCallout()
      statusMessage.textContent = 'An error occurred while validating the Apprise location.'
      statusMessage.style.color = '#ea868f'
      statusMessage.style.display = 'block'
    })
})
