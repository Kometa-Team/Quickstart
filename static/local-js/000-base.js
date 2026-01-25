/* global bootstrap, $, location, MutationObserver, requestAnimationFrame */

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

  if (isDebug && isVerbose) {
    ['log', 'debug', 'warn', 'error'].forEach((method) => {
      const original = console[method]
      console[method] = function (...args) {
        original.call(console, `[${getLocalTimestamp()}]`, ...args)
      }
    })
  } else {
    // In non-verbose mode, keep errors but mute spammy logs
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

// Loading spinner functionality
function loading (action) {
  console.log('action:', action)

  let spinnerIcon
  switch (action) {
    case 'prev':
      spinnerIcon = document.getElementById('prev-spinner-icon')
      break
    case 'next':
      spinnerIcon = document.getElementById('next-spinner-icon')
      break
    case 'jump':
      spinnerIcon = document.getElementById('next-spinner-icon') || document.getElementById('prev-spinner-icon')
      break
    default:
      console.error('Unsupported action:', action)
      return
  }

  if (spinnerIcon) {
    spinnerIcon.classList.remove('fa-arrow-left', 'fa-arrow-right')
    // spinnerIcon.classList.add('fa-spinner', 'fa-pulse', 'fa-fw');
    spinnerIcon.classList.add('spinner-border', 'spinner-border-sm')
  } else {
    console.error('Spinner icon not found for action:', action)
  }
}

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

// Function to show toast messages
function showToast (type, message) {
  const toastId = `toast-${Date.now()}` // Unique ID for each toast
  const toastContainer = document.querySelector('.toast-container')

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
          <i class="bi ${icon} me-2"></i> ${message}
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

// Mark all <select> elements when changed, so we can tell if a user modified them
function trackModifiedSelects () {
  document.querySelectorAll('select').forEach(select => {
    select.addEventListener('change', (event) => {
      if (event && event.isTrusted === false) return
      select.setAttribute('data-user-modified', 'true')
    })
  })
}

function restartQuickstart () {
  fetch('/restart', { method: 'POST' })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        // Disable the restart button immediately
        const restartBtn = document.querySelector('#updateResult button')
        if (restartBtn) restartBtn.disabled = true

        document.getElementById('updateResult').innerHTML = `
          <strong>🚀 ${data.message}</strong><br>
          Please wait while Quickstart restarts... this page will auto-reload shortly.
        `
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
      updateBtn.disabled = true
      updateBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Updating...'

      const branch = updateBtn.dataset.branch || 'master'

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
          resultBox.innerHTML = `
            <strong>✅ Update Successful!</strong><br>
            <span class="text-info">Branch: <code>${data.branch || branch}</code></span>
            <pre class="form-control bg-dark text-light" style="height: 300px; overflow-y: auto; overflow-x: auto; white-space: pre;">${lines.join('\n')}</pre>
            <button class="btn btn-sm btn-success mt-2" onclick="restartQuickstart()">Restart Quickstart</button>
          `
        } else {
          resultBox.innerHTML = `
            <strong>❌ Error:</strong> ${data.error || 'Update failed'}<br>
            <pre class="form-control bg-dark text-light" style="height: 300px; overflow-y: auto; overflow-x: auto; white-space: pre;">${lines.join('\n')}</pre>
          `
        }
      } catch (err) {
        resultBox.classList.remove('d-none')
        resultBox.innerHTML = `<strong>❌ Request Failed:</strong> ${String(err)}`
      } finally {
        updateBtn.disabled = false
        updateBtn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Run Update Now'
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

      try {
        const res = await fetch('/switch-config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: target })
        })
        const data = await res.json()
        if (!res.ok || !data.success) {
          throw new Error(data.message || 'Failed to switch profiles.')
        }
        showToast('success', `Switched to profile "${data.name}".`)
        setTimeout(() => location.reload(), 500)
      } catch (err) {
        confirmBtn.disabled = false
        confirmBtn.textContent = 'Switch'
        showToast('error', err.message || 'Failed to switch profiles.')
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
    updateThemeUi(getCurrentTheme())
    setStatus('', false)
    if (applyBtn) applyBtn.disabled = false
  })

  async function saveTestLibraryPaths (confirmOverride = false) {
    const quickstartRoot = getQuickstartRoot()
    if (!quickstartRoot) {
      throw new Error('Quickstart root not available.')
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

        const newPort = data.new_port || portNum || getCurrentPort()
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
        const protocol = window.location.protocol
        const host = window.location.hostname
        setTimeout(() => {
          window.location.href = `${protocol}//${host}:${newPort}`
        }, 4000)
      } catch (err) {
        setStatus(err.message || 'Failed to update settings.', true)
        showToast('error', err.message || 'Failed to update settings.')
        applyBtn.disabled = false
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

  function setStatus (text, isError) {
    if (!status) return
    status.textContent = text || ''
    status.classList.toggle('text-danger', Boolean(isError))
    status.classList.toggle('text-muted', !isError)
  }

  async function loadSupportInfo () {
    if (!output) return
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
    } catch (err) {
      output.textContent = `Unable to load support info.\n${err.message || String(err)}`
      setStatus('Error loading support info', true)
    }
  }

  function fallbackCopy (text) {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'absolute'
    textarea.style.left = '-9999px'
    document.body.appendChild(textarea)
    textarea.select()
    try {
      document.execCommand('copy')
      showToast('success', 'Support info copied to clipboard.')
    } catch (err) {
      showToast('error', 'Copy failed. Please copy manually.')
    } finally {
      document.body.removeChild(textarea)
    }
  }

  async function copySupportInfo () {
    if (!output) return
    const text = output.textContent || ''
    if (!text.trim()) {
      showToast('warning', 'Nothing to copy yet.')
      return
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(text)
        showToast('success', 'Support info copied to clipboard.')
      } catch (err) {
        fallbackCopy(text)
      }
    } else {
      fallbackCopy(text)
    }
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
    if (!canScroll) return
    const atTop = scrollTop <= threshold
    const atBottom = scrollTop + clientHeight >= scrollHeight - threshold
    topBtn.classList.toggle('is-hidden', atTop)
    bottomBtn.classList.toggle('is-hidden', atBottom)
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
style.innerHTML = `
  .spin {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`
document.head.appendChild(style)
