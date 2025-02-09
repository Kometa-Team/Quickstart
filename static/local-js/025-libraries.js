/* global $, showToast */

document.addEventListener('DOMContentLoaded', function () {
  fetch('/check_base_images')
    .then(response => response.json())
    .then(data => {
      if (!data.movie_exists) {
        deleteMovieImage.style.display = 'none'
      } else {
        deleteMovieImage.style.display = 'block'
        showToast('info', 'Custom movie base image detected.')
      }

      if (!data.show_exists) {
        deleteShowImage.style.display = 'none'
      } else {
        deleteShowImage.style.display = 'block'
        showToast('info', 'Custom show base image detected.')
      }
    })
    .catch(error => console.error('Error checking base images:', error))
  const previewMovieButton = document.getElementById('previewOverlayButtonMovie')
  const previewShowButton = document.getElementById('previewOverlayButtonShow')
  const uploadMovieInput = document.getElementById('baseImageUploadMovie')
  const uploadShowInput = document.getElementById('baseImageUploadShow')
  const previewMovieImageContainer = document.getElementById('previewMovieImageContainer')
  const previewShowImageContainer = document.getElementById('previewShowImageContainer')
  const previewMovieImage = document.getElementById('previewMovieImage')
  const previewShowImage = document.getElementById('previewShowImage')
  const deleteMovieImage = document.getElementById('deleteMovieImage')
  const deleteShowImage = document.getElementById('deleteShowImage')

  function generatePreview (isMoviePreview) {
    const selectedOverlays = []
    const overlayContainer = isMoviePreview ? document.getElementById('movieOverlays') : document.getElementById('showOverlays')
    const overlayPrefix = isMoviePreview ? 'mov-' : 'sho-'

    overlayContainer.querySelectorAll('input.form-check-input:checked').forEach(input => {
      if (input.id.startsWith(overlayPrefix)) {
        selectedOverlays.push(input.name)
      }
    })

    const selectedRating = overlayContainer.querySelector("input[type='radio']:checked")
    if (selectedRating) {
      selectedOverlays.push(selectedRating.value)
    }

    if (selectedOverlays.length === 0) {
      if (isMoviePreview) {
        previewMovieImageContainer.style.display = 'none'
      } else {
        previewShowImageContainer.style.display = 'none'
      }
      showToast('warning', 'No overlays selected!')
      return
    }

    fetch('/generate_preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ overlays: selectedOverlays, type: isMoviePreview ? 'movie' : 'show' })
    })
      .then(response => response.blob())
      .then(blob => {
        const url = URL.createObjectURL(blob)
        if (isMoviePreview) {
          previewMovieImage.src = url
          previewMovieImageContainer.style.display = 'block'
          deleteMovieImage.style.display = 'block'
        } else {
          previewShowImage.src = url
          previewShowImageContainer.style.display = 'block'
          deleteShowImage.style.display = 'block'
        }
      })
      .catch(error => {
        console.error('Error generating preview:', error)
        showToast('error', 'Failed to generate preview.')
      })
  }

  if (previewMovieButton) {
    previewMovieButton.addEventListener('click', function (event) {
      event.preventDefault()
      event.stopPropagation()
      event.preventDefault()
      generatePreview(true)
    })
  }

  if (previewShowButton) {
    previewShowButton.addEventListener('click', function (event) {
      event.preventDefault()
      event.stopPropagation()
      event.preventDefault()
      generatePreview(false)
    })
  }

  function deleteCustomImage (isMovie) {
    fetch('/delete_base_image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `type=${isMovie ? 'movie' : 'show'}`
    })
      .then(response => response.json())
      .then(data => {
        showToast('success', data.message)
      })
      .catch(error => {
        console.error('Error deleting image:', error)
        showToast('error', 'Failed to delete custom image.')
      })
  }

  if (deleteMovieImage) {
    deleteMovieImage.addEventListener('click', function (event) {
      event.preventDefault()
      event.stopPropagation()
      deleteCustomImage(true)
      previewMovieImageContainer.style.display = 'none'
      deleteMovieImage.style.display = 'none'
    })
  }

  if (deleteShowImage) {
    deleteShowImage.addEventListener('click', function (event) {
      event.preventDefault()
      event.stopPropagation()
      deleteCustomImage(false)
      previewShowImageContainer.style.display = 'none'
      deleteShowImage.style.display = 'none'
    })
  }

  function handleImageUpload (isMovieUpload, inputElement) {
    const file = inputElement.files[0]
    if (!file) return

    const formData = new FormData()
    formData.append('image', file)
    formData.append('type', isMovieUpload ? 'movie' : 'show')

    fetch('/upload_base_image', {
      method: 'POST',
      body: formData
    })
      .then(response => response.json())
      .then(data => {
        if (data.status === 'success') {
          showToast('success', isMovieUpload ? 'Movie base image uploaded successfully!' : 'Show base image uploaded successfully!')
        } else {
          showToast('error', data.message)
        }
      })
      .catch(error => {
        console.error('Upload error:', error)
        showToast('error', 'Failed to upload base image.')
      })
  }

  if (uploadMovieInput) {
    uploadMovieInput.addEventListener('change', function () {
      previewMovieImageContainer.style.display = 'none'
      handleImageUpload(true, uploadMovieInput)
    })
  }

  if (uploadShowInput) {
    uploadShowInput.addEventListener('change', function () {
      previewShowImageContainer.style.display = 'none'
      handleImageUpload(false, uploadShowInput)
    })
  }

  function updateHiddenInputs (prefix) {
    const form = document.getElementById('configForm')
    if (!form) {
      console.error("[ERROR] Form element 'configForm' not found!")
      return
    }

    const useSeparatorsDropdown = document.getElementById(`${prefix}-attribute_use_separators`)
    let useSeparatorsInput = document.getElementById(`${prefix}-template_variables_use_separators`)
    let sepStyleInput = document.getElementById(`${prefix}-template_variables_sep_style`)

    // Get related separator toggles
    const chartSeparatorToggle = document.getElementById(`${prefix}-collection_separator_chart`)
    const awardSeparatorToggle = document.getElementById(`${prefix}-collection_separator_award`)

    // **New Logic: Check if any other award/chart toggles are enabled**
    const awardTogglesChecked = $(`#${prefix}-awardCollectionsAccordion input[type="checkbox"]:checked`).not(`#${prefix}-collection_separator_award`).length > 0
    const chartTogglesChecked = $(`#${prefix}-chartCollectionsAccordion input[type="checkbox"]:checked`).not(`#${prefix}-collection_separator_chart`).length > 0

    // Debugging Logs
    console.log(`[DEBUG] ${prefix}-attribute_use_separators changed to:`, useSeparatorsDropdown?.value)
    console.log(`[DEBUG] Award Toggles Checked: ${awardTogglesChecked}`)
    console.log(`[DEBUG] Chart Toggles Checked: ${chartTogglesChecked}`)
    console.log('[DEBUG] Chart Separator Toggle Exists:', !!chartSeparatorToggle)
    console.log('[DEBUG] Award Separator Toggle Exists:', !!awardSeparatorToggle)

    const selectedValue = useSeparatorsDropdown.value
    const isEnabled = selectedValue !== 'none'

    // Ensure hidden inputs exist
    if (!useSeparatorsInput) {
      useSeparatorsInput = document.createElement('input')
      useSeparatorsInput.type = 'hidden'
      useSeparatorsInput.name = `${prefix}-template_variables[use_separators]`
      useSeparatorsInput.id = `${prefix}-template_variables_use_separators`
      form.appendChild(useSeparatorsInput)
    }
    useSeparatorsInput.value = isEnabled ? 'true' : 'false'

    if (!sepStyleInput) {
      sepStyleInput = document.createElement('input')
      sepStyleInput.type = 'hidden'
      sepStyleInput.name = `${prefix}-template_variables[sep_style]`
      sepStyleInput.id = `${prefix}-template_variables_sep_style`
      form.appendChild(sepStyleInput)
    }
    sepStyleInput.value = isEnabled ? selectedValue : ''

    // **Enable/Disable Award Separator Toggle**
    if (awardSeparatorToggle) {
      awardSeparatorToggle.disabled = !isEnabled || !awardTogglesChecked // Enable only if separators are enabled and an award toggle is checked
      awardSeparatorToggle.checked = isEnabled && awardTogglesChecked // Auto-check if conditions met
      console.log('[DEBUG] Award Separator Toggle is now:', awardSeparatorToggle.checked)
    }

    // **Enable/Disable Chart Separator Toggle**
    if (chartSeparatorToggle) {
      chartSeparatorToggle.disabled = !isEnabled || !chartTogglesChecked // Enable only if separators are enabled and a chart toggle is checked
      chartSeparatorToggle.checked = isEnabled && chartTogglesChecked // Auto-check if conditions met
      console.log('[DEBUG] Chart Separator Toggle is now:', chartSeparatorToggle.checked)
    }

    // updateValidationState() // ✅ Ensure validation updates when separators change
  }

  // Function to update separator toggles dynamically when a checkbox is clicked
  function attachToggleListeners (prefix) {
    // Attach event listeners to award checkboxes
    $(`#${prefix}-awardCollectionsAccordion input[type="checkbox"]`).change(function () {
      console.log(`[DEBUG] Award Collection Checkbox Changed: ${this.id}`)
      updateHiddenInputs(prefix)
    })

    // Attach event listeners to chart checkboxes
    $(`#${prefix}-chartCollectionsAccordion input[type="checkbox"]`).change(function () {
      console.log(`[DEBUG] Chart Collection Checkbox Changed: ${this.id}`)
      updateHiddenInputs(prefix)
    })
  }

  // Apply for both Movies (mov) and Shows (sho)
  ['mov', 'sho'].forEach((prefix) => {
    const dropdown = document.getElementById(`${prefix}-attribute_use_separators`)
    if (dropdown) {
      dropdown.addEventListener('change', function () {
        console.log(`[DEBUG] ${prefix}-attribute_use_separators dropdown changed`)
        updateHiddenInputs(prefix)
        // updateValidationState() // ✅ Ensure validation updates when separators change
      })
      updateHiddenInputs(prefix) // Run once on load
      attachToggleListeners(prefix) // Attach listeners for dynamic changes
    } else {
      console.error(`[ERROR] Dropdown ${prefix}-attribute_use_separators not found!`)
    }
  })

  // Updated Form Submission Logic
  $('#configForm').submit(function () {
    console.log('[DEBUG] Form submission triggered.')
    /* eslint-disable no-unexpected-multiline, no-sequences */
      ['mov', 'sho'].forEach((prefix) => {
        const useSeparatorsDropdown = document.getElementById(`${prefix}-attribute_use_separators`)
        const useSeparatorsValue = useSeparatorsDropdown ? useSeparatorsDropdown.value : 'none'

        console.log(`[DEBUG] Storing separator values for ${prefix}:`, useSeparatorsValue)
        /* eslint-enable no-unexpected-multiline, no-sequences */

        $('input[name="' + prefix + '-template_variables[use_separators]"]').val(
          useSeparatorsValue !== 'none' ? 'true' : 'false'
        )
        $('input[name="' + prefix + '-template_variables[sep_style]"]').val(
          useSeparatorsValue !== 'none' ? useSeparatorsValue : ''
        )

        $('input[name="' + prefix + '-collection_separator_award"]').val(
          $('#' + prefix + '-collection_separator_award').prop('checked') ? 'true' : 'false'
        )
        $('input[name="' + prefix + '-collection_separator_chart"]').val(
          $('#' + prefix + '-collection_separator_chart').prop('checked') ? 'true' : 'false'
        )
      })

    updateValidationState() // ✅ Ensure validation updates on form submission
  })
})

