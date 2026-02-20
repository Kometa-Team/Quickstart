/* global EventHandler, ValidationHandler, OverlayHandler, Sortable, showToast, setupParentChildToggleSync, bootstrap, FontFace, PathValidation */

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
        const currentValue = select.value || ''
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
        select.innerHTML = ''
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
        select.innerHTML = ''
        keep.forEach(option => select.appendChild(option))
        sortable.forEach(option => select.appendChild(option))
        select.value = currentValue
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

    function setupTemplateStringListHandlers (scope) {
      const root = scope || document
      root.querySelectorAll('[data-template-string-list]').forEach(wrapper => {
        if (wrapper.dataset.listenerAdded) return
        const hiddenId = wrapper.dataset.hiddenInput
        const hidden = hiddenId ? document.getElementById(hiddenId) : wrapper.querySelector('input[type="hidden"]')
        const input = wrapper.querySelector('input[type="text"]')
        const addBtn = wrapper.querySelector('[data-template-string-add]')
        const list = wrapper.querySelector('[data-template-string-items]')

        if (!hidden || !input || !addBtn || !list) return

        function parseValues () {
          const raw = String(hidden.value || '').trim()
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

        function renderList (values) {
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

            li.querySelector('button').addEventListener('click', () => {
              const updated = values.filter(item => item !== value)
              hidden.value = JSON.stringify(updated)
              renderList(updated)
            })
          })
        }

        function addValue () {
          const value = input.value.trim()
          if (!value) return
          const current = parseValues()
          if (current.includes(value)) return
          current.push(value)
          hidden.value = JSON.stringify(current)
          renderList(current)
          input.value = ''
        }

        const initial = parseValues()
        hidden.value = JSON.stringify(initial)
        renderList(initial)

        addBtn.addEventListener('click', addValue)
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

      grid.innerHTML = ''
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
      syncStatus()
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
      sortLanguageSelects(card)
      initNumericOnlyInputs(card)
      initStylePreviewGrids(card)
      initRelativeYearInputs(card)
      initScheduleBuilders(card)
      wireOffsetReset(card)
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
      setupAddMissingDependencies(card)
      if (typeof setupParentChildToggleSync === 'function') {
        setupParentChildToggleSync()
      }
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
    }

    wireFontPickerModal()

    function buildPayloadFromCard (card) {
      const payload = {}
      card.querySelectorAll('input, select, textarea').forEach(el => {
        if (!el.name || el.disabled) return
        if (el.dataset && el.dataset.skipYaml === 'true') return
        if (el.type === 'file') return

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

        payload[el.name] = el.value ?? ''
      })
      return payload
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
          const inputId = `copy-target-${id}`
          const item = document.createElement('label')
          item.className = 'list-group-item d-flex align-items-center gap-2'
          item.innerHTML = `
            <input id="${inputId}" name="copy_target" class="form-check-input me-2 copy-target-checkbox" type="checkbox" value="${id}">
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
        if (changes.length) {
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

function setupAddMissingDependencies (scope) {
  const root = scope || document
  const addMissingToggles = Array.from(root.querySelectorAll('input.template-child-toggle[id*="radarr_add_missing_"], input.template-child-toggle[id*="sonarr_add_missing_"]'))
  if (!addMissingToggles.length) return

  const groupMap = new Map()

  addMissingToggles.forEach(addToggle => {
    const id = addToggle.id || ''
    const split = id.split('-template_collection_')
    if (split.length !== 2) return
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
    if (!useTail) return
    const useToggle = document.getElementById(`${prefix}-template_collection_${useTail}`)
    if (!useToggle) return

    const list = groupMap.get(useToggle) || []
    list.push(addToggle)
    groupMap.set(useToggle, list)
  })

  const applyState = (useToggle, toggles) => {
    const show = useToggle.checked
    toggles.forEach(addToggle => {
      const row = addToggle.closest('.form-check')
      if (row) row.style.display = show ? '' : 'none'
      addToggle.disabled = !show
      if (!show) {
        addToggle.checked = false
        const hidden = document.querySelector(`input[type="hidden"][name="${addToggle.name}"]`)
        if (hidden) hidden.value = 'false'
      }
    })
  }

  groupMap.forEach((toggles, useToggle) => {
    if (useToggle.dataset.addMissingBound === 'true') return
    useToggle.dataset.addMissingBound = 'true'
    useToggle.addEventListener('change', () => applyState(useToggle, toggles))
    applyState(useToggle, toggles)
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
