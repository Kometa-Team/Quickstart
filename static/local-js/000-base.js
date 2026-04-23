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

function getWorkspaceLoadingHost () {
  return document.body || document.querySelector('.qs-workspace-grid') || document.querySelector('.qs-workspace-shell')
}

const QS_NAV_LOADING_QUOTES = [
  'Downloading more RAM…',
  'Downloading more RAM.',
  'Now in technicolor.',
  'Previously on Quickstart...',
  'Previously on Kometa...',
  'Previously on Plex Meta Manager...',
  'Bleep Bloop.',
  'Locating the required gigapixels to render...',
  'Spinning up the hamster wheel...',
  'At least you\'re not on hold.',
  'Hum something loud while others stare.',
  'Scanning the high seas... please hold while we avoid suspicious parrots.',
  'Loading... or maybe just staring dramatically into the middle distance.',
  'Optimizing your patience... progress bar sold separately.',
  'Negotiating with your hard drive. It\'s asking for a coffee break.',
  'Buffering... because time travel is still in beta.',
  'We\'re not stuck. We\'re just... thinking about our life choices.',
  'This would be faster in Python… probably.',
  'Polishing pixels for maximum shininess…',
  'Untangling cable spaghetti…',
  'Reticulating splines…',
  'Calibrating the matrix…',
  'Negotiating with APIs…',
  'Aligning bits and vibes…',
  'Warming up the hamsters…',
  'Summoning config gremlins…',
  'Congratulations! You are the 1000th visitor.',
  'HELP! I\'m being held hostage and forced to write these stupid lines!',
  'RE-calibrating the internet...',
  'I\'ll be here all week',
  'Don\'t forget to tip your waitress',
  'Apply directly to the forehead',
  'Loading Battlestation',
  'It\'s not you. It\'s me.',
  'Do not run! We are your friends!',
  'What do you call 8 Hobbits? A Hobbyte.',
  'Putting the icing on the cake. The cake is not a lie...',
  'There is no spoon. Because we are not done loading it',
  'Chuck Norris never git push. The repo pulls before.',
  'Java developers never RIP. They just get Garbage Collected.',
  'Proving P=NP...',
  'Please wait... Consulting the manual...',
  'It is dark. You\'re likely to be eaten by a grue.',
  'It\'s 10:00pm somewhere. Do you know where your children are?',
  'Please wait, while we purge the Decepticons for you. Yes, You can thank us later!',
  'Chuck Norris doesn\'t wear a watch. HE decides what time it is.',
  'Creating an anti-time reaction, please wait...',
  'Rupturing the subspace barrier, please wait...',
  'Converging tachyon pulses, please wait...',
  'Bypassing control of the matter-antimatter integrator, please wait...',
  'Adjusting the dilithium crystal converter assembly, please wait...',
  'Reversing the shield polarity, please wait...',
  'Disrupting warp fields with an inverse graviton burst, please wait...',
  'Compiling infinite wisdom… almost done.',
  'Reversing the bits… because why not?',
  'Fetching more coffee for the CPU.',
  'Allocating some humor memory… nearly full.',
  'Defragging your patience… please hold.',
  'Overclocking the hamsters… success imminent.',
  'Optimizing quantum entanglement for page load…',
  'Executing sudo patience command… don\'t panic.',
  'Patching reality… ETA unknown.',
  'Waiting for the flux capacitor to stabilize…',
  'Summoning Gandalf for assistance…',
  'We\'re engaging cloaking device, please stand by.',
  'Trying to remember the words to the Cantina song…',
  'Calculating the odds like C-3PO…',
  'Asking Yoda: \'Patience, you must have…\'',
  'Decrypting the Matrix… red pill or blue pill…?',
  'Teleporting the data from a parallel dimension…',
  'Counting invisible unicorns… half done.',
  'Waiting for the penguins to align…',
  'Negotiating with the Wi-Fi spirits…',
  'Polishing pixels… carefully…',
  'Training squirrels to deliver your data…',
  'Washing imaginary dishes… almost there.',
  'Inflating your patience balloon… watch out for pop!',
  'Calibrating toaster for maximum browning… do not touch.',
  'This message will self-destruct in 3… 2… 1…',
  'Congratulations, you discovered a loading joke!',
  'If you are reading this, you are officially patient.',
  'Almost finished, but now I’m thinking about snacks.',
  'Loading… your expectations may vary.',
  'Please wait… our developers are dancing while waiting too.',
  'You’re not stuck, the page is just contemplating existence.',
  'This text is taking longer to write than the page.'
]

let qsNavLoadingQuoteTimer = null
let qsNavLoadingQuoteKickTimer = null
let qsNavLoadingQuotePool = []
let qsNavLoadingLastQuote = ''

function shuffleNavLoadingQuotes (items) {
  const shuffled = items.slice()
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    const temp = shuffled[i]
    shuffled[i] = shuffled[j]
    shuffled[j] = temp
  }
  return shuffled
}

function refillNavLoadingQuotePool () {
  qsNavLoadingQuotePool = shuffleNavLoadingQuotes(QS_NAV_LOADING_QUOTES)
  if (qsNavLoadingQuotePool.length > 1 && qsNavLoadingQuotePool[0] === qsNavLoadingLastQuote) {
    const swapIndex = 1 + Math.floor(Math.random() * (qsNavLoadingQuotePool.length - 1))
    const temp = qsNavLoadingQuotePool[0]
    qsNavLoadingQuotePool[0] = qsNavLoadingQuotePool[swapIndex]
    qsNavLoadingQuotePool[swapIndex] = temp
  }
}

function nextNavLoadingQuote () {
  if (!QS_NAV_LOADING_QUOTES.length) return 'Loading…'
  if (QS_NAV_LOADING_QUOTES.length === 1) return QS_NAV_LOADING_QUOTES[0]
  if (!qsNavLoadingQuotePool.length) {
    refillNavLoadingQuotePool()
  }
  const nextQuote = qsNavLoadingQuotePool.shift() || QS_NAV_LOADING_QUOTES[0]
  qsNavLoadingLastQuote = nextQuote
  return nextQuote
}

function setNavLoadingQuote (overlay) {
  if (!overlay) return
  const quoteNode = overlay.querySelector('.qs-nav-loading-quote')
  if (!quoteNode) return
  quoteNode.textContent = nextNavLoadingQuote()
}

function startNavLoadingQuoteLoop (overlay) {
  if (qsNavLoadingQuoteKickTimer) {
    clearTimeout(qsNavLoadingQuoteKickTimer)
    qsNavLoadingQuoteKickTimer = null
  }
  if (qsNavLoadingQuoteTimer) {
    clearInterval(qsNavLoadingQuoteTimer)
    qsNavLoadingQuoteTimer = null
  }
  setNavLoadingQuote(overlay)
  // Show the first quote change quickly so short waits still feel alive.
  qsNavLoadingQuoteKickTimer = setTimeout(() => {
    setNavLoadingQuote(overlay)
    qsNavLoadingQuoteTimer = setInterval(() => {
      setNavLoadingQuote(overlay)
    }, 2800)
  }, 1400)
}

function stopNavLoadingQuoteLoop () {
  if (qsNavLoadingQuoteKickTimer) {
    clearTimeout(qsNavLoadingQuoteKickTimer)
    qsNavLoadingQuoteKickTimer = null
  }
  if (!qsNavLoadingQuoteTimer) return
  clearInterval(qsNavLoadingQuoteTimer)
  qsNavLoadingQuoteTimer = null
}

function startNavLoadingSpinnerLoop (overlay) {
  const spinner = overlay ? overlay.querySelector('.qs-nav-loading-spinner') : null
  if (!spinner) return
  spinner.classList.add('is-spinning')
}

function stopNavLoadingSpinnerLoop () {
  document.querySelectorAll('.qs-nav-loading-spinner.is-spinning').forEach((spinner) => {
    spinner.classList.remove('is-spinning')
  })
}

function ensureNavigationLoadingOverlay () {
  const host = getWorkspaceLoadingHost()
  if (!host) return null

  let overlay = host.querySelector('[data-qs-nav-overlay]')
  if (overlay) return overlay

  overlay = document.createElement('div')
  overlay.className = 'qs-nav-loading-overlay'
  overlay.setAttribute('data-qs-nav-overlay', 'true')
  overlay.setAttribute('aria-hidden', 'true')
  overlay.innerHTML = `
    <div class="qs-nav-loading-card" role="status" aria-live="polite">
      <div class="qs-nav-loading-spinner" aria-hidden="true"></div>
      <div class="qs-nav-loading-text">
        <div class="qs-nav-loading-label">Opening step…</div>
        <div class="qs-nav-loading-quote">Downloading more RAM…</div>
      </div>
    </div>
  `
  host.appendChild(overlay)
  return overlay
}

function showNavigationLoadingOverlay (action, targetLabel) {
  const overlay = ensureNavigationLoadingOverlay()
  if (!overlay) return

  const label = overlay.querySelector('.qs-nav-loading-label')
  const actionText = {
    prev: 'Opening previous step…',
    next: 'Opening next step…',
    jump: 'Opening selected step…',
    'library-initial': 'Loading first library…',
    'library-switch': 'Switching library…',
    'kometa-check': 'Validating Kometa…',
    'header-style': 'Regenerating section style…',
    'config-switch': 'Saving current page…'
  }
  const normalizedTarget = String(targetLabel || '').trim()
  if (label) {
    if (normalizedTarget) {
      label.textContent = `Opening ${normalizedTarget}…`
    } else {
      label.textContent = actionText[action] || 'Loading…'
    }
  }

  startNavLoadingQuoteLoop(overlay)
  startNavLoadingSpinnerLoop(overlay)
  overlay.classList.add('is-active')
  overlay.setAttribute('aria-hidden', 'false')
}

