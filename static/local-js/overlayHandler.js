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
      // Only depend on sep_style being set to enable/disable
      awardSeparatorToggle.disabled = !isEnabled
      awardSeparatorToggle.checked = isEnabled
    }

    if (chartSeparatorToggle) {
      // Only depend on sep_style being set to enable/disable
      chartSeparatorToggle.disabled = !isEnabled
      chartSeparatorToggle.checked = isEnabled
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
    const libraryName = dropdown.dataset.libraryId

    // 1. Initialize overlay dropdowns and separator preview
    OverlayHandler.initializeOverlays(libraryId, isMovie)

    // 2. Populate IMDb dropdown options
    const currentValue = dropdown.value
    OverlayHandler.populateImdbDropdown(dropdown, libraryName, isMovie ? 'movie' : 'show', currentValue)
  })

  // 3. Sync parent/child toggle checked state
  setupParentChildToggleSync()

  // 4. Toggle child wrapper visibility for both collections and overlays
  document.querySelectorAll('input[data-template-group]').forEach(parent => {
    const parentId = parent.id
    const childWrapper = document.querySelector(`.child-toggle-wrapper[data-toggle-parent="${parentId}"]`)
    if (!childWrapper) return

    // Initial visibility
    childWrapper.style.display = parent.checked ? '' : 'none'

    // Toggle visibility on change
    parent.addEventListener('change', () => {
      childWrapper.style.display = parent.checked ? '' : 'none'
    })
  })
})

// eslint-disable-next-line no-unused-vars
function setupParentChildToggleSync () {
  let syncing = false

  const parents = document.querySelectorAll('.template-parent-toggle')

  parents.forEach(parent => {
    const groupId = parent.dataset.templateGroup
    const wrapper = document.querySelector(`[data-toggle-parent="${groupId}"]`)
    const isRadioStyle = parent.type === 'radio' || parent.dataset.radioGroup === 'true'

    const groupName = parent.name
    const childToggles = wrapper?.querySelectorAll('.template-child-toggle') || []

    parent.addEventListener('click', () => {
      if (syncing) return
      syncing = true

      const isChecked = parent.checked

      if (isRadioStyle) {
        const groupParents = document.querySelectorAll(`input[name="${groupName}"]`)

        groupParents.forEach(other => {
          if (other !== parent) {
            other.checked = false
            other.dataset.wasChecked = 'false'

            const otherWrapper = document.querySelector(`[data-toggle-parent="${other.dataset.templateGroup}"]`)
            const otherChildren = otherWrapper?.querySelectorAll('.template-child-toggle') || []
            otherChildren.forEach(child => {
              child.checked = false
              child.dispatchEvent(new Event('change', { bubbles: true }))
            })
            if (otherWrapper) otherWrapper.style.display = 'none'
          }
        })

        if (isChecked && parent.dataset.wasChecked === 'true') {
          // Toggle OFF previously checked pseudo-radio
          parent.checked = false
          parent.dataset.wasChecked = 'false'
          if (wrapper) wrapper.style.display = 'none'
          childToggles.forEach(child => {
            child.checked = false
            child.dispatchEvent(new Event('change', { bubbles: true }))
          })
        } else {
          parent.dataset.wasChecked = 'true'
          if (wrapper) wrapper.style.display = ''
          childToggles.forEach(child => {
            child.checked = true
            child.dispatchEvent(new Event('change', { bubbles: true }))
          })
        }

        // Always sync hidden input after processing toggle group
        setTimeout(() => {
          const groupToggles = document.querySelectorAll(`input[name="${groupName}"][data-radio-group="true"]`)
          const anyChecked = Array.from(groupToggles).some(t => t.checked)
          const selectedToggle = Array.from(groupToggles).find(t => t.checked)
          const hidden = document.querySelector(`input[type="hidden"][name="${groupName}"]`)
          if (hidden) {
            hidden.value = anyChecked ? (selectedToggle?.value || '') : ''
            console.debug(`[SYNC] Hidden input for ${groupName} = "${hidden.value}"`)
          }
        }, 0)
      }

      syncing = false
    })

    // Sync back from children
    childToggles.forEach(child => {
      child.addEventListener('change', () => {
        if (syncing) return
        syncing = true

        const anyChecked = Array.from(childToggles).some(c => c.checked)
        parent.checked = anyChecked
        if (wrapper) wrapper.style.display = anyChecked ? '' : 'none'

        if (!anyChecked && isRadioStyle) {
          parent.dataset.wasChecked = 'false'

          // Clear hidden if no toggle remains selected
          setTimeout(() => {
            const groupToggles = document.querySelectorAll(`input[name="${groupName}"][data-radio-group="true"]`)
            const anyLeftChecked = Array.from(groupToggles).some(t => t.checked)
            const hidden = document.querySelector(`input[type="hidden"][name="${groupName}"]`)
            if (hidden) {
              hidden.value = anyLeftChecked ? (Array.from(groupToggles).find(t => t.checked)?.value || '') : ''
              console.debug(`[SYNC] Hidden input for ${groupName} = "${hidden.value}"`)
            }
          }, 0)
        }

        syncing = false
      })
    })
  })
}
