/* global $, alert */

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
  let selectedLibraries = []
  const librariesValue = document.getElementById('libraries').value
  if (librariesValue) {
    try {
      selectedLibraries = JSON.parse(librariesValue)
    } catch (error) {
      console.error('Error parsing libraries:', error)
    }
  }
  console.log('Selected Libraries:', selectedLibraries)
  $('.library-checkbox').each(function () {
    const checkboxLibrary = $(this).val()
    const checkboxType = $(this).data('type')
    if (selectedLibraries.some(library => library.name === checkboxLibrary && library.type === checkboxType)) {
      $(this).prop('checked', true)
    }
  })

  // Update hidden input field when checkboxes are changed
  $('.library-checkbox').change(function () {
    const selectedLibraries = []
    $('.library-checkbox:checked').each(function () {
      selectedLibraries.push({
        name: $(this).val(),
        type: $(this).data('type')
      })
    })
    document.getElementById('libraries').value = JSON.stringify(selectedLibraries)
    updateLibraries(selectedLibraries)
  })

  // Function to update libraries and create/delete template files
  async function updateLibraries (selectedLibraries) {
    if (!validateLibrarySelection(selectedLibraries)) {
      alert('Please select at least one library.')
      return
    }

    try {
      const response = await fetch('/update_libraries', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ libraries: selectedLibraries })
      })

      if (!response.ok) {
        throw new Error(`Error updating libraries: ${response.statusText}`)
      }

      const result = await response.json()
      console.log('Libraries updated successfully:', result)
      document.getElementById('configForm').submit()
    } catch (error) {
      console.error('Error updating libraries:', error)
    }
  }

  const isValidated = document.getElementById('library_selection_validated').value.toLowerCase()
  console.log('Validated: ' + isValidated)
})

// Function to validate that at least one library is selected
function validateLibrarySelection (selectedLibraries) {
  return selectedLibraries.length > 0
}

/* eslint-disable no-unused-vars, camelcase */
function validateForm () {
  const selectedLibraries = JSON.parse(document.getElementById('libraries').value.trim())
  if (!validateLibrarySelection(selectedLibraries)) {
    alert('Please select at least one library.')
    return false
  }

  return true // Allow form submission
}
