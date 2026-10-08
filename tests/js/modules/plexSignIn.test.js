import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setupPlexSignIn } from '../../../static/local-js/modules/plexSignIn.js'
import { createApiKeyValidator } from '../../../static/local-js/modules/createApiKeyValidator.js'

let popup
let fetchMock

function response (data, status = 200) {
  return { ok: status < 400, status, json: async () => data }
}

async function settle () {
  for (let index = 0; index < 12; index++) await Promise.resolve()
}

function button (id) { return document.getElementById(id) }

beforeEach(() => {
  vi.useFakeTimers()
  document.body.innerHTML = `
    <form id="configForm">
      <input id="qs-active-config-input" value="first">
      <input id="plex_token" value="old-token">
      <input id="plex_url" value="http://plex:32400">
      <input id="plex_validated" value="true">
      <input id="plex_validated_at" value="old-date">
      <button type="button" id="plexSignIn">Sign in with Plex</button>
      <button type="button" id="plexSignInCancel" class="d-none">Cancel</button>
      <a id="plexSignInOpen" class="d-none"></a>
      <span id="plexSignInSpinner" class="d-none"></span>
      <div id="plexAuthStatus"></div>
      <div id="statusMessage"></div>
      <button type="button" id="toggleApikeyVisibility"></button>
      <button type="button" id="validateButton">Validate</button>
    </form>`
  popup = { close: vi.fn(), closed: false, location: 'about:blank' }
  vi.spyOn(window, 'open').mockReturnValue(popup)
  fetchMock = vi.fn(async (url) => {
    if (url.endsWith('/start')) return response({ attempt_id: 'attempt', auth_url: 'https://app.plex.tv/auth#?code=pin', expires_in: 60 })
    if (url.endsWith('/check')) return response({ authenticated: true, token: 'approved-token', username: 'owner' })
    if (url === '/validate_plex') return response({ validated: true })
    return response({ cancelled: true })
  })
  vi.stubGlobal('fetch', fetchMock)
  createApiKeyValidator({
    fieldId: 'plex_token',
    additionalFieldIds: ['plex_url'],
    validatedFieldId: 'plex_validated',
    validatedAtFieldId: 'plex_validated_at',
    endpoint: '/validate_plex',
    buildPayload: (token, extra) => ({ plex_token: token, plex_url: extra.plex_url }),
    isValid: data => data.validated === true
  })
  setupPlexSignIn()
})

