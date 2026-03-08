/* global bootstrap, $, location, MutationObserver, requestAnimationFrame, PathValidation, URLValidation */

(function () {
  const isDebug = typeof window.QS_DEBUG !== 'undefined' && String(window.QS_DEBUG).toLowerCase() === 'true'

  function getLocalTimestamp () {
    const now = new Date()
    const yyyy = now.getFullYear()
    const MM = String(now.getMonth() + 1).padStart(2, '0')
    const dd = String(now.getDate()).padStart(2, '0')
    const hh = String(now.getHours()).padStart(2, '0')
    const mm = String(now.getMinutes()).padStart(2, '0')
    const ss = String(now.getSeconds()).padStart(2, '0')
    const ms = String(now.getMilliseconds()).padStart(3, '0')
    return `${yyyy}-${MM}-${dd} ${hh}:${mm}:${ss},${ms}`
  }

  const isVerbose = typeof window.QS_VERBOSE !== 'undefined' && String(window.QS_VERBOSE).toLowerCase() === 'true'

  if (isDebug) {
    if (isVerbose) {
      ['log', 'debug', 'warn', 'error'].forEach((method) => {
        const original = console[method]
        console[method] = function (...args) {
          original.call(console, `[${getLocalTimestamp()}]`, ...args)
        }
      })
    }
  } else {
    // In non-debug mode, keep errors but mute spammy logs
    console.debug = () => { }
    console.log = () => { }
    console.warn = () => { }
    // console.error = () => {} // optionally disable this too
  }
})()

document.addEventListener('DOMContentLoaded', function () {
  // Prevent form submission on "Enter" key press, except for textarea
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && event.target.tagName !== 'TEXTAREA') {
      const form = event.target.closest('form')
      if (form) {
        event.preventDefault() // Prevent form submission
      }
    }
  })
})

document.addEventListener('DOMContentLoaded', function () {
  // Track user-modified <select> fields
  trackModifiedSelects()
})

document.addEventListener('DOMContentLoaded', function () {
  if (typeof PathValidation !== 'undefined' && PathValidation.attach) {
    PathValidation.attach(document)
  }
  if (typeof URLValidation !== 'undefined' && URLValidation.attach) {
    URLValidation.attach(document)
  }
  const saveError = document.getElementById('qs-save-error')
  if (saveError && saveError.dataset && saveError.dataset.message) {
    showToast('error', saveError.dataset.message)
  }
})

// Loading spinner functionality
function loading (action) {
  console.log('action:', action)

  if (action === 'prev' || action === 'next') {
    restoreBlankCacheExpirations()
  }

  let spinnerIcon
  switch (action) {
    case 'prev':
      spinnerIcon = document.getElementById('prev-spinner-icon')
      break
    case 'next':
      spinnerIcon = document.getElementById('next-spinner-icon')
      break
    case 'jump':
      spinnerIcon = null
      break
    default:
      console.error('Unsupported action:', action)
      return
  }

  if (!spinnerIcon && action !== 'jump') {
    console.error('Spinner icon not found for action:', action)
    return
  }

  if (action === 'jump') {
    const jumpLeft = document.querySelector('.jump-to-left')
    if (jumpLeft) {
      jumpLeft.classList.add('is-loading')
    }
    return
  }

  spinnerIcon.classList.remove('fa-arrow-left', 'fa-arrow-right', 'fa-list')
  // spinnerIcon.classList.add('fa-spinner', 'fa-pulse', 'fa-fw');
  spinnerIcon.classList.add('spinner-border', 'spinner-border-sm')
}

function resetNavigationSpinners () {
  const prevIcon = document.getElementById('prev-spinner-icon')
  if (prevIcon) {
    prevIcon.classList.remove('spinner-border', 'spinner-border-sm')
    if (!prevIcon.classList.contains('fa-arrow-left')) {
      prevIcon.classList.add('fa-arrow-left')
    }
  }
  const nextIcon = document.getElementById('next-spinner-icon')
  if (nextIcon) {
    nextIcon.classList.remove('spinner-border', 'spinner-border-sm')
    if (!nextIcon.classList.contains('fa-arrow-right')) {
      nextIcon.classList.add('fa-arrow-right')
    }
  }
  const jumpLeft = document.querySelector('.jump-to-left')
  if (jumpLeft) {
    jumpLeft.classList.remove('is-loading')
  }
}

document.addEventListener('invalid', function () {
  resetNavigationSpinners()
}, true)

document.addEventListener('submit', function (event) {
  setTimeout(() => {
    if (event.defaultPrevented) {
      resetNavigationSpinners()
    }
  }, 0)
})

/* eslint-disable no-unused-vars */
// Function to show the spinner on validate
function showSpinner (webhookType) {
  document.getElementById(`spinner_${webhookType}`).style.display = 'inline-block'
}

// Function to hide the spinner on validate
function hideSpinner (webhookType) {
  document.getElementById(`spinner_${webhookType}`).style.display = 'none'
}

// Function to handle jump to action
function jumpTo (targetPage) {
  console.log('JumpTo initiated for target page:', targetPage)

  restoreBlankCacheExpirations()

  const form = document.getElementById('configForm') || document.getElementById('final-form')
  if (!form) {
    console.error('Form not found')
    return
  }

  if (!form.checkValidity()) {
    console.warn('Form is invalid. Reporting validity.')
    form.reportValidity()
    return
  }

  // Append custom webhook URLs if needed
  $('select.form-select').each(function () {
    if ($(this).val() === 'custom') {
      const customInputId = $(this).attr('id') + '_custom'
      const customUrl = $('#' + customInputId).find('input.custom-webhook-url').val()
      if (customUrl) {
        $(this).append('<option value="' + customUrl + '" selected="selected">' + customUrl + '</option>')
        $(this).val(customUrl)
      }
    }
  })

  // Temporarily change the action and submit the form
  const originalAction = form.action
  form.action = '/step/' + targetPage
  loading('jump') // optional spinner
  form.submit()
  form.action = originalAction // optional restore
}

