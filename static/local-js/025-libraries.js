// Static ES-module imports (hoisted). Migrated from window.EventHandler
// in #1346 step 2f -- direct-consumer form of the accordion-highlight
// surface. Both this file and the dynamically-imported modules below
// share the same module instance (ES modules are singletons keyed by
// URL), so importing here is the same object EventHandler.updateAccordionHighlights
// delegates to.
import { updateAccordionHighlights } from '/static/local-js/modules/accordionHighlights.js'

// Load all helper modules in parallel. These publish their symbols
// via window.* shims (same pattern as pathValidation.js).
await Promise.all([
  import('/static/local-js/imageHandler.js'),
  import('/static/local-js/overlayHandler.js'),
  import('/static/local-js/validationHandler.js'),
  import('/static/local-js/eventHandler.js'),
  import('/static/local-js/rgbaPicker.js')
])

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
let lookupLabelAutosaveTimer = null
let libraryCardInitializing = 0

function setLibrariesButtonBusy (button, busy, label = 'Working...') {
  if (!button) return
  if (!button.dataset.librariesBusyOriginalHtml) {
    button.dataset.librariesBusyOriginalHtml = button.innerHTML
  }
  if (!button.dataset.librariesBusyOriginalWidth) {
    const width = button.getBoundingClientRect ? button.getBoundingClientRect().width : 0
    if (width > 0) {
      button.dataset.librariesBusyOriginalWidth = `${Math.ceil(width)}px`
      button.style.minWidth = button.dataset.librariesBusyOriginalWidth
    }
  }
  button.disabled = !!busy
  button.setAttribute('aria-busy', busy ? 'true' : 'false')
  if (busy) {
    button.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>${label}`
  } else {
    button.innerHTML = button.dataset.librariesBusyOriginalHtml || button.innerHTML
    button.removeAttribute('aria-busy')
  }
}

function shouldShowLibrariesButtonSpinner (button) {
  if (!button || button.disabled || button.getAttribute('aria-busy') === 'true') return false
  if (!button.classList.contains('btn')) return false
  if (button.classList.contains('accordion-button') || button.classList.contains('btn-close')) return false
  if (button.matches('[data-bs-dismiss], [data-bs-toggle="collapse"], [data-bs-toggle="dropdown"], [data-bs-toggle="modal"]')) return false
  if (button.matches('[data-toggle-secret-visibility], [data-collection-section-move], [data-section-id]')) return false
  if (button.matches('[data-external-yaml-undo], [data-external-yaml-redo], [data-external-yaml-select-all], [data-external-yaml-search-prev], [data-external-yaml-search-next]')) return false
  if (button.matches('.style-preview-card, .font-picker-card, .overlay-details-toggle')) return false
  if (button.closest('.btn-group') && button.querySelector('.bi-chevron-up, .bi-chevron-down')) return false
  return true
}

function showLibrariesButtonClickSpinner (button, label = 'Working...') {
  if (!shouldShowLibrariesButtonSpinner(button)) return
  const token = String(Date.now())
  button.dataset.librariesClickBusyToken = token
  setLibrariesButtonBusy(button, true, label)
  window.setTimeout(() => {
    if (button.dataset.librariesClickBusyToken !== token) return
    delete button.dataset.librariesClickBusyToken
    setLibrariesButtonBusy(button, false)
  }, 450)
}

function setLibrariesButtonPersistentBusy (button, busy, label = 'Working...') {
  if (busy && button?.dataset?.librariesClickBusyToken) {
    delete button.dataset.librariesClickBusyToken
  }
  setLibrariesButtonBusy(button, busy, label)
}

document.addEventListener('click', event => {
  const button = event.target.closest('button')
  if (!button || !document.body.contains(button)) return
  showLibrariesButtonClickSpinner(button)
}, true)
const dependencyHintConfigs = {
  tautulli: {
    stepKey: '030-tautulli',
    endpoint: '/libraries_tautulli_dependency_hint',
    windowKey: 'QS_TAUTULLI_REQUIREMENT_REASONS'
  },
  tracearr: {
    stepKey: '035-tracearr',
    endpoint: '/libraries_tracearr_dependency_hint',
    windowKey: 'QS_TRACEARR_REQUIREMENT_REASONS'
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
  floppy: {
    stepKey: '067-floppy',
    endpoint: '/libraries_floppy_dependency_hint',
    windowKey: 'QS_FLOPPY_REQUIREMENT_REASONS'
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
  } catch {
    return []
  }
}

const metadataCustomRepoRaw = String(window.QS_SETTINGS_CUSTOM_REPO || '').trim()
const metadataCustomRepoBase = String(window.QS_SETTINGS_CUSTOM_REPO_BASE || '').trim()
const metadataRepoDependencyMessage = 'Metadata file repo entries require Custom Repo to be configured and saved first within the Settings page.'
const collectionRepoDependencyMessage = 'Collection file repo entries require Custom Repo to be configured and saved first within the Settings page.'
const overlayRepoDependencyMessage = 'Overlay file repo entries require Custom Repo to be configured and saved first within the Settings page.'
const playlistRepoDependencyMessage = 'Playlist file repo entries require Custom Repo to be configured and saved first within the Settings page.'

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

function ensureLibrariesModalRoot (modalEl) {
  if (!modalEl || !document.body) return modalEl
  const modalId = modalEl.id
  modalEl.dataset.librariesModal = 'true'
  if (modalId) {
    const bodyModal = Array.from(document.body.querySelectorAll('[data-libraries-modal]'))
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

function syncLibrariesModalBackdrop (modalEl) {
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

function cleanupLibrariesModalBackdrops () {
  if (document.querySelector('.modal.show')) return
  document.querySelectorAll('.modal-backdrop').forEach(backdrop => backdrop.remove())
}

function queueLibrariesModalBackdropSync (modalEl) {
  if (window && typeof window.requestAnimationFrame === 'function') {
    window.requestAnimationFrame(() => syncLibrariesModalBackdrop(modalEl))
    return
  }
  syncLibrariesModalBackdrop(modalEl)
}

function prepareLibrariesModal (modalEl) {
  if (!modalEl) return modalEl
  modalEl = ensureLibrariesModalRoot(modalEl)
  if (modalEl.dataset.librariesModalPrepared === 'true') return modalEl
  modalEl.dataset.librariesModalPrepared = 'true'
  modalEl.addEventListener('show.bs.modal', function () {
    syncLibrariesModalBackdrop(modalEl)
    queueLibrariesModalBackdropSync(modalEl)
  })
  modalEl.addEventListener('shown.bs.modal', function () {
    syncLibrariesModalBackdrop(modalEl)
  })
  modalEl.addEventListener('hidden.bs.modal', function () {
    cleanupLibrariesModalBackdrops()
  })
  return modalEl
}

function hideLibrariesModal (modalEl) {
  if (!modalEl || typeof bootstrap === 'undefined' || !bootstrap.Modal) return
  const modal = bootstrap.Modal.getInstance(modalEl)
  if (modal) modal.hide()
}

function parsePlaylistUserInputValue (value) {
  if (Array.isArray(value)) {
    return value.map(item => String(item || '').trim()).filter(Boolean)
  }
  const text = String(value || '').trim()
  if (!text) return []
  if (text.startsWith('[') && text.endsWith(']')) {
    try {
      const parsed = JSON.parse(text)
      if (Array.isArray(parsed)) {
        return parsed.map(item => String(item || '').trim()).filter(Boolean)
      }
    } catch {}
  }
  return text.split(',').map(item => item.trim()).filter(Boolean)
}

function initPlaylistUserPickers (scope) {
  const root = scope || document
  root.querySelectorAll('[data-playlist-user-picker]').forEach(wrapper => {
    if (wrapper.dataset.playlistUserPickerReady === 'true') return
    const inputId = String(wrapper.dataset.inputId || '').trim()
    const modalId = String(wrapper.dataset.modalId || '').trim()
    const allowAll = String(wrapper.dataset.allowAll || '').trim().toLowerCase() === 'true'
    const input = inputId ? document.getElementById(inputId) : wrapper.querySelector('[data-playlist-user-input]')
    let modalEl = modalId ? document.getElementById(modalId) : wrapper.querySelector('.modal')
    if (!input || !modalEl) return

    modalEl = prepareLibrariesModal(modalEl)
    const applyButton = modalEl.querySelector('[data-playlist-user-apply]')
    const allToggle = modalEl.querySelector('[data-playlist-user-all-toggle]')

    const syncTogglesFromInput = () => {
      const selected = parsePlaylistUserInputValue(input.value)
      const hasAll = selected.includes('all')
      if (allowAll && allToggle) {
        allToggle.checked = hasAll
      }
      modalEl.querySelectorAll('[data-playlist-user-toggle]').forEach(toggle => {
        toggle.checked = !hasAll && selected.includes(toggle.value)
      })
    }

    if (modalEl.dataset.playlistUserModalBound !== 'true') {
      modalEl.addEventListener('show.bs.modal', syncTogglesFromInput)
      modalEl.dataset.playlistUserModalBound = 'true'
    }

    if (applyButton && applyButton.dataset.playlistUserApplyBound !== 'true') {
      applyButton.addEventListener('click', () => {
        const values = []
        if (allowAll && allToggle && allToggle.checked) {
          values.push('all')
        } else {
          modalEl.querySelectorAll('[data-playlist-user-toggle]:checked').forEach(toggle => {
            values.push(toggle.value)
          })
        }
        input.value = values.join(', ')
        input.dispatchEvent(new Event('input', { bubbles: true }))
        input.dispatchEvent(new Event('change', { bubbles: true }))
        hideLibrariesModal(modalEl)
      })
      applyButton.dataset.playlistUserApplyBound = 'true'
    }

    const normalizedValues = parsePlaylistUserInputValue(input.value)
    input.value = normalizedValues.join(', ')
    wrapper.dataset.playlistUserPickerReady = 'true'
  })
}

function initPlaylistKeyToggleGroups (scope) {
  const root = scope || document
  root.querySelectorAll('[data-playlist-key-toggle-group]').forEach(wrapper => {
    if (wrapper.dataset.playlistKeyToggleReady === 'true') return
    const hiddenId = String(wrapper.dataset.hiddenInput || '').trim()
    const hidden = hiddenId ? document.getElementById(hiddenId) : wrapper.querySelector('input[type="hidden"]')
    const toggles = Array.from(wrapper.querySelectorAll('[data-playlist-key-toggle]'))
    if (!hidden || !toggles.length) return

    const parseStoredMapping = () => {
      const raw = String(hidden.value || '').trim()
      if (!raw) return {}
      try {
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          return parsed
        }
      } catch {}
      return {}
    }

    const isFalseValue = (value) => {
      if (value === false || value === 0) return true
      const text = String(value ?? '').trim().toLowerCase()
      return text === 'false' || text === '0' || text === 'off' || text === 'no'
    }

    const syncFromHidden = () => {
      const mapping = parseStoredMapping()
      toggles.forEach(toggle => {
        const key = String(toggle.dataset.playlistKey || '').trim()
        if (!key) return
        const storedValue = Object.prototype.hasOwnProperty.call(mapping, key) ? mapping[key] : undefined
        toggle.checked = storedValue === undefined ? true : !isFalseValue(storedValue)
      })
    }

    const syncToHidden = () => {
      const mapping = parseStoredMapping()
      toggles.forEach(toggle => {
        const key = String(toggle.dataset.playlistKey || '').trim()
        if (!key) return
        if (toggle.checked) {
          delete mapping[key]
        } else {
          mapping[key] = false
        }
      })
      hidden.value = JSON.stringify(mapping)
      hidden.dispatchEvent(new Event('input', { bubbles: true }))
      hidden.dispatchEvent(new Event('change', { bubbles: true }))
    }

    toggles.forEach(toggle => {
      toggle.addEventListener('change', syncToHidden)
    })
    hidden.addEventListener('change', syncFromHidden)
    syncFromHidden()
    wrapper.dataset.playlistKeyToggleReady = 'true'
  })
}

function getActiveConfigName () {
  const selected = String(document.querySelector('[name="configSelector"]')?.value || '').trim()
  if (selected && selected !== 'add_config') return selected
  return String(document.querySelector('[name="newConfigName"]')?.value || '').trim()
}

const externalYamlEditorKinds = {
  metadata_files: {
    label: 'Metadata file',
    defaultFilename: 'metadata.yml',
    typeSelector: '[data-metadata-file-type]',
    locationSelector: '[data-metadata-file-location]',
    rowSelector: '[data-metadata-file-row]',
    editorSelector: '[data-metadata-files-editor]',
    setStatus: setMetadataFileStatus,
    sync: syncMetadataFilesEditor
  },
  collection_files: {
    label: 'Collection file',
    defaultFilename: 'collections.yml',
    typeSelector: '[data-collection-file-type]',
    locationSelector: '[data-collection-file-location]',
    rowSelector: '[data-collection-file-row]',
    editorSelector: '[data-collection-files-editor]',
    setStatus: setCollectionFileStatus,
    sync: syncCollectionFilesEditor
  },
  overlay_files: {
    label: 'Overlay file',
    defaultFilename: 'overlays.yml',
    typeSelector: '[data-overlay-file-type]',
    locationSelector: '[data-overlay-file-location]',
    rowSelector: '[data-overlay-file-row]',
    editorSelector: '[data-overlay-files-editor]',
    setStatus: setOverlayFileStatus,
    sync: syncOverlayFilesEditor
  },
  playlist_files: {
    label: 'Playlist file',
    defaultFilename: 'playlists.yml',
    typeSelector: '[data-playlist-file-type]',
    locationSelector: '[data-playlist-file-location]',
    rowSelector: '[data-playlist-file-row]',
    editorSelector: '[data-playlist-files-editor]',
    setStatus: setPlaylistFileStatus,
    sync: syncPlaylistFilesEditor
  }
}

let externalYamlModalState = null

function getExternalYamlEditorConfig (kind) {
  return externalYamlEditorKinds[String(kind || '').trim()] || null
}

function updateExternalYamlEditButton (row, kind) {
  const config = getExternalYamlEditorConfig(kind)
  if (!row || !config) return
  const button = row.querySelector(`[data-external-yaml-edit][data-external-yaml-kind="${kind}"]`)
  if (!button) return
  const type = String(row.querySelector(config.typeSelector)?.value || '').trim().toLowerCase()
  const location = String(row.querySelector(config.locationSelector)?.value || '').trim()
  button.disabled = false
  if (type === 'folder') {
    button.textContent = 'Choose File'
    button.disabled = !location
    button.title = location ? 'Choose a local YAML file inside this folder to edit.' : 'Enter a folder path first.'
  } else if (['url', 'git', 'repo'].includes(type)) {
    button.textContent = 'Copy Local'
    button.disabled = !location
    button.title = location ? 'Copy this remote YAML source to a local editable file.' : 'Enter a remote YAML source first.'
  } else if (type === 'file' || !type) {
    button.textContent = location ? 'Edit' : 'Create'
    button.title = ''
  } else {
    button.disabled = true
    button.textContent = 'Edit'
    button.title = 'This source type is not editable in Quickstart.'
  }
}

function getExternalYamlModal () {
  let modalEl = document.getElementById('externalYamlEditorModal')
  if (modalEl) return prepareLibrariesModal(modalEl)
  modalEl = document.createElement('div')
  modalEl.className = 'modal fade'
  modalEl.id = 'externalYamlEditorModal'
  modalEl.tabIndex = -1
  modalEl.setAttribute('aria-hidden', 'true')
  modalEl.innerHTML = `
    <div class="modal-dialog modal-xl modal-dialog-scrollable">
      <div class="modal-content bg-dark text-light">
        <div class="modal-header">
          <h5 class="modal-title" data-external-yaml-title>Edit YAML file</h5>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
        </div>
        <div class="modal-body">
          <div class="alert alert-info small">
            YAML syntax errors block saving. Schema warnings are reported but do not block saving.
          </div>
          <div class="alert alert-warning small d-none" data-external-yaml-copy-warning>
            This remote source will be saved as a local Quickstart-managed file. After saving, the row will use the local copy and will not track upstream remote changes.
          </div>
          <div class="border rounded p-3 mb-3 d-none" data-external-yaml-folder-panel>
            <label class="form-label small text-muted" for="externalYamlEditorFolderFile">Folder YAML file</label>
            <select class="form-select mb-2" id="externalYamlEditorFolderFile" data-external-yaml-folder-file></select>
            <div class="input-group input-group-sm">
              <span class="input-group-text">New file</span>
              <input type="text" class="form-control" placeholder="custom.yml" data-external-yaml-folder-new>
              <button type="button" class="btn btn-outline-primary" data-external-yaml-folder-create>Use New File</button>
            </div>
            <div class="form-text">Only top-level .yml and .yaml files in this folder are listed.</div>
          </div>
          <label class="form-label small text-muted" for="externalYamlEditorLocation">Location</label>
          <input type="text" class="form-control mb-3" id="externalYamlEditorLocation" data-external-yaml-location>
          <div class="external-yaml-editor-toolbar">
            <label class="form-label small text-muted mb-0" for="externalYamlEditorContent">YAML</label>
            <div class="external-yaml-editor-actions">
              <div class="external-yaml-search" data-external-yaml-search>
                <input type="search" class="form-control form-control-sm" placeholder="Search YAML" aria-label="Search YAML" data-external-yaml-search-input>
                <button type="button" class="btn btn-outline-secondary btn-sm" data-external-yaml-search-prev title="Previous match" disabled>
                  <i class="bi bi-chevron-up"></i>
                </button>
                <button type="button" class="btn btn-outline-secondary btn-sm" data-external-yaml-search-next title="Next match" disabled>
                  <i class="bi bi-chevron-down"></i>
                </button>
                <span class="external-yaml-search-count" data-external-yaml-search-count></span>
              </div>
              <button type="button" class="btn btn-outline-secondary btn-sm" data-external-yaml-select-all>
                Select All
              </button>
              <button type="button" class="btn btn-outline-secondary btn-sm" data-external-yaml-undo disabled>
                <i class="bi bi-arrow-counterclockwise"></i> Undo
              </button>
              <button type="button" class="btn btn-outline-secondary btn-sm" data-external-yaml-redo disabled>
                <i class="bi bi-arrow-clockwise"></i> Redo
              </button>
            </div>
          </div>
          <div class="external-yaml-status-banner d-none" data-external-yaml-status></div>
          <div class="external-yaml-editor-shell">
            <div class="external-yaml-editor-lines" aria-hidden="true" data-external-yaml-lines></div>
            <textarea class="form-control font-monospace external-yaml-editor-content" id="externalYamlEditorContent" data-external-yaml-content rows="22" spellcheck="false" wrap="off"></textarea>
          </div>
          <div class="external-yaml-editor-help small text-muted mt-2">
            Line numbers are clickable from validation results. Pressing Tab inserts two spaces.
          </div>
          <div class="external-yaml-status-details mt-3 small d-none" data-external-yaml-status></div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-outline-info" data-external-yaml-validate>Validate YAML</button>
          <button type="button" class="btn btn-success" data-external-yaml-save>Save</button>
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  `
  document.body.appendChild(modalEl)
  initExternalYamlEditor(modalEl)
  modalEl.addEventListener('hide.bs.modal', event => {
    if (externalYamlModalState?.allowCloseOnce) {
      externalYamlModalState.allowCloseOnce = false
      return
    }
    if (!isExternalYamlEditorDirty(modalEl)) return
    const discard = window.confirm('Discard unsaved YAML changes?')
    if (!discard) {
      event.preventDefault()
    }
  })
  return prepareLibrariesModal(modalEl)
}

function getExternalYamlContentInput (modalEl) {
  return modalEl?.querySelector('[data-external-yaml-content]') || null
}

function getExternalYamlContent (modalEl) {
  return getExternalYamlContentInput(modalEl)?.value || ''
}

function getExternalYamlLocation (modalEl) {
  return modalEl?.querySelector('[data-external-yaml-location]')?.value || ''
}

function externalYamlValidationSummary (validation, prefix = 'Validation complete.', savedLocation = '') {
  const issues = Array.isArray(validation?.issues) ? validation.issues : []
  const warnings = Array.isArray(validation?.warnings) ? validation.warnings : []
  const errorCount = issues.filter(issue => issue?.severity === 'error').length
  const warningCount = warnings.length || issues.filter(issue => issue?.severity !== 'error').length
  const locationSuffix = savedLocation ? ` Saved to ${savedLocation}.` : ''
  if (!validation?.can_save) {
    const location = issues.find(issue => issue?.line)?.line
    const lineSuffix = location ? ` Check line ${location}.` : ''
    return `${validation?.error || 'YAML syntax validation failed.'}${lineSuffix}`
  }
  if (warningCount) {
    return `${prefix} YAML is valid with ${warningCount} schema warning${warningCount === 1 ? '' : 's'}.${locationSuffix}`
  }
  if (errorCount) {
    return `${prefix} YAML has ${errorCount} error${errorCount === 1 ? '' : 's'}.${locationSuffix}`
  }
  return `${prefix} YAML and schema validation passed.${locationSuffix}`
}

function setExternalYamlDirtyState (modalEl, dirty) {
  if (!externalYamlModalState) return
  externalYamlModalState.dirty = Boolean(dirty)
  const title = modalEl?.querySelector('[data-external-yaml-title]')
  if (title) {
    const baseTitle = externalYamlModalState.baseTitle || title.textContent.replace(/\s+\*$/, '')
    externalYamlModalState.baseTitle = baseTitle
    title.textContent = `${baseTitle}${externalYamlModalState.dirty ? ' *' : ''}`
  }
}

function isExternalYamlEditorDirty (modalEl) {
  if (!externalYamlModalState) return false
  const savedContent = externalYamlModalState.savedContent ?? ''
  const savedLocation = externalYamlModalState.savedLocation ?? ''
  return getExternalYamlContent(modalEl) !== savedContent || getExternalYamlLocation(modalEl) !== savedLocation
}

function syncExternalYamlDirtyState (modalEl) {
  setExternalYamlDirtyState(modalEl, isExternalYamlEditorDirty(modalEl))
}

function markExternalYamlEditorClean (modalEl, location = null) {
  if (!externalYamlModalState) return
  if (location !== null) {
    const locationInput = modalEl?.querySelector('[data-external-yaml-location]')
    if (locationInput) locationInput.value = location || ''
  }
  externalYamlModalState.savedContent = getExternalYamlContent(modalEl)
  externalYamlModalState.savedLocation = getExternalYamlLocation(modalEl)
  setExternalYamlDirtyState(modalEl, false)
}

function issueLineSet (issues) {
  const lines = new Set()
  if (!Array.isArray(issues)) return lines
  issues.forEach(issue => {
    const line = Number(issue?.line)
    if (Number.isInteger(line) && line > 0) lines.add(line)
  })
  return lines
}

function syncExternalYamlEditorLineNumbers (modalEl) {
  const contentInput = getExternalYamlContentInput(modalEl)
  const gutter = modalEl?.querySelector('[data-external-yaml-lines]')
  if (!contentInput || !gutter) return
  const lineCount = Math.max(1, contentInput.value.split(/\r\n|\r|\n/).length)
  const markedLines = issueLineSet(externalYamlModalState?.issues)
  gutter.replaceChildren()
  for (let line = 1; line <= lineCount; line += 1) {
    const lineEl = document.createElement('button')
    lineEl.type = 'button'
    lineEl.className = 'external-yaml-editor-line'
    lineEl.textContent = String(line)
    lineEl.dataset.externalYamlLine = String(line)
    if (markedLines.has(line)) lineEl.classList.add('external-yaml-editor-line--issue')
    gutter.appendChild(lineEl)
  }
  gutter.scrollTop = contentInput.scrollTop
}

function setExternalYamlEditorContent (modalEl, content) {
  const contentInput = getExternalYamlContentInput(modalEl)
  if (!contentInput) return
  contentInput.value = String(content || '')
  syncExternalYamlEditorLineNumbers(modalEl)
  resetExternalYamlUndoHistory(modalEl)
  resetExternalYamlSearch(modalEl)
}

function externalYamlHistoryState () {
  if (!externalYamlModalState) return null
  if (!externalYamlModalState.history) {
    externalYamlModalState.history = { stack: [], index: -1, applying: false, timer: null }
  }
  return externalYamlModalState.history
}

function updateExternalYamlUndoRedoButtons (modalEl) {
  const history = externalYamlHistoryState()
  const undoButton = modalEl?.querySelector('[data-external-yaml-undo]')
  const redoButton = modalEl?.querySelector('[data-external-yaml-redo]')
  const canUndo = Boolean(history && history.index > 0)
  const canRedo = Boolean(history && history.index >= 0 && history.index < history.stack.length - 1)
  if (undoButton) undoButton.disabled = !canUndo
  if (redoButton) redoButton.disabled = !canRedo
}

function resetExternalYamlUndoHistory (modalEl) {
  const history = externalYamlHistoryState()
  if (!history) return
  if (history.timer) {
    window.clearTimeout(history.timer)
    history.timer = null
  }
  history.stack = [getExternalYamlContent(modalEl)]
  history.index = 0
  history.applying = false
  updateExternalYamlUndoRedoButtons(modalEl)
}

function captureExternalYamlUndoHistory (modalEl) {
  const history = externalYamlHistoryState()
  if (!history || history.applying) return
  const content = getExternalYamlContent(modalEl)
  if (history.index >= 0 && history.stack[history.index] === content) {
    updateExternalYamlUndoRedoButtons(modalEl)
    return
  }
  if (history.index < history.stack.length - 1) {
    history.stack = history.stack.slice(0, history.index + 1)
  }
  history.stack.push(content)
  if (history.stack.length > 100) {
    history.stack.shift()
  }
  history.index = history.stack.length - 1
  updateExternalYamlUndoRedoButtons(modalEl)
}

function scheduleExternalYamlUndoHistoryCapture (modalEl) {
  const history = externalYamlHistoryState()
  if (!history || history.applying) return
  if (history.timer) window.clearTimeout(history.timer)
  history.timer = window.setTimeout(() => {
    history.timer = null
    captureExternalYamlUndoHistory(modalEl)
  }, 250)
}

function applyExternalYamlUndoHistory (modalEl, direction) {
  const history = externalYamlHistoryState()
  const contentInput = getExternalYamlContentInput(modalEl)
  if (!history || !contentInput) return
  const nextIndex = history.index + direction
  if (nextIndex < 0 || nextIndex >= history.stack.length) return
  if (history.timer) {
    window.clearTimeout(history.timer)
    history.timer = null
    captureExternalYamlUndoHistory(modalEl)
  }
  history.applying = true
  history.index = nextIndex
  contentInput.value = history.stack[history.index]
  const cursor = contentInput.value.length
  contentInput.setSelectionRange(cursor, cursor)
  syncExternalYamlEditorLineNumbers(modalEl)
  history.applying = false
  updateExternalYamlUndoRedoButtons(modalEl)
  syncExternalYamlDirtyState(modalEl)
  updateExternalYamlSearch(modalEl)
}

function externalYamlSearchState () {
  if (!externalYamlModalState) return null
  if (!externalYamlModalState.search) {
    externalYamlModalState.search = { query: '', matches: [], index: -1 }
  }
  return externalYamlModalState.search
}

function updateExternalYamlSearchControls (modalEl) {
  const state = externalYamlSearchState()
  const prevButton = modalEl?.querySelector('[data-external-yaml-search-prev]')
  const nextButton = modalEl?.querySelector('[data-external-yaml-search-next]')
  const count = modalEl?.querySelector('[data-external-yaml-search-count]')
  const hasMatches = Boolean(state && state.matches.length)
  if (prevButton) prevButton.disabled = !hasMatches
  if (nextButton) nextButton.disabled = !hasMatches
  if (count) {
    count.textContent = !state?.query ? '' : (hasMatches ? `${state.index + 1}/${state.matches.length}` : '0 matches')
  }
}

function resetExternalYamlSearch (modalEl) {
  const state = externalYamlSearchState()
  if (!state) return
  state.query = ''
  state.matches = []
  state.index = -1
  const input = modalEl?.querySelector('[data-external-yaml-search-input]')
  if (input) input.value = ''
  updateExternalYamlSearchControls(modalEl)
}

function updateExternalYamlSearch (modalEl, preserveIndex = true) {
  const state = externalYamlSearchState()
  const input = modalEl?.querySelector('[data-external-yaml-search-input]')
  if (!state || !input) return
  const query = String(input.value || '')
  const content = getExternalYamlContent(modalEl)
  const previousIndex = preserveIndex ? state.index : -1
  state.query = query
  state.matches = []
  state.index = -1
  if (query) {
    const lowerContent = content.toLowerCase()
    const lowerQuery = query.toLowerCase()
    let offset = lowerContent.indexOf(lowerQuery)
    while (offset !== -1) {
      state.matches.push(offset)
      offset = lowerContent.indexOf(lowerQuery, offset + Math.max(1, lowerQuery.length))
    }
    if (state.matches.length) {
      state.index = Math.min(Math.max(0, previousIndex), state.matches.length - 1)
    }
  }
  updateExternalYamlSearchControls(modalEl)
}

function jumpExternalYamlSearch (modalEl, direction) {
  const state = externalYamlSearchState()
  const contentInput = getExternalYamlContentInput(modalEl)
  if (!state || !contentInput) return
  updateExternalYamlSearch(modalEl)
  if (!state.matches.length) return
  state.index = (state.index + direction + state.matches.length) % state.matches.length
  const offset = state.matches[state.index]
  const queryLength = String(state.query || '').length
  contentInput.focus()
  contentInput.setSelectionRange(offset, offset + queryLength)
  updateExternalYamlSearchControls(modalEl)
}

function externalYamlOffsetForLineColumn (content, line, column) {
  const lines = String(content || '').split(/\r\n|\r|\n/)
  const targetLine = Math.max(1, Number(line) || 1)
  const targetColumn = Math.max(1, Number(column) || 1)
  let offset = 0
  for (let index = 0; index < Math.min(targetLine - 1, lines.length); index += 1) {
    offset += lines[index].length + 1
  }
  return Math.min(String(content || '').length, offset + targetColumn - 1)
}

function jumpExternalYamlEditorToIssue (modalEl, issue) {
  const contentInput = getExternalYamlContentInput(modalEl)
  if (!contentInput || !issue?.line) return
  const offset = externalYamlOffsetForLineColumn(contentInput.value, issue.line, issue.column || 1)
  contentInput.focus()
  contentInput.setSelectionRange(offset, offset)
  const lineHeight = Number.parseFloat(window.getComputedStyle(contentInput).lineHeight) || 20
  contentInput.scrollTop = Math.max(0, (Number(issue.line) - 4) * lineHeight)
  syncExternalYamlEditorLineNumbers(modalEl)
}

function initExternalYamlEditor (modalEl) {
  const contentInput = getExternalYamlContentInput(modalEl)
  if (!contentInput || contentInput.dataset.externalYamlEditorReady === 'true') return
  contentInput.dataset.externalYamlEditorReady = 'true'
  contentInput.addEventListener('input', () => {
    const history = externalYamlHistoryState()
    if (externalYamlModalState) {
      externalYamlModalState.issues = []
    }
    syncExternalYamlEditorLineNumbers(modalEl)
    if (!history?.applying) {
      syncExternalYamlDirtyState(modalEl)
      updateExternalYamlSearch(modalEl)
      renderExternalYamlStatus(
        modalEl.querySelector('[data-external-yaml-status]'),
        'warning',
        'Edited since last validation. Validate YAML or Save to check this file.'
      )
      scheduleExternalYamlUndoHistoryCapture(modalEl)
    }
  })
  contentInput.addEventListener('scroll', () => {
    const gutter = modalEl.querySelector('[data-external-yaml-lines]')
    if (gutter) gutter.scrollTop = contentInput.scrollTop
  })
  contentInput.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === 'z') {
      event.preventDefault()
      applyExternalYamlUndoHistory(modalEl, -1)
      return
    }
    if ((event.ctrlKey || event.metaKey) && (event.key.toLowerCase() === 'y' || (event.shiftKey && event.key.toLowerCase() === 'z'))) {
      event.preventDefault()
      applyExternalYamlUndoHistory(modalEl, 1)
      return
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') {
      event.preventDefault()
      modalEl.querySelector('[data-external-yaml-search-input]')?.focus()
      return
    }
    if (event.key !== 'Tab') return
    event.preventDefault()
    const start = contentInput.selectionStart
    const end = contentInput.selectionEnd
    const indent = '  '
    contentInput.value = `${contentInput.value.slice(0, start)}${indent}${contentInput.value.slice(end)}`
    const cursor = start + indent.length
    contentInput.setSelectionRange(cursor, cursor)
    contentInput.dispatchEvent(new Event('input', { bubbles: true }))
  })
  const searchInput = modalEl.querySelector('[data-external-yaml-search-input]')
  if (searchInput && searchInput.dataset.externalYamlSearchReady !== 'true') {
    searchInput.dataset.externalYamlSearchReady = 'true'
    searchInput.addEventListener('input', () => updateExternalYamlSearch(modalEl, false))
    searchInput.addEventListener('keydown', event => {
      if (event.key !== 'Enter') return
      event.preventDefault()
      jumpExternalYamlSearch(modalEl, event.shiftKey ? -1 : 1)
    })
  }
  const locationInput = modalEl.querySelector('[data-external-yaml-location]')
  if (locationInput && locationInput.dataset.externalYamlLocationReady !== 'true') {
    locationInput.dataset.externalYamlLocationReady = 'true'
    locationInput.addEventListener('input', () => {
      syncExternalYamlDirtyState(modalEl)
      renderExternalYamlStatus(
        modalEl.querySelector('[data-external-yaml-status]'),
        'warning',
        'Location edited. Save to write this YAML file to the new target.'
      )
    })
  }
}

function renderExternalYamlStatus (target, type, message, warnings = []) {
  if (!target) return
  const modalEl = target.closest('.modal') || document
  const targets = Array.from(modalEl.querySelectorAll('[data-external-yaml-status]'))
  const renderTargets = targets.length ? targets : [target]
  renderTargets.forEach(statusTarget => {
    const isBanner = statusTarget.classList.contains('external-yaml-status-banner')
    statusTarget.replaceChildren()
    statusTarget.className = isBanner ? 'external-yaml-status-banner' : 'external-yaml-status-details mt-3 small'
    statusTarget.classList.remove('d-none')
    statusTarget.classList.add(`external-yaml-status--${type === 'error' ? 'error' : (type === 'success' ? 'success' : 'warning')}`)
    const summary = document.createElement('div')
    summary.textContent = message || ''
    statusTarget.appendChild(summary)
    if (!isBanner && warnings.length) {
      const list = document.createElement('ul')
      list.className = 'mb-0 mt-2 ps-3'
      warnings.forEach(warning => {
        const item = document.createElement('li')
        item.textContent = String(warning || '')
        list.appendChild(item)
      })
      statusTarget.appendChild(list)
    }
  })
}

function renderExternalYamlIssueList (target, issues) {
  if (!target || !Array.isArray(issues) || !issues.length) return
  const list = document.createElement('div')
  list.className = 'external-yaml-issue-list mt-2'
  issues.forEach(issue => {
    const item = document.createElement('button')
    item.type = 'button'
    item.className = `external-yaml-issue external-yaml-issue--${issue.severity === 'error' ? 'error' : 'warning'}`
    const location = issue.line ? `Line ${issue.line}${issue.column ? `:${issue.column}` : ''}` : (issue.path ? issue.path : issue.source || 'YAML')
    item.textContent = `${location} - ${issue.message || 'Validation issue'}`
    item.addEventListener('click', () => jumpExternalYamlEditorToIssue(getExternalYamlModal(), issue))
    list.appendChild(item)
  })
  target.appendChild(list)
}

function renderExternalYamlValidationStatus (validation, prefix = 'Validation complete.') {
  const modalEl = getExternalYamlModal()
  const status = modalEl.querySelector('[data-external-yaml-status]')
  const issues = Array.isArray(validation?.issues) ? validation.issues : []
  if (externalYamlModalState) {
    externalYamlModalState.issues = issues
  }
  syncExternalYamlEditorLineNumbers(modalEl)
  if (!validation?.can_save) {
    renderExternalYamlStatus(status, 'error', externalYamlValidationSummary(validation, prefix))
    renderExternalYamlIssueList(modalEl.querySelector('.external-yaml-status-details'), issues)
    return
  }
  const warnings = Array.isArray(validation.warnings) ? validation.warnings : []
  if (warnings.length) {
    renderExternalYamlStatus(status, 'warning', externalYamlValidationSummary(validation, prefix), warnings)
    renderExternalYamlIssueList(modalEl.querySelector('.external-yaml-status-details'), issues)
  } else {
    renderExternalYamlStatus(status, 'success', externalYamlValidationSummary(validation, prefix))
  }
}

function renderExternalYamlSaveStatus (validation, location, prefix = 'Saved.') {
  const modalEl = getExternalYamlModal()
  const status = modalEl.querySelector('[data-external-yaml-status]')
  const issues = Array.isArray(validation?.issues) ? validation.issues : []
  if (externalYamlModalState) {
    externalYamlModalState.issues = issues
  }
  syncExternalYamlEditorLineNumbers(modalEl)
  const warnings = Array.isArray(validation?.warnings) ? validation.warnings : []
  const message = externalYamlValidationSummary(validation, prefix, location)
  if (!validation?.can_save) {
    renderExternalYamlStatus(status, 'error', message)
    renderExternalYamlIssueList(modalEl.querySelector('.external-yaml-status-details'), issues)
  } else if (warnings.length) {
    renderExternalYamlStatus(status, 'warning', message, warnings)
    renderExternalYamlIssueList(modalEl.querySelector('.external-yaml-status-details'), issues)
  } else {
    renderExternalYamlStatus(status, 'success', message)
  }
}

function setExternalYamlModalMode (modalEl, mode) {
  const folderPanel = modalEl.querySelector('[data-external-yaml-folder-panel]')
  const remoteCopyWarning = modalEl.querySelector('[data-external-yaml-copy-warning]')
  folderPanel?.classList.toggle('d-none', mode !== 'folder')
  remoteCopyWarning?.classList.toggle('d-none', mode !== 'remote')
}

function loadExternalYamlEditorPayload (modalEl, payload, prefix) {
  const locationInput = modalEl.querySelector('[data-external-yaml-location]')
  if (locationInput) locationInput.value = payload.location || ''
  setExternalYamlEditorContent(modalEl, payload.content || '')
  markExternalYamlEditorClean(modalEl)
  renderExternalYamlValidationStatus(payload.validation, prefix)
}

function confirmExternalYamlDiscardIfDirty (modalEl) {
  if (!isExternalYamlEditorDirty(modalEl)) return true
  return window.confirm('Discard unsaved YAML changes and load a different file?')
}

function externalYamlFolderNewFileLocation (folderLocation, filename) {
  const folder = String(folderLocation || '').trim().replace(/\\/g, '/').replace(/\/+$/, '')
  const file = String(filename || '').trim().replace(/\\/g, '/').split('/').filter(Boolean).pop() || ''
  if (!folder || !file) return ''
  return `${folder}/${file}`
}

async function loadExternalYamlFileIntoModal (modalEl, kind, location, libraryId, prefix) {
  const response = await fetch('/external_yaml_file/read', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      kind,
      location,
      config_name: getActiveConfigName(),
      library_id: libraryId
    })
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || !payload.success) {
    renderExternalYamlStatus(modalEl.querySelector('[data-external-yaml-status]'), 'error', payload.error || 'YAML file could not be opened.')
    return null
  }
  loadExternalYamlEditorPayload(modalEl, payload, prefix || (payload.created ? 'Create template loaded.' : 'File loaded.'))
  return payload
}

async function validateExternalYamlModalContent () {
  if (!externalYamlModalState) return null
  const modalEl = getExternalYamlModal()
  const response = await fetch('/external_yaml_file/validate', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      kind: externalYamlModalState.kind,
      content: getExternalYamlContent(modalEl)
    })
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || !payload.success) {
    renderExternalYamlStatus(modalEl.querySelector('[data-external-yaml-status]'), 'error', payload.error || 'YAML validation failed.')
    return null
  }
  renderExternalYamlValidationStatus(payload.validation)
  return payload.validation
}

async function saveExternalYamlModalContent () {
  if (!externalYamlModalState) return
  const modalEl = getExternalYamlModal()
  const saveButton = modalEl.querySelector('[data-external-yaml-save]')
  const locationInput = modalEl.querySelector('[data-external-yaml-location]')
  setLibrariesButtonPersistentBusy(saveButton, true, 'Saving...')
  try {
    const response = await fetch('/external_yaml_file/save', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        kind: externalYamlModalState.kind,
        location: locationInput?.value || '',
        content: getExternalYamlContent(modalEl),
        config_name: getActiveConfigName(),
        library_id: externalYamlModalState.libraryId
      })
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok || !payload.success) {
      renderExternalYamlStatus(
        modalEl.querySelector('[data-external-yaml-status]'),
        'error',
        payload.validation?.error || payload.error || 'YAML could not be saved.'
      )
      return
    }

    const config = getExternalYamlEditorConfig(externalYamlModalState.kind)
    const row = externalYamlModalState.row
    const editor = externalYamlModalState.editor
    const rowType = row?.querySelector(config.typeSelector)
    const rowLocation = row?.querySelector(config.locationSelector)
    if (externalYamlModalState.mode === 'remote' && rowType) {
      rowType.value = 'file'
    }
    if (externalYamlModalState.mode !== 'folder' && rowLocation && payload.location) {
      rowLocation.value = payload.location
    }
    const warnings = Array.isArray(payload.validation?.warnings) ? payload.validation.warnings : []
    const savedLocation = String(payload.location || locationInput?.value || '').trim()
    config.setStatus(row, 'success', {
      text: savedLocation ? `Saved ${savedLocation}.` : (payload.message || 'Saved.'),
      files: warnings
    })
    config.sync(editor)
    updateExternalYamlEditButton(row, externalYamlModalState.kind)
    markExternalYamlEditorClean(modalEl, savedLocation)
    renderExternalYamlSaveStatus(payload.validation, savedLocation, payload.message || 'Saved.')
  } catch {
    renderExternalYamlStatus(modalEl.querySelector('[data-external-yaml-status]'), 'error', 'YAML save request failed.')
  } finally {
    setLibrariesButtonPersistentBusy(saveButton, false)
  }
}

async function openExternalYamlEditor (row, kind) {
  const config = getExternalYamlEditorConfig(kind)
  if (!row || !config) return
  const type = String(row.querySelector(config.typeSelector)?.value || '').trim().toLowerCase()
  const location = String(row.querySelector(config.locationSelector)?.value || '').trim()
  const editor = row.closest(config.editorSelector)
  const libraryId = String(editor?.dataset.libraryId || '').trim()
  if (!['file', 'folder', 'url', 'git', 'repo'].includes(type || 'file')) {
    config.setStatus(row, '', 'This source type cannot be edited in Quickstart.')
    return
  }
  if (type !== 'file' && !location) {
    config.setStatus(row, '', 'Enter a source location first.')
    return
  }

  const modalEl = getExternalYamlModal()
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl)
  const mode = type === 'folder' ? 'folder' : (['url', 'git', 'repo'].includes(type) ? 'remote' : 'file')
  const titlePrefix = mode === 'folder' ? 'Choose' : (mode === 'remote' ? 'Copy Local' : (location ? 'Edit' : 'Create'))
  const title = `${titlePrefix} ${config.label}`
  modalEl.querySelector('[data-external-yaml-title]').textContent = title
  modalEl.querySelectorAll('[data-external-yaml-status]').forEach(status => status.classList.add('d-none'))
  const locationInput = modalEl.querySelector('[data-external-yaml-location]')
  locationInput.value = location
  locationInput.disabled = mode === 'folder' || (mode === 'file' && Boolean(location))
  setExternalYamlModalMode(modalEl, mode)
  externalYamlModalState = {
    row,
    editor,
    kind,
    libraryId,
    mode,
    sourceType: type,
    folderLocation: mode === 'folder' ? location : '',
    issues: [],
    savedContent: '',
    savedLocation: location,
    dirty: false,
    baseTitle: title
  }
  setExternalYamlEditorContent(modalEl, '')
  syncExternalYamlEditorLineNumbers(modalEl)
  modal.show()

  try {
    if (mode === 'remote') {
      renderExternalYamlStatus(modalEl.querySelector('[data-external-yaml-status]'), 'warning', 'Fetching remote YAML source...')
      const response = await fetch('/external_yaml_file/remote_read', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind,
          source_type: type,
          location,
          config_name: getActiveConfigName(),
          library_id: libraryId
        })
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || !payload.success) {
        renderExternalYamlStatus(modalEl.querySelector('[data-external-yaml-status]'), 'error', payload.error || 'Remote YAML source could not be copied.')
        return
      }
      loadExternalYamlEditorPayload(modalEl, payload, 'Remote source loaded.')
      return
    }

    if (mode === 'folder') {
      renderExternalYamlStatus(modalEl.querySelector('[data-external-yaml-status]'), 'warning', 'Loading folder YAML files...')
      const response = await fetch('/external_yaml_file/folder_files', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind,
          location,
          config_name: getActiveConfigName(),
          library_id: libraryId
        })
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || !payload.success) {
        renderExternalYamlStatus(modalEl.querySelector('[data-external-yaml-status]'), 'error', payload.error || 'Folder YAML files could not be listed.')
        return
      }
      const select = modalEl.querySelector('[data-external-yaml-folder-file]')
      const newInput = modalEl.querySelector('[data-external-yaml-folder-new]')
      select.replaceChildren()
      const files = Array.isArray(payload.files) ? payload.files : []
      files.forEach(file => {
        const option = document.createElement('option')
        option.value = file.location || ''
        option.textContent = file.name || file.location || ''
        select.appendChild(option)
      })
      select.disabled = !files.length
      newInput.value = config.defaultFilename || 'custom.yml'
      externalYamlModalState.folderLocation = payload.folder || location
      if (files.length) {
        await loadExternalYamlFileIntoModal(modalEl, kind, files[0].location, libraryId, 'Folder file loaded.')
      } else {
        const newLocation = externalYamlFolderNewFileLocation(externalYamlModalState.folderLocation, newInput.value)
        await loadExternalYamlFileIntoModal(modalEl, kind, newLocation, libraryId, 'Create template loaded. No YAML files were found in this folder.')
      }
      return
    }

    await loadExternalYamlFileIntoModal(modalEl, kind, location, libraryId)
  } catch {
    renderExternalYamlStatus(modalEl.querySelector('[data-external-yaml-status]'), 'error', 'YAML file could not be opened.')
  }
}

document.addEventListener('click', async function (event) {
  const editButton = event.target.closest('[data-external-yaml-edit]')
  if (editButton) {
    const kind = String(editButton.dataset.externalYamlKind || '').trim()
    const config = getExternalYamlEditorConfig(kind)
    const row = config ? editButton.closest(config.rowSelector) : null
    await openExternalYamlEditor(row, kind)
    return
  }

  const validateButton = event.target.closest('[data-external-yaml-validate]')
  if (validateButton) {
    setLibrariesButtonPersistentBusy(validateButton, true, 'Validating...')
    try {
      await validateExternalYamlModalContent()
    } finally {
      setLibrariesButtonPersistentBusy(validateButton, false)
    }
    return
  }

  const saveButton = event.target.closest('[data-external-yaml-save]')
  if (saveButton) {
    await saveExternalYamlModalContent()
    return
  }

  const undoButton = event.target.closest('[data-external-yaml-undo]')
  if (undoButton) {
    applyExternalYamlUndoHistory(getExternalYamlModal(), -1)
    return
  }

  const redoButton = event.target.closest('[data-external-yaml-redo]')
  if (redoButton) {
    applyExternalYamlUndoHistory(getExternalYamlModal(), 1)
    return
  }

  const selectAllButton = event.target.closest('[data-external-yaml-select-all]')
  if (selectAllButton) {
    const contentInput = getExternalYamlContentInput(getExternalYamlModal())
    if (contentInput) {
      contentInput.focus()
      contentInput.select()
    }
    return
  }

  const searchPrevButton = event.target.closest('[data-external-yaml-search-prev]')
  if (searchPrevButton) {
    jumpExternalYamlSearch(getExternalYamlModal(), -1)
    return
  }

  const searchNextButton = event.target.closest('[data-external-yaml-search-next]')
  if (searchNextButton) {
    jumpExternalYamlSearch(getExternalYamlModal(), 1)
    return
  }

  const folderCreateButton = event.target.closest('[data-external-yaml-folder-create]')
  if (folderCreateButton) {
    const modalEl = getExternalYamlModal()
    const newInput = modalEl.querySelector('[data-external-yaml-folder-new]')
    const filename = String(newInput?.value || '').trim()
    if (!externalYamlModalState || externalYamlModalState.mode !== 'folder') return
    if (!filename.toLowerCase().endsWith('.yml') && !filename.toLowerCase().endsWith('.yaml')) {
      renderExternalYamlStatus(modalEl.querySelector('[data-external-yaml-status]'), 'error', 'New YAML file name must end with .yml or .yaml.')
      return
    }
    if (!confirmExternalYamlDiscardIfDirty(modalEl)) return
    const newLocation = externalYamlFolderNewFileLocation(externalYamlModalState.folderLocation, filename)
    await loadExternalYamlFileIntoModal(modalEl, externalYamlModalState.kind, newLocation, externalYamlModalState.libraryId, 'Create template loaded.')
  }
})

document.addEventListener('input', function (event) {
  const target = event.target
  if (!target) return
  Object.entries(externalYamlEditorKinds).forEach(([kind, config]) => {
    if (!target.matches(`${config.typeSelector}, ${config.locationSelector}`)) return
    const row = target.closest(config.rowSelector)
    updateExternalYamlEditButton(row, kind)
  })

})

window.addEventListener('beforeunload', event => {
  const modalEl = document.getElementById('externalYamlEditorModal')
  if (!modalEl || !isExternalYamlEditorDirty(modalEl)) return
  event.preventDefault()
  event.returnValue = ''
})

document.addEventListener('change', function (event) {
  const target = event.target
  if (!target) return
  Object.entries(externalYamlEditorKinds).forEach(([kind, config]) => {
    if (!target.matches(`${config.typeSelector}, ${config.locationSelector}`)) return
    const row = target.closest(config.rowSelector)
    updateExternalYamlEditButton(row, kind)
  })

  if (target.matches('[data-external-yaml-folder-file]')) {
    const location = String(target.value || '').trim()
    if (!externalYamlModalState || externalYamlModalState.mode !== 'folder' || !location) return
    const modalEl = getExternalYamlModal()
    if (!confirmExternalYamlDiscardIfDirty(modalEl)) {
      target.value = externalYamlModalState.savedLocation || ''
      return
    }
    loadExternalYamlFileIntoModal(modalEl, externalYamlModalState.kind, location, externalYamlModalState.libraryId, 'Folder file loaded.')
  }
})

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
        <div class="col-md-3 d-flex gap-2 flex-wrap justify-content-md-end">
          <button type="button" class="btn btn-success btn-sm" data-validate-metadata-file>Validate</button>
          <button type="button" class="btn btn-outline-primary btn-sm" data-external-yaml-edit data-external-yaml-kind="metadata_files">Edit</button>
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
  updateExternalYamlEditButton(wrapper, 'metadata_files')
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
        <div class="col-md-3 d-flex gap-2 flex-wrap justify-content-md-end">
          <button type="button" class="btn btn-success btn-sm" data-validate-collection-file>Validate</button>
          <button type="button" class="btn btn-outline-primary btn-sm" data-external-yaml-edit data-external-yaml-kind="collection_files">Edit</button>
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
  updateExternalYamlEditButton(wrapper, 'collection_files')
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
    if (!hasEntries && !hasInvalid) {
      updateAccordionHighlights()
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
    } catch {
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
    } catch {
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
        <div class="col-md-3 d-flex gap-2 flex-wrap justify-content-md-end">
          <button type="button" class="btn btn-success btn-sm" data-validate-overlay-file>Validate</button>
          <button type="button" class="btn btn-outline-primary btn-sm" data-external-yaml-edit data-external-yaml-kind="overlay_files">Edit</button>
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
  updateExternalYamlEditButton(wrapper, 'overlay_files')
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
    if (!hasEntries && !hasInvalid) {
      updateAccordionHighlights()
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
    } catch {
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

function normalizePlaylistFileEntry (entry) {
  if (!entry || typeof entry !== 'object') return null
  const type = String(entry.type || '').trim().toLowerCase()
  const location = String(entry.location || '').trim()
  const validated = entry.validated === true || String(entry.validated || '').trim().toLowerCase() === 'true'
  if (!type && !location) return null
  const normalized = { type, location }
  if (validated) normalized.validated = true
  return normalized
}

function parsePlaylistFilesValue (rawValue) {
  if (!rawValue) return []
  try {
    const parsed = JSON.parse(String(rawValue))
    if (!Array.isArray(parsed)) return []
    return parsed
      .map(normalizePlaylistFileEntry)
      .filter(Boolean)
  } catch {
    return []
  }
}

function buildPlaylistFileRow (entry = {}) {
  const wrapper = document.createElement('div')
  wrapper.className = 'card bg-body-tertiary border-secondary'
  wrapper.setAttribute('data-playlist-file-row', 'true')
  wrapper.innerHTML = `
    <div class="card-body">
      <div class="row g-3 align-items-end">
        <div class="col-md-2">
          <label class="form-label small text-muted">Type</label>
          <select class="form-select form-select-sm" data-playlist-file-type>
            <option value="file">file</option>
            <option value="git">git</option>
            <option value="repo">repo</option>
            <option value="url">url</option>
          </select>
        </div>
        <div class="col-md-7">
          <label class="form-label small text-muted">Location</label>
          <input type="text" class="form-control form-control-sm" data-playlist-file-location placeholder="config/playlists.yml, user/playlists.yml, or https://example.com/playlists.yml">
        </div>
        <div class="col-md-3 d-flex gap-2 flex-wrap justify-content-md-end">
          <button type="button" class="btn btn-outline-primary btn-sm" data-external-yaml-edit data-external-yaml-kind="playlist_files">Edit</button>
          <button type="button" class="btn btn-success btn-sm" data-validate-playlist-file>Validate</button>
          <button type="button" class="btn btn-danger btn-sm" data-remove-playlist-file>Remove</button>
        </div>
      </div>
      <div class="mt-2 small d-none" data-playlist-file-status></div>
    </div>
  `
  const typeSelect = wrapper.querySelector('[data-playlist-file-type]')
  const locationInput = wrapper.querySelector('[data-playlist-file-location]')
  if (typeSelect && ['file', 'url', 'git', 'repo'].includes(entry.type)) {
    typeSelect.value = entry.type
  }
  if (locationInput && entry.location) {
    locationInput.value = entry.location
  }
  if (entry.validated) {
    wrapper.dataset.playlistFileState = 'success'
    wrapper.dataset.playlistFileButtonState = 'success'
  }
  updatePlaylistFileValidateButton(wrapper, Boolean(entry.validated))
  updateExternalYamlEditButton(wrapper, 'playlist_files')
  return wrapper
}

function updatePlaylistFileValidateButton (row, isValidated) {
  if (!row) return
  const button = row.querySelector('[data-validate-playlist-file]')
  if (!button) return
  const state = String(row.dataset.playlistFileButtonState || '').trim() || (isValidated ? 'success' : 'idle')
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

function setPlaylistFileButtonState (row, state) {
  if (!row) return
  row.dataset.playlistFileButtonState = state || 'idle'
  updatePlaylistFileValidateButton(row, state === 'success')
}

function updatePlaylistCustomRepoStatus (editor) {
  if (!editor) return
  const target = editor.querySelector('[data-playlist-custom-repo-status]')
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
    target.append(' playlist files.')
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
}

function applyPlaylistFileDependencyState (row, opts = {}) {
  if (!row) return false
  const skipStatus = Boolean(opts.skipStatus)
  const type = row.querySelector('[data-playlist-file-type]')?.value || ''
  if (type !== 'repo') {
    if (row.dataset.playlistFileDependency === 'repo-missing') {
      row.dataset.playlistFileDependency = ''
    }
    return false
  }

  if (metadataCustomRepoBase) {
    if (row.dataset.playlistFileDependency === 'repo-missing') {
      row.dataset.playlistFileDependency = ''
    }
    return false
  }

  row.dataset.playlistFileDependency = 'repo-missing'
  setPlaylistFileButtonState(row, 'blocked')
  if (!skipStatus) {
    setPlaylistFileStatus(row, 'error', playlistRepoDependencyMessage)
  }
  return true
}

function renderPlaylistFileStatusMessage (target, message) {
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
      const list = document.createElement('ul')
      list.className = 'mb-0 mt-1 ps-3'
      files.forEach(file => {
        const item = document.createElement('li')
        appendInlineCodeText(item, file, { wrapPlainInCode: true })
        list.appendChild(item)
      })
      target.appendChild(list)
    }
    return
  }

  const text = String(message || '').trim()
  if (!text) return

  if (text === playlistRepoDependencyMessage) {
    target.append('Playlist file repo entries require Custom Repo to be configured and saved first within the ')
    appendMetadataSettingsLink(target)
    target.append(' page.')
    return
  }

  appendInlineCodeText(target, text)
}

function setPlaylistFileStatus (row, kind, message) {
  if (!row) return
  const target = row.querySelector('[data-playlist-file-status]')
  if (!target) return
  row.dataset.playlistFileState = kind || ''
  target.className = 'mt-2 small'
  if (!message) {
    target.classList.add('d-none')
    target.textContent = ''
    if (applyPlaylistFileDependencyState(row, { skipStatus: true })) {
      setPlaylistFileButtonState(row, 'blocked')
    } else {
      setPlaylistFileButtonState(row, 'idle')
    }
    const editor = row.closest('[data-playlist-files-editor]')
    if (editor) updatePlaylistFilesAccordionState(editor)
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
  renderPlaylistFileStatusMessage(target, message)
  if (kind === 'success') {
    setPlaylistFileButtonState(row, 'success')
  } else if (row.dataset.playlistFileDependency === 'repo-missing') {
    setPlaylistFileButtonState(row, 'blocked')
  } else {
    setPlaylistFileButtonState(row, 'idle')
  }
  const editor = row.closest('[data-playlist-files-editor]')
  if (editor) updatePlaylistFilesAccordionState(editor)
}

function updatePlaylistFilesAccordionState (editor) {
  if (!editor) return
  const accordionItem = editor.closest('.accordion-item')
  const accordionHeader = accordionItem?.querySelector(':scope > .accordion-header')
  if (!accordionHeader) return

  const rows = Array.from(editor.querySelectorAll('[data-playlist-file-row]'))
  const hasEntries = rows.some(row => {
    const type = row.querySelector('[data-playlist-file-type]')?.value || ''
    const location = row.querySelector('[data-playlist-file-location]')?.value || ''
    return Boolean(normalizePlaylistFileEntry({ type, location }))
  })
  const hasInvalid = rows.some(row => {
    const state = String(row.dataset.playlistFileState || '').trim().toLowerCase()
    return state === 'error' || state === 'warning'
  })

  accordionHeader.classList.remove('invalid', 'warning')
  if (hasInvalid) {
    accordionHeader.classList.add('invalid')
    return
  }
  if (hasEntries) {
    accordionHeader.classList.add('selected')
  } else {
    accordionHeader.classList.remove('selected')
  }
}

function syncPlaylistFilesEditor (editor, emitEvents = true) {
  if (!editor) return []
  const hidden = editor.querySelector('input[type="hidden"][name="playlist_files_entries"]')
  if (!hidden) return []
  const alreadySyncing = editor.dataset.playlistFilesSyncing === 'true'
  if (emitEvents && alreadySyncing) {
    emitEvents = false
  }
  editor.dataset.playlistFilesSyncing = 'true'
  const rows = Array.from(editor.querySelectorAll('[data-playlist-file-row]'))
  const entries = rows.map(row => {
    const type = row.querySelector('[data-playlist-file-type]')?.value
    const location = row.querySelector('[data-playlist-file-location]')?.value
    const validated = String(row.dataset.playlistFileState || '').trim().toLowerCase() === 'success'
    return normalizePlaylistFileEntry({ type, location, validated })
  }).filter(Boolean)
  hidden.value = JSON.stringify(entries)
  if (emitEvents) {
    hidden.dispatchEvent(new Event('input', { bubbles: true }))
    hidden.dispatchEvent(new Event('change', { bubbles: true }))
  }
  delete editor.dataset.playlistFilesSyncing
  updatePlaylistFilesAccordionState(editor)
  return entries
}

function renderPlaylistFilesEditor (editor) {
  if (!editor) return
  const hidden = editor.querySelector('input[type="hidden"][name="playlist_files_entries"]')
  const list = editor.querySelector('[data-playlist-files-list]')
  if (!hidden || !list) return
  updatePlaylistCustomRepoStatus(editor)
  const entries = parsePlaylistFilesValue(hidden.value)
  list.replaceChildren()
  entries.forEach(entry => list.appendChild(buildPlaylistFileRow(entry)))
  list.querySelectorAll('[data-playlist-file-row]').forEach(row => {
    if (applyPlaylistFileDependencyState(row)) return
    if (String(row.dataset.playlistFileState || '').trim().toLowerCase() === 'success') {
      setPlaylistFileButtonState(row, 'success')
    } else {
      setPlaylistFileButtonState(row, 'idle')
    }
  })
  syncPlaylistFilesEditor(editor, false)
  updatePlaylistFilesAccordionState(editor)
}

function initPlaylistFilesEditors (scope) {
  const root = scope || document
  root.querySelectorAll('[data-playlist-files-editor]').forEach(editor => {
    if (editor.dataset.playlistFilesReady === 'true') return
    renderPlaylistFilesEditor(editor)
    editor.dataset.playlistFilesReady = 'true'
  })
}

function renderLibraryFileEditorForHiddenInput (input) {
  if (!input || input.type !== 'hidden') return false

  const editorConfigs = [
    { selector: '[data-metadata-files-editor]', render: renderMetadataFilesEditor },
    { selector: '[data-collection-files-editor]', render: renderCollectionFilesEditor },
    { selector: '[data-overlay-files-editor]', render: renderOverlayFilesEditor },
    { selector: '[data-playlist-files-editor]', render: renderPlaylistFilesEditor }
  ]

  for (const config of editorConfigs) {
    const editor = input.closest(config.selector)
    if (!editor) continue
    config.render(editor)
    return true
  }

  return false
}

document.addEventListener('click', async event => {
  const addButton = event.target.closest('[data-add-playlist-file]')
  if (addButton) {
    const editor = addButton.closest('[data-playlist-files-editor]')
    const list = editor?.querySelector('[data-playlist-files-list]')
    if (!editor || !list) return
    list.appendChild(buildPlaylistFileRow())
    syncPlaylistFilesEditor(editor)
    return
  }

  const removeButton = event.target.closest('[data-remove-playlist-file]')
  if (removeButton) {
    const row = removeButton.closest('[data-playlist-file-row]')
    const editor = removeButton.closest('[data-playlist-files-editor]')
    if (!row || !editor) return
    row.remove()
    syncPlaylistFilesEditor(editor)
    return
  }

  const validateButton = event.target.closest('[data-validate-playlist-file]')
  if (validateButton) {
    const row = validateButton.closest('[data-playlist-file-row]')
    const editor = validateButton.closest('[data-playlist-files-editor]')
    if (!row || !editor) return
    const type = row.querySelector('[data-playlist-file-type]')?.value || ''
    const location = row.querySelector('[data-playlist-file-location]')?.value || ''
    syncPlaylistFilesEditor(editor, false)
    setPlaylistFileStatus(row, '', 'Validating...')
    setPlaylistFileButtonState(row, 'loading')
    try {
      const response = await fetch('/validate_playlist_file', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          playlist_file_type: type,
          playlist_file_location: location,
          config_name: getActiveConfigName()
        })
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.valid === false) {
        setPlaylistFileStatus(row, 'error', payload.error_details || payload.error || 'Validation failed.')
        return
      }
      applyNormalizedLibraryFileLocation(row, '[data-playlist-file-location]', payload, editor, syncPlaylistFilesEditor)
      setPlaylistFileStatus(row, 'success', payload.message || 'Validated successfully.')
    } catch {
      setPlaylistFileStatus(row, 'error', 'Validation failed.')
    }
    syncPlaylistFilesEditor(editor)
    return
  }
})

document.addEventListener('input', event => {
  const target = event.target
  if (!target || !target.closest('[data-playlist-files-editor]')) return
  if (target.matches('input[type="hidden"][name="playlist_files_entries"]')) return
  const row = target.closest('[data-playlist-file-row]')
  const editor = target.closest('[data-playlist-files-editor]')
  if (row) {
    setPlaylistFileStatus(row, '', '')
    applyPlaylistFileDependencyState(row)
  }
  syncPlaylistFilesEditor(editor)
})

document.addEventListener('change', event => {
  const target = event.target
  if (!target || !target.closest('[data-playlist-files-editor]')) return
  if (target.matches('input[type="hidden"][name="playlist_files_entries"]')) return
  const row = target.closest('[data-playlist-file-row]')
  const editor = target.closest('[data-playlist-files-editor]')
  if (row) {
    setPlaylistFileStatus(row, '', '')
    applyPlaylistFileDependencyState(row)
  }
  syncPlaylistFilesEditor(editor)
})

initPlaylistFilesEditors(document)
if (libraryContainer && typeof MutationObserver !== 'undefined') {
  const playlistFilesObserver = new MutationObserver(() => initPlaylistFilesEditors(libraryContainer))
  playlistFilesObserver.observe(libraryContainer, { childList: true, subtree: true })
}
initPlaylistKeyToggleGroups(document)
if (libraryContainer && typeof MutationObserver !== 'undefined') {
  const playlistKeyToggleObserver = new MutationObserver(() => initPlaylistKeyToggleGroups(libraryContainer))
  playlistKeyToggleObserver.observe(libraryContainer, { childList: true, subtree: true })
}
initPlaylistUserPickers(document)
if (libraryContainer && typeof MutationObserver !== 'undefined') {
  const playlistUserPickerObserver = new MutationObserver(() => initPlaylistUserPickers(libraryContainer))
  playlistUserPickerObserver.observe(libraryContainer, { childList: true, subtree: true })
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
    } catch {
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
    } catch {
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

function setupCollectionTemplateFieldRules (scope) {
  const root = scope || document

  function normalizeFieldValue (input) {
    if (!input) return
    const preset = String(input.dataset.validationPreset || '').trim()
    if (preset === 'iso_3166_1_code' && input.type !== 'checkbox') {
      const raw = String(input.value || '')
      const cleaned = raw.replace(/[^a-z]/gi, '').slice(0, 2).toUpperCase()
      if (raw !== cleaned) input.value = cleaned
    }
  }

  function isActiveField (input) {
    if (!input) return false
    if (input.type === 'checkbox') return !!input.checked
    return String(input.value || '').trim().length > 0
  }

  function setFieldDisabledState (input, disabled) {
    if (!input) return
    input.disabled = !!disabled
  }

  function syncTemplateRequirementState (group) {
    if (!group) return

    const fieldByKey = new Map()
    Array.from(group.querySelectorAll('[data-template-variable-key]')).forEach(field => {
      const key = String(field.dataset.templateVariableKey || '').trim()
      if (key && !fieldByKey.has(key)) fieldByKey.set(key, field)
    })

    const dependentFields = Array.from(group.querySelectorAll('[data-template-variable-key][data-requires-any-of-template-keys]'))
    dependentFields.forEach(field => {
      if (field.dataset.requirementBaseDisabled === undefined) {
        field.dataset.requirementBaseDisabled = field.disabled ? 'true' : 'false'
      }

      const baseDisabled = field.dataset.requirementBaseDisabled === 'true'
      const requiresPlexPass = field.dataset.requiresPlexPass === 'true'
      const plexPassAvailable = field.dataset.plexPassAvailable !== 'false'
      const wrapper = field.closest('[data-collection-field-wrapper="true"]')
      const requiredKeys = String(field.dataset.requiresAnyOfTemplateKeys || '')
        .split(',')
        .map(key => key.trim())
        .filter(Boolean)
      const anyActive = requiredKeys.some(key => isActiveField(fieldByKey.get(key)))
      const shouldDisableForDependency = !anyActive
      const shouldDisable = baseDisabled || (requiresPlexPass && !plexPassAvailable) || shouldDisableForDependency

      field.disabled = shouldDisable

      if (!wrapper || (requiresPlexPass && !plexPassAvailable)) return

      const hintId = field.id ? `${field.id}_requirement_hint` : ''
      let hint = hintId ? group.querySelector(`[data-requirement-hint-for="${field.id}"]`) : null
      if (!hint && hintId) {
        hint = document.createElement('div')
        hint.className = 'form-text text-warning mb-2 d-none'
        hint.id = hintId
        hint.dataset.requirementHintFor = field.id
        wrapper.insertAdjacentElement('afterend', hint)
      }
      if (!hint) return

      if (shouldDisableForDependency) {
        hint.textContent = String(field.dataset.requirementHint || 'Requires one of Visible Home, Visible Library, or Visible Shared to be enabled first.').trim()
        hint.classList.remove('d-none')
      } else {
        hint.classList.add('d-none')
        hint.textContent = ''
      }
    })
  }

  function syncMutualState (group) {
    if (!group) return
    const fields = Array.from(group.querySelectorAll('[data-template-variable-key][data-mutually-exclusive-with]'))
    if (!fields.length) return

    const fieldByKey = new Map()
    fields.forEach(field => {
      const key = String(field.dataset.templateVariableKey || '').trim()
      if (key && !fieldByKey.has(key)) fieldByKey.set(key, field)
    })

    let hasConflict = false
    fields.forEach(field => {
      const key = String(field.dataset.templateVariableKey || '').trim()
      const counterpartKey = String(field.dataset.mutuallyExclusiveWith || '').trim()
      if (!key || !counterpartKey) return

      const counterpart = fieldByKey.get(counterpartKey)
      if (!counterpart) return

      const fieldActive = isActiveField(field)
      const counterpartActive = isActiveField(counterpart)
      if (fieldActive && counterpartActive) hasConflict = true

      if (fieldActive && !counterpartActive) {
        setFieldDisabledState(counterpart, true)
      } else if (!counterpartActive) {
        setFieldDisabledState(counterpart, false)
      }
    })

    let warning = group.querySelector('[data-collection-mutual-warning]')
    if (!warning) {
      warning = document.createElement('div')
      warning.className = 'alert alert-warning py-2 px-3 mb-2 small d-none'
      warning.dataset.collectionMutualWarning = 'true'
      warning.textContent = 'Originals Only and Region cannot both be set at the same time.'
      const anchor = group.querySelector('.child-toggle-wrapper')
      if (anchor) {
        anchor.insertAdjacentElement('afterbegin', warning)
      } else {
        group.appendChild(warning)
      }
    }
    warning.classList.toggle('d-none', !hasConflict)
  }

  root.querySelectorAll('[data-collection-config="true"]').forEach(group => {
    if (group.dataset.templateFieldRulesBound === 'true') return

    const fields = Array.from(group.querySelectorAll('[data-template-variable-key]'))
    fields.forEach(input => {
      const preset = String(input.dataset.validationPreset || '').trim()
      if (preset === 'iso_3166_1_code' && input.type !== 'checkbox') {
        const feedbackId = `${input.id}_feedback`
        let feedback = document.getElementById(feedbackId)
        if (!feedback) {
          feedback = document.createElement('div')
          feedback.id = feedbackId
          feedback.className = 'invalid-feedback'
          feedback.textContent = 'Enter a 2-letter ISO 3166-1 region code.'
          input.insertAdjacentElement('afterend', feedback)
        }

        const validateRegion = () => {
          normalizeFieldValue(input)
          const value = String(input.value || '').trim()
          const valid = !value || /^[A-Z]{2}$/.test(value)
          input.classList.toggle('is-invalid', !valid)
          input.setCustomValidity(valid ? '' : 'Enter a 2-letter ISO 3166-1 region code.')
        }

        input.addEventListener('input', validateRegion)
        input.addEventListener('change', validateRegion)
        input.addEventListener('blur', validateRegion)
        validateRegion()
      }

      input.addEventListener('input', () => {
        normalizeFieldValue(input)
        syncMutualState(group)
        syncTemplateRequirementState(group)
      })
      input.addEventListener('change', () => {
        normalizeFieldValue(input)
        syncMutualState(group)
        syncTemplateRequirementState(group)
      })
    })

    syncMutualState(group)
    syncTemplateRequirementState(group)
    group.dataset.templateFieldRulesBound = 'true'
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

  const shouldTrack = (target) => {
    if (!target || target.nodeType !== 1) return false
    if (
      target.dataset.skipLibraryInputBubble === 'true' ||
      target.closest('[data-overlay-source-editor="true"]') ||
      target.closest('[data-overlay-source-hidden]') ||
      (target.matches('input') && target.type === 'hidden')
    ) {
      return false
    }

    const fieldName = String(target.name || '')
    if (!fieldName) return false
    return /-library$|-collection_|-template_collection_|-attribute_|-overlay_|-template_overlay_/i.test(fieldName)
  }

  const onFieldInteraction = (event) => {
    const target = event && event.target
    if (!shouldTrack(target)) return
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
    hidden.addEventListener('change', () => {
      const next = resolveInitial()
      modeSelect.value = next.mode
      valueInput.value = next.number
      updateHidden()
    })

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
        nextValue = buildValueFromInputs(mode) || ''
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

    hidden.addEventListener('change', () => {
      const nextRaw = String(hidden.value || '').trim()
      const nextParsed = parseSchedule(nextRaw)
      applyParsed(nextParsed)
      updateFromBuilder()
    })

    builder.dataset.listenerAdded = 'true'
  })
}

const languageCollectionKeys = JSON.parse(`["ab", "aa", "af", "ak", "sq", "am", "ar", "an", "hy", "as", "av", "ae", "ay", "az", "bm", "ba", "eu", "be", "bn", "bi", "bs", "br", "bg", "my", "ca", "km", "ch", "ce", "ny", "zh", "cu", "cv", "kw", "co", "cr", "hr", "cs", "da", "dv", "nl", "dz", "en", "eo", "et", "ee", "fo", "fj", "fil", "fi", "fr", "ff", "gd", "gl", "lg", "ka", "de", "el", "gn", "gu", "ht", "ha", "he", "hz", "hi", "ho", "hu", "is", "io", "ig", "id", "ia", "ie", "iu", "ik", "ga", "it", "ja", "jv", "kl", "kn", "kr", "ks", "kk", "ki", "rw", "ky", "kv", "kg", "ko", "kj", "ku", "lo", "la", "lv", "li", "ln", "lt", "lu", "lb", "mk", "mg", "ms", "ml", "mt", "gv", "mi", "mr", "mh", "myn", "mn", "na", "nv", "ng", "ne", "nd", "se", "no", "nb", "nn", "oc", "oj", "or", "om", "os", "pi", "ps", "fa", "pl", "pt", "pa", "qu", "ro", "rm", "rom", "rn", "ru", "sm", "sg", "sa", "sc", "sr", "sn", "ii", "sd", "si", "sk", "sl", "so", "nr", "st", "es", "su", "sw", "ss", "sv", "tl", "ty", "tai", "tg", "ta", "tt", "te", "th", "bo", "ti", "to", "ts", "tn", "tr", "tk", "tw", "ug", "uk", "ur", "uz", "ve", "vi", "vo", "wa", "cy", "fy", "wo", "xh", "yi", "yo", "za", "zu", "other"]`).map(value => String(value))
const countryNameCollectionKeys = JSON.parse(`["Algeria", "Egypt", "Libya", "Morocco", "Sudan", "Tunisia", "Western Sahara", "British Indian Ocean Territory", "Burundi", "Comoros", "Djibouti", "Eritrea", "Ethiopia", "French Southern Territories", "Kenya", "Madagascar", "Malawi", "Mauritius", "Mayotte", "Mozambique", "R\u00e9union", "Rwanda", "Seychelles", "Somalia", "South Sudan", "Uganda", "Tanzania", "Zambia", "Zimbabwe", "Angola", "Cameroon", "Central African Republic", "Chad", "Republic of the Congo", "Democratic Republic of the Congo", "Equatorial Guinea", "Gabon", "S\u00e3o Tom\u00e9 and Pr\u00edncipe", "Botswana", "Eswatini", "Lesotho", "Namibia", "South Africa", "Benin", "Burkina Faso", "Cape Verde", "C\u00f4te d'Ivoire", "Gambia", "Ghana", "Guinea", "Guinea-Bissau", "Liberia", "Mali", "Mauritania", "Niger", "Nigeria", "Saint Helena, Ascension and Tristan da Cunha", "Senegal", "Sierra Leone", "Togo", "Anguilla", "Antigua and Barbuda", "Aruba", "Bahamas", "Barbados", "Bonaire, Sint Eustatius and Saba", "Netherlands Antilles", "British Virgin Islands", "Cayman Islands", "Cuba", "Cura\u00e7ao", "Dominica", "Dominican Republic", "Grenada", "Guadeloupe", "Haiti", "Jamaica", "Martinique", "Montserrat", "Puerto Rico", "Saint Barth\u00e9lemy", "Saint Kitts and Nevis", "Saint Lucia", "Saint Martin", "Saint Vincent and the Grenadines", "Sint Maarten", "Trinidad and Tobago", "Turks and Caicos Islands", "US Virgin Islands", "Belize", "Costa Rica", "El Salvador", "Guatemala", "Honduras", "Mexico", "Nicaragua", "Panama", "Argentina", "Bolivia", "Bouvet Island", "Brazil", "Chile", "Colombia", "Ecuador", "Falkland Islands", "French Guiana", "Guyana", "Paraguay", "Peru", "South Georgia and the South Sandwich Islands", "Suriname", "Uruguay", "Venezuela", "Bermuda", "Canada", "Greenland", "Saint Pierre and Miquelon", "United States", "Antarctica", "Kazakhstan", "Kyrgyzstan", "Tajikistan", "Turkmenistan", "Uzbekistan", "China", "Hong Kong", "Macao", "North Korea", "Japan", "Mongolia", "South Korea", "Taiwan", "Brunei", "Cambodia", "Indonesia", "Laos", "Malaysia", "Myanmar", "Philippines", "Singapore", "Thailand", "East Timor", "Vietnam", "Afghanistan", "Bangladesh", "Bhutan", "India", "Iran", "Maldives", "Nepal", "Pakistan", "Sri Lanka", "Armenia", "Azerbaijan", "Bahrain", "Cyprus", "Georgia", "Iraq", "Israel", "Jordan", "Kuwait", "Lebanon", "Oman", "Qatar", "Saudi Arabia", "Palestine", "Syria", "Turkey", "United Arab Emirates", "Yemen", "Belarus", "Bulgaria", "Czech Republic", "Hungary", "Poland", "Moldova", "Romania", "Russia", "Slovakia", "Ukraine", "\u00c5land Islands", "Guernsey", "Jersey", "Sark", "Denmark", "Estonia", "Faroe Islands", "Finland", "Iceland", "Ireland", "Northern Ireland", "Isle of Man", "Latvia", "Lithuania", "Norway", "Svalbard and Jan Mayen Islands", "Sweden", "United Kingdom", "Albania", "Andorra", "Bosnia and Herzegovina", "Croatia", "Gibraltar", "Greece", "Kosovo", "Vatican City", "Italy", "Malta", "Montenegro", "North Macedonia", "Portugal", "San Marino", "Serbia", "Serbia and Montenegro", "Slovenia", "Spain", "Yugoslavia", "Austria", "Belgium", "France", "Germany", "Liechtenstein", "Luxembourg", "Monaco", "Netherlands", "Switzerland", "Australia", "Christmas Island", "Cocos (Keeling) Islands", "Heard Island and McDonald Islands", "New Zealand", "Norfolk Island", "Fiji", "New Caledonia", "Papua New Guinea", "Solomon Islands", "Vanuatu", "Guam", "Kiribati", "Marshall Islands", "Micronesia", "Nauru", "Northern Mariana Islands", "Palau", "US Minor Outlying Islands", "American Samoa", "Cook Islands", "French Polynesia", "Niue", "Pitcairn Islands", "Samoa", "Tokelau", "Tonga", "Tuvalu", "Wallis and Futuna Islands", "other"]`).map(value => String(value))
const countryCodeCollectionKeys = JSON.parse(`["dz", "eg", "ly", "ma", "sd", "tn", "eh", "io", "bi", "km", "dj", "er", "et", "tf", "ke", "mg", "mw", "mu", "yt", "mz", "re", "rw", "sc", "so", "ss", "ug", "tz", "zm", "zw", "ao", "cm", "cf", "td", "cg", "cd", "gq", "ga", "st", "bw", "sz", "ls", "na", "za", "bj", "bf", "cv", "ci", "gm", "gh", "gn", "gw", "lr", "ml", "mr", "ne", "ng", "sh", "sn", "sl", "tg", "ai", "ag", "aw", "bs", "bb", "bq", "an", "vg", "ky", "cu", "cw", "dm", "do", "gd", "gp", "ht", "jm", "mq", "ms", "pr", "bl", "kn", "lc", "mf", "vc", "sx", "tt", "tc", "vi", "bz", "cr", "sv", "gt", "hn", "mx", "ni", "pa", "ar", "bo", "bv", "br", "cl", "co", "ec", "fk", "gf", "gy", "py", "pe", "gs", "sr", "uy", "ve", "bm", "ca", "gl", "pm", "us", "aq", "kz", "kg", "tj", "tm", "uz", "cn", "hk", "mo", "kp", "jp", "mn", "kr", "tw", "bn", "kh", "id", "la", "my", "mm", "ph", "sg", "th", "tp", "vn", "af", "bd", "bt", "in", "ir", "mv", "np", "pk", "lk", "am", "az", "bh", "cy", "ge", "iq", "il", "jo", "kw", "lb", "om", "qa", "sa", "ps", "sy", "tr", "ae", "ye", "by", "bg", "cz", "hu", "pl", "md", "ro", "ru", "sk", "ua", "ax", "gg", "je", "cq", "dk", "ee", "fo", "fi", "is", "ie", "im", "lv", "lt", "no", "sj", "se", "gb", "al", "ad", "ba", "hr", "gi", "gr", "xk", "va", "it", "mt", "me", "mk", "pt", "sm", "rs", "si", "es", "yu", "at", "be", "fr", "de", "li", "lu", "mc", "nl", "ch", "au", "cx", "cc", "hm", "nz", "nf", "fj", "nc", "pg", "sb", "vu", "gu", "ki", "mh", "fm", "nr", "mp", "pw", "um", "as", "ck", "pf", "nu", "pn", "ws", "tk", "to", "tv", "wf", "other"]`).map(value => String(value))
const continentCollectionKeys = JSON.parse(`["Africa", "Americas", "Antarctica", "Asia", "Europe", "Oceania", "other"]`).map(value => String(value))
const regionCollectionKeys = JSON.parse(`["Northern Africa", "Eastern Africa", "Central Africa", "Southern Africa", "Western Africa", "Caribbean", "Central America", "South America", "North America", "Antarctica", "Central Asia", "Eastern Asia", "South-Eastern Asia", "Southern Asia", "Western Asia", "Eastern Europe", "Northern Europe", "Southern Europe", "Western Europe", "Australia and New Zealand", "Melanesia", "Micronesia", "Polynesia", "other"]`).map(value => String(value))
const studioCollectionKeys = JSON.parse(`["8bit", "A-1 Pictures", "A.C.G.T.", "Acca effe", "Actas", "AIC", "Ajia-Do", "Akatsuki", "Animation Do", "Ankama", "APPP", "Arms", "Artland", "Artmic", "Arvo Animation", "Asahi Production", "Ashi Productions", "asread.", "AtelierPontdarc", "B.CMAY PICTURES", "Bandai Namco Pictures", "Bee Train", "Berlanti Productions", "Bibury Animation Studios", "bilibili", "Bones", "Brain's Base", "Bridge", "BUG FILMS", "C-Station", "C2C", "Children's Playground Entertainment", "Cloud Hearts", "CloverWorks", "Colored Pencil Animation", "CoMix Wave Films", "Connect", "Craftar Studios", "Creators in Pack", "CygamesPictures", "David Production", "Diomed\\u00e9a", "DLE", "Doga Kobo", "domerica", "Drive", "EMT Squared", "Encourage Films", "ENGI", "feel.", "Felix Film", "Fenz", "GAINAX", "Gallop", "Geek Toys", "Gekkou", "Gemba", "GENCO", "Geno Studio", "GoHands", "Gonzo", "Graphinica", "Group Tac", "Hal Film Maker", "Haoliners Animation League", "Hoods Entertainment", "Hotline", "J.C.Staff", "Jumondou", "Kadokawa", "Khara", "Kinema Citrus", "Kyoto Animation", "Lan Studio", "LandQ Studio", "Lay-duce", "Lerche", "LIDENFILMS", "M.S.C", "Madhouse", "Magic Bus", "Maho Film", "Manglobe", "MAPPA", "Millepensee", "Namu Animation", "NAZ", "Nexus", "Nippon Animation", "Nomad", "Nut", "Okuruto Noboru", "OLM", "Orange", "Ordet", "OZ", "P.A. Works", "P.I.C.S.", "Passione", "Pb Animation Co. Ltd", "Pierrot", "Pine Jam", "Platinum Vision", "Polygon Pictures", "Pony Canyon", "Production +h.", "Production I.G", "Production IMS", "Production Reed", "Project No.9", "Quad", "Radix", "Revoroot", "Saetta", "SANZIGEN", "Satelight", "Science SARU", "Sentai Filmworks", "Seven Arcs", "Shaft", "Shin-Ei Animation", "Shogakukan", "Shuka", "Signal.MD", "Silver", "SILVER LINK.", "Square Enix", "Staple Entertainment", "Studio 3Hz", "Studio A-CAT", "Studio Bind", "Studio Blanc.", "Studio Chizu", "Studio Comet", "Studio Deen", "Studio Elle", "Studio Ghibli", "Studio Flad", "Studio Gokumi", "Studio Guts", "Studio Hibari", "Studio Kafka", "Studio Kai", "Studio Mir", "studio MOTHER", "Studio Palette", "Studio Rikka", "Studio Signpost", "Studio VOLN", "STUDIO4\\u00b0C", "Sunrise Beyond", "Sunrise", "SynergySP", "Tatsunoko Production", "Telecom Animation Film", "Tezuka Productions", "TMS Entertainment", "TNK", "Toei Animation", "Topcraft", "Triangle Staff", "Trigger", "TROYCA", "TYO Animations", "Typhoon Graphics", "ufotable", "V1 Studio", "W-Toon Studio", "Wawayu Animation", "White Fox", "Wit Studio", "Wolfsbane", "Xebec", "Yokohama Animation Lab", "Yostar Pictures", "Yumeta Company", "Zero-G", "Zexcs", "3 Arts Entertainment", "6th & Idaho", "20th Century Animation", "20th Century Studios", "20th Century Fox Television", "21 Laps Entertainment", "87Eleven", "87North Productions", "101 Studios", "1492 Pictures", "A Bigger Boat", "A+E Studios", "A24", "Aardman", "Aamir Khan Productions", "ABC Signature", "ABC Studios", "Ace Entertainment", "AGBO", "Amazon Studios", "Amblin Entertainment", "AMC Studios", "Anima Sola Productions", "Annapurna Pictures", "Ardustry Entertainment", "Artisan Entertainment", "Artists First", "Atlas Entertainment", "Atresmedia", "Bad Hat Harry Productions", "Bad Robot", "Bad Wolf", "Barunson E&A", "Bakken Record", "Bardel Entertainment", "BBC Studios", "Bill Melendez Productions", "Blade", "Bleecker Street", "Blown Deadline Productions", "Blue Ice Pictures", "Blue Sky Studios", "Bluegrass Films", "Blueprint Pictures", "Blumhouse Productions", "Blur Studio", "Bold Films", "Bona Film Group", "Bonanza Productions", "Boo Pictures", "Bosque Ranch Productions", "Box to Box Films", "Brandywine Productions", "Broken Lizard Industries", "Broken Road Productions", "Calt Production", "Canal+", "Carnival Films", "Carolco", "Cartoon Saloon", "Carsey-Werner Company", "Castle Rock Entertainment", "CBS Productions", "CBS Studios", "CBS Television Studios", "Centropolis Entertainment", "Chernin Entertainment", "Chimp Television", "Chris Morgan Productions", "Cinergi Pictures Entertainment", "Codeblack Entertainment", "Columbia Pictures", "Constantin Film", "Cowboy Films", "Cross Creek Pictures", "Dark Horse Entertainment", "Davis Entertainment", "DC Comics", "Dimension Films", "Dino De Laurentiis Company", "Disney Television Animation", "DisneyToon Studios", "Don Simpson Jerry Bruckheimer Films", "Doozer", "Dreams Salon Entertainment Culture", "DreamWorks Studios", "DreamWorks Pictures", "Dropout", "Dynamic Planning", "Eleventh Hour Films", "EMJAG Productions", "Endeavor Content", "Entertainment 360", "Entertainment One", "Eon Productions", "Everest Entertainment", "Expectation Entertainment", "Exposure Labs", "Fandango", "Fields Entertainment", "Film4 Productions", "FilmDistrict", "FilmNation Entertainment", "Flynn Picture Company", "Focus Features", "Food Network", "Fortiche Production", "Fox Television Studios", "Freckle Films", "Frederator Studios", "FremantleMedia", "Fuqua Films", "Gallagher Films Ltd", "Gary Sanchez Productions", "Gaumont", "Generator Entertainment", "Golden Harvest", "Gracie Films", "Green Hat Films", "Grindstone Entertainment Group", "Hallmark", "HandMade Films", "Happy Madison Productions", "HartBeat Productions", "Hartswood Films", "Hasbro", "HBO", "Heyday Films", "Hughes Entertainment", "Hungry Man", "Hurwitz & Schlossberg Productions", "Hyperobject Industries", "Icon Entertainment International", "IFC Films", "Illumination Entertainment", "Imagin", "Imperative Entertainment", "Impossible Factual", "Ingenious Media", "Irwin Entertainment", "Jerry Bruckheimer Films", "Jessie Films", "Jinks-Cohen Company", "Kazak Productions", "Kennedy Miller Productions", "Kilter Films", "Kjam Media", "Kudos", "Kurtzman Orci", "Laika Entertainment", "Landscape Entertainment", "Laura Ziskin Productions", "Leftfield Pictures", "Legendary Pictures", "Let's Not Turn This Into a Whole Big Production", "Lifetime", "Levity Entertainment Group", "Lightstorm Entertainment", "Likely Story", "Lionsgate", "Live Entertainment", "Lord Miller Productions", "Lucasfilm Ltd", "Magic Light Pictures", "Magnolia Pictures", "Malevolent Films", "Mandalay Entertainment", "Mandarin", "Mandarin Motion Pictures Limited", "Marv Films", "Marvel Animation", "Marvel Studios", "Matt Tolmach Productions", "Maximum Effort", "Media Res", "Metro-Goldwyn-Mayer", "Michael Patrick King Productions", "Millennium Films", "Miramax", "NEON", "Netflix", "New Line Cinema", "Nickelodeon Animation Studio", "NorthSouth Productions", "Nu Boyana Film Studios", "O2 Filmes", "Open Road Films", "Original Film", "Orion Pictures", "Palomar", "Paramount Animation", "Paramount Pictures", "Paramount Television Studios", "Participant", "Phoenix Pictures", "Piki Films", "Pixar", "Plan B Entertainment", "PlayStation Productions", "Playtone", "Plum Pictures", "Powerhouse Animation Studios", "PRA", "Prescience", "Prospect Park", "Pulse Films", "Radar Pictures", "RadicalMedia", "Railsplitter Pictures", "Rankin Bass Productions", "RatPac Entertainment", "Red Dog Culture House", "Regency Pictures", "Reveille Productions", "Rip Cord Productions", "RocketScience", "Savoy Pictures", "Scenic Labs", "Scion Films", "Scott Free Productions", "Sculptor Media", "Screen Gems", "Sean Daniel Company", "Searchlight Pictures", "Secret Hideout", "See-Saw Films", "Serendipity Pictures", "Shaw Brothers", "Show East", "Showtime Networks", "Sil-Metropole Organisation", "Silverback Films", "Siren Pictures", "SISTER", "Sixteen String Jack Productions", "SKA Films", "Sky studios", "Skydance", "Sony Pictures Animation", "Sony Pictures", "Sph\\u00e8re M\\u00e9dia Plus", "Spyglass Entertainment", "St\\u00f6\\u00f0 2", "Star Thrower Entertainment", "Stark Raving Black Productions", "StudioCanal", "Studio 8", "Studio Babelsberg", "Studio Dragon", "Studio Live", "STX Entertainment", "Summit Entertainment", "Syfy", "Syncopy", "T-Street Productions", "Tall Ship Productions", "Team Downey", "Temple Street Productions", "The Cat in the Hat Productions", "The Donners' Company", "The Jim Henson Company", "The Kennedy-Marshall Company", "The Linson Company", "The Littlefield Company", "The Mark Gordon Company", "The Sea Change Project", "The Stone Quarry", "The Weinstein Company", "Tim Burton Productions", "TOHO", "Thunder Road", "Titmouse", "Tomorrow Studios", "Touchstone Pictures", "Touchstone Television", "Trademark Films", "Triage Entertainment", "Tribeca Productions", "TriStar Pictures", "TSG Entertainment", "Twisted Pictures", "UCP", "United Artists", "Universal Animation Studios", "Universal Pictures", "Universal Television", "Vancouver Media", "Vertigo Entertainment", "Village Roadshow Pictures", "W. Chump and Sons", "Walden Media", "Walt Disney Animation Studios", "Walt Disney Pictures", "Walt Disney Productions", "Warner Animation Group", "Warner Bros. Pictures", "Warner Bros. Television", "Warner Premiere", "warparty", "Waverly Films", "Wayfare Entertainment", "Williams Street", "Whitaker Entertainment", "Wiedemann & Berg Television", "Winkler Films", "Wolf Entertainment", "Working Title Films"]`).map(value => String(value))
const networkCollectionKeys = JSON.parse(`["#0", 5, "7mate", "ABC", "ABC Family", "ABC Kids", "ABC TV", "ABS-CBN", "Acorn TV", "Adult Swim", "AHC", "ALTBalaji", "Amazon Kids+", "AMC", "AMC+", "Animal Planet", "ANIMAX", "Angel Studios", "Antena 3", "Apple TV", "ARD", "Arte", "Atresplayer Premium", "Atres Player", "AT-X", "Audience", "AXN", "Azteca Uno", "A&E", "BBC America", "BBC Four", "BBC iPlayer", "BBC One", "BBC Scotland", "BBC Three", "BBC Two", "BET", "BET+", "bilibili", "Binge", "BluTV", "Boomerang", "Bravo", "BritBox", "C More", "Canale 5", "Canal+", "Cartoon Network", "Cartoonito", "CBC", "CBC Television", "Cbeebies", "CBS", "Channel 3", "Channel 4", "CHCH-DT", "Cinemax", "Citytv", "CNN", "Comedy Central", "Cooking Channel", "Crackle", "Crave", "Criterion Channel", "Crunchyroll", "CTV", "Cuatro", "Curiosity Stream", "DC Universe", "Discovery", "Discovery Kids", "discovery+", "Disney Channel", "Disney Junior", "Disney XD", "Disney+", "DR1", "Dropout", "Elisa Viihde", "Elisa Viihde Viaplay", "ENA", "Epix", "ESPN", "EXXEN", "E!", "E4", "Facebook Watch", "Family Channel", "Ficci\\u00f3n Producciones", "Flooxer", "Food Network", "FOX", "Fox Kids", "France 2", "Freeform", "Freevee", "Fuji TV", "funnyordie.com", "FX", "FXX", "GA\\u0130N", "Game Show Network", "Global TV", "Globoplay", "GMA Network", "Hallmark", "HBO", "HBO Max", "HGTV", "History", "HOT3", "Hulu", "ICTV", "IFC", "IMDb TV", "Investigation Discovery", "ION Television", "iQiyi", "ITV", "ITV Encore", "ITV1", "ITV2", "ITV3", "ITV4", "ITVBe", "ITVX", "JioCinema", "joyn", "JTBC", "Kan 11", "Kanal 5", "KBS2", "Kids WB", "La 1", "La Une", "Las Estrellas", "Lifetime", "Lionsgate+", "Logo", "Magnolia Network", "MasterClass", "MBC", "MBN", "MGM+", "mitele", "Movistar Plus+", "MTV", "M-Net", "National Geographic", "NBC", "Netflix", "Network 10", "NFL Network", "NHK", "Nick", "Nick Jr", "Nickelodeon", "Nicktoons", "Nine Network", "Nippon TV", "NRK1", "OCS City", "OCS Max", "ORF", "Oxygen", "Pantaya", "Paramount Network", "Paramount+", "PBS", "PBS Kids", "Peacock", "Plan\\u00e8te+ A&E", "Prime Video", "Quibi", "Rai 1", "Reelz", "RT\\u00c9 One", "RTL", "RTL T\\u00e9l\\u00e9", "RTP1", "R\\u00daV", "S4C", "SAT.1", "SBS", "Science", "Seeso", "Seven Network", "Shahid", "Showcase", "Showmax", "Showtime", "Shudder", "Sky", "Smithsonian", "Space", "Spectrum", "Spike", "St\\u00f6\\u00f0 2", "Stan", "Starz", "STAR+", "Sundance TV", "SVT", "SVT Play", "SVT1", "Syfy", "Syndication", "TBS", "Telecinco", "Telefe", "Telemundo", "Televisi\\u00f3n de Galicia", "Televisi\\u00f3n P\\u00fablica Argentina", "Tencent Video", "TF1", "The CW", "The Daily Wire", "The Roku Channel", "The WB", "TLC", "TNT", "Tokyo MX", "Travel Channel", "truTV", "tubi", "Turner Classic Movies", "TV 2", "tv asahi", "TV Globo", "TV Land", "TV Tokyo", "TV3", "TV4", "TV4 Play", "TVB Jade", "tving", "tvN", "TVNZ 1", "TVNZ 2", "TVP1", "U", "U&Alibi", "U&Dave", "U&Drama", "U&Eden", "U&Gold", "U&W", "U&Yesterday", "UniM\\u00e1s", "Universal Kids", "Universal TV", "Univision", "UPN", "USA Network", "U+ Mobile TV", "VH1", "Viaplay", "Vice", "Virgin Media One", "ViuTV", "ViX+", "VRT 1", "VRT Max", "VTM", "W", "WE tv", "Xbox Live", "YLE", "Youku", "YouTube", "ZDF", "ZEE5"]`).map(value => String(value))
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
      } catch {
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
  numeric_id: {
    duplicateInsensitive: true,
    normalize: value => value,
    lookupService: 'tmdb',
    validate: value => /^\d+$/.test(value)
      ? { valid: true }
      : { valid: false, message: 'Enter a numeric ID like 603 or 1399.' }
  },
  imdb_id_tmdb: {
    duplicateInsensitive: true,
    normalize: value => value.toLowerCase(),
    lookupService: 'tmdb',
    validate: value => /^tt\d{7,8}$/i.test(value)
      ? { valid: true }
      : { valid: false, message: 'Enter an IMDb ID like tt1234567 or tt12345678.' }
  },
  imdb_id_plex: {
    duplicateInsensitive: true,
    normalize: value => value.toLowerCase(),
    lookupService: 'plex',
    validate: value => /^tt\d{7,8}$/i.test(value)
      ? { valid: true }
      : { valid: false, message: 'Enter an IMDb ID like tt1234567 or tt12345678.' }
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
  other_chart_key: {
    duplicateInsensitive: true,
    normalize: value => value.toLowerCase(),
    suggestions: ['commonsense', 'metacritic', 'stevenlu', 'pirated'],
    allowedValues: new Set(['commonsense', 'metacritic', 'stevenlu', 'pirated']),
    validate: value => templateStringListPresetConfigs.other_chart_key.allowedValues.has(value)
      ? { valid: true }
      : { valid: false, message: 'Select a supported Other Charts key like commonsense, metacritic, stevenlu, or pirated.' }
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
  language_key: {
    duplicateInsensitive: true,
    normalize: value => value.replace(/\s+/g, ' ').trim().toLowerCase(),
    suggestions: ['en', 'fr', 'ja', 'ko', 'es', 'other'],
    allowedValues: new Set(languageCollectionKeys),
    validate: value => templateStringListPresetConfigs.language_key.allowedValues.has(value)
      ? { valid: true }
      : { valid: false, message: 'Select a supported language code like en, fr, ja, or other.' }
  },
  country_name_key: {
    duplicateInsensitive: true,
    normalize: value => value.replace(/\s+/g, ' ').trim(),
    suggestions: ['France', 'Japan', 'United States of America', 'India', 'other'],
    allowedValues: new Set(countryNameCollectionKeys),
    validate: value => templateStringListPresetConfigs.country_name_key.allowedValues.has(value)
      ? { valid: true }
      : { valid: false, message: 'Select a supported country key like France, Japan, or other.' }
  },
  country_code_key: {
    duplicateInsensitive: true,
    normalize: value => value.replace(/\s+/g, ' ').trim(),
    suggestions: ['fr', 'jp', 'us', 'in', 'other'],
    allowedValues: new Set(countryCodeCollectionKeys),
    validate: value => templateStringListPresetConfigs.country_code_key.allowedValues.has(value)
      ? { valid: true }
      : { valid: false, message: 'Select a supported country code key like fr, jp, us, or other.' }
  },
  continent_key: {
    duplicateInsensitive: true,
    normalize: value => value.replace(/\s+/g, ' ').trim(),
    suggestions: ['Africa', 'Americas', 'Asia', 'Europe', 'Oceania', 'other'],
    allowedValues: new Set(continentCollectionKeys),
    validate: value => templateStringListPresetConfigs.continent_key.allowedValues.has(value)
      ? { valid: true }
      : { valid: false, message: 'Select a supported continent key like Africa, Europe, or other.' }
  },
  region_key: {
    duplicateInsensitive: true,
    normalize: value => value.replace(/\s+/g, ' ').trim(),
    suggestions: ['North America', 'Western Europe', 'Eastern Asia', 'Caribbean', 'other'],
    allowedValues: new Set(regionCollectionKeys),
    validate: value => templateStringListPresetConfigs.region_key.allowedValues.has(value)
      ? { valid: true }
      : { valid: false, message: 'Select a supported region key like North America, Eastern Asia, or other.' }
  },
  studio_key: {
    duplicateInsensitive: true,
    normalize: value => value.replace(/\s+/g, ' ').trim(),
    suggestions: ['A24', 'Marvel Studios', 'Pixar', 'Studio Ghibli', 'Warner Bros. Pictures'],
    allowedValues: new Set(studioCollectionKeys),
    validate: value => templateStringListPresetConfigs.studio_key.allowedValues.has(value)
      ? { valid: true }
      : { valid: false, message: 'Select a supported studio key like A24, Pixar, or Warner Bros. Pictures.' }
  },
  network_key: {
    duplicateInsensitive: true,
    normalize: value => value.replace(/\s+/g, ' ').trim(),
    suggestions: ['Apple TV', 'Disney+', 'HBO Max', 'Netflix', 'Showtime'],
    allowedValues: new Set(networkCollectionKeys),
    validate: value => templateStringListPresetConfigs.network_key.allowedValues.has(value)
      ? { valid: true }
      : { valid: false, message: 'Select a supported network key like Netflix, HBO Max, or Apple TV.' }
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

function ensureTemplatePresetDatalist (wrapper, input, presetConfig, presetName) {
  if (!wrapper || !input || !presetConfig || !Array.isArray(presetConfig.suggestions) || !presetConfig.suggestions.length) return
  if (String(input.tagName || '').toUpperCase() === 'SELECT') return
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

function getTemplatePresetSelectableOptions (presetConfig) {
  if (!presetConfig) return []
  if (Array.isArray(presetConfig.selectOptions) && presetConfig.selectOptions.length) {
    return presetConfig.selectOptions
  }
  if (presetConfig.allowedValues instanceof Set && presetConfig.allowedValues.size) {
    return Array.from(presetConfig.allowedValues)
  }
  if (Array.isArray(presetConfig.allowedValues) && presetConfig.allowedValues.length) {
    return presetConfig.allowedValues
  }
  if (Array.isArray(presetConfig.suggestions) && presetConfig.suggestions.length) {
    return presetConfig.suggestions
  }
  return []
}

function parseTemplateSelectableOptions (wrapper, presetConfig, datasetKey = 'keyOptions') {
  const raw = String(wrapper?.dataset?.[datasetKey] || '').trim()
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        return parsed
          .map(option => {
            if (option && typeof option === 'object') {
              const value = String(option.value || '').trim()
              const label = String(option.label || value).trim()
              return value ? { value, label } : null
            }
            const value = String(option || '').trim()
            return value ? { value, label: value } : null
          })
          .filter(Boolean)
      }
    } catch {}
  }

  return getTemplatePresetSelectableOptions(presetConfig)
    .map(option => {
      const value = String(option || '').trim()
      return value ? { value, label: value } : null
    })
    .filter(Boolean)
}

function ensureTemplateSelectOptions (wrapper, selectInput, presetConfig, datasetKey = 'keyOptions') {
  if (!wrapper || !selectInput || String(selectInput.tagName || '').toUpperCase() !== 'SELECT') return
  const options = parseTemplateSelectableOptions(wrapper, presetConfig, datasetKey)
  if (!options.length) return

  const currentValue = String(selectInput.value || '').trim()
  selectInput.querySelectorAll('option[data-template-generated-option="true"]').forEach(option => option.remove())
  options.forEach(({ value, label }) => {
    const option = document.createElement('option')
    option.value = value
    option.textContent = label
    option.dataset.templateGeneratedOption = 'true'
    selectInput.appendChild(option)
  })
  selectInput.value = currentValue
}

function setupTemplateStringListHandlers (scope) {
  const templateStringLookupCache = window.__qsTemplateStringLookupCache || new Map()
  window.__qsTemplateStringLookupCache = templateStringLookupCache

  function getServiceValidationState (serviceName) {
    const el = document.getElementById(`qs-validate-${serviceName}`)
    return String(el?.value || '').trim().toLowerCase() === 'true'
  }

    function setLookupState (target, state) {
      if (!target) return
      target.textContent = state?.message || ''
      const inlineLookup = target.dataset.lookupInline === 'true'
      target.className = inlineLookup ? 'small ms-2' : 'small mt-1'
      if (!state?.message) {
        target.classList.add('d-none')
        return
      }
    target.classList.remove('d-none')
    if (state.level === 'warning') {
      target.classList.add('text-warning')
    } else if (state.valid && state.verified) {
      target.classList.add('text-success')
    } else if (state.verified) {
      target.classList.add('text-danger')
    } else {
      target.classList.add('text-warning')
    }
  }

function applyLookupState (target, presetConfig, presetName, value, context = {}, onResolvedLabel = null) {
    if (!target || !presetConfig?.lookupService || !value) return

    if (presetConfig.lookupService === 'tmdb') {
      if (!getServiceValidationState('tmdb')) {
        setLookupState(target, {
          valid: false,
          verified: false,
          message: 'TMDb not validated, so the collection title could not be checked.'
        })
        return
      }

      setLookupState(target, {
        valid: false,
        verified: false,
        message: 'Checking TMDb collection title...'
      })
      lookupTemplateStringValue(presetName, value, context).then(result => {
        if (!target.isConnected) return
      if (result.valid && result.verified && result.label) {
        if (typeof onResolvedLabel === 'function') {
          onResolvedLabel(value, result.label)
        }
        const successMessage = result.message || `TMDb: ${result.label}`
          setLookupState(target, {
            valid: true,
            verified: true,
            level: result.level,
            message: successMessage
          })
          return
        }
        setLookupState(target, {
          valid: Boolean(result.valid),
          verified: Boolean(result.verified),
          message: result.message || 'TMDb lookup failed.'
        })
      })
      return
    }

    if (presetConfig.lookupService === 'plex') {
      if (!getServiceValidationState('plex')) {
        setLookupState(target, {
          valid: false,
          verified: false,
          message: 'Plex not validated, so the IMDb ID could not be checked against the active library.'
        })
        return
      }
      if (!String(context.libraryName || '').trim()) {
        setLookupState(target, {
          valid: false,
          verified: false,
          message: 'Library context is unavailable for Plex lookup.'
        })
        return
      }

      setLookupState(target, {
        valid: false,
        verified: false,
        message: 'Checking Plex library for this IMDb ID...'
      })
      lookupTemplateStringValue(presetName, value, context).then(result => {
        if (!target.isConnected) return
      if (result.valid && result.verified && result.label) {
        if (typeof onResolvedLabel === 'function') {
          onResolvedLabel(value, result.label)
        }
        const successMessage = result.message || `Plex: ${result.label}`
          setLookupState(target, {
            valid: true,
            verified: true,
            level: result.level,
            message: successMessage
          })
          return
        }
        setLookupState(target, {
          valid: Boolean(result.valid),
          verified: Boolean(result.verified),
          message: result.message || 'Plex lookup failed.'
        })
      })
    }
  }

  async function lookupTemplateStringValue (presetName, value, context = {}) {
    const libraryName = String(context.libraryName || '').trim()
    const mediaType = String(context.mediaType || '').trim()
    const cacheKey = `${presetName}:${libraryName}:${mediaType}:${value}`
    if (templateStringLookupCache.has(cacheKey)) {
      return templateStringLookupCache.get(cacheKey)
    }
    const request = fetch('/lookup_template_string_value', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        preset: presetName,
        value,
        library_name: libraryName,
        media_type: mediaType
      })
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
  root.querySelectorAll('[data-template-scalar-lookup="true"]').forEach(input => {
    if (input.dataset.templateScalarLookupBound === 'true') return

    const presetName = String(input.dataset.validationPreset || '').trim()
    const presetConfig = templateStringListPresetConfigs[presetName]
    if (!presetConfig?.lookupService) return

    const lookupLabelsHidden = input.id ? document.getElementById(`${input.id}__lookup_labels`) : null
    const libraryName = String(input.dataset.libraryName || '').trim()
    const mediaType = String(input.dataset.mediaType || '').trim()
    const lookupMeta = document.createElement('div')
    lookupMeta.className = 'small mt-1 d-none'

    const wrapper = input.closest('[data-collection-field-wrapper="true"], .input-group') || input
    wrapper.insertAdjacentElement('afterend', lookupMeta)

    function writeLookupLabels (labels) {
      if (!lookupLabelsHidden) return
      const cleanLabels = Object.fromEntries(
        Object.entries(labels || {})
          .map(([key, value]) => [String(key || '').trim(), String(value || '').trim()])
          .filter(([key, value]) => key && value)
      )
      lookupLabelsHidden.value = JSON.stringify(cleanLabels)
      lookupLabelsHidden.dispatchEvent(new Event('change', { bubbles: true }))
    }

    function validateScalarValue () {
      const rawValue = String(input.value || '').trim()
      const normalized = presetConfig.normalize ? presetConfig.normalize(rawValue) : rawValue
      const result = presetConfig.validate ? presetConfig.validate(normalized) : { valid: Boolean(normalized) }
      return {
        value: normalized,
        valid: Boolean(result.valid),
        message: result.message || 'Enter a valid value.'
      }
    }

    function storeLookupLabel (value, label) {
      if (!lookupLabelsHidden || !value || !label) return
      const key = String(value).trim()
      const normalizedLabel = String(label).trim()
      if (!key || !normalizedLabel) return
      writeLookupLabels({ [key]: normalizedLabel })
      scheduleLookupLabelAutosave()
    }

    function runLookup () {
      const checked = validateScalarValue()
      if (!checked.value) {
        setLookupState(lookupMeta, { message: '' })
        writeLookupLabels({})
        return
      }
      if (!checked.valid) {
        setLookupState(lookupMeta, {
          valid: false,
          verified: true,
          message: checked.message
        })
        writeLookupLabels({})
        return
      }
      if (input.value !== checked.value) {
        input.value = checked.value
      }
      applyLookupState(lookupMeta, presetConfig, presetName, checked.value, { libraryName, mediaType }, storeLookupLabel)
    }

    input.addEventListener('input', () => {
      writeLookupLabels({})
      setLookupState(lookupMeta, { message: '' })
    })
    input.addEventListener('change', runLookup)
    input.addEventListener('blur', runLookup)
    runLookup()
    input.dataset.templateScalarLookupBound = 'true'
  })

  root.querySelectorAll('[data-template-string-list]').forEach(wrapper => {
    if (wrapper.dataset.listenerAdded) return
    const hiddenId = wrapper.dataset.hiddenInput
    const hidden = hiddenId ? document.getElementById(hiddenId) : wrapper.querySelector('input[type="hidden"]')
    const lookupLabelsHidden = hiddenId ? document.getElementById(`${hiddenId}__lookup_labels`) : null
    const input = wrapper.querySelector('[data-template-string-input]')
    const addBtn = wrapper.querySelector('[data-template-string-add]')
    const list = wrapper.querySelector('[data-template-string-items]')
    const feedback = wrapper.querySelector('[data-template-string-feedback]')
    const templateVariableKey = String(wrapper.dataset.templateVariableKey || '').trim()
    const mutuallyExclusiveWith = String(wrapper.dataset.mutuallyExclusiveWith || '').trim()
    const inputMode = String(wrapper.dataset.inputMode || 'text').trim().toLowerCase()

    if (!hidden || !input || !addBtn || !list) return

    const presetName = inferTemplateStringListPreset(wrapper, input)
    const presetConfig = templateStringListPresetConfigs[presetName] || templateStringListPresetConfigs.generic_text
    const libraryName = String(wrapper.dataset.libraryName || '').trim()
    const mediaType = String(wrapper.dataset.mediaType || '').trim()
    ensureTemplatePresetDatalist(wrapper, input, presetConfig, presetName)
    if (inputMode === 'select') {
      ensureTemplateSelectOptions(wrapper, input, presetConfig, 'selectOptions')
    }

    function parseStoredStringList (rawValue) {
      const raw = String(rawValue || '').trim()
      if (!raw) return []
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) {
          return parsed.map(item => String(item).trim()).filter(Boolean)
        }
      } catch {
        // fall through to treat as single value
      }
      return [raw]
    }

    function parseLookupLabels () {
      if (!lookupLabelsHidden) return {}
      const raw = String(lookupLabelsHidden.value || '').trim()
      if (!raw) return {}
      try {
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          return Object.fromEntries(
            Object.entries(parsed)
              .map(([key, value]) => [String(key || '').trim(), String(value || '').trim()])
              .filter(([key, value]) => key && value)
          )
        }
      } catch {
        return {}
      }
      return {}
    }

    function writeLookupLabels (labels) {
      if (!lookupLabelsHidden) return
      const cleanLabels = Object.fromEntries(
        Object.entries(labels || {})
          .map(([key, value]) => [String(key || '').trim(), String(value || '').trim()])
          .filter(([key, value]) => key && value)
      )
      lookupLabelsHidden.value = JSON.stringify(cleanLabels)
      lookupLabelsHidden.dispatchEvent(new Event('change', { bubbles: true }))
    }

    function pruneLookupLabels (values) {
      if (!lookupLabelsHidden) return
      const allowed = new Set((values || []).map(value => String(value || '').trim()).filter(Boolean))
      const labels = parseLookupLabels()
      let changed = false
      Object.keys(labels).forEach(key => {
        if (!allowed.has(key)) {
          delete labels[key]
          changed = true
        }
      })
      if (changed) writeLookupLabels(labels)
    }

    function storeLookupLabel (value, label) {
      if (!lookupLabelsHidden || !value || !label) return
      const labels = parseLookupLabels()
      const key = String(value).trim()
      const normalizedLabel = String(label).trim()
      if (!key || !normalizedLabel || labels[key] === normalizedLabel) return
      labels[key] = normalizedLabel
      writeLookupLabels(labels)
      scheduleLookupLabelAutosave()
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
        if (presetConfig.lookupService) {
          lookupMeta.dataset.lookupInline = 'true'
          titleRow.appendChild(lookupMeta)
        } else {
          textWrap.appendChild(lookupMeta)
        }
        lookupMeta.className = presetConfig.lookupService ? 'small ms-2 d-none' : 'small mt-1 d-none'

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

        if (item.valid && presetConfig.lookupService) {
          applyLookupState(lookupMeta, presetConfig, presetName, item.value, { libraryName, mediaType }, storeLookupLabel)
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
      pruneLookupLabels(normalizedValues)
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
    hidden.addEventListener('change', () => {
      syncState(parseValues())
    })
    input.addEventListener('input', clearTransientFeedback)
    input.addEventListener('change', clearTransientFeedback)
    if (String(input.tagName || '').toUpperCase() !== 'SELECT') {
      input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault()
          addValue()
        }
      })
    }

    wrapper.dataset.listenerAdded = 'true'
  })
}

function setupTemplateMappingListHandlers (scope) {
  const templateStringLookupCache = window.__qsTemplateStringLookupCache || new Map()
  window.__qsTemplateStringLookupCache = templateStringLookupCache
  const root = scope || document
  root.querySelectorAll('[data-template-mapping-list]').forEach(wrapper => {
    if (wrapper.dataset.listenerAdded) return

    const hiddenId = wrapper.dataset.hiddenInput
    const hidden = hiddenId ? document.getElementById(hiddenId) : wrapper.querySelector('input[type="hidden"]')
    const keyInput = wrapper.querySelector('[data-template-mapping-key]')
    const valueInput = wrapper.querySelector('[data-template-mapping-value]')
    const addBtn = wrapper.querySelector('[data-template-mapping-add]')
    const list = wrapper.querySelector('[data-template-mapping-items]')
    const feedback = wrapper.querySelector('[data-template-mapping-feedback]')
    const validationPreset = String(wrapper.dataset.validationPreset || '').trim().toLowerCase()
    const keyValidationPreset = String(wrapper.dataset.keyValidationPreset || '').trim().toLowerCase()
    const keyInputMode = String(wrapper.dataset.keyInputMode || 'text').trim().toLowerCase()
    const lookupDisplayMode = String(wrapper.dataset.lookupDisplayMode || 'stacked').trim().toLowerCase()
    const valueDisplayLabel = String(wrapper.dataset.valueDisplayLabel || '').trim()
    const valueKind = String(wrapper.dataset.mappingValueKind || 'string_list').trim().toLowerCase()
    const libraryName = String(wrapper.dataset.libraryName || '').trim()
    const mediaType = String(wrapper.dataset.mediaType || '').trim()
    const keyPresetConfig = keyValidationPreset && templateStringListPresetConfigs[keyValidationPreset]
      ? templateStringListPresetConfigs[keyValidationPreset]
      : null

    if (!hidden || !keyInput || !valueInput || !addBtn || !list) return
    ensureTemplatePresetDatalist(wrapper, keyInput, keyPresetConfig, keyValidationPreset || 'mapping-key')
    if (keyInputMode === 'select') {
      ensureTemplateSelectOptions(wrapper, keyInput, keyPresetConfig, 'keyOptions')
    }

    function getServiceValidationState (serviceName) {
      const el = document.getElementById(`qs-validate-${serviceName}`)
      return String(el?.value || '').trim().toLowerCase() === 'true'
    }

    function setLookupState (target, state) {
      if (!target) return
      target.textContent = state?.message || ''
      const inlineLookup = target.dataset.lookupInline === 'true'
      target.className = inlineLookup ? 'small ms-2' : 'small mt-1'
      if (!state?.message) {
        target.classList.add('d-none')
        return
      }
      target.classList.remove('d-none')
      if (state.level === 'warning') {
        target.classList.add('text-warning')
      } else if (state.valid && state.verified) {
        target.classList.add('text-success')
      } else if (state.verified) {
        target.classList.add('text-danger')
      } else {
        target.classList.add('text-warning')
      }
    }

    async function lookupTemplateStringValue (presetName, value, context = {}) {
      const currentLibraryName = String(context.libraryName || '').trim()
      const currentMediaType = String(context.mediaType || '').trim()
      const cacheKey = `${presetName}:${currentLibraryName}:${currentMediaType}:${value}`
      if (templateStringLookupCache.has(cacheKey)) {
        return templateStringLookupCache.get(cacheKey)
      }
      const request = fetch('/lookup_template_string_value', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          preset: presetName,
          value,
          library_name: currentLibraryName,
          media_type: currentMediaType
        })
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

    function applyLookupState (target, presetConfig, presetName, value, context = {}) {
      if (!target || !presetConfig?.lookupService || !value) return

      if (presetConfig.lookupService === 'tmdb') {
        if (!getServiceValidationState('tmdb')) {
          setLookupState(target, {
            valid: false,
            verified: false,
            message: 'TMDb not validated, so the collection title could not be checked.'
          })
          return
        }

        setLookupState(target, {
          valid: false,
          verified: false,
          message: 'Checking TMDb collection title...'
        })
        lookupTemplateStringValue(presetName, value, context).then(result => {
          if (!target.isConnected) return
          if (result.valid && result.verified && result.label) {
            const successMessage = result.message || `TMDb: ${result.label}`
            setLookupState(target, {
              valid: true,
              verified: true,
              level: result.level,
              message: successMessage
            })
            return
          }
          setLookupState(target, {
            valid: Boolean(result.valid),
            verified: Boolean(result.verified),
            message: result.message || 'TMDb lookup failed.'
          })
        })
        return
      }

      if (presetConfig.lookupService === 'plex') {
        if (!getServiceValidationState('plex')) {
          setLookupState(target, {
            valid: false,
            verified: false,
            message: 'Plex not validated, so the IMDb ID could not be checked against the active library.'
          })
          return
        }
        if (!String(context.libraryName || '').trim()) {
          setLookupState(target, {
            valid: false,
            verified: false,
            message: 'Library context is unavailable for Plex lookup.'
          })
          return
        }

        setLookupState(target, {
          valid: false,
          verified: false,
          message: 'Checking Plex library for this IMDb ID...'
        })
        lookupTemplateStringValue(presetName, value, context).then(result => {
          if (!target.isConnected) return
          if (result.valid && result.verified && result.label) {
            const successMessage = result.message || `Plex: ${result.label}`
            setLookupState(target, {
              valid: true,
              verified: true,
              level: result.level,
              message: successMessage
            })
            return
          }
          setLookupState(target, {
            valid: Boolean(result.valid),
            verified: Boolean(result.verified),
            message: result.message || 'Plex lookup failed.'
          })
        })
      }
    }

    if (keyValidationPreset === 'tmdb_collection_id' || keyValidationPreset === 'numeric_id' || keyValidationPreset === 'year' || keyValidationPreset === 'decade') {
      keyInput.setAttribute('inputmode', 'numeric')
    }
    if (keyValidationPreset.startsWith('imdb_id')) {
      keyInput.setAttribute('autocapitalize', 'off')
    }

    function parseValuesList (rawValue) {
      if (Array.isArray(rawValue)) {
        return rawValue.map(item => String(item).trim()).filter(Boolean)
      }
      const text = String(rawValue || '').trim()
      if (!text) return []
      return text.split(',').map(item => item.trim()).filter(Boolean)
    }

    function parseScalarValue (rawValue) {
      if (Array.isArray(rawValue)) {
        return String(rawValue[0] || '').trim()
      }
      return String(rawValue || '').trim()
    }

    function parseStoredMapping (rawValue) {
      const raw = String(rawValue || '').trim()
      if (!raw) return {}
      try {
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          return parsed
        }
      } catch {
        // fall through to empty mapping
      }
      return {}
    }

    function setFeedback (message = '') {
      if (!feedback) return
      feedback.textContent = message
      feedback.classList.toggle('d-none', !message)
      feedback.classList.toggle('d-block', Boolean(message))
    }

    function setKeyInputValidity (result) {
      if (!keyInput) return
      if (!result || result.valid) {
        keyInput.classList.remove('is-invalid')
        return
      }
      keyInput.classList.add('is-invalid')
    }

    function setValueInputValidity (result) {
      if (!valueInput) return
      if (!result || result.valid) {
        valueInput.classList.remove('is-invalid')
        return
      }
      valueInput.classList.add('is-invalid')
    }

    function normalizeMappingKey (rawKey) {
      const keyText = String(rawKey || '').trim()
      if (!keyText) return ''
      return keyPresetConfig?.normalize ? keyPresetConfig.normalize(keyText) : keyText
    }

    function validateKey (rawKey) {
      const normalized = normalizeMappingKey(rawKey)
      if (!normalized) {
        return { value: '', valid: false, message: 'Enter a key before adding it.' }
      }
      if (!keyPresetConfig?.validate) {
        return { value: normalized, valid: true, message: '' }
      }
      const result = keyPresetConfig.validate(normalized)
      return {
        value: normalized,
        valid: Boolean(result.valid),
        message: result.message || 'Enter a valid key.'
      }
    }

    function normalizeMappingValue (rawValue) {
      if (valueKind === 'string_list') {
        const values = parseValuesList(rawValue)
        return values.length ? values : null
      }
      const value = parseScalarValue(rawValue)
      return value || null
    }

    function normalizeMapping (mapping) {
      const normalized = {}
      Object.entries(mapping || {}).forEach(([rawKey, rawValues]) => {
        const key = normalizeMappingKey(rawKey)
        if (!key) return
        const value = normalizeMappingValue(rawValues)
        if (value == null) return
        normalized[key] = value
      })
      return normalized
    }

    function renderList (mapping) {
      list.replaceChildren()
      Object.entries(mapping).forEach(([key, value]) => {
        const keyResult = validateKey(key)
        const li = document.createElement('li')
        li.className = 'list-group-item d-flex justify-content-between align-items-center'
        if (!keyResult.valid) li.classList.add('list-group-item-danger')

        const textWrap = document.createElement('div')
        textWrap.className = 'd-flex flex-column'

        const titleRow = document.createElement('div')
        titleRow.className = 'd-flex align-items-center gap-2'

        const title = document.createElement('span')
        title.textContent = key
        titleRow.appendChild(title)

        if (!keyResult.valid) {
          const badge = document.createElement('span')
          badge.className = 'badge text-bg-danger'
          badge.textContent = 'Invalid'
          badge.title = keyResult.message
          titleRow.appendChild(badge)
        }

        textWrap.appendChild(titleRow)

        const lookupMeta = document.createElement('div')
        if (lookupDisplayMode === 'inline') {
          lookupMeta.dataset.lookupInline = 'true'
          titleRow.appendChild(lookupMeta)
        }
        lookupMeta.className = lookupDisplayMode === 'inline' ? 'small ms-2 d-none' : 'small mt-1 d-none'
        if (lookupDisplayMode !== 'inline') {
          textWrap.appendChild(lookupMeta)
        }

        const details = document.createElement('div')
        details.className = 'small text-muted'
        const rawDetails = Array.isArray(value) ? value.join(', ') : String(value || '')
        details.textContent = valueDisplayLabel && !Array.isArray(value)
          ? `${valueDisplayLabel}: ${rawDetails}`
          : rawDetails
        textWrap.appendChild(details)

        const button = document.createElement('button')
        button.type = 'button'
        button.className = 'btn btn-sm btn-danger'
        button.setAttribute('aria-label', 'Remove')
        const icon = document.createElement('i')
        icon.className = 'bi bi-x-lg'
        button.appendChild(icon)

        li.append(textWrap, button)
        list.appendChild(li)

        if (keyResult.valid && keyPresetConfig?.lookupService) {
          applyLookupState(lookupMeta, keyPresetConfig, keyValidationPreset, keyResult.value, { libraryName, mediaType })
        }

        button.addEventListener('click', () => {
          const current = normalizeMapping(parseStoredMapping(hidden.value))
          delete current[key]
          hidden.value = JSON.stringify(current)
          renderList(current)
          setFeedback('')
        })
      })
    }

    function syncState (mapping, message = '') {
      const normalized = normalizeMapping(mapping)
      hidden.value = JSON.stringify(normalized)
      renderList(normalized)
      setFeedback(message)
      setKeyInputValidity({ valid: true })
      setValueInputValidity({ valid: true })
      return normalized
    }

    function addEntry () {
      const keyResult = validateKey(keyInput.value)
      if (!keyResult.valid) {
        setKeyInputValidity(keyResult)
        setFeedback(keyResult.message || 'Enter a valid key before adding it.')
        return
      }
      const normalizedValue = normalizeMappingValue(valueInput.value)
      if (normalizedValue == null) {
        setKeyInputValidity({ valid: true })
        setFeedback('Enter at least one value before adding it.')
        return
      }
      if (validationPreset === 'url' && typeof URLValidation !== 'undefined' && typeof URLValidation.validateValue === 'function') {
        const validationResult = URLValidation.validateValue(normalizedValue)
        if (!validationResult.valid) {
          setValueInputValidity(validationResult)
          setKeyInputValidity({ valid: true })
          setFeedback(validationResult.message || 'Enter a valid URL before adding it.')
          return
        }
      }
      const current = normalizeMapping(parseStoredMapping(hidden.value))
      current[keyResult.value] = normalizedValue
      syncState(current)
      keyInput.value = ''
      valueInput.value = ''
    }

    syncState(parseStoredMapping(hidden.value))

    addBtn.addEventListener('click', addEntry)
    hidden.addEventListener('change', () => {
      syncState(parseStoredMapping(hidden.value))
    })
    const clearKeyFeedback = () => {
      setFeedback('')
      setKeyInputValidity({ valid: true })
    }
    keyInput.addEventListener('input', clearKeyFeedback)
    keyInput.addEventListener('change', clearKeyFeedback)
    valueInput.addEventListener('input', () => {
      setFeedback('')
      setValueInputValidity({ valid: true })
    })
    if (String(keyInput.tagName || '').toUpperCase() !== 'SELECT') {
      keyInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault()
          addEntry()
        }
      })
    }
    valueInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault()
        addEntry()
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

function nbspLeadingSpaces (s) {
  const lstripped = s.replace(/^ +/, '')
  const leading = s.length - lstripped.length
  const rstripped = lstripped.replace(/ +$/, '')
  const trailing = lstripped.length - rstripped.length
  return ' '.repeat(leading) + rstripped + ' '.repeat(trailing)
}

function refreshPickerLabels () {
  if (!libraryPicker) return
  libraryPicker.querySelectorAll('option[value]').forEach(opt => {
    const base = opt.dataset.label || opt.textContent.replace(/\s+\(configured\)$/, '')
    const configured = opt.dataset.configured === 'true'
    const displayBase = nbspLeadingSpaces(base)
    opt.textContent = configured ? `${displayBase} (configured)` : displayBase
  })
  updateConfiguredCounts()
}

function isLibraryCardInitializing (card) {
  return libraryCardInitializing > 0 || card?.dataset?.libraryInitializing === 'true'
}

function setLibraryIncludedFromUserEdit (card, libraryId) {
  if (!libraryPicker || !card || !libraryId) return
  const toggle = card.querySelector('.include-library-toggle')
  if (!toggle || toggle.checked || toggle.disabled) return
  const targetInputId = toggle.dataset.targetInput
  const targetInput = targetInputId ? document.getElementById(targetInputId) : null
  const option = libraryPicker.querySelector(`option[value="${libraryId}"]`)
  toggle.checked = true
  if (targetInput) targetInput.value = toggle.value
  if (option) option.dataset.configured = 'true'
  toggle.dispatchEvent(new Event('change', { bubbles: true }))
}

function shouldAutoIncludeLibraryEditTarget (target) {
  if (!target || !target.closest) return false
  if (target.closest('[data-resetting="true"]')) return false
  if (target.closest('.external-yaml-editor-modal')) return false
  if (target.matches('.include-library-toggle, .library-advanced-toggle, .accordion-button')) return false
  if (target.matches('[data-bs-toggle="collapse"], [data-bs-toggle="modal"], [data-bs-dismiss]')) return false
  if (target.matches('[data-toggle-secret-visibility], [data-collection-details-toggle], [data-overlay-details-toggle]')) return false
  if (target.matches('[data-external-yaml-edit], [data-external-yaml-create], [data-external-yaml-choose]')) return false

  if (target.matches('[data-playlist-key-toggle]')) return true
  if (target.matches('[data-template-string-add], [data-template-mapping-add], [data-add-asset-directory]')) return true
  if (target.matches('[data-add-collection-file], [data-add-metadata-file], [data-add-overlay-file], [data-add-playlist-file]')) return true
  if (target.matches('[data-remove-collection-file], [data-remove-metadata-file], [data-remove-overlay-file], [data-remove-playlist-file]')) return true
  if (target.matches('.library-remove-asset-directory')) return true

  const field = target.matches('input, select, textarea') ? target : target.closest('input, select, textarea')
  if (!field || field.disabled || !field.name) return false
  if (field.type === 'file') return false
  if (field.type === 'hidden' && isInternalTemplateMetadataField(field)) return false
  if (field.dataset?.skipYaml === 'true' || field.dataset?.skipOverrideCount === 'true') return false
  if (field.classList.contains('include-library-toggle')) return false
  return true
}

function wireAutoIncludeOnLibraryEdits (card, libraryId) {
  if (!card || card.dataset.autoIncludeOnEditBound === 'true') return
  const maybeInclude = event => {
    if (!event.isTrusted || isLibraryCardInitializing(card)) return
    if (!shouldAutoIncludeLibraryEditTarget(event.target)) return
    setLibraryIncludedFromUserEdit(card, libraryId)
  }
  card.addEventListener('input', maybeInclude)
  card.addEventListener('change', maybeInclude)
  card.addEventListener('click', maybeInclude)
  card.dataset.autoIncludeOnEditBound = 'true'
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
    status.textContent = included ? 'Included in config' : 'Excluded from config'
    status.classList.toggle('bg-success', included)
    status.classList.toggle('bg-secondary', !included)
    if (playlistToggle) {
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
  } catch {}
  const initialVisible = persisted === 'true' || (persisted !== 'false' && hasConfiguredAdvancedValues(card))
  setAdvancedVisibility(card, initialVisible)

  toggle.addEventListener('click', () => {
    const nextVisible = card.dataset.advancedVisible !== 'true'
    setAdvancedVisibility(card, nextVisible)
    try {
      if (window.localStorage) window.localStorage.setItem(advancedVisibilityStorageKey, nextVisible ? 'true' : 'false')
    } catch {}
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

function setCachedCardFormSubmission (card, cached) {
  if (!card) return
  card.querySelectorAll('input, select, textarea').forEach(el => {
    if (cached) {
      el.dataset.qsCachedDisabled = el.disabled ? 'true' : 'false'
      el.disabled = true
    } else if (el.dataset.qsCachedDisabled !== undefined) {
      el.disabled = el.dataset.qsCachedDisabled === 'true'
      delete el.dataset.qsCachedDisabled
    }
  })
}

function moveCurrentToCache () {
  const current = libraryContainer.firstElementChild
  if (current) {
    setCachedCardFormSubmission(current, true)
    current.style.display = 'none'
    libraryCache.appendChild(current)
  }
}

function initializeLibraryCardControls (card, libraryId) {
  libraryCardInitializing += 1
  if (card) card.dataset.libraryInitializing = 'true'
  try {
    initPlaylistKeyToggleGroups(card)
    initPlaylistUserPickers(card)
    initPlaylistFilesEditors(card)
    initSecretVisibilityToggles(card)
    syncHiddenCheckboxPairs(card)
    wireIncludeToggle(card, libraryId)
    wireAutoIncludeOnLibraryEdits(card, libraryId)
    wireAdvancedToggle(card)
    wireLibraryServiceValidationButtons(card)
    refreshPickerLabels()
    initTooltips(card)
    sortLanguageSelects(card)
    setupOverlayLanguageWeightBuilders(card)
    initNumericOnlyInputs(card)
    setupCollectionTemplateFieldRules(card)
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
    setupTemplateMappingListHandlers(card)
    setupMappingListHandlers('genre_mapper', card)
    setupMappingListHandlers('content_rating_mapper', card)
    wireOverlayDetailToggles(card)
    wireOverlayVariableSectionToggles(card)
    wireCollectionDetailToggles(card)
    wireCollectionVariableSectionToggles(card)
    setupParentChildToggleVisibility(card)
    if (typeof setupParentChildToggleSync === 'function') {
      setupParentChildToggleSync()
    }
    setupAddMissingDependencies(card)
    wireOverlayTemplateSections(card)
    wireCollectionTemplateSections(card)
    wireOverlayVariableSections(card)
    wireCollectionVariableSections(card)
    wireLibraryOverrideScopes(card)
    wireLazyCollectionGroups(card)
    updateLazySectionOverrideSummaries(card)
    refreshTemplateOverrideState(card)
    wireOffsetReset(card)
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
      EventHandler.attachLibraryListeners(card)
    }
    if (typeof PathValidation !== 'undefined' && PathValidation.attach) {
      PathValidation.attach(card)
    }
    if (typeof URLValidation !== 'undefined' && URLValidation.attach) {
      URLValidation.attach(card)
    }
    if (typeof ValidationHandler !== 'undefined' && ValidationHandler.updateValidationState) {
      ValidationHandler.updateValidationState()
    }
    wireFontUploads(card)
    wireFontPreviews(card)
    wireFontPickerButtons(card)
    bindDependencyRequirementHintLiveRefresh(card)
    scheduleDependencyRequirementHintRefresh(0)
  } finally {
    libraryCardInitializing = Math.max(0, libraryCardInitializing - 1)
    if (card) delete card.dataset.libraryInitializing
  }
}

function wireLazyLibrarySections (card) {
  if (!card || card.dataset.lazyLibrarySectionsBound === 'true') return

  card.addEventListener('shown.bs.collapse', event => {
    const collapse = event.target
    if (!collapse || !collapse.querySelector) return
    const placeholder = collapse.querySelector('[data-library-lazy-section][data-library-id]')
    if (!placeholder || placeholder.dataset.lazyState === 'loaded' || placeholder.dataset.lazyState === 'loading') return

    const sectionName = placeholder.dataset.libraryLazySection
    const libraryId = placeholder.dataset.libraryId
    if (!sectionName || !libraryId) return

    const spinner = placeholder.querySelector('.spinner-border')
    const status = placeholder.querySelector('span')
    placeholder.dataset.lazyState = 'loading'
    spinner?.classList.remove('d-none')
    if (status) status.textContent = `Loading ${sectionName} settings...`

    fetch(`/library_fragment/${encodeURIComponent(libraryId)}/section/${encodeURIComponent(sectionName)}`, {
      credentials: 'same-origin'
    })
      .then(res => {
        if (!res.ok) throw new Error(`Failed to load ${sectionName} (${res.status})`)
        return res.text()
      })
      .then(html => {
        const body = placeholder.closest('.accordion-body')
        if (!body) return
        body.innerHTML = html
        placeholder.dataset.lazyState = 'loaded'
        initializeLibraryCardControls(card, libraryId)
      })
      .catch(err => {
        console.error('[Libraries] Failed to load lazy library section', err)
        placeholder.dataset.lazyState = 'error'
        spinner?.classList.add('d-none')
        if (status) status.textContent = `Unable to load ${sectionName} settings. Close and reopen this section to retry.`
        if (typeof showToast === 'function') {
          showToast('error', `Unable to load ${sectionName} settings. Try again.`)
        }
      })
  })

  card.dataset.lazyLibrarySectionsBound = 'true'
}

function loadedCollectionGroupMarker (card) {
  if (!card) return null
  let marker = card.querySelector('input[type="hidden"][name="__loaded_collection_groups"]')
  if (marker) return marker

  marker = document.createElement('input')
  marker.type = 'hidden'
  marker.name = '__loaded_collection_groups'
  marker.value = ''
  card.appendChild(marker)
  return marker
}

function resetCollectionDefaultsMarker (card) {
  if (!card) return null
  let marker = card.querySelector('input[type="hidden"][name="__reset_collection_defaults"]')
  if (marker) return marker

  marker = document.createElement('input')
  marker.type = 'hidden'
  marker.name = '__reset_collection_defaults'
  marker.value = 'false'
  card.appendChild(marker)
  return marker
}

function markCollectionDefaultsReset (card) {
  const marker = resetCollectionDefaultsMarker(card)
  if (marker) marker.value = 'true'
}

function markLazyCollectionGroupLoaded (card, groupIndex) {
  const marker = loadedCollectionGroupMarker(card)
  if (!marker) return
  const values = new Set(String(marker.value || '').split(',').map(value => value.trim()).filter(Boolean))
  values.add(String(groupIndex))
  marker.value = Array.from(values).sort((a, b) => Number(a) - Number(b)).join(',')
}

function loadLazyCollectionGroup (collapse, card) {
  if (!collapse || collapse.dataset?.collectionGroupLazyCollapse !== 'true') {
    return Promise.resolve(collapse?.closest('[data-collection-group-shell="true"]') || null)
  }
  if (collapse.dataset.lazyState === 'loading') {
    return Promise.reject(new Error('Collection group is already loading.'))
  }

  const libraryId = collapse.dataset.libraryId || card?.dataset?.libraryId || activeLibraryId
  const groupIndex = collapse.dataset.collectionGroupIndex
  if (!libraryId || groupIndex === undefined) {
    return Promise.reject(new Error('Missing collection group identifiers.'))
  }

  const shell = collapse.closest('[data-collection-group-shell="true"]')
  const placeholder = collapse.querySelector('[data-collection-group-lazy-placeholder]')
  const spinner = placeholder?.querySelector('.spinner-border')
  const status = placeholder?.querySelector('span')
  collapse.dataset.lazyState = 'loading'
  spinner?.classList.remove('d-none')
  if (status) status.textContent = 'Loading collection group settings...'

  return fetch(`/library_fragment/${encodeURIComponent(libraryId)}/section/collections/group/${encodeURIComponent(groupIndex)}`, {
    credentials: 'same-origin'
  })
    .then(res => {
      if (!res.ok) throw new Error(`Failed to load collection group (${res.status})`)
      return res.text()
    })
    .then(html => {
      if (!shell) return null
      const template = document.createElement('template')
      template.innerHTML = String(html || '').trim()
      const replacement = template.content.firstElementChild
      if (!replacement) throw new Error('Empty collection group fragment')
      shell.replaceWith(replacement)
      replacement.dataset.collectionGroupLoaded = 'true'
      replacement.dataset.collectionGroupIndex = String(groupIndex)
      const replacementCollapse = replacement.querySelector('.accordion-collapse')
      const replacementButton = replacement.querySelector('.accordion-button')
      if (replacementCollapse) {
        replacementCollapse.classList.add('show')
        replacementCollapse.dataset.collectionGroupLoaded = 'true'
        replacementCollapse.dataset.collectionGroupIndex = String(groupIndex)
      }
      if (replacementButton) {
        replacementButton.classList.remove('collapsed')
        replacementButton.setAttribute('aria-expanded', 'true')
      }
      markLazyCollectionGroupLoaded(card, groupIndex)
      initializeLibraryCardControls(card, libraryId)
      refreshTemplateOverrideState(card)
      return replacement
    })
}

function wireLazyCollectionGroups (card) {
  if (!card || card.dataset.lazyCollectionGroupsBound === 'true') return

  card.addEventListener('shown.bs.collapse', event => {
    const collapse = event.target
    if (!collapse || collapse.dataset?.collectionGroupLazyCollapse !== 'true') return
    if (collapse.dataset.lazyState === 'loaded' || collapse.dataset.lazyState === 'loading') return
    const placeholder = collapse.querySelector('[data-collection-group-lazy-placeholder]')
    const spinner = placeholder?.querySelector('.spinner-border')
    const status = placeholder?.querySelector('span')

    loadLazyCollectionGroup(collapse, card)
      .catch(err => {
        console.error('[Libraries] Failed to load lazy collection group', err)
        collapse.dataset.lazyState = 'error'
        spinner?.classList.add('d-none')
        if (status) status.textContent = 'Unable to load this collection group. Close and reopen it to retry.'
        if (typeof showToast === 'function') {
          showToast('error', 'Unable to load collection group settings. Try again.')
        }
      })
  })

  card.dataset.lazyCollectionGroupsBound = 'true'
}

function mountCard (card, libraryId) {
  libraryContainer.replaceChildren()
  setCachedCardFormSubmission(card, false)
  card.style.display = ''
  libraryContainer.appendChild(card)
  activeLibraryId = libraryId
  wireLazyLibrarySections(card)
  initializeLibraryCardControls(card, libraryId)
}

function fetchLibraryFragment (libraryId, attempt = 0) {
  return fetch(`/library_fragment/${encodeURIComponent(libraryId)}`, {
    credentials: 'same-origin'
  })
    .then(res => {
      if (!res.ok) {
        throw new Error(`Failed to load library ${libraryId} (${res.status})`)
      }
      return res.text()
    })
    .catch(err => {
      if (attempt < 1) {
        return new Promise(resolve => window.setTimeout(resolve, 250))
          .then(() => fetchLibraryFragment(libraryId, attempt + 1))
      }
      throw err
    })
}

function restorePreviousLibrarySelection (previousLibraryId) {
  if (libraryPicker && previousLibraryId) {
    libraryPicker.value = previousLibraryId
  }
  if (!libraryContainer.firstElementChild && previousLibraryId) {
    const previousCard = libraryCache.querySelector(`[data-library-id="${previousLibraryId}"]`)
    if (previousCard) {
      mountCard(previousCard, previousLibraryId)
    }
  }
}

wireFontPickerModal()

function isUncheckedTemplateParentToggle (field) {
  if (!field || field.type !== 'checkbox' || field.dataset?.radioGroup === 'true') return false
  if (field.dataset?.default !== undefined) return false
  return !field.checked && Boolean(field.matches('[data-template-group], .overlay-toggle'))
}

function shouldOmitDefaultFieldFromLibraryPayload (field) {
  if (!field || !field.dataset || field.dataset.default === undefined) return false
  if (field.classList?.contains('include-library-toggle') || field.classList?.contains('playlist-library-toggle')) return false
  if (String(field.name || '').endsWith('-library') || String(field.name || '').endsWith('-playlist')) return false
  if (isInternalTemplateMetadataField(field)) return false
  return !isCollectionSectionFieldConfigured([field])
}

function buildPayloadFromCard (card) {
  const payload = {}
  const libraryId = activeLibraryId || String(card?.querySelector('[name]')?.name || '').split('-')[0]
  const loadedLazySections = []
  ;['collections', 'overlays'].forEach(sectionName => {
    const section = document.getElementById(`${libraryId}-${sectionName}`)
    const placeholder = card.querySelector(`[data-library-lazy-section="${sectionName}"][data-library-id="${libraryId}"]`)
    if (section && !placeholder) {
      loadedLazySections.push(sectionName)
    }
  })
  payload.__loaded_sections = loadedLazySections
  const loadedCollectionGroups = new Set()
  const collectionGroupMarker = card.querySelector('input[type="hidden"][name="__loaded_collection_groups"]')
  String(collectionGroupMarker?.value || '').split(',').forEach(value => {
    const trimmed = value.trim()
    if (trimmed) loadedCollectionGroups.add(trimmed)
  })
  card.querySelectorAll('[data-collection-group-loaded="true"][data-collection-group-index]').forEach(group => {
    loadedCollectionGroups.add(String(group.dataset.collectionGroupIndex || '').trim())
  })
  payload.__loaded_collection_groups = Array.from(loadedCollectionGroups)
    .filter(Boolean)
    .sort((a, b) => Number(a) - Number(b))
  const resetCollectionDefaults = card.querySelector('input[type="hidden"][name="__reset_collection_defaults"]')
  if (resetCollectionDefaults && resetCollectionDefaults.value === 'true') {
    payload.__reset_collection_defaults = 'true'
  }
  const checkboxNames = new Set(
    Array.from(card.querySelectorAll('input[type="checkbox"][name]'))
      .map(el => String(el.name || '').trim())
      .filter(Boolean)
  )
  const radioCheckboxValues = new Map()
  card.querySelectorAll('input[type="checkbox"][name][data-radio-group="true"]').forEach(el => {
    const name = String(el.name || '').trim()
    if (!name || el.disabled) return
    if (!radioCheckboxValues.has(name)) {
      radioCheckboxValues.set(name, '')
    }
    if (el.checked) {
      radioCheckboxValues.set(name, el.value || 'true')
    }
  })
  card.querySelectorAll('input, select, textarea').forEach(el => {
    if (!el.name || el.disabled) return
    if (el.name === '__loaded_collection_groups' || el.name === '__reset_collection_defaults') return
    if (el.dataset && el.dataset.skipYaml === 'true') return
    if (el.type === 'file') return

    if (el.type === 'hidden' && checkboxNames.has(String(el.name || '').trim())) {
      return
    }
    if (isUncheckedTemplateParentToggle(el)) return
    if (shouldOmitDefaultFieldFromLibraryPayload(el)) return

    if (el.tagName === 'SELECT' && el.multiple) {
      payload[el.name] = Array.from(el.selectedOptions).map(opt => opt.value)
      return
    }

    if (el.type === 'checkbox') {
      if (el.dataset && el.dataset.radioGroup === 'true') {
        if (!Object.prototype.hasOwnProperty.call(payload, el.name)) {
          const selectedValue = radioCheckboxValues.get(el.name) || ''
          if (selectedValue) {
            payload[el.name] = selectedValue
          }
        }
        return
      }
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
      if (shouldOmitDefaultFieldFromLibraryPayload(el)) return
      payload[el.name] = el.value ?? ''
    })
  }
  card.querySelectorAll('input.playlist-library-toggle[type="checkbox"][name]:disabled').forEach(el => {
    payload[el.name] = el.checked ? (el.value || 'true') : 'false'
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
    container.dataset.assetDirectoryCounter = String(container.querySelectorAll(`input[name="${inputName}"]`).length)

    if (addBtn) {
      addBtn.addEventListener('click', () => {
        const row = buildLibraryAssetDirectoryRow(container, inputName, '')
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

function buildLibraryAssetDirectoryRow (container, inputName, value = '') {
  const current = Number(container?.dataset?.assetDirectoryCounter || '0') || 0
  const next = current + 1
  if (container) {
    container.dataset.assetDirectoryCounter = String(next)
  }

  const row = document.createElement('div')
  row.className = 'input-group mb-2'

  const input = document.createElement('input')
  input.type = 'text'
  input.className = 'form-control'
  input.name = inputName
  input.id = `${container?.id || 'asset_directory'}_${next}`
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

function resetLibraryAssetDirectoryContainers (scope, changes) {
  if (!scope) return []
  const changedInputs = []

  scope.querySelectorAll('[data-library-asset-directory-container]').forEach(container => {
    const inputName = container.dataset.inputName
    if (!inputName) return

    const rows = Array.from(container.querySelectorAll('.input-group'))
    const values = Array.from(container.querySelectorAll(`input[name="${inputName}"]`))
      .map(input => String(input.value || '').trim())
    const populated = values.filter(Boolean)
    const needsReset = populated.length > 0 || rows.length !== 1
    if (!needsReset) return

    if (Array.isArray(changes)) {
      changes.push({
        label: 'Asset Directory',
        from: populated.length ? populated.join(', ') : `${rows.length} blank rows`,
        to: 'Default'
      })
    }

    container.replaceChildren()
    container.dataset.assetDirectoryCounter = '0'
    const row = buildLibraryAssetDirectoryRow(container, inputName, '')
    container.appendChild(row)
    if (typeof PathValidation !== 'undefined' && PathValidation.attach) {
      PathValidation.attach(row)
    }
    const input = row.querySelector(`input[name="${inputName}"]`)
    if (input) {
      changedInputs.push(input)
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
    }
  })

  return changedInputs
}

function scheduleLookupLabelAutosave (delayMs = 900) {
  if (lookupLabelAutosaveTimer) {
    clearTimeout(lookupLabelAutosaveTimer)
    lookupLabelAutosaveTimer = null
  }
  lookupLabelAutosaveTimer = setTimeout(() => {
    lookupLabelAutosaveTimer = null
    if (!activeLibraryId || window.QS_SWITCHING_CONFIG) return
    autosaveActiveLibrary({ quiet: true, lookupLabelsOnly: true })
      .catch(err => {
        console.warn('[Autosave] Failed to persist lookup labels', err)
      })
  }, Math.max(0, Number(delayMs) || 0))
}

function buildLookupLabelPayloadFromCard (card) {
  const payload = { __lookup_labels_only: true }
  if (!card) return payload
  card.querySelectorAll('input[type="hidden"][name$="__lookup_labels"]').forEach(el => {
    if (!el.name || el.disabled) return
    payload[el.name] = el.value ?? '{}'
  })
  return payload
}

function autosaveActiveLibrary (options = {}) {
  const card = libraryContainer.firstElementChild
  if (!activeLibraryId || !card) return Promise.resolve()
  if (window.QS_SWITCHING_CONFIG) return Promise.resolve()
  const quiet = Boolean(options && options.quiet)
  const lookupLabelsOnly = Boolean(options && options.lookupLabelsOnly)

  if (!lookupLabelsOnly && typeof PathValidation !== 'undefined' && PathValidation.validateAll) {
    const pathValid = PathValidation.validateAll(card)
    if (!pathValid) {
      if (typeof ValidationHandler !== 'undefined' && typeof ValidationHandler.focusFirstInvalidField === 'function') {
        ValidationHandler.focusFirstInvalidField(card)
      }
      if (!quiet && typeof showToast === 'function') {
        showToast('error', 'Please fix invalid path fields before saving.')
      }
      return Promise.reject(new Error('Invalid path fields'))
    }
  }

  if (!lookupLabelsOnly && typeof URLValidation !== 'undefined' && URLValidation.validateAll) {
    const urlValid = URLValidation.validateAll(card)
    if (!urlValid) {
      if (typeof ValidationHandler !== 'undefined' && typeof ValidationHandler.focusFirstInvalidField === 'function') {
        ValidationHandler.focusFirstInvalidField(card)
      }
      if (!quiet && typeof showToast === 'function') {
        showToast('error', 'Please fix invalid URL fields before saving.')
      }
      return Promise.reject(new Error('Invalid URL fields'))
    }
  }

  const payload = lookupLabelsOnly ? buildLookupLabelPayloadFromCard(card) : buildPayloadFromCard(card)
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
      if (data && data.success && !quiet && typeof showToast === 'function') {
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
      if (!quiet && typeof showToast === 'function') {
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
        refreshTemplateOverrideState(libraryContainer?.firstElementChild || document)
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

  // Replace the previous modal source/target closure each time this opens.
  copyConfirmBtn.onclick = onConfirm
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
        moveCurrentToCache()
        libraryContainer.replaceChildren()
        activeLibraryId = null
        setLoading(false)
        return
      }

      const cached = libraryCache.querySelector(`[data-library-id="${libraryId}"]`)
      if (cached) {
        if (requestId !== loadRequestId) return
        moveCurrentToCache()
        mountCard(cached, libraryId)
        setLoading(false)
        return
      }

      fetchLibraryFragment(libraryId)
        .then(html => {
          if (requestId !== loadRequestId) return
          const parser = new DOMParser()
          const doc = parser.parseFromString(html, 'text/html')
          const parsedCard = doc.body.firstElementChild
          const card = parsedCard ? document.importNode(parsedCard, true) : null
          if (!card) throw new Error('Empty fragment response')
          moveCurrentToCache()
          mountCard(card, libraryId)
          setLoading(false)
        })
        .catch(err => {
          if (requestId !== loadRequestId) return
          console.error('[Libraries] Failed to load library fragment', err)
          restorePreviousLibrarySelection(previousLibraryId)
          if (typeof showToast === 'function') {
            showToast('error', 'Unable to load that library. Your current library stayed open; try again.')
          }
          setLoading(false)
        })
    })
    .catch(() => {
      if (requestId !== loadRequestId) return
      restorePreviousLibrarySelection(previousLibraryId)
      setLoading(false)
    })
}

if (libraryPicker) {
  libraryPicker.addEventListener('change', (e) => {
    loadLibrary(e.target.value, 'switch')
  })

  refreshPickerLabels()
  libraryPicker.value = ''
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
setupCollectionTemplateFieldRules()
setupCustomStringListHandlers('mass_genre_update')
setupCustomStringListHandlers('radarr_remove_by_tag')
setupCustomStringListHandlers('sonarr_remove_by_tag')
setupCustomStringListHandlers('metadata_backup')
setupCustomStringListHandlers('mass_content_rating_update')
setupCustomStringListHandlers('mass_genre_mapper')
setupTemplateStringListHandlers()
setupTemplateMappingListHandlers()
setupMappingListHandlers('genre_mapper')
setupMappingListHandlers('content_rating_mapper')

document.querySelectorAll('.overlay-template-section').forEach((el) => {
  el.style.display = 'none'
})

wireOverlayDetailToggles()
wireOverlayVariableSectionToggles()
wireCollectionDetailToggles()
wireCollectionVariableSectionToggles()
wireOverlayTemplateSections()
wireCollectionTemplateSections()
wireOverlayVariableSections()
wireCollectionVariableSections()
wireRatingsOffsetSync()

document.addEventListener('click', (e) => {
  const btn = e.target.closest('.copy-library-btn')
  if (!btn) return
  const sourceId = btn.dataset.libraryId
  const sourceName = btn.dataset.libraryName
  const sourceType = btn.dataset.libraryType
  openCopyModal(sourceId, sourceName, sourceType)
})

function compareCollectionSectionValues (a, b) {
  const aTrimmed = String(a || '').trim()
  const bTrimmed = String(b || '').trim()
  const aNumeric = /^\d+$/.test(aTrimmed)
  const bNumeric = /^\d+$/.test(bTrimmed)
  if (aNumeric && bNumeric) return Number(aTrimmed) - Number(bTrimmed)
  if (aNumeric) return -1
  if (bNumeric) return 1
  if (aTrimmed && bTrimmed) return aTrimmed.localeCompare(bTrimmed)
  if (aTrimmed) return -1
  if (bTrimmed) return 1
  return 0
}

function getCollectionSectionEntries (libraryId) {
  const container = document.getElementById(`${libraryId}-container`)
  if (!container) return []
  const groups = Array.from(container.querySelectorAll('[data-collection-config="true"]'))
  const entries = []
  groups.forEach((group, index) => {
    const collectionId = group.dataset.collectionId || ''
    const label = group.dataset.collectionLabel || collectionId
    const toggle = collectionId ? group.querySelector(`input[type="checkbox"]#${libraryId}-${collectionId}`) : null
    if (!toggle || !toggle.checked) return
    const input = group.querySelector('input[name$="_collection_section"]')
    if (!input) return
    entries.push({
      collectionId,
      label,
      inputId: input.id,
      defaultValue: String(input.dataset.default || '').trim(),
      currentValue: String(input.value || '').trim(),
      effectiveValue: String(input.value || input.dataset.default || '').trim(),
      domIndex: index
    })
  })
  entries.sort((left, right) => {
    const byValue = compareCollectionSectionValues(left.effectiveValue, right.effectiveValue)
    if (byValue !== 0) return byValue
    return left.domIndex - right.domIndex
  })
  return entries
}

