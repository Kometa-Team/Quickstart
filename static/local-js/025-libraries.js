/* global EventHandler, ValidationHandler, OverlayHandler, Sortable, showToast, setupParentChildToggleSync, bootstrap, FontFace, PathValidation, DOMParser, MutationObserver, jumpTo, showNavigationLoadingOverlay, hideNavigationLoadingOverlay */

document.addEventListener('DOMContentLoaded', function () {
  console.log('[DEBUG] Initializing Libraries...')

  const scriptsToLoad = [
    '/static/local-js/imageHandler.js',
    '/static/local-js/overlayHandler.js',
    '/static/local-js/validationHandler.js',
    '/static/local-js/eventHandler.js'
  ]

  function loadScriptsSequentially (scripts, callback) {
    let index = 0

    function loadNext () {
      if (index >= scripts.length) {
        console.log('[DEBUG] All scripts loaded.')
        if (callback) callback()
        return
      }

      const script = document.createElement('script')
      script.src = scripts[index]
      script.type = 'text/javascript'
      script.onload = function () {
        console.log(`[DEBUG] Loaded script: ${scripts[index]}`)
        index++
        loadNext()
      }
      script.onerror = function () {
        console.error(`[ERROR] Failed to load script: ${scripts[index]}`)
      }

      document.head.appendChild(script)
    }

    loadNext()
  }

  loadScriptsSequentially(scriptsToLoad, function () {
    console.log('[DEBUG] All dependencies loaded. Running Library Initialization...')
    if (typeof PathValidation !== 'undefined' && PathValidation.init) {
      PathValidation.init()
    }

    const libraryPicker = document.getElementById('libraryPicker')
    const libraryContainer = document.getElementById('library-form-container')
    const libraryCache = document.getElementById('library-cache')
    const configuredCountsDisplay = document.getElementById('configuredCountsDisplay')
    const libraryLoading = document.getElementById('libraryLoading')
    const copyModalEl = document.getElementById('copyLibraryModal')
    const copyTargetsContainer = document.getElementById('copyLibraryTargets')
    const copySubtitle = document.getElementById('copyLibrarySubtitle')
    const copyWarning = document.getElementById('copyLibraryWarning')
    const copyConfirmBtn = document.getElementById('copyLibraryConfirm')
    const copySelectAllBtn = document.getElementById('copySelectAll')
    const copyDeselectAllBtn = document.getElementById('copyDeselectAll')
    const copyModal = copyModalEl ? new bootstrap.Modal(copyModalEl) : null
    let activeLibraryId = null
    let loadRequestId = 0
    let allowNextStepNavigation = false
    const dependencyHintConfigs = {
      tautulli: {
        stepKey: '030-tautulli',
        endpoint: '/libraries_tautulli_dependency_hint',
        windowKey: 'QS_TAUTULLI_REQUIREMENT_REASONS'
      },
      omdb: {
        stepKey: '050-omdb',
        endpoint: '/libraries_omdb_dependency_hint',
        windowKey: 'QS_OMDB_REQUIREMENT_REASONS'
      },
      mdblist: {
        stepKey: '060-mdblist',
        endpoint: '/libraries_mdblist_dependency_hint',
        windowKey: 'QS_MDBLIST_REQUIREMENT_REASONS'
      },
      anidb: {
        stepKey: '100-anidb',
        endpoint: '/libraries_anidb_dependency_hint',
        windowKey: 'QS_ANIDB_REQUIREMENT_REASONS'
      },
      radarr: {
        stepKey: '110-radarr',
        endpoint: '/libraries_radarr_dependency_hint',
        windowKey: 'QS_RADARR_REQUIREMENT_REASONS'
      },
      sonarr: {
        stepKey: '120-sonarr',
        endpoint: '/libraries_sonarr_dependency_hint',
        windowKey: 'QS_SONARR_REQUIREMENT_REASONS'
      },
      trakt: {
        stepKey: '130-trakt',
        endpoint: '/libraries_trakt_dependency_hint',
        windowKey: 'QS_TRAKT_REQUIREMENT_REASONS'
      },
      mal: {
        stepKey: '140-mal',
        endpoint: '/libraries_mal_dependency_hint',
        windowKey: 'QS_MAL_REQUIREMENT_REASONS'
      }
    }
    let dependencyHintRefreshTimer = null
    let dependencyHintRequestToken = 0
    const advancedVisibilityStorageKey = 'qsLibrariesAdvancedVisible'

    function normalizeMetadataFileEntry (entry) {
      if (!entry || typeof entry !== 'object') return null
      const type = String(entry.type || '').trim().toLowerCase()
      const location = String(entry.location || '').trim()
      const validated = entry.validated === true || String(entry.validated || '').trim().toLowerCase() === 'true'
      if (!type && !location) return null
      const normalized = { type, location }
      if (validated) normalized.validated = true
      return normalized
    }

    function parseMetadataFilesValue (rawValue) {
      if (!rawValue) return []
      try {
        const parsed = JSON.parse(String(rawValue))
        if (!Array.isArray(parsed)) return []
        return parsed
          .map(normalizeMetadataFileEntry)
          .filter(Boolean)
      } catch (_error) {
        return []
      }
    }

    const metadataCustomRepoRaw = String(window.QS_SETTINGS_CUSTOM_REPO || '').trim()
    const metadataCustomRepoBase = String(window.QS_SETTINGS_CUSTOM_REPO_BASE || '').trim()
    const metadataRepoDependencyMessage = 'Metadata file repo entries require Custom Repo to be configured and saved first within the Settings page.'
    const collectionRepoDependencyMessage = 'Collection file repo entries require Custom Repo to be configured and saved first within the Settings page.'
    const overlayRepoDependencyMessage = 'Overlay file repo entries require Custom Repo to be configured and saved first within the Settings page.'

    function appendMetadataSettingsLink (target, className = 'link-light fw-semibold text-decoration-underline') {
      const link = document.createElement('a')
      link.href = '/step/150-settings#custom_repo'
      link.textContent = 'Settings'
      link.className = className
      target.appendChild(link)
      return link
    }

    function appendInlineCodeText (target, text, options = {}) {
      const value = String(text || '')
      const wrapPlainInCode = Boolean(options.wrapPlainInCode)
      const parts = value.split(/(`[^`]+`)/g)
      const hasInlineCode = parts.some(part => part.startsWith('`') && part.endsWith('`'))

      if (!hasInlineCode && wrapPlainInCode) {
        const code = document.createElement('code')
        code.textContent = value
        target.appendChild(code)
        return
      }

      parts.forEach(part => {
        if (!part) return
        if (part.startsWith('`') && part.endsWith('`')) {
          const code = document.createElement('code')
          code.textContent = part.slice(1, -1)
          target.appendChild(code)
        } else {
          target.appendChild(document.createTextNode(part))
        }
      })
    }

    function getActiveConfigName () {
      const selected = String(document.querySelector('[name="configSelector"]')?.value || '').trim()
      if (selected && selected !== 'add_config') return selected
      return String(document.querySelector('[name="newConfigName"]')?.value || '').trim()
    }

    function applyNormalizedLibraryFileLocation (row, selector, payload, editor, syncFn) {
      const normalizedLocation = String(payload?.normalized_location || '').trim()
      if (!row || !normalizedLocation) return
      const input = row.querySelector(selector)
      if (!input) return
      input.value = normalizedLocation
      if (typeof syncFn === 'function') {
        syncFn(editor, false)
      }
    }

    function buildMetadataFileRow (entry = {}) {
      const wrapper = document.createElement('div')
      wrapper.className = 'card bg-body-tertiary border-secondary'
      wrapper.setAttribute('data-metadata-file-row', 'true')
      wrapper.innerHTML = `
        <div class="card-body">
          <div class="row g-3 align-items-end">
            <div class="col-md-2">
              <label class="form-label small text-muted">Type</label>
              <select class="form-select form-select-sm" data-metadata-file-type>
                <option value="file">file</option>
                <option value="folder">folder</option>
                <option value="git">git</option>
                <option value="repo">repo</option>
                <option value="url">url</option>
              </select>
            </div>
            <div class="col-md-7">
              <label class="form-label small text-muted">Location</label>
              <input type="text" class="form-control form-control-sm" data-metadata-file-location placeholder="config/metadata.yml, config/metadata/, user/file.yml, or https://example.com/metadata.yml">
            </div>
            <div class="col-md-3 d-flex gap-2 justify-content-md-end">
              <button type="button" class="btn btn-success btn-sm" data-validate-metadata-file>Validate</button>
              <button type="button" class="btn btn-danger btn-sm" data-remove-metadata-file>Remove</button>
            </div>
          </div>
          <div class="mt-2 small d-none" data-metadata-file-status></div>
        </div>
      `
      const typeSelect = wrapper.querySelector('[data-metadata-file-type]')
      const locationInput = wrapper.querySelector('[data-metadata-file-location]')
      if (typeSelect && ['file', 'folder', 'git', 'repo', 'url'].includes(entry.type)) {
        typeSelect.value = entry.type
      }
      if (locationInput && entry.location) {
        locationInput.value = entry.location
      }
      if (entry.validated) {
        wrapper.dataset.metadataFileState = 'success'
        wrapper.dataset.metadataFileButtonState = 'success'
      }
      updateMetadataFileValidateButton(wrapper, Boolean(entry.validated))
      return wrapper
    }

    function updateMetadataFileValidateButton (row, isValidated) {
      if (!row) return
      const button = row.querySelector('[data-validate-metadata-file]')
      if (!button) return
      const state = String(row.dataset.metadataFileButtonState || '').trim() || (isValidated ? 'success' : 'idle')
      button.classList.remove('btn-success', 'btn-secondary')
      if (state === 'success') {
        button.disabled = true
        button.classList.add('btn-secondary')
        button.textContent = 'Validated'
        return
      }
      if (state === 'blocked') {
        button.disabled = true
        button.classList.add('btn-secondary')
        button.textContent = 'Needs Repo'
        return
      }
      if (state === 'loading') {
        button.disabled = true
        button.classList.add('btn-secondary')
        button.textContent = 'Validating...'
        return
      }
      button.disabled = false
      button.classList.add('btn-success')
      button.textContent = 'Validate'
    }

    function setMetadataFileButtonState (row, state) {
      if (!row) return
      row.dataset.metadataFileButtonState = state || 'idle'
      updateMetadataFileValidateButton(row, state === 'success')
    }

    function updateMetadataCustomRepoStatus (editor) {
      if (!editor) return
      const target = editor.querySelector('[data-metadata-custom-repo-status]')
      if (!target) return

      target.replaceChildren()
      target.className = 'alert small mb-3'
      if (!metadataCustomRepoBase) {
        target.classList.add('alert-warning')
        target.append('Custom Repo is not configured. ')
        target.append('Use ')
        appendMetadataSettingsLink(target, 'alert-link fw-semibold')
        target.append(' to configure and save it before using ')
        const code = document.createElement('code')
        code.textContent = 'repo'
        target.appendChild(code)
        target.append(' metadata files.')
        return
      }

      target.classList.add('alert-secondary')
      const label = document.createElement('div')
      label.className = 'fw-semibold mb-1'
      label.textContent = 'Custom Repo base used for repo entries'
      target.appendChild(label)

      const baseValue = document.createElement('code')
      baseValue.textContent = metadataCustomRepoBase
      target.appendChild(baseValue)

      if (metadataCustomRepoRaw && metadataCustomRepoRaw !== metadataCustomRepoBase) {
        const savedValue = document.createElement('div')
        savedValue.className = 'mt-2'
        savedValue.append('Saved Custom Repo value: ')
        const savedCode = document.createElement('code')
        savedCode.textContent = metadataCustomRepoRaw
        savedValue.appendChild(savedCode)
        target.appendChild(savedValue)
      }

      const hint = document.createElement('div')
      hint.className = 'mt-2'
      hint.append('Change it in ')
      appendMetadataSettingsLink(hint, 'alert-link fw-semibold')
      hint.append('.')
      target.appendChild(hint)
    }

    function applyMetadataFileDependencyState (row, opts = {}) {
      if (!row) return false
      const skipStatus = Boolean(opts.skipStatus)
      const type = row.querySelector('[data-metadata-file-type]')?.value || ''
      if (type !== 'repo') {
        if (row.dataset.metadataFileDependency === 'repo-missing') {
          row.dataset.metadataFileDependency = ''
        }
        return false
      }

      if (metadataCustomRepoBase) {
        if (row.dataset.metadataFileDependency === 'repo-missing') {
          row.dataset.metadataFileDependency = ''
        }
        return false
      }

      row.dataset.metadataFileDependency = 'repo-missing'
      setMetadataFileButtonState(row, 'blocked')
      if (!skipStatus) {
        setMetadataFileStatus(row, 'error', metadataRepoDependencyMessage)
      }
      return true
    }

    function renderMetadataFileStatusMessage (target, message) {
      target.replaceChildren()
      if (!message) return

      if (typeof message === 'object' && message !== null) {
        const text = String(message.text || message.message || '').trim()
        const files = Array.isArray(message.files) ? message.files.filter(Boolean) : []
        if (text) {
          const summary = document.createElement('div')
          appendInlineCodeText(summary, text)
          target.appendChild(summary)
        }
        if (files.length) {
          if (files.length <= 5) {
            const list = document.createElement('ul')
            list.className = 'mb-0 mt-1 ps-3'
            files.forEach(file => {
              const item = document.createElement('li')
              appendInlineCodeText(item, file, { wrapPlainInCode: true })
              list.appendChild(item)
            })
            target.appendChild(list)
          } else {
            const details = document.createElement('details')
            details.className = 'mt-1'
            const summary = document.createElement('summary')
            summary.className = 'cursor-pointer'
            summary.textContent = 'Show files'
            details.appendChild(summary)
            const list = document.createElement('ul')
            list.className = 'mb-0 mt-1 ps-3'
            files.forEach(file => {
              const item = document.createElement('li')
              appendInlineCodeText(item, file, { wrapPlainInCode: true })
              list.appendChild(item)
            })
            details.appendChild(list)
            target.appendChild(details)
          }
        }
        return
      }

      const text = String(message || '').trim()
      if (!text) return

      if (text === metadataRepoDependencyMessage) {
        target.append('Metadata file repo entries require Custom Repo to be configured and saved first within the ')
        appendMetadataSettingsLink(target)
        target.append(' page.')
        return
      }

      appendInlineCodeText(target, text)
    }

    function setMetadataFileStatus (row, kind, message) {
      if (!row) return
      const target = row.querySelector('[data-metadata-file-status]')
      if (!target) return
      row.dataset.metadataFileState = kind || ''
      target.className = 'mt-2 small'
      if (!message) {
        target.classList.add('d-none')
        target.textContent = ''
        if (applyMetadataFileDependencyState(row, { skipStatus: true })) {
          setMetadataFileButtonState(row, 'blocked')
        } else {
          setMetadataFileButtonState(row, 'idle')
        }
        const editor = row.closest('[data-metadata-files-editor]')
        if (editor) updateMetadataFilesAccordionState(editor)
        return
      }
      target.classList.remove('d-none')
      if (kind === 'success') {
        target.classList.add('text-success')
      } else if (kind === 'error') {
        target.classList.add('text-danger')
      } else {
        target.classList.add('text-warning')
      }
      renderMetadataFileStatusMessage(target, message)
      if (kind === 'success') {
        setMetadataFileButtonState(row, 'success')
      } else if (row.dataset.metadataFileDependency === 'repo-missing') {
        setMetadataFileButtonState(row, 'blocked')
      } else {
        setMetadataFileButtonState(row, 'idle')
      }
      const editor = row.closest('[data-metadata-files-editor]')
      if (editor) updateMetadataFilesAccordionState(editor)
    }

    function updateMetadataFilesAccordionState (editor) {
      if (!editor) return
      const accordionItem = editor.closest('.accordion-item')
      const accordionHeader = accordionItem?.querySelector(':scope > .accordion-header')
      if (!accordionHeader) return

      const rows = Array.from(editor.querySelectorAll('[data-metadata-file-row]'))
      const hasEntries = rows.some(row => {
        const type = row.querySelector('[data-metadata-file-type]')?.value || ''
        const location = row.querySelector('[data-metadata-file-location]')?.value || ''
        return Boolean(normalizeMetadataFileEntry({ type, location }))
      })
      const hasInvalid = rows.some(row => {
        const state = String(row.dataset.metadataFileState || '').trim().toLowerCase()
        return state === 'error' || state === 'warning'
      })

      accordionHeader.classList.remove('invalid')
      if (hasInvalid) {
        accordionHeader.classList.add('invalid')
        return
      }

      accordionHeader.classList.remove('warning')
      if (hasEntries) {
        accordionHeader.classList.add('selected')
      } else {
        accordionHeader.classList.remove('selected')
      }
    }

    function applyMetadataFileServerErrors (editor, errors) {
      if (!editor || !Array.isArray(errors) || !errors.length) return false
      const rows = Array.from(editor.querySelectorAll('[data-metadata-file-row]'))
      rows.forEach(row => setMetadataFileStatus(row, '', ''))
      let applied = false
      errors.forEach(error => {
        const text = String(error || '').trim()
        const match = text.match(/metadata_files\[(\d+)\]:\s*(.+)$/i)
        if (!match) return
        const index = Number(match[1]) - 1
        const message = match[2] || 'Validation failed.'
        if (!Number.isInteger(index) || index < 0 || index >= rows.length) return
        setMetadataFileStatus(rows[index], 'error', message)
        applied = true
      })
      return applied
    }

    function syncMetadataFilesEditor (editor, emitEvents = true) {
      if (!editor) return []
      const hidden = editor.querySelector('input[type="hidden"][name$="-metadata_files"]')
      if (!hidden) return []
      const rows = Array.from(editor.querySelectorAll('[data-metadata-file-row]'))
      const entries = rows.map(row => {
        const type = row.querySelector('[data-metadata-file-type]')?.value
        const location = row.querySelector('[data-metadata-file-location]')?.value
        const validated = String(row.dataset.metadataFileState || '').trim().toLowerCase() === 'success'
        return normalizeMetadataFileEntry({ type, location, validated })
      }).filter(Boolean)
      hidden.value = JSON.stringify(entries)
      if (emitEvents) {
        hidden.dispatchEvent(new Event('input', { bubbles: true }))
        hidden.dispatchEvent(new Event('change', { bubbles: true }))
      }
      updateMetadataFilesAccordionState(editor)
      return entries
    }

    function renderMetadataFilesEditor (editor) {
      if (!editor) return
      const hidden = editor.querySelector('input[type="hidden"][name$="-metadata_files"]')
      const list = editor.querySelector('[data-metadata-files-list]')
      if (!hidden || !list) return
      updateMetadataCustomRepoStatus(editor)
      const entries = parseMetadataFilesValue(hidden.value)
      list.replaceChildren()
      entries.forEach(entry => list.appendChild(buildMetadataFileRow(entry)))
      list.querySelectorAll('[data-metadata-file-row]').forEach(row => {
        if (applyMetadataFileDependencyState(row)) return
        if (String(row.dataset.metadataFileState || '').trim().toLowerCase() === 'success') {
          setMetadataFileButtonState(row, 'success')
        } else {
          setMetadataFileButtonState(row, 'idle')
        }
      })
      syncMetadataFilesEditor(editor, false)
      updateMetadataFilesAccordionState(editor)
    }

    function initMetadataFilesEditors (scope) {
      const root = scope || document
      root.querySelectorAll('[data-metadata-files-editor]').forEach(editor => {
        if (editor.dataset.metadataFilesReady === 'true') return
        renderMetadataFilesEditor(editor)
        editor.dataset.metadataFilesReady = 'true'
      })
    }

    function buildCollectionFileRow (entry = {}) {
      const wrapper = document.createElement('div')
      wrapper.className = 'card bg-body-tertiary border-secondary'
      wrapper.setAttribute('data-collection-file-row', 'true')
      wrapper.innerHTML = `
        <div class="card-body">
          <div class="row g-3 align-items-end">
            <div class="col-md-2">
              <label class="form-label small text-muted">Type</label>
              <select class="form-select form-select-sm" data-collection-file-type>
                <option value="file">file</option>
                <option value="folder">folder</option>
                <option value="git">git</option>
                <option value="repo">repo</option>
                <option value="url">url</option>
              </select>
            </div>
            <div class="col-md-7">
              <label class="form-label small text-muted">Location</label>
              <input type="text" class="form-control form-control-sm" data-collection-file-location placeholder="config/collections.yml, config/collections/, user/file.yml, or https://example.com/collections.yml">
            </div>
            <div class="col-md-3 d-flex gap-2 justify-content-md-end">
              <button type="button" class="btn btn-success btn-sm" data-validate-collection-file>Validate</button>
              <button type="button" class="btn btn-danger btn-sm" data-remove-collection-file>Remove</button>
            </div>
          </div>
          <div class="mt-2 small d-none" data-collection-file-status></div>
        </div>
      `
      const typeSelect = wrapper.querySelector('[data-collection-file-type]')
      const locationInput = wrapper.querySelector('[data-collection-file-location]')
      if (typeSelect && ['file', 'folder', 'git', 'repo', 'url'].includes(entry.type)) {
        typeSelect.value = entry.type
      }
      if (locationInput && entry.location) {
        locationInput.value = entry.location
      }
      if (entry.validated) {
        wrapper.dataset.collectionFileState = 'success'
        wrapper.dataset.collectionFileButtonState = 'success'
      }
      updateCollectionFileValidateButton(wrapper, Boolean(entry.validated))
      return wrapper
    }

    function updateCollectionFileValidateButton (row, isValidated) {
      if (!row) return
      const button = row.querySelector('[data-validate-collection-file]')
      if (!button) return
      const state = String(row.dataset.collectionFileButtonState || '').trim() || (isValidated ? 'success' : 'idle')
      button.classList.remove('btn-success', 'btn-secondary')
      if (state === 'success') {
        button.disabled = true
        button.classList.add('btn-secondary')
        button.textContent = 'Validated'
        return
      }
      if (state === 'blocked') {
        button.disabled = true
        button.classList.add('btn-secondary')
        button.textContent = 'Needs Repo'
        return
      }
      if (state === 'loading') {
        button.disabled = true
        button.classList.add('btn-secondary')
        button.textContent = 'Validating...'
        return
      }
      button.disabled = false
      button.classList.add('btn-success')
      button.textContent = 'Validate'
    }

    function setCollectionFileButtonState (row, state) {
      if (!row) return
      row.dataset.collectionFileButtonState = state || 'idle'
      updateCollectionFileValidateButton(row, state === 'success')
    }

    function updateCollectionCustomRepoStatus (editor) {
      if (!editor) return
      const target = editor.querySelector('[data-collection-custom-repo-status]')
      if (!target) return

      target.replaceChildren()
      target.className = 'alert small mb-3'
      if (!metadataCustomRepoBase) {
        target.classList.add('alert-warning')
        target.append('Custom Repo is not configured. ')
        target.append('Use ')
        appendMetadataSettingsLink(target, 'alert-link fw-semibold')
        target.append(' to configure and save it before using ')
        const code = document.createElement('code')
        code.textContent = 'repo'
        target.appendChild(code)
        target.append(' collection files.')
        return
      }

      target.classList.add('alert-secondary')
      const label = document.createElement('div')
      label.className = 'fw-semibold mb-1'
      label.textContent = 'Custom Repo base used for repo entries'
      target.appendChild(label)

      const baseValue = document.createElement('code')
      baseValue.textContent = metadataCustomRepoBase
      target.appendChild(baseValue)

      if (metadataCustomRepoRaw && metadataCustomRepoRaw !== metadataCustomRepoBase) {
        const savedValue = document.createElement('div')
        savedValue.className = 'mt-2'
        savedValue.append('Saved Custom Repo value: ')
        const savedCode = document.createElement('code')
        savedCode.textContent = metadataCustomRepoRaw
        savedValue.appendChild(savedCode)
        target.appendChild(savedValue)
      }

      const hint = document.createElement('div')
      hint.className = 'mt-2'
      hint.append('Change it in ')
      appendMetadataSettingsLink(hint, 'alert-link fw-semibold')
      hint.append('.')
      target.appendChild(hint)
    }

    function applyCollectionFileDependencyState (row, opts = {}) {
      if (!row) return false
      const skipStatus = Boolean(opts.skipStatus)
      const type = row.querySelector('[data-collection-file-type]')?.value || ''
      if (type !== 'repo') {
        if (row.dataset.collectionFileDependency === 'repo-missing') {
          row.dataset.collectionFileDependency = ''
        }
        return false
      }

      if (metadataCustomRepoBase) {
        if (row.dataset.collectionFileDependency === 'repo-missing') {
          row.dataset.collectionFileDependency = ''
        }
        return false
      }

      row.dataset.collectionFileDependency = 'repo-missing'
      setCollectionFileButtonState(row, 'blocked')
      if (!skipStatus) {
        setCollectionFileStatus(row, 'error', collectionRepoDependencyMessage)
      }
      return true
    }

    function renderCollectionFileStatusMessage (target, message) {
      target.replaceChildren()
      if (!message) return

      if (typeof message === 'object' && message !== null) {
        const text = String(message.text || message.message || '').trim()
        const files = Array.isArray(message.files) ? message.files.filter(Boolean) : []
        if (text) {
          const summary = document.createElement('div')
          appendInlineCodeText(summary, text)
          target.appendChild(summary)
        }
        if (files.length) {
          if (files.length <= 5) {
            const list = document.createElement('ul')
            list.className = 'mb-0 mt-1 ps-3'
            files.forEach(file => {
              const item = document.createElement('li')
              appendInlineCodeText(item, file, { wrapPlainInCode: true })
              list.appendChild(item)
            })
            target.appendChild(list)
          } else {
            const details = document.createElement('details')
            details.className = 'mt-1'
            const summary = document.createElement('summary')
            summary.className = 'cursor-pointer'
            summary.textContent = 'Show files'
            details.appendChild(summary)
            const list = document.createElement('ul')
            list.className = 'mb-0 mt-1 ps-3'
            files.forEach(file => {
              const item = document.createElement('li')
              appendInlineCodeText(item, file, { wrapPlainInCode: true })
              list.appendChild(item)
            })
            details.appendChild(list)
            target.appendChild(details)
          }
        }
        return
      }

      const text = String(message || '').trim()
      if (!text) return

      if (text === collectionRepoDependencyMessage) {
        target.append('Collection file repo entries require Custom Repo to be configured and saved first within the ')
        appendMetadataSettingsLink(target)
        target.append(' page.')
        return
      }

      appendInlineCodeText(target, text)
    }

    function setCollectionFileStatus (row, kind, message) {
      if (!row) return
      const target = row.querySelector('[data-collection-file-status]')
      if (!target) return
      row.dataset.collectionFileState = kind || ''
      target.className = 'mt-2 small'
      if (!message) {
        target.classList.add('d-none')
        target.textContent = ''
        if (applyCollectionFileDependencyState(row, { skipStatus: true })) {
          setCollectionFileButtonState(row, 'blocked')
        } else {
          setCollectionFileButtonState(row, 'idle')
        }
        const editor = row.closest('[data-collection-files-editor]')
        if (editor) updateCollectionFilesAccordionState(editor)
        return
      }
      target.classList.remove('d-none')
      if (kind === 'success') {
        target.classList.add('text-success')
      } else if (kind === 'error') {
        target.classList.add('text-danger')
      } else {
        target.classList.add('text-warning')
      }
      renderCollectionFileStatusMessage(target, message)
      if (kind === 'success') {
        setCollectionFileButtonState(row, 'success')
      } else if (row.dataset.collectionFileDependency === 'repo-missing') {
        setCollectionFileButtonState(row, 'blocked')
      } else {
        setCollectionFileButtonState(row, 'idle')
      }
      const editor = row.closest('[data-collection-files-editor]')
      if (editor) updateCollectionFilesAccordionState(editor)
    }

    function updateCollectionFilesAccordionState (editor) {
      if (!editor) return
      const accordionItem = editor.closest('.accordion-item')
      const accordionHeader = accordionItem?.querySelector(':scope > .accordion-header')
      if (!accordionHeader) return

      const rows = Array.from(editor.querySelectorAll('[data-collection-file-row]'))
      const hasEntries = rows.some(row => normalizeMetadataFileEntry({
        type: row.querySelector('[data-collection-file-type]')?.value || '',
        location: row.querySelector('[data-collection-file-location]')?.value || ''
      }))
      const hasInvalid = rows.some(row => {
        const state = String(row.dataset.collectionFileState || '').trim().toLowerCase()
        return state === 'error' || state === 'warning'
      })

      accordionHeader.classList.remove('warning')
      accordionHeader.classList.toggle('invalid', hasInvalid)
      if (!hasInvalid && hasEntries) {
        accordionHeader.classList.add('selected')
      } else {
        accordionHeader.classList.remove('selected')
        if (!hasEntries && !hasInvalid && typeof EventHandler !== 'undefined' && typeof EventHandler.updateAccordionHighlights === 'function') {
          EventHandler.updateAccordionHighlights()
        }
      }
    }

    function applyCollectionFileServerErrors (editor, errors) {
      if (!editor || !Array.isArray(errors) || !errors.length) return false
      const rows = Array.from(editor.querySelectorAll('[data-collection-file-row]'))
      rows.forEach(row => setCollectionFileStatus(row, '', ''))
      let applied = false
      errors.forEach(error => {
        const text = String(error || '').trim()
        const match = text.match(/collection_files\[(\d+)\]:\s*(.+)$/i)
        if (!match) return
        const index = Number(match[1]) - 1
        const message = match[2] || 'Validation failed.'
        if (!Number.isInteger(index) || index < 0 || index >= rows.length) return
        setCollectionFileStatus(rows[index], 'error', message)
        applied = true
      })
      return applied
    }

    function syncCollectionFilesEditor (editor, emitEvents = true) {
      if (!editor) return []
      const hidden = editor.querySelector('input[type="hidden"][name$="-collection_files"]')
      if (!hidden) return []
      const rows = Array.from(editor.querySelectorAll('[data-collection-file-row]'))
      const entries = rows.map(row => {
        const type = row.querySelector('[data-collection-file-type]')?.value
        const location = row.querySelector('[data-collection-file-location]')?.value
        const validated = String(row.dataset.collectionFileState || '').trim().toLowerCase() === 'success'
        return normalizeMetadataFileEntry({ type, location, validated })
      }).filter(Boolean)
      hidden.value = JSON.stringify(entries)
      if (emitEvents) {
        hidden.dispatchEvent(new Event('input', { bubbles: true }))
        hidden.dispatchEvent(new Event('change', { bubbles: true }))
      }
      updateCollectionFilesAccordionState(editor)
      return entries
    }

    function renderCollectionFilesEditor (editor) {
      if (!editor) return
      const hidden = editor.querySelector('input[type="hidden"][name$="-collection_files"]')
      const list = editor.querySelector('[data-collection-files-list]')
      if (!hidden || !list) return
      updateCollectionCustomRepoStatus(editor)
      const entries = parseMetadataFilesValue(hidden.value)
      list.replaceChildren()
      entries.forEach(entry => list.appendChild(buildCollectionFileRow(entry)))
      list.querySelectorAll('[data-collection-file-row]').forEach(row => {
        if (applyCollectionFileDependencyState(row)) return
        if (String(row.dataset.collectionFileState || '').trim().toLowerCase() === 'success') {
          setCollectionFileButtonState(row, 'success')
        } else {
          setCollectionFileButtonState(row, 'idle')
        }
      })
      syncCollectionFilesEditor(editor, false)
      updateCollectionFilesAccordionState(editor)
    }

    function initCollectionFilesEditors (scope) {
      const root = scope || document
      root.querySelectorAll('[data-collection-files-editor]').forEach(editor => {
        if (editor.dataset.collectionFilesReady === 'true') return
        renderCollectionFilesEditor(editor)
        editor.dataset.collectionFilesReady = 'true'
      })
    }

    document.addEventListener('click', async function (event) {
      const addButton = event.target.closest('[data-add-metadata-file]')
      if (addButton) {
        const editor = addButton.closest('[data-metadata-files-editor]')
        const list = editor?.querySelector('[data-metadata-files-list]')
        if (!editor || !list) return
        list.appendChild(buildMetadataFileRow({ type: 'file', location: '' }))
        syncMetadataFilesEditor(editor)
        return
      }

      const removeButton = event.target.closest('[data-remove-metadata-file]')
      if (removeButton) {
        const row = removeButton.closest('[data-metadata-file-row]')
        const editor = removeButton.closest('[data-metadata-files-editor]')
        if (!row || !editor) return
        row.remove()
        syncMetadataFilesEditor(editor)
        return
      }

      const validateButton = event.target.closest('[data-validate-metadata-file]')
      if (validateButton) {
        const row = validateButton.closest('[data-metadata-file-row]')
        const editor = validateButton.closest('[data-metadata-files-editor]')
        if (!row || !editor) return
        if (applyMetadataFileDependencyState(row)) return
        const type = row.querySelector('[data-metadata-file-type]')?.value || ''
        const location = row.querySelector('[data-metadata-file-location]')?.value || ''
        const libraryId = String(editor.dataset.libraryId || '').trim()
        syncMetadataFilesEditor(editor, false)
        setMetadataFileStatus(row, '', 'Validating...')
        setMetadataFileButtonState(row, 'loading')
        try {
          const response = await fetch('/validate_metadata_file', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              metadata_file_type: type,
              metadata_file_location: location,
              library_id: libraryId,
              config_name: getActiveConfigName()
            })
          })
          const payload = await response.json().catch(() => ({}))
          if (!response.ok || !payload.valid) {
            setMetadataFileStatus(row, 'error', payload.error_details || {
              text: payload.error || 'Validation failed.',
              files: Array.isArray(payload.files) ? payload.files : []
            })
          } else {
            applyNormalizedLibraryFileLocation(row, '[data-metadata-file-location]', payload, editor, syncMetadataFilesEditor)
            setMetadataFileStatus(row, 'success', {
              text: payload.message || 'Metadata source looks valid.',
              files: Array.isArray(payload.files) ? payload.files : []
            })
            syncMetadataFilesEditor(editor, false)
          }
        } catch (_error) {
          setMetadataFileStatus(row, 'error', 'Validation request failed.')
        } finally {
          if (row.dataset.metadataFileState !== 'success' && row.dataset.metadataFileDependency !== 'repo-missing') {
            setMetadataFileButtonState(row, 'idle')
          }
        }
      }
    })

    document.addEventListener('input', function (event) {
      const target = event.target
      if (!target || !target.closest('[data-metadata-files-editor]')) return
      if (!target.matches('[data-metadata-file-type], [data-metadata-file-location]')) return
      const row = target.closest('[data-metadata-file-row]')
      const editor = target.closest('[data-metadata-files-editor]')
      setMetadataFileStatus(row, '', '')
      applyMetadataFileDependencyState(row)
      syncMetadataFilesEditor(editor)
    })

    document.addEventListener('change', function (event) {
      const target = event.target
      if (!target || !target.closest('[data-metadata-files-editor]')) return
      if (!target.matches('[data-metadata-file-type], [data-metadata-file-location]')) return
      const row = target.closest('[data-metadata-file-row]')
      const editor = target.closest('[data-metadata-files-editor]')
      setMetadataFileStatus(row, '', '')
      applyMetadataFileDependencyState(row)
      syncMetadataFilesEditor(editor)
    })

    initMetadataFilesEditors(document)
    if (libraryContainer && typeof MutationObserver !== 'undefined') {
      const metadataObserver = new MutationObserver(() => initMetadataFilesEditors(libraryContainer))
      metadataObserver.observe(libraryContainer, { childList: true, subtree: true })
    }

    document.addEventListener('click', async function (event) {
      const addButton = event.target.closest('[data-add-collection-file]')
      if (addButton) {
        const editor = addButton.closest('[data-collection-files-editor]')
        const list = editor?.querySelector('[data-collection-files-list]')
        if (!editor || !list) return
        list.appendChild(buildCollectionFileRow({ type: 'file', location: '' }))
        syncCollectionFilesEditor(editor)
        return
      }

      const removeButton = event.target.closest('[data-remove-collection-file]')
      if (removeButton) {
        const row = removeButton.closest('[data-collection-file-row]')
        const editor = removeButton.closest('[data-collection-files-editor]')
        if (!row || !editor) return
        row.remove()
        syncCollectionFilesEditor(editor)
        return
      }

      const validateButton = event.target.closest('[data-validate-collection-file]')
      if (validateButton) {
        const row = validateButton.closest('[data-collection-file-row]')
        const editor = validateButton.closest('[data-collection-files-editor]')
        if (!row || !editor) return
        if (applyCollectionFileDependencyState(row)) return
        const type = row.querySelector('[data-collection-file-type]')?.value || ''
        const location = row.querySelector('[data-collection-file-location]')?.value || ''
        const libraryId = String(editor.dataset.libraryId || '').trim()
        syncCollectionFilesEditor(editor, false)
        setCollectionFileStatus(row, '', 'Validating...')
        setCollectionFileButtonState(row, 'loading')
        try {
          const response = await fetch('/validate_collection_file', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              collection_file_type: type,
              collection_file_location: location,
              library_id: libraryId,
              config_name: getActiveConfigName()
            })
          })
          const payload = await response.json().catch(() => ({}))
          if (!response.ok || !payload.valid) {
            setCollectionFileStatus(row, 'error', payload.error_details || {
              text: payload.error || 'Validation failed.',
              files: Array.isArray(payload.files) ? payload.files : []
            })
          } else {
            applyNormalizedLibraryFileLocation(row, '[data-collection-file-location]', payload, editor, syncCollectionFilesEditor)
            setCollectionFileStatus(row, 'success', {
              text: payload.message || 'Collection source looks valid.',
              files: Array.isArray(payload.files) ? payload.files : []
            })
            syncCollectionFilesEditor(editor, false)
          }
        } catch (_error) {
          setCollectionFileStatus(row, 'error', 'Validation request failed.')
        } finally {
          if (row.dataset.collectionFileState !== 'success' && row.dataset.collectionFileDependency !== 'repo-missing') {
            setCollectionFileButtonState(row, 'idle')
          }
        }
      }
    })

    document.addEventListener('input', function (event) {
      const target = event.target
      if (!target || !target.closest('[data-collection-files-editor]')) return
      if (!target.matches('[data-collection-file-type], [data-collection-file-location]')) return
      const row = target.closest('[data-collection-file-row]')
      const editor = target.closest('[data-collection-files-editor]')
      setCollectionFileStatus(row, '', '')
      applyCollectionFileDependencyState(row)
      syncCollectionFilesEditor(editor)
    })

    document.addEventListener('change', function (event) {
      const target = event.target
      if (!target || !target.closest('[data-collection-files-editor]')) return
      if (!target.matches('[data-collection-file-type], [data-collection-file-location]')) return
      const row = target.closest('[data-collection-file-row]')
      const editor = target.closest('[data-collection-files-editor]')
      setCollectionFileStatus(row, '', '')
      applyCollectionFileDependencyState(row)
      syncCollectionFilesEditor(editor)
    })

    initCollectionFilesEditors(document)
    if (libraryContainer && typeof MutationObserver !== 'undefined') {
      const collectionObserver = new MutationObserver(() => initCollectionFilesEditors(libraryContainer))
      collectionObserver.observe(libraryContainer, { childList: true, subtree: true })
    }

    function buildOverlayFileRow (entry = {}) {
      const wrapper = document.createElement('div')
      wrapper.className = 'card bg-body-tertiary border-secondary'
      wrapper.setAttribute('data-overlay-file-row', 'true')
      wrapper.innerHTML = `
        <div class="card-body">
          <div class="row g-3 align-items-end">
            <div class="col-md-2">
              <label class="form-label small text-muted">Type</label>
              <select class="form-select form-select-sm" data-overlay-file-type>
                <option value="file">file</option>
                <option value="folder">folder</option>
                <option value="git">git</option>
                <option value="repo">repo</option>
                <option value="url">url</option>
              </select>
            </div>
            <div class="col-md-7">
              <label class="form-label small text-muted">Location</label>
              <input type="text" class="form-control form-control-sm" data-overlay-file-location placeholder="config/overlays.yml, config/overlays/, user/file.yml, or https://example.com/overlays.yml">
            </div>
            <div class="col-md-3 d-flex gap-2 justify-content-md-end">
              <button type="button" class="btn btn-success btn-sm" data-validate-overlay-file>Validate</button>
              <button type="button" class="btn btn-danger btn-sm" data-remove-overlay-file>Remove</button>
            </div>
          </div>
          <div class="mt-2 small d-none" data-overlay-file-status></div>
        </div>
      `
      const typeSelect = wrapper.querySelector('[data-overlay-file-type]')
      const locationInput = wrapper.querySelector('[data-overlay-file-location]')
      if (typeSelect && ['file', 'folder', 'git', 'repo', 'url'].includes(entry.type)) {
        typeSelect.value = entry.type
      }
      if (locationInput && entry.location) {
        locationInput.value = entry.location
      }
      if (entry.validated) {
        wrapper.dataset.overlayFileState = 'success'
        wrapper.dataset.overlayFileButtonState = 'success'
      }
      updateOverlayFileValidateButton(wrapper, Boolean(entry.validated))
      return wrapper
    }

    function updateOverlayFileValidateButton (row, isValidated) {
      if (!row) return
      const button = row.querySelector('[data-validate-overlay-file]')
      if (!button) return
      const state = String(row.dataset.overlayFileButtonState || '').trim() || (isValidated ? 'success' : 'idle')
      button.classList.remove('btn-success', 'btn-secondary')
      if (state === 'success') {
        button.disabled = true
        button.classList.add('btn-secondary')
        button.textContent = 'Validated'
        return
      }
      if (state === 'blocked') {
        button.disabled = true
        button.classList.add('btn-secondary')
        button.textContent = 'Needs Repo'
        return
      }
      if (state === 'loading') {
        button.disabled = true
        button.classList.add('btn-secondary')
        button.textContent = 'Validating...'
        return
      }
      button.disabled = false
      button.classList.add('btn-success')
      button.textContent = 'Validate'
    }

    function setOverlayFileButtonState (row, state) {
      if (!row) return
      row.dataset.overlayFileButtonState = state || 'idle'
      updateOverlayFileValidateButton(row, state === 'success')
    }

    function updateOverlayCustomRepoStatus (editor) {
      if (!editor) return
      const target = editor.querySelector('[data-overlay-custom-repo-status]')
      if (!target) return

      target.replaceChildren()
      target.className = 'alert small mb-3'
      if (!metadataCustomRepoBase) {
        target.classList.add('alert-warning')
        target.append('Custom Repo is not configured. ')
        target.append('Use ')
        appendMetadataSettingsLink(target, 'alert-link fw-semibold')
        target.append(' to configure and save it before using ')
        const code = document.createElement('code')
        code.textContent = 'repo'
        target.appendChild(code)
        target.append(' overlay files.')
        return
      }

      target.classList.add('alert-secondary')
      const label = document.createElement('div')
      label.className = 'fw-semibold mb-1'
      label.textContent = 'Custom Repo base used for repo entries'
      target.appendChild(label)

      const baseValue = document.createElement('code')
      baseValue.textContent = metadataCustomRepoBase
      target.appendChild(baseValue)

      if (metadataCustomRepoRaw && metadataCustomRepoRaw !== metadataCustomRepoBase) {
        const savedValue = document.createElement('div')
        savedValue.className = 'mt-2'
        savedValue.append('Saved Custom Repo value: ')
        const savedCode = document.createElement('code')
        savedCode.textContent = metadataCustomRepoRaw
        savedValue.appendChild(savedCode)
        target.appendChild(savedValue)
      }

      const hint = document.createElement('div')
      hint.className = 'mt-2'
      hint.append('Change it in ')
      appendMetadataSettingsLink(hint, 'alert-link fw-semibold')
      hint.append('.')
      target.appendChild(hint)
    }

    function applyOverlayFileDependencyState (row, opts = {}) {
      if (!row) return false
      const skipStatus = Boolean(opts.skipStatus)
      const type = row.querySelector('[data-overlay-file-type]')?.value || ''
      if (type !== 'repo') {
        if (row.dataset.overlayFileDependency === 'repo-missing') {
          row.dataset.overlayFileDependency = ''
        }
        return false
      }

      if (metadataCustomRepoBase) {
        if (row.dataset.overlayFileDependency === 'repo-missing') {
          row.dataset.overlayFileDependency = ''
        }
        return false
      }

      row.dataset.overlayFileDependency = 'repo-missing'
      setOverlayFileButtonState(row, 'blocked')
      if (!skipStatus) {
        setOverlayFileStatus(row, 'error', overlayRepoDependencyMessage)
      }
      return true
    }

    function renderOverlayFileStatusMessage (target, message) {
      target.replaceChildren()
      if (!message) return

      if (typeof message === 'object' && message !== null) {
        const text = String(message.text || message.message || '').trim()
        const files = Array.isArray(message.files) ? message.files.filter(Boolean) : []
        if (text) {
          const summary = document.createElement('div')
          appendInlineCodeText(summary, text)
          target.appendChild(summary)
        }
        if (files.length) {
          if (files.length <= 5) {
            const list = document.createElement('ul')
            list.className = 'mb-0 mt-1 ps-3'
            files.forEach(file => {
              const item = document.createElement('li')
              appendInlineCodeText(item, file, { wrapPlainInCode: true })
              list.appendChild(item)
            })
            target.appendChild(list)
          } else {
            const details = document.createElement('details')
            details.className = 'mt-1'
            const summary = document.createElement('summary')
            summary.className = 'cursor-pointer'
            summary.textContent = 'Show files'
            details.appendChild(summary)
            const list = document.createElement('ul')
            list.className = 'mb-0 mt-1 ps-3'
            files.forEach(file => {
              const item = document.createElement('li')
              appendInlineCodeText(item, file, { wrapPlainInCode: true })
              list.appendChild(item)
            })
            details.appendChild(list)
            target.appendChild(details)
          }
        }
        return
      }

      const text = String(message || '').trim()
      if (!text) return

      if (text === overlayRepoDependencyMessage) {
        target.append('Overlay file repo entries require Custom Repo to be configured and saved first within the ')
        appendMetadataSettingsLink(target)
        target.append(' page.')
        return
      }

      appendInlineCodeText(target, text)
    }

    function setOverlayFileStatus (row, kind, message) {
      if (!row) return
      const target = row.querySelector('[data-overlay-file-status]')
      if (!target) return
      row.dataset.overlayFileState = kind || ''
      target.className = 'mt-2 small'
      if (!message) {
        target.classList.add('d-none')
        target.textContent = ''
        if (applyOverlayFileDependencyState(row, { skipStatus: true })) {
          setOverlayFileButtonState(row, 'blocked')
        } else {
          setOverlayFileButtonState(row, 'idle')
        }
        const editor = row.closest('[data-overlay-files-editor]')
        if (editor) updateOverlayFilesAccordionState(editor)
        return
      }
      target.classList.remove('d-none')
      if (kind === 'success') {
        target.classList.add('text-success')
      } else if (kind === 'error') {
        target.classList.add('text-danger')
      } else {
        target.classList.add('text-warning')
      }
      renderOverlayFileStatusMessage(target, message)
      if (kind === 'success') {
        setOverlayFileButtonState(row, 'success')
      } else if (row.dataset.overlayFileDependency === 'repo-missing') {
        setOverlayFileButtonState(row, 'blocked')
      } else {
        setOverlayFileButtonState(row, 'idle')
      }
      const editor = row.closest('[data-overlay-files-editor]')
      if (editor) updateOverlayFilesAccordionState(editor)
    }

    function updateOverlayFilesAccordionState (editor) {
      if (!editor) return
      const accordionItem = editor.closest('.accordion-item')
      const accordionHeader = accordionItem?.querySelector(':scope > .accordion-header')
      if (!accordionHeader) return

      const rows = Array.from(editor.querySelectorAll('[data-overlay-file-row]'))
      const hasEntries = rows.some(row => normalizeMetadataFileEntry({
        type: row.querySelector('[data-overlay-file-type]')?.value || '',
        location: row.querySelector('[data-overlay-file-location]')?.value || ''
      }))
      const hasInvalid = rows.some(row => {
        const state = String(row.dataset.overlayFileState || '').trim().toLowerCase()
        return state === 'error' || state === 'warning'
      })

      accordionHeader.classList.remove('warning')
      accordionHeader.classList.toggle('invalid', hasInvalid)
      if (!hasInvalid && hasEntries) {
        accordionHeader.classList.add('selected')
      } else {
        accordionHeader.classList.remove('selected')
        if (!hasEntries && !hasInvalid && typeof EventHandler !== 'undefined' && typeof EventHandler.updateAccordionHighlights === 'function') {
          EventHandler.updateAccordionHighlights()
        }
      }
    }

    function applyOverlayFileServerErrors (editor, errors) {
      if (!editor || !Array.isArray(errors) || !errors.length) return false
      const rows = Array.from(editor.querySelectorAll('[data-overlay-file-row]'))
      rows.forEach(row => setOverlayFileStatus(row, '', ''))
      let applied = false
      errors.forEach(error => {
        const text = String(error || '').trim()
        const match = text.match(/overlay_files\[(\d+)\]:\s*(.+)$/i)
        if (!match) return
        const index = Number(match[1]) - 1
        const message = match[2] || 'Validation failed.'
        if (!Number.isInteger(index) || index < 0 || index >= rows.length) return
        setOverlayFileStatus(rows[index], 'error', message)
        applied = true
      })
      return applied
    }

    function syncOverlayFilesEditor (editor, emitEvents = true) {
      if (!editor) return []
      const hidden = editor.querySelector('input[type="hidden"][name$="-overlay_files"]')
      if (!hidden) return []
      const rows = Array.from(editor.querySelectorAll('[data-overlay-file-row]'))
      const entries = rows.map(row => {
        const type = row.querySelector('[data-overlay-file-type]')?.value
        const location = row.querySelector('[data-overlay-file-location]')?.value
        const validated = String(row.dataset.overlayFileState || '').trim().toLowerCase() === 'success'
        return normalizeMetadataFileEntry({ type, location, validated })
      }).filter(Boolean)
      hidden.value = JSON.stringify(entries)
      if (emitEvents) {
        hidden.dispatchEvent(new Event('input', { bubbles: true }))
        hidden.dispatchEvent(new Event('change', { bubbles: true }))
      }
      updateOverlayFilesAccordionState(editor)
      return entries
    }

    function renderOverlayFilesEditor (editor) {
      if (!editor) return
      const hidden = editor.querySelector('input[type="hidden"][name$="-overlay_files"]')
      const list = editor.querySelector('[data-overlay-files-list]')
      if (!hidden || !list) return
      updateOverlayCustomRepoStatus(editor)
      const entries = parseMetadataFilesValue(hidden.value)
      list.replaceChildren()
      entries.forEach(entry => list.appendChild(buildOverlayFileRow(entry)))
      list.querySelectorAll('[data-overlay-file-row]').forEach(row => {
        if (applyOverlayFileDependencyState(row)) return
        if (String(row.dataset.overlayFileState || '').trim().toLowerCase() === 'success') {
          setOverlayFileButtonState(row, 'success')
        } else {
          setOverlayFileButtonState(row, 'idle')
        }
      })
      syncOverlayFilesEditor(editor, false)
      updateOverlayFilesAccordionState(editor)
    }

    function initOverlayFilesEditors (scope) {
      const root = scope || document
      root.querySelectorAll('[data-overlay-files-editor]').forEach(editor => {
        if (editor.dataset.overlayFilesReady === 'true') return
        renderOverlayFilesEditor(editor)
        editor.dataset.overlayFilesReady = 'true'
      })
    }

    document.addEventListener('click', async function (event) {
      const addButton = event.target.closest('[data-add-overlay-file]')
      if (addButton) {
        const editor = addButton.closest('[data-overlay-files-editor]')
        const list = editor?.querySelector('[data-overlay-files-list]')
        if (!editor || !list) return
        list.appendChild(buildOverlayFileRow({ type: 'file', location: '' }))
        syncOverlayFilesEditor(editor)
        return
      }

      const removeButton = event.target.closest('[data-remove-overlay-file]')
      if (removeButton) {
        const row = removeButton.closest('[data-overlay-file-row]')
        const editor = removeButton.closest('[data-overlay-files-editor]')
        if (!row || !editor) return
        row.remove()
        syncOverlayFilesEditor(editor)
        return
      }

      const validateButton = event.target.closest('[data-validate-overlay-file]')
      if (validateButton) {
        const row = validateButton.closest('[data-overlay-file-row]')
        const editor = validateButton.closest('[data-overlay-files-editor]')
        if (!row || !editor) return
        if (applyOverlayFileDependencyState(row)) return
        const type = row.querySelector('[data-overlay-file-type]')?.value || ''
        const location = row.querySelector('[data-overlay-file-location]')?.value || ''
        const libraryId = String(editor.dataset.libraryId || '').trim()
        syncOverlayFilesEditor(editor, false)
        setOverlayFileStatus(row, '', 'Validating...')
        setOverlayFileButtonState(row, 'loading')
        try {
          const response = await fetch('/validate_overlay_file', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              overlay_file_type: type,
              overlay_file_location: location,
              library_id: libraryId,
              config_name: getActiveConfigName()
            })
          })
          const payload = await response.json().catch(() => ({}))
          if (!response.ok || !payload.valid) {
            setOverlayFileStatus(row, 'error', payload.error_details || {
              text: payload.error || 'Validation failed.',
              files: Array.isArray(payload.files) ? payload.files : []
            })
          } else {
            applyNormalizedLibraryFileLocation(row, '[data-overlay-file-location]', payload, editor, syncOverlayFilesEditor)
            setOverlayFileStatus(row, 'success', {
              text: payload.message || 'Overlay source looks valid.',
              files: Array.isArray(payload.files) ? payload.files : []
            })
            syncOverlayFilesEditor(editor, false)
          }
        } catch (_error) {
          setOverlayFileStatus(row, 'error', 'Validation request failed.')
        } finally {
          if (row.dataset.overlayFileState !== 'success' && row.dataset.overlayFileDependency !== 'repo-missing') {
            setOverlayFileButtonState(row, 'idle')
          }
        }
      }
    })

    document.addEventListener('input', function (event) {
      const target = event.target
      if (!target || !target.closest('[data-overlay-files-editor]')) return
      if (!target.matches('[data-overlay-file-type], [data-overlay-file-location]')) return
      const row = target.closest('[data-overlay-file-row]')
      const editor = target.closest('[data-overlay-files-editor]')
      setOverlayFileStatus(row, '', '')
      applyOverlayFileDependencyState(row)
      syncOverlayFilesEditor(editor)
    })

    document.addEventListener('change', function (event) {
      const target = event.target
      if (!target || !target.closest('[data-overlay-files-editor]')) return
      if (!target.matches('[data-overlay-file-type], [data-overlay-file-location]')) return
      const row = target.closest('[data-overlay-file-row]')
      const editor = target.closest('[data-overlay-files-editor]')
      setOverlayFileStatus(row, '', '')
      applyOverlayFileDependencyState(row)
      syncOverlayFilesEditor(editor)
    })

    initOverlayFilesEditors(document)
    if (libraryContainer && typeof MutationObserver !== 'undefined') {
      const overlayObserver = new MutationObserver(() => initOverlayFilesEditors(libraryContainer))
      overlayObserver.observe(libraryContainer, { childList: true, subtree: true })
    }

    // Ensure hidden "false" inputs don't submit alongside checked checkboxes with the same name
    function syncHiddenCheckboxPairs (scope) {
      const root = scope || document
      root.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        const hidden = root.querySelector(`input[type="hidden"][name="${cb.name}"]`)
        if (!hidden || cb.dataset.hiddenSynced === 'true') return
        const update = () => {
          hidden.disabled = !!cb.checked
        }
        cb.addEventListener('change', update)
        update()
        cb.dataset.hiddenSynced = 'true'
      })
    }

    function initTooltips (scope) {
      const root = scope || document
      if (typeof bootstrap === 'undefined' || !bootstrap.Tooltip) return
      const tooltipTriggerList = root.querySelectorAll('[data-bs-toggle="tooltip"]')
      tooltipTriggerList.forEach(el => {
        const existing = bootstrap.Tooltip.getInstance(el)
        if (existing) existing.dispose()
        bootstrap.Tooltip.getOrCreateInstance(el, { html: true, sanitize: false })
      })
    }

    function updateFontSelects (fonts, scope) {
      if (!Array.isArray(fonts)) return
      const root = scope || document
      root.querySelectorAll('select[data-font-select]').forEach(select => {
        const currentValue = select.value || select.dataset.default || ''
        const seen = new Set()
        const merged = []
        fonts.forEach(font => {
          if (!font || seen.has(font)) return
          merged.push(font)
          seen.add(font)
        })
        if (currentValue && !seen.has(currentValue)) {
          merged.push(currentValue)
        }
        select.replaceChildren()
        const placeholder = document.createElement('option')
        placeholder.value = ''
        placeholder.textContent = 'Select font'
        if (!currentValue) placeholder.selected = true
        select.appendChild(placeholder)
        merged.forEach(font => {
          const option = document.createElement('option')
          option.value = font
          option.textContent = font
          if (font === currentValue) option.selected = true
          select.appendChild(option)
        })
        if (typeof updateFontPreviewForSelect === 'function') {
          updateFontPreviewForSelect(select)
        }
        if (typeof updateFontPickerButton === 'function') {
          updateFontPickerButton(select)
        }
      })
    }

    function sortLanguageSelects (scope) {
      const root = scope || document
      const selects = Array.from(root.querySelectorAll('select')).filter(select => {
        const name = select.name || ''
        const id = select.id || ''
        return name.includes('attribute_template_variables[language]') ||
          name.includes('template_variables[language]') ||
          /template_variables_language$/i.test(id)
      })

      selects.forEach(select => {
        const options = Array.from(select.options)
        if (!options.length) return
        const currentValue = select.value
        const keep = []
        const sortable = []
        options.forEach(option => {
          const label = option.textContent.trim().toLowerCase()
          if (option.value === '' || label === 'none') {
            keep.push(option)
          } else {
            sortable.push(option)
          }
        })
        sortable.sort((a, b) => a.textContent.trim().localeCompare(b.textContent.trim()))
        select.replaceChildren()
        keep.forEach(option => select.appendChild(option))
        sortable.forEach(option => select.appendChild(option))
        select.value = currentValue
      })
    }

    const overlayLanguageWeightDefaults = {
      en: 610,
      de: 600,
      fr: 590,
      es: 580,
      pt: 570,
      ja: 560,
      ko: 550,
      zh: 540,
      da: 530,
      ru: 520,
      it: 510,
      hi: 500,
      te: 490,
      fa: 480,
      th: 470,
      nl: 460,
      no: 450,
      is: 440,
      sv: 430,
      tr: 420,
      pl: 410,
      cs: 400,
      uk: 390,
      hu: 380,
      ar: 370,
      bg: 360,
      bn: 350,
      bs: 340,
      ca: 330,
      cy: 320,
      el: 310,
      et: 300,
      eu: 290,
      fi: 280,
      tl: 270,
      fil: 265,
      gl: 260,
      he: 250,
      hr: 240,
      id: 230,
      ka: 220,
      kk: 210,
      kn: 200,
      la: 190,
      lt: 180,
      lv: 170,
      mk: 160,
      ml: 150,
      mr: 140,
      ms: 130,
      nb: 120,
      nn: 110,
      pa: 100,
      ro: 90,
      sk: 80,
      sl: 70,
      sq: 60,
      sr: 50,
      so: 45,
      sw: 40,
      ta: 30,
      ur: 20,
      ay: 19,
      ga: 18,
      li: 17,
      kh: 16,
      vi: 15,
      mn: 14,
      af: 13,
      bm: 12,
      ln: 11,
      wo: 10,
      lo: 9,
      myn: 8,
      iu: 7,
      rom: 6,
      am: 5,
      su: 4,
      zu: 3,
      lb: 2,
      mos: 1
    }

    function setupOverlayLanguageWeightBuilders (scope) {
      const root = scope || document
      root.querySelectorAll('[data-overlay-language-weight-builder]').forEach(wrapper => {
        if (wrapper.dataset.listenerAdded === 'true') return

        const templateName = String(wrapper.dataset.templateName || '').trim()
        const languageInputId = String(wrapper.dataset.languageInputId || '').trim()
        const rowsContainer = wrapper.querySelector('[data-overlay-language-weight-rows]')
        const addButton = wrapper.querySelector('[data-overlay-language-weight-add]')
        const hiddenContainer = wrapper.querySelector('[data-overlay-language-weight-hidden]')
        if (!templateName || !rowsContainer || !addButton || !hiddenContainer) return

        let options = []
        try {
          const parsed = JSON.parse(wrapper.dataset.options || '[]')
          if (Array.isArray(parsed)) {
            const seen = new Set()
            options = parsed
              .map(option => {
                if (typeof option === 'string') {
                  return { value: option, label: option }
                }
                if (option && typeof option === 'object' && option.value) {
                  return { value: String(option.value), label: String(option.label || option.value) }
                }
                return null
              })
              .filter(Boolean)
              .filter(option => {
                if (seen.has(option.value)) return false
                seen.add(option.value)
                return true
              })
          }
        } catch (_error) {
          options = []
        }

        let state = []
        try {
          const parsed = JSON.parse(wrapper.dataset.existing || '{}')
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            state = Object.entries(parsed).map(([key, weight], index) => ({
              id: `weight-${index + 1}`,
              key: String(key || '').trim(),
              weight: String(weight ?? '').trim()
            })).filter(row => row.key)
          }
        } catch (_error) {
          state = []
        }

        let rowCounter = state.length

        function getLanguageSelect () {
          return languageInputId ? document.getElementById(languageInputId) : null
        }

        function getSelectedLanguages () {
          const select = getLanguageSelect()
          if (!select || !select.multiple) return []
          return Array.from(select.selectedOptions)
            .map(option => String(option.value || '').trim())
            .filter(Boolean)
        }

        function getDefaultWeight (key) {
          return Object.prototype.hasOwnProperty.call(overlayLanguageWeightDefaults, key)
            ? overlayLanguageWeightDefaults[key]
            : null
        }

        function rowStatusText (row) {
          const defaultWeight = getDefaultWeight(row.key)
          const weightText = String(row.weight || '').trim()
          if (!weightText) return 'Using Kometa default weight'
          if (!/^-?\d+$/.test(weightText)) return 'Enter a whole number'
          if (defaultWeight !== null && Number(weightText) === defaultWeight) return 'Matches default weight, so it will not be emitted'
          return 'Custom override will be emitted'
        }

        function currentOptionsForRow (row) {
          const selectedLanguages = new Set(getSelectedLanguages())
          const selectedKeys = new Set(state.map(entry => entry.key).filter(Boolean))
          const weightedOptions = options.map(option => {
            const defaultWeight = getDefaultWeight(option.value)
            return {
              value: option.value,
              label: option.label,
              defaultWeight,
              preferred: selectedLanguages.has(option.value) || option.value === row.key,
              usedElsewhere: selectedKeys.has(option.value) && option.value !== row.key
            }
          })
          weightedOptions.sort((left, right) => {
            if (left.preferred !== right.preferred) return left.preferred ? -1 : 1
            return left.label.localeCompare(right.label)
          })
          return weightedOptions
        }

        function nextRowId () {
          rowCounter += 1
          return `weight-${rowCounter}`
        }

        function nextAvailableKey () {
          const usedKeys = new Set(state.map(row => row.key).filter(Boolean))
          const selectedLanguages = getSelectedLanguages()
          for (const key of selectedLanguages) {
            if (!usedKeys.has(key)) return key
          }
          for (const option of options) {
            if (!usedKeys.has(option.value)) return option.value
          }
          return options[0]?.value || ''
        }

        function syncHiddenInputs () {
          hiddenContainer.replaceChildren()
          state.forEach(row => {
            const key = String(row.key || '').trim()
            const weightText = String(row.weight || '').trim()
            if (!key || !weightText || !/^-?\d+$/.test(weightText)) return
            const numericWeight = Number.parseInt(weightText, 10)
            const defaultWeight = getDefaultWeight(key)
            if (defaultWeight !== null && numericWeight === defaultWeight) return
            const hidden = document.createElement('input')
            hidden.type = 'hidden'
            hidden.name = `${templateName}[weight_${key}]`
            hidden.value = String(numericWeight)
            hiddenContainer.appendChild(hidden)
          })
        }

        function renderRows () {
          rowsContainer.replaceChildren()

          state.forEach(row => {
            const rowWrap = document.createElement('div')
            rowWrap.className = 'border rounded p-2'

            const controls = document.createElement('div')
            controls.className = 'row g-2 align-items-end'

            const keyCol = document.createElement('div')
            keyCol.className = 'col-md-5'
            const keyLabel = document.createElement('label')
            keyLabel.className = 'form-label mb-1'
            keyLabel.textContent = 'Language'
            const keySelect = document.createElement('select')
            keySelect.className = 'form-select form-select-sm'
            currentOptionsForRow(row).forEach(option => {
              const el = document.createElement('option')
              el.value = option.value
              const suffix = option.defaultWeight !== null ? ` (${option.value}, default ${option.defaultWeight})` : ` (${option.value})`
              el.textContent = `${option.label}${suffix}`
              if (option.value === row.key) el.selected = true
              if (option.usedElsewhere) el.disabled = true
              keySelect.appendChild(el)
            })
            keyCol.append(keyLabel, keySelect)

            const defaultCol = document.createElement('div')
            defaultCol.className = 'col-md-3'
            const defaultLabel = document.createElement('label')
            defaultLabel.className = 'form-label mb-1'
            defaultLabel.textContent = 'Default Weight'
            const defaultBadge = document.createElement('div')
            defaultBadge.className = 'form-control form-control-sm bg-body-tertiary'
            const defaultWeight = getDefaultWeight(row.key)
            defaultBadge.textContent = defaultWeight !== null ? String(defaultWeight) : 'Unknown'
            defaultCol.append(defaultLabel, defaultBadge)

            const customCol = document.createElement('div')
            customCol.className = 'col-md-3'
            const customLabel = document.createElement('label')
            customLabel.className = 'form-label mb-1'
            customLabel.textContent = 'Custom Weight'
            const customInput = document.createElement('input')
            customInput.type = 'number'
            customInput.className = 'form-control form-control-sm'
            customInput.step = '1'
            customInput.value = row.weight
            customInput.placeholder = defaultWeight !== null ? String(defaultWeight) : 'Weight'
            customCol.append(customLabel, customInput)

            const removeCol = document.createElement('div')
            removeCol.className = 'col-md-1 d-grid'
            const removeButton = document.createElement('button')
            removeButton.type = 'button'
            removeButton.className = 'btn btn-outline-danger btn-sm'
            removeButton.textContent = 'Remove'
            removeCol.appendChild(removeButton)

            const status = document.createElement('div')
            status.className = 'form-text mt-2'
            status.textContent = rowStatusText(row)

            controls.append(keyCol, defaultCol, customCol, removeCol)
            rowWrap.append(controls, status)
            rowsContainer.appendChild(rowWrap)

            keySelect.addEventListener('change', () => {
              row.key = String(keySelect.value || '').trim()
              renderRows()
            })
            customInput.addEventListener('input', () => {
              row.weight = String(customInput.value || '').trim()
              syncHiddenInputs()
              status.textContent = rowStatusText(row)
            })
            removeButton.addEventListener('click', () => {
              state = state.filter(entry => entry.id !== row.id)
              renderRows()
            })
          })

          syncHiddenInputs()
          const disableAdd = options.length === 0 || state.length >= options.length
          addButton.disabled = disableAdd
        }

        addButton.addEventListener('click', () => {
          const key = nextAvailableKey()
          if (!key) return
          state.push({ id: nextRowId(), key, weight: '' })
          renderRows()
        })

        const languageSelect = getLanguageSelect()
        if (languageSelect) {
          languageSelect.addEventListener('change', () => {
            renderRows()
          })
        }

        renderRows()
        wrapper.dataset.listenerAdded = 'true'
      })
    }

    function initNumericOnlyInputs (scope) {
      const root = scope || document
      root.querySelectorAll('input[data-numeric-only="true"]').forEach(input => {
        if (input.dataset.numericOnlyBound) return
        input.addEventListener('input', () => {
          const raw = String(input.value || '')
          const cleaned = raw.replace(/\D+/g, '')
          if (raw !== cleaned) {
            input.value = cleaned
          }
        })
        input.addEventListener('blur', () => {
          const raw = String(input.value || '').trim()
          if (raw !== '') return
          const fallback = input.dataset.defaultValue
          if (fallback !== undefined && String(fallback).trim() !== '') {
            input.value = fallback
            input.dispatchEvent(new Event('change', { bubbles: true }))
          }
        })
        input.dataset.numericOnlyBound = 'true'
      })
    }

    function initStylePreviewGrids (scope) {
      const root = scope || document
      root.querySelectorAll('[data-style-preview-grid]').forEach(grid => {
        const selectId = grid.dataset.styleSelect
        if (!selectId) return
        const select = document.getElementById(selectId)
        if (!select) return
        const cards = Array.from(grid.querySelectorAll('.style-preview-card'))
        if (!cards.length) return

        function syncActive () {
          const value = select.value || ''
          cards.forEach(card => {
            const isActive = card.dataset.styleValue === value
            card.classList.toggle('active', isActive)
            card.setAttribute('aria-pressed', isActive ? 'true' : 'false')
          })
        }

        if (!select.dataset.stylePreviewBound) {
          select.addEventListener('change', syncActive)
          select.dataset.stylePreviewBound = 'true'
        }

        cards.forEach(card => {
          if (card.dataset.stylePreviewBound) return
          card.addEventListener('click', () => {
            const targetValue = card.dataset.styleValue
            if (!targetValue || select.disabled) return
            select.value = targetValue
            select.dispatchEvent(new Event('change', { bubbles: true }))
          })
          card.dataset.stylePreviewBound = 'true'
        })

        syncActive()
      })
    }

    function normalizeDependencyHintReasons (reasons) {
      if (!Array.isArray(reasons)) return []
      return reasons
        .map(reason => String(reason || '').trim())
        .filter(Boolean)
    }

    function parseStepOrder (stepKey) {
      const match = String(stepKey || '').match(/^(\d+)-/)
      if (!match) return Number.MAX_SAFE_INTEGER
      const parsed = Number.parseInt(match[1], 10)
      return Number.isFinite(parsed) ? parsed : Number.MAX_SAFE_INTEGER
    }

    function insertStepByOrder (container, stepButton) {
      if (!container || !stepButton) return
      const targetOrder = parseStepOrder(stepButton.dataset.stepKey)
      const siblings = Array.from(container.querySelectorAll('.qs-step-link[data-step-key]')).filter(el => el !== stepButton)
      const nextSibling = siblings.find(el => parseStepOrder(el.dataset.stepKey) > targetOrder)
      if (nextSibling) {
        container.insertBefore(stepButton, nextSibling)
      } else {
        container.appendChild(stepButton)
      }
    }

    function syncDependencyStepGrouping (providerKey, isRequired) {
      const dependencyConfig = dependencyHintConfigs[providerKey]
      if (!dependencyConfig) return
      const requiredList = document.querySelector('.qs-step-group[data-step-group="required"] .qs-step-group-list')
      const optionalList = document.querySelector('.qs-step-group[data-step-group="optional"] .qs-step-group-list')
      if (!requiredList || !optionalList) return

      const stepButton = document.querySelector(`.qs-step-group-list .qs-step-link[data-step-key="${dependencyConfig.stepKey}"]`)
      if (!stepButton) return

      const targetList = isRequired ? requiredList : optionalList
      if (stepButton.parentElement === targetList) return

      insertStepByOrder(targetList, stepButton)
      if (window.QSValidationCallouts && typeof window.QSValidationCallouts.refreshSidebar === 'function') {
        window.QSValidationCallouts.refreshSidebar()
      }
    }

    function applyDependencyRequirementHint (providerKey, reasons, options = {}) {
      const dependencyConfig = dependencyHintConfigs[providerKey]
      if (!dependencyConfig) return

      const normalized = normalizeDependencyHintReasons(reasons)
      const refreshUi = options.refreshUi !== false
      syncDependencyStepGrouping(providerKey, normalized.length > 0)

      if (Array.isArray(window.QS_REQUIRED_KEYS) && Array.isArray(window.QS_OPTIONAL_KEYS)) {
        const shouldRequire = normalized.length > 0
        const required = window.QS_REQUIRED_KEYS.filter(key => key !== dependencyConfig.stepKey)
        const optional = window.QS_OPTIONAL_KEYS.filter(key => key !== dependencyConfig.stepKey)
        if (shouldRequire) {
          required.push(dependencyConfig.stepKey)
        } else {
          optional.push(dependencyConfig.stepKey)
        }
        window.QS_REQUIRED_KEYS = required
        window.QS_OPTIONAL_KEYS = optional
      }
      window[dependencyConfig.windowKey] = normalized

      const hints = document.querySelectorAll(`[data-qs-dependency-hint="${providerKey}"]`)
      hints.forEach((hint) => {
        const lines = hint.querySelector('[data-qs-dependency-lines]')
        if (!lines) return

        lines.replaceChildren()
        if (!normalized.length) {
          hint.classList.add('d-none')
          return
        }

        hint.classList.remove('d-none')
        const visibleCount = 2
        normalized.slice(0, visibleCount).forEach((reason) => {
          const row = document.createElement('div')
          row.className = 'qs-dependency-hint-line'
          row.textContent = reason
          lines.appendChild(row)
        })

        if (normalized.length > visibleCount) {
          const more = document.createElement('div')
          more.className = 'qs-dependency-hint-line'
          more.textContent = `+${normalized.length - visibleCount} more...`
          lines.appendChild(more)
        }
      })

      if (refreshUi) {
        if (window.QSValidationCallouts && typeof window.QSValidationCallouts.refresh === 'function') {
          window.QSValidationCallouts.refresh()
        }
        if (window.QSWorkspaceStatus && typeof window.QSWorkspaceStatus.recalculateFromSidebar === 'function') {
          window.QSWorkspaceStatus.recalculateFromSidebar()
        }
      }
    }

    function requestDependencyRequirementHintsNow () {
      const card = libraryContainer ? libraryContainer.firstElementChild : null
      if (!card || !activeLibraryId) return Promise.resolve()

      const payload = {
        source_library_id: activeLibraryId,
        source_payload: buildPayloadFromCard(card)
      }
      const currentToken = ++dependencyHintRequestToken
      const requests = Object.entries(dependencyHintConfigs).map(([providerKey, config]) => {
        return fetch(config.endpoint, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
          .then(res => {
            if (!res.ok) throw new Error(`${providerKey} hint request failed: ${res.status}`)
            return res.json()
          })
          .then(data => ({ providerKey, reasons: data && data.success ? data.reasons : [] }))
          .catch(() => ({ providerKey, reasons: [] }))
      })

      return Promise.all(requests).then((results) => {
        if (currentToken !== dependencyHintRequestToken) return
        results.forEach(({ providerKey, reasons }) => {
          applyDependencyRequirementHint(providerKey, reasons, { refreshUi: false })
        })
        if (window.QSValidationCallouts && typeof window.QSValidationCallouts.refresh === 'function') {
          window.QSValidationCallouts.refresh()
        }
        if (window.QSWorkspaceStatus && typeof window.QSWorkspaceStatus.recalculateFromSidebar === 'function') {
          window.QSWorkspaceStatus.recalculateFromSidebar()
        }
      })
    }

    function scheduleDependencyRequirementHintRefresh (delayMs = 220) {
      if (dependencyHintRefreshTimer) {
        clearTimeout(dependencyHintRefreshTimer)
        dependencyHintRefreshTimer = null
      }
      dependencyHintRefreshTimer = setTimeout(() => {
        dependencyHintRefreshTimer = null
        requestDependencyRequirementHintsNow()
      }, Math.max(0, Number(delayMs) || 0))
    }

    function bindDependencyRequirementHintLiveRefresh (card) {
      if (!card || card.dataset.dependencyHintWatcherBound === 'true') return

      const shouldTrack = (name) => {
        const fieldName = String(name || '')
        if (!fieldName) return false
        return /-library$|-collection_|-template_collection_|-attribute_|-overlay_|-template_overlay_/i.test(fieldName)
      }

      const onFieldInteraction = (event) => {
        const target = event && event.target
        if (!target || !shouldTrack(target.name)) return
        scheduleDependencyRequirementHintRefresh(160)
      }

      card.addEventListener('input', onFieldInteraction)
      card.addEventListener('change', onFieldInteraction)
      card.dataset.dependencyHintWatcherBound = 'true'
    }

    function initRelativeYearInputs (scope) {
      const root = scope || document
      root.querySelectorAll('[data-relative-year]').forEach(wrapper => {
        if (wrapper.dataset.listenerAdded) return
        const hiddenId = wrapper.dataset.hiddenInput
        const hidden = hiddenId ? document.getElementById(hiddenId) : wrapper.querySelector('input[type="hidden"]')
        const modeSelect = wrapper.querySelector('[data-relative-year-mode]')
        const valueInput = wrapper.querySelector('[data-relative-year-value]')
        const minYear = parseInt(wrapper.dataset.minYear || '1', 10) || 1
        const defaultValue = String(wrapper.dataset.defaultValue || '').trim()

        if (!hidden || !modeSelect || !valueInput) {
          console.warn('[relative-year missing]', { hiddenId, hasHidden: !!hidden, hasMode: !!modeSelect, hasValue: !!valueInput })
          return
        }

        const options = Array.from(modeSelect.options).map(option => {
          let kind = option.dataset.kind || ''
          if (!kind) {
            if (option.value === 'year') {
              kind = 'year'
            } else if (option.value.startsWith('relative_')) {
              kind = 'relative'
            } else {
              kind = 'fixed'
            }
          }
          let token = option.dataset.token || ''
          if (!token && kind === 'fixed') {
            token = option.value
          }
          let prefix = option.dataset.prefix || ''
          if (!prefix && kind === 'relative') {
            const suffix = option.value.replace(/^relative_/, '')
            if (suffix === 'first') {
              prefix = 'first+'
            } else if (suffix === 'latest') {
              prefix = 'latest-'
            } else if (suffix) {
              prefix = `${suffix}-`
            }
          }
          return {
            value: option.value,
            kind,
            token,
            prefix
          }
        })
        const yearOption = options.find(opt => opt.kind === 'year')

        function parseValue (raw) {
          const value = String(raw || '').trim()
          const lowered = value.toLowerCase()
          if (!value) return { valid: false }
          for (const opt of options) {
            if (opt.kind !== 'fixed') continue
            if (String(opt.token || '').toLowerCase() === lowered) {
              return { valid: true, mode: opt.value, number: '' }
            }
          }
          for (const opt of options) {
            if (opt.kind !== 'relative') continue
            const prefix = String(opt.prefix || '').toLowerCase()
            if (!prefix || !lowered.startsWith(prefix)) continue
            const remainder = lowered.slice(prefix.length)
            if (/^\d+$/.test(remainder)) {
              return { valid: true, mode: opt.value, number: remainder }
            }
          }
          if (yearOption && /^\d+$/.test(lowered)) {
            return { valid: true, mode: yearOption.value, number: lowered }
          }
          return { valid: false }
        }

        function resolveFallback () {
          const fixed = options.find(opt => opt.kind === 'fixed')
          if (fixed) return { mode: fixed.value, number: '' }
          const relative = options.find(opt => opt.kind === 'relative')
          if (relative) return { mode: relative.value, number: '1' }
          if (yearOption) return { mode: yearOption.value, number: String(minYear) }
          const first = options[0]
          return { mode: first ? first.value : '', number: '' }
        }

        function resolveInitial () {
          const current = parseValue(hidden.value)
          if (current.valid) return current
          const fallback = parseValue(defaultValue)
          if (fallback.valid) return fallback
          return resolveFallback()
        }

        function getActiveOption (mode) {
          return options.find(opt => opt.value === mode) || null
        }

        function applyModeUI (mode) {
          const active = getActiveOption(mode)
          const kind = active ? active.kind : 'fixed'
          const isFixed = kind === 'fixed'
          valueInput.classList.toggle('d-none', isFixed)
          if (kind === 'year') {
            valueInput.placeholder = 'Year'
            valueInput.min = String(minYear)
          } else if (kind === 'relative') {
            valueInput.placeholder = 'Offset'
            valueInput.min = '1'
          } else {
            valueInput.placeholder = ''
            valueInput.min = '1'
          }
        }

        function updateHidden () {
          const mode = modeSelect.value
          const rawNum = parseInt(valueInput.value || '', 10)
          let nextValue = ''
          const active = getActiveOption(mode)
          const kind = active ? active.kind : 'fixed'

          if (kind === 'year') {
            let year = Number.isFinite(rawNum) ? rawNum : minYear
            if (year < minYear) year = minYear
            valueInput.value = String(year)
            nextValue = String(year)
          } else if (kind === 'relative') {
            let offset = Number.isFinite(rawNum) ? rawNum : 1
            if (offset < 1) offset = 1
            valueInput.value = String(offset)
            const prefix = active ? String(active.prefix || '') : ''
            nextValue = `${prefix}${offset}`
          } else if (kind === 'fixed') {
            valueInput.value = ''
            nextValue = active ? String(active.token || mode) : mode
          } else {
            nextValue = defaultValue || (yearOption ? String(minYear) : '')
          }

          hidden.value = nextValue
          applyModeUI(mode)
        }

        const initial = resolveInitial()
        modeSelect.value = initial.mode
        valueInput.value = initial.number
        updateHidden()

        modeSelect.addEventListener('change', () => updateHidden())
        valueInput.addEventListener('input', () => updateHidden())
        valueInput.addEventListener('blur', () => updateHidden())

        wrapper.dataset.listenerAdded = 'true'
      })
    }

    function initScheduleBuilders (scope) {
      const root = scope || document
      root.querySelectorAll('[data-schedule-builder]').forEach(builder => {
        if (builder.dataset.listenerAdded) return
        const hiddenId = builder.dataset.hiddenInput
        const hidden = hiddenId ? document.getElementById(hiddenId) : builder.querySelector('input[type="hidden"]')
        const modeSelect = builder.querySelector('[data-schedule-mode-select]')
        const preview = builder.querySelector('[data-schedule-preview]')
        const rawInput = builder.querySelector('[data-schedule-raw]')
        const modeSections = Array.from(builder.querySelectorAll('[data-schedule-mode]'))
        const rangeStart = builder.querySelector('[data-schedule-range-start]')
        const rangeEnd = builder.querySelector('[data-schedule-range-end]')
        const weeklyDays = Array.from(builder.querySelectorAll('[data-schedule-week-day]'))
        const monthlyDay = builder.querySelector('[data-schedule-month-day]')
        const yearlyInput = builder.querySelector('[data-schedule-yearly]')
        const dateInput = builder.querySelector('[data-schedule-date]')
        const hourStart = builder.querySelector('[data-schedule-hour-start]')
        const hourEnd = builder.querySelector('[data-schedule-hour-end]')
        const defaultValue = String(builder.dataset.defaultValue || '').trim()

        if (!hidden || !modeSelect) return

        function formatMonthDay (dateValue) {
          if (!dateValue || typeof dateValue !== 'string') return ''
          const parts = dateValue.split('-')
          if (parts.length < 3) return ''
          return `${parts[1]}/${parts[2]}`
        }

        function formatDateValue (dateValue) {
          if (!dateValue || typeof dateValue !== 'string') return ''
          const parts = dateValue.split('-')
          if (parts.length < 3) return ''
          return `${parts[1]}/${parts[2]}/${parts[0]}`
        }

        function setMonthDayInput (input, monthDay) {
          if (!input) return
          const md = String(monthDay || '').trim()
          const match = md.match(/^(\d{1,2})\/(\d{1,2})$/)
          if (!match) return
          const month = match[1].padStart(2, '0')
          const day = match[2].padStart(2, '0')
          input.value = `2000-${month}-${day}`
        }

        function setDateInput (input, dateValue) {
          if (!input) return
          const raw = String(dateValue || '').trim()
          const match = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/)
          if (!match) return
          const month = match[1].padStart(2, '0')
          const day = match[2].padStart(2, '0')
          input.value = `${match[3]}-${month}-${day}`
        }

        function parseSchedule (rawValue) {
          const raw = String(rawValue || '').trim()
          if (!raw) return { mode: 'range', raw: '' }
          const lower = raw.toLowerCase()
          if (['daily', 'never', 'non_existing'].includes(lower)) {
            return { mode: lower, raw }
          }
          if (lower.startsWith('hourly(') && lower.endsWith(')')) {
            const inner = raw.slice(7, -1).trim()
            const parts = inner.split('-').map(val => val.trim())
            return { mode: 'hourly', hourStart: parts[0] || '', hourEnd: parts[1] || '', raw }
          }
          if (lower.startsWith('weekly(') && lower.endsWith(')')) {
            const inner = raw.slice(7, -1).trim()
            if (inner.includes('|')) {
              return { mode: 'weekly', days: inner.split('|').map(d => d.trim().toLowerCase()).filter(Boolean), raw }
            }
            return { mode: 'weekly', days: [inner.toLowerCase()], raw }
          }
          if (lower.startsWith('monthly(') && lower.endsWith(')')) {
            const inner = raw.slice(8, -1).trim()
            return { mode: 'monthly', day: inner, raw }
          }
          if (lower.startsWith('yearly(') && lower.endsWith(')')) {
            const inner = raw.slice(7, -1).trim()
            return { mode: 'yearly', monthDay: inner, raw }
          }
          if (lower.startsWith('date(') && lower.endsWith(')')) {
            const inner = raw.slice(5, -1).trim()
            return { mode: 'date', date: inner, raw }
          }
          if (lower.startsWith('range(') && lower.endsWith(')')) {
            const inner = raw.slice(6, -1).trim()
            if (inner.includes('|')) {
              return { mode: 'custom', raw }
            }
            const parts = inner.split('-').map(val => val.trim())
            return { mode: 'range', start: parts[0] || '', end: parts[1] || '', raw }
          }
          if (lower.startsWith('all[')) {
            return { mode: 'custom', raw }
          }
          return { mode: 'custom', raw }
        }

        function setMode (mode) {
          modeSelect.value = mode
          modeSections.forEach(section => {
            const active = section.dataset.scheduleMode === mode
            section.classList.toggle('is-active', active)
          })
        }

        function buildValueFromInputs (mode) {
          if (mode === 'range') {
            const start = formatMonthDay(rangeStart?.value)
            const end = formatMonthDay(rangeEnd?.value)
            if (start && end) return `range(${start}-${end})`
          }
          if (mode === 'weekly') {
            const selected = weeklyDays.filter(day => day.checked).map(day => day.value)
            if (selected.length) return `weekly(${selected.join('|')})`
          }
          if (mode === 'monthly') {
            const day = String(monthlyDay?.value || '').trim()
            if (day) return `monthly(${day})`
          }
          if (mode === 'yearly') {
            const md = formatMonthDay(yearlyInput?.value)
            if (md) return `yearly(${md})`
          }
          if (mode === 'date') {
            const dateVal = formatDateValue(dateInput?.value)
            if (dateVal) return `date(${dateVal})`
          }
          if (mode === 'hourly') {
            const start = String(hourStart?.value || '').trim()
            const end = String(hourEnd?.value || '').trim()
            if (start && end) return `hourly(${start}-${end})`
            if (start) return `hourly(${start})`
          }
          if (mode === 'daily') return 'daily'
          if (mode === 'never') return 'never'
          if (mode === 'non_existing') return 'non_existing'
          if (mode === 'custom') {
            return String(rawInput?.value || '').trim()
          }
          return ''
        }

        function updatePreview (value) {
          if (preview) preview.textContent = value || ''
        }

        function updateFromBuilder () {
          const mode = modeSelect.value
          setMode(mode)
          let nextValue = ''
          if (mode === 'custom') {
            nextValue = String(rawInput?.value || '').trim()
          } else {
            nextValue = buildValueFromInputs(mode) || defaultValue || ''
          }
          hidden.value = nextValue
          updatePreview(nextValue)
          if (rawInput && mode !== 'custom') {
            rawInput.value = nextValue
          }
        }

        function applyParsed (parsed) {
          const mode = parsed.mode || 'custom'
          setMode(mode)
          if (mode === 'range') {
            setMonthDayInput(rangeStart, parsed.start)
            setMonthDayInput(rangeEnd, parsed.end)
          } else if (mode === 'weekly') {
            const selected = new Set((parsed.days || []).map(day => day.toLowerCase()))
            weeklyDays.forEach(day => {
              day.checked = selected.has(day.value)
            })
          } else if (mode === 'monthly') {
            if (monthlyDay) monthlyDay.value = parsed.day || ''
          } else if (mode === 'yearly') {
            setMonthDayInput(yearlyInput, parsed.monthDay)
          } else if (mode === 'date') {
            setDateInput(dateInput, parsed.date)
          } else if (mode === 'hourly') {
            if (hourStart) hourStart.value = parsed.hourStart || ''
            if (hourEnd) hourEnd.value = parsed.hourEnd || ''
          }
          if (rawInput) rawInput.value = parsed.raw || ''
          updatePreview(parsed.raw || '')
        }

        const initialRaw = String(hidden.value || defaultValue || '').trim()
        const parsed = parseSchedule(initialRaw)
        applyParsed(parsed)
        updateFromBuilder()

        modeSelect.addEventListener('change', () => updateFromBuilder())
        if (rangeStart) rangeStart.addEventListener('change', () => updateFromBuilder())
        if (rangeEnd) rangeEnd.addEventListener('change', () => updateFromBuilder())
        weeklyDays.forEach(day => {
          day.addEventListener('change', () => updateFromBuilder())
        })
        if (monthlyDay) monthlyDay.addEventListener('input', () => updateFromBuilder())
        if (yearlyInput) yearlyInput.addEventListener('change', () => updateFromBuilder())
        if (dateInput) dateInput.addEventListener('change', () => updateFromBuilder())
        if (hourStart) hourStart.addEventListener('input', () => updateFromBuilder())
        if (hourEnd) hourEnd.addEventListener('input', () => updateFromBuilder())

        if (rawInput) {
          rawInput.addEventListener('change', () => {
            const raw = String(rawInput.value || '').trim()
            const parsedRaw = parseSchedule(raw)
            applyParsed(parsedRaw)
            if (parsedRaw.mode === 'custom') {
              hidden.value = raw
              updatePreview(raw)
            } else {
              updateFromBuilder()
            }
          })
        }

        builder.dataset.listenerAdded = 'true'
      })
    }

    const templateStringListPresetConfigs = {
      generic_text: {
        duplicateInsensitive: false,
        normalize: value => value,
        validate: value => {
          if (!value) return { valid: false, message: 'Enter a value before adding it.' }
          return { valid: true }
        }
      },
      name_like: {
        duplicateInsensitive: true,
        normalize: value => value.replace(/\s+/g, ' '),
        validate: value => {
          const normalized = String(value || '').trim()
          if (!normalized) return { valid: false, message: 'Enter a text value before adding it.' }
          try {
            if (!/[\p{L}\p{N}]/u.test(normalized)) {
              return { valid: false, message: 'Enter a text value with letters or numbers.' }
            }
            if (!/^[\p{L}\p{N} .,&'’:+\-/()!]+$/u.test(normalized)) {
              return { valid: false, message: 'Use letters, numbers, spaces, or common punctuation only.' }
            }
          } catch (_error) {
            if (!/[A-Za-z0-9]/.test(normalized)) {
              return { valid: false, message: 'Enter a text value with letters or numbers.' }
            }
            if (!/^[A-Za-z0-9 .,&':+\-/()!]+$/.test(normalized)) {
              return { valid: false, message: 'Use letters, numbers, spaces, or common punctuation only.' }
            }
          }
          return { valid: true }
        }
      },
      tmdb_collection_id: {
        duplicateInsensitive: true,
        normalize: value => value,
        lookupService: 'tmdb',
        validate: value => /^\d+$/.test(value)
          ? { valid: true }
          : { valid: false, message: 'Enter a numeric TMDb collection ID like 131292.' }
      },
      year: {
        duplicateInsensitive: true,
        normalize: value => value,
        validate: value => /^\d{4}$/.test(value)
          ? { valid: true }
          : { valid: false, message: 'Enter a 4-digit year like 2022.' }
      },
      decade: {
        duplicateInsensitive: true,
        normalize: value => value,
        validate: value => /^\d{3,4}0$/.test(value)
          ? { valid: true }
          : { valid: false, message: 'Enter a decade key ending in 0 like 2020.' }
      },
      language_code: {
        duplicateInsensitive: true,
        normalize: value => value.toLowerCase(),
        suggestions: [
          'en', 'fr', 'es', 'de', 'it', 'pt', 'ja', 'ko', 'zh', 'ru', 'ar', 'hi',
          'fil', 'myn', 'rom', 'tai'
        ],
        validate: value => /^[a-z]{2,3}$/.test(value)
          ? { valid: true }
          : { valid: false, message: 'Enter a 2 or 3 letter language code like fr or fil.' }
      },
      aspect_key: {
        duplicateInsensitive: true,
        normalize: value => value,
        suggestions: ['1.33', '1.65', '1.66', '1.78', '1.85', '2.2', '2.35', '2.77'],
        allowedValues: new Set(['1.33', '1.65', '1.66', '1.78', '1.85', '2.2', '2.35', '2.77']),
        validate: value => templateStringListPresetConfigs.aspect_key.allowedValues.has(value)
          ? { valid: true }
          : { valid: false, message: 'Enter a supported aspect ratio key like 1.78 or 2.35.' }
      },
      resolution_key: {
        duplicateInsensitive: true,
        normalize: value => value.toLowerCase(),
        suggestions: ['4k', '1080', '720', '480', '8k', '2k', '576', 'sd'],
        allowedValues: new Set(['4k', '1080', '720', '480', '8k', '2k', '144', '240', '360', '576', 'sd']),
        validate: value => templateStringListPresetConfigs.resolution_key.allowedValues.has(value)
          ? { valid: true }
          : { valid: false, message: 'Enter a supported resolution key like 4k, 1080, 720, 480, or sd.' }
      },
      streaming_key: {
        duplicateInsensitive: true,
        normalize: value => value.toLowerCase(),
        suggestions: ['netflix', 'disney', 'amazon', 'hulu', 'hbomax', 'paramount', 'peacock'],
        allowedValues: new Set(['channel4', 'appletv', 'bet', 'crave', 'crunchyroll', 'discovery', 'disney', 'itvx', 'hbomax', 'hayu', 'hulu', 'movistar', 'atresplayer', 'netflix', 'now', 'paramount', 'peacock', 'amazon', 'amc', 'filmin', 'youtube', 'tubi']),
        validate: value => templateStringListPresetConfigs.streaming_key.allowedValues.has(value)
          ? { valid: true }
          : { valid: false, message: 'Enter a supported streaming service key like netflix, disney, or amazon.' }
      },
      universe_key: {
        duplicateInsensitive: true,
        normalize: value => value.toLowerCase(),
        suggestions: ['mcu', 'star', 'trek', 'wizard', 'fast'],
        allowedValues: new Set(['avp', 'arrow', 'askew', 'conjuring', 'dca', 'dcu', 'fast', 'marvel', 'mcu', 'middle', 'rocky', 'trek', 'star', 'mummy', 'wizard', 'xmen']),
        validate: value => templateStringListPresetConfigs.universe_key.allowedValues.has(value)
          ? { valid: true }
          : { valid: false, message: 'Enter a supported universe key like mcu, star, trek, or wizard.' }
      },
      based_key: {
        duplicateInsensitive: true,
        normalize: value => value.toLowerCase(),
        suggestions: ['books', 'comics', 'true_story', 'video_games'],
        allowedValues: new Set(['books', 'comics', 'true_story', 'video_games']),
        validate: value => templateStringListPresetConfigs.based_key.allowedValues.has(value)
          ? { valid: true }
          : { valid: false, message: 'Enter a supported media outlet key like books or video_games.' }
      },
      seasonal_key: {
        duplicateInsensitive: true,
        normalize: value => value.toLowerCase(),
        suggestions: ['christmas', 'halloween', 'valentine', 'years', 'women'],
        allowedValues: new Set(['years', 'valentine', 'patrick', 'easter', 'mother', 'memorial', 'father', 'independence', 'labor', 'halloween', 'veteran', 'thanksgiving', 'christmas', 'aapi', 'disabilities', 'black_history', 'lgbtq', 'latinx', 'women']),
        validate: value => templateStringListPresetConfigs.seasonal_key.allowedValues.has(value)
          ? { valid: true }
          : { valid: false, message: 'Enter a supported seasonal key like halloween, christmas, or women.' }
      },
      content_rating: {
        duplicateInsensitive: true,
        normalize: value => value.replace(/\s+/g, ' '),
        validate: value => /^[A-Za-z0-9][A-Za-z0-9 +\-./()]*$/.test(value)
          ? { valid: true }
          : { valid: false, message: 'Enter a content rating like PG-13, TV-14, 15, or M.' }
      }
    }

    function inferTemplateStringListPreset (wrapper, input) {
      const explicitPreset = String(wrapper.dataset.validationPreset || input.dataset.validationPreset || '').trim()
      if (explicitPreset && templateStringListPresetConfigs[explicitPreset]) return explicitPreset

      const placeholder = String(input.getAttribute('placeholder') || '').trim().toLowerCase()
      if (placeholder.includes('tmdb collection id')) return 'tmdb_collection_id'
      if (placeholder.includes('year (e.g. 2022)')) return 'year'
      if (placeholder.includes('decade key')) return 'decade'
      if (placeholder.includes('language code')) return 'language_code'
      if (placeholder.includes('aspect ratio key')) return 'aspect_key'
      if (placeholder.includes('resolution key')) return 'resolution_key'
      if (placeholder.includes('service key')) return 'streaming_key'
      if (placeholder.includes('universe key')) return 'universe_key'
      if (placeholder.includes('media outlet key')) return 'based_key'
      if (placeholder.includes('seasonal key')) return 'seasonal_key'
      if (placeholder.includes('content rating')) return 'content_rating'
      if (
        placeholder.includes('genre name') ||
        placeholder.includes('person name') ||
        placeholder.includes('studio name') ||
        placeholder.includes('network name') ||
        placeholder.includes('country name') ||
        placeholder.includes('region name') ||
        placeholder.includes('continent name')
      ) {
        return 'name_like'
      }
      return 'generic_text'
    }

    function ensureTemplateStringListDatalist (wrapper, input, presetConfig, presetName) {
      if (!wrapper || !input || !presetConfig || !Array.isArray(presetConfig.suggestions) || !presetConfig.suggestions.length) return
      if (presetConfig.suggestions.length > 50) return
      const existingListId = input.getAttribute('list')
      if (existingListId && document.getElementById(existingListId)) return
      const hiddenId = String(wrapper.dataset.hiddenInput || input.id || 'template-string-list').replace(/[^A-Za-z0-9_-]+/g, '_')
      const datalistId = `${hiddenId}_${presetName}_options`
      let datalist = document.getElementById(datalistId)
      if (!datalist) {
        datalist = document.createElement('datalist')
        datalist.id = datalistId
        presetConfig.suggestions.forEach(value => {
          const option = document.createElement('option')
          option.value = value
          datalist.appendChild(option)
        })
        wrapper.appendChild(datalist)
      }
      input.setAttribute('list', datalistId)
    }

    function setupTemplateStringListHandlers (scope) {
      const templateStringLookupCache = window.__qsTemplateStringLookupCache || new Map()
      window.__qsTemplateStringLookupCache = templateStringLookupCache

      function getServiceValidationState (serviceName) {
        const el = document.getElementById(`qs-validate-${serviceName}`)
        return String(el?.value || '').trim().toLowerCase() === 'true'
      }

      async function lookupTemplateStringValue (presetName, value) {
        const cacheKey = `${presetName}:${value}`
        if (templateStringLookupCache.has(cacheKey)) {
          return templateStringLookupCache.get(cacheKey)
        }
        const request = fetch('/lookup_template_string_value', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ preset: presetName, value })
        })
          .then(async (response) => {
            const data = await response.json().catch(() => ({}))
            if (!response.ok) {
              return {
                valid: false,
                verified: false,
                message: data.error || data.message || `Lookup failed (${response.status})`
              }
            }
            return data
          })
          .catch(() => ({
            valid: false,
            verified: false,
            message: 'Lookup unavailable right now.'
          }))
        templateStringLookupCache.set(cacheKey, request)
        return request
      }

      const root = scope || document
      root.querySelectorAll('[data-template-string-list]').forEach(wrapper => {
        if (wrapper.dataset.listenerAdded) return
        const hiddenId = wrapper.dataset.hiddenInput
        const hidden = hiddenId ? document.getElementById(hiddenId) : wrapper.querySelector('input[type="hidden"]')
        const input = wrapper.querySelector('input[type="text"]')
        const addBtn = wrapper.querySelector('[data-template-string-add]')
        const list = wrapper.querySelector('[data-template-string-items]')
        const feedback = wrapper.querySelector('[data-template-string-feedback]')
        const templateVariableKey = String(wrapper.dataset.templateVariableKey || '').trim()
        const mutuallyExclusiveWith = String(wrapper.dataset.mutuallyExclusiveWith || '').trim()

        if (!hidden || !input || !addBtn || !list) return

        const presetName = inferTemplateStringListPreset(wrapper, input)
        const presetConfig = templateStringListPresetConfigs[presetName] || templateStringListPresetConfigs.generic_text
        ensureTemplateStringListDatalist(wrapper, input, presetConfig, presetName)

        function parseStoredStringList (rawValue) {
          const raw = String(rawValue || '').trim()
          if (!raw) return []
          try {
            const parsed = JSON.parse(raw)
            if (Array.isArray(parsed)) {
              return parsed.map(item => String(item).trim()).filter(Boolean)
            }
          } catch (e) {
            // fall through to treat as single value
          }
          return [raw]
        }

        function getCounterpartHiddenId () {
          if (!hiddenId || !templateVariableKey || !mutuallyExclusiveWith) return ''
          const suffix = `_${templateVariableKey}`
          if (!hiddenId.endsWith(suffix)) return ''
          return `${hiddenId.slice(0, -suffix.length)}_${mutuallyExclusiveWith}`
        }

        function getCounterpartWrapper () {
          const counterpartHiddenId = getCounterpartHiddenId()
          if (!counterpartHiddenId) return null
          return document.querySelector(`[data-template-string-list][data-hidden-input="${counterpartHiddenId}"]`)
        }

        function getCounterpartValues () {
          const counterpartWrapper = getCounterpartWrapper()
          if (counterpartWrapper && typeof counterpartWrapper.__qsTemplateStringListGetValues === 'function') {
            return counterpartWrapper.__qsTemplateStringListGetValues()
          }
          const counterpartHiddenId = getCounterpartHiddenId()
          const counterpartHidden = counterpartHiddenId ? document.getElementById(counterpartHiddenId) : null
          return parseStoredStringList(counterpartHidden?.value)
        }

        function setLookupState (target, state) {
          if (!target) return
          target.textContent = state?.message || ''
          target.className = 'small mt-1'
          if (!state?.message) {
            target.classList.add('d-none')
            return
          }
          target.classList.remove('d-none')
          if (state.valid && state.verified) {
            target.classList.add('text-success')
          } else if (state.verified) {
            target.classList.add('text-danger')
          } else {
            target.classList.add('text-warning')
          }
        }

        function setFeedback (message, persistent = false, level = 'error') {
          const isError = Boolean(message) && level === 'error'
          if (feedback) {
            feedback.textContent = message || ''
            feedback.classList.toggle('d-none', !message)
            feedback.classList.toggle('d-block', Boolean(message))
            feedback.classList.toggle('invalid-feedback', isError)
            feedback.classList.toggle('text-warning', Boolean(message) && level === 'warning')
            feedback.classList.toggle('small', Boolean(message) && level === 'warning')
          }
          input.classList.toggle('is-invalid', isError)
          input.setCustomValidity(persistent && isError && message ? message : '')
        }

        function clearTransientFeedback () {
          if (input.validationMessage) return
          setFeedback('')
        }

        function parseValues () {
          return parseStoredStringList(hidden.value)
        }

        function validateValue (rawValue) {
          const normalizedRaw = String(rawValue || '').trim()
          const normalized = presetConfig.normalize ? presetConfig.normalize(normalizedRaw) : normalizedRaw
          const result = presetConfig.validate ? presetConfig.validate(normalized) : { valid: Boolean(normalized) }
          return {
            value: normalized,
            valid: Boolean(result.valid),
            message: result.message || 'Enter a valid value.'
          }
        }

        function duplicateKeyForValue (value) {
          return presetConfig.duplicateInsensitive ? String(value || '').toLowerCase() : String(value || '')
        }

        function analyzeValues (values) {
          const seen = new Set()
          const analyzed = []
          values.forEach(rawValue => {
            const checked = validateValue(rawValue)
            if (!checked.value) return
            const duplicateKey = duplicateKeyForValue(checked.value)
            if (seen.has(duplicateKey)) return
            seen.add(duplicateKey)
            analyzed.push(checked)
          })
          return analyzed
        }

        function renderList (items) {
          list.replaceChildren()
          items.forEach((item, index) => {
            const li = document.createElement('li')
            li.className = 'list-group-item d-flex justify-content-between align-items-center'
            if (!item.valid) li.classList.add('list-group-item-danger')

            const textWrap = document.createElement('div')
            textWrap.className = 'd-flex flex-column'

            const titleRow = document.createElement('div')
            titleRow.className = 'd-flex align-items-center gap-2'

            const textSpan = document.createElement('span')
            textSpan.textContent = item.value
            titleRow.appendChild(textSpan)

            if (!item.valid) {
              const badge = document.createElement('span')
              badge.className = 'badge text-bg-danger'
              badge.textContent = 'Invalid'
              badge.title = item.message
              titleRow.appendChild(badge)
            }

            textWrap.appendChild(titleRow)

            const lookupMeta = document.createElement('div')
            lookupMeta.className = 'small mt-1 d-none'
            textWrap.appendChild(lookupMeta)

            const button = document.createElement('button')
            button.type = 'button'
            button.className = 'btn btn-sm btn-danger'
            button.setAttribute('aria-label', 'Remove')
            const icon = document.createElement('i')
            icon.className = 'bi bi-x-lg'
            button.appendChild(icon)
            li.append(textWrap, button)
            list.appendChild(li)

            button.addEventListener('click', () => {
              const updated = items
                .filter((_, itemIndex) => itemIndex !== index)
                .map(entry => entry.value)
              syncState(updated)
            })

            if (item.valid && presetConfig.lookupService === 'tmdb') {
              if (!getServiceValidationState('tmdb')) {
                setLookupState(lookupMeta, {
                  valid: false,
                  verified: false,
                  message: 'TMDb not validated, so the collection title could not be checked.'
                })
              } else {
                setLookupState(lookupMeta, {
                  valid: false,
                  verified: false,
                  message: 'Checking TMDb collection title...'
                })
                lookupTemplateStringValue(presetName, item.value).then(result => {
                  if (!lookupMeta.isConnected) return
                  if (result.valid && result.verified && result.label) {
                    setLookupState(lookupMeta, {
                      valid: true,
                      verified: true,
                      message: `TMDb: ${result.label}`
                    })
                    return
                  }
                  setLookupState(lookupMeta, {
                    valid: Boolean(result.valid),
                    verified: Boolean(result.verified),
                    message: result.message || 'TMDb lookup failed.'
                  })
                })
              }
            }
          })
        }

        function syncState (values, transientMessage = '', options = {}) {
          const analyzed = analyzeValues(values)
          const normalizedValues = analyzed.map(item => item.value)
          let feedbackMessage = transientMessage || ''
          let feedbackLevel = 'error'

          if (!options.skipMutualExclusion && mutuallyExclusiveWith && normalizedValues.length) {
            const counterpartValues = getCounterpartValues()
            if (counterpartValues.length) {
              if (!feedbackMessage) {
                feedbackMessage = 'Include and Exclude are both set. Kometa code allows this, but the wiki says not to combine them.'
                feedbackLevel = 'warning'
              }
            }
          }

          hidden.value = JSON.stringify(normalizedValues)
          renderList(analyzed)

          const invalidItems = analyzed.filter(item => !item.valid)
          if (invalidItems.length) {
            const message = invalidItems.length === 1
              ? `${invalidItems[0].message} Remove or fix the invalid entry.`
              : `${invalidItems[0].message} Remove or fix the invalid entries.`
            setFeedback(message, true)
            return analyzed
          }

          setFeedback(feedbackMessage || '', false, feedbackLevel)
          return analyzed
        }

        function addValue () {
          const checked = validateValue(input.value)
          if (!checked.value) {
            setFeedback('Enter a value before adding it.', false)
            return
          }
          if (!checked.valid) {
            setFeedback(checked.message, false)
            return
          }
          const current = analyzeValues(parseValues())
          if (current.some(item => duplicateKeyForValue(item.value) === duplicateKeyForValue(checked.value))) {
            setFeedback('That value is already in the list.', false)
            return
          }
          current.push(checked)
          syncState(current.map(item => item.value))
          input.value = ''
          clearTransientFeedback()
        }

        wrapper.__qsTemplateStringListGetValues = () => parseValues()
        wrapper.__qsTemplateStringListSync = syncState
        syncState(parseValues())

        addBtn.addEventListener('click', addValue)
        input.addEventListener('input', clearTransientFeedback)
        input.addEventListener('keydown', (event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            addValue()
          }
        })

        wrapper.dataset.listenerAdded = 'true'
      })
    }

    const fontPreviewCache = new Map()

    function loadFontPreview (file) {
      if (!file) return Promise.resolve(null)
      if (fontPreviewCache.has(file)) return fontPreviewCache.get(file)
      if (typeof FontFace === 'undefined') {
        fontPreviewCache.set(file, Promise.resolve(null))
        return fontPreviewCache.get(file)
      }
      const family = file.replace(/\.[^.]+$/, '')
      const face = new FontFace(family, `url(/custom-fonts/${encodeURIComponent(file)})`)
      const promise = face.load()
        .then(loaded => {
          document.fonts.add(loaded)
          return family
        })
        .catch(() => null)
      fontPreviewCache.set(file, promise)
      return promise
    }

    function updateFontPreviewForSelect (select) {
      if (!select) return
      if (typeof updateFontPickerButton === 'function') {
        updateFontPickerButton(select)
      }
      const preview = document.querySelector(`[data-preview-for="${select.id}"]`)
      if (!preview) return
      const value = select.value || select.dataset.default || ''
      const file = value.split(/[\\/]/).pop()
      preview.textContent = file ? 'AaBb123' : 'AaBb123'
      preview.title = file || ''
      if (!file) {
        preview.style.fontFamily = ''
        return
      }
      loadFontPreview(file).then(family => {
        if (family) {
          preview.style.fontFamily = `"${family}", sans-serif`
        }
      })
    }
    window.updateFontPreviewForSelect = updateFontPreviewForSelect

    function updateFontPickerButton (select) {
      if (!select) return
      const button = document.querySelector(`[data-font-picker-target="${select.id}"]`)
      if (!button) return
      const value = select.value || select.dataset.default || ''
      const file = value.split(/[\\/]/).pop()
      button.textContent = file || 'Select font'
      button.title = file || ''
      if (!file) {
        button.style.fontFamily = ''
        return
      }
      loadFontPreview(file).then(family => {
        if (family) {
          button.style.fontFamily = `"${family}", sans-serif`
        }
      })
    }
    window.updateFontPickerButton = updateFontPickerButton

    const fontPickerState = {
      activeSelect: null,
      sampleText: 'AaBb123 Quickstart'
    }

    function getFontPickerModal () {
      const modalEl = document.getElementById('fontPickerModal')
      if (!modalEl || !bootstrap || !bootstrap.Modal) return null
      return bootstrap.Modal.getOrCreateInstance(modalEl)
    }

    function getFontsFromSelect (select) {
      const fonts = []
      const seen = new Set()
      if (!select) return fonts
      select.querySelectorAll('option').forEach(option => {
        const value = option.value || ''
        if (!value || seen.has(value)) return
        fonts.push(value)
        seen.add(value)
      })
      return fonts
    }

    function renderFontPickerGrid (select) {
      const modalEl = document.getElementById('fontPickerModal')
      const grid = document.getElementById('font-picker-grid')
      const status = document.getElementById('font-picker-status')
      const search = document.getElementById('font-picker-search')
      const sampleInput = document.getElementById('font-picker-sample')
      if (!grid || !modalEl) return

      const fonts = getFontsFromSelect(select)
      const query = (search?.value || '').trim().toLowerCase()
      const sampleText = sampleInput ? sampleInput.value : fontPickerState.sampleText
      fontPickerState.sampleText = sampleText

      const cards = []
      fonts.forEach(font => {
        const label = font.split(/[\\/]/).pop()
        cards.push({ font, label })
      })

      const filtered = cards.filter(card => {
        if (!query) return true
        return card.label.toLowerCase().includes(query)
      })

      grid.replaceChildren()
      if (status) {
        status.textContent = `${filtered.length} font${filtered.length === 1 ? '' : 's'}`
      }

      if (!filtered.length) {
        const empty = document.createElement('div')
        empty.className = 'text-muted small'
        empty.textContent = 'No fonts match your search.'
        grid.appendChild(empty)
        return
      }

      const selectedValue = select ? (select.value || '') : ''

      filtered.forEach(card => {
        const button = document.createElement('button')
        button.type = 'button'
        button.className = 'font-picker-card'
        button.dataset.font = card.font
        if ((card.font || '') === selectedValue) {
          button.classList.add('active')
        }
        const title = document.createElement('div')
        title.className = 'font-picker-card-title'
        title.textContent = card.label
        const sample = document.createElement('div')
        sample.className = 'font-picker-card-sample'
        sample.textContent = sampleText || 'AaBb123 Quickstart'

        if (card.font) {
          const file = card.font.split(/[\\/]/).pop()
          loadFontPreview(file).then(family => {
            if (family) {
              sample.style.fontFamily = `"${family}", sans-serif`
            }
          })
        }

        button.appendChild(title)
        button.appendChild(sample)
        button.addEventListener('click', () => {
          if (select) {
            select.value = card.font
            select.dispatchEvent(new Event('change', { bubbles: true }))
            updateFontPickerButton(select)
            updateFontPreviewForSelect(select)
          }
          const modal = getFontPickerModal()
          if (modal) modal.hide()
        })

        grid.appendChild(button)
      })
    }

    function wireFontPickerModal () {
      const modalEl = document.getElementById('fontPickerModal')
      if (!modalEl) return
      const search = document.getElementById('font-picker-search')
      const sampleInput = document.getElementById('font-picker-sample')

      modalEl.addEventListener('show.bs.modal', () => {
        if (sampleInput) {
          sampleInput.value = fontPickerState.sampleText
        }
        renderFontPickerGrid(fontPickerState.activeSelect)
      })

      if (search) {
        search.addEventListener('input', () => renderFontPickerGrid(fontPickerState.activeSelect))
      }
      if (sampleInput) {
        sampleInput.addEventListener('input', () => renderFontPickerGrid(fontPickerState.activeSelect))
      }
    }

    function wireFontPickerButtons (scope) {
      const root = scope || document
      root.querySelectorAll('[data-font-picker-target]').forEach(button => {
        if (button.dataset.fontPickerBound === 'true') return
        button.addEventListener('click', () => {
          const selectId = button.dataset.fontPickerTarget
          const select = selectId ? document.getElementById(selectId) : null
          fontPickerState.activeSelect = select
          const modal = getFontPickerModal()
          if (modal) modal.show()
        })
        button.dataset.fontPickerBound = 'true'
      })
    }

    function wireFontPreviews (scope) {
      const root = scope || document
      root.querySelectorAll('select[data-font-select]').forEach(select => {
        if (select.dataset.fontPreviewBound === 'true') return
        select.addEventListener('change', () => updateFontPreviewForSelect(select))
        updateFontPreviewForSelect(select)
        updateFontPickerButton(select)
        select.dataset.fontPreviewBound = 'true'
      })
    }

    function wireFontUploads (scope) {
      const root = scope || document
      root.querySelectorAll('[data-font-upload]').forEach(card => {
        if (card.dataset.fontUploadBound === 'true') return
        const input = card.querySelector('[data-font-upload-input]')
        const button = card.querySelector('[data-font-upload-button]')
        const status = card.querySelector('[data-font-upload-status]')
        if (!input || !button) return

        const setStatus = (text, isError) => {
          if (!status) return
          status.textContent = text || ''
          status.classList.toggle('text-danger', Boolean(isError))
          status.classList.toggle('text-muted', !isError)
        }

        button.addEventListener('click', async () => {
          const files = input.files ? Array.from(input.files) : []
          if (!files.length) {
            setStatus('Choose one or more .ttf/.otf files to upload.', true)
            return
          }

          const formData = new FormData()
          files.forEach(file => formData.append('fonts', file))
          button.disabled = true
          setStatus('Uploading fonts...', false)

          try {
            const res = await fetch('/upload-fonts', { method: 'POST', body: formData })
            const data = await res.json()
            if (!res.ok || data.status !== 'success') {
              throw new Error(data.message || 'Font upload failed.')
            }
            updateFontSelects(data.fonts || [], root)
            renderFontPickerGrid(fontPickerState.activeSelect)
            input.value = ''
            const saved = Array.isArray(data.saved) ? data.saved.length : 0
            setStatus(`Uploaded ${saved} font(s).`, false)
            if (typeof showToast === 'function') {
              showToast('success', data.message || 'Fonts uploaded.')
            }
            if (Array.isArray(data.errors) && data.errors.length) {
              setStatus(data.errors.join(' '), true)
            }
          } catch (err) {
            setStatus(err.message || 'Font upload failed.', true)
            if (typeof showToast === 'function') {
              showToast('error', err.message || 'Font upload failed.')
            }
          } finally {
            button.disabled = false
          }
        })

        card.dataset.fontUploadBound = 'true'
      })
    }

    function updateConfiguredCounts () {
      if (!libraryPicker || !configuredCountsDisplay) return
      const counts = { movie: 0, show: 0 }
      libraryPicker.querySelectorAll('option[value]').forEach(opt => {
        if (opt.dataset.configured === 'true') {
          const type = opt.dataset.libraryType
          if (type && counts[type] !== undefined) {
            counts[type]++
          }
        }
      })
      const movieLabel = counts.movie === 1 ? 'movie' : 'movies'
      const showLabel = counts.show === 1 ? 'show' : 'shows'
      configuredCountsDisplay.textContent = `Configured: ${counts.movie} ${movieLabel} / ${counts.show} ${showLabel}`
    }

    function refreshPickerLabels () {
      if (!libraryPicker) return
      libraryPicker.querySelectorAll('option[value]').forEach(opt => {
        const base = opt.dataset.label || opt.textContent.replace(/\s+\(configured\)$/, '')
        const configured = opt.dataset.configured === 'true'
        opt.textContent = configured ? `${base} (configured)` : base
      })
      updateConfiguredCounts()
    }

    function wireIncludeToggle (card, libraryId) {
      if (!libraryPicker || !card) return
      const toggle = card.querySelector('.include-library-toggle')
      const playlistToggle = card.querySelector('.playlist-library-toggle')
      const option = libraryPicker.querySelector(`option[value="${libraryId}"]`)
      const targetInputId = toggle?.dataset.targetInput
      const targetInput = targetInputId ? document.getElementById(targetInputId) : null
      const status = card.querySelector('[data-include-status]')
      if (!toggle || !option || toggle.dataset.listenerAdded || !targetInput) return

      function syncStatus () {
        if (!status) return
        const included = toggle.checked
        status.textContent = included ? 'Included in YAML' : 'Excluded from YAML'
        status.classList.toggle('bg-success', included)
        status.classList.toggle('bg-secondary', !included)
        if (playlistToggle) {
          if (!included) {
            playlistToggle.checked = false
          }
          playlistToggle.disabled = !included
          playlistToggle.closest('.form-check')?.classList.toggle('opacity-50', !included)
        }
      }

      toggle.addEventListener('change', () => {
        option.dataset.configured = toggle.checked ? 'true' : 'false'
        targetInput.value = toggle.checked ? toggle.value : ''
        refreshPickerLabels()
        syncStatus()
        if (typeof ValidationHandler !== 'undefined' && ValidationHandler.updateValidationState) {
          ValidationHandler.updateValidationState()
        }
      })
      if (playlistToggle && !playlistToggle.dataset.listenerAdded) {
        playlistToggle.addEventListener('change', () => {
          syncStatus()
          if (typeof ValidationHandler !== 'undefined' && ValidationHandler.updateValidationState) {
            ValidationHandler.updateValidationState()
          }
        })
        playlistToggle.dataset.listenerAdded = 'true'
      }
      syncStatus()
      toggle.dataset.listenerAdded = 'true'
    }

    function hasConfiguredAdvancedValues (card) {
      if (!card) return false
      const fields = card.querySelectorAll('.library-advanced-section [name]')
      return Array.from(fields).some((field) => {
        if (!field || field.disabled) return false
        if (field.type === 'checkbox' || field.type === 'radio') return field.checked
        const value = String(field.value ?? '').trim()
        if (!value) return false
        if (field.name.endsWith('-metadata_files') || field.name.endsWith('-collection_files') || field.name.endsWith('-overlay_files')) {
          return value !== '[]'
        }
        return true
      })
    }

    function setAdvancedVisibility (card, visible) {
      if (!card) return
      card.querySelectorAll('.library-advanced-section').forEach(section => {
        section.classList.toggle('d-none', !visible)
      })
      const toggle = card.querySelector('.library-advanced-toggle')
      if (toggle) {
        toggle.textContent = visible ? 'Hide Advanced' : 'Show Advanced'
        toggle.setAttribute('aria-expanded', visible ? 'true' : 'false')
      }
      card.dataset.advancedVisible = visible ? 'true' : 'false'
    }

    function wireAdvancedToggle (card) {
      if (!card || card.dataset.advancedToggleBound === 'true') return
      const toggle = card.querySelector('.library-advanced-toggle')
      if (!toggle) return

      let persisted = null
      try {
        persisted = window.localStorage ? window.localStorage.getItem(advancedVisibilityStorageKey) : null
      } catch (_error) {}
      const initialVisible = persisted === 'true' || (persisted !== 'false' && hasConfiguredAdvancedValues(card))
      setAdvancedVisibility(card, initialVisible)

      toggle.addEventListener('click', () => {
        const nextVisible = card.dataset.advancedVisible !== 'true'
        setAdvancedVisibility(card, nextVisible)
        try {
          if (window.localStorage) window.localStorage.setItem(advancedVisibilityStorageKey, nextVisible ? 'true' : 'false')
        } catch (_error) {}
      })

      card.dataset.advancedToggleBound = 'true'
    }

    function setLibraryServiceStatus (card, serviceName, kind, message) {
      const statusEl = card ? card.querySelector(`[data-library-service-status="${serviceName}"]`) : null
      if (!statusEl) return
      const text = String(message || '').trim()
      if (!text) {
        statusEl.classList.add('d-none')
        statusEl.textContent = ''
        statusEl.classList.remove('alert-success', 'alert-danger', 'alert-info')
        return
      }
      statusEl.textContent = text
      statusEl.classList.remove('d-none', 'alert-success', 'alert-danger', 'alert-info')
      statusEl.classList.add(kind === 'success' ? 'alert-success' : kind === 'error' ? 'alert-danger' : 'alert-info')
    }

    function getLibraryServiceValidationFields (card, serviceName) {
      if (!card || !serviceName) return {}
      return {
        validatedInput: card.querySelector(`[data-library-service-validated="${serviceName}"]`),
        validatedAtInput: card.querySelector(`[data-library-service-validated-at="${serviceName}"]`),
        button: card.querySelector(`[data-validate-library-service="${serviceName}"]`)
      }
    }

    function isLibraryServiceValidated (card, serviceName) {
      const { validatedInput } = getLibraryServiceValidationFields(card, serviceName)
      return String(validatedInput?.value || '').trim().toLowerCase() === 'true'
    }

    function updateLibraryServiceValidateButton (card, serviceName, state = null) {
      const { button } = getLibraryServiceValidationFields(card, serviceName)
      if (!button) return
      const effectiveState = String(state || button.dataset.validationState || '').trim() || (isLibraryServiceValidated(card, serviceName) ? 'success' : 'idle')
      button.dataset.validationState = effectiveState
      button.classList.remove('btn-success', 'btn-secondary')

      if (effectiveState === 'loading') {
        button.disabled = true
        button.classList.add('btn-secondary')
        button.textContent = `Validating ${serviceName === 'radarr' ? 'Radarr' : 'Sonarr'} Overrides...`
        return
      }

      if (effectiveState === 'success') {
        button.disabled = true
        button.classList.add('btn-secondary')
        button.textContent = 'Validated'
        return
      }

      button.disabled = false
      button.classList.add('btn-success')
      button.textContent = `Validate ${serviceName === 'radarr' ? 'Radarr' : 'Sonarr'} Overrides`
    }

    function setLibraryServiceValidatedState (card, serviceName, isValidated) {
      const { validatedInput, validatedAtInput, button } = getLibraryServiceValidationFields(card, serviceName)
      if (validatedInput) validatedInput.value = isValidated ? 'true' : 'false'
      if (validatedAtInput) validatedAtInput.value = isValidated ? new Date().toISOString() : ''
      if (button) {
        button.dataset.validationState = isValidated ? 'success' : 'idle'
      }
      updateLibraryServiceValidateButton(card, serviceName, isValidated ? 'success' : 'idle')
    }

    function resetLibraryServiceValidatedState (card, serviceName, opts = {}) {
      const clearStatus = opts.clearStatus !== false
      setLibraryServiceValidatedState(card, serviceName, false)
      if (clearStatus) {
        setLibraryServiceStatus(card, serviceName, '', '')
      }
    }

    function libraryServiceOverrideFieldSelector (serviceName) {
      return `[name*="-attribute_${serviceName}_"]`
    }

    function setSecretToggleButtonIcon (button, showPlainText) {
      if (!button) return
      const icon = document.createElement('i')
      icon.className = showPlainText ? 'fas fa-eye-slash' : 'fas fa-eye'
      button.replaceChildren(icon)
    }

    function initSecretVisibilityToggles (scope) {
      const root = scope || document
      root.querySelectorAll('[data-toggle-secret-visibility]').forEach(button => {
        if (button.dataset.secretToggleBound === 'true') return
        const targetId = button.dataset.targetInput
        const input = targetId ? root.querySelector(`#${targetId}`) : null
        if (!input) return

        const syncState = () => {
          const hasValue = String(input.value || '').trim() !== ''
          const forceVisible = button.dataset.secretVisible === 'true'
          const showPlainText = !hasValue || forceVisible
          input.setAttribute('type', showPlainText ? 'text' : 'password')
          setSecretToggleButtonIcon(button, showPlainText)
        }

        button.dataset.secretVisible = 'false'
        syncState()

        button.addEventListener('click', () => {
          const currentType = input.getAttribute('type')
          const nextVisible = currentType === 'password'
          button.dataset.secretVisible = nextVisible ? 'true' : 'false'
          syncState()
        })

        input.addEventListener('input', () => {
          if (String(input.value || '').trim() === '') {
            button.dataset.secretVisible = 'false'
          }
          syncState()
        })

        button.dataset.secretToggleBound = 'true'
      })
    }

    function populateOverrideDatalist (card, listId, items, valueField) {
      const list = card ? card.querySelector(`#${listId}`) : null
      if (!list) return
      list.replaceChildren()
      const normalizedItems = Array.isArray(items) ? items : []
      normalizedItems.forEach(item => {
        const value = item && typeof item === 'object' ? item[valueField] : ''
        if (!value) return
        const option = document.createElement('option')
        option.value = value
        list.appendChild(option)
      })
    }

    function validateLibraryServiceOverrides (button) {
      const serviceName = button?.dataset?.validateLibraryService
      const libraryId = button?.dataset?.libraryId || activeLibraryId
      const card = libraryContainer?.firstElementChild
      if (!button || !serviceName || !libraryId || !card) return

      const payload = buildPayloadFromCard(card)
      updateLibraryServiceValidateButton(card, serviceName, 'loading')
      setLibraryServiceStatus(card, serviceName, 'info', `Validating ${serviceName} overrides...`)

      fetch(`/validate_library_service_overrides/${encodeURIComponent(libraryId)}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(async (res) => {
          const data = await res.json().catch(() => ({}))
          if (!res.ok) {
            const errors = Array.isArray(data.errors) ? data.errors : [data.error || `Validation failed (${res.status})`]
            throw new Error(errors.filter(Boolean).join(' '))
          }
          return data
        })
        .then((data) => {
          if (serviceName === 'radarr') {
            populateOverrideDatalist(card, `${libraryId}-radarr-root-folders`, data.root_folders, 'path')
            populateOverrideDatalist(card, `${libraryId}-radarr-quality-profiles`, data.quality_profiles, 'name')
          } else {
            populateOverrideDatalist(card, `${libraryId}-sonarr-root-folders`, data.root_folders, 'path')
            populateOverrideDatalist(card, `${libraryId}-sonarr-quality-profiles`, data.quality_profiles, 'name')
            populateOverrideDatalist(card, `${libraryId}-sonarr-language-profiles`, data.language_profiles, 'name')
          }
          setAdvancedVisibility(card, true)
          setLibraryServiceValidatedState(card, serviceName, true)
          setLibraryServiceStatus(card, serviceName, 'success', `${serviceName === 'radarr' ? 'Radarr' : 'Sonarr'} overrides validated.`)
        })
        .catch((error) => {
          setAdvancedVisibility(card, true)
          resetLibraryServiceValidatedState(card, serviceName, { clearStatus: false })
          setLibraryServiceStatus(card, serviceName, 'error', error.message || 'Validation failed.')
        })
        .finally(() => {
          if (!isLibraryServiceValidated(card, serviceName)) {
            updateLibraryServiceValidateButton(card, serviceName, 'idle')
          }
        })
    }

    function wireLibraryServiceValidationButtons (card) {
      if (!card || card.dataset.libraryServiceValidationBound === 'true') return
      card.querySelectorAll('[data-validate-library-service]').forEach(button => {
        const serviceName = button.dataset.validateLibraryService
        updateLibraryServiceValidateButton(card, serviceName)
        button.addEventListener('click', () => validateLibraryServiceOverrides(button))
      })
      card.querySelectorAll(`${libraryServiceOverrideFieldSelector('radarr')}, ${libraryServiceOverrideFieldSelector('sonarr')}`).forEach(field => {
        const fieldName = String(field.name || '')
        const serviceName = fieldName.includes('-attribute_sonarr_') ? 'sonarr' : fieldName.includes('-attribute_radarr_') ? 'radarr' : ''
        if (!serviceName || field.dataset.libraryServiceWatcherBound === 'true') return
        const onChange = () => resetLibraryServiceValidatedState(card, serviceName)
        field.addEventListener('input', onChange)
        field.addEventListener('change', onChange)
        field.dataset.libraryServiceWatcherBound = 'true'
      })
      card.dataset.libraryServiceValidationBound = 'true'
    }

    function moveCurrentToCache () {
      const current = libraryContainer.firstElementChild
      if (current) {
        current.style.display = 'none'
        libraryCache.appendChild(current)
      }
    }

    function mountCard (card, libraryId) {
      libraryContainer.replaceChildren()
      card.style.display = ''
      libraryContainer.appendChild(card)
      activeLibraryId = libraryId
      initSecretVisibilityToggles(card)
      syncHiddenCheckboxPairs(card)
      wireIncludeToggle(card, libraryId)
      wireAdvancedToggle(card)
      wireLibraryServiceValidationButtons(card)
      refreshPickerLabels()
      initTooltips(card)
      sortLanguageSelects(card)
      setupOverlayLanguageWeightBuilders(card)
      initNumericOnlyInputs(card)
      initStylePreviewGrids(card)
      initRelativeYearInputs(card)
      initScheduleBuilders(card)
      initLibraryAssetDirectoryInputs(card)
      wireOffsetReset(card)
      wireRatingsOffsetSync(card)
      initSortablesInScope(card)
      setupCustomStringListHandlers('mass_genre_update', card)
      setupCustomStringListHandlers('radarr_remove_by_tag', card)
      setupCustomStringListHandlers('sonarr_remove_by_tag', card)
      setupCustomStringListHandlers('metadata_backup', card)
      setupCustomStringListHandlers('mass_content_rating_update', card)
      setupCustomStringListHandlers('mass_genre_mapper', card)
      setupTemplateStringListHandlers(card)
      setupMappingListHandlers('genre_mapper', card)
      setupMappingListHandlers('content_rating_mapper', card)
      wireOverlayDetailToggles(card)
      setupParentChildToggleVisibility(card)
      if (typeof setupParentChildToggleSync === 'function') {
        setupParentChildToggleSync()
      }
      setupAddMissingDependencies(card)
      wireOverlayTemplateSections(card)
      if (typeof OverlayHandler !== 'undefined' && OverlayHandler.initializeOverlayBoards) {
        OverlayHandler.initializeOverlayBoards(card)
      }
      if (typeof OverlayHandler !== 'undefined' && OverlayHandler.initializeOverlayPositioners) {
        OverlayHandler.initializeOverlayPositioners(card)
      }
      if (typeof OverlayHandler !== 'undefined' && OverlayHandler.initializeJumpButtons) {
        OverlayHandler.initializeJumpButtons(card)
      }
      if (typeof EventHandler !== 'undefined') {
        EventHandler.attachLibraryListeners()
      }
      if (typeof PathValidation !== 'undefined' && PathValidation.attach) {
        PathValidation.attach(card)
      }
      if (typeof ValidationHandler !== 'undefined' && ValidationHandler.updateValidationState) {
        ValidationHandler.updateValidationState()
      }
      wireFontUploads(card)
      wireFontPreviews(card)
      wireFontPickerButtons(card)
      bindDependencyRequirementHintLiveRefresh(card)
      scheduleDependencyRequirementHintRefresh(0)
    }

    wireFontPickerModal()

    function buildPayloadFromCard (card) {
      const payload = {}
      const libraryId = activeLibraryId || String(card?.querySelector('[name]')?.name || '').split('-')[0]
      const checkboxNames = new Set(
        Array.from(card.querySelectorAll('input[type="checkbox"][name]'))
          .map(el => String(el.name || '').trim())
          .filter(Boolean)
      )
      card.querySelectorAll('input, select, textarea').forEach(el => {
        if (!el.name || el.disabled) return
        if (el.dataset && el.dataset.skipYaml === 'true') return
        if (el.type === 'file') return

        if (el.type === 'hidden' && checkboxNames.has(String(el.name || '').trim())) {
          return
        }

        if (el.tagName === 'SELECT' && el.multiple) {
          payload[el.name] = Array.from(el.selectedOptions).map(opt => opt.value)
          return
        }

        if (el.type === 'checkbox') {
          payload[el.name] = el.checked ? (el.value || 'true') : 'false'
          return
        }

        if (el.type === 'radio') {
          if (el.checked) {
            payload[el.name] = el.value || 'on'
          }
          return
        }

        if (el.name.endsWith('-attribute_asset_directory')) {
          if (!Array.isArray(payload[el.name])) payload[el.name] = []
          payload[el.name].push(el.value ?? '')
          return
        }

        payload[el.name] = el.value ?? ''
      })
      if (libraryId) {
        document.querySelectorAll(`input[type="hidden"][name^="${libraryId}-"]`).forEach(el => {
          if (!el.name || el.disabled) return
          if (card.contains(el)) return
          if (checkboxNames.has(String(el.name || '').trim())) return
          payload[el.name] = el.value ?? ''
        })
      }
      card.querySelectorAll('input.playlist-library-toggle[type="checkbox"][name]:disabled').forEach(el => {
        payload[el.name] = 'false'
      })
      return payload
    }

    function initLibraryAssetDirectoryInputs (card) {
      card.querySelectorAll('[data-library-asset-directory-container]').forEach(container => {
        if (container.dataset.assetDirectoryBound === 'true') return
        container.dataset.assetDirectoryBound = 'true'

        const inputName = container.dataset.inputName
        const addBtnSelector = `[data-add-asset-directory="${container.id}"]`
        const addBtn = card.querySelector(addBtnSelector)
        let counter = container.querySelectorAll(`input[name="${inputName}"]`).length

        const buildRow = (value = '') => {
          counter += 1
          const row = document.createElement('div')
          row.className = 'input-group mb-2'

          const input = document.createElement('input')
          input.type = 'text'
          input.className = 'form-control'
          input.name = inputName
          input.id = `${container.id}_${counter}`
          input.placeholder = 'Add Asset Directory'
          input.dataset.pathRule = 'asset_directory'
          input.value = value

          const removeBtn = document.createElement('button')
          removeBtn.className = 'btn btn-danger library-remove-asset-directory'
          removeBtn.type = 'button'
          removeBtn.textContent = 'Remove'

          row.append(input, removeBtn)
          return row
        }

        if (addBtn) {
          addBtn.addEventListener('click', () => {
            const row = buildRow('')
            container.appendChild(row)
            if (typeof PathValidation !== 'undefined' && PathValidation.attach) {
              PathValidation.attach(row)
            }
          })
        }

        container.addEventListener('click', event => {
          if (!event.target.classList.contains('library-remove-asset-directory')) return
          const fieldGroup = event.target.closest('.input-group')
          if (!fieldGroup) return
          let next = fieldGroup.nextElementSibling
          while (next && next.dataset && next.dataset.pathHint) {
            const toRemove = next
            next = next.nextElementSibling
            toRemove.remove()
          }
          container.removeChild(fieldGroup)
        })
      })
    }

    function autosaveActiveLibrary () {
      const card = libraryContainer.firstElementChild
      if (!activeLibraryId || !card) return Promise.resolve()
      if (window.QS_SWITCHING_CONFIG) return Promise.resolve()

      if (typeof PathValidation !== 'undefined' && PathValidation.validateAll) {
        const pathValid = PathValidation.validateAll(card)
        if (!pathValid) {
          if (typeof showToast === 'function') {
            showToast('error', 'Please fix invalid path fields before saving.')
          }
          return Promise.reject(new Error('Invalid path fields'))
        }
      }

      const payload = buildPayloadFromCard(card)
      const collectionEditor = card.querySelector('[data-collection-files-editor]')
      const metadataEditor = card.querySelector('[data-metadata-files-editor]')
      const overlayEditor = card.querySelector('[data-overlay-files-editor]')
      const option = libraryPicker?.querySelector(`option[value="${activeLibraryId}"]`)
      const friendlyName = option?.dataset.label || option?.textContent?.trim() || activeLibraryId

      return fetch(`/autosave_library/${encodeURIComponent(activeLibraryId)}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(res => {
          if (!res.ok) {
            return res.json().catch(() => ({})).then(body => {
              if (collectionEditor) {
                applyCollectionFileServerErrors(collectionEditor, body && body.errors)
              }
              if (metadataEditor) {
                applyMetadataFileServerErrors(metadataEditor, body && body.errors)
              }
              if (overlayEditor) {
                applyOverlayFileServerErrors(overlayEditor, body && body.errors)
              }
              const message = body && body.error ? body.error : `Autosave failed: ${res.status}`
              throw new Error(message)
            })
          }
          return res.json().catch(() => ({}))
        })
        .then(data => {
          if (data && data.success && typeof showToast === 'function') {
            showToast('success', `Autosaved ${friendlyName}.`)
          }
          if (data && data.success) {
            scheduleDependencyRequirementHintRefresh(0)
            document.dispatchEvent(new CustomEvent('qs:workspace-data-changed', { detail: { source: 'libraries-autosave', delayMs: 80 } }))
          }
          return data
        })
        .catch(err => {
          console.error('[Autosave] Failed to save library', activeLibraryId, err)
          if (typeof showToast === 'function') {
            showToast('error', err.message || `Autosave failed for ${friendlyName}.`)
          }
          throw err
        })
    }

    function openCopyModal (sourceId, sourceName, sourceType) {
      if (!copyModal) return
      copyWarning.style.display = 'none'
      copySubtitle.textContent = `Mirror settings from "${sourceName}" to other ${sourceType === 'movie' ? 'movie' : 'show'} libraries`
      copyTargetsContainer.replaceChildren()

      const options = Array.from(libraryPicker.querySelectorAll('option[value]')).filter(opt =>
        opt.dataset.libraryType === sourceType && opt.value !== sourceId
      )

      if (!options.length) {
        const empty = document.createElement('div')
        empty.className = 'text-muted'
        empty.textContent = 'No other libraries of this type available.'
        copyTargetsContainer.appendChild(empty)
      } else {
        options.forEach(opt => {
          const id = opt.value
          const label = opt.dataset.label || opt.textContent
          const inputId = `copy-target-${id}`
          const item = document.createElement('label')
          item.className = 'list-group-item d-flex align-items-center gap-2'
          const input = document.createElement('input')
          input.id = inputId
          input.name = 'copy_target'
          input.className = 'form-check-input me-2 copy-target-checkbox'
          input.type = 'checkbox'
          input.value = id
          const span = document.createElement('span')
          span.textContent = label
          item.append(input, span)
          copyTargetsContainer.appendChild(item)
        })
      }

      const checkboxes = () => Array.from(copyTargetsContainer.querySelectorAll('.copy-target-checkbox'))
      const clearWarning = () => { copyWarning.style.display = 'none' }
      checkboxes().forEach(cb => cb.addEventListener('change', clearWarning))

      if (copySelectAllBtn) {
        copySelectAllBtn.onclick = () => {
          checkboxes().forEach(cb => { cb.checked = true })
          clearWarning()
        }
      }
      if (copyDeselectAllBtn) {
        copyDeselectAllBtn.onclick = () => {
          checkboxes().forEach(cb => { cb.checked = false })
          clearWarning()
        }
      }

      copyModal.show()

      const onConfirm = () => {
        const selected = Array.from(copyTargetsContainer.querySelectorAll('.copy-target-checkbox:checked')).map(cb => cb.value)
        const prefix = sourceType === 'movie' ? 'mov-' : 'sho-'
        const filtered = selected.filter(id => id.startsWith(prefix))
        if (!filtered.length) {
          copyWarning.style.display = 'block'
          return
        }
        copyWarning.style.display = 'none'

        const currentCard = libraryContainer?.firstElementChild
        const sourcePayload = currentCard ? buildPayloadFromCard(currentCard) : {}

        autosaveActiveLibrary()
          .then(resp => {
            if (!resp || resp.success !== true) {
              throw new Error('Autosave did not complete')
            }
          })
          .then(() => fetch('/copy_library_settings', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              source_library_id: sourceId,
              target_library_ids: filtered,
              source_payload: sourcePayload
            })
          }))
          .then(res => {
            if (!res) return
            if (!res.ok) {
              return res.json().catch(() => ({})).then(body => {
                const msg = body && body.error ? body.error : `Copy failed: ${res.status}`
                throw new Error(msg)
              })
            }
            return res.json()
          })
          .then((data) => {
            // Clear all cached cards to avoid stale data
            libraryCache.replaceChildren()

            filtered.forEach(id => {
              const cached = libraryCache.querySelector(`[data-library-id="${id}"]`)
              if (cached && cached.parentElement === libraryCache) {
                cached.remove()
              }
              if (activeLibraryId === id) {
                activeLibraryId = null
              }
              const opt = libraryPicker.querySelector(`option[value="${id}"]`)
              if (opt) {
                opt.dataset.configured = 'false'
              }
            })
            refreshPickerLabels()
            // Reload current selection to pick up fresh data if it was among the targets
            if (libraryPicker && libraryPicker.value) {
              loadLibrary(libraryPicker.value)
            }
            if (typeof showToast === 'function') {
              const label = filtered.length === 1 ? 'library' : 'libraries'
              showToast('success', `Mirrored settings to ${filtered.length} ${label}.`)
            }
            scheduleDependencyRequirementHintRefresh(0)
            document.dispatchEvent(new CustomEvent('qs:workspace-data-changed', { detail: { source: 'libraries-copy', delayMs: 80 } }))
          })
          .catch(err => {
            console.error('[Copy] Failed to mirror library settings', err)
            if (typeof showToast === 'function') {
              showToast('error', `Mirror failed. ${err.message}`)
            }
          })
          .finally(() => {
            if (copyConfirmBtn && typeof copyConfirmBtn.blur === 'function') {
              copyConfirmBtn.blur()
            }
            copyModal.hide()
          })
      }

      // Ensure we don't accumulate handlers across openings
      copyConfirmBtn.onclick = null
      copyConfirmBtn.addEventListener('click', onConfirm)
    }

    function loadLibrary (libraryId, context = 'switch') {
      if (libraryId === activeLibraryId) return
      const requestId = ++loadRequestId
      const previousLibraryId = activeLibraryId
      const setLoading = (flag) => {
        if (libraryLoading) {
          libraryLoading.classList.toggle('d-none', !flag)
        }
        if (libraryPicker) {
          libraryPicker.disabled = !!flag
        }
        if (flag) {
          if (typeof showNavigationLoadingOverlay === 'function') {
            showNavigationLoadingOverlay(context === 'initial' ? 'library-initial' : 'library-switch')
          }
        } else if (typeof hideNavigationLoadingOverlay === 'function') {
          hideNavigationLoadingOverlay()
        }
      }

      setLoading(true)
      autosaveActiveLibrary()
        .then(() => {
          if (requestId !== loadRequestId) return

          if (!libraryId) {
            libraryContainer.replaceChildren()
            activeLibraryId = null
            setLoading(false)
            return
          }

          // Move currently active card to cache (to preserve state/inputs)
          moveCurrentToCache()

          const cached = libraryCache.querySelector(`[data-library-id="${libraryId}"]`)
          if (cached) {
            if (requestId !== loadRequestId) return
            mountCard(cached, libraryId)
            setLoading(false)
            return
          }

          fetch(`/library_fragment/${encodeURIComponent(libraryId)}`)
            .then(res => {
              if (!res.ok) throw new Error(`Failed to load library ${libraryId}`)
              return res.text()
            })
            .then(html => {
              if (requestId !== loadRequestId) return
              const parser = new DOMParser()
              const doc = parser.parseFromString(html, 'text/html')
              const parsedCard = doc.body.firstElementChild
              const card = parsedCard ? document.importNode(parsedCard, true) : null
              if (!card) throw new Error('Empty fragment response')
              mountCard(card, libraryId)
              setLoading(false)
            })
            .catch(err => {
              console.error(err)
              setLoading(false)
            })
        })
        .catch(() => {
          if (requestId !== loadRequestId) return
          if (libraryPicker && previousLibraryId) {
            libraryPicker.value = previousLibraryId
          }
          setLoading(false)
        })
    }

    if (libraryPicker) {
      libraryPicker.addEventListener('change', (e) => {
        loadLibrary(e.target.value, 'switch')
      })

      refreshPickerLabels()
      const configuredFirst = libraryPicker.querySelector('option[data-configured="true"]')
      const firstLibrary = libraryPicker.value ||
        configuredFirst?.value ||
        libraryPicker.querySelector('option[value]:not([value=""])')?.value
      if (configuredFirst) {
        libraryPicker.value = configuredFirst.value
        loadLibrary(configuredFirst.value, 'initial')
      } else if (firstLibrary) {
        loadLibrary(firstLibrary, 'initial')
      } else {
        libraryPicker.value = ''
      }
    }

    document.addEventListener('qs:before-step-navigation', (event) => {
      const detail = (event && event.detail) || {}
      if (allowNextStepNavigation) {
        allowNextStepNavigation = false
        return
      }
      if (!activeLibraryId || !libraryContainer || !libraryContainer.firstElementChild) return
      if (!detail.targetPage || detail.targetPage === '025-libraries') return

      event.preventDefault()

      autosaveActiveLibrary()
        .then(() => {
          allowNextStepNavigation = true
          jumpTo(detail.targetPage, detail.targetLabel)
        })
        .catch(() => {
          allowNextStepNavigation = false
        })
    })

    if (typeof setupParentChildToggleSync === 'function') {
      setupParentChildToggleSync()
    }

    if (typeof EventHandler !== 'undefined' && EventHandler.attachLibraryListeners) {
      EventHandler.attachLibraryListeners()
    }

    if (typeof ValidationHandler !== 'undefined' && ValidationHandler.updateValidationState) {
      ValidationHandler.updateValidationState()
    }

    setupParentChildToggleVisibility()
    setupCustomStringListHandlers('mass_genre_update')
    setupCustomStringListHandlers('radarr_remove_by_tag')
    setupCustomStringListHandlers('sonarr_remove_by_tag')
    setupCustomStringListHandlers('metadata_backup')
    setupCustomStringListHandlers('mass_content_rating_update')
    setupCustomStringListHandlers('mass_genre_mapper')
    setupMappingListHandlers('genre_mapper')
    setupMappingListHandlers('content_rating_mapper')

    document.querySelectorAll('.overlay-template-section').forEach((el) => {
      el.style.display = 'none'
    })

    wireOverlayDetailToggles()
    wireOverlayTemplateSections()
    wireRatingsOffsetSync()

    document.addEventListener('click', (e) => {
      const btn = e.target.closest('.copy-library-btn')
      if (!btn) return
      const sourceId = btn.dataset.libraryId
      const sourceName = btn.dataset.libraryName
      const sourceType = btn.dataset.libraryType
      openCopyModal(sourceId, sourceName, sourceType)
    })

    function initializeSortableList (libraryId, prefix) {
      const list = document.getElementById(`${libraryId}-attribute_${prefix}_sortable`)
      const hiddenInput = document.getElementById(`${libraryId}-attribute_${prefix}_order`)

      if (!list || !hiddenInput) {
        console.warn('[WARN] Missing sortable list or hidden input for', `${libraryId}-${prefix}`)
        return
      }

      let values = []
      try {
        values = JSON.parse(hiddenInput.value || '[]')
        console.log('[DEBUG] Parsed hidden input from', hiddenInput.id, values)
      } catch (e) {
        console.warn('[WARN] Could not parse JSON from hidden input', hiddenInput.id, hiddenInput.value)
      }

      // If no order is saved yet, default to currently checked toggles (in DOM order)
      if (!values.length) {
        const toggles = Array.from(document.querySelectorAll(`input[type=checkbox][id^='${libraryId}-attribute_${prefix}_']`))
        values = toggles.filter(t => t.checked).map(t => t.id.replace(`${libraryId}-attribute_${prefix}_`, ''))
        hiddenInput.value = JSON.stringify(values)
      }
      renderSortableList(libraryId, prefix, list, hiddenInput, values)
    }

    function initSortablesInScope (scope) {
      const root = scope || document
      root.querySelectorAll('.sortable-list').forEach(list => {
        if (list.dataset.sortableInit === 'true') return

        const match = list.id.match(/^(.*?)-attribute_(.+?)_sortable$/)
        if (!match) return

        const libraryId = match[1]
        const prefix = match[2]

        console.log('[DEBUG] Initializing sortable for', libraryId, 'with prefix', prefix, '(scoped)')

        initializeSortableList(libraryId, prefix)
        bindToggleToList(libraryId, prefix)

        Sortable.create(list, {
          handle: '.drag-handle',
          animation: 150,
          onSort: function () {
            const hiddenInput = document.getElementById(`${libraryId}-attribute_${prefix}_order`)
            const selected = [...list.querySelectorAll('li')].map(li => li.dataset.value)
            hiddenInput.value = JSON.stringify(selected)
            console.log('[DEBUG] Updated order for', hiddenInput.id, selected)
          }
        })

        list.dataset.sortableInit = 'true'
      })
    }

    function renderSortableList (libraryId, prefix, list, hiddenInput, values) {
      list.replaceChildren()

      values.forEach(item => {
        const toggle = document.getElementById(`${libraryId}-attribute_${prefix}_${item}`)
        if (toggle) toggle.checked = true

        const li = document.createElement('li')
        li.className = 'list-group-item sortable-item d-flex justify-content-between align-items-center'
        li.dataset.value = item

        const labelElement = document.querySelector(`label[for="${libraryId}-attribute_${prefix}_${item}"]`)
        const friendlyText = labelElement?.dataset.label || item

        const span = document.createElement('span')
        const icon = document.createElement('i')
        icon.className = 'bi bi-grip-vertical me-2 drag-handle'
        span.append(icon, document.createTextNode(friendlyText))

        li.appendChild(span)
        list.appendChild(li)
      })
    }

    function bindToggleToList (libraryId, prefix) {
      document.querySelectorAll(`input[type=checkbox][id^='${libraryId}-attribute_${prefix}_']`).forEach(toggle => {
        toggle.addEventListener('change', function () {
          const source = this.id.match(new RegExp(`${libraryId}-attribute_${prefix}_(.+)$`))[1]
          const list = document.getElementById(`${libraryId}-attribute_${prefix}_sortable`)
          const hiddenInput = document.getElementById(`${libraryId}-attribute_${prefix}_order`)

          if (!list || !hiddenInput) return

          let current = []
          try {
            current = JSON.parse(hiddenInput.value || '[]')
          } catch (e) {
            console.warn('[WARN] Could not parse hidden input value:', hiddenInput.value)
          }

          const index = current.indexOf(source)
          if (this.checked && index === -1) {
            current.push(source)
          } else if (!this.checked && index !== -1) {
            current.splice(index, 1)
          }

          hiddenInput.value = JSON.stringify(current)
          renderSortableList(libraryId, prefix, list, hiddenInput, current)
        })
      })
    }

    document.querySelectorAll('.sortable-list').forEach(list => {
      const match = list.id.match(/^(.*?)-attribute_(.+?)_sortable$/)
      if (!match) return

      const libraryId = match[1]
      const prefix = match[2]

      console.log(`[DEBUG] Initializing sortable for ${libraryId} with prefix ${prefix}`)

      initializeSortableList(libraryId, prefix)
      bindToggleToList(libraryId, prefix)

      // Create Sortable only once here
      Sortable.create(list, {
        handle: '.drag-handle',
        animation: 150,
        onSort: function () {
          const hiddenInput = document.getElementById(`${libraryId}-attribute_${prefix}_order`)
          const selected = [...list.querySelectorAll('li')].map(li => li.dataset.value)
          hiddenInput.value = JSON.stringify(selected)
          console.log(`[DEBUG] Updated order for #${hiddenInput.id}:`, selected)
        }
      })
    })
  })
})