function escapeHtml (value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function setButtonIconAndText (button, iconClasses, text) {
  if (!button) return
  const icon = document.createElement('i')
  icon.className = iconClasses
  button.replaceChildren(icon, document.createTextNode(` ${text}`))
}

// Function to show toast messages
function showToast (type, message) {
  const toastId = `toast-${Date.now()}` // Unique ID for each toast
  const toastContainer = document.querySelector('.toast-container')
  const safeMessage = escapeHtml(message)

  // Define Bootstrap colors, icons, and progress bar styles per type
  const toastConfig = {
    success: { class: 'text-bg-success', icon: 'bi-check-circle-fill', progress: 'bg-success' },
    error: { class: 'text-bg-danger', icon: 'bi-exclamation-triangle-fill', progress: 'bg-danger' },
    info: { class: 'text-bg-primary', icon: 'bi-info-circle-fill', progress: 'bg-primary' },
    warning: { class: 'text-bg-warning text-dark', icon: 'bi-exclamation-circle-fill', progress: 'bg-warning' },
    default: { class: 'text-bg-secondary', icon: 'bi-chat-left-dots-fill', progress: 'bg-secondary' }
  }

  // Get the settings based on toast type, defaulting to "default"
  const { class: toastTypeClass, icon, progress: progressColor } = toastConfig[type] || toastConfig.default

  // Create toast HTML dynamically
  const toastHTML = `
    <div id="${toastId}" class="toast align-items-center ${toastTypeClass} border-0 shadow-lg" role="alert" aria-live="assertive" aria-atomic="true" data-bs-delay="10000">
      <div class="d-flex">
        <div class="toast-body">
          <i class="bi ${icon} me-2"></i> ${safeMessage}
        </div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
      <div class="progress toast-progress" style="height: 4px;">
        <div class="progress-bar ${progressColor}" role="progressbar" style="width: 100%; transition: width 10s linear;"></div>
      </div>
    </div>`

  // Append toast to the container
  toastContainer.insertAdjacentHTML('beforeend', toastHTML)
  const toastElement = document.getElementById(toastId)

  // Initialize Bootstrap toast
  const toast = new bootstrap.Toast(toastElement, { autohide: true, delay: 10000 })

  // Start progress bar animation when toast shows
  toastElement.addEventListener('shown.bs.toast', () => {
    toastElement.querySelector('.progress-bar').style.width = '0%'
  })

  // Remove toast from DOM when hidden
  toastElement.addEventListener('hidden.bs.toast', () => {
    toastElement.remove()
  })

  // Show the toast
  toast.show()
}

function getValidatedInput () {
  const form = document.getElementById('configForm') || document.getElementById('final-form') || document
  if (!form) return null
  return form.querySelector('input[id$="_validated"]')
}

function updateValidationCallouts (inputId) {
  const callouts = document.querySelectorAll('.qs-validation-accordion')
  if (!callouts.length) return

  callouts.forEach((wrapper) => {
    const targetId = inputId || wrapper.dataset.qsValidatedInput
    const validatedInput = targetId ? document.getElementById(targetId) : getValidatedInput()
    if (!validatedInput) return

    const isValidated = String(validatedInput.value || '').toLowerCase() === 'true'
    const collapse = wrapper.querySelector('.accordion-collapse')
    const button = wrapper.querySelector('.accordion-button')
    if (!collapse || !button) return

    const shouldShow = !isValidated
    button.classList.toggle('collapsed', !shouldShow)
    button.setAttribute('aria-expanded', shouldShow ? 'true' : 'false')

    if (typeof bootstrap !== 'undefined' && bootstrap.Collapse) {
      const instance = bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false })
      if (shouldShow) {
        instance.show()
      } else {
        instance.hide()
      }
    } else {
      collapse.classList.toggle('show', shouldShow)
    }
  })
}

function setupValidationCallouts () {
  const callouts = document.querySelectorAll('.qs-validation-callout')
  if (!callouts.length) return

  callouts.forEach((alert, index) => {
    if (alert.closest('.modal')) return
    if (alert.closest('.qs-validation-accordion')) return

    const validatedInput = getValidatedInput()
    if (!validatedInput) return

    const isValidated = String(validatedInput.value || '').toLowerCase() === 'true'
    const heading = alert.querySelector('h6, h4')
    const title = alert.dataset.qsCalloutTitle || (heading ? heading.textContent.trim() : 'Setup guidance')
    const accordionId = `qs-validation-accordion-${index}`
    const collapseId = `qs-validation-collapse-${index}`
    const headingId = `qs-validation-heading-${index}`

    const wrapper = document.createElement('div')
    wrapper.className = 'accordion qs-validation-accordion mb-2'
    wrapper.dataset.qsValidatedInput = validatedInput.id
    const accordionItem = document.createElement('div')
    accordionItem.className = 'accordion-item'

    const header = document.createElement('h2')
    header.className = 'accordion-header'
    header.id = headingId

    const button = document.createElement('button')
    button.className = `accordion-button ${isValidated ? 'collapsed' : ''}`
    button.type = 'button'
    button.setAttribute('data-bs-toggle', 'collapse')
    button.setAttribute('data-bs-target', `#${collapseId}`)
    button.setAttribute('aria-expanded', isValidated ? 'false' : 'true')
    button.setAttribute('aria-controls', collapseId)
    button.textContent = title

    header.appendChild(button)

    const collapse = document.createElement('div')
    collapse.id = collapseId
    collapse.className = `accordion-collapse collapse ${isValidated ? '' : 'show'}`
    collapse.setAttribute('aria-labelledby', headingId)

    const body = document.createElement('div')
    body.className = 'accordion-body p-0'

    collapse.appendChild(body)
    accordionItem.appendChild(header)
    accordionItem.appendChild(collapse)
    wrapper.appendChild(accordionItem)

    const parent = alert.parentNode
    parent.insertBefore(wrapper, alert)
    body.appendChild(alert)
    alert.classList.add('mb-0')
  })
}

const CACHE_EXPIRATION_FIELDS = [
  { id: 'tmdb_cache_expiration', label: 'TMDb cache expiration' },
  { id: 'omdb_cache_expiration', label: 'OMDb cache expiration' },
  { id: 'mdblist_cache_expiration', label: 'MDBList cache expiration' },
  { id: 'anidb_cache_expiration', label: 'AniDB cache expiration' },
  { id: 'mal_cache_expiration', label: 'MyAnimeList cache expiration' },
  { id: 'cache_expiration', label: 'Cache expiration' },
  { id: 'plex_db_cache', label: 'Plex cache size' },
  { id: 'plex_timeout', label: 'Plex timeout' }
]

