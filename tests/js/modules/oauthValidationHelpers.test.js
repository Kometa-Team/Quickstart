import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import {
  STATUS_COLOR_SUCCESS,
  STATUS_COLOR_ERROR,
  isBlankTokenValue,
  wireSecretToggle,
  wireCredentialResetListeners,
  showStatusMessage,
  performValidationRequest
} from '../../../static/local-js/modules/oauthValidationHelpers.js'

// These tests exercise the four narrow helpers used by the OAuth-PIN
// wizards (130-trakt and 140-mal). They avoid testing wizard-specific
// orchestration -- that's covered by the e2e tests.

describe('oauthValidationHelpers.isBlankTokenValue', () => {
  it('treats undefined as blank', () => {
    expect(isBlankTokenValue(undefined)).toBe(true)
  })

  it('treats null as blank', () => {
    expect(isBlankTokenValue(null)).toBe(true)
  })

  it('treats empty string as blank', () => {
    expect(isBlankTokenValue('')).toBe(true)
  })

  it('treats whitespace-only as blank', () => {
    expect(isBlankTokenValue('   ')).toBe(true)
    expect(isBlankTokenValue('\t\n')).toBe(true)
  })

  it('treats the literal string "none" as blank (case-insensitive)', () => {
    // Persisted state may round-trip None -> "None" -> "none" through
    // Python/Jinja/JSON. All variants should be treated as blank so
    // the Check Token button stays disabled.
    expect(isBlankTokenValue('none')).toBe(true)
    expect(isBlankTokenValue('None')).toBe(true)
    expect(isBlankTokenValue('NONE')).toBe(true)
    expect(isBlankTokenValue('  none  ')).toBe(true)
  })

  it('treats the literal string "null" as blank (case-insensitive)', () => {
    expect(isBlankTokenValue('null')).toBe(true)
    expect(isBlankTokenValue('Null')).toBe(true)
    expect(isBlankTokenValue('NULL')).toBe(true)
    expect(isBlankTokenValue('\tnull\t')).toBe(true)
  })

  it('treats a real-looking token as non-blank', () => {
    expect(isBlankTokenValue('abc123')).toBe(false)
    expect(isBlankTokenValue('a-very-long-token-value-here-1234567890')).toBe(false)
  })

  it('does NOT treat tokens that contain "none" as a substring as blank', () => {
    // Defensive: "honeybadger" contains "none" but is a valid token.
    // The check is for exact equality after trim+lower, not contains.
    expect(isBlankTokenValue('honeybadger')).toBe(false)
    expect(isBlankTokenValue('nullify')).toBe(false)
  })
})

describe('oauthValidationHelpers.wireSecretToggle', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('sets type=text and "show plain" icon when secret field is empty', () => {
    document.body.innerHTML = `
      <input id="secret" type="password" value="">
      <button id="toggle"></button>
    `
    const secret = document.getElementById('secret')
    const toggle = document.getElementById('toggle')
    wireSecretToggle(secret, toggle)

    expect(secret.getAttribute('type')).toBe('text')
    expect(toggle.firstChild.className).toBe('fas fa-eye-slash')
  })

  it('keeps type=password and "hide plain" icon when secret field is populated', () => {
    document.body.innerHTML = `
      <input id="secret" type="password" value="my-secret">
      <button id="toggle"></button>
    `
    const secret = document.getElementById('secret')
    const toggle = document.getElementById('toggle')
    wireSecretToggle(secret, toggle)

    expect(secret.getAttribute('type')).toBe('password')
    expect(toggle.firstChild.className).toBe('fas fa-eye')
  })

  it('toggles the type on click', () => {
    document.body.innerHTML = `
      <input id="secret" type="password" value="my-secret">
      <button id="toggle"></button>
    `
    const secret = document.getElementById('secret')
    const toggle = document.getElementById('toggle')
    wireSecretToggle(secret, toggle)
    expect(secret.getAttribute('type')).toBe('password')

    toggle.click()
    expect(secret.getAttribute('type')).toBe('text')

    toggle.click()
    expect(secret.getAttribute('type')).toBe('password')
  })

  it('treats whitespace-only secret as empty', () => {
    document.body.innerHTML = `
      <input id="secret" type="password" value="   ">
      <button id="toggle"></button>
    `
    wireSecretToggle(document.getElementById('secret'), document.getElementById('toggle'))
    expect(document.getElementById('secret').getAttribute('type')).toBe('text')
  })

  it('does not throw when secret input is missing', () => {
    document.body.innerHTML = '<button id="toggle"></button>'
    expect(() => wireSecretToggle(null, document.getElementById('toggle'))).not.toThrow()
  })

  it('does not throw when toggle button is missing', () => {
    document.body.innerHTML = '<input id="secret" type="password" value="">'
    expect(() => wireSecretToggle(document.getElementById('secret'), null)).not.toThrow()
  })
})

