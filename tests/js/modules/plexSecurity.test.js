import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { renderPlexSecurity } from '../../../static/local-js/modules/plexSecurity.js'
import { createApiKeyValidator } from '../../../static/local-js/modules/createApiKeyValidator.js'

const assessment = (status) => [{ status, advisory_id: 'PLEX-PMS-2026-09', detected_version: '1.43.3.10861', minimum_patched_version: '1.43.3.10861', advisory_url: 'https://forums.plex.tv/t/test/1' }]
const settle = async () => { for (let index = 0; index < 8; index++) await Promise.resolve() }

beforeEach(() => {
  document.body.innerHTML = `<form id="configForm">
    <input id="token" value="token"><input id="url" value="http://localhost:32400">
    <input id="validated" value="true"><button id="validateButton" type="button">Validate</button>
    <div id="statusMessage"></div><div id="plex-security-status"></div></form>`
})
afterEach(() => vi.unstubAllGlobals())

function setup () {
  createApiKeyValidator({
    fieldId: 'token', additionalFieldIds: ['url'], validatedFieldId: 'validated', endpoint: '/validate_plex',
    buildPayload: (token, extras) => ({ token, ...extras }), revalidateOnLoad: true, allowRevalidation: true,
    isValid: data => data.validated === true,
    onValidationSuccess: data => renderPlexSecurity(data.plex_security),
    onValidationReset: () => renderPlexSecurity(), onValidationStart: () => renderPlexSecurity(),
    onValidationFailure: () => renderPlexSecurity()
  })
}

it('shows red affected warning, small patched status, and neutral unknown without blocking save', () => {
  const target = document.getElementById('plex-security-status')
  renderPlexSecurity(assessment('affected'))
  expect(target.className).toContain('alert-danger')
  expect(target.textContent).toContain('Update Plex Media Server')
  expect(target.textContent).toContain('not an official CVSS')
  expect(target.querySelector('a').rel).toContain('noopener')
  renderPlexSecurity(assessment('patched'))
  expect(target.className).not.toContain('alert-danger')
  expect(target.textContent).toContain('this advisory only')
  renderPlexSecurity()
  expect(target.textContent).toContain('unknown')
  expect(document.getElementById('configForm').dispatchEvent(new Event('submit', { cancelable: true }))).toBe(true)
})

it('refreshes status on revisit and clears it on connection edits', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ json: async () => ({ validated: true, plex_security: assessment('affected') }) }))
  setup()
  await settle()
  expect(document.getElementById('plex-security-status').className).toContain('alert-danger')
  expect(document.getElementById('validateButton').disabled).toBe(false)
  document.getElementById('url').dispatchEvent(new Event('input'))
  expect(document.getElementById('plex-security-status').textContent).toContain('unknown')
})

it('ignores a stale response after connection changes', async () => {
  let resolveRequest
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { resolveRequest = resolve })))
  setup()
  document.getElementById('token').value = 'different'
  document.getElementById('token').dispatchEvent(new Event('input'))
  resolveRequest({ json: async () => ({ validated: true, plex_security: assessment('affected') }) })
  await settle()
  expect(document.getElementById('validated').value).toBe('false')
  expect(document.getElementById('plex-security-status').textContent).toContain('unknown')
})

it('clears status after failed or unavailable validation', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
  renderPlexSecurity(assessment('patched'))
  setup()
  await settle()
  expect(document.getElementById('plex-security-status').textContent).toContain('unknown')
})

it('keeps a new validation result when an older request finishes later', async () => {
  const requests = []
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { requests.push(resolve) })))
  setup()
  document.getElementById('validateButton').click()
  requests[1]({ json: async () => ({ validated: true, plex_security: assessment('patched') }) })
  await settle()
  requests[0]({ json: async () => ({ validated: true, plex_security: assessment('affected') }) })
  await settle()
  expect(document.getElementById('plex-security-status').textContent).toContain('this advisory only')
  expect(document.getElementById('plex-security-status').className).not.toContain('alert-danger')
})
