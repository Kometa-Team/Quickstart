// Clearing remains available when Plex Pass prevents selecting a new sort mode.
export function clearAutoSortHubs (button) {
  const field = document.getElementById(button.dataset.clearAutoSortHubs)
  if (!field) return
  const preserved = document.getElementById(`${field.id}_preserved`)
  field.value = ''
  if (preserved) preserved.value = ''
  field.dispatchEvent(new Event('change', { bubbles: true }))
}

export function initAutoSortHubs () {
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-clear-auto-sort-hubs]')
    if (button) clearAutoSortHubs(button)
  })
}