describe('oauthValidationHelpers.wireCredentialResetListeners', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    // QSValidationCallouts is a window-scoped helper that owns the
    // legacy floating-callout UI. The validationPageBase helper
    // refreshValidationCallout() proxies into it when present. For
    // tests we just stub it so we can assert it was called.
    window.QSValidationCallouts = { refresh: vi.fn() }
  })

  afterEach(() => {
    delete window.QSValidationCallouts
  })

  it('resets validatedField and validatedAt when ANY tracked input fires "input"', () => {
    document.body.innerHTML = `
      <input id="a">
      <input id="b">
      <input id="c">
      <input id="validated" value="true">
      <input id="validated_at" value="2026-06-29T00:00:00Z">
      <button id="validate" disabled></button>
      <button id="check" disabled></button>
    `
    const validatedField = document.getElementById('validated')
    const validatedAtField = document.getElementById('validated_at')
    const validateButton = document.getElementById('validate')
    const checkTokenButton = document.getElementById('check')
    // checkToken starts disabled (no token saved scenario). Pretend
    // a previous validate enabled it.
    checkTokenButton.disabled = false

    wireCredentialResetListeners({
      fieldIds: ['a', 'b', 'c'],
      validatedField,
      validatedAtField,
      validateButton,
      checkTokenButton,
      validatedFieldId: 'validated'
    })

    document.getElementById('b').dispatchEvent(new Event('input'))

    expect(validatedField.value).toBe('false')
    expect(validatedAtField.value).toBe('')
    expect(validateButton.disabled).toBe(false)
    expect(checkTokenButton.disabled).toBe(true)
    expect(window.QSValidationCallouts.refresh).toHaveBeenCalledWith('validated')
  })

  it('warns when a field ID is missing instead of throwing', () => {
    document.body.innerHTML = '<input id="exists">'
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(() => wireCredentialResetListeners({
      fieldIds: ['exists', 'does_not_exist'],
      validatedField: null,
      validateButton: null,
      validatedFieldId: 'whatever'
    })).not.toThrow()
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('does_not_exist'))
    warnSpy.mockRestore()
  })

  it('still resets validatedField even when checkTokenButton is omitted', () => {
    document.body.innerHTML = `
      <input id="a">
      <input id="validated" value="true">
      <button id="validate"></button>
    `
    wireCredentialResetListeners({
      fieldIds: ['a'],
      validatedField: document.getElementById('validated'),
      validateButton: document.getElementById('validate'),
      validatedFieldId: 'validated'
    })
    document.getElementById('a').dispatchEvent(new Event('input'))
    expect(document.getElementById('validated').value).toBe('false')
  })
})

describe('oauthValidationHelpers.showStatusMessage', () => {
  it('sets text + color and makes the element visible', () => {
    document.body.innerHTML = '<div id="status" style="display:none;"></div>'
    const status = document.getElementById('status')
    showStatusMessage(status, 'Hello', STATUS_COLOR_SUCCESS)
    expect(status.textContent).toBe('Hello')
    expect(status.style.color).toBe('rgb(117, 183, 152)') // computed form of #75b798
    expect(status.style.display).toBe('block')
  })

  it('is a no-op when status element is null', () => {
    expect(() => showStatusMessage(null, 'x', STATUS_COLOR_ERROR)).not.toThrow()
  })
})

