import {
  hasCheckedTemplateGroupToggle,
  hasLibraryFileEntries,
  highlightParentAccordions,
  removeHighlightIfEmpty,
  updateAccordionHighlights
} from './modules/accordionHighlights.js'

function callValidationHandler (methodName, ...args) {
  const handler = window.ValidationHandler
  if (!handler || typeof handler[methodName] !== 'function') {
    return
  }
  return handler[methodName](...args)
}

const EventHandler = {
  attachLibraryListeners: function () {
    document.querySelectorAll('.library-checkbox').forEach((checkbox) => {
      const libraryId = checkbox.id.replace(/-(library|card-container)$/, '')

      if (checkbox.dataset.listenerAdded !== 'true') {
        console.log(`[DEBUG] Attaching toggle listener for Library: ${libraryId}`)

        // Attach event listener to each checkbox
        checkbox.addEventListener('change', () => {
          EventHandler.toggleLibraryVisibility(libraryId, checkbox.checked)
          callValidationHandler('updateValidationState')
        })
        checkbox.dataset.listenerAdded = 'true'
      }

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

      // Attach overlay selection listeners (CHANGE events)
      library.querySelectorAll('.accordion input').forEach((input) => {
        library.querySelectorAll('.accordion select').forEach(select => {
          if (!select.dataset.listenerAdded) {
            select.addEventListener('change', () => {
              console.log(`[DEBUG] Dropdown changed: ${select.id} -> ${select.value}`)
              updateAccordionHighlights()
              callValidationHandler('updateValidationState')

              // Trigger preview update if template variable
              if (select.classList.contains('template-variable-select')) {
                const nameParts = select.name.split('-')
                const previewLibraryId = nameParts.slice(0, 2).join('-') // e.g., mov-library_movies
                const type = nameParts[2] // e.g., movie
                ImageHandler.generateSinglePreview(previewLibraryId, type)
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
              updateAccordionHighlights()
              callValidationHandler('updateValidationState')
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
            updateAccordionHighlights()
            callValidationHandler('updateValidationState')
          })

          dropdown.dataset.listenerAdded = 'true'
        }
      })

      // Automatically trigger preview updates when overlays are toggled or content rating changes
      library.querySelectorAll('input[type="checkbox"].overlay-toggle, input[type="radio"].overlay-toggle').forEach(input => {
        if (input.dataset.previewListenerAdded === 'true') return
        input.addEventListener('change', () => {
          console.log(`[DEBUG] Overlay toggle changed: ${input.id}`)
          const match = input.id.match(/-(movie|show|season|episode)-overlay_/)
          const inputType = match ? match[1] : (isMovie ? 'movie' : 'show')
          ImageHandler.generateSinglePreview(libraryId, inputType)
        })
        input.dataset.previewListenerAdded = 'true'
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
                const removeIcon = document.createElement('i')
                removeIcon.className = 'bi bi-x-lg'
                removeBtn.appendChild(removeIcon)
                removeBtn.addEventListener('click', function () {
                  li.remove()
                  updateHiddenInput(customList, hiddenCustomInput)
                })

                li.appendChild(removeBtn)
                customList.appendChild(li)
              })
              hiddenCustomInput.value = JSON.stringify(savedItems)
            } catch (e) {
              console.warn('[WARN] Could not parse saved custom list for', prefix, 'in', libraryId, e)
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
            const removeIcon = document.createElement('i')
            removeIcon.className = 'bi bi-x-lg'
            removeBtn.appendChild(removeIcon)
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
      const bubbleHandler = (event) => {
        const target = event?.target
        if (
          target && target.nodeType === 1 &&
          (
            target.dataset.skipLibraryInputBubble === 'true' ||
            target.closest('[data-overlay-source-editor="true"]')
          )
        ) {
          return
        }
        updateAccordionHighlights()
        callValidationHandler('updateValidationState')
      }
      library.querySelectorAll('input:not([type="hidden"]), select, textarea').forEach(el => {
        if (el.dataset.highlightListener === 'true') return
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
  }
}

// Accordion-highlight state -- extracted to a shared module in step 2f
// of #1346 so overlayHandler.js and 025-libraries.js can import from
// one source instead of reaching for window.EventHandler. We still
// mirror onto EventHandler here so external non-module callers keep
// working during the migration.
EventHandler.hasCheckedTemplateGroupToggle = hasCheckedTemplateGroupToggle
EventHandler.hasLibraryFileEntries = hasLibraryFileEntries
EventHandler.highlightParentAccordions = highlightParentAccordions
EventHandler.removeHighlightIfEmpty = removeHighlightIfEmpty
EventHandler.updateAccordionHighlights = updateAccordionHighlights

window.EventHandler = EventHandler

// MutationObserver for dynamically added elements
const shouldReattachForNode = (node) => {
  if (!node || node.nodeType !== 1) return false
  if (node.closest('[data-overlay-source-editor="true"]') || node.closest('[data-overlay-source-hidden]')) return false
  if (node.matches("[id$='-card-container']")) return true
  if (node.matches('input[type="hidden"]')) return false
  if (node.matches('.accordion input:not([type="hidden"]), .accordion select, .accordion textarea')) return true

  const descendants = node.querySelectorAll?.('.accordion input:not([type="hidden"]), .accordion select, .accordion textarea')
  return Array.from(descendants || []).some(descendant => {
    return !descendant.closest('[data-overlay-source-editor="true"]') &&
      !descendant.closest('[data-overlay-source-hidden]')
  })
}

const observer = new MutationObserver((mutations) => {
  let needsReattachment = false

  mutations.forEach((mutation) => {
    if (mutation.addedNodes.length > 0) {
      mutation.addedNodes.forEach((node) => {
        if (shouldReattachForNode(node)) {
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
console.log('[DEBUG] Initializing EventHandler...')

// Run once on page load
EventHandler.attachLibraryListeners()
callValidationHandler('restoreSelectedLibraries')
callValidationHandler('updateValidationState')
installRatingSubmitGuard()

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
      list.replaceChildren()
      Object.entries(mapping).forEach(([key, value]) => {
        const li = document.createElement('li')
        li.className = 'list-group-item d-flex justify-content-between align-items-center'

        const display = value ? `${key} → ${value}` : `${key} → (remove)`
        const textSpan = document.createElement('span')
        textSpan.textContent = display
        const button = document.createElement('button')
        button.type = 'button'
        button.className = 'btn btn-sm btn-danger'
        button.setAttribute('aria-label', 'Remove')
        const icon = document.createElement('i')
        icon.className = 'bi bi-x-lg'
        button.appendChild(icon)
        button.addEventListener('click', function () {
          delete mapping[key]
          hiddenInput.value = JSON.stringify(mapping)
          renderMappingList(mapping)
        })

        li.append(textSpan, button)
        list.appendChild(li)
      })
    }

    // Initialize from hidden input
    let mapping = {}
    try {
      mapping = JSON.parse(hiddenInput.value || '{}')
    } catch (e) {
      console.warn('[WARN] Could not parse JSON for', prefix, e)
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
