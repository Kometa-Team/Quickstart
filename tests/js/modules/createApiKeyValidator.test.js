// Tests for static/local-js/modules/createApiKeyValidator.js
// (#1334 Step 6 PR 1).
//
// This factory is the shared replacement for ~9 near-duplicate wizard
// modules. The tests below lock down the full behavioural contract so
// every wizard migration in PR 2 has a safety net.
//
// Pattern follows the existing modules/*.test.js style:
//   - import the factory by name (it's a proper ES module from day 1)
//   - one describe block per behaviour cluster
//   - beforeEach resets document.body and the window-global shims
//
// SHIMS:
//
//   The factory calls showSpinner/hideSpinner as plain globals (legacy
//   pattern inherited from 000-base.js). We stub them as window globals
//   per test and verify call counts where it matters.
//
//   The factory delegates to refreshValidationCallout from
//   validationPageBase.js — that delegate is itself a no-op when
//   window.QSValidationCallouts is undefined, so we don't have to stub
//   anything for it. Where we want to verify refresh DID fire, we stub
//   window.QSValidationCallouts.refresh and assert on it.
//
//   fetch is stubbed per test with vi.stubGlobal('fetch', ...) and
//   restored in afterEach. Don't import fetch — just trust the stub.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApiKeyValidator } from '../../../static/local-js/modules/createApiKeyValidator.js'

function buildBaseHTML ({ keyValue = '', validated = 'false', extraInputs = '' } = {}) {
  return `
    <form id="configForm">
      <input id="test_apikey" type="password" value="${keyValue}">
      <input id="test_validated" type="hidden" value="${validated}">
      <input id="test_validated_at" type="hidden" value="">
      <button id="toggleApikeyVisibility" type="button">
        <i class="bi"></i>
      </button>
      <button id="validateButton" type="button">Validate</button>
      <div id="statusMessage" style="display:none"></div>
      ${extraInputs}
    </form>
  `
}

function defaultConfig (overrides = {}) {
  return {
    fieldId: 'test_apikey',
    validatedFieldId: 'test_validated',
    validatedAtFieldId: 'test_validated_at',
    endpoint: '/validate_test',
    buildPayload: (apiKey) => ({ test_apikey: apiKey }),
    ...overrides
  }
}

beforeEach(() => {
  document.body.innerHTML = ''
  window.showSpinner = vi.fn()
  window.hideSpinner = vi.fn()
  delete window.QSValidationCallouts
})

afterEach(() => {
  vi.unstubAllGlobals()
  delete window.showSpinner
  delete window.hideSpinner
  delete window.QSValidationCallouts
})

describe('createApiKeyValidator config validation', () => {
  it('throws when fieldId is missing', () => {
    document.body.innerHTML = buildBaseHTML()
    expect(() => createApiKeyValidator({
      validatedFieldId: 'test_validated',
      endpoint: '/x',
      buildPayload: () => ({})
    })).toThrow(/fieldId is required/)
  })

  it('throws when validatedFieldId is missing', () => {
    document.body.innerHTML = buildBaseHTML()
    expect(() => createApiKeyValidator({
      fieldId: 'test_apikey',
      endpoint: '/x',
      buildPayload: () => ({})
    })).toThrow(/validatedFieldId is required/)
  })

  it('throws when endpoint is missing', () => {
    document.body.innerHTML = buildBaseHTML()
    expect(() => createApiKeyValidator({
      fieldId: 'test_apikey',
      validatedFieldId: 'test_validated',
      buildPayload: () => ({})
    })).toThrow(/endpoint is required/)
  })

  it('throws when buildPayload is not a function', () => {
    document.body.innerHTML = buildBaseHTML()
    expect(() => createApiKeyValidator({
      fieldId: 'test_apikey',
      validatedFieldId: 'test_validated',
      endpoint: '/x',
      buildPayload: 'not a function'
    })).toThrow(/buildPayload must be a function/)
  })
})

