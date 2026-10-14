import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { initLogscanAutoUpload } from '../../../static/local-js/modules/logscanAutoUpload.js'
import { getAppConfig, setAppConfig } from '../../../static/local-js/modules/appConfig.js'

describe('run section automatic Logscan uploads', () => {
  beforeEach(() => {
    window.QS_AppConfig = {}
    document.body.innerHTML = '<button id="quickstart-settings-btn"></button>' + ['kometa', 'imagemaid'].map(tool => `
      <input type="checkbox" id="quickstart-settings-auto-upload-${tool}">
      <input type="checkbox" id="${tool}-auto-upload" data-logscan-auto-upload="${tool}">
      <div id="${tool}-auto-upload-status"></div>`).join('')
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    document.body.innerHTML = ''
    delete window.QS_AppConfig
    vi.unstubAllGlobals()
  })

  it.each(['kometa', 'imagemaid'])('persists the %s switch and synchronizes Settings', async tool => {
    const field = `logscan_auto_upload_${tool}`
    fetch.mockResolvedValue({ ok: true, json: async () => ({ success: true, [field]: true }) })
    initLogscanAutoUpload()
    initLogscanAutoUpload()
    const input = document.getElementById(`${tool}-auto-upload`)
    input.click()
    expect(input.disabled).toBe(true)
    await vi.waitFor(() => expect(input.disabled).toBe(false))
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/update-quickstart-settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ [field]: true })
    })
    expect(input.checked).toBe(true)
    expect(document.getElementById(`quickstart-settings-auto-upload-${tool}`).checked).toBe(true)
    expect(getAppConfig(`QS_LOGSCAN_AUTO_UPLOAD_${tool.toUpperCase()}`)).toBe(true)
    expect(document.getElementById(`${tool}-auto-upload-status`).textContent).toBe('Saved.')
  })

  it('reflects changes saved in Settings without a reload', () => {
    setAppConfig({ QS_LOGSCAN_AUTO_UPLOAD_KOMETA: true })
    initLogscanAutoUpload()
    const input = document.getElementById('kometa-auto-upload')
    expect(input.checked).toBe(true)
    setAppConfig({ QS_LOGSCAN_AUTO_UPLOAD_KOMETA: false })
    document.dispatchEvent(new CustomEvent('quickstart-settings-change'))
    expect(input.checked).toBe(false)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('restores the saved value and reports a failed save', async () => {
    fetch.mockResolvedValue({ ok: false, json: async () => ({ message: 'Settings could not be saved.' }) })
    initLogscanAutoUpload()
    const input = document.getElementById('kometa-auto-upload')
    input.click()
    await vi.waitFor(() => expect(input.disabled).toBe(false))
    expect(input.checked).toBe(false)
    expect(document.getElementById('quickstart-settings-auto-upload-kometa').disabled).toBe(false)
    expect(document.getElementById('kometa-auto-upload-status').textContent).toBe('Settings could not be saved.')
  })
})