function restoreBlankCacheExpirations () {
  const restored = []
  const isNumericValue = (value) => {
    if (value === null || value === undefined) return false
    const trimmed = String(value).trim()
    if (trimmed === '') return false
    return Number.isFinite(Number(trimmed))
  }

  CACHE_EXPIRATION_FIELDS.forEach(({ id, label }) => {
    const input = document.getElementById(id)
    if (!input) return

    const currentValue = String(input.value || '').trim()
    if (currentValue !== '') return

    const fallbackValue = String(input.dataset.defaultValue || input.defaultValue || '').trim()
    let restoreValue = null
    let reason = 'default'

    if (isNumericValue(fallbackValue)) {
      restoreValue = fallbackValue
    } else {
      const minValue = input.getAttribute('min')
      if (isNumericValue(minValue)) {
        restoreValue = String(minValue).trim()
        reason = 'minimum'
      }
    }

    if (!restoreValue) return

    input.value = restoreValue
    restored.push({ label, value: restoreValue, reason })
  })

  if (restored.length && typeof showToast === 'function') {
    const message = restored
      .map(item => (
        item.reason === 'minimum'
          ? `${item.label} was blank. Set to minimum: ${item.value}.`
          : `${item.label} was blank. Restored to default: ${item.value}.`
      ))
      .join('<br>')
    showToast('info', message)
  }
}

document.addEventListener('DOMContentLoaded', () => {
  setupValidationCallouts()
})

window.QSValidationCallouts = {
  refresh: updateValidationCallouts,
  setup: setupValidationCallouts
}

document.addEventListener('DOMContentLoaded', () => {
  const notice = window.QS_RESTART_NOTICE
  if (!notice || notice.reason !== 'update') return

  const noticeKey = `qs_restart_notice_${notice.reason}_${notice.created_at || ''}`
  try {
    if (window.localStorage && window.localStorage.getItem(noticeKey)) return
    if (window.localStorage) window.localStorage.setItem(noticeKey, '1')
  } catch (err) {
    // Ignore localStorage failures (private mode, etc.)
  }

  const message = notice.message || 'Update complete. Quickstart restarted successfully.'
  showToast('success', message)
})

// Mark all <select> elements when changed, so we can tell if a user modified them
function trackModifiedSelects () {
  document.querySelectorAll('select').forEach(select => {
    select.addEventListener('change', (event) => {
      if (event && event.isTrusted === false) return
      select.setAttribute('data-user-modified', 'true')
    })
  })
}

function restartQuickstart (reason) {
  const payload = (typeof reason === 'string' && reason.trim()) ? { reason: reason.trim() } : null
  const options = { method: 'POST' }
  if (payload) {
    options.headers = { 'Content-Type': 'application/json' }
    options.body = JSON.stringify(payload)
  }
  fetch('/restart', options)
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        // Disable the restart button immediately
        const restartBtn = document.querySelector('#updateResult button')
        if (restartBtn) restartBtn.disabled = true

        const updateResult = document.getElementById('updateResult')
        if (updateResult) {
          const message = data.message || 'Update complete. Quickstart restarted successfully.'
          const strong = document.createElement('strong')
          strong.textContent = `🚀 ${message}`
          updateResult.replaceChildren(
            strong,
            document.createElement('br'),
            document.createTextNode('Please wait while Quickstart restarts... this page will auto-reload shortly.')
          )
        }
        setTimeout(() => location.reload(), 6000)
      } else {
        showToast('error', data.message || 'Restart failed.')
      }
    })
    .catch(err => {
      showToast('error', `Restart error: ${err.message}`)
    })
}

/* eslint-enable no-unused-vars */
document.addEventListener('DOMContentLoaded', () => {
  const updateBtn = document.getElementById('updateQuickstartBtn')
  const resultBox = document.getElementById('updateResult')

  if (updateBtn && resultBox) {
    updateBtn.addEventListener('click', async () => {
      if (updateBtn.dataset.state === 'ready-restart') {
        restartQuickstart('update')
        return
      }
      updateBtn.disabled = true
      setButtonIconAndText(updateBtn, 'bi bi-arrow-repeat spin', 'Updating...')
      updateBtn.dataset.originalClasses = updateBtn.className
      updateBtn.classList.remove('btn-warning')
      updateBtn.classList.add('btn-secondary')

      const branch = updateBtn.dataset.branch || 'master'
      let updateSucceeded = false

      try {
        const res = await fetch('/update-quickstart', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ branch })
        })
        const data = await res.json()

        resultBox.classList.remove('d-none')
        resultBox.classList.add('border', 'rounded', 'bg-body-tertiary', 'p-3', 'text-light')

        const lines = Array.isArray(data.log) ? data.log.filter(Boolean).map(String) : []

        if (data.success) {
          updateSucceeded = true
          const branchLabel = data.branch || branch
          const successStrong = document.createElement('strong')
          successStrong.textContent = '✅ Update Successful!'
          const branchSpan = document.createElement('span')
          branchSpan.className = 'text-info'
          const branchCode = document.createElement('code')
          branchCode.textContent = branchLabel
          branchSpan.append('Branch: ', branchCode)
          const successPre = document.createElement('pre')
          successPre.className = 'form-control bg-dark text-light'
          successPre.style.height = '300px'
          successPre.style.overflowY = 'auto'
          successPre.style.overflowX = 'auto'
          successPre.style.whiteSpace = 'pre'
          successPre.textContent = lines.join('\n')
          resultBox.replaceChildren(successStrong, document.createElement('br'), branchSpan, successPre)
        } else {
          const errorMessage = data.error || 'Update failed'
          const errorStrong = document.createElement('strong')
          errorStrong.textContent = '❌ Error:'
          const errorPre = document.createElement('pre')
          errorPre.className = 'form-control bg-dark text-light'
          errorPre.style.height = '300px'
          errorPre.style.overflowY = 'auto'
          errorPre.style.overflowX = 'auto'
          errorPre.style.whiteSpace = 'pre'
          errorPre.textContent = lines.join('\n')
          resultBox.replaceChildren(
            errorStrong,
            document.createTextNode(` ${errorMessage}`),
            document.createElement('br'),
            errorPre
          )
        }
      } catch (err) {
        resultBox.classList.remove('d-none')
        const errorStrong = document.createElement('strong')
        errorStrong.textContent = '❌ Request Failed:'
        resultBox.replaceChildren(errorStrong, document.createTextNode(` ${String(err)}`))
      } finally {
        if (updateSucceeded) {
          updateBtn.disabled = false
          updateBtn.dataset.state = 'ready-restart'
          updateBtn.classList.remove('btn-secondary')
          updateBtn.classList.add('btn-success')
          setButtonIconAndText(updateBtn, 'bi bi-arrow-repeat', 'Restart Quickstart')
        } else {
          updateBtn.disabled = false
          setButtonIconAndText(updateBtn, 'bi bi-arrow-clockwise', 'Run Update Now')
          if (updateBtn.dataset.originalClasses) {
            updateBtn.className = updateBtn.dataset.originalClasses
            delete updateBtn.dataset.originalClasses
          }
        }
      }
    })
  }
})