/* eslint-disable camelcase */
$(document).ready(function () {
  console.log('[DEBUG] Document ready event triggered.')
  const mov_awardSeparatorToggle = $('#mov-collection_separator_award')
  const mov_chartSeparatorToggle = $('#mov-collection_separator_chart')
  const sho_awardSeparatorToggle = $('#sho-collection_separator_award')
  const sho_chartSeparatorToggle = $('#sho-collection_separator_chart')
  const plexValid = $('#plex_valid').data('plex-valid') === 'True'
  console.log('[DEBUG] Plex Valid:', plexValid)

  if (!plexValid) {
    $('#all-accordions-container').hide()
    showValidationMessage(
      'Plex settings have not been validated successfully. Please return to that page and validate before proceeding.',
      'danger'
    )
    disableNavigation()
    return
  } else {
    $('#all-accordions-container').show()
  }

  // Restore saved library selections
  const librariesInput = $('#libraries')
  if (!librariesInput.val()) {
    console.log('Libraries field is empty. Initializing...')
    librariesInput.val('') // Initialize if empty
  }
  const selectedLibraries = librariesInput.val().split(',').map(item => item.trim())
  console.log('Restoring Selected Libraries:', selectedLibraries)

  $('.library-checkbox').each(function () {
    if (selectedLibraries.includes($(this).val())) {
      $(this).prop('checked', true)
    }
  })

  // Attach change listeners to library and accordion checkboxes
  $('.library-checkbox, .accordion-item input[type="checkbox"]').change(function () {
    console.log('[DEBUG] Checkbox state changed.')
    updateValidationState() // ✅ Ensure validation updates when checkboxes change
  })

  // Ensure values are stored properly before form submission
  $('#configForm').submit(function () {
    $('input[name="mov-collection_separator_award"]').val(
      mov_awardSeparatorToggle.prop('checked') ? 'true' : 'false'
    )
    $('input[name="mov-collection_separator_chart"]').val(
      mov_chartSeparatorToggle.prop('checked') ? 'true' : 'false'
    )
    $('input[name="sho-collection_separator_award"]').val(
      sho_awardSeparatorToggle.prop('checked') ? 'true' : 'false'
    )
    $('input[name="sho-collection_separator_chart"]').val(
      sho_chartSeparatorToggle.prop('checked') ? 'true' : 'false'
    )
  })

  // Allow unselecting content rating radio buttons
  document.querySelectorAll('input[type="radio"][name$="-content-rating-group"]').forEach(radio => {
    radio.addEventListener('click', function () {
      console.log(`[DEBUG] Radio button clicked: ${this.name} -> ${this.value}`)

      if (this.checked && this.dataset.wasChecked === 'true') {
        this.checked = false
        this.dataset.wasChecked = 'false'

        const hiddenInputName = this.name.replace('-content-rating-group', '-attribute_selected_content_rating')
        const hiddenInput = document.querySelector(`input[name="${hiddenInputName}"]`)
        if (hiddenInput) {
          hiddenInput.value = ''
        }
        console.log('[DEBUG] Unselected radio button:', this.name)
      } else {
        document.querySelectorAll(`input[name="${this.name}"]`).forEach(r => { r.dataset.wasChecked = 'false' })
        this.dataset.wasChecked = 'true'

        let selectedValue = this.value

        // 🔥 Fix: Ensure Common Sense gets stored as 'commonsense' instead of 'content_rating_commonsense'
        if (selectedValue === 'content_rating_commonsense') {
          selectedValue = 'commonsense'
        }

        const hiddenInputName = this.name.replace('-content-rating-group', '-attribute_selected_content_rating')
        const hiddenInput = document.querySelector(`input[name="${hiddenInputName}"]`)
        if (hiddenInput) {
          hiddenInput.value = selectedValue
        }
        console.log(`[DEBUG] Selected radio button: ${this.name} -> ${selectedValue}`)
      }

      updateValidationState() // ✅ Ensure validation updates when radio selection changes
    })
  })

  updateValidationState()
})