function toggleOverlayTemplateSection (checkbox) {
  const groupContainer = checkbox.closest('.template-toggle-group') // <== FIXED
  const templateSection = groupContainer?.querySelector('.overlay-template-section')
  const detailsToggle = groupContainer?.querySelector('.overlay-details-toggle')
  const detailActions = groupContainer?.querySelector('.overlay-detail-actions')

  if (templateSection) {
    if (checkbox.checked) {
      templateSection.style.display = 'none'
      if (detailActions) {
        detailActions.classList.remove('d-none')
      }
      if (detailsToggle) {
        detailsToggle.textContent = 'Show Details'
      }
    } else {
      templateSection.style.display = 'none'
      if (detailActions) {
        detailActions.classList.add('d-none')
      }
      if (detailsToggle) {
        detailsToggle.textContent = 'Show Details'
      }
    }
  }
}

function setupCustomStringListHandlers (prefix, scope) {
  const root = scope || document
  root.querySelectorAll(`input[id$="attribute_${prefix}_custom_hidden"]`).forEach(hidden => {
    if (hidden.dataset.listenerAdded) return
    const libraryId = hidden.id.split('-attribute_')[0]
    const input = document.getElementById(`${libraryId}-attribute_${prefix}_custom_input`)
    const list = document.getElementById(`${libraryId}-attribute_${prefix}_custom_list`)
    const button = document.getElementById(`${libraryId}-attribute_${prefix}_custom_add`)

    if (!input || !list || !button) return

    function renderCustomList (values) {
      list.replaceChildren()

      values.forEach(value => {
        const li = document.createElement('li')
        li.className = 'list-group-item d-flex justify-content-between align-items-center'
        const textSpan = document.createElement('span')
        textSpan.textContent = value
        const button = document.createElement('button')
        button.type = 'button'
        button.className = 'btn btn-sm btn-danger'
        button.setAttribute('aria-label', 'Remove')
        const icon = document.createElement('i')
        icon.className = 'bi bi-x-lg'
        button.appendChild(icon)
        li.append(textSpan, button)
        list.appendChild(li)

        button.addEventListener('click', function () {
          const updated = values.filter(item => item !== value)
          hidden.value = JSON.stringify(updated)
          renderCustomList(updated) // 🔁 Rerender the new list and update the array
        })
      })
    }

    // Initialize list from hidden input value
    let current = []
    try {
      current = JSON.parse(hidden.value || '[]')
    } catch (e) {
      console.warn('[WARN] Could not parse hidden input for', prefix, hidden.value)
    }
    renderCustomList(current)

    // Add button logic
    button.addEventListener('click', function () {
      let current = []
      try {
        current = JSON.parse(hidden.value || '[]')
      } catch (e) {
        console.warn('[WARN] Could not parse hidden input for', prefix, hidden.value)
      }

      const value = input.value.trim()
      if (!value || current.includes(value)) return

      current.push(value)
      hidden.value = JSON.stringify(current)
      renderCustomList(current)
      input.value = ''
    })

    hidden.dataset.listenerAdded = 'true'
  })
}