document.addEventListener('DOMContentLoaded', () => {
  const modalEl = document.getElementById('configSwitchModal')
  if (!modalEl) return

  const select = modalEl.querySelector('#configSwitchSelect')
  const confirmBtn = modalEl.querySelector('#configSwitchConfirm')
  const badgeBtn = document.querySelector('.config-badge-button')

  function getCurrentConfig () {
    return badgeBtn?.dataset.current || ''
  }

  if (select) {
    modalEl.addEventListener('show.bs.modal', () => {
      const current = getCurrentConfig()
      if (current) select.value = current
    })
  }

  if (confirmBtn && select) {
    confirmBtn.addEventListener('click', async () => {
      const target = select.value
      const current = getCurrentConfig()
      if (!target || target === current) {
        const modal = bootstrap.Modal.getInstance(modalEl)
        if (modal) modal.hide()
        return
      }

      confirmBtn.disabled = true
      confirmBtn.textContent = 'Switching...'
      window.QS_SWITCHING_CONFIG = true

      try {
        const res = await fetch('/switch-config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: target })
        })
        const data = await res.json()
        if (!res.ok || !data.success) {
          throw new Error(data.message || 'Failed to switch configs.')
        }
        showToast('success', `Switched to config "${data.name}".`)
        setTimeout(() => window.location.reload(), 150)
      } catch (err) {
        window.QS_SWITCHING_CONFIG = false
        confirmBtn.disabled = false
        confirmBtn.textContent = 'Switch'
        showToast('error', err.message || 'Failed to switch configs.')
      }
    })
  }
})

