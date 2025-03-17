/* global EventHandler */

const OverlayHandler = {
  initializeOverlays: function (libraryId, isMovie) {
    console.log(`[DEBUG] Initializing overlays for ${libraryId} - ${isMovie ? 'Movie' : 'Show'}`)

    // Attach event listener for separator dropdown
    const separatorDropdown = document.getElementById(`${libraryId}-attribute_use_separators`)
    if (separatorDropdown && !separatorDropdown.dataset.listenerAdded) {
      separatorDropdown.addEventListener('change', () => {
        const selectedStyle = separatorDropdown.value !== 'none'
        OverlayHandler.updateSeparatorToggles(libraryId, selectedStyle)
        OverlayHandler.updateSeparatorPreview(libraryId, separatorDropdown.value)
        EventHandler.updateAccordionHighlights()
      })
      separatorDropdown.dataset.listenerAdded = true

      // Apply separator toggle logic on page load
      OverlayHandler.updateSeparatorToggles(libraryId, separatorDropdown.value !== 'none')
      OverlayHandler.updateSeparatorPreview(libraryId, separatorDropdown.value)
      EventHandler.updateAccordionHighlights() // Apply green bar updates on load
    }
  },

  /**
     * Enable/Disable Award & Chart Separator Toggles Based on Separator Style Selection
     */
  updateSeparatorToggles: function (libraryId, isEnabled) {
    console.log(`[DEBUG] Updating Separator Toggles for ${libraryId} - Enabled: ${isEnabled}`)

    const awardToggle = document.getElementById(`${libraryId}-collection_separator_award`)
    const chartToggle = document.getElementById(`${libraryId}-collection_separator_chart`)

    if (awardToggle) {
      awardToggle.disabled = !isEnabled
      awardToggle.checked = isEnabled
      console.log(`[DEBUG] Award Separator Toggle is now ${isEnabled ? 'ENABLED' : 'DISABLED'}`)
    }

    if (chartToggle) {
      chartToggle.disabled = !isEnabled
      chartToggle.checked = isEnabled
      console.log(`[DEBUG] Chart Separator Toggle is now ${isEnabled ? 'ENABLED' : 'DISABLED'}`)
    }
  },

  updateSeparatorPreview: function (libraryId, selectedStyle) {
    console.log(`[DEBUG] Updating Separator Preview for ${libraryId} - Style: ${selectedStyle}`)
    const separatorPreviewContainer = document.getElementById(`${libraryId}-separatorPreviewContainer`)
    const separatorPreviewImage = document.getElementById(`${libraryId}-separatorPreviewImage`)

    if (!separatorPreviewContainer || !separatorPreviewImage) {
      console.error(`[ERROR] Separator preview elements missing for ${libraryId}`)
      return
    }

    if (selectedStyle !== 'none') {
      const imageUrl = `https://github.com/Kometa-Team/Default-Images/blob/master/separators/${selectedStyle}/chart.jpg?raw=true`
      separatorPreviewImage.src = imageUrl
      separatorPreviewContainer.style.display = 'block'
      console.log(`[DEBUG] Separator preview updated to: ${imageUrl}`)
    } else {
      separatorPreviewContainer.style.display = 'none'
    }
  },

  updateHiddenInputs: function (libraryId, isMovie) {
    console.log(`[DEBUG] Updating hidden inputs for Library: ${libraryId} - ${isMovie ? 'Movies' : 'Shows'}`)

    const form = document.getElementById('configForm')
    if (!form) {
      console.error("[ERROR] Form element 'configForm' not found!")
      return
    }

    const useSeparatorsDropdown = document.getElementById(`${libraryId}-attribute_use_separators`)
    let useSeparatorsInput = document.getElementById(`${libraryId}-template_variables_use_separators`)
    let sepStyleInput = document.getElementById(`${libraryId}-template_variables_sep_style`)

    const awardSeparatorToggle = document.getElementById(`${libraryId}-collection_separator_award`)
    const chartSeparatorToggle = document.getElementById(`${libraryId}-collection_separator_chart`)

    const awardTogglesChecked = document.querySelectorAll(`[id^="${libraryId}-awardCollectionsAccordion"] input[type="checkbox"]:checked`).length > 0
    const chartTogglesChecked = document.querySelectorAll(`[id^="${libraryId}-chartCollectionsAccordion"] input[type="checkbox"]:checked`).length > 0

    const selectedValue = useSeparatorsDropdown.value
    const isEnabled = selectedValue !== 'none'

    // Create hidden inputs dynamically if missing
    if (!useSeparatorsInput) {
      useSeparatorsInput = document.createElement('input')
      useSeparatorsInput.type = 'hidden'
      useSeparatorsInput.name = `${libraryId}-template_variables[use_separators]`
      useSeparatorsInput.id = `${libraryId}-template_variables_use_separators`
      form.appendChild(useSeparatorsInput)
    }
    useSeparatorsInput.value = isEnabled ? 'true' : 'false'

    if (!sepStyleInput) {
      sepStyleInput = document.createElement('input')
      sepStyleInput.type = 'hidden'
      sepStyleInput.name = `${libraryId}-template_variables[sep_style]`
      sepStyleInput.id = `${libraryId}-template_variables_sep_style`
      form.appendChild(sepStyleInput)
    }
    sepStyleInput.value = isEnabled ? selectedValue : ''

    if (awardSeparatorToggle) {
      awardSeparatorToggle.disabled = !isEnabled || !awardTogglesChecked
      awardSeparatorToggle.checked = isEnabled && awardTogglesChecked
    }

    if (chartSeparatorToggle) {
      chartSeparatorToggle.disabled = !isEnabled || !chartTogglesChecked
      chartSeparatorToggle.checked = isEnabled && chartTogglesChecked
    }

    OverlayHandler.updateSeparatorPreview(libraryId, selectedValue)
  }

}
