/* global EventHandler, ValidationHandler, Sortable, showToast, setupParentChildToggleSync, bootstrap */

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
      const option = libraryPicker.querySelector(`option[value="${libraryId}"]`)
      const targetInputId = toggle?.dataset.targetInput
      const targetInput = targetInputId ? document.getElementById(targetInputId) : null
      if (!toggle || !option || toggle.dataset.listenerAdded || !targetInput) return

      toggle.addEventListener('change', () => {
        option.dataset.configured = toggle.checked ? 'true' : 'false'
        targetInput.value = toggle.checked ? toggle.value : ''
        refreshPickerLabels()
        if (typeof ValidationHandler !== 'undefined' && ValidationHandler.updateValidationState) {
          ValidationHandler.updateValidationState()
        }
      })
      toggle.dataset.listenerAdded = 'true'
    }

    function moveCurrentToCache () {
      const current = libraryContainer.firstElementChild
      if (current) {
        current.style.display = 'none'
        libraryCache.appendChild(current)
      }
    }

    function mountCard (card, libraryId) {
      libraryContainer.innerHTML = ''
      card.style.display = ''
      libraryContainer.appendChild(card)
      activeLibraryId = libraryId
      syncHiddenCheckboxPairs(card)
      wireIncludeToggle(card, libraryId)
      refreshPickerLabels()
      initTooltips(card)
      wireOffsetReset(card)
      initSortablesInScope(card)
      setupCustomStringListHandlers('mass_genre_update', card)
      setupCustomStringListHandlers('radarr_remove_by_tag', card)
      setupCustomStringListHandlers('sonarr_remove_by_tag', card)
      setupCustomStringListHandlers('metadata_backup', card)
      setupCustomStringListHandlers('mass_content_rating_update', card)
      setupCustomStringListHandlers('mass_genre_mapper', card)
      setupMappingListHandlers('genre_mapper', card)
      setupMappingListHandlers('content_rating_mapper', card)
      wireOverlayDetailToggles(card)
      setupParentChildToggleVisibility(card)
      if (typeof setupParentChildToggleSync === 'function') {
        setupParentChildToggleSync()
      }
      wireOverlayTemplateSections(card)
      if (typeof EventHandler !== 'undefined') {
        EventHandler.attachLibraryListeners()
      }
      if (typeof ValidationHandler !== 'undefined' && ValidationHandler.updateValidationState) {
        ValidationHandler.updateValidationState()
      }
    }

    function buildPayloadFromCard (card) {
      const payload = {}
      card.querySelectorAll('input, select, textarea').forEach(el => {
        if (!el.name || el.disabled) return
        if (el.type === 'file') return

        if (el.tagName === 'SELECT' && el.multiple) {
          payload[el.name] = Array.from(el.selectedOptions).map(opt => opt.value)
          return
        }

        if (el.type === 'checkbox' || el.type === 'radio') {
          payload[el.name] = el.checked ? (el.value || 'on') : ''
          return
        }

        payload[el.name] = el.value ?? ''
      })
      return payload
    }

    function autosaveActiveLibrary () {
      const card = libraryContainer.firstElementChild
      if (!activeLibraryId || !card) return Promise.resolve()

      const payload = buildPayloadFromCard(card)
      const option = libraryPicker?.querySelector(`option[value="${activeLibraryId}"]`)
      const friendlyName = option?.dataset.label || option?.textContent?.trim() || activeLibraryId

      return fetch(`/autosave_library/${encodeURIComponent(activeLibraryId)}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(res => {
          if (!res.ok) throw new Error(`Autosave failed: ${res.status}`)
          return res.json().catch(() => ({}))
        })
        .then(data => {
          if (data && data.success && typeof showToast === 'function') {
            showToast('success', `Autosaved ${friendlyName}.`)
          }
          return data
        })
        .catch(err => {
          console.error('[Autosave] Failed to save library', activeLibraryId, err)
          if (typeof showToast === 'function') {
            showToast('error', `Autosave failed for ${friendlyName}.`)
          }
          throw err
        })
    }

    function openCopyModal (sourceId, sourceName, sourceType) {
      if (!copyModal) return
      copyWarning.style.display = 'none'
      copySubtitle.textContent = `Mirror settings from "${sourceName}" to other ${sourceType === 'movie' ? 'movie' : 'show'} libraries`
      copyTargetsContainer.innerHTML = ''

      const options = Array.from(libraryPicker.querySelectorAll('option[value]')).filter(opt =>
        opt.dataset.libraryType === sourceType && opt.value !== sourceId
      )

      if (!options.length) {
        copyTargetsContainer.innerHTML = '<div class="text-muted">No other libraries of this type available.</div>'
      } else {
        options.forEach(opt => {
          const id = opt.value
          const label = opt.dataset.label || opt.textContent
          const item = document.createElement('label')
          item.className = 'list-group-item d-flex align-items-center gap-2'
          item.innerHTML = `
            <input class="form-check-input me-2 copy-target-checkbox" type="checkbox" value="${id}">
            <span>${label}</span>
          `
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
            libraryCache.innerHTML = ''

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

    function loadLibrary (libraryId) {
      if (libraryId === activeLibraryId) return
      const requestId = ++loadRequestId
      const setLoading = (flag) => {
        if (libraryLoading) {
          libraryLoading.classList.toggle('d-none', !flag)
        }
        if (libraryPicker) {
          libraryPicker.disabled = !!flag
        }
      }

      setLoading(true)
      autosaveActiveLibrary()
        .finally(() => {
          if (requestId !== loadRequestId) return

          if (!libraryId) {
            libraryContainer.innerHTML = ''
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
              const wrapper = document.createElement('div')
              wrapper.innerHTML = html
              const card = wrapper.firstElementChild
              if (!card) throw new Error('Empty fragment response')
              mountCard(card, libraryId)
              setLoading(false)
            })
            .catch(err => {
              console.error(err)
              setLoading(false)
            })
        })
    }

    if (libraryPicker) {
      libraryPicker.addEventListener('change', (e) => {
        loadLibrary(e.target.value)
      })

      refreshPickerLabels()
      const configuredFirst = libraryPicker.querySelector('option[data-configured="true"]')
      const firstLibrary = libraryPicker.value ||
        configuredFirst?.value ||
        libraryPicker.querySelector('option[value]:not([value=""])')?.value
      if (configuredFirst) {
        libraryPicker.value = configuredFirst.value
        loadLibrary(configuredFirst.value)
      } else if (firstLibrary) {
        loadLibrary(firstLibrary)
      } else {
        libraryPicker.value = ''
      }
    }

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
        console.warn(`[WARN] Missing sortable list or hidden input for ${libraryId}-${prefix}`)
        return
      }

      let values = []
      try {
        values = JSON.parse(hiddenInput.value || '[]')
        console.log(`[DEBUG] Parsed hidden input from #${hiddenInput.id}:`, values)
      } catch (e) {
        console.warn(`[WARN] Could not parse JSON from hidden input #${hiddenInput.id}:`, hiddenInput.value)
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

        console.log(`[DEBUG] Initializing sortable for ${libraryId} with prefix ${prefix} (scoped)`)

        initializeSortableList(libraryId, prefix)
        bindToggleToList(libraryId, prefix)

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

        list.dataset.sortableInit = 'true'
      })
    }

    function renderSortableList (libraryId, prefix, list, hiddenInput, values) {
      list.innerHTML = ''

      values.forEach(item => {
        const toggle = document.getElementById(`${libraryId}-attribute_${prefix}_${item}`)
        if (toggle) toggle.checked = true

        const li = document.createElement('li')
        li.className = 'list-group-item sortable-item d-flex justify-content-between align-items-center'
        li.dataset.value = item

        const labelElement = document.querySelector(`label[for="${libraryId}-attribute_${prefix}_${item}"]`)
        const friendlyText = labelElement?.dataset.label || item

        const span = document.createElement('span')
        span.innerHTML = `<i class="bi bi-grip-vertical me-2 drag-handle"></i>${friendlyText}`

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

  if (templateSection) {
    if (checkbox.checked) {
      templateSection.style.display = 'block'
      if (detailsToggle) {
        detailsToggle.classList.remove('d-none')
        detailsToggle.textContent = 'Hide Details'
      }
    } else {
      templateSection.style.display = 'none'
      if (detailsToggle) {
        detailsToggle.classList.add('d-none')
        detailsToggle.textContent = 'Details'
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
      list.innerHTML = ''

      values.forEach(value => {
        const li = document.createElement('li')
        li.className = 'list-group-item d-flex justify-content-between align-items-center'
        li.innerHTML = `
          <span>${value}</span>
          <button type="button" class="btn btn-sm btn-danger" aria-label="Remove">
            <i class="bi bi-x-lg"></i>
          </button>`
        list.appendChild(li)

        li.querySelector('button').addEventListener('click', function () {
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
      console.warn(`[WARN] Could not parse hidden input for ${prefix}:`, hidden.value)
    }
    renderCustomList(current)

    // Add button logic
    button.addEventListener('click', function () {
      let current = []
      try {
        current = JSON.parse(hidden.value || '[]')
      } catch (e) {
        console.warn(`[WARN] Could not parse hidden input for ${prefix}:`, hidden.value)
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
      list.innerHTML = ''
      Object.entries(data).forEach(([key, value]) => {
        const li = document.createElement('li')
        li.className = 'list-group-item d-flex justify-content-between align-items-center'
        const display = value ? `${key} -> ${value}` : `${key} (remove)`
        li.innerHTML = `
          <span>${display}</span>
          <button type="button" class="btn btn-sm btn-danger" aria-label="Remove">
            <i class="bi bi-x-lg"></i>
          </button>`
        list.appendChild(li)
        li.querySelector('button').addEventListener('click', () => {
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
      console.warn(`[WARN] Could not parse hidden input for ${prefix}:`, hidden.value)
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
      const hId = btn.dataset.horizontalId
      const vId = btn.dataset.verticalId
      const pId = btn.dataset.positionId
      const hInput = hId ? document.getElementById(hId) : null
      const vInput = vId ? document.getElementById(vId) : null
      const pInput = pId ? document.getElementById(pId) : null
      if (hInput && hInput.dataset.default !== undefined) {
        hInput.value = hInput.dataset.default
        hInput.dispatchEvent(new Event('change', { bubbles: true }))
      }
      if (vInput && vInput.dataset.default !== undefined) {
        vInput.value = vInput.dataset.default
        vInput.dispatchEvent(new Event('change', { bubbles: true }))
      }
      if (pInput && pInput.dataset.default !== undefined) {
        pInput.value = pInput.dataset.default
        pInput.dispatchEvent(new Event('change', { bubbles: true }))
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

    function updateVisibilityAndBorder () {
      const childrenToggles = childrenGroup.querySelectorAll("input[type='checkbox']")
      const anyChildChecked = Array.from(childrenToggles).some(el => el.checked)
      const parentChecked = parentToggle.checked

      childrenGroup.style.display = parentChecked ? 'block' : 'none'

      if (!parentChecked) {
        childrenToggles.forEach(child => {
          child.checked = false
          const hidden = document.querySelector(`input[type="hidden"][name="${child.name}"]`)
          if (hidden) hidden.value = 'false'
        })
      }

      if (parentChecked && anyChildChecked) {
        wrapper.classList.add('template-toggle-group-bordered')
      } else {
        wrapper.classList.remove('template-toggle-group-bordered')
      }

      EventHandler.updateAccordionHighlights()
      ValidationHandler.updateValidationState()
    }

    parentToggle.addEventListener('change', updateVisibilityAndBorder)
    childrenGroup.querySelectorAll("input[type='checkbox']").forEach(child =>
      child.addEventListener('change', updateVisibilityAndBorder)
    )

    updateVisibilityAndBorder() // Initial check
    parentToggle.dataset.childVisibilityBound = 'true'
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
      btn.textContent = isHidden ? 'Hide Details' : 'Details'
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
