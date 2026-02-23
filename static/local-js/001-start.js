/* global showToast, bootstrap, localStorage, $, PathValidation */

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

function applyValidationStyles (inputElement, type, message) {
  removeValidationMessages(inputElement)
  let iconHTML = ''
  if (type === 'error') {
    inputElement.classList.add('is-invalid')
    inputElement.style.border = '1px solid #dc3545'
    const msg = message || 'Name already exists. Pick from dropdown instead?'
    iconHTML = `<div class="invalid-feedback"><i class="bi bi-exclamation-triangle-fill text-danger"></i> ${msg}</div>`
  } else if (type === 'success') {
    inputElement.classList.add('is-valid')
    inputElement.style.border = '1px solid #28a745'
    const msg = message || 'Name is available'
    iconHTML = `<div class="valid-feedback"><i class="bi bi-check-circle-fill text-success"></i> ${msg}</div>`
  }
  inputElement.insertAdjacentHTML('afterend', iconHTML)
}

function removeValidationMessages (inputElement) {
  inputElement.classList.remove('is-invalid', 'is-valid')
  inputElement.style.border = ''
  const feedback = inputElement.parentElement.querySelector('.invalid-feedback, .valid-feedback')
  if (feedback) feedback.remove()
}

function sanitizeConfigName (value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9_]/g, '')
}

/* ============================== */
/* Main page logic                */
/* ============================== */

