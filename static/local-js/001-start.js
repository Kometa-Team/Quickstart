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
  const installType = window.pageInfo?.install_type || ''
  const isDocker = installType === 'Docker'
  const isFrozen = installType.startsWith('Frozen-')
  const isLocal = installType.startsWith('Local-')
  const isManagedInstall = isDocker || isFrozen || isLocal

  if (isManagedInstall) {
    const testLibStatus = document.getElementById('test-lib-status')
    const statusMsg = document.getElementById('test-lib-status-message')
    const cloneBtn = document.getElementById('clone-test-lib-btn')
    const purgeBtn = document.getElementById('purge-test-lib-btn')

    if (testLibStatus && statusMsg && cloneBtn && purgeBtn) {
      fetch('/check-test-libraries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quickstart_root: window.pageInfo.quickstart_root,
          use_config_dir: isDocker || isFrozen
        })
      })
        .then(res => res.json())
        .then(data => {
          const pathHtml = data.target_path ? `<br><code>${data.target_path}</code>` : ''

          // Not found: show clone only
          if (!data.found) {
            testLibStatus.classList.remove('d-none', 'alert-success', 'alert-danger')
            testLibStatus.classList.add('alert-warning')
            statusMsg.innerHTML = `
            <strong>Test media libraries not found.</strong>
            <span class="ms-1">We recommend setting them up for testing with Kometa. Be patient as the repository is about 7GB.</span>
            ${pathHtml}
          `
            cloneBtn.classList.remove('d-none')
            purgeBtn.classList.add('d-none')
            return
          }

          // Found: show purge only
          testLibStatus.classList.remove('d-none', 'alert-warning', 'alert-danger')
          testLibStatus.classList.add('alert-success')
          cloneBtn.classList.add('d-none')
          purgeBtn.classList.remove('d-none')

          if (data.is_git_repo) {
            statusMsg.innerHTML = `<strong>✅ Test libraries already set up.</strong>${pathHtml}`

            // 🔄 Silently pull updates
            fetch('/clone-test-libraries', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                quickstart_root: window.pageInfo.quickstart_root,
                use_config_dir: isDocker || isFrozen
              })
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
            // ZIP install
            let shaNotice = ''
            if (data.local_sha && data.remote_sha) {
              shaNotice = `<br><small>Installed version: <code>${data.local_sha}</code> • Latest: <code>${data.remote_sha}</code></small>`
            }

            statusMsg.innerHTML = `<strong>✅ Test libraries already set up (ZIP install).</strong>${pathHtml}${shaNotice}`

            if (data.is_outdated) {
              showToast(
                'warning',
                `⚠️ A new version of the test libraries is available. Installed: ${data.local_sha}, Latest: ${data.remote_sha}`
              )
            }
          }
        })

      // PURGE BUTTON
      // Bind Bootstrap modal to purge button
      purgeBtn.addEventListener('click', () => {
        const deleteModal = new bootstrap.Modal(document.getElementById('confirm-delete-test-libraries'))
        deleteModal.show()
      })

      // When user confirms in modal
      document.getElementById('confirm-delete-test-libraries-btn').addEventListener('click', () => {
        const deleteModalEl = document.getElementById('confirm-delete-test-libraries')
        const deleteModal = bootstrap.Modal.getInstance(deleteModalEl)
        deleteModal.hide()

        purgeBtn.disabled = true
        purgeBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> Purging...'

        fetch('/purge-test-libraries', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            quickstart_root: window.pageInfo.quickstart_root,
            use_config_dir: isDocker || isFrozen
          })
        })
          .then(res => res.json())
          .then(result => {
            purgeBtn.disabled = false
            purgeBtn.innerHTML = '<i class="bi bi-trash3 me-1"></i> Delete Test Libraries'

            if (result.success) {
              showToast('success', result.message)
              testLibStatus.classList.remove('alert-danger', 'alert-success')
              testLibStatus.classList.add('alert-warning')
              statusMsg.innerHTML = `
          <strong>🗑️ ${result.message}</strong>
          <span class="ms-1">You can re-download the test libraries if needed.</span>
        `
              purgeBtn.classList.add('d-none')
              cloneBtn.classList.remove('d-none')
            } else {
              showToast('error', result.message)
            }
          })
          .catch(err => {
            purgeBtn.disabled = false
            purgeBtn.innerHTML = '<i class="bi bi-trash3 me-1"></i> Delete Test Libraries'
            showToast('error', `Failed to purge: ${err.message}`)
          })
      })

      // CLONE BUTTON
      cloneBtn.addEventListener('click', () => {
        cloneBtn.disabled = true
        cloneBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> Downloading test media (~7GB)...'

        let toastCounter = 0
        const toastInterval = setInterval(() => {
          toastCounter += 1
          showToast('info', `Still downloading test libraries... (${toastCounter * 30} seconds elapsed)`)
        }, 30000)

        fetch('/clone-test-libraries', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            quickstart_root: window.pageInfo.quickstart_root,
            use_config_dir: isDocker || isFrozen
          })
        })
          .then(res => res.json())
          .then(result => {
            clearInterval(toastInterval)
            cloneBtn.innerHTML = 'Clone Again'
            cloneBtn.disabled = false

            const pathHtml = result.target_path ? `<br><code>${result.target_path}</code>` : ''
            if (result.success) {
              testLibStatus.classList.remove('alert-warning', 'alert-danger')
              testLibStatus.classList.add('alert-success')
              statusMsg.innerHTML = `<strong>✅ ${result.message}</strong>${pathHtml}`
              cloneBtn.classList.add('d-none')
              purgeBtn.classList.remove('d-none')
            } else {
              testLibStatus.classList.remove('alert-warning', 'alert-success')
              testLibStatus.classList.add('alert-danger')
              statusMsg.innerHTML = `<strong>❌ ${result.message}</strong>`
            }
          })
          .catch(err => {
            clearInterval(toastInterval)
            cloneBtn.innerHTML = 'Clone Again'
            cloneBtn.disabled = false
            testLibStatus.classList.remove('alert-warning', 'alert-success')
            testLibStatus.classList.add('alert-danger')
            statusMsg.innerHTML = `<strong>❌ Clone failed:</strong> ${err.message}`
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
