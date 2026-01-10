/* global showToast, bootstrap, $ */

/* ============================== */
/* Helpers for the config UI      */
/* ============================== */

function toggleConfigInput (selectElement) {
  const box = document.getElementById('newConfigInput')
  if (!box) return

  const adding = selectElement.value === 'add_config'
  box.classList.toggle('d-none', !adding)

  if (!adding) {
    const input = document.getElementById('newConfigName')
    if (input) removeValidationMessages(input)
  }
}

// expose for inline HTML usage: onchange="toggleConfigInput(this)"
window.toggleConfigInput = toggleConfigInput

function applyValidationStyles (inputElement, type) {
  removeValidationMessages(inputElement)
  let iconHTML = ''
  if (type === 'error') {
    inputElement.classList.add('is-invalid')
    inputElement.style.border = '1px solid #dc3545'
    iconHTML = '<div class="invalid-feedback"><i class="bi bi-exclamation-triangle-fill text-danger"></i> Name already exists. Pick from dropdown instead?</div>'
  } else if (type === 'success') {
    inputElement.classList.add('is-valid')
    inputElement.style.border = '1px solid #28a745'
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

/* ============================== */
/* Main page logic                */
/* ============================== */

document.addEventListener('DOMContentLoaded', function () {
  const configSelector = document.getElementById('configSelector')
  const newConfigInput = document.getElementById('newConfigName')
  const resetConfigButton = document.getElementById('resetConfigButton')
  const deleteConfigButton = document.getElementById('deleteConfigButton')
  const confirmConfigActionButton = document.getElementById('confirmConfigAction')
  const bulkDeleteModalEl = document.getElementById('bulkDeleteModal')
  const bulkDeleteList = document.getElementById('bulkDeleteList')
  const bulkDeleteSelectAll = document.getElementById('bulkDeleteSelectAll')
  const bulkDeleteCount = document.getElementById('bulkDeleteCount')
  const confirmBulkDeleteButton = document.getElementById('confirmBulkDeleteButton')
  const confirmShutdownButton = document.getElementById('confirmShutdownButton')
  const shutdownModalEl = document.getElementById('shutdownModal')
  const shutdownCancelButton = document.getElementById('shutdownCancelButton')

  const configActionModalElement = document.getElementById('configActionModal')
  let configActionModal = null
  if (configActionModalElement) configActionModal = new bootstrap.Modal(configActionModalElement)

  let currentAction = ''

  function updateButtonState () {
    const isAddConfig = configSelector.value === 'add_config'
    const onlyAddConfigAvailable = configSelector.options.length === 1 && isAddConfig

    resetConfigButton.disabled = isAddConfig
    deleteConfigButton.disabled = isAddConfig

    const box = document.getElementById('newConfigInput')
    if (box) box.classList.toggle('d-none', !(isAddConfig || onlyAddConfigAvailable))
  }

  updateButtonState()
  configSelector.addEventListener('change', updateButtonState)

  document.querySelectorAll('[data-action]').forEach(button => {
    button.addEventListener('click', function () {
      currentAction = this.dataset.action
      const selectedConfig = configSelector.value
      if (!selectedConfig || selectedConfig === 'add_config') {
        showToast('error', 'Please select a valid config.')
        return
      }
      const modalTitle = document.getElementById('configActionModalLabel')
      const modalBody = document.getElementById('configActionModalBody')
      if (!modalTitle || !modalBody) return
      if (currentAction === 'reset') {
        modalTitle.textContent = 'Reset Config'
        modalBody.textContent = `Are you sure you want to reset "${selectedConfig}"? This will wipe all settings, but keep the config available.`
      } else if (currentAction === 'delete') {
        modalTitle.textContent = 'Delete Config'
        modalBody.textContent = `Are you sure you want to delete "${selectedConfig}" permanently? This action cannot be undone.`
      }
    })
  })

  function getAvailableConfigs () {
    if (!configSelector) return []
    const names = Array.from(configSelector.options)
      .map(option => option.value)
      .filter(value => value && value !== 'add_config')
    return Array.from(new Set(names))
  }

  function updateBulkDeleteState () {
    if (!bulkDeleteList || !confirmBulkDeleteButton) return
    const allBoxes = bulkDeleteList.querySelectorAll('.bulk-delete-checkbox')
    const checked = bulkDeleteList.querySelectorAll('.bulk-delete-checkbox:checked')

    if (bulkDeleteCount) bulkDeleteCount.textContent = String(checked.length)
    confirmBulkDeleteButton.disabled = checked.length === 0

    if (bulkDeleteSelectAll) {
      bulkDeleteSelectAll.checked = allBoxes.length > 0 && checked.length === allBoxes.length
      bulkDeleteSelectAll.indeterminate = checked.length > 0 && checked.length < allBoxes.length
    }
  }

  function buildBulkDeleteRow (name, isCurrent, index) {
    const row = document.createElement('div')
    row.className = 'form-check bulk-delete-item'

    const input = document.createElement('input')
    input.type = 'checkbox'
    input.className = 'form-check-input bulk-delete-checkbox'
    input.value = name
    input.id = `bulk-delete-${index}-${name.replace(/[^a-zA-Z0-9_-]/g, '_')}`
    input.addEventListener('change', updateBulkDeleteState)

    const label = document.createElement('label')
    label.className = 'form-check-label'
    label.setAttribute('for', input.id)
    label.textContent = name

    if (isCurrent) {
      const badge = document.createElement('span')
      badge.className = 'badge bg-secondary ms-2'
      badge.textContent = 'current'
      label.appendChild(badge)
    }

    row.appendChild(input)
    row.appendChild(label)
    return row
  }

  function renderBulkDeleteList () {
    if (!bulkDeleteList) return
    bulkDeleteList.innerHTML = ''

    const configs = getAvailableConfigs()
    if (!configs.length) {
      const empty = document.createElement('div')
      empty.className = 'text-muted small'
      empty.textContent = 'No saved profiles found.'
      bulkDeleteList.appendChild(empty)
      if (bulkDeleteSelectAll) {
        bulkDeleteSelectAll.checked = false
        bulkDeleteSelectAll.indeterminate = false
        bulkDeleteSelectAll.disabled = true
      }
      updateBulkDeleteState()
      return
    }

    const currentConfig = window.pageInfo?.config_name || configSelector?.value
    configs.forEach((name, index) => {
      bulkDeleteList.appendChild(buildBulkDeleteRow(name, name === currentConfig, index))
    })

    if (bulkDeleteSelectAll) {
      bulkDeleteSelectAll.checked = false
      bulkDeleteSelectAll.indeterminate = false
      bulkDeleteSelectAll.disabled = false
    }
    updateBulkDeleteState()
  }

  if (bulkDeleteModalEl) {
    bulkDeleteModalEl.addEventListener('show.bs.modal', renderBulkDeleteList)
  }

  if (bulkDeleteSelectAll) {
    bulkDeleteSelectAll.addEventListener('change', () => {
      if (!bulkDeleteList) return
      const checkboxes = bulkDeleteList.querySelectorAll('.bulk-delete-checkbox')
      checkboxes.forEach(box => { box.checked = bulkDeleteSelectAll.checked })
      updateBulkDeleteState()
    })
  }

  if (confirmBulkDeleteButton) {
    confirmBulkDeleteButton.addEventListener('click', async () => {
      if (!bulkDeleteList) return
      const selected = Array.from(bulkDeleteList.querySelectorAll('.bulk-delete-checkbox:checked'))
        .map(box => box.value)
      if (!selected.length) {
        showToast('error', 'Select at least one profile to delete.')
        return
      }

      confirmBulkDeleteButton.disabled = true
      const originalText = confirmBulkDeleteButton.textContent
      confirmBulkDeleteButton.textContent = 'Deleting...'

      try {
        const res = await fetch('/bulk-delete-configs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ names: selected })
        })
        const data = await res.json()
        if (!res.ok || !data.success) {
          throw new Error(data.message || 'Failed to delete profiles.')
        }
        showToast('success', `Deleted ${data.deleted.length} profile(s).`)
        const modal = bootstrap.Modal.getInstance(bulkDeleteModalEl)
        if (modal) modal.hide()
        setTimeout(() => window.location.reload(), 1200)
      } catch (err) {
        confirmBulkDeleteButton.disabled = false
        confirmBulkDeleteButton.textContent = originalText
        showToast('error', err.message || 'Failed to delete profiles.')
      }
    })
  }

  if (confirmShutdownButton) {
    confirmShutdownButton.addEventListener('click', async () => {
      const modal = shutdownModalEl ? bootstrap.Modal.getInstance(shutdownModalEl) : null
      confirmShutdownButton.disabled = true
      const originalText = confirmShutdownButton.textContent
      confirmShutdownButton.textContent = 'Shutting down...'

      try {
        const res = await fetch('/shutdown', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            nonce: window.pageInfo?.shutdown_nonce,
            confirmed: true
          })
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok || !data.success) throw new Error(data.message || 'Shutdown request failed.')
        if (modal) modal.hide()
        showToast('info', data.message || 'Shutting down Quickstart...')
      } catch (err) {
        confirmShutdownButton.disabled = false
        confirmShutdownButton.textContent = originalText
        showToast('error', err.message || 'Failed to shut down Quickstart.')
      }
    })
  }

  if (shutdownModalEl && shutdownCancelButton) {
    shutdownModalEl.addEventListener('shown.bs.modal', () => {
      shutdownCancelButton.focus()
    })
  }

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
          setTimeout(() => window.location.reload(), 4500)
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
          if (response.ok) return response.text()
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
          if (configActionModal) configActionModal.hide()
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
      text = text.toLowerCase().replace(/[^a-z0-9_]/g, '')
      newConfigInput.value = text
      checkDuplicateConfigName()
    })
  }

  function checkDuplicateConfigName () {
    const name = newConfigInput.value.trim().toLowerCase()
    let dup = false
    removeValidationMessages(newConfigInput)
    for (const option of configSelector.options) {
      if (option.value.trim().toLowerCase() === name) { dup = true; break }
    }
    if (dup) {
      showToast('error', `Config "${newConfigInput.value}" already exists!`)
      applyValidationStyles(newConfigInput, 'error')
    } else if (name !== '') {
      applyValidationStyles(newConfigInput, 'success')
    }
  }

  /* ============================== */
  /* Test libraries UI + Progress   */
  /* ============================== */

  const testLibStatus = document.getElementById('test-lib-status')
  const statusMsg = document.getElementById('test-lib-status-message')
  const cloneBtn = document.getElementById('clone-test-lib-btn')
  const purgeBtn = document.getElementById('purge-test-lib-btn')
  const updateRow = document.getElementById('test-lib-update-row')
  const localShaEl = document.getElementById('test-lib-local-sha')
  const remoteShaEl = document.getElementById('test-lib-remote-sha')
  const updateBtn = document.getElementById('update-test-lib-btn')

  // Progress block (existing or injected)
  let progWrap = document.getElementById('test-lib-progress')
  let progBar = document.getElementById('test-lib-progress-bar')
  let progTxt = document.getElementById('test-lib-progress-text')
  if (!progWrap && testLibStatus) {
    testLibStatus.insertAdjacentHTML('beforeend', `
      <div id="test-lib-progress" class="d-none mt-2">
        <div class="progress" style="height:18px;">
          <div id="test-lib-progress-bar" class="progress-bar" role="progressbar" style="width:0%">0%</div>
        </div>
        <small id="test-lib-progress-text" class="text-muted"></small>
      </div>
    `)
    progWrap = document.getElementById('test-lib-progress')
    progBar = document.getElementById('test-lib-progress-bar')
    progTxt = document.getElementById('test-lib-progress-text')
  }

  // --- Spinner button helpers (prevents flicker) -------------------
  // Structure: <button id="clone-test-lib-btn"><span class="spin"></span><span class="btn-label"></span></button>
  function ensureBusyButtonSkeleton () {
    if (!cloneBtn.querySelector('.btn-label')) {
      cloneBtn.innerHTML = `
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        <span class="btn-label"></span>
      `
    } else if (!cloneBtn.querySelector('.spinner-border')) {
      cloneBtn.insertAdjacentHTML('afterbegin',
        '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>')
    }
  }
  function setButtonBusy (text) {
    ensureBusyButtonSkeleton()
    cloneBtn.disabled = true
    const label = cloneBtn.querySelector('.btn-label')
    if (label) label.textContent = text
  }
  function setButtonIdle (text) {
    cloneBtn.disabled = false
    const spin = cloneBtn.querySelector('.spinner-border')
    if (spin) spin.remove()
    const label = cloneBtn.querySelector('.btn-label')
    if (label) {
      label.remove()
      cloneBtn.textContent = text
    } else {
      cloneBtn.textContent = text
    }
  }
  function updateButtonLabel (text) {
    const label = cloneBtn.querySelector('.btn-label')
    if (label) label.textContent = text
  }

  // Elapsed time shown inside the button label (no DOM rebuilds)
  let elapsedTimer = null
  let startedAt = 0
  let baseBtnMsg = '' // e.g., "Downloading… 1.2 GB • 20 MB/s"
  function startElapsedTimer () {
    startedAt = Date.now()
    clearInterval(elapsedTimer)
    elapsedTimer = setInterval(() => {
      const s = Math.floor((Date.now() - startedAt) / 1000)
      const m = String(Math.floor(s / 60)).padStart(2, '0')
      const ss = String(s % 60).padStart(2, '0')
      updateButtonLabel(`${baseBtnMsg}  (${m}:${ss})`)
    }, 1000)
  }
  function stopElapsedTimer () {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }

  // ---------------------------------------------------------------

  const isManagedInstall = true

  function bytes (n) {
    if (!n && n !== 0) return ''
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    let i = 0
    let v = n
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
    return `${v.toFixed(v >= 10 || i < 2 ? 0 : 1)} ${units[i]}`
  }

  function setProgress (pct, text, { indeterminate = false } = {}) {
    if (!progWrap || !progBar || !progTxt) return
    progWrap.classList.remove('d-none')
    if (indeterminate) {
      progBar.classList.add('progress-bar-striped', 'progress-bar-animated')
      progBar.style.width = '100%'
      progBar.textContent = ''
    } else {
      progBar.classList.remove('progress-bar-striped', 'progress-bar-animated')
      const p = Math.max(0, Math.min(100, Number.isFinite(pct) ? pct : 0))
      progBar.style.width = p + '%'
      progBar.textContent = p + '%'
    }
    progTxt.textContent = text || ''
  }

  function resetProgress () {
    if (!progWrap || !progBar || !progTxt) return
    progWrap.classList.add('d-none')
    progBar.classList.remove('progress-bar-striped', 'progress-bar-animated')
    progBar.style.width = '0%'
    progBar.textContent = '0%'
    progTxt.textContent = ''
  }

  function setScenarioNotFound (pathHtml) {
    testLibStatus.classList.remove('d-none', 'alert-success', 'alert-danger')
    testLibStatus.classList.add('alert-warning')
    statusMsg.innerHTML = `
      <strong>Test media libraries not found.</strong>
      <span class="ms-1">We recommend setting them up for testing with Kometa. Be patient as the repository is about 7GB.</span>
      ${pathHtml || ''}
    `
    cloneBtn.classList.remove('d-none')
    purgeBtn.classList.add('d-none')
    updateRow?.classList.add('d-none')
  }

  function setScenarioFoundZip (data, pathHtml) {
    testLibStatus.classList.remove('d-none', 'alert-warning', 'alert-danger')
    testLibStatus.classList.add('alert-success')
    const shaNotice = (data.local_sha && data.remote_sha)
      ? `<br><small>Installed version: <code>${data.local_sha}</code> • Latest: <code>${data.remote_sha}</code></small>`
      : ''
    statusMsg.innerHTML = `<strong>✅ Test libraries already set up (ZIP install).</strong>${pathHtml || ''}${shaNotice}`
    cloneBtn.classList.add('d-none')
    purgeBtn.classList.remove('d-none')
    if (data.is_outdated) {
      updateRow?.classList.remove('d-none')
      if (localShaEl) localShaEl.textContent = data.local_sha || ''
      if (remoteShaEl) remoteShaEl.textContent = data.remote_sha || ''
    } else {
      updateRow?.classList.add('d-none')
    }
  }

  async function refreshStatus () {
    const res = await fetch('/check-test-libraries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        quickstart_root: window.pageInfo.quickstart_root,
        use_config_dir: true
      })
    })
    const data = await res.json()
    const pathHtml = data.target_path ? `<br><code>${data.target_path}</code>` : ''
    if (!data.found) setScenarioNotFound(pathHtml)
    else setScenarioFoundZip(data, pathHtml)
  }

  if (isManagedInstall && testLibStatus && statusMsg && cloneBtn && purgeBtn) {
    refreshStatus().catch(() => setScenarioNotFound(''))

    // PURGE (with confirm modal)
    purgeBtn.addEventListener('click', () => {
      const deleteModal = new bootstrap.Modal(document.getElementById('confirm-delete-test-libraries'))
      deleteModal.show()
    })

    document.getElementById('confirm-delete-test-libraries-btn').addEventListener('click', async () => {
      const deleteModalEl = document.getElementById('confirm-delete-test-libraries')
      const deleteModal = bootstrap.Modal.getInstance(deleteModalEl)
      deleteModal.hide()

      const prevText = cloneBtn.textContent
      purgeBtn.disabled = true
      purgeBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> Purging...'

      try {
        const res = await fetch('/purge-test-libraries', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            quickstart_root: window.pageInfo.quickstart_root,
            use_config_dir: true
          })
        }).then(r => r.json())

        purgeBtn.disabled = false
        purgeBtn.innerHTML = '<i class="bi bi-trash3 me-1"></i> Delete Test Libraries'

        if (res.success) {
          showToast('success', res.message)
          setScenarioNotFound(`<br><code>${res.message.replace('Test libraries deleted at: ', '')}</code>`)
          setButtonIdle(prevText || 'Download Test Libraries')
          resetProgress()
        } else {
          showToast('error', res.message)
        }
      } catch (err) {
        purgeBtn.disabled = false
        purgeBtn.innerHTML = '<i class="bi bi-trash3 me-1"></i> Delete Test Libraries'
        showToast('error', `Failed to purge: ${err.message}`)
      }
    })

    // DOWNLOAD / UPDATE flow (start + poll)
    let running = false

    async function startJobAndPoll () {
      if (running) return
      running = true

      const isUpdate = updateRow && !updateRow.classList.contains('d-none')
      baseBtnMsg = isUpdate ? 'Updating…' : 'Downloading…'

      setButtonBusy(`${baseBtnMsg} (00:00)`)
      if (updateBtn) updateBtn.disabled = true
      resetProgress()
      setProgress(0, isUpdate ? 'Preparing update…' : 'Preparing download…')
      startElapsedTimer()

      // 1) Start job
      let jobId = null
      try {
        const startRes = await fetch('/clone-test-libraries-start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            quickstart_root: window.pageInfo.quickstart_root,
            use_config_dir: true
          })
        }).then(r => r.json())
        if (!startRes.success) throw new Error(startRes.message || 'Failed to start')
        jobId = startRes.job_id
      } catch (err) {
        running = false
        stopElapsedTimer()
        setButtonIdle('Download Again')
        if (updateBtn) updateBtn.disabled = false
        showToast('error', `Failed to start: ${err.message}`)
        return
      }

      function setPhase (msg) {
        baseBtnMsg = msg // keep only the word; the timer appends (mm:ss)
        // also reflect immediately (don’t wait for the next 1s tick)
        const s = Math.floor((Date.now() - startedAt) / 1000)
        const m = String(Math.floor(s / 60)).padStart(2, '0')
        const ss = String(s % 60).padStart(2, '0')
        updateButtonLabel(`${baseBtnMsg}  (${m}:${ss})`)
      }

      // 2) Poll progress
      let lastDownloaded = 0
      let lastTs = Date.now()

      try {
        let done = false
        while (!done) {
          const prog = await fetch(`/clone-test-libraries-progress?job_id=${encodeURIComponent(jobId)}`).then(r => r.json())
          if (!prog.success) throw new Error(prog.message || 'Progress error')

          const phase = prog.phase
          if (phase === 'download') {
            const hasTotal = Number.isFinite(prog.total) && prog.total > 0
            const pct = (prog.pct == null && !hasTotal) ? null : prog.pct
            const now = Date.now()
            const dt = Math.max(1, now - lastTs) / 1000
            const deltaBytes = (prog.downloaded || 0) - lastDownloaded
            const speedStr = deltaBytes > 0 ? `${bytes(deltaBytes / dt)}/s` : ''
            lastDownloaded = prog.downloaded || 0
            lastTs = now

            // ✅ BUTTON: only the phase word + timer (kept elsewhere)
            setPhase('Downloading…')

            // Details stay under the bar
            if (pct === null) {
              setProgress(100, `Downloading… ${bytes(prog.downloaded || 0)} ${speedStr ? `• ${speedStr}` : ''}`, { indeterminate: true })
            } else {
              const totalStr = hasTotal ? ` / ${bytes(prog.total)}` : ''
              setProgress(pct, `Downloading… ${bytes(prog.downloaded || 0)}${totalStr} (${pct}%) ${speedStr ? `• ${speedStr}` : ''}`)
            }
          } else if (phase === 'extract') {
            setPhase('Extracting…')
            setProgress(prog.pct || 0, `Extracting… ${prog.files_done || 0}/${prog.files_total || 0} files`)
          } else if (phase === 'finalize') {
            setPhase('Finalizing…')
            setProgress(prog.pct || 95, 'Finalizing…')
          } else if (phase === 'done') {
            setPhase('Completed.')
            setProgress(100, 'Completed.')
            done = true
          } else if (phase === 'error') {
            throw new Error(prog.text || 'Unknown error')
          }

          await new Promise((resolve) => setTimeout(resolve, 1000))
        }

        await refreshStatus()
        showToast('success', 'Test libraries installed/updated successfully.')
      } catch (err) {
        testLibStatus.classList.remove('alert-success', 'alert-warning')
        testLibStatus.classList.add('alert-danger')
        statusMsg.innerHTML = `<strong>❌ ${String(err.message || err)}</strong>`
        showToast('error', String(err.message || err))
      } finally {
        running = false
        stopElapsedTimer()
        setButtonIdle('Download Again')
        if (updateBtn) updateBtn.disabled = false
      }
    }

    // Buttons
    cloneBtn.addEventListener('click', (e) => {
      e.preventDefault()
      startJobAndPoll()
    })

    if (updateBtn && !updateBtn.dataset.bound) {
      updateBtn.dataset.bound = '1'
      updateBtn.addEventListener('click', (e) => {
        e.preventDefault()
        startJobAndPoll()
      })
    }
  }
})
