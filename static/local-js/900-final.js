/* global $ */

$(document).ready(function () {
  // Debugging: Confirm jQuery is loaded
  // console.log("jQuery loaded.");

  // Fetch the validation status
  const plexValid = $('#plex_valid').data('plex-valid') === 'True'
  const tmdbValid = $('#tmdb_valid').data('tmdb-valid') === 'True'
  const yamlValid = $('#yaml_valid').data('yaml-valid') === 'True'
  // const validationError = $('#validation-error').val().trim()
  // Debugging: Check the values of the meta tags

  const showYAML = plexValid && tmdbValid && yamlValid

  console.log('Plex Valid:', plexValid)
  console.log('TMDb Valid:', tmdbValid)
  console.log('YAML Valid:', yamlValid)
  console.log('Show YAML:', showYAML)

  // Initialize validation messages array
  const validationMessages = []

  // Add messages based on validation status
  if (!plexValid) {
    validationMessages.push('Plex settings have not been validated successfully. Please return to that page and hit the validate button and ensure success before returning here.')
  }
  if (!tmdbValid) {
    validationMessages.push('TMDb settings have not been validated successfully. Please return to that page and hit the validate button and ensure success before returning here.')
  }

  // If there are validation messages, display them
  if (!showYAML) {
    if (validationMessages.length > 0) {
      $('#validation-messages').html(validationMessages.join('<br>')).show()
    } else {
      $('#validation-messages').html('').hide()
    }

    $('#no-validation-warning, #yaml-warnings, #yaml-warning-msg, #validation-error').removeClass('d-none')
    // Hide the download button
    $('#download-btn').addClass('d-none')
  } else {
    $('#no-validation-warning, #yaml-warnings, #yaml-warning-msg, #validation-error').addClass('d-none')
    $('#yaml-content, #final-yaml, #download-btn').removeClass('d-none')
  }

  // Debugging: Confirm if validation messages div is updated
  // console.log("Validation Messages:", $('#validation-messages').html());
})

document.getElementById('header-style').addEventListener('change', function () {
  document.getElementById('final-form').submit()
})