function hideNavigationLoadingOverlay () {
  stopNavLoadingQuoteLoop()
  stopNavLoadingSpinnerLoop()
  document.querySelectorAll('[data-qs-nav-overlay]').forEach((overlay) => {
    overlay.classList.remove('is-active')
    overlay.setAttribute('aria-hidden', 'true')
  })
}

// Loading spinner functionality
function loading (action, targetLabel) {
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
    showNavigationLoadingOverlay(action, targetLabel)
    return
  }

  spinnerIcon.classList.remove('fa-arrow-left', 'fa-arrow-right', 'fa-list')
  // spinnerIcon.classList.add('fa-spinner', 'fa-pulse', 'fa-fw');
  spinnerIcon.classList.add('spinner-border', 'spinner-border-sm')
  showNavigationLoadingOverlay(action, targetLabel)
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
  hideNavigationLoadingOverlay()
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
function qsGetStepLabel (targetPage) {
  if (!targetPage) return ''
  const key = String(targetPage).trim()
  if (!key) return ''

  const candidates = document.querySelectorAll('[data-step-key]')
  for (const candidate of candidates) {
    if (!candidate || !candidate.dataset || candidate.dataset.stepKey !== key) continue
    const explicit = candidate.getAttribute('title')
    if (explicit) return explicit.trim()
    const labelEl = candidate.querySelector('.qs-step-link-label')
    if (labelEl && labelEl.textContent) return labelEl.textContent.trim()
    if (candidate.textContent) {
      return candidate.textContent.replace(/\s+/g, ' ').trim()
    }
  }
  return ''
}

