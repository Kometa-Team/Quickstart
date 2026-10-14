import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { initLogscanUpload } from '../../../static/local-js/modules/kometa/_logscanUpload.js'

const reply = (data, ok = true) => ({ ok, json: async () => data })
const flush = async () => { for (let i = 0; i < 10; i++) await Promise.resolve() }
const completed = { phase: 'complete', result_url: 'https://logscan.kometa.team/scan/abc', management_url: 'https://logscan.kometa.team/scan/abc#delete=private' }

describe('manual compressed Logscan upload', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    document.body.innerHTML = `
      <button id="logscan-upload"></button><div id="logscan-upload-status"></div>
      <div id="logscan-upload-links" class="d-none"><a id="logscan-upload-result"></a>
      <a id="logscan-upload-management"></a><button id="logscan-upload-copy"></button></div>`
    vi.stubGlobal('QS_confirmAction', vi.fn().mockResolvedValue(true))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply({ phase: 'idle' })))
  })
  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('shows automatic queue progress without posting from the browser', async () => {
    document.getElementById('logscan-upload').remove()
    document.body.insertAdjacentHTML('beforeend', '<table id="logscan-trends-table"><tbody><tr><td><button class="logscan-upload-log" data-run-key="auto"></button><div class="logscan-upload-feedback" data-run-key="auto"></div></td></tr></tbody></table>')
    fetch.mockResolvedValueOnce(reply({ phase: 'idle', automatic_pending: true, automatic_results: { auto: { phase: 'waiting' } }, run_results: {} }))
      .mockResolvedValueOnce(reply({ phase: 'idle', automatic_pending: false, automatic_results: { auto: completed }, run_results: { auto: completed } }))
    const control = initLogscanUpload({ historical: true })
    await flush()
    expect(control.isBusy()).toBe(true)
    expect(control.hasResult('auto')).toBe(false)
    expect(document.querySelector('.logscan-upload-feedback').textContent).toContain('Waiting')
    expect(document.querySelector('.logscan-upload-log').disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(2000)
    expect(control.hasResult('auto')).toBe(true)
    expect(control.isBusy()).toBe(false)
    expect(document.querySelector('.logscan-upload-feedback a').href).toBe(completed.result_url)
    expect(fetch.mock.calls.every(([, options]) => !options?.method)).toBe(true)
  })

  it('shows the current Kometa automatic upload and keeps polling until its support link is ready', async () => {
    initLogscanUpload()
    await flush()
    fetch.mockResolvedValueOnce(reply({ phase: 'idle', automatic_enabled: true, automatic_pending: true, automatic_results: { current: { phase: 'uploading' } } }))
      .mockResolvedValueOnce(reply({ phase: 'idle', automatic_enabled: true, run_results: { current: completed } }))
    document.dispatchEvent(new CustomEvent('logscan-analysis', { detail: { runKey: 'current' } }))
    await flush()
    expect(fetch).toHaveBeenLastCalledWith('/logscan/upload/status?history=1')
    expect(document.getElementById('logscan-upload-status').textContent).toContain('Uploading')
    await vi.advanceTimersByTimeAsync(2000)
    expect(document.getElementById('logscan-upload-result').href).toBe(completed.result_url)
    expect(document.getElementById('logscan-upload-links').classList.contains('d-none')).toBe(false)
    expect(fetch.mock.calls.every(([, options]) => !options?.method)).toBe(true)
    await vi.advanceTimersByTimeAsync(15000)
    expect(fetch).toHaveBeenCalledTimes(4)
  })

  it('does not show an older session upload as the new Kometa run result', async () => {
    fetch.mockResolvedValue(reply({ ...completed, run_key: 'old', run_results: { old: completed } }))
    initLogscanUpload()
    await flush()
    document.dispatchEvent(new CustomEvent('logscan-analysis', { detail: { runKey: 'new' } }))
    await flush()
    expect(document.getElementById('logscan-upload-links').classList.contains('d-none')).toBe(true)
  })

  it('shows automatic upload failures on the Kometa run page', async () => {
    fetch.mockResolvedValue(reply({ phase: 'idle', automatic_results: { current: { phase: 'failed', error: 'Logscan unavailable.' } } }))
    initLogscanUpload()
    await flush()
    document.dispatchEvent(new CustomEvent('logscan-analysis', { detail: { runKey: 'current' } }))
    await flush()
    expect(document.getElementById('logscan-upload-status').textContent).toBe('Logscan unavailable.')
  })

  it('restores automatic failures without marking them uploaded', async () => {
    document.getElementById('logscan-upload').remove()
    document.body.insertAdjacentHTML('beforeend', '<table id="logscan-trends-table"><tbody><tr><td><div class="logscan-upload-feedback" data-run-key="failed"></div></td></tr></tbody></table>')
    fetch.mockResolvedValueOnce(reply({ phase: 'idle', run_results: {}, automatic_results: { failed: { phase: 'failed', error: 'Upload could not be confirmed.' } } }))
    const control = initLogscanUpload({ historical: true })
    await flush()
    expect(control.hasResult('failed')).toBe(false)
    expect(document.querySelector('.logscan-upload-feedback').textContent).toBe('Upload could not be confirmed.')
    expect(document.querySelector('.logscan-upload-feedback a')).toBeNull()
  })

  it('continues polling Analytics for new automatic uploads without a manual click', async () => {
    document.getElementById('logscan-upload').remove()
    document.body.insertAdjacentHTML('beforeend', '<table id="logscan-trends-table"><tbody></tbody></table>')
    fetch.mockResolvedValue(reply({ phase: 'idle', automatic_enabled: true }))
    initLogscanUpload({ historical: true })
    await flush()
    await vi.advanceTimersByTimeAsync(15000)
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch.mock.calls.every(([url, options]) => url === '/logscan/upload/status?history=1' && !options?.method)).toBe(true)
  })

  it('keeps saved links stable across automatic background polls', async () => {
    document.getElementById('logscan-upload').remove()
    document.body.insertAdjacentHTML('beforeend', '<table id="logscan-trends-table"><tbody><tr><td><div class="logscan-upload-feedback" data-run-key="auto"></div></td></tr></tbody></table>')
    fetch.mockResolvedValue(reply({ phase: 'idle', automatic_enabled: true, run_results: { auto: completed } }))
    initLogscanUpload({ historical: true })
    await flush()
    const link = document.querySelector('.logscan-upload-feedback a')
    await vi.advanceTimersByTimeAsync(15000)
    expect(document.querySelector('.logscan-upload-feedback a')).toBe(link)
  })

  it('does not upload on initialization or cancelled confirmation', async () => {
    initLogscanUpload()
    await flush()
    window.QS_confirmAction.mockResolvedValue(false)
    document.getElementById('logscan-upload').click()
    await flush()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith('/logscan/upload/status')
  })

  it('posts no config/history payload and displays separate result links', async () => {
    initLogscanUpload()
    await flush()
    fetch.mockResolvedValueOnce(reply({ phase: 'compressing' })).mockResolvedValueOnce(reply(completed))
    document.getElementById('logscan-upload').click()
    await flush()
    expect(fetch).toHaveBeenNthCalledWith(2, '/logscan/upload', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"confirm":true}'
    })
    expect(document.getElementById('logscan-upload').disabled).toBe(true)
    expect(document.getElementById('logscan-upload-status').textContent).toContain('Compressing')
    await vi.advanceTimersByTimeAsync(2000)
    expect(document.getElementById('logscan-upload').disabled).toBe(false)
    expect(document.getElementById('logscan-upload-links').classList.contains('d-none')).toBe(false)
    expect(document.getElementById('logscan-upload-result').href).toBe(completed.result_url)
    expect(document.getElementById('logscan-upload-management').href).toBe(completed.management_url)
  })

  it('copies only the public link', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    fetch.mockResolvedValueOnce(reply(completed))
    initLogscanUpload()
    await flush()
    document.getElementById('logscan-upload-copy').click()
    await flush()
    expect(writeText).toHaveBeenCalledWith(completed.result_url)
    expect(document.getElementById('logscan-upload-status').textContent).toBe('Support link copied.')
  })

  it('restores a queued upload without submitting again', async () => {
    fetch.mockResolvedValueOnce(reply({ phase: 'queued' })).mockResolvedValueOnce(reply(completed))
    initLogscanUpload()
    await flush()
    expect(document.getElementById('logscan-upload').disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(2000)
    expect(fetch.mock.calls.every(([url]) => url === '/logscan/upload/status')).toBe(true)
    expect(document.getElementById('logscan-upload-result').href).toBe(completed.result_url)
  })

  it('shows failures as text and hides old links', async () => {
    initLogscanUpload()
    await flush()
    fetch.mockResolvedValueOnce(reply({ error: 'Current log is not ready.' }, false))
    document.getElementById('logscan-upload').click()
    await flush()
    expect(document.getElementById('logscan-upload-status').textContent).toBe('Current log is not ready.')
    expect(document.getElementById('logscan-upload-links').classList.contains('d-none')).toBe(true)
  })

  it('keeps the existing upload busy while its response is recovered', async () => {
    fetch.mockResolvedValueOnce(reply({ phase: 'checking_status' })).mockResolvedValueOnce(reply(completed))
    initLogscanUpload()
    await flush()
    expect(document.getElementById('logscan-upload').disabled).toBe(true)
    expect(document.getElementById('logscan-upload-status').textContent).toBe('Checking the existing upload with Logscan...')
    await vi.advanceTimersByTimeAsync(2000)
    expect(document.getElementById('logscan-upload').disabled).toBe(false)
    expect(document.getElementById('logscan-upload-result').href).toBe(completed.result_url)
    expect(fetch.mock.calls.every(([url, options]) => url === '/logscan/upload/status' && !options?.method)).toBe(true)
  })

  it('binds once and ignores pages without the upload button', () => {
    initLogscanUpload()
    initLogscanUpload()
    expect(fetch).toHaveBeenCalledTimes(1)
    document.body.innerHTML = ''
    expect(() => initLogscanUpload()).not.toThrow()
  })

  it('uploads an Analytics run using only its run ID and confirmation', async () => {
    document.getElementById('logscan-upload').remove()
    document.body.insertAdjacentHTML('beforeend', '<table id="logscan-trends-table"><tbody></tbody></table>')
    const control = initLogscanUpload({ historical: true })
    await flush()
    document.querySelector('tbody').innerHTML = '<tr><td><button class="logscan-upload-log" data-run-key="old-run" data-run-label="Old Movies"><i></i>Upload</button><div class="logscan-upload-feedback" data-run-key="old-run"></div></td></tr>'
    fetch.mockResolvedValueOnce(reply({ phase: 'preparing' })).mockResolvedValueOnce(reply(completed))
    document.querySelector('.logscan-upload-log i').click()
    await flush()
    expect(fetch).toHaveBeenNthCalledWith(2, '/logscan/upload', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"confirm":true,"run_key":"old-run"}'
    })
    expect(window.QS_confirmAction).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Upload to Logscan', details: expect.stringContaining('Old Movies'), confirmText: 'Upload log', iconClass: 'bi bi-cloud-upload text-info'
    }))
    expect(control.isBusy()).toBe(true)
    expect(document.querySelector('.logscan-upload-feedback').textContent).toContain('Preparing')
    expect(document.querySelector('.logscan-upload-log').disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(2000)
    expect(control.isBusy()).toBe(false)
    expect(document.getElementById('logscan-upload-result').href).toBe(completed.result_url)
    const feedback = document.querySelector('.logscan-upload-feedback')
    expect(feedback.textContent).toContain('Uploaded')
    expect(feedback.querySelector('a').href).toBe(completed.result_url)
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    feedback.querySelector('button').click()
    await flush()
    expect(writeText).toHaveBeenCalledWith(completed.result_url)
    feedback.innerHTML = ''
    control.refresh()
    expect(feedback.textContent).toContain('Uploaded')
  })

  it('shows an already uploaded result next to its Analytics run after reload', async () => {
    document.getElementById('logscan-upload').remove()
    document.body.insertAdjacentHTML('beforeend', '<table id="logscan-trends-table"><tbody><tr><td><div class="logscan-upload-feedback" data-run-key="old-run"></div></td></tr></tbody></table>')
    fetch.mockResolvedValueOnce(reply({ ...completed, run_key: 'old-run', already_uploaded: true }))
    initLogscanUpload({ historical: true })
    await flush()
    expect(document.querySelector('.logscan-upload-feedback').textContent).toContain('Already uploaded')
    expect(document.querySelector('.logscan-upload-feedback a').href).toBe(completed.result_url)
  })

  it('ignores an old status response arriving after upload submission', async () => {
    let resolvePoll
    fetch.mockReturnValueOnce(new Promise(resolve => { resolvePoll = resolve }))
    initLogscanUpload()
    fetch.mockResolvedValueOnce(reply(completed))
    document.getElementById('logscan-upload').click()
    await flush()
    resolvePoll(reply({ phase: 'idle' }))
    await flush()
    expect(document.getElementById('logscan-upload-links').classList.contains('d-none')).toBe(false)
  })

  it('restores every saved run when the latest session job is gone', async () => {
    document.getElementById('logscan-upload').remove()
    document.body.insertAdjacentHTML('beforeend', '<table id="logscan-trends-table"><tbody><tr><td><div class="logscan-upload-feedback" data-run-key="one"></div><div class="logscan-upload-feedback" data-run-key="two"></div></td></tr></tbody></table>')
    const second = { ...completed, result_url: 'https://logscan.kometa.team/scan/second' }
    fetch.mockResolvedValueOnce(reply({ phase: 'idle', run_results: { one: completed, two: second }, restoring: false }))
    const control = initLogscanUpload({ historical: true })
    await flush()
    expect(fetch).toHaveBeenCalledWith('/logscan/upload/status?history=1')
    expect(document.querySelector('[data-run-key="one"] a').href).toBe(completed.result_url)
    expect(document.querySelector('[data-run-key="two"] a').href).toBe(second.result_url)
    expect(control.isBusy()).toBe(false)
    expect(fetch.mock.calls.every(([, options]) => !options?.method)).toBe(true)
  })

  it('hydrates run results from Analytics data even when status is idle', async () => {
    document.getElementById('logscan-upload').remove()
    document.body.insertAdjacentHTML('beforeend', '<table id="logscan-trends-table"><tbody><tr><td><div class="logscan-upload-feedback" data-run-key="one"></div></td></tr></tbody></table>')
    const control = initLogscanUpload({ historical: true })
    await flush()
    control.refresh([{ run_key: 'one', portal_upload: completed }])
    expect(document.querySelector('.logscan-upload-feedback a').href).toBe(completed.result_url)
    control.refresh()
    expect(document.querySelector('.logscan-upload-feedback').textContent).toContain('Uploaded')
  })

  it('polls a local legacy receipt recovery without starting an upload', async () => {
    document.getElementById('logscan-upload').remove()
    document.body.insertAdjacentHTML('beforeend', '<table id="logscan-trends-table"><tbody><tr><td><div class="logscan-upload-feedback" data-run-key="one"></div></td></tr></tbody></table>')
    const control = initLogscanUpload({ historical: true })
    await flush()
    fetch.mockResolvedValueOnce(reply({ phase: 'idle', run_results: {}, restoring: true }))
      .mockResolvedValueOnce(reply({ phase: 'idle', run_results: { one: completed }, restoring: false }))
    control.refresh([{ run_key: 'one', portal_upload_pending: true }])
    await flush()
    await vi.advanceTimersByTimeAsync(2000)
    expect(document.querySelector('.logscan-upload-feedback a').href).toBe(completed.result_url)
    expect(fetch.mock.calls.every(([, options]) => !options?.method)).toBe(true)
    expect(control.isBusy()).toBe(false)
  })

  it('keeps one modal open and waits for approval before posting', async () => {
    let approve
    window.QS_confirmAction.mockReturnValueOnce(new Promise(resolve => { approve = resolve }))
    initLogscanUpload()
    await flush()
    document.getElementById('logscan-upload').click()
    document.getElementById('logscan-upload').click()
    await flush()
    expect(window.QS_confirmAction).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledTimes(1)
    fetch.mockResolvedValueOnce(reply(completed))
    approve(true)
    await flush()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('confirms selected logs once and displays per-run duplicate results', async () => {
    document.getElementById('logscan-upload').remove()
    document.body.insertAdjacentHTML('beforeend', '<button id="logscan-upload-cancel-batch" class="d-none"></button><table id="logscan-trends-table"><tbody><tr><td><div class="logscan-upload-feedback" data-run-key="one"></div><div class="logscan-upload-feedback" data-run-key="two"></div></td></tr></tbody></table>')
    const control = initLogscanUpload({ historical: true })
    await flush()
    fetch.mockResolvedValueOnce(reply({ kind: 'batch', phase: 'uploading', items: [{ run_key: 'one', phase: 'scanning' }, { run_key: 'two', phase: 'waiting' }] }))
      .mockResolvedValueOnce(reply({ kind: 'batch', phase: 'complete', items: [{ ...completed, run_key: 'one', already_uploaded: false }, { ...completed, run_key: 'two', already_uploaded: true }] }))
    await control.uploadSelected([{ run_key: 'one' }, { run_key: 'two' }, { run_key: 'one' }])
    expect(window.QS_confirmAction).toHaveBeenCalledTimes(1)
    expect(window.QS_confirmAction).toHaveBeenCalledWith(expect.objectContaining({ title: 'Upload selected logs', confirmText: 'Upload 2 logs' }))
    expect(fetch).toHaveBeenNthCalledWith(2, '/logscan/upload/batch', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"confirm":true,"run_keys":["one","two"]}'
    })
    expect(control.isBusy()).toBe(true)
    expect(document.querySelector('[data-run-key="two"]').textContent).toContain('Waiting')
    expect(document.getElementById('logscan-upload-cancel-batch').classList.contains('d-none')).toBe(false)
    await vi.advanceTimersByTimeAsync(2000)
    expect(control.isBusy()).toBe(false)
    expect(control.hasResult('one') && control.hasResult('two')).toBe(true)
    expect(document.querySelector('[data-run-key="two"]').textContent).toContain('Already uploaded')
    expect(document.getElementById('logscan-upload-status').textContent).toContain('1 uploaded, 1 already uploaded')
    expect(document.getElementById('logscan-upload-links').classList.contains('d-none')).toBe(true)
  })

  it('does not submit a cancelled batch confirmation', async () => {
    document.getElementById('logscan-upload').remove()
    document.body.insertAdjacentHTML('beforeend', '<table id="logscan-trends-table"></table>')
    const control = initLogscanUpload({ historical: true })
    await flush()
    window.QS_confirmAction.mockResolvedValue(false)
    await control.uploadSelected([{ run_key: 'one' }, { run_key: 'two' }])
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('removes invalidated receipts without restoring stale Analytics links', async () => {
    document.getElementById('logscan-upload').remove()
    document.body.insertAdjacentHTML('beforeend', '<table id="logscan-trends-table"><tbody><tr><td><div class="logscan-upload-feedback" data-run-key="one"></div></td></tr></tbody></table>')
    fetch.mockResolvedValueOnce(reply({ phase: 'idle', run_results: { one: completed }, restoring: true }))
      .mockResolvedValueOnce(reply({ phase: 'idle', run_results: {}, restoring: false }))
    const control = initLogscanUpload({ historical: true })
    await flush()
    expect(control.hasResult('one')).toBe(true)
    await vi.advanceTimersByTimeAsync(2000)
    control.refresh([{ run_key: 'one', portal_upload: completed }])
    expect(control.hasResult('one', completed)).toBe(false)
    expect(document.querySelector('.logscan-upload-feedback a')).toBeNull()
  })

  it('restores a server queue and stops remaining logs without reposting them', async () => {
    document.getElementById('logscan-upload').remove()
    document.body.insertAdjacentHTML('beforeend', '<button id="logscan-upload-cancel-batch"></button><table id="logscan-trends-table"><tr><td><div class="logscan-upload-feedback" data-run-key="two"></div></td></tr></table>')
    fetch.mockResolvedValueOnce(reply({ kind: 'batch', phase: 'uploading', items: [{ ...completed, run_key: 'one' }, { phase: 'waiting', run_key: 'two' }] }))
      .mockResolvedValueOnce(reply({ kind: 'batch', phase: 'complete', cancel_requested: true, items: [{ ...completed, run_key: 'one' }, { phase: 'not_uploaded', run_key: 'two' }] }))
    const control = initLogscanUpload({ historical: true })
    await flush()
    document.getElementById('logscan-upload-cancel-batch').click()
    await flush()
    expect(fetch.mock.calls[1][0]).toBe('/logscan/upload/batch/cancel')
    expect(control.isBusy()).toBe(false)
    expect(document.querySelector('.logscan-upload-feedback').textContent).toBe('Not uploaded.')
    expect(window.QS_confirmAction).not.toHaveBeenCalled()
  })
})