function buildCollectionSectionListItem (entry, position) {
  const li = document.createElement('li')
  li.className = 'list-group-item sortable-item d-flex justify-content-between align-items-center gap-3'
  li.dataset.inputId = entry.inputId
  li.dataset.collectionId = entry.collectionId
  li.innerHTML = `
    <div class="d-flex align-items-center gap-2 flex-grow-1">
      <i class="bi bi-grip-vertical drag-handle text-muted" role="button" aria-label="Drag to reorder"></i>
      <div class="d-flex flex-column">
        <span class="fw-semibold">${entry.label}</span>
        <span class="small text-muted"><code>${entry.collectionId.replace(/^collection_/, '')}</code></span>
      </div>
    </div>
    <div class="d-flex align-items-center gap-2">
      <div class="btn-group btn-group-sm" role="group" aria-label="Move collection section">
        <button type="button" class="btn btn-outline-secondary" data-collection-section-move="up" aria-label="Move up">
          <i class="bi bi-chevron-up"></i>
        </button>
        <button type="button" class="btn btn-outline-secondary" data-collection-section-move="down" aria-label="Move down">
          <i class="bi bi-chevron-down"></i>
        </button>
      </div>
    </div>
    <div class="text-end">
      <div class="small text-muted">${entry.currentValue ? 'Current' : 'Default'}</div>
      <span class="badge bg-secondary" data-collection-section-current>${entry.currentValue || entry.defaultValue || 'blank'}</span>
      <div class="small text-muted mt-1">New: <span data-collection-section-next>${String(position * 10).padStart(3, '0')}</span></div>
    </div>
  `
  return li
}

