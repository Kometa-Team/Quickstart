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
      // Load custom images based on type
      const types = isMovie ? ['movie'] : ['show', 'season', 'episode']
      types.forEach(type => {
        ImageHandler.loadAvailableImages(libraryId, type)

        const uploadInput = document.getElementById(`${libraryId}-${type}-upload-image`)
        if (uploadInput && !uploadInput.dataset.listenerAdded) {
          uploadInput.addEventListener('change', event => {
            if (event.target.files.length > 0) {
              console.log(`[DEBUG] Upload triggered for ${libraryId} - ${type}`)
              ImageHandler.uploadLibraryImage(libraryId, type)
            }
          })
          uploadInput.dataset.listenerAdded = 'true'
        }

        const dropdown = document.getElementById(`${libraryId}-${type}-image-dropdown`)
        if (dropdown && !dropdown.dataset.listenerAdded) {
          dropdown.addEventListener('change', () => {
            const selectedImage = dropdown.value || 'default'
            console.log(`[DEBUG] Dropdown changed: ${dropdown.id} -> ${selectedImage}`)

            const hiddenInput = document.getElementById(`${libraryId}-${type}_selected_image`)
            if (hiddenInput) {
              hiddenInput.value = selectedImage
              console.debug(`[SYNC] Updated hidden input: ${hiddenInput.id} = ${selectedImage}`)
            }

            ImageHandler.generateSinglePreview(libraryId, type)
            ImageHandler.toggleDeleteButton(libraryId, type)
          })
          dropdown.dataset.listenerAdded = 'true'
        }

        const fetchBtn = document.getElementById(`${libraryId}-${type}-fetch-url-btn`)
        if (fetchBtn && !fetchBtn.dataset.listenerAdded) {
          fetchBtn.addEventListener('click', () => {
            console.log(`[DEBUG] Fetch triggered for ${libraryId} - ${type}`)
            ImageHandler.fetchLibraryImage(libraryId, type)
          })
          fetchBtn.dataset.listenerAdded = 'true'
        }

        const deleteBtn = document.getElementById(`${libraryId}-${type}-delete-image-btn`)
        if (deleteBtn && !deleteBtn.dataset.listenerAdded) {
          deleteBtn.addEventListener('click', () => {
            ImageHandler.deleteCustomImage(libraryId, type)
          })
          deleteBtn.dataset.listenerAdded = 'true'
        }

        const renameBtn = document.getElementById(`${libraryId}-${type}-rename-image-btn`)
        if (renameBtn && !renameBtn.dataset.listenerAdded) {
          renameBtn.addEventListener('click', () => {
            ImageHandler.openRenameModal(libraryId, type)
          })
          renameBtn.dataset.listenerAdded = 'true'
        }
      })

      // Initialize overlays after image listeners
      OverlayHandler.initializeOverlays(libraryId, isMovie)

      // Allow unselecting Content Rating radio buttons
      library.querySelectorAll('input[type="radio"][id*="-overlay_content_rating_"]').forEach(radio => {
        if (!radio.dataset.listenerAdded) {
          radio.addEventListener('click', function () {
            console.log(`[DEBUG] Radio button clicked: ${this.name} -> ${this.value}`)

            // More reliable way to get libraryId from DOM
            const cardContainer = this.closest('.library-settings-card')
            const clickedLibraryId = cardContainer?.id?.replace('-card-container', '')
            if (!clickedLibraryId) {
              console.warn(`[WARNING] Could not determine libraryId from ${this.id}`)
              return
            }
            const isMovieRadio = clickedLibraryId.startsWith('mov-library_')

            if (this.checked && this.dataset.wasChecked === 'true') {
              // Unselect if clicked again
              this.checked = false
              this.dataset.wasChecked = 'false'

              // Clear corresponding hidden input
              const hiddenInput = document.querySelector(`input[name="${clickedLibraryId}-overlay_content_rating"]`)
              if (hiddenInput) {
                hiddenInput.value = ''
              }

              console.log(`[DEBUG] Unselected radio button: ${this.name}`)
            } else {
              // Reset all radios in group
              document.querySelectorAll(`input[name="${this.name}"]`).forEach(r => {
                r.dataset.wasChecked = 'false'
              })
              this.dataset.wasChecked = 'true'

              const selectedValue = this.value
              const hiddenInput = document.querySelector(`input[name="${clickedLibraryId}-overlay_content_rating"]`)
              if (hiddenInput) {
                hiddenInput.value = selectedValue
              }

              console.log(`[DEBUG] Selected radio button: ${this.name} -> ${selectedValue}`)
            }

            // Update UI and preview
            EventHandler.updateAccordionHighlights()
            ValidationHandler.updateValidationState()
            if (isMovieRadio) {
              ImageHandler.generateSinglePreview(clickedLibraryId, 'movie')
            } else {
              ['show', 'season', 'episode'].forEach(type => {
                ImageHandler.generateSinglePreview(clickedLibraryId, type)
              })
            }
          })

          radio.dataset.listenerAdded = 'true'
          radio.dataset.wasChecked = 'false'
        }
      })
      // Attach overlay selection listeners (CHANGE events)
      library.querySelectorAll('.accordion input').forEach((input) => {
        library.querySelectorAll('.accordion select').forEach(select => {
          if (!select.dataset.listenerAdded) {
            select.addEventListener('change', () => {
              console.log(`[DEBUG] Dropdown changed: ${select.id} -> ${select.value}`)
              EventHandler.updateAccordionHighlights()
              ValidationHandler.updateValidationState()

              // Trigger preview update if template variable
              if (select.classList.contains('template-variable-select')) {
                const nameParts = select.name.split('-')
                const libraryId = nameParts.slice(0, 2).join('-') // e.g., mov-library_movies
                const type = nameParts[2] // e.g., movie
                ImageHandler.generateSinglePreview(libraryId, type)
              }
            })
            select.dataset.listenerAdded = 'true'
          }
        })

        if (input.id && !input.dataset.listenerAdded) {
          console.log(`[DEBUG] Attaching toggle listener for ${input.id}`)
          input.addEventListener('change', () => {
            console.log(`[DEBUG] Overlay changed: ${input.id}`)

            // Exclude preview overlay accordions from highlight updates
            if (!input.closest('.preview-accordion')) {
              EventHandler.updateAccordionHighlights()
              ValidationHandler.updateValidationState()
            }
          })
          input.dataset.listenerAdded = true
        }
      })

      // Attach attribute_reset_overlays listeners
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

      // Automatically trigger preview updates when overlays are toggled or content rating changes
      library.querySelectorAll('input[type="checkbox"].overlay-toggle, input[type="radio"].overlay-toggle').forEach(input => {
        input.addEventListener('change', () => {
          console.log(`[DEBUG] Overlay toggle changed: ${input.id}`)
          const match = input.id.match(/-(movie|show|season|episode)-overlay_/)
          const inputType = match ? match[1] : (isMovie ? 'movie' : 'show')
          ImageHandler.generateSinglePreview(libraryId, inputType)
        })
      })

      // Attach separator preview logic (Now handled by OverlayHandler)
      const separatorDropdown = library.querySelector("[id$='-attribute_use_separator']")
      if (separatorDropdown && !separatorDropdown.dataset.listenerAdded) {
        console.log(`[DEBUG] Found separator dropdown: ${separatorDropdown.id}`)
        separatorDropdown.addEventListener('change', () => {
          OverlayHandler.updateHiddenInputs(libraryId, isMovie)
        })
        separatorDropdown.dataset.listenerAdded = true
        OverlayHandler.updateHiddenInputs(libraryId, isMovie)
      }

      // Attach listener for custom genre "Add" button
      const listBasedPrefixes = ['mass_genre_update', 'radarr_remove_by_tag', 'sonarr_remove_by_tag', 'metadata_backup']

      listBasedPrefixes.forEach(prefix => {
        console.log(`[DEBUG] Setting up list-based input for prefix: ${prefix} in ${libraryId}`)
        const customAddButton = document.getElementById(`${libraryId}-${prefix}_custom_add`)
        if (customAddButton && !customAddButton.dataset.listenerAdded) {
          console.log(`[DEBUG] Attaching custom string add listener for ${prefix} in ${libraryId}`)

          const customList = document.getElementById(`${libraryId}-${prefix}_custom_list`)
          const hiddenCustomInput = document.getElementById(`${libraryId}-${prefix}_custom_hidden`)

          if (hiddenCustomInput && customList) {
            try {
              const parsed = JSON.parse(hiddenCustomInput.value || '[]')
              const savedItems = Array.isArray(parsed) ? parsed.filter(Boolean) : []
              savedItems.forEach(value => {
                const li = document.createElement('li')
                li.className = 'list-group-item d-flex justify-content-between align-items-center'
                li.textContent = value

                const removeBtn = document.createElement('button')
                removeBtn.type = 'button'
                removeBtn.className = 'btn btn-sm btn-danger'
                removeBtn.innerHTML = '<i class="bi bi-x-lg"></i>'
                removeBtn.addEventListener('click', function () {
                  li.remove()
                  updateHiddenInput(customList, hiddenCustomInput)
                })

                li.appendChild(removeBtn)
                customList.appendChild(li)
              })
              hiddenCustomInput.value = JSON.stringify(savedItems)
            } catch (e) {
              console.warn(`[WARN] Could not parse saved custom list for ${prefix} in ${libraryId}:`, e)
              hiddenCustomInput.value = '[]'
            }
          }

          function updateHiddenInput (listElement, hiddenInput) {
            const values = Array.from(listElement.children).map(item =>
              item.firstChild.textContent.replace(/^"|"$/g, '')
            )
            hiddenInput.value = values.length ? JSON.stringify(values) : ''
          }

          customAddButton.addEventListener('click', function () {
            const input = document.getElementById(`${libraryId}-${prefix}_custom_input`)
            const list = document.getElementById(`${libraryId}-${prefix}_custom_list`)
            const hidden = document.getElementById(`${libraryId}-${prefix}_custom_hidden`)

            const value = input.value.trim()
            if (!value) return

            // Create the list item
            const li = document.createElement('li')
            li.className = 'list-group-item d-flex justify-content-between align-items-center'
            li.textContent = value

            const removeBtn = document.createElement('button')
            removeBtn.type = 'button'
            removeBtn.className = 'btn btn-sm btn-danger'
            removeBtn.innerHTML = '<i class="bi bi-x-lg"></i>'
            removeBtn.addEventListener('click', function () {
              li.remove()
              updateHiddenInput(list, hidden)
            })

            li.appendChild(removeBtn)
            list.appendChild(li)
            input.value = ''
            updateHiddenInput(list, hidden)
          })

          customAddButton.dataset.listenerAdded = 'true'
        }
      })

      // Rating range validation (0-10)
      library.querySelectorAll('input[data-validate="rating"]').forEach(input => {
        if (input.dataset.listenerAdded) return
        // Restore native bounds so the control enforces numeric range
        const minSaved = input.dataset.minSaved || input.getAttribute('min') || '0'
        const maxSaved = input.dataset.maxSaved || input.getAttribute('max') || '10'
        input.setAttribute('min', minSaved)
        input.setAttribute('max', maxSaved)
        input.dataset.minSaved = minSaved
        input.dataset.maxSaved = maxSaved
        const validateRating = () => {
          // If hidden (collapsed), skip validation to avoid unfocusable errors on navigation
          const isHidden = !input.offsetParent
          const min = parseFloat(input.dataset.minSaved || '0')
          const max = parseFloat(input.dataset.maxSaved || '10')
          const val = parseFloat(input.value)
          if (isHidden) {
            const feedback = input.parentElement?.querySelector('.invalid-feedback')
            input.setCustomValidity('')
            input.classList.remove('is-invalid')
            if (feedback) feedback.classList.remove('d-block')
            return
          }
          const feedback = input.parentElement?.querySelector('.invalid-feedback')
          const invalid = Number.isNaN(val) || val < min || val > max
          if (invalid) {
            input.setCustomValidity(`Enter a value between ${min} and ${max}`)
            input.classList.add('is-invalid')
            if (feedback) feedback.classList.add('d-block')
          } else {
            input.setCustomValidity('')
            input.classList.remove('is-invalid')
            if (feedback) feedback.classList.remove('d-block')
          }
        }
        input.addEventListener('input', validateRating)
        input.addEventListener('blur', validateRating)
        validateRating()
        input.dataset.listenerAdded = 'true'
      })

      // Any change/input inside this library should update highlights/validation (not just toggles)
      const bubbleHandler = () => {
        if (typeof EventHandler.updateAccordionHighlights === 'function') {
          EventHandler.updateAccordionHighlights()
        }
        if (typeof ValidationHandler !== 'undefined' && ValidationHandler.updateValidationState) {
          ValidationHandler.updateValidationState()
        }
      }
      library.querySelectorAll('input:not([type="hidden"]), select, textarea').forEach(el => {
        el.addEventListener('change', bubbleHandler, true)
        el.addEventListener('input', bubbleHandler, true)
        el.dataset.highlightListener = 'true'
      })

      // Delegated catch-all for dynamically added inputs/selects (including date)
      if (!library.dataset.highlightDelegate) {
        library.addEventListener('change', bubbleHandler, true)
        library.addEventListener('input', bubbleHandler, true)
        library.dataset.highlightDelegate = 'true'
      }
    })
    // === Expand child toggle sections if any are checked ===
    expandCheckedChildToggleSections()
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
      const accordionBody = accordion.querySelector('.accordion-body')

      // Skip preview overlays
      if (isPreviewOverlay) {
        accordionHeader.classList.remove('selected')
        return
      }

      let isCheckedOrSelected = false
      let hasValue = false

      if (accordionBody) {
        // 1. Check for directly selected inputs (checkboxes, radios, list selections)
        isCheckedOrSelected = accordionBody.querySelector(
          "input[type='checkbox']:checked:not(.readonly-toggle):not(.template-child-toggle):not([hidden]):not([type='hidden']), " +
          "input[type='radio']:checked:not([hidden]):not([type='hidden']), " +
          '.list-group li'
        ) !== null

        // 1b. Any non-empty inputs/selects also count as activity
        // Suppress value-based highlighting for true Collection/Overlay sections,
        // but allow it for "Delete Collections" (so its numeric field bubbles up).
        const headerLower = headerText.toLowerCase()
        const suppressValueCheck =
          headerLower.includes('overlay') ||
          (headerLower.includes('collection') && !headerLower.includes('delete collections'))
        if (!suppressValueCheck) {
          const textInputs = Array.from(
            accordionBody.querySelectorAll("input[type='text'], input[type='number'], input[type='date']")
          )
          const selects = Array.from(accordionBody.querySelectorAll('select'))
          hasValue = textInputs.some((input) => {
            const v = (input.value || '').trim().toLowerCase()
            return v && v !== 'none'
          }) || selects.some((sel) => {
            const v = (sel.value || '').trim().toLowerCase()
            return v && v !== 'none'
          })
        }

        // 2. Check for modified template selects, but only if toggle is still ON
        if (!isCheckedOrSelected) {
          isCheckedOrSelected = Array.from(
            accordionBody.querySelectorAll('.template-variable-select[data-user-modified="true"]')
          ).some((select) => {
            const group = select.closest('.template-toggle-group')
            const toggle = group?.querySelector('.overlay-toggle')
            return toggle?.checked
          })
        }
      }

      if (isCheckedOrSelected || hasValue) {
        accordionHeader.classList.add('selected')
        EventHandler.highlightParentAccordions(accordionHeader)
      } else {
        EventHandler.removeHighlightIfEmpty(accordionHeader)
      }
    })

    // Special case: don't highlight parent "Overlays" if only preview overlays are selected
    document.querySelectorAll('.accordion-item').forEach((accordion) => {
      const accordionHeader = accordion.querySelector('.accordion-header')
      const headerText = accordionHeader?.textContent.trim().toLowerCase()
      if (headerText !== 'overlays') return

      const childItems = accordion.querySelectorAll('.accordion-item')
      const hasNonPreviewSelection = Array.from(childItems).some((child) => {
        const childHeader = child.querySelector('.accordion-header')
        const isPreview = childHeader?.textContent.trim().toLowerCase().includes('preview overlays')

        if (isPreview) return false

        // Only highlight if child toggle is on or has modified select tied to an enabled toggle
        const hasActiveToggle = child.querySelector(
          "input[type='checkbox']:checked:not(.readonly-toggle):not(.template-child-toggle):not([hidden]):not([type='hidden']), " +
          "input[type='radio']:checked:not([hidden]):not([type='hidden']), " +
          '.list-group li'
        )
        if (hasActiveToggle) return true

        const hasModifiedSelectWithToggle = Array.from(
          child.querySelectorAll('.template-variable-select[data-user-modified="true"]')
        ).some((select) => {
          const group = select.closest('.template-toggle-group')
          const toggle = group?.querySelector('.overlay-toggle')
          return toggle?.checked
        })

        return hasModifiedSelectWithToggle
      })

      if (hasNonPreviewSelection) {
        accordionHeader.classList.add('selected')
      } else {
        accordionHeader.classList.remove('selected')
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
        return
      }

      if (isOverlaysSection) {
        const hasValidChild = Array.from(parentAccordion.querySelectorAll('.accordion-item')).some(child => {
          const childHeader = child.querySelector('.accordion-header')
          const childText = childHeader ? childHeader.textContent.trim() : ''
          const isPreviewChild = childText.toLowerCase().includes('preview overlays')

          return !isPreviewChild && child.querySelector('input:checked:not(.template-child-toggle)')
        })

        if (!hasValidChild) {
          console.log(`🚫 [DEBUG] Preventing Overlays from inheriting highlight due to only Preview Overlays: ${parentText}`)
          return
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

    const accordionBody = accordionItem.querySelector('.accordion-body')

    if (isPreviewOverlay) {
      console.log(`🚫 [DEBUG] Preventing highlight removal check for Preview Overlays: ${accordionId}`)
      return
    }

    const hasSelections = accordionBody?.querySelector(
      "input[type='checkbox']:checked:not(.readonly-toggle):not(.template-child-toggle):not([hidden]):not([type='hidden']), " +
      "input[type='radio']:checked:not([hidden]):not([type='hidden']), " +
      "select[data-user-modified='true'] option:checked:not([value='']):not([value='none']), " +
      '.list-group li'
    ) !== null

    if (!hasSelections) {
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

  installRatingSubmitGuard()
})

document.querySelectorAll('select.template-variable-select').forEach(select => {
  const selectedValue = select.dataset.selected
  if (selectedValue !== undefined && selectedValue !== null) {
    select.value = selectedValue
    console.debug(`[RESTORE] Select value set: ${select.name} = ${selectedValue}`)
  }
})

// =============================
// Mapping List Handler
// =============================
const mappingPrefixes = ['genre_mapper', 'content_rating_mapper']

mappingPrefixes.forEach(prefix => {
  console.log(`[DEBUG] Setting up mapping input for ${prefix}`)

  document.querySelectorAll(`[id$='-attribute_${prefix}_hidden']`).forEach(hiddenInput => {
    const libraryId = hiddenInput.id.split('-attribute_')[0]
    const inputField = document.getElementById(`${libraryId}-attribute_${prefix}_input`)
    const outputField = document.getElementById(`${libraryId}-attribute_${prefix}_output`)
    const addButton = document.getElementById(`${libraryId}-attribute_${prefix}_add`)
    const list = document.getElementById(`${libraryId}-attribute_${prefix}_list`)

    if (!inputField || !outputField || !addButton || !list) return

    function renderMappingList (mapping) {
      list.innerHTML = ''
      Object.entries(mapping).forEach(([key, value]) => {
        const li = document.createElement('li')
        li.className = 'list-group-item d-flex justify-content-between align-items-center'

        const display = value ? `${key} → ${value}` : `${key} → (remove)`
        li.innerHTML = `
          <span>${display}</span>
          <button type="button" class="btn btn-sm btn-danger" aria-label="Remove">
            <i class="bi bi-x-lg"></i>
          </button>
        `

        li.querySelector('button').addEventListener('click', function () {
          delete mapping[key]
          hiddenInput.value = JSON.stringify(mapping)
          renderMappingList(mapping)
        })

        list.appendChild(li)
      })
    }

    // Initialize from hidden input
    let mapping = {}
    try {
      mapping = JSON.parse(hiddenInput.value || '{}')
    } catch (e) {
      console.warn(`[WARN] Could not parse JSON for ${prefix}:`, e)
    }

    renderMappingList(mapping)

    // Handle click to add new mapping
    addButton.addEventListener('click', () => {
      const input = inputField.value.trim()
      const output = outputField.value.trim()

      if (!input || Object.keys(mapping).includes(input)) return

      mapping[input] = output || null
      hiddenInput.value = JSON.stringify(mapping)
      renderMappingList(mapping)

      inputField.value = ''
      outputField.value = ''
    })
  })
})

function expandCheckedChildToggleSections () {
  document.querySelectorAll('.child-toggle-wrapper').forEach(wrapper => {
    const anyChecked = wrapper.querySelector('.template-child-toggle:checked')
    const parentId = wrapper.dataset.toggleParent
    const parentToggle = parentId ? document.getElementById(parentId) : null
    const parentChecked = parentToggle ? parentToggle.checked : false
    console.log(`[DEBUG] Child section check: ${wrapper.id || 'unknown'}, checked: ${!!anyChecked}, parent: ${parentChecked}`)

    if (anyChecked && parentChecked) {
      wrapper.style.display = 'block'
    }
  })
}

// Prevent submit if any visible rating field is out of range; show inline error and scroll to it
function installRatingSubmitGuard () {
  const form = document.getElementById('configForm')
  if (!form || form.dataset.ratingGuarded) return

  const checkRatings = (evt) => {
    const ratings = Array.from(document.querySelectorAll('input[data-validate="rating"]'))
    const invalid = ratings.filter(input => {
      if (!input.offsetParent) return false
      const min = parseFloat(input.dataset.minSaved || input.getAttribute('min') || '0')
      const max = parseFloat(input.dataset.maxSaved || input.getAttribute('max') || '10')
      const val = parseFloat(input.value)
      return Number.isNaN(val) || val < min || val > max
    })
    if (invalid.length) {
      evt.preventDefault()
      evt.stopPropagation()
      invalid.forEach(input => {
        input.classList.add('is-invalid')
        const feedback = input.parentElement?.querySelector('.invalid-feedback')
        if (feedback) feedback.classList.add('d-block')
        const min = parseFloat(input.dataset.minSaved || input.getAttribute('min') || '0')
        const max = parseFloat(input.dataset.maxSaved || input.getAttribute('max') || '10')
        input.setCustomValidity(`Enter a value between ${min} and ${max}`)
      })
      const first = invalid[0]
      first.scrollIntoView({ behavior: 'smooth', block: 'center' })
      first.focus({ preventScroll: true })
      // Force native reporting to show tooltip if supported
      if (typeof form.reportValidity === 'function') {
        form.reportValidity()
      }
    }
  }

  form.addEventListener('submit', checkRatings, true)
  // Also guard nav buttons that submit via JS-triggered submit
  const navButtons = form.querySelectorAll('button[type="submit"]')
  navButtons.forEach(btn => {
    if (btn.dataset.ratingGuard) return
    btn.addEventListener('click', checkRatings, true)
    btn.dataset.ratingGuard = 'true'
  })
  form.dataset.ratingGuarded = 'true'
}
