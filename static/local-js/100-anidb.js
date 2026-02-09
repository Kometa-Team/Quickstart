/* global $ */

$(document).ready(function () {
  const enableToggle = document.getElementById('anidb_enable')
  const fields = document.getElementById('anidb-fields')

  if (!enableToggle || !fields) return

  const updateVisibility = () => {
    const enabled = enableToggle.checked
    fields.classList.toggle('d-none', !enabled)
    if (!enabled) {
      const matureToggle = document.getElementById('anidb_enable_mature')
      const languageSelect = document.getElementById('anidb_language')
      const cacheInput = document.getElementById('anidb_cache_expiration')
      if (matureToggle) matureToggle.checked = false
      if (languageSelect) languageSelect.value = ''
      if (cacheInput) cacheInput.value = ''
    }
  }

  updateVisibility()
  enableToggle.addEventListener('change', updateVisibility)
})