function jumpTo (targetPage, targetLabel) {
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

  const resolvedTargetLabel = String(targetLabel || '').trim() || qsGetStepLabel(targetPage)
  const beforeNavigateEvent = new CustomEvent('qs:before-step-navigation', {
    cancelable: true,
    detail: {
      source: 'jump',
      targetPage: String(targetPage || '').trim(),
      targetLabel: resolvedTargetLabel
    }
  })
  const allowed = document.dispatchEvent(beforeNavigateEvent)
  if (!allowed) {
    resetNavigationSpinners()
    return
  }

  // Temporarily change the action and submit the form
  const originalAction = form.action
  form.action = '/step/' + targetPage
  loading('jump', resolvedTargetLabel) // optional spinner
  if (typeof form.requestSubmit === 'function') {
    form.requestSubmit()
  } else {
    form.submit()
  }
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

// --- Plex maintenance toasts (global) ---
const QS_MAINTENANCE_TOAST_INTERVAL_MS = 45000
let qsLastMaintenanceToastAt = 0
let qsLastMaintenancePaused = false
let qsLastQueuedStartedAt = null

function qsFormatLocalTime () {
  const now = new Date()
  const yyyy = now.getFullYear()
  const MM = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  const ss = String(now.getSeconds()).padStart(2, '0')
  return `${yyyy}-${MM}-${dd} ${hh}:${mm}:${ss}`
}

function qsFormatTimestamp (value) {
  const d = value ? new Date(value) : new Date()
  const yyyy = d.getFullYear()
  const MM = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  return `${yyyy}-${MM}-${dd} ${hh}:${mm}:${ss}`
}

function qsHandleMaintenanceStatus (data) {
  if (typeof showToast !== 'function' || !data) return
  const paused = Boolean(data.maintenance_paused)
  const windowLabel = data.maintenance_window ? ` (${data.maintenance_window})` : ''
  const nowLabel = qsFormatLocalTime()
  const now = Date.now()
  const badge = document.getElementById('qs-maintenance-badge')
  const runningBadge = document.getElementById('qs-running-badge')
  const unavailableBadge = document.getElementById('qs-maintenance-unavailable-badge')
  const queuedBadge = document.getElementById('qs-queued-badge')

  if (runningBadge) {
    if (data.status === 'running') {
      const elapsed = typeof data.elapsed_seconds === 'number' ? data.elapsed_seconds : null
      let elapsedLabel = ''
      if (elapsed !== null) {
        const hours = Math.floor(elapsed / 3600)
        const minutes = Math.floor((elapsed % 3600) / 60)
        const seconds = Math.floor(elapsed % 60)
        const parts = []
        if (hours) parts.push(`${hours}h`)
        parts.push(`${minutes}m`)
        parts.push(`${String(seconds).padStart(2, '0')}s`)
        elapsedLabel = ` (${parts.join(' ')})`
      }
      runningBadge.classList.remove('d-none')
      const label = runningBadge.querySelector('span')
      if (label) {
        label.innerHTML = `<i class="bi bi-play-circle me-1"></i> Kometa running${elapsedLabel}`
      }
    } else {
      runningBadge.classList.add('d-none')
    }
  }

  if (paused) {
    if (badge) {
      badge.classList.remove('d-none')
      const label = badge.querySelector('span')
      if (label) {
        label.innerHTML = `<i class="bi bi-pause-circle me-1"></i> Kometa paused for Plex maintenance${windowLabel}`
      }
    }
    if (!qsLastMaintenanceToastAt || (now - qsLastMaintenanceToastAt) >= QS_MAINTENANCE_TOAST_INTERVAL_MS) {
      showToast('warning', `Kometa paused for Plex maintenance${windowLabel} at ${nowLabel}. It will resume automatically when maintenance ends.`)
      qsLastMaintenanceToastAt = now
    }
  } else if (qsLastMaintenancePaused) {
    if (badge) {
      badge.classList.add('d-none')
    }
    showToast('success', `Plex maintenance ended at ${nowLabel}. Kometa resumed.`)
    qsLastMaintenanceToastAt = 0
  } else if (badge) {
    badge.classList.add('d-none')
  }

  if (queuedBadge) {
    if (data.pending_start) {
      const requestedAt = data.pending_requested_at ? qsFormatTimestamp(data.pending_requested_at) : null
      const label = queuedBadge.querySelector('span')
      const requestedLabel = requestedAt ? ` (requested ${requestedAt})` : ''
      queuedBadge.classList.remove('d-none')
      if (label) {
        label.innerHTML = `<i class="bi bi-hourglass-split me-1"></i> Kometa start queued${windowLabel}${requestedLabel}`
      }
    } else {
      queuedBadge.classList.add('d-none')
    }
  }

  if (unavailableBadge) {
    if (data.window_unavailable) {
      const sinceLabel = data.window_unavailable_since ? ` (since ${qsFormatTimestamp(data.window_unavailable_since)})` : ''
      const label = unavailableBadge.querySelector('span')
      unavailableBadge.classList.remove('d-none')
      if (label) {
        label.innerHTML = `<i class="bi bi-exclamation-triangle me-1"></i> Plex maintenance window unavailable${sinceLabel}`
      }
    } else {
      unavailableBadge.classList.add('d-none')
    }
  }

  if (data.queued_started_at) {
    if (!qsLastQueuedStartedAt || qsLastQueuedStartedAt !== data.queued_started_at) {
      const startedLabel = qsFormatTimestamp(data.queued_started_at)
      showToast('success', `Kometa started from queued request at ${startedLabel}.`)
      qsLastQueuedStartedAt = data.queued_started_at
    }
  }

  qsLastMaintenancePaused = paused
}

window.QS_handleMaintenanceStatus = qsHandleMaintenanceStatus
window.QS_formatTimestamp = qsFormatTimestamp

;(function qsMaintenancePoll () {
  const poll = () => {
    fetch('/kometa-status')
      .then(res => res.json())
      .then(data => qsHandleMaintenanceStatus(data))
      .catch(() => {})
  }
  // Slight delay to avoid racing early page initialization
  setTimeout(poll, 1200)
  setInterval(poll, QS_MAINTENANCE_TOAST_INTERVAL_MS)
})()

function getValidatedInput () {
  const form = document.getElementById('configForm') || document.getElementById('final-form') || document
  if (!form) return null
  return form.querySelector('input[id$="_validated"]')
}

const QS_STATUS_STATES = ['unknown', 'ok', 'warn', 'error']
const QS_STATUS_WEIGHT = { unknown: 0, ok: 1, warn: 2, error: 3 }

function qsNormalizeStatusState (status) {
  const normalized = String(status || '').trim().toLowerCase()
  return QS_STATUS_STATES.includes(normalized) ? normalized : 'warn'
}

function qsGetIndicatorState (element, baseClass) {
  if (!element) return 'warn'
  for (const state of QS_STATUS_STATES) {
    if (element.classList.contains(`${baseClass}--${state}`)) {
      return state
    }
  }
  return 'warn'
}

function qsGetStatusIconClass (state) {
  switch (state) {
    case 'ok':
      return 'bi-check-lg'
    case 'error':
      return 'bi-x-lg'
    case 'unknown':
      return 'bi-info-lg'
    default:
      return 'bi-exclamation-lg'
  }
}

function qsApplyIndicatorState (element, baseClass, nextState) {
  if (!element) return
  const normalized = qsNormalizeStatusState(nextState)
  QS_STATUS_STATES.forEach((state) => {
    element.classList.remove(`${baseClass}--${state}`)
  })
  element.classList.add(`${baseClass}--${normalized}`)

  const icon = element.querySelector('i')
  if (icon) {
    icon.className = `bi ${qsGetStatusIconClass(normalized)}`
  }
}

function qsGetCurrentStepKey () {
  const workspace = document.querySelector('.qs-workspace-section[data-current-step]')
  if (workspace && workspace.dataset.currentStep) {
    return workspace.dataset.currentStep
  }

  const activeLink = document.querySelector('.qs-step-link.is-active[data-step-key]')
  return activeLink ? activeLink.dataset.stepKey : null
}

function qsIsNonBlankFormValue (value) {
  const text = String(value || '').trim()
  if (!text) return false
  return !['none', 'null', 'false'].includes(text.toLowerCase())
}

function qsCurrentStepHasMeaningfulInput () {
  const stepKey = qsGetCurrentStepKey()
  if (stepKey === '100-anidb') {
    return Boolean(document.getElementById('anidb_enable')?.checked)
  }
  const fieldMap = {
    '030-tautulli': ['tautulli_url', 'tautulli_apikey'],
    '040-github': ['github_token'],
    '050-omdb': ['omdb_apikey'],
    '060-mdblist': ['mdblist_apikey'],
    '070-notifiarr': ['notifiarr_apikey'],
    '080-gotify': ['gotify_url', 'gotify_token'],
    '085-ntfy': ['ntfy_url', 'ntfy_token', 'ntfy_topic'],
    '110-radarr': ['radarr_url', 'radarr_token'],
    '120-sonarr': ['sonarr_url', 'sonarr_token'],
    '130-trakt': ['trakt_client_id', 'trakt_client_secret', 'trakt_pin', 'trakt_access_token', 'trakt_refresh_token'],
    '140-mal': ['mal_client_id', 'mal_client_secret', 'mal_localhost_url', 'mal_access_token', 'mal_refresh_token']
  }
  const mappedFields = fieldMap[stepKey] || []
  if (mappedFields.length) {
    return mappedFields.some((id) => qsIsNonBlankFormValue(document.getElementById(id)?.value))
  }

  const form = document.getElementById('configForm')
  if (!form) return false
  const fields = form.querySelectorAll('input, select, textarea')
  return Array.from(fields).some((field) => {
    if (!field || field.disabled) return false
    const type = String(field.type || '').toLowerCase()
    if (['hidden', 'button', 'submit', 'reset', 'file'].includes(type)) return false
    if (field.id && (field.id.endsWith('_validated') || field.id.endsWith('_validated_at'))) return false
    if (type === 'checkbox' || type === 'radio') return Boolean(field.checked)
    return qsIsNonBlankFormValue(field.value)
  })
}

function qsSetCurrentValidationAttempted (attempted) {
  const validatedInput = getValidatedInput()
  if (!validatedInput) return
  if (attempted) {
    validatedInput.dataset.qsValidationAttempted = 'true'
  } else {
    delete validatedInput.dataset.qsValidationAttempted
  }
}

function qsStateFromValidatedInput (validatedInput) {
  if (!validatedInput) return null
  const value = String(validatedInput.value || '').trim().toLowerCase()
  if (value === 'true') return 'ok'

  const group = getCurrentTemplateGroup()
  if (value === 'false') {
    if (group === 'optional') {
      if (validatedInput.dataset.qsValidationAttempted === 'true') return 'error'
      return qsCurrentStepHasMeaningfulInput() ? 'warn' : 'unknown'
    }
    return group === 'review' ? 'ok' : 'error'
  }

  if (group === 'optional') {
    return qsCurrentStepHasMeaningfulInput() ? 'warn' : 'unknown'
  }
  return 'warn'
}

function qsUpdateStepIndicators (stepKey, status) {
  if (!stepKey) return
  const normalized = qsNormalizeStatusState(status)
  window.QS_STEP_STATUSES = window.QS_STEP_STATUSES && typeof window.QS_STEP_STATUSES === 'object'
    ? window.QS_STEP_STATUSES
    : {}
  window.QS_STEP_STATUSES[stepKey] = normalized

  document.querySelectorAll('[data-step-key]').forEach((stepTarget) => {
    if (stepTarget.dataset.stepKey !== stepKey) return
    const linkIndicator = stepTarget.querySelector('.qs-step-link-state')
    const dropdownIndicator = stepTarget.querySelector('.qs-step-dropdown-state')
    qsApplyIndicatorState(linkIndicator, 'qs-step-link-state', normalized)
    qsApplyIndicatorState(dropdownIndicator, 'qs-step-dropdown-state', normalized)
  })
}

function qsGetCurrentStepStatus () {
  const stepKey = qsGetCurrentStepKey()
  if (!stepKey) return null

  if (window.QS_STEP_STATUSES && typeof window.QS_STEP_STATUSES === 'object' && window.QS_STEP_STATUSES[stepKey]) {
    return qsNormalizeStatusState(window.QS_STEP_STATUSES[stepKey])
  }

  const indicator = document.querySelector(`.qs-step-link[data-step-key="${stepKey}"] .qs-step-link-state`)
  return indicator ? qsGetIndicatorState(indicator, 'qs-step-link-state') : null
}

function qsIsCurrentStepConfigured (validatedInput) {
  if (validatedInput) {
    return String(validatedInput.value || '').toLowerCase() === 'true'
  }
  return qsGetCurrentStepStatus() === 'ok'
}

function qsResolveGroupState (groupKey, childStates) {
  if (!childStates.length) {
    return groupKey === 'optional' ? 'unknown' : 'warn'
  }

  if (groupKey === 'optional') {
    if (childStates.includes('error')) return 'error'
    if (childStates.includes('warn')) return 'warn'
    if (childStates.includes('unknown')) return 'unknown'
    return 'ok'
  }

  let worst = 'ok'
  childStates.forEach((state) => {
    const normalized = qsNormalizeStatusState(state)
    if ((QS_STATUS_WEIGHT[normalized] || 0) > (QS_STATUS_WEIGHT[worst] || 0)) {
      worst = normalized
    }
  })
  return worst
}

function qsRefreshSectionRollups () {
  document.querySelectorAll('.qs-step-group[data-step-group]').forEach((groupElement) => {
    const groupKey = String(groupElement.dataset.stepGroup || '').trim().toLowerCase()
    const childStates = Array.from(groupElement.querySelectorAll('.qs-step-group-list .qs-step-link-state'))
      .map((indicator) => qsGetIndicatorState(indicator, 'qs-step-link-state'))
    const groupState = qsResolveGroupState(groupKey, childStates)

    QS_STATUS_STATES.forEach((state) => {
      groupElement.classList.remove(`qs-step-group--${state}`)
    })
    groupElement.classList.add(`qs-step-group--${groupState}`)

    const groupIndicator = groupElement.querySelector('.qs-step-group-state')
    qsApplyIndicatorState(groupIndicator, 'qs-step-group-state', groupState)
  })
}

function qsRefreshSidebarValidationState (inputId) {
  const validatedInput = inputId ? document.getElementById(inputId) : getValidatedInput()
  if (!validatedInput) return

  const currentStepKey = qsGetCurrentStepKey()
  if (!currentStepKey) return

  const stepState = qsStateFromValidatedInput(validatedInput)
  if (!stepState) return

  const activeStepLink = document.querySelector(`.qs-step-link[data-step-key="${currentStepKey}"]`)
  const previousState = qsGetIndicatorState(activeStepLink ? activeStepLink.querySelector('.qs-step-link-state') : null, 'qs-step-link-state')

  qsUpdateStepIndicators(currentStepKey, stepState)
  qsRefreshSectionRollups()
  qsRecalculateReadinessFromSidebar()
  qsApplyAllDependencyHints()

  if (previousState !== stepState && window.QSWorkspaceStatus && typeof window.QSWorkspaceStatus.refresh === 'function') {
    window.QSWorkspaceStatus.refresh({ reason: 'validation-state-change', delayMs: 120 })
  }
}

function qsSetSidebarStepStatus (stepKey, status) {
  if (!stepKey) return
  qsUpdateStepIndicators(stepKey, status)
  qsRefreshSectionRollups()
  qsRecalculateReadinessFromSidebar()
  qsApplyAllDependencyHints()
}

let qsWorkspaceStatusRequest = null
let qsWorkspaceStatusPending = false
let qsWorkspaceStatusTimer = null

function qsArrayFromKeys (value) {
  if (!Array.isArray(value)) return []
  const seen = new Set()
  const result = []
  value.forEach((entry) => {
    const key = String(entry || '').trim()
    if (!key || seen.has(key)) return
    seen.add(key)
    result.push(key)
  })
  return result
}

function qsApplyGroupMembership (requiredKeys, optionalKeys, reviewKeys) {
  const groups = {
    required: document.querySelector('.qs-step-group[data-step-group="required"] .qs-step-group-list'),
    optional: document.querySelector('.qs-step-group[data-step-group="optional"] .qs-step-group-list'),
    review: document.querySelector('.qs-step-group[data-step-group="review"] .qs-step-group-list')
  }
  if (!groups.required || !groups.optional || !groups.review) return

  const currentStepKey = qsGetCurrentStepKey()
  const currentStepLinkBeforeMove = currentStepKey
    ? document.querySelector(`.qs-step-link[data-step-key="${currentStepKey}"]`)
    : null
  const previousGroupKey = currentStepLinkBeforeMove
    ? String(currentStepLinkBeforeMove.closest('.qs-step-group[data-step-group]')?.dataset?.stepGroup || '').trim().toLowerCase()
    : ''

  const stepMap = {}
  document.querySelectorAll('.qs-step-group-list .qs-step-link[data-step-key]').forEach((stepLink) => {
    const key = String(stepLink.dataset.stepKey || '').trim()
    if (!key || stepMap[key]) return
    stepMap[key] = stepLink
  })

  const appendInOrder = (listEl, keys) => {
    keys.forEach((key) => {
      const stepLink = stepMap[key]
      if (!stepLink) return
      listEl.appendChild(stepLink)
    })
  }

  appendInOrder(groups.required, requiredKeys)
  appendInOrder(groups.optional, optionalKeys)
  appendInOrder(groups.review, reviewKeys)

  // Preserve user-controlled expanded/collapsed state.
  // Only auto-open when the current step actually moves to a different section
  // (e.g., Optional -> Required via dependency changes such as MAL).
  let currentGroupKey = ''
  if (currentStepKey) {
    if (requiredKeys.includes(currentStepKey)) currentGroupKey = 'required'
    else if (reviewKeys.includes(currentStepKey)) currentGroupKey = 'review'
    else if (optionalKeys.includes(currentStepKey)) currentGroupKey = 'optional'
  }

  if (currentGroupKey && currentGroupKey !== previousGroupKey) {
    const nextGroup = document.querySelector(`.qs-step-group[data-step-group="${currentGroupKey}"]`)
    if (nextGroup) nextGroup.open = true
  }
}

function qsApplyReadinessStrip (readiness) {
  const strip = document.querySelector('.qs-readiness-strip')
  if (!strip) return

  const source = (readiness && typeof readiness === 'object') ? readiness : {}
  const requiredReady = Number(source.required_ready || 0)
  const requiredTotal = Number(source.required_total || 0)
  const requiredPercent = Number(source.required_percent || 0)
  const requiredState = qsNormalizeStatusState(source.required_state || 'unknown')
  const optionalTotal = Number(source.optional_total || 0)
  const optionalConfigured = Number(source.optional_configured || 0)
  const optionalIssueCount = Number(source.optional_issue_count || 0)
  const optionalSummary = String(source.optional_summary || 'Optional 0/0 configured')
  const validationAge = String(source.validation_age_label || 'Never')
  const validationFreshness = ['fresh', 'stale', 'never'].includes(String(source.validation_freshness || 'never'))
    ? String(source.validation_freshness || 'never')
    : 'never'

  QS_STATUS_STATES.forEach((state) => {
    strip.classList.remove(`qs-readiness-state-${state}`)
  })
  strip.classList.add(`qs-readiness-state-${requiredState}`)

  const bar = strip.querySelector('.qs-readiness-required-bar')
  if (bar) {
    bar.style.width = `${Math.max(0, Math.min(100, requiredPercent))}%`
  }

  const full = strip.querySelector('.qs-step-progress-text-full')
  if (full) full.textContent = `Required ${requiredReady}/${requiredTotal}`

  const compact = strip.querySelector('.qs-step-progress-text-short')
  if (compact) compact.textContent = `${requiredReady}/${requiredTotal}`

  const sublines = strip.querySelectorAll('.qs-readiness-subline')
  if (sublines[0]) sublines[0].textContent = optionalSummary
  if (sublines[1]) {
    sublines[1].textContent = `Last validated: ${validationAge}`
    sublines[1].classList.remove('qs-readiness-freshness-fresh', 'qs-readiness-freshness-stale', 'qs-readiness-freshness-never')
    sublines[1].classList.add(`qs-readiness-freshness-${validationFreshness}`)
  }

  const compactRequired = strip.querySelector('[data-qs-readiness-required-short]')
  if (compactRequired) compactRequired.textContent = `${requiredReady}/${requiredTotal}`

  const compactRequiredRow = strip.querySelector('[data-qs-readiness-required-row]')
  if (compactRequiredRow) {
    compactRequiredRow.title = `Required ${requiredReady}/${requiredTotal} complete`
  }

  const compactOptional = strip.querySelector('[data-qs-readiness-optional-short]')
  if (compactOptional) compactOptional.textContent = `${optionalConfigured}/${optionalTotal}`

  const compactOptionalRow = strip.querySelector('[data-qs-readiness-optional-row]')
  if (compactOptionalRow) {
    compactOptionalRow.title = optionalSummary
    compactOptionalRow.classList.remove('qs-readiness-compact-row--ok', 'qs-readiness-compact-row--warn', 'qs-readiness-compact-row--unknown')
    if (optionalIssueCount > 0) {
      compactOptionalRow.classList.add('qs-readiness-compact-row--warn')
    } else if (optionalConfigured > 0 || optionalTotal === 0) {
      compactOptionalRow.classList.add('qs-readiness-compact-row--ok')
    } else {
      compactOptionalRow.classList.add('qs-readiness-compact-row--unknown')
    }
  }

  const compactValidation = strip.querySelector('[data-qs-readiness-validation-short]')
  if (compactValidation) compactValidation.textContent = qsCompactValidationLabel(validationAge)

  const compactValidationRow = strip.querySelector('[data-qs-readiness-validation-row]')
  if (compactValidationRow) {
    compactValidationRow.title = `Last validated: ${validationAge}`
    compactValidationRow.classList.remove('qs-readiness-freshness-fresh', 'qs-readiness-freshness-stale', 'qs-readiness-freshness-never')
    compactValidationRow.classList.add(`qs-readiness-freshness-${validationFreshness}`)
  }
}

function qsCompactValidationLabel (label) {
  const text = String(label || 'Never').trim()
  if (!text) return 'Never'
  if (/^just now$/i.test(text)) return 'Now'
  return text
}

function qsDependencyConfigMap () {
  return {
    tautulli: {
      stepKey: '030-tautulli',
      windowKey: 'QS_TAUTULLI_REQUIREMENT_REASONS',
      label: 'Tautulli'
    },
    omdb: {
      stepKey: '050-omdb',
      windowKey: 'QS_OMDB_REQUIREMENT_REASONS',
      label: 'OMDb'
    },
    mdblist: {
      stepKey: '060-mdblist',
      windowKey: 'QS_MDBLIST_REQUIREMENT_REASONS',
      label: 'MDBList'
    },
    anidb: {
      stepKey: '100-anidb',
      windowKey: 'QS_ANIDB_REQUIREMENT_REASONS',
      label: 'AniDB'
    },
    radarr: {
      stepKey: '110-radarr',
      windowKey: 'QS_RADARR_REQUIREMENT_REASONS',
      label: 'Radarr'
    },
    sonarr: {
      stepKey: '120-sonarr',
      windowKey: 'QS_SONARR_REQUIREMENT_REASONS',
      label: 'Sonarr'
    },
    trakt: {
      stepKey: '130-trakt',
      windowKey: 'QS_TRAKT_REQUIREMENT_REASONS',
      label: 'Trakt'
    },
    mal: {
      stepKey: '140-mal',
      windowKey: 'QS_MAL_REQUIREMENT_REASONS',
      label: 'MyAnimeList'
    }
  }
}

function qsNormalizeDependencyReasons (reasons) {
  const normalized = Array.isArray(reasons)
    ? reasons.map(reason => String(reason || '').trim()).filter(Boolean)
    : []
  return normalized
}

function qsGetDependencyReasonsForProvider (providerKey) {
  const config = qsDependencyConfigMap()[providerKey]
  if (!config) return []
  return qsNormalizeDependencyReasons(window[config.windowKey])
}

function qsGetStepStatus (stepKey) {
  if (!stepKey) return null

  if (window.QS_STEP_STATUSES && typeof window.QS_STEP_STATUSES === 'object' && window.QS_STEP_STATUSES[stepKey]) {
    return qsNormalizeStatusState(window.QS_STEP_STATUSES[stepKey])
  }

  const indicator = document.querySelector(`.qs-step-link[data-step-key="${stepKey}"] .qs-step-link-state`)
  return indicator ? qsGetIndicatorState(indicator, 'qs-step-link-state') : null
}

function qsIsDependencyStepConfigured (providerKey) {
  const config = qsDependencyConfigMap()[providerKey]
  if (!config) return false
  return qsGetStepStatus(config.stepKey) === 'ok'
}

function qsBindDependencyHintNavigation (hint, providerKey) {
  if (!hint || hint.dataset.qsDependencyNavBound === 'true') return
  const config = qsDependencyConfigMap()[providerKey]
  if (!config) return

  hint.dataset.qsDependencyNavBound = 'true'
  hint.dataset.stepKey = config.stepKey
  hint.setAttribute('role', 'button')
  hint.setAttribute('tabindex', '0')
  hint.title = config.label

  const navigate = () => {
    if (hint.classList.contains('d-none')) return
    jumpTo(config.stepKey, config.label)
  }

  hint.addEventListener('click', navigate)
  hint.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    navigate()
  })
}

