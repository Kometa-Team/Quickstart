/* global $, bootstrap */

$(document).ready(function () {
  const $tableBody = $('#logscan-trends-table tbody')
  const $summary = $('#logscan-trends-summary')
  const $daily = $('#logscan-trends-daily')
  const $runtime = $('#logscan-trends-runtime')
  const $counts = $('#logscan-trends-counts')
  const $ingest = $('#logscan-trends-ingest')
  const $analyze = $('#logscan-trends-analyze')
  const $status = $('#logscan-trends-status')
  const $progress = $('#logscan-trends-progress')
  const $progressBar = $('#logscan-trends-progress-bar')
  const $progressText = $('#logscan-trends-progress-text')
  const $limit = $('#logscan-trends-limit')
  const $configFilter = $('#logscan-trends-config-filter')
  const $refresh = $('#logscan-trends-refresh')
  const $reset = $('#logscan-trends-reset')
  const $reingest = $('#logscan-trends-reingest')
  const $confirmReset = $('#logscan-confirm-reset')
  const $confirmReingest = $('#logscan-confirm-reingest')
  const $missingDownload = $('#logscan-trends-missing-download')
  const $confirmMissingDownload = $('#logscan-confirm-missing-download')
  const $runDetailsBody = $('#logscan-run-details-body')
  const $runDetailsTitle = $('#logscan-run-details-title')
  const resetModalEl = document.getElementById('logscan-reset-modal')
  const reingestModalEl = document.getElementById('logscan-reingest-modal')
  const missingDownloadModalEl = document.getElementById('logscan-missing-download-modal')
  const runDetailsModalEl = document.getElementById('logscan-run-details-modal')
  let missingDownloadUrl = ''
  let reingestPollTimer = null
  let reingestJobId = null
  let allRuns = []
  const sortState = { key: 'finished_at', dir: 'desc' }
  let lastIngestState = null

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
    if (!value) return null
    const text = String(value).trim()
    const match = text.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})/)
    if (match) return `${match[1]} ${match[2]}`
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

  function getSectionTotal (sectionRuntimes) {
    if (!sectionRuntimes || typeof sectionRuntimes !== 'object') return 0
    return Object.values(sectionRuntimes).reduce((sum, value) => {
      if (typeof value === 'number' && Number.isFinite(value)) return sum + value
      return sum
    }, 0)
  }

  function getCountsTotal (run) {
    return getCount(run, 'warning_count') + getCount(run, 'error_count') + getCount(run, 'trace_count')
  }

  function normalizeConfigName (value) {
    const cleaned = String(value || '').trim()
    return cleaned || 'default'
  }

  function getCount (run, key) {
    const value = run && typeof run[key] === 'number' ? run[key] : 0
    return Number.isFinite(value) ? value : 0
  }

  function getAnalyzeCount (run, key) {
    const counts = run && run.analysis_counts && typeof run.analysis_counts === 'object'
      ? run.analysis_counts
      : {}
    const value = counts && typeof counts[key] === 'number' ? counts[key] : 0
    return Number.isFinite(value) ? value : 0
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
      if (!buckets[key]) {
        buckets[key] = { total: 0, configs: {} }
      }
      buckets[key].total += 1
      buckets[key].configs[config] = (buckets[key].configs[config] || 0) + 1
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
      .map(run => run.run_time_seconds)
      .filter(val => typeof val === 'number' && Number.isFinite(val) && val > 0)
    const avgRuntime = runtimeValues.length
      ? runtimeValues.reduce((sum, val) => sum + val, 0) / runtimeValues.length
      : null
    const configs = new Set(runs.map(run => normalizeConfigName(run.config_name)))
    const lines = [
      `Runs stored: ${runs.length}`,
      `Latest run: ${getDisplayFinished(latest)}`,
      `Average runtime: ${avgRuntime ? formatSeconds(avgRuntime) : 'n/a'}`,
      `Configs tracked: ${configs.size}`
    ]
    const selectedConfig = $configFilter.val()
    if (selectedConfig) {
      lines.push(`Filtered config: ${selectedConfig}`)
    }
    $summary.html(lines.map(line => `<div>${escapeHtml(line)}</div>`).join(''))
  }

  function renderDaily (runs) {
    const buckets = buildDailyBuckets(runs)
    const days = Object.keys(buckets).sort().slice(-14)
    if (!days.length) {
      $daily.text('No daily totals yet.')
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
  }

  function renderTable (runs) {
    if (!runs.length) {
      $tableBody.html('<tr><td colspan="8" class="text-muted">No runs stored yet.</td></tr>')
      return
    }
    const rows = runs.map((run, index) => {
      const command = run.command_signature || 'n/a'
      const commandTitle = run.run_command || ''
      const counts = `W:${getCount(run, 'warning_count')} E:${getCount(run, 'error_count')} T:${getCount(run, 'trace_count')}`
      const countsTitle = `Warnings: ${getCount(run, 'warning_count')} | Errors: ${getCount(run, 'error_count')} | Tracebacks: ${getCount(run, 'trace_count')}`
      const sectionLines = buildSectionDetails(run.section_runtimes, run.run_time_seconds)
      const sectionId = `logscan-section-${index + 1}`
      const sectionSummary = sectionLines.length ? sectionLines[0] : 'n/a'
      const sectionDetails = sectionLines.length > 1 ? sectionLines.slice(1) : []
      const sectionDetailsHtml = sectionDetails.map(line => `<div>${escapeHtml(line)}</div>`).join('')
      let sectionCell = `
        <div class="d-flex flex-column align-items-center gap-1">
          <div class="text-muted small text-center">${escapeHtml(sectionSummary)}</div>
      `
      if (sectionDetails.length) {
        sectionCell += `
          <button type="button" class="btn nav-button btn-sm logscan-action-btn"
            data-bs-toggle="collapse" data-bs-target="#${sectionId}"
            aria-expanded="false" aria-controls="${sectionId}">
            Expand
          </button>
          <div class="collapse mt-2" id="${sectionId}">
            <div class="text-muted small">${sectionDetailsHtml}</div>
          </div>
        `
      }
      sectionCell += '</div>'
      let kometaDisplay = run.kometa_version || 'n/a'
      if (run.kometa_version && run.kometa_newest_version && run.kometa_version !== run.kometa_newest_version) {
        kometaDisplay = `${run.kometa_version} -> ${run.kometa_newest_version}`
      }
      const runKey = run.run_key || ''
      return `
        <tr>
          <td class="text-nowrap">${escapeHtml(getDisplayFinished(run))}</td>
          <td>${escapeHtml(formatSeconds(run.run_time_seconds))}</td>
          <td>${escapeHtml(run.config_name || 'default')}</td>
          <td><span title="${escapeHtml(commandTitle)}">${escapeHtml(command)}</span></td>
          <td title="${escapeHtml(countsTitle)}">${escapeHtml(counts)}</td>
          <td>${escapeHtml(kometaDisplay)}</td>
          <td class="text-center align-middle">${sectionCell}</td>
          <td class="text-center align-middle">
            <button type="button" class="btn nav-button btn-sm logscan-action-btn logscan-run-details"
              data-run-key="${escapeHtml(runKey)}">Open</button>
          </td>
        </tr>
      `
    })
    $tableBody.html(rows.join(''))
  }

  function renderRuntimeDistribution (runs) {
    if (!$runtime.length) return
    const durations = runs
      .map(run => run.run_time_seconds)
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
    const buckets = {}
    runs.forEach(run => {
      const key = getRunDateKey(run)
      if (!key) return
      if (!buckets[key]) {
        buckets[key] = { warning: 0, error: 0, trace: 0 }
      }
      buckets[key].warning += getCount(run, 'warning_count')
      buckets[key].error += getCount(run, 'error_count')
      buckets[key].trace += getCount(run, 'trace_count')
    })
    const days = Object.keys(buckets).sort().slice(-14)
    if (!days.length) {
      $counts.text('No W/E/T totals yet.')
      return
    }
    const totals = days.map(day => buckets[day].warning + buckets[day].error + buckets[day].trace)
    const maxTotal = Math.max(...totals, 1)
    const rows = days.map((day, index) => {
      const data = buckets[day]
      const total = totals[index]
      const barWidth = maxTotal ? Math.round((total / maxTotal) * 100) : 0
      const warningPct = total ? Math.round((data.warning / total) * 100) : 0
      const errorPct = total ? Math.round((data.error / total) * 100) : 0
      const tracePct = total ? Math.max(0, 100 - warningPct - errorPct) : 0
      return `
        <div class="logscan-stack-row">
          <div class="logscan-stack-label">${escapeHtml(day)}</div>
          <div class="logscan-stack-bar-wrap">
            <div class="logscan-stack-bar" style="width: ${barWidth}%">
              <span class="logscan-stack-segment logscan-stack-warning" style="width: ${warningPct}%"></span>
              <span class="logscan-stack-segment logscan-stack-error" style="width: ${errorPct}%"></span>
              <span class="logscan-stack-segment logscan-stack-trace" style="width: ${tracePct}%"></span>
            </div>
          </div>
          <div class="logscan-stack-count">W:${data.warning} E:${data.error} T:${data.trace}</div>
        </div>
      `
    })
    const legend = `
      <div class="logscan-stack-legend">
        <span><span class="logscan-legend-swatch logscan-stack-warning"></span>Warnings</span>
        <span><span class="logscan-legend-swatch logscan-stack-error"></span>Errors</span>
        <span><span class="logscan-legend-swatch logscan-stack-trace"></span>Tracebacks</span>
      </div>
    `
    $counts.html(`${rows.join('')}${legend}`)
  }

  function renderAnalyzeIssues (runs) {
    if (!$analyze.length) return
    const buckets = {}
    runs.forEach(run => {
      const key = getRunDateKey(run)
      if (!key) return
      if (!buckets[key]) {
        buckets[key] = { convert: 0, anidb: 0, regex: 0 }
      }
      buckets[key].convert += getAnalyzeCount(run, 'convert')
      buckets[key].anidb += getAnalyzeCount(run, 'anidb')
      buckets[key].regex += getAnalyzeCount(run, 'regex')
    })
    const days = Object.keys(buckets).sort().slice(-14)
    if (!days.length) {
      $analyze.text('No analyze issue totals yet.')
      return
    }
    const totals = days.map(day => buckets[day].convert + buckets[day].anidb + buckets[day].regex)
    const maxTotal = Math.max(...totals, 1)
    const rows = days.map((day, index) => {
      const data = buckets[day]
      const total = totals[index]
      const barWidth = maxTotal ? Math.round((total / maxTotal) * 100) : 0
      const convertPct = total ? Math.round((data.convert / total) * 100) : 0
      const anidbPct = total ? Math.round((data.anidb / total) * 100) : 0
      const regexPct = total ? Math.max(0, 100 - convertPct - anidbPct) : 0
      return `
        <div class="logscan-stack-row">
          <div class="logscan-stack-label">${escapeHtml(day)}</div>
          <div class="logscan-stack-bar-wrap">
            <div class="logscan-stack-bar" style="width: ${barWidth}%">
              <span class="logscan-stack-segment logscan-stack-convert" style="width: ${convertPct}%"></span>
              <span class="logscan-stack-segment logscan-stack-anidb" style="width: ${anidbPct}%"></span>
              <span class="logscan-stack-segment logscan-stack-regex" style="width: ${regexPct}%"></span>
            </div>
          </div>
          <div class="logscan-stack-count">C:${data.convert} A:${data.anidb} R:${data.regex}</div>
        </div>
      `
    })
    const legend = `
      <div class="logscan-stack-legend">
        <span><span class="logscan-legend-swatch logscan-stack-convert"></span>Convert</span>
        <span><span class="logscan-legend-swatch logscan-stack-anidb"></span>AniDB</span>
        <span><span class="logscan-legend-swatch logscan-stack-regex"></span>Regex</span>
      </div>
    `
    $analyze.html(`${rows.join('')}${legend}`)
  }

  function renderIngestHealth (state) {
    if (!$ingest.length) return
    if (!state || typeof state.scanned !== 'number') {
      $ingest.text('No ingest history yet.')
      return
    }
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
    $ingest.html(`<div class="logscan-kpi-grid">${tiles.join('')}</div>`)
  }

  function getSortValue (run, key) {
    switch (key) {
      case 'finished_at':
        return getSortTimestamp(run)
      case 'run_time_seconds':
        return typeof run.run_time_seconds === 'number' ? run.run_time_seconds : 0
      case 'config_name':
        return normalizeConfigName(run.config_name)
      case 'command_signature':
        return run.command_signature || ''
      case 'counts':
        return getCountsTotal(run)
      case 'kometa_version':
        return run.kometa_version || ''
      case 'section_runtimes':
        return getSectionTotal(run.section_runtimes)
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
  }

  function updateConfigFilter (runs) {
    if (!$configFilter.length) return
    const selected = $configFilter.val() || ''
    const configs = Array.from(new Set(runs.map(run => normalizeConfigName(run.config_name)))).sort()
    const options = ['<option value="">All configs</option>']
    configs.forEach(cfg => {
      options.push(`<option value="${escapeHtml(cfg)}">${escapeHtml(cfg)}</option>`)
    })
    $configFilter.html(options.join(''))
    if (selected && configs.includes(selected)) {
      $configFilter.val(selected)
    } else {
      $configFilter.val('')
    }
  }

  function applyFiltersAndRender () {
    const selectedConfig = $configFilter.val()
    const filtered = selectedConfig
      ? allRuns.filter(run => normalizeConfigName(run.config_name) === selectedConfig)
      : allRuns.slice()
    renderSummary(filtered)
    renderDaily(filtered)
    renderRuntimeDistribution(filtered)
    renderCountsMix(filtered)
    renderAnalyzeIssues(filtered)
    renderTable(sortRuns(filtered))
    renderIngestHealth(lastIngestState)
    updateSortIndicators()
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
    $configFilter.prop('disabled', disabled)
    $confirmReset.prop('disabled', disabled)
    $confirmReingest.prop('disabled', disabled)
    $confirmMissingDownload.prop('disabled', disabled)
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

  function formatRecommendationMessage (message) {
    if (!message) return ''
    return escapeHtml(message).replace(/\n/g, '<br>')
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
        const recs = Array.isArray(data.recommendations) ? data.recommendations : []
        if (!recs.length) {
          if ($runDetailsBody.length) {
            $runDetailsBody.text('No recommendations recorded for this run.')
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
          $runDetailsBody.html(blocks.join(''))
        }
      })
      .catch(() => {
        if ($runDetailsBody.length) {
          $runDetailsBody.text('Unable to load recommendations.')
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
        allRuns = Array.isArray(data.runs) ? data.runs : []
        updateConfigFilter(allRuns)
        applyFiltersAndRender()
        if (!suppressStatus) {
          updateStatus(`Last updated: ${formatTimestamp(new Date().toISOString())}`)
        }
      })
      .catch(err => {
        console.error(err)
        if (!suppressStatus) updateStatus('Failed to load trends.')
        $summary.text('Unable to load summary.')
        $daily.text('Unable to load daily totals.')
        $runtime.text('Unable to load runtime distribution.')
        $counts.text('Unable to load W/E/T totals.')
        $analyze.text('Unable to load analyze issue totals.')
        $tableBody.html('<tr><td colspan="8" class="text-muted">Unable to load runs.</td></tr>')
      })
  }

  $refresh.on('click', fetchRuns)
  $limit.on('change', fetchRuns)
  $configFilter.on('change', applyFiltersAndRender)
  $confirmReset.on('click', handleReset)
  $confirmReingest.on('click', handleReingest)
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
  $('#logscan-trends-table thead').on('click', '.logscan-sort-button', function () {
    const key = $(this).data('sort')
    if (!key) return
    if (sortState.key === key) {
      sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc'
    } else {
      sortState.key = key
      sortState.dir = 'desc'
    }
    applyFiltersAndRender()
  })
  checkMissingDownload()
  fetchRuns()
  fetchReingestStatus()
})