function setupMappingListHandlers (prefix, scope) {
  const root = scope || document
  root.querySelectorAll(`input[id$="attribute_${prefix}_hidden"]`).forEach(hidden => {
    if (hidden.dataset.listenerAdded) return

    const libraryId = hidden.id.split('-attribute_')[0]
    const inputField = document.getElementById(`${libraryId}-attribute_${prefix}_input`)
    const outputField = document.getElementById(`${libraryId}-attribute_${prefix}_output`)
    const list = document.getElementById(`${libraryId}-attribute_${prefix}_list`)
    const addBtn = document.getElementById(`${libraryId}-attribute_${prefix}_add`)

    if (!inputField || !outputField || !list || !addBtn) return

    function renderList (data) {
      list.replaceChildren()
      Object.entries(data).forEach(([key, value]) => {
        const li = document.createElement('li')
        li.className = 'list-group-item d-flex justify-content-between align-items-center'
        const display = value ? `${key} -> ${value}` : `${key} (remove)`
        const textSpan = document.createElement('span')
        textSpan.textContent = display
        const button = document.createElement('button')
        button.type = 'button'
        button.className = 'btn btn-sm btn-danger'
        button.setAttribute('aria-label', 'Remove')
        const icon = document.createElement('i')
        icon.className = 'bi bi-x-lg'
        button.appendChild(icon)
        li.append(textSpan, button)
        list.appendChild(li)
        button.addEventListener('click', () => {
          delete data[key]
          hidden.value = JSON.stringify(data)
          renderList(data)
        })
      })
    }

    let current = {}
    try {
      current = JSON.parse(hidden.value || '{}') || {}
    } catch (e) {
      console.warn('[WARN] Could not parse hidden input for', prefix, hidden.value)
      current = {}
    }
    renderList(current)

    addBtn.addEventListener('click', () => {
      const key = inputField.value.trim()
      const val = outputField.value.trim()
      if (!key) return
      current[key] = val
      hidden.value = JSON.stringify(current)
      renderList(current)
      inputField.value = ''
      outputField.value = ''
    })

    hidden.dataset.listenerAdded = 'true'
  })
}