afterEach(() => {
  window.dispatchEvent(new Event('pagehide'))
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Plex sign-in', () => {
  it('checks approval immediately when focus returns to QS', async () => {
    button('plexSignIn').click()
    await settle()
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/check'))).toBe(false)
    window.dispatchEvent(new Event('focus'))
    await settle()
    expect(button('plex_token').value).toBe('approved-token')
    expect(button('plex_validated').value).toBe('true')
  })

  it('does not overlap checks when focus and visibility return together', async () => {
    const fallback = fetchMock.getMockImplementation()
    let resolveCheck
    fetchMock.mockImplementation(url => url.endsWith('/check') ? new Promise(resolve => { resolveCheck = resolve }) : fallback(url))
    button('plexSignIn').click()
    await settle()
    window.dispatchEvent(new Event('focus'))
    window.dispatchEvent(new Event('focus'))
    document.dispatchEvent(new Event('visibilitychange'))
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/check'))).toHaveLength(1)
    resolveCheck(response({ authenticated: true, token: 'approved-token', username: 'owner' }))
    await settle()
    expect(button('plex_token').value).toBe('approved-token')
  })

  it('accepts approval after ten minutes when Plex grants thirty minutes', async () => {
    const fallback = fetchMock.getMockImplementation()
    fetchMock.mockImplementation(url => url.endsWith('/start') ? response({ attempt_id: 'attempt', auth_url: 'https://app.plex.tv/auth', expires_in: 1800 }) : fallback(url))
    button('plexSignIn').click()
    await settle()
    vi.setSystemTime(Date.now() + 11 * 60 * 1000)
    window.dispatchEvent(new Event('focus'))
    await settle()
    expect(button('plexAuthStatus').textContent).toBe('Signed in as owner.')
    expect(button('plex_token').value).toBe('approved-token')
  })

  it('opens synchronously, masks the approved token and validates the server', async () => {
    button('plexSignIn').click()
    expect(window.open).toHaveBeenCalled()
    expect(button('plex_token').readOnly).toBe(true)
    await settle()
    expect(popup.location).toContain('https://app.plex.tv/auth')
    await vi.advanceTimersByTimeAsync(2000)
    expect(button('plex_token').value).toBe('approved-token')
    expect(button('plex_token').type).toBe('password')
    expect(button('plexAuthStatus').textContent).toBe('Signed in as owner.')
    expect(button('plexAuthStatus').style.display).toBe('block')
    const validation = fetchMock.mock.calls.find(([url]) => url === '/validate_plex')
    expect(JSON.parse(validation[1].body)).toEqual({ plex_token: 'approved-token', plex_url: 'http://plex:32400' })
    expect(button('plex_validated').value).toBe('true')
    expect(popup.close).toHaveBeenCalled()
    expect(button('plex_url').value).toBe('http://plex:32400')
    expect(fetchMock.mock.calls.some(([url]) => /\/(servers|connect)$/.test(url))).toBe(false)
  })

  it('accepts sign-in without a server URL and focuses the URL field', async () => {
    button('plex_url').value = ''
    button('plexSignIn').click()
    await settle()
    await vi.advanceTimersByTimeAsync(2000)
    expect(button('plex_token').value).toBe('approved-token')
    expect(button('plex_validated').value).toBe('false')
    expect(button('plex_validated_at').value).toBe('')
    expect(document.activeElement).toBe(button('plex_url'))
    expect(fetchMock.mock.calls.some(([url]) => url === '/validate_plex')).toBe(false)
    expect(button('plexAuthStatus').textContent).toBe('Signed in as owner. Enter your Plex server URL, then validate.')
    expect(button('plex_url').value).toBe('')
    expect(button('plexSignIn').disabled).toBe(false)
    expect(button('plex_token').readOnly).toBe(false)
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/plex-auth/start', '/plex-auth/check', '/plex-auth/cancel'])
  })

  it('validates a manually entered LAN address using the token obtained earlier', async () => {
    button('plex_url').value = ''
    button('plexSignIn').click()
    await settle()
    await vi.advanceTimersByTimeAsync(2000)
    button('plex_url').value = 'http://192.168.2.242:32400'
    button('plex_url').dispatchEvent(new Event('input', { bubbles: true }))
    button('validateButton').click()
    await settle()
    expect(button('plex_validated').value).toBe('true')
    const validation = fetchMock.mock.calls.find(([url]) => url === '/validate_plex')
    expect(JSON.parse(validation[1].body)).toEqual({ plex_token: 'approved-token', plex_url: 'http://192.168.2.242:32400' })
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/start'))).toHaveLength(1)
    expect(fetchMock.mock.calls.some(([url]) => /\/(servers|connect)$/.test(url))).toBe(false)
  })

  it('keeps a URL entered while approval is pending', async () => {
    button('plex_url').value = ''
    button('plexSignIn').click()
    await settle()
    button('plex_url').value = 'http://manual:32400'
    button('plex_url').dispatchEvent(new Event('input', { bubbles: true }))
    expect(button('validateButton').disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(2000)
    expect(button('plex_url').value).toBe('http://manual:32400')
    expect(button('plex_validated').value).toBe('true')
    expect(fetchMock.mock.calls.some(([url]) => /\/(servers|connect)$/.test(url))).toBe(false)
  })

  it('keeps account success separate from a server validation failure', async () => {
    fetchMock.mockImplementation(async (url) => {
      if (url.endsWith('/start')) return response({ attempt_id: 'attempt', auth_url: 'https://app.plex.tv/auth', expires_in: 60 })
      if (url.endsWith('/check')) return response({ authenticated: true, token: 'approved-token', username: 'owner' })
      return response({ validated: false })
    })
    button('plexSignIn').click()
    await settle()
    await vi.advanceTimersByTimeAsync(2000)
    expect(button('plexAuthStatus').textContent).toBe('Signed in as owner.')
    expect(button('plex_validated').value).toBe('false')
    expect(button('validateButton').disabled).toBe(false)
  })

  it('provides a link when the popup is blocked', async () => {
    window.open.mockReturnValue(null)
    button('plexSignIn').click()
    await settle()
    expect(button('plexSignInOpen').classList.contains('d-none')).toBe(false)
    expect(button('plexSignInOpen').href).toContain('https://app.plex.tv/auth')
    await vi.advanceTimersByTimeAsync(2000)
    expect(button('plex_token').value).toBe('approved-token')
  })

  it('cancels a pending start and cleans up its late response', async () => {
    let resolveStart
    fetchMock.mockImplementationOnce(() => new Promise(resolve => { resolveStart = resolve }))
    button('plexSignIn').click()
    button('plexSignInCancel').click()
    resolveStart(response({ attempt_id: 'late-attempt', auth_url: 'https://app.plex.tv/auth', expires_in: 60 }))
    await settle()
    expect(button('plex_token').value).toBe('old-token')
    expect(button('plexSignIn').disabled).toBe(false)
    const cancellation = fetchMock.mock.calls.find(([url]) => url.endsWith('/cancel'))
    expect(JSON.parse(cancellation[1].body).attempt_id).toBe('late-attempt')
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/check'))).toBe(false)
  })

  it('ignores a late approved response after cancellation', async () => {
    let resolveCheck
    fetchMock.mockImplementation(async (url) => {
      if (url.endsWith('/start')) return response({ attempt_id: 'attempt', auth_url: 'https://app.plex.tv/auth', expires_in: 60 })
      if (url.endsWith('/check')) return new Promise(resolve => { resolveCheck = resolve })
      return response({ cancelled: true })
    })
    button('plexSignIn').click()
    await settle()
    await vi.advanceTimersByTimeAsync(2000)
    button('plexSignInCancel').click()
    resolveCheck(response({ authenticated: true, token: 'late-token' }))
    await settle()
    expect(button('plex_token').value).toBe('old-token')
    expect(button('plexAuthStatus').textContent).toBe('Plex sign-in cancelled.')
  })

  it('stops before polling when the config has changed', async () => {
    button('plexSignIn').click()
    await settle()
    button('qs-active-config-input').value = 'second'
    await vi.advanceTimersByTimeAsync(2000)
    expect(button('plex_token').value).toBe('old-token')
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/check'))).toBe(false)
    expect(button('plexAuthStatus').textContent).toContain('configuration changed')
  })

  it('retries provider outages and stops on expiry', async () => {
    fetchMock.mockImplementation(async (url) => {
      if (url.endsWith('/start')) return response({ attempt_id: 'attempt', auth_url: 'https://app.plex.tv/auth', expires_in: 5 })
      return response({ error: 'Temporary Plex outage.' }, 502)
    })
    button('plexSignIn').click()
    await settle()
    await vi.advanceTimersByTimeAsync(4000)
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/check'))).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(2000)
    expect(button('plexSignIn').disabled).toBe(false)
    expect(button('plex_token').value).toBe('old-token')
    expect(button('plexAuthStatus').textContent).toContain('expired')
  })
})
