/* global $ */

$(document).ready(function () {
  const plexValid = $('#plex_valid').data('plex-valid') === 'True'
  console.log('Plex Valid:', plexValid)

  // Initialize validation messages array
  const validationMessages = []

  // Add messages based on validation status
  if (!plexValid) {
    validationMessages.push('Plex settings have not been validated successfully. Please return to that page and hit the validate button and ensure success before returning here.')
    // Hide the libraries container if plex is not valid
    $('#libraries-container').hide()
  } else {
    // Show the libraries container if plex is valid
    $('#libraries-container').show()
  }

  // If there are validation messages, display them
  if (validationMessages.length > 0) {
    $('#validation-messages').html(validationMessages.join('<br>')).show()
  } else {
    $('#validation-messages').html('').hide()
  }

  // Initialize checkboxes based on the hidden input field value
  const selectedLibraries = document.getElementById('libraries').value.split(',').map(item => item.trim())
  console.log('Selected Libraries:', selectedLibraries)
  $('.library-checkbox').each(function () {
    if (selectedLibraries.includes($(this).val())) {
      $(this).prop('checked', true)
    }
  })

  // Update hidden input field when checkboxes are changed
  $('.library-checkbox').change(function () {
    const selectedLibraries = []
    $('.library-checkbox:checked').each(function () {
      selectedLibraries.push($(this).val())
    })
    document.getElementById('libraries').value = selectedLibraries.join(', ')
    setSettingsValidated(false)
  })

  const isValidated = document.getElementById('playlist_files_validated').value.toLowerCase()
  console.log('Validated: ' + isValidated)

  if (isValidated === 'true') {
    document.getElementById('validateSettingsButton').disabled = true
  } else {
    document.getElementById('validateSettingsButton').disabled = false
  }
})

document.addEventListener('DOMContentLoaded', function () {
  const validateSettingsButton = document.getElementById('validateSettingsButton')

  validateSettingsButton.addEventListener('click', function () {
    if (validateForm()) {
      setSettingsValidated(true)
      this.disabled = true
    }
  })
})

function setSettingsValidated (isValid) {
  const settingsValidatedInput = document.getElementById('playlist_files_validated')
  settingsValidatedInput.value = isValid ? 'true' : 'false'
  document.getElementById('validateSettingsButton').disabled = isValid
}

function validateForm () {
  const selectedLibraries = document.getElementById('libraries').value.trim()
  if (!selectedLibraries) {
    return false // Prevent form submission if no libraries are selected
  }

  // Additional form validation logic can go here if needed
  return true // Allow form submission
}
