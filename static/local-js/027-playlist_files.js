/* global $ */

$(document).ready(function () {
  const plexValid = $('#plex_valid').length > 0 && $('#plex_valid').data('plex-valid') === 'True'
  console.log('Plex Valid:', plexValid)

  if (!plexValid) {
    $('#libraries-container').hide()
    $('#validation-messages').html(
      'Plex settings have not been validated successfully. Please <a href="javascript:void(0);" onclick="jumpTo(\'010-plex\');">return to the Plex page</a> and hit the validate button and ensure success before returning here.<br>'
    ).show()
  } else {
    $('#libraries-container').show()
    $('#validation-messages').hide()
  }

  // Initialize checkboxes based on preselected libraries
  const selectedLibraries = $('#libraries').val().split(',').map(item => item.trim())
  console.log('Preselected Libraries:', selectedLibraries)
  $('.library-checkbox').each(function () {
    if (selectedLibraries.includes($(this).val())) {
      $(this).prop('checked', true)
    }
  })

  // Update hidden input field when checkboxes are changed
  $('.library-checkbox').change(function () {
    const updatedLibraries = []
    $('.library-checkbox:checked').each(function () {
      updatedLibraries.push($(this).val())
    })
    $('#libraries').val(updatedLibraries.join(', '))
    updateValidationState(updatedLibraries.length > 0)
    console.log('Updated Libraries:', updatedLibraries)
  })

  // Update validation state
  function updateValidationState (isValid) {
    $('#playlist_files_validated').val(isValid ? 'true' : 'false')
    console.log('Validation State Updated:', isValid)
  }

  // Preserve data on form submission for backend processing
  $('#configForm').on('submit', function () {
    // Log the data being submitted for debugging
    console.log('Form Submitted:')
    console.log('Default:', $('#default').val())
    console.log('Libraries:', $('#libraries').val())
    console.log('Validated:', $('#playlist_files_validated').val())
    console.log('Template Variables:', $('#template_variables').val())
  })
})
