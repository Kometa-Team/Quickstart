/* global showToast, bootstrap, $ */

/* eslint-disable no-unused-vars */
function toggleConfigInput (selectElement) {
  const newConfigInputContainer = document.getElementById('newConfigInput')

  if (selectElement.value === 'add_config') {
    newConfigInputContainer.style.display = 'block'
  } else {
    newConfigInputContainer.style.display = 'none'

    // 🛠️ Reset validation when hiding input
    const newConfigInput = document.getElementById('newConfigName')
    removeValidationMessages(newConfigInput)
  }
}

function applyValidationStyles (inputElement, type) {
  removeValidationMessages(inputElement)

  let iconHTML = ''

  if (type === 'error') {
    inputElement.classList.add('is-invalid')
    inputElement.style.border = '1px solid #dc3545' // 🔴 Red border
    iconHTML = '<div class="invalid-feedback"><i class="bi bi-exclamation-triangle-fill text-danger"></i> Name already exists. Pick from dropdown instead?</div>'
  } else if (type === 'success') {
    inputElement.classList.add('is-valid')
    inputElement.style.border = '1px solid #28a745' // Green border
    iconHTML = '<div class="valid-feedback"><i class="bi bi-check-circle-fill text-success"></i> Name is available</div>'
  }

  inputElement.insertAdjacentHTML('afterend', iconHTML)
}

function removeValidationMessages (inputElement) {
  inputElement.classList.remove('is-invalid', 'is-valid')
  inputElement.style.border = ''
  const feedback = inputElement.parentElement.querySelector('.invalid-feedback, .valid-feedback')
  if (feedback) feedback.remove()
}

/* eslint-enable no-unused-vars */