function wireOffsetReset (scope) {
  const root = scope || document
  root.querySelectorAll('.reset-offset-btn').forEach(btn => {
    if (btn.dataset.listenerAdded) return
    btn.addEventListener('click', () => {
      const group = btn.closest('.template-toggle-group')
      if (group) {
        group.dataset.resetting = 'true'
      }
      const changes = []
      const touched = new Set()
      const isRatingsOverlay = group?.dataset?.overlayId === 'overlay_ratings'
      const escapeHtml = (value) => String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
      const getInputLabel = (input) => {
        if (!input) return 'Field'
        const describedBy = input.getAttribute('aria-describedby')
        if (describedBy) {
          const firstId = describedBy.split(' ')[0]
          const el = document.getElementById(firstId)
          if (el && el.textContent) return el.textContent.trim()
        }
        if (input.id) {
          const label = document.querySelector(`label[for="${input.id}"]`)
          if (label && label.textContent) return label.textContent.trim()
        }
        return input.name || input.id || 'Field'
      }
      const getDisplayValue = (input) => {
        if (!input) return ''
        if (input.tagName === 'SELECT') {
          return input.selectedOptions?.[0]?.textContent?.trim() || input.value || ''
        }
        if (input.type === 'checkbox') return input.checked ? 'On' : 'Off'
        if (input.type === 'radio') return input.checked ? 'Selected' : 'Not selected'
        return input.value ?? ''
      }
      const ratingFontInputs = isRatingsOverlay
        ? new Set(
          Array.from(group.querySelectorAll('select[id$="-rating1_font"], select[id$="-rating2_font"], select[id$="-rating3_font"]'))
        )
        : new Set()
      const ratingFontBefore = new Map()
      if (isRatingsOverlay) {
        ratingFontInputs.forEach(input => {
          ratingFontBefore.set(input, getDisplayValue(input))
        })
      }
      const getDefaultDisplayValue = (input, defaultValue) => {
        if (!input) return ''
        if (input.type === 'checkbox' || input.type === 'radio') {
          const normalizedDefault = (defaultValue || '').toString().toLowerCase()
          const normalizedValue = (input.value || '').toString().toLowerCase()
          const checked = normalizedDefault === 'true' || normalizedDefault === normalizedValue
          return checked ? (input.type === 'radio' ? 'Selected' : 'On') : (input.type === 'radio' ? 'Not selected' : 'Off')
        }
        if (input.tagName === 'SELECT') {
          const option = Array.from(input.options).find(o => String(o.value) === String(defaultValue))
          return option ? (option.textContent || '').trim() : (defaultValue ?? '')
        }
        return defaultValue ?? ''
      }
      const recordReset = (input, defaultValue) => {
        if (!input || touched.has(input)) return
        touched.add(input)
        const from = getDisplayValue(input)
        const to = getDefaultDisplayValue(input, defaultValue)
        if (from !== to) {
          if (!(isRatingsOverlay && ratingFontInputs.has(input))) {
            changes.push({ label: getInputLabel(input), from, to })
          }
          return true
        }
        return false
      }

      const hId = btn.dataset.horizontalId
      const vId = btn.dataset.verticalId
      const pId = btn.dataset.positionId
      const hInput = hId ? document.getElementById(hId) : null
      const vInput = vId ? document.getElementById(vId) : null
      const pInput = pId ? document.getElementById(pId) : null
      const extraIds = (btn.dataset.resetIds || '')
        .split(',')
        .map(id => id.trim())
        .filter(Boolean)

      if (hInput && hInput.dataset.default !== undefined) {
        const changed = recordReset(hInput, hInput.dataset.default)
        if (changed) {
          hInput.value = hInput.dataset.default
          hInput.dispatchEvent(new Event('change', { bubbles: true }))
        }
      }
      if (vInput && vInput.dataset.default !== undefined) {
        const changed = recordReset(vInput, vInput.dataset.default)
        if (changed) {
          vInput.value = vInput.dataset.default
          vInput.dispatchEvent(new Event('change', { bubbles: true }))
        }
      }
      if (pInput && pInput.dataset.default !== undefined) {
        const changed = recordReset(pInput, pInput.dataset.default)
        if (changed) {
          pInput.value = pInput.dataset.default
          pInput.dispatchEvent(new Event('change', { bubbles: true }))
        }
      }
      extraIds.forEach(id => {
        const input = document.getElementById(id)
        if (input && input.dataset.default !== undefined) {
          const defaultValue = input.dataset.default
          if (input.type === 'checkbox') {
            const normalizedDefault = (defaultValue || '').toString().toLowerCase()
            const normalizedValue = (input.value || '').toString().toLowerCase()
            const nextChecked = normalizedDefault === 'true' || normalizedDefault === normalizedValue
            const changed = recordReset(input, defaultValue)
            if (changed) {
              input.checked = nextChecked
              input.dispatchEvent(new Event('change', { bubbles: true }))
            }
            return
          }
          const changed = recordReset(input, defaultValue)
          if (changed) {
            input.value = defaultValue
            input.dispatchEvent(new Event('change', { bubbles: true }))
          }
        }
      })

      if (group) {
        group.querySelectorAll('input[data-default], select[data-default], textarea[data-default]').forEach(input => {
          if (input.disabled) return
          const defaultValue = input.dataset.default
          if (defaultValue === undefined) return

          if (input.type === 'checkbox' || input.type === 'radio') {
            const normalizedDefault = (defaultValue || '').toString().toLowerCase()
            const normalizedValue = (input.value || '').toString().toLowerCase()
            const nextChecked = normalizedDefault === 'true' || normalizedDefault === normalizedValue
            const changed = recordReset(input, defaultValue)
            if (changed) input.checked = nextChecked
          } else {
            const changed = recordReset(input, defaultValue)
            if (changed) input.value = defaultValue
          }
          if (changes.length && touched.has(input)) {
            input.dispatchEvent(new Event('input', { bubbles: true }))
            input.dispatchEvent(new Event('change', { bubbles: true }))
          }
        })
      }

      if (group) {
        delete group.dataset.resetting
        if (isRatingsOverlay) {
          const alignmentInput = group.querySelector('[name$="[rating_alignment]"]')
          if (alignmentInput) {
            alignmentInput.dispatchEvent(new Event('change', { bubbles: true }))
          }
        }
        if (changes.length) {
          if (isRatingsOverlay) {
            if (hInput) {
              hInput.dispatchEvent(new Event('input', { bubbles: true }))
              hInput.dispatchEvent(new Event('change', { bubbles: true }))
            }
            if (vInput) {
              vInput.dispatchEvent(new Event('input', { bubbles: true }))
              vInput.dispatchEvent(new Event('change', { bubbles: true }))
            }
            if (pInput) {
              pInput.dispatchEvent(new Event('change', { bubbles: true }))
            }
          }
          const trigger = group.querySelector('input:not([disabled]), select:not([disabled]), textarea:not([disabled])')
          if (trigger) {
            trigger.dispatchEvent(new Event('change', { bubbles: true }))
          }
        }
      }

      const finalizeToast = () => {
        if (changes.length && typeof showToast === 'function') {
          const details = changes
            .map(change => `${escapeHtml(change.label)}: ${escapeHtml(change.from)} → ${escapeHtml(change.to)}`)
            .join('<br>')
          showToast('info', `Reset to defaults:<br>${details}`)
        } else if (!changes.length && typeof showToast === 'function') {
          showToast('info', 'Already at defaults (no changes).')
        }
      }

      if (isRatingsOverlay && group) {
        group.dataset.ratingFontForce = 'true'
        const ratingImageInputs = group.querySelectorAll('[name$="[rating1_image]"], [name$="[rating2_image]"], [name$="[rating3_image]"]')
        ratingImageInputs.forEach(input => {
          input.dispatchEvent(new Event('change', { bubbles: true }))
        })
        window.setTimeout(() => {
          ratingFontInputs.forEach(input => {
            const from = ratingFontBefore.get(input) || ''
            const to = getDisplayValue(input)
            if (from !== to) {
              changes.push({ label: getInputLabel(input), from, to })
            }
          })
          finalizeToast()
        }, 0)
      } else {
        finalizeToast()
      }
    })
    btn.dataset.listenerAdded = 'true'
  })
}