function qsRefreshDependencyTodoGroup () {
  const group = document.querySelector('[data-qs-dependency-todo]')
  if (!group) return

  const visibleHints = Array.from(group.querySelectorAll('[data-qs-dependency-hint]'))
    .filter((hint) => !hint.classList.contains('d-none'))
  const countElement = group.querySelector('[data-qs-dependency-todo-count]')

  if (countElement) {
    countElement.textContent = String(visibleHints.length)
  }

  group.classList.toggle('d-none', visibleHints.length === 0)
}

function qsApplyDependencyHintSidebar (providerKey, reasons) {
  const normalized = qsNormalizeDependencyReasons(reasons)

  document.querySelectorAll(`[data-qs-dependency-hint="${providerKey}"]`).forEach((hint) => {
    qsBindDependencyHintNavigation(hint, providerKey)
    const lines = hint.querySelector('[data-qs-dependency-lines]')
    if (!lines) return

    lines.replaceChildren()
    if (!normalized.length || qsIsDependencyStepConfigured(providerKey)) {
      hint.classList.add('d-none')
      return
    }

    hint.classList.remove('d-none')
    const visibleCount = 2
    normalized.slice(0, visibleCount).forEach((reason) => {
      const row = document.createElement('div')
      row.className = 'qs-dependency-hint-line'
      row.textContent = reason
      lines.appendChild(row)
    })

    if (normalized.length > visibleCount) {
      const more = document.createElement('div')
      more.className = 'qs-dependency-hint-line'
      more.textContent = `+${normalized.length - visibleCount} more...`
      lines.appendChild(more)
    }
  })
  qsRefreshDependencyTodoGroup()
}

