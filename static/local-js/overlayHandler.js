/* global EventHandler */

const OverlayHandler = {
  initializeOverlays: function (libraryId, isMovie) {
    console.log(`[DEBUG] Initializing overlays for ${libraryId} - ${isMovie ? 'Movie' : 'Show'}`)

    // Attach event listener for separator dropdown
    const fieldId = `${libraryId}-template_variables[use_separator]`
    const separatorDropdown = document.querySelector(`[name="${fieldId}"]`)

    if (separatorDropdown && !separatorDropdown.dataset.listenerAdded) {
      separatorDropdown.addEventListener('change', () => {
        const selectedStyle = separatorDropdown.value !== 'none'
        OverlayHandler.updateSeparatorToggles(libraryId, selectedStyle)
        OverlayHandler.updateSeparatorPreview(fieldId, separatorDropdown.value)
        OverlayHandler.toggleImdbPlaceholder(libraryId, isMovie ? 'movie' : 'show', selectedStyle)
        OverlayHandler.updateHiddenInputs(libraryId, isMovie)
        EventHandler.updateAccordionHighlights()
      })

      separatorDropdown.dataset.listenerAdded = true

      // Apply separator logic on initial page load
      const initialSelected = separatorDropdown.value !== 'none'
      OverlayHandler.updateSeparatorToggles(libraryId, initialSelected)
      OverlayHandler.updateSeparatorPreview(fieldId, separatorDropdown.value)
      OverlayHandler.toggleImdbPlaceholder(libraryId, isMovie ? 'movie' : 'show', initialSelected)
      OverlayHandler.updateHiddenInputs(libraryId, isMovie)
      EventHandler.updateAccordionHighlights()
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

  updateSeparatorPreview: function (fieldId, selectedStyle) {
    console.log(`[DEBUG] Updating Separator Preview for ${fieldId} - Style: ${selectedStyle}`)

    const safeId = fieldId.replace('[', '_').replace(']', '')
    const containerId = `${safeId}-separatorPreviewContainer`
    const imageId = `${safeId}-separatorPreviewImage`

    const separatorPreviewContainer = document.getElementById(containerId)
    const separatorPreviewImage = document.getElementById(imageId)

    if (!separatorPreviewContainer || !separatorPreviewImage) {
      console.error(`[ERROR] Separator preview elements missing for ${fieldId}`)
      return
    }

    if (selectedStyle && selectedStyle !== 'none') {
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

    const useSeparatorsDropdown = document.querySelector(`[name="${libraryId}-template_variables[use_separator]"]`)
    let useSeparatorsInput = document.getElementById(`${libraryId}-template_variables_use_separator`)
    let sepStyleInput = document.getElementById(`${libraryId}-template_variables_sep_style`)

    const awardSeparatorToggle = document.getElementById(`${libraryId}-collection_separator_award`)
    const chartSeparatorToggle = document.getElementById(`${libraryId}-collection_separator_chart`)

    const awardTogglesChecked = document.querySelectorAll(`[id^="${libraryId}-awardCollectionsAccordion"] input[type="checkbox"]:checked`).length > 0
    const chartTogglesChecked = document.querySelectorAll(`[id^="${libraryId}-chartCollectionsAccordion"] input[type="checkbox"]:checked`).length > 0

    const selectedValue = useSeparatorsDropdown.value
    const isEnabled = selectedValue !== 'none'

    // Clear IMDb placeholder selection if separator is disabled
    if (!isEnabled) {
      const imdbDropdown = document.querySelector(`#${libraryId}-attribute_template_variables_placeholder_imdb_id`)
      if (imdbDropdown) {
        imdbDropdown.value = ''
        const optionsToRemove = [...imdbDropdown.options].slice(1) // skip the first option
        optionsToRemove.forEach(opt => imdbDropdown.remove(opt.index))
      }
    }

    // Create hidden inputs dynamically if missing
    if (!useSeparatorsInput) {
      useSeparatorsInput = document.createElement('input')
      useSeparatorsInput.type = 'hidden'
      useSeparatorsInput.name = `${libraryId}-template_variables[use_separator]`
      useSeparatorsInput.id = `${libraryId}-template_variables_use_separator`
      form.appendChild(useSeparatorsInput)
    }

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

    const fieldId = `${libraryId}-template_variables[use_separator]`
    OverlayHandler.updateSeparatorPreview(fieldId, selectedValue)
  },

  toggleImdbPlaceholder: function (libraryId, mediaType, show) {
    const dropdown = document.getElementById(`${libraryId}-attribute_template_variables_placeholder_imdb_id`)
    if (!dropdown) {
      console.error(`[ERROR] IMDb dropdown not found for libraryId: ${libraryId}`)
      return
    }

    const libraryName = dropdown.dataset.libraryId
    const imdbBlock = document.querySelector(`.imdb-placeholder-wrapper[data-library-id="${libraryName}"]`)
    if (!imdbBlock) {
      console.error(`[ERROR] IMDb block not found for libraryName: ${libraryName}`)
      return
    }

    if (show) {
      imdbBlock.classList.remove('visually-hidden')
      const currentValue = dropdown.value
      OverlayHandler.populateImdbDropdown(dropdown, libraryName, mediaType, currentValue)
    } else {
      imdbBlock.classList.add('visually-hidden')
    }
  },

  populateImdbDropdown: function (dropdown, libraryName, mediaType, placeholderId = '') {
    console.log(`[DEBUG] Fetching top IMDb items for "${libraryName}" (type=${mediaType})`)

    const url = `/get_top_imdb_items/${encodeURIComponent(libraryName)}?type=${mediaType}` + (placeholderId ? `&placeholder_id=${placeholderId}` : '')

    fetch(url)
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          // Clear existing options
          dropdown.innerHTML = ''

          // Add "None" option
          const noneOption = document.createElement('option')
          noneOption.value = ''
          noneOption.textContent = 'None'
          dropdown.appendChild(noneOption)

          // Add items
          data.items.forEach(item => {
            const option = document.createElement('option')
            option.value = item.id
            option.textContent = `${item.title} (${item.id})`
            dropdown.appendChild(option)
          })

          // Insert saved placeholder item if returned separately
          if (data.saved_item) {
            const savedOption = document.createElement('option')
            savedOption.value = data.saved_item.id
            savedOption.textContent = `${data.saved_item.title} (${data.saved_item.id}) (Not in Top 25)`
            dropdown.appendChild(savedOption)
          }

          // Restore previous selection
          dropdown.value = placeholderId || ''
        } else {
          console.warn(`Failed to load IMDb titles for ${libraryName}:`, data.message)
        }
      })
      .catch(err => {
        console.error(`IMDb fetch failed for ${libraryName}:`, err)
      })
  }

}

document.addEventListener('DOMContentLoaded', function () {
  const imdbDropdowns = document.querySelectorAll('.placeholder-imdb-dropdown')

  imdbDropdowns.forEach(dropdown => {
    const libraryId = dropdown.id.split('-attribute_template_variables')[0]
    const isMovie = dropdown.dataset.libraryType === 'movie'
    const libraryName = dropdown.dataset.libraryId // Movies / TestMovies etc.

    // 1. Initialize separator overlay logic
    OverlayHandler.initializeOverlays(libraryId, isMovie)

    // 2. Populate IMDb Dropdown immediately
    const currentValue = dropdown.value // current selected tt######
    OverlayHandler.populateImdbDropdown(dropdown, libraryName, isMovie ? 'movie' : 'show', currentValue)
  })
})