describe('createApiKeyValidator graceful no-op on missing DOM', () => {
  it('returns without throwing when the credential input is absent', () => {
    document.body.innerHTML = '<form id="configForm"></form>'
    expect(() => createApiKeyValidator(defaultConfig())).not.toThrow()
  })

  it('returns without throwing when validatedField is absent', () => {
    document.body.innerHTML = `
      <form id="configForm">
        <input id="test_apikey" type="password">
        <button id="validateButton">Validate</button>
      </form>
    `
    expect(() => createApiKeyValidator(defaultConfig())).not.toThrow()
  })

  it('returns without throwing when validateButton is absent', () => {
    document.body.innerHTML = `
      <form id="configForm">
        <input id="test_apikey" type="password">
        <input id="test_validated" type="hidden" value="false">
      </form>
    `
    expect(() => createApiKeyValidator(defaultConfig())).not.toThrow()
  })
})

describe('createApiKeyValidator initial field state', () => {
  it('switches an empty credential field to type="text" so placeholder shows', () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: '' })
    createApiKeyValidator(defaultConfig())
    expect(document.getElementById('test_apikey').getAttribute('type')).toBe('text')
  })

  it('keeps a populated credential field as type="password"', () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'secret123' })
    createApiKeyValidator(defaultConfig())
    expect(document.getElementById('test_apikey').getAttribute('type')).toBe('password')
  })

  it('treats whitespace-only credential as empty (still password initially, then text)', () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: '   ' })
    createApiKeyValidator(defaultConfig())
    expect(document.getElementById('test_apikey').getAttribute('type')).toBe('text')
  })

  it('disables the validate button when the page loads with validated=true', () => {
    document.body.innerHTML = buildBaseHTML({ validated: 'true' })
    createApiKeyValidator(defaultConfig())
    expect(document.getElementById('validateButton').disabled).toBe(true)
  })

  it('enables the validate button when the page loads with validated=false', () => {
    document.body.innerHTML = buildBaseHTML({ validated: 'false' })
    createApiKeyValidator(defaultConfig())
    expect(document.getElementById('validateButton').disabled).toBe(false)
  })

  it('treats "TRUE" (uppercase) as validated', () => {
    document.body.innerHTML = buildBaseHTML({ validated: 'TRUE' })
    createApiKeyValidator(defaultConfig())
    expect(document.getElementById('validateButton').disabled).toBe(true)
  })
})

describe('createApiKeyValidator reset-on-input', () => {
  it('resets validated field and re-enables button when user types in credential field', () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'old', validated: 'true' })
    createApiKeyValidator(defaultConfig())
    const input = document.getElementById('test_apikey')
    const validated = document.getElementById('test_validated')
    const button = document.getElementById('validateButton')

    expect(validated.value).toBe('true')
    expect(button.disabled).toBe(true)

    input.dispatchEvent(new Event('input'))

    expect(validated.value).toBe('false')
    expect(button.disabled).toBe(false)
  })

  it('clears validated_at timestamp on input', () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'old', validated: 'true' })
    document.getElementById('test_validated_at').value = '2026-01-01T00:00:00Z'
    createApiKeyValidator(defaultConfig())

    document.getElementById('test_apikey').dispatchEvent(new Event('input'))
    expect(document.getElementById('test_validated_at').value).toBe('')
  })

  it('also resets on input for extra fields in additionalFieldIds', () => {
    document.body.innerHTML = buildBaseHTML({
      keyValue: 'old',
      validated: 'true',
      extraInputs: '<input id="test_url" type="text" value="http://x">'
    })
    createApiKeyValidator(defaultConfig({
      additionalFieldIds: ['test_url']
    }))

    document.getElementById('test_url').dispatchEvent(new Event('input'))
    expect(document.getElementById('test_validated').value).toBe('false')
    expect(document.getElementById('validateButton').disabled).toBe(false)
  })

  it('ignores missing extra field ids without throwing', () => {
    document.body.innerHTML = buildBaseHTML({ validated: 'true' })
    expect(() => createApiKeyValidator(defaultConfig({
      additionalFieldIds: ['nonexistent_field']
    }))).not.toThrow()
  })

  it('calls refreshValidationCallout when the field is reset', () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'old', validated: 'true' })
    const refreshSpy = vi.fn()
    window.QSValidationCallouts = { refresh: refreshSpy }

    createApiKeyValidator(defaultConfig())
    document.getElementById('test_apikey').dispatchEvent(new Event('input'))

    expect(refreshSpy).toHaveBeenCalledWith('test_validated')
  })
})

