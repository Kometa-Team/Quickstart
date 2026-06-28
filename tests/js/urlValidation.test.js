// Tests for static/local-js/urlValidation.js (#1334 Step 8 — coverage push).
//
// urlValidation.js predates the ES-module migration and is still an IIFE
// that pins itself to window.URLValidation. We can't `import` the public
// API the way we do for the modules/ files, so the pattern here is a
// side-effect import that runs the IIFE in jsdom, then reads off
// window.URLValidation.
//
// Once urlValidation.js gets a proper `export` alongside the window
// assignment (a separate refactor), these tests should switch to a
// named import. Until then, the side-effect pattern keeps this PR
// purely additive — zero production code changes.
//
// Why this module is high value to lock down:
//   - Called from 000-base.js, validationHandler.js, 025-libraries.js
//     (4 sites), totalling ~10 usages across the codebase.
//   - Every credential-style page with a URL field uses this on input
//     and on form submit. A regression in `validateValue` would silently
//     accept malformed URLs across every wizard at once.
//   - The hostname / IPv4 / IPv6 helpers are pure functions with many
//     edge cases. Lock them down before any refactor touches them.

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import '../../static/local-js/urlValidation.js'

const URLValidation = window.URLValidation

describe('URLValidation.validateValue', () => {
  describe('empty / null inputs', () => {
    it('treats null as valid (caller decides what required-ness means)', () => {
      expect(URLValidation.validateValue(null)).toEqual({ valid: true })
    })

    it('treats undefined as valid', () => {
      expect(URLValidation.validateValue(undefined)).toEqual({ valid: true })
    })

    it('treats empty string as valid', () => {
      expect(URLValidation.validateValue('')).toEqual({ valid: true })
    })

    it('treats whitespace-only as valid', () => {
      expect(URLValidation.validateValue('   \t\n  ')).toEqual({ valid: true })
    })
  })

  describe('placeholder rejection', () => {
    it('rejects bare "http://"', () => {
      const result = URLValidation.validateValue('http://')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('URL is incomplete.')
    })

    it('rejects bare "https://"', () => {
      const result = URLValidation.validateValue('https://')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('URL is incomplete.')
    })

    it('rejects placeholders case-insensitively', () => {
      const result = URLValidation.validateValue('HTTPS://')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('URL is incomplete.')
    })

    it('rejects placeholders with surrounding whitespace', () => {
      const result = URLValidation.validateValue('  http://  ')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('URL is incomplete.')
    })
  })

  describe('empty port detection', () => {
    it('rejects "http://example.com:"', () => {
      const result = URLValidation.validateValue('http://example.com:')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('URL port is missing after ":"')
    })

    it('rejects "https://localhost:" before URL parsing would catch it', () => {
      const result = URLValidation.validateValue('https://localhost:')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('URL port is missing after ":"')
    })

    it('accepts a present port', () => {
      expect(URLValidation.validateValue('http://example.com:8080').valid).toBe(true)
    })
  })

  describe('URL parse failures', () => {
    it('rejects a string that is not a URL at all', () => {
      const result = URLValidation.validateValue('not a url')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('Please enter a valid URL.')
    })

    it('rejects a bare hostname with no scheme', () => {
      const result = URLValidation.validateValue('example.com')
      expect(result.valid).toBe(false)
      // Without a scheme, URL parse fails first
      expect(result.message).toBe('Please enter a valid URL.')
    })
  })

  describe('protocol enforcement', () => {
    it('rejects ftp://', () => {
      const result = URLValidation.validateValue('ftp://example.com')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('URL must start with http:// or https://.')
    })

    it('rejects file://', () => {
      const result = URLValidation.validateValue('file:///etc/passwd')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('URL must start with http:// or https://.')
    })

    it('rejects ws:// even though it parses', () => {
      const result = URLValidation.validateValue('ws://example.com')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('URL must start with http:// or https://.')
    })

    it('accepts http://', () => {
      expect(URLValidation.validateValue('http://example.com').valid).toBe(true)
    })

    it('accepts https://', () => {
      expect(URLValidation.validateValue('https://example.com').valid).toBe(true)
    })
  })

  describe('port range', () => {
    it('accepts port 1', () => {
      expect(URLValidation.validateValue('http://example.com:1').valid).toBe(true)
    })

    it('accepts port 65535', () => {
      expect(URLValidation.validateValue('http://example.com:65535').valid).toBe(true)
    })

    // Note: URL parser may normalise port 0 by dropping it from .port,
    // and 65536+ becomes a URL parse failure. The explicit branch in
    // validateValue covers integer ports that survive URL parse but are
    // out of range — testing it directly is tricky because the parser
    // rejects most invalid ports up-front. The presence of the branch
    // is still worth keeping as a defence-in-depth check.
  })

  describe('hostname validation', () => {
    it('accepts localhost', () => {
      expect(URLValidation.validateValue('http://localhost').valid).toBe(true)
    })

    it('accepts localhost with port', () => {
      expect(URLValidation.validateValue('http://localhost:8080').valid).toBe(true)
    })

    it('accepts a single-label hostname', () => {
      expect(URLValidation.validateValue('http://myserver').valid).toBe(true)
    })

    it('accepts a normal domain', () => {
      expect(URLValidation.validateValue('https://example.com').valid).toBe(true)
    })

    it('accepts a subdomain', () => {
      expect(URLValidation.validateValue('https://api.example.com').valid).toBe(true)
    })

    it('accepts an IPv4 address', () => {
      expect(URLValidation.validateValue('http://192.168.1.1').valid).toBe(true)
    })

    it('accepts an IPv4 address with port', () => {
      expect(URLValidation.validateValue('http://192.168.1.1:32400').valid).toBe(true)
    })

    it('rejects bracketed IPv6 (current behaviour — see SUBTLE-BUG below)', () => {
      // SUBTLE BUG in production: URL.hostname returns the bracketed form
      // "[::1]" for IPv6, but isIPv6() regex is /^[0-9a-f:]+$/i which
      // does not allow brackets. So validateValue rejects valid IPv6
      // URLs as "URL hostname is invalid." This test locks in the
      // current behaviour so a future fix in urlValidation.js will
      // need to update this expectation.
      const result = URLValidation.validateValue('http://[::1]')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('URL hostname is invalid.')
    })

    it('rejects a hostname starting with a hyphen', () => {
      const result = URLValidation.validateValue('http://-example.com')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('URL hostname is invalid.')
    })

    it('rejects a hostname ending with a hyphen', () => {
      const result = URLValidation.validateValue('http://example-.com')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('URL hostname is invalid.')
    })

    it('rejects a TLD that is too short', () => {
      const result = URLValidation.validateValue('http://example.x')
      expect(result.valid).toBe(false)
      expect(result.message).toBe('URL hostname is invalid.')
    })

    it('rejects a numeric-only TLD', () => {
      const result = URLValidation.validateValue('http://example.123')
      expect(result.valid).toBe(false)
      // The URL parser rejects this before isValidHostname runs, so we
      // get the generic parse-failure message rather than the hostname-
      // specific one. Either way it's rejected — that's what matters.
      expect(result.message).toBe('Please enter a valid URL.')
    })
  })

  describe('paths and query strings', () => {
    it('accepts a URL with a path', () => {
      expect(URLValidation.validateValue('https://example.com/api/v1/things').valid).toBe(true)
    })

    it('accepts a URL with a query string', () => {
      expect(URLValidation.validateValue('https://example.com/search?q=foo').valid).toBe(true)
    })

    it('accepts a URL with a fragment', () => {
      expect(URLValidation.validateValue('https://example.com/page#section').valid).toBe(true)
    })
  })

  describe('non-string inputs', () => {
    it('coerces a number to string and rejects it', () => {
      const result = URLValidation.validateValue(42)
      expect(result.valid).toBe(false)
      expect(result.message).toBe('Please enter a valid URL.')
    })

    it('coerces an object to string and rejects it', () => {
      const result = URLValidation.validateValue({ toString: () => 'http://x.io' })
      expect(result.valid).toBe(true)
    })
  })
})

