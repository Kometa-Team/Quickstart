/* global showToast , bootstrap, updateFormData, refreshOverlayPreviewImage */

const ImageHandler = {
  loadAvailableImages: function (libraryId, type = 'movie', callback = null) {
    const dropdownId = `${libraryId}-${type}-image-dropdown`
    const hiddenInputId = `${libraryId}-${type}-hidden`
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

        dropdown.innerHTML = ''

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

    const hiddenInput = document.getElementById(`${libraryId}-${type}-hidden`)
    if (hiddenInput) {
      hiddenInput.value = selectedImage
      console.debug(`[SYNC] Set hidden input: ${hiddenInput.id} = ${selectedImage}`)
    }

    const isMovie = libraryId.startsWith('mov-library_')
    const selectedOverlays = ImageHandler.getLibraryOverlays(libraryId, isMovie)

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

  getLibraryOverlays: function (libraryId, isMovie, type = 'movie') {
    const overlays = []

    // 1. Handle all checked toggles (standard overlays)
    document.querySelectorAll(`#${libraryId}-overlays input[type="checkbox"]:checked`).forEach(input => {
      const cleaned = input.name.replace(new RegExp(`^${libraryId}-`), '')
      const prefix = type === 'episode' ? 'epi-sho-' : isMovie ? 'mov-' : 'sho-'
      overlays.push(`${prefix}${cleaned}`)
    })

    // 2. Handle Content Rating overlay radio
    const selectedRating = document.querySelector(
      `#${libraryId}-ContentRatingOverlays input.template-parent-toggle[data-radio-group="true"]:checked`
    )
    if (selectedRating) {
      const value = selectedRating.value // e.g., "de"
      const prefix = type === 'episode'
        ? 'epi-sho-overlay_content_rating_'
        : isMovie ? 'mov-overlay_content_rating_' : 'sho-overlay_content_rating_'
      overlays.push(prefix + value)
    }

    console.log(`[DEBUG] Overlays found for ${libraryId}, type: ${type}:`, overlays)
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

          // Set dropdown value to new filename
          const dropdown = document.getElementById(`${libraryId}-${type}-image-dropdown`)
          if (dropdown) dropdown.value = data.filename

          // Sync to hidden input
          const hiddenInput = document.getElementById(`${libraryId}-${type}-hidden`)
          if (hiddenInput) {
            hiddenInput.value = data.filename
            console.debug(`[SYNC] Updated hidden input after upload: ${hiddenInput.id} = ${data.filename}`)
          }

          ImageHandler.loadAvailableImages(libraryId, type)

          // Slight delay to allow dropdown update before regenerating preview
          setTimeout(() => {
            ImageHandler.generateSinglePreview(libraryId, type)
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

          // Update dropdown to reflect new image
          const dropdown = document.getElementById(`${libraryId}-${type}-image-dropdown`)
          if (dropdown) dropdown.value = data.filename

          // Sync to hidden input
          const hiddenInput = document.getElementById(`${libraryId}-${type}-hidden`)
          if (hiddenInput) {
            hiddenInput.value = data.filename
            console.debug(`[SYNC] Updated hidden input after fetch: ${hiddenInput.id} = ${data.filename}`)
          }

          ImageHandler.loadAvailableImages(libraryId, type)

          setTimeout(() => {
            ImageHandler.generateSinglePreview(libraryId, type)
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

  toggleDeleteButton: function (libraryId, isMovie) {
    const dropdown = document.querySelector(`[id="${libraryId}-image-dropdown"]`)
    const deleteBtn = document.getElementById(`${libraryId}-delete-image-btn`)
    const renameBtn = document.getElementById(`${libraryId}-rename-image-btn`)

    if (!dropdown || !deleteBtn || !renameBtn) {
      console.error(`[ERROR] Missing dropdown, delete button, or rename button for ${isMovie ? 'movie' : 'show'} in library ${libraryId}`)
      return
    }

    const isDefaultSelected = dropdown.value === 'default'
    const onlyDefaultExists = dropdown.options.length === 1 && isDefaultSelected

    deleteBtn.style.display = (isDefaultSelected || onlyDefaultExists) ? 'none' : 'block'
    renameBtn.style.display = (isDefaultSelected || onlyDefaultExists) ? 'none' : 'block'
    console.log(`[DEBUG] Toggled delete/rename buttons for ${libraryId} - Delete: ${deleteBtn.style.display}, Rename: ${renameBtn.style.display}`)
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

          // Sync new name to dropdown and hidden input
          ImageHandler.loadAvailableImages(libraryId, type, () => {
            const dropdown = document.getElementById(`${libraryId}-${type}-image-dropdown`)
            if (dropdown) {
              dropdown.value = newName
            }

            const hiddenInput = document.getElementById(`${libraryId}-${type}-hidden`)
            if (hiddenInput) {
              hiddenInput.value = newName
              console.debug(`[SYNC] Renamed image synced to hidden input: ${hiddenInput.id} = ${newName}`)
            }

            ImageHandler.generateSinglePreview(libraryId, type)

            const modal = bootstrap.Modal.getInstance(document.getElementById('renameModal'))
            if (modal) modal.hide()
          })
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
        refreshOverlayPreviewImage(target)
      }
    })
  })
})