describe('createApiKeyValidator validate click — empty credential', () => {
  it('shows the empty-message and does not call fetch', () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: '' })
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    createApiKeyValidator(defaultConfig())
    document.getElementById('validateButton').click()

    const status = document.getElementById('statusMessage')
    expect(status.textContent).toBe('Please enter an API key.')
    expect(status.style.color).toBe('rgb(234, 134, 143)') // #ea868f as rgb
    expect(status.style.display).toBe('block')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('uses the custom empty message when provided', () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: '' })
    vi.stubGlobal('fetch', vi.fn())

    createApiKeyValidator(defaultConfig({
      messages: { empty: 'Please enter an OMDb API key.' }
    }))
    document.getElementById('validateButton').click()

    expect(document.getElementById('statusMessage').textContent).toBe('Please enter an OMDb API key.')
  })
})

describe('createApiKeyValidator validate click — server says valid', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ valid: true })
    })))
  })

  it('POSTs to the configured endpoint with the configured payload', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig({
      endpoint: '/validate_omdb',
      buildPayload: (key) => ({ omdb_apikey: key })
    }))
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(fetch).toHaveBeenCalledWith('/validate_omdb', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ omdb_apikey: 'mykey' })
    })
  })

  it('sets validated field to "true" on success', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig())
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(document.getElementById('test_validated').value).toBe('true')
  })

  it('stamps validated_at with an ISO timestamp on success', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig())
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    const stamp = document.getElementById('test_validated_at').value
    expect(stamp).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/)
  })

  it('shows success message in success color', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig())
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    const status = document.getElementById('statusMessage')
    expect(status.textContent).toBe('API key is valid!')
    expect(status.style.color).toBe('rgb(117, 183, 152)') // #75b798
  })

  it('uses the custom success message when provided', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig({
      messages: { success: 'OMDb API key is valid.' }
    }))
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(document.getElementById('statusMessage').textContent).toBe('OMDb API key is valid.')
  })

  it('disables the validate button after a successful validation', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig())
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(document.getElementById('validateButton').disabled).toBe(true)
  })

  it('calls showSpinner and hideSpinner with the configured key', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig({ spinnerKey: 'omdb-validate' }))
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(window.showSpinner).toHaveBeenCalledWith('omdb-validate')
    expect(window.hideSpinner).toHaveBeenCalledWith('omdb-validate')
  })

  it('defaults spinnerKey to "validate" when not configured', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig())
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(window.showSpinner).toHaveBeenCalledWith('validate')
    expect(window.hideSpinner).toHaveBeenCalledWith('validate')
  })
})

describe('createApiKeyValidator validate click — server says invalid', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ valid: false })
    })))
  })

  it('sets validated field to "false"', async () => {
    // Start with validated=false so the button is enabled and clickable.
    // (A disabled validate button silently swallows clicks, which is
    //  intended production behaviour after a successful validation.)
    document.body.innerHTML = buildBaseHTML({ keyValue: 'badkey', validated: 'false' })
    createApiKeyValidator(defaultConfig())
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(document.getElementById('test_validated').value).toBe('false')
  })

  it('clears validated_at on failure', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'badkey' })
    document.getElementById('test_validated_at').value = '2026-01-01T00:00:00Z'
    createApiKeyValidator(defaultConfig())
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(document.getElementById('test_validated_at').value).toBe('')
  })

  it('shows failure message in error color', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'badkey' })
    createApiKeyValidator(defaultConfig())
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    const status = document.getElementById('statusMessage')
    expect(status.textContent).toBe('API key is invalid.')
    expect(status.style.color).toBe('rgb(234, 134, 143)') // #ea868f
  })

  it('uses the custom failure message when provided', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'badkey' })
    createApiKeyValidator(defaultConfig({
      messages: { failure: 'Failed to validate MDBList server. Please check your API Key.' }
    }))
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(document.getElementById('statusMessage').textContent).toBe(
      'Failed to validate MDBList server. Please check your API Key.'
    )
  })

  it('does NOT disable the validate button on failure (user can retry)', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'badkey' })
    createApiKeyValidator(defaultConfig())
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(document.getElementById('validateButton').disabled).toBe(false)
  })
})

