/* global EventHandler, ValidationHandler, Sortable */

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

    if (typeof EventHandler !== 'undefined' && EventHandler.attachLibraryListeners) {
      EventHandler.attachLibraryListeners()
    }

    if (typeof ValidationHandler !== 'undefined' && ValidationHandler.updateValidationState) {
      ValidationHandler.updateValidationState()
    }

    function initializeSortableList (libraryId, prefix) {
      const list = document.getElementById(`${libraryId}-${prefix}_sortable`)
      const hiddenInput = document.getElementById(`${libraryId}-${prefix}_order`)

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

      // eslint-disable-next-line no-unused-vars
      const _sortable = new Sortable(list, {
        handle: '.drag-handle',
        animation: 150,
        onSort: function () {
          const selected = [...list.querySelectorAll('li')].map(li => li.dataset.value)
          hiddenInput.value = JSON.stringify(selected)
          console.log(`[DEBUG] Updated order for #${hiddenInput.id}:`, selected)
        }
      })
    }

    function bindToggleToList (libraryId, prefix) {
      document.querySelectorAll(`input[type=checkbox][id^='${libraryId}-attribute_${prefix}_']`).forEach(toggle => {
        toggle.addEventListener('change', function () {
          const source = this.id.match(new RegExp(`${libraryId}-attribute_${prefix}_(.+)$`))[1]
          const list = document.getElementById(`${libraryId}-${prefix}_sortable`)
          const hiddenInput = document.getElementById(`${libraryId}-${prefix}_order`)

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

    const knownPrefixes = ['mass_genre_update', 'mass_content_rating_update', 'mass_original_title_update']

    document.querySelectorAll('.sortable-list').forEach(list => {
      const match = list.id.match(/^(.*?)-(mass_.*?)_sortable$/)
      if (!match) return

      const libraryId = match[1]
      const prefix = match[2]

      if (!knownPrefixes.includes(prefix)) return

      initializeSortableList(libraryId, prefix)
      bindToggleToList(libraryId, prefix)
    })
  })
})