function qsApplyAllDependencyHints (dependencyPayload) {
  const configMap = qsDependencyConfigMap()
  Object.keys(configMap).forEach((providerKey) => {
    const reasons = dependencyPayload && typeof dependencyPayload === 'object' && providerKey in dependencyPayload
      ? dependencyPayload[providerKey]
      : qsGetDependencyReasonsForProvider(providerKey)
    qsApplyDependencyHintSidebar(providerKey, reasons)
  })
}

function qsApplySectionStatuses (sectionStatuses) {
  if (!sectionStatuses || typeof sectionStatuses !== 'object') {
    qsRefreshSectionRollups()
    return
  }

  document.querySelectorAll('.qs-step-group[data-step-group]').forEach((groupElement) => {
    const groupKey = String(groupElement.dataset.stepGroup || '').trim().toLowerCase()
    const state = qsNormalizeStatusState(sectionStatuses[groupKey] || 'warn')

    QS_STATUS_STATES.forEach((candidate) => {
      groupElement.classList.remove(`qs-step-group--${candidate}`)
    })
    groupElement.classList.add(`qs-step-group--${state}`)

    const indicator = groupElement.querySelector('.qs-step-group-state')
    qsApplyIndicatorState(indicator, 'qs-step-group-state', state)
  })
}

function qsRecalculateReadinessFromSidebar () {
  const requiredLinks = Array.from(document.querySelectorAll('.qs-step-group[data-step-group="required"] .qs-step-link'))
  const optionalLinks = Array.from(document.querySelectorAll('.qs-step-group[data-step-group="optional"] .qs-step-link'))
  if (!requiredLinks.length && !optionalLinks.length) return

  const requiredStates = requiredLinks
    .map(link => qsGetIndicatorState(link.querySelector('.qs-step-link-state'), 'qs-step-link-state'))
  const optionalStates = optionalLinks
    .map(link => qsGetIndicatorState(link.querySelector('.qs-step-link-state'), 'qs-step-link-state'))

  const requiredTotal = requiredStates.length
  const requiredReady = requiredStates.filter(state => state === 'ok').length
  const requiredPercent = requiredTotal ? Math.round((requiredReady / requiredTotal) * 100) : 0
  const requiredState = qsResolveGroupState('required', requiredStates)

  const optionalTotal = optionalStates.length
  const optionalConfigured = optionalStates.filter(state => state !== 'unknown').length
  const optionalIssueCount = optionalStates.filter(state => state === 'warn' || state === 'error').length
  let optionalSummary = optionalTotal ? `Optional ${optionalConfigured}/${optionalTotal} configured` : 'No optional pages'
  if (optionalIssueCount > 0) {
    optionalSummary += ` • ${optionalIssueCount} issue${optionalIssueCount === 1 ? '' : 's'}`
  }

  let validationAgeLabel = 'Never'
  let validationFreshness = 'never'
  const strip = document.querySelector('.qs-readiness-strip')
  if (strip) {
    const sublines = strip.querySelectorAll('.qs-readiness-subline')
    if (sublines[1]) {
      const text = String(sublines[1].textContent || '').trim()
      const match = text.match(/^Last validated:\s*(.+)$/i)
      if (match && match[1]) validationAgeLabel = match[1].trim()
      ;['fresh', 'stale', 'never'].forEach((candidate) => {
        if (sublines[1].classList.contains(`qs-readiness-freshness-${candidate}`)) {
          validationFreshness = candidate
        }
      })
    }
  }

  qsApplyReadinessStrip({
    required_total: requiredTotal,
    required_ready: requiredReady,
    required_percent: requiredPercent,
    required_state: requiredState,
    optional_total: optionalTotal,
    optional_configured: optionalConfigured,
    optional_issue_count: optionalIssueCount,
    optional_summary: optionalSummary,
    validation_age_label: validationAgeLabel,
    validation_freshness: validationFreshness
  })
}

function qsApplyWorkspaceStatus (payload) {
  if (!payload || typeof payload !== 'object') return

  const requiredKeys = qsArrayFromKeys(payload.required_keys)
  const optionalKeys = qsArrayFromKeys(payload.optional_keys)
  const reviewKeys = qsArrayFromKeys(payload.review_keys)
  const tautulliReasons = qsArrayFromKeys(payload.tautulli_requirement_reasons)
  const omdbReasons = qsArrayFromKeys(payload.omdb_requirement_reasons)
  const mdblistReasons = qsArrayFromKeys(payload.mdblist_requirement_reasons)
  const anidbReasons = qsArrayFromKeys(payload.anidb_requirement_reasons)
  const radarrReasons = qsArrayFromKeys(payload.radarr_requirement_reasons)
  const sonarrReasons = qsArrayFromKeys(payload.sonarr_requirement_reasons)
  const traktReasons = qsArrayFromKeys(payload.trakt_requirement_reasons)
  const malReasons = qsArrayFromKeys(payload.mal_requirement_reasons)

  window.QS_REQUIRED_KEYS = requiredKeys
  window.QS_OPTIONAL_KEYS = optionalKeys
  window.QS_REVIEW_KEYS = reviewKeys
  window.QS_TAUTULLI_REQUIREMENT_REASONS = tautulliReasons
  window.QS_OMDB_REQUIREMENT_REASONS = omdbReasons
  window.QS_MDBLIST_REQUIREMENT_REASONS = mdblistReasons
  window.QS_ANIDB_REQUIREMENT_REASONS = anidbReasons
  window.QS_RADARR_REQUIREMENT_REASONS = radarrReasons
  window.QS_SONARR_REQUIREMENT_REASONS = sonarrReasons
  window.QS_TRAKT_REQUIREMENT_REASONS = traktReasons
  window.QS_MAL_REQUIREMENT_REASONS = malReasons

  qsApplyGroupMembership(requiredKeys, optionalKeys, reviewKeys)
  qsApplyAllDependencyHints({
    tautulli: tautulliReasons,
    omdb: omdbReasons,
    mdblist: mdblistReasons,
    anidb: anidbReasons,
    radarr: radarrReasons,
    sonarr: sonarrReasons,
    trakt: traktReasons,
    mal: malReasons
  })

  if (payload.step_statuses && typeof payload.step_statuses === 'object') {
    Object.keys(payload.step_statuses).forEach((stepKey) => {
      qsUpdateStepIndicators(stepKey, payload.step_statuses[stepKey])
    })
  }

  qsApplySectionStatuses(payload.section_statuses)
  qsApplyReadinessStrip(payload.readiness || {})
  qsRecalculateReadinessFromSidebar()
  updateValidationCallouts()
}

function qsFetchWorkspaceStatus (options = {}) {
  if (qsWorkspaceStatusRequest) {
    qsWorkspaceStatusPending = true
    return qsWorkspaceStatusRequest
  }

  const params = new URLSearchParams()
  if (options.configName) params.set('config_name', options.configName)
  params.set('_', String(Date.now()))
  qsWorkspaceStatusRequest = fetch(`/workspace_status?${params.toString()}`, {
    method: 'GET',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { Accept: 'application/json' }
  })
    .then(async (response) => {
      let data = null
      try {
        data = await response.json()
      } catch (err) {
        data = null
      }
      if (!response.ok || !data || data.success !== true) {
        throw new Error((data && (data.message || data.error)) || `workspace_status failed (${response.status})`)
      }
      qsApplyWorkspaceStatus(data)
      return data
    })
    .catch(() => null)
    .finally(() => {
      qsWorkspaceStatusRequest = null
      if (qsWorkspaceStatusPending) {
        qsWorkspaceStatusPending = false
        qsFetchWorkspaceStatus(options)
      }
    })

  return qsWorkspaceStatusRequest
}

function qsRefreshWorkspaceStatus (options = {}) {
  const delayMs = Number(options.delayMs || 0)
  const immediate = Boolean(options.immediate)
  const requestOptions = { configName: options.configName || '' }

  if (qsWorkspaceStatusTimer) {
    clearTimeout(qsWorkspaceStatusTimer)
    qsWorkspaceStatusTimer = null
  }

  if (immediate || delayMs <= 0) {
    return qsFetchWorkspaceStatus(requestOptions)
  }

  qsWorkspaceStatusTimer = setTimeout(() => {
    qsWorkspaceStatusTimer = null
    qsFetchWorkspaceStatus(requestOptions)
  }, delayMs)

  return Promise.resolve(null)
}

let qsBulkValidationRequest = null

function qsGetBulkSummaryCounts (summary) {
  const source = (summary && typeof summary === 'object') ? summary : {}
  return {
    validated: Number(source.validated || 0),
    failed: Number(source.failed || 0),
    skipped: Number(source.skipped || 0)
  }
}

function qsBulkSummaryState (summary) {
  const counts = qsGetBulkSummaryCounts(summary)
  if (counts.failed > 0) return 'error'
  if (counts.skipped > 0) return 'warn'
  if (counts.validated > 0) return 'ok'
  return 'unknown'
}

function qsBulkSummaryLabel (summary) {
  const counts = qsGetBulkSummaryCounts(summary)
  const state = qsBulkSummaryState(summary)
  if (state === 'error') return `${counts.failed} failed`
  if (state === 'warn') return `${counts.skipped} skipped`
  if (state === 'ok') return 'All good'
  return 'Not run'
}

