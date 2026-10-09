export function getRatingChoice (input) {
  return String(input?.value ?? input?.dataset?.default ?? '').trim().toLowerCase()
}

export function getRatingSourceService (source) {
  const value = String(source || '').toLowerCase()
  if (value === 'mdb' || value.startsWith('mdb_')) return 'mdblist'
  if (value === 'omdb' || value.startsWith('omdb_')) return 'omdb'
  if (value === 'anidb' || value.startsWith('anidb_')) return 'anidb'
  if (value === 'mal' || value.startsWith('mal_')) return 'mal'
  if (value === 'plex' || value.startsWith('plex_') || ['critic', 'audience', 'user'].includes(value)) return 'plex'
  if (['tmdb', 'floppy', 'serializd'].includes(value)) return value
  return null
}

export function enforceUniqueRatingSlots (selects, container) {
  const counts = new Map()
  selects.forEach(select => {
    const value = getRatingChoice(select)
    if (!value || value === 'none') return
    counts.set(value, (counts.get(value) || 0) + 1)
  })
  selects.forEach(select => {
    const selectedValue = getRatingChoice(select)
    Array.from(select.options || []).forEach(option => {
      const value = String(option.value || '').trim().toLowerCase()
      option.disabled = Boolean(value && value !== 'none' && value !== selectedValue && counts.has(value))
    })
  })
  const existing = container.querySelector('.rating-unique-warning')
  if (Array.from(counts.values()).some(count => count > 1)) {
    if (!existing) {
      const anchor = selects[0]?.closest('.input-group') || selects[0]?.parentElement
      if (anchor) {
        const warning = document.createElement('div')
        warning.className = 'alert alert-warning py-1 px-2 mt-2 small rating-unique-warning'
        warning.textContent = 'Each rating source can only be used once. Please choose unique values.'
        anchor.insertAdjacentElement('afterend', warning)
      }
    }
  } else {
    existing?.remove()
  }
}