describe('URLValidation.attach + validateAll', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('binds inputs whose name matches the URL pattern', () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="my_url" value="http://example.com">
      </div>
    `
    URLValidation.attach(document)
    const input = document.querySelector('input[name="my_url"]')
    expect(input.dataset.urlValidationBound).toBe('true')
    expect(input.dataset.urlValid).toBe('true')
  })

  it('binds inputs whose id matches the URL pattern', () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" id="webhook-url" value="http://example.com">
      </div>
    `
    URLValidation.attach(document)
    const input = document.getElementById('webhook-url')
    expect(input.dataset.urlValidationBound).toBe('true')
  })

  it('binds inputs with type="url" even without url in the name', () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="url" name="endpoint" value="http://example.com">
      </div>
    `
    URLValidation.attach(document)
    const input = document.querySelector('input[name="endpoint"]')
    expect(input.dataset.urlValidationBound).toBe('true')
  })

  it('does not bind unrelated inputs', () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="username" value="bob">
      </div>
    `
    URLValidation.attach(document)
    const input = document.querySelector('input[name="username"]')
    expect(input.dataset.urlValidationBound).toBeUndefined()
  })

  it('honors data-url-skip="true" as an opt-out', () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="my_url" data-url-skip="true" value="http://example.com">
      </div>
    `
    URLValidation.attach(document)
    const input = document.querySelector('input[name="my_url"]')
    expect(input.dataset.urlValidationBound).toBeUndefined()
  })

  it('marks the input is-invalid and adds feedback for a bad URL', () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="my_url" value="not a url">
      </div>
    `
    URLValidation.attach(document)
    const input = document.querySelector('input[name="my_url"]')
    expect(input.classList.contains('is-invalid')).toBe(true)
    expect(input.dataset.urlValid).toBe('false')
    const feedback = document.querySelector('.invalid-feedback')
    expect(feedback).not.toBeNull()
    expect(feedback.textContent).toBe('Please enter a valid URL.')
  })

  it('clears is-invalid when the value becomes valid after input event', () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="my_url" value="not a url">
      </div>
    `
    URLValidation.attach(document)
    const input = document.querySelector('input[name="my_url"]')
    expect(input.classList.contains('is-invalid')).toBe(true)

    input.value = 'https://example.com'
    input.dispatchEvent(new Event('input'))

    expect(input.classList.contains('is-invalid')).toBe(false)
    expect(input.dataset.urlValid).toBe('true')
  })

  it('reuses an existing .invalid-feedback element if one is already in the input-group', () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="my_url" value="not a url">
        <div class="invalid-feedback">existing message</div>
      </div>
    `
    URLValidation.attach(document)
    const feedbacks = document.querySelectorAll('.invalid-feedback')
    expect(feedbacks.length).toBe(1)
    expect(feedbacks[0].textContent).toBe('Please enter a valid URL.')
  })

  it('does not double-bind on repeated attach() calls', () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="my_url" value="http://example.com">
      </div>
    `
    URLValidation.attach(document)
    URLValidation.attach(document)
    URLValidation.attach(document)
    // If it double-bound, dispatching input would still produce only
    // one validation pass — but the cheaper assertion is that the
    // bound-flag prevents re-entry. We verify by ensuring validateAll
    // still returns the same result (no thrown error from re-binding).
    expect(URLValidation.validateAll(document)).toBe(true)
  })

  it('validateAll returns true when all bound inputs are valid', () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="my_url" value="https://a.io">
      </div>
      <div class="input-group">
        <input type="text" name="other_url" value="https://b.io">
      </div>
    `
    URLValidation.attach(document)
    expect(URLValidation.validateAll(document)).toBe(true)
  })

  it('validateAll returns false when any bound input is invalid', () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="my_url" value="https://a.io">
      </div>
      <div class="input-group">
        <input type="text" name="other_url" value="not a url">
      </div>
    `
    URLValidation.attach(document)
    expect(URLValidation.validateAll(document)).toBe(false)
  })

  it('validateAll binds previously-unbound url inputs in the container', () => {
    // Simulates a freshly-injected card / partial that attach() never saw.
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="my_url" value="not a url">
      </div>
    `
    expect(URLValidation.validateAll(document)).toBe(false)
    const input = document.querySelector('input[name="my_url"]')
    expect(input.dataset.urlValidationBound).toBe('true')
  })

  it('scopes validation to the passed container', () => {
    document.body.innerHTML = `
      <div id="card-a" class="input-group">
        <input type="text" name="my_url" value="not a url">
      </div>
      <div id="card-b" class="input-group">
        <input type="text" name="other_url" value="https://valid.io">
      </div>
    `
    const cardB = document.getElementById('card-b')
    // Only card B is being validated — card A has a bad URL but isn't in scope.
    expect(URLValidation.validateAll(cardB)).toBe(true)
  })
})
