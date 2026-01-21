/* global $, bootstrap */

$(document).ready(function () {
  const $tableBody = $('#logscan-trends-table tbody')
  const $summary = $('#logscan-trends-summary')
  const $daily = $('#logscan-trends-daily')
  const $status = $('#logscan-trends-status')
  const $progress = $('#logscan-trends-progress')
  const $progressBar = $('#logscan-trends-progress-bar')
  const $progressText = $('#logscan-trends-progress-text')
  const $limit = $('#logscan-trends-limit')
  const $refresh = $('#logscan-trends-refresh')
  const $reset = $('#logscan-trends-reset')
  const $reingest = $('#logscan-trends-reingest')
  const $confirmReset = $('#logscan-confirm-reset')
  const $confirmReingest = $('#logscan-confirm-reingest')
  const $missingDownload = $('#logscan-trends-missing-download')
  const resetModalEl = document.getElementById('logscan-reset-modal')
  const reingestModalEl = document.getElementById('logscan-reingest-modal')
  let reingestPollTimer = null
  let reingestJobId = null

  function escapeHtml (value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
  }

  function formatSeconds (seconds) {
    if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds <= 0) return 'n/a'
    const total = Math.max(0, Math.floor(seconds))
    const hrs = Math.floor(total / 3600)
    const mins = Math.floor((total % 3600) / 60)
    const secs = total % 60
    const parts = []
    if (hrs) parts.push(`${hrs}h`)
    if (mins || hrs) parts.push(`${mins}m`)
    parts.push(`${secs}s`)
    return parts.join(' ')
  }

  function formatTimestamp (value) {
    if (!value) return 'n/a'
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return String(value)
    return parsed.toLocaleString()
  }

  function extractDateKey (value) {
    if (!value) return null
    const match = String(value).match(/(\d{4}-\d{2}-\d{2})/)
    if (match) return match[1]
    const parsed = new Date(value)
    if (!Number.isNaN(parsed.getTime())) return parsed.toISOString().slice(0, 10)
    return null
  }

  function getRunDateKey (run) {
    if (!run) return null
    const finishedKey = extractDateKey(run.finished_at)
    if (finishedKey) return finishedKey
    if (typeof run.log_mtime === 'number' && Number.isFinite(run.log_mtime)) {
      return new Date(run.log_mtime * 1000).toISOString().slice(0, 10)
    }
    return null
  }

  function getDisplayFinished (run) {
    if (!run) return 'n/a'
    if (run.finished_at) return run.finished_at
    if (typeof run.log_mtime === 'number' && Number.isFinite(run.log_mtime)) {
      return formatTimestamp(new Date(run.log_mtime * 1000).toISOString())
    }
    return formatTimestamp(run.created_at)
  }

  function getCount (run, key) {
    const value = run && typeof run[key] === 'number' ? run[key] : 0
    return Number.isFinite(value) ? value : 0
  }

  function buildSectionDetails (sectionRuntimes, runSeconds) {
    if (!sectionRuntimes || typeof sectionRuntimes !== 'object') return ['n/a']
    const entries = Object.entries(sectionRuntimes)
      .filter(([, value]) => typeof value === 'number' && Number.isFinite(value))
    if (!entries.length) return ['n/a']
    entries.sort((a, b) => b[1] - a[1])
    const totalSeconds = entries.reduce((sum, [, seconds]) => sum + seconds, 0)
    const lines = []
    if (Number.isFinite(totalSeconds)) {
      lines.push(`sum: ${formatSeconds(totalSeconds)}`)
    }
    if (typeof runSeconds === 'number' && Number.isFinite(runSeconds)) {
      lines.push(`run total: ${formatSeconds(runSeconds)}`)
      const delta = totalSeconds - runSeconds
      const deltaText = formatSeconds(Math.abs(delta)) || '0s'
      const sign = delta > 0 ? '+' : delta < 0 ? '-' : ''
      lines.push(`delta: ${sign}${deltaText}`)
    }
    entries.forEach(([name, seconds]) => {
      lines.push(`${name}: ${formatSeconds(seconds)}`)
    })
    return lines
  }

  function renderSummary (runs) {
    if (!runs.length) {
      $summary.text('No runs stored yet.')
      return
    }
    const runtimeValues = runs
      .map(run => run.run_time_seconds)
      .filter(val => typeof val === 'number' && Number.isFinite(val) && val > 0)
    const avgRuntime = runtimeValues.length
      ? runtimeValues.reduce((sum, val) => sum + val, 0) / runtimeValues.length
      : null
    const configs = new Set(runs.map(run => run.config_name || 'default'))
    const latest = runs[0]
    const lines = [
      `Runs stored: ${runs.length}`,
      `Latest run: ${getDisplayFinished(latest)}`,
      `Average runtime: ${avgRuntime ? formatSeconds(avgRuntime) : 'n/a'}`,
      `Configs tracked: ${configs.size}`
    ]
    $summary.html(lines.map(line => `<div>${escapeHtml(line)}</div>`).join(''))
  }

  function renderDaily (runs) {
    const dayCounts = {}
    runs.forEach(run => {
      const key = getRunDateKey(run)
      if (!key) return
      dayCounts[key] = (dayCounts[key] || 0) + 1
    })
    const days = Object.keys(dayCounts).sort().slice(-14)
    if (!days.length) {
      $daily.text('No daily totals yet.')
      return
    }
    const maxCount = Math.max(...days.map(day => dayCounts[day]))
    const rows = days.map(day => {
      const count = dayCounts[day]
      const pct = maxCount ? Math.round((count / maxCount) * 100) : 0
      return `
        <div class="d-flex align-items-center gap-2 mb-1">
          <div class="text-muted small" style="width: 96px;">${escapeHtml(day)}</div>
          <div class="flex-grow-1">
            <div class="progress" style="height: 6px;">
              <div class="progress-bar bg-info" style="width: ${pct}%"></div>
            </div>
          </div>
          <div class="text-muted small" style="width: 28px; text-align: right;">${count}</div>
        </div>
      `
    })
    $daily.html(rows.join(''))
  }

  function renderTable (runs) {
    if (!runs.length) {
      $tableBody.html('<tr><td colspan="7" class="text-muted">No runs stored yet.</td></tr>')
      return
    }
    const rows = runs.map(run => {
      const command = run.command_signature || 'n/a'
      const commandTitle = run.run_command || ''
      const counts = `W:${getCount(run, 'warning_count')} E:${getCount(run, 'error_count')} T:${getCount(run, 'trace_count')}`
      const sectionLines = buildSectionDetails(run.section_runtimes, run.run_time_seconds)
      const sectionHtml = sectionLines.map(line => `<div>${escapeHtml(line)}</div>`).join('')
      let kometaDisplay = run.kometa_version || 'n/a'
      if (run.kometa_version && run.kometa_newest_version && run.kometa_version !== run.kometa_newest_version) {
        kometaDisplay = `${run.kometa_version} -> ${run.kometa_newest_version}`
      }
      return `
        <tr>
          <td>${escapeHtml(getDisplayFinished(run))}</td>
          <td>${escapeHtml(formatSeconds(run.run_time_seconds))}</td>
          <td>${escapeHtml(run.config_name || 'default')}</td>
          <td><span title="${escapeHtml(commandTitle)}">${escapeHtml(command)}</span></td>
          <td>${escapeHtml(counts)}</td>
          <td>${escapeHtml(kometaDisplay)}</td>
          <td class="text-muted small">${sectionHtml}</td>
        </tr>
      `
    })
    $tableBody.html(rows.join(''))
  }

  function updateStatus (message) {
    if ($status.length) $status.text(message)
  }

  function setProgressVisible (visible) {
    if (!$progress.length) return
    if (visible) {
      $progress.removeClass('d-none')
    } else {
      $progress.addClass('d-none')
    }
  }

  function updateProgressFromState (state) {
    if (!state || !$progressBar.length) return
    const total = Number.isFinite(state.total) ? state.total : 0
    const scanned = Number.isFinite(state.scanned) ? state.scanned : 0
    const ingested = Number.isFinite(state.ingested) ? state.ingested : 0
    const skippedIncomplete = Number.isFinite(state.skipped_incomplete) ? state.skipped_incomplete : 0
    const skippedInvalid = Number.isFinite(state.skipped_invalid) ? state.skipped_invalid : 0
    const errors = Number.isFinite(state.errors) ? state.errors : 0
    const pct = total ? Math.min(100, Math.round((scanned / total) * 100)) : 0
    $progressBar.css('width', `${pct}%`)
    const pieces = [
      `Scanned: ${scanned}/${total}`,
      `Ingested: ${ingested}`,
      `Skipped: ${skippedIncomplete + skippedInvalid}`,
      `Errors: ${errors}`
    ]
    if (state.current_file) {
      pieces.unshift(`Processing: ${state.current_file}`)
    }
    if ($progressText.length) {
      $progressText.text(pieces.join(' | '))
    }
  }

  function hideModal (modalEl) {
    if (!modalEl) return
    const instance = bootstrap.Modal.getInstance(modalEl)
    if (instance) instance.hide()
  }

  function setControlsDisabled (disabled) {
    $reset.prop('disabled', disabled)
    $reingest.prop('disabled', disabled)
    $refresh.prop('disabled', disabled)
    $limit.prop('disabled', disabled)
    $confirmReset.prop('disabled', disabled)
    $confirmReingest.prop('disabled', disabled)
  }

  function setMissingDownloadVisible (visible, count) {
    if (visible) {
      if (typeof count === 'number') {
        $missingDownload.text(`Download missing people log (${count})`)
      } else {
        $missingDownload.text('Download missing people log')
      }
      $missingDownload.removeClass('d-none')
    } else {
      $missingDownload.addClass('d-none')
    }
  }

  function checkMissingDownload () {
    fetch('/logscan/trends/people-missing/status')
      .then(res => res.json())
      .then(data => {
        const exists = Boolean(data && data.exists)
        const count = data && typeof data.missing_people_unique === 'number'
          ? data.missing_people_unique
          : undefined
        setMissingDownloadVisible(exists, count)
      })
      .catch(() => {
        setMissingDownloadVisible(false)
      })
  }

  function handleReset () {
    setControlsDisabled(true)
    hideModal(resetModalEl)
    updateStatus('Resetting trends...')
    fetch('/logscan/trends/reset', { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        if (data && data.success) {
          updateStatus('Trends cleared. Reingest logs when you are ready.')
          fetchRuns({ suppressStatus: true })
          setMissingDownloadVisible(false)
        } else {
          updateStatus('Reset failed.')
        }
      })
      .catch(err => {
        console.error(err)
        updateStatus('Reset failed.')
      })
      .finally(() => {
        setControlsDisabled(false)
      })
  }

  function applyReingestSummary (data) {
    const summary = [
      `Scanned: ${data.scanned || 0}`,
      `Ingested: ${data.ingested || 0}`,
      `Duplicates: ${data.duplicates || 0}`,
      `Skipped incomplete: ${data.skipped_incomplete || 0}`,
      `Skipped invalid: ${data.skipped_invalid || 0}`,
      `Errors: ${data.errors || 0}`,
      `Missing people (deduped): ${data.missing_people_unique || 0}`
    ].join(' | ')
    updateStatus(`Reingest complete. ${summary}`)
    fetchRuns({ suppressStatus: true })
    setMissingDownloadVisible(Boolean(data.missing_people_log_ready), data.missing_people_unique)
    setProgressVisible(false)
    setControlsDisabled(false)
  }

  function stopReingestPolling () {
    if (reingestPollTimer) {
      clearInterval(reingestPollTimer)
      reingestPollTimer = null
    }
    reingestJobId = null
  }

  function fetchReingestStatus (jobId) {
    const query = jobId ? `?job=${encodeURIComponent(jobId)}` : ''
    fetch(`/logscan/trends/reingest/status${query}`)
      .then(res => res.json().then(data => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (!ok || !data) return
        if (data.status === 'running') {
          updateProgressFromState(data)
          updateStatus('Reingesting logs...')
          if (!reingestPollTimer) {
            reingestJobId = data.job_id || jobId || null
            setProgressVisible(true)
            setControlsDisabled(true)
            reingestPollTimer = setInterval(() => fetchReingestStatus(reingestJobId), 1500)
          }
          return
        }
        if (data.status === 'complete') {
          stopReingestPolling()
          applyReingestSummary(data)
          return
        }
        if (data.status === 'error') {
          stopReingestPolling()
          updateStatus(data.error || 'Reingest failed.')
          setProgressVisible(false)
          setControlsDisabled(false)
        }
      })
      .catch(err => {
        console.error(err)
      })
  }

  function startReingestPolling (jobId) {
    stopReingestPolling()
    reingestJobId = jobId || null
    setProgressVisible(true)
    setControlsDisabled(true)
    fetchReingestStatus(reingestJobId)
    reingestPollTimer = setInterval(() => fetchReingestStatus(reingestJobId), 1500)
  }

  function handleReingest () {
    setControlsDisabled(true)
    hideModal(reingestModalEl)
    updateStatus('Starting reingest...')
    setProgressVisible(true)
    fetch('/logscan/trends/reingest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reset: false, background: true })
    })
      .then(res => res.json().then(data => ({ ok: res.ok, status: res.status, data })))
      .then(({ ok, status, data }) => {
        if (ok && data && data.job_id) {
          startReingestPolling(data.job_id)
          return
        }
        if (status === 409 && data && data.job_id) {
          updateStatus('Reingest already running. Showing progress...')
          startReingestPolling(data.job_id)
          return
        }
        if (data && data.success) {
          applyReingestSummary(data)
          return
        }
        updateStatus(data && data.error ? data.error : 'Reingest failed.')
      })
      .catch(err => {
        console.error(err)
        updateStatus('Reingest failed.')
      })
      .finally(() => {
        if (!reingestJobId) {
          setProgressVisible(false)
          setControlsDisabled(false)
        }
      })
  }

  function fetchRuns (options = {}) {
    const suppressStatus = options && options.suppressStatus
    const limit = parseInt($limit.val() || '50', 10)
    const safeLimit = Number.isFinite(limit) ? limit : 50
    if (!suppressStatus) updateStatus('Loading trends...')
    fetch(`/logscan/trends?limit=${safeLimit}`)
      .then(res => res.json())
      .then(data => {
        const runs = Array.isArray(data.runs) ? data.runs : []
        renderSummary(runs)
        renderDaily(runs)
        renderTable(runs)
        if (!suppressStatus) {
          updateStatus(`Last updated: ${formatTimestamp(new Date().toISOString())}`)
        }
      })
      .catch(err => {
        console.error(err)
        if (!suppressStatus) updateStatus('Failed to load trends.')
        $summary.text('Unable to load summary.')
        $daily.text('Unable to load daily totals.')
        $tableBody.html('<tr><td colspan="7" class="text-muted">Unable to load runs.</td></tr>')
      })
  }

  $refresh.on('click', fetchRuns)
  $limit.on('change', fetchRuns)
  $confirmReset.on('click', handleReset)
  $confirmReingest.on('click', handleReingest)
  checkMissingDownload()
  fetchRuns()
  fetchReingestStatus()
})