function setupParentChildToggleVisibility (scope) {
  const root = scope || document

  root.querySelectorAll('[data-template-group]').forEach(parentToggle => {
    if (parentToggle.dataset.childVisibilityBound === 'true') return

    const groupId = parentToggle.getAttribute('data-template-group')
    const wrapper = parentToggle.closest('.template-toggle-group')
    // Prefer lookup within the provided scope; fall back to document if needed.
    let childrenGroup = root.querySelector(`[data-toggle-parent="${groupId}"]`)
    if (!childrenGroup) {
      childrenGroup = document.querySelector(`[data-toggle-parent="${groupId}"]`)
    }

    if (!childrenGroup || !wrapper) return

    function updateVisibilityAndBorder (fromParent = false) {
      const childrenToggles = childrenGroup.querySelectorAll("input[type='checkbox']")
      const syncChildHidden = (child) => {
        const row = child.closest('.form-check')
        const hidden = row
          ? row.querySelector(`input[type="hidden"][name="${child.name}"]`)
          : document.querySelector(`input[type="hidden"][name="${child.name}"]`)
        if (!hidden) return
        hidden.value = child.checked ? 'true' : 'false'
        hidden.disabled = !!child.checked
      }
      childrenToggles.forEach(child => {
        if (child.dataset.initialChecked === undefined) {
          child.dataset.initialChecked = child.checked ? 'true' : 'false'
        }
      })
      let parentChecked = parentToggle.checked
      const wasChecked = parentToggle.dataset.wasChecked === 'true'

      if (!parentChecked) {
        childrenToggles.forEach(child => {
          child.dataset.lastChecked = child.checked ? 'true' : 'false'
          child.checked = false
          syncChildHidden(child)
        })
      } else if (parentChecked && !wasChecked) {
        childrenToggles.forEach(child => {
          if (child.dataset.lastChecked !== undefined) {
            child.checked = child.dataset.lastChecked === 'true'
          } else {
            child.checked = child.dataset.initialChecked === 'true'
          }
          syncChildHidden(child)
        })
      } else {
        childrenToggles.forEach(child => syncChildHidden(child))
      }

      const isAddMissingToggle = (child) => {
        const id = child.id || ''
        return id.includes('_radarr_add_missing_') || id.includes('_sonarr_add_missing_')
      }
      const isVisibleToggle = (child) => {
        const id = child.id || ''
        return id.includes('_visible_')
      }
      const isRequiredChild = (child) => {
        const id = child.id || ''
        if (!id.includes('-template_collection_')) return false
        if (isAddMissingToggle(child) || isVisibleToggle(child)) return false
        return id.includes('_use_')
      }
      const requiredChildren = Array.from(childrenToggles).filter(isRequiredChild)
      const hasRequiredChildren = requiredChildren.length > 0
      let anyRequiredChecked = requiredChildren.some(el => el.checked)
      const isCollectionParent = parentToggle.id.includes('-collection_')
      if (fromParent && parentChecked && isCollectionParent && hasRequiredChildren && !anyRequiredChecked) {
        const candidate = requiredChildren[0]
        if (candidate) {
          candidate.checked = true
          syncChildHidden(candidate)
          anyRequiredChecked = true
        }
      }
      const parentHidden = document.querySelector(`input[type="hidden"][name="${parentToggle.name}"]`)
      if (parentChecked && hasRequiredChildren && !anyRequiredChecked) {
        parentChecked = false
        parentToggle.checked = false
        parentToggle.dataset.wasChecked = 'false'
        if (parentHidden) parentHidden.value = 'false'
      }
      if (parentHidden) {
        parentHidden.disabled = parentChecked
        if (!parentChecked) parentHidden.value = 'false'
      }

      childrenGroup.style.display = parentChecked ? 'block' : 'none'
      if (parentChecked && (hasRequiredChildren ? anyRequiredChecked : true)) {
        wrapper.classList.add('template-toggle-group-bordered')
      } else {
        wrapper.classList.remove('template-toggle-group-bordered')
      }

      EventHandler.updateAccordionHighlights()
      ValidationHandler.updateValidationState()
      parentToggle.dataset.wasChecked = parentChecked ? 'true' : 'false'
    }

    parentToggle.addEventListener('change', () => updateVisibilityAndBorder(true))
    childrenGroup.querySelectorAll("input[type='checkbox']").forEach(child =>
      child.addEventListener('change', () => updateVisibilityAndBorder(false))
    )

    updateVisibilityAndBorder(false) // Initial check
    parentToggle.dataset.childVisibilityBound = 'true'
  })
}

