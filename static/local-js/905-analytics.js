/* global $, bootstrap */

$(document).ready(function () {
  const $tableBody = $('#logscan-trends-table tbody')
  const $tableSummary = $('#logscan-table-summary')
  const $tablePolicy = $('#logscan-table-policy')
  const $tableSortKey = $('#logscan-table-sort-key')
  const $tableSortDir = $('#logscan-table-sort-dir')
  const $tablePageSize = $('#logscan-table-page-size')
  const $tableFilterCount = $('#logscan-table-filter-count')
  const $tablePageInfo = $('#logscan-table-page-info')
  const $tablePrev = $('#logscan-table-prev')
  const $tableNext = $('#logscan-table-next')
  const $tableToggle = $('#logscan-table-toggle')
  const $tableSelectAll = $('#logscan-table-select-all')
  const $tableSelectComplete = $('#logscan-table-select-complete')
  const $tableSelectIncomplete = $('#logscan-table-select-incomplete')
  const $tableClearSelection = $('#logscan-table-clear-selection')
  const $tableCompressSelected = $('#logscan-table-compress-selected')
  const $tableDeleteSelected = $('#logscan-table-delete-selected')
  const $tableSelectionSummary = $('#logscan-table-selection-summary')
  const tableCollapseEl = document.getElementById('logscan-recent-runs-collapse')
  const $summary = $('#logscan-trends-summary')
  const $daily = $('#logscan-trends-daily')
  const $dailyRuntime = $('#logscan-trends-daily-runtime')
  const $runtime = $('#logscan-trends-runtime')
  const $imagemaidSummary = $('#logscan-trends-imagemaid-summary')
  const $imagemaidRecovered = $('#logscan-trends-imagemaid-recovered')
  const $imagemaidFiles = $('#logscan-trends-imagemaid-files')
  const $imagemaidModes = $('#logscan-trends-imagemaid-modes')
  const $counts = $('#logscan-trends-counts')
  const $countsSeries = $('#logscan-trends-counts-series')
  const $ingest = $('#logscan-trends-ingest')
  const $issues = $('#logscan-trends-issues')
  const $libraries = $('#logscan-trends-libraries')
  const $libraryFilter = $('#logscan-trends-library-filter, #logscan-trends-library-filter-bottom')
  const $status = $('#logscan-trends-status')
  const $progress = $('#logscan-trends-progress')
  const $progressBar = $('#logscan-trends-progress-bar')
  const $progressText = $('#logscan-trends-progress-text')
  const $limit = $('#logscan-trends-limit, #logscan-trends-limit-bottom')
  const $configFilter = $('#logscan-trends-config-filter, #logscan-trends-config-filter-bottom')
  const $toolFilter = $('#logscan-trends-tool-filter, #logscan-trends-tool-filter-bottom')
  const $timeRange = $('#logscan-trends-time-range, #logscan-trends-time-range-bottom')
  const $commandFilter = $('#logscan-trends-command-filter, #logscan-trends-command-filter-bottom')
  const $resetFilters = $('#logscan-trends-reset-filters, #logscan-trends-reset-filters-bottom')
  const $dateStart = $('#logscan-trends-date-start, #logscan-trends-date-start-bottom')
  const $dateEnd = $('#logscan-trends-date-end, #logscan-trends-date-end-bottom')
  const $customDateRow = $('#logscan-trends-custom-date-row, #logscan-trends-custom-date-row-bottom')
  const $dateHint = $('#logscan-trends-date-hint, #logscan-trends-date-hint-bottom')
  const $runCount = $('#logscan-trends-count, #logscan-trends-count-bottom')
  const $reset = $('#logscan-trends-reset')
  const $reingest = $('#logscan-trends-reingest')
  const $clearInvalidArchived = $('#logscan-trends-clear-invalid')
  const $confirmReset = $('#logscan-confirm-reset')
  const $confirmReingest = $('#logscan-confirm-reingest')
  const $missingDownload = $('#logscan-trends-missing-download')
  const $invalidLogBody = $('#logscan-invalid-log-body')
  const $invalidLogStatus = $('#logscan-invalid-log-status')
  const $invalidLogSuccess = $('#logscan-invalid-log-success')
  const $invalidLogError = $('#logscan-invalid-log-error')
  const $confirmInvalidLog = $('#logscan-confirm-invalid-log')
  const $cancelInvalidLog = $('#logscan-cancel-invalid-log')
  const $confirmMissingDownload = $('#logscan-confirm-missing-download')
  const $deleteLogBody = $('#logscan-delete-log-body')
  const $deleteLogStatus = $('#logscan-delete-log-status')
  const $deleteLogSuccess = $('#logscan-delete-log-success')
  const $deleteLogError = $('#logscan-delete-log-error')
  const $confirmDeleteLog = $('#logscan-confirm-delete-log')
  const $cancelDeleteLog = $('#logscan-cancel-delete-log')
  const $compressLogBody = $('#logscan-compress-log-body')
  const $compressLogStatus = $('#logscan-compress-log-status')
  const $compressLogSuccess = $('#logscan-compress-log-success')
  const $compressLogError = $('#logscan-compress-log-error')
  const $confirmCompressLog = $('#logscan-confirm-compress-log')
  const $cancelCompressLog = $('#logscan-cancel-compress-log')
  const $runDetailsBody = $('#logscan-run-details-body')
  const $runDetailsTitle = $('#logscan-run-details-title')
  const $preferencesSave = $('#logscan-preferences-save')
  const $preferencesRecommended = $('#logscan-preferences-recommended')
  const $preferencesStatus = $('#logscan-preferences-status')
  const $preferencesInputs = $('.logscan-pref-input')
  const resetModalEl = document.getElementById('logscan-reset-modal')
  const reingestModalEl = document.getElementById('logscan-reingest-modal')
  const invalidLogModalEl = document.getElementById('logscan-invalid-log-modal')
  const missingDownloadModalEl = document.getElementById('logscan-missing-download-modal')
  const deleteLogModalEl = document.getElementById('logscan-delete-log-modal')
  const compressLogModalEl = document.getElementById('logscan-compress-log-modal')
  const runDetailsModalEl = document.getElementById('logscan-run-details-modal')
  const preferencesModalEl = document.getElementById('logscan-preferences-modal')
  let missingDownloadUrl = ''
  let pendingInvalidLogCleanup = null
  let pendingDeleteRun = null
  let pendingCompressRun = null
  let reingestPollTimer = null
  let reingestJobId = null
  let autoReingestTriggered = false
  let allRuns = []
  let allIncompleteRuns = []
  let allTableRuns = []
  const sectionDetailsByRunKey = new Map()
  const expandedProgressRunKeys = new Set()
  let currentFilteredRuns = []
  let currentTableRuns = []
  let allRunsTotal = 0
  let allIncompleteRunsTotal = 0
  let latestArchiveStorage = null
  let tablePage = 1
  let tableStatusFilter = 'all'
  const selectedRunKeys = new Set()
  const sortState = { key: 'finished_at', dir: 'desc' }
  let lastIngestState = null
  let analyticsPrefs = null
  const defaultReingestButtonLabel = $reingest.text().trim() || 'Reingest logs'

  function syncMirroredControlValue ($controls, source) {
    if (!$controls.length || !source) return
    const value = $(source).val()
    $controls.each(function () {
      if (this === source) return
      $(this).val(value)
    })
  }

  function escapeHtml (value) {
    return String(value || '')
      .replaceAll(/&/g, '&amp;')
      .replaceAll(/</g, '&lt;')
      .replaceAll(/>/g, '&gt;')
      .replaceAll(/"/g, '&quot;')
      .replaceAll(/'/g, '&#39;')
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

  function formatAverage (value) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '0'
    if (Number.isInteger(value)) return String(value)
    return value.toFixed(1).replace(/\.0$/, '')
  }

  function formatCompactNumber (value) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '0'
    const rounded = Math.round(value)
    if (Math.abs(rounded) >= 1000000) return `${(rounded / 1000000).toFixed(1).replace(/\.0$/, '')}M`
    if (Math.abs(rounded) >= 1000) return `${(rounded / 1000).toFixed(1).replace(/\.0$/, '')}K`
    return String(rounded)
  }

  function formatBytes (value) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return 'n/a'
    if (value === 0) return '0 B'
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    let size = value
    let unitIndex = 0
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024
      unitIndex += 1
    }
    const precision = size >= 10 || unitIndex === 0 ? 1 : 2
    const rounded = Number(size.toFixed(precision))
    const display = Number.isInteger(rounded) ? String(rounded) : String(rounded)
    return `${display} ${units[unitIndex]}`
  }

  function formatTimestamp (value) {
    if (!value) return null
    const text = String(value).trim()
    const match = text.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})/)
    const hasTimezone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(text)
    if (match && !hasTimezone) return `${match[1]} ${match[2]}`
    if (!/\d{4}-\d{2}-\d{2}/.test(text)) return null
    const parsed = new Date(text)
    if (Number.isNaN(parsed.getTime())) return null
    const yyyy = parsed.getFullYear()
    const MM = String(parsed.getMonth() + 1).padStart(2, '0')
    const dd = String(parsed.getDate()).padStart(2, '0')
    const hh = String(parsed.getHours()).padStart(2, '0')
    const mm = String(parsed.getMinutes()).padStart(2, '0')
    const ss = String(parsed.getSeconds()).padStart(2, '0')
    return `${yyyy}-${MM}-${dd} ${hh}:${mm}:${ss}`
  }

  function formatShortTimestamp (value) {
    const full = formatTimestamp(value)
    if (!full) return null
    const match = full.match(/^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})/)
    if (match) return `${match[1]} ${match[2]}`
    return full
  }

  function extractDateKey (value) {
    if (!value) return null
    const match = String(value).match(/(\d{4}-\d{2}-\d{2})/)
    if (match) return match[1]
    const parsed = new Date(value)
    if (!Number.isNaN(parsed.getTime())) return parsed.toISOString().slice(0, 10)
    return null
  }

  function isFutureDateKey (key) {
    if (!key) return false
    const parsed = new Date(`${key}T00:00:00`)
    if (Number.isNaN(parsed.getTime())) return false
    const now = new Date()
    const cutoff = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
    return parsed > cutoff
  }

  function getSortTimestamp (run) {
    if (!run) return null
    if (run.finished_at) {
      const parsed = new Date(run.finished_at)
      if (!Number.isNaN(parsed.getTime())) return parsed.getTime()
    }
    if (typeof run.log_mtime === 'number' && Number.isFinite(run.log_mtime)) {
      return run.log_mtime * 1000
    }
    if (run.created_at) {
      const created = new Date(run.created_at)
      if (!Number.isNaN(created.getTime())) return created.getTime()
    }
    return null
  }

  function tokenizeCommand (command) {
    if (!command) return []
    const tokens = []
    const regex = /"([^"]*)"|'([^']*)'|(\S+)/g
    let match
    while ((match = regex.exec(command)) !== null) {
      tokens.push(match[1] || match[2] || match[3] || '')
    }
    return tokens
  }

  function normalizeRunCommand (command) {
    if (!command) return ''
    const tokens = tokenizeCommand(command)
    if (!tokens.length) return ''
    let baseCommand = 'kometa.py'
    let startIndex = tokens.findIndex(token => /kometa\.py$/i.test(token))
    const imagemaidIndex = tokens.findIndex(token => /imagemaid(?:\.py)?$/i.test(token))
    if (imagemaidIndex >= 0 && (startIndex < 0 || imagemaidIndex < startIndex)) {
      baseCommand = 'imagemaid'
      startIndex = imagemaidIndex
    } else if (startIndex >= 0) {
      baseCommand = 'kometa.py'
    } else if (tokens[0] && !String(tokens[0]).startsWith('-')) {
      startIndex = 0
      if (/imagemaid(?:\.py)?$/i.test(tokens[0])) {
        baseCommand = 'imagemaid'
      } else if (/kometa\.py$/i.test(tokens[0])) {
        baseCommand = 'kometa.py'
      } else {
        baseCommand = String(tokens[0])
      }
    } else {
      startIndex = -1
    }
    const args = tokens.slice(startIndex + 1)
    const groups = []
    for (let i = 0; i < args.length; i += 1) {
      const token = args[i]
      if (!token) continue
      if (token.startsWith('-')) {
        if (token.includes('=')) {
          const [flag, value] = token.split('=', 2)
          groups.push({ flag, value: value || null })
          continue
        }
        const next = args[i + 1]
        if (next && !next.startsWith('-')) {
          groups.push({ flag: token, value: next })
          i += 1
        } else {
          groups.push({ flag: token, value: null })
        }
      } else {
        groups.push({ flag: '', value: token })
      }
    }
    groups.sort((a, b) => {
      const aKey = a.flag.toLowerCase()
      const bKey = b.flag.toLowerCase()
      if (aKey === bKey) {
        return String(a.value || '').localeCompare(String(b.value || ''))
      }
      if (!aKey) return 1
      if (!bKey) return -1
      return aKey.localeCompare(bKey)
    })
    const parts = [baseCommand]
    groups.forEach(group => {
      if (group.flag) {
        if (group.value) {
          const needsQuotes = /\s/.test(group.value)
          const value = needsQuotes ? `"${group.value}"` : group.value
          parts.push(`${group.flag} ${value}`)
        } else {
          parts.push(group.flag)
        }
      } else if (group.value) {
        const needsQuotes = /\s/.test(group.value)
        parts.push(needsQuotes ? `"${group.value}"` : group.value)
      }
    })
    return parts.join(' ').trim()
  }

  function getDefaultToolFilterValue (tools) {
    return ''
  }

  function getRunCommandValue (run) {
    if (!run) return ''
    if (run.run_command) return normalizeRunCommand(run.run_command)
    if (run.command_signature) {
      const toolName = getRunToolName(run)
      const baseCommand = toolName === 'imagemaid' ? 'imagemaid' : 'kometa.py'
      return normalizeRunCommand(`${baseCommand} ${run.command_signature}`)
    }
    return ''
  }

  function getRunToolName (run) {
    if (!run) return 'kometa'
    return String(run.tool_name || 'kometa').trim().toLowerCase() || 'kometa'
  }

  function getRunToolLabel (run) {
    return getRunToolName(run) === 'imagemaid' ? 'ImageMaid' : 'Kometa'
  }

  function getRunToolIconPath (run) {
    return getRunToolName(run) === 'imagemaid'
      ? '/static/images/app-icons/imagemaid.png'
      : '/static/images/app-icons/kometa.png'
  }

  function renderRunToolIndicator (run) {
    const label = getRunToolLabel(run)
    const iconPath = getRunToolIconPath(run)
    return `
      <span class="logscan-app-indicator">
        <img src="${escapeHtml(iconPath)}" alt="" class="logscan-app-indicator__icon" aria-hidden="true">
        <span>${escapeHtml(label)}</span>
      </span>
    `
  }

  function getKometaStartMode (run) {
    if (!run || getRunToolName(run) !== 'kometa') return ''
    const mode = String(run.start_mode || '').trim().toLowerCase()
    return ['current', 'recovery', 'logged'].includes(mode) ? mode : ''
  }

  function getKometaStartModeLabel (run) {
    const mode = getKometaStartMode(run)
    if (mode === 'recovery') return 'Recovery'
    if (mode === 'logged') return 'Logged'
    if (mode === 'current') return 'Current'
    return ''
  }

  function renderKometaStartModeBadge (run) {
    const label = getKometaStartModeLabel(run)
    if (!label) return ''
    return `<span class="badge text-bg-secondary ms-2">Start: ${escapeHtml(label)}</span>`
  }

  function getImagemaidMode (run) {
    const direct = String(run && run.imagemaid_mode ? run.imagemaid_mode : '').trim().toLowerCase()
    if (direct) return direct
    const signatureMatch = String(run && run.command_signature ? run.command_signature : '').match(/--mode\s+([a-z]+)/i)
    if (signatureMatch) return String(signatureMatch[1] || '').trim().toLowerCase()
    const commandMatch = String(run && run.run_command ? run.run_command : '').match(/--mode\s+([a-z]+)/i)
    if (commandMatch) return String(commandMatch[1] || '').trim().toLowerCase()
    return 'unknown'
  }

  function getRunDateKey (run) {
    if (!run) return null
    const finishedKey = extractDateKey(run.finished_at)
    if (finishedKey && !isFutureDateKey(finishedKey)) return finishedKey
    if (typeof run.log_mtime === 'number' && Number.isFinite(run.log_mtime)) {
      const key = new Date(run.log_mtime * 1000).toISOString().slice(0, 10)
      if (!isFutureDateKey(key)) return key
    }
    return null
  }

  function isDateWithinRange (dateKey, start, end) {
    if (!dateKey) return false
    if (start && dateKey < start) return false
    if (end && dateKey > end) return false
    return true
  }

  function getDisplayFinished (run) {
    if (!run) return 'n/a'
    const finished = formatTimestamp(run.finished_at)
    if (finished) return finished
    if (typeof run.log_mtime === 'number' && Number.isFinite(run.log_mtime)) {
      const mtime = formatTimestamp(new Date(run.log_mtime * 1000).toISOString())
      if (mtime) return mtime
    }
    const created = formatTimestamp(run.created_at)
    return created || 'n/a'
  }

  function getDisplayStarted (run) {
    if (!run) return 'n/a'
    const started = formatTimestamp(run.started_at)
    return started || 'n/a'
  }

  function getSectionTotal (sectionRuntimes) {
    if (!sectionRuntimes || typeof sectionRuntimes !== 'object') return 0
    return Object.values(sectionRuntimes).reduce((sum, value) => {
      if (typeof value === 'number' && Number.isFinite(value)) return sum + value
      return sum
    }, 0)
  }

  function getRunTimeParts (run) {
    const raw = run && typeof run.run_time_seconds === 'number' && Number.isFinite(run.run_time_seconds)
      ? run.run_time_seconds
      : 0
    const sectionTotal = getSectionTotal(run && run.section_runtimes)
    const effective = Math.max(raw, sectionTotal)
    return { raw, sectionTotal, effective }
  }

  function getEffectiveRunTimeSeconds (run) {
    return getRunTimeParts(run).effective
  }

  function getRuntimeHelpText (run) {
    const parts = getRunTimeParts(run)
    if (parts.raw > 0 && parts.sectionTotal > parts.raw + 60) {
      return `Displayed from section runtimes (${formatSeconds(parts.sectionTotal)}) because the parsed run total was ${formatSeconds(parts.raw)}. Reingest logs after this update to refresh stored run totals.`
    }
    return 'Total run time parsed from the run summary.'
  }

  function getMaintenanceSummary (run) {
    const summary = run && run.maintenance_summary && typeof run.maintenance_summary === 'object'
      ? run.maintenance_summary
      : {}
    return {
      hadPause: Boolean(run && run.maintenance_had_pause) || Boolean(summary.had_pause),
      pauseCount: Number.isFinite(summary.pause_count) ? summary.pause_count : 0,
      pauseSeconds: Number.isFinite(summary.pause_seconds) ? summary.pause_seconds : 0,
      openPause: Boolean(summary.open_pause),
      window: summary.window || '',
      events: Array.isArray(summary.events) ? summary.events : []
    }
  }

  function getMaintenanceSortValue (run) {
    const summary = getMaintenanceSummary(run)
    if (!summary.hadPause) return 0
    const seconds = Number.isFinite(summary.pauseSeconds) ? summary.pauseSeconds : 0
    const count = Number.isFinite(summary.pauseCount) ? summary.pauseCount : 0
    return (seconds * 100) + count + (summary.openPause ? 1 : 0)
  }

  function renderMaintenanceSummaryCell (run) {
    const summary = getMaintenanceSummary(run)
    if (!summary.hadPause) {
      return '<span class="text-muted">No pause</span>'
    }
    const parts = [`Paused ${summary.pauseCount || 1}x`]
    if (summary.pauseSeconds > 0) {
      parts.push(formatSeconds(summary.pauseSeconds))
    }
    if (summary.openPause) {
      parts.push('open')
    }
    const detailParts = []
    if (summary.window) {
      detailParts.push(`Window: ${summary.window}`)
    }
    if (summary.events.length) {
      detailParts.push(`Events: ${summary.events.map(event => event.event).join(', ')}`)
    }
    const title = detailParts.join(' | ')
    return `<span title="${escapeHtml(title)}">${escapeHtml(parts.join(' • '))}</span>`
  }

  function getProgressSnapshot (run) {
    const snapshot = run && run.progress_snapshot && typeof run.progress_snapshot === 'object'
      ? run.progress_snapshot
      : (run && run.resume_progress_snapshot && typeof run.resume_progress_snapshot === 'object'
          ? run.resume_progress_snapshot
          : null)
    if (!snapshot) return null
    const columns = Array.isArray(snapshot.columns) ? snapshot.columns : []
    const rows = Array.isArray(snapshot.rows) ? snapshot.rows : []
    if (!columns.length || !rows.length) return null
    return snapshot
  }

  function renderProgressSnapshotCellLabel (cell) {
    const safeCell = cell && typeof cell === 'object' ? cell : {}
    if (!safeCell.label) return '<span class="text-muted small">—</span>'
    const tone = String(safeCell.tone || '').trim().toLowerCase()
    const toneMap = {
      primary: 'text-bg-primary',
      success: 'text-bg-success',
      warning: 'text-bg-warning',
      danger: 'text-bg-danger',
      info: 'text-bg-info',
      secondary: 'text-bg-secondary'
    }
    const badgeClass = toneMap[tone] || 'text-bg-success'
    return `<span class="badge ${badgeClass}">${escapeHtml(safeCell.label)}</span>`
  }

  function renderProgressSnapshotPanel (run, snapshot) {
    const columns = Array.isArray(snapshot.columns) ? snapshot.columns : []
    const rows = Array.isArray(snapshot.rows) ? snapshot.rows : []
    const footerCells = Array.isArray(snapshot.footer_cells) ? snapshot.footer_cells : []
    const preparationLabel = snapshot.preparation_label || ''
    const totalLabel = snapshot.total_label || ''
    const nameLabel = snapshot.name_label || 'Library'
    const typeLabel = snapshot.type_label || 'Type'
    const maintenance = getMaintenanceSummary(run)
    const prepRow = preparationLabel
      ? `<div class="logscan-progress-inline-row"><span class="fw-semibold">Preparation</span><span class="badge text-bg-primary">${escapeHtml(preparationLabel)}</span></div>`
      : ''
    let maintenanceRow = ''
    if (maintenance.hadPause) {
      const maintText = maintenance.pauseSeconds > 0
        ? formatSeconds(maintenance.pauseSeconds)
        : `${maintenance.pauseCount || 1} pause${(maintenance.pauseCount || 1) === 1 ? '' : 's'}`
      const maintDetails = maintenance.window ? ` <span class="text-muted small">(${escapeHtml(maintenance.window)})</span>` : ''
      maintenanceRow = `<div class="logscan-progress-inline-row"><span class="fw-semibold">Maintenance</span><span class="badge text-bg-primary">${escapeHtml(maintText)}</span>${maintDetails}</div>`
    }
    const headCells = columns.map(column => `<th scope="col" class="text-end">${escapeHtml(column.label || column.key || '')}</th>`).join('')
    const bodyRows = rows.map(row => {
      const phaseCells = Array.isArray(row.phase_cells) ? row.phase_cells : []
      const statusClass = row.status_class ? ` ${escapeHtml(row.status_class)}` : ''
      const phaseHtml = columns.map((column, index) => `<td class="text-end">${renderProgressSnapshotCellLabel(phaseCells[index])}</td>`).join('')
      return `
        <tr>
          <td>${escapeHtml(row.name || '—')}</td>
          <td>${escapeHtml(row.type || '—')}</td>
          <td><span class="badge${statusClass}">${escapeHtml(row.status || 'Pending')}</span></td>
          ${phaseHtml}
        </tr>
      `
    }).join('')
    const footerHtml = columns.map((column, index) => {
      const label = footerCells[index] || ''
      return `<td class="text-end">${label ? renderProgressSnapshotCellLabel({ label, tone: 'success' }) : '<span class="text-muted small">—</span>'}</td>`
    }).join('')
    return `
      <div class="logscan-progress-panel-inner">
        ${prepRow}
        ${maintenanceRow}
        <div class="table-responsive logscan-progress-table-wrap" data-qs-sticky-first="true">
          <table class="table table-sm table-striped mb-0 qs-incomplete-progress-table qs-analytics-progress-table">
            <thead>
              <tr>
                <th scope="col">${escapeHtml(nameLabel)}</th>
                <th scope="col">${escapeHtml(typeLabel)}</th>
                <th scope="col">Status</th>
                ${headCells}
              </tr>
            </thead>
            <tbody>
              ${bodyRows}
            </tbody>
            <tfoot>
              <tr class="table-group-divider">
                <th scope="row" class="fw-semibold">Total</th>
                <td><span class="text-muted small">—</span></td>
                <td>${totalLabel ? renderProgressSnapshotCellLabel({ label: totalLabel, tone: 'success' }) : '<span class="text-muted small">—</span>'}</td>
                ${footerHtml}
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    `
  }

  function renderProgressSnapshotCell (run, runKey) {
    const snapshot = getProgressSnapshot(run)
    if (!snapshot) return '<span class="text-muted">n/a</span>'
    const expanded = expandedProgressRunKeys.has(runKey)
    const buttonLabel = expanded ? 'Hide matrix' : 'View matrix'
    return `
      <div class="logscan-progress-head">
        <button type="button"
          class="btn nav-button btn-sm logscan-action-btn logscan-progress-toggle"
          data-run-key="${escapeHtml(runKey)}"
          aria-expanded="${expanded ? 'true' : 'false'}">
          ${buttonLabel}
        </button>
      </div>
      <div class="logscan-progress-panel${expanded ? '' : ' d-none'}" data-run-key="${escapeHtml(runKey)}">
          ${renderProgressSnapshotPanel(run, snapshot)}
      </div>
    `
  }

  function getQuietPeriodSummary (run) {
    const summary = run && run.quiet_period_summary && typeof run.quiet_period_summary === 'object'
      ? run.quiet_period_summary
      : {}
    return {
      longestGapSeconds: Number.isFinite(summary.longest_gap_seconds) ? summary.longest_gap_seconds : 0,
      longestGapStartedAt: summary.longest_gap_started_at || '',
      longestGapEndedAt: summary.longest_gap_ended_at || '',
      longestGapStartLine: Number.isFinite(summary.longest_gap_start_line) ? summary.longest_gap_start_line : null,
      longestGapEndLine: Number.isFinite(summary.longest_gap_end_line) ? summary.longest_gap_end_line : null,
      longestGapLastLine: summary.longest_gap_last_line || '',
      longestGapFirstLine: summary.longest_gap_first_line || '',
      gapsOver300: Number.isFinite(summary.gaps_over_300) ? summary.gaps_over_300 : 0,
      gapsOver900: Number.isFinite(summary.gaps_over_900) ? summary.gaps_over_900 : 0,
      gapsOver1800: Number.isFinite(summary.gaps_over_1800) ? summary.gaps_over_1800 : 0,
      maintenanceOverlap: summary.longest_gap_maintenance_overlap || 'unknown',
      longestUnexplainedGapSeconds: Number.isFinite(summary.longest_unexplained_gap_seconds) ? summary.longest_unexplained_gap_seconds : 0,
      longestUnexplainedGapStartedAt: summary.longest_unexplained_gap_started_at || '',
      longestUnexplainedGapEndedAt: summary.longest_unexplained_gap_ended_at || '',
      longestUnexplainedGapStartLine: Number.isFinite(summary.longest_unexplained_gap_start_line) ? summary.longest_unexplained_gap_start_line : null,
      longestUnexplainedGapEndLine: Number.isFinite(summary.longest_unexplained_gap_end_line) ? summary.longest_unexplained_gap_end_line : null,
      longestUnexplainedGapLastLine: summary.longest_unexplained_gap_last_line || '',
      longestUnexplainedGapFirstLine: summary.longest_unexplained_gap_first_line || '',
      longestUnexplainedGapOverlap: summary.longest_unexplained_gap_maintenance_overlap || 'unknown',
      confirmedMaintenanceGapsOver300: Number.isFinite(summary.confirmed_maintenance_gaps_over_300) ? summary.confirmed_maintenance_gaps_over_300 : 0,
      unexplainedGapsOver300: Number.isFinite(summary.unexplained_gaps_over_300) ? summary.unexplained_gaps_over_300 : 0,
      notableGaps: Array.isArray(summary.notable_gaps) ? summary.notable_gaps : []
    }
  }

  function getQuietPeriodOutcome (run, summary) {
    if (run && run.is_incomplete) return 'incomplete'
    const finishedAt = run && run.finished_at ? Date.parse(run.finished_at) : NaN
    const longestGapEndedAt = summary && summary.longestGapEndedAt ? Date.parse(summary.longestGapEndedAt) : NaN
    if (Number.isFinite(finishedAt) && Number.isFinite(longestGapEndedAt) && finishedAt === longestGapEndedAt) {
      return 'completed'
    }
    return 'resumed'
  }

  function getQuietPeriodSortValue (run) {
    return getQuietPeriodSummary(run).longestUnexplainedGapSeconds
  }

  function renderQuietPeriodCell (run) {
    const summary = getQuietPeriodSummary(run)
    if (summary.longestGapSeconds <= 0) {
      return '<span class="text-muted">No gaps</span>'
    }
    const parts = []
    if (summary.longestUnexplainedGapSeconds > 0) {
      parts.push(`Unexplained ${formatSeconds(summary.longestUnexplainedGapSeconds)}`)
    } else {
      parts.push('No unexplained gaps')
    }
    if (summary.longestGapSeconds > 0 && summary.longestGapSeconds !== summary.longestUnexplainedGapSeconds && summary.maintenanceOverlap === 'confirmed') {
      parts.push(`Maint ${formatSeconds(summary.longestGapSeconds)}`)
    }
    if (summary.unexplainedGapsOver300 > 0) {
      parts.push(`${summary.unexplainedGapsOver300} unexplained`)
    }
    const detailParts = []
    if (summary.longestUnexplainedGapStartedAt && summary.longestUnexplainedGapEndedAt) {
      detailParts.push(`Longest unexplained: ${summary.longestUnexplainedGapStartedAt} -> ${summary.longestUnexplainedGapEndedAt}`)
    }
    if (summary.longestGapStartedAt && summary.longestGapEndedAt) {
      detailParts.push(`Longest overall: ${summary.longestGapStartedAt} -> ${summary.longestGapEndedAt}`)
    }
    if (summary.gapsOver1800 > 0) {
      detailParts.push(`>30m: ${summary.gapsOver1800}`)
    }
    if (summary.confirmedMaintenanceGapsOver300 > 0) {
      detailParts.push(`Maintenance gaps: ${summary.confirmedMaintenanceGapsOver300}`)
    }
    const title = detailParts.join(' | ')
    return `
      <div class="logscan-action-stack">
        <span title="${escapeHtml(title)}">${escapeHtml(parts.join(' • '))}</span>
        <button type="button" class="btn nav-button btn-sm logscan-action-btn logscan-quiet-period-details"
          data-run-key="${escapeHtml(String(run && run.run_key ? run.run_key : ''))}">Open</button>
      </div>
    `
  }

  function getCountsTotal (run) {
    return getCount(run, 'warning_count') + getCount(run, 'error_count') + getCount(run, 'trace_count')
  }

  function getDisplayedItemsTotal (run) {
    if (getRunToolName(run) === 'imagemaid') {
      const cache = getCount(run, 'cache_line_count')
      const debug = getCount(run, 'debug_count')
      const info = getCount(run, 'info_count')
      const warnings = getCount(run, 'warning_count')
      const errors = getCount(run, 'error_count')
      const critical = getCount(run, 'critical_count')
      const traces = getCount(run, 'trace_count')
      return cache + debug + info + warnings + errors + critical + traces
    }
    return getRunLibraryTotals(run).total
  }

  function renderInfoDot (helpText) {
    return `<span class="logscan-info-dot" tabindex="0" title="${escapeHtml(helpText)}" data-help="${escapeHtml(helpText)}" aria-label="${escapeHtml(helpText)}">i</span>`
  }

  function renderRunCardCell (label, helpText, valueHtml, attrs = '') {
    return `
      <td data-label="${escapeHtml(label)}" ${attrs}>
        <span class="logscan-card-label">${escapeHtml(label)} ${renderInfoDot(helpText)}</span>
        <span class="logscan-card-value">${valueHtml}</span>
      </td>
    `
  }

  function renderCountChip (shortName, label, value, variant) {
    const displayValue = Number.isFinite(value) ? value : 0
    const title = `${shortName} = ${label}: ${displayValue}`
    return `
      <span class="logscan-count-chip logscan-count-chip--${variant}" title="${escapeHtml(title)}">
        <span>${escapeHtml(shortName)}</span><strong>${escapeHtml(String(displayValue))}</strong>
      </span>
    `
  }

  function normalizeConfigName (value) {
    const cleaned = String(value || '').trim()
    return cleaned || 'default'
  }

  function getCount (run, key) {
    const value = run && typeof run[key] === 'number' ? run[key] : 0
    return Number.isFinite(value) ? value : 0
  }

  function renderRunCountChips (run) {
    if (getRunToolName(run) === 'imagemaid') {
      const cache = getCount(run, 'cache_line_count')
      const debug = getCount(run, 'debug_count')
      const info = getCount(run, 'info_count')
      const warnings = getCount(run, 'warning_count')
      const errors = getCount(run, 'error_count')
      const critical = getCount(run, 'critical_count')
      const traces = getCount(run, 'trace_count')
      const total = cache + debug + info + warnings + errors + critical + traces
      return [
        renderCountChip('C', 'Cache lines', cache, 'cache'),
        renderCountChip('D', 'Debug lines', debug, 'debug'),
        renderCountChip('I', 'Info lines', info, 'info'),
        renderCountChip('W', 'Warnings', warnings, 'warning'),
        renderCountChip('E', 'Errors', errors, 'error'),
        renderCountChip('Cr', 'Critical lines', critical, 'critical'),
        renderCountChip('T', 'Tracebacks', traces, 'trace'),
        renderCountChip('Items', 'Total counted lines', total, 'total')
      ].join('')
    }

    const cache = getCount(run, 'cache_line_count')
    const debug = getCount(run, 'debug_count')
    const info = getCount(run, 'info_count')
    const warnings = getCount(run, 'warning_count')
    const errors = getCount(run, 'error_count')
    const critical = getCount(run, 'critical_count')
    const traces = getCount(run, 'trace_count')
    const libraryTotals = getRunLibraryTotals(run)
    return [
      renderCountChip('C', 'Cache lines', cache, 'cache'),
      renderCountChip('D', 'Debug lines', debug, 'debug'),
      renderCountChip('I', 'Info lines', info, 'info'),
      renderCountChip('W', 'Warnings', warnings, 'warning'),
      renderCountChip('E', 'Errors', errors, 'error'),
      renderCountChip('Cr', 'Critical lines', critical, 'critical'),
      renderCountChip('T', 'Tracebacks', traces, 'trace'),
      renderCountChip('M', 'Movies', libraryTotals.movies, 'movie'),
      renderCountChip('S', 'Shows', libraryTotals.shows, 'show'),
      renderCountChip('Ep', 'Episodes', libraryTotals.episodes, 'episode'),
      renderCountChip('Items', 'Library items total (movies + episodes, or show count when episode totals are unavailable)', libraryTotals.total, 'total')
    ].join('')
  }

  function getIssueCount (run, key, fallbackKey) {
    const counts = run && run.analysis_counts && typeof run.analysis_counts === 'object'
      ? run.analysis_counts
      : {}
    let value = counts && typeof counts[key] === 'number' ? counts[key] : 0
    if ((!Number.isFinite(value) || value === 0) && fallbackKey) {
      const fallback = counts && typeof counts[fallbackKey] === 'number' ? counts[fallbackKey] : 0
      value = Number.isFinite(fallback) ? fallback : value
    }
    return Number.isFinite(value) ? value : 0
  }

  function getPreferenceConfigName () {
    return ($configFilter.val() || 'all').trim() || 'all'
  }

  function mergePreferences (prefs) {
    const merged = {
      panels: { ...ANALYTICS_RECOMMENDED_PREFS.panels },
      issues: { ...ANALYTICS_RECOMMENDED_PREFS.issues }
    }
    if (!prefs || typeof prefs !== 'object') return merged
    const panels = prefs.panels
    if (panels && typeof panels === 'object') {
      PANEL_PREFS.forEach(item => {
        if (Object.prototype.hasOwnProperty.call(panels, item.key)) {
          merged.panels[item.key] = Boolean(panels[item.key])
        }
      })
      if (!Object.prototype.hasOwnProperty.call(panels, 'issue_trends')) {
        let legacyValue = null
        if (Object.prototype.hasOwnProperty.call(panels, 'analyze_issues')) {
          legacyValue = Boolean(panels.analyze_issues)
        }
        if (Object.prototype.hasOwnProperty.call(panels, 'analytics_breakdown')) {
          const breakdownValue = Boolean(panels.analytics_breakdown)
          legacyValue = legacyValue === null ? breakdownValue : legacyValue || breakdownValue
        }
        if (legacyValue !== null) {
          merged.panels.issue_trends = legacyValue
        }
      }
    }
    const issues = prefs.issues && typeof prefs.issues === 'object'
      ? prefs.issues
      : (prefs.breakdown && typeof prefs.breakdown === 'object' ? prefs.breakdown : null)
    if (issues) {
      ISSUE_PREFS.forEach(item => {
        if (Object.prototype.hasOwnProperty.call(issues, item.key)) {
          merged.issues[item.key] = Boolean(issues[item.key])
        }
      })
    }
    return merged
  }

  function applyPanelVisibility () {
    $('[data-panel-key]').each(function () {
      const key = $(this).data('panelKey') || $(this).attr('data-panel-key')
      const enabled = analyticsPrefs && analyticsPrefs.panels
        ? analyticsPrefs.panels[key] !== false
        : true
      $(this).toggleClass('d-none', !enabled)
    })
  }

  function syncPreferencesModal () {
    if (!$preferencesInputs.length) return
    $preferencesInputs.each(function () {
      const group = $(this).data('prefGroup') || $(this).attr('data-pref-group')
      const key = $(this).data('prefKey') || $(this).attr('data-pref-key')
      const value = analyticsPrefs && analyticsPrefs[group] && typeof analyticsPrefs[group][key] === 'boolean'
        ? analyticsPrefs[group][key]
        : true
      $(this).prop('checked', value)
    })
    if ($preferencesStatus.length) {
      const configName = getPreferenceConfigName()
      $preferencesStatus.text(`Saved per config: ${configName}`)
    }
  }

  function collectPreferencesFromModal () {
    const prefs = { panels: {}, issues: {} }
    $preferencesInputs.each(function () {
      const group = $(this).data('prefGroup') || $(this).attr('data-pref-group')
      const key = $(this).data('prefKey') || $(this).attr('data-pref-key')
      if (!group || !key) return
      if (!prefs[group]) prefs[group] = {}
      prefs[group][key] = $(this).is(':checked')
    })
    return prefs
  }

  function loadPreferences () {
    const configName = getPreferenceConfigName()
    return fetch(`/logscan/trends/preferences?config_name=${encodeURIComponent(configName)}`)
      .then(res => res.json())
      .then(data => {
        analyticsPrefs = mergePreferences(data && data.preferences)
        applyPanelVisibility()
        syncPreferencesModal()
      })
      .catch(() => {
        analyticsPrefs = mergePreferences(null)
        applyPanelVisibility()
        syncPreferencesModal()
      })
  }

  function savePreferences (prefs) {
    const configName = getPreferenceConfigName()
    return fetch('/logscan/trends/preferences', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config_name: configName, preferences: prefs })
    })
      .then(res => res.json().then(data => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error('Save failed')
        analyticsPrefs = mergePreferences(data && data.preferences)
        applyPanelVisibility()
        syncPreferencesModal()
        return true
      })
  }

  const CONFIG_COLORS = [
    '#f9c74f',
    '#4cc9f0',
    '#90be6d',
    '#f94144',
    '#577590',
    '#f9844a',
    '#43aa8b',
    '#f3722c'
  ]

  const ISSUE_COLORS = [
    '#f9c74f',
    '#f9844a',
    '#f3722c',
    '#f94144',
    '#90be6d',
    '#43aa8b',
    '#4cc9f0',
    '#577590',
    '#4d908e',
    '#277da1',
    '#f8961e',
    '#90a955'
  ]

  const ISSUE_GROUPS = [
    {
      id: 'people',
      label: 'People posters',
      items: [
        { key: 'people_posters', label: 'Missing people posters' }
      ]
    },
    {
      id: 'service',
      label: 'Service/connectivity',
      items: [
        { key: 'anidb_auth', label: 'AniDB auth errors' },
        { key: 'flixpatrol_errors', label: 'FlixPatrol errors' },
        { key: 'flixpatrol_paywall', label: 'FlixPatrol paywall' },
        { key: 'lsio_errors', label: 'LSIO errors' },
        { key: 'mal_connection_errors', label: 'MAL connection errors' },
        { key: 'mdblist_api_limit_errors', label: 'MDBList API limit' },
        { key: 'mdblist_attr_errors', label: 'MDBList attribute errors' },
        { key: 'mdblist_errors', label: 'MDBList errors' },
        { key: 'omdb_api_limit_errors', label: 'OMDb API limit' },
        { key: 'omdb_errors', label: 'OMDb errors' },
        { key: 'tautulli_apikey_errors', label: 'Tautulli API key errors' },
        { key: 'tautulli_url_errors', label: 'Tautulli URL errors' },
        { key: 'tmdb_api_errors', label: 'TMDb API errors' },
        { key: 'tmdb_fail_errors', label: 'TMDb connection failures' },
        { key: 'trakt_connection_errors', label: 'Trakt connection errors' }
      ]
    },
    {
      id: 'config',
      label: 'Config/setup',
      items: [
        { key: 'config_bad_version', label: 'Bad version found' },
        { key: 'config_api_blank', label: 'Blank API keys' },
        { key: 'config_cache_false', label: 'Cache false warnings' },
        { key: 'config_delete_unmanaged', label: 'Delete unmanaged warnings' },
        { key: 'config_mass_update', label: 'Mass update warnings' },
        { key: 'config_missing_path', label: 'Missing paths' },
        { key: 'config_other_award', label: 'Other awards errors' },
        { key: 'config_to_be_configured', label: '"To be configured" builders' }
      ]
    },
    {
      id: 'plex',
      label: 'Plex issues',
      items: [
        { key: 'plex_library_errors', label: 'Plex library errors' },
        { key: 'plex_regex_errors', label: 'Plex regex errors' },
        { key: 'plex_rounding_errors', label: 'Plex rounding errors' },
        { key: 'plex_url_errors', label: 'Plex URL errors' }
      ]
    },
    {
      id: 'metadata',
      label: 'Metadata/overlay/playlist',
      items: [
        { key: 'metadata_attribute_errors', label: 'Metadata attribute errors' },
        { key: 'metadata_load_errors', label: 'Metadata load errors' },
        { key: 'overlay_apply_errors', label: 'Overlay apply errors' },
        { key: 'overlay_font_missing', label: 'Overlay font missing' },
        { key: 'overlay_image_missing', label: 'Overlay image missing' },
        { key: 'overlay_level_errors', label: 'Overlay level errors' },
        { key: 'overlay_load_errors', label: 'Overlay load errors' },
        { key: 'overlays_bloat', label: 'Overlays bloat warnings' },
        { key: 'playlist_errors', label: 'Playlist errors' },
        { key: 'playlist_load_errors', label: 'Playlist load errors' }
      ]
    },
    {
      id: 'convert',
      label: 'Convert/image',
      items: [
        { key: 'convert_issues', label: 'Convert errors' },
        { key: 'image_corrupt', label: 'Corrupt images' },
        { key: 'image_size', label: 'Image size warnings' }
      ]
    },
    {
      id: 'runtime',
      label: 'Runtime/behavior',
      items: [
        { key: 'runtime_checkfiles', label: 'checkFiles flagged' },
        { key: 'runtime_run_order', label: 'Run order errors' },
        { key: 'runtime_timeout', label: 'Timeout errors' }
      ]
    },
    {
      id: 'update',
      label: 'Update/version',
      items: [
        { key: 'update_git', label: 'Kometa git errors' },
        { key: 'update_kometa', label: 'New Kometa version' },
        { key: 'update_plexapi', label: 'New PlexAPI version' }
      ]
    },
    {
      id: 'platform',
      label: 'Platform/system',
      items: [
        { key: 'platform_db_cache', label: 'DB cache recommendation' },
        { key: 'platform_kometa_time', label: 'Kometa time recommendation' },
        { key: 'platform_memory', label: 'Memory recommendation' },
        { key: 'platform_wsl', label: 'WSL detected' }
      ]
    },
    {
      id: 'misc',
      label: 'Misc',
      items: [
        { key: 'anidb_69', label: 'AniDB 69 errors' },
        { key: 'misc_internal_server', label: 'Internal server errors' },
        { key: 'misc_pmm_legacy', label: 'Legacy PMM errors' },
        { key: 'misc_no_items', label: 'No items found' }
      ]
    }
  ]

  const ISSUE_PREFS = []
  ISSUE_GROUPS.forEach(group => {
    group.items.forEach(item => {
      ISSUE_PREFS.push({ ...item, group: group.id })
    })
  })
  ISSUE_PREFS.forEach((item, index) => {
    item.color = ISSUE_COLORS[index % ISSUE_COLORS.length]
  })

  const ISSUE_DEFAULT_KEYS = new Set([
    'people_posters',
    'anidb_auth',
    'tmdb_api_errors',
    'tmdb_fail_errors',
    'trakt_connection_errors',
    'omdb_errors',
    'omdb_api_limit_errors',
    'mdblist_errors',
    'mdblist_api_limit_errors',
    'mdblist_attr_errors',
    'mal_connection_errors',
    'tautulli_url_errors',
    'tautulli_apikey_errors',
    'lsio_errors',
    'plex_library_errors',
    'plex_url_errors',
    'plex_regex_errors',
    'plex_rounding_errors',
    'metadata_load_errors',
    'metadata_attribute_errors',
    'overlay_load_errors',
    'overlay_apply_errors',
    'overlay_level_errors',
    'overlay_font_missing',
    'overlay_image_missing',
    'playlist_load_errors',
    'playlist_errors',
    'config_api_blank',
    'config_bad_version',
    'config_missing_path',
    'config_other_award',
    'image_corrupt',
    'image_size',
    'misc_internal_server',
    'runtime_timeout'
  ])

  const PANEL_PREFS = [
    { key: 'summary', label: 'Summary + ingest health' },
    { key: 'daily_runs', label: 'Daily runs' },
    { key: 'imagemaid_summary', label: 'ImageMaid summary' },
    { key: 'imagemaid_recovered_trend', label: 'ImageMaid recovered space by day' },
    { key: 'imagemaid_files_trend', label: 'ImageMaid files removed by day' },
    { key: 'imagemaid_mode_mix', label: 'ImageMaid runs by mode' },
    { key: 'runtime_distribution', label: 'Runtime distribution' },
    { key: 'counts_mix', label: 'Log levels + cache' },
    { key: 'issue_trends', label: 'Issue trends' },
    { key: 'library_inventory', label: 'Library inventory' }
  ]

  const LOG_LEVEL_SERIES = [
    { key: 'cache_line_count', short: 'C', label: 'Cache', css: 'logscan-stack-cache' },
    { key: 'debug_count', short: 'D', label: 'Debug', css: 'logscan-stack-debug' },
    { key: 'info_count', short: 'I', label: 'Info', css: 'logscan-stack-info' },
    { key: 'warning_count', short: 'W', label: 'Warnings', css: 'logscan-stack-warning' },
    { key: 'error_count', short: 'E', label: 'Errors', css: 'logscan-stack-error' },
    { key: 'critical_count', short: 'Cr', label: 'Critical', css: 'logscan-stack-critical' },
    { key: 'trace_count', short: 'T', label: 'Tracebacks', css: 'logscan-stack-trace' }
  ]
  const COUNTS_SERIES_STORAGE_KEY = 'qs.logscan.counts.series.v1'

  const ANALYTICS_RECOMMENDED_PREFS = {
    panels: PANEL_PREFS.reduce((acc, item) => ({ ...acc, [item.key]: true }), {}),
    issues: ISSUE_PREFS.reduce((acc, item) => ({ ...acc, [item.key]: ISSUE_DEFAULT_KEYS.has(item.key) }), {})
  }

  function getDefaultCountsSeriesSelection () {
    const defaults = {}
    LOG_LEVEL_SERIES.forEach(series => {
      defaults[series.key] = !['debug_count', 'info_count'].includes(series.key)
    })
    return defaults
  }

  function hasSelectedCountsSeries (selection) {
    return LOG_LEVEL_SERIES.some(series => selection && selection[series.key])
  }

  function loadCountsSeriesSelection () {
    const defaults = getDefaultCountsSeriesSelection()
    try {
      const raw = window.localStorage ? window.localStorage.getItem(COUNTS_SERIES_STORAGE_KEY) : null
      if (!raw) return defaults
      const parsed = JSON.parse(raw)
      if (!parsed || typeof parsed !== 'object') return defaults
      const merged = { ...defaults }
      LOG_LEVEL_SERIES.forEach(series => {
        if (Object.prototype.hasOwnProperty.call(parsed, series.key)) {
          merged[series.key] = Boolean(parsed[series.key])
        }
      })
      return hasSelectedCountsSeries(merged) ? merged : defaults
    } catch {
      return defaults
    }
  }

  function saveCountsSeriesSelection (selection) {
    try {
      if (!window.localStorage) return
      window.localStorage.setItem(COUNTS_SERIES_STORAGE_KEY, JSON.stringify(selection))
    } catch {
      // ignore storage errors
    }
  }

  const countsSeriesSelection = loadCountsSeriesSelection()

  function getSelectedCountSeries () {
    return LOG_LEVEL_SERIES.filter(series => countsSeriesSelection && countsSeriesSelection[series.key])
  }

  function renderCountsSeriesSelector () {
    if (!$countsSeries.length) return
    const html = LOG_LEVEL_SERIES.map(series => {
      const active = Boolean(countsSeriesSelection && countsSeriesSelection[series.key])
      return `
        <button type="button" class="logscan-series-toggle ${active ? 'active' : ''}" data-series-key="${escapeHtml(series.key)}" title="Toggle ${escapeHtml(series.label)}">
          <span class="logscan-legend-swatch ${escapeHtml(series.css)}"></span>
          <span>${escapeHtml(series.label)}</span>
        </button>
      `
    }).join('')
    $countsSeries.html(`<div class="logscan-series-filter">${html}</div>`)
  }

  function buildConfigColorMap (configs) {
    const map = {}
    configs.forEach((config, index) => {
      map[config] = CONFIG_COLORS[index % CONFIG_COLORS.length]
    })
    return map
  }

  function buildDailyBuckets (runs) {
    const buckets = {}
    runs.forEach(run => {
      const key = getRunDateKey(run)
      if (!key) return
      const config = normalizeConfigName(run.config_name)
      const cacheLines = (typeof run.cache_line_count === 'number' && Number.isFinite(run.cache_line_count))
        ? run.cache_line_count
        : 0
      if (!buckets[key]) {
        buckets[key] = { total: 0, configs: {}, cache_total: 0, cache_runs: 0 }
      }
      buckets[key].total += 1
      buckets[key].configs[config] = (buckets[key].configs[config] || 0) + 1
      buckets[key].cache_total += cacheLines
      buckets[key].cache_runs += 1
    })
    return buckets
  }

  function getImagemaidRuns (runs) {
    return Array.isArray(runs)
      ? runs.filter(run => getRunToolName(run) === 'imagemaid')
      : []
  }

  function buildImagemaidDailyBuckets (runs) {
    const buckets = {}
    getImagemaidRuns(runs).forEach(run => {
      const key = getRunDateKey(run)
      if (!key) return
      const counts = run && run.analysis_counts && typeof run.analysis_counts === 'object'
        ? run.analysis_counts
        : {}
      if (!buckets[key]) {
        buckets[key] = {
          runs: 0,
          recoveredBytes: 0,
          removedFiles: 0,
          modes: {}
        }
      }
      buckets[key].runs += 1
      buckets[key].recoveredBytes += Number.isFinite(counts.imagemaid_total_recovered_bytes) ? counts.imagemaid_total_recovered_bytes : 0
      buckets[key].removedFiles += Number.isFinite(counts.imagemaid_total_removed_files) ? counts.imagemaid_total_removed_files : 0
      const mode = getImagemaidMode(run)
      buckets[key].modes[mode] = (buckets[key].modes[mode] || 0) + 1
    })
    return buckets
  }

  function computeRollingAverage (values, windowSize) {
    const window = Math.max(1, windowSize || 1)
    const averages = []
    for (let i = 0; i < values.length; i += 1) {
      const start = Math.max(0, i - window + 1)
      const slice = values.slice(start, i + 1)
      const total = slice.reduce((sum, value) => sum + value, 0)
      averages.push(slice.length ? total / slice.length : 0)
    }
    return averages
  }

  function collectLibraryNames (runs) {
    const names = new Set()
    runs.forEach(run => {
      const counts = run && run.library_counts && typeof run.library_counts === 'object'
        ? run.library_counts
        : null
      if (!counts) return
      Object.keys(counts).forEach(name => {
        if (name) names.add(name)
      })
    })
    return Array.from(names).sort()
  }

  function buildLibrarySnapshots (runs) {
    const snapshots = {}
    runs.forEach(run => {
      const key = getRunDateKey(run)
      if (!key) return
      const counts = run && run.library_counts && typeof run.library_counts === 'object'
        ? run.library_counts
        : null
      if (!counts || !Object.keys(counts).length) return
      const ts = getSortTimestamp(run) || 0
      if (!snapshots[key] || ts > snapshots[key].ts) {
        snapshots[key] = { ts, libraries: counts }
      }
    })
    return snapshots
  }

  function getLibraryMediaTotals (entry) {
    if (!entry || typeof entry !== 'object') {
      return {
        movies: 0,
        episodes: 0,
        shows: 0,
        total: 0
      }
    }
    const items = Number.isFinite(entry.items) ? entry.items : 0
    const episodes = Number.isFinite(entry.episodes) ? entry.episodes : 0
    const type = entry.type || ''
    const isShow = type === 'show' || episodes > 0
    const movies = isShow ? 0 : items
    const shows = isShow ? items : 0
    let total = movies + episodes
    if (isShow && total === 0) {
      total = shows
    }
    return { movies, episodes, shows, total }
  }

  function getRunLibraryTotals (run) {
    const counts = run && run.library_counts && typeof run.library_counts === 'object'
      ? run.library_counts
      : null
    const totals = { movies: 0, episodes: 0, shows: 0, total: 0 }
    if (!counts) return totals
    Object.values(counts).forEach(entry => {
      const entryTotals = getLibraryMediaTotals(entry)
      totals.movies += entryTotals.movies
      totals.episodes += entryTotals.episodes
      totals.shows += entryTotals.shows
      totals.total += entryTotals.total
    })
    return totals
  }

  function getLatestLibrarySnapshot (runs) {
    let latest = null
    let latestTs = null
    runs.forEach(run => {
      const counts = run && run.library_counts && typeof run.library_counts === 'object'
        ? run.library_counts
        : null
      if (!counts || !Object.keys(counts).length) return
      const ts = getSortTimestamp(run) || 0
      if (latest === null || ts > latestTs) {
        latest = run
        latestTs = ts
      }
    })
    if (!latest) return null
    return { run: latest, libraries: latest.library_counts || {} }
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
      lines.push(`Sum: ${formatSeconds(totalSeconds)}`)
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
    let latest = runs[0]
    let latestTs = getSortTimestamp(latest) || 0
    runs.forEach(run => {
      const ts = getSortTimestamp(run)
      if (typeof ts === 'number' && ts > latestTs) {
        latest = run
        latestTs = ts
      }
    })
    const runtimeValues = runs
      .map(run => getEffectiveRunTimeSeconds(run))
      .filter(val => typeof val === 'number' && Number.isFinite(val) && val > 0)
    const avgRuntime = runtimeValues.length
      ? runtimeValues.reduce((sum, val) => sum + val, 0) / runtimeValues.length
      : null
    const configs = new Set(runs.map(run => normalizeConfigName(run.config_name)))
    const cacheBuckets = buildDailyBuckets(runs)
    const cacheDays = Object.keys(cacheBuckets).filter(day => cacheBuckets[day].cache_runs > 0)
    const cacheTotal = cacheDays.reduce((sum, day) => sum + (cacheBuckets[day].cache_total || 0), 0)
    const avgCachePerDay = cacheDays.length ? (cacheTotal / cacheDays.length) : null
    const formatAvgCache = (value) => {
      if (!Number.isFinite(value)) return 'n/a'
      const rounded = Math.round(value * 10) / 10
      return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
    }
    const lines = [
      `Runs stored: ${runs.length}`,
      `Latest run: ${getDisplayFinished(latest)}`,
      `Average runtime: ${avgRuntime ? formatSeconds(avgRuntime) : 'n/a'}`,
      `Configs tracked: ${configs.size}`,
      {
        text: `Avg cache lines/day: ${formatAvgCache(avgCachePerDay)}`,
        title: 'Average number of log lines containing "from Cache" per day across the filtered runs.'
      }
    ]
    const selectedConfig = $configFilter.val()
    if (selectedConfig) {
      lines.push(`Filtered config: ${selectedConfig}`)
    }
    const selectedLibrary = $libraryFilter.length ? $libraryFilter.val() : ''
    const latestSnapshot = getLatestLibrarySnapshot(runs)
    if (latestSnapshot && latestSnapshot.libraries && Object.keys(latestSnapshot.libraries).length) {
      const libraryEntries = Object.values(latestSnapshot.libraries)
      const libraryCount = Object.keys(latestSnapshot.libraries).length
      const totals = libraryEntries.reduce((acc, entry) => {
        const entryTotals = getLibraryMediaTotals(entry)
        acc.movies += entryTotals.movies
        acc.episodes += entryTotals.episodes
        acc.shows += entryTotals.shows
        acc.total += entryTotals.total
        return acc
      }, {
        movies: 0,
        episodes: 0,
        shows: 0,
        total: 0
      })
      lines.push(`Libraries: ${libraryCount}`)
      lines.push(`Total items: ${totals.total}`)
      if (totals.movies) {
        lines.push(`Total movies: ${totals.movies}`)
      }
      if (totals.episodes) {
        lines.push(`Total episodes: ${totals.episodes}`)
      }
      if (totals.shows) {
        lines.push(`Total shows: ${totals.shows}`)
      }
      if (selectedLibrary && latestSnapshot.libraries[selectedLibrary]) {
        const entry = latestSnapshot.libraries[selectedLibrary]
        const entryTotals = getLibraryMediaTotals(entry)
        lines.push(`Total items (${selectedLibrary}): ${entryTotals.total}`)
        if (entryTotals.movies) {
          lines.push(`Movies (${selectedLibrary}): ${entryTotals.movies}`)
        }
        if (entryTotals.episodes) {
          lines.push(`Episodes (${selectedLibrary}): ${entryTotals.episodes}`)
        }
        if (entryTotals.shows) {
          lines.push(`Shows (${selectedLibrary}): ${entryTotals.shows}`)
        }
      }
    }
    $summary.html(lines.map(line => {
      if (typeof line === 'string') {
        return `<div>${escapeHtml(line)}</div>`
      }
      const text = line && typeof line.text === 'string' ? line.text : ''
      const title = line && typeof line.title === 'string' ? line.title : ''
      const titleAttr = title ? ` title="${escapeHtml(title)}"` : ''
      return `<div${titleAttr}>${escapeHtml(text)}</div>`
    }).join(''))
  }

  function renderImagemaidSummary (runs) {
    if (!$imagemaidSummary.length) return
    const imagemaidRuns = getImagemaidRuns(runs)
    if (!imagemaidRuns.length) {
      $imagemaidSummary.text('No ImageMaid runs in the current filters.')
      return
    }
    const totals = imagemaidRuns.reduce((acc, run) => {
      const counts = run && run.analysis_counts && typeof run.analysis_counts === 'object'
        ? run.analysis_counts
        : {}
      acc.recoveredBytes += Number.isFinite(counts.imagemaid_total_recovered_bytes) ? counts.imagemaid_total_recovered_bytes : 0
      acc.removedFiles += Number.isFinite(counts.imagemaid_total_removed_files) ? counts.imagemaid_total_removed_files : 0
      const mode = getImagemaidMode(run)
      acc.modes[mode] = (acc.modes[mode] || 0) + 1
      return acc
    }, { recoveredBytes: 0, removedFiles: 0, modes: {} })
    const modeEntries = Object.entries(totals.modes).sort((a, b) => b[1] - a[1])
    const topMode = modeEntries.length ? `${modeEntries[0][0]} (${modeEntries[0][1]})` : 'n/a'
    const avgRecovered = imagemaidRuns.length ? totals.recoveredBytes / imagemaidRuns.length : 0
    const cards = [
      { label: 'Runs', value: imagemaidRuns.length },
      { label: 'Recovered', value: formatBytes(totals.recoveredBytes) },
      { label: 'Files Removed', value: formatCompactNumber(totals.removedFiles) },
      { label: 'Top Mode', value: topMode }
    ]
    const notes = [
      `Average recovered per run: ${formatBytes(avgRecovered)}`,
      `Modes tracked: ${modeEntries.length || 0}`
    ]
    $imagemaidSummary.html(`
      <div class="logscan-kpi-grid">
        ${cards.map(card => `
          <div class="logscan-kpi">
            <div class="logscan-kpi-label">${escapeHtml(card.label)}</div>
            <div class="logscan-kpi-value">${escapeHtml(String(card.value))}</div>
          </div>
        `).join('')}
      </div>
      <div class="small text-muted mt-2">${notes.map(note => `<div>${escapeHtml(note)}</div>`).join('')}</div>
    `)
  }

  function renderImagemaidTrendChart ($el, runs, metricKey, options = {}) {
    if (!$el.length) return
    const imagemaidRuns = getImagemaidRuns(runs)
    if (!imagemaidRuns.length) {
      $el.text('No ImageMaid runs in the current filters.')
      return
    }
    const buckets = buildImagemaidDailyBuckets(imagemaidRuns)
    const days = Object.keys(buckets).sort().slice(-14)
    if (!days.length) {
      $el.text('No ImageMaid trend data yet.')
      return
    }
    const values = days.map(day => {
      const bucket = buckets[day] || {}
      return Number.isFinite(bucket[metricKey]) ? bucket[metricKey] : 0
    })
    if (!values.some(value => value > 0)) {
      $el.text(options.emptyText || 'No ImageMaid activity recorded for this metric yet.')
      return
    }
    const maxValue = Math.max(...values, 1)
    const rollingAvg = computeRollingAverage(values, 7)
    const barWidth = 18
    const gap = 10
    const chartHeight = 120
    const paddingTop = 6
    const paddingBottom = 14
    const chartAreaHeight = chartHeight - paddingTop - paddingBottom
    const chartWidth = Math.max(1, (barWidth + gap) * days.length - gap)
    const bars = []
    const linePoints = []
    days.forEach((day, index) => {
      const x = index * (barWidth + gap)
      const value = values[index]
      const height = chartAreaHeight * (value / maxValue)
      const y = paddingTop + chartAreaHeight - height
      bars.push(`<rect x="${x}" y="${y.toFixed(2)}" width="${barWidth}" height="${height.toFixed(2)}" fill="${options.barColor || '#4cc9f0'}"></rect>`)
      const avgValue = rollingAvg[index] || 0
      const lineX = x + (barWidth / 2)
      const lineY = paddingTop + (chartAreaHeight - (chartAreaHeight * (avgValue / maxValue)))
      linePoints.push(`${lineX.toFixed(2)},${lineY.toFixed(2)}`)
    })
    const labels = days.map((day, index) => {
      const displayValue = typeof options.formatValue === 'function'
        ? options.formatValue(values[index])
        : String(values[index])
      return `
        <div class="logscan-daily-label" title="${escapeHtml(day)}">
          <span class="logscan-daily-label-date">${escapeHtml(day.slice(5))}</span>
          <span class="logscan-daily-label-count">${escapeHtml(displayValue)}</span>
        </div>
      `
    })
    const labelStyle = `style="grid-template-columns: repeat(${days.length}, minmax(0, 1fr));"`
    const legend = `
      <div class="logscan-daily-legend">
        <span class="logscan-legend-item"><span class="logscan-legend-swatch" style="background:${escapeHtml(options.barColor || '#4cc9f0')}"></span>${escapeHtml(options.seriesLabel || 'Daily total')}</span>
        <span class="logscan-legend-item"><span class="logscan-legend-line"></span>7-day avg</span>
      </div>
    `
    $el.html(`
      <div class="logscan-library-meta">${escapeHtml(options.metaLabel || 'Last 14 days of ImageMaid activity')}</div>
      <div class="logscan-daily-chart">
        <svg class="logscan-daily-svg" viewBox="0 0 ${chartWidth} ${chartHeight}" preserveAspectRatio="none">
          ${bars.join('')}
          <polyline class="logscan-daily-line" points="${linePoints.join(' ')}"></polyline>
        </svg>
        <div class="logscan-daily-labels" ${labelStyle}>
          ${labels.join('')}
        </div>
      </div>
      ${legend}
    `)
  }

  function renderImagemaidModeMix (runs) {
    if (!$imagemaidModes.length) return
    const imagemaidRuns = getImagemaidRuns(runs)
    if (!imagemaidRuns.length) {
      $imagemaidModes.text('No ImageMaid runs in the current filters.')
      return
    }
    const counts = {}
    imagemaidRuns.forEach(run => {
      const mode = getImagemaidMode(run)
      counts[mode] = (counts[mode] || 0) + 1
    })
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1])
    if (!entries.length) {
      $imagemaidModes.text('No ImageMaid mode data yet.')
      return
    }
    const maxCount = Math.max(...entries.map(([, count]) => count), 1)
    const rows = entries.map(([mode, count]) => {
      const pct = maxCount ? Math.round((count / maxCount) * 100) : 0
      return `
        <div class="logscan-histogram-row">
          <div class="logscan-histogram-label">${escapeHtml(mode)}</div>
          <div class="logscan-histogram-bar-wrap">
            <div class="logscan-histogram-bar" style="width: ${pct}%"></div>
          </div>
          <div class="logscan-histogram-count">${count}</div>
        </div>
      `
    })
    $imagemaidModes.html(rows.join(''))
  }

  function renderArchiveStorageSummary (storage) {
    if (!$tablePolicy.length) return
    const kometaKeepLimit = storage && Number.isFinite(storage.kometa_keep_limit)
      ? storage.kometa_keep_limit
      : (parseInt(window.QS_KOMETA_LOG_KEEP || '0', 10) || 0)
    const imagemaidKeepLimit = storage && Number.isFinite(storage.imagemaid_keep_limit)
      ? storage.imagemaid_keep_limit
      : (parseInt(window.QS_IMAGEMAID_LOG_KEEP || '0', 10) || 0)
    const kometaRetentionLabel = storage && storage.kometa_retention_label
      ? storage.kometa_retention_label
      : (kometaKeepLimit > 0 ? `Keep last ${kometaKeepLimit} archived logs` : 'Keep all archived logs')
    const imagemaidRetentionLabel = storage && storage.imagemaid_retention_label
      ? storage.imagemaid_retention_label
      : (imagemaidKeepLimit > 0 ? `Keep last ${imagemaidKeepLimit} archived logs` : 'Keep all archived logs')
    const archivedFiles = storage && Number.isFinite(storage.archived_files) ? storage.archived_files : 0
    const archivedBytes = storage && Number.isFinite(storage.archived_bytes) ? storage.archived_bytes : 0
    const extraArchivedFiles = storage && Number.isFinite(storage.extra_archived_files) ? storage.extra_archived_files : 0
    const extraArchivedBytes = storage && Number.isFinite(storage.extra_archived_bytes) ? storage.extra_archived_bytes : 0
    const fileLabel = archivedFiles === 1 ? 'file' : 'files'
    const lines = [
      `Archived log retention: Kometa: ${kometaRetentionLabel} | ImageMaid: ${imagemaidRetentionLabel}`,
      `Tracked archived log storage: ${formatBytes(archivedBytes)} across ${archivedFiles} ${fileLabel}`
    ]
    if (extraArchivedFiles > 0) {
      const extraLabel = extraArchivedFiles === 1 ? 'file' : 'files'
      lines.push(`Additional archived logs on disk not linked to Analytics: ${formatBytes(extraArchivedBytes)} across ${extraArchivedFiles} ${extraLabel}`)
    }
    $tablePolicy.html(lines.map(line => `<div>${escapeHtml(line)}</div>`).join(''))
  }

  function renderDaily (runs) {
    const buckets = buildDailyBuckets(runs)
    const days = Object.keys(buckets).sort().slice(-14)
    if (!days.length) {
      $daily.text('No daily totals yet.')
      if ($dailyRuntime.length) {
        $dailyRuntime.text('No runtime averages yet.')
      }
      return
    }
    const totals = days.map(day => buckets[day].total || 0)
    const maxTotal = Math.max(...totals, 1)
    const selectedConfig = $configFilter.val()
    const configTotals = {}
    days.forEach(day => {
      const configs = buckets[day].configs || {}
      Object.entries(configs).forEach(([config, count]) => {
        configTotals[config] = (configTotals[config] || 0) + count
      })
    })
    let configs = Object.keys(configTotals)
    if (selectedConfig) {
      configs = [selectedConfig]
    } else {
      configs.sort((a, b) => (configTotals[b] || 0) - (configTotals[a] || 0))
    }
    if (!configs.length) {
      configs = ['default']
    }
    const colorMap = buildConfigColorMap(configs)
    const rollingAvg = computeRollingAverage(totals, 7)
    const barWidth = 18
    const gap = 10
    const chartHeight = 120
    const paddingTop = 6
    const paddingBottom = 14
    const chartAreaHeight = chartHeight - paddingTop - paddingBottom
    const chartWidth = Math.max(1, (barWidth + gap) * days.length - gap)
    const bars = []
    const linePoints = []
    days.forEach((day, index) => {
      const bucket = buckets[day]
      const x = index * (barWidth + gap)
      let yCursor = paddingTop + chartAreaHeight
      configs.forEach(config => {
        const count = bucket.configs[config] || 0
        if (!count) return
        const height = chartAreaHeight * (count / maxTotal)
        const y = yCursor - height
        bars.push(
          `<rect x="${x}" y="${y.toFixed(2)}" width="${barWidth}" height="${height.toFixed(2)}" fill="${colorMap[config]}"></rect>`
        )
        yCursor = y
      })
      const avgValue = rollingAvg[index] || 0
      const lineX = x + (barWidth / 2)
      const lineY = paddingTop + (chartAreaHeight - (chartAreaHeight * (avgValue / maxTotal)))
      linePoints.push(`${lineX.toFixed(2)},${lineY.toFixed(2)}`)
    })
    const dayLabels = days.map(day => {
      const total = buckets[day].total || 0
      const runLabel = total === 1 ? 'run' : 'runs'
      return (
      `<div class="logscan-daily-label" title="${escapeHtml(day)}">
        <span class="logscan-daily-label-date">${escapeHtml(day.slice(5))}</span>
        <span class="logscan-daily-label-count">${total} ${runLabel}</span>
      </div>`
      )
    })
    const labelStyle = `style="grid-template-columns: repeat(${days.length}, minmax(0, 1fr));"`
    const legendItems = configs.map(config => (
      `<span class="logscan-legend-item"><span class="logscan-legend-swatch" style="background:${colorMap[config]}"></span>${escapeHtml(config)}</span>`
    ))
    legendItems.push('<span class="logscan-legend-item"><span class="logscan-legend-line"></span>7-day avg</span>')
    const html = `
        <div class="logscan-daily-chart">
          <svg class="logscan-daily-svg" viewBox="0 0 ${chartWidth} ${chartHeight}" preserveAspectRatio="none">
            ${bars.join('')}
            <polyline class="logscan-daily-line" points="${linePoints.join(' ')}"></polyline>
          </svg>
        <div class="logscan-daily-labels" ${labelStyle}>
          ${dayLabels.join('')}
        </div>
        </div>
        <div class="logscan-daily-legend">${legendItems.join('')}</div>
      `
    $daily.html(html)
    renderDailyRuntimeAverages(runs, days)
  }

  function renderDailyRuntimeAverages (runs, days) {
    if (!$dailyRuntime.length) return
    const buckets = {}
    runs.forEach(run => {
      const key = getRunDateKey(run)
      if (!key) return
      const runtime = getEffectiveRunTimeSeconds(run)
      if (typeof runtime !== 'number' || !Number.isFinite(runtime) || runtime <= 0) return
      if (!buckets[key]) {
        buckets[key] = { total: 0, count: 0 }
      }
      buckets[key].total += runtime
      buckets[key].count += 1
    })
    const rowsData = days.map(day => {
      const bucket = buckets[day]
      const avg = bucket && bucket.count ? bucket.total / bucket.count : 0
      return { day, avg }
    })
    if (!rowsData.some(row => row.avg > 0)) {
      $dailyRuntime.text('No runtime averages yet.')
      return
    }
    const maxAvg = Math.max(...rowsData.map(row => row.avg), 1)
    const rows = rowsData.map(row => {
      const barWidth = maxAvg ? Math.round((row.avg / maxAvg) * 100) : 0
      return `
        <div class="logscan-stack-row">
          <div class="logscan-stack-label">${escapeHtml(row.day)}</div>
          <div class="logscan-stack-bar-wrap">
            <div class="logscan-stack-bar" style="width: ${barWidth}%">
              <span class="logscan-stack-segment logscan-stack-runtime" style="width: 100%"></span>
            </div>
          </div>
          <div class="logscan-stack-count">${formatSeconds(row.avg)}</div>
        </div>
      `
    })
    $dailyRuntime.html(rows.join(''))
  }

  function getTablePageSize () {
    const parsed = parseInt($tablePageSize.val() || '10', 10)
    if ([10, 25, 100].includes(parsed)) return parsed
    return 10
  }

  function isRunSelectable (run) {
    return Boolean(run && run.run_key && run.log_can_delete)
  }

  function getSelectableRuns (runs) {
    return Array.isArray(runs) ? runs.filter(isRunSelectable) : []
  }

  function getSelectableRunsByCompletion (runs, isIncomplete) {
    return getSelectableRuns(runs).filter(run => Boolean(run && run.is_incomplete) === Boolean(isIncomplete))
  }

  function isRunCompressible (run) {
    return Boolean(run && run.run_key && run.log_can_compress)
  }

  function getCompressibleRuns (runs) {
    return Array.isArray(runs) ? runs.filter(isRunCompressible) : []
  }

  function getSelectedCompressibleRuns () {
    if (!selectedRunKeys.size) return []
    return getCompressibleRuns(allTableRuns).filter(run => selectedRunKeys.has(run.run_key))
  }

  function pruneSelectedRunKeys () {
    const validKeys = new Set(getSelectableRuns(allTableRuns).map(run => run.run_key))
    Array.from(selectedRunKeys).forEach(runKey => {
      if (!validKeys.has(runKey)) {
        selectedRunKeys.delete(runKey)
      }
    })
  }

  function updateSelectionSummary () {
    if (!$tableSelectionSummary.length) return
    const selectedCount = selectedRunKeys.size
    const visibleSelectable = getSelectableRuns(currentTableRuns).length
    const visibleCompleteSelectable = getSelectableRunsByCompletion(currentTableRuns, false).length
    const visibleIncompleteSelectable = getSelectableRunsByCompletion(currentTableRuns, true).length
    const selectedCompressibleCount = getSelectedCompressibleRuns().length
    if (!selectedCount) {
      $tableSelectionSummary.text('No logs selected.')
    } else {
      $tableSelectionSummary.text(`${selectedCount} selected. ${selectedCompressibleCount} compressible. ${visibleSelectable} deletable in current view.`)
    }
    if ($tableCompressSelected.length) {
      $tableCompressSelected.prop('disabled', selectedCompressibleCount === 0)
    }
    if ($tableDeleteSelected.length) {
      $tableDeleteSelected.prop('disabled', selectedCount === 0)
    }
    if ($tableClearSelection.length) {
      $tableClearSelection.prop('disabled', selectedCount === 0)
    }
    if ($tableSelectAll.length) {
      $tableSelectAll.prop('disabled', visibleSelectable === 0)
    }
    if ($tableSelectComplete.length) {
      $tableSelectComplete.prop('disabled', visibleCompleteSelectable === 0)
      $tableSelectComplete.toggleClass('is-active', tableStatusFilter === 'complete')
    }
    if ($tableSelectIncomplete.length) {
      $tableSelectIncomplete.prop('disabled', visibleIncompleteSelectable === 0)
      $tableSelectIncomplete.toggleClass('is-active', tableStatusFilter === 'incomplete')
    }
  }

  function filterTableRunsByStatus (runs) {
    if (!Array.isArray(runs) || !runs.length) return []
    if (tableStatusFilter === 'complete') {
      return runs.filter(run => !run.is_incomplete)
    }
    if (tableStatusFilter === 'incomplete') {
      return runs.filter(run => Boolean(run.is_incomplete))
    }
    return runs
  }

  function updateTableSummary (total, pageSize, pageCount) {
    const totalComplete = Number.isFinite(allRunsTotal) ? allRunsTotal : allRuns.length
    const totalIncomplete = Number.isFinite(allIncompleteRunsTotal) ? allIncompleteRunsTotal : allIncompleteRuns.length
    const loaded = allTableRuns.length
    const grandTotal = totalComplete + totalIncomplete
    if ($tableSummary.length) {
      if (!total) {
        $tableSummary.text('No runs match the current filters.')
      } else {
        $tableSummary.text(`Ingested: ${totalComplete}. Incomplete: ${totalIncomplete}. Showing: ${total}. Page size: ${pageSize}.`)
      }
    }
    if ($tableFilterCount.length) {
      let filterText = `Filtered: ${total} of ${loaded} loaded`
      if (grandTotal > loaded) {
        filterText += ` (${grandTotal} total)`
      }
      $tableFilterCount.text(filterText)
    }
    if (!$tablePageInfo.length) return
    if (!total) {
      $tablePageInfo.text('No rows')
      updateSelectionSummary()
      return
    }
    const start = ((tablePage - 1) * pageSize) + 1
    const end = Math.min(total, tablePage * pageSize)
    $tablePageInfo.text(`Showing ${start}-${end} of ${total} loaded entr${total === 1 ? 'y' : 'ies'} (page ${tablePage}/${pageCount})`)
    updateSelectionSummary()
  }

  function renderTable (runs) {
    currentTableRuns = runs
    pruneSelectedRunKeys()
    const pageSize = getTablePageSize()
    const total = runs.length
    const pageCount = Math.max(1, Math.ceil(total / pageSize))
    tablePage = Math.min(Math.max(tablePage, 1), pageCount)
    updateTableSummary(total, pageSize, pageCount)
    $tablePrev.prop('disabled', tablePage <= 1 || total === 0)
    $tableNext.prop('disabled', tablePage >= pageCount || total === 0)
    if (!total) {
      $tableBody.html('<tr><td colspan="18" class="text-muted">No runs match the current filters.</td></tr>')
      return
    }
    sectionDetailsByRunKey.clear()
    const pageStart = (tablePage - 1) * pageSize
    const pageRuns = runs.slice(pageStart, pageStart + pageSize)
    const rows = pageRuns.map((run, index) => {
      const absoluteIndex = pageStart + index
      const command = getRunCommandValue(run) || 'n/a'
      const commandTitle = run.run_command
        ? `Original: ${run.run_command}`
        : (run.command_signature ? `Signature: ${run.command_signature}` : '')
      const countChips = renderRunCountChips(run)
      const configLineCount = (typeof run.config_line_count === 'number' && Number.isFinite(run.config_line_count))
        ? run.config_line_count
        : 'n/a'
      const runtimeParts = getRunTimeParts(run)
      const sectionLines = buildSectionDetails(run.section_runtimes, runtimeParts.effective)
      const sectionSummary = sectionLines.length ? sectionLines[0] : 'n/a'
      const sectionDetails = sectionLines.length > 1 ? sectionLines.slice(1) : []
      const rowKey = (run.run_key && String(run.run_key).trim()) || `row-${absoluteIndex + 1}`
      sectionDetailsByRunKey.set(rowKey, {
        summary: sectionSummary,
        details: sectionDetails
      })
      let sectionCell = `
        <div class="logscan-card-inline">
      `
      if (sectionDetails.length) {
        sectionCell += `
          <button type="button" class="btn nav-button btn-sm logscan-action-btn"
            data-run-key="${escapeHtml(rowKey)}"
            data-section-details="1">
            View
          </button>
        `
      }
      sectionCell += `<span class="logscan-section-summary">${escapeHtml(sectionSummary)}</span>`
      sectionCell += '</div>'
      const isImageMaidRun = getRunToolName(run) === 'imagemaid'
      const progressLabel = getRunToolName(run) === 'imagemaid' ? 'Operation matrix' : 'Progress matrix'
      const progressHelpText = getRunToolName(run) === 'imagemaid'
        ? 'Stored ImageMaid operation matrix for this run, including observed scan/action timings, item counts, and outcomes.'
        : 'Inline final progress snapshot for this run, including preparation, maintenance context, and per-library phase status.'
      let kometaDisplay = run.kometa_version || 'n/a'
      if (run.kometa_version && run.kometa_newest_version && run.kometa_version !== run.kometa_newest_version) {
        kometaDisplay = `${run.kometa_version} -> ${run.kometa_newest_version}`
      }
      const runKey = run.run_key || rowKey
      const isProgressExpanded = expandedProgressRunKeys.has(runKey)
      const isSelectable = isRunSelectable(run)
      const isSelected = isSelectable && selectedRunKeys.has(runKey)
      const statusDisplay = run.is_incomplete ? 'Incomplete' : 'Complete'
      const startModeBadge = renderKometaStartModeBadge(run)
      const startedDisplay = escapeHtml(getDisplayStarted(run))
      const finishedDisplay = escapeHtml(getDisplayFinished(run))
      const sizeBytes = typeof run.log_resolved_size === 'number'
        ? run.log_resolved_size
        : (typeof run.log_size === 'number' ? run.log_size : null)
      const runLabel = `${run.config_name || 'default'} @ ${getDisplayFinished(run)}`
      const logActions = []
      if (run.log_available) {
        logActions.push(`
          <a class="btn nav-button btn-sm logscan-action-btn" href="/logscan/trends/log?run_key=${encodeURIComponent(runKey)}">
            Download
          </a>
        `)
      } else {
        logActions.push('<span class="small text-muted">Unavailable</span>')
      }
      if (run.log_can_compress) {
        logActions.push(`
          <button type="button" class="btn nav-button btn-sm logscan-action-btn logscan-compress-log"
            data-run-key="${escapeHtml(runKey)}"
            data-run-label="${escapeHtml(runLabel)}">
            Compress
          </button>
        `)
      } else if (run.log_is_compressed) {
        logActions.push('<span class="small text-muted">Compressed</span>')
      }
      if (run.log_can_delete) {
        logActions.push(`
          <button type="button" class="btn nav-button nav-button-danger btn-sm logscan-action-btn logscan-delete-log"
            data-run-key="${escapeHtml(runKey)}"
            data-run-label="${escapeHtml(runLabel)}">
            Delete
          </button>
        `)
      } else if (run.log_location === 'live') {
        logActions.push('<span class="small text-muted">Live log</span>')
      }
      if (run.is_incomplete && run.resume_reason) {
        logActions.push(`<span class="small text-warning">${escapeHtml(run.resume_reason)}</span>`)
      }
      const rowClasses = [
        isSelected ? 'logscan-row-selected' : '',
        isProgressExpanded ? 'logscan-row-progress-expanded' : ''
      ].filter(Boolean).join(' ')
      return `
        <tr class="${rowClasses}">
          ${renderRunCardCell('Select', 'Select this archived log for bulk actions.', `
            <span class="logscan-select-wrap">
              <span class="form-check form-switch logscan-select-switch">
                <input type="checkbox" class="form-check-input logscan-select-toggle-input"
                  data-run-key="${escapeHtml(runKey)}"
                  ${isSelected ? 'checked' : ''}
                  ${isSelectable ? '' : 'disabled'}
                  aria-label="Select ${escapeHtml(runLabel)}">
                <label class="form-check-label">${isSelected ? 'Selected' : 'Select'}</label>
              </span>
            </span>
          `, 'class="logscan-select-cell"')}
          ${renderRunCardCell('Status', 'Complete runs are included in charts. Incomplete logs are shown here for investigation and file management.', `<span class="${run.is_incomplete ? 'text-warning' : 'text-success'} fw-semibold">${escapeHtml(statusDisplay)}</span>${startModeBadge}`, 'class="text-nowrap"')}
          ${renderRunCardCell('Started', 'Timestamp parsed from the stored run start marker or run summary.', startedDisplay, 'class="text-nowrap"')}
          ${renderRunCardCell('Finished', 'Timestamp of the run finishing. Incomplete logs are shown here for investigation only and are excluded from charts.', finishedDisplay, 'class="text-nowrap"')}
          ${renderRunCardCell('Runtime', getRuntimeHelpText(run), escapeHtml(formatSeconds(runtimeParts.effective)))}
          ${renderRunCardCell('Config', 'Config name detected for the run.', escapeHtml(run.config_name || 'default'))}
          ${renderRunCardCell('App', 'App that produced this run.', renderRunToolIndicator(run))}
          ${isImageMaidRun ? '' : renderRunCardCell('Config lines', 'Non-comment lines captured from the redacted config output.', escapeHtml(String(configLineCount)))}
          ${renderRunCardCell('Command', 'Sanitized command line captured for the run.', `<span class="logscan-command" title="${escapeHtml(commandTitle)}">${escapeHtml(command)}</span>`)}
          ${renderRunCardCell('Counts', 'Kometa: C cache, D debug, I info, W warnings, E errors, Cr critical, T tracebacks, plus M movies, S shows, Ep episodes, and Items total. ImageMaid: C D I W E Cr T plus Items total.', `<span class="logscan-count-chip-row">${countChips}</span>`)}
          ${renderRunCardCell('Version', 'Detected tool version for the run, plus newest version when different.', escapeHtml(kometaDisplay))}
          ${renderRunCardCell('Maintenance', 'Quickstart maintenance pauses recorded in meta.log for this run.', renderMaintenanceSummaryCell(run))}
          ${renderRunCardCell('Quiet periods', 'Emphasizes the longest unexplained delay between timestamped run log lines, with maintenance-related gaps available in the details view.', renderQuietPeriodCell(run))}
          ${renderRunCardCell(progressLabel, progressHelpText, renderProgressSnapshotCell(run, runKey), 'class="logscan-progress-cell"')}
          ${isImageMaidRun ? '' : renderRunCardCell('Section runtimes', 'Runtime totals parsed per run section when available.', sectionCell)}
          ${renderRunCardCell('Log size', 'Current on-disk size of the resolved log file when available, otherwise the ingested size.', escapeHtml(formatBytes(sizeBytes)))}
          ${renderRunCardCell('Log', 'Download the source log for this run. Archived plain logs can also be compressed, and archived logs can be deleted here.', `<div class="logscan-action-stack">${logActions.join('')}</div>`)}
          ${renderRunCardCell('Report', run.is_incomplete ? 'Open recommendations and diagnostics captured for this incomplete log.' : 'Open the recommendations recorded for the run.', `
            <div class="logscan-action-stack">
              <button type="button" class="btn nav-button btn-sm logscan-action-btn logscan-run-details"
                data-run-key="${escapeHtml(runKey)}">Open</button>
            </div>
          `)}
        </tr>
      `
    })
    $tableBody.html(rows.join(''))
  }

  function renderRuntimeDistribution (runs) {
    if (!$runtime.length) return
    const durations = runs
      .map(run => getEffectiveRunTimeSeconds(run))
      .filter(val => typeof val === 'number' && Number.isFinite(val) && val > 0)
    if (!durations.length) {
      $runtime.text('No runtime data yet.')
      return
    }
    const bins = [
      { label: '<10m', max: 600 },
      { label: '10-30m', max: 1800 },
      { label: '30-60m', max: 3600 },
      { label: '1-2h', max: 7200 },
      { label: '2-4h', max: 14400 },
      { label: '4h+', max: Infinity }
    ]
    const counts = bins.map(() => 0)
    durations.forEach(seconds => {
      const idx = bins.findIndex(bin => seconds <= bin.max)
      if (idx >= 0) counts[idx] += 1
    })
    const maxCount = Math.max(...counts, 1)
    const rows = bins.map((bin, index) => {
      const count = counts[index]
      const pct = maxCount ? Math.round((count / maxCount) * 100) : 0
      return `
        <div class="logscan-histogram-row">
          <div class="logscan-histogram-label">${escapeHtml(bin.label)}</div>
          <div class="logscan-histogram-bar-wrap">
            <div class="logscan-histogram-bar" style="width: ${pct}%"></div>
          </div>
          <div class="logscan-histogram-count">${count}</div>
        </div>
      `
    })
    $runtime.html(rows.join(''))
  }

  function renderCountsMix (runs) {
    if (!$counts.length) return
    const selectedSeries = getSelectedCountSeries()
    if (!selectedSeries.length) {
      $counts.text('Select at least one series to display.')
      return
    }
    const buckets = {}
    runs.forEach(run => {
      const key = getRunDateKey(run)
      if (!key) return
      if (!buckets[key]) {
        buckets[key] = { count: 0 }
        selectedSeries.forEach(series => {
          buckets[key][series.key] = 0
        })
      }
      selectedSeries.forEach(series => {
        if (series.key === 'cache_line_count') {
          const cacheValue = (typeof run.cache_line_count === 'number' && Number.isFinite(run.cache_line_count))
            ? run.cache_line_count
            : 0
          buckets[key][series.key] += cacheValue
        } else {
          buckets[key][series.key] += getCount(run, series.key)
        }
      })
      buckets[key].count += 1
    })
    const days = Object.keys(buckets).sort().slice(-14)
    if (!days.length) {
      $counts.text('No log-level averages yet.')
      return
    }
    const totals = days.map(day => {
      const bucket = buckets[day]
      if (!bucket || !bucket.count) return 0
      return selectedSeries.reduce((sum, series) => {
        return sum + (bucket[series.key] / bucket.count)
      }, 0)
    })
    const maxTotal = Math.max(...totals, 1)
    const rows = days.map((day, index) => {
      const data = buckets[day]
      const total = totals[index]
      const averages = {}
      selectedSeries.forEach(series => {
        averages[series.key] = data.count ? data[series.key] / data.count : 0
      })
      const barWidth = maxTotal ? Math.round((total / maxTotal) * 100) : 0
      let usedPct = 0
      const segments = selectedSeries.map((series, seriesIndex) => {
        let pct = 0
        if (total) {
          if (seriesIndex === selectedSeries.length - 1) {
            pct = Math.max(0, 100 - usedPct)
          } else {
            pct = Math.round((averages[series.key] / total) * 100)
            usedPct += pct
          }
        }
        return `<span class="logscan-stack-segment ${series.css}" style="width: ${pct}%"></span>`
      }).join('')
      const countText = selectedSeries
        .map(series => `${series.short}:${formatAverage(averages[series.key])}`)
        .join(' ')
      return `
        <div class="logscan-stack-row">
          <div class="logscan-stack-label">${escapeHtml(day)}</div>
          <div class="logscan-stack-bar-wrap">
            <div class="logscan-stack-bar" style="width: ${barWidth}%">
              ${segments}
            </div>
          </div>
          <div class="logscan-stack-count logscan-stack-count-wide">${escapeHtml(countText)}</div>
        </div>
      `
    })
    const legend = `
      <div class="logscan-stack-legend">
        ${selectedSeries.map(series => `<span><span class="logscan-legend-swatch ${series.css}"></span>${escapeHtml(series.label)}</span>`).join('')}
      </div>
    `
    $counts.html(`${rows.join('')}${legend}`)
  }

  function renderIssueTrends (runs) {
    if (!$issues.length) return
    if (!runs.length) {
      $issues.text('No issue data yet.')
      return
    }
    const selectedItems = ISSUE_PREFS.filter(item => {
      if (!analyticsPrefs || !analyticsPrefs.issues) return true
      return analyticsPrefs.issues[item.key] !== false
    })
    if (!selectedItems.length) {
      $issues.text('No issue toggles selected.')
      return
    }
    const sorted = runs.slice().sort((a, b) => {
      const aTs = getSortTimestamp(a) || 0
      const bTs = getSortTimestamp(b) || 0
      return aTs - bTs
    })
    const totals = sorted.map(run => selectedItems.reduce((sum, item) => {
      return sum + getIssueCount(run, item.key, item.fallbackKey)
    }, 0))
    const maxTotal = Math.max(...totals, 1)
    const rows = sorted.map((run, index) => {
      const total = totals[index]
      const barWidth = maxTotal ? Math.round((total / maxTotal) * 100) : 0
      const label = formatShortTimestamp(run.finished_at) ||
        extractDateKey(run.finished_at) ||
        extractDateKey(run.created_at) ||
        'n/a'
      const segments = []
      const details = []
      selectedItems.forEach(item => {
        const count = getIssueCount(run, item.key, item.fallbackKey)
        if (count > 0) {
          details.push(`${item.label}: ${count}`)
        }
        const pct = total ? Math.round((count / total) * 100) : 0
        if (pct > 0) {
          segments.push(
            `<span class="logscan-stack-segment" style="width: ${pct}%; background: ${item.color};"></span>`
          )
        }
      })
      const title = details.length ? details.join(' | ') : 'No issues detected'
      return `
        <div class="logscan-stack-row" title="${escapeHtml(title)}">
          <div class="logscan-stack-label">${escapeHtml(label)}</div>
          <div class="logscan-stack-bar-wrap">
            <div class="logscan-stack-bar" style="width: ${barWidth}%">
              ${segments.join('')}
            </div>
          </div>
          <div class="logscan-stack-count">Total: ${total}</div>
        </div>
      `
    })
    const legend = `
      <div class="logscan-stack-legend">
        ${selectedItems.map(item => (
          `<span class="logscan-legend-item"><span class="logscan-legend-swatch" style="background:${item.color}"></span>${escapeHtml(item.label)}</span>`
        )).join('')}
      </div>
    `
    $issues.html(`${rows.join('')}${legend}`)
  }

  function updateLibraryFilter (runs) {
    if (!$libraryFilter.length) return false
    const names = collectLibraryNames(runs)
    const selected = $libraryFilter.val() || ''
    const options = ['<option value="">All libraries</option>']
    names.forEach(name => {
      options.push(`<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)
    })
    $libraryFilter.html(options.join(''))
    const nextValue = selected && names.includes(selected) ? selected : ''
    $libraryFilter.val(nextValue)
    return nextValue !== selected
  }

  function renderLibraryInventory (runs) {
    if (!$libraries.length) return
    const runsWithCounts = runs.filter(run => {
      const counts = run && run.library_counts && typeof run.library_counts === 'object'
        ? run.library_counts
        : null
      return counts && Object.keys(counts).length
    })
    if (!runsWithCounts.length) {
      $libraries.text('No library totals yet.')
      return
    }
    const selectedLibrary = $libraryFilter.val() || ''
    const snapshots = buildLibrarySnapshots(runsWithCounts)
    const days = Object.keys(snapshots).sort().slice(-14)
    if (!days.length) {
      $libraries.text('No library totals yet.')
      return
    }
    const rowsData = days.map(day => {
      const snapshot = snapshots[day]
      const libraries = snapshot ? snapshot.libraries || {} : {}
      let movies = 0
      let episodes = 0
      let shows = 0
      let total = 0
      if (selectedLibrary) {
        const entryTotals = getLibraryMediaTotals(libraries[selectedLibrary] || {})
        movies = entryTotals.movies
        episodes = entryTotals.episodes
        shows = entryTotals.shows
        total = entryTotals.total
      } else {
        Object.values(libraries).forEach(entry => {
          const entryTotals = getLibraryMediaTotals(entry)
          movies += entryTotals.movies
          episodes += entryTotals.episodes
          shows += entryTotals.shows
          total += entryTotals.total
        })
      }
      return {
        day,
        movies,
        episodes,
        shows,
        total
      }
    })
    if (selectedLibrary && rowsData.every(row => row.total === 0 && row.shows === 0)) {
      $libraries.text('No totals recorded for the selected library yet.')
      return
    }
    const totals = rowsData.map(row => row.total || 0)
    const maxTotal = Math.max(...totals, 1)
    const rollingAvg = computeRollingAverage(totals, 7)
    const barWidth = 18
    const gap = 10
    const chartHeight = 120
    const paddingTop = 6
    const paddingBottom = 14
    const chartAreaHeight = chartHeight - paddingTop - paddingBottom
    const chartWidth = Math.max(1, (barWidth + gap) * rowsData.length - gap)
    const bars = []
    const linePoints = []
    rowsData.forEach((row, index) => {
      const x = index * (barWidth + gap)
      let yCursor = paddingTop + chartAreaHeight
      const segments = [
        { count: row.movies, color: '#43aa8b' },
        { count: row.episodes, color: '#4cc9f0' }
      ]
      segments.forEach(segment => {
        if (!segment.count) return
        const height = chartAreaHeight * (segment.count / maxTotal)
        const y = yCursor - height
        bars.push(
          `<rect x="${x}" y="${y.toFixed(2)}" width="${barWidth}" height="${height.toFixed(2)}" fill="${segment.color}"></rect>`
        )
        yCursor = y
      })
      const avgValue = rollingAvg[index] || 0
      const lineX = x + (barWidth / 2)
      const lineY = paddingTop + (chartAreaHeight - (chartAreaHeight * (avgValue / maxTotal)))
      linePoints.push(`${lineX.toFixed(2)},${lineY.toFixed(2)}`)
    })
    const dayLabels = rowsData.map(row => (
      `<div class="logscan-daily-label" title="${escapeHtml(row.day)}">
        <span class="logscan-daily-label-date">${escapeHtml(row.day.slice(5))}</span>
        <span class="logscan-daily-label-count">T:${row.total}</span>
        <span class="logscan-daily-label-sub">M:${row.movies} S:${row.shows} E:${row.episodes}</span>
      </div>`
    ))
    const labelStyle = `style="grid-template-columns: repeat(${rowsData.length}, minmax(0, 1fr));"`
    const metaLabel = selectedLibrary ? `Tracking: ${escapeHtml(selectedLibrary)}` : 'Tracking: All libraries'
    const legend = `
      <div class="logscan-daily-legend">
        <span class="logscan-legend-item"><span class="logscan-legend-swatch" style="background:#43aa8b"></span>Movies</span>
        <span class="logscan-legend-item"><span class="logscan-legend-swatch" style="background:#4cc9f0"></span>Episodes</span>
        <span class="logscan-legend-item"><span class="logscan-legend-line"></span>7-day avg</span>
      </div>
    `
    const html = `
      <div class="logscan-library-meta">${metaLabel}</div>
      <div class="logscan-daily-chart">
        <svg class="logscan-daily-svg" viewBox="0 0 ${chartWidth} ${chartHeight}" preserveAspectRatio="none">
          ${bars.join('')}
          <polyline class="logscan-daily-line" points="${linePoints.join(' ')}"></polyline>
        </svg>
        <div class="logscan-daily-labels" ${labelStyle}>
          ${dayLabels.join('')}
        </div>
      </div>
      ${legend}
    `
    $libraries.html(html)
  }

  function renderIngestHealth (state) {
    if (!$ingest.length) return
    const invalidArchivedCount = Number.isFinite(state && state.invalid_archived_count) ? state.invalid_archived_count : 0
    const invalidArchivedSample = Array.isArray(state && state.invalid_archived_sample) ? state.invalid_archived_sample : []

    if ($clearInvalidArchived.length) {
      if (invalidArchivedCount > 0) {
        $clearInvalidArchived
          .removeClass('d-none')
          .prop('disabled', false)
          .text(invalidArchivedCount > 1 ? `Clear invalid archived logs (${invalidArchivedCount})` : 'Clear invalid archived log')
        pendingInvalidLogCleanup = {
          count: invalidArchivedCount,
          sample: invalidArchivedSample
        }
      } else {
        $clearInvalidArchived
          .addClass('d-none')
          .prop('disabled', true)
          .text('Clear invalid archived logs')
        pendingInvalidLogCleanup = null
      }
    }

    if (!state) {
      $ingest.text('No ingest history yet.')
      return
    }

    if (typeof state.scanned === 'number') {
      const skipped = (state.skipped_incomplete || 0) + (state.skipped_invalid || 0)
      const items = [
        { label: 'Scanned', value: state.scanned || 0 },
        { label: 'Ingested', value: state.ingested || 0 },
        { label: 'Duplicates', value: state.duplicates || 0 },
        { label: 'Skipped', value: skipped }
      ]
      const tiles = items.map(item => `
        <div class="logscan-kpi">
          <div class="logscan-kpi-label">${escapeHtml(item.label)}</div>
          <div class="logscan-kpi-value">${item.value}</div>
        </div>
      `)
      const notes = []
      if (skipped > 0) {
        notes.push('Some logs were skipped. Reingest after runs complete to catch missing data.')
      }
      if (state.errors) {
        notes.push(`${state.errors} error(s) occurred while ingesting.`)
      }
      if (Array.isArray(state.sample_incomplete) && state.sample_incomplete.length) {
        notes.push(`Incomplete samples: ${state.sample_incomplete.join(', ')}`)
      }
      if (Array.isArray(state.sample_errors) && state.sample_errors.length) {
        notes.push(`Sample errors: ${state.sample_errors.join('; ')}`)
      }
      if (!notes.length) notes.push('Ingest complete.')
      const notesHtml = notes.map(note => `<div>${escapeHtml(note)}</div>`).join('')
      $ingest.html(`<div class="logscan-kpi-grid">${tiles.join('')}</div><div class="small text-muted mt-2">${notesHtml}</div>`)
      return
    }

    if (typeof state.total !== 'number') {
      $ingest.text('No ingest history yet.')
      return
    }
    const items = [
      { label: 'Logs found', value: state.total || 0 },
      { label: 'Tracked', value: state.tracked || 0 },
      { label: 'Missing', value: state.missing || 0 },
      { label: 'Incomplete', value: state.incomplete || 0 }
    ]
    const tiles = items.map(item => `
      <div class="logscan-kpi">
        <div class="logscan-kpi-label">${escapeHtml(item.label)}</div>
        <div class="logscan-kpi-value">${item.value}</div>
      </div>
    `)
    const lines = []
    if (state.log_dir_missing) {
      lines.push('Log folder not found: config/kometa/config/logs.')
    } else if (state.total === 0) {
      lines.push('No log files found yet.')
    } else if (state.needs_reingest) {
      lines.push('Missing or incomplete logs detected. Use Reingest logs to catch up.')
    } else {
      lines.push('All available logs are ingested.')
    }
    if (state.pending_active) {
      lines.push('Active run detected; meta.log will ingest after completion.')
    }
    if (state.last_updated) {
      const updated = formatTimestamp(state.last_updated) || state.last_updated
      lines.push(`Ingest cache updated: ${updated}`)
    }
    if (Array.isArray(state.missing_sample) && state.missing_sample.length) {
      lines.push(`Missing samples: ${state.missing_sample.join(', ')}`)
    }
    if (Array.isArray(state.incomplete_sample) && state.incomplete_sample.length) {
      lines.push(`Incomplete samples: ${state.incomplete_sample.join(', ')}`)
    }
    if (invalidArchivedCount > 0) {
      lines.push(`Invalid archived logs: ${invalidArchivedCount}. Use Clear invalid archived logs to remove them.`)
    }
    if (invalidArchivedSample.length) {
      lines.push(`Invalid archived samples: ${invalidArchivedSample.join(', ')}`)
    }
    const linesHtml = lines.map(line => `<div>${escapeHtml(line)}</div>`).join('')
    $ingest.html(`<div class="logscan-kpi-grid">${tiles.join('')}</div><div class="small text-muted mt-2">${linesHtml}</div>`)
  }

  function getSortValue (run, key) {
    switch (key) {
      case 'status':
        return run && run.is_incomplete ? 1 : 0
      case 'started_at':
        if (run && run.started_at) {
          const parsed = new Date(run.started_at)
          if (!Number.isNaN(parsed.getTime())) return parsed.getTime()
        }
        return null
      case 'finished_at':
        return getSortTimestamp(run)
      case 'run_time_seconds':
        return getEffectiveRunTimeSeconds(run)
      case 'config_name':
        return normalizeConfigName(run.config_name)
      case 'tool_name':
        return getRunToolName(run)
      case 'command_signature':
        return getRunCommandValue(run)
      case 'counts':
        return getCountsTotal(run)
      case 'warning_count':
      case 'debug_count':
      case 'info_count':
      case 'error_count':
      case 'critical_count':
      case 'trace_count':
        return getCount(run, key)
      case 'config_line_count':
        return typeof run.config_line_count === 'number' ? run.config_line_count : 0
      case 'cache_line_count':
        return typeof run.cache_line_count === 'number' ? run.cache_line_count : 0
      case 'library_movies':
        return getRunLibraryTotals(run).movies
      case 'library_shows':
        return getRunLibraryTotals(run).shows
      case 'library_episodes':
        return getRunLibraryTotals(run).episodes
      case 'library_total':
        return getRunLibraryTotals(run).total
      case 'items_total':
        return getDisplayedItemsTotal(run)
      case 'kometa_version':
        return run.kometa_version || ''
      case 'maintenance':
        return getMaintenanceSortValue(run)
      case 'quiet_periods':
        return getQuietPeriodSortValue(run)
      case 'section_runtimes':
        return getSectionTotal(run.section_runtimes)
      case 'log_resolved_size':
        return typeof run.log_resolved_size === 'number' ? run.log_resolved_size : 0
      case 'recommendations_count':
        return typeof run.recommendations_count === 'number' ? run.recommendations_count : 0
      default:
        return run[key] || ''
    }
  }

  function compareValues (aVal, bVal, dir) {
    const aMissing = aVal === null || aVal === undefined || aVal === ''
    const bMissing = bVal === null || bVal === undefined || bVal === ''
    if (aMissing && bMissing) return 0
    if (aMissing) return 1
    if (bMissing) return -1
    if (typeof aVal === 'number' && typeof bVal === 'number') {
      return dir === 'asc' ? aVal - bVal : bVal - aVal
    }
    const aText = String(aVal)
    const bText = String(bVal)
    return dir === 'asc' ? aText.localeCompare(bText) : bText.localeCompare(aText)
  }

  function sortRuns (runs) {
    if (!runs.length) return runs
    const { key, dir } = sortState
    const direction = dir === 'asc' ? 'asc' : 'desc'
    return runs.slice().sort((a, b) => {
      const aVal = getSortValue(a, key)
      const bVal = getSortValue(b, key)
      const result = compareValues(aVal, bVal, direction)
      if (result !== 0) return result
      const aTs = getSortTimestamp(a) || 0
      const bTs = getSortTimestamp(b) || 0
      return direction === 'asc' ? aTs - bTs : bTs - aTs
    })
  }

  function updateSortIndicators () {
    $('#logscan-trends-table thead .logscan-sort-button').removeClass('is-asc is-desc')
    const selector = `.logscan-sort-button[data-sort="${sortState.key}"]`
    const $button = $(selector)
    if ($button.length) {
      $button.addClass(sortState.dir === 'asc' ? 'is-asc' : 'is-desc')
    }
    $tableSortKey.val(sortState.key)
    $tableSortDir.val(sortState.dir === 'asc' ? 'asc' : 'desc')
  }

  function updateConfigFilter (runs) {
    if (!$configFilter.length) return false
    const selected = $configFilter.val() || ''
    const configs = Array.from(new Set(runs.map(run => normalizeConfigName(run.config_name)))).sort()
    const options = ['<option value="">All configs</option>']
    configs.forEach(cfg => {
      options.push(`<option value="${escapeHtml(cfg)}">${escapeHtml(cfg)}</option>`)
    })
    $configFilter.html(options.join(''))
    const nextValue = selected && configs.includes(selected) ? selected : ''
    $configFilter.val(nextValue)
    return nextValue !== selected
  }

  function updateCommandFilter (runs) {
    if (!$commandFilter.length) return false
    const selected = $commandFilter.val() || ''
    const counts = new Map()
    runs.forEach(run => {
      const command = getRunCommandValue(run)
      if (!command) return
      counts.set(command, (counts.get(command) || 0) + 1)
    })
    const commands = Array.from(counts.entries()).sort((a, b) => {
      if (b[1] !== a[1]) return b[1] - a[1]
      return a[0].localeCompare(b[0])
    })
    const options = ['<option value="">All commands</option>']
    commands.forEach(([command]) => {
      const cleaned = command.replaceAll(/\s+/g, ' ').trim()
      const label = cleaned.length > 90 ? `${cleaned.slice(0, 87)}...` : cleaned
      options.push(
        `<option value="${escapeHtml(command)}" title="${escapeHtml(command)}">${escapeHtml(label)}</option>`
      )
    })
    $commandFilter.html(options.join(''))
    const nextValue = selected && counts.has(selected) ? selected : ''
    $commandFilter.val(nextValue)
    return nextValue !== selected
  }

  function getAvailableDateBounds (runs) {
    const dates = runs.map(run => getRunDateKey(run)).filter(Boolean).sort()
    if (!dates.length) {
      return { minDate: '', maxDate: '' }
    }
    return { minDate: dates[0], maxDate: dates[dates.length - 1] }
  }

  function updateDateRangeInputs (runs, state) {
    if (!$dateStart.length || !$dateEnd.length) return false
    const { minDate, maxDate } = getAvailableDateBounds(runs)
    const isCustom = state.timeRange === 'custom'
    if (!minDate || !maxDate) {
      const hadValue = $dateStart.val() || $dateEnd.val()
      $dateStart.val('')
      $dateEnd.val('')
      $dateStart.prop('disabled', true)
      $dateEnd.prop('disabled', true)
      if ($dateHint.length) $dateHint.text('No dated runs available for the current scope.')
      return Boolean(hadValue)
    }
    $dateStart.prop('disabled', !isCustom)
    $dateEnd.prop('disabled', !isCustom)
    $dateStart.attr('min', minDate)
    $dateStart.attr('max', maxDate)
    $dateEnd.attr('min', minDate)
    $dateEnd.attr('max', maxDate)
    if ($dateHint.length) {
      $dateHint.text(`Available data: ${minDate} to ${maxDate}`)
    }
    if (!isCustom) {
      const hadValue = $dateStart.val() || $dateEnd.val()
      $dateStart.val('')
      $dateEnd.val('')
      return Boolean(hadValue)
    }
    let start = state.start || ''
    let end = state.end || ''
    if (!start || start < minDate || start > maxDate) start = minDate
    if (!end || end > maxDate || end < minDate) end = maxDate
    if (start > end) start = end
    const changed = start !== state.start || end !== state.end
    $dateStart.val(start)
    $dateEnd.val(end)
    return changed
  }

  function clearDateFilters () {
    if (!$dateStart.length || !$dateEnd.length) return
    $dateStart.val('')
    $dateEnd.val('')
  }

  function syncDateRangeVisibility () {
    if (!$customDateRow.length) return
    const isCustom = ($timeRange.val() || 'all') === 'custom'
    $customDateRow.toggleClass('d-none', !isCustom)
  }

  function getRelativeDateRangeBounds (runs, days) {
    const { maxDate } = getAvailableDateBounds(runs)
    if (!maxDate) return { start: '', end: '' }
    const endDate = new Date(`${maxDate}T00:00:00`)
    if (Number.isNaN(endDate.getTime())) return { start: '', end: '' }
    const startDate = new Date(endDate)
    startDate.setDate(startDate.getDate() - Math.max(0, days - 1))
    const start = startDate.toISOString().slice(0, 10)
    return { start, end: maxDate }
  }

  function updateRunCountDisplay (filtered) {
    if (!$runCount.length) return
    const loaded = allTableRuns.length
    const total = (Number.isFinite(allRunsTotal) ? allRunsTotal : allRuns.length) +
      (Number.isFinite(allIncompleteRunsTotal) ? allIncompleteRunsTotal : allIncompleteRuns.length)
    const filteredCount = filtered.length
    let text = `Entries shown: ${filteredCount}`
    if (filteredCount !== loaded) {
      text += ` of ${loaded} loaded`
    }
    if (total > loaded) {
      text += ` (${total} total)`
    }
    $runCount.text(text)
  }

  function getFilterState () {
    return {
      config: $configFilter.val() || '',
      tool: $toolFilter.val() || '',
      timeRange: $timeRange.val() || 'all',
      command: $commandFilter.val() || '',
      library: $libraryFilter.val() || '',
      start: $dateStart.val() || '',
      end: $dateEnd.val() || ''
    }
  }

  function filterRuns (runs, state) {
    let rangeStart = ''
    let rangeEnd = ''
    if (state.timeRange === 'custom') {
      rangeStart = state.start
      rangeEnd = state.end
    } else if (state.timeRange === '7' || state.timeRange === '30' || state.timeRange === '90') {
      const relative = getRelativeDateRangeBounds(runs, parseInt(state.timeRange, 10))
      rangeStart = relative.start
      rangeEnd = relative.end
    }
    return runs.filter(run => {
      if (state.config && normalizeConfigName(run.config_name) !== state.config) return false
      if (state.tool && getRunToolName(run) !== state.tool) return false
      if (state.command && getRunCommandValue(run) !== state.command) return false
      if (rangeStart || rangeEnd) {
        const dateKey = getRunDateKey(run)
        if (!isDateWithinRange(dateKey, rangeStart, rangeEnd)) return false
      }
      return true
    })
  }

  function updateFilterOptions (state) {
    let changed = false
    changed = updateConfigFilter(filterRuns(allTableRuns, { ...state, config: '' })) || changed
    changed = updateToolFilter(filterRuns(allTableRuns, { ...state, tool: '' })) || changed
    changed = updateCommandFilter(filterRuns(allTableRuns, { ...state, command: '' })) || changed
    changed = updateDateRangeInputs(filterRuns(allTableRuns, { ...state, start: '', end: '', timeRange: 'all' }), state) || changed
    changed = updateLibraryFilter(filterRuns(allRuns, { ...state, library: '' })) || changed
    return changed
  }

  function updateToolFilter (runs) {
    if (!$toolFilter.length) return false
    const selected = $toolFilter.val() || ''
    const tools = Array.from(new Set(runs.map(run => getRunToolName(run)))).sort()
    const options = ['<option value="">All apps</option>']
    tools.forEach(tool => {
      const label = tool === 'imagemaid' ? 'ImageMaid' : 'Kometa'
      options.push(`<option value="${escapeHtml(tool)}">${escapeHtml(label)}</option>`)
    })
    $toolFilter.html(options.join(''))
    const nextValue = selected && tools.includes(selected) ? selected : getDefaultToolFilterValue(tools)
    $toolFilter.val(nextValue)
    return nextValue !== selected
  }

  function applyFiltersAndRender () {
    syncDateRangeVisibility()
    let state = getFilterState()
    for (let i = 0; i < 2; i += 1) {
      const changed = updateFilterOptions(state)
      if (!changed) break
      state = getFilterState()
    }
    const filtered = filterRuns(allRuns, state)
    const filteredTableRuns = filterTableRunsByStatus(filterRuns(allTableRuns, state))
    currentFilteredRuns = filtered
    updateRunCountDisplay(filtered)
    renderSummary(filtered)
    renderDaily(filtered)
    renderImagemaidSummary(filtered)
    renderImagemaidTrendChart($imagemaidRecovered, filtered, 'recoveredBytes', {
      barColor: '#43aa8b',
      seriesLabel: 'Recovered space',
      formatValue: value => formatBytes(value),
      metaLabel: 'Daily total recovered space from ImageMaid runs'
    })
    renderImagemaidTrendChart($imagemaidFiles, filtered, 'removedFiles', {
      barColor: '#f9c74f',
      seriesLabel: 'Files removed',
      formatValue: value => formatCompactNumber(value),
      metaLabel: 'Daily total files removed by ImageMaid'
    })
    renderImagemaidModeMix(filtered)
    renderRuntimeDistribution(filtered)
    renderCountsMix(filtered)
    renderIssueTrends(filtered)
    updateLibraryFilter(filtered)
    renderLibraryInventory(filtered)
    renderTable(sortRuns(filteredTableRuns))
    renderIngestHealth(lastIngestState)
    updateSortIndicators()
  }

  function updateStatus (message) {
    if ($status.length) $status.text(message)
  }

  function setReingestButtonLabel (label) {
    if (!$reingest.length) return
    $reingest.text(label || defaultReingestButtonLabel)
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
    lastIngestState = state
    renderIngestHealth(lastIngestState)
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
      pieces.unshift(`Processing: ${formatProcessingFileLabel(state.current_file)}`)
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

  function formatProcessingFileLabel (value) {
    const text = String(value || '').trim()
    if (!text) return ''
    if (text.length <= 96) return text
    const extMatch = text.match(/(\.log(?:\.gz)?)$/i)
    const ext = extMatch ? extMatch[1] : ''
    const suffixLength = ext ? Math.max(24, ext.length + 20) : 24
    return `${text.slice(0, 56)}...${text.slice(-suffixLength)}`
  }

  function setButtonSpinner ($button, text) {
    if (!$button || !$button.length) return
    $button.html(`<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>${escapeHtml(text)}`)
  }

  function setModalAlert ($el, message) {
    if (!$el || !$el.length) return
    if (!message) {
      $el.addClass('d-none').text('')
      return
    }
    $el.removeClass('d-none').text(message)
  }

  function setDeleteModalBusy (busy) {
    $confirmDeleteLog.prop('disabled', busy)
    $cancelDeleteLog.prop('disabled', busy)
    if (deleteLogModalEl) {
      $(deleteLogModalEl).find('.btn-close').prop('disabled', busy)
    }
  }

  function setInvalidLogModalBusy (busy) {
    $confirmInvalidLog.prop('disabled', busy)
    $cancelInvalidLog.prop('disabled', busy)
    if (invalidLogModalEl) {
      $(invalidLogModalEl).find('.btn-close').prop('disabled', busy)
    }
  }

  function setCompressModalBusy (busy) {
    $confirmCompressLog.prop('disabled', busy)
    $cancelCompressLog.prop('disabled', busy)
    if (compressLogModalEl) {
      $(compressLogModalEl).find('.btn-close').prop('disabled', busy)
    }
  }

  function setControlsDisabled (disabled) {
    $reset.prop('disabled', disabled)
    $reingest.prop('disabled', disabled)
    $clearInvalidArchived.prop('disabled', disabled || $clearInvalidArchived.hasClass('d-none'))
    $limit.prop('disabled', disabled)
    $tableSortKey.prop('disabled', disabled)
    $tableSortDir.prop('disabled', disabled)
    $tablePageSize.prop('disabled', disabled)
    $tablePrev.prop('disabled', disabled || tablePage <= 1 || currentTableRuns.length === 0)
    $tableNext.prop('disabled', disabled || tablePage >= Math.max(1, Math.ceil(currentTableRuns.length / getTablePageSize())) || currentTableRuns.length === 0)
    $configFilter.prop('disabled', disabled)
    $toolFilter.prop('disabled', disabled)
    $commandFilter.prop('disabled', disabled)
    $dateStart.prop('disabled', disabled)
    $dateEnd.prop('disabled', disabled)
    $confirmReset.prop('disabled', disabled)
    $confirmReingest.prop('disabled', disabled)
    $confirmInvalidLog.prop('disabled', disabled)
    $confirmMissingDownload.prop('disabled', disabled)
    $tableSelectAll.prop('disabled', disabled || getSelectableRuns(currentTableRuns).length === 0)
    $tableSelectComplete.prop('disabled', disabled || getSelectableRunsByCompletion(currentTableRuns, false).length === 0)
    $tableSelectIncomplete.prop('disabled', disabled || getSelectableRunsByCompletion(currentTableRuns, true).length === 0)
    $tableClearSelection.prop('disabled', disabled || selectedRunKeys.size === 0)
    $tableCompressSelected.prop('disabled', disabled || getSelectedCompressibleRuns().length === 0)
    $tableDeleteSelected.prop('disabled', disabled || selectedRunKeys.size === 0)
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
          lastIngestState = null
          renderIngestHealth(lastIngestState)
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
    lastIngestState = data
    renderIngestHealth(lastIngestState)
    const isStartupMigration = data && data.trigger === 'startup_migration'
    updateStatus(`${isStartupMigration ? 'Startup Analytics migration complete.' : 'Reingest complete.'} ${summary}`)
    fetchRuns({ suppressStatus: true })
    setMissingDownloadVisible(Boolean(data.missing_people_log_ready), data.missing_people_unique)
    setProgressVisible(false)
    setControlsDisabled(false)
    setReingestButtonLabel(defaultReingestButtonLabel)
  }

  function stopReingestPolling () {
    if (reingestPollTimer) {
      clearInterval(reingestPollTimer)
      reingestPollTimer = null
    }
    reingestJobId = null
    setReingestButtonLabel(defaultReingestButtonLabel)
  }

  function fetchReingestStatus (jobId) {
    const query = jobId ? `?job=${encodeURIComponent(jobId)}` : ''
    fetch(`/logscan/trends/reingest/status${query}`)
      .then(res => res.json().then(data => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (!ok || !data) return
        if (typeof window.QS_handleLogscanReingestStatus === 'function') {
          window.QS_handleLogscanReingestStatus(data)
        }
        if (data.status === 'running') {
          const isStartupMigration = data.trigger === 'startup_migration'
          const migrationLevel = Number.isFinite(data.migration_level) ? data.migration_level : null
          updateProgressFromState(data)
          updateStatus(
            isStartupMigration
              ? `Startup Analytics migration is rebuilding trends${migrationLevel ? ` (level ${migrationLevel})` : ''}. Reingest controls are locked until it finishes.`
              : 'Reingesting logs...'
          )
          setReingestButtonLabel(isStartupMigration ? 'Startup migration running...' : 'Reingest running...')
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
          setReingestButtonLabel(defaultReingestButtonLabel)
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
    setReingestButtonLabel('Reingest running...')
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

  function formatRecommendationMessage (message) {
    if (!message) return ''
    return escapeHtml(message).replaceAll('\n', '<br>')
  }

  function buildImagemaidDetailsBlock (run) {
    if (!run || getRunToolName(run) !== 'imagemaid') return ''
    const counts = run.analysis_counts && typeof run.analysis_counts === 'object' ? run.analysis_counts : {}
    const modeMatch = String(run.command_signature || '').match(/--mode\s+([a-z]+)/i)
    const mode = modeMatch ? modeMatch[1].toLowerCase() : 'report'
    const operations = []
    if (counts.imagemaid_database_seen) operations.push('Database')
    if (counts.imagemaid_photo_transcoder_enabled) operations.push('PhotoTranscoder')
    if (counts.imagemaid_empty_trash_enabled) operations.push('Empty Trash')
    if (counts.imagemaid_clean_bundles_enabled) operations.push('Clean Bundles')
    if (counts.imagemaid_optimize_db_enabled) operations.push('Optimize DB')
    const facts = [
      `Mode: ${escapeHtml(mode)}`,
      `Completion: ${escapeHtml(String(run.completion_reason || (run.is_incomplete ? 'unknown_incomplete' : 'completed')).replaceAll('_', ' '))}`,
      `Operations: ${escapeHtml(operations.length ? operations.join(', ') : 'None detected')}`,
      `Database download: ${counts.imagemaid_database_downloaded_new ? 'Downloaded new database' : (counts.imagemaid_database_download_failed ? 'Failed to download database' : 'No download recorded')}`,
      `Restore directory files found: ${escapeHtml(String(counts.imagemaid_restore_found_files || 0))}`,
      `Restore directory files removed: ${escapeHtml(String(counts.imagemaid_restore_removed_files || 0))}`,
      `Restore directory bytes recovered: ${escapeHtml(formatBytes(counts.imagemaid_restore_recovered_bytes || 0))}`,
      `PhotoTranscoder files found: ${escapeHtml(String(counts.imagemaid_photo_found_files || 0))}`,
      `PhotoTranscoder files removed: ${escapeHtml(String(counts.imagemaid_photo_removed_files || 0))}`,
      `PhotoTranscoder bytes recovered: ${escapeHtml(formatBytes(counts.imagemaid_photo_recovered_bytes || 0))}`,
      `Total files removed: ${escapeHtml(String(counts.imagemaid_total_removed_files || 0))}`,
      `Total bytes recovered: ${escapeHtml(formatBytes(counts.imagemaid_total_recovered_bytes || 0))}`
    ]
    const sectionLines = buildSectionDetails(run.section_runtimes, getRunTimeParts(run).effective)
    if (sectionLines.length) {
      facts.push(`Parsed timings: ${escapeHtml(sectionLines.join(' | '))}`)
    }
    return `
      <div class="mb-3">
        <div class="fw-semibold mb-1">ImageMaid Details</div>
        <div class="small text-muted">
          ${facts.map(line => `<div>${line}</div>`).join('')}
        </div>
      </div>
    `
  }

  function buildKometaDetailsBlock (run) {
    if (!run || getRunToolName(run) !== 'kometa') return ''
    const startMode = getKometaStartModeLabel(run) || 'Unknown'
    const facts = [
      `Start mode: ${escapeHtml(startMode)}`,
      `Completion: ${escapeHtml(String(run.completion_reason || (run.is_incomplete ? 'unknown_incomplete' : 'completed')).replaceAll('_', ' '))}`
    ]
    return `
      <div class="mb-3">
        <div class="fw-semibold mb-1">Kometa Details</div>
        <div class="small text-muted">
          ${facts.map(line => `<div>${line}</div>`).join('')}
        </div>
      </div>
    `
  }

  function showRunDetails (runKey) {
    if (!runKey) return
    if ($runDetailsBody.length) {
      $runDetailsBody.html('Loading recommendations...')
    }
    if ($runDetailsTitle.length) {
      $runDetailsTitle.text('Run Recommendations')
    }
    if (runDetailsModalEl) {
      bootstrap.Modal.getOrCreateInstance(runDetailsModalEl).show()
    }
    fetch(`/logscan/trends/recommendations?run_key=${encodeURIComponent(runKey)}`)
      .then(res => res.json().then(data => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          if ($runDetailsBody.length) {
            $runDetailsBody.text(data && data.error ? data.error : 'Unable to load recommendations.')
          }
          return
        }
        const detailsBlock = `${buildKometaDetailsBlock(data && data.run)}${buildImagemaidDetailsBlock(data && data.run)}`
        const recs = Array.isArray(data.recommendations) ? data.recommendations : []
        if (!recs.length) {
          if ($runDetailsBody.length) {
            $runDetailsBody.html(detailsBlock || 'No recommendations recorded for this run.')
          }
          return
        }
        const blocks = recs.map(rec => {
          const title = rec && rec.first_line ? escapeHtml(rec.first_line) : 'Recommendation'
          const message = rec && rec.message ? formatRecommendationMessage(rec.message) : ''
          return `
            <div class="mb-3">
              <div class="fw-semibold mb-1">${title}</div>
              <div class="small text-muted">${message}</div>
            </div>
          `
        })
        if ($runDetailsBody.length) {
          $runDetailsBody.html(`${detailsBlock}${blocks.join('')}`)
        }
      })
      .catch(() => {
        if ($runDetailsBody.length) {
          $runDetailsBody.text('Unable to load recommendations.')
        }
      })
  }

  function maybeStartAutoReingest (ingestHealth) {
    if (autoReingestTriggered) return
    if (!ingestHealth || !ingestHealth.needs_reingest) return
    autoReingestTriggered = true
    updateStatus('Refreshing trends in the background...')
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
          startReingestPolling(data.job_id)
          return
        }
        autoReingestTriggered = false
      })
      .catch(err => {
        console.error(err)
        autoReingestTriggered = false
      })
  }

  function showSectionDetails (runKey) {
    const payload = sectionDetailsByRunKey.get(runKey)
    if (!payload) return
    if ($runDetailsTitle.length) {
      $runDetailsTitle.text('Section Runtimes')
    }
    if ($runDetailsBody.length) {
      const summary = payload.summary || 'n/a'
      const details = Array.isArray(payload.details) ? payload.details : []
      let bodyHtml = `
        <div class="mb-3">
          <div class="fw-semibold mb-1">Summary</div>
          <div class="small text-muted">${escapeHtml(summary)}</div>
        </div>
      `
      if (!details.length) {
        bodyHtml += '<div class="small text-muted">No additional section details for this run.</div>'
      } else {
        bodyHtml += `
          <div class="fw-semibold mb-2">Details</div>
          <div class="small text-muted">
            ${details.map(line => `<div>${escapeHtml(line)}</div>`).join('')}
          </div>
        `
      }
      $runDetailsBody.html(bodyHtml)
    }
    if (runDetailsModalEl) {
      bootstrap.Modal.getOrCreateInstance(runDetailsModalEl).show()
    }
  }

  function showQuietPeriodDetails (runKey) {
    const run = allTableRuns.find(entry => entry && entry.run_key === runKey)
    const summary = getQuietPeriodSummary(run)
    if (!run || summary.longestGapSeconds <= 0) return
    if ($runDetailsTitle.length) {
      $runDetailsTitle.text('Quiet Period Details')
    }
    if ($runDetailsBody.length) {
      const renderGapBlock = (title, gapSeconds, startedAtRaw, endedAtRaw, startLine, endLine, overlap, lastLine, firstLine) => {
        if (!(gapSeconds > 0)) {
          return `
            <div class="mb-3">
              <div class="fw-semibold mb-1">${escapeHtml(title)}</div>
              <div class="small text-muted">None detected.</div>
            </div>
          `
        }
        const startedAt = formatTimestamp(startedAtRaw) || 'n/a'
        const endedAt = formatTimestamp(endedAtRaw) || 'n/a'
        const lineWindow = startLine && endLine ? `${startLine} → ${endLine}` : 'n/a'
        const beforeLine = lastLine
          ? `<pre class="small mb-0"><code>${escapeHtml(lastLine)}</code></pre>`
          : '<div class="small text-muted">Unavailable</div>'
        const afterLine = firstLine
          ? `<pre class="small mb-0"><code>${escapeHtml(firstLine)}</code></pre>`
          : '<div class="small text-muted">Unavailable</div>'
        return `
          <div class="mb-3">
            <div class="fw-semibold mb-1">${escapeHtml(title)}</div>
            <div class="small text-muted">Duration: ${escapeHtml(formatSeconds(gapSeconds))}</div>
            <div class="small text-muted">Window: ${escapeHtml(startedAt)} to ${escapeHtml(endedAt)}</div>
            <div class="small text-muted">Lines: ${escapeHtml(lineWindow)}</div>
            <div class="small text-muted">Maintenance overlap: ${escapeHtml(overlap || 'unknown')}</div>
          </div>
          <div class="mb-3">
            <div class="fw-semibold mb-1">Last line before gap</div>
            ${beforeLine}
          </div>
          <div class="mb-3">
            <div class="fw-semibold mb-1">First line after gap</div>
            ${afterLine}
          </div>
        `
      }
      const outcome = getQuietPeriodOutcome(run, {
        longestGapEndedAt: summary.longestUnexplainedGapEndedAt || summary.longestGapEndedAt
      })
      const counts = []
      if (summary.gapsOver300 > 0) counts.push(`All >5m: ${summary.gapsOver300}`)
      if (summary.gapsOver900 > 0) counts.push(`All >15m: ${summary.gapsOver900}`)
      if (summary.gapsOver1800 > 0) counts.push(`All >30m: ${summary.gapsOver1800}`)
      counts.push(`Confirmed maintenance: ${summary.confirmedMaintenanceGapsOver300}`)
      counts.push(`Unexplained: ${summary.unexplainedGapsOver300}`)
      const notableRows = summary.notableGaps.length
        ? summary.notableGaps.map(gap => {
          const gapWindow = `${formatTimestamp(gap.started_at) || gap.started_at} to ${formatTimestamp(gap.ended_at) || gap.ended_at}`
          const lineWindow = gap.start_line && gap.end_line ? `${gap.start_line} → ${gap.end_line}` : 'n/a'
          return `
              <tr>
                <td>${escapeHtml(formatSeconds(gap.gap_seconds))}</td>
                <td>${escapeHtml(gapWindow)}</td>
                <td>${escapeHtml(lineWindow)}</td>
                <td>${escapeHtml(gap.maintenance_overlap || 'unknown')}</td>
              </tr>
            `
        }).join('')
        : '<tr><td colspan="4" class="text-muted">No notable gaps recorded.</td></tr>'
      $runDetailsBody.html(`
        <div class="mb-3">
          <div class="fw-semibold mb-2">Summary</div>
          <div class="small text-muted">Longest unexplained quiet period: ${escapeHtml(formatSeconds(summary.longestUnexplainedGapSeconds) || 'n/a')}</div>
          <div class="small text-muted">Longest overall quiet period: ${escapeHtml(formatSeconds(summary.longestGapSeconds) || 'n/a')}</div>
          <div class="small text-muted">Run outcome: ${escapeHtml(outcome)}</div>
          <div class="small text-muted">Gap counts: ${escapeHtml(counts.join(' • ') || 'Longest gap only')}</div>
        </div>
        ${renderGapBlock(
          'Longest unexplained quiet period',
          summary.longestUnexplainedGapSeconds,
          summary.longestUnexplainedGapStartedAt,
          summary.longestUnexplainedGapEndedAt,
          summary.longestUnexplainedGapStartLine,
          summary.longestUnexplainedGapEndLine,
          summary.longestUnexplainedGapOverlap,
          summary.longestUnexplainedGapLastLine,
          summary.longestUnexplainedGapFirstLine
        )}
        ${renderGapBlock(
          'Longest overall quiet period',
          summary.longestGapSeconds,
          summary.longestGapStartedAt,
          summary.longestGapEndedAt,
          summary.longestGapStartLine,
          summary.longestGapEndLine,
          summary.maintenanceOverlap,
          summary.longestGapLastLine,
          summary.longestGapFirstLine
        )}
        <div>
          <div class="fw-semibold mb-2">Notable quiet periods (&gt;5m)</div>
          <div class="table-responsive">
            <table class="table table-dark table-sm align-middle mb-0">
              <thead>
                <tr>
                  <th>Duration</th>
                  <th>Window</th>
                  <th>Lines</th>
                  <th>Overlap</th>
                </tr>
              </thead>
              <tbody>${notableRows}</tbody>
            </table>
          </div>
        </div>
      `)
    }
    if (runDetailsModalEl) {
      bootstrap.Modal.getOrCreateInstance(runDetailsModalEl).show()
    }
  }

  function fetchRuns (options = {}) {
    const suppressStatus = options && options.suppressStatus
    const rawLimit = String($limit.val() || '500').toLowerCase()
    const safeLimit = rawLimit === 'all' ? 'all' : (Number.isFinite(parseInt(rawLimit, 10)) ? parseInt(rawLimit, 10) : 500)
    if (!suppressStatus) updateStatus('Loading trends...')
    fetch(`/logscan/trends?limit=${safeLimit}`)
      .then(res => res.json())
      .then(data => {
        allRuns = Array.isArray(data.runs) ? data.runs : []
        allIncompleteRuns = Array.isArray(data.incomplete_runs) ? data.incomplete_runs : []
        allTableRuns = allRuns.concat(allIncompleteRuns)
        pruneSelectedRunKeys()
        allRunsTotal = Number.isFinite(data.total_runs) ? data.total_runs : allRuns.length
        allIncompleteRunsTotal = Number.isFinite(data.total_incomplete_runs) ? data.total_incomplete_runs : allIncompleteRuns.length
        latestArchiveStorage = data && data.archive_storage ? data.archive_storage : null
        renderArchiveStorageSummary(latestArchiveStorage)
        if (data && data.ingest_health && (!lastIngestState || lastIngestState.status !== 'running')) {
          lastIngestState = data.ingest_health
        }
        updateConfigFilter(allTableRuns)
        updateCommandFilter(allTableRuns)
        updateDateRangeInputs(allTableRuns, getFilterState())
        loadPreferences()
          .then(() => {
            applyFiltersAndRender()
            if (!suppressStatus && (!lastIngestState || lastIngestState.status !== 'running')) {
              updateStatus(`Last updated: ${formatTimestamp(new Date().toISOString())}`)
            }
            maybeStartAutoReingest(data && data.ingest_health)
          })
      })
      .catch(err => {
        console.error(err)
        if (!suppressStatus) updateStatus('Failed to load trends.')
        $summary.text('Unable to load summary.')
        $daily.text('Unable to load daily totals.')
        if ($dailyRuntime.length) {
          $dailyRuntime.text('Unable to load runtime averages.')
        }
        $runtime.text('Unable to load runtime distribution.')
        $counts.text('Unable to load log-level averages.')
        $issues.text('Unable to load issue trends.')
        $libraries.text('Unable to load library totals.')
        if ($tableSummary.length) $tableSummary.text('Unable to load runs.')
        if ($tablePolicy.length) $tablePolicy.text('Unable to load archived log policy.')
        if ($tablePageInfo.length) $tablePageInfo.text('No rows')
        $tablePrev.prop('disabled', true)
        $tableNext.prop('disabled', true)
        $tableBody.html('<tr><td colspan="18" class="text-muted">Unable to load runs.</td></tr>')
        updateSelectionSummary()
      })
  }

  function refreshAnalyticsPage (options = {}) {
    const suppressStatus = Boolean(options && options.suppressStatus)
    checkMissingDownload()
    fetchRuns({ suppressStatus })
    fetchReingestStatus()
  }

  function getSelectedRuns () {
    if (!selectedRunKeys.size) return []
    return getSelectableRuns(allTableRuns).filter(run => selectedRunKeys.has(run.run_key))
  }

  function openCompressLogModal (runKeys, runLabel) {
    const normalizedRunKeys = Array.isArray(runKeys)
      ? runKeys.map(value => String(value || '').trim()).filter(Boolean)
      : [String(runKeys || '').trim()].filter(Boolean)
    if (!normalizedRunKeys.length) return
    pendingCompressRun = {
      runKeys: normalizedRunKeys,
      runLabel,
      bulk: normalizedRunKeys.length > 1
    }
    if ($compressLogBody.length) {
      if (normalizedRunKeys.length === 1) {
        $compressLogBody.html(`Compress archived log for <strong>${escapeHtml(runLabel || normalizedRunKeys[0])}</strong> as <code>.log.gz</code>?`)
      } else {
        $compressLogBody.html(`Compress <strong>${normalizedRunKeys.length} selected logs</strong> as <code>.log.gz</code>?`)
      }
    }
    if (compressLogModalEl) {
      bootstrap.Modal.getOrCreateInstance(compressLogModalEl).show()
      return
    }
    const confirmText = normalizedRunKeys.length === 1
      ? `Compress archived log for ${runLabel || normalizedRunKeys[0]}?`
      : `Compress ${normalizedRunKeys.length} selected logs?`
    if (window.confirm(confirmText)) {
      handleCompressLog()
    }
  }

  function openDeleteLogModal (runKeys, runLabel) {
    const normalizedRunKeys = Array.isArray(runKeys)
      ? runKeys.map(value => String(value || '').trim()).filter(Boolean)
      : [String(runKeys || '').trim()].filter(Boolean)
    if (!normalizedRunKeys.length) return
    pendingDeleteRun = {
      runKeys: normalizedRunKeys,
      runLabel,
      bulk: normalizedRunKeys.length > 1
    }
    if ($deleteLogBody.length) {
      if (normalizedRunKeys.length === 1) {
        $deleteLogBody.html(`Delete log for <strong>${escapeHtml(runLabel || normalizedRunKeys[0])}</strong> from disk and remove it from Analytics?`)
      } else {
        $deleteLogBody.html(`Delete <strong>${normalizedRunKeys.length} selected logs</strong> from disk and remove their runs from Analytics?`)
      }
    }
    setModalAlert($deleteLogStatus, '')
    setModalAlert($deleteLogSuccess, '')
    setModalAlert($deleteLogError, '')
    $confirmDeleteLog.text('Delete')
    setDeleteModalBusy(false)
    if (deleteLogModalEl) {
      bootstrap.Modal.getOrCreateInstance(deleteLogModalEl).show()
      return
    }
    const confirmText = normalizedRunKeys.length === 1
      ? `Delete log for ${runLabel || normalizedRunKeys[0]}?`
      : `Delete ${normalizedRunKeys.length} selected logs?`
    if (window.confirm(confirmText)) {
      handleDeleteLog()
    }
  }

  function openInvalidLogModal () {
    if (!pendingInvalidLogCleanup || !Number.isFinite(pendingInvalidLogCleanup.count) || pendingInvalidLogCleanup.count <= 0) {
      return
    }
    const invalidCount = pendingInvalidLogCleanup.count
    const sample = Array.isArray(pendingInvalidLogCleanup.sample) ? pendingInvalidLogCleanup.sample : []
    if ($invalidLogBody.length) {
      const sampleHtml = sample.length
        ? `<div class="small text-muted mt-2">Samples: ${escapeHtml(sample.join(', '))}</div>`
        : ''
      $invalidLogBody.html(
        invalidCount === 1
          ? `Delete <strong>1 invalid archived log</strong> from disk?${sampleHtml}`
          : `Delete <strong>${invalidCount} invalid archived logs</strong> from disk?${sampleHtml}`
      )
    }
    setModalAlert($invalidLogStatus, '')
    setModalAlert($invalidLogSuccess, '')
    setModalAlert($invalidLogError, '')
    $confirmInvalidLog.text('Delete')
    setInvalidLogModalBusy(false)
    if (invalidLogModalEl) {
      bootstrap.Modal.getOrCreateInstance(invalidLogModalEl).show()
      return
    }
    const confirmText = invalidCount === 1
      ? 'Delete 1 invalid archived log?'
      : `Delete ${invalidCount} invalid archived logs?`
    if (window.confirm(confirmText)) {
      handleInvalidLogDelete()
    }
  }

  function handleDeleteLog () {
    if (!pendingDeleteRun || !Array.isArray(pendingDeleteRun.runKeys) || !pendingDeleteRun.runKeys.length) {
      hideModal(deleteLogModalEl)
      return
    }
    let deleteSucceeded = false
    const deleteCount = pendingDeleteRun.runKeys.length
    setModalAlert($deleteLogSuccess, '')
    setModalAlert($deleteLogError, '')
    setModalAlert($deleteLogStatus, deleteCount > 1 ? `Deleting ${deleteCount} logs...` : 'Deleting log...')
    setDeleteModalBusy(true)
    setButtonSpinner($confirmDeleteLog, 'Deleting...')
    fetch('/logscan/trends/log/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(
        pendingDeleteRun.runKeys.length === 1
          ? { run_key: pendingDeleteRun.runKeys[0] }
          : { run_keys: pendingDeleteRun.runKeys }
      )
    })
      .then(async res => {
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          throw new Error((data && data.error) || 'Delete failed')
        }
        const deletedKeys = Array.isArray(pendingDeleteRun.runKeys) ? pendingDeleteRun.runKeys : []
        deletedKeys.forEach(runKey => selectedRunKeys.delete(runKey))
        const deletedCount = Number.isFinite(data && data.deleted) ? data.deleted : deletedKeys.length
        deleteSucceeded = true
        pendingDeleteRun = null
        setModalAlert($deleteLogStatus, '')
        setModalAlert($deleteLogSuccess, deletedCount > 1 ? `${deletedCount} logs deleted. Updating Analytics...` : 'Log deleted. Updating Analytics...')
        if (Array.isArray(data && data.failures) && data.failures.length) {
          updateStatus(`${deletedCount} logs deleted. ${data.failures.length} failed.`)
        } else {
          updateStatus(deletedCount > 1 ? `${deletedCount} logs deleted.` : 'Log deleted.')
        }
        window.setTimeout(() => hideModal(deleteLogModalEl), 650)
        fetchRuns({ suppressStatus: true })
      })
      .catch(err => {
        console.error(err)
        setModalAlert($deleteLogStatus, '')
        setModalAlert($deleteLogError, err && err.message ? err.message : 'Failed to delete log.')
        updateStatus(err && err.message ? err.message : 'Failed to delete log.', true)
      })
      .finally(() => {
        if (!deleteSucceeded) {
          $confirmDeleteLog.text('Delete')
          setDeleteModalBusy(false)
        }
      })
  }

  function handleInvalidLogDelete () {
    if (!pendingInvalidLogCleanup || !Number.isFinite(pendingInvalidLogCleanup.count) || pendingInvalidLogCleanup.count <= 0) {
      hideModal(invalidLogModalEl)
      return
    }
    let deleteSucceeded = false
    const invalidCount = pendingInvalidLogCleanup.count
    setModalAlert($invalidLogSuccess, '')
    setModalAlert($invalidLogError, '')
    setModalAlert($invalidLogStatus, invalidCount > 1 ? `Deleting ${invalidCount} invalid archived logs...` : 'Deleting invalid archived log...')
    setInvalidLogModalBusy(true)
    setButtonSpinner($confirmInvalidLog, 'Deleting...')
    fetch('/logscan/trends/log/invalid/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
      .then(async res => {
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          throw new Error((data && data.error) || 'Delete failed')
        }
        const deletedCount = Number.isFinite(data && data.deleted) ? data.deleted : invalidCount
        deleteSucceeded = true
        pendingInvalidLogCleanup = null
        setModalAlert($invalidLogStatus, '')
        setModalAlert($invalidLogSuccess, deletedCount > 1 ? `${deletedCount} invalid archived logs deleted. Updating Analytics...` : 'Invalid archived log deleted. Updating Analytics...')
        if (Array.isArray(data && data.failures) && data.failures.length) {
          updateStatus(`${deletedCount} invalid archived logs deleted. ${data.failures.length} failed.`)
        } else {
          updateStatus(deletedCount > 1 ? `${deletedCount} invalid archived logs deleted.` : 'Invalid archived log deleted.')
        }
        window.setTimeout(() => hideModal(invalidLogModalEl), 650)
        fetchRuns({ suppressStatus: true })
      })
      .catch(err => {
        console.error(err)
        setModalAlert($invalidLogStatus, '')
        setModalAlert($invalidLogError, err && err.message ? err.message : 'Failed to delete invalid archived logs.')
        updateStatus(err && err.message ? err.message : 'Failed to delete invalid archived logs.', true)
      })
      .finally(() => {
        if (!deleteSucceeded) {
          $confirmInvalidLog.text('Delete')
          setInvalidLogModalBusy(false)
        }
      })
  }

  function handleCompressLog () {
    if (!pendingCompressRun || !Array.isArray(pendingCompressRun.runKeys) || !pendingCompressRun.runKeys.length) {
      hideModal(compressLogModalEl)
      return
    }
    let compressSucceeded = false
    const compressCount = pendingCompressRun.runKeys.length
    setModalAlert($compressLogSuccess, '')
    setModalAlert($compressLogError, '')
    setModalAlert($compressLogStatus, compressCount > 1 ? `Compressing ${compressCount} logs...` : 'Compressing log...')
    setCompressModalBusy(true)
    setButtonSpinner($confirmCompressLog, 'Compressing...')
    fetch('/logscan/trends/log/compress', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(
        pendingCompressRun.runKeys.length === 1
          ? { run_key: pendingCompressRun.runKeys[0] }
          : { run_keys: pendingCompressRun.runKeys }
      )
    })
      .then(async res => {
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          throw new Error((data && data.error) || 'Compress failed')
        }
        const compressedCount = Number.isFinite(data && data.compressed) ? data.compressed : pendingCompressRun.runKeys.length
        compressSucceeded = true
        pendingCompressRun = null
        setModalAlert($compressLogStatus, '')
        setModalAlert($compressLogSuccess, compressedCount > 1 ? `${compressedCount} logs compressed. Updating Analytics...` : 'Log compressed. Updating Analytics...')
        if (Array.isArray(data && data.failures) && data.failures.length) {
          updateStatus(`${compressedCount} logs compressed. ${data.failures.length} failed.`)
        } else {
          updateStatus(compressedCount > 1 ? `${compressedCount} logs compressed.` : 'Log compressed.')
        }
        window.setTimeout(() => hideModal(compressLogModalEl), 650)
        fetchRuns({ suppressStatus: true })
      })
      .catch(err => {
        console.error(err)
        setModalAlert($compressLogStatus, '')
        setModalAlert($compressLogError, err && err.message ? err.message : 'Failed to compress log.')
        updateStatus(err && err.message ? err.message : 'Failed to compress log.', true)
      })
      .finally(() => {
        if (!compressSucceeded) {
          $confirmCompressLog.text('Compress')
          setCompressModalBusy(false)
        }
      })
  }

  $limit.on('change', function () {
    syncMirroredControlValue($limit, this)
    tablePage = 1
    fetchRuns()
  })
  $tablePageSize.on('change', function () {
    tablePage = 1
    renderTable(currentTableRuns)
  })
  $tableSortKey.on('change', function () {
    const key = String($tableSortKey.val() || 'finished_at')
    if (!key) return
    sortState.key = key
    tablePage = 1
    applyFiltersAndRender()
  })
  $tableSortDir.on('change', function () {
    sortState.dir = $tableSortDir.val() === 'asc' ? 'asc' : 'desc'
    tablePage = 1
    applyFiltersAndRender()
  })
  $tablePrev.on('click', function () {
    if (tablePage <= 1) return
    tablePage -= 1
    renderTable(currentTableRuns)
  })
  $tableNext.on('click', function () {
    const pageCount = Math.max(1, Math.ceil(currentTableRuns.length / getTablePageSize()))
    if (tablePage >= pageCount) return
    tablePage += 1
    renderTable(currentTableRuns)
  })
  if (tableCollapseEl) {
    tableCollapseEl.addEventListener('shown.bs.collapse', function () {
      $tableToggle.text('Hide table')
    })
    tableCollapseEl.addEventListener('hidden.bs.collapse', function () {
      $tableToggle.text('Show table')
    })
  }
  $configFilter.on('change', function () {
    syncMirroredControlValue($configFilter, this)
    tablePage = 1
    loadPreferences().then(() => applyFiltersAndRender())
  })
  $toolFilter.on('change', function () {
    syncMirroredControlValue($toolFilter, this)
    tablePage = 1
    clearDateFilters()
    applyFiltersAndRender()
  })
  $timeRange.on('change', function () {
    syncMirroredControlValue($timeRange, this)
    tablePage = 1
    clearDateFilters()
    applyFiltersAndRender()
  })
  $commandFilter.on('change', function () {
    syncMirroredControlValue($commandFilter, this)
    tablePage = 1
    applyFiltersAndRender()
  })
  $dateStart.on('change', function () {
    syncMirroredControlValue($dateStart, this)
    tablePage = 1
    applyFiltersAndRender()
  })
  $dateEnd.on('change', function () {
    syncMirroredControlValue($dateEnd, this)
    tablePage = 1
    applyFiltersAndRender()
  })
  $libraryFilter.on('change', function () {
    syncMirroredControlValue($libraryFilter, this)
    renderLibraryInventory(currentFilteredRuns)
  })
  $countsSeries.on('click', '.logscan-series-toggle', function () {
    const key = $(this).data('seriesKey') || $(this).attr('data-series-key')
    if (!key || !Object.prototype.hasOwnProperty.call(countsSeriesSelection, key)) return
    const currentlyEnabled = Boolean(countsSeriesSelection[key])
    if (currentlyEnabled && getSelectedCountSeries().length <= 1) {
      return
    }
    countsSeriesSelection[key] = !currentlyEnabled
    saveCountsSeriesSelection(countsSeriesSelection)
    renderCountsSeriesSelector()
    renderCountsMix(currentFilteredRuns)
  })
  $resetFilters.on('click', function () {
    $limit.val('500')
    tablePage = 1
    tableStatusFilter = 'all'
    $configFilter.val('')
    $toolFilter.val('')
    $timeRange.val('all')
    $commandFilter.val('')
    $libraryFilter.val('')
    clearDateFilters()
    fetchRuns({ suppressStatus: true })
  })
  if (preferencesModalEl) {
    preferencesModalEl.addEventListener('show.bs.modal', function () {
      syncPreferencesModal()
    })
  }
  $preferencesSave.on('click', function () {
    const prefs = collectPreferencesFromModal()
    savePreferences(prefs)
      .then(() => {
        if ($preferencesStatus.length) {
          $preferencesStatus.text('Preferences saved.')
        }
        applyFiltersAndRender()
      })
      .catch(() => {
        if ($preferencesStatus.length) {
          $preferencesStatus.text('Unable to save preferences.')
        }
      })
  })
  $preferencesRecommended.on('click', function () {
    const prefs = mergePreferences(ANALYTICS_RECOMMENDED_PREFS)
    analyticsPrefs = prefs
    applyPanelVisibility()
    syncPreferencesModal()
    savePreferences(prefs)
      .then(() => {
        if ($preferencesStatus.length) {
          $preferencesStatus.text('Recommended preset saved.')
        }
        applyFiltersAndRender()
      })
      .catch(() => {
        if ($preferencesStatus.length) {
          $preferencesStatus.text('Unable to save recommended preset.')
        }
      })
  })
  $confirmReset.on('click', handleReset)
  $confirmReingest.on('click', handleReingest)
  $clearInvalidArchived.on('click', function () {
    if ($clearInvalidArchived.hasClass('d-none')) return
    openInvalidLogModal()
  })
  $confirmInvalidLog.on('click', handleInvalidLogDelete)
  $confirmDeleteLog.on('click', handleDeleteLog)
  $confirmCompressLog.on('click', handleCompressLog)
  $missingDownload.on('click', function (event) {
    event.preventDefault()
    if (!$missingDownload.length || $missingDownload.hasClass('d-none')) return
    missingDownloadUrl = $missingDownload.attr('href') || ''
    if (!missingDownloadModalEl) {
      if (missingDownloadUrl) window.location.href = missingDownloadUrl
      return
    }
    const modal = bootstrap.Modal.getOrCreateInstance(missingDownloadModalEl)
    modal.show()
  })
  $confirmMissingDownload.on('click', function () {
    if (!missingDownloadUrl) {
      hideModal(missingDownloadModalEl)
      return
    }
    hideModal(missingDownloadModalEl)
    window.location.href = missingDownloadUrl
  })
  $tableBody.on('click', '.logscan-run-details', function () {
    const runKey = $(this).data('runKey') || $(this).attr('data-run-key')
    showRunDetails(runKey)
  })
  $tableBody.on('click', '.logscan-progress-toggle', function () {
    const runKey = $(this).data('runKey') || $(this).attr('data-run-key')
    if (!runKey) return
    if (expandedProgressRunKeys.has(runKey)) {
      expandedProgressRunKeys.delete(runKey)
    } else {
      expandedProgressRunKeys.add(runKey)
    }
    renderTable(currentTableRuns)
  })
  $tableBody.on('change', '.logscan-select-toggle-input', function () {
    const runKey = $(this).data('runKey') || $(this).attr('data-run-key')
    if (!runKey) return
    if ($(this).is(':checked')) {
      selectedRunKeys.add(runKey)
    } else {
      selectedRunKeys.delete(runKey)
    }
    renderTable(currentTableRuns)
  })
  $tableBody.on('click', '.logscan-delete-log', function () {
    const runKey = $(this).data('runKey') || $(this).attr('data-run-key')
    const runLabel = $(this).data('runLabel') || $(this).attr('data-run-label') || runKey
    if (!runKey) return
    openDeleteLogModal(runKey, runLabel)
  })
  $tableBody.on('click', '.logscan-compress-log', function () {
    const runKey = $(this).data('runKey') || $(this).attr('data-run-key')
    const runLabel = $(this).data('runLabel') || $(this).attr('data-run-label') || runKey
    if (!runKey) return
    openCompressLogModal(runKey, runLabel)
  })
  $tableSelectAll.on('click', function () {
    getSelectableRuns(currentTableRuns).forEach(run => selectedRunKeys.add(run.run_key))
    renderTable(currentTableRuns)
  })
  $tableSelectComplete.on('click', function () {
    tableStatusFilter = tableStatusFilter === 'complete' ? 'all' : 'complete'
    tablePage = 1
    applyFiltersAndRender()
  })
  $tableSelectIncomplete.on('click', function () {
    tableStatusFilter = tableStatusFilter === 'incomplete' ? 'all' : 'incomplete'
    tablePage = 1
    applyFiltersAndRender()
  })
  $tableClearSelection.on('click', function () {
    selectedRunKeys.clear()
    renderTable(currentTableRuns)
  })
  $tableDeleteSelected.on('click', function () {
    const selectedRuns = getSelectedRuns()
    if (!selectedRuns.length) return
    openDeleteLogModal(selectedRuns.map(run => run.run_key), `${selectedRuns.length} selected logs`)
  })
  $tableCompressSelected.on('click', function () {
    const selectedRuns = getSelectedCompressibleRuns()
    if (!selectedRuns.length) return
    openCompressLogModal(selectedRuns.map(run => run.run_key), `${selectedRuns.length} selected logs`)
  })
  $tableBody.on('click', '[data-section-details="1"]', function () {
    const runKey = $(this).data('runKey') || $(this).attr('data-run-key')
    showSectionDetails(runKey)
  })
  $tableBody.on('click', '.logscan-quiet-period-details', function () {
    const runKey = $(this).data('runKey') || $(this).attr('data-run-key')
    showQuietPeriodDetails(runKey)
  })
  $('#logscan-trends-table thead').on('click', '.logscan-sort-button', function () {
    const key = $(this).data('sort')
    if (!key) return
    tablePage = 1
    if (sortState.key === key) {
      sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc'
    } else {
      sortState.key = key
      sortState.dir = 'desc'
    }
    applyFiltersAndRender()
  })
  window.addEventListener('pageshow', function (event) {
    if (!event || !event.persisted) return
    refreshAnalyticsPage({ suppressStatus: true })
  })
  renderCountsSeriesSelector()
  refreshAnalyticsPage()
})