document.addEventListener('DOMContentLoaded', function () {
  const configSelector = document.getElementById('configSelector')
  const newConfigInput = document.getElementById('newConfigName')
  const resetConfigButton = document.getElementById('resetConfigButton')
  const deleteConfigButton = document.getElementById('deleteConfigButton')
  const renameConfigButton = document.getElementById('renameConfigButton')
  const confirmConfigActionButton = document.getElementById('confirmConfigAction')
  const bulkDeleteModalEl = document.getElementById('bulkDeleteModal')
  const bulkDeleteList = document.getElementById('bulkDeleteList')
  const bulkDeleteSelectAll = document.getElementById('bulkDeleteSelectAll')
  const bulkDeleteCount = document.getElementById('bulkDeleteCount')
  const confirmBulkDeleteButton = document.getElementById('confirmBulkDeleteButton')
  const configActionModalElement = document.getElementById('configActionModal')
  const renameConfigModalEl = document.getElementById('renameConfigModal')
  const renameConfigCurrentName = document.getElementById('renameConfigCurrentName')
  const renameConfigNewName = document.getElementById('renameConfigNewName')
  const renameConfigError = document.getElementById('renameConfigError')
  const confirmRenameConfig = document.getElementById('confirmRenameConfig')
  const importConfigModalEl = document.getElementById('importConfigModal')
  const importConfigFile = document.getElementById('importConfigFile')
  const importConfigName = document.getElementById('importConfigName')
  const importModeNew = document.getElementById('importModeNew')
  const importModeMerge = document.getElementById('importModeMerge')
  const importMergeBaseSection = document.getElementById('importMergeBaseSection')
  const importMergeBaseConfig = document.getElementById('importMergeBaseConfig')
  const importPlexCredentials = document.getElementById('importPlexCredentials')
  const importPlexUrl = document.getElementById('importPlexUrl')
  const importPlexToken = document.getElementById('importPlexToken')
  const importPlexTokenToggle = document.getElementById('importPlexTokenToggle')
  const importTmdbCredentials = document.getElementById('importTmdbCredentials')
  const importTmdbApiKey = document.getElementById('importTmdbApiKey')
  const importTmdbApiKeyToggle = document.getElementById('importTmdbApiKeyToggle')
  const importConfigError = document.getElementById('importConfigError')
  const previewImportButton = document.getElementById('previewImportButton')
  const confirmImportButton = document.getElementById('confirmImportButton')
  const importPreviewSection = document.getElementById('importPreviewSection')
  const importSummary = document.getElementById('importSummary')
  const importReport = document.getElementById('importReport')
  const downloadImportReport = document.getElementById('downloadImportReport')
  const importMergeSection = document.getElementById('importMergeSection')
  const importMergeSectionList = document.getElementById('importMergeSectionList')
  const importMergeSelectAll = document.getElementById('importMergeSelectAll')
  const importMergeSelectNone = document.getElementById('importMergeSelectNone')
  const importLibraryMappingSection = document.getElementById('importLibraryMappingSection')
  const importLibraryMappingList = document.getElementById('importLibraryMappingList')
  const importMappingNote = document.getElementById('importMappingNote')
  const importReportFilters = document.getElementById('importReportFilters')
  let configActionModal = null
  if (configActionModalElement) configActionModal = new bootstrap.Modal(configActionModalElement)

  let currentAction = ''
  let importToken = null
  let importReportHeader = ''
  let importReportBody = ''
  let importReportFilter = 'all'
  let importNeedsPlexCredentials = false
  let importNeedsTmdbCredentials = false

  if (importPlexTokenToggle && importPlexToken) {
    if (!importPlexToken.value.trim()) {
      importPlexToken.setAttribute('type', 'text')
      importPlexTokenToggle.innerHTML = '<i class="bi bi-eye-slash"></i>'
    }
    importPlexTokenToggle.addEventListener('click', () => {
      const isPassword = importPlexToken.getAttribute('type') === 'password'
      importPlexToken.setAttribute('type', isPassword ? 'text' : 'password')
      importPlexTokenToggle.innerHTML = isPassword ? '<i class="bi bi-eye-slash"></i>' : '<i class="bi bi-eye"></i>'
    })
  }

  if (importTmdbApiKeyToggle && importTmdbApiKey) {
    if (!importTmdbApiKey.value.trim()) {
      importTmdbApiKey.setAttribute('type', 'text')
      importTmdbApiKeyToggle.innerHTML = '<i class="bi bi-eye-slash"></i>'
    }
    importTmdbApiKeyToggle.addEventListener('click', () => {
      const isPassword = importTmdbApiKey.getAttribute('type') === 'password'
      importTmdbApiKey.setAttribute('type', isPassword ? 'text' : 'password')
      importTmdbApiKeyToggle.innerHTML = isPassword ? '<i class="bi bi-eye-slash"></i>' : '<i class="bi bi-eye"></i>'
    })
  }

  function updateButtonState () {
    const isAddConfig = configSelector.value === 'add_config'
    const onlyAddConfigAvailable = configSelector.options.length === 1 && isAddConfig

    resetConfigButton.disabled = isAddConfig
    if (deleteConfigButton) deleteConfigButton.disabled = isAddConfig
    if (renameConfigButton) renameConfigButton.disabled = isAddConfig

    const box = document.getElementById('newConfigInput')
    if (box) box.classList.toggle('d-none', !(isAddConfig || onlyAddConfigAvailable))
  }

  function updateConfigBadge (name) {
    const badgeBtn = document.querySelector('.config-badge-button[data-current]')
    if (!badgeBtn || !name) return
    badgeBtn.dataset.current = name
    const label = badgeBtn.querySelector('span')
    if (!label) return
    label.textContent = `Config: ${name}`
    const icon = document.createElement('i')
    icon.className = 'bi bi-chevron-down ms-1'
    label.appendChild(icon)
  }

  async function syncSelectedConfig () {
    if (!configSelector) return
    const selected = configSelector.value
    if (!selected || selected === 'add_config') return

    if (window.pageInfo && window.pageInfo.config_name === selected) {
      updateConfigBadge(selected)
      return
    }

    try {
      const res = await fetch('/switch-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: selected })
      })
      const data = await res.json()
      if (!res.ok || !data.success) {
        throw new Error(data.message || 'Failed to switch configs.')
      }
      if (window.pageInfo) window.pageInfo.config_name = data.name
      updateConfigBadge(data.name)
    } catch (err) {
      showToast('error', err.message || 'Failed to switch configs.')
    }
  }

  updateButtonState()
  configSelector.addEventListener('change', () => {
    updateButtonState()
    syncSelectedConfig()
  })

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
        modalTitle.textContent = 'Delete Configs'
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
      empty.textContent = 'No saved configs found.'
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
        showToast('error', 'Select at least one config to delete.')
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
          throw new Error(data.message || 'Failed to delete configs.')
        }
        showToast('success', `Deleted ${data.deleted.length} config(s).`)
        const modal = bootstrap.Modal.getInstance(bulkDeleteModalEl)
        if (modal) modal.hide()
        setTimeout(() => window.location.reload(), 1200)
      } catch (err) {
        confirmBulkDeleteButton.disabled = false
        confirmBulkDeleteButton.textContent = originalText
        showToast('error', err.message || 'Failed to delete configs.')
      }
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
      newConfigInput.value = sanitizeConfigName(newConfigInput.value)
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

  function isDuplicateName (name, exclude) {
    if (!name) return false
    const lowerName = name.toLowerCase()
    return getAvailableConfigs().some(existing => {
      if (exclude && existing.toLowerCase() === exclude.toLowerCase()) return false
      return existing.toLowerCase() === lowerName
    })
  }

  function setRenameError (message) {
    if (!renameConfigError) return
    if (!message) {
      renameConfigError.classList.add('d-none')
      renameConfigError.textContent = ''
      return
    }
    renameConfigError.classList.remove('d-none')
    renameConfigError.textContent = message
  }

  function updateRenameState () {
    if (!renameConfigNewName || !confirmRenameConfig) return
    const currentName = configSelector?.value || ''
    const sanitized = sanitizeConfigName(renameConfigNewName.value)
    renameConfigNewName.value = sanitized
    removeValidationMessages(renameConfigNewName)
    confirmRenameConfig.disabled = true
    setRenameError('')

    if (!sanitized) return
    if (currentName && sanitized.toLowerCase() === currentName.toLowerCase()) {
      applyValidationStyles(renameConfigNewName, 'error', 'Name must be different.')
      setRenameError('New name must be different.')
      return
    }
    if (isDuplicateName(sanitized, currentName)) {
      applyValidationStyles(renameConfigNewName, 'error', 'Name already exists.')
      setRenameError('Config name already exists.')
      return
    }
    applyValidationStyles(renameConfigNewName, 'success')
    confirmRenameConfig.disabled = false
  }

  if (renameConfigModalEl) {
    renameConfigModalEl.addEventListener('show.bs.modal', () => {
      const currentName = configSelector?.value || ''
      if (renameConfigCurrentName) renameConfigCurrentName.textContent = currentName || 'unknown'
      if (renameConfigNewName) {
        renameConfigNewName.value = ''
        removeValidationMessages(renameConfigNewName)
      }
      setRenameError('')
      if (confirmRenameConfig) confirmRenameConfig.disabled = true
    })
  }

  if (renameConfigNewName) {
    renameConfigNewName.addEventListener('input', updateRenameState)
  }

  if (confirmRenameConfig) {
    confirmRenameConfig.addEventListener('click', async () => {
      const oldName = configSelector?.value || ''
      const newName = sanitizeConfigName(renameConfigNewName?.value || '')
      if (!oldName || oldName === 'add_config') {
        showToast('error', 'Select a config to rename.')
        return
      }
      if (!newName) {
        setRenameError('Enter a new config name.')
        return
      }
      confirmRenameConfig.disabled = true
      try {
        const res = await fetch('/rename-config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ old_name: oldName, new_name: newName })
        })
        const data = await res.json()
        if (!res.ok || !data.success) {
          throw new Error(data.message || 'Rename failed.')
        }
        showToast('success', `Renamed '${oldName}' to '${data.new_name}'.`)
        const modal = bootstrap.Modal.getInstance(renameConfigModalEl)
        if (modal) modal.hide()
        setTimeout(() => window.location.reload(), 900)
      } catch (err) {
        confirmRenameConfig.disabled = false
        setRenameError(err.message || 'Rename failed.')
      }
    })
  }

  function setImportError (message) {
    if (!importConfigError) return
    if (!message) {
      importConfigError.classList.add('d-none')
      importConfigError.textContent = ''
      if (importPlexCredentials) importPlexCredentials.classList.add('d-none')
      if (importTmdbCredentials) importTmdbCredentials.classList.add('d-none')
      return
    }
    importConfigError.classList.remove('d-none')
    importConfigError.textContent = message
    if (importPlexCredentials) {
      const needsPlex = importNeedsPlexCredentials || /plex/i.test(message)
      importPlexCredentials.classList.toggle('d-none', !needsPlex)
    }
    if (importTmdbCredentials) {
      const needsTmdb = importNeedsTmdbCredentials || /tmdb/i.test(message)
      importTmdbCredentials.classList.toggle('d-none', !needsTmdb)
    }
  }

  function setImportCredentialFlags (options) {
    importNeedsPlexCredentials = Boolean(options && options.needsPlex)
    importNeedsTmdbCredentials = Boolean(options && options.needsTmdb)
  }

  function getImportMode () {
    if (importModeMerge && importModeMerge.checked) return 'merge'
    return 'new'
  }

  function getMergeBaseConfig () {
    if (!importMergeBaseConfig) return ''
    return importMergeBaseConfig.value.trim()
  }

  function clearMergeSections () {
    if (importMergeSectionList) importMergeSectionList.innerHTML = ''
    if (importMergeSection) importMergeSection.classList.add('d-none')
  }

  function toggleImportModeUI () {
    const isMerge = getImportMode() === 'merge'
    if (importMergeBaseSection) importMergeBaseSection.classList.toggle('d-none', !isMerge)
    if (!isMerge) clearMergeSections()
  }

  function titleCase (value) {
    return String(value || '')
      .split('_')
      .map(part => (part ? part[0].toUpperCase() + part.slice(1) : ''))
      .join(' ')
  }

  const mergeSectionLabels = {
    plex: 'Plex',
    tmdb: 'TMDb',
    omdb: 'OMDb',
    mdblist: 'MDBList',
    tautulli: 'Tautulli',
    notifiarr: 'Notifiarr',
    gotify: 'Gotify',
    ntfy: 'ntfy',
    github: 'GitHub',
    radarr: 'Radarr',
    sonarr: 'Sonarr',
    trakt: 'Trakt',
    mal: 'MyAnimeList',
    anidb: 'AniDB',
    webhooks: 'Webhooks',
    settings: 'Settings',
    playlist_files: 'Playlists',
    libraries: 'Libraries'
  }

  const mergeSectionOrder = [
    'plex',
    'tmdb',
    'libraries',
    'playlist_files',
    'tautulli',
    'github',
    'omdb',
    'mdblist',
    'notifiarr',
    'gotify',
    'ntfy',
    'webhooks',
    'anidb',
    'radarr',
    'sonarr',
    'trakt',
    'mal',
    'settings'
  ]

  const mergeDefaultSelected = new Set(['libraries', 'playlist_files', 'settings'])

  function renderMergeSections (sections) {
    if (!importMergeSection || !importMergeSectionList) return
    importMergeSectionList.innerHTML = ''
    if (getImportMode() !== 'merge') {
      importMergeSection.classList.add('d-none')
      return
    }
    const list = Array.isArray(sections) ? sections.filter(Boolean) : []
    if (!list.length) {
      importMergeSection.classList.add('d-none')
      return
    }
    const ordered = []
    const remaining = new Set(list)
    mergeSectionOrder.forEach(section => {
      if (remaining.has(section)) {
        ordered.push(section)
        remaining.delete(section)
      }
    })
    Array.from(remaining).sort().forEach(section => ordered.push(section))

    const shouldUseDefaults = ordered.some(section => mergeDefaultSelected.has(section))

    ordered.forEach((section, idx) => {
      const id = `import-merge-${idx}-${String(section).replace(/[^a-zA-Z0-9_-]/g, '_')}`
      const wrapper = document.createElement('div')
      wrapper.className = 'form-check form-check-inline'

      const input = document.createElement('input')
      input.type = 'checkbox'
      input.className = 'form-check-input import-merge-section'
      input.id = id
      input.value = section
      input.checked = shouldUseDefaults ? mergeDefaultSelected.has(section) : true
      input.addEventListener('change', updateImportConfirmState)

      const label = document.createElement('label')
      label.className = 'form-check-label small'
      label.setAttribute('for', id)
      label.textContent = mergeSectionLabels[section] || titleCase(section)

      wrapper.appendChild(input)
      wrapper.appendChild(label)
      importMergeSectionList.appendChild(wrapper)
    })
    importMergeSection.classList.remove('d-none')
  }

  function collectMergeSections () {
    if (!importMergeSectionList) return []
    return Array.from(importMergeSectionList.querySelectorAll('.import-merge-section:checked'))
      .map(input => input.value)
  }

  function setMergeSelection (checked) {
    if (!importMergeSectionList) return
    importMergeSectionList.querySelectorAll('.import-merge-section').forEach(input => {
      input.checked = checked
    })
    updateImportConfirmState()
  }

  if (importMergeSelectAll) {
    importMergeSelectAll.addEventListener('click', () => {
      setMergeSelection(true)
    })
  }
  if (importMergeSelectNone) {
    importMergeSelectNone.addEventListener('click', () => {
      setMergeSelection(false)
    })
  }

  function updateImportConfirmState () {
    if (!confirmImportButton) return
    if (confirmImportButton.classList.contains('d-none')) return
    const isMerge = getImportMode() === 'merge'
    if (isMerge && !getMergeBaseConfig()) {
      confirmImportButton.disabled = true
      setImportError('Select a base config to merge into.')
      return
    }
    if (importLibraryMappingSection && !importLibraryMappingSection.classList.contains('d-none')) {
      const selects = importLibraryMappingList
        ? Array.from(importLibraryMappingList.querySelectorAll('.import-library-map'))
        : []
      const missing = selects.some(select => !select.value)
      confirmImportButton.disabled = missing
      if (missing) {
        setImportError('Select a Plex library or Ignore for all listed libraries.')
      } else {
        setImportError('')
      }
      return
    }
    if (isMerge && !collectMergeSections().length) {
      confirmImportButton.disabled = true
      setImportError('Select at least one section to merge.')
      return
    }
    confirmImportButton.disabled = false
    setImportError('')
  }

  let mappingRefreshTimer = null

  function collectLibraryMapping () {
    const mapping = {}
    if (!importLibraryMappingList) return mapping
    importLibraryMappingList.querySelectorAll('.import-library-map').forEach(select => {
      if (select.dataset.libraryName && select.value) {
        mapping[select.dataset.libraryName] = select.value
      }
    })
    return mapping
  }

  async function refreshMappedPreview () {
    if (!importToken) return
    try {
      const res = await fetch('/import-config/preview-mapped', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: importToken, library_mapping: collectLibraryMapping() })
      })
      const data = await res.json()
      if (!res.ok || !data.success) {
        throw new Error(data.message || 'Preview refresh failed.')
      }
      if (importReport) {
        importReportHeader = buildImportHeader(data)
        importReportBody = data.annotated_report || (data.report_lines || []).join('\n')
        applyImportReportFilter()
      }
      if (importSummary) {
        importSummary.textContent = ''
        importSummary.classList.add('d-none')
      }
      if (downloadImportReport && data.report_url) {
        downloadImportReport.href = data.report_url
        downloadImportReport.download = `import_report_${importConfigName?.value || 'import'}.txt`
        downloadImportReport.classList.remove('d-none')
      }
      renderMergeSections(data.importable_sections)
    } catch (err) {
      setImportError(err.message || 'Preview refresh failed.')
    }
  }

  function scheduleMappedPreviewRefresh () {
    if (!importToken) return
    if (mappingRefreshTimer) clearTimeout(mappingRefreshTimer)
    mappingRefreshTimer = setTimeout(refreshMappedPreview, 300)
  }

  function renderLibraryMapping (items, plexLibraries) {
    if (!importLibraryMappingSection || !importLibraryMappingList) return
    importLibraryMappingList.innerHTML = ''
    const pending = Array.isArray(items) ? items : []
    if (!pending.length) {
      importLibraryMappingSection.classList.add('d-none')
      if (importMappingNote) importMappingNote.classList.add('d-none')
      return
    }
    if (importMappingNote) importMappingNote.classList.remove('d-none')

    const movieNames = Array.isArray(plexLibraries?.movie) ? plexLibraries.movie.map(name => String(name)) : []
    const showNames = Array.isArray(plexLibraries?.show) ? plexLibraries.show.map(name => String(name)) : []
    const plexNameMap = {}
    movieNames.concat(showNames).forEach(name => {
      plexNameMap[name.toLowerCase()] = name
    })

    function suggestPlexName (item) {
      const rawName = String(item?.name || '').trim()
      if (!rawName) return ''
      const match = plexNameMap[rawName.toLowerCase()]
      if (match) return match
      if (item?.inferred_type === 'movie' && movieNames.length === 1) return movieNames[0]
      if (item?.inferred_type === 'show' && showNames.length === 1) return showNames[0]
      return ''
    }

    pending.forEach((item, idx) => {
      const row = document.createElement('div')
      row.className = 'd-flex align-items-center justify-content-between flex-wrap gap-2 border rounded p-2 mb-2'

      const left = document.createElement('div')
      left.className = 'd-flex flex-column'
      const title = document.createElement('div')
      title.innerHTML = `<strong>${item.name}</strong>`
      const meta = document.createElement('div')
      meta.className = 'small text-muted'
      const confidence = item.confidence || 'unknown'
      const inferred = item.inferred_type || 'unknown'
      const scoreText = `movie ${item.movie_score || 0} / show ${item.show_score || 0}`
      const suggested = suggestPlexName(item)
      let metaText = `inferred: ${inferred} • confidence: ${confidence} (${scoreText})`
      if (suggested) metaText += ` • suggested: ${suggested}`
      meta.textContent = metaText
      left.appendChild(title)
      left.appendChild(meta)

      const select = document.createElement('select')
      select.className = 'form-select form-select-sm import-library-map'
      select.dataset.libraryName = item.name
      select.style.minWidth = '140px'

      const emptyOption = document.createElement('option')
      emptyOption.value = ''
      emptyOption.textContent = 'Select Plex library'
      select.appendChild(emptyOption)

      const ignoreOption = document.createElement('option')
      ignoreOption.value = '__ignore__'
      ignoreOption.textContent = 'Ignore this library'
      select.appendChild(ignoreOption)

      if (movieNames.length) {
        const group = document.createElement('optgroup')
        group.label = 'Movies'
        movieNames.forEach(name => {
          const option = document.createElement('option')
          option.value = name
          option.textContent = name
          group.appendChild(option)
        })
        select.appendChild(group)
      }

      if (showNames.length) {
        const group = document.createElement('optgroup')
        group.label = 'Shows'
        showNames.forEach(name => {
          const option = document.createElement('option')
          option.value = name
          option.textContent = name
          group.appendChild(option)
        })
        select.appendChild(group)
      }

      if (suggested) select.value = suggested

      select.addEventListener('change', () => {
        updateImportConfirmState()
        scheduleMappedPreviewRefresh()
      })

      row.appendChild(left)
      row.appendChild(select)
      importLibraryMappingList.appendChild(row)
    })

    importLibraryMappingSection.classList.remove('d-none')
    updateImportConfirmState()
    scheduleMappedPreviewRefresh()
  }

  function resetImportModal () {
    importToken = null
    importReportHeader = ''
    importReportBody = ''
    importReportFilter = 'all'
    setImportCredentialFlags({ needsPlex: false, needsTmdb: false })
    if (importConfigFile) importConfigFile.value = ''
    if (importConfigName) {
      importConfigName.value = ''
      removeValidationMessages(importConfigName)
    }
    if (importModeNew) importModeNew.checked = true
    if (importModeMerge) importModeMerge.checked = false
    if (importMergeBaseConfig) {
      const current = configSelector?.value && configSelector.value !== 'add_config'
        ? configSelector.value
        : ''
      if (current) {
        importMergeBaseConfig.value = current
      } else if (importMergeBaseConfig.options.length) {
        importMergeBaseConfig.selectedIndex = 0
      }
    }
    if (importMergeBaseSection) importMergeBaseSection.classList.add('d-none')
    clearMergeSections()
    if (importPlexCredentials) importPlexCredentials.classList.add('d-none')
    if (importPlexUrl) importPlexUrl.value = ''
    if (importPlexToken) importPlexToken.value = ''
    if (importTmdbCredentials) importTmdbCredentials.classList.add('d-none')
    if (importTmdbApiKey) importTmdbApiKey.value = ''
    if (importPreviewSection) importPreviewSection.classList.add('d-none')
    if (importReport) importReport.textContent = ''
    if (importSummary) {
      importSummary.textContent = ''
      importSummary.classList.add('d-none')
    }
    if (importReportFilters) {
      importReportFilters.querySelectorAll('button[data-filter]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === 'all')
      })
    }
    if (importSummary) importSummary.textContent = ''
    if (downloadImportReport) {
      downloadImportReport.classList.add('d-none')
      downloadImportReport.removeAttribute('href')
    }
    if (importLibraryMappingSection) importLibraryMappingSection.classList.add('d-none')
    if (importLibraryMappingList) importLibraryMappingList.innerHTML = ''
    if (importMappingNote) importMappingNote.classList.add('d-none')
    if (confirmImportButton) confirmImportButton.classList.add('d-none')
    if (previewImportButton) previewImportButton.disabled = false
    setImportError('')
  }

  function clearImportPreviewState (options = {}) {
    importToken = null
    importReportHeader = ''
    importReportBody = ''
    if (!options.keepCredentials) {
      setImportCredentialFlags({ needsPlex: false, needsTmdb: false })
    }
    if (importPreviewSection) importPreviewSection.classList.add('d-none')
    if (importReport) importReport.textContent = ''
    if (importSummary) {
      importSummary.textContent = ''
      importSummary.classList.add('d-none')
    }
    if (confirmImportButton) confirmImportButton.classList.add('d-none')
    if (importTmdbCredentials) importTmdbCredentials.classList.add('d-none')
    clearMergeSections()
    if (importReportFilters) {
      importReportFilters.querySelectorAll('button[data-filter]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === 'all')
      })
    }
  }

  function applyImportReportFilter () {
    if (!importReport) return
    if (!importReportBody && !importReportHeader) {
      importReport.textContent = ''
      return
    }
    const importedPattern = /(?:#|\|) imported(?:\s*-.*)?$/
    const notImportedPattern = /(?:#|\|) not imported(?:\s*-.*)?$/
    const lines = importReportBody.split('\n')
    const filtered = lines.filter(line => {
      const trimmed = line.trimEnd()
      if (importReportFilter === 'imported') {
        return importedPattern.test(trimmed)
      }
      if (importReportFilter === 'not_imported') {
        return notImportedPattern.test(trimmed)
      }
      if (importReportFilter === 'comments') {
        return line.trimStart().startsWith('#')
      }
      return true
    })
    const header = importReportHeader ? `${importReportHeader}\n` : ''
    importReport.textContent = header + filtered.join('\n')
  }

  if (importReportFilters) {
    importReportFilters.addEventListener('click', (event) => {
      const btn = event.target.closest('button[data-filter]')
      if (!btn) return
      importReportFilter = btn.dataset.filter || 'all'
      importReportFilters.querySelectorAll('button[data-filter]').forEach(node => {
        node.classList.toggle('active', node === btn)
      })
      applyImportReportFilter()
    })
  }

  function buildImportHeader (data) {
    const counts = data.line_counts || {}
    const summary = data.summary || {}
    const imported = typeof counts.imported_lines === 'number' ? counts.imported_lines : (summary.imported || 0)
    const notImported = typeof counts.not_imported_lines === 'number'
      ? counts.not_imported_lines
      : ((summary.unmapped || 0) + (summary.skipped || 0))
    const comments = typeof counts.comments === 'number' ? counts.comments : (data.comments_count || 0)
    const blank = typeof counts.blank === 'number' ? counts.blank : 0
    const total = typeof counts.total === 'number' ? counts.total : 0
    const diff = typeof counts.diff === 'number'
      ? counts.diff
      : (total - (imported + notImported + blank + comments))
    const name = data.config_name || importConfigName?.value || 'import'
    const header = [
      `# Import Report for ${name}`,
      `# Imported: ${imported}`,
      `# Not Imported: ${notImported}`,
      `# Comments: ${comments}`,
      `# Blank: ${blank}`,
      `# Total: ${total}`,
      `# Diff: ${diff}`,
      ''
    ]
    const mapping = data.mapping_summary || {}
    if (mapping && Object.keys(mapping).length) {
      const mapped = mapping.mapped || 0
      const ignored = mapping.ignored || 0
      const missing = mapping.missing || 0
      const invalid = mapping.invalid || 0
      const duplicate = mapping.duplicate || 0
      header.splice(
        header.length - 1,
        0,
        `# Mapping Applied: mapped ${mapped}, ignored ${ignored}, missing ${missing}, invalid ${invalid}, duplicate ${duplicate}`
      )
    }
    return header.join('\n')
  }

  if (importConfigModalEl) {
    importConfigModalEl.addEventListener('hidden.bs.modal', resetImportModal)
    importConfigModalEl.addEventListener('show.bs.modal', () => {
      if (!importConfigName) return
      removeValidationMessages(importConfigName)
      setImportError('')
      if (importModeNew) importModeNew.checked = true
      if (importModeMerge) importModeMerge.checked = false
      if (importMergeBaseConfig) {
        const current = configSelector?.value && configSelector.value !== 'add_config'
          ? configSelector.value
          : ''
        if (current) {
          importMergeBaseConfig.value = current
        }
      }
      toggleImportModeUI()
      let suggested = ''
      const selectorValue = configSelector?.value || ''
      if (selectorValue === 'add_config') {
        suggested = newConfigInput?.value || ''
      } else {
        suggested = selectorValue
      }
      suggested = sanitizeConfigName(suggested)
      importConfigName.value = suggested
      if (!suggested) return
      if (isDuplicateName(suggested)) {
        applyValidationStyles(importConfigName, 'error', 'Name already exists.')
        setImportError('Config name already exists. Choose a unique name or rename it first.')
      } else {
        applyValidationStyles(importConfigName, 'success', 'Name is available')
        setImportError('')
      }
    })
  }

  if (importConfigName) {
    importConfigName.addEventListener('input', () => {
      importConfigName.value = sanitizeConfigName(importConfigName.value)
      removeValidationMessages(importConfigName)
      if (isDuplicateName(importConfigName.value)) {
        applyValidationStyles(importConfigName, 'error', 'Name already exists.')
        setImportError('Config name already exists. Choose a unique name or rename it first.')
      } else if (importConfigName.value) {
        applyValidationStyles(importConfigName, 'success', 'Name is available')
        setImportError('')
      }
    })
  }

  function handleImportMergeSettingsChange () {
    toggleImportModeUI()
    clearImportPreviewState({ keepCredentials: true })
    if (previewImportButton) previewImportButton.textContent = 'Preview Import'
    updateImportConfirmState()
  }

  if (importModeNew) {
    importModeNew.addEventListener('change', handleImportMergeSettingsChange)
  }
  if (importModeMerge) {
    importModeMerge.addEventListener('change', handleImportMergeSettingsChange)
  }
  if (importMergeBaseConfig) {
    importMergeBaseConfig.addEventListener('change', handleImportMergeSettingsChange)
  }

  if (previewImportButton) {
    previewImportButton.addEventListener('click', async () => {
      setImportError('')
      if (importToken && importPreviewSection && !importPreviewSection.classList.contains('d-none')) {
        previewImportButton.disabled = true
        previewImportButton.textContent = 'Refreshing Preview...'
        try {
          await refreshMappedPreview()
        } finally {
          previewImportButton.disabled = false
          previewImportButton.textContent = 'Refresh Preview'
        }
        return
      }
      if (downloadImportReport) {
        downloadImportReport.classList.add('d-none')
        downloadImportReport.removeAttribute('href')
      }
      if (!importConfigFile || !importConfigFile.files || !importConfigFile.files[0]) {
        setImportError('Select a .yml, .yaml, or .zip file to import.')
        return
      }
      if (!importConfigName || !importConfigName.value) {
        setImportError('Enter a unique config name.')
        return
      }
      if (isDuplicateName(importConfigName.value)) {
        setImportError('That config name already exists.')
        return
      }
      if (getImportMode() === 'merge' && !getMergeBaseConfig()) {
        setImportError('Select a base config to merge into.')
        return
      }

      previewImportButton.disabled = true
      previewImportButton.textContent = 'Previewing...'

      try {
        const formData = new FormData()
        formData.append('file', importConfigFile.files[0])
        formData.append('config_name', importConfigName.value)
        if (getImportMode() === 'merge') {
          formData.append('merge_mode', 'merge')
          const baseConfig = getMergeBaseConfig()
          if (baseConfig) formData.append('base_config', baseConfig)
        }
        if (importPlexUrl && importPlexUrl.value.trim()) {
          formData.append('plex_url', importPlexUrl.value.trim())
        }
        if (importPlexToken && importPlexToken.value.trim()) {
          formData.append('plex_token', importPlexToken.value.trim())
        }
        if (importTmdbApiKey && importTmdbApiKey.value.trim()) {
          formData.append('tmdb_apikey', importTmdbApiKey.value.trim())
        }
        const res = await fetch('/import-config/preview', {
          method: 'POST',
          body: formData
        })
        const data = await res.json()
        if (!res.ok || !data.success) {
          setImportCredentialFlags({
            needsPlex: Boolean(data && data.needs_plex_credentials),
            needsTmdb: Boolean(data && data.needs_tmdb_credentials)
          })
          if (data && data.needs_plex_credentials && importPlexCredentials) {
            importPlexCredentials.classList.remove('d-none')
            if (importPlexUrl && data.plex_url && !importPlexUrl.value.trim()) {
              importPlexUrl.value = data.plex_url
            }
            if (importPlexToken && data.plex_token && !importPlexToken.value.trim()) {
              importPlexToken.value = data.plex_token
            }
          }
          if (data && data.needs_tmdb_credentials && importTmdbCredentials) {
            importTmdbCredentials.classList.remove('d-none')
            if (importTmdbApiKey && data.tmdb_apikey && !importTmdbApiKey.value.trim()) {
              importTmdbApiKey.value = data.tmdb_apikey
            }
          }
          clearImportPreviewState({ keepCredentials: true })
          setImportError(data.message || 'Preview failed.')
          return
        }
        setImportCredentialFlags({ needsPlex: false, needsTmdb: false })
        if (importPlexCredentials) importPlexCredentials.classList.add('d-none')
        if (importTmdbCredentials) importTmdbCredentials.classList.add('d-none')
        importToken = data.token
        if (importPreviewSection) importPreviewSection.classList.remove('d-none')
        if (importReport) {
          importReportHeader = buildImportHeader(data)
          importReportBody = data.annotated_report || (data.report_lines || []).join('\n')
          applyImportReportFilter()
        }
        if (importSummary) {
          importSummary.textContent = ''
          importSummary.classList.add('d-none')
        }
        if (downloadImportReport && data.report_url) {
          downloadImportReport.href = data.report_url
          downloadImportReport.download = `import_report_${importConfigName.value}.txt`
          downloadImportReport.classList.remove('d-none')
        }
        renderMergeSections(data.importable_sections)
        renderLibraryMapping(data.library_mapping || [], data.plex_libraries || {})
        if (confirmImportButton) confirmImportButton.classList.remove('d-none')
        updateImportConfirmState()
      } catch (err) {
        setImportError(err.message || 'Preview failed.')
      } finally {
        previewImportButton.disabled = false
        previewImportButton.textContent = (importToken ? 'Refresh Preview' : 'Preview Import')
      }
    })
  }

  if (confirmImportButton) {
    confirmImportButton.addEventListener('click', async () => {
      if (!importToken) {
        setImportError('Preview the import before confirming.')
        return
      }
      confirmImportButton.disabled = true
      confirmImportButton.textContent = 'Importing...'

      function showImportRedirectOverlay (message, detail) {
        const existing = document.getElementById('qs-import-redirect')
        if (existing) {
          const msgEl = existing.querySelector('.qs-import-redirect-message')
          const detailEl = existing.querySelector('.qs-import-redirect-detail')
          if (msgEl) msgEl.textContent = message || msgEl.textContent
          if (detailEl) detailEl.textContent = detail || detailEl.textContent
          return
        }

        const overlay = document.createElement('div')
        overlay.id = 'qs-import-redirect'
        overlay.setAttribute('role', 'dialog')
        overlay.setAttribute('aria-modal', 'true')
        overlay.style.cssText = [
          'position:fixed',
          'inset:0',
          'z-index:2000',
          'background:rgba(8, 10, 12, 0.78)',
          'display:flex',
          'align-items:center',
          'justify-content:center',
          'padding:24px'
        ].join(';')

        overlay.innerHTML = `
          <div class="text-center text-light p-4 rounded" style="background:#0f1113;border:1px solid #2b2f33;max-width:520px;width:100%;">
            <div class="spinner-border text-info mb-3" role="status" aria-hidden="true"></div>
            <div class="fw-semibold mb-1 qs-import-redirect-message">${message || 'Import complete. Redirecting...'}</div>
            <div class="small text-muted mb-3 qs-import-redirect-detail" style="white-space: pre-line;">${detail || 'Loading Final Validation. This can take up to 30 seconds.'}</div>
            <button type="button" class="btn btn-sm btn-outline-info qs-import-redirect-btn d-none">Go to Final Validation</button>
          </div>
        `

        document.body.appendChild(overlay)
        const redirectBtn = overlay.querySelector('.qs-import-redirect-btn')
        if (redirectBtn) {
          redirectBtn.addEventListener('click', () => {
            window.location = '/step/900-final'
          })
          setTimeout(() => {
            if (document.getElementById('qs-import-redirect')) {
              redirectBtn.classList.remove('d-none')
            }
          }, 60000)
        }
      }
      try {
        const libraryMapping = {}
        if (importLibraryMappingList) {
          importLibraryMappingList.querySelectorAll('.import-library-map').forEach(select => {
            if (select.dataset.libraryName && select.value) {
              libraryMapping[select.dataset.libraryName] = select.value
            }
          })
        }
        const isMerge = getImportMode() === 'merge'
        const mergePayload = {
          merge_mode: isMerge,
          base_config: isMerge ? getMergeBaseConfig() : '',
          merge_sections: isMerge ? collectMergeSections() : []
        }
        const res = await fetch('/import-config/confirm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            token: importToken,
            library_mapping: libraryMapping,
            ...mergePayload
          })
        })
        const data = await res.json()
        if (!res.ok || !data.success) {
          throw new Error(data.message || 'Import failed.')
        }
        let msg = `Imported config '${data.config_name}'.`
        if (Array.isArray(data.fonts_copied) && data.fonts_copied.length) {
          msg += ` Fonts added: ${data.fonts_copied.length}.`
        }
        const skippedExisting = Array.isArray(data.fonts_skipped_existing) ? data.fonts_skipped_existing : []
        const skippedFailed = Array.isArray(data.fonts_skipped_failed) ? data.fonts_skipped_failed : []
        if (skippedExisting.length) {
          msg += ` Fonts skipped (already exists): ${skippedExisting.length}.`
        }
        if (skippedFailed.length) {
          msg += ` Fonts skipped (copy failed): ${skippedFailed.length}.`
        }
        if (!skippedExisting.length && !skippedFailed.length && Array.isArray(data.fonts_skipped) && data.fonts_skipped.length) {
          msg += ` Fonts skipped: ${data.fonts_skipped.length}.`
        }
        const guidance = 'Import complete. Go to Final Validation and click Validate Configured Services to check all services, then fix any failures (especially interactive pages).'
        showImportRedirectOverlay(msg, `${guidance}\nLoading Final Validation. This can take up to 30 seconds.`)
        const modal = bootstrap.Modal.getInstance(importConfigModalEl)
        if (modal) modal.hide()
        setTimeout(() => { window.location = '/step/900-final' }, 1200)
      } catch (err) {
        const message = err.message || 'Import failed.'
        if (/import token is invalid/i.test(message)) {
          clearImportPreviewState()
          setImportError('Import preview expired. Please run Preview Import again.')
        } else {
          setImportError(message)
        }
      } finally {
        confirmImportButton.disabled = false
        confirmImportButton.textContent = 'Import'
      }
    })
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
  const tempPathInput = document.getElementById('test-lib-temp-path')
  const finalPathInput = document.getElementById('test-lib-final-path')
  const savePathsBtn = document.getElementById('test-lib-paths-apply')
  const pathsStatus = document.getElementById('test-lib-paths-status')
  const testLibAccordion = document.getElementById('test-lib-accordion-collapse')

  function setTestLibAccordionExpanded (shouldExpand) {
    if (!testLibAccordion) return
    if (typeof bootstrap !== 'undefined' && bootstrap.Collapse) {
      const instance = bootstrap.Collapse.getOrCreateInstance(testLibAccordion, { toggle: false })
      if (shouldExpand) instance.show()
      else instance.hide()
    } else {
      testLibAccordion.classList.toggle('show', Boolean(shouldExpand))
    }
  }

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
  function startElapsedTimer (resumeAt) {
    startedAt = Number.isFinite(resumeAt) ? resumeAt : Date.now()
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

  function storeJob (jobId, startedAt) {
    try {
      localStorage.setItem(jobStorageKey, jobId)
      const ts = Number.isFinite(startedAt) ? startedAt : Date.now()
      localStorage.setItem(jobStartedKey, String(ts))
    } catch (e) {
      // ignore storage errors
    }
  }

  function getStoredJob () {
    try {
      return {
        jobId: localStorage.getItem(jobStorageKey),
        startedAt: Number(localStorage.getItem(jobStartedKey))
      }
    } catch (e) {
      return { jobId: null, startedAt: NaN }
    }
  }

  function clearStoredJob () {
    try {
      localStorage.removeItem(jobStorageKey)
      localStorage.removeItem(jobStartedKey)
    } catch (e) {
      // ignore storage errors
    }
  }

  // ---------------------------------------------------------------

  const isManagedInstall = true
  const jobStorageKey = 'qs_test_lib_job_id'
  const jobStartedKey = 'qs_test_lib_job_started_at'

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
      progBar.style.width = '40%'
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

  function setScenarioNotFound (pathHtml, opts = {}) {
    const unrecognizedNote = opts.unrecognized
      ? '<div class="small text-danger mt-1">Target path exists but does not look like test libraries.</div>'
      : ''
    testLibStatus.classList.remove('d-none', 'alert-success', 'alert-danger')
    testLibStatus.classList.add('alert-warning')
    statusMsg.innerHTML = `
      <strong>Test media libraries not found.</strong>
      <span class="ms-1">We recommend setting them up for testing with Kometa. Be patient as the repository is about 7GB.</span>
      ${pathHtml || ''}
      ${unrecognizedNote}
    `
    cloneBtn.classList.remove('d-none')
    purgeBtn.classList.add('d-none')
    updateRow?.classList.add('d-none')
    setTestLibAccordionExpanded(true)
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
    setTestLibAccordionExpanded(false)
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
    if (!data.found) setScenarioNotFound(pathHtml, { unrecognized: data.unrecognized })
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

    function setPathsStatus (text, isError = false) {
      if (!pathsStatus) return
      pathsStatus.textContent = text || ''
      pathsStatus.classList.remove('text-danger', 'text-success', 'text-muted')
      if (!text) {
        pathsStatus.classList.add('text-muted')
        return
      }
      pathsStatus.classList.add(isError ? 'text-danger' : 'text-success')
    }

    async function saveTestLibPaths (confirmOverride = false) {
      if (!savePathsBtn) return
      savePathsBtn.disabled = true
      savePathsBtn.textContent = 'Saving...'
      setPathsStatus('Validating paths...')

      if (typeof PathValidation !== 'undefined' && PathValidation.validateAll) {
        const validPaths = PathValidation.validateAll(document)
        if (!validPaths) {
          savePathsBtn.disabled = false
          savePathsBtn.textContent = 'Save Paths'
          setPathsStatus('Please fix invalid paths.', true)
          showToast('error', 'Please fix invalid path fields before saving.')
          return
        }
      }

      const payload = {
        quickstart_root: window.pageInfo.quickstart_root,
        temp_path: tempPathInput ? tempPathInput.value.trim() : '',
        final_path: finalPathInput ? finalPathInput.value.trim() : '',
        confirm: confirmOverride
      }

      try {
        const res = await fetch('/test-libraries-settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
        const data = await res.json()

        if (!res.ok && data && data.needs_confirm) {
          savePathsBtn.disabled = false
          savePathsBtn.textContent = 'Save Paths'
          setPathsStatus('')
          const msg = data.message || 'Paths need confirmation.'
          if (window.confirm(`${msg}\n\nContinue anyway?`)) {
            await saveTestLibPaths(true)
          }
          return
        }

        if (!res.ok || !data.success) {
          throw new Error(data.message || 'Failed to save paths.')
        }

        if (data.temp_path && tempPathInput) tempPathInput.value = data.temp_path
        if (data.final_path && finalPathInput) finalPathInput.value = data.final_path
        setPathsStatus('Saved.')
        showToast('success', data.message || 'Test library paths saved.')
        await refreshStatus()
      } catch (err) {
        setPathsStatus('Failed to save.', true)
        showToast('error', err.message || 'Failed to save paths.')
      } finally {
        savePathsBtn.disabled = false
        savePathsBtn.textContent = 'Save Paths'
      }
    }

    if (savePathsBtn) {
      savePathsBtn.addEventListener('click', (e) => {
        e.preventDefault()
        saveTestLibPaths().catch(() => {})
      })
    }

    // DOWNLOAD / UPDATE flow (start + poll)
    let running = false

    function setPhase (msg) {
      baseBtnMsg = msg // keep only the word; the timer appends (mm:ss)
      const s = Math.floor((Date.now() - startedAt) / 1000)
      const m = String(Math.floor(s / 60)).padStart(2, '0')
      const ss = String(s % 60).padStart(2, '0')
      updateButtonLabel(`${baseBtnMsg}  (${m}:${ss})`)
    }

    async function pollJob (jobId) {
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
            const isEstimated = prog.estimated === true
            let pct = Number.isFinite(prog.pct) ? prog.pct : null
            if (pct === null && hasTotal && Number.isFinite(prog.downloaded)) {
              pct = Math.max(0, Math.min(100, Math.floor((prog.downloaded || 0) * 100 / prog.total)))
            }
            const estimateTooSmall = isEstimated && Number.isFinite(prog.downloaded) && prog.total > 0 && prog.downloaded > prog.total
            const now = Date.now()
            const dt = Math.max(1, now - lastTs) / 1000
            const deltaBytes = (prog.downloaded || 0) - lastDownloaded
            const speedStr = deltaBytes > 0 ? `${bytes(deltaBytes / dt)}/s` : ''
            lastDownloaded = prog.downloaded || 0
            lastTs = now

            setPhase('Downloading…')

            if (pct === null || estimateTooSmall) {
              const speedNote = speedStr ? `• ${speedStr}` : ''
              const sizeNote = estimateTooSmall ? '• estimate too small' : '• size unknown'
              setProgress(40, `Downloading… ${bytes(prog.downloaded || 0)} ${speedNote} ${sizeNote}`, { indeterminate: true })
            } else {
              const totalStr = hasTotal ? ` / ${bytes(prog.total)}` : ''
              const estimateLabel = ''
              setProgress(pct, `Downloading… ${bytes(prog.downloaded || 0)}${totalStr} (${pct}%) ${speedStr ? `• ${speedStr}` : ''}${estimateLabel}`)
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
        clearStoredJob()
        stopElapsedTimer()
        setButtonIdle('Download Again')
        if (updateBtn) updateBtn.disabled = false
      }
    }

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
        const startedAt = Number(startRes.started_at)
        storeJob(jobId, Number.isFinite(startedAt) ? startedAt * 1000 : undefined)
      } catch (err) {
        running = false
        stopElapsedTimer()
        setButtonIdle('Download Again')
        if (updateBtn) updateBtn.disabled = false
        showToast('error', `Failed to start: ${err.message}`)
        return
      }

      await pollJob(jobId)
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

    // Resume any in-flight job after refresh/navigation
    function resumeJob (jobId, startedAtMs) {
      running = true
      baseBtnMsg = 'Resuming…'
      setButtonBusy(`${baseBtnMsg} (00:00)`)
      if (updateBtn) updateBtn.disabled = true
      resetProgress()
      setProgress(40, 'Resuming download…', { indeterminate: true })
      startElapsedTimer(Number.isFinite(startedAtMs) ? startedAtMs : undefined)

      fetch(`/clone-test-libraries-progress?job_id=${encodeURIComponent(jobId)}`)
        .then(r => r.json())
        .then(data => {
          if (!data.success) throw new Error(data.message || 'Unknown job')
          return pollJob(jobId)
        })
        .catch(() => {
          running = false
          clearStoredJob()
          stopElapsedTimer()
          setButtonIdle('Download Test Libraries')
          if (updateBtn) updateBtn.disabled = false
          resetProgress()
        })
    }

    const stored = getStoredJob()
    if (stored.jobId && !running) {
      resumeJob(stored.jobId, stored.startedAt)
    } else {
      fetch('/clone-test-libraries-active')
        .then(r => r.json())
        .then(data => {
          if (!data.success || !data.active || !data.job_id || running) return
          const startedAtSec = Number(data.started_at)
          const startedAtMs = Number.isFinite(startedAtSec) ? startedAtSec * 1000 : undefined
          storeJob(data.job_id, startedAtMs)
          resumeJob(data.job_id, startedAtMs)
        })
        .catch(() => {})
    }
  }
})