function wireRatingsOffsetSync (scope) {
  const root = scope || document
  root.querySelectorAll('.template-toggle-group[data-overlay-id="overlay_ratings"]').forEach(group => {
    if (group.dataset.ratingsOffsetSyncBound === 'true') return

    const templateName = group.dataset.overlayTemplate
    if (!templateName) return

    const sharedInputs = {
      horizontal: group.querySelector(`[name="${templateName}[horizontal_offset]"]`),
      vertical: group.querySelector(`[name="${templateName}[vertical_offset]"]`)
    }
    if (!sharedInputs.horizontal || !sharedInputs.vertical) return

    const metricInputs = {
      backHeight: group.querySelector(`[name="${templateName}[back_height]"]`),
      backWidth: group.querySelector(`[name="${templateName}[back_width]"]`),
      backPadding: group.querySelector(`[name="${templateName}[back_padding]"]`)
    }
    const alignmentInput = group.querySelector(`[name="${templateName}[rating_alignment]"]`)
    const addonPositionInput = group.querySelector(`[name="${templateName}[addon_position]"]`)
    const positionInput = group.querySelector(`[name="${templateName}[horizontal_position]"]`)
    const verticalPositionInput = group.querySelector(`[name="${templateName}[vertical_position]"]`)
    const slotDefs = ['rating1', 'rating2', 'rating3'].map(slot => ({
      slot,
      ratingInput: group.querySelector(`[name="${templateName}[${slot}]"]`),
      imageInput: group.querySelector(`[name="${templateName}[${slot}_image]"]`),
      horizontalInput: group.querySelector(`[name="${templateName}[${slot}_horizontal_offset]"]`),
      verticalInput: group.querySelector(`[name="${templateName}[${slot}_vertical_offset]"]`)
    })).filter(slot => slot.horizontalInput || slot.verticalInput || slot.ratingInput || slot.imageInput)
    const slotInputs = {
      horizontal: slotDefs.map(slot => slot.horizontalInput).filter(Boolean),
      vertical: slotDefs.map(slot => slot.verticalInput).filter(Boolean)
    }

    const toNumber = (value, fallback = 0) => {
      const n = Number(value)
      return Number.isFinite(n) ? n : fallback
    }
    const normalizeValue = (value) => String(value ?? '').trim().toLowerCase()
    const hasMeaningfulValue = (input) => {
      if (!input) return false
      const value = normalizeValue(input.value)
      return value !== '' && value !== 'none'
    }
    const isConfiguredSlot = (slot) => hasMeaningfulValue(slot.ratingInput) && hasMeaningfulValue(slot.imageInput)
    const getActiveSlots = () => slotDefs.filter(isConfiguredSlot)
    const getAlignment = () => {
      const raw = normalizeValue(alignmentInput?.value || alignmentInput?.dataset?.default || 'vertical')
      return raw === 'horizontal' ? 'horizontal' : 'vertical'
    }
    const getHorizontalPosition = () => {
      const raw = normalizeValue(positionInput?.value || positionInput?.dataset?.default || 'left')
      return (raw === 'center' || raw === 'right') ? raw : 'left'
    }
    const getVerticalPosition = () => {
      const verticalInput = group.querySelector(`[name="${templateName}[vertical_position]"]`)
      const raw = normalizeValue(verticalInput?.value || verticalInput?.dataset?.default || 'center')
      return (raw === 'top' || raw === 'bottom') ? raw : 'center'
    }
    const getPlacementDefaults = () => {
      const hPos = getHorizontalPosition()
      const vPos = getVerticalPosition()
      return {
        // Offsets are distance from the selected origin edge.
        // Left/Right (and Top/Bottom) edge anchors both use +15 for inset margin.
        horizontal: hPos === 'center' ? 0 : 15,
        vertical: vPos === 'center' ? 0 : 15
      }
    }
    const ensureAdjustedIndicator = (input, axisLabel) => {
      if (!input) return null
      const wrapper = input.closest('.input-group')
      if (!wrapper) return null
      let indicator = wrapper.querySelector(`.ratings-position-adjusted[data-axis="${axisLabel}"]`)
      if (indicator) return indicator
      indicator = document.createElement('span')
      indicator.className = 'input-group-text ratings-position-adjusted d-none'
      indicator.dataset.axis = axisLabel
      indicator.textContent = 'Adjusted'
      indicator.title = `${axisLabel} anchor has manual offset adjustments.`
      wrapper.appendChild(indicator)
      return indicator
    }
    const horizontalAdjustedIndicator = ensureAdjustedIndicator(positionInput, 'horizontal')
    const verticalAdjustedIndicator = ensureAdjustedIndicator(verticalPositionInput, 'vertical')
    const updateAdjustedIndicators = () => {
      const defaults = getPlacementDefaults()
      const hCurrent = Math.round(toNumber(sharedInputs.horizontal?.value, defaults.horizontal))
      const vCurrent = Math.round(toNumber(sharedInputs.vertical?.value, defaults.vertical))
      if (horizontalAdjustedIndicator) {
        horizontalAdjustedIndicator.classList.toggle('d-none', hCurrent === defaults.horizontal)
      }
      if (verticalAdjustedIndicator) {
        verticalAdjustedIndicator.classList.toggle('d-none', vCurrent === defaults.vertical)
      }
    }
    const setDefaultValue = (input, nextValue, force = false) => {
      if (!input || nextValue === undefined || nextValue === null) return
      const prevDefault = input.dataset.default
      const prevValue = String(input.value ?? '')
      const prevDefaultValue = String(prevDefault ?? '')
      const shouldUpdate = force || prevValue === prevDefaultValue || prevValue === ''
      input.dataset.default = String(nextValue)
      if (shouldUpdate) {
        input.value = String(nextValue)
        if (group.dataset.ratingsBulkUpdate !== 'true') {
          input.dispatchEvent(new Event('input', { bubbles: true }))
          input.dispatchEvent(new Event('change', { bubbles: true }))
        }
      }
    }
    const applyAlignmentDefaults = (force = false) => {
      if (!alignmentInput) return
      const alignment = getAlignment()
      const defaults = alignment === 'horizontal'
        ? { backWidth: 270, backHeight: 80, addonPosition: 'left' }
        : { backWidth: 160, backHeight: 160, addonPosition: 'top' }
      setDefaultValue(metricInputs.backWidth, defaults.backWidth, force)
      setDefaultValue(metricInputs.backHeight, defaults.backHeight, force)
      setDefaultValue(addonPositionInput, defaults.addonPosition, force)
    }
    const applyPlacementDefaults = (force = false) => {
      const defaults = getPlacementDefaults()
      setDefaultValue(sharedInputs.horizontal, defaults.horizontal, force)
      setDefaultValue(sharedInputs.vertical, defaults.vertical, force)
    }
    const ratingConstants = {
      edgeInset: 30,
      center: 0,
      v2: 235,
      v3: 440,
      cv2: 105,
      cv3: 205,
      h2: 345,
      h3: 660,
      ch2: 160,
      ch3: 335
    }
    const buildAxisPositions = (axis, position, count) => {
      const safeCount = Math.max(1, Math.min(3, Number(count) || 1))
      if (axis === 'horizontal') {
        if (position === 'center') {
          if (safeCount === 1) return [ratingConstants.center]
          if (safeCount === 2) return [-ratingConstants.ch2, ratingConstants.ch2]
          return [-ratingConstants.ch3, ratingConstants.center, ratingConstants.ch3]
        }
        if (position === 'right') {
          if (safeCount === 1) return [-ratingConstants.edgeInset]
          if (safeCount === 2) return [-ratingConstants.h2, -ratingConstants.edgeInset]
          return [-ratingConstants.h3, -ratingConstants.h2, -ratingConstants.edgeInset]
        }
        if (safeCount === 1) return [ratingConstants.edgeInset]
        if (safeCount === 2) return [ratingConstants.edgeInset, ratingConstants.h2]
        return [ratingConstants.edgeInset, ratingConstants.h2, ratingConstants.h3]
      }

      if (position === 'center') {
        if (safeCount === 1) return [ratingConstants.center]
        if (safeCount === 2) return [-ratingConstants.cv2, ratingConstants.cv2]
        return [-ratingConstants.cv3, ratingConstants.center, ratingConstants.cv3]
      }
      if (position === 'bottom') {
        if (safeCount === 1) return [-ratingConstants.edgeInset]
        if (safeCount === 2) return [-ratingConstants.v2, -ratingConstants.edgeInset]
        return [-ratingConstants.v3, -ratingConstants.v2, -ratingConstants.edgeInset]
      }
      if (safeCount === 1) return [ratingConstants.edgeInset]
      if (safeCount === 2) return [ratingConstants.edgeInset, ratingConstants.v2]
      return [ratingConstants.edgeInset, ratingConstants.v2, ratingConstants.v3]
    }
    const computeRatingOffsets = () => {
      const alignment = getAlignment()
      const hPos = getHorizontalPosition()
      const vPos = getVerticalPosition()
      const activeSlots = getActiveSlots()
      const activeCount = activeSlots.length
      const offsets = {
        rating1: { horizontal: ratingConstants.edgeInset, vertical: ratingConstants.edgeInset },
        rating2: { horizontal: ratingConstants.edgeInset, vertical: ratingConstants.edgeInset },
        rating3: { horizontal: ratingConstants.edgeInset, vertical: ratingConstants.edgeInset }
      }
      if (!activeCount) return offsets

      if (alignment === 'horizontal') {
        const xPositions = buildAxisPositions('horizontal', hPos, activeCount)
        const yShared = vPos === 'center' ? 0 : (vPos === 'bottom' ? -ratingConstants.edgeInset : ratingConstants.edgeInset)
        activeSlots.forEach((slot, idx) => {
          offsets[slot.slot].horizontal = xPositions[idx]
          offsets[slot.slot].vertical = yShared
        })
        return offsets
      }

      const yPositions = buildAxisPositions('vertical', vPos, activeCount)
      const xShared = hPos === 'center' ? 0 : (hPos === 'right' ? -ratingConstants.edgeInset : ratingConstants.edgeInset)
      activeSlots.forEach((slot, idx) => {
        offsets[slot.slot].horizontal = xShared
        offsets[slot.slot].vertical = yPositions[idx]
      })
      return offsets
    }
    const applyComputedOffsets = (force = false) => {
      const offsets = computeRatingOffsets()
      const targetSlots = slotDefs.filter(slot => slot.horizontalInput || slot.verticalInput)
      group.dataset.ratingsBulkUpdate = 'true'
      targetSlots.forEach(slot => {
        const computed = offsets[slot.slot]
        if (!computed) return
        setDefaultValue(slot.horizontalInput, computed.horizontal, force)
        setDefaultValue(slot.verticalInput, computed.vertical, force)
      })
      delete group.dataset.ratingsBulkUpdate
    }
    const updateInputValue = (input, nextValue) => {
      if (!input) return
      const normalized = String(Math.round(nextValue))
      if (String(input.value ?? '') === normalized) return
      input.value = normalized
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
    }

    const valuesDiffer = (input) => {
      if (!input) return false
      return String(input.value ?? '') !== String(input.dataset.default ?? '')
    }
    const hasExplicitSlotOffsets = (axis = null) => {
      const activeSlots = getActiveSlots()
      const inputs = axis
        ? activeSlots.map(slot => slot[`${axis}Input`]).filter(Boolean)
        : activeSlots.flatMap(slot => [slot.horizontalInput, slot.verticalInput]).filter(Boolean)
      return inputs.some(valuesDiffer)
    }

    const withSyncGuard = (callback) => {
      group.dataset.syncingRatingOffsets = 'true'
      try {
        callback()
      } finally {
        delete group.dataset.syncingRatingOffsets
      }
    }

    const syncSharedFromSlots = (axis) => {
      const sharedInput = sharedInputs[axis]
      const activeSlots = getActiveSlots()
      const inputs = activeSlots.map(slot => slot[`${axis}Input`]).filter(Boolean)
      if (!sharedInput || !inputs.length || !activeSlots.length) return
      if (group.dataset.syncingRatingOffsets === 'true' || group.dataset.resetting === 'true') {
        sharedInput.dataset.prevValue = String(sharedInput.value ?? '')
        return
      }
      const defaults = getPlacementDefaults()
      const baseOffsets = computeRatingOffsets()
      const hPos = getHorizontalPosition()
      const vPos = getVerticalPosition()
      const deltas = activeSlots.map(slot => {
        const baseAxis = axis === 'horizontal'
          ? toNumber(baseOffsets[slot.slot]?.horizontal, 0)
          : toNumber(baseOffsets[slot.slot]?.vertical, 0)
        const currentAxis = toNumber(
          slot[`${axis}Input`]?.value,
          toNumber(slot[`${axis}Input`]?.dataset?.default, baseAxis)
        )
        return currentAxis - baseAxis
      })
      const averageDelta = Math.round(deltas.reduce((sum, value) => sum + value, 0) / deltas.length)
      withSyncGuard(() => {
        const sharedBase = axis === 'horizontal' ? defaults.horizontal : defaults.vertical
        const sharedValue = axis === 'horizontal'
          ? (hPos === 'right' ? sharedBase - averageDelta : sharedBase + averageDelta)
          : (vPos === 'bottom' ? sharedBase - averageDelta : sharedBase + averageDelta)
        sharedInput.value = String(sharedValue)
        sharedInput.dataset.prevValue = String(sharedValue)
        sharedInput.dispatchEvent(new Event('input', { bubbles: true }))
        sharedInput.dispatchEvent(new Event('change', { bubbles: true }))
      })
      updateAdjustedIndicators()
    }

    const syncSlotsFromShared = (axis) => {
      const sharedInput = sharedInputs[axis]
      const activeSlots = getActiveSlots()
      if (!sharedInput || !activeSlots.length) return
      if (group.dataset.syncingRatingOffsets === 'true' || group.dataset.resetting === 'true') {
        sharedInput.dataset.prevValue = String(sharedInput.value ?? '')
        return
      }
      const current = toNumber(sharedInput.value, toNumber(sharedInput.dataset.default, 0))
      sharedInput.dataset.prevValue = String(current)
      const defaults = getPlacementDefaults()
      const baseOffsets = computeRatingOffsets()
      const hPos = getHorizontalPosition()
      const vPos = getVerticalPosition()
      withSyncGuard(() => {
        if (axis === 'horizontal') {
          const sharedBase = defaults.horizontal
          const delta = hPos === 'right' ? (sharedBase - current) : (current - sharedBase)
          activeSlots.forEach(slot => {
            const baseValue = toNumber(baseOffsets[slot.slot]?.horizontal, 0)
            updateInputValue(slot.horizontalInput, baseValue + delta)
          })
          return
        }

        const sharedBase = defaults.vertical
        const delta = vPos === 'bottom' ? (sharedBase - current) : (current - sharedBase)
        activeSlots.forEach(slot => {
          const baseValue = toNumber(baseOffsets[slot.slot]?.vertical, 0)
          updateInputValue(slot.verticalInput, baseValue + delta)
        })
      })
      updateAdjustedIndicators()
    }

    const seedSharedFromSlots = () => {
      const sharedAtDefaults = Object.values(sharedInputs).every(input => !valuesDiffer(input))
      if (!hasExplicitSlotOffsets() || !sharedAtDefaults) return
      if (hasExplicitSlotOffsets('horizontal')) syncSharedFromSlots('horizontal')
      if (hasExplicitSlotOffsets('vertical')) syncSharedFromSlots('vertical')
    }

    applyAlignmentDefaults()
    applyPlacementDefaults()
    applyComputedOffsets()
    seedSharedFromSlots()

    Object.entries(sharedInputs).forEach(([axis, input]) => {
      input.dataset.prevValue = String(input.value ?? '')
      const syncFromShared = () => syncSlotsFromShared(axis)
      input.addEventListener('input', syncFromShared)
      input.addEventListener('change', syncFromShared)
    })

    if (alignmentInput && alignmentInput.dataset.ratingsAlignmentBound !== 'true') {
      const handleAlignmentChange = () => {
        if (group.dataset.resetting === 'true') return
        group.dataset.ratingsBulkUpdate = 'true'
        applyAlignmentDefaults(true)
        applyPlacementDefaults(true)
        applyComputedOffsets(true)
        delete group.dataset.ratingsBulkUpdate
        refreshDerivedOffsets()
      }
      alignmentInput.addEventListener('input', handleAlignmentChange)
      alignmentInput.addEventListener('change', handleAlignmentChange)
      alignmentInput.dataset.ratingsAlignmentBound = 'true'
    }

    if (positionInput && positionInput.dataset.ratingsPositionBound !== 'true') {
      const refreshFromPosition = () => {
        if (group.dataset.resetting === 'true') return
        group.dataset.ratingsBulkUpdate = 'true'
        applyPlacementDefaults(true)
        applyComputedOffsets(true)
        delete group.dataset.ratingsBulkUpdate
        refreshDerivedOffsets()
        updateAdjustedIndicators()
      }
      positionInput.addEventListener('change', refreshFromPosition)
      positionInput.dataset.ratingsPositionBound = 'true'
    }

    if (verticalPositionInput && verticalPositionInput.dataset.ratingsPositionBound !== 'true') {
      const refreshFromVertical = () => {
        if (group.dataset.resetting === 'true') return
        group.dataset.ratingsBulkUpdate = 'true'
        applyPlacementDefaults(true)
        applyComputedOffsets(true)
        delete group.dataset.ratingsBulkUpdate
        refreshDerivedOffsets()
        updateAdjustedIndicators()
      }
      verticalPositionInput.addEventListener('change', refreshFromVertical)
      verticalPositionInput.dataset.ratingsPositionBound = 'true'
    }

    Object.entries(slotInputs).forEach(([axis, inputs]) => {
      inputs.forEach(input => {
        input.addEventListener('change', () => syncSharedFromSlots(axis))
      })
    })

    const refreshDerivedOffsets = () => {
      if (group.dataset.resetting === 'true') return
      const sharedChanged = valuesDiffer(sharedInputs.horizontal) || valuesDiffer(sharedInputs.vertical)
      if (sharedChanged) {
        syncSlotsFromShared('horizontal')
        syncSlotsFromShared('vertical')
        updateAdjustedIndicators()
        return
      }
      if (!hasExplicitSlotOffsets()) {
        applyComputedOffsets()
      }
      updateAdjustedIndicators()
    }

    slotDefs.forEach(slot => {
      if (slot.ratingInput) slot.ratingInput.addEventListener('change', refreshDerivedOffsets)
      if (slot.imageInput) slot.imageInput.addEventListener('change', refreshDerivedOffsets)
    })
    if (metricInputs.backHeight) metricInputs.backHeight.addEventListener('change', refreshDerivedOffsets)
    if (metricInputs.backWidth) metricInputs.backWidth.addEventListener('change', refreshDerivedOffsets)
    if (metricInputs.backPadding) metricInputs.backPadding.addEventListener('change', refreshDerivedOffsets)

    updateAdjustedIndicators()
    group.dataset.ratingsOffsetSyncBound = 'true'
  })
}

