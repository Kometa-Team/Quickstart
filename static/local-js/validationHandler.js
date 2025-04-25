/* global $ */

const ValidationHandler = {
  updateValidationState: function () {
    console.log('[DEBUG] Running validation state update.')

    // Check Plex Validation first
    if (!ValidationHandler.validatePlexState()) {
      return
    }

    const selectedMovieLibraries = ValidationHandler.getSelectedLibraries('mov')
    const selectedShowLibraries = ValidationHandler.getSelectedLibraries('sho')
    const isValid = ValidationHandler.validateForm()

    console.log(`[DEBUG] Selected Movie Libraries: ${selectedMovieLibraries}`)
    console.log(`[DEBUG] Selected Show Libraries: ${selectedShowLibraries}`)
    console.log(`[DEBUG] Form is valid: ${isValid}`)

    document.getElementById('libraries').value = [...selectedMovieLibraries, ...selectedShowLibraries].join(',')
    document.getElementById('libraries_validated').value = isValid ? 'true' : 'false'

    if (isValid) {
      console.log('[DEBUG] Validation Passed! Enabling navigation.')
      ValidationHandler.showValidationMessage('Validation successful! You may proceed.', 'success')
      ValidationHandler.enableNavigation()
    } else {
      console.log('[DEBUG] Validation Failed! Disabling navigation.')
      ValidationHandler.showValidationMessage(
        'Please review your selections: ensure you have picked at least one library, selected an item inside each chosen library, and if using Separators, selected a valid <strong>Placeholder IMDb ID</strong>. Items needing attention are highlighted in red below.',
        'danger'
      )
      ValidationHandler.disableNavigation(false)
    }
  },

  validatePlexState: function () {
    const plexValid = $('#plex_valid').data('plex-valid') === 'True'
    console.log('[DEBUG] Plex Valid:', plexValid)

    if (!plexValid) {
      console.log('[DEBUG] Plex validation failed! Hiding all accordions & disabling navigation.')
      document.getElementById('selected-libraries-container').style.display = 'none'
      $('#all-accordions-container').hide()
      ValidationHandler.showValidationMessage(
        'Plex settings have not been validated successfully. Please <a href="javascript:void(0);" onclick="jumpTo(\'010-plex\');">return to the Plex page</a> and hit the validate button and ensure success before returning here.<br>',
        'danger'
      )
      ValidationHandler.disableNavigation()
      return false
    } else {
      console.log('[DEBUG] Plex validation passed! Showing all accordions.')
      document.getElementById('selected-libraries-container').style.display = 'block'
      $('#all-accordions-container').show()
      return true
    }
  },

  validateForm: function () {
    console.log('[DEBUG] Running validateForm...')

    const selectedMovieLibraries = ValidationHandler.getSelectedLibraries('mov')
    const selectedShowLibraries = ValidationHandler.getSelectedLibraries('sho')
    const libraryList = [...selectedMovieLibraries, ...selectedShowLibraries]

    console.log(`[DEBUG] Selected Movie Libraries: ${selectedMovieLibraries}`)
    console.log(`[DEBUG] Selected Show Libraries: ${selectedShowLibraries}`)
    console.log(`[DEBUG] Combined Library List: ${libraryList}`)

    // If no libraries are selected, disable navigation immediately
    if (libraryList.length === 0) {
      console.log('[DEBUG] No libraries selected! Disabling navigation.')
      ValidationHandler.showValidationMessage(
        'You must select at least one library to proceed.',
        'danger'
      )
      ValidationHandler.disableNavigation(false)
      return false
    }

    // Validate that all selected libraries have at least one highlight
    const validateLibraries = () => {
      const selectedLibraries = Array.from(document.querySelectorAll('.library-checkbox:checked'))
        .map(checkbox => checkbox.id.replace(/-library$/, '')) // Normalize ID

      const invalidLibraries = []

      // Reset all borders before validation
      document.querySelectorAll('[id$="-container"]').forEach(container => {
        container.style.border = '' // Remove the red border
      })

      const isValid = selectedLibraries.every(libraryId => {
        const libraryContainer = document.querySelector(`#${libraryId}-container`)
        console.log(`[DEBUG] Looking for libraryContainer: #${libraryId}-container`)

        if (!libraryContainer) {
          console.log(`[DEBUG] No container found for selected library: ${libraryId}`)
          invalidLibraries.push(libraryId)
          return false
        }

        const hasSelectedHeader = libraryContainer.querySelector('.accordion-header.selected') !== null
        console.log(`[DEBUG] Library "${libraryId}-container" has selected header highlight: ${hasSelectedHeader}`)

        if (!hasSelectedHeader) {
          invalidLibraries.push(libraryId)
        } else {
          // If the library is valid, remove red border
          libraryContainer.style.border = ''
        }

        return hasSelectedHeader
      })

      if (!isValid) {
        // Highlight problematic containers
        invalidLibraries.forEach(libraryId => {
          const libraryContainer = document.querySelector(`#${libraryId}-container`)
          if (libraryContainer) {
            libraryContainer.style.border = '2px solid red' // Highlight border in red
          }
        })

        // Display a Bootstrap Toast notification
        // showToast('error', `The following libraries must have at least one selected item:<br><strong>${invalidLibraries.join(", ")}</strong>`)
      }

      return isValid
    }

    const allLibrariesValid = validateLibraries(libraryList)

    const validatePlaceholderSelection = () => {
      let allPlaceholdersValid = true

      document.querySelectorAll('.placeholder-imdb-dropdown').forEach(dropdown => {
        dropdown.classList.remove('is-invalid')

        const libraryId = dropdown.dataset.libraryId
        const libraryType = dropdown.dataset.libraryType
        const libraryPrefix = libraryType === 'movie' ? 'mov' : 'sho'

        const separatorDropdown = document.querySelector(`[name="${libraryPrefix}-library_${libraryId.replace(/\s+/g, '').toLowerCase()}-template_variables[use_separator]"]`)

        if (separatorDropdown && separatorDropdown.value !== 'none') {
          if (!dropdown.value) {
            console.log(`[DEBUG] Placeholder missing for library: ${libraryId}`)
            allPlaceholdersValid = false
            dropdown.classList.add('is-invalid')

            // Bubble up red invalid highlight properly
            let parent = dropdown.closest('.accordion-item')
            while (parent) {
              const header = parent.querySelector(':scope > .accordion-header')
              if (header) {
                header.classList.remove('selected')
                header.classList.add('invalid')
              }
              parent = parent.parentElement?.closest('.accordion-item')
            }
          } else {
            // Valid placeholder selected, bubble up green
            let parent = dropdown.closest('.accordion-item')
            while (parent) {
              const header = parent.querySelector(':scope > .accordion-header')
              if (header) {
                header.classList.remove('invalid')
                header.classList.add('selected')
              }
              parent = parent.parentElement?.closest('.accordion-item')
            }
          }
        }
      })

      return allPlaceholdersValid
    }

    const allPlaceholdersValid = validatePlaceholderSelection()

    console.log(`[DEBUG] Libraries Valid: ${allLibrariesValid}`)
    console.log(`[DEBUG] Placeholders Valid: ${allPlaceholdersValid}`)

    if (allLibrariesValid && allPlaceholdersValid) {
      console.log('[DEBUG] Validation Passed! Enabling navigation.')
      ValidationHandler.showValidationMessage('Validation successful! You may proceed.', 'success')
      ValidationHandler.enableNavigation()
      return true
    } else {
      console.log('[DEBUG] Some validations failed! Disabling navigation.')
      ValidationHandler.showValidationMessage(
        'Each selected library must have at least one highlighted item, and a valid Placeholder IMDb must be selected if a Separator is enabled.',
        'danger'
      )
      ValidationHandler.disableNavigation(false)
      return false
    }
  },

  getSelectedLibraries: function (type) {
    const selectedLibraries = [...document.querySelectorAll(`.library-checkbox[id^="${type}-library"]:checked`)]
      .map(input => input.value.trim()) // Ensure we get the actual library name

    console.log(`[DEBUG] Selected ${type} Libraries:`, selectedLibraries)
    return selectedLibraries
  },

  restoreSelectedLibraries: function () {
    const libraryInput = document.getElementById('libraries')
    if (!libraryInput.value) {
      console.log('[DEBUG] Libraries field is empty. Initializing...')
      libraryInput.value = '' // Initialize if empty
    }

    const selectedLibraries = libraryInput ? libraryInput.value.split(',').map(item => item.trim()) : []
    console.log('[DEBUG] Restoring Selected Libraries:', selectedLibraries)

    $('.library-checkbox').each(function () {
      if (selectedLibraries.includes($(this).val())) {
        console.log(`[DEBUG] Restoring selection: ${$(this).val()}`)
        $(this).prop('checked', true)
      }
    })
  },

  showValidationMessage: function (message, type) {
    const validationBox = document.getElementById('validation-messages')
    if (!validationBox) return

    console.log(`[DEBUG] Showing validation message: "${message}" (${type})`)

    validationBox.innerHTML = message
    validationBox.classList.remove('alert-danger', 'alert-success')
    validationBox.classList.add(`alert-${type}`)
    validationBox.style.display = 'block'
  },

  disableNavigation: function (lockAccordions = true) {
    console.log('[DEBUG] Disabling navigation.')
    document.querySelectorAll("#configForm .dropdown-toggle, #configForm button[onclick*='next']").forEach(button => {
      button.disabled = true
    })

    // Keep the Previous button enabled
    document.querySelector("#configForm button[onclick*='prev']").disabled = false

    // Handle accordions based on the lockAccordions flag
    if (!lockAccordions) {
      console.log('[DEBUG] Accordions are unlocked despite validation failure.')
      document.querySelectorAll('.accordion-button').forEach(button => {
        button.disabled = false
      })
    }
  },

  enableNavigation: function () {
    console.log('[DEBUG] Enabling navigation.')
    document.querySelectorAll('#configForm button, #configForm .dropdown-toggle').forEach(button => {
      button.disabled = false
    })
  }
}

// Restore previously selected libraries
ValidationHandler.restoreSelectedLibraries()

// Attach validation update on input change
document.addEventListener('DOMContentLoaded', () => {
  console.log('[DEBUG] Adding change event listeners to library checkboxes & accordions.')

  document.querySelectorAll('.library-checkbox, .accordion input').forEach((input) => {
    input.addEventListener('change', () => {
      console.log(`[DEBUG] Change detected on: ${input.id || '(unknown input)'}`)
      ValidationHandler.updateValidationState()
    })
  })

  // Initial validation check on page load
  console.log('[DEBUG] Running initial validation check on page load.')
  ValidationHandler.updateValidationState()
})
