// Shared library-files-editor subsystem.
//
// Extracted from static/local-js/025-libraries.js as part of the #1334
// Step 9 direction. Previously the "editor for the four kinds of
// library file lists" (metadata_files / collection_files /
// overlay_files / playlist_files) was implemented as 44 near-duplicate
// functions -- 11 helper families x 4 kinds -- with the same shape
// copy-pasted across ~1100 lines. This module collapses that into ONE
// implementation parameterised by a per-kind config object.
//
// Public API: createLibraryFilesEditor(config) returns a bundle of the
// 11 methods sharing a closure over `config`. 025-libraries.js calls
// this factory four times (once per kind) and re-exposes each returned
// method under its historical name (setMetadataFileStatus,
// syncPlaylistFilesEditor, etc.) so the ~184 in-file call sites don't
// change.
//
// Config shape (all fields required unless marked optional):
//
//   {
//     kind: 'metadata_files' | 'collection_files' | 'overlay_files' | 'playlist_files'
//                                              -- used in the error-parser regex
//     domPrefix: 'metadata-file' | 'collection-file' | 'overlay-file' | 'playlist-file'
//                                              -- powers every data-* attribute lookup
//     editorSelector: e.g. '[data-metadata-files-editor]'
//     listSelector:   e.g. '[data-metadata-files-list]'
//     hiddenInputSelector: CSS selector that finds the JSON hidden input
//                                              -- differs meaningfully: metadata/collection/overlay use
//                                              -- name-suffix, playlist uses exact name
//     customRepoStatusSelector: e.g. '[data-metadata-custom-repo-status]'
//     repoDependencyMessage: 'Metadata file repo entries require...' -- pinned string
//     kindWord: 'metadata' | 'collection' | 'overlay' | 'playlist'
//                                              -- for the "... to be configured and saved first" prose
//                                              -- and the "... files." suffix in the custom-repo alert
//     entryLabel: 'metadata files' | 'collection files' | 'overlay files' | 'playlist files'
//                                              -- optional; if omitted, derived as kindWord + ' files'
//     normalizeEntry: (entry) => normalized-entry-or-null
//     parseFilesValue: (rawJson) => entry[]
//     buildRow: (entry) => HTMLElement
//     truncateLongFileLists: boolean
//                                              -- metadata/collection/overlay: true; playlist: false
//     showCustomRepoSavedValueDiff: boolean
//                                              -- metadata/collection/overlay: true; playlist: false
//     accordionStateStyle: 'toggle' | 'early-return'
//                                              -- collection/overlay use 'toggle' (with an
//                                              -- updateAccordionHighlights callback when the editor
//                                              -- drains to empty); metadata/playlist use
//                                              -- 'early-return' (add-invalid-and-return if any row
//                                              -- is bad, no highlight callback).
//     accordionStateClearWarningUpFront: boolean
//                                              -- only consulted when accordionStateStyle is 'early-return'.
//                                              -- playlist clears 'invalid' AND 'warning' up-front;
//                                              -- metadata only clears 'invalid' up-front and clears
//                                              -- 'warning' after the early return.
//     syncingGuardKey: optional dataset key; if set, the sync method
//                                              -- flips it to 'true' during work and drops it after,
//                                              -- suppressing re-entrant event dispatches. Only
//                                              -- playlist needed this in the original code.
//
// Injected shared helpers (all required):
//
//   {
//     getCustomRepoBase: () => string
//     getCustomRepoRaw:  () => string
//     appendMetadataSettingsLink: (target, className?) => void
//     appendInlineCodeText: (target, text, options?) => void
//     updateAccordionHighlights: () => void
//   }
//
// The factory is pure -- no module-level state, no listeners attached
// at import time. It is safe to call once per kind on page init.