function refreshCollectionSectionPreviewNumbers (list) {
  if (!list) return
  Array.from(list.children).forEach((item, index) => {
    const next = item.querySelector('[data-collection-section-next]')
    if (next) next.textContent = String((index + 1) * 10).padStart(3, '0')
  })
}

function setCollectionSectionActionBusy (button, busy) {
  setLibrariesButtonPersistentBusy(button, busy)
}

function markCollectionSectionModalCustomOrder (modalEl) {
  if (!modalEl) return
  modalEl.dataset.collectionSectionResetMode = 'false'
  const status = modalEl.querySelector('[data-collection-section-modal-status]')
  if (status) status.textContent = 'Custom order pending. Save Order will write collection_section overrides.'
}

function ensureCollectionSectionModalRoot (modalEl) {
  if (!modalEl || !document.body) return modalEl
  const modalId = modalEl.id
  if (modalId) {
    const bodyModal = Array.from(document.body.querySelectorAll('[data-collection-section-modal]'))
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

function syncCollectionSectionModalBackdrop (modalEl) {
  if (!modalEl) return
  modalEl.style.zIndex = '2000'
  modalEl.style.pointerEvents = 'auto'
  modalEl.removeAttribute('inert')

  const dialog = modalEl.querySelector('.modal-dialog')
  if (dialog) dialog.style.pointerEvents = 'auto'

  const content = modalEl.querySelector('.modal-content')
  if (content) content.style.pointerEvents = 'auto'

  const backdrops = Array.from(document.querySelectorAll('.modal-backdrop'))
  const latestBackdrop = backdrops.at(-1)
  if (latestBackdrop) latestBackdrop.style.zIndex = '1990'
}

function cleanupCollectionSectionModalBackdrops () {
  if (document.querySelector('.modal.show')) return
  document.querySelectorAll('.modal-backdrop').forEach(backdrop => backdrop.remove())
}

function prepareCollectionSectionModal (modalEl) {
  if (!modalEl) return modalEl
  modalEl = ensureCollectionSectionModalRoot(modalEl)
  if (modalEl.dataset.collectionSectionPrepared === 'true') return modalEl
  modalEl.dataset.collectionSectionPrepared = 'true'
  modalEl.addEventListener('show.bs.modal', () => {
    syncCollectionSectionModalBackdrop(modalEl)
    requestAnimationFrame(() => syncCollectionSectionModalBackdrop(modalEl))
  })
  modalEl.addEventListener('shown.bs.modal', () => {
    syncCollectionSectionModalBackdrop(modalEl)
  })
  modalEl.addEventListener('hidden.bs.modal', () => {
    cleanupCollectionSectionModalBackdrops()
  })
  return modalEl
}

function renderCollectionSectionModalList (modalEl) {
  if (!modalEl) return []
  const libraryId = modalEl.dataset.libraryId
  const list = modalEl.querySelector('[data-collection-section-sortable]')
  const status = modalEl.querySelector('[data-collection-section-modal-status]')
  const saveButton = modalEl.querySelector('[data-collection-section-save]')
  const entries = getCollectionSectionEntries(libraryId)
  list.replaceChildren()
  if (!entries.length) {
    if (status) status.textContent = 'No enabled collections with a collection_section field are available to reorder in this library.'
    if (saveButton) saveButton.disabled = true
    return entries
  }
  entries.forEach((entry, index) => list.appendChild(buildCollectionSectionListItem(entry, index + 1)))
  modalEl.dataset.collectionSectionResetMode = 'false'
  if (status) status.textContent = `${entries.length} enabled collection default${entries.length === 1 ? '' : 's'} ready to reorder.`
  if (saveButton) saveButton.disabled = false
  refreshCollectionSectionPreviewNumbers(list)
  if (modalEl._collectionSectionSortable && typeof modalEl._collectionSectionSortable.destroy === 'function') {
    modalEl._collectionSectionSortable.destroy()
  }
  modalEl._collectionSectionSortable = Sortable.create(list, {
    handle: '.drag-handle',
    animation: 150,
    delayOnTouchOnly: true,
    delay: 180,
    touchStartThreshold: 6,
    onSort: function () {
      markCollectionSectionModalCustomOrder(modalEl)
      refreshCollectionSectionPreviewNumbers(list)
    }
  })
  return entries
}

function saveCollectionSectionModalOrder (modalEl) {
  if (!modalEl) return
  modalEl = prepareCollectionSectionModal(modalEl)
  const saveButton = modalEl.querySelector('[data-collection-section-save]')
  setCollectionSectionActionBusy(saveButton, true)
  const list = modalEl.querySelector('[data-collection-section-sortable]')
  const items = Array.from(list ? list.children : [])
  const resetMode = modalEl.dataset.collectionSectionResetMode === 'true'
  window.setTimeout(() => {
    if (!items.length) {
      setCollectionSectionActionBusy(saveButton, false)
      return
    }
    if (!resetMode) {
      items.forEach((item, index) => {
        const inputId = item.dataset.inputId
        const input = inputId ? document.getElementById(inputId) : null
        if (!input) return
        const nextValue = String((index + 1) * 10).padStart(3, '0')
        input.value = nextValue
        input.dispatchEvent(new Event('input', { bubbles: true }))
        input.dispatchEvent(new Event('change', { bubbles: true }))
        const current = item.querySelector('[data-collection-section-current]')
        if (current) current.textContent = nextValue
      })
    }
    if (typeof showToast === 'function') {
      showToast(resetMode ? 'info' : 'success', resetMode ? 'Collection section overrides cleared. JSON defaults will be used.' : 'Collection section order updated.')
    }
    refreshCollectionSectionPreviewNumbers(list)
    const modal = typeof bootstrap !== 'undefined' && bootstrap.Modal ? bootstrap.Modal.getOrCreateInstance(modalEl) : null
    if (modal) modal.hide()
    setCollectionSectionActionBusy(saveButton, false)
  }, 120)
}

function resetCollectionSectionModalOrder (modalEl) {
  if (!modalEl) return
  modalEl = prepareCollectionSectionModal(modalEl)
  const resetButton = modalEl.querySelector('[data-collection-section-reset]')
  setCollectionSectionActionBusy(resetButton, true)
  const entries = getCollectionSectionEntries(modalEl.dataset.libraryId)
  window.setTimeout(() => {
    entries.forEach(entry => {
      const input = entry.inputId ? document.getElementById(entry.inputId) : null
      if (!input) return
      input.value = ''
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
    })
    renderCollectionSectionModalList(modalEl)
    modalEl.dataset.collectionSectionResetMode = 'true'
    const status = modalEl.querySelector('[data-collection-section-modal-status]')
    if (status) status.textContent = 'Defaults pending. Save Order will clear collection_section overrides and use JSON defaults.'
    if (typeof showToast === 'function') {
      showToast('info', 'Collection section overrides cleared. Save Order to use JSON defaults.')
    }
    setCollectionSectionActionBusy(resetButton, false)
  }, 120)
}

document.addEventListener('click', (event) => {
  const trigger = event.target.closest('[data-collection-section-modal-trigger]')
  if (trigger) {
    const libraryId = trigger.dataset.libraryId
    let modalEl = libraryId ? document.getElementById(`${libraryId}-collection-section-modal`) : null
    if (!modalEl || !bootstrap || !bootstrap.Modal) return
    modalEl = prepareCollectionSectionModal(modalEl)
    renderCollectionSectionModalList(modalEl)
    bootstrap.Modal.getOrCreateInstance(modalEl).show()
    return
  }

  const resetButton = event.target.closest('[data-collection-section-reset]')
  if (resetButton) {
    const modalEl = resetButton.closest('[data-collection-section-modal]')
    resetCollectionSectionModalOrder(modalEl)
    return
  }

  const saveButton = event.target.closest('[data-collection-section-save]')
  if (saveButton) {
    const modalEl = saveButton.closest('[data-collection-section-modal]')
    saveCollectionSectionModalOrder(modalEl)
    return
  }

  const moveButton = event.target.closest('[data-collection-section-move]')
  if (moveButton) {
    const direction = moveButton.dataset.collectionSectionMove
    const item = moveButton.closest('li')
    const list = item?.parentElement
    if (!item || !list) return
    if (direction === 'up' && item.previousElementSibling) {
      list.insertBefore(item, item.previousElementSibling)
    } else if (direction === 'down' && item.nextElementSibling) {
      list.insertBefore(item.nextElementSibling, item)
    }
    markCollectionSectionModalCustomOrder(moveButton.closest('[data-collection-section-modal]'))
    refreshCollectionSectionPreviewNumbers(list)
  }
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
  } catch {
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
      } catch {
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
function toggleOverlayTemplateSection (checkbox) {
  const groupContainer = checkbox.closest('.template-toggle-group') // <== FIXED
  const templateSection = groupContainer?.querySelector('.overlay-template-section')
  const detailsToggle = groupContainer?.querySelector('.overlay-details-toggle')
  const detailActions = groupContainer?.querySelector('.overlay-detail-actions')

  if (templateSection) {
    if (checkbox.checked) {
      setDetailSectionExpanded(templateSection, detailsToggle, false)
      if (detailActions) {
        detailActions.classList.remove('d-none')
      }
    } else {
      setDetailSectionExpanded(templateSection, detailsToggle, false)
      if (detailActions) {
        detailActions.classList.add('d-none')
      }
    }
  }
  groupContainer?.querySelectorAll('[data-overlay-variable-section="true"]').forEach(section => {
    updateOverlayVariableSectionSummary(section)
  })
}

function toggleCollectionTemplateSection (parentToggle) {
  const groupContainer = parentToggle?.closest('.template-toggle-group[data-collection-config="true"]')
  const templateSection = groupContainer?.querySelector('.collection-template-section')
  const detailsToggle = groupContainer?.querySelector('.collection-details-toggle')
  const detailActions = groupContainer?.querySelector('.collection-detail-actions')

  if (!templateSection) return

  setDetailSectionExpanded(templateSection, detailsToggle, false)
  if (detailActions) {
    detailActions.classList.toggle('d-none', !parentToggle?.checked)
  }
  groupContainer?.querySelectorAll('[data-collection-variable-section="true"]').forEach(section => {
    updateCollectionVariableSectionSummary(section)
  })
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
        const removeButton = document.createElement('button')
        removeButton.type = 'button'
        removeButton.className = 'btn btn-sm btn-danger'
        removeButton.setAttribute('aria-label', 'Remove')
        const icon = document.createElement('i')
        icon.className = 'bi bi-x-lg'
        removeButton.appendChild(icon)
        li.append(textSpan, removeButton)
        list.appendChild(li)

        removeButton.addEventListener('click', function () {
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
    } catch {
      console.warn('[WARN] Could not parse hidden input for', prefix, hidden.value)
    }
    renderCustomList(current)

    // Add button logic
    button.addEventListener('click', function () {
      let currentValues = []
      try {
        currentValues = JSON.parse(hidden.value || '[]')
      } catch {
        console.warn('[WARN] Could not parse hidden input for', prefix, hidden.value)
      }

      const value = input.value.trim()
      if (!value || currentValues.includes(value)) return

      currentValues.push(value)
      hidden.value = JSON.stringify(currentValues)
      renderCustomList(currentValues)
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
    } catch {
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

async function runCollectionGroupReset (btn, group, options = {}) {
  if (!btn || !group || btn.dataset.resetBusy === 'true') return

  const idleLabel = btn.dataset.resetIdleLabel || btn.textContent.trim() || 'Reset to Defaults'
  btn.dataset.resetIdleLabel = idleLabel
  btn.dataset.resetBusy = 'true'
  setLibrariesButtonPersistentBusy(btn, true, 'Resetting...')

  const pauseForPaint = async () => {
    await new Promise(resolve => requestAnimationFrame(() => resolve()))
    await new Promise(resolve => window.setTimeout(resolve, 0))
  }
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
  const shouldDispatchCollectionChange = (input) => {
    if (!input) return false
    if (input.type === 'hidden') return true
    if (input.type === 'checkbox' || input.type === 'radio') return true
    return input.tagName === 'SELECT'
  }
  const flushQueuedChanges = async (inputs) => {
    let index = 0
    for (const input of inputs) {
      input.dispatchEvent(new Event('change', { bubbles: true }))
      index += 1
      if (index % 20 === 0) {
        await new Promise(resolve => window.setTimeout(resolve, 0))
      }
    }
  }
  const finalizeToast = (changes) => {
    if (typeof showToast !== 'function') return
    if (!changes.length) {
      showToast('info', 'Already at defaults (no changes).')
      return
    }
    const preview = changes.slice(0, 12)
      .map(change => `${change.label}: ${change.from} -> ${change.to}`)
      .join('\n')
    const extraCount = changes.length - 12
    const suffix = extraCount > 0 ? `\n...and ${extraCount} more field${extraCount === 1 ? '' : 's'}.` : ''
    showToast('info', `Reset to defaults (${changes.length} field${changes.length === 1 ? '' : 's'}):\n${preview}${suffix}`)
  }

  try {
    await pauseForPaint()

    const changes = []
    const touched = new Set()
    const pendingChangeInputs = new Set()
    group.dataset.resetting = 'true'

    const recordReset = (input, defaultValue) => {
      if (!input || touched.has(input)) return false
      touched.add(input)
      const from = getDisplayValue(input)
      const to = getDefaultDisplayValue(input, defaultValue)
      if (from !== to) {
        const scheduleEquivalent = input.closest('[data-schedule-builder]') &&
          normalizeScheduleOverrideValue(from) === normalizeScheduleOverrideValue(to)
        if (!scheduleEquivalent) {
          changes.push({ label: getInputLabel(input), from, to })
        }
        return true
      }
      return false
    }

    resetLibraryAssetDirectoryContainers(group, changes).forEach(input => {
      pendingChangeInputs.add(input)
    })

    const inputs = Array.from(group.querySelectorAll('input[data-default], select[data-default], textarea[data-default]'))
    for (let index = 0; index < inputs.length; index += 1) {
      const input = inputs[index]
      if (input.disabled) continue
      const defaultValue = input.dataset.default
      if (defaultValue === undefined) continue

      let changed = false
      if (input.type === 'checkbox' || input.type === 'radio') {
        const normalizedDefault = (defaultValue || '').toString().toLowerCase()
        const normalizedValue = (input.value || '').toString().toLowerCase()
        const nextChecked = normalizedDefault === 'true' || normalizedDefault === normalizedValue
        changed = recordReset(input, defaultValue)
        if (changed) input.checked = nextChecked
      } else {
        changed = recordReset(input, defaultValue)
        if (changed) {
          input.value = defaultValue
          renderLibraryFileEditorForHiddenInput(input)
        }
      }

      if (changed) {
        input.dispatchEvent(new Event('input', { bubbles: true }))
        if (shouldDispatchCollectionChange(input)) {
          pendingChangeInputs.add(input)
        }
      }

      if (index > 0 && index % 30 === 0) {
        await new Promise(resolve => window.setTimeout(resolve, 0))
      }
    }

    delete group.dataset.resetting

    if (pendingChangeInputs.size) {
      await flushQueuedChanges(pendingChangeInputs)
    }

    const trigger = group.querySelector('input:not([disabled]), select:not([disabled]), textarea:not([disabled])')
    if (trigger && changes.length) {
      trigger.dispatchEvent(new Event('change', { bubbles: true }))
    }

    refreshTemplateOverrideState(group.closest('.template-toggle-group') || group)
    updateAccordionHighlights()
    if (typeof ValidationHandler !== 'undefined' && typeof ValidationHandler.updateValidationState === 'function') {
      ValidationHandler.updateValidationState()
    }
    if (!options.suppressToast) {
      finalizeToast(changes)
    }
  } finally {
    delete group.dataset.resetting
    btn.dataset.resetBusy = 'false'
    setLibrariesButtonPersistentBusy(btn, false)
  }
}

function wireOffsetReset (scope) {
  const root = scope || document
  root.querySelectorAll('.reset-offset-btn').forEach(btn => {
    if (btn.dataset.listenerAdded) return
    btn.addEventListener('click', async () => {
      if (btn.dataset.collectionAllReset === 'true') {
        const sectionBody = btn.closest('.accordion-body')
        if (sectionBody) {
          const card = btn.closest('.library-settings-card')
          try {
            markCollectionDefaultsReset(card)
            clearLazyCollectionShellOverrideSummaries(sectionBody)
            await runCollectionGroupReset(btn, sectionBody, { suppressToast: true })
            setLibrariesButtonPersistentBusy(btn, true, 'Saving...')
            refreshTemplateOverrideState(sectionBody.closest('.accordion-collapse') || sectionBody)
            await autosaveActiveLibrary({ quiet: true })
            if (typeof showToast === 'function') {
              showToast('info', 'Collections reset to defaults.')
            }
          } catch (error) {
            console.error('[collections reset failed]', error)
            if (typeof showToast === 'function') {
              showToast('error', 'Collections reset to defaults failed.')
            }
          } finally {
            const marker = card?.querySelector('input[type="hidden"][name="__reset_collection_defaults"]')
            if (marker) marker.value = 'false'
            setLibrariesButtonPersistentBusy(btn, false)
          }
          return
        }
      }

      if (btn.dataset.collectionParentReset === 'true') {
        let sectionBody = btn.closest('.accordion-body')
        if (!sectionBody) {
          const groupShell = btn.closest('[data-collection-group-shell="true"]')
          const lazyCollapse = groupShell?.querySelector('[data-collection-group-lazy-collapse="true"]')
          if (lazyCollapse) {
            try {
              setLibrariesButtonPersistentBusy(btn, true)
              const card = btn.closest('.library-settings-card')
              const replacement = await loadLazyCollectionGroup(lazyCollapse, card)
              const resetBtn = replacement?.querySelector('[data-collection-parent-reset="true"]')
              sectionBody = replacement?.querySelector('.accordion-body')
              if (sectionBody && resetBtn) {
                await runCollectionGroupReset(resetBtn, sectionBody)
                refreshTemplateOverrideState(sectionBody.closest('.accordion-collapse') || sectionBody)
              }
            } catch (error) {
              console.error('[collection parent reset failed]', error)
              if (typeof showToast === 'function') {
                showToast('error', 'Collection group reset to defaults failed.')
              }
            } finally {
              setLibrariesButtonPersistentBusy(btn, false)
            }
            return
          }
          sectionBody = btn.closest('.accordion')?.querySelector(':scope > .accordion-item > .accordion-collapse > .accordion-body')
        }
        if (sectionBody) {
          runCollectionGroupReset(btn, sectionBody).then(() => {
            refreshTemplateOverrideState(sectionBody.closest('.accordion-collapse') || sectionBody)
          }).catch(error => {
            console.error('[collection parent reset failed]', error)
            if (typeof showToast === 'function') {
              showToast('error', 'Collection group reset to defaults failed.')
            }
          })
          return
        }
      }

      if (btn.dataset.collectionVariableSectionReset === 'true') {
        const section = btn.closest('[data-collection-variable-section="true"]')
        const sectionBody = section?.querySelector('.collection-variable-section-body') || section
        if (sectionBody) {
          runCollectionGroupReset(btn, sectionBody).then(() => {
            refreshTemplateOverrideState(section.closest('.template-toggle-group') || section)
          }).catch(error => {
            console.error('[collection section reset failed]', error)
            if (typeof showToast === 'function') {
              showToast('error', 'Section reset to defaults failed.')
            }
          })
          return
        }
      }

      if (btn.dataset.overlayVariableSectionReset === 'true') {
        const section = btn.closest('[data-overlay-variable-section="true"]')
        const sectionBody = section?.querySelector('.overlay-variable-section-body') || section
        if (sectionBody) {
          runCollectionGroupReset(btn, sectionBody).then(() => {
            refreshTemplateOverrideState(section.closest('.template-toggle-group') || section)
          }).catch(error => {
            console.error('[overlay section reset failed]', error)
            if (typeof showToast === 'function') {
              showToast('error', 'Overlay section reset to defaults failed.')
            }
          })
          return
        }
      }

      if (btn.dataset.libraryOverrideReset === 'true') {
        const section = btn.closest('[data-library-override-scope="true"]')
        const sectionBody = getDirectAccordionBody(section)
        if (sectionBody) {
          runCollectionGroupReset(btn, sectionBody).then(() => {
            refreshTemplateOverrideState(section.closest('.library-settings-card') || section)
          }).catch(error => {
            console.error('[library override reset failed]', error)
            if (typeof showToast === 'function') {
              showToast('error', 'Section reset to defaults failed.')
            }
          })
          return
        }
      }

      const group = btn.closest('.template-toggle-group')
      if (group?.dataset?.collectionId) {
        runCollectionGroupReset(btn, group).catch(error => {
          console.error('[collection reset failed]', error)
          if (typeof showToast === 'function') {
            showToast('error', 'Reset to defaults failed.')
          }
        })
        return
      }
      setLibrariesButtonPersistentBusy(btn, true, 'Resetting...')
      await new Promise(resolve => requestAnimationFrame(() => resolve()))
      await new Promise(resolve => window.setTimeout(resolve, 0))
      const finishOverlayReset = () => {
        if (group) {
          refreshTemplateOverrideState(group)
          updateAccordionHighlights()
          if (typeof ValidationHandler !== 'undefined' && typeof ValidationHandler.updateValidationState === 'function') {
            ValidationHandler.updateValidationState()
          }
        }
        setLibrariesButtonPersistentBusy(btn, false)
      }
      try {
        if (group) {
          group.dataset.resetting = 'true'
        }
        const changes = []
        const touched = new Set()
        const isRatingsOverlay = group?.dataset?.overlayId === 'overlay_ratings'
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
            renderLibraryFileEditorForHiddenInput(input)
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
            if (changed) {
              input.value = defaultValue
              renderLibraryFileEditorForHiddenInput(input)
            }
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
            .map(change => `${change.label}: ${change.from} -> ${change.to}`)
            .join('\n')
          showToast('info', `Reset to defaults:\n${details}`)
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
            finishOverlayReset()
          }, 0)
        } else {
          finalizeToast()
          finishOverlayReset()
        }
      } catch (error) {
        console.error('[overlay reset failed]', error)
        if (group) delete group.dataset.resetting
        if (typeof showToast === 'function') {
          showToast('error', 'Reset to defaults failed.')
        }
        finishOverlayReset()
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

      if (!parentChecked) {
        childrenToggles.forEach(child => syncChildHidden(child))
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
      const isCollectionBehaviorToggle = (child) => {
        const id = child.id || ''
        return id.endsWith('_use_separator') || id.endsWith('_use_other')
      }
      const isRequiredChild = (child) => {
        const id = child.id || ''
        if (!id.includes('-template_collection_')) return false
        if (isAddMissingToggle(child) || isVisibleToggle(child) || isCollectionBehaviorToggle(child)) return false
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

      updateAccordionHighlights()
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

    const resetRatingsPlacement = (refreshAlignmentDefaults = false) => {
      if (group.dataset.resetting === 'true') return
      group.dataset.ratingsBulkUpdate = 'true'
      try {
        if (refreshAlignmentDefaults) {
          applyAlignmentDefaults(true)
        }
        applyPlacementDefaults(true)
        applyComputedOffsets(true)
        Object.values(sharedInputs).forEach(input => {
          if (!input) return
          input.dataset.prevValue = String(input.value ?? '')
        })
      } finally {
        delete group.dataset.ratingsBulkUpdate
      }
      updateAdjustedIndicators()
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
        resetRatingsPlacement(true)
      }
      alignmentInput.addEventListener('input', handleAlignmentChange)
      alignmentInput.addEventListener('change', handleAlignmentChange)
      alignmentInput.dataset.ratingsAlignmentBound = 'true'
    }

    if (positionInput && positionInput.dataset.ratingsPositionBound !== 'true') {
      const refreshFromPosition = () => {
        if (group.dataset.resetting === 'true') return
        resetRatingsPlacement(false)
      }
      positionInput.addEventListener('change', refreshFromPosition)
      positionInput.dataset.ratingsPositionBound = 'true'
    }

    if (verticalPositionInput && verticalPositionInput.dataset.ratingsPositionBound !== 'true') {
      const refreshFromVertical = () => {
        if (group.dataset.resetting === 'true') return
        resetRatingsPlacement(false)
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
    refreshTemplateOverrideState(group)
    group.dataset.ratingsOffsetSyncBound = 'true'
  })
}

window.wireRatingsOffsetSync = wireRatingsOffsetSync

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

function setDetailSectionExpanded (section, toggle, expanded) {
  if (!section) return
  section.style.display = expanded ? 'block' : 'none'
  section.dataset.detailVisible = expanded ? 'true' : 'false'
  if (!toggle) return
  const showLabel = String(toggle.dataset.showLabel || 'Show Details')
  const hideLabel = String(toggle.dataset.hideLabel || 'Hide Details')
  toggle.textContent = expanded ? hideLabel : showLabel
  toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false')
}

function wireDetailToggles (selector, scope) {
  const root = scope || document
  root.querySelectorAll(selector).forEach(btn => {
    if (btn.dataset.listenerAdded === 'true') return
    const targetId = btn.dataset.sectionId
    const section = targetId ? document.getElementById(targetId) : null
    if (!section) return

    btn.addEventListener('click', () => {
      const isHidden = section.style.display === 'none'
      setDetailSectionExpanded(section, btn, isHidden)
      updateAccordionHighlights()
    })

    const defaultOpen = section.dataset.detailVisible === 'true' || section.dataset.defaultOpen === 'true'
    setDetailSectionExpanded(section, btn, defaultOpen)
    btn.dataset.listenerAdded = 'true'
  })
}

function wireOverlayDetailToggles (scope) {
  wireDetailToggles('.overlay-details-toggle', scope)
}

function wireOverlayVariableSectionToggles (scope) {
  wireDetailToggles('.overlay-variable-section-toggle', scope)
}

function wireCollectionDetailToggles (scope) {
  wireDetailToggles('.collection-details-toggle', scope)
}

function wireCollectionVariableSectionToggles (scope) {
  wireDetailToggles('.collection-variable-section-toggle', scope)
}

function parseCollectionSectionStoredStringList (rawValue) {
  const raw = String(rawValue || '').trim()
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      return parsed.map(item => String(item).trim()).filter(Boolean)
    }
  } catch {
    // fall back to single-value handling
  }
  return [raw]
}

function parseCollectionSectionStoredMapping (rawValue) {
  const raw = String(rawValue || '').trim()
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed
    }
  } catch {
    // fall through to empty mapping
  }
  return {}
}

function normalizeScheduleOverrideValue (rawValue) {
  const raw = String(rawValue || '').trim().toLowerCase()
  if (!raw) return ''
  const normalizeMonthDay = value => {
    const match = String(value || '').trim().match(/^0*(\d{1,2})\/0*(\d{1,2})$/)
    if (!match) return String(value || '').trim().toLowerCase()
    return `${Number(match[1])}/${Number(match[2])}`
  }
  const normalizeDate = value => {
    const match = String(value || '').trim().match(/^0*(\d{1,2})\/0*(\d{1,2})\/(\d{4})$/)
    if (!match) return String(value || '').trim().toLowerCase()
    return `${Number(match[1])}/${Number(match[2])}/${match[3]}`
  }

  const wrapperMatch = raw.match(/^([a-z_]+)\((.*)\)$/)
  if (!wrapperMatch) return raw.replace(/\s+/g, '')
  const mode = wrapperMatch[1]
  const inner = wrapperMatch[2].trim()
  if (mode === 'range' && !inner.includes('|')) {
    const parts = inner.split('-').map(value => value.trim())
    return `range(${normalizeMonthDay(parts[0])}-${normalizeMonthDay(parts[1])})`
  }
  if (mode === 'yearly') return `yearly(${normalizeMonthDay(inner)})`
  if (mode === 'date') return `date(${normalizeDate(inner)})`
  if (mode === 'weekly') {
    return `weekly(${inner.split('|').map(value => value.trim().toLowerCase()).filter(Boolean).join('|')})`
  }
  return `${mode}(${inner.replace(/\s+/g, '')})`
}

function isInternalTemplateMetadataField (field) {
  if (!field) return false
  const name = String(field.name || '').trim()
  return field.dataset?.skipOverrideCount === 'true' ||
    field.dataset?.skipYaml === 'true' ||
    field.dataset?.templateMetadata === 'lookup-labels' ||
    name.includes('-library_service_') ||
    name.endsWith('_hidden') ||
    name.endsWith('__lookup_labels')
}

function isCollectionSectionFieldConfigured (fields) {
  const enabledFields = Array.from(fields || []).filter(field => field && !field.disabled && !isInternalTemplateMetadataField(field))
  if (!enabledFields.length) return false

  const visibleFields = enabledFields.filter(field => field.type !== 'hidden')
  const checkboxField = visibleFields.find(field => field.type === 'checkbox')
  if (checkboxField) {
    const defaultRaw = String(checkboxField.dataset.default || '').trim().toLowerCase()
    const currentChecked = checkboxField.checked
    if (defaultRaw) {
      const normalizedValue = String(checkboxField.value || 'true').trim().toLowerCase()
      const defaultChecked = defaultRaw === 'true' || defaultRaw === normalizedValue
      return currentChecked !== defaultChecked
    }
    return currentChecked
  }

  const radioFields = visibleFields.filter(field => field.type === 'radio')
  if (radioFields.length) {
    return radioFields.some(field => field.checked)
  }

  const primaryField = visibleFields[0] || enabledFields[0]
  if (!primaryField) return false

  if (String(primaryField.name || '').endsWith('-attribute_asset_directory')) {
    return visibleFields.some(field => String(field.value ?? '').trim())
  }

  if (primaryField.closest('[data-template-string-list]')) {
    const values = parseCollectionSectionStoredStringList(primaryField.value)
    const defaults = parseCollectionSectionStoredStringList(primaryField.dataset.default || '[]')
    return JSON.stringify(values) !== JSON.stringify(defaults)
  }

  if (primaryField.closest('[data-template-mapping-list]')) {
    const values = parseCollectionSectionStoredMapping(primaryField.value)
    const defaults = parseCollectionSectionStoredMapping(primaryField.dataset.default || '{}')
    return JSON.stringify(values) !== JSON.stringify(defaults)
  }

  const value = String(primaryField.value ?? '').trim()
  const defaultValue = String(primaryField.dataset.default || '').trim()
  if (primaryField.closest('[data-schedule-builder]')) {
    return normalizeScheduleOverrideValue(value) !== normalizeScheduleOverrideValue(defaultValue)
  }
  if (!value) return false
  return defaultValue ? value !== defaultValue : true
}

function formatTemplateOverrideCount (count) {
  return count === 1 ? '1 override' : `${count} overrides`
}

function isTrueDatasetValue (value) {
  return String(value || '').trim().toLowerCase() === 'true'
}

function checkboxCheckedDiffersFromDefault (field) {
  if (!field || (field.type !== 'checkbox' && field.type !== 'radio')) return false
  const defaultRaw = String(field.dataset?.default || '').trim().toLowerCase()
  if (!defaultRaw) return field.checked
  const normalizedValue = String(field.value || 'true').trim().toLowerCase()
  const defaultChecked = defaultRaw === 'true' || defaultRaw === normalizedValue
  return field.checked !== defaultChecked
}

function isTemplateGroupActiveForSignal (group) {
  if (!group) return false
  const toggle = group.querySelector('input[type="checkbox"][data-template-group], input[type="radio"][data-template-group], .overlay-toggle')
  if (!toggle) return false
  return checkboxCheckedDiffersFromDefault(toggle)
}

function getLazyElementSignalCount (element) {
  return Number(element?.dataset?.lazyOverrideCount || '0') || 0
}

function getLazyElementHasSignal (element) {
  return getLazyElementSignalCount(element) > 0 || isTrueDatasetValue(element?.dataset?.lazyActive)
}

function setOverrideSummaryBadge (badge, count) {
  if (!badge) return
  badge.textContent = count > 0 ? formatTemplateOverrideCount(count) : ''
  badge.classList.toggle('d-none', count <= 0)
}

function findTemplateVariableFieldRow (field) {
  if (!field) return null
  return field.closest(
    '[data-playlist-files-editor], ' +
    '[data-collection-files-editor], ' +
    '[data-metadata-files-editor], ' +
    '[data-overlay-files-editor], ' +
    '[data-playlist-key-toggle-group], ' +
    '[data-playlist-user-picker], ' +
    '[data-template-string-list], ' +
    '[data-template-mapping-list], ' +
    '[data-overlay-language-weight-builder], ' +
    '[data-collection-field-wrapper], ' +
    '.rgba-group, ' +
    '.font-row, ' +
    '.input-group'
  )
}

function updateTemplateVariableFieldOverrideStates (body, fieldsByName) {
  if (!body) return
  clearTemplateVariableFieldOverrideStates(body)

  fieldsByName.forEach(fields => {
    if (!isCollectionSectionFieldConfigured(fields)) return
    fields.forEach(field => {
      if (isInternalTemplateMetadataField(field)) return
      const row = findTemplateVariableFieldRow(field)
      if (!row) return
      row.classList.add('template-variable-field-has-override')
      row.dataset.templateVariableFieldOverride = 'true'
    })
  })
}

function clearTemplateVariableFieldOverrideStates (scope) {
  if (!scope) return
  const rows = []
  if (scope.classList?.contains('template-variable-field-has-override')) {
    rows.push(scope)
  }
  scope.querySelectorAll?.('.template-variable-field-has-override').forEach(row => {
    rows.push(row)
  })
  rows.forEach(row => {
    row.classList.remove('template-variable-field-has-override')
    row.removeAttribute('data-template-variable-field-override')
  })
}

function getOrCreateTemplateOverrideBadge (group) {
  if (!group) return null
  let badge = group.querySelector('[data-template-group-override-summary]')
  if (badge) return badge

  badge = document.createElement('span')
  badge.className = 'small template-override-summary ms-2 d-none'
  badge.dataset.templateGroupOverrideSummary = 'true'

  const target = group.querySelector('.overlay-toggle-row') || group.querySelector('.form-check > .d-flex') || group.querySelector('.form-check')
  target?.appendChild(badge)
  return badge
}

function getOrCreateAccordionOverrideBadge (header) {
  if (!header) return null
  let badge = header.querySelector('[data-accordion-override-summary]')
  if (badge) return badge

  const button = header.querySelector('.accordion-button')
  if (!button) return null

  badge = document.createElement('span')
  badge.className = 'small accordion-override-summary ms-3 d-none'
  badge.dataset.accordionOverrideSummary = 'true'
  button.appendChild(badge)
  return badge
}

function updateAncestorOverrideSummaries (element) {
  let collapse = element?.closest('.accordion-collapse')
  const seen = new Set()

  while (collapse && !seen.has(collapse)) {
    seen.add(collapse)
    const accordionItem = collapse.closest('.accordion-item')
    const header = accordionItem?.querySelector('.accordion-header')
    const count = getAccordionCollapseOverrideCount(collapse)
    const hasSignal = getAccordionCollapseHasActiveSignal(collapse)

    accordionItem?.classList.toggle('template-variable-section-has-overrides', hasSignal)
    header?.classList.toggle('template-variable-section-has-overrides', hasSignal)
    setOverrideSummaryBadge(getOrCreateAccordionOverrideBadge(header), count)

    collapse = accordionItem?.parentElement?.closest('.accordion-collapse')
  }
  updateLibraryAggregateOverrideSummaries(element?.closest('.library-settings-card'))
}

function updateLazySectionOverrideSummaries (scope) {
  const root = scope || document
  root.querySelectorAll?.('[data-library-lazy-section][data-lazy-override-count]').forEach(placeholder => {
    const count = getLazyElementSignalCount(placeholder)
    const hasSignal = getLazyElementHasSignal(placeholder)
    const collapse = placeholder.closest('.accordion-collapse')
    const item = collapse?.closest('.accordion-item')
    const header = item?.querySelector(':scope > .accordion-header') || item?.querySelector('.accordion-header')

    item?.classList.toggle('template-variable-section-has-overrides', hasSignal)
    header?.classList.toggle('template-variable-section-has-overrides', hasSignal)
    setOverrideSummaryBadge(getOrCreateAccordionOverrideBadge(header), count)
  })
  root.querySelectorAll?.('[data-collection-group-lazy-collapse][data-lazy-override-count]').forEach(collapse => {
    const count = getLazyElementSignalCount(collapse)
    const hasSignal = getLazyElementHasSignal(collapse)
    const item = collapse.closest('.accordion-item')
    const header = item?.querySelector(':scope > .accordion-header') || item?.querySelector('.accordion-header')

    item?.classList.toggle('template-variable-section-has-overrides', hasSignal)
    header?.classList.toggle('template-variable-section-has-overrides', hasSignal)
    setOverrideSummaryBadge(getOrCreateAccordionOverrideBadge(header), count)
  })
}

function clearLazyCollectionShellOverrideSummaries (scope) {
  const root = scope || document
  root.querySelectorAll?.('[data-collection-group-lazy-collapse][data-lazy-override-count]').forEach(collapse => {
    collapse.dataset.lazyOverrideCount = '0'
    collapse.dataset.lazyActive = 'false'
    const item = collapse.closest('.accordion-item')
    const header = item?.querySelector(':scope > .accordion-header') || item?.querySelector('.accordion-header')

    item?.classList.remove('template-variable-section-has-overrides')
    header?.classList.remove('template-variable-section-has-overrides')
    setOverrideSummaryBadge(getOrCreateAccordionOverrideBadge(header), 0)
  })
}

function isOverlayTemplateGroupActiveForCounts (group) {
  const toggle = group?.querySelector('.overlay-toggle')
  return !toggle || toggle.checked
}

function getDirectChildAccordionItems (collapse) {
  return Array.from(collapse?.querySelectorAll?.(':scope > .accordion-body > .accordion > .accordion-item') || [])
}

function getAccordionCollapseOverrideCount (collapse) {
  const explicitCount = Number(collapse?.dataset?.overrideCount || '')
  if (Number.isFinite(explicitCount) && explicitCount > 0) return explicitCount

  const lazyCount = Number(collapse?.querySelector?.('[data-library-lazy-section][data-lazy-override-count]')?.dataset?.lazyOverrideCount || '')
  if (Number.isFinite(lazyCount) && lazyCount > 0) return lazyCount

  const lazyGroupCount = Number(collapse?.dataset?.lazyOverrideCount || '')
  if (collapse?.dataset?.collectionGroupLazyCollapse === 'true' && Number.isFinite(lazyGroupCount) && lazyGroupCount > 0) return lazyGroupCount

  const childItems = getDirectChildAccordionItems(collapse)
  if (childItems.length) {
    return childItems.reduce((total, item) => total + getAccordionItemOverrideCount(item), 0)
  }

  return Array.from(collapse?.querySelectorAll?.('.template-toggle-group') || []).reduce((total, group) => {
    if (!isOverlayTemplateGroupActiveForCounts(group)) return total
    return total + (Number(group.dataset.overrideCount || '0') || 0)
  }, 0)
}

function getAccordionCollapseHasActiveSignal (collapse) {
  if (!collapse) return false
  if (getAccordionCollapseOverrideCount(collapse) > 0) return true
  const lazyPlaceholder = collapse.querySelector?.('[data-library-lazy-section][data-lazy-active="true"]')
  if (lazyPlaceholder) return true
  if (collapse.dataset?.collectionGroupLazyCollapse === 'true' && isTrueDatasetValue(collapse.dataset.lazyActive)) return true
  return Array.from(collapse.querySelectorAll?.('.template-toggle-group') || []).some(group => {
    return isOverlayTemplateGroupActiveForCounts(group) && isTemplateGroupActiveForSignal(group)
  })
}

function getAccordionItemOverrideCount (item) {
  if (!item) return 0
  const collapse = Array.from(item.children).find(child => child.classList?.contains('accordion-collapse'))
  return getAccordionCollapseOverrideCount(collapse)
}

function getLibrarySectionOverrideTotal (card, advanced) {
  if (!card) return 0
  const accordion = card.querySelector('.accordion')
  const items = Array.from(accordion?.children || []).filter(item => item.classList?.contains('accordion-item'))
  return items.reduce((total, item) => {
    const isAdvanced = item.classList.contains('library-advanced-section')
    if (advanced !== isAdvanced) return total
    return total + getAccordionItemOverrideCount(item)
  }, 0)
}

function getLibraryCardOverrideTotal (card) {
  if (!card) return 0
  return getLibrarySectionOverrideTotal(card, false) + getLibrarySectionOverrideTotal(card, true)
}

function syncDirectLibraryAccordionOverrideSignals (card) {
  if (!card) return
  const accordion = card.querySelector('.accordion')
  const items = Array.from(accordion?.children || []).filter(item => item.classList?.contains('accordion-item'))
  items.forEach(item => {
    const collapse = Array.from(item.children).find(child => child.classList?.contains('accordion-collapse'))
    const header = Array.from(item.children).find(child => child.classList?.contains('accordion-header')) || item.querySelector(':scope > .accordion-header')
    const count = getAccordionCollapseOverrideCount(collapse)
    const hasSignal = getAccordionCollapseHasActiveSignal(collapse)
    item.classList.toggle('template-variable-section-has-overrides', hasSignal)
    header?.classList.toggle('template-variable-section-has-overrides', hasSignal)
    setOverrideSummaryBadge(getOrCreateAccordionOverrideBadge(header), count)
  })
}

function getLibraryCardHasConfigurationSignal (card) {
  if (!card) return false
  if (getLibraryCardOverrideTotal(card) > 0) return true
  if (card.querySelector('.template-variable-section-has-overrides, .template-variable-field-has-override')) return true
  if (card.querySelector('[data-library-lazy-section][data-lazy-active="true"], [data-collection-group-lazy-collapse][data-lazy-active="true"]')) return true
  return Array.from(card.querySelectorAll('[data-library-lazy-section][data-lazy-override-count], [data-collection-group-lazy-collapse][data-lazy-override-count]')).some(element => {
    const count = Number(element.dataset.lazyOverrideCount || '0') || 0
    return count > 0
  })
}

function updateLibraryAggregateOverrideSummaries (card) {
  if (!card) return
  syncDirectLibraryAccordionOverrideSignals(card)
  const coreCount = getLibrarySectionOverrideTotal(card, false)
  const advancedCount = getLibrarySectionOverrideTotal(card, true)
  setOverrideSummaryBadge(card.querySelector('[data-library-core-summary]'), coreCount)
  setOverrideSummaryBadge(card.querySelector('[data-library-advanced-summary]'), advancedCount)
  setOverrideSummaryBadge(card.querySelector('[data-library-total-summary]'), getLibraryCardOverrideTotal(card))
}

function updateTemplateGroupOverrideSummary (section) {
  const group = section?.closest('.template-toggle-group')
  if (!group) return

  const sections = group.querySelectorAll('[data-collection-variable-section="true"], [data-overlay-variable-section="true"]')
  const count = isOverlayTemplateGroupActiveForCounts(group)
    ? Array.from(sections).reduce((total, item) => {
        return total + (Number(item.dataset.overrideCount || '0') || 0)
      }, 0)
    : 0

  group.dataset.overrideCount = String(count)
  group.classList.toggle('template-variable-section-has-overrides', count > 0 || isTemplateGroupActiveForSignal(group))
  setOverrideSummaryBadge(getOrCreateTemplateOverrideBadge(group), count)
  updateAncestorOverrideSummaries(group)
}

function refreshTemplateOverrideState (scope) {
  const root = scope || document
  clearTemplateVariableFieldOverrideStates(root)
  updateLazySectionOverrideSummaries(root)
  root.querySelectorAll('[data-collection-variable-section="true"]').forEach(section => {
    updateCollectionVariableSectionSummary(section)
  })
  root.querySelectorAll('[data-overlay-variable-section="true"]').forEach(section => {
    updateOverlayVariableSectionSummary(section)
  })
  getLibraryOverrideScopes(root).forEach(section => {
    updateLibraryOverrideScopeSummary(section)
  })
  root.querySelectorAll?.('.library-settings-card').forEach(card => {
    updateLibraryAggregateOverrideSummaries(card)
  })
  if (root.matches?.('.library-settings-card')) {
    updateLibraryAggregateOverrideSummaries(root)
  }
}

window.QSLibraryValidation = {
  hasConfiguredSignal: getLibraryCardHasConfigurationSignal,
  refreshSummaries: refreshTemplateOverrideState
}

function getLibraryOverrideScopes (root) {
  if (!root) return []
  const scopes = []
  if (root.matches?.('[data-library-override-scope="true"]')) {
    scopes.push(root)
  }
  root.querySelectorAll?.('[data-library-override-scope="true"]').forEach(section => {
    scopes.push(section)
  })
  return scopes
}

function getDirectAccordionHeader (scope) {
  const item = scope?.closest('.accordion-item')
  if (!item) return null
  return Array.from(item.children).find(child => child.classList?.contains('accordion-header')) || item.querySelector(':scope > .accordion-header')
}

function getDirectAccordionBody (scope) {
  if (!scope) return null
  return Array.from(scope.children).find(child => child.classList?.contains('accordion-body')) || scope.querySelector(':scope > .accordion-body') || scope
}

function getLibraryOverrideScopeFields (scope) {
  const body = getDirectAccordionBody(scope)
  const fieldsByName = new Map()
  if (!body) return fieldsByName
  body.querySelectorAll('[name]').forEach(field => {
    if (!field || field.disabled) return
    if (isInternalTemplateMetadataField(field)) return
    const name = String(field.name || '').trim()
    if (!name) return
    if (!fieldsByName.has(name)) fieldsByName.set(name, [])
    fieldsByName.get(name).push(field)
  })
  return fieldsByName
}

function ensureLibraryOverrideResetButton (scope) {
  const body = getDirectAccordionBody(scope)
  if (!body || body.dataset.libraryOverrideResetPrepared === 'true') return
  const label = scope.dataset.libraryOverrideLabel || getDirectAccordionHeader(scope)?.textContent?.trim() || 'Section'
  const actions = document.createElement('div')
  actions.className = 'd-flex justify-content-end mb-2'
  actions.dataset.libraryOverrideResetActions = 'true'
  actions.innerHTML = `
    <button type="button" class="btn btn-outline-secondary btn-sm reset-offset-btn" data-library-override-reset="true">
      Reset ${label}
    </button>
  `
  body.prepend(actions)
  body.dataset.libraryOverrideResetPrepared = 'true'
}

function updateLibraryOverrideScopeSummary (scope) {
  if (!scope) return
  const fieldsByName = getLibraryOverrideScopeFields(scope)
  let configuredCount = 0
  fieldsByName.forEach(fields => {
    if (isCollectionSectionFieldConfigured(fields)) configuredCount += 1
  })

  const body = getDirectAccordionBody(scope)
  updateTemplateVariableFieldOverrideStates(body, fieldsByName)

  scope.dataset.overrideCount = String(configuredCount)
  const item = scope.closest('.accordion-item')
  const header = getDirectAccordionHeader(scope)
  item?.classList.toggle('template-variable-section-has-overrides', configuredCount > 0)
  header?.classList.toggle('template-variable-section-has-overrides', configuredCount > 0)
  setOverrideSummaryBadge(getOrCreateAccordionOverrideBadge(header), configuredCount)
  updateLibraryAggregateOverrideSummaries(scope.closest('.library-settings-card'))
}

function wireLibraryOverrideScopes (scope) {
  const root = scope || document
  getLibraryOverrideScopes(root).forEach(section => {
    if (section.dataset.libraryOverrideScopeBound === 'true') return
    ensureLibraryOverrideResetButton(section)
    const refresh = () => updateLibraryOverrideScopeSummary(section)
    section.addEventListener('input', refresh)
    section.addEventListener('change', refresh)
    refresh()
    section.dataset.libraryOverrideScopeBound = 'true'
  })
}

function updateCollectionVariableSectionSummary (section) {
  if (!section) return
  const summary = section.querySelector('[data-collection-section-summary]')
  const body = section.querySelector('.collection-variable-section-body')
  if (!summary || !body) return

  const fieldsByName = new Map()
  body.querySelectorAll('[name]').forEach(field => {
    if (!field || field.disabled) return
    if (isInternalTemplateMetadataField(field)) return
    const name = String(field.name || '').trim()
    if (!name) return
    if (!fieldsByName.has(name)) fieldsByName.set(name, [])
    fieldsByName.get(name).push(field)
  })

  let configuredCount = 0
  fieldsByName.forEach(fields => {
    if (isCollectionSectionFieldConfigured(fields)) configuredCount += 1
  })

  updateTemplateVariableFieldOverrideStates(body, fieldsByName)

  summary.textContent = configuredCount === 0
    ? 'Defaults'
    : configuredCount === 1
      ? '1 override'
      : `${configuredCount} overrides`
  section.classList.toggle('template-variable-section-has-overrides', configuredCount > 0)
  section.dataset.overrideCount = String(configuredCount)
  updateTemplateGroupOverrideSummary(section)
}

function updateOverlayVariableSectionSummary (section) {
  if (!section) return
  const summary = section.querySelector('[data-overlay-section-summary]')
  const body = section.querySelector('.overlay-variable-section-body')
  if (!summary || !body) return
  const group = section.closest('.template-toggle-group')
  const activeGroup = isOverlayTemplateGroupActiveForCounts(group)

  const fieldsByName = new Map()
  body.querySelectorAll('[name]').forEach(field => {
    if (!field || field.disabled) return
    if (isInternalTemplateMetadataField(field)) return
    const name = String(field.name || '').trim()
    if (!name) return
    if (!fieldsByName.has(name)) fieldsByName.set(name, [])
    fieldsByName.get(name).push(field)
  })

  let configuredCount = 0
  if (activeGroup) {
    fieldsByName.forEach(fields => {
      if (isCollectionSectionFieldConfigured(fields)) configuredCount += 1
    })
  }

  if (activeGroup) {
    updateTemplateVariableFieldOverrideStates(body, fieldsByName)
  }

  summary.textContent = configuredCount === 0
    ? 'Defaults'
    : configuredCount === 1
      ? '1 override'
      : `${configuredCount} overrides`
  section.classList.toggle('template-variable-section-has-overrides', configuredCount > 0)
  section.dataset.overrideCount = String(configuredCount)
  updateTemplateGroupOverrideSummary(section)
}

function wireOverlayVariableSections (scope) {
  const root = scope || document
  root.querySelectorAll('[data-overlay-variable-section="true"]').forEach(section => {
    if (section.dataset.summaryBound === 'true') return

    const refresh = () => updateOverlayVariableSectionSummary(section)
    section.addEventListener('input', refresh)
    section.addEventListener('change', refresh)
    refresh()

    section.dataset.summaryBound = 'true'
  })
}

function wireCollectionVariableSections (scope) {
  const root = scope || document
  root.querySelectorAll('[data-collection-variable-section="true"]').forEach(section => {
    if (section.dataset.summaryBound === 'true') return

    const refresh = () => updateCollectionVariableSectionSummary(section)
    section.addEventListener('input', refresh)
    section.addEventListener('change', refresh)
    refresh()

    section.dataset.summaryBound = 'true'
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

function wireCollectionTemplateSections (scope) {
  const root = scope || document
  root.querySelectorAll('.template-toggle-group[data-collection-config="true"]').forEach(group => {
    if (group.dataset.collectionTemplateBound === 'true') return
    const parentToggle = group.querySelector('[data-template-group]')
    if (!parentToggle) return
    parentToggle.addEventListener('change', function () {
      toggleCollectionTemplateSection(this)
    })
    toggleCollectionTemplateSection(parentToggle)
    group.dataset.collectionTemplateBound = 'true'
  })
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
