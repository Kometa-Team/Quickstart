import { initProcessingMode, processingModeValue, validateProcessingMode } from './processingMode.js'

export function decodeLibrarySchedule (raw) {
  if (typeof raw !== 'string') return raw
  const value = raw.trim()
  return /^[\[{"]/.test(value) ? JSON.parse(value) : value
}

export function scheduleYamlPreview (value) {
  if (value === '' || value == null) return '# No library schedule; process whenever Kometa runs.'
  if (!Array.isArray(value)) return `schedule: ${JSON.stringify(value)}`
  return 'schedule:\n' + value.map(rule => typeof rule === 'string' ? `  - ${JSON.stringify(rule)}` : `  - schedule: ${JSON.stringify(rule.schedule)}\n    mode: ${JSON.stringify(rule.mode)}`).join('\n')
}

const dayAliases = ['monday mon m', 'tuesday tues tue tu t', 'wednesday wed w', 'thursday thurs thur thu th r', 'friday fri f', 'saturday sat s', 'sunday sun su u']
const canonicalDay = value => dayAliases.find(names => names.split(' ').includes(value))?.split(' ')[0]

export function initLibraryScheduling (scope = document) {
  scope.querySelectorAll('[data-library-scheduling]').forEach(root => {
    if (root.dataset.schedulingInitialized) return
    root.dataset.schedulingInitialized = 'true'
    const hidden = root.querySelector('[data-library-schedule-value]')
    const format = root.querySelector('[data-library-schedule-format]')
    const editor = root.querySelector('[data-library-schedule-editor]')
    const rows = root.querySelector('[data-library-schedule-rows]')
    const preview = root.querySelector('[data-library-schedule-preview]')
    const error = root.querySelector('[data-library-schedule-error]')
    const repair = root.querySelector('[data-library-schedule-repair]')
    const raw = root.querySelector('[data-library-schedule-raw]')
    const template = root.querySelector('[data-library-schedule-row-template]')
    let sequence = 0
    let legacyList = false
    let writing = false
    const allRows = () => Array.from(rows.children)
    const showFormat = () => {
      editor.classList.toggle('d-none', format.value === 'none')
      allRows().forEach((row, index) => {
        row.querySelector('[data-schedule-rule-mode]').classList.toggle('d-none', format.value !== 'rules')
        row.querySelector('[data-schedule-row-number]').textContent = `Rule ${index + 1}`
        row.querySelector('[data-schedule-up]').disabled = index === 0
        row.querySelector('[data-schedule-down]').disabled = index === rows.children.length - 1
      })
    }
    const expression = row => {
      const frequency = row.querySelector('[data-schedule-frequency]').value
      row.querySelectorAll('[data-schedule-fields]').forEach(el => el.classList.toggle('d-none', el.dataset.scheduleFields !== frequency))
      row.querySelector('[data-schedule-exclusion]').classList.toggle('d-none', !['weekly', 'monthly'].includes(frequency))
      if (frequency === 'daily') return 'daily'
      if (frequency === 'custom') return row.querySelector('[data-schedule-expression]').value.trim()
      const params = frequency === 'weekly'
        ? Array.from(row.querySelectorAll('[data-schedule-day]:checked')).map(input => input.value).join('|')
        : row.querySelector('[data-schedule-dates]').value.trim().split(/[|,]+/).map(day => day.trim()).join('|')
      return `${frequency}${row.querySelector('[data-schedule-not]').checked ? '.not' : ''}(${params})`
    }
    const update = () => {
      showFormat()
      const values = allRows().map(row => ({ schedule: expression(row), mode: processingModeValue(row.querySelector('[data-processing-mode]')) }))
      let value = ''
      if (format.value === 'rules') value = values
      if (format.value === 'basic') value = values.length === 1 && !legacyList ? values[0].schedule : values.map(rule => rule.schedule)
      const next = typeof value === 'string' ? value : JSON.stringify(value)
      if (hidden.value !== next) {
        hidden.value = next
        writing = true
        hidden.dispatchEvent(new Event('change', { bubbles: true }))
        writing = false
      }
      preview.textContent = scheduleYamlPreview(value)
      error.textContent = ''
      if (format.value !== 'none') {
        try {
          if (!values.length) throw new Error('Add at least one rule or choose No library schedule.')
          for (const rule of values) {
            if (!rule.schedule || /\(\)/.test(rule.schedule)) throw new Error('Choose days or enter a complete schedule expression.')
            if (format.value === 'rules') validateProcessingMode(rule.mode)
          }
        } catch (err) { error.textContent = err.message }
      }
    }
    const addRow = (rule = { schedule: 'daily', mode: 'full' }) => {
      const wrapper = document.createElement('div')
      wrapper.innerHTML = template.innerHTML.replaceAll('__RULE__', `${root.dataset.libraryId}-rule-${++sequence}`)
      const row = wrapper.firstElementChild
      rows.append(row)
      const frequency = row.querySelector('[data-schedule-frequency]')
      const value = rule.schedule
      const match = value.match(/^(weekly|monthly)(\.not)?\(([^()]+)\)$/i)
      frequency.value = value === 'daily' ? 'daily' : 'custom'
      row.querySelector('[data-schedule-expression]').value = value
      if (match) {
        const params = match[3].toLowerCase().split('|')
        if (match[1].toLowerCase() === 'monthly' || params.every(day => canonicalDay(day))) {
          frequency.value = match[1].toLowerCase()
          row.querySelector('[data-schedule-not]').checked = Boolean(match[2])
          row.querySelector('[data-schedule-dates]').value = match[3]
          row.querySelectorAll('[data-schedule-day]').forEach(input => { input.checked = params.map(canonicalDay).includes(input.value) })
        }
      }
      initProcessingMode(row.querySelector('[data-processing-mode]'), rule.mode)
      expression(row)
      row.querySelector('[data-schedule-up]').addEventListener('click', () => { if (row.previousElementSibling) rows.insertBefore(row, row.previousElementSibling); update() })
      row.querySelector('[data-schedule-down]').addEventListener('click', () => { if (row.nextElementSibling) rows.insertBefore(row.nextElementSibling, row); update() })
      row.querySelector('[data-schedule-remove]').addEventListener('click', () => { row.remove(); if (!rows.children.length) format.value = 'none'; update() })
      for (const eventName of ['input', 'change']) row.addEventListener(eventName, update)
    }
    const restore = () => {
      rows.replaceChildren()
      error.textContent = ''
      repair.classList.add('d-none')
      try {
        const value = decodeLibrarySchedule(hidden.value)
        if (value && !Array.isArray(value) && typeof value !== 'string') throw new Error('Processing rules must be an ordered list. Repair the imported schedule below.')
        if (Array.isArray(value) && !value.length) throw new Error('Add a scheduling rule or select No library schedule.')
        legacyList = Array.isArray(value) && value.every(entry => typeof entry === 'string')
        const entries = Array.isArray(value) ? value : value ? [value] : []
        if (entries.some(entry => typeof entry !== 'string' && (!entry || typeof entry.schedule !== 'string' || typeof entry.mode !== 'string' || Object.keys(entry).sort().join('|') !== 'mode|schedule'))) throw new Error('The imported schedule contains unsupported values. Repair it below; its saved value is preserved.')
        if (entries.some(entry => typeof entry === 'string') && entries.some(entry => typeof entry !== 'string')) throw new Error('Basic schedule expressions and processing rules cannot be mixed.')
        format.value = !entries.length ? 'none' : entries.every(entry => typeof entry === 'string') ? 'basic' : 'rules'
        entries.forEach(entry => addRow(typeof entry === 'string' ? { schedule: entry, mode: 'full' } : entry))
        preview.textContent = scheduleYamlPreview(value)
      } catch (err) {
        format.value = 'none'
        error.textContent = err.message
        repair.classList.remove('d-none')
        raw.value = hidden.value
        preview.textContent = hidden.value
      }
      showFormat()
    }
    root.querySelector('[data-library-schedule-add]').addEventListener('click', () => { addRow(); update() })
    format.addEventListener('change', () => { if (format.value !== 'none' && !rows.children.length) addRow(); repair.classList.add('d-none'); update() })
    root.querySelector('[data-library-schedule-load]').addEventListener('click', () => { hidden.value = raw.value; restore(); hidden.dispatchEvent(new Event('change', { bubbles: true })) })
    hidden.addEventListener('change', () => { if (!writing) restore() })
    const confirm = root.querySelector('[data-schedule-confirm]')
    confirm?.addEventListener('change', () => {
      const output = root.querySelector('[data-schedule-confirm-value]')
      output.value = String(confirm.checked)
      output.dispatchEvent(new Event('change', { bubbles: true }))
    })
    restore()
  })
}
