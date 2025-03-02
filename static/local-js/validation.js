/* global */

const ValidationHandler = {
  updateValidationState: function () {
    console.log('[DEBUG] Running validation state update.')

    const selectedMovieLibraries = ValidationHandler.getSelectedLibraries('mov')
    const selectedShowLibraries = ValidationHandler.getSelectedLibraries('sho')
    const isValid = ValidationHandler.validateForm()

    document.getElementById('libraries').value = [...selectedMovieLibraries, ...selectedShowLibraries].join(', ')
    document.getElementById('libraries_validated').value = isValid ? 'true' : 'false'

    if (isValid) {
      ValidationHandler.showValidationMessage('Validation successful! You may proceed.', 'success')
      ValidationHandler.enableNavigation()
    } else {
      ValidationHandler.showValidationMessage(
        'You must select at least one library and at least one corresponding accordion item.',
        'danger'
      )
      ValidationHandler.disableNavigation(false)
    }
  },

  validateForm: function () {
    console.log('[DEBUG] Running validateForm...')

    // **Movies Section Validation**
    const movieLibrarySelected = document.querySelectorAll('[id^="mov-library_"]:checked').length > 0
    const selectedMovieToggles = [...document.querySelectorAll('#accordionMovies .accordion-item input:checked')]
      .map((input) => input.id.startsWith('mov-library_') ? input.id : null)
      .filter(Boolean)

    const movieAccordionSelected = selectedMovieToggles.length > 0

    // **TV Shows Section Validation**
    const showLibrarySelected = document.querySelectorAll('[id^="sho-library_"]:checked').length > 0
    const selectedShowToggles = [...document.querySelectorAll('#accordionShows .accordion-item input:checked')]
      .map((input) => input.id.startsWith('sho-') ? input.id : null)
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
    return [...document.querySelectorAll(`[id^="${type}-library_"]:checked`)]
      .map(input => input.value)
  },

  showValidationMessage: function (message, type) {
    const validationBox = document.getElementById('validation-messages')
    if (!validationBox) return

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
      document.querySelectorAll('.accordion-button').forEach(function (button) {
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

// ✅ Attach validation update on input change
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.library-checkbox, .accordion input').forEach((input) => {
    input.addEventListener('change', () => {
      ValidationHandler.updateValidationState()
    })
  })

  // ✅ Initial validation check on page load
  ValidationHandler.updateValidationState()
})