document.addEventListener('DOMContentLoaded', () => {
  const modalEl = document.getElementById('quickstartSettingsModal')
  if (!modalEl) return

  const portInput = document.getElementById('quickstart-settings-port')
  const debugInput = document.getElementById('quickstart-settings-debug')
  const themeInput = document.getElementById('quickstart-settings-theme')
  const themeButton = document.getElementById('quickstart-settings-theme-btn')
  const optimizeInput = document.getElementById('quickstart-settings-optimize')
  const historyInput = document.getElementById('quickstart-settings-config-history')
  const logKeepInput = document.getElementById('quickstart-settings-log-keep')
  const testLibsTmpInput = document.getElementById('quickstart-settings-test-libs-tmp')
  const testLibsPathInput = document.getElementById('quickstart-settings-test-libs-path')
  const sessionLifetimeInput = document.getElementById('quickstart-settings-session-lifetime')
  const sessionDirInput = document.getElementById('quickstart-settings-session-dir')
  const secretRegenBtn = document.getElementById('quickstart-settings-secret-regen')
  const themeText = modalEl.querySelector('.theme-picker-text')
  const themeSwatch = modalEl.querySelector('[data-theme-swatch]')
  const themeOptions = modalEl.querySelectorAll('.theme-option')
  const applyBtn = document.getElementById('quickstart-settings-apply')
  const statusEl = document.getElementById('quickstart-settings-status')
  const triggerBtn = document.getElementById('quickstart-settings-btn')

  function setStatus (text, isError) {
    if (!statusEl) return
    statusEl.textContent = text || ''
    statusEl.classList.toggle('text-danger', Boolean(isError))
    statusEl.classList.toggle('text-muted', !isError)
  }

  function getCurrentPort () {
    if (triggerBtn && triggerBtn.dataset.currentPort) return triggerBtn.dataset.currentPort
    return window.QS_PORT || ''
  }

  function getCurrentDebug () {
    const raw = (triggerBtn && triggerBtn.dataset.currentDebug) ? triggerBtn.dataset.currentDebug : window.QS_DEBUG
    return String(raw).toLowerCase() === 'true'
  }

  function getCurrentTheme () {
    if (triggerBtn && triggerBtn.dataset.currentTheme) return triggerBtn.dataset.currentTheme
    return window.QS_THEME || 'kometa'
  }

  function getCurrentOptimizeDefaults () {
    const raw = (triggerBtn && triggerBtn.dataset.currentOptimizeDefaults)
      ? triggerBtn.dataset.currentOptimizeDefaults
      : window.QS_OPTIMIZE_DEFAULTS
    return String(raw).toLowerCase() === 'true'
  }

  function getCurrentConfigHistory () {
    const raw = (triggerBtn && triggerBtn.dataset.currentConfigHistory)
      ? triggerBtn.dataset.currentConfigHistory
      : window.QS_CONFIG_HISTORY
    const parsed = Number.parseInt(raw, 10)
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0
  }

  function getCurrentLogKeep () {
    const raw = (triggerBtn && triggerBtn.dataset.currentLogKeep)
      ? triggerBtn.dataset.currentLogKeep
      : window.QS_KOMETA_LOG_KEEP
    const parsed = Number.parseInt(raw, 10)
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0
  }

  function getCurrentTestLibsTmp () {
    if (triggerBtn && triggerBtn.dataset.currentTestLibsTmp) return triggerBtn.dataset.currentTestLibsTmp
    return window.QS_TEST_LIBS_TMP || ''
  }

  function getCurrentTestLibsPath () {
    if (triggerBtn && triggerBtn.dataset.currentTestLibsPath) return triggerBtn.dataset.currentTestLibsPath
    return window.QS_TEST_LIBS_PATH || ''
  }

  function getCurrentSessionLifetimeDays () {
    const raw = (triggerBtn && triggerBtn.dataset.currentSessionLifetime)
      ? triggerBtn.dataset.currentSessionLifetime
      : window.QS_SESSION_LIFETIME_DAYS
    const parsed = Number.parseInt(raw, 10)
    return Number.isFinite(parsed) && parsed >= 1 ? parsed : 30
  }

  function getCurrentSessionDir () {
    if (triggerBtn && triggerBtn.dataset.currentSessionDir) return triggerBtn.dataset.currentSessionDir
    return window.QS_FLASK_SESSION_DIR || ''
  }

  function getQuickstartRoot () {
    if (triggerBtn && triggerBtn.dataset.quickstartRoot) return triggerBtn.dataset.quickstartRoot
    return window.QS_APP_ROOT || ''
  }

  function getThemeLabel (themeValue) {
    const option = modalEl.querySelector(`.theme-option[data-theme="${themeValue}"]`)
    return option?.dataset?.label || themeValue
  }

  function updateThemeUi (themeValue) {
    const value = themeValue || 'kometa'
    if (themeInput) themeInput.value = value
    if (themeText) themeText.textContent = getThemeLabel(value)
    if (themeSwatch) {
      const baseClass = 'theme-swatch'
      themeSwatch.className = `${baseClass} theme-swatch--${value}`
    }
    if (themeOptions.length) {
      themeOptions.forEach(option => {
        option.classList.toggle('active', option.dataset.theme === value)
      })
    }
  }

  if (themeOptions.length && themeButton) {
    themeOptions.forEach(option => {
      option.addEventListener('click', () => {
        const value = option.dataset.theme || 'kometa'
        updateThemeUi(value)
        const dropdown = bootstrap.Dropdown.getOrCreateInstance(themeButton)
        dropdown.hide()
      })
    })
  }

  modalEl.addEventListener('show.bs.modal', () => {
    if (portInput) portInput.value = getCurrentPort()
    if (debugInput) debugInput.checked = getCurrentDebug()
    if (optimizeInput) optimizeInput.checked = getCurrentOptimizeDefaults()
    if (historyInput) historyInput.value = getCurrentConfigHistory()
    if (logKeepInput) logKeepInput.value = getCurrentLogKeep()
    if (testLibsTmpInput) testLibsTmpInput.value = getCurrentTestLibsTmp()
    if (testLibsPathInput) testLibsPathInput.value = getCurrentTestLibsPath()
    if (sessionLifetimeInput) sessionLifetimeInput.value = getCurrentSessionLifetimeDays()
    if (sessionDirInput) sessionDirInput.value = getCurrentSessionDir()
    updateThemeUi(getCurrentTheme())
    setStatus('', false)
    if (applyBtn) applyBtn.disabled = false
  })

  async function saveTestLibraryPaths (confirmOverride = false) {
    const quickstartRoot = getQuickstartRoot()
    if (!quickstartRoot) {
      throw new Error('Quickstart root not available.')
    }

    if (typeof PathValidation !== 'undefined' && PathValidation.validateAll) {
      const validPaths = PathValidation.validateAll(modalEl)
      if (!validPaths) {
        throw new Error('Please fix invalid path fields before saving.')
      }
    }

    const payload = {
      quickstart_root: quickstartRoot,
      temp_path: testLibsTmpInput ? testLibsTmpInput.value.trim() : '',
      final_path: testLibsPathInput ? testLibsPathInput.value.trim() : '',
      confirm: confirmOverride
    }

    const res = await fetch('/test-libraries-settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    const data = await res.json()

    if (!res.ok && data && data.needs_confirm) {
      const proceed = window.confirm(`${data.message || 'Confirm test library path update.'}\n\nContinue anyway?`)
      if (!proceed) {
        return { skipped: true }
      }
      return await saveTestLibraryPaths(true)
    }

    if (!res.ok || !data.success) {
      throw new Error(data.message || 'Failed to save test library paths.')
    }

    if (triggerBtn) {
      if (data.final_path) triggerBtn.dataset.currentTestLibsPath = data.final_path
      if (data.temp_path) triggerBtn.dataset.currentTestLibsTmp = data.temp_path
    }
    if (typeof data.final_path === 'string') window.QS_TEST_LIBS_PATH = data.final_path
    if (typeof data.temp_path === 'string') window.QS_TEST_LIBS_TMP = data.temp_path
    if (testLibsTmpInput && data.temp_path) testLibsTmpInput.value = data.temp_path
    if (testLibsPathInput && data.final_path) testLibsPathInput.value = data.final_path
    return data
  }

  if (applyBtn) {
    applyBtn.addEventListener('click', async () => {
      const payload = {}
      let portNum = null
      let hasPortChange = false
      const currentOptimize = getCurrentOptimizeDefaults()
      const desiredOptimize = optimizeInput ? optimizeInput.checked : currentOptimize
      const hasOptimizeChange = optimizeInput ? desiredOptimize !== currentOptimize : false
      const currentHistory = getCurrentConfigHistory()
      let desiredHistory = currentHistory
      const currentLogKeep = getCurrentLogKeep()
      let desiredLogKeep = currentLogKeep
      const currentSessionLifetime = getCurrentSessionLifetimeDays()
      const currentSessionDir = getCurrentSessionDir()
      if (historyInput) {
        const rawHistory = historyInput.value.trim()
        if (!/^\d+$/.test(rawHistory)) {
          setStatus('Config history must be a non-negative number.', true)
          return
        }
        desiredHistory = Number(rawHistory)
        if (desiredHistory < 0) {
          setStatus('Config history must be a non-negative number.', true)
          return
        }
        if (desiredHistory !== currentHistory) {
          payload.config_history = desiredHistory
        }
      }
      if (logKeepInput) {
        const rawLogKeep = logKeepInput.value.trim()
        if (!/^\d+$/.test(rawLogKeep)) {
          setStatus('Kometa log retention must be a non-negative number.', true)
          return
        }
        desiredLogKeep = Number(rawLogKeep)
        if (desiredLogKeep < 0) {
          setStatus('Kometa log retention must be a non-negative number.', true)
          return
        }
        if (desiredLogKeep !== currentLogKeep) {
          payload.kometa_log_keep = desiredLogKeep
        }
      }
      if (sessionLifetimeInput) {
        const rawSessionLifetime = sessionLifetimeInput.value.trim()
        if (!/^\d+$/.test(rawSessionLifetime)) {
          setStatus('Session lifetime must be a positive number of days.', true)
          return
        }
        const desiredSessionLifetime = Number(rawSessionLifetime)
        if (desiredSessionLifetime < 1) {
          setStatus('Session lifetime must be at least 1 day.', true)
          return
        }
        if (desiredSessionLifetime !== currentSessionLifetime) {
          payload.session_lifetime_days = desiredSessionLifetime
        }
      }
      if (sessionDirInput) {
        const desiredSessionDir = sessionDirInput.value.trim()
        if (desiredSessionDir !== currentSessionDir) {
          payload.session_dir = desiredSessionDir
        }
      }
      if (portInput) {
        const portValue = portInput.value.trim()
        if (!/^\d+$/.test(portValue)) {
          setStatus('Port must be a number between 1 and 65535.', true)
          return
        }
        portNum = Number(portValue)
        if (portNum < 1 || portNum > 65535) {
          setStatus('Port must be a number between 1 and 65535.', true)
          return
        }
        if (String(portNum) !== String(getCurrentPort())) {
          payload.port = portNum
          hasPortChange = true
        }
      }

      if (debugInput) payload.debug = debugInput.checked
      if (optimizeInput) payload.optimize_defaults = desiredOptimize
      if (themeInput) payload.theme = themeInput.value

      applyBtn.disabled = true
      setStatus('Saving settings...', false)

      try {
        const desiredTmp = testLibsTmpInput ? testLibsTmpInput.value.trim() : ''
        const desiredPath = testLibsPathInput ? testLibsPathInput.value.trim() : ''
        const currentTmp = getCurrentTestLibsTmp()
        const currentPath = getCurrentTestLibsPath()
        const hasTestLibChange = (testLibsTmpInput || testLibsPathInput)
          ? (desiredTmp !== currentTmp || desiredPath !== currentPath)
          : false

        let testLibsResult = null
        if (hasTestLibChange) {
          setStatus('Saving test library paths...', false)
          testLibsResult = await saveTestLibraryPaths(false)
          if (testLibsResult && testLibsResult.skipped) {
            showToast('info', 'Test library path update skipped.')
          } else {
            showToast('success', 'Test library paths saved.')
          }
        }

        if (!Object.keys(payload).length) {
          if (hasTestLibChange && !testLibsResult?.skipped) {
            setStatus('Settings updated.', false)
            applyBtn.disabled = false
            const modal = bootstrap.Modal.getInstance(modalEl)
            if (modal) modal.hide()
            return
          }
          if (hasTestLibChange && testLibsResult?.skipped) {
            setStatus('No changes applied.', false)
            applyBtn.disabled = false
            return
          }
        }

        if (!Object.keys(payload).length) {
          setStatus('No changes applied.', false)
          applyBtn.disabled = false
          return
        }

        const res = await fetch('/update-quickstart-settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
        const data = await res.json()
        if (!res.ok || !data.success) {
          throw new Error(data.message || 'Failed to update settings.')
        }

        if (!data.restart) {
          if (data.theme) {
            document.documentElement.setAttribute('data-theme', data.theme)
            window.QS_THEME = data.theme
            if (triggerBtn) triggerBtn.dataset.currentTheme = data.theme
            updateThemeUi(data.theme)
          }
          if (typeof payload.debug !== 'undefined') {
            const debugFlag = Boolean(payload.debug)
            window.QS_DEBUG = debugFlag
            if (triggerBtn) triggerBtn.dataset.currentDebug = debugFlag ? 'true' : 'false'
          }
          if (typeof payload.optimize_defaults !== 'undefined') {
            const optimizeFlag = Boolean(payload.optimize_defaults)
            window.QS_OPTIMIZE_DEFAULTS = optimizeFlag
            if (triggerBtn) triggerBtn.dataset.currentOptimizeDefaults = optimizeFlag ? 'true' : 'false'
          }
          if (typeof payload.config_history !== 'undefined') {
            const historyFlag = Number(payload.config_history)
            window.QS_CONFIG_HISTORY = historyFlag
            if (triggerBtn) triggerBtn.dataset.currentConfigHistory = String(historyFlag)
          }
          if (typeof payload.kometa_log_keep !== 'undefined') {
            const logKeepFlag = Number(payload.kometa_log_keep)
            window.QS_KOMETA_LOG_KEEP = logKeepFlag
            if (triggerBtn) triggerBtn.dataset.currentLogKeep = String(logKeepFlag)
          }
          if (typeof data.session_lifetime_days !== 'undefined' || typeof payload.session_lifetime_days !== 'undefined') {
            const lifetimeFlag = Number(
              (typeof data.session_lifetime_days !== 'undefined') ? data.session_lifetime_days : payload.session_lifetime_days
            )
            window.QS_SESSION_LIFETIME_DAYS = lifetimeFlag
            if (triggerBtn) triggerBtn.dataset.currentSessionLifetime = String(lifetimeFlag)
          }
          if (typeof data.session_dir !== 'undefined' || typeof payload.session_dir !== 'undefined') {
            const sessionDirFlag = String(
              (typeof data.session_dir !== 'undefined') ? data.session_dir : (payload.session_dir || '')
            )
            window.QS_FLASK_SESSION_DIR = sessionDirFlag
            if (triggerBtn) triggerBtn.dataset.currentSessionDir = sessionDirFlag
          }
          if (hasPortChange && triggerBtn) {
            triggerBtn.dataset.currentPort = String(portNum)
          }
          setStatus(data.message || 'Settings updated.', false)
          showToast('success', data.message || 'Settings updated.')
          applyBtn.disabled = false
          const modal = bootstrap.Modal.getInstance(modalEl)
          if (modal) modal.hide()
          const isFinalPage = Boolean(document.getElementById('final-yaml'))
          if (isFinalPage && hasOptimizeChange) {
            setStatus('Refreshing final config...', false)
            const configForm = document.getElementById('configForm')
            if (configForm) {
              configForm.submit()
              return
            }
            setTimeout(() => window.location.reload(), 250)
            return
          }
          return
        }

        setStatus('Restarting Quickstart...', false)
        showToast('info', 'Restarting Quickstart...')
        await fetch('/restart', { method: 'POST' })

        if (data.theme) {
          document.documentElement.setAttribute('data-theme', data.theme)
          window.QS_THEME = data.theme
          if (triggerBtn) triggerBtn.dataset.currentTheme = data.theme
          updateThemeUi(data.theme)
        }
        if (typeof payload.config_history !== 'undefined') {
          const historyFlag = Number(payload.config_history)
          window.QS_CONFIG_HISTORY = historyFlag
          if (triggerBtn) triggerBtn.dataset.currentConfigHistory = String(historyFlag)
        }
        if (typeof payload.kometa_log_keep !== 'undefined') {
          const logKeepFlag = Number(payload.kometa_log_keep)
          window.QS_KOMETA_LOG_KEEP = logKeepFlag
          if (triggerBtn) triggerBtn.dataset.currentLogKeep = String(logKeepFlag)
        }
        if (typeof data.session_lifetime_days !== 'undefined' || typeof payload.session_lifetime_days !== 'undefined') {
          const lifetimeFlag = Number(
            (typeof data.session_lifetime_days !== 'undefined') ? data.session_lifetime_days : payload.session_lifetime_days
          )
          window.QS_SESSION_LIFETIME_DAYS = lifetimeFlag
          if (triggerBtn) triggerBtn.dataset.currentSessionLifetime = String(lifetimeFlag)
        }
        if (typeof data.session_dir !== 'undefined' || typeof payload.session_dir !== 'undefined') {
          const sessionDirFlag = String(
            (typeof data.session_dir !== 'undefined') ? data.session_dir : (payload.session_dir || '')
          )
          window.QS_FLASK_SESSION_DIR = sessionDirFlag
          if (triggerBtn) triggerBtn.dataset.currentSessionDir = sessionDirFlag
        }
        const rawPort = data.new_port ?? portNum ?? getCurrentPort()
        const parsedPort = Number(rawPort)
        const safePort = Number.isInteger(parsedPort) && parsedPort >= 1 && parsedPort <= 65535
          ? parsedPort
          : null
        setTimeout(() => {
          if (safePort) {
            window.location.port = String(safePort)
          } else {
            window.location.reload()
          }
        }, 4000)
      } catch (err) {
        setStatus(err.message || 'Failed to update settings.', true)
        showToast('error', err.message || 'Failed to update settings.')
        applyBtn.disabled = false
      }
    })
  }

  if (secretRegenBtn) {
    secretRegenBtn.addEventListener('click', async () => {
      const proceed = window.confirm('Regenerate the secret key? This will invalidate all active sessions.')
      if (!proceed) return
      secretRegenBtn.disabled = true
      const originalText = secretRegenBtn.textContent
      secretRegenBtn.textContent = 'Regenerating...'
      try {
        const res = await fetch('/update-quickstart-settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ regenerate_secret: true })
        })
        const data = await res.json()
        if (!res.ok || !data.success) {
          throw new Error(data.message || 'Failed to regenerate secret key.')
        }
        showToast('success', data.message || 'Secret key regenerated.')
      } catch (err) {
        showToast('error', err.message || 'Failed to regenerate secret key.')
      } finally {
        secretRegenBtn.disabled = false
        secretRegenBtn.textContent = originalText
      }
    })
  }
})

document.addEventListener('DOMContentLoaded', () => {
  const searchInput = document.querySelector('[data-qs-search-input]')
  if (!searchInput) return

  const searchWrapper = searchInput.closest('[data-qs-search-scope]')
  const searchScopeId = searchWrapper?.dataset?.qsSearchScope
  const searchClear = document.querySelector('[data-qs-search-clear]')
  const searchStatus = document.querySelector('[data-qs-search-status]')
  const scopedContainer = searchScopeId ? document.getElementById(searchScopeId) : null
  const container = scopedContainer || document.getElementById('configForm') || document.body
  const selectorList = ['.accordion-item', '.card', '.template-toggle-group']
  let targets = []
  let targetData = []
  let refreshTimer = null
  let lastQuery = ''

  function normalizeText (value) {
    return String(value || '').toLowerCase().replace(/\s+/g, ' ').trim()
  }

  function refreshTargets () {
    const rawTargets = Array.from(container.querySelectorAll(selectorList.join(',')))
      .filter(element => !element.closest('.modal'))
      .filter(element => !element.closest('.page-search'))

    targets = rawTargets.filter(element => {
      if (element.classList.contains('template-toggle-group')) return true
      if (element.classList.contains('accordion-item')) {
        return !element.querySelector('.accordion-item') && !element.querySelector('.template-toggle-group')
      }
      if (element.classList.contains('card')) {
        return !element.querySelector('.accordion-item') && !element.querySelector('.template-toggle-group')
      }
      return true
    })

    targetData = targets.map(element => ({
      element,
      text: normalizeText(element.textContent)
    }))
  }

  function toggleAccordionParentControl (disable) {
    const collapseEls = container.querySelectorAll('.accordion-collapse')
    collapseEls.forEach(collapseEl => {
      if (disable) {
        if (collapseEl.hasAttribute('data-bs-parent')) {
          collapseEl.dataset.qsParent = collapseEl.getAttribute('data-bs-parent')
          collapseEl.removeAttribute('data-bs-parent')
        }
        return
      }
      if (collapseEl.dataset.qsParent) {
        collapseEl.setAttribute('data-bs-parent', collapseEl.dataset.qsParent)
        delete collapseEl.dataset.qsParent
      }
    })
  }

  function setStatus (visibleCount, totalCount, query) {
    if (!searchStatus) return
    if (!query) {
      searchStatus.textContent = ''
      return
    }
    searchStatus.textContent = `matches (${visibleCount})`
  }

  function applySearch () {
    const query = normalizeText(searchInput.value)
    let visibleCount = 0
    let firstMatch = null
    const hasQuery = Boolean(query)

    toggleAccordionParentControl(hasQuery)

    targetData.forEach(({ element, text }) => {
      const match = !query || text.includes(query)
      element.classList.toggle('qs-search-hidden', !match)
      element.classList.toggle('qs-search-match', Boolean(query && match))
      if (match) visibleCount += 1
      if (match && query) {
        if (!firstMatch) firstMatch = element
        expandAccordionFor(element)
      }
    })

    if (searchClear) searchClear.classList.toggle('d-none', !query)
    setStatus(visibleCount, targetData.length, query)

    if (query && query !== lastQuery && firstMatch && firstMatch.scrollIntoView) {
      firstMatch.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    lastQuery = query
  }

  function expandAccordionFor (element) {
    const collapseEls = new Set()

    if (element.classList.contains('accordion-item')) {
      const collapseEl = element.querySelector('.accordion-collapse')
      if (collapseEl) collapseEls.add(collapseEl)
    }

    if (element.classList.contains('accordion-collapse')) {
      collapseEls.add(element)
    }

    const parentItem = element.closest('.accordion-item')
    const parentCollapse = element.closest('.accordion-collapse')
    if (parentItem) {
      const collapseEl = parentItem.querySelector('.accordion-collapse')
      if (collapseEl) collapseEls.add(collapseEl)
    }
    if (parentCollapse) collapseEls.add(parentCollapse)

    let ancestor = element.parentElement
    while (ancestor) {
      if (ancestor.classList && ancestor.classList.contains('accordion-collapse')) {
        collapseEls.add(ancestor)
      }
      ancestor = ancestor.parentElement
    }

    if (!collapseEls.size) return

    collapseEls.forEach(collapseEl => {
      if (collapseEl.classList.contains('show')) return
      if (!window.bootstrap || !window.bootstrap.Collapse) {
        collapseEl.classList.add('show')
        return
      }
      const collapse = bootstrap.Collapse.getOrCreateInstance(collapseEl, { toggle: false })
      collapse.show()
    })
  }

  searchInput.addEventListener('input', applySearch)
  searchInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') event.preventDefault()
  })

  if (searchClear) {
    searchClear.addEventListener('click', () => {
      searchInput.value = ''
      searchInput.focus()
      applySearch()
    })
  }

  refreshTargets()
  applySearch()

  const observer = new MutationObserver(() => {
    if (refreshTimer) return
    refreshTimer = setTimeout(() => {
      refreshTimer = null
      refreshTargets()
      applySearch()
    }, 150)
  })

  observer.observe(container, { childList: true, subtree: true })
})