describe('createApiKeyValidator function-valued messages', () => {
  // Messages can be either a literal string OR a function that takes
  // the parsed server response and returns a string. Lets wizards
  // forward server-provided text verbatim (apprise uses data.error,
  // github uses data.message on both success and failure).

  it('uses a function-valued success message with response data', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ valid: true, message: 'Server says: hello!' })
    })))
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig({
      messages: { success: (data) => data.message }
    }))
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(document.getElementById('statusMessage').textContent).toBe('Server says: hello!')
  })

  it('uses a function-valued failure message with response data', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ valid: false, error: 'Apprise YAML at /missing.yml not found.' })
    })))
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig({
      messages: { failure: (data) => data.error }
    }))
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(document.getElementById('statusMessage').textContent).toBe('Apprise YAML at /missing.yml not found.')
  })

  it('function-valued messages receive {} for empty-credential case', () => {
    let received = null
    document.body.innerHTML = buildBaseHTML({ keyValue: '' })
    createApiKeyValidator(defaultConfig({
      messages: { empty: (data) => { received = data; return 'go away' } }
    }))
    document.getElementById('validateButton').click()

    expect(received).toEqual({})
    expect(document.getElementById('statusMessage').textContent).toBe('go away')
  })

  it('function-valued messages receive {} for network error case', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('boom'))))
    let received = null
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig({
      messages: { networkError: (data) => { received = data; return 'network sad' } }
    }))
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(received).toEqual({})
    expect(document.getElementById('statusMessage').textContent).toBe('network sad')
  })

  it('string and function-valued messages can be mixed in the same wizard', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ valid: true, message: 'all good' })
    })))
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig({
      messages: {
        empty: 'literal empty',
        success: (data) => data.message,
        failure: 'literal failure',
        networkError: 'literal network'
      }
    }))
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(document.getElementById('statusMessage').textContent).toBe('all good')
  })
})