function qsApplyValidationRollupBadge (summary) {
  const counts = qsGetBulkSummaryCounts(summary)
  const state = qsBulkSummaryState(summary)
  document.querySelectorAll('[data-qs-validation-rollup-badge]').forEach((badge) => {
    if (!badge) return
    badge.textContent = qsBulkSummaryLabel(summary)
    badge.dataset.validated = String(counts.validated)
    badge.dataset.failed = String(counts.failed)
    badge.dataset.skipped = String(counts.skipped)
    badge.classList.remove(
      'qs-validation-rollup-badge--unknown',
      'qs-validation-rollup-badge--ok',
      'qs-validation-rollup-badge--warn',
      'qs-validation-rollup-badge--error'
    )
    badge.classList.add(`qs-validation-rollup-badge--${state}`)
  })
}

function qsStepStateFromBulkStatus (status) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'validated') return 'ok'
  if (normalized === 'failed') return 'error'
  if (normalized === 'skipped') return 'warn'
  return 'warn'
}

function qsApplyBulkValidationResults (results, summary) {
  if (results && typeof results === 'object') {
    Object.keys(results).forEach((stepKey) => {
      qsUpdateStepIndicators(stepKey, qsStepStateFromBulkStatus(results[stepKey] && results[stepKey].status))
    })
  }

  const finalState = qsBulkSummaryState(summary)
  qsUpdateStepIndicators('900-final', finalState === 'unknown' ? 'warn' : finalState)
  qsRefreshSectionRollups()
  qsRecalculateReadinessFromSidebar()
  qsApplyValidationRollupBadge(summary)
}

function qsSetBulkValidationLoading (isLoading) {
  document.querySelectorAll('[data-qs-validate-all]').forEach((button) => {
    button.disabled = !!isLoading
    const spinner = button.querySelector('.qs-validate-all-spinner')
    if (spinner) {
      spinner.classList.toggle('d-none', !isLoading)
    }
  })
}

function qsRunBulkValidation (options = {}) {
  if (qsBulkValidationRequest) return qsBulkValidationRequest

  document.dispatchEvent(new CustomEvent('qs:bulk-validation-start', { detail: { source: options.source || null } }))
  qsSetBulkValidationLoading(true)

  qsBulkValidationRequest = fetch('/validate_all_services', { method: 'POST' })
    .then(async (res) => {
      let data = null
      try {
        data = await res.json()
      } catch (err) {
        data = null
      }

      if (!res.ok) {
        const message = (data && (data.message || data.error)) || `Request failed (${res.status}).`
        throw new Error(message)
      }
      if (!data || !data.success) {
        throw new Error((data && (data.message || data.error)) || 'Validation failed. Please try again.')
      }

      const results = data.results || {}
      const summary = data.summary || {}
      qsApplyBulkValidationResults(results, summary)
      document.dispatchEvent(new CustomEvent('qs:bulk-validation-complete', { detail: data }))

      if (!options.silentToast && typeof showToast === 'function') {
        const counts = qsGetBulkSummaryCounts(summary)
        showToast('info', `Validate all complete. Validated: ${counts.validated} • Failed: ${counts.failed} • Skipped: ${counts.skipped}`)
      }

      return data
    })
    .catch((err) => {
      const message = err && err.message ? err.message : 'Validate all failed. Please try again.'
      if (typeof showToast === 'function') {
        showToast('error', message)
      }
      document.dispatchEvent(new CustomEvent('qs:bulk-validation-error', { detail: { message } }))
      throw err
    })
    .finally(() => {
      qsSetBulkValidationLoading(false)
      qsBulkValidationRequest = null
    })

  return qsBulkValidationRequest
}

function updateValidationCallouts (inputId) {
  const callouts = document.querySelectorAll('.qs-validation-accordion')
  if (callouts.length) {
    callouts.forEach((wrapper) => {
      const targetId = inputId || wrapper.dataset.qsValidatedInput
      const validatedInput = targetId ? document.getElementById(targetId) : getValidatedInput()
      const isConfigured = qsIsCurrentStepConfigured(validatedInput)

      const alert = wrapper.querySelector('.qs-validation-callout')
      if (alert) {
        applyDynamicValidationCalloutState(alert, isConfigured)
      }

      const collapse = wrapper.querySelector('.accordion-collapse')
      const button = wrapper.querySelector('.accordion-button')
      if (!collapse || !button) return

      const shouldCollapse = isConfigured && wrapper.dataset.qsAutoCollapsed !== 'true'
      if (shouldCollapse) {
        button.classList.add('collapsed')
        button.setAttribute('aria-expanded', 'false')

        if (typeof bootstrap !== 'undefined' && bootstrap.Collapse) {
          const instance = bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false })
          instance.hide()
        } else {
          collapse.classList.remove('show')
        }
        wrapper.dataset.qsAutoCollapsed = 'true'
      }

      refreshValidationAccordionTitle(wrapper, isConfigured)
    })
  }

  document.querySelectorAll('.qs-validation-callout').forEach((alert) => {
    if (alert.closest('.qs-validation-accordion')) return
    applyDynamicValidationCalloutState(alert)
  })

  qsRefreshSidebarValidationState(inputId)
}

function getCurrentTemplateKey () {
  const raw = String(window.QS_CURRENT_TEMPLATE || '').trim()
  if (!raw) return ''
  return raw.endsWith('.html') ? raw.replace(/\.html$/i, '') : raw
}

function getCurrentTemplateGroup () {
  const key = getCurrentTemplateKey()
  if (!key) return ''
  const required = Array.isArray(window.QS_REQUIRED_KEYS) ? window.QS_REQUIRED_KEYS : []
  const review = Array.isArray(window.QS_REVIEW_KEYS) ? window.QS_REVIEW_KEYS : []
  if (required.includes(key)) return 'required'
  if (review.includes(key)) return 'review'
  return 'optional'
}

function applyDynamicValidationCalloutState (alert, isConfiguredOverride = null) {
  if (!alert) return

  if (!alert.dataset.qsOriginalHtml) {
    alert.dataset.qsOriginalHtml = alert.innerHTML
  }

  const group = getCurrentTemplateGroup()
  const templateKey = getCurrentTemplateKey()
  const isRequired = group === 'required'
  const isOptional = group === 'optional'
  const isReview = group === 'review'
  const isConfigured = isConfiguredOverride === null
    ? qsIsCurrentStepConfigured(getValidatedInput())
    : Boolean(isConfiguredOverride)

  let html = alert.dataset.qsOriginalHtml

  if (isRequired && !isConfigured) {
    html = html.replace(
      /<br>\s*Alternatively,\s*navigate to another page to skip this section\./gi,
      '<br><strong>This page is currently required based on your configuration.</strong>'
    )
  }

  alert.innerHTML = html

  const heading = alert.querySelector('h6, h4')
  if (heading && !isReview) {
    heading.innerHTML = `<b>${
      isConfigured
        ? (isRequired ? 'This required page is configured' : 'This optional page is configured')
        : (isRequired ? 'This page is mandatory and must be completed' : 'This page is optional')
    }</b>`
  }

  alert.classList.remove('alert-info', 'alert-danger', 'alert-warning', 'alert-success')
  if (isConfigured || isReview) {
    alert.classList.add('alert-success')
  } else if (isRequired) {
    alert.classList.add('alert-danger')
  } else if (isOptional) {
    alert.classList.add('alert-info')
  }

  const dependencyMap = qsDependencyConfigMap()
  const dependencyEntry = Object.entries(dependencyMap).find(([, config]) => config.stepKey === templateKey)
  const dependencyConfig = dependencyEntry ? dependencyEntry[1] : null
  if (dependencyConfig) {
    alert.querySelectorAll('[data-qs-callout-mal-reason]').forEach((el) => el.remove())
    const reasons = qsGetDependencyReasonsForProvider(dependencyEntry[0])
    if (isRequired && reasons.length) {
      const box = document.createElement('div')
      box.className = 'qs-callout-mal-reason mt-2'
      box.setAttribute('data-qs-callout-mal-reason', 'true')

      const title = document.createElement('div')
      title.className = 'qs-callout-mal-reason-title'
      title.textContent = isConfigured
        ? `${dependencyConfig.label} was required because it is needed by:`
        : `Now required because ${dependencyConfig.label} is needed by:`
      box.appendChild(title)

      const list = document.createElement('ul')
      list.className = 'qs-callout-mal-reason-list'
      reasons.slice(0, 3).forEach((reason) => {
        const li = document.createElement('li')
        li.textContent = String(reason)
        list.appendChild(li)
      })
      if (reasons.length > 3) {
        const li = document.createElement('li')
        li.textContent = `+${reasons.length - 3} more...`
        list.appendChild(li)
      }
      box.appendChild(list)

      const headingNode = alert.querySelector('h6, h4')
      if (headingNode && headingNode.parentNode) {
        headingNode.insertAdjacentElement('afterend', box)
      } else {
        alert.prepend(box)
      }
    }
  }
}

function qsGetCalloutAccordionState (isConfigured) {
  if (isConfigured) return 'ok'
  const inputState = qsStateFromValidatedInput(getValidatedInput())
  if (inputState) return inputState
  const currentState = qsGetCurrentStepStatus()
  if (currentState) return currentState
  const group = getCurrentTemplateGroup()
  if (group === 'required') return 'error'
  if (group === 'optional') return 'unknown'
  if (group === 'review') return 'ok'
  return 'warn'
}

function qsGetCalloutAccordionIconClass (state) {
  const normalized = qsNormalizeStatusState(state)
  return qsGetStatusIconClass(normalized)
}