function setupAddMissingDependencies (scope) {
  const root = scope || document
  const addMissingToggles = Array.from(root.querySelectorAll('input.template-child-toggle[id*="radarr_add_missing_"], input.template-child-toggle[id*="sonarr_add_missing_"]'))
  if (!addMissingToggles.length) return

  const resolveDependency = (addToggle) => {
    const id = addToggle.id || ''
    const split = id.split('-template_collection_')
    if (split.length !== 2) return null
    const prefix = split[0]
    const tail = split[1]
    let useTail = null
    const radarrMatch = tail.match(/(.+)_radarr_add_missing_(.+)$/)
    if (radarrMatch) {
      useTail = `${radarrMatch[1]}_use_${radarrMatch[2]}`
    } else {
      const sonarrMatch = tail.match(/(.+)_sonarr_add_missing_(.+)$/)
      if (sonarrMatch) {
        useTail = `${sonarrMatch[1]}_use_${sonarrMatch[2]}`
      }
    }
    if (!useTail) return null
    const useToggle = document.getElementById(`${prefix}-template_collection_${useTail}`)
    if (!useToggle) return null
    const parentToggle = addToggle.dataset.parentToggle
      ? document.getElementById(addToggle.dataset.parentToggle)
      : null
    return { useToggle, parentToggle }
  }

  const applyState = (addToggle) => {
    const dependency = resolveDependency(addToggle)
    if (!dependency) return
    const { useToggle } = dependency
    const useReady = useToggle.checked && !useToggle.disabled
    const enabled = useReady
    const row = addToggle.closest('.form-check')
    if (row) row.style.display = useReady ? '' : 'none'
    addToggle.disabled = !enabled
    if (!enabled) {
      addToggle.checked = false
      const hidden = document.querySelector(`input[type="hidden"][name="${addToggle.name}"]`)
      if (hidden) {
        hidden.value = 'false'
        hidden.disabled = false
      }
    }
  }

  addMissingToggles.forEach(addToggle => {
    const dependency = resolveDependency(addToggle)
    if (!dependency) return
    const { useToggle, parentToggle } = dependency

    if (addToggle.dataset.addMissingBound !== 'true') {
      const refresh = () => applyState(addToggle)
      useToggle.addEventListener('change', refresh)
      if (parentToggle) parentToggle.addEventListener('change', refresh)
      addToggle.dataset.addMissingBound = 'true'
    }

    applyState(addToggle)
  })
}

