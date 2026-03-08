/* global showToast , bootstrap, updateFormData */

const ImageHandler = {
  loadAvailableImages: function (libraryId, type = 'movie', callback = null) {
    const dropdownId = `${libraryId}-${type}-image-dropdown`
    const hiddenInputId = `${libraryId}-${type}_selected_image` // FIXED to match stored key
    const dropdown = document.getElementById(dropdownId)
    const hiddenInput = document.getElementById(hiddenInputId)

    if (!dropdown) return

    fetch(`/list_uploaded_images?type=${type}`)
      .then(res => res.json())
      .then(data => {
        if (data.status !== 'success') {
          showToast('error', data.message || 'Failed to load images.')
          return
        }

        dropdown.replaceChildren()

        const defaultOption = document.createElement('option')
        defaultOption.value = 'default'
        defaultOption.textContent = `Select ${type} image`
        dropdown.appendChild(defaultOption)

        data.images.forEach(image => {
          const option = document.createElement('option')
          option.value = image
          option.textContent = image
          dropdown.appendChild(option)
        })

        const saved = hiddenInput?.value
        console.log(`[DEBUG] Trying to reselect hidden input image for ${libraryId} - ${type}: ${saved}`)

        if (saved && data.images.includes(saved)) {
          dropdown.value = saved
          console.log(`[DEBUG] Successfully reselected image from hidden input: ${saved}`)
          ImageHandler.generateSinglePreview(libraryId, type)
        } else {
          console.warn(`[DEBUG] Hidden input image not found in dropdown for ${libraryId} - ${type}.`)
          ImageHandler.updateOverlayBoardBackground(libraryId, type, 'default')
        }

        if (callback) callback()
      })
      .catch(err => {
        console.error('[ERROR] Failed to load images:', err)
        showToast('error', 'Could not load image list.')
      })
  },

  generateSinglePreview: function (libraryId, type) {
    const dropdownId = `${libraryId}-${type}-image-dropdown`
    const imageElementId = `${libraryId}-overlayPreviewImage-${type}`
    const dropdown = document.getElementById(dropdownId)
    if (!dropdown) return

    const selectedImage = dropdown.value || 'default'
    ImageHandler.updateOverlayBoardBackground(libraryId, type, selectedImage)

    const hiddenInput = document.getElementById(`${libraryId}-${type}-hidden`)
    if (hiddenInput) {
      hiddenInput.value = selectedImage
      console.debug(`[SYNC] Set hidden input: ${hiddenInput.id} = ${selectedImage}`)
    }

    const isMovie = libraryId.startsWith('mov-library_')
    const selectedOverlays = ImageHandler.getLibraryOverlays(libraryId, isMovie, type)
    console.debug('[DEBUG] Selected Overlays:', selectedOverlays)

    fetch('/generate_preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        library_id: libraryId,
        overlays: selectedOverlays,
        type,
        selected_image: selectedImage
      })
    })
      .then(response => response.json())
      .then(data => {
        if (data.status === 'success') {
          const previewUrl = `/config/previews/${libraryId}-${type}_preview.png?t=` + new Date().getTime()
          const img = document.getElementById(imageElementId)
          if (img) img.src = previewUrl
        }
      })
      .catch(error => console.error(`[ERROR] Generating preview for ${type}:`, error))
  },

  updateOverlayBoardBackground: function (libraryId, type, selectedImage) {
    const board = document.querySelector(
      `.overlay-board[data-library-id="${libraryId}"][data-overlay-type="${type}"]`
    )
    if (!board) return
    const canvas = board.querySelector('.overlay-board-canvas')
    if (!canvas) return

    const baseWidth = Number(board.dataset.baseWidth) || (type === 'episode' ? 1920 : 1000)
    const baseHeight = Number(board.dataset.baseHeight) || (type === 'episode' ? 1080 : 1500)
    const normalized = selectedImage && selectedImage !== 'default'
      ? `/config/uploads/${type}s/${encodeURIComponent(selectedImage)}`
      : `/static/images/default-${baseWidth}x${baseHeight}.png`
    canvas.style.backgroundImage = `url("${normalized}")`
  },

  getLibraryOverlays: function (libraryId, isMovie, type = 'movie') {
    const overlays = []

    // Find all enabled checkboxes in this overlay group
    document.querySelectorAll(`#${libraryId}-overlays input[type="checkbox"]:checked`).forEach(input => {
      if (!input.name.includes(`-${type}-`)) return

      const fullName = input.name // e.g., mov-library_movies-movie-overlay_ribbon
      const overlayIdMatch = fullName.match(/overlay_([a-zA-Z0-9_]+)/)
      if (!overlayIdMatch) return

      const overlaySuffix = overlayIdMatch[1]
      const overlayId = `overlay_${overlaySuffix}`

      const overlayObj = {
        id: overlayId,
        template_variables: {}
      }

      const container = input.closest('.template-toggle-group')
      const templateName = container?.dataset.overlayTemplate
      const templatePrefix = templateName || fullName.replace('-overlay_', '-template_overlay_')

      // Collect template variables: selects and toggles (e.g., use_edition)
      const selectors = container
        ? container.querySelectorAll(
            `select[name^="${templatePrefix}["], input[type="checkbox"][name^="${templatePrefix}["], input[type="text"][name^="${templatePrefix}["], input[type="number"][name^="${templatePrefix}["], input[type="color"][name^="${templatePrefix}["]`
        )
        : document.querySelectorAll(
            `select[name^="${templatePrefix}["], input[type="checkbox"][name^="${templatePrefix}["], input[type="text"][name^="${templatePrefix}["], input[type="number"][name^="${templatePrefix}["], input[type="color"][name^="${templatePrefix}["]`
        )

      selectors.forEach((el) => {
        const match = el.name.match(/\[([^\]]+)\]/)
        if (!match) return
        const varName = match[1]
        // Do not emit text variables for overlays that only need text for preview
        if (varName === 'text' && (['overlay_video_format', 'overlay_aspect'].includes(overlayId) || ['video_format', 'aspect'].includes(overlaySuffix))) {
          return
        }
        if (el.type === 'checkbox') {
          overlayObj.template_variables[varName] = el.checked ? (el.value || 'true') : 'false'
        } else if (el.type === 'number') {
          const num = Number(el.value)
          overlayObj.template_variables[varName] = Number.isFinite(num) ? num : el.value
        } else if (el.type === 'color') {
          overlayObj.template_variables[varName] = el.value
        } else {
          overlayObj.template_variables[varName] = el.value
        }
      })

      // Ensure text is not emitted for overlays that only use it for preview
      if (['video_format', 'aspect'].includes(overlaySuffix)) {
        delete overlayObj.template_variables.text
      } else if (['content_rating_commonsense', 'overlay_content_rating_commonsense'].includes(overlaySuffix)) {
        delete overlayObj.template_variables.text
        delete overlayObj.template_variables.font
        delete overlayObj.template_variables.font_size
        delete overlayObj.template_variables.font_color
      }

      overlays.push(overlayObj)
    })

    // Content rating logic (radio buttons)
    const selectedRating = document.querySelector(
      `#${libraryId}-ContentRatingOverlays .overlay-group[data-type="${type}"] input.template-parent-toggle[data-radio-group="true"]:checked`
    )
    if (selectedRating) {
      const value = selectedRating.value // e.g., "nz"
      const overlaySuffix = `content_rating_${value}`
      const overlayId = `overlay_${overlaySuffix}`

      // eslint-disable-next-line camelcase
      const template_variables = {}

      const colorInput = document.querySelector(
        `#${libraryId}-ContentRatingOverlays .overlay-group[data-type="${type}"] select[name="${libraryId}-${type}-template_overlay_${overlaySuffix}[color]"]`
      )
      if (colorInput) {
        // eslint-disable-next-line camelcase
        template_variables.color = colorInput.value.toString()
      }

      // Capture offsets for all content ratings (including commonsense)
      const setNum = (key, el) => {
        if (!el) return
        const n = Number(el.value)
        // eslint-disable-next-line camelcase
        template_variables[key] = Number.isFinite(n) ? n : el.value
      }
      const hInput = document.querySelector(
        `#${libraryId}-ContentRatingOverlays .overlay-group[data-type="${type}"] input[name="${libraryId}-${type}-template_overlay_${overlaySuffix}[horizontal_offset]"]`
      )
      const vInput = document.querySelector(
        `#${libraryId}-ContentRatingOverlays .overlay-group[data-type="${type}"] input[name="${libraryId}-${type}-template_overlay_${overlaySuffix}[vertical_offset]"]`
      )
      setNum('horizontal_offset', hInput)
      setNum('vertical_offset', vInput)

      // If commonsense, also capture text/post_text/addon_offset and offsets from its template container
      if (value === 'commonsense') {
        const container = document.querySelector(
          `.template-toggle-group[data-overlay-id="overlay_${overlaySuffix}"][data-library-id="${libraryId}"][data-overlay-type="${type}"]`
        )
        if (container) {
          const templateName = container.dataset.overlayTemplate
          const grab = (key) => {
            const el = container.querySelector(`[name="${templateName}[${key}]"]`)
            if (!el) return null
            if (el.type === 'number') {
              const n = Number(el.value)
              return Number.isFinite(n) ? n : el.value
            }
            return el.value
          }
          const maybeSet = (key) => {
            const val = grab(key)
            // eslint-disable-next-line camelcase
            if (val !== null && val !== undefined) template_variables[key] = val
          }
          ;['post_text', 'addon_offset', 'horizontal_offset', 'vertical_offset'].forEach(maybeSet)
        }
      }

      // eslint-disable-next-line camelcase
      overlays.push({ id: overlayId, template_variables })
    }

    console.debug(`[DEBUG] Overlays found for ${libraryId}, type: ${type}:`, overlays)
    return overlays
  },

  uploadLibraryImage: function (libraryId, type) {
    console.log(`[DEBUG] Uploading image for Library: ${libraryId}, Type: ${type}`)

    const fileInput = document.getElementById(`${libraryId}-${type}-upload-image`)
    if (!fileInput || !fileInput.files.length) {
      showToast('warning', 'Please select an image file.')
      return
    }

    const formData = new FormData()
    formData.append('image', fileInput.files[0])
    formData.append('type', type)

    fetch('/upload_library_image', {
      method: 'POST',
      body: formData
    })
      .then(response => response.json())
      .then(data => {
        if (data.status === 'success') {
          showToast('success', data.message)

          // Reload dropdown to include new image
          ImageHandler.loadAvailableImages(libraryId, type)

          // Delay ensures dropdown is repopulated before setting value and syncing
          setTimeout(() => {
            const dropdown = document.getElementById(`${libraryId}-${type}-image-dropdown`)
            if (dropdown) dropdown.value = data.filename

            const hiddenInput = document.getElementById(`${libraryId}-${type}_selected_image`)
            if (hiddenInput) {
              hiddenInput.value = data.filename
              console.debug(`[SYNC] Updated hidden input after upload: ${hiddenInput.id} = ${data.filename}`)
            }

            ImageHandler.generateSinglePreview(libraryId, type)
            ImageHandler.toggleDeleteButton(libraryId, type)
          }, 300)
        } else {
          showToast('error', data.message)
        }
      })
      .catch(error => {
        console.error('[ERROR] Uploading image failed:', error)
        showToast('error', 'Failed to upload image.')
      })
  },

  fetchLibraryImage: function (libraryId, type) {
    console.log(`[DEBUG] Fetching image for Library: ${libraryId}, Type: ${type}`)

    const urlInput = document.getElementById(`${libraryId}-${type}-image-url`)
    const imageUrl = urlInput.value.trim()

    if (!imageUrl) {
      showToast('warning', 'Please enter a valid image URL.')
      return
    }

    fetch('/fetch_library_image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: imageUrl,
        type
      })
    })
      .then(response => response.json())
      .then(data => {
        if (data.status === 'success') {
          showToast('success', data.message)

          // Reload dropdown to include fetched image
          ImageHandler.loadAvailableImages(libraryId, type)

          setTimeout(() => {
            const dropdown = document.getElementById(`${libraryId}-${type}-image-dropdown`)
            if (dropdown) dropdown.value = data.filename

            const hiddenInput = document.getElementById(`${libraryId}-${type}_selected_image`)
            if (hiddenInput) {
              hiddenInput.value = data.filename
              console.debug(`[SYNC] Updated hidden input after fetch: ${hiddenInput.id} = ${data.filename}`)
            }

            ImageHandler.generateSinglePreview(libraryId, type)
            ImageHandler.toggleDeleteButton(libraryId, type)
          }, 300)
        } else {
          showToast('error', data.message)
        }
      })
      .catch(error => {
        console.error('[ERROR] Fetching image failed:', error)
        showToast('error', 'Failed to fetch image.')
      })
  },

  toggleDeleteButton: function (libraryId, type = 'movie') {
    const dropdown = document.getElementById(`${libraryId}-${type}-image-dropdown`)
    const deleteBtn = document.getElementById(`${libraryId}-${type}-delete-image-btn`)
    const renameBtn = document.getElementById(`${libraryId}-${type}-rename-image-btn`)

    if (!dropdown || !deleteBtn || !renameBtn) {
      console.error(`[ERROR] Missing dropdown, delete button, or rename button for ${type} in ${libraryId}`)
      return
    }

    const isDefaultSelected = dropdown.value === 'default'
    const onlyDefaultExists = dropdown.options.length === 1 && isDefaultSelected

    const show = !(isDefaultSelected || onlyDefaultExists)
    deleteBtn.style.display = show ? 'block' : 'none'
    renameBtn.style.display = show ? 'block' : 'none'

    console.debug(`[DEBUG] Toggled delete/rename buttons for ${libraryId} - ${type} | Delete: ${deleteBtn.style.display}, Rename: ${renameBtn.style.display}`)
  },

  deleteCustomImage: function (libraryId, type = 'movie') {
    const dropdown = document.getElementById(`${libraryId}-${type}-image-dropdown`)
    const selectedImage = dropdown?.value
    if (!selectedImage || selectedImage === 'default') {
      showToast('warning', 'Please select an image to delete.')
      return
    }

    fetch(`/delete_library_image/${encodeURIComponent(selectedImage)}?type=${type}`, {
      method: 'DELETE'
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          showToast('success', data.message)

          // Set dropdown to default
          if (dropdown) dropdown.value = 'default'

          // Clear hidden input
          const hiddenInput = document.getElementById(`${libraryId}-${type}-hidden`)
          if (hiddenInput) {
            hiddenInput.value = 'default'
            console.debug(`[SYNC] Cleared hidden input after delete: ${hiddenInput.id}`)
          }

          ImageHandler.loadAvailableImages(libraryId, type)
          ImageHandler.toggleDeleteButton(libraryId, type)

          setTimeout(() => {
            ImageHandler.generateSinglePreview(libraryId, type)
          }, 300)
        } else {
          showToast('error', data.message)
        }
      })
      .catch(err => {
        console.error('[ERROR] Failed to delete image:', err)
        showToast('error', 'Image deletion failed.')
      })
  },

  openRenameModal: function (libraryId, type) {
    console.log(`[DEBUG] Open Rename Modal for Library: ${libraryId} - Type: ${type}`)

    const dropdown = document.getElementById(`${libraryId}-${type}-image-dropdown`)
    if (!dropdown) {
      console.error(`[ERROR] No dropdown found for ${libraryId} - ${type}`)
      return
    }

    const selectedImage = dropdown.value
    if (!selectedImage || selectedImage === 'default') {
      showToast('warning', 'Please select a custom image first.')
      return
    }

    // DOM elements
    const preview = document.getElementById('rename-image-preview')
    const currentName = document.getElementById('rename-current-name')
    const renameModalElement = document.getElementById('renameModal')
    const inputMap = {
      movie: document.getElementById('mov-image-name'),
      show: document.getElementById('sho-image-name'),
      season: document.getElementById('sea-image-name'),
      episode: document.getElementById('epi-image-name')
    }

    if (!preview || !currentName || !renameModalElement || Object.values(inputMap).some(el => !el)) {
      console.error('[ERROR] One or more modal elements are missing.')
      return
    }

    // Hide all inputs, show only the one for the current type
    Object.entries(inputMap).forEach(([key, input]) => {
      input.style.display = key === type ? 'block' : 'none'
      input.value = ''
    })

    // Update modal content
    preview.src = `/config/uploads/${type}s/${selectedImage}`
    currentName.textContent = `Current Name: ${selectedImage}`

    // Show modal
    const modal = new bootstrap.Modal(renameModalElement)
    modal.show()

    // Prepare confirm button
    const confirmBtn = document.getElementById('rename-confirm-btn')
    confirmBtn.dataset.libraryId = libraryId
    confirmBtn.dataset.selectedImage = selectedImage
    confirmBtn.dataset.type = type

    confirmBtn.onclick = () => ImageHandler.confirmRenameImage()

    // Clean previous Enter key handler and add a fresh one
    renameModalElement.onkeydown = function (event) {
      if (event.key === 'Enter') {
        event.preventDefault()
        confirmBtn.click()
      }
    }

    // Clear Enter handler after modal closes
    renameModalElement.addEventListener('hidden.bs.modal', () => {
      renameModalElement.onkeydown = null
    }, { once: true })
  },

  confirmRenameImage: function () {
    const confirmBtn = document.getElementById('rename-confirm-btn')
    const libraryId = confirmBtn.dataset.libraryId
    const selectedImage = confirmBtn.dataset.selectedImage
    const type = confirmBtn.dataset.type

    const inputMap = {
      movie: document.getElementById('mov-image-name'),
      show: document.getElementById('sho-image-name'),
      season: document.getElementById('sea-image-name'),
      episode: document.getElementById('epi-image-name')
    }

    const inputField = inputMap[type]
    const baseName = inputField?.value.trim()

    if (!baseName) {
      showToast('error', 'Please enter a new image name.')
      return
    }

    const extension = selectedImage.split('.').pop()
    const newName = `${baseName}.${extension}`

    console.log(`[DEBUG] Renaming ${selectedImage} to ${newName} in type: ${type}`)

    fetch('/rename_library_image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        old_name: selectedImage,
        new_name: newName,
        type
      })
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          showToast('success', data.message)

          ImageHandler.loadAvailableImages(libraryId, type)

          setTimeout(() => {
            const dropdown = document.getElementById(`${libraryId}-${type}-image-dropdown`)
            if (dropdown) dropdown.value = newName

            const hiddenInput = document.getElementById(`${libraryId}-${type}_selected_image`)
            if (hiddenInput) {
              hiddenInput.value = newName
              console.debug(`[SYNC] Updated hidden input after rename: ${hiddenInput.id} = ${newName}`)
            }

            ImageHandler.generateSinglePreview(libraryId, type)
            ImageHandler.toggleDeleteButton(libraryId, type)

            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('renameModal'))
            if (modal) modal.hide()
          }, 300)
        } else {
          showToast('error', data.message)
        }
      })
      .catch(err => {
        console.error('[ERROR] Rename failed:', err)
        showToast('error', 'Rename failed.')
      })
  }
}

// Global listener to refresh image preview only if toggle is in preview overlay section
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.form-check-input').forEach((input) => {
    input.addEventListener('change', (event) => {
      const target = event.target

      // Always update the form model
      updateFormData(target)

      // Look for the overlay section specifically (e.g., mov-library_movies-overlays)
      const isInOverlayAccordion = target.closest('[id$="-overlays"]')
      if (isInOverlayAccordion) {
        const container = target.closest('.library-settings-card')
        const libraryId = container?.id?.replace('-card-container', '')
        if (!libraryId) return

        const isMovie = libraryId.startsWith('mov-library_')
        const types = isMovie ? ['movie'] : ['show', 'season', 'episode']

        types.forEach(type => {
          ImageHandler.generateSinglePreview(libraryId, type)
        })
      }
    })
  })
})
