// Tests for static/local-js/modules/createOauthValidator.js
// (#1334 Step 6 PR 2).
//
// The OAuth-shaped counterpart to createApiKeyValidator. Locks down
// the behaviour before 130-trakt and 140-mal migrate onto it.
//
// SHIMS follow the same pattern as createApiKeyValidator.test.js:
//   - showSpinner / hideSpinner stubbed as window globals
//   - fetch stubbed via vi.stubGlobal
//   - QSValidationCallouts optional per test
//
// FIXTURE:
//   buildBaseHTML() renders a stripped-down Trakt-shaped page with the
//   full standard element set. Tests override HTML fragments as needed
//   for edge cases (missing checkTokenButton, extra credential inputs,
//   etc.).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createOauthValidator } from '../../../static/local-js/modules/createOauthValidator.js'

function buildBaseHTML ({
  clientIdValue = '',
  secretValue = '',
  secondaryValue = '',
  validated = 'false',
  extraInputs = '',
  includeCheckTokenButton = true
} = {}) {
  const checkTokenBtn = includeCheckTokenButton
    ? '<button id="test_check_token" type="button">Check Token</button>'
    : ''
  return `
    <form id="configForm">
      <input id="test_client_id" type="text" value="${clientIdValue}">
      <input id="test_client_secret" type="password" value="${secretValue}">
      <input id="test_pin" type="text" value="${secondaryValue}">
      <input id="test_url" type="hidden" value="">
      <input id="test_validated" type="hidden" value="${validated}">
      <input id="test_validated_at" type="hidden" value="">
      <input id="access_token" type="hidden" value="">
      <input id="refresh_token" type="hidden" value="">
      <button id="toggleClientSecretVisibility" type="button">
        <i class="bi"></i>
      </button>
      <button id="test_authorize" type="button">Authorize</button>
      <button id="test_validate" type="button">Validate</button>
      ${checkTokenBtn}
      <div id="statusMessage" style="display:none"></div>
      ${extraInputs}
    </form>
  `
}

function defaultConfig (overrides = {}) {
  return {
    serviceName: 'Test',
    validatedFieldId: 'test_validated',
    validatedAtFieldId: 'test_validated_at',
    clientIdFieldId: 'test_client_id',
    clientSecretFieldId: 'test_client_secret',
    authorizeButtonId: 'test_authorize',
    validateButtonId: 'test_validate',
    checkTokenButtonId: 'test_check_token',
    urlFieldId: 'test_url',
    expectedClientIdLength: 8,
    buildAuthorizationURL: (clientId) => `https://example.test/auth?client_id=${clientId}`,
    secondaryValueFieldId: 'test_pin',
    validateEndpoint: '/validate_test',
    buildValidatePayload: ({ clientId, clientSecret, secondaryValue }) => ({
      test_client_id: clientId,
      test_client_secret: clientSecret,
      test_pin: secondaryValue
    }),
    validateSpinnerKey: 'validate',
    applyValidateSuccess: () => {},
    checkTokenEndpoint: '/validate_test_token',
    buildCheckTokenPayload: ({ accessToken }) => ({ access_token: accessToken, debug: true }),
    ...overrides
  }
}

