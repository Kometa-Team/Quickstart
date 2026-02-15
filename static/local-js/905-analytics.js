/* global $, bootstrap */

$(document).ready(function () {
  const $tableBody = $('#logscan-trends-table tbody')
  const $summary = $('#logscan-trends-summary')
  const $daily = $('#logscan-trends-daily')
  const $dailyRuntime = $('#logscan-trends-daily-runtime')
  const $runtime = $('#logscan-trends-runtime')
  const $counts = $('#logscan-trends-counts')
  const $ingest = $('#logscan-trends-ingest')
  const $issues = $('#logscan-trends-issues')
  const $libraries = $('#logscan-trends-libraries')
  const $libraryFilter = $('#logscan-trends-library-filter')
  const $status = $('#logscan-trends-status')
  const $progress = $('#logscan-trends-progress')
  const $progressBar = $('#logscan-trends-progress-bar')
  const $progressText = $('#logscan-trends-progress-text')
  const $limit = $('#logscan-trends-limit')
  const $configFilter = $('#logscan-trends-config-filter')
  const $commandFilter = $('#logscan-trends-command-filter')
  const $resetFilters = $('#logscan-trends-reset-filters')
  const $dateStart = $('#logscan-trends-date-start')
  const $dateEnd = $('#logscan-trends-date-end')
  const $runCount = $('#logscan-trends-count')
  const $reset = $('#logscan-trends-reset')
  const $reingest = $('#logscan-trends-reingest')
  const $confirmReset = $('#logscan-confirm-reset')
  const $confirmReingest = $('#logscan-confirm-reingest')
  const $missingDownload = $('#logscan-trends-missing-download')
  const $confirmMissingDownload = $('#logscan-confirm-missing-download')
  const $runDetailsBody = $('#logscan-run-details-body')
  const $runDetailsTitle = $('#logscan-run-details-title')
  const $preferencesSave = $('#logscan-preferences-save')
  const $preferencesRecommended = $('#logscan-preferences-recommended')
  const $preferencesStatus = $('#logscan-preferences-status')
  const $preferencesInputs = $('.logscan-pref-input')
  const resetModalEl = document.getElementById('logscan-reset-modal')
  const reingestModalEl = document.getElementById('logscan-reingest-modal')
  const missingDownloadModalEl = document.getElementById('logscan-missing-download-modal')
  const runDetailsModalEl = document.getElementById('logscan-run-details-modal')
  const preferencesModalEl = document.getElementById('logscan-preferences-modal')
  let missingDownloadUrl = ''
  let reingestPollTimer = null
  let reingestJobId = null
  let allRuns = []
  let currentFilteredRuns = []
  let allRunsTotal = 0
  const sortState = { key: 'finished_at', dir: 'desc' }
  let lastIngestState = null
  let analyticsPrefs = null

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

  function formatAverage (value) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '0'
    if (Number.isInteger(value)) return String(value)
    return value.toFixed(1).replace(/\.0$/, '')
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
    let startIndex = tokens.findIndex(token => /kometa\.py$/i.test(token))
    if (startIndex < 0) startIndex = -1
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
    const parts = ['kometa.py']
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

  function getRunCommandValue (run) {
    if (!run) return ''
    if (run.run_command) return normalizeRunCommand(run.run_command)
    if (run.command_signature) return normalizeRunCommand(`kometa.py ${run.command_signature}`)
    return ''
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
    { key: 'runtime_distribution', label: 'Runtime distribution' },
    { key: 'counts_mix', label: 'Warnings / Errors / Tracebacks' },
    { key: 'issue_trends', label: 'Issue trends' },
    { key: 'library_inventory', label: 'Library inventory' }
  ]

  const ANALYTICS_RECOMMENDED_PREFS = {
    panels: PANEL_PREFS.reduce((acc, item) => ({ ...acc, [item.key]: true }), {}),
    issues: ISSUE_PREFS.reduce((acc, item) => ({ ...acc, [item.key]: ISSUE_DEFAULT_KEYS.has(item.key) }), {})
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
      .map(run => run.run_time_seconds)
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
      const runtime = run.run_time_seconds
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

  function renderTable (runs) {
    if (!runs.length) {
      $tableBody.html('<tr><td colspan="10" class="text-muted">No runs stored yet.</td></tr>')
      return
    }
    const rows = runs.map((run, index) => {
      const command = getRunCommandValue(run) || 'n/a'
      const commandTitle = run.run_command
        ? `Original: ${run.run_command}`
        : (run.command_signature ? `Signature: ${run.command_signature}` : '')
      const warnings = getCount(run, 'warning_count')
      const errors = getCount(run, 'error_count')
      const traces = getCount(run, 'trace_count')
      const counts = `W:${warnings} E:${errors} T:${traces}`
      const libraryTotals = getRunLibraryTotals(run)
      const hasLibraryTotals = libraryTotals.movies > 0 || libraryTotals.episodes > 0 || libraryTotals.shows > 0
      const libraryCounts = hasLibraryTotals
        ? `M:${libraryTotals.movies} S:${libraryTotals.shows} Ep:${libraryTotals.episodes} Tot:${libraryTotals.total}`
        : 'M:- S:- Ep:- Tot:-'
      const countsTitle = `Warnings: ${warnings} | Errors: ${errors} | Tracebacks: ${traces} | Movies: ${libraryTotals.movies} | Shows: ${libraryTotals.shows} | Episodes: ${libraryTotals.episodes} | Total: ${libraryTotals.total}`
      const configLineCount = (typeof run.config_line_count === 'number' && Number.isFinite(run.config_line_count))
        ? run.config_line_count
        : 'n/a'
      const sectionLines = buildSectionDetails(run.section_runtimes, run.run_time_seconds)
      const sectionId = `logscan-section-${index + 1}`
      const sectionSummary = sectionLines.length ? sectionLines[0] : 'n/a'
      const cacheLineCount = (typeof run.cache_line_count === 'number' && Number.isFinite(run.cache_line_count))
        ? run.cache_line_count
        : 'n/a'
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
          <td class="text-center">${escapeHtml(configLineCount)}</td>
          <td class="text-center">${escapeHtml(cacheLineCount)}</td>
          <td><span class="logscan-command" title="${escapeHtml(commandTitle)}">${escapeHtml(command)}</span></td>
          <td title="${escapeHtml(countsTitle)}">
            <div>${escapeHtml(counts)}</div>
            <div class="text-muted small">${escapeHtml(libraryCounts)}</div>
          </td>
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
        buckets[key] = { warning: 0, error: 0, trace: 0, count: 0 }
      }
      buckets[key].warning += getCount(run, 'warning_count')
      buckets[key].error += getCount(run, 'error_count')
      buckets[key].trace += getCount(run, 'trace_count')
      buckets[key].count += 1
    })
    const days = Object.keys(buckets).sort().slice(-14)
    if (!days.length) {
      $counts.text('No W/E/T averages yet.')
      return
    }
    const totals = days.map(day => {
      const bucket = buckets[day]
      if (!bucket || !bucket.count) return 0
      return (bucket.warning + bucket.error + bucket.trace) / bucket.count
    })
    const maxTotal = Math.max(...totals, 1)
    const rows = days.map((day, index) => {
      const data = buckets[day]
      const total = totals[index]
      const avgWarning = data.count ? data.warning / data.count : 0
      const avgError = data.count ? data.error / data.count : 0
      const avgTrace = data.count ? data.trace / data.count : 0
      const barWidth = maxTotal ? Math.round((total / maxTotal) * 100) : 0
      const warningPct = total ? Math.round((avgWarning / total) * 100) : 0
      const errorPct = total ? Math.round((avgError / total) * 100) : 0
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
          <div class="logscan-stack-count">W:${formatAverage(avgWarning)} E:${formatAverage(avgError)} T:${formatAverage(avgTrace)}</div>
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
    const linesHtml = lines.map(line => `<div>${escapeHtml(line)}</div>`).join('')
    $ingest.html(`<div class="logscan-kpi-grid">${tiles.join('')}</div><div class="small text-muted mt-2">${linesHtml}</div>`)
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
        return getRunCommandValue(run)
      case 'counts':
        return getCountsTotal(run)
      case 'config_line_count':
        return typeof run.config_line_count === 'number' ? run.config_line_count : 0
      case 'cache_line_count':
        return typeof run.cache_line_count === 'number' ? run.cache_line_count : 0
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
      const cleaned = command.replace(/\s+/g, ' ').trim()
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

  function updateDateRangeInputs (runs, state) {
    if (!$dateStart.length || !$dateEnd.length) return false
    const dates = runs.map(run => getRunDateKey(run)).filter(Boolean).sort()
    if (!dates.length) {
      const hadValue = $dateStart.val() || $dateEnd.val()
      $dateStart.val('')
      $dateEnd.val('')
      $dateStart.prop('disabled', true)
      $dateEnd.prop('disabled', true)
      return Boolean(hadValue)
    }
    const minDate = dates[0]
    const maxDate = dates[dates.length - 1]
    $dateStart.prop('disabled', false)
    $dateEnd.prop('disabled', false)
    $dateStart.attr('min', minDate)
    $dateStart.attr('max', maxDate)
    $dateEnd.attr('min', minDate)
    $dateEnd.attr('max', maxDate)
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

  function updateRunCountDisplay (filtered) {
    if (!$runCount.length) return
    const loaded = allRuns.length
    const total = Number.isFinite(allRunsTotal) && allRunsTotal > 0 ? allRunsTotal : loaded
    const filteredCount = filtered.length
    let text = `Runs shown: ${filteredCount}`
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
      command: $commandFilter.val() || '',
      library: $libraryFilter.val() || '',
      start: $dateStart.val() || '',
      end: $dateEnd.val() || ''
    }
  }

  function filterRuns (runs, state) {
    return runs.filter(run => {
      if (state.config && normalizeConfigName(run.config_name) !== state.config) return false
      if (state.command && getRunCommandValue(run) !== state.command) return false
      if (state.start || state.end) {
        const dateKey = getRunDateKey(run)
        if (!isDateWithinRange(dateKey, state.start, state.end)) return false
      }
      return true
    })
  }

  function updateFilterOptions (state) {
    let changed = false
    changed = updateConfigFilter(filterRuns(allRuns, { ...state, config: '' })) || changed
    changed = updateCommandFilter(filterRuns(allRuns, { ...state, command: '' })) || changed
    changed = updateDateRangeInputs(filterRuns(allRuns, { ...state, start: '', end: '' }), state) || changed
    changed = updateLibraryFilter(filterRuns(allRuns, { ...state, library: '' })) || changed
    return changed
  }

  function applyFiltersAndRender () {
    let state = getFilterState()
    for (let i = 0; i < 2; i += 1) {
      const changed = updateFilterOptions(state)
      if (!changed) break
      state = getFilterState()
    }
    const filtered = filterRuns(allRuns, state)
    currentFilteredRuns = filtered
    updateRunCountDisplay(filtered)
    renderSummary(filtered)
    renderDaily(filtered)
    renderRuntimeDistribution(filtered)
    renderCountsMix(filtered)
    renderIssueTrends(filtered)
    updateLibraryFilter(filtered)
    renderLibraryInventory(filtered)
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
    $limit.prop('disabled', disabled)
    $configFilter.prop('disabled', disabled)
    $commandFilter.prop('disabled', disabled)
    $dateStart.prop('disabled', disabled)
    $dateEnd.prop('disabled', disabled)
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
    const rawLimit = String($limit.val() || '25').toLowerCase()
    const parsed = parseInt(rawLimit, 10)
    const safeLimit = Number.isFinite(parsed) ? parsed : 25
    if (!suppressStatus) updateStatus('Loading trends...')
    fetch(`/logscan/trends?limit=${safeLimit}`)
      .then(res => res.json())
      .then(data => {
        allRuns = Array.isArray(data.runs) ? data.runs : []
        allRunsTotal = Number.isFinite(data.total_runs) ? data.total_runs : allRuns.length
        if (data && data.ingest_health && (!lastIngestState || lastIngestState.status !== 'running')) {
          lastIngestState = data.ingest_health
        }
        updateConfigFilter(allRuns)
        updateCommandFilter(allRuns)
        updateDateRangeInputs(allRuns, getFilterState())
        loadPreferences()
          .then(() => {
            applyFiltersAndRender()
            if (!suppressStatus) {
              updateStatus(`Last updated: ${formatTimestamp(new Date().toISOString())}`)
            }
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
        $counts.text('Unable to load W/E/T averages.')
        $issues.text('Unable to load issue trends.')
        $libraries.text('Unable to load library totals.')
        $tableBody.html('<tr><td colspan="10" class="text-muted">Unable to load runs.</td></tr>')
      })
  }

  $limit.on('change', fetchRuns)
  $configFilter.on('change', function () {
    loadPreferences().then(() => applyFiltersAndRender())
  })
  $commandFilter.on('change', function () {
    applyFiltersAndRender()
  })
  $dateStart.on('change', function () {
    applyFiltersAndRender()
  })
  $dateEnd.on('change', function () {
    applyFiltersAndRender()
  })
  $libraryFilter.on('change', function () {
    renderLibraryInventory(currentFilteredRuns)
  })
  $resetFilters.on('click', function () {
    $limit.val('500')
    $configFilter.val('')
    $commandFilter.val('')
    $libraryFilter.val('')
    $dateStart.val('')
    $dateEnd.val('')
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