describe('createApiKeyValidator multi-field wizards (additionalFieldIds)', () => {
  // These tests cover the multi-field shape used by tautulli (url +
  // apikey), gotify (url + token), ntfy (url + token + topic). Only
  // the primary `fieldId` gets the show/hide toggle; the others are
  // plain inputs that contribute to required-field validation, the
  // reset-on-input listener wiring, and the payload builder.

  function buildMultiFieldHTML ({
    primaryValue = '',
    urlValue = '',
    topicValue = '',
    validated = 'false'
  } = {}) {
    return `
      <form id="configForm">
        <input id="test_url" type="text" value="${urlValue}">
        <input id="test_apikey" type="password" value="${primaryValue}">
        <input id="test_topic" type="text" value="${topicValue}">
        <input id="test_validated" type="hidden" value="${validated}">
        <input id="test_validated_at" type="hidden" value="">
        <button id="toggleApikeyVisibility" type="button"><i class="bi"></i></button>
        <button id="validateButton" type="button">Validate</button>
        <div id="statusMessage" style="display:none"></div>
      </form>
    `
  }

  it('passes additional field values as the second arg to buildPayload', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ valid: true })
    })))
    document.body.innerHTML = buildMultiFieldHTML({
      primaryValue: 'mykey',
      urlValue: 'http://server',
      topicValue: 'alerts'
    })
    const buildPayload = vi.fn((credential, extras) => ({
      key: credential,
      url: extras.test_url,
      topic: extras.test_topic
    }))
    createApiKeyValidator(defaultConfig({
      additionalFieldIds: ['test_url', 'test_topic'],
      buildPayload
    }))
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(buildPayload).toHaveBeenCalledWith('mykey', {
      test_url: 'http://server',
      test_topic: 'alerts'
    })
    expect(fetch).toHaveBeenCalledWith('/validate_test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'mykey', url: 'http://server', topic: 'alerts' })
    })
  })

  it('passes an empty object as the second arg when no additionalFieldIds', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ valid: true })
    })))
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    const buildPayload = vi.fn((credential, extras) => ({ key: credential }))
    createApiKeyValidator(defaultConfig({ buildPayload }))
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(buildPayload).toHaveBeenCalledWith('mykey', {})
  })

  it('shows the empty message when the credential is filled but an additional field is empty', () => {
    document.body.innerHTML = buildMultiFieldHTML({
      primaryValue: 'mykey',
      urlValue: '', // url missing
      topicValue: 'alerts'
    })
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    createApiKeyValidator(defaultConfig({
      additionalFieldIds: ['test_url', 'test_topic'],
      messages: { empty: 'Please enter all fields.' }
    }))
    document.getElementById('validateButton').click()

    expect(document.getElementById('statusMessage').textContent).toBe('Please enter all fields.')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('shows the empty message when an additional field is filled but the credential is empty', () => {
    document.body.innerHTML = buildMultiFieldHTML({
      primaryValue: '', // credential missing
      urlValue: 'http://server',
      topicValue: 'alerts'
    })
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    createApiKeyValidator(defaultConfig({
      additionalFieldIds: ['test_url', 'test_topic']
    }))
    document.getElementById('validateButton').click()

    expect(document.getElementById('statusMessage').textContent).toBe('Please enter an API key.')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('resets validation when ANY additional field receives an input event', () => {
    document.body.innerHTML = buildMultiFieldHTML({
      primaryValue: 'mykey',
      urlValue: 'http://server',
      topicValue: 'alerts',
      validated: 'true'
    })
    createApiKeyValidator(defaultConfig({
      additionalFieldIds: ['test_url', 'test_topic']
    }))
    expect(document.getElementById('validateButton').disabled).toBe(true)

    // Typing in the topic field should reset validation
    document.getElementById('test_topic').dispatchEvent(new Event('input'))
    expect(document.getElementById('test_validated').value).toBe('false')
    expect(document.getElementById('validateButton').disabled).toBe(false)
  })

  it('normalises absent additional field values on form submit', () => {
    document.body.innerHTML = buildMultiFieldHTML({
      primaryValue: 'mykey',
      urlValue: '',
      topicValue: ''
    })
    createApiKeyValidator(defaultConfig({
      additionalFieldIds: ['test_url', 'test_topic']
    }))

    const form = document.getElementById('configForm')
    form.dispatchEvent(new Event('submit'))

    expect(document.getElementById('test_url').value).toBe('')
    expect(document.getElementById('test_topic').value).toBe('')
  })

  it('treats a missing additional field as absent (does not block validation)', async () => {
    // additionalFieldIds includes one id that does not exist on the page.
    // The factory should silently drop it from the empty check and the
    // payload rather than crash. (Protects against template/JS drift.)
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ valid: true })
    })))
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    const buildPayload = vi.fn((credential, extras) => ({ key: credential, ...extras }))
    createApiKeyValidator(defaultConfig({
      additionalFieldIds: ['nonexistent_topic'],
      buildPayload
    }))
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(buildPayload).toHaveBeenCalledWith('mykey', {})
  })
})

describe('createApiKeyValidator validate click — network error', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('boom'))))
  })

  it('shows the network-error message in error color', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig())
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    const status = document.getElementById('statusMessage')
    expect(status.textContent).toBe('An error occurred. Please try again.')
    expect(status.style.color).toBe('rgb(234, 134, 143)') // #ea868f
  })

  it('clears validated_at on network failure', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    document.getElementById('test_validated_at').value = '2026-01-01T00:00:00Z'
    createApiKeyValidator(defaultConfig())
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(document.getElementById('test_validated_at').value).toBe('')
  })

  it('still calls hideSpinner in finally (even though fetch rejected)', async () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig())
    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(window.hideSpinner).toHaveBeenCalledWith('validate')
  })
})

