/* global $ alert */

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
      generateTabs(selectedLibraries)
      // document.getElementById('configForm').submit()
    } catch (error) {
      console.error('Error updating libraries:', error)
    }
  }

  const isValidated = document.getElementById('library_selection_validated').value.toLowerCase()
  console.log('Validated: ' + isValidated)

  // Initial call to generate tabs on page load
  generateTabs(selectedLibraries)
})

// Function to validate that at least one library is selected
function validateLibrarySelection (selectedLibraries) {
  return selectedLibraries.length > 0
}

// Generate tabs and content
function generateTabs (selectedLibraries) {
  const tabsContainer = $('#tabs')
  const contentContainer = $('#tab-content')

  tabsContainer.empty()
  contentContainer.empty()

  selectedLibraries.forEach((library, index) => {
    const tabId = `tab-${library.name.replace(' ', '-')}`
    const isActive = index === 0 ? 'active' : ''
    const showClass = index === 0 ? 'show active' : ''

    tabsContainer.append(`
            <li class="nav-item">
                <a class="nav-link ${isActive}" id="${tabId}-tab" data-toggle="tab" href="#${tabId}" role="tab" aria-controls="${tabId}" aria-selected="true">${library.name}</a>
            </li>
        `)

    contentContainer.append(`
            <div class="tab-pane fade ${showClass}" id="${tabId}" role="tabpanel" aria-labelledby="${tabId}-tab">
                <!-- Include content for ${library.name} here -->
                ${library.type === 'movie' ? $('#movie-template').html() : $('#show-template').html()}
            </div>
        `)
  })
}

const chBoxes = document.querySelectorAll('.dropdown-menu input[type="checkbox"]')
// const dpBtn = document.getElementById('multiSelectDropdown')
let mySelectedListItems = []

/* eslint-disable no-unused-vars */
function handleCB () {
  mySelectedListItems = []
  let mySelectedListItemsText = ''

  chBoxes.forEach((checkbox) => {
    if (checkbox.checked) {
      mySelectedListItems.push(checkbox.value)
      mySelectedListItemsText += checkbox.value + ', '
    }
  })
}
/* eslint-enable no-unused-vars */

document.addEventListener('DOMContentLoaded', function () {
  const cardFooters = document.querySelectorAll('.card-footer')

  cardFooters.forEach(cardFooter => {
    const checkbox = cardFooter.querySelector('input[type="checkbox"]')
    const button = cardFooter.querySelector('button')

    if (checkbox && button) { // Ensure both elements exist
      checkbox.addEventListener('change', function () {
        button.disabled = !this.checked
      })

      // Initial State: Check if the button should be disabled on load
      button.disabled = !checkbox.checked
    }
  })
})

/* eslint-disable no-unused-vars */
function librarySelect () {
  const T = document.getElementById('library_select')
  T.style.display = 'block' // <-- Set it to block
}
/* eslint-enable no-unused-vars */

/* eslint-disable no-unused-vars, camelcase */
function validateForm () {
  const selectedLibraries = JSON.parse(document.getElementById('libraries').value.trim())
  if (!validateLibrarySelection(selectedLibraries)) {
    alert('Please select at least one library.')
    return false
  }

  return true // Allow form submission
}