export function createLibraryFilesEditor (config, shared) {
  const {
    kind,
    domPrefix,
    editorSelector,
    listSelector,
    hiddenInputSelector,
    customRepoStatusSelector,
    repoDependencyMessage,
    kindWord,
    entryLabel = `${kindWord} files`,
    normalizeEntry,
    parseFilesValue,
    buildRow,
    truncateLongFileLists,
    showCustomRepoSavedValueDiff,
    accordionStateStyle,
    accordionStateClearWarningUpFront = false,
    syncingGuardKey
  } = config

  const {
    getCustomRepoBase,
    getCustomRepoRaw,
    appendMetadataSettingsLink,
    appendInlineCodeText,
    updateAccordionHighlights
  } = shared

  // Dataset key derived from the DOM prefix. All the original functions
  // referenced dataset properties like row.dataset.metadataFileState;
  // the browser converts data-metadata-file-state to metadataFileState.
  const stateKey = camelCase(`${domPrefix}-state`)              // e.g. metadataFileState
  const buttonStateKey = camelCase(`${domPrefix}-button-state`) // e.g. metadataFileButtonState
  const dependencyKey = camelCase(`${domPrefix}-dependency`)    // e.g. metadataFileDependency
  const readyKey = camelCase(`${domPrefix.replace(/-file$/, '')}-files-ready`)
  const syncingKey = syncingGuardKey || null

  // Precompiled selectors for the row-level bits.
  const rowSelector = `[data-${domPrefix}-row]`
  const typeSelector = `[data-${domPrefix}-type]`
  const locationSelector = `[data-${domPrefix}-location]`
  const statusSelector = `[data-${domPrefix}-status]`
  const validateButtonSelector = `[data-validate-${domPrefix}]`

  function updateValidateButton (row, isValidated) {
    if (!row) return
    const button = row.querySelector(validateButtonSelector)
    if (!button) return
    const state = String(row.dataset[buttonStateKey] || '').trim() || (isValidated ? 'success' : 'idle')
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

  function setButtonState (row, state) {
    if (!row) return
    row.dataset[buttonStateKey] = state || 'idle'
    updateValidateButton(row, state === 'success')
  }

  function applyDependencyState (row, opts = {}) {
    if (!row) return false
    const skipStatus = Boolean(opts.skipStatus)
    const type = row.querySelector(typeSelector)?.value || ''
    if (type !== 'repo') {
      if (row.dataset[dependencyKey] === 'repo-missing') {
        row.dataset[dependencyKey] = ''
      }
      return false
    }

    if (getCustomRepoBase()) {
      if (row.dataset[dependencyKey] === 'repo-missing') {
        row.dataset[dependencyKey] = ''
      }
      return false
    }

    row.dataset[dependencyKey] = 'repo-missing'
    setButtonState(row, 'blocked')
    if (!skipStatus) {
      setStatus(row, 'error', repoDependencyMessage)
    }
    return true
  }

  function renderStatusMessage (target, message) {
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
        // metadata/collection/overlay use a <details> disclosure when
        // the file list is long (>5); playlist always shows all files
        // inline.
        if (truncateLongFileLists && files.length > 5) {
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
        } else {
          const list = document.createElement('ul')
          list.className = 'mb-0 mt-1 ps-3'
          files.forEach(file => {
            const item = document.createElement('li')
            appendInlineCodeText(item, file, { wrapPlainInCode: true })
            list.appendChild(item)
          })
          target.appendChild(list)
        }
      }
      return
    }

    const text = String(message || '').trim()
    if (!text) return

    if (text === repoDependencyMessage) {
      target.append(`${capitalize(kindWord)} file repo entries require Custom Repo to be configured and saved first within the `)
      appendMetadataSettingsLink(target)
      target.append(' page.')
      return
    }

    appendInlineCodeText(target, text)
  }

  function setStatus (row, statusKind, message) {
    if (!row) return
    const target = row.querySelector(statusSelector)
    if (!target) return
    row.dataset[stateKey] = statusKind || ''
    target.className = 'mt-2 small'
    if (!message) {
      target.classList.add('d-none')
      target.textContent = ''
      if (applyDependencyState(row, { skipStatus: true })) {
        setButtonState(row, 'blocked')
      } else {
        setButtonState(row, 'idle')
      }
      const editor = row.closest(editorSelector)
      if (editor) updateAccordionState(editor)
      return
    }
    target.classList.remove('d-none')
    if (statusKind === 'success') {
      target.classList.add('text-success')
    } else if (statusKind === 'error') {
      target.classList.add('text-danger')
    } else {
      target.classList.add('text-warning')
    }
    renderStatusMessage(target, message)
    if (statusKind === 'success') {
      setButtonState(row, 'success')
    } else if (row.dataset[dependencyKey] === 'repo-missing') {
      setButtonState(row, 'blocked')
    } else {
      setButtonState(row, 'idle')
    }
    const editor = row.closest(editorSelector)
    if (editor) updateAccordionState(editor)
  }

  function updateCustomRepoStatus (editor) {
    if (!editor) return
    const target = editor.querySelector(customRepoStatusSelector)
    if (!target) return

    target.replaceChildren()
    target.className = 'alert small mb-3'
    const base = getCustomRepoBase()
    if (!base) {
      target.classList.add('alert-warning')
      target.append('Custom Repo is not configured. ')
      target.append('Use ')
      appendMetadataSettingsLink(target, 'alert-link fw-semibold')
      target.append(' to configure and save it before using ')
      const code = document.createElement('code')
      code.textContent = 'repo'
      target.appendChild(code)
      target.append(` ${entryLabel}.`)
      return
    }

    target.classList.add('alert-secondary')
    const label = document.createElement('div')
    label.className = 'fw-semibold mb-1'
    label.textContent = 'Custom Repo base used for repo entries'
    target.appendChild(label)

    const baseValue = document.createElement('code')
    baseValue.textContent = base
    target.appendChild(baseValue)

    // metadata/collection/overlay: if the saved value differs from
    // the normalized base, also show the saved value and a "change it"
    // hint. Playlist historically didn't include either -- gated by
    // showCustomRepoSavedValueDiff.
    if (!showCustomRepoSavedValueDiff) return

    const raw = getCustomRepoRaw()
    if (raw && raw !== base) {
      const savedValue = document.createElement('div')
      savedValue.className = 'mt-2'
      savedValue.append('Saved Custom Repo value: ')
      const savedCode = document.createElement('code')
      savedCode.textContent = raw
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

  function updateAccordionState (editor) {
    if (!editor) return
    const accordionItem = editor.closest('.accordion-item')
    const accordionHeader = accordionItem?.querySelector(':scope > .accordion-header')
    if (!accordionHeader) return

    const rows = Array.from(editor.querySelectorAll(rowSelector))
    const hasEntries = rows.some(row => {
      const type = row.querySelector(typeSelector)?.value || ''
      const location = row.querySelector(locationSelector)?.value || ''
      return Boolean(normalizeEntry({ type, location }))
    })
    const hasInvalid = rows.some(row => {
      const state = String(row.dataset[stateKey] || '').trim().toLowerCase()
      return state === 'error' || state === 'warning'
    })

    if (accordionStateStyle === 'early-return') {
      // metadata / playlist. Clear 'invalid' (and, for playlist, also
      // 'warning') up-front; short-circuit on hasInvalid.
      if (accordionStateClearWarningUpFront) {
        accordionHeader.classList.remove('invalid', 'warning')
      } else {
        accordionHeader.classList.remove('invalid')
      }
      if (hasInvalid) {
        accordionHeader.classList.add('invalid')
        return
      }
      if (!accordionStateClearWarningUpFront) {
        accordionHeader.classList.remove('warning')
      }
      if (hasEntries) {
        accordionHeader.classList.add('selected')
      } else {
        accordionHeader.classList.remove('selected')
      }
      return
    }

    // 'toggle' style -- collection / overlay. Refreshes accordion
    // highlights globally when the editor drains to empty.
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

  function applyServerErrors (editor, errors) {
    if (!editor || !Array.isArray(errors) || !errors.length) return false
    const rows = Array.from(editor.querySelectorAll(rowSelector))
    rows.forEach(row => setStatus(row, '', ''))
    let applied = false
    const pattern = new RegExp(`${kind}\\[(\\d+)\\]:\\s*(.+)$`, 'i')
    errors.forEach(error => {
      const text = String(error || '').trim()
      const match = text.match(pattern)
      if (!match) return
      const index = Number(match[1]) - 1
      const message = match[2] || 'Validation failed.'
      if (!Number.isInteger(index) || index < 0 || index >= rows.length) return
      setStatus(rows[index], 'error', message)
      applied = true
    })
    return applied
  }

  function syncEditor (editor, emitEvents = true) {
    if (!editor) return []
    const hidden = editor.querySelector(hiddenInputSelector)
    if (!hidden) return []

    // playlist historically had a re-entrancy guard because its own
    // change-listener could re-invoke sync mid-flight. Gated on
    // syncingKey so metadata/collection/overlay stay guard-free.
    let requestedEmit = emitEvents
    if (syncingKey) {
      const alreadySyncing = editor.dataset[syncingKey] === 'true'
      if (requestedEmit && alreadySyncing) requestedEmit = false
      editor.dataset[syncingKey] = 'true'
    }

    const rows = Array.from(editor.querySelectorAll(rowSelector))
    const entries = rows.map(row => {
      const type = row.querySelector(typeSelector)?.value
      const location = row.querySelector(locationSelector)?.value
      const validated = String(row.dataset[stateKey] || '').trim().toLowerCase() === 'success'
      return normalizeEntry({ type, location, validated })
    }).filter(Boolean)
    hidden.value = JSON.stringify(entries)
    if (requestedEmit) {
      hidden.dispatchEvent(new Event('input', { bubbles: true }))
      hidden.dispatchEvent(new Event('change', { bubbles: true }))
    }
    if (syncingKey) {
      delete editor.dataset[syncingKey]
    }
    updateAccordionState(editor)
    return entries
  }

  function renderEditor (editor) {
    if (!editor) return
    const hidden = editor.querySelector(hiddenInputSelector)
    const list = editor.querySelector(listSelector)
    if (!hidden || !list) return
    updateCustomRepoStatus(editor)
    const entries = parseFilesValue(hidden.value)
    list.replaceChildren()
    entries.forEach(entry => list.appendChild(buildRow(entry)))
    list.querySelectorAll(rowSelector).forEach(row => {
      if (applyDependencyState(row)) return
      if (String(row.dataset[stateKey] || '').trim().toLowerCase() === 'success') {
        setButtonState(row, 'success')
      } else {
        setButtonState(row, 'idle')
      }
    })
    syncEditor(editor, false)
    updateAccordionState(editor)
  }

  function initEditors (scope) {
    const root = scope || document
    root.querySelectorAll(editorSelector).forEach(editor => {
      if (editor.dataset[readyKey] === 'true') return
      renderEditor(editor)
      editor.dataset[readyKey] = 'true'
    })
  }

  return {
    updateValidateButton,
    setButtonState,
    applyDependencyState,
    renderStatusMessage,
    setStatus,
    updateCustomRepoStatus,
    updateAccordionState,
    applyServerErrors,
    syncEditor,
    renderEditor,
    initEditors
  }
}

function camelCase (kebab) {
  return kebab.replace(/-([a-z])/g, (_, c) => c.toUpperCase())
}

function capitalize (str) {
  return str.charAt(0).toUpperCase() + str.slice(1)
}
