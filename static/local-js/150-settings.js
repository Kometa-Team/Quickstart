/* global PathValidation, bootstrap */

document.addEventListener('DOMContentLoaded', function () {
  const validatedAtInput = document.getElementById('settings_validated_at')
  let settingsTouched = false
  const saveSyncChangesButton = document.getElementById('saveSyncChangesButton')
  const saveExcludeChangesButton = document.getElementById('saveExcludeChangesButton')
  const configForm = document.getElementById('configForm')
  const validationMessages = document.getElementById('validation-messages')
  let syncUsersModal = document.getElementById('syncUsersModal')
  let excludeUsersModal = document.getElementById('excludeUsersModal')

  function ensureSettingsModalRoot (modalEl) {
    if (!modalEl || !document.body) return modalEl
    const modalId = modalEl.id
    modalEl.dataset.settingsModal = 'true'
    if (modalId) {
      const bodyModal = Array.from(document.body.querySelectorAll('[data-settings-modal]'))
        .find(el => el.id === modalId && el !== modalEl)
      if (bodyModal) {
        if (modalEl.parentElement) modalEl.remove()
        return bodyModal
      }
    }
    if (modalEl.parentElement !== document.body) {
      document.body.appendChild(modalEl)
    }
    return modalEl
  }

  function syncSettingsModalBackdrop (modalEl) {
    if (!modalEl) return
    modalEl.style.zIndex = '2000'
    modalEl.style.pointerEvents = 'auto'
    modalEl.removeAttribute('inert')

    const dialog = modalEl.querySelector('.modal-dialog')
    if (dialog) dialog.style.pointerEvents = 'auto'

    const content = modalEl.querySelector('.modal-content')
    if (content) content.style.pointerEvents = 'auto'

    const latestBackdrop = Array.from(document.querySelectorAll('.modal-backdrop')).at(-1)
    if (latestBackdrop) latestBackdrop.style.zIndex = '1990'
  }

  function cleanupSettingsModalBackdrops () {
    if (document.querySelector('.modal.show')) return
    document.querySelectorAll('.modal-backdrop').forEach(backdrop => backdrop.remove())
  }

  function queueSettingsModalBackdropSync (modalEl) {
    if (window && typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(() => syncSettingsModalBackdrop(modalEl))
      return
    }
    syncSettingsModalBackdrop(modalEl)
  }

  function prepareSettingsModal (modalEl) {
    if (!modalEl) return modalEl
    modalEl = ensureSettingsModalRoot(modalEl)
    if (modalEl.dataset.settingsModalPrepared === 'true') return modalEl
    modalEl.dataset.settingsModalPrepared = 'true'
    modalEl.addEventListener('show.bs.modal', function () {
      syncSettingsModalBackdrop(modalEl)
      queueSettingsModalBackdropSync(modalEl)
    })
    modalEl.addEventListener('shown.bs.modal', function () {
      syncSettingsModalBackdrop(modalEl)
    })
    modalEl.addEventListener('hidden.bs.modal', function () {
      cleanupSettingsModalBackdrops()
    })
    return modalEl
  }

  function hideSettingsModal (modalEl) {
    if (!modalEl || typeof bootstrap === 'undefined' || !bootstrap.Modal) return
    const modal = bootstrap.Modal.getInstance(modalEl)
    if (modal) modal.hide()
  }

  syncUsersModal = prepareSettingsModal(syncUsersModal)
  excludeUsersModal = prepareSettingsModal(excludeUsersModal)

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
  if (syncUsersModal) {
    syncUsersModal.addEventListener('show.bs.modal', function () {
      populateModalToggles('playlist_sync_to_users', '#syncUsersModal', 'sync-user-toggle')
    })
  }

  // Populate Exclude Users modal when opened
  if (excludeUsersModal) {
    excludeUsersModal.addEventListener('show.bs.modal', function () {
      populateModalToggles('playlist_exclude_users', '#excludeUsersModal', 'exclude-user-toggle')
    })
  }

  if (saveSyncChangesButton) {
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

      hideSettingsModal(syncUsersModal)

      // Mark settings as invalid until re-validated
      setSettingsValidated(false)
    })
  }
  if (saveExcludeChangesButton) {
    saveExcludeChangesButton.addEventListener('click', function () {
      const selectedUsers = []
      const checkboxes = document.querySelectorAll('#excludeUserListForm input[type="checkbox"]:checked')

      checkboxes.forEach((checkbox) => {
        selectedUsers.push(checkbox.value)
      })

      const csvUsers = selectedUsers.join(', ')
      document.getElementById('playlist_exclude_users').value = csvUsers
      hideSettingsModal(excludeUsersModal)
      setSettingsValidated(false)
    })
  }

  function setSettingsValidated (isValid) {
    const settingsValidatedInput = document.getElementById('settings_validated')
    settingsValidatedInput.value = isValid ? 'true' : 'false'
    if (validatedAtInput) {
      if (isValid) {
        if (!validatedAtInput.value || settingsTouched) {
          validatedAtInput.value = new Date().toISOString()
        }
      } else {
        validatedAtInput.value = ''
      }
    }
    if (window.QSValidationCallouts && typeof window.QSValidationCallouts.refresh === 'function') {
      window.QSValidationCallouts.refresh('settings_validated')
    }
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

  function focusFieldFromHash () {
    const hash = String(window.location.hash || '').trim()
    if (!hash || hash.length < 2) return
    const field = document.getElementById(hash.slice(1))
    if (!field) return

    showAccordionForField(field)
    window.setTimeout(() => {
      field.scrollIntoView({ behavior: 'smooth', block: 'center' })
      if (typeof field.focus === 'function') {
        field.focus({ preventScroll: true })
      }
    }, 200)
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
      id: 'asset_depth',
      regex: /^(0|[1-9]\d*)$/,
      errorMessage: 'Please enter a valid integer (0 or greater).'
    },
    {
      id: 'overlay_artwork_quality',
      regex: /^(|100|[1-9][0-9]?)$/,
      errorMessage: 'Please enter an integer between 1 and 100, or leave blank.'
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
      regex: /^(|None|\d{1,8}(,\d{1,8})*)$/i,
      errorMessage: 'Please enter a valid CSV list of numeric IDs (1-8 digits), "None", or leave blank.'
    },
    {
      id: 'ignore_imdb_ids',
      regex: /^(|None|tt\d{7,8}(,tt\d{7,8})*)$/i,
      errorMessage: 'Please enter a valid CSV list of IMDb IDs (e.g., tt1234567), "None", or leave blank.'
    },
    {
      id: 'custom_repo',
      regex: /^(|None|https?:\/\/[\da-z.-]+\.[a-z.]{2,6}([/\w.-]*)*\/?)$/i,
      errorMessage: 'Please enter a valid URL, "None", or leave blank.'
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
      const field = document.getElementById(id)
      if (field) {
        const isValid = validateField(field, regex, errorMessage)
        if (!isValid) {
          isFormValid = false
        }
      }
    })

    if (typeof PathValidation !== 'undefined' && PathValidation.validateAll) {
      const pathsValid = PathValidation.validateAll()
      if (!pathsValid) {
        isFormValid = false
      }
    }

    updateValidationMessages(isFormValid)
    return isFormValid
  }

  document.querySelectorAll('input, select, textarea').forEach((element) => {
    const markTouched = (event) => {
      if (event && event.isTrusted === false) return
      settingsTouched = true
    }
    element.addEventListener('input', markTouched)
    element.addEventListener('change', markTouched)
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

    const input = document.createElement('input')
    input.type = 'text'
    input.className = 'form-control'
    input.name = 'asset_directory'
    input.placeholder = 'Add Asset Directory'

    const removeButton = document.createElement('button')
    removeButton.className = 'btn btn-danger remove-asset-directory'
    removeButton.type = 'button'
    removeButton.textContent = 'Remove'

    newFieldGroup.append(input, removeButton)
    assetDirectoryContainer.appendChild(newFieldGroup)
    const newField = newFieldGroup.querySelector('input[name="asset_directory"]')
    if (newField && typeof PathValidation !== 'undefined' && PathValidation.attach) {
      PathValidation.attach(newFieldGroup)
    }
  })

  // Remove an asset directory input field
  assetDirectoryContainer.addEventListener('click', (event) => {
    if (event.target.classList.contains('remove-asset-directory')) {
      const fieldGroup = event.target.closest('.input-group')
      if (!fieldGroup) return
      let next = fieldGroup.nextElementSibling
      while (next && next.dataset && next.dataset.pathHint) {
        const toRemove = next
        next = next.nextElementSibling
        toRemove.remove()
      }
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

  // Sidebar step pills also navigate via jumpTo(), so validate here before that submit runs.
  document.addEventListener('qs:before-step-navigation', function (event) {
    const detail = event && event.detail ? event.detail : {}
    const source = String(detail.source || '').trim().toLowerCase()
    if (source !== 'jump') return

    const workspaceSection = document.querySelector('.qs-workspace-section[data-current-step]')
    const currentStep = workspaceSection ? String(workspaceSection.dataset.currentStep || '').trim() : ''
    if (currentStep !== '150-settings') return

    const targetStep = String(detail.targetPage || '').trim()
    if (!targetStep || targetStep === currentStep) return

    if (!validateForm()) {
      event.preventDefault()
      setSettingsValidated(false)
    } else {
      setSettingsValidated(true)
    }
  })

  focusFieldFromHash()
  window.addEventListener('hashchange', focusFieldFromHash)
})
