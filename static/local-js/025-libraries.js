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
      console.log('[DEBUG] Calling EventHandler.attachLibraryListeners()')
      EventHandler.attachLibraryListeners()
    }

    if (typeof ValidationHandler !== 'undefined' && ValidationHandler.updateValidationState) {
      console.log('[DEBUG] Calling ValidationHandler.updateValidationState()')
      ValidationHandler.updateValidationState()
    }

    // Restore sortable list and recheck toggles
    document.querySelectorAll('.sortable-list').forEach(list => {
      const inputId = list.id.replace('sortable', 'order')
      const hiddenInput = document.getElementById(inputId)
      let values = []

      try {
        values = JSON.parse(hiddenInput.value || '[]')
        console.log(`[DEBUG] Parsed hidden input from #${inputId}:`, values)
      } catch (e) {
        console.warn(`[WARN] Could not parse JSON from hidden input #${inputId}:`, hiddenInput.value)
      }

      list.innerHTML = ''

      values.forEach(item => {
        const toggle = document.querySelector(`#attribute_mass_genre_update_${item}`)
        if (toggle) {
          toggle.checked = true
          console.log(`[DEBUG] Auto-checked toggle: #attribute_mass_genre_update_${item}`)
        } else {
          console.log(`[DEBUG] No toggle found for: ${item}`)
        }

        const li = document.createElement('li')
        li.className = 'list-group-item sortable-item d-flex justify-content-between align-items-center'
        li.dataset.value = item

        const labelElement = document.querySelector(`label[for="attribute_mass_genre_update_${item}"]`)
        const friendlyText = labelElement?.dataset.label || item

        const span = document.createElement('span')
        span.innerHTML = `<i class="bi bi-grip-vertical me-2 drag-handle"></i>${friendlyText}`

        li.appendChild(span)

        list.appendChild(li)

        console.log(`[DEBUG] Added list item for: ${item}`)
      })

      // eslint-disable-next-line no-unused-vars
      const _sortable = new Sortable(list, {
        handle: '.drag-handle',
        animation: 150,
        onSort: function () {
          const selected = [...list.querySelectorAll('li')].map(li => li.dataset.value)
          hiddenInput.value = JSON.stringify(selected)
          console.log(`[DEBUG] Updated order for #${inputId}:`, selected)
        }
      })
    })

    document.querySelectorAll('.sortable-list').forEach(list => {
      if (!list.id.includes('mass_content_rating_update_sortable')) return

      const inputId = list.id.replace('sortable', 'order')
      const hiddenInput = document.getElementById(inputId)
      let values = []

      try {
        values = JSON.parse(hiddenInput.value || '[]')
        console.log(`[DEBUG] Parsed hidden input from #${inputId}:`, values)
      } catch (e) {
        console.warn(`[WARN] Could not parse JSON from hidden input #${inputId}:`, hiddenInput.value)
      }

      list.innerHTML = ''

      values.forEach(item => {
        const toggle = document.querySelector(`#attribute_mass_content_rating_update_${item}`)
        if (toggle) {
          toggle.checked = true
          console.log(`[DEBUG] Auto-checked content rating toggle: #attribute_mass_content_rating_update_${item}`)
        }

        const li = document.createElement('li')
        li.className = 'list-group-item sortable-item d-flex justify-content-between align-items-center'
        li.dataset.value = item

        const labelElement = document.querySelector(`label[for="attribute_mass_content_rating_update_${item}"]`)
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
          console.log(`[DEBUG] Updated content rating order for #${inputId}:`, selected)
        }
      })
    })

    // Handle toggle changes to sync with sortable list
    document.querySelectorAll("input[type=checkbox][id*='attribute_mass_content_rating_update_']").forEach(toggle => {
      toggle.addEventListener('change', function () {
        const source = this.id.match(/attribute_mass_content_rating_update_(.+)$/)[1]
        const list = document.getElementById(this.id.replace(`attribute_mass_content_rating_update_${source}`, 'mass_content_rating_update_sortable'))
        const hiddenInput = document.getElementById(this.id.replace(`attribute_mass_content_rating_update_${source}`, 'mass_content_rating_update_order'))

        let current = []
        try {
          current = JSON.parse(hiddenInput.value || '[]')
        } catch (e) {
          console.warn('[WARN] Could not parse hidden input value:', hiddenInput.value)
        }

        const index = current.indexOf(source)
        if (this.checked && index === -1) {
          current.push(source)
          console.log(`[DEBUG] Toggle ON: Added ${source} to content rating sortable + hidden input`)
        } else if (!this.checked && index !== -1) {
          current.splice(index, 1)
          console.log(`[DEBUG] Toggle OFF: Removed ${source} from content rating sortable + hidden input`)
        }

        hiddenInput.value = JSON.stringify(current)

        list.innerHTML = ''
        current.forEach(item => {
          const li = document.createElement('li')
          li.className = 'list-group-item sortable-item d-flex justify-content-between align-items-center'
          li.dataset.value = item

          const labelElement = document.querySelector(`label[for="attribute_mass_content_rating_update_${item}"]`)
          const friendlyText = labelElement?.dataset.label || item

          const span = document.createElement('span')
          span.innerHTML = `<i class="bi bi-grip-vertical me-2 drag-handle"></i>${friendlyText}`

          li.appendChild(span)

          list.appendChild(li)
        })
      })
    })

    // Handle toggle changes to sync with sortable list
    document.querySelectorAll("input[type=checkbox][id*='attribute_mass_genre_update_']").forEach(toggle => {
      toggle.addEventListener('change', function () {
        const source = this.id.match(/attribute_mass_genre_update_(.+)$/)[1]
        const list = document.getElementById(this.id.replace(`attribute_mass_genre_update_${source}`, 'mass_genre_update_sortable'))
        const hiddenInput = document.getElementById(this.id.replace(`attribute_mass_genre_update_${source}`, 'mass_genre_update_order'))

        let current = []
        try {
          current = JSON.parse(hiddenInput.value || '[]')
        } catch (e) {
          console.warn('[WARN] Could not parse hidden input value:', hiddenInput.value)
        }

        const index = current.indexOf(source)
        if (this.checked && index === -1) {
          current.push(source)
          console.log(`[DEBUG] Toggle ON: Added ${source} to sortable + hidden input`)
        } else if (!this.checked && index !== -1) {
          current.splice(index, 1)
          console.log(`[DEBUG] Toggle OFF: Removed ${source} from sortable + hidden input`)
        }

        hiddenInput.value = JSON.stringify(current)

        list.innerHTML = ''
        current.forEach(item => {
          const li = document.createElement('li')
          li.className = 'list-group-item sortable-item d-flex justify-content-between align-items-center'
          li.dataset.value = item

          const labelElement = document.querySelector(`label[for="attribute_mass_genre_update_${item}"]`)
          const friendlyText = labelElement?.dataset.label || item

          const span = document.createElement('span')
          span.innerHTML = `<i class="bi bi-grip-vertical me-2 drag-handle"></i>${friendlyText}`

          li.appendChild(span)

          list.appendChild(li)
        })
      })
    })

    // Handle toggle changes to sync with sortable list
    document.querySelectorAll("input[type=checkbox][id*='attribute_mass_original_title_update_']").forEach(toggle => {
      toggle.addEventListener('change', function () {
        const source = this.id.match(/attribute_mass_original_title_update_(.+)$/)[1]
        const list = document.getElementById(this.id.replace(`attribute_mass_original_title_update_${source}`, 'mass_original_title_update_sortable'))
        const hiddenInput = document.getElementById(this.id.replace(`attribute_mass_original_title_update_${source}`, 'mass_original_title_update_order'))

        let current = []
        try {
          current = JSON.parse(hiddenInput.value || '[]')
        } catch (e) {
          console.warn('[WARN] Could not parse hidden input value:', hiddenInput.value)
        }

        const index = current.indexOf(source)
        if (this.checked && index === -1) {
          current.push(source)
          console.log(`[DEBUG] Toggle ON: Added ${source} to original title sortable + hidden input`)
        } else if (!this.checked && index !== -1) {
          current.splice(index, 1)
          console.log(`[DEBUG] Toggle OFF: Removed ${source} from original title sortable + hidden input`)
        }

        hiddenInput.value = JSON.stringify(current)

        list.innerHTML = ''
        current.forEach(item => {
          const li = document.createElement('li')
          li.className = 'list-group-item sortable-item d-flex justify-content-between align-items-center'
          li.dataset.value = item

          const labelElement = document.querySelector(`label[for="attribute_mass_original_title_update_${item}"]`)
          const friendlyText = labelElement?.dataset.label || item

          const span = document.createElement('span')
          span.innerHTML = `<i class="bi bi-grip-vertical me-2 drag-handle"></i>${friendlyText}`

          li.appendChild(span)

          list.appendChild(li)
        })
      })
    })

    document.querySelectorAll('.sortable-list').forEach(list => {
      if (!list.id.includes('mass_original_title_update_sortable')) return

      const inputId = list.id.replace('sortable', 'order')
      const hiddenInput = document.getElementById(inputId)
      let values = []

      try {
        values = JSON.parse(hiddenInput.value || '[]')
        console.log(`[DEBUG] Parsed hidden input from #${inputId}:`, values)
      } catch (e) {
        console.warn(`[WARN] Could not parse JSON from hidden input #${inputId}:`, hiddenInput.value)
      }

      list.innerHTML = ''

      values.forEach(item => {
        const toggle = document.querySelector(`#attribute_mass_original_title_update_${item}`)
        if (toggle) {
          toggle.checked = true
          console.log(`[DEBUG] Auto-checked original title toggle: #attribute_mass_original_title_update_${item}`)
        }

        const li = document.createElement('li')
        li.className = 'list-group-item sortable-item d-flex justify-content-between align-items-center'
        li.dataset.value = item

        const labelElement = document.querySelector(`label[for="attribute_mass_original_title_update_${item}"]`)
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
          console.log(`[DEBUG] Updated original title order for #${inputId}:`, selected)
        }
      })
    })

    // (Custom genre handling will come later)
  })
})