document.addEventListener('DOMContentLoaded', () => {
  const confirmShutdownButton = document.getElementById('confirmShutdownButton')
  if (!confirmShutdownButton) return

  const shutdownModalEl = document.getElementById('shutdownModal')
  const shutdownCancelButton = document.getElementById('shutdownCancelButton')

  confirmShutdownButton.addEventListener('click', async () => {
    const modal = shutdownModalEl ? bootstrap.Modal.getInstance(shutdownModalEl) : null
    confirmShutdownButton.disabled = true
    const originalText = confirmShutdownButton.textContent
    confirmShutdownButton.textContent = 'Shutting down...'

    try {
      const res = await fetch('/shutdown', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nonce: confirmShutdownButton.dataset.shutdownNonce || window.pageInfo?.shutdown_nonce,
          confirmed: true
        })
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok || !data.success) throw new Error(data.message || 'Shutdown request failed.')
      if (modal) modal.hide()
      showToast('info', data.message || 'Shutting down Quickstart...')
    } catch (err) {
      confirmShutdownButton.disabled = false
      confirmShutdownButton.textContent = originalText
      showToast('error', err.message || 'Failed to shut down Quickstart.')
    }
  })

  if (shutdownModalEl && shutdownCancelButton) {
    shutdownModalEl.addEventListener('shown.bs.modal', () => {
      shutdownCancelButton.focus()
    })
  }
})