function refreshValidationAccordionTitle (wrapper, isValidated) {
  if (!wrapper) return
  const button = wrapper.querySelector('.accordion-button')
  if (!button) return

  const baseTitle = String(
    wrapper.dataset.qsCalloutTitle ||
    button.dataset.qsBaseTitle ||
    button.textContent ||
    'Setup guidance'
  ).trim()

  if (!button.dataset.qsBaseTitle) {
    button.dataset.qsBaseTitle = baseTitle
  }
  if (!wrapper.dataset.qsCalloutTitle) {
    wrapper.dataset.qsCalloutTitle = baseTitle
  }

  let title = baseTitle
  const state = qsGetCalloutAccordionState(isValidated)
  if (isValidated) {
    const group = getCurrentTemplateGroup()
    if (group === 'required') {
      title = 'Required page validated'
    } else if (group === 'optional') {
      title = 'Optional page guidance'
    } else if (group === 'review') {
      title = 'Review page guidance'
    } else {
      title = 'Page guidance'
    }
  }

  button.replaceChildren()
  const label = document.createElement('span')
  label.textContent = title
  button.appendChild(label)

  const indicator = document.createElement('span')
  indicator.className = `qs-step-link-state qs-step-link-state--${qsNormalizeStatusState(state)} ms-2`
  indicator.setAttribute('aria-hidden', 'true')

  const icon = document.createElement('i')
  icon.className = `bi ${qsGetCalloutAccordionIconClass(state)}`
  indicator.appendChild(icon)
  button.appendChild(indicator)
}

function setupValidationCallouts () {
  const callouts = document.querySelectorAll('.qs-validation-callout')
  if (!callouts.length) return

  callouts.forEach((alert, index) => {
    if (alert.closest('.modal')) return
    if (alert.closest('.qs-validation-accordion')) return

    const validatedInput = getValidatedInput()
    const isValidated = qsIsCurrentStepConfigured(validatedInput)

    applyDynamicValidationCalloutState(alert, isValidated)
    const heading = alert.querySelector('h6, h4')
    const title = alert.dataset.qsCalloutTitle || (heading ? heading.textContent.trim() : 'Setup guidance')
    const accordionId = `qs-validation-accordion-${index}`
    const collapseId = `qs-validation-collapse-${index}`
    const headingId = `qs-validation-heading-${index}`

    const wrapper = document.createElement('div')
    wrapper.className = 'accordion qs-validation-accordion mb-2'
    if (validatedInput && validatedInput.id) {
      wrapper.dataset.qsValidatedInput = validatedInput.id
    }
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
    wrapper.dataset.qsCalloutTitle = title

    const parent = alert.parentNode
    parent.insertBefore(wrapper, alert)
    body.appendChild(alert)
    alert.classList.add('mb-0')

    refreshValidationAccordionTitle(wrapper, isValidated)
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
  qsRefreshSidebarValidationState()
  qsRefreshWorkspaceStatus({ immediate: true })
  document.addEventListener('click', (event) => {
    const target = event.target instanceof window.Element ? event.target : null
    if (!target) return
    if (target.closest('#validateButton, #validate_trakt_pin, #validate_mal_url, .validate-button')) {
      qsSetCurrentValidationAttempted(true)
    }
  })
  document.addEventListener('input', (event) => {
    const target = event.target instanceof window.Element ? event.target : null
    if (!target || !target.closest('#configForm')) return
    if (target.matches('input[id$="_validated"], input[id$="_validated_at"]')) return
    qsSetCurrentValidationAttempted(false)
  }, true)
  document.addEventListener('change', (event) => {
    const target = event.target instanceof window.Element ? event.target : null
    if (!target || !target.closest('#configForm')) return
    if (target.matches('input[id$="_validated"], input[id$="_validated_at"]')) return
    qsSetCurrentValidationAttempted(false)
  }, true)
  document.querySelectorAll('[data-qs-validate-all]').forEach((button) => {
    if (button.dataset.qsValidateAllBound === 'true') return
    button.dataset.qsValidateAllBound = 'true'
    button.addEventListener('click', () => {
      qsRunBulkValidation({ source: button.id || null }).catch(() => {})
    })
  })
})

window.QSValidationCallouts = {
  refresh: updateValidationCallouts,
  setup: setupValidationCallouts,
  refreshSidebar: qsRefreshSidebarValidationState,
  setStepStatus: qsSetSidebarStepStatus
}
window.QSBulkValidation = {
  run: qsRunBulkValidation,
  applyResults: qsApplyBulkValidationResults,
  getSummaryState: qsBulkSummaryState,
  getSummaryCounts: qsGetBulkSummaryCounts
}
window.QSWorkspaceStatus = {
  refresh: qsRefreshWorkspaceStatus,
  apply: qsApplyWorkspaceStatus,
  recalculateFromSidebar: qsRecalculateReadinessFromSidebar
}

document.addEventListener('qs:workspace-data-changed', (event) => {
  const detail = (event && event.detail) || {}
  const delayMs = Number(detail.delayMs || 120)
  qsRefreshWorkspaceStatus({ delayMs: Number.isFinite(delayMs) ? delayMs : 120 })
})

document.addEventListener('qs:bulk-validation-complete', () => {
  qsRefreshWorkspaceStatus({ delayMs: 120 })
})

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

function getQuickstartUpdateCommand (info) {
  const branch = String(info?.branch || 'master')
  if (branch === 'master') return 'git pull && pip install -r requirements.txt'
  if (branch === 'develop') return 'git fetch && git reset --hard kometa-team/develop && pip install -r requirements.txt'
  return `git fetch && git checkout ${branch} && pip install -r requirements.txt`
}

function renderQuickstartUpdateAlert (info) {
  const existingAlerts = document.querySelectorAll('[data-qs-update-alert]')
  existingAlerts.forEach(el => el.remove())
  document.querySelectorAll('[data-qs-update-alert-spacer]').forEach(el => el.remove())

  if (!info || !info.update_available) return

  const anchor = document.querySelector('[data-qs-update-alert-anchor]') || document.querySelector('.early-warning')
  const wrapper = anchor?.parentElement || document.querySelector('.qs-content-wrapper')
  if (!wrapper) return

  const alert = document.createElement('div')
  alert.className = 'alert alert-danger text-center qs-wide-alert'
  alert.id = 'quickstart-update-alert'
  alert.dataset.qsUpdateAlert = 'true'
  alert.setAttribute('role', 'alert')

  const icon = document.createElement('i')
  icon.className = 'bi bi-arrow-up-circle'
  alert.append(icon, document.createTextNode(' A new version of Quickstart ('))

  const version = document.createElement('strong')
  version.textContent = info.remote_version || 'unknown'
  alert.append(version, document.createTextNode(') is available!'))

  const runningOn = String(info.running_on || '')
  const branch = String(info.branch || 'master')
  alert.append(document.createElement('br'), document.createElement('br'))

  if (runningOn === 'Docker') {
    alert.append(document.createTextNode('Since you are running Quickstart inside a Docker container, update it as you normally would:'))
    alert.append(document.createElement('br'))
    const code = document.createElement('code')
    code.textContent = `docker pull kometateam/quickstart:${branch}`
    alert.append(code)
  } else if (runningOn.startsWith('Local')) {
    alert.append(document.createTextNode('Update with:'))
    alert.append(document.createElement('br'))
    const code = document.createElement('code')
    code.textContent = getQuickstartUpdateCommand(info)
    alert.append(code, document.createElement('br'))
    const button = document.createElement('button')
    button.id = 'updateQuickstartBtn'
    button.className = 'btn btn-warning mt-2'
    button.dataset.branch = branch
    const buttonIcon = document.createElement('i')
    buttonIcon.className = 'bi bi-arrow-clockwise'
    button.append(buttonIcon, document.createTextNode(' Run Update Now'))
    alert.append(button)
    const result = document.createElement('div')
    result.id = 'updateResult'
    result.className = 'mt-3 text-start small d-none'
    alert.append(result)
  } else {
    const releaseTag = branch === 'develop' ? 'prerelease' : `v${info.remote_version || ''}`
    const buildSuffix = branch === 'develop' && info.buildnum ? `-build${info.buildnum}` : ''
    const platform = runningOn.replace('Frozen-', '')
    const link = document.createElement('a')
    link.href = `https://github.com/Kometa-Team/Quickstart/releases/download/${releaseTag}/Quickstart-v${info.remote_version || ''}${buildSuffix}-${platform}${info.file_ext || ''}`
    link.target = '_blank'
    link.className = 'alert-link'
    link.textContent = 'Click here to update.'
    alert.append(link)
  }

  const spacer = document.createElement('br')
  spacer.dataset.qsUpdateAlertSpacer = 'true'
  wrapper.insertBefore(alert, anchor || wrapper.firstChild)
  wrapper.insertBefore(spacer, anchor || alert.nextSibling)
  bindQuickstartUpdateButtons(alert)
}

async function runQuickstartUpdateCheck (options = {}) {
  const res = await fetch('/check-quickstart-update', { method: 'POST' })
  const data = await res.json()
  if (!res.ok || !data.success) {
    throw new Error(data.message || 'Failed to check for Quickstart updates.')
  }
  renderQuickstartUpdateAlert(data.version_info)
  if (!options.silent && typeof showToast === 'function') {
    if (data.version_info?.update_available) {
      showToast('warning', `Quickstart update available: ${data.version_info.remote_version || 'unknown'}`)
    } else {
      showToast('success', 'Quickstart is up to date.')
    }
  }
  return data.version_info
}

/* eslint-enable no-unused-vars */
function bindQuickstartUpdateButtons (root = document) {
  const buttons = root.querySelectorAll ? root.querySelectorAll('#updateQuickstartBtn') : []
  buttons.forEach(updateBtn => {
    if (updateBtn.dataset.qsUpdateBound === 'true') return
    const resultBox = updateBtn.closest('[data-qs-update-alert]')?.querySelector('#updateResult') || document.getElementById('updateResult')
    if (!resultBox) return
    updateBtn.dataset.qsUpdateBound = 'true'
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
  })
}

document.addEventListener('DOMContentLoaded', () => {
  bindQuickstartUpdateButtons(document)
})

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-qs-update-check]').forEach(button => {
    if (button.dataset.qsUpdateCheckBound === 'true') return
    button.dataset.qsUpdateCheckBound = 'true'
    const statusEl = button.closest('.qs-sidebar-version')?.querySelector('[data-qs-update-check-status]')

    function setUpdateStatus (text, isError) {
      if (!statusEl) return
      statusEl.textContent = text || ''
      statusEl.classList.toggle('text-danger', Boolean(isError))
      statusEl.classList.toggle('text-muted', !isError)
    }

    button.addEventListener('click', async () => {
      button.disabled = true
      const originalHtml = button.innerHTML
      button.innerHTML = '<i class="bi bi-arrow-repeat spin me-1"></i><span class="qs-sidebar-text">Checking...</span>'
      setUpdateStatus('Checking...', false)
      try {
        const info = await runQuickstartUpdateCheck({ silent: true })
        if (info?.update_available) {
          setUpdateStatus(`${info.local_version || 'unknown'} -> ${info.remote_version || 'unknown'}`, false)
          showToast('warning', `Quickstart update available: ${info.remote_version || 'unknown'}`)
        } else {
          setUpdateStatus(`Up to date (${info?.local_version || 'unknown'})`, false)
          showToast('success', 'Quickstart is up to date.')
        }
      } catch (err) {
        const message = err?.message || 'Failed to check for Quickstart updates.'
        setUpdateStatus('Check failed.', true)
        showToast('error', message)
      } finally {
        button.disabled = false
        button.innerHTML = originalHtml
      }
    })
  })
})

