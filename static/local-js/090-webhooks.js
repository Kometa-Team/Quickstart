import { refreshValidationCallout } from './modules/validationPageBase.js'

const validatedWebhooks = {}
const validatedAtInput = document.getElementById('webhooks_validated_at')
let webhooksTouched = false
let initialValidated = false
let initialConfigured = false

function isWebhookConfigured (selectElement) {
  if (!selectElement) return false
  const value = (selectElement.value || '').toString().trim().toLowerCase()
  if (!value || value === 'none') return false
  if (value === 'custom') {
    const customInputId = selectElement.id + '_custom'
    const customUrl = document.getElementById(customInputId)?.querySelector('input.custom-webhook-url')?.value
    return Boolean(customUrl && customUrl.trim())
  }
  return true
}

function hasConfiguredWebhooks () {
  const selects = document.querySelectorAll('select.form-select')
  return Array.from(selects).some(selectElement => isWebhookConfigured(selectElement))
}

function setWebhookValidated (state, webhookType = null) {
  document.getElementById('webhooks_validated').value = state ? 'true' : 'false'
  refreshValidationCallout('webhooks_validated')

  if (webhookType) {
    // Enable the validate button if the URL changes and validation is false
    const validateButton = document.querySelector(`#webhooks_${webhookType}_custom .validate-button`)
    if (validateButton) {
      validateButton.disabled = state
    }
  }
}

function showCustomInput (selectElement, isValidated) {
  const customInputId = selectElement.id + '_custom'
  console.log(`showCustomInput called for: ${selectElement.id}, isValidated: ${isValidated}`)
  const customInput = document.getElementById(customInputId)
  if (!customInput) {
    console.warn(`Custom input container not found for: ${customInputId}`)
    return
  }
  if (selectElement.value === 'custom') {
    customInput.style.display = 'block'
    if (isValidated === true) {
      setWebhookValidated(true, selectElement.id)
    } else {
      setWebhookValidated(false, selectElement.id)
    }
  } else {
    customInput.style.display = 'none'
    validatedWebhooks[selectElement.id] = true
    updateValidationState()
  }
}

function updateValidationState () {
  const anyConfigured = hasConfiguredWebhooks()
  console.log('Validation State Updated:', validatedWebhooks, `Any Configured: ${anyConfigured}`)
  if (!webhooksTouched && !initialValidated && !initialConfigured) {
    setWebhookValidated(false)
    return
  }
  setWebhookValidated(anyConfigured)
  if (validatedAtInput) {
    if (anyConfigured) {
      if (!validatedAtInput.value) {
        validatedAtInput.value = new Date().toISOString()
      }
    } else {
      validatedAtInput.value = ''
    }
  }
}

const isValidated = document.getElementById('webhooks_validated').value.toLowerCase() === 'true'
initialValidated = isValidated
console.log('Page Load - Is Validated:', isValidated)

document.querySelectorAll('select.form-select').forEach(selectElement => {
  const customInputId = selectElement.id + '_custom'
  const customUrlEl = document.getElementById(customInputId)?.querySelector('input.custom-webhook-url')
  const customUrl = customUrlEl ? customUrlEl.value : ''

  showCustomInput(selectElement, isValidated)

  if (selectElement.value === 'custom' && customUrl) {
    validatedWebhooks[selectElement.id] = isValidated
    console.log(`Custom webhook found: ${selectElement.id}, URL: ${customUrl}`)
  } else {
    validatedWebhooks[selectElement.id] = isValidated
  }
})
initialConfigured = hasConfiguredWebhooks()

document.querySelectorAll('.validate-button').forEach(button => {
  button.disabled = isValidated === true
  button.addEventListener('click', () => {
    const webhookKey = button.dataset.webhookKey
    if (webhookKey) validateWebhook(webhookKey)
  })
})

// The select dropdown handles three concerns when it changes:
//   1. showCustomInput reveals/hides the custom-URL input panel
//      depending on whether 'custom' is selected.
//   2. markTouched updates the validation state callout.
// Both fire on every 'change' event. (Previously #1 was wired via the
// inline onchange="showCustomInput(this)" attribute, which was broken
// for module-scoped scripts -- the function wasn't on window so the
// inline call silently no-op'd, leaving the custom-URL panel hidden
// when the user picked 'Custom' from the dropdown.)
document.querySelectorAll('select.form-select').forEach((selectElement) => {
  selectElement.addEventListener('change', () => showCustomInput(selectElement, false))
})

