/* global */

const URLValidation = (() => {
  const urlKeyPattern = /(^|[_-])url([_-]|$)/i
  const placeholderValues = new Set(['http://', 'https://'])

  function isUrlField (input) {
    if (!input) return false
    if (input.dataset && input.dataset.urlSkip === 'true') return false
    if (input.type && input.type.toLowerCase() === 'url') return true
    const key = (input.name || input.id || '').toLowerCase()
    return urlKeyPattern.test(key)
  }

  function isPlaceholder (value) {
    return placeholderValues.has(String(value || '').trim().toLowerCase())
  }

  function hasEmptyPort (text) {
    const match = String(text).match(/^[a-z][a-z0-9+.-]*:\/\/([^/?#]*)/i)
    if (!match) return false
    const authority = match[1]
    return authority.endsWith(':')
  }

  function validateValue (value) {
    if (value == null) return { valid: true }
    const text = String(value).trim()
    if (!text) return { valid: true }
    if (isPlaceholder(text)) return { valid: false, message: 'URL is incomplete.' }
    if (hasEmptyPort(text)) return { valid: false, message: 'URL port is missing after ":"' }
    let parsed
    try {
      parsed = new URL(text)
    } catch (err) {
      return { valid: false, message: 'Please enter a valid URL.' }
    }
    if (!parsed.protocol || !['http:', 'https:'].includes(parsed.protocol)) {
      return { valid: false, message: 'URL must start with http:// or https://.' }
    }
    if (!parsed.hostname) {
      return { valid: false, message: 'URL is missing a hostname.' }
    }
    if (parsed.port) {
      const portNum = Number(parsed.port)
      if (!Number.isInteger(portNum) || portNum < 1 || portNum > 65535) {
        return { valid: false, message: 'URL port must be between 1 and 65535.' }
      }
    }
    if (!isValidHostname(parsed.hostname)) {
      return { valid: false, message: 'URL hostname is invalid.' }
    }
    return { valid: true }
  }

  function ensureFeedback (input) {
    const parent = input.closest('.input-group') || input.parentElement
    if (!parent) return null
    let feedback = parent.querySelector('.invalid-feedback')
    if (!feedback) {
      feedback = document.createElement('div')
      feedback.className = 'invalid-feedback'
      parent.appendChild(feedback)
    }
    return feedback
  }

  function applyResult (input, result) {
    if (!input) return
    if (result.valid) {
      input.classList.remove('is-invalid')
      input.dataset.urlValid = 'true'
      const feedback = ensureFeedback(input)
      if (feedback) feedback.textContent = ''
      return
    }
    input.classList.add('is-invalid')
    input.dataset.urlValid = 'false'
    const feedback = ensureFeedback(input)
    if (feedback) feedback.textContent = result.message || 'Invalid URL.'
  }

  function bindInput (input) {
    if (!input || input.dataset.urlValidationBound === 'true') return
    input.dataset.urlValidationBound = 'true'
    const validate = () => {
      const result = validateValue(input.value)
      applyResult(input, result)
      return result.valid
    }
    input.addEventListener('input', validate)
    input.addEventListener('blur', validate)
    validate()
  }

  function attach (container = document) {
    const inputs = Array.from(container.querySelectorAll('input[type="text"], input[type="url"], input[type="search"], textarea'))
    inputs.forEach(input => {
      if (isUrlField(input)) {
        bindInput(input)
      }
    })
  }

  function validateAll (container = document) {
    let allValid = true
    const inputs = Array.from(container.querySelectorAll('[data-url-validation-bound="true"]'))
    inputs.forEach(input => {
      const result = validateValue(input.value)
      applyResult(input, result)
      if (!result.valid) allValid = false
    })
    return allValid
  }

  return {
    attach,
    validateAll
  }
})()

window.URLValidation = URLValidation

function isValidHostname (hostname) {
  const host = String(hostname || '').toLowerCase()
  if (!host) return false
  if (host === 'localhost') return true
  if (host.startsWith('.') || host.endsWith('.')) return false
  if (host.includes('..')) return false
  if (isIPv4(host) || isIPv6(host)) return true
  const labels = host.split('.')
  for (const label of labels) {
    if (!label.length || label.length > 63) return false
    if (label.startsWith('-') || label.endsWith('-')) return false
    if (!/^[a-z0-9-]+$/.test(label)) return false
  }
  if (labels.length > 1) {
    const tld = labels[labels.length - 1]
    if (tld.length < 2 || tld.length > 63) return false
    if (!/[a-z]/.test(tld)) return false
  }
  return true
}

function isIPv4 (host) {
  const parts = host.split('.')
  if (parts.length !== 4) return false
  return parts.every(part => {
    if (!/^\d+$/.test(part)) return false
    const num = Number(part)
    return num >= 0 && num <= 255
  })
}

function isIPv6 (host) {
  return /^[0-9a-f:]+$/i.test(host) && host.includes(':')
}
