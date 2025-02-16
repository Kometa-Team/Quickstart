/* global $ */

$(document).ready(function () {
  // Debugging: Confirm jQuery is loaded
  // console.log("jQuery loaded.");

  // Fetch the validation status
  const plexValid = $('#plex_valid').data('plex-valid') === 'True'
  const tmdbValid = $('#tmdb_valid').data('tmdb-valid') === 'True'
  const libsValid = $('#libs_valid').data('libs-valid') === 'True'
  const settValid = $('#sett_valid').data('sett-valid') === 'True'
  const yamlValid = $('#yaml_valid').data('yaml-valid') === 'True'
  // const validationError = $('#validation-error').val().trim()
  // Debugging: Check the values of the meta tags

  const showYAML = plexValid && tmdbValid && libsValid && settValid && yamlValid

  console.log('Plex Valid:', plexValid)
  console.log('TMDb Valid:', tmdbValid)
  console.log('LIBS Valid:', libsValid)
  console.log('Settings Valid:', settValid)
  console.log('YAML Valid:', yamlValid)
  console.log('Show YAML:', showYAML)

  // Initialize validation messages array
  const validationMessages = []

  // Add messages based on validation status
  if (!plexValid) {
    validationMessages.push(
      'Plex settings have not been validated successfully. Please <a href="javascript:void(0);" onclick="jumpTo(\'010-plex\');">return to the Plex page</a> and hit the validate button and ensure success before returning here.<br>'
    )
  }
  if (!tmdbValid) {
    validationMessages.push(
      'TMDb settings have not been validated successfully. Please <a href="javascript:void(0);" onclick="jumpTo(\'020-tmdb\');">return to the TMDb page</a> and hit the validate button and ensure success before returning here.<br>'
    )
  }
  if (!libsValid) {
    validationMessages.push(
      'Libraries page settings have not been validated successfully. Please <a href="javascript:void(0);" onclick="jumpTo(\'025-libraries\');">return to the Libraries page</a> and ensure you make appropriate selections before returning here.<br>'
    )
  }

  if (!settValid) {
    validationMessages.push(
      'Settings page values have likely been skipped. Please <a href="javascript:void(0);" onclick="jumpTo(\'150-settings\');">return to the Settings page</a> and ensure you make appropriate selections before returning here.<br>'
    )
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
    $('#download-redacted-btn').addClass('d-none')
  } else {
    $('#no-validation-warning, #yaml-warnings, #yaml-warning-msg, #validation-error').addClass('d-none')
    $('#yaml-content, #final-yaml, #download-btn, #download-redacted-btn').removeClass('d-none')
  }

  // Debugging: Confirm if validation messages div is updated
  // console.log("Validation Messages:", $('#validation-messages').html());
})

document.getElementById('header-style').addEventListener('change', function () {
  document.getElementById('configForm').submit()
})