document.addEventListener('DOMContentLoaded', () => {
  if (getCurrentTemplateKey() !== '900-final') return
  runQuickstartUpdateCheck({ silent: true }).catch(() => {
    // Keep final-page update checks non-intrusive; manual checks report errors.
  })
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

  async function autoSaveCurrentPageBeforeConfigSwitch (currentConfig) {
    const form = document.getElementById('configForm')
    const path = window.location?.pathname || ''
    if (!form || !path.startsWith('/step/')) {
      return { saved: false, skipped: true }
    }

    const formData = new FormData(form)
    if (currentConfig) {
      formData.set('configSelector', currentConfig)
      formData.set('config_name', currentConfig)
    }

    const response = await fetch(path, {
      method: 'POST',
      body: formData,
      cache: 'no-store',
      credentials: 'same-origin',
      headers: { Accept: 'text/html' }
    })
    const text = await response.text()
    if (!response.ok || text.includes('Invalid values:')) {
      throw new Error('Current page could not be saved. Fix validation errors before switching configs.')
    }
    return { saved: true, skipped: false }
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
      confirmBtn.textContent = 'Saving...'
      window.QS_SWITCHING_CONFIG = true

      try {
        if (typeof showNavigationLoadingOverlay === 'function') {
          showNavigationLoadingOverlay('config-switch')
        }
        await autoSaveCurrentPageBeforeConfigSwitch(current)
        confirmBtn.textContent = 'Switching...'
        const res = await fetch('/switch-config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: target })
        })
        const data = await res.json()
        if (!res.ok || !data.success) {
          throw new Error(data.message || 'Failed to switch configs.')
        }
        if (badgeBtn) {
          badgeBtn.dataset.current = data.name || target
        }
        if (data.workspace_status && typeof qsApplyWorkspaceStatus === 'function') {
          qsApplyWorkspaceStatus(Object.assign({ success: true, config_name: data.name || target }, data.workspace_status))
        } else {
          qsRefreshWorkspaceStatus({ immediate: true, configName: data.name || target })
        }
        showToast('success', `Switched to config "${data.name}".`)
        setTimeout(() => window.location.reload(), 150)
      } catch (err) {
        window.QS_SWITCHING_CONFIG = false
        confirmBtn.disabled = false
        confirmBtn.textContent = 'Switch'
        if (typeof hideNavigationLoadingOverlay === 'function') {
          hideNavigationLoadingOverlay()
        }
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

document.addEventListener('DOMContentLoaded', () => {
  const viewportQuery = window.matchMedia('(min-width: 800px)')
  const rootEl = document.documentElement
  const sidebarStorageKey = 'qs_sidebar_collapsed'
  let sidebarBound = false
  const mainSlotSelector = '[data-qs-workspace-slot]'
  const modalPanelSelectors = [
    '#supportInfoModal',
    '#quickstartSettingsModal',
    '#fontPickerModal',
    '#zoomPreviewModal',
    '#stop-kometa-modal',
    '[id$="-overlay-toolbox-help-modal"]',
    '[id$="-overlay-canvas-modal"]',
    '[id^="logscan-"][id$="-modal"]'
  ]

  let scheduledRefresh = null

  function isMobileViewport () {
    return !viewportQuery.matches
  }

  function applyViewportFlag () {
    rootEl.dataset.qsViewport = isMobileViewport() ? 'mobile' : 'desktop'
  }

  function setupSidebarToggle () {
    const section = document.querySelector('.qs-workspace-section')
    const toggleBtn = document.getElementById('qs-sidebar-toggle')
    if (!section || !toggleBtn) return

    function setSidebarState (collapsed, persist) {
      const shouldCollapse = Boolean(collapsed) && !isMobileViewport()
      section.dataset.qsSidebar = shouldCollapse ? 'collapsed' : 'expanded'
      toggleBtn.setAttribute('aria-expanded', shouldCollapse ? 'false' : 'true')
      toggleBtn.title = shouldCollapse ? 'Expand sidebar' : 'Collapse sidebar'
      if (persist) {
        window.localStorage.setItem(sidebarStorageKey, shouldCollapse ? '1' : '0')
      }
    }

    if (!sidebarBound) {
      sidebarBound = true
      toggleBtn.addEventListener('click', () => {
        const isCollapsed = section.dataset.qsSidebar === 'collapsed'
        setSidebarState(!isCollapsed, true)
      })
    }

    const saved = window.localStorage.getItem(sidebarStorageKey) === '1'
    setSidebarState(saved, false)
  }

  function moveWorkspaceContentIntoSlot () {
    const section = document.querySelector('.qs-workspace-section')
    if (!section) return
    const shell = Array.from(section.children).find(child =>
      child.classList && child.classList.contains('qs-workspace-shell')
    )
    const slot = section.querySelector(mainSlotSelector)
    if (!shell || !slot) return
    if (slot.dataset.qsHydrated === 'true') return

    let node = shell.nextSibling
    while (node) {
      const next = node.nextSibling

      if (node.nodeType === window.Node.ELEMENT_NODE) {
        const el = node
        const skip =
          el.classList.contains('modal') ||
          el.tagName === 'SCRIPT' ||
          el.classList.contains('page-nav-divider')

        if (!skip) {
          slot.appendChild(el)
        }
      }

      node = next
    }

    slot.dataset.qsHydrated = 'true'
  }

  function extractTableHeaders (table) {
    const headers = Array.from(table.querySelectorAll('thead th')).map((header, index) => {
      const text = String(header.textContent || '').replace(/\s+/g, ' ').trim()
      return text || `Column ${index + 1}`
    })
    return headers
  }

  function annotateTableCells (table) {
    const headers = extractTableHeaders(table)
    if (!headers.length) return

    const rows = table.querySelectorAll('tbody tr, tfoot tr')
    rows.forEach(row => {
      const cells = Array.from(row.children).filter(cell => cell.tagName === 'TD')
      cells.forEach((cell, index) => {
        if (!cell.dataset.label || cell.dataset.labelSource === 'auto') {
          cell.dataset.label = headers[index] || headers[headers.length - 1] || `Column ${index + 1}`
          cell.dataset.labelSource = 'auto'
        }
      })
    })
  }

  function applyStickyFirstColumnHints () {
    const explicit = document.querySelectorAll('.table-responsive[data-qs-sticky-first="true"]')
    explicit.forEach(wrapper => {
      wrapper.dataset.stickyFirst = 'true'
    })

    const finalWrappers = document.querySelectorAll('#validation-status-collapse .table-responsive, #run-progress .table-responsive')
    finalWrappers.forEach(wrapper => {
      wrapper.dataset.stickyFirst = 'true'
    })
  }

  function applyTableMode () {
    const wrappers = document.querySelectorAll('.qs-workspace-main-panel .table-responsive')
    const useCardMode = isMobileViewport()

    wrappers.forEach(wrapper => {
      if (wrapper.classList.contains('qs-table-no-cards')) return

      wrapper.classList.toggle('qs-table-card-mode', useCardMode)

      const table = wrapper.querySelector('table')
      if (!table) return
      annotateTableCells(table)
    })

    applyStickyFirstColumnHints()
  }

  function applyMobilePanels () {
    document.querySelectorAll(modalPanelSelectors.join(',')).forEach(modal => {
      modal.classList.add('qs-mobile-panel-target')
    })
  }

  function refreshLayoutState () {
    const hasWorkspace = Boolean(document.querySelector('.qs-workspace-section'))
    document.body.classList.toggle('qs-has-workspace', hasWorkspace)
    applyViewportFlag()
    setupSidebarToggle()
    moveWorkspaceContentIntoSlot()
    applyTableMode()
    applyMobilePanels()
  }

  function scheduleRefresh () {
    if (scheduledRefresh) return
    scheduledRefresh = requestAnimationFrame(() => {
      scheduledRefresh = null
      refreshLayoutState()
    })
  }

  refreshLayoutState()
  viewportQuery.addEventListener('change', refreshLayoutState)
  window.addEventListener('resize', scheduleRefresh, { passive: true })

  const observer = new MutationObserver(scheduleRefresh)
  observer.observe(document.body, { childList: true, subtree: true, attributes: true })
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
