/* global $, showToast , localStorage, generatePreview */

document.addEventListener('DOMContentLoaded', function () {
  console.log('[DEBUG] Document fully loaded')

  console.log('[DEBUG] Restoring selected libraries for 025-libraries')

  function renameSelectedImage (isMovie) {
    const dropdown = document.getElementById(isMovie ? 'mov-library-image-dropdown' : 'sho-library-image-dropdown')
    const inputField = document.getElementById(isMovie ? 'mov-image-name' : 'sho-image-name')

    if (!dropdown || !inputField) {
      console.error(`[ERROR] Missing elements for renaming ${isMovie ? 'movie' : 'show'} image.`)
      return
    }

    const oldFilename = dropdown.value
    const newName = inputField.value.trim()

    if (!newName) {
      showToast('warning', 'Please enter a new name.')
      return
    }

    if (oldFilename === 'default') {
      showToast('warning', 'You cannot rename the default image.')
      return
    }

    // Preserve file extension
    const newFilename = newName + oldFilename.substring(oldFilename.lastIndexOf('.'))

    console.log(`[DEBUG] Renaming ${isMovie ? 'movie' : 'show'} image: ${oldFilename} -> ${newFilename}`)

    // Send request to Flask to rename the file
    fetch('/rename_library_image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        old_name: oldFilename,
        new_name: newFilename,
        type: isMovie ? 'movie' : 'show'
      })
    })
      .then(response => response.json())
      .then(data => {
        if (data.status === 'success') {
          showToast('success', `Successfully renamed to ${newFilename}`)
          inputField.value = '' // Clear input

          // Reload dropdown and select the renamed image
          loadAvailableImages(isMovie, newFilename)
        } else {
          showToast('error', `Rename failed: ${data.message}`)
        }
      })
      .catch(error => console.error('Rename error:', error))
  }

  // Read preselected libraries from the hidden input field
  const libraryInput = document.getElementById('libraries')
  const selectedLibraries = libraryInput ? libraryInput.value.split(',').map(item => item.trim()) : []
  console.log('[DEBUG] Preselected Libraries:', selectedLibraries)

  document.querySelectorAll('.library-checkbox').forEach(checkbox => {
    if (selectedLibraries.includes(checkbox.value)) {
      checkbox.checked = true
    }

    // Update hidden input when checkbox changes
    checkbox.addEventListener('change', function () {
      const updatedLibraries = []
      document.querySelectorAll('.library-checkbox:checked').forEach(cb => {
        updatedLibraries.push(cb.value)
      })

      // Store updated values in the hidden input field
      if (libraryInput) {
        libraryInput.value = updatedLibraries.join(', ')
      }

      console.log('[DEBUG] Updated Libraries:', updatedLibraries)
    })
  })

  const movieDropdown = document.getElementById('mov-library-image-dropdown')
  const showDropdown = document.getElementById('sho-library-image-dropdown')
  const moviePreviewImage = document.getElementById('mov-preview-image')
  const showPreviewImage = document.getElementById('sho-preview-image')

  function updateAccordionHighlights () {
    document.querySelectorAll('.accordion-item').forEach((accordion) => {
      const isCheckedOrSelected = accordion.querySelector(
        "input[type='checkbox']:checked, input[type='radio']:checked, select option:checked:not([value='']):not([value='none'])"
      ) !== null

      const accordionHeader = accordion.querySelector('.accordion-header')

      if (isCheckedOrSelected) {
        highlightParentAccordions(accordionHeader)
      } else {
        removeHighlightIfEmpty(accordionHeader)
      }
    })
  }

  function highlightParentAccordions (element) {
    while (element) {
      if (element.classList.contains('accordion-header')) {
        element.classList.add('selected')
      }
      element = element.closest('.accordion-item')?.parentElement.closest('.accordion-item')
    }
  }

  function removeHighlightIfEmpty (element) {
    if (!element) return
    const accordionItem = element.closest('.accordion-item')
    if (!accordionItem) return

    const hasSelections = accordionItem.querySelector(
      "input[type='checkbox']:checked, input[type='radio']:checked, select option:checked:not([value='']):not([value='none'])"
    )

    if (!hasSelections) {
      element.classList.remove('selected')
    }

    // Recursively check parents
    const parentAccordionHeader = accordionItem.parentElement.closest('.accordion-item')?.querySelector('.accordion-header')
    removeHighlightIfEmpty(parentAccordionHeader)
  }

  function loadAvailableImages (isMovie, selectedImage = null) {
    fetch(`/list_uploaded_images?type=${isMovie ? 'movie' : 'show'}`)
      .then(response => response.json())
      .then(data => {
        if (data.status === 'error') {
          console.error('Error fetching images:', data.message)
          showToast('error', data.message)
          return
        }

        const dropdown = isMovie ? movieDropdown : showDropdown
        if (!dropdown) {
          console.error(`Dropdown ${isMovie ? 'mov' : 'sho'}-library-image-dropdown not found!`)
          return
        }

        dropdown.innerHTML = "<option value='default'>Default Grey</option>"

        data.images.forEach(img => {
          const option = document.createElement('option')
          option.value = img
          option.textContent = img
          dropdown.appendChild(option)
        })

        // Restore last selected image OR keep renamed file selected
        const storedImage = selectedImage || localStorage.getItem(`${isMovie ? 'mov' : 'sho'}-selected-image`)
        if (storedImage && [...dropdown.options].some(option => option.value === storedImage)) {
          dropdown.value = storedImage
          storeSelectedImage(isMovie) // Store in localStorage
        }

        generatePreview(isMovie)
      })
      .catch(error => {
        console.error('Error loading images:', error)
        showToast('error', 'Failed to load available images.')
      })
  }

  function getSelectedOverlays (isMovie) {
    const overlayContainer = isMovie ? document.getElementById('movieOverlays') : document.getElementById('showOverlays')
    const overlayPrefix = isMovie ? 'mov-' : 'sho-'
    const selectedOverlays = []

    overlayContainer.querySelectorAll('input.form-check-input:checked').forEach(input => {
      if (input.id.startsWith(overlayPrefix)) {
        selectedOverlays.push(input.name)
      }
    })

    return selectedOverlays
  }

  window.generatePreview = function (isMovie) {
    const selectedImage = isMovie ? movieDropdown.value : showDropdown.value
    let selectedOverlays = getSelectedOverlays(isMovie)

    // Remove old rating before adding a new one
    const overlayContainer = isMovie ? document.getElementById('movieOverlays') : document.getElementById('showOverlays')
    const selectedRating = overlayContainer.querySelector("input[type='radio']:checked")

    if (selectedRating) {
      selectedOverlays.push(selectedRating.value)
    } else {
      // Ensure the last content rating is removed if none are selected
      selectedOverlays = selectedOverlays.filter(overlay => !overlay.startsWith('content_rating'))
    }

    fetch('/generate_preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        overlays: selectedOverlays,
        type: isMovie ? 'movie' : 'show',
        selected_image: selectedImage
      })
    })
      .then(response => response.json())
      .then(data => {
        if (data.status === 'success') {
          const newPreviewURL = `/config/previews/${isMovie ? 'movie' : 'show'}_preview.png?t=` + new Date().getTime()
          const previewImage = isMovie ? moviePreviewImage : showPreviewImage
          previewImage.src = newPreviewURL
        }
      })
      .catch(error => console.error('Error generating preview:', error))
  }

  function storeSelectedImage (isMovie) {
    const selectedImage = isMovie ? movieDropdown.value : showDropdown.value
    localStorage.setItem(`${isMovie ? 'mov' : 'sho'}-selected-image`, selectedImage)
  }

  function deleteCustomImage (isMovie) {
    const dropdown = isMovie ? movieDropdown : showDropdown
    const selectedImage = dropdown.value

    if (!selectedImage || selectedImage === 'default') {
      console.warn('No image selected for deletion.')
      showToast('warning', 'Please select an image before deleting.')
      return
    }

    fetch(`/delete_library_image/${encodeURIComponent(selectedImage)}?type=${isMovie ? 'movie' : 'show'}`, {
      method: 'DELETE'
    })
      .then(response => response.json())
      .then(data => {
        showToast(data.status === 'success' ? 'success' : 'error', data.message)
        loadAvailableImages(isMovie)
      })
      .catch(error => {
        console.error('Error deleting image:', error)
        showToast('error', 'Failed to delete image.')
      })
  }

  function uploadLibraryImage (isMovie) {
    const fileInput = document.getElementById(isMovie ? 'mov-upload-library-image' : 'sho-upload-library-image')
    if (!fileInput.files.length) {
      console.warn('No file selected for upload.')
      showToast('warning', 'Please select an image file to upload.')
      return
    }

    const formData = new FormData()
    formData.append('image', fileInput.files[0])
    formData.append('type', isMovie ? 'movie' : 'show')

    fetch('/upload_library_image', {
      method: 'POST',
      body: formData
    })
      .then(response => response.json())
      .then(data => {
        showToast(data.status === 'success' ? 'success' : 'error', data.message)
        loadAvailableImages(isMovie)
      })
      .catch(error => {
        console.error('Upload error:', error)
        showToast('error', 'Failed to upload image.')
      })
  }

  function fetchLibraryImage (isMovie) {
    const urlInput = document.getElementById(isMovie ? 'mov-image-url' : 'sho-image-url')
    const url = urlInput.value
    if (!url) {
      console.warn('No URL provided.')
      showToast('warning', 'Please enter an image URL.')
      return
    }

    fetch('/fetch_library_image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, type: isMovie ? 'movie' : 'show' })
    })
      .then(response => response.json())
      .then(data => {
        showToast(data.status === 'success' ? 'success' : 'error', data.message)
        loadAvailableImages(isMovie)
      })
      .catch(error => {
        console.error('Fetch error:', error)
        showToast('error', 'Failed to fetch image.')
      })
  }

  // ✅ Bind event listeners correctly
  document.getElementById('mov-delete-image-btn').addEventListener('click', () => deleteCustomImage(true))
  document.getElementById('sho-delete-image-btn').addEventListener('click', () => deleteCustomImage(false))
  document.getElementById('mov-upload-btn').addEventListener('click', () => uploadLibraryImage(true))
  document.getElementById('sho-upload-btn').addEventListener('click', () => uploadLibraryImage(false))
  document.getElementById('mov-fetch-url-btn').addEventListener('click', () => fetchLibraryImage(true))
  document.getElementById('sho-fetch-url-btn').addEventListener('click', () => fetchLibraryImage(false))

  movieDropdown.addEventListener('change', function () {
    storeSelectedImage(true)
    generatePreview(true)
  })

  showDropdown.addEventListener('change', function () {
    storeSelectedImage(false)
    generatePreview(false)
  })

  // Attach event listeners to rename buttons
  document.getElementById('mov-rename-image').addEventListener('click', function () {
    renameSelectedImage(true)
  })

  document.getElementById('sho-rename-image').addEventListener('click', function () {
    renameSelectedImage(false)
  })

  document.querySelectorAll('#movieOverlays input, #showOverlays input').forEach(input => {
    input.addEventListener('change', function () {
      generatePreview(this.id.startsWith('mov-'))
    })
  })

  // Attach event listeners to checkboxes, radio buttons, and dropdowns
  document.querySelectorAll("input[type='checkbox'], input[type='radio'], select").forEach((input) => {
    input.addEventListener('change', updateAccordionHighlights)
  })

  // Run on page load to update any previously selected items
  loadAvailableImages(true)
  loadAvailableImages(false)
  updateAccordionHighlights()
  updateValidationState()
})

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

  // Separator Preview Elements
  const separatorPreviewContainer = document.getElementById(`${prefix}-separatorPreviewContainer`)
  const separatorPreviewImage = document.getElementById(`${prefix}-separatorPreviewImage`)

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

  // **Fetch Separator Style**
  const selectedStyle = selectedValue || 'none'

  sepStyleInput.value = isEnabled ? selectedStyle : ''

  // **Update Separator Preview Image**
  function updateSeparatorPreview () {
    if (selectedStyle !== 'none') {
      const imageUrl = `https://github.com/Kometa-Team/Default-Images/blob/master/separators/${selectedStyle}/chart.jpg?raw=true`
      separatorPreviewImage.src = imageUrl
      separatorPreviewContainer.style.display = 'block'
    } else {
      separatorPreviewContainer.style.display = 'none'
    }
  }

  updateSeparatorPreview() // Update on load
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

  updateValidationState() // Ensure validation updates on form submission
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
    updateValidationState() // Ensure validation updates when checkboxes change
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

      const isMovie = this.id.startsWith('mov-') // Determine if it's a movie or show
      const wasChecked = this.dataset.wasChecked === 'true'

      if (wasChecked) {
        this.checked = false // Allow unchecking the radio button
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
      }

      // Force `generatePreview()` to run regardless of select/unselect
      generatePreview(isMovie)
    })

    radio.addEventListener('change', function () {
      const isMovie = this.id.startsWith('mov-')
      generatePreview(isMovie)
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