document.addEventListener('DOMContentLoaded', function () {
  const configSelector = document.getElementById('configSelector')
  const newConfigInput = document.getElementById('newConfigName')
  const resetConfigButton = document.getElementById('resetConfigButton')
  const deleteConfigButton = document.getElementById('deleteConfigButton')
  const confirmConfigActionButton = document.getElementById('confirmConfigAction')

  const configActionModalElement = document.getElementById('configActionModal')
  let configActionModal = null

  if (configActionModalElement) {
    configActionModal = new bootstrap.Modal(configActionModalElement)
  } else {
    console.warn('⚠️ Warning: configActionModal not found in the DOM.')
  }

  let currentAction = ''

  // Ensure buttons are enabled if the config isn't "Add Config"
  function updateButtonState () {
    const isAddConfig = configSelector.value === 'add_config'
    const onlyAddConfigAvailable = configSelector.options.length === 1 && isAddConfig // Check if it's the only option

    resetConfigButton.disabled = isAddConfig
    deleteConfigButton.disabled = isAddConfig

    // 🛠️ Ensure input box is visible if "Add Config" is the only option
    if (onlyAddConfigAvailable) {
      document.getElementById('newConfigInput').style.display = 'block'
    } else {
      toggleConfigInput(configSelector)
    }
  }

  // Ensure input box appears on page load if necessary
  updateButtonState()

  configSelector.addEventListener('change', function () {
    updateButtonState()
  })

  document.querySelectorAll('[data-bs-toggle="modal"]').forEach(button => {
    button.addEventListener('click', function () {
      currentAction = this.dataset.action
      const selectedConfig = configSelector.value

      if (!selectedConfig || selectedConfig === 'add_config') {
        showToast('error', 'Please select a valid config.')
        return
      }

      const modalTitle = document.getElementById('configActionModalLabel')
      const modalBody = document.getElementById('configActionModalBody')

      if (!modalTitle || !modalBody) {
        console.error('⚠️ Modal elements not found in the DOM!')
        return
      }

      if (currentAction === 'reset') {
        modalTitle.textContent = 'Reset Config'
        modalBody.textContent = `Are you sure you want to reset "${selectedConfig}"? This will wipe all settings, but keep the config available.`
      } else if (currentAction === 'delete') {
        modalTitle.textContent = 'Delete Config'
        modalBody.textContent = `Are you sure you want to delete "${selectedConfig}" permanently? This action cannot be undone.`
      }
    })
  })

  confirmConfigActionButton.addEventListener('click', function () {
    const selectedConfig = configSelector.value

    if (!selectedConfig || selectedConfig === 'add_config') {
      showToast('error', 'Please select a valid config.')
      return
    }

    if (currentAction === 'reset') {
      $.post('/clear_session', { name: selectedConfig }, function (response) {
        if (response.status === 'success') {
          showToast('success', response.message)
          setTimeout(() => {
            window.location.reload()
          }, 4500)
        } else {
          showToast('error', response.message || 'An unexpected error occurred.')
        }
      }).fail(function (error) {
        const errorMessage = error.responseJSON?.message || 'An unknown error occurred.'
        showToast('error', errorMessage)
      })
    } else if (currentAction === 'delete') {
      fetch(`/clear_data/${selectedConfig}`, { method: 'GET' })
        .then(response => {
          if (response.ok) {
            return response.text()
          }
          throw new Error('Failed to delete config.')
        })
        .then(() => {
          showToast('success', `Config '${selectedConfig}' deleted successfully.`)

          const optionToRemove = configSelector.querySelector(`option[value="${selectedConfig}"]`)
          if (optionToRemove) {
            const nextOption = optionToRemove.nextElementSibling || optionToRemove.previousElementSibling
            optionToRemove.remove()

            configSelector.value = nextOption ? nextOption.value : 'add_config'
          }

          updateButtonState()

          if (configActionModal) {
            configActionModal.hide()
          }
        })
        .catch(error => {
          console.error('Error:', error)
          showToast('error', 'Failed to delete config.')
        })
    }
  })

  if (newConfigInput) {
    newConfigInput.addEventListener('input', function () {
      let text = newConfigInput.value
      text = text.toLowerCase()
      text = text.replace(/[^a-z0-9_]/g, '')
      newConfigInput.value = text
      checkDuplicateConfigName()
    })
  }

  // Show test libraries banner or silently pull if valid
  if (window.pageInfo?.install_type?.startsWith('Local-')) {
    const testLibStatus = document.getElementById('test-lib-status')
    const cloneBtn = document.getElementById('clone-test-lib-btn')

    if (testLibStatus && cloneBtn) {
      fetch('/check-test-libraries')
        .then(res => res.json())
        .then(data => {
          if (!data.found) {
            // Folder doesn't exist → show clone banner
            testLibStatus.classList.remove('d-none')
          } else if (data.found && data.is_git_repo) {
            // Folder exists and is a git repo → show permanent success message and silently pull
            testLibStatus.classList.remove('d-none', 'alert-warning', 'alert-danger')
            testLibStatus.classList.add('alert-success')
            testLibStatus.innerHTML = '<strong>✅ Test libraries already set up.</strong>'
            // Folder exists and is a git repo → silently pull
            fetch('/clone-test-libraries', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ quickstart_root: window.pageInfo.quickstart_root })
            })
              .then(res => res.json())
              .then(result => {
                if (result.success) {
                  showToast('success', result.message || 'Test libraries updated successfully.')
                } else {
                  showToast('error', result.message)
                }
              })
              .catch(err => showToast('error', `Update failed: ${err.message}`))
          } else {
            // Folder exists but not a git repo → show error banner
            testLibStatus.classList.remove('d-none')
            testLibStatus.classList.remove('alert-warning')
            testLibStatus.classList.add('alert-danger')
            testLibStatus.innerHTML = `
            <strong>⚠️ Existing folder is not a git repo.</strong>
            <br>Please delete the <code>plex_test_libraries</code> folder manually and try again.
          `
          }
        })

      // Manual clone button
      cloneBtn.addEventListener('click', () => {
        cloneBtn.disabled = true
        cloneBtn.innerHTML = 'Cloning...'

        fetch('/clone-test-libraries', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ quickstart_root: window.pageInfo.quickstart_root })
        })
          .then(res => res.json())
          .then(result => {
            if (result.success) {
              testLibStatus.classList.remove('alert-warning')
              testLibStatus.classList.add('alert-success')
              testLibStatus.innerHTML = `<strong>✅ ${result.message}</strong>`
            } else {
              testLibStatus.classList.remove('alert-warning')
              testLibStatus.classList.add('alert-danger')
              testLibStatus.innerHTML = `<strong>❌ ${result.message}</strong>`
            }
          })
          .catch(err => {
            testLibStatus.classList.remove('alert-warning')
            testLibStatus.classList.add('alert-danger')
            testLibStatus.innerHTML = `<strong>❌ Clone failed:</strong> ${err.message}`
          })
      })
    }
  }

  function checkDuplicateConfigName () {
    const newConfigName = newConfigInput.value.trim().toLowerCase()
    let isDuplicate = false

    removeValidationMessages(newConfigInput)

    for (const option of configSelector.options) {
      if (option.value.trim().toLowerCase() === newConfigName) {
        isDuplicate = true
        break
      }
    }

    if (isDuplicate) {
      showToast('error', `Config "${newConfigInput.value}" already exists!`)
      applyValidationStyles(newConfigInput, 'error')
    } else if (newConfigName !== '') {
      applyValidationStyles(newConfigInput, 'success')
    }
  }
})
