/* global $ */

$(document).ready(function () {
  const $tableBody = $('#logscan-trends-table tbody')
  const $summary = $('#logscan-trends-summary')
  const $daily = $('#logscan-trends-daily')
  const $status = $('#logscan-trends-status')
  const $limit = $('#logscan-trends-limit')
  const $refresh = $('#logscan-trends-refresh')

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

  function getDisplayFinished (run) {
    if (!run) return 'n/a'
    if (run.finished_at) return run.finished_at
    return formatTimestamp(run.created_at)
  }

  function getCount (run, key) {
    const value = run && typeof run[key] === 'number' ? run[key] : 0
    return Number.isFinite(value) ? value : 0
  }

  function buildTopSections (sectionRuntimes) {
    if (!sectionRuntimes || typeof sectionRuntimes !== 'object') return 'n/a'
    const entries = Object.entries(sectionRuntimes)
      .filter(([, value]) => typeof value === 'number' && Number.isFinite(value))
    if (!entries.length) return 'n/a'
    entries.sort((a, b) => b[1] - a[1])
    return entries.slice(0, 3)
      .map(([name, seconds]) => `${name}: ${formatSeconds(seconds)}`)
      .join(', ')
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
      const created = run.created_at
      const parsed = new Date(created)
      if (Number.isNaN(parsed.getTime())) return
      const key = parsed.toISOString().slice(0, 10)
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
      const topSections = buildTopSections(run.section_runtimes)
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
          <td class="text-muted small">${escapeHtml(topSections)}</td>
        </tr>
      `
    })
    $tableBody.html(rows.join(''))
  }

  function updateStatus (message) {
    if ($status.length) $status.text(message)
  }

  function fetchRuns () {
    const limit = parseInt($limit.val() || '50', 10)
    const safeLimit = Number.isFinite(limit) ? limit : 50
    updateStatus('Loading trends...')
    fetch(`/logscan/trends?limit=${safeLimit}`)
      .then(res => res.json())
      .then(data => {
        const runs = Array.isArray(data.runs) ? data.runs : []
        renderSummary(runs)
        renderDaily(runs)
        renderTable(runs)
        updateStatus(`Last updated: ${formatTimestamp(new Date().toISOString())}`)
      })
      .catch(err => {
        console.error(err)
        updateStatus('Failed to load trends.')
        $summary.text('Unable to load summary.')
        $daily.text('Unable to load daily totals.')
        $tableBody.html('<tr><td colspan="7" class="text-muted">Unable to load runs.</td></tr>')
      })
  }

  $refresh.on('click', fetchRuns)
  $limit.on('change', fetchRuns)
  fetchRuns()
})
