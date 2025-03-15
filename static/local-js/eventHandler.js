/* global MutationObserver, ImageHandler, OverlayHandler, ValidationHandler */

const EventHandler = {
  attachLibraryListeners: function () {
    document.querySelectorAll('.library-checkbox').forEach((checkbox) => {
      const libraryId = checkbox.id.replace(/-(library|card-container)$/, '')

      console.log(`[DEBUG] Attaching toggle listener for Library: ${libraryId}`)

      // Attach event listener to each checkbox
      checkbox.addEventListener('change', () => {
        EventHandler.toggleLibraryVisibility(libraryId, checkbox.checked)
        ValidationHandler.updateValidationState()
      })

      // Ensure libraries are HIDDEN by default on first entry
      if (!checkbox.checked) {
        EventHandler.toggleLibraryVisibility(libraryId, false)
      }
    })

    document.querySelectorAll("[id$='-card-container']").forEach((library) => {
      const libraryId = library.id.replace('-card-container', '')
      const isMovie = libraryId.startsWith('mov-library_')

      console.log(`[DEBUG] Attaching listeners for Library: ${libraryId}, Type: ${isMovie ? 'Movie' : 'Show'}`)
      ImageHandler.loadAvailableImages(libraryId, isMovie)
      OverlayHandler.initializeOverlays(libraryId, isMovie) // 🚀 Now handled in overlayHandler.js

      // Attach dropdown change listener for main library image
      library.querySelectorAll("[id$='-image-dropdown']").forEach((dropdown) => {
        if (!dropdown.dataset.listenerAdded) {
          console.log(`[DEBUG] Attaching dropdown listener for ${dropdown.id}`)
          dropdown.addEventListener('change', () => {
            console.log(`[DEBUG] Dropdown changed: ${dropdown.id}`)
            ImageHandler.generatePreview(libraryId, isMovie)
            ImageHandler.toggleDeleteButton(libraryId, isMovie)
          })
          dropdown.dataset.listenerAdded = true
        }
      })

      // Attach Fetch & Upload button listeners
      const fetchButton = document.getElementById(`${libraryId}-fetch-url-btn`)
      if (fetchButton && !fetchButton.dataset.listenerAdded) {
        console.log(`[DEBUG] Attaching fetch listener for ${libraryId}`)
        fetchButton.addEventListener('click', () => {
          ImageHandler.fetchLibraryImage(libraryId, isMovie)
        })
        fetchButton.dataset.listenerAdded = true
      }

      const uploadButton = document.getElementById(`${libraryId}-upload-image`)
      if (uploadButton && !uploadButton.dataset.listenerAdded) {
        console.log(`[DEBUG] Attaching upload listener for ${libraryId}`)
        uploadButton.addEventListener('change', (event) => {
          if (event.target.files.length > 0) {
            console.log(`[DEBUG] File selected, starting upload for ${libraryId}`)
            ImageHandler.uploadLibraryImage(libraryId, isMovie)
          } else {
            console.log('[DEBUG] No file selected, upload not triggered.')
          }
        })
        uploadButton.dataset.listenerAdded = true
      }

      // Attach overlay selection listeners
      library.querySelectorAll('.accordion input').forEach((input) => {
        if (input.id && !input.dataset.listenerAdded) {
          console.log(`[DEBUG] Attaching toggle listener for ${input.id}`)
          input.addEventListener('change', () => {
            console.log(`[DEBUG] Overlay changed: ${input.id}`)

            // 🚀 Exclude preview overlay accordions from highlight updates
            if (!input.closest('.preview-accordion')) {
              EventHandler.updateAccordionHighlights()
              ValidationHandler.updateValidationState() // Run validation when a toggle is changed
            }
          })
          input.dataset.listenerAdded = true
        }
      })

      // tach attribute_reset_overlays listeners
      document.querySelectorAll("[id$='-attribute_reset_overlays']").forEach(dropdown => {
        if (!dropdown.dataset.listenerAdded) {
          console.log(`[DEBUG] Attaching change listener for Reset Overlays: ${dropdown.id}`)

          dropdown.addEventListener('change', function () {
            console.log(`[DEBUG] Reset Overlays dropdown changed: ${this.id} -> ${this.value}`)

            // Ensure Highlights Update Properly
            EventHandler.updateAccordionHighlights()
            ValidationHandler.updateValidationState()
          })

          dropdown.dataset.listenerAdded = 'true'
        }
      })

      // Allow unselecting Content Rating radio buttons
      document.querySelectorAll('input[type="radio"][id*="-overlay_content_rating_"]').forEach(radio => {
        if (!radio.dataset.listenerAdded) {
          radio.addEventListener('click', function () {
            console.log(`[DEBUG] Radio button clicked: ${this.name} -> ${this.value}`)

            // Extract libraryId strictly from content rating radios only
            const match = this.id.match(/^(mov|sho)-library_([^-]+(?:-[^-]+)*)-overlay_content_rating_/)
            const libraryId = match ? match[0].replace('-overlay_content_rating_', '') : null
            if (!libraryId) {
              console.warn(`[WARNING] Could not determine libraryId from ${this.id}`)
              return
            }
            const isMovie = libraryId.startsWith('mov-library_')

            if (this.checked && this.dataset.wasChecked === 'true') {
              // Unselect if clicked again
              this.checked = false
              this.dataset.wasChecked = 'false'

              // Clear corresponding hidden input
              const hiddenInput = document.querySelector(`input[name="${libraryId}-overlay_selected_content_rating"]`)
              if (hiddenInput) {
                hiddenInput.value = '' // Clear hidden input when unselected
              }

              console.log(`[DEBUG] Unselected radio button: ${this.name}`)
            } else {
              // Mark this radio as checked and reset others in the group
              document.querySelectorAll(`input[name="${this.name}"]`).forEach(r => {
                r.dataset.wasChecked = 'false'
              })
              this.dataset.wasChecked = 'true'

              const selectedValue = this.value

              // Update hidden input
              const hiddenInputName = `${libraryId}-overlay_selected_content_rating`
              const hiddenInput = document.querySelector(`input[name="${hiddenInputName}"]`)
              if (hiddenInput) {
                hiddenInput.value = selectedValue
              }

              console.log(`[DEBUG] Selected radio button: ${this.name} -> ${selectedValue}`)
            }

            // Ensure preview updates after selection/unselection
            EventHandler.updateAccordionHighlights()
            ValidationHandler.updateValidationState()
            ImageHandler.generatePreview(libraryId, isMovie)
          })

          radio.dataset.listenerAdded = 'true'
          radio.dataset.wasChecked = 'false' // Track the initial state
        }
      })

      // Automatically Update Preview When Overlay Toggles or Content Rating Changes
      library.querySelectorAll('.accordion input[type="checkbox"], .accordion input[type="radio"]').forEach(input => {
        input.addEventListener('change', () => {
          console.log(`[DEBUG] Overlay or Rating Changed: ${input.id} - Checked/Selected: ${input.checked || input.value}`)
          ImageHandler.generatePreview(libraryId, isMovie)
        })
      })

      // Attach separator preview logic (Now handled by OverlayHandler)
      const separatorDropdown = library.querySelector("[id$='-attribute_use_separators']")
      if (separatorDropdown && !separatorDropdown.dataset.listenerAdded) {
        console.log(`[DEBUG] Found separator dropdown: ${separatorDropdown.id}`)
        separatorDropdown.addEventListener('change', () => {
          OverlayHandler.updateHiddenInputs(libraryId, isMovie) // 🚀 Now delegated
        })
        separatorDropdown.dataset.listenerAdded = true
        OverlayHandler.updateHiddenInputs(libraryId, isMovie)
      }

      const deleteButton = document.getElementById(`${libraryId}-delete-image-btn`)
      if (deleteButton && !deleteButton.dataset.listenerAdded) {
        console.log(`[DEBUG] Attaching delete listener for ${libraryId}`)
        deleteButton.addEventListener('click', () =>
          ImageHandler.deleteCustomImage(libraryId, isMovie)
        )
        deleteButton.dataset.listenerAdded = true
      }

      const renameButton = document.getElementById(`${libraryId}-rename-image-btn`)
      if (renameButton && !renameButton.dataset.listenerAdded) {
        console.log(`[DEBUG] Attaching rename listener for ${libraryId}`)
        renameButton.addEventListener('click', () =>
          ImageHandler.openRenameModal(libraryId, isMovie)
        )
        renameButton.dataset.listenerAdded = true
      }
    })
  },

  /**
     * Show/Hide Library section based on toggle state
     */
  toggleLibraryVisibility: function (libraryId, isVisible) {
    const libraryContainer = document.getElementById(`${libraryId}-card-container`)

    if (!libraryContainer) {
      console.warn(`[WARNING] Library container not found: ${libraryId}-card-container`)
      return
    }

    libraryContainer.style.display = isVisible ? 'block' : 'none'
    console.log(`[DEBUG] Library ${libraryId} is now ${isVisible ? 'VISIBLE' : 'HIDDEN'}`)
  },

  /**
   * Update accordion highlights when selections change
   */
  updateAccordionHighlights: function () {
    console.log('🔍 [DEBUG] Updating accordion highlights...')

    document.querySelectorAll('.accordion-item').forEach((accordion) => {
      const accordionHeader = accordion.querySelector('.accordion-header')
      if (!accordionHeader) return

      const headerText = accordionHeader.textContent.trim()
      const isPreviewOverlay = headerText.toLowerCase().includes('preview overlays')

      // Skip Preview Overlays
      if (isPreviewOverlay) {
        console.log(`🚫 [DEBUG] Skipping Preview Overlays: ${headerText}`)
        accordionHeader.classList.remove('selected')
        return
      }

      // Check if this section has selected checkboxes, radios, or dropdowns
      const isCheckedOrSelected = accordion.querySelector(
        "input[type='checkbox']:checked, input[type='radio']:checked, select option:checked:not([value='']):not([value='none'])"
      ) !== null

      if (isCheckedOrSelected) {
        console.log(`✅ [DEBUG] Highlighting: ${headerText}`)
        accordionHeader.classList.add('selected')

        // Ensure the **IMMEDIATE PARENT** gets highlighted before moving up
        EventHandler.highlightParentAccordions(accordionHeader)
      } else {
        // console.log(`❌ [DEBUG] Removing highlight: ${headerText}`)
        EventHandler.removeHighlightIfEmpty(accordionHeader)
      }
    })

    // Ensure Overlays does NOT highlight if only Preview Overlays are active
    document.querySelectorAll('.accordion-item').forEach((accordion) => {
      const accordionHeader = accordion.querySelector('.accordion-header')
      if (!accordionHeader) return

      const headerText = accordionHeader.textContent.trim()
      const isOverlaysSection = headerText.toLowerCase() === 'overlays'

      if (isOverlaysSection) {
        console.log(`🔍 [DEBUG] Checking Overlays: ${headerText}`)

        // Ensure at least one non-preview child is active
        const hasValidChild = Array.from(accordion.querySelectorAll('.accordion-item')).some(child => {
          const childHeader = child.querySelector('.accordion-header')
          if (!childHeader) return false

          const childText = childHeader.textContent.trim()
          const isPreviewChild = childText.toLowerCase().includes('preview overlays')

          if (!isPreviewChild && child.querySelector("input:checked, input[type='radio']:checked")) {
            console.log(`✅ [DEBUG] Valid selection found under: ${childText}`)
            childHeader.classList.add('selected') // Ensure child is highlighted first
            return true
          }
          return false
        })

        if (!hasValidChild) {
          console.log(`🚫 [DEBUG] Overlays should NOT highlight: ${headerText}`)
          accordionHeader.classList.remove('selected')
        } else {
          console.log(`✅ [DEBUG] Highlighting Overlays: ${headerText}`)
          accordionHeader.classList.add('selected')
        }
      }
    })
  },

  /**
   * Highlight parent accordions when a child section is selected
   */
  highlightParentAccordions: function (element) {
    while (element) {
      const parentAccordion = element.closest('.accordion-item')
      if (!parentAccordion) break

      const parentHeader = parentAccordion.querySelector('.accordion-header')
      const parentText = parentHeader ? parentHeader.textContent.trim() : ''
      const isPreviewOverlay = parentText.toLowerCase().includes('preview overlays')
      const isOverlaysSection = parentText.toLowerCase().includes('overlays')

      if (isPreviewOverlay) {
        console.log(`🚫 [DEBUG] Skipping parent highlight for Preview Overlays: ${parentText}`)
        return // Prevent parent highlight inheritance from Preview Overlays
      }

      if (isOverlaysSection) {
        const hasValidChild = Array.from(parentAccordion.querySelectorAll('.accordion-item')).some(child => {
          const childHeader = child.querySelector('.accordion-header')
          const childText = childHeader ? childHeader.textContent.trim() : ''
          const isPreviewChild = childText.toLowerCase().includes('preview overlays')

          return !isPreviewChild && child.querySelector('input:checked') // Only highlight Overlays if non-preview children are checked
        })

        if (!hasValidChild) {
          console.log(`🚫 [DEBUG] Preventing Overlays from inheriting highlight due to only Preview Overlays: ${parentText}`)
          return // Stop if Overlays only contain Preview Overlays
        }
      }

      console.log(`🎯 [DEBUG] Adding highlight to parent: ${parentText}`)
      parentHeader.classList.add('selected')

      element = parentAccordion.parentElement.closest('.accordion-item')?.querySelector('.accordion-header')
    }
  },

  /**
   * Remove highlight if an accordion has no selections
   */
  removeHighlightIfEmpty: function (element) {
    if (!element) return
    const accordionItem = element.closest('.accordion-item')
    if (!accordionItem) return

    const accordionId = accordionItem.id || ''
    const isPreviewOverlay = accordionId.includes('-previewOverlays')

    if (isPreviewOverlay) {
      console.log(`🚫 [DEBUG] Preventing highlight removal check for Preview Overlays: ${accordionId}`)
      return // Do not allow Preview Overlays to trigger highlight removal
    }

    const hasSelections = accordionItem.querySelector(
      "input[type='checkbox']:checked, input[type='radio']:checked, select option:checked:not([value='']):not([value='none'])"
    )

    if (!hasSelections) {
      // console.log(`🔻 [DEBUG] Removing highlight from: ${accordionId}`)
      element.classList.remove('selected')
    }

    // Recursively check parents
    const parentAccordionHeader = accordionItem.parentElement.closest('.accordion-item')?.querySelector('.accordion-header')
    EventHandler.removeHighlightIfEmpty(parentAccordionHeader)
  }
}

// MutationObserver for dynamically added elements
const observer = new MutationObserver((mutations) => {
  let needsReattachment = false

  mutations.forEach((mutation) => {
    if (mutation.addedNodes.length > 0) {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === 1 && node.matches("[id$='-card-container'], .accordion input")) {
          console.log(`[DEBUG] New element detected: ${node.id || node.className}, triggering re-attachment.`)
          needsReattachment = true
        }
      })
    }
  })

  if (needsReattachment) {
    console.log('[DEBUG] Reattaching event listeners due to DOM mutation...')
    EventHandler.attachLibraryListeners()
  }
})

observer.observe(document.body, { childList: true, subtree: true })

// Initial call on page load
document.addEventListener('DOMContentLoaded', () => {
  console.log('[DEBUG] Initializing EventHandler...')

  // Run once on page load
  EventHandler.attachLibraryListeners()
  ValidationHandler.restoreSelectedLibraries()
  ValidationHandler.updateValidationState()
})
