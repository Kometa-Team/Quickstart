/* global EventHandler, ValidationHandler, Sortable, setupParentChildToggleSync, bootstrap */

document.addEventListener('DOMContentLoaded', function () {
  console.log('[DEBUG] Initializing Libraries...')

  const scriptsToLoad = [
    '/static/local-js/imageHandler.js',
    '/static/local-js/overlayHandler.js',
    '/static/local-js/validationHandler.js',
    '/static/local-js/eventHandler.js'
  ]

  function reinitializeTooltipsAndPopovers () {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    tooltipTriggerList.forEach(el => {
      bootstrap.Tooltip.getOrCreateInstance(el)
    })

    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'))
    popoverTriggerList.forEach(el => {
      bootstrap.Popover.getOrCreateInstance(el)
    })

    console.log('[DEBUG] Reinitialized tooltips and popovers')
  }

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

    document.querySelectorAll('.overlay-template-section').forEach((el) => {
      el.style.display = 'none'
    })

    document.querySelectorAll('.overlay-toggle').forEach((checkbox) => {
      checkbox.addEventListener('change', function () {
        toggleOverlayTemplateSection(this)
      })
      toggleOverlayTemplateSection(checkbox) // immediate init
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
      renderSortableList(libraryId, prefix, list, hiddenInput, values)
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

    // Lazy load each library section on accordion expand
    document.querySelectorAll('.lazy-library-body').forEach(container => {
      const wrapper = container.closest('.collapse')
      if (!wrapper) return

      wrapper.addEventListener('show.bs.collapse', () => {
        if (!container.dataset.loaded) {
          const template = document.getElementById(`${container.dataset.libraryId}-template`)
          if (template) {
            container.innerHTML = template.innerHTML
            container.dataset.loaded = 'true'

            reinitializeTooltipsAndPopovers()
            setupParentChildToggleVisibility()

            if (typeof EventHandler?.attachLibraryListeners === 'function') {
              EventHandler.attachLibraryListeners()
            }

            if (typeof ValidationHandler?.updateValidationState === 'function') {
              ValidationHandler.updateValidationState()
            }

            console.log(`[DEBUG] Loaded: ${container.dataset.libraryId}`)
          }
        }
      })
    })

    // Rotate chevron icon on collapse/expand
    document.querySelectorAll('.card-header[data-bs-toggle="collapse"]').forEach(header => {
      const targetSelector = header.getAttribute('data-bs-target')
      const target = document.querySelector(targetSelector)
      const chevron = header.querySelector('.rotate-icon')

      if (!target || !chevron) return

      target.addEventListener('show.bs.collapse', () => {
        chevron.classList.add('rotate')
      })

      target.addEventListener('hide.bs.collapse', () => {
        chevron.classList.remove('rotate')
      })
    })
  })
})

function toggleOverlayTemplateSection (checkbox) {
  const groupContainer = checkbox.closest('.template-toggle-group')
  const templateSection = groupContainer?.querySelector('.overlay-template-section')

  if (templateSection) {
    templateSection.style.display = checkbox.checked ? '' : 'none'
  }
}

function setupCustomStringListHandlers (prefix) {
  document.querySelectorAll(`input[id$="attribute_${prefix}_custom_hidden"]`).forEach(hidden => {
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
          renderCustomList(updated)
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
  })
}

function setupParentChildToggleVisibility () {
  document.querySelectorAll('[data-template-group]').forEach(parentToggle => {
    const groupId = parentToggle.getAttribute('data-template-group')
    const wrapper = parentToggle.closest('.template-toggle-group')
    const childrenGroup = document.querySelector(`[data-toggle-parent="${groupId}"]`)

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
