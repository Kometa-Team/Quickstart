/* global bootstrap, $, location */

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
    select.addEventListener('change', () => {
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