function mockFetchOK (body) {
  const fetchMock = vi.fn(() => Promise.resolve({
    ok: true,
    json: () => Promise.resolve(body)
  }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mockFetchReject (err = new Error('boom')) {
  const fetchMock = vi.fn(() => Promise.reject(err))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function flushPromises () {
  // Two microtasks: one for fetch's then(res=>res.json()), one for the
  // json()'s .then(...) callback that runs onSuccess/onFailure.
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
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

describe('createOauthValidator config validation', () => {
  it.each([
    ['serviceName', { serviceName: undefined }],
    ['validatedFieldId', { validatedFieldId: undefined }],
    ['clientIdFieldId', { clientIdFieldId: undefined }],
    ['clientSecretFieldId', { clientSecretFieldId: undefined }],
    ['authorizeButtonId', { authorizeButtonId: undefined }],
    ['validateButtonId', { validateButtonId: undefined }],
    ['urlFieldId', { urlFieldId: undefined }],
    ['expectedClientIdLength', { expectedClientIdLength: undefined }],
    ['buildAuthorizationURL', { buildAuthorizationURL: undefined }],
    ['secondaryValueFieldId', { secondaryValueFieldId: undefined }],
    ['validateEndpoint', { validateEndpoint: undefined }],
    ['buildValidatePayload', { buildValidatePayload: undefined }],
    ['validateSpinnerKey', { validateSpinnerKey: undefined }],
    ['applyValidateSuccess', { applyValidateSuccess: undefined }]
  ])('throws when %s is missing', (fieldName, override) => {
    document.body.innerHTML = buildBaseHTML()
    expect(() => createOauthValidator(defaultConfig(override)))
      .toThrow(new RegExp(`${fieldName} is required`))
  })
})

describe('createOauthValidator wizard-not-rendered short-circuit', () => {
  it('returns silently when clientId input is missing', () => {
    document.body.innerHTML = '<form id="configForm"></form>'
    expect(() => createOauthValidator(defaultConfig())).not.toThrow()
  })

  it('returns silently when validate button is missing', () => {
    document.body.innerHTML = buildBaseHTML()
    document.getElementById('test_validate').remove()
    expect(() => createOauthValidator(defaultConfig())).not.toThrow()
  })

  it('returns silently when urlField is missing', () => {
    document.body.innerHTML = buildBaseHTML()
    document.getElementById('test_url').remove()
    expect(() => createOauthValidator(defaultConfig())).not.toThrow()
  })
})

describe('createOauthValidator initial button state', () => {
  it('disables validate button when previously validated', () => {
    document.body.innerHTML = buildBaseHTML({ validated: 'true' })
    createOauthValidator(defaultConfig())
    expect(document.getElementById('test_validate').disabled).toBe(true)
  })

  it('leaves validate button in "no secondary value" state when not previously validated', () => {
    document.body.innerHTML = buildBaseHTML({ validated: 'false' })
    createOauthValidator(defaultConfig())
    // secondaryValue empty AND no persisted validation -> button disabled
    expect(document.getElementById('test_validate').disabled).toBe(true)
  })

  it('starts authorize button disabled when urlField is empty', () => {
    document.body.innerHTML = buildBaseHTML()
    createOauthValidator(defaultConfig())
    expect(document.getElementById('test_authorize').disabled).toBe(true)
  })

  it('disables check-token button when access_token is empty', () => {
    document.body.innerHTML = buildBaseHTML()
    createOauthValidator(defaultConfig())
    expect(document.getElementById('test_check_token').disabled).toBe(true)
  })

  it('enables check-token button when access_token is populated', () => {
    document.body.innerHTML = buildBaseHTML()
    document.getElementById('access_token').value = 'existing-token'
    createOauthValidator(defaultConfig())
    expect(document.getElementById('test_check_token').disabled).toBe(false)
  })
})

describe('createOauthValidator authorization URL builder', () => {
  it('builds URL when clientId reaches expected length', () => {
    document.body.innerHTML = buildBaseHTML()
    createOauthValidator(defaultConfig({ expectedClientIdLength: 8 }))

    const clientIdInput = document.getElementById('test_client_id')
    clientIdInput.value = '12345678'
    clientIdInput.dispatchEvent(new Event('input'))

    expect(document.getElementById('test_url').value)
      .toBe('https://example.test/auth?client_id=12345678')
    expect(document.getElementById('test_authorize').disabled).toBe(false)
  })

  it('clears URL when clientId shrinks below expected length', () => {
    document.body.innerHTML = buildBaseHTML()
    createOauthValidator(defaultConfig({ expectedClientIdLength: 8 }))

    const clientIdInput = document.getElementById('test_client_id')
    clientIdInput.value = '12345678'
    clientIdInput.dispatchEvent(new Event('input'))
    clientIdInput.value = '1234567'
    clientIdInput.dispatchEvent(new Event('input'))

    expect(document.getElementById('test_url').value).toBe('')
    expect(document.getElementById('test_authorize').disabled).toBe(true)
  })

  it('resets validated state when URL is built', () => {
    document.body.innerHTML = buildBaseHTML({ validated: 'true' })
    document.getElementById('test_validated_at').value = '2026-01-01T00:00:00Z'
    createOauthValidator(defaultConfig({ expectedClientIdLength: 8 }))

    const clientIdInput = document.getElementById('test_client_id')
    clientIdInput.value = '12345678'
    clientIdInput.dispatchEvent(new Event('input'))

    expect(document.getElementById('test_validated').value).toBe('false')
    expect(document.getElementById('test_validated_at').value).toBe('')
  })

  it('passes extra credential values into buildAuthorizationURL', () => {
    document.body.innerHTML = buildBaseHTML({
      extraInputs: '<input id="test_verifier" type="text" value="my-pkce-verifier">'
    })
    const buildURL = vi.fn((clientId, extras) =>
      `https://example.test/auth?client_id=${clientId}&challenge=${extras.test_verifier}`)
    createOauthValidator(defaultConfig({
      expectedClientIdLength: 8,
      buildAuthorizationURL: buildURL,
      extraCredentialFieldIds: ['test_verifier']
    }))

    const clientIdInput = document.getElementById('test_client_id')
    clientIdInput.value = '12345678'
    clientIdInput.dispatchEvent(new Event('input'))

    expect(buildURL).toHaveBeenCalledWith('12345678', { test_verifier: 'my-pkce-verifier' })
    expect(document.getElementById('test_url').value)
      .toBe('https://example.test/auth?client_id=12345678&challenge=my-pkce-verifier')
  })
})

describe('createOauthValidator authorize button click', () => {
  it('opens URL in new tab and shows retrieve spinner', () => {
    document.body.innerHTML = buildBaseHTML()
    const openSpy = vi.fn(() => ({ focus: vi.fn() }))
    vi.stubGlobal('open', openSpy)
    createOauthValidator(defaultConfig({ expectedClientIdLength: 8 }))

    const clientIdInput = document.getElementById('test_client_id')
    clientIdInput.value = '12345678'
    clientIdInput.dispatchEvent(new Event('input'))

    document.getElementById('test_authorize').click()

    expect(openSpy).toHaveBeenCalledWith('https://example.test/auth?client_id=12345678', '_blank')
    expect(window.showSpinner).toHaveBeenCalledWith('retrieve')
  })

  it('does nothing when URL is empty', () => {
    document.body.innerHTML = buildBaseHTML()
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    createOauthValidator(defaultConfig())

    document.getElementById('test_authorize').click()
    expect(openSpy).not.toHaveBeenCalled()
  })
})

describe('createOauthValidator secondary value gating', () => {
  it('enables validate button when secondary value is populated', () => {
    document.body.innerHTML = buildBaseHTML()
    createOauthValidator(defaultConfig())

    const secondaryInput = document.getElementById('test_pin')
    secondaryInput.value = 'ABC123'
    secondaryInput.dispatchEvent(new Event('input'))

    expect(document.getElementById('test_validate').disabled).toBe(false)
  })

  it('disables validate button when secondary value is cleared', () => {
    document.body.innerHTML = buildBaseHTML({ secondaryValue: 'ABC123' })
    createOauthValidator(defaultConfig())

    const secondaryInput = document.getElementById('test_pin')
    secondaryInput.value = ''
    secondaryInput.dispatchEvent(new Event('input'))

    expect(document.getElementById('test_validate').disabled).toBe(true)
  })
})

describe('createOauthValidator validate flow', () => {
  it('shows missing-fields message when any credential is empty', () => {
    // Populate secondaryValue so the button is enabled, then clear the
    // secret to trigger the missing-fields path when clicked.
    document.body.innerHTML = buildBaseHTML({
      clientIdValue: 'abc',
      secretValue: 'x',
      secondaryValue: 'ABC123'
    })
    createOauthValidator(defaultConfig())
    // Now clear the secret post-init to leave it blank at click time.
    document.getElementById('test_client_secret').value = ''

    document.getElementById('test_validate').click()
    expect(document.getElementById('statusMessage').textContent)
      .toBe('ID, secret, and secondary value are all required.')
  })

  it('POSTs the payload from buildValidatePayload on click', async () => {
    document.body.innerHTML = buildBaseHTML({
      clientIdValue: 'my-client-id',
      secretValue: 'my-secret',
      secondaryValue: 'my-pin'
    })
    const fetchMock = mockFetchOK({ valid: true })
    createOauthValidator(defaultConfig())

    document.getElementById('test_validate').click()
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/validate_test', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        test_client_id: 'my-client-id',
        test_client_secret: 'my-secret',
        test_pin: 'my-pin'
      })
    }))
  })

  it('calls applyValidateSuccess and marks validated on ok response', async () => {
    document.body.innerHTML = buildBaseHTML({
      clientIdValue: 'my-client-id',
      secretValue: 'my-secret',
      secondaryValue: 'my-pin'
    })
    mockFetchOK({ valid: true, extra: 'stuff' })
    const applySuccess = vi.fn()
    createOauthValidator(defaultConfig({ applyValidateSuccess: applySuccess }))

    document.getElementById('test_validate').click()
    await flushPromises()

    expect(applySuccess).toHaveBeenCalledWith(
      expect.objectContaining({ valid: true, extra: 'stuff' }),
      expect.objectContaining({ markValidated: expect.any(Function) })
    )
    expect(document.getElementById('test_validated').value).toBe('true')
    expect(document.getElementById('test_validated_at').value).not.toBe('')
    expect(document.getElementById('statusMessage').textContent)
      .toContain('Test credentials validated successfully!')
  })

  it('sets validated=false on failure response', async () => {
    document.body.innerHTML = buildBaseHTML({
      clientIdValue: 'my-client-id',
      secretValue: 'my-secret',
      secondaryValue: 'my-pin',
      validated: 'true'
    })
    document.getElementById('test_validated_at').value = '2026-01-01T00:00:00Z'
    mockFetchOK({ valid: false })
    createOauthValidator(defaultConfig())
    // secondaryValueInput populated => re-enable button before click
    document.getElementById('test_validate').disabled = false

    document.getElementById('test_validate').click()
    await flushPromises()

    expect(document.getElementById('test_validated').value).toBe('false')
    expect(document.getElementById('test_validated_at').value).toBe('')
  })

  it('shows error message on fetch rejection', async () => {
    document.body.innerHTML = buildBaseHTML({
      clientIdValue: 'my-client-id',
      secretValue: 'my-secret',
      secondaryValue: 'my-pin'
    })
    mockFetchReject()
    createOauthValidator(defaultConfig())

    document.getElementById('test_validate').click()
    await flushPromises()

    expect(document.getElementById('statusMessage').textContent)
      .toBe('An error occurred while validating Test credentials.')
  })
})

