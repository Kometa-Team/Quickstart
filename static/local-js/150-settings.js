/* global $ */

document.addEventListener('DOMContentLoaded', function () {
  const saveSyncChangesButton = document.getElementById('saveSyncChangesButton')
  const saveExcludeChangesButton = document.getElementById('saveExcludeChangesButton')
  const configForm = document.getElementById('configForm')
  const validationMessages = document.getElementById('validation-messages')
  const syncUsersModal = document.getElementById('syncUsersModal')
  const excludeUsersModal = document.getElementById('excludeUsersModal')

  function populateModalToggles (inputId, modalSelector, toggleClass) {
    const selectedUsers = document.getElementById(inputId).value.split(', ').map(u => u.trim())

    document.querySelectorAll(`${modalSelector} .${toggleClass}`).forEach(toggle => {
      toggle.checked = selectedUsers.includes(toggle.value)
    })

    // Handle "All Users" toggle
    const allToggle = document.querySelector(`${modalSelector} #sync_all_users`)
    if (allToggle) {
      allToggle.checked = selectedUsers.includes('all')
    }
  }

  // Populate Sync Users modal when opened
  syncUsersModal.addEventListener('show.bs.modal', function () {
    populateModalToggles('playlist_sync_to_users', '#syncUsersModal', 'sync-user-toggle')
  })

  // Populate Exclude Users modal when opened
  excludeUsersModal.addEventListener('show.bs.modal', function () {
    populateModalToggles('playlist_exclude_users', '#excludeUsersModal', 'exclude-user-toggle')
  })

  saveSyncChangesButton.addEventListener('click', function () {
    const selectedUsers = []
    const checkboxes = document.querySelectorAll('#syncUserListForm input[type="checkbox"]:checked')
    const allSelected = document.getElementById('sync_all_users').checked

    if (allSelected) {
      selectedUsers.push('all')
    } else {
      checkboxes.forEach((checkbox) => {
        if (checkbox.value !== 'all') {
          selectedUsers.push(checkbox.value)
        }
      })
    }

    const csvUsers = selectedUsers.join(', ')
    document.getElementById('playlist_sync_to_users').value = csvUsers

    // Close the modal using Bootstrap 4 jQuery method
    console.log($('#syncUsersModal').data('bs.modal'))
    $('#syncUsersModal').modal('hide')

    // Mark settings as invalid until re-validated
    setSettingsValidated(false)
  })
  saveExcludeChangesButton.addEventListener('click', function () {
    const selectedUsers = []
    const checkboxes = document.querySelectorAll('#excludeUserListForm input[type="checkbox"]:checked')

    checkboxes.forEach((checkbox) => {
      selectedUsers.push(checkbox.value)
    })

    const csvUsers = selectedUsers.join(', ')
    document.getElementById('playlist_exclude_users').value = csvUsers
    $('#excludeUsersModal').modal('hide')
    setSettingsValidated(false)
  })

  function setSettingsValidated (isValid) {
    const settingsValidatedInput = document.getElementById('settings_validated')
    settingsValidatedInput.value = isValid ? 'true' : 'false'
  }

  function showAccordionForField (field) {
    const accordionItem = field.closest('.accordion-collapse')
    if (accordionItem && !accordionItem.classList.contains('show')) {
      const accordionHeader = accordionItem.previousElementSibling.querySelector('button.accordion-button')
      if (accordionHeader) {
        accordionHeader.click() // Simulate a click to open the accordion
      }
    }
  }

  function validateField (field, regex, errorMessage) {
    const value = field.value.trim()
    console.log(`Validating field: ${field.name}, Value: "${value}"`) // Debug log

    const errorDivClass = 'error-message'
    const successClass = 'is-valid'

    let errorDiv = field.parentNode.querySelector(`.${errorDivClass}`)
    if (!errorDiv) {
      errorDiv = document.createElement('div')
      errorDiv.className = `${errorDivClass} text-danger`
      field.parentNode.appendChild(errorDiv)
    }

    if (!regex.test(value)) {
      console.log(`Validation failed for: ${field.name}`) // Debug log
      field.classList.add('is-invalid')
      field.classList.remove(successClass)
      errorDiv.textContent = errorMessage
      showAccordionForField(field)
      return false
    } else {
      console.log(`Validation passed for: ${field.name}`) // Debug log
      field.classList.remove('is-invalid')
      field.classList.add(successClass)
      errorDiv.textContent = ''
      return true
    }
  }

  const fieldsToValidate = [
    {
      id: 'asset_directory',
      regex: /^(?:[a-zA-Z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*|\\{2}[^\\/:*?"<>|\r\n]+(?:\\[^\\/:*?"<>|\r\n]+)*|(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]+|\/(?:[^/]+\/)*[^/]*|\.{1,2}(?:\/[^/]*)*|(?:[^/]+\/)*[^/]*)$/,
      errorMessage: 'Please enter a valid asset directory path.'
    },
    {
      id: 'asset_depth',
      regex: /^(0|[1-9]\d*)$/,
      errorMessage: 'Please enter a valid integer (0 or greater).'
    },
    {
      id: 'overlay_artwork_quality',
      regex: /^(100|[1-9][0-9]?)$/,
      errorMessage: 'Please enter an integer between 1 and 100.'
    },
    {
      id: 'cache_expiration',
      regex: /^[1-9]\d*$/,
      errorMessage: 'Please enter a valid integer greater than 0.'
    },
    {
      id: 'item_refresh_delay',
      regex: /^(0|[1-9]\d*)$/,
      errorMessage: 'Please enter a valid integer (0 or greater).'
    },
    {
      id: 'minimum_items',
      regex: /^[1-9]\d*$/,
      errorMessage: 'Please enter a valid integer greater than 0.'
    },
    {
      id: 'run_again_delay',
      regex: /^(0|[1-9]\d*)$/,
      errorMessage: 'Please enter a valid integer (0 or greater).'
    },
    {
      id: 'ignore_ids',
      regex: /^(None|\d{1,8}(,\d{1,8})*)$/,
      errorMessage: 'Please enter a valid CSV list of numeric IDs (1-8 digits) or "None".'
    },
    {
      id: 'ignore_imdb_ids',
      regex: /^(None|tt\d{7,8}(,tt\d{7,8})*)$/,
      errorMessage: 'Please enter a valid CSV list of IMDb IDs (e.g., tt1234567) or "None".'
    },
    {
      id: 'custom_repo',
      regex: /^(None|https?:\/\/[\da-z.-]+\.[a-z.]{2,6}([/\w.-]*)*\/?)$/,
      errorMessage: 'Please enter a valid URL or "None".'
    }
  ]

  function updateValidationMessages (isValid) {
    if (isValid) {
      validationMessages.style.display = 'block'
      validationMessages.classList.remove('alert-danger')
      validationMessages.classList.add('alert-success')
      validationMessages.textContent = 'All fields are valid!'
    } else {
      validationMessages.style.display = 'block'
      validationMessages.classList.remove('alert-success')
      validationMessages.classList.add('alert-danger')
      validationMessages.textContent = 'Please fix the highlighted errors before submitting.'
    }
  }

  function validateForm () {
    let isFormValid = true

    fieldsToValidate.forEach(({ id, regex, errorMessage }) => {
      // Handle dynamically generated asset_directory inputs
      const fields = id === 'asset_directory'
        ? document.querySelectorAll('input[name="asset_directory"]')
        : [document.getElementById(id)]

      fields.forEach((field) => {
        if (field) {
          const isValid = validateField(field, regex, errorMessage)
          if (!isValid) {
            isFormValid = false
          }
        }
      })
    })

    updateValidationMessages(isFormValid)
    return isFormValid
  }

  document.querySelectorAll('input[name="asset_directory"]').forEach((input) => {
    const fieldToValidate = fieldsToValidate.find(field => field.id === 'asset_directory')
    if (fieldToValidate) {
      input.addEventListener('input', function () {
        validateField(input, fieldToValidate.regex, fieldToValidate.errorMessage)
        validateForm() // Recheck the entire form
      })
    }
  })

  document.querySelectorAll('input, select, textarea').forEach((element) => {
    const fieldToValidate = fieldsToValidate.find((field) => field.id === element.id)
    if (fieldToValidate) {
      // Add real-time validation
      element.addEventListener('input', function () {
        const isValid = validateField(this, fieldToValidate.regex, fieldToValidate.errorMessage)
        updateValidationMessages(isValid && validateForm())
      })
    }
  })

  const assetDirectoryContainer = document.getElementById('asset_directory_container')
  const addAssetDirectoryButton = document.getElementById('add-asset-directory')

  // Add new asset directory input field
  addAssetDirectoryButton.addEventListener('click', () => {
    const newFieldGroup = document.createElement('div')
    newFieldGroup.className = 'input-group mb-2'

    newFieldGroup.innerHTML = `
        <input type="text" class="form-control" name="asset_directory" placeholder="Add Asset Directory">
        <button class="btn btn-danger remove-asset-directory" type="button">Remove</button>
    `
    assetDirectoryContainer.appendChild(newFieldGroup)

    // Attach validation to the new field
    const newField = newFieldGroup.querySelector('input[name="asset_directory"]')
    const fieldToValidate = fieldsToValidate.find(field => field.id === 'asset_directory')
    if (fieldToValidate) {
      newField.addEventListener('input', function () {
        validateField(newField, fieldToValidate.regex, fieldToValidate.errorMessage)
        validateForm() // Recheck the form
      })
    }
  })

  // Remove an asset directory input field
  assetDirectoryContainer.addEventListener('click', (event) => {
    if (event.target.classList.contains('remove-asset-directory')) {
      const fieldGroup = event.target.closest('.input-group')
      assetDirectoryContainer.removeChild(fieldGroup)
    }
  })

  // Validate form before submission
  configForm.addEventListener('submit', function (event) {
    if (!validateForm()) {
      event.preventDefault() // Prevent form submission if validation fails
      setSettingsValidated(false)
    } else {
      setSettingsValidated(true)
    }
  })

  // Validate form before navigation (Next, Previous, JumpTo)
  document.querySelectorAll('.next-button, .previous-button, .jump-to-button').forEach((button) => {
    button.addEventListener('click', function (event) {
      if (!validateForm()) {
        event.preventDefault() // Prevent navigation
        setSettingsValidated(false)
      } else {
        setSettingsValidated(true)
      }
    })
  })
})
