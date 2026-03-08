/* global */

const PathValidation = (() => {
  let rules = []
  let meta = { platform: 'linux', is_docker: false }
  let loadPromise = null

  const WINDOWS_INVALID_CHARS = /[<>:"|?*]/
  const WINDOWS_RESERVED = new Set([
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
  ])

  function loadRules () {
    if (loadPromise) return loadPromise
    loadPromise = fetch('/path-validation-rules', { credentials: 'same-origin' })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data && Array.isArray(data.rules)) {
          rules = data.rules
          meta = {
            platform: data.platform || meta.platform,
            is_docker: Boolean(data.is_docker)
          }
        }
        return { rules, meta }
      })
      .catch(() => ({ rules, meta }))
    return loadPromise
  }

  function ruleForInput (input) {
    const explicit = input.dataset && input.dataset.pathRule
    if (explicit) {
      return rules.find(r => r.id === explicit)
    }
    const name = input.name || ''
    return rules.find(r => name === r.id || name.endsWith(`-${r.id}`))
  }

  function isWindowsAbsolute (value) {
    return /^[A-Za-z]:[\\/]/.test(value) || value.startsWith('\\\\') || value.startsWith('//')
  }

  function isAbsolute (value, platform) {
    if (platform === 'windows') return isWindowsAbsolute(value)
    return value.startsWith('/')
  }

  function hasControlChars (value) {
    for (let i = 0; i < value.length; i++) {
      if (value.charCodeAt(i) < 32) return true
    }
    return false
  }

  function invalidWindowsSegment (segment) {
    if (!segment) return false
    if (segment === '.' || segment === '..') return true
    if (segment.endsWith(' ') || segment.endsWith('.')) return true
    const base = segment.split('.')[0].toUpperCase()
    return WINDOWS_RESERVED.has(base)
  }

  function validateValue (value, rule, platform) {
    if (value == null) return { valid: true }
    const str = String(value).trim()
    if (!str) return { valid: true }
    const lowered = str.toLowerCase()
    if (lowered === 'none' || lowered === 'null') {
      return { valid: true }
    }
    if (lowered.includes('\\0') || lowered.includes('\\x00') || lowered.includes('\\u0000')) {
      return { valid: false, message: 'Contains an invalid null sequence.' }
    }

    if (platform !== 'windows' && isWindowsAbsolute(str)) {
      return { valid: false, message: 'Windows-style paths are not valid on Linux/macOS/Docker.' }
    }

    if (!rule.allow_relative && !isAbsolute(str, platform)) {
      return { valid: false, message: 'Path must be absolute.' }
    }

    if (hasControlChars(str)) {
      return { valid: false, message: 'Contains control characters.' }
    }

    if (platform === 'windows') {
      for (let i = 0; i < str.length; i++) {
        const ch = str[i]
        if (WINDOWS_INVALID_CHARS.test(ch)) {
          if (ch === ':' && i === 1 && /^[A-Za-z]:/.test(str)) continue
          return { valid: false, message: 'Contains invalid characters for Windows paths.' }
        }
      }
      const segments = str.split(/[\\/]+/)
      for (const seg of segments) {
        if (invalidWindowsSegment(seg)) {
          return { valid: false, message: 'Contains a reserved or invalid Windows path segment.' }
        }
      }
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

  function insertHintAfter (input, hintEl) {
    let anchor = input.closest('.input-group') || input
    while (anchor && anchor.nextElementSibling) {
      const next = anchor.nextElementSibling
      if (next.classList && next.classList.contains('form-text')) {
        anchor = next
        continue
      }
      if (next.dataset && next.dataset.pathHint) {
        anchor = next
        continue
      }
      break
    }
    anchor.after(hintEl)
  }

  function ensureDockerHint (input, rule) {
    if (!meta.is_docker) return
    const hint = rule && rule.ui && rule.ui.hint_docker
    if (!hint) return
    const parent = input.closest('.input-group') || input.parentElement
    if (!parent) return
    if (parent.dataset.dockerHintAdded) return
    const note = document.createElement('div')
    note.className = 'form-text text-muted'
    note.textContent = hint
    note.dataset.pathHint = 'docker'
    insertHintAfter(input, note)
    parent.dataset.dockerHintAdded = 'true'
  }

  const platformStatusEls = new WeakMap()

  function ensurePlatformStatus (input, rule) {
    if (!input) return null
    if (rule && rule.ui && rule.ui.platform_status === false) return null
    const parent = input.closest('.input-group') || input.parentElement
    if (!parent) return null
    let el = platformStatusEls.get(input)
    if (el) return el

    el = document.createElement('div')
    el.className = 'form-text'
    el.dataset.pathHint = 'platform-status'
    insertHintAfter(input, el)
    platformStatusEls.set(input, el)
    return el
  }

  function applyResult (input, result) {
    if (!input) return
    if (result.valid) {
      input.classList.remove('is-invalid')
      input.dataset.pathValid = 'true'
      const feedback = ensureFeedback(input)
      if (feedback) feedback.textContent = ''
      return
    }
    input.classList.add('is-invalid')
    input.dataset.pathValid = 'false'
    const feedback = ensureFeedback(input)
    if (feedback) feedback.textContent = result.message || 'Invalid path.'
  }

  function buildPlatformLine (label, result) {
    const line = document.createElement('div')
    line.className = result.valid ? 'text-success' : 'text-danger'
    const icon = document.createElement('i')
    icon.className = result.valid
      ? 'bi bi-check-circle-fill me-1'
      : 'bi bi-exclamation-circle-fill me-1'
    line.appendChild(icon)
    const msg = result.valid ? 'OK' : (result.message || 'Invalid')
    line.appendChild(document.createTextNode(`${label}: ${msg}`))
    return line
  }

  function updatePlatformStatus (input, rule) {
    const el = ensurePlatformStatus(input, rule)
    if (!el) return
    const windowsResult = validateValue(input.value, rule, 'windows')
    const posixResult = validateValue(input.value, rule, 'linux')

    el.replaceChildren()
    el.appendChild(buildPlatformLine('Windows', windowsResult))
    el.appendChild(buildPlatformLine('Linux/macOS/Docker', posixResult))
  }

  function bindInput (input, rule) {
    if (!input || input.dataset.pathValidationBound === 'true') return
    input.dataset.pathValidationBound = 'true'
    ensureDockerHint(input, rule)
    const validate = () => {
      const result = validateValue(input.value, rule, meta.platform)
      applyResult(input, result)
      updatePlatformStatus(input, rule)
      return result.valid
    }
    input.addEventListener('input', validate)
    input.addEventListener('blur', validate)
    validate()
  }

  function attach (container = document) {
    return loadRules().then(() => {
      const inputs = Array.from(container.querySelectorAll('input[type="text"], input[type="search"], textarea'))
      inputs.forEach(input => {
        const rule = ruleForInput(input)
        if (rule) bindInput(input, rule)
      })
    })
  }

  function validateAll (container = document) {
    let allValid = true
    const inputs = Array.from(container.querySelectorAll('[data-path-validation-bound="true"]'))
    inputs.forEach(input => {
      const rule = ruleForInput(input)
      if (!rule) return
      const result = validateValue(input.value, rule, meta.platform)
      applyResult(input, result)
      updatePlatformStatus(input, rule)
      if (!result.valid) allValid = false
    })
    return allValid
  }

  function init () {
    return loadRules()
  }

  return {
    init,
    attach,
    validateAll
  }
})()

window.PathValidation = PathValidation
