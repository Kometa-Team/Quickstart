// Delegated listeners also cover library/collection fragments loaded lazily.
let directDefaults = { radarr: false, sonarr: false }

export function updateSeerrSwitch (row) {
  const output = row.querySelector('[data-seerr-switch-output]')
  const explicit = row.querySelector('[data-seerr-explicit]')
  const toggle = row.querySelector('[data-seerr-value]')
  if (output && explicit && toggle) output.value = explicit.checked ? String(toggle.checked) : ''
}

export function updateTierOverrides (section) {
  const textarea = section.querySelector('[data-seerr-json]')
  if (!textarea) return
  let overrides
  try {
    overrides = textarea.value.trim() ? JSON.parse(textarea.value) : {}
  } catch {
    return // Retain invalid text so server validation can explain it.
  }
  if (!overrides || Array.isArray(overrides) || typeof overrides !== 'object') return
  section.querySelectorAll('[data-seerr-tier][data-seerr-field]').forEach(input => {
    const tier = input.dataset.seerrTier
    const field = input.dataset.seerrField
    const value = input.value.trim()
    if (!overrides[tier] || typeof overrides[tier] !== 'object') overrides[tier] = {}
    if (!value) delete overrides[tier][field]
    else overrides[tier][field] = (field === 'server_id' || field === 'quality_profile') && /^\d+$/.test(value) ? Number(value) : value
    if (!Object.keys(overrides[tier]).length) delete overrides[tier]
  })
  textarea.value = Object.keys(overrides).length ? JSON.stringify(overrides) : ''
}

function enabled (value) {
  return value === true || value === 'true'
}

function formValue (name) {
  const elements = document.getElementsByName(name)
  for (const element of elements) {
    if (element.type === 'checkbox') return element.checked ? 'true' : 'false'
    if (element.type !== 'hidden' || elements.length === 1) return element.value
  }
  return ''
}

export function updateDuplicateWarning (root) {
  const missing = root.querySelector('[data-seerr-switch-output]')
  const warning = root.querySelector('[data-seerr-duplicate-warning]')
  if (!missing || !warning) return
  const libraryId = missing.name.split('-template')[0]
  const sharedMissing = formValue(`${libraryId}-template_variables[seerr_add_missing]`)
  const existing = root.querySelectorAll('[data-seerr-switch-output]')[1]
  const sharedExisting = formValue(`${libraryId}-template_variables[seerr_add_existing]`)
  const seerrEnabled = enabled(missing.value || sharedMissing) || enabled(existing?.value || sharedExisting)
  const service = libraryId.startsWith('mov-') ? 'radarr' : 'sonarr'
  const collectionValue = formValue(missing.name.replace('seerr_add_missing', `${service}_add_missing`))
  const libraryValue = formValue(`${libraryId}-attribute_${service}_add_missing`)
  const direct = collectionValue || libraryValue || directDefaults[service]
  const keyedRisk = Array.from(root.querySelectorAll('[data-seerr-keyed-output]')).some(input => {
    if (!/seerr_add_(missing|existing)_/.test(input.name) || !enabled(input.value)) return false
    const directKey = formValue(input.name.replace(/seerr_add_(missing|existing)/, `${service}_add_missing`))
    return enabled(directKey || direct)
  })
  warning.hidden = !((seerrEnabled && enabled(direct)) || keyedRisk)
}

export function refreshSeerrWarnings () {
  document.querySelectorAll('[data-seerr-options]').forEach(updateDuplicateWarning)
}

export function handleSeerrInput (event) {
  const target = event.target
  const row = target.closest?.('[data-seerr-switch]')
  if (row && !target.matches('[data-seerr-switch-output]')) updateSeerrSwitch(row)
  const section = target.closest?.('[data-seerr-overrides]')
  if (section && target.matches('[data-seerr-tier]')) updateTierOverrides(section)
  if (section && target.matches('[data-seerr-json]')) {
    try {
      const data = JSON.parse(target.value || '{}')
      section.querySelectorAll('[data-seerr-tier][data-seerr-field]').forEach(input => {
        input.value = data?.[input.dataset.seerrTier]?.[input.dataset.seerrField] ?? ''
      })
    } catch { /* Keep the entered text for server validation. */ }
  }
  if (target.matches?.('[data-seerr-keyed]')) {
    const root = target.closest('[data-seerr-options]')
    const status = root.querySelector('[data-seerr-keyed-error]')
    try {
      const keyed = JSON.parse(target.value || '{}')
      if (!keyed || Array.isArray(keyed) || typeof keyed !== 'object' || Object.keys(keyed).some(key => !/^seerr_(add_missing|add_existing|instance|overrides)_.+$/.test(key))) throw new Error('Invalid keys')
      root.querySelectorAll('[data-seerr-keyed-output]').forEach(input => {
        const key = input.name.slice(target.dataset.seerrPrefix.length, target.dataset.seerrSuffix ? -target.dataset.seerrSuffix.length : undefined)
        if (Object.hasOwn(keyed, key)) input.remove()
        else input.value = '' // Explicitly clear saved values through partial/lazy saves.
      })
      Object.entries(keyed).forEach(([key, value]) => {
        const input = document.createElement('input')
        input.type = 'hidden'
        input.name = target.dataset.seerrPrefix + key + target.dataset.seerrSuffix
        input.dataset.seerrKeyedOutput = ''
        input.value = typeof value === 'object' ? JSON.stringify(value) : String(value)
        root.appendChild(input)
      })
      target.setCustomValidity('')
      if (status) status.textContent = ''
    } catch {
      const message = 'Enter a JSON object containing seerr_add_missing_KEY, seerr_add_existing_KEY, seerr_instance_KEY, or seerr_overrides_KEY.'
      target.setCustomValidity(message)
      if (status) status.textContent = message
    }
  }
  refreshSeerrWarnings()
}

document.addEventListener('input', handleSeerrInput, true)
document.addEventListener('change', handleSeerrInput, true)
document.addEventListener('click', async event => {
  const button = event.target.closest?.('[data-seerr-inherit], [data-seerr-validate]')
  const root = button?.closest('[data-seerr-library]')
  if (!root) return
  const libraryId = root.dataset.seerrLibrary
  const url = document.getElementById(`${libraryId}-attribute_seerr_url`)
  const key = document.getElementById(`${libraryId}-attribute_seerr_apikey`)
  if (button.matches('[data-seerr-inherit]')) {
    for (const input of [url, key]) {
      input.value = ''
      input.dispatchEvent(new Event('input', { bubbles: true }))
    }
    return
  }
  const status = root.querySelector('[data-seerr-status]')
  button.disabled = true
  try {
    const response = await fetch(`/validate_library_seerr/${encodeURIComponent(libraryId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url.value, apikey: key.value })
    })
    const data = await response.json()
    status.textContent = data.valid ? 'Effective Seerr connection validated. No media requests were created.' : data.error
  } catch {
    status.textContent = 'Unable to validate the Seerr connection.'
  } finally {
    button.disabled = false
  }
}, true)

if (document.getElementById('libraryPicker')) {
  fetch('/seerr-context').then(response => response.json()).then(data => {
    directDefaults = data.direct_add_missing || directDefaults
    refreshSeerrWarnings()
  }).catch(() => {})
  new MutationObserver(refreshSeerrWarnings).observe(document.getElementById('library-form-container') || document.body, { childList: true, subtree: true })
}
