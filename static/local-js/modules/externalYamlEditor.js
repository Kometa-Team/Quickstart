// External YAML editor subsystem.
//
// Extracted from static/local-js/025-libraries.js as part of the #1334
// Step 9 direction (component islands): complex behaviours that used to
// live inside the 9k-line 025-libraries.js get pulled out into their
// own modules under static/local-js/modules/ so the monolith stops
// growing.
//
// This module owns the "edit metadata/collection/overlay/playlist YAML
// files inline in a modal" workflow. It is completely self-contained --
// no other module or template references the externalYaml* symbols
// directly. 025-libraries.js keeps ownership of the four row builders
// (buildMetadataFileRow, etc.) and their per-kind status/sync helpers;
// those are wired in through dependency injection at init time.
//
// Usage from a page module:
//
//   import { initExternalYamlEditorSubsystem } from './modules/externalYamlEditor.js'
//   const externalYaml = initExternalYamlEditorSubsystem({
//     kinds: { metadata_files: {..., setStatus, sync}, ... },
//     getActiveConfigName,
//     setLibrariesButtonPersistentBusy,
//     prepareLibrariesModal
//   })
//   externalYaml.updateExternalYamlEditButton(row, 'metadata_files')
//
// The subsystem is idempotent -- calling init more than once returns the
// existing instance and does not re-attach document-level listeners.

let externalYamlEditorKinds = null
let externalYamlModalState = null
let getActiveConfigName = () => ''
let setLibrariesButtonPersistentBusy = () => {}
let prepareLibrariesModal = (el) => el
let listenersAttached = false
let subsystemInstance = null

export function initExternalYamlEditorSubsystem (deps) {
  if (subsystemInstance) return subsystemInstance
  externalYamlEditorKinds = deps.kinds
  getActiveConfigName = deps.getActiveConfigName
  setLibrariesButtonPersistentBusy = deps.setLibrariesButtonPersistentBusy
  prepareLibrariesModal = deps.prepareLibrariesModal
  attachDocumentListeners()
  subsystemInstance = { updateExternalYamlEditButton }
  return subsystemInstance
}


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
function attachDocumentListeners () {
  if (listenersAttached) return
  listenersAttached = true

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

}