describe('oauthValidationHelpers.performValidationRequest', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="status"></div>'
    // showSpinner/hideSpinner are globals defined in 000-base.js. The
    // helper module calls them by name; we stub them on window for
    // Vitest's jsdom env.
    window.showSpinner = vi.fn()
    window.hideSpinner = vi.fn()
  })

  afterEach(() => {
    delete window.showSpinner
    delete window.hideSpinner
    vi.unstubAllGlobals()
  })

  it('POSTs JSON to the endpoint and invokes onSuccess with parsed data', async () => {
    const fetchSpy = vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ valid: true, hello: 'world' })
    }))
    vi.stubGlobal('fetch', fetchSpy)
    const onSuccess = vi.fn()
    const onFailure = vi.fn()

    await performValidationRequest({
      endpoint: '/check',
      payload: { key: 'value' },
      spinnerKey: 'validate',
      statusElement: document.getElementById('status'),
      onSuccess,
      onFailure
    })

    expect(fetchSpy).toHaveBeenCalledWith('/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'value' })
    })
    expect(onSuccess).toHaveBeenCalledWith({ valid: true, hello: 'world' })
    expect(onFailure).not.toHaveBeenCalled()
  })

  it('invokes onFailure when data.valid is falsy and shows the data.error message', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ valid: false, error: 'bad credentials' })
    })))
    const onSuccess = vi.fn()
    const onFailure = vi.fn()
    const statusElement = document.getElementById('status')

    await performValidationRequest({
      endpoint: '/check',
      payload: {},
      spinnerKey: 'validate',
      statusElement,
      onSuccess,
      onFailure
    })

    expect(onSuccess).not.toHaveBeenCalled()
    expect(onFailure).toHaveBeenCalledWith({ valid: false, error: 'bad credentials' })
    expect(statusElement.textContent).toBe('bad credentials')
    expect(statusElement.style.color).toBe('rgb(234, 134, 143)')
  })

  it('falls back to a generic failure message when data.error is missing', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ valid: false })
    })))
    const statusElement = document.getElementById('status')

    await performValidationRequest({
      endpoint: '/check',
      payload: {},
      spinnerKey: 'validate',
      statusElement,
      onSuccess: vi.fn(),
      onFailure: vi.fn()
    })

    expect(statusElement.textContent).toBe('Validation failed.')
  })

  it('invokes onError and skips onSuccess/onFailure when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))))
    const onSuccess = vi.fn()
    const onFailure = vi.fn()
    const onError = vi.fn()

    await performValidationRequest({
      endpoint: '/check',
      payload: {},
      spinnerKey: 'validate',
      statusElement: document.getElementById('status'),
      onSuccess,
      onFailure,
      onError
    })

    expect(onSuccess).not.toHaveBeenCalled()
    expect(onFailure).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledWith(expect.any(Error))
    expect(onError.mock.calls[0][0].message).toBe('network down')
  })

  it('calls showSpinner before fetch and hideSpinner after', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ valid: true })
    })))

    await performValidationRequest({
      endpoint: '/check',
      payload: {},
      spinnerKey: 'my_spinner',
      statusElement: document.getElementById('status'),
      onSuccess: vi.fn(),
      onFailure: vi.fn()
    })

    expect(window.showSpinner).toHaveBeenCalledWith('my_spinner')
    expect(window.hideSpinner).toHaveBeenCalledWith('my_spinner')
  })

  it('still hides the spinner when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('boom'))))

    await performValidationRequest({
      endpoint: '/check',
      payload: {},
      spinnerKey: 'my_spinner',
      statusElement: document.getElementById('status'),
      onSuccess: vi.fn(),
      onFailure: vi.fn(),
      onError: vi.fn()
    })

    expect(window.hideSpinner).toHaveBeenCalledWith('my_spinner')
  })

  it('does not throw when onError is omitted and fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('boom'))))
    await expect(performValidationRequest({
      endpoint: '/check',
      payload: {},
      spinnerKey: 'k',
      statusElement: document.getElementById('status'),
      onSuccess: vi.fn(),
      onFailure: vi.fn()
    })).resolves.toBeUndefined()
  })
})
