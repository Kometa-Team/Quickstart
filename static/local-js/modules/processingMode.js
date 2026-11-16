export function validateProcessingMode (value) {
  if (value === '' || value === 'full' || value === 'diff') return value
  const added = value.match(/^added\((0*[1-9][0-9]*)([mhd]?)\)$/i)
  if (added) {
    const seconds = Number(added[1]) * ({ m: 60, h: 3600 }[added[2].toLowerCase()] || 86400)
    if (Number.isSafeInteger(seconds) && seconds <= Date.now() / 1000 + 62135596800) return value
    throw new Error('Added duration is too large.')
  }
  const index = value.match(/^index\(([a-z])(?:-([a-z])(#)?)?\)$/i)
  if (index) {
    if (index[1].toLowerCase() <= (index[2] || index[1]).toLowerCase()) return value
    throw new Error('Alphabetical range must be ascending, such as A-F.')
  }
  if (/^items\(((?:(?:tmdb|tvdb|plex):0*[1-9][0-9]*|imdb:tt[0-9]+))(\|(?:(?:tmdb|tvdb|plex):0*[1-9][0-9]*|imdb:tt[0-9]+))*\)$/.test(value)) return value
  throw new Error('Choose a valid processing mode. Durations and numeric IDs must be positive; item IDs need a Plex, IMDb, TMDb, or TVDb prefix.')
}

export function processingModeValue (root) {
  if (!root) return ''
  const value = selector => root.querySelector(selector)?.value?.trim() || ''
  switch (value('[data-processing-kind]')) {
    case 'added': return `added(${value('[data-processing-amount]')}${value('[data-processing-unit]')})`
    case 'index': {
      const first = value('[data-processing-first]').toUpperCase()
      let last = value('[data-processing-last]').toUpperCase()
      const symbols = root.querySelector('[data-processing-symbols]')?.checked
      if (symbols && !last) last = first
      return `index(${first}${last ? `-${last}${symbols ? '#' : ''}` : ''})`
    }
    case 'items': return `items(${value('[data-processing-ids]').split(/[|,\n]+/).map(id => id.trim()).filter(Boolean).join('|')})`
    case 'custom': return value('[data-processing-custom]')
    default: return value('[data-processing-kind]')
  }
}

export function initProcessingMode (root, initial = 'full', onChange = () => {}) {
  if (!root || root.dataset.processingInitialized) return
  root.dataset.processingInitialized = 'true'
  const kind = root.querySelector('[data-processing-kind]')
  const set = (selector, value) => { root.querySelector(selector).value = value }
  const added = initial.match(/^added\((\d+)([mhd]?)\)$/i)
  const index = initial.match(/^index\(([a-z])(?:-([a-z])(#)?)?\)$/i)
  if (added) {
    kind.value = 'added'
    set('[data-processing-amount]', added[1])
    set('[data-processing-unit]', added[2].toLowerCase())
  } else if (index) {
    kind.value = 'index'
    set('[data-processing-first]', index[1].toUpperCase())
    set('[data-processing-last]', (index[2] || '').toUpperCase())
    root.querySelector('[data-processing-symbols]').checked = Boolean(index[3])
  } else if (initial.startsWith('items(') && initial.endsWith(')')) {
    kind.value = 'items'
    set('[data-processing-ids]', initial.slice(6, -1))
  } else if (['', 'full', 'diff'].includes(initial)) {
    kind.value = initial
  } else {
    kind.value = 'custom'
    set('[data-processing-custom]', initial)
  }
  const refresh = () => {
    root.querySelectorAll('[data-processing-fields]').forEach(el => {
      const active = el.dataset.processingFields === kind.value
      el.classList.toggle('d-none', !active)
      el.querySelectorAll('input, select, textarea').forEach(input => { input.disabled = !active })
    })
    const error = root.querySelector('[data-processing-error]')
    try {
      validateProcessingMode(processingModeValue(root))
      if (error) error.textContent = ''
    } catch (err) { if (error) error.textContent = err.message }
  }
  refresh()
  for (const eventName of ['input', 'change']) root.addEventListener(eventName, () => { refresh(); onChange() })
}
