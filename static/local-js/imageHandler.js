/* global showToast , localStorage, bootstrap, updateFormData, refreshOverlayPreviewImage */

const ImageHandler = {
  loadAvailableImages: function (libraryId, isMovie) {
    console.log(`[DEBUG] Loading uploaded images for Library: ${libraryId}, Type: ${isMovie ? 'Movie' : 'Show'}`)

    fetch(`/list_uploaded_images?type=${isMovie ? 'movie' : 'show'}`)
      .then(response => response.json())
      .then(data => {
        if (data.status === 'error') {
          showToast('error', data.message)
          return
        }

        const dropdown = document.querySelector(`[id="${libraryId}-image-dropdown"]`)
        if (!dropdown) {
          console.error(`[ERROR] Dropdown for uploaded images for library ${libraryId} not found!`)
          return
        }

        dropdown.innerHTML = "<option value='default'>Default Kometa</option>"

        data.images.forEach(img => {
          const option = document.createElement('option')
          option.value = img
          option.textContent = img
          dropdown.appendChild(option)
        })

        // Restore last selected image after dropdown reloads on page
        const storedImage = localStorage.getItem(`${libraryId}-selected-image`)
        if (storedImage && [...dropdown.options].some(option => option.value === storedImage)) {
          dropdown.value = storedImage
        }

        // Store selection when changed
        dropdown.addEventListener('change', function () {
          localStorage.setItem(`${libraryId}-selected-image`, dropdown.value)
        })

        ImageHandler.generatePreview(libraryId, isMovie)
        ImageHandler.toggleDeleteButton(libraryId, isMovie)
      })
      .catch(error => {
        console.error('[ERROR] Loading uploaded images:', error)
        showToast('error', 'Failed to load available images. Please check your network or try again.')
      })
  },

  generatePreview: function (libraryId, isMovie) {
    console.log(`[DEBUG] Generating preview for Library: ${libraryId}`)

    const dropdown = document.querySelector(`[id="${libraryId}-image-dropdown"]`)
    if (!dropdown) {
      console.error(`[ERROR] Dropdown not found for library ${libraryId}`)
      return
    }

    const selectedImage = dropdown ? dropdown.value : 'default.png'
    const selectedOverlays = ImageHandler.getLibraryOverlays(libraryId, isMovie)

    fetch('/generate_preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        library_id: libraryId,
        overlays: selectedOverlays,
        type: isMovie ? 'movie' : 'show',
        selected_image: selectedImage
      })
    })
      .then(response => response.json())
      .then(data => {
        if (data.status === 'success') {
          const newPreviewURL = `/config/previews/${libraryId}-${isMovie ? 'movie' : 'show'}_preview.png?t=` + new Date().getTime()
          const previewImage = document.querySelector(`[id="${libraryId}-overlayPreviewImage"]`)

          if (previewImage) {
            previewImage.src = newPreviewURL
            console.log(`[DEBUG] Updated preview image for ${libraryId}: ${newPreviewURL}`)
          } else {
            console.error(`[ERROR] Overlay preview image not found for library ${libraryId}`)
          }
        }
      })
      .catch(error => console.error('[ERROR] Generating overlay preview:', error))
  },

  getLibraryOverlays: function (libraryId, isMovie) {
    let overlays = []

    // Get all selected overlay checkboxes within the library section
    document.querySelectorAll(`#${libraryId}-overlays input[type="checkbox"]:checked`).forEach(input => {
      overlays.push(input.name)
    })

    // Ensure rating overlay is included
    const selectedRating = document.querySelector(
      `#${libraryId}-contentRatingOverlays input[type='radio']:checked`
    )

    if (selectedRating) {
      overlays.push(selectedRating.value)
    } else {
      // Remove previous content rating overlays if none is selected
      overlays = overlays.filter(overlay => !overlay.startsWith('content_rating'))
    }

    // **Fix: Strip out `library_<library_name>-` from overlay names**
    overlays = overlays.map(overlay => overlay.replace(new RegExp(`^${libraryId}-`), `${isMovie ? 'mov' : 'sho'}-`))

    console.log(`[DEBUG] Overlays found for ${libraryId}:`, overlays)
    return overlays
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

  deleteCustomImage: function (libraryId, isMovie) {
    const dropdown = document.querySelector(`[id="${libraryId}-image-dropdown"]`)
    if (!dropdown) {
      console.error(`[ERROR] Dropdown for library ${libraryId} not found!`)
      return
    }

    const selectedImage = dropdown.value
    if (!selectedImage || selectedImage === 'default') {
      showToast('warning', 'Please select an image before deleting.')
      return
    }

    console.log(`[DEBUG] Deleting image: ${selectedImage} from Library: ${libraryId}`)

    fetch(`/delete_library_image/${encodeURIComponent(selectedImage)}?type=${isMovie ? 'movie' : 'show'}`, {
      method: 'DELETE'
    })
      .then(response => response.json())
      .then(data => {
        if (data.status === 'success') {
          showToast('success', data.message)
          console.log(`[DEBUG] Image "${selectedImage}" deleted successfully.`)

          // Reload dropdown list to remove the deleted image
          ImageHandler.loadAvailableImages(libraryId, isMovie)
        } else {
          showToast('error', data.message)
          console.error(`[ERROR] Failed to delete image: ${data.message}`)
        }
      })
      .catch(error => {
        console.error('[ERROR] Deleting image failed:', error)
        showToast('error', 'Failed to delete image.')
      })
  },

  openRenameModal: function (libraryId, isMovie) {
    console.log(`[DEBUG] Open Rename Modal for Library: ${libraryId} - ${isMovie ? 'Movies' : 'Shows'}`)

    const dropdown = document.querySelector(`[id="${libraryId}-image-dropdown"]`)
    if (!dropdown) {
      console.error(`[ERROR] No dropdown found for ${libraryId}`)
      return
    }

    const selectedImage = dropdown.value
    if (!selectedImage || selectedImage === 'default') {
      showToast('warning', 'Please select a custom image first.')
      return
    }

    const renameImagePreview = document.getElementById('rename-image-preview')
    const renameCurrentName = document.getElementById('rename-current-name')
    const renameNewNameMovie = document.getElementById('mov-image-name')
    const renameNewNameShow = document.getElementById('sho-image-name')
    const renameModalElement = document.getElementById('renameModal')

    if (!renameImagePreview || !renameCurrentName || !renameNewNameMovie || !renameNewNameShow || !renameModalElement) {
      console.error('[ERROR] Missing modal elements.')
      return
    }

    renameNewNameMovie.style.display = isMovie ? 'block' : 'none'
    renameNewNameShow.style.display = isMovie ? 'none' : 'block'

    renameImagePreview.src = `/config/uploads/${isMovie ? 'movies' : 'shows'}/${selectedImage}`
    renameCurrentName.textContent = `Current Name: ${selectedImage}`
    renameNewNameMovie.value = ''
    renameNewNameShow.value = ''

    const renameModal = new bootstrap.Modal(renameModalElement)
    renameModal.show()

    document.getElementById('rename-current-name').textContent = `Current Name: ${selectedImage}`
    document.getElementById(isMovie ? 'mov-image-name' : 'sho-image-name').value = ''
    document.getElementById('rename-confirm-btn').dataset.libraryId = libraryId
    document.getElementById('rename-confirm-btn').dataset.selectedImage = selectedImage
    document.getElementById('rename-confirm-btn').dataset.isMovie = isMovie
    document.getElementById('rename-confirm-btn').onclick = function () {
      ImageHandler.confirmRenameImage()
    }
    // Ensure "Enter" key triggers OK button
    renameModalElement.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault()
        document.getElementById('rename-confirm-btn').click()
      }
    })
  },

  confirmRenameImage: function () {
    const renameConfirmBtn = document.getElementById('rename-confirm-btn')
    const libraryId = renameConfirmBtn.dataset.libraryId
    const selectedImage = renameConfirmBtn.dataset.selectedImage
    const isMovie = renameConfirmBtn.dataset.isMovie === 'true'

    const renameNewNameMovie = document.getElementById('mov-image-name').value.trim()
    const renameNewNameShow = document.getElementById('sho-image-name').value.trim()
    const newImageName = isMovie ? renameNewNameMovie : renameNewNameShow

    if (!newImageName) {
      showToast('error', 'Please enter a new image name.')
      return
    }

    console.log(`[DEBUG] Renaming ${selectedImage} to ${newImageName} in ${isMovie ? 'movies' : 'shows'}`)

    fetch('/rename_library_image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        old_name: selectedImage,
        new_name: newImageName,
        type: isMovie ? 'movie' : 'show'
      })
    })
      .then(response => response.json())
      .then(data => {
        if (data.status === 'success') {
          showToast('success', 'Image renamed successfully.')

          // Reload the dropdown list to reflect new name
          ImageHandler.loadAvailableImages(libraryId, isMovie)

          // Hide the modal after renaming
          bootstrap.Modal.getInstance(document.getElementById('renameModal')).hide()
        } else {
          showToast('error', data.message)
        }
      })
      .catch(error => {
        console.error('[ERROR] Failed to rename image:', error)
        showToast('error', 'Failed to rename image.')
      })
  },

  renameLibraryImage: function () {
    const confirmBtn = document.getElementById('rename-confirm-btn')
    const libraryId = confirmBtn.dataset.libraryId

    const dropdown = document.querySelector(`[id="${libraryId}-image-dropdown"]`)
    if (!dropdown) {
      console.error(`[ERROR] Dropdown not found for library ${libraryId}`)
      return
    }

    const oldName = dropdown.value
    const newNameInput = document.getElementById(libraryId.startsWith('mov') ? 'mov-image-name' : 'sho-image-name')
    const newName = newNameInput.value.trim()

    if (!oldName || oldName === 'default' || !newName) {
      showToast('warning', 'Please enter a valid new name.')
      return
    }

    console.log(`[DEBUG] Renaming image: ${oldName} to ${newName} in ${libraryId}`)

    fetch('/rename_library_image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        old_name: oldName,
        new_name: newName,
        type: libraryId.startsWith('mov') ? 'movie' : 'show'
      })
    })
      .then(response => response.json())
      .then(data => {
        if (data.status === 'success') {
          showToast('success', 'Image renamed successfully.')

          // Store the new name temporarily before reloading the dropdown
          localStorage.setItem(`${libraryId}-selected-image`, newName)

          // Reload the dropdown and reselect the renamed file
          ImageHandler.loadAvailableImages(libraryId, libraryId.startsWith('mov'))

          // Close the modal after successful rename
          const renameModalElement = document.getElementById('renameModal')
          const renameModal = bootstrap.Modal.getInstance(renameModalElement)
          if (renameModal) renameModal.hide()
        } else {
          showToast('error', data.message)
        }
      })
      .catch(error => {
        console.error('[ERROR] Renaming image failed:', error)
        showToast('error', 'Failed to rename image.')
      })
  },

  uploadLibraryImage: function (libraryId, isMovie) {
    console.log(`[DEBUG] Uploading image for Library: ${libraryId}`)

    const fileInput = document.getElementById(`${libraryId}-upload-image`)
    if (!fileInput || !fileInput.files.length) {
      showToast('warning', 'Please select an image file.')
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
        if (data.status === 'success') {
          showToast(data.status === 'success' ? 'success' : 'error', data.message)
          localStorage.setItem(`${libraryId}-selected-image`, data.filename)
          ImageHandler.loadAvailableImages(libraryId, isMovie)
        } else {
          showToast('error', data.message)
        }
      })
      .catch(error => {
        console.error('[ERROR] Uploading image failed:', error)
        showToast('error', 'Failed to upload image.')
      })
  },

  fetchLibraryImage: function (libraryId, isMovie) {
    console.log(`[DEBUG] Fetching image for Library: ${libraryId}`)

    const urlInput = document.getElementById(`${libraryId}-image-url`)
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
        type: isMovie ? 'movie' : 'show'
      })
    })
      .then(response => response.json())
      .then(data => {
        if (data.status === 'success') {
          showToast(data.status === 'success' ? 'success' : 'error', data.message)
          localStorage.setItem(`${libraryId}-selected-image`, data.filename)
          ImageHandler.loadAvailableImages(libraryId, isMovie)
        } else {
          showToast('error', data.message)
        }
      })
      .catch(error => {
        console.error('[ERROR] Fetching image failed:', error)
        showToast('error', 'Failed to fetch image.')
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
