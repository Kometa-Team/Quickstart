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
    inputElement.style.border = '1px solid #28a745' // ✅ Green border
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

  configSelector.dispatchEvent(new Event('change'))
  // ✅ Ensure buttons are enabled if the config isn't "Add Config"
  function updateButtonState () {
    const isAddConfig = configSelector.value === 'add_config'
    resetConfigButton.disabled = isAddConfig
    deleteConfigButton.disabled = isAddConfig
  }

  // ✅ Trigger `change` event on page load to enable/disable buttons properly
  updateButtonState()

  configSelector.addEventListener('change', function () {
    const isAddConfig = configSelector.value === 'add_config'

    resetConfigButton.disabled = isAddConfig
    deleteConfigButton.disabled = isAddConfig
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
      if (!modalTitle) {
        console.error('⚠️ configActionModalLabel not found in the DOM!')
        return
      }

      const modalBody = document.getElementById('configActionModalBody')
      if (!modalBody) {
        console.error('⚠️ configActionModalBody not found in the DOM!')
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

          const isAddConfig = configSelector.value === 'add_config'
          resetConfigButton.disabled = isAddConfig
          deleteConfigButton.disabled = isAddConfig

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