describe('createApiKeyValidator toggle visibility button', () => {
  it('toggles credential field from password to text on click', () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'secret' })
    createApiKeyValidator(defaultConfig())
    expect(document.getElementById('test_apikey').getAttribute('type')).toBe('password')

    document.getElementById('toggleApikeyVisibility').click()
    expect(document.getElementById('test_apikey').getAttribute('type')).toBe('text')
  })

  it('toggles credential field from text back to password on second click', () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'secret' })
    createApiKeyValidator(defaultConfig())
    const toggle = document.getElementById('toggleApikeyVisibility')

    toggle.click()
    toggle.click()
    expect(document.getElementById('test_apikey').getAttribute('type')).toBe('password')
  })

  it('accepts a custom toggleButtonId (for wizards using toggleTokenVisibility)', () => {
    document.body.innerHTML = `
      <form id="configForm">
        <input id="test_apikey" type="password" value="secret">
        <input id="test_validated" type="hidden" value="false">
        <input id="test_validated_at" type="hidden" value="">
        <button id="toggleTokenVisibility" type="button"><i class="bi"></i></button>
        <button id="validateButton" type="button">Validate</button>
        <div id="statusMessage" style="display:none"></div>
      </form>
    `
    createApiKeyValidator(defaultConfig({ toggleButtonId: 'toggleTokenVisibility' }))

    document.getElementById('toggleTokenVisibility').click()
    expect(document.getElementById('test_apikey').getAttribute('type')).toBe('text')
  })

  it('does not throw when toggle button is absent', () => {
    document.body.innerHTML = `
      <form id="configForm">
        <input id="test_apikey" type="password" value="secret">
        <input id="test_validated" type="hidden" value="false">
        <input id="test_validated_at" type="hidden" value="">
        <button id="validateButton" type="button">Validate</button>
        <div id="statusMessage" style="display:none"></div>
      </form>
    `
    expect(() => createApiKeyValidator(defaultConfig())).not.toThrow()
  })
})

describe('createApiKeyValidator form submit normalization', () => {
  it('preserves an existing credential value on form submit', () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: 'mykey' })
    createApiKeyValidator(defaultConfig())

    const form = document.getElementById('configForm')
    const submitEvent = new Event('submit', { cancelable: true })
    submitEvent.preventDefault() // prevent jsdom from navigating
    form.dispatchEvent(submitEvent)

    expect(document.getElementById('test_apikey').value).toBe('mykey')
  })

  it('normalises an empty-string credential to empty-string on submit (no-op safety)', () => {
    document.body.innerHTML = buildBaseHTML({ keyValue: '' })
    createApiKeyValidator(defaultConfig())

    const form = document.getElementById('configForm')
    form.dispatchEvent(new Event('submit'))

    expect(document.getElementById('test_apikey').value).toBe('')
  })

  it('does not throw when the form element is absent', () => {
    document.body.innerHTML = `
      <input id="test_apikey" type="password" value="secret">
      <input id="test_validated" type="hidden" value="false">
      <button id="validateButton" type="button">Validate</button>
      <div id="statusMessage" style="display:none"></div>
    `
    expect(() => createApiKeyValidator(defaultConfig())).not.toThrow()
  })
})

describe('createApiKeyValidator without validatedAtFieldId', () => {
  // Some legacy templates may not have the _validated_at hidden input.
  // The factory should tolerate that — we never assigned to a null el.

  it('still works when validatedAtFieldId is omitted', async () => {
    document.body.innerHTML = `
      <form id="configForm">
        <input id="test_apikey" type="password" value="mykey">
        <input id="test_validated" type="hidden" value="false">
        <button id="validateButton" type="button">Validate</button>
        <div id="statusMessage" style="display:none"></div>
      </form>
    `
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ valid: true })
    })))

    expect(() => createApiKeyValidator({
      fieldId: 'test_apikey',
      validatedFieldId: 'test_validated',
      endpoint: '/x',
      buildPayload: () => ({})
    })).not.toThrow()

    document.getElementById('validateButton').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(document.getElementById('test_validated').value).toBe('true')
  })
})
