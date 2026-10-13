// Portal uploads: local analytics and scanning are independent.
export function initLogscanUpload ({ historical = false } = {}) {
  const status = document.getElementById('logscan-upload-status')
  if (!status || status.dataset.uploadBound) return
  status.dataset.uploadBound = 'true'
  const selector = historical ? '.logscan-upload-log' : '#logscan-upload'
  const root = historical ? document.getElementById('logscan-trends-table') : document.getElementById('logscan-upload')
  if (!root) return
  const links = document.getElementById('logscan-upload-links')
  const result = document.getElementById('logscan-upload-result')
  const management = document.getElementById('logscan-upload-management')
  const copy = document.getElementById('logscan-upload-copy')
  const cancel = document.getElementById('logscan-upload-cancel-batch')
  let timer
  let submitting = false
  let confirming = false
  let busy = false
  let pollSequence = 0
  let selectedRunKey = null
  let restorationRequested = false
  let historyLoaded = false
  const runFeedback = new Map()
  const confirmedRuns = new Set()
  const labels = { preparing: 'Preparing archived log...', compressing: 'Compressing log snapshot...', checking: 'Checking for a previous upload...', checking_status: 'Checking the existing upload with Logscan...', uploading: 'Uploading compressed log...', queued: 'Logscan is queued...', validating: 'Logscan is validating the log...', scanning: 'Logscan is scanning...', saving: 'Logscan is saving results...' }

  function updateButtons () {
    document.querySelectorAll(selector).forEach(button => { button.disabled = busy || submitting })
  }

  function message (data) {
    if (data.phase === 'complete') return data.already_uploaded ? 'Already uploaded. Here is the existing support link.' : 'Uploaded. Your support link is ready.'
    if (data.phase === 'failed') return data.error || 'Upload failed.'
    if (data.phase === 'waiting') return 'Waiting in upload queue...'
    if (data.phase === 'not_uploaded') return 'Not uploaded.'
    if (data.phase === 'expired') return 'Previous upload is no longer available.'
    return labels[data.phase] || 'Logscan is processing the upload...'
  }

  function refresh (runs = []) {
    runs.forEach(run => {
      if (!historyLoaded && run.portal_upload) {
        confirmedRuns.add(run.run_key)
        if (!runFeedback.has(run.run_key)) runFeedback.set(run.run_key, run.portal_upload)
      }
    })
    updateButtons()
    document.querySelectorAll('.logscan-upload-feedback').forEach(container => {
      const data = runFeedback.get(container.dataset.runKey)
      const signature = JSON.stringify(data ? [data.phase, data.already_uploaded, data.result_url, data.management_url, data.error] : null)
      if (container.dataset.uploadFeedback === signature && (!data || container.childElementCount > 0)) return
      container.dataset.uploadFeedback = signature
      container.replaceChildren()
      container.classList.toggle('d-none', !data)
      if (!data) return
      const text = document.createElement('div')
      text.className = data.phase === 'complete' ? 'small text-success' : 'small'
      text.textContent = message(data)
      container.append(text)
      if (data.phase !== 'complete') return
      const resultLink = document.createElement('a')
      resultLink.href = data.result_url
      resultLink.target = '_blank'
      resultLink.rel = 'noopener noreferrer'
      resultLink.textContent = 'Open support result'
      const copyLink = document.createElement('button')
      copyLink.type = 'button'
      copyLink.className = 'btn nav-button btn-sm'
      copyLink.dataset.logscanCopyLink = data.result_url
      copyLink.innerHTML = '<i class="bi bi-clipboard" aria-hidden="true"></i> Copy support link'
      const managementLink = document.createElement('a')
      managementLink.href = data.management_url
      managementLink.target = '_blank'
      managementLink.rel = 'noopener noreferrer'
      managementLink.textContent = 'Manage/delete upload (private)'
      container.append(resultLink, copyLink, managementLink)
    })
    if (!restorationRequested && runs.some(run => run.portal_upload_pending)) {
      restorationRequested = true
      poll()
    }
  }

  function updateRunFeedback (data) {
    const runKey = data.run_key || selectedRunKey
    if (historical && runKey && data.phase !== 'idle') runFeedback.set(runKey, data)
    refresh()
  }

  function render (data) {
    clearTimeout(timer)
    busy = !['idle', 'complete', 'failed'].includes(data.phase) || Boolean(data.automatic_pending)
    let resultsChanged = false
    Object.entries(data.automatic_results || {}).forEach(([runKey, saved]) => {
      runFeedback.set(runKey, data.run_results?.[runKey] || saved)
    })
    if (data.run_results) {
      historyLoaded = true
      confirmedRuns.forEach(runKey => {
        if (!data.run_results[runKey]) {
          confirmedRuns.delete(runKey)
          if (runFeedback.get(runKey)?.phase === 'complete') runFeedback.delete(runKey)
          resultsChanged = true
        }
      })
    }
    Object.entries(data.run_results || {}).forEach(([runKey, saved]) => {
      const current = runFeedback.get(runKey)
      if (!confirmedRuns.has(runKey)) resultsChanged = true
      confirmedRuns.add(runKey)
      if (!current || current.phase === 'complete') runFeedback.set(runKey, saved)
    })
    const items = data.kind === 'batch' ? data.items || [] : [data]
    items.forEach(item => {
      if (historical && data.run_results && item.phase === 'complete' && !data.run_results[item.run_key || selectedRunKey]) {
        updateRunFeedback({ ...item, phase: 'expired' })
        return
      }
      const previous = runFeedback.get(item.run_key || selectedRunKey)
      if (item.phase === 'complete' && (previous?.phase !== 'complete' || previous.result_url !== item.result_url)) resultsChanged = true
      if (item.phase === 'complete' && historical) confirmedRuns.add(item.run_key || selectedRunKey)
      if (data.kind === 'batch' && historical) runFeedback.set(item.run_key, item)
      else updateRunFeedback(item)
    })
    refresh()
    links.classList.add('d-none')
    if (cancel) {
      cancel.classList.toggle('d-none', !busy || data.kind !== 'batch')
      cancel.disabled = Boolean(data.cancel_requested)
    }
    if (data.kind === 'batch') {
      const uploaded = items.filter(item => item.phase === 'complete' && !item.already_uploaded).length
      const reused = items.filter(item => item.phase === 'complete' && item.already_uploaded).length
      const failed = items.filter(item => item.phase === 'failed').length
      const notUploaded = items.filter(item => item.phase === 'not_uploaded').length
      status.textContent = `${busy ? `Uploading selected logs: ${uploaded + reused + failed}/${items.length}.` : 'Uploads finished.'} ${uploaded} uploaded, ${reused} already uploaded, ${failed} failed, ${notUploaded} not uploaded.${data.cancel_requested ? ' Remaining uploads stopped.' : ''}${data.error ? ` ${data.error}` : ''}`
    } else if (data.phase === 'complete') {
      result.href = data.result_url
      management.href = data.management_url
      links.classList.remove('d-none')
      status.textContent = message(data)
    } else if (data.phase === 'failed') {
      status.textContent = data.error || 'Upload failed.'
    } else if (data.phase !== 'idle') {
      status.textContent = labels[data.phase] || 'Logscan is processing the upload...'
    } else if (data.automatic_pending) {
      status.textContent = 'Automatic log uploads in progress...'
    } else if (status.textContent === 'Automatic log uploads in progress...') {
      status.textContent = 'Automatic log uploads finished.'
    }
    document.dispatchEvent(new CustomEvent('logscan-upload-change', { detail: { resultsChanged } }))
    if (busy || data.restoring || (historical && data.automatic_enabled)) timer = setTimeout(poll, busy || data.restoring ? 2000 : 15000)
  }

  async function poll () {
    const sequence = ++pollSequence
    try {
      const response = await fetch(historical ? '/logscan/upload/status?history=1' : '/logscan/upload/status')
      if (!response.ok) throw new Error('Cannot retrieve upload status.')
      const data = await response.json()
      if (!submitting && sequence === pollSequence) render(data)
    } catch {
      if (submitting || sequence !== pollSequence) return
      status.textContent = 'Cannot retrieve upload status. Retrying...'
      timer = setTimeout(poll, 5000)
    }
  }

  if (historical) {
    document.addEventListener('quickstart-settings-change', () => {
      if (root.isConnected) poll()
    })
  }

  root.addEventListener('click', async event => {
    const copyButton = event.target.closest('[data-logscan-copy-link]')
    if (copyButton) {
      try {
        await navigator.clipboard.writeText(copyButton.dataset.logscanCopyLink)
        copyButton.textContent = 'Copied'
      } catch {
        copyButton.textContent = 'Copy the support link manually'
      }
      return
    }
    const button = event.target.closest(selector)
    if (!button) return
    const runKey = historical ? button.dataset.runKey : null
    if (historical && !runKey) return
    await submitUpload({ runKey, runLabel: button.dataset.runLabel || runKey })
  })

  async function submitUpload ({ runKey = null, runLabel, runKeys = null }) {
    if (busy || submitting || confirming) return
    if (typeof window.QS_confirmAction !== 'function') {
      status.textContent = 'Reload the page to open upload confirmation.'
      return
    }
    confirming = true
    let confirmed
    try {
      confirmed = await window.QS_confirmAction({
        title: runKeys ? 'Upload selected logs' : 'Upload to Logscan',
        message: runKeys ? `Send ${runKeys.length} selected logs to logscan.kometa.team for scans and support links.` : 'Send this log to logscan.kometa.team for a scan and a support link.',
        details: `${runKeys ? 'Already uploaded logs will reuse their existing links' : historical ? runLabel || runKey : 'Current Kometa log'}. Anonymous uploads. Analytics stay local.`,
        confirmText: runKeys ? `Upload ${runKeys.length} logs` : 'Upload log',
        cancelText: 'Cancel',
        confirmClass: 'btn-primary',
        iconClass: 'bi bi-cloud-upload text-info'
      })
    } catch {
      status.textContent = 'Could not open upload confirmation. Reload the page and try again.'
      return
    } finally {
      confirming = false
    }
    if (!confirmed || busy || submitting) return
    clearTimeout(timer)
    pollSequence++
    submitting = true
    selectedRunKey = runKey
    if (runKeys) runKeys.forEach(key => runFeedback.set(key, { phase: 'waiting', run_key: key }))
    else updateRunFeedback({ phase: 'preparing', run_key: runKey })
    refresh()
    document.dispatchEvent(new CustomEvent('logscan-upload-change', { detail: { resultsChanged: false } }))
    links.classList.add('d-none')
    status.textContent = 'Preparing log upload...'
    try {
      const payload = { confirm: true }
      if (runKey) payload.run_key = runKey
      if (runKeys) payload.run_keys = runKeys
      const response = await fetch(runKeys ? '/logscan/upload/batch' : '/logscan/upload', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      const data = await response.json()
      submitting = false
      if (!response.ok) throw new Error(data.error || 'Could not start upload.')
      render(data)
    } catch (error) {
      submitting = false
      updateButtons()
      status.textContent = error.message
      if (runKeys) runKeys.forEach(key => runFeedback.delete(key))
      else updateRunFeedback({ phase: 'failed', error: error.message, run_key: runKey })
      refresh()
      document.dispatchEvent(new CustomEvent('logscan-upload-change', { detail: { resultsChanged: false } }))
      timer = setTimeout(poll, 2000)
    }
  }
  cancel?.addEventListener('click', async () => {
    cancel.disabled = true
    try {
      const response = await fetch('/logscan/upload/batch/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      if (!response.ok) throw new Error('Could not stop the remaining uploads.')
      render(await response.json())
    } catch (error) {
      status.textContent = error.message
      cancel.disabled = false
      timer = setTimeout(poll, 2000)
    }
  })
  copy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(result.href)
      status.textContent = 'Support link copied.'
    } catch {
      status.textContent = 'Copy the Open support result link manually.'
    }
  })
  poll()
  return {
    isBusy: () => busy || submitting,
    hasResult: (runKey, saved = null) => confirmedRuns.has(runKey) || (!historyLoaded && Boolean(saved)),
    uploadSelected: runs => {
      const keys = [...new Set(runs.map(run => run.run_key).filter(Boolean))]
      if (!keys.length) return
      if (keys.length > 500) {
        status.textContent = 'Select up to 500 logs per upload queue.'
        return
      }
      return submitUpload({ runKeys: keys })
    },
    refresh
  }
}