document.addEventListener('DOMContentLoaded', () => {
  const modalEl = document.getElementById('supportInfoModal')
  if (!modalEl) return

  const output = modalEl.querySelector('#supportInfoOutput')
  const refreshBtn = modalEl.querySelector('#supportInfoRefresh')
  const copyBtn = modalEl.querySelector('#supportInfoCopy')
  const status = modalEl.querySelector('#supportInfoStatus')
  const isSecureContext = window.isSecureContext

  function setStatus (text, isError) {
    if (!status) return
    status.textContent = text || ''
    status.classList.toggle('text-danger', Boolean(isError))
    status.classList.toggle('text-muted', !isError)
  }

  if (copyBtn && !isSecureContext) {
    copyBtn.textContent = 'Select'
  }

  async function loadSupportInfo () {
    if (!output) return
    if (copyBtn) copyBtn.disabled = true
    setStatus('Loading...', false)
    output.textContent = 'Loading support info...'

    try {
      const res = await fetch('/support-info')
      const data = await res.json()
      if (!res.ok || !data || !data.text) {
        throw new Error((data && data.error) || 'Failed to load support info.')
      }
      output.textContent = data.text
      setStatus(data.generated_at ? `Updated ${data.generated_at}` : 'Updated', false)
      if (copyBtn) copyBtn.disabled = !data.text.trim()
    } catch (err) {
      output.textContent = `Unable to load support info.\n${err.message || String(err)}`
      setStatus('Error loading support info', true)
      if (copyBtn) copyBtn.disabled = true
    }
  }

  function fallbackCopy (text, opts = {}) {
    const showFailureToast = opts.showFailureToast !== false
    const showSuccessToast = opts.showSuccessToast !== false
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'absolute'
    textarea.style.left = '-9999px'
    document.body.appendChild(textarea)
    textarea.focus()
    textarea.select()
    textarea.setSelectionRange(0, textarea.value.length)
    try {
      const success = document.execCommand('copy')
      if (success) {
        if (showSuccessToast) showToast('success', 'Support info copied to clipboard.')
        return true
      }
      if (showFailureToast) showToast('error', 'Copy failed. Please copy manually.')
    } catch (err) {
      if (showFailureToast) showToast('error', 'Copy failed. Please copy manually.')
    } finally {
      document.body.removeChild(textarea)
    }
    return false
  }

  function selectSupportInfoText () {
    if (!output) return
    try {
      const selection = window.getSelection()
      const range = document.createRange()
      range.selectNodeContents(output)
      selection.removeAllRanges()
      selection.addRange(range)
      if (typeof output.focus === 'function') output.focus()
    } catch (err) {
      // No-op: selection best-effort only.
    }
  }

  async function copySupportInfo () {
    if (!output) return
    const text = output.textContent || ''
    if (!text.trim()) {
      showToast('warning', 'Nothing to copy yet.')
      return
    }
    const canUseClipboard = isSecureContext && navigator.clipboard && navigator.clipboard.writeText
    if (canUseClipboard) {
      try {
        await navigator.clipboard.writeText(text)
        showToast('success', 'Support info copied to clipboard.')
        return
      } catch (err) {
        // Fall back to execCommand below.
      }
    }
    if (canUseClipboard) {
      fallbackCopy(text, { showFailureToast: true })
      return
    }
    fallbackCopy(text, { showFailureToast: false, showSuccessToast: false })
    selectSupportInfoText()
    showToast('warning', 'Clipboard blocked on non-HTTPS. Text selected; press Ctrl+C to copy.')
  }

  modalEl.addEventListener('show.bs.modal', () => {
    loadSupportInfo()
  })

  if (refreshBtn) refreshBtn.addEventListener('click', loadSupportInfo)
  if (copyBtn) copyBtn.addEventListener('click', copySupportInfo)
})