$(document).on('change', '[id^="mov-library_"], [id^="sho-library_"], #accordionMovies input[type="checkbox"], #accordionShows input[type="checkbox"]', function () {
  validateForm() // Re-run validation when a selection is made
})

/* eslint-enable camelcase */

function updateValidationState () {
  console.log('[DEBUG] Running validation state update.')
  const selectedMovieLibraries = getSelectedLibraries('mov-library_')
  const selectedShowLibraries = getSelectedLibraries('sho-library_')
  const isValid = validateForm()

  $('#libraries').val([...selectedMovieLibraries, ...selectedShowLibraries].join(', '))
  $('#libraries_validated').val(isValid ? 'true' : 'false')

  if (isValid) {
    showValidationMessage('Validation successful! You may proceed.', 'success')
    enableNavigation()
  } else {
    showValidationMessage('You must select at least one library and at least one corresponding accordion item.', 'danger')
    disableNavigation(false)
  }
}

function validateForm () {
  console.log('[DEBUG] Running validateForm...')

  // **Movies Section Validation**
  const movieLibrarySelected = $('[id^="mov-library_"]:checked').length > 0
  const selectedMovieToggles = $('#accordionMovies .accordion-item input:checked')
    .map(function () {
      const id = $(this).attr('id')
      return id && id.startsWith('mov-') ? id : null // Only return IDs that start with "mov-"
    })
    .get()

  const movieAccordionSelected = selectedMovieToggles.length > 0

  // **TV Shows Section Validation**
  const showLibrarySelected = $('[id^="sho-library_"]:checked').length > 0
  const selectedShowToggles = $('#accordionShows .accordion-item input:checked')
    .map(function () {
      const id = $(this).attr('id')
      return id && id.startsWith('sho-') ? id : null // Only return IDs that start with "sho-"
    })
    .get()

  const showAccordionSelected = selectedShowToggles.length > 0

  // **Validation Logic**
  const moviesValid = !movieLibrarySelected || movieAccordionSelected // Movie valid if library selected and at least one accordion toggle is checked
  const showsValid = !showLibrarySelected || showAccordionSelected // Show valid if library selected and at least one accordion toggle is checked
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
}

function getSelectedLibraries (prefix) {
  return $(`[id^="${prefix}"]:checked`)
    .map(function () {
      return $(this).val()
    })
    .get()
}

function showValidationMessage (message, type) {
  const validationBox = $('#validation-messages')
  validationBox
    .html(message)
    .removeClass('alert-danger alert-success')
    .addClass(`alert-${type}`)
    .show()
}

function disableNavigation (lockAccordions = true) {
  // Disable the Jump To and Next buttons
  $('#configForm .dropdown-toggle').prop('disabled', true) // Jump To dropdown
  $('#configForm button[onclick*="next"]').prop('disabled', true) // Next button

  // Keep the Previous button enabled at all times
  $('#configForm button[onclick*="prev"]').prop('disabled', false) // Enable Previous button

  // Handle accordions based on the lockAccordions flag
  if (!lockAccordions) {
    $('.accordion-button').prop('disabled', false) // Keep accordions interactive
  }
}

function enableNavigation () {
  $('#configForm button').prop('disabled', false)
  $('#configForm .dropdown-toggle').prop('disabled', false)
}