function wireOverlayDetailToggles (scope) {
  const root = scope || document
  root.querySelectorAll('.overlay-details-toggle').forEach(btn => {
    if (btn.dataset.listenerAdded === 'true') return
    const targetId = btn.dataset.sectionId
    const section = targetId ? document.getElementById(targetId) : null
    if (!section) return

    btn.addEventListener('click', () => {
      const isHidden = section.style.display === 'none'
      section.style.display = isHidden ? 'block' : 'none'
      btn.textContent = isHidden ? 'Hide Details' : 'Show Details'
      if (typeof EventHandler !== 'undefined') {
        EventHandler.updateAccordionHighlights()
      }
    })

    btn.dataset.listenerAdded = 'true'
  })
}

function wireOverlayTemplateSections (scope) {
  const root = scope || document
  root.querySelectorAll('.overlay-toggle').forEach((checkbox) => {
    if (checkbox.dataset.overlayTemplateBound === 'true') return
    checkbox.addEventListener('change', function () {
      toggleOverlayTemplateSection(this)
    })
    toggleOverlayTemplateSection(checkbox) // immediate init
    checkbox.dataset.overlayTemplateBound = 'true'
  })

  if (typeof setupParentChildToggleSync === 'function') {
    setupParentChildToggleSync()
  }
}

function showZoomPreviewModal (imageSrc) {
  const zoomImg = document.getElementById('zoom-preview-img')
  const caption = document.getElementById('zoom-preview-caption')
  const modalElement = document.getElementById('zoomPreviewModal')

  if (!modalElement || !zoomImg || !caption) {
    console.error('[Zoom Modal] Required DOM elements missing.')
    return
  }

  // Set image and caption
  zoomImg.src = imageSrc
  caption.textContent = imageSrc.split('/').pop()

  // Ensure Bootstrap Modal is available
  if (typeof bootstrap !== 'undefined' && typeof bootstrap.Modal === 'function') {
    try {
      const modalInstance = bootstrap.Modal.getOrCreateInstance(modalElement)
      modalInstance.show()
    } catch (err) {
      console.error('[Zoom Modal] Failed to show modal:', err)
    }
  } else {
    console.error('[Zoom Modal] Bootstrap Modal not available.')
  }
}
window.showZoomPreviewModal = showZoomPreviewModal