describe('createOauthValidator check-token flow', () => {
  it('shows missing message when access_token is blank', () => {
    document.body.innerHTML = buildBaseHTML()
    createOauthValidator(defaultConfig())

    document.getElementById('test_check_token').disabled = false
    document.getElementById('test_check_token').click()
    expect(document.getElementById('statusMessage').textContent).toBe('Missing access token.')
  })

  it('POSTs check-token payload and marks validated on success', async () => {
    document.body.innerHTML = buildBaseHTML()
    document.getElementById('access_token').value = 'my-access-token'
    document.getElementById('refresh_token').value = 'my-refresh-token'
    const fetchMock = mockFetchOK({ valid: true })
    createOauthValidator(defaultConfig({
      buildCheckTokenPayload: ({ accessToken, clientId, clientSecret, refreshToken }) => ({
        access_token: accessToken,
        client_id: clientId,
        client_secret: clientSecret,
        refresh_token: refreshToken,
        debug: true
      })
    }))

    document.getElementById('test_check_token').click()
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/validate_test_token', expect.objectContaining({
      body: JSON.stringify({
        access_token: 'my-access-token',
        client_id: '',
        client_secret: '',
        refresh_token: 'my-refresh-token',
        debug: true
      })
    }))
    expect(document.getElementById('test_validated').value).toBe('true')
    expect(document.getElementById('statusMessage').textContent).toContain('Test token is valid.')
  })

  it('calls applyCheckTokenSuccess when provided', async () => {
    document.body.innerHTML = buildBaseHTML()
    document.getElementById('access_token').value = 'my-access-token'
    mockFetchOK({ valid: true, authorization: { access_token: 'rotated' } })
    const applyCheck = vi.fn()
    createOauthValidator(defaultConfig({ applyCheckTokenSuccess: applyCheck }))

    document.getElementById('test_check_token').click()
    await flushPromises()

    expect(applyCheck).toHaveBeenCalledWith(
      expect.objectContaining({ authorization: { access_token: 'rotated' } }),
      expect.objectContaining({ markValidated: expect.any(Function) })
    )
  })

  it('does not wire check-token flow when checkTokenButtonId is omitted', () => {
    document.body.innerHTML = buildBaseHTML({ includeCheckTokenButton: false })
    expect(() => createOauthValidator(defaultConfig({
      checkTokenButtonId: undefined,
      checkTokenEndpoint: undefined,
      buildCheckTokenPayload: undefined
    }))).not.toThrow()
  })

  it('sets validated=false on check-token failure response', async () => {
    document.body.innerHTML = buildBaseHTML({ validated: 'true' })
    document.getElementById('access_token').value = 'my-access-token'
    document.getElementById('test_validated_at').value = '2026-01-01T00:00:00Z'
    mockFetchOK({ valid: false })
    createOauthValidator(defaultConfig())

    document.getElementById('test_check_token').disabled = false
    document.getElementById('test_check_token').click()
    await flushPromises()

    expect(document.getElementById('test_validated').value).toBe('false')
    expect(document.getElementById('test_validated_at').value).toBe('')
  })

  it('shows error message on check-token fetch rejection', async () => {
    document.body.innerHTML = buildBaseHTML()
    document.getElementById('access_token').value = 'my-access-token'
    mockFetchReject()
    createOauthValidator(defaultConfig())

    document.getElementById('test_check_token').disabled = false
    document.getElementById('test_check_token').click()
    await flushPromises()

    expect(document.getElementById('statusMessage').textContent)
      .toBe('An error occurred while validating Test token.')
  })

  it('runs custom checkTokenPreflight guard when provided', () => {
    document.body.innerHTML = buildBaseHTML()
    document.getElementById('access_token').value = 'my-access-token'
    const fetchMock = mockFetchOK({ valid: true })
    createOauthValidator(defaultConfig({
      checkTokenPreflight: ({ accessToken, clientId }) =>
        (!accessToken.trim() || !clientId.trim())
          ? 'Missing access token or client ID.'
          : null
    }))

    // clientId is empty, so the preflight should abort with the custom message
    document.getElementById('test_check_token').disabled = false
    document.getElementById('test_check_token').click()

    expect(document.getElementById('statusMessage').textContent)
      .toBe('Missing access token or client ID.')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('proceeds when checkTokenPreflight returns null', async () => {
    document.body.innerHTML = buildBaseHTML({ clientIdValue: 'x' })
    document.getElementById('access_token').value = 'my-access-token'
    const fetchMock = mockFetchOK({ valid: true })
    createOauthValidator(defaultConfig({
      checkTokenPreflight: () => null
    }))

    document.getElementById('test_check_token').disabled = false
    document.getElementById('test_check_token').click()
    await flushPromises()

    expect(fetchMock).toHaveBeenCalled()
  })
})

