/* global MutationObserver, ImageHandler, OverlayHandler, ValidationHandler */

const EventHandler = {
  attachLibraryListeners: function () {
    document.querySelectorAll('.library-checkbox').forEach((checkbox) => {
      const libraryId = checkbox.id.replace(/-(library|card-container)$/, '')

      console.log(`[DEBUG] Attaching toggle listener for Library: ${libraryId}`)

      // ✅ Attach event listener to each checkbox
      checkbox.addEventListener('change', () => {
        EventHandler.toggleLibraryVisibility(libraryId, checkbox.checked)
        ValidationHandler.updateValidationState() // ✅ Run validation when a library is selected/unselected
      })

      // ✅ Ensure libraries are HIDDEN by default on first entry
      if (!checkbox.checked) {
        EventHandler.toggleLibraryVisibility(libraryId, false)
      }
    })

    document.querySelectorAll("[id$='-card-container']").forEach((library) => {
      const libraryId = library.id.replace('-card-container', '')
      const isMovie = libraryId.startsWith('mov')

      console.log(`[DEBUG] Attaching listeners for Library: ${libraryId}, Type: ${isMovie ? 'Movie' : 'Show'}`)
      ImageHandler.loadAvailableImages(libraryId, isMovie)
      OverlayHandler.initializeOverlays(libraryId, isMovie) // 🚀 Now handled in overlayHandler.js

      // ✅ Attach dropdown change listener for main library image
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

      // ✅ Attach Fetch & Upload button listeners
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

      // ✅ Attach overlay selection listeners
      library.querySelectorAll('.accordion input').forEach((input) => {
        if (input.id && !input.dataset.listenerAdded) {
          console.log(`[DEBUG] Attaching overlay listener for ${input.id}`)
          input.addEventListener('change', () => {
            console.log(`[DEBUG] Overlay changed: ${input.id}`)

            // 🚀 Exclude preview overlay accordions from highlight updates
            if (!input.closest('.preview-accordion')) {
              EventHandler.updateAccordionHighlights()
              ValidationHandler.updateValidationState() // ✅ Run validation when a toggle is changed
            }
          })
          input.dataset.listenerAdded = true
        }
      })

      // ✅ Attach separator preview logic (Now handled by OverlayHandler)
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
     * Updates accordion highlights when items are selected (EXCLUDES Preview Overlays)
     */
  updateAccordionHighlights: function () {
    document.querySelectorAll('.accordion-item').forEach((accordion) => {
      const isPreview = accordion.classList.contains('preview-accordion')
      if (isPreview) return // 🚀 Skip preview accordions

      const isCheckedOrSelected = accordion.querySelector(
        "input[type='checkbox']:checked, input[type='radio']:checked, select option:checked:not([value='']):not([value='none'])"
      ) !== null

      const accordionHeader = accordion.querySelector('.accordion-header')

      if (isCheckedOrSelected) {
        EventHandler.highlightParentAccordions(accordionHeader)
      } else {
        EventHandler.removeHighlightIfEmpty(accordionHeader)
      }
    })
  },

  highlightParentAccordions: function (element) {
    while (element) {
      if (element.classList.contains('accordion-header')) {
        element.classList.add('selected')
      }
      element = element.closest('.accordion-item')?.parentElement.closest('.accordion-item')?.querySelector('.accordion-header')
    }
  },

  removeHighlightIfEmpty: function (element) {
    if (!element) return
    const accordionItem = element.closest('.accordion-item')
    if (!accordionItem) return

    const hasSelections = accordionItem.querySelector(
      "input[type='checkbox']:checked, input[type='radio']:checked, select option:checked:not([value='']):not([value='none'])"
    )

    if (!hasSelections) {
      element.classList.remove('selected')
    }

    const parentAccordionHeader = accordionItem.parentElement.closest('.accordion-item')?.querySelector('.accordion-header')
    EventHandler.removeHighlightIfEmpty(parentAccordionHeader)
  }
}

// ✅ MutationObserver for dynamically added elements
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
    EventHandler.attachLibraryListeners()
  }
})

observer.observe(document.body, { childList: true, subtree: true })

// ✅ Initial call on page load
document.addEventListener('DOMContentLoaded', () => {
  console.log('[DEBUG] Initializing EventHandler...')
  EventHandler.attachLibraryListeners()
  ValidationHandler.updateValidationState()
})