// The custom-URL input fires setWebhookValidated(false, ...) on every
// keystroke -- typing a new URL invalidates whatever previous
// validation succeeded. (Previously wired via inline oninput=.)
document.querySelectorAll('input.custom-webhook-url').forEach((input) => {
  input.addEventListener('input', () => {
    const webhookKey = input.dataset.webhookKey
    if (webhookKey) setWebhookValidated(false, webhookKey)
  })
})

document.querySelectorAll('select.form-select, input.custom-webhook-url').forEach((element) => {
  const markTouched = (event) => {
    if (event && event.isTrusted === false) return
    webhooksTouched = true
    updateValidationState()
  }
  element.addEventListener('change', markTouched)
  element.addEventListener('input', markTouched)
})

updateValidationState()

// Debugging for navigation actions
document.getElementById('configForm').addEventListener('submit', function (event) {
  const actionType = event.submitter?.getAttribute('onclick')?.includes('loading') ? event.submitter.innerText.trim() : 'unknown'
  console.log(`Form Submitted - Action: ${actionType}`)

  document.querySelectorAll('select.form-select').forEach(selectElement => {
    if (selectElement.value === 'custom') {
      const customInputId = selectElement.id + '_custom'
      const customUrlEl = document.getElementById(customInputId)?.querySelector('input.custom-webhook-url')
      const customUrl = customUrlEl ? customUrlEl.value : ''
      if (customUrl) {
        console.log(`Serializing custom webhook for dropdown: ${selectElement.id}, URL: ${customUrl}`)
        const option = document.createElement('option')
        option.value = customUrl
        option.textContent = customUrl
        option.selected = true
        selectElement.appendChild(option)
        selectElement.value = customUrl
      } else {
        console.log(`Custom webhook dropdown ${selectElement.id} has no URL to serialize.`)
      }
    }
  })
})

function validateWebhook (webhookType) {
  const customContainer = document.getElementById('webhooks_' + webhookType + '_custom')
  if (!customContainer) return
  const inputGroup = customContainer.querySelector('.input-group')
  if (!inputGroup) return
  const webhookUrlEl = inputGroup.querySelector('input.custom-webhook-url')
  const webhookUrl = webhookUrlEl ? webhookUrlEl.value : ''
  // .validation-message is a sibling of .input-group, both children of customContainer
  const validationMessage = customContainer.querySelector('.validation-message')
  const validateButton = inputGroup.querySelector('.validate-button')
  const webhookTypeFormatted = webhookType.replace(/_/g, ' ').replace(/\b\w/g, function (l) { return l.toUpperCase() })

  webhooksTouched = true
  console.log(`Validating webhook: ${webhookType}, URL: ${webhookUrl}`)

  showSpinner(webhookType)
  if (validationMessage) {
    validationMessage.innerHTML = '<div class="alert alert-info" role="alert">Validating...</div>'
    validationMessage.style.display = ''
  }

  fetch('/validate_webhook', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      webhook_url: webhookUrl,
      message: 'Kometa Quickstart Test message for ' + webhookTypeFormatted + ' webhook'
    })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        console.log(`Webhook validation successful for: ${webhookType}`)
        hideSpinner(webhookType)
        if (validationMessage) validationMessage.innerHTML = '<div class="alert alert-success" role="alert">' + data.success + '</div>'
        if (validateButton) validateButton.disabled = true
        validatedWebhooks['webhooks_' + webhookType] = true
      } else {
        console.error(`Webhook validation failed for: ${webhookType}, Error: ${data.error}`)
        hideSpinner(webhookType)
        if (validationMessage) validationMessage.innerHTML = '<div class="alert alert-danger" role="alert">' + data.error + '</div>'
        validatedWebhooks['webhooks_' + webhookType] = false
      }
      updateValidationState()
    })
    .catch((error) => {
      console.error(`Error during webhook validation for: ${webhookType}`, error)
      hideSpinner(webhookType)
      if (validationMessage) validationMessage.innerHTML = '<div class="alert alert-danger" role="alert">An error occurred. Please try again.</div>'
      validatedWebhooks['webhooks_' + webhookType] = false
      updateValidationState()
    })
}