describe('createOauthValidator message overrides', () => {
  it('uses custom messages from config', async () => {
    document.body.innerHTML = buildBaseHTML({
      clientIdValue: 'x', secretValue: 'y', secondaryValue: 'z'
    })
    mockFetchOK({ valid: true })
    createOauthValidator(defaultConfig({
      messages: {
        validateSuccess: 'HOORAY!',
        validateError: 'BOOM',
        validateMissingFields: 'You forgot something.',
        checkTokenSuccess: 'good token',
        checkTokenError: 'bad token',
        checkTokenMissingFields: 'no token yet'
      }
    }))

    document.getElementById('test_validate').click()
    await flushPromises()

    expect(document.getElementById('statusMessage').textContent).toContain('HOORAY!')
  })
})

describe('createOauthValidator credential reset listeners', () => {
  it('resets validated state when clientId is edited', () => {
    document.body.innerHTML = buildBaseHTML({ validated: 'true' })
    document.getElementById('test_validated_at').value = '2026-01-01T00:00:00Z'
    createOauthValidator(defaultConfig())

    const clientIdInput = document.getElementById('test_client_id')
    clientIdInput.value = 'a'
    clientIdInput.dispatchEvent(new Event('input'))

    expect(document.getElementById('test_validated').value).toBe('false')
    expect(document.getElementById('test_validated_at').value).toBe('')
  })

  it('resets validated state when clientSecret is edited', () => {
    document.body.innerHTML = buildBaseHTML({ validated: 'true' })
    document.getElementById('test_validated_at').value = '2026-01-01T00:00:00Z'
    createOauthValidator(defaultConfig())

    const secretInput = document.getElementById('test_client_secret')
    secretInput.value = 'new-secret'
    secretInput.dispatchEvent(new Event('input'))

    expect(document.getElementById('test_validated').value).toBe('false')
  })

  it('resets validated state when secondaryValue is edited', () => {
    document.body.innerHTML = buildBaseHTML({ validated: 'true' })
    createOauthValidator(defaultConfig())

    const secondary = document.getElementById('test_pin')
    secondary.value = 'newpin'
    secondary.dispatchEvent(new Event('input'))

    expect(document.getElementById('test_validated').value).toBe('false')
  })
})