document.addEventListener('DOMContentLoaded', () => {
  const controls = document.getElementById('qs-scroll-controls')
  const topBtn = document.getElementById('qs-scroll-top')
  const bottomBtn = document.getElementById('qs-scroll-bottom')
  if (!controls || !topBtn || !bottomBtn) return

  const doc = document.documentElement
  const threshold = 20
  let ticking = false

  const updateControls = () => {
    const scrollHeight = doc.scrollHeight
    const clientHeight = doc.clientHeight
    const scrollTop = window.pageYOffset || doc.scrollTop || 0
    const canScroll = scrollHeight > clientHeight + threshold
    controls.classList.toggle('is-visible', canScroll)
    controls.setAttribute('aria-hidden', canScroll ? 'false' : 'true')
    if (!canScroll) {
      if (document.activeElement === topBtn || document.activeElement === bottomBtn) {
        document.activeElement.blur()
      }
      topBtn.tabIndex = -1
      bottomBtn.tabIndex = -1
      return
    }
    const atTop = scrollTop <= threshold
    const atBottom = scrollTop + clientHeight >= scrollHeight - threshold
    topBtn.classList.toggle('is-hidden', atTop)
    bottomBtn.classList.toggle('is-hidden', atBottom)
    topBtn.tabIndex = atTop ? -1 : 0
    bottomBtn.tabIndex = atBottom ? -1 : 0
  }

  const onScroll = () => {
    if (ticking) return
    ticking = true
    requestAnimationFrame(() => {
      updateControls()
      ticking = false
    })
  }

  topBtn.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  })

  bottomBtn.addEventListener('click', () => {
    window.scrollTo({ top: doc.scrollHeight, behavior: 'smooth' })
  })

  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll)
  updateControls()
})

// Optional: Rotate icon spinner style
const style = document.createElement('style')
style.textContent = `
  .spin {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`
document.head.appendChild(style)
