/* global $ */

const ValidationHandler = {
  updateValidationState: function () {
    console.log('[DEBUG] Running validation state update.')

    // 🚀 Check Plex Validation First
    if (!ValidationHandler.validatePlexState()) {
      return // Stop further validation if Plex is not valid
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
        'You must select at least one library and at least one corresponding accordion item.',
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

    // **Movies Section Validation**
    const movieLibrarySelected = document.querySelectorAll('[id^="mov-library_"]:checked').length > 0
    const selectedMovieToggles = [...document.querySelectorAll('#accordionMovies .accordion-item input:checked')]
      .map((input) => {
        const libraryIdMatch = input.id.match(/^mov-library_(.+)-library$/) // Extracts the unique library name
        return libraryIdMatch ? libraryIdMatch[1] : null
      })
      .filter(Boolean)

    const movieAccordionSelected = selectedMovieToggles.length > 0

    // **TV Shows Section Validation**
    const showLibrarySelected = document.querySelectorAll('[id^="sho-library_"]:checked').length > 0
    const selectedShowToggles = [...document.querySelectorAll('#accordionShows .accordion-item input:checked')]
      .map((input) => {
        const libraryIdMatch = input.id.match(/^sho-library_(.+)-library$/) // Extracts the unique library name
        return libraryIdMatch ? libraryIdMatch[1] : null
      })
      .filter(Boolean)

    const showAccordionSelected = selectedShowToggles.length > 0

    // **Validation Logic**
    const moviesValid = !movieLibrarySelected || movieAccordionSelected
    const showsValid = !showLibrarySelected || showAccordionSelected
    const atLeastOneLibrarySelected = movieLibrarySelected || showLibrarySelected
    const librariesValid = moviesValid && showsValid

    // **Debug Logs**
    console.log('===== VALIDATION DEBUG LOGS =====')
    console.log('  Movie Library Selected:', movieLibrarySelected)
    console.log('  Movie Accordion Selected:', movieAccordionSelected)
    console.log('  Selected Movie Toggles:', selectedMovieToggles)
    console.log('  Show Library Selected:', showLibrarySelected)
    console.log('  Show Accordion Selected:', showAccordionSelected)
    console.log('  Selected Show Toggles:', selectedShowToggles)
    console.log('  Movies Valid:', moviesValid)
    console.log('  Shows Valid:', showsValid)
    console.log('  At Least One Library Selected:', atLeastOneLibrarySelected)
    console.log('  Libraries Valid:', librariesValid)
    console.log('  Final Validation Result:', atLeastOneLibrarySelected && librariesValid)
    console.log('=================================')

    return atLeastOneLibrarySelected && librariesValid
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

    // Hide after 5 seconds if it's a success message
    if (type === 'success') {
      setTimeout(() => {
        validationBox.style.display = 'none'
      }, 5000)
    }
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

// ✅ Restore previously selected libraries
ValidationHandler.restoreSelectedLibraries()

// ✅ Attach validation update on input change
document.addEventListener('DOMContentLoaded', () => {
  console.log('[DEBUG] Adding change event listeners to library checkboxes & accordions.')

  document.querySelectorAll('.library-checkbox, .accordion input').forEach((input) => {
    input.addEventListener('change', () => {
      console.log(`[DEBUG] Change detected on: ${input.id || '(unknown input)'}`)
      ValidationHandler.updateValidationState()
    })
  })

  // ✅ Initial validation check on page load
  console.log('[DEBUG] Running initial validation check on page load.')
  ValidationHandler.updateValidationState()
})
