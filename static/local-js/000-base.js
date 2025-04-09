/* global bootstrap, $ */
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

/* eslint-enable no-unused-vars */
