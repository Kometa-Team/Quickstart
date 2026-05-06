/* global $, bootstrap, showToast, showNavigationLoadingOverlay, hideNavigationLoadingOverlay */

// Global flag so other handlers know an update is in progress
let KOMETA_UPDATING = false
let KOMETA_VALIDATED = false
let KOMETA_VALIDATION_IN_PROGRESS = false
let KOMETA_UPDATE_AVAILABLE = false
let KOMETA_UPDATE_CHECK_SKIPPED = false
let KOMETA_UPDATE_CHECK_COMPLETED = false
let KOMETA_INSTALLED = false
let KOMETA_LOCAL_CHECK_COMPLETED = false
// Polling handles (hoist to top so all handlers see them safely)
let kometaInterval = null
let kometaStatusInterval = null
let kometaProgressInterval = null
let kometaPollingStarted = false
let autoScrollEnabled = true
let tailSize = '2000'
let KOMETA_STATUS = null
let KOMETA_PENDING_START = false
let logPollingPaused = false
let logFilter = ''
let lastLogText = ''
let lastLogStatsTotal = null
let logStatsPollCounter = 0
let lastLogscanPayload = null
let logscanPollCounter = 0
let finalLogscanAnalyzeTriggered = false
let lastRunProgressPayload = null
let logscanAnalyzeInFlight = false
let runProgressInFlight = false
let activeRunCommandOverride = null
let activeRunCommandMode = null
let latestKometaStatusPayload = null
const KOMETA_BRANCH_OVERRIDE_STORAGE_KEY = 'qs-kometa-branch-override'
let kometaUpdatePollInterval = null
let kometaUpdateJobId = null
let kometaUpdateLogIndex = 0

const _qsEnvEl = document.getElementById('qs-env')
const runningOn = (_qsEnvEl && _qsEnvEl.dataset.runningOn) ? _qsEnvEl.dataset.runningOn : ''
const isWindows = typeof runningOn === 'string' && runningOn.includes('Windows')
// const isFrozen = typeof runningOn === 'string' && runningOn.startsWith('Frozen')
// const isDocker = runningOn === 'Docker'

// function toDisplayPath (p) { return isWindows ? String(p).replace(/\//g, '\\') : String(p) }
// function toPosix (p) { return String(p).replace(/\\/g, '/') }
function quoteIfNeeded (s) { return /\s/.test(s) ? `"${s}"` : s }

function formatElapsed (ms) {
  const sec = Math.floor(ms / 1000)
  const mm = String(Math.floor(sec / 60)).padStart(2, '0')
  const ss = String(sec % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

$(document).ready(function () {
  const $runLog = $('#run-output-log')
  const $tailNotice = $('#run-output-notice')
  const $tailSelect = $('#run-log-tail')
  const $autoScrollToggle = $('#run-log-autoscroll')
  const $downloadLogBtn = $('#download-log-btn')
  const $pauseLogBtn = $('#pause-log-btn')
  const $filterInput = $('#run-log-filter')
  const $clearFilterBtn = $('#clear-log-filter')
  const $levelButtons = $('.log-level-btn')
  const $logStats = $('#run-log-stats')
  const $logStatsFiltered = $('#run-log-stats-filtered')
  const $logscanPanel = $('#logscan-panel')
  const $logscanRecommendations = $('#logscan-recommendations')
  const $logscanSummary = $('#logscan-summary')
  const $logscanMissing = $('#logscan-missing-people')
  const $logscanSections = $('#logscan-sections')
  const $updateKometaBtn = $('#update-kometa-btn')
  const $forceUpdateToggle = $('#force-kometa-update')
  const $kometaBranchOverride = $('#kometa-branch-override')
  const $kometaBranchSelection = $('#kometa-branch-selection')
  const $kometaEffectiveBranch = $('#kometa-effective-branch')
  const $kometaUpdatePhaseBadge = $('#kometa-update-phase-badge')
  const $kometaLocalVersionStatus = $('#kometa-local-version-status')
  const $kometaRemoteVersionStatus = $('#kometa-remote-version-status')
  const $kometaVersionSourceUrl = $('#kometa-version-source-url')
  const $kometaZipSourceUrl = $('#kometa-zip-source-url')
  const $kometaMaintenancePageBadge = $('#kometa-maintenance-page-badge')
  const $runStatusRow = $('#run-status-row')
  const $runStatusTimer = $('#run-status-timer')
  const $runStatusMetrics = $('#run-status-metrics')
  const $runStatusLog = $('#run-status-log')
  const $runStatusSparklines = $('#run-status-sparklines')
  const $runSparkCpuSystem = $('#run-spark-cpu-system')
  const $runSparkCpuKometa = $('#run-spark-cpu-kometa')
  const $runSparkMemSystem = $('#run-spark-mem-system')
  const $runSparkMemKometa = $('#run-spark-mem-kometa')
  const $yamlOutput = $('#final-yaml')
  const $yamlLineCount = $('#yaml-line-count')
  let showYAML = false
  const stopModalEl = document.getElementById('stop-kometa-modal')
  const stopModal = (stopModalEl && typeof bootstrap !== 'undefined') ? new bootstrap.Modal(stopModalEl) : null
  const $confirmStopBtn = $('#confirm-stop-kometa')
  const headerSelect = document.getElementById('header-style')
  const headerGrid = document.getElementById('header-style-grid')
  const headerGridCollapse = document.getElementById('header-style-grid-collapse')
  const headerStyleWait = document.getElementById('header-style-wait')
  const finalContentWrapper = document.getElementById('final-content-wrapper')
  const headerGridStatus = document.getElementById('header-style-grid-status')
  const headerGridProgress = document.getElementById('header-style-grid-progress')
  const headerGridProgressBar = headerGridProgress ? headerGridProgress.querySelector('.progress-bar') : null
  const headerStyleLabel = document.getElementById('header-style-label')
  const kometaActionsHeading = document.getElementById('kometa-actions-heading')
  const kometaActionsCollapse = document.getElementById('kometa-actions-collapse')
  const kometaActionsToggle = document.getElementById('kometa-actions-toggle')
  const kometaBranchOverrideWarning = document.getElementById('kometa-branch-override-warning')
  const runCommandCollapse = document.getElementById('run-command-output-collapse')
  let headerStyleSubmitting = false
  let kometaLocalVersionStatus = 'Unknown'
  let kometaRemoteVersionStatus = ''
  let kometaRemoteVersionChecked = false
  let kometaRemoteVersionSkipped = false
  let kometaUpdatePhaseStatus = 'idle'

  function syncKometaMaintenancePageBadge (data) {
    if (!$kometaMaintenancePageBadge.length) return
    const paused = Boolean(data && data.maintenance_paused)
    const pending = Boolean(data && data.pending_start)
    const active = Boolean(data && data.maintenance_active)
    const windowLabel = data && data.maintenance_window ? ` (${data.maintenance_window})` : ''
    let label = ''

    if (paused) {
      label = `Paused for Plex maintenance${windowLabel}`
    } else if (pending) {
      label = `Queued for Plex maintenance${windowLabel}`
    } else if (active) {
      label = `Plex maintenance active${windowLabel}`
    }

    if (label) {
      $kometaMaintenancePageBadge.removeClass('d-none')
      const textEl = $kometaMaintenancePageBadge.find('span').last()
      if (textEl.length) textEl.text(label)
    } else {
      $kometaMaintenancePageBadge.addClass('d-none')
    }
  }

  document.addEventListener('qs:maintenance-status', function (event) {
    syncKometaMaintenancePageBadge(event.detail || null)
  })

  function readMetaFlag (id, datasetKey, attrKey) {
    const el = document.getElementById(id)
    if (!el) return false
    const raw = (el.dataset && el.dataset[datasetKey]) || el.getAttribute(`data-${attrKey}`) || ''
    return String(raw).toLowerCase() === 'true'
  }

  function setMetaFlag (id, datasetKey, attrKey, value) {
    const el = document.getElementById(id)
    if (!el) return
    const serialized = value ? 'True' : 'False'
    if (el.dataset) el.dataset[datasetKey] = serialized
    el.setAttribute(`data-${attrKey}`, serialized)
  }

  function setHeaderRollupBadge (id, state, label) {
    const badge = document.getElementById(id)
    if (!badge) return
    badge.textContent = label
    badge.classList.remove(
      'qs-validation-rollup-badge--unknown',
      'qs-validation-rollup-badge--ok',
      'qs-validation-rollup-badge--warn',
      'qs-validation-rollup-badge--error'
    )
    const normalized = ['unknown', 'ok', 'warn', 'error'].includes(state) ? state : 'unknown'
    badge.classList.add(`qs-validation-rollup-badge--${normalized}`)
  }

  function prettifyFlag (value) {
    const raw = String(value || '').trim()
    if (!raw) return 'Default'
    const noPrefix = raw.replace(/^--/, '')
    return noPrefix.replace(/-/g, ' ')
  }

  function updateSectionStyleHeaderBadge (value) {
    const label = formatHeaderStyleLabel(value)
    setHeaderRollupBadge('header-style-rollup-badge', 'ok', label || 'Active')
  }

  function updateConfigOutputHeaderBadges () {
    const yamlText = $yamlOutput.length ? String($yamlOutput.val() || '') : ''
    const lineCount = computeYamlLineCount(yamlText)
    setHeaderRollupBadge('config-output-lines-badge', lineCount > 0 ? 'ok' : 'unknown', `${lineCount} lines`)
    if (!yamlText.trim()) {
      setHeaderRollupBadge('config-output-rollup-badge', 'unknown', 'No YAML')
      return
    }
    setHeaderRollupBadge('config-output-rollup-badge', showYAML ? 'ok' : 'error', showYAML ? 'Validated' : 'Needs fixes')
  }

  function updateModeHeaderBadge () {
    const showCli = $('#show-cli-toggle').is(':checked')
    setHeaderRollupBadge('heading-mode-rollup-badge', showCli ? 'ok' : 'unknown', showCli ? 'CLI labels' : 'Friendly')
  }

  function updateRunOptionHeaderBadge () {
    const mainOption = $('input[name="run-option"]:checked').val() || ''
    const selectedLibs = $('#library-multiselect').length ? ($('#library-multiselect').val() || []) : []
    if (mainOption === '--run-libraries') {
      if (!selectedLibs.length) {
        setHeaderRollupBadge('heading-runopt-rollup-badge', 'warn', 'Libraries needed')
      } else {
        setHeaderRollupBadge('heading-runopt-rollup-badge', 'ok', `${selectedLibs.length} libraries`)
      }
      return
    }
    if (mainOption === '--times') {
      const timesInput = $('#times-input').val().trim()
      if (!timesInput) {
        setHeaderRollupBadge('heading-runopt-rollup-badge', 'warn', 'Times needed')
        return
      }
      setHeaderRollupBadge('heading-runopt-rollup-badge', isValidTimesFormat(timesInput) ? 'ok' : 'error', isValidTimesFormat(timesInput) ? 'Times set' : 'Invalid times')
      return
    }
    if (mainOption === '--run') {
      setHeaderRollupBadge('heading-runopt-rollup-badge', 'ok', 'Run now')
      return
    }
    setHeaderRollupBadge('heading-runopt-rollup-badge', 'unknown', 'Scheduled')
  }

  function updateModeFlagsHeaderBadge () {
    const modeFlag = $('input[name="mode-flag"]:checked').val() || ''
    setHeaderRollupBadge('heading-modeflags-rollup-badge', modeFlag ? 'ok' : 'unknown', prettifyFlag(modeFlag))
  }

  function updateLogFlagsHeaderBadge () {
    const logFlag = $('input[name="log-flag"]:checked').val() || ''
    setHeaderRollupBadge('heading-logflags-rollup-badge', logFlag ? 'ok' : 'unknown', prettifyFlag(logFlag))
  }

  function updateOtherFlagsHeaderBadge () {
    const coreCount = [
      'delete-collections', 'delete-labels', 'read-only-config', 'low-priority',
      'no-report', 'no-missing', 'no-countdown', 'ignore-ghost',
      'ignore-schedules', 'no-verify-ssl', 'tests'
    ].filter(opt => $(`#opt-${opt}`).is(':checked')).length
    const extrasCount = ($('#opt-timeout').is(':checked') ? 1 : 0) +
      ($('#opt-divider').is(':checked') ? 1 : 0) +
      ($('#opt-width').is(':checked') ? 1 : 0)
    const total = coreCount + extrasCount
    if (!total) {
      setHeaderRollupBadge('heading-otherflags-rollup-badge', 'unknown', 'Default')
      return
    }
    setHeaderRollupBadge('heading-otherflags-rollup-badge', 'ok', `${total} enabled`)
  }

  function updateRunCommandHeaderBadge () {
    if (!showYAML) {
      setHeaderRollupBadge('run-command-rollup-badge', 'error', 'Fix validation')
      return
    }
    if (KOMETA_VALIDATION_IN_PROGRESS) {
      setHeaderRollupBadge('run-command-rollup-badge', 'unknown', 'Checking Kometa')
      return
    }
    if (KOMETA_UPDATING) {
      setHeaderRollupBadge('run-command-rollup-badge', 'unknown', 'Updating Kometa')
      return
    }
    if (!KOMETA_VALIDATED) {
      setHeaderRollupBadge('run-command-rollup-badge', 'warn', 'Validate Kometa')
      return
    }
    if (KOMETA_STATUS === 'running') {
      setHeaderRollupBadge('run-command-rollup-badge', 'warn', 'Run in progress')
      return
    }
    setHeaderRollupBadge('run-command-rollup-badge', isRunCommandValid() ? 'ok' : 'warn', isRunCommandValid() ? 'Ready' : 'Incomplete')
  }

  function updateLogscanHeaderBadge (data) {
    const source = data || lastLogscanPayload
    if (!source) {
      setHeaderRollupBadge('logscan-rollup-badge', 'unknown', 'Pending')
      return
    }
    if (source.error) {
      setHeaderRollupBadge('logscan-rollup-badge', 'error', 'Unavailable')
      return
    }
    const recCount = Array.isArray(source.recommendations) ? source.recommendations.length : 0
    const missingCount = Array.isArray(source.missing_people) ? source.missing_people.length : 0
    const issueCount = recCount + missingCount
    if (!issueCount) {
      setHeaderRollupBadge('logscan-rollup-badge', 'ok', 'No issues')
      return
    }
    setHeaderRollupBadge('logscan-rollup-badge', 'warn', `${issueCount} items`)
  }

  function syncFinalAccordionRollups () {
    updateModeHeaderBadge()
    updateRunOptionHeaderBadge()
    updateModeFlagsHeaderBadge()
    updateLogFlagsHeaderBadge()
    updateOtherFlagsHeaderBadge()
    updateConfigOutputHeaderBadges()
    updateRunCommandHeaderBadge()
    updateLogscanHeaderBadge()
    syncKometaBranchRollupBadge()
  }

  function getFinalGateState () {
    const el = document.getElementById('final-gate-state')
    if (!el) {
      return {
        stage: 'config',
        autoValidate: false,
        configValid: false
      }
    }
    return {
      stage: String(el.dataset.stage || 'config'),
      todoCount: Number(el.dataset.todoCount || 0),
      autoValidate: el.dataset.autoValidate === 'true',
      configValid: el.dataset.configValid === 'true',
      bulkFresh: el.dataset.bulkFresh === 'true'
    }
  }

  function updateValidationGate () {
    const finalGate = getFinalGateState()
    if (finalGate.stage === 'todo' || finalGate.stage === 'freshness') {
      showYAML = false
      $('#validation-messages').hide()
      $('#no-validation-warning, #yaml-warnings, #yaml-warning-msg, #validation-error').addClass('d-none')
      $('#download-btn, #download-redacted-btn').addClass('d-none')
      $('#run-controls-container').addClass('d-none')
      $('#run-now').prop('disabled', true)
      $('#run-now-label').text('Run Now')
      updateRunNowState()
      syncFinalAccordionRollups()
      return
    }

    const plexValid = readMetaFlag('plex_valid', 'plexValid', 'plex-valid')
    const tmdbValid = readMetaFlag('tmdb_valid', 'tmdbValid', 'tmdb-valid')
    const libsValid = readMetaFlag('libs_valid', 'libsValid', 'libs-valid')
    const settValid = readMetaFlag('sett_valid', 'settValid', 'sett-valid')
    const yamlValid = readMetaFlag('yaml_valid', 'yamlValid', 'yaml-valid')

    showYAML = finalGate.configValid || (plexValid && tmdbValid && libsValid && settValid && yamlValid)

    const validationMessages = []
    const rowFor = (label, href) => {
      return `
        <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
          <span>${label}</span>
          <a href="${href}" class="ms-2 text-decoration-none">
            Open page
            <i class="bi bi-box-arrow-up-right"></i>
          </a>
        </div>
      `
    }
    if (!plexValid) validationMessages.push(rowFor('Plex settings have not been validated successfully.', '/step/010-plex'))
    if (!tmdbValid) validationMessages.push(rowFor('TMDb settings have not been validated successfully.', '/step/020-tmdb'))
    if (!libsValid) validationMessages.push(rowFor('Libraries page settings have not been validated successfully.', '/step/025-libraries'))
    if (!settValid) validationMessages.push(rowFor('Settings page values have likely been skipped.', '/step/150-settings'))

    $('#run-now').prop('disabled', true)
    $('#run-now-label').text('Run Now')

    if (!showYAML) {
      if (validationMessages.length) {
        $('#validation-messages').html(validationMessages.join('<br>')).show()
      } else {
        $('#validation-messages').hide()
      }
      $('#no-validation-warning, #yaml-warnings, #yaml-warning-msg, #validation-error').removeClass('d-none')
      $('#download-btn, #download-redacted-btn').addClass('d-none')
      $('#run-controls-container').addClass('d-none') // Hide run section
    } else {
      $('#validation-messages').hide()
      $('#no-validation-warning, #yaml-warnings, #yaml-warning-msg, #validation-error').addClass('d-none')
      $('#yaml-content, #final-yaml, #download-btn, #download-redacted-btn').removeClass('d-none')
      $('#run-controls-container').removeClass('d-none') // Show run section
      $('#run-now').prop('disabled', true)
      $('#run-now-label').text('Run Now')
    }

    updateRunNowState()
    syncFinalAccordionRollups()
  }

  updateValidationGate()

  tailSize = $tailSelect.val() || tailSize
  updateTailNotice()
  $tailSelect.on('change', function () {
    tailSize = $(this).val() || tailSize
    updateTailNotice()
    fetchKometaLog()
  })

  function computeYamlLineCount (text) {
    if (!text) return 0
    const normalized = String(text).replace(/\r\n/g, '\n')
    let count = normalized.split('\n').length
    if (normalized.endsWith('\n')) count -= 1
    return Math.max(0, count)
  }

  function updateYamlLineCount () {
    if (!$yamlLineCount.length || !$yamlOutput.length) return
    const lineCount = computeYamlLineCount($yamlOutput.val())
    $yamlLineCount.text(`Line count (includes comments and blank lines): ${lineCount}`)
    updateConfigOutputHeaderBadges()
  }

  updateYamlLineCount()
  $yamlOutput.on('input', updateYamlLineCount)

  function normalizeFontName (value) {
    return String(value || '').trim().replace(/_/g, ' ')
  }

  function formatHeaderStyleLabel (value) {
    const text = normalizeFontName(value)
    if (!text) return 'Single line'
    return text.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase())
  }

  function updateHeaderStyleLabel (value) {
    if (!headerStyleLabel) return
    headerStyleLabel.textContent = formatHeaderStyleLabel(value)
    updateSectionStyleHeaderBadge(value)
  }

  function setActiveGridCard (fontName) {
    if (!headerGrid) return
    const activeFont = normalizeFontName(fontName)
    headerGrid.querySelectorAll('.header-style-card').forEach(card => {
      card.classList.toggle('active', card.dataset.font === activeFont)
    })
  }

  function updateGridStatus (message) {
    if (headerGridStatus) headerGridStatus.textContent = message || ''
  }

  function updateGridProgress (loaded, total) {
    if (!headerGridProgress || !headerGridProgressBar) return
    if (!total) {
      headerGridProgress.classList.add('d-none')
      headerGridProgressBar.style.width = '0%'
      return
    }
    const pct = Math.min(100, Math.round((loaded / total) * 100))
    headerGridProgress.classList.remove('d-none')
    headerGridProgressBar.style.width = `${pct}%`
  }

  async function loadHeaderGridSamples () {
    if (!headerGrid) return
    const fonts = JSON.parse(headerGrid.dataset.fonts || '[]')
    if (!fonts.length) {
      headerGrid.replaceChildren()
      const empty = document.createElement('div')
      empty.className = 'text-muted small'
      empty.textContent = 'No fonts available.'
      headerGrid.appendChild(empty)
      updateGridStatus('')
      updateGridProgress(0, 0)
      return
    }

    updateGridStatus(`Loading ${fonts.length} font previews...`)
    updateGridProgress(0, fonts.length)

    headerGrid.replaceChildren()
    fonts.forEach(font => {
      const card = document.createElement('button')
      card.type = 'button'
      card.className = 'header-style-card'
      card.dataset.font = font
      const title = document.createElement('div')
      title.className = 'header-style-card-title'
      title.textContent = font.replace(/_/g, ' ')
      const preview = document.createElement('pre')
      preview.className = 'header-style-card-preview'
      preview.textContent = 'Loading...'
      card.append(title, preview)
      card.addEventListener('click', () => {
        if (headerSelect) {
          headerSelect.value = font
          headerSelect.dispatchEvent(new Event('change'))
        }
        updateHeaderStyleLabel(font)
        setActiveGridCard(font)
      })
      headerGrid.appendChild(card)
    })

    setActiveGridCard(headerSelect ? headerSelect.value : '')

    const chunkSize = 12
    let loadedCount = 0
    for (let i = 0; i < fonts.length; i += chunkSize) {
      const chunk = fonts.slice(i, i + chunkSize)
      try {
        const res = await fetch('/header-style-previews', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ fonts: chunk })
        })
        const data = await res.json()
        if (!res.ok || !data.success) {
          throw new Error(data.message || 'Preview unavailable.')
        }
        const previews = data.previews || []
        previews.forEach(entry => {
          const card = headerGrid.querySelector(`.header-style-card[data-font="${entry.font}"]`)
          const pre = card ? card.querySelector('.header-style-card-preview') : null
          if (pre) pre.textContent = entry.preview || ''
        })
      } catch (err) {
        chunk.forEach(font => {
          const card = headerGrid.querySelector(`.header-style-card[data-font="${font}"]`)
          const pre = card ? card.querySelector('.header-style-card-preview') : null
          if (pre) pre.textContent = 'Preview unavailable.'
        })
      }
      loadedCount += chunk.length
      updateGridStatus(`Loaded ${Math.min(loadedCount, fonts.length)} of ${fonts.length} previews`)
      updateGridProgress(Math.min(loadedCount, fonts.length), fonts.length)
    }
    updateGridStatus(`Loaded ${fonts.length} previews`)
    updateGridProgress(fonts.length, fonts.length)
    setTimeout(() => updateGridProgress(0, 0), 800)
  }

  if (headerGridCollapse && headerGrid) {
    let gridLoaded = false
    headerGridCollapse.addEventListener('show.bs.collapse', () => {
      if (!gridLoaded) {
        gridLoaded = true
        loadHeaderGridSamples()
      }
    })
  }

  if (headerSelect && headerGrid) {
    headerSelect.addEventListener('change', () => setActiveGridCard(headerSelect.value))
  }
  updateHeaderStyleLabel(headerSelect ? headerSelect.value : '')
  $('#open-kometa-actions-button').on('click', function () {
    if (KOMETA_STATUS === 'running') return
    if (!kometaActionsCollapse || typeof bootstrap === 'undefined' || !bootstrap.Collapse) return
    bootstrap.Collapse.getOrCreateInstance(kometaActionsCollapse, { toggle: false }).show()
  })
  $('#open-kometa-actions-panel-button').on('click', function () {
    if (KOMETA_STATUS === 'running') return
    if (!kometaActionsCollapse || typeof bootstrap === 'undefined' || !bootstrap.Collapse) return
    bootstrap.Collapse.getOrCreateInstance(kometaActionsCollapse, { toggle: false }).show()
  })

  function updateLibraryVisibility (mainOption) {
    const librarySection = $('#library-multiselect').closest('.mb-2')
    if (mainOption === '--run-libraries') {
      librarySection.removeClass('d-none')
    } else {
      librarySection.addClass('d-none')
    }
  }

  const flagsMap = {
    '--run': {
      label: 'Run Immediately',
      description: 'If you want Kometa to run immediately rather than waiting until 5AM, set this flag'
    },
    '--run-libraries': {
      label: 'Run Specific Libraries',
      description: 'Run Kometa only on selected libraries.'
    },
    '--times': {
      label: 'Time to Run',
      description: 'Run at these times. Kometa wakes up at 5:00 AM to process the config file. If you want to change that time, or tell Kometa to wake up at multiple times, use this flag.'
    },
    '--operations-only': {
      label: 'Operations Only',
      description: 'Only perform operations (e.g., rating/poster updates).'
    },
    '--metadata-only': {
      label: 'Metadata Only',
      description: 'Only run metadata files.'
    },
    '--collections-only': {
      label: 'Collections Only',
      description: 'Only build collections.'
    },
    '--playlists-only': {
      label: 'Playlists Only',
      description: 'Only build playlists, skip everything else.'
    },
    '--overlays-only': {
      label: 'Overlays Only',
      description: 'Only apply overlays to media posters.'
    },
    '--debug': {
      label: 'Debug Logging',
      description: 'Enable debug-level logging.'
    },
    '--trace': {
      label: 'Trace Logging',
      description: 'Enable trace-level (very verbose) logging.'
    },
    '--log-requests': {
      label: 'Log Requests Logging',
      description: 'Most verbose logging. If you enable this, every external network request made by Kometa will be logged, along with the data that is returned. This will add a lot of data to the logs, and will probably contain things like tokens, since the auto-redaction of such things is not generalized enough to catch any token that may be in any URL.<br><strong>WARNING</strong>:<br><code>This can potentially have personal information in it.</code>'
    },
    '--delete-collections': {
      label: 'Delete Collections',
      description: 'Delete all collections in each library as the first step in the run.<br><strong>WARNING</strong>:<br><code>You will lose all collections in the library - this will delete all collections, including ones not created or maintained by Kometa.</code>'
    },
    '--delete-labels': {
      label: 'Delete Labels',
      description: 'Delete all labels [except one, see below] on every item in a Library prior to running collections/operations.<br><strong>WARNING</strong>:<br><code>To preserve functionality of Kometa, this will not remove the Overlay label, which is required for Kometa to know which items have Overlays applied. This will impact any Smart Label Collections that you have in your library. We do not recommend using this on a regular basis if you also use any operations or collections that update labels, as you are effectively deleting and adding labels on each run.</code>'
    },
    '--read-only-config': {
      label: 'Read Only Config',
      description: 'Kometa reads in and then writes out a properly formatted version of your config.yml on each run;this makes the formatting consistent and ensures that you have visibility into new settings that get added. If you want to disable this behavior and tell Kometa to leave your config.yml as-is, use this flag.'
    },
    '--low-priority': {
      label: 'Priority',
      description: 'Run the Kometa process at a lower priority. Will default to normal priority if not specified.'
    },
    '--no-report': {
      label: 'No Report',
      description: 'Kometa can produce a report of missing items, collections, and other information. If you have this report enabled but want to disable it for a specific run, use this flag.'
    },
    '--no-missing': {
      label: 'No Missing',
      description: 'Kometa can take various actions on missing items, such as sending them to Radarr, listing them in the log, or saving a report. If you want to disable all of these actions, use this flag.'
    },
    '--no-countdown': {
      label: 'No Countdown',
      description: 'Typically, when not doing an immediate run, Kometa displays a countdown in the terminal where it is running. If you want to hide this countdown, use this flag.'
    },
    '--ignore-ghost': {
      label: 'Ignore Ghost',
      description: 'Kometa prints some things to the log that do not actually go into the log file on disk. Typically these are things like status messages while loading and/or filtering. If you want to hide all ghost logging for the run, use this flag.'
    },
    '--ignore-schedules': {
      label: 'Ignore Schedules',
      description: 'Ignore all schedules for the run. Range Scheduled collections (such as Christmas movies) will still be ignored.'
    },
    '--no-verify-ssl': {
      label: 'No Verify SSL',
      description: 'Turn SSL Verification off.<br><strong>NOTE</strong>:<br>Set this if your log file shows any errors similar to <code>SSL: CERTIFICATE_VERIFY_FAILED</code>'
    },
    '--tests': {
      label: 'Run Tests',
      description: 'If you set this flag to true, Kometa will run only collections that you have marked as test immediately, like KOMETA_RUN.<br><strong>NOTE</strong>:<br>This will only run collections with <code>test: true</code> in the definition.'
    },
    '--timeout': {
      label: 'Timeout',
      description: 'Change the timeout in seconds for all non-Plex services (such as TMDb, Radarr, and Trakt). This will default to <code>180</code> when not specified and is overwritten by any timeouts mentioned for specific services in the Configuration File.'
    },
    '--divider': {
      label: 'Divider Character',
      description: 'Customize the divider shown between repeated output elements (e.g., <code>></code>) Default is <code>=</code>'
    },
    '--width': {
      label: 'Screen Width',
      description: 'The log is formatted to fit within a certain width. If you wish to change that width, you can do that with this flag. Not that long lines are not wrapped or truncated to this width; this controls the minimum width of the log. Default is <code>100</code>'
    }
  }

  function updateFlagLabels (showCli) {
    const runOptions = ['--run', '--run-libraries', '--times']
    const modeFlags = ['--operations-only', '--metadata-only', '--collections-only', '--overlays-only', '--playlists-only']
    const logFlags = ['--debug', '--trace', '--log-requests']
    const otherFlags = [
      '--delete-collections', '--delete-labels', '--read-only-config', '--low-priority',
      '--no-report', '--no-missing', '--no-countdown', '--ignore-ghost',
      '--ignore-schedules', '--no-verify-ssl', '--tests', '--timeout', '--divider', '--width'
    ]

    function updateLabels (group, prefix = '') {
      group.forEach(flag => {
        const id = `${prefix}${flag.replace(/^--/, '')}`
        const label = $(`label[for="${id}"]`)
        if (label.length) {
          const content = showCli ? flag : (flagsMap[flag]?.label || flag)
          label.html(`${content} <span class="text-info" data-bs-toggle="tooltip" title="${flagsMap[flag]?.description || ''}"><i class="bi bi-info-circle-fill ms-1"></i></span>`)
        }
      })
    }

    updateLabels(runOptions, 'opt-')
    updateLabels(modeFlags, 'opt-')
    updateLabels(logFlags, 'opt-')
    updateLabels(otherFlags, 'opt-')

    $('[data-bs-toggle="tooltip"]').tooltip({ html: true })
    syncFinalAccordionRollups()
  }

  updateFlagLabels(false) // Default to friendly labels
  $('#show-cli-toggle').on('change', function () {
    const showCli = $(this).is(':checked')
    updateFlagLabels(showCli)
  })

  function isRunCommandValid () {
    const cmd = $('#run-command-output').text().trim()
    return Boolean(cmd) && !cmd.startsWith('??')
  }

  function setRunCommandPlaceholderState () {
    const $panel = $('#run-command-panel-message')
    const $panelTitle = $('#run-command-panel-title')
    const $panelText = $('#run-command-panel-text')
    const $panelButton = $('#open-kometa-actions-panel-button')
    const $box = $('#run-command-box')

    if (!$panel.length) return

    let title = 'Run command is not ready yet'
    let message = 'Open Prepare Kometa to install, validate, or update the local Kometa setup before running.'
    let showButton = true

    if (!showYAML) {
      title = 'Fix validation before building the run command'
      message = 'Resolve the current validation issues first. The run command will appear after the config validates cleanly.'
      showButton = false
    } else if (KOMETA_STATUS === 'running') {
      title = 'Kometa is currently running'
      message = 'Run output and stop controls are active below. Prepare Kometa is locked until the current run finishes.'
      showButton = false
    } else if (KOMETA_UPDATING) {
      title = 'Kometa update in progress'
      message = 'Wait for the current install or update to finish. The run command will appear automatically afterward.'
    } else if (KOMETA_VALIDATION_IN_PROGRESS) {
      title = 'Preparing Kometa'
      message = 'Quickstart is validating the Kometa folder and environment now. The run command will appear automatically when ready.'
    } else if (!KOMETA_LOCAL_CHECK_COMPLETED) {
      title = 'Checking Kometa state'
      message = 'Quickstart is probing the local Kometa path. Wait for that check to finish, then prepare Kometa if needed.'
      showButton = false
    } else if (!KOMETA_INSTALLED) {
      title = 'Install Kometa to build the run command'
      message = 'Kometa is not installed in the selected path yet. Open Prepare Kometa to install it first.'
    } else if (!KOMETA_VALIDATED) {
      title = 'Validate Kometa to build the run command'
      message = 'Next step: open Prepare Kometa, let Quickstart validate the Kometa folder and environment, then this command will be generated here.'
    }

    $panelTitle.text(title)
    $panelText.text(message)
    $panelButton.toggleClass('d-none', !showButton)
    $panel.removeClass('d-none')
    $box.addClass('d-none').removeClass('fade-in')
  }

  function clearRunCommandPlaceholderState () {
    $('#run-command-panel-message').addClass('d-none')
    $('#run-command-placeholder').addClass('d-none')
    $('#open-kometa-actions-button').addClass('d-none')
    $('#run-command-box').removeClass('d-none')
    $('#run-command-box .form-label').removeClass('d-none')
    $('#run-command-box pre').removeClass('d-none')
    $('#copy-command').removeClass('d-none')
  }

  function getRunCommandModeLabel (mode) {
    const normalized = String(mode || 'current').trim().toLowerCase()
    if (normalized === 'recovery') return 'Recovery Command'
    if (normalized === 'logged') return 'Last Logged Command'
    return 'Command'
  }

  function getRunCommandModeBadgeLabel (mode) {
    const normalized = String(mode || 'current').trim().toLowerCase()
    if (normalized === 'recovery') return 'Recovery Active'
    if (normalized === 'logged') return 'Logged Active'
    return 'Current Active'
  }

  function getRunCommandModeBadgeClass (mode) {
    const normalized = String(mode || 'current').trim().toLowerCase()
    if (normalized === 'recovery') return 'text-bg-warning'
    if (normalized === 'logged') return 'text-bg-secondary'
    return 'text-bg-primary'
  }

  function applyActiveRunCommandState (command, mode) {
    const normalizedMode = String(mode || 'current').trim().toLowerCase() || 'current'
    activeRunCommandOverride = command || null
    activeRunCommandMode = normalizedMode

    if (command) {
      $('#run-command-output').text(command)
    }

    $('#run-command-label').text(getRunCommandModeLabel(normalizedMode))
    $('#run-command-active-badge')
      .removeClass('d-none text-bg-warning text-bg-secondary text-bg-primary')
      .addClass(getRunCommandModeBadgeClass(normalizedMode))
      .text(getRunCommandModeBadgeLabel(normalizedMode))
  }

  function clearActiveRunCommandState () {
    activeRunCommandOverride = null
    activeRunCommandMode = null
    $('#run-command-label').text('Command')
    $('#run-command-active-badge')
      .addClass('d-none')
      .removeClass('text-bg-warning text-bg-secondary text-bg-primary')
      .text('Recovery Active')
  }

  function updateRunNowState () {
    const $runNow = $('#run-now')
    if (!$runNow.length) {
      updateRunCommandHeaderBadge()
      syncIncompleteRunActions()
      return
    }

    if (!showYAML || KOMETA_VALIDATION_IN_PROGRESS || KOMETA_UPDATING || KOMETA_STATUS === 'running' || !KOMETA_VALIDATED) {
      $runNow.prop('disabled', true)
      updateRunCommandHeaderBadge()
      syncIncompleteRunActions()
      return
    }

    if (!isRunCommandValid()) {
      $runNow.prop('disabled', true)
      updateRunCommandHeaderBadge()
      syncIncompleteRunActions()
      return
    }

    $runNow.prop('disabled', false)
    updateRunCommandHeaderBadge()
    syncIncompleteRunActions()
  }

  function buildCommand () {
    const runCmdOutput = $('#run-command-output')
    const configFilename = runCmdOutput.data('config-filename') || ''

    // Always use normalized forward slashes internally
    const pythonBinNorm = (runCmdOutput.data('venv-python') || 'python3').replace(/\\/g, '/')
    const kometaRootNorm = (runCmdOutput.data('kometa-root') || '').replace(/\\/g, '/')

    const fullKometaPy = `${kometaRootNorm}/kometa.py`
    const fullConfigPath = `${kometaRootNorm}/config/${configFilename}`

    // use the global isWindows we computed from backend values
    const finalPythonBin = isWindows ? pythonBinNorm.replace(/\//g, '\\') : pythonBinNorm
    const finalKometaPy = isWindows ? fullKometaPy.replace(/\//g, '\\') : fullKometaPy
    const finalConfigPath = isWindows ? fullConfigPath.replace(/\//g, '\\') : fullConfigPath

    // Quote paths that may contain spaces
    let cli = `${quoteIfNeeded(finalPythonBin)} ${quoteIfNeeded(finalKometaPy)}`

    const mainOption = $('input[name="run-option"]:checked').val() || ''
    const selectedLibs = $('#library-multiselect').length ? ($('#library-multiselect').val() || []) : []

    if (mainOption) cli += ` ${mainOption}`

    if (mainOption === '--times') {
      const timesInput = $('#times-input').val().trim()
      const isValid = isValidTimesFormat(timesInput)
      toggleTimesInputVisibility('--times')
      if (!isValid) {
        $('#times-error').removeClass('d-none')
        runCmdOutput.text('⚠️ Invalid time format. Use pipe-separated 24h times like 06:00|15:00.')
        updateRunNowState()
        syncFinalAccordionRollups()
        return false
      } else {
        $('#times-error').addClass('d-none')
        checkMaintenanceWarning(mainOption)
        cli += ` "${timesInput}"`
      }
    } else {
      toggleTimesInputVisibility(mainOption)
    }

    if (mainOption === '--run-libraries') {
      if (!selectedLibs.length) {
        runCmdOutput.text('⚠️ Please select at least one library when using --run-libraries.')
        updateRunNowState()
        syncFinalAccordionRollups()
        return false
      }
      cli += ` "${selectedLibs.join('|')}"`
    }

    const modeFlag = $('input[name="mode-flag"]:checked').val()
    if (modeFlag) cli += ` ${modeFlag}`

    const logFlag = $('input[name="log-flag"]:checked').val()
    if (logFlag) cli += ` ${logFlag}`

    const checkboxFlags = [
      'delete-collections', 'delete-labels', 'read-only-config', 'low-priority',
      'no-report', 'no-missing', 'no-countdown', 'ignore-ghost',
      'ignore-schedules', 'no-verify-ssl', 'tests'
    ]
    checkboxFlags.forEach(opt => {
      const checkbox = $(`#opt-${opt}`)
      if (checkbox.length && checkbox.is(':checked')) cli += ` --${opt}`
    })

    // Always append --config with platform-adjusted path
    cli += ` --config ${quoteIfNeeded(finalConfigPath)}`

    const timeoutChecked = $('#opt-timeout').is(':checked')
    const timeoutValue = $('#opt-timeout-val').val().trim()
    if (timeoutChecked) {
      const timeoutNum = parseInt(timeoutValue, 10)
      if (!/^\d+$/.test(timeoutValue) || timeoutNum <= 0) {
        $('#timeout-error').removeClass('d-none')
        runCmdOutput.text('⚠️ Invalid timeout. Please enter a positive whole number.')
        updateRunNowState()
        syncFinalAccordionRollups()
        return false
      } else {
        $('#timeout-error').addClass('d-none')
        cli += ` --timeout ${timeoutNum}`
      }
    }

    const widthChecked = $('#opt-width').is(':checked')
    const widthValue = $('#opt-width-val').val().trim()
    if (widthChecked) {
      const widthNum = parseInt(widthValue, 10)
      if (!/^\d+$/.test(widthValue) || widthNum < 90 || widthNum > 300) {
        $('#width-error').removeClass('d-none')
        runCmdOutput.text('⚠️ Width must be a number between 90 and 300.')
        updateRunNowState()
        syncFinalAccordionRollups()
        return false
      } else {
        $('#width-error').addClass('d-none')
        cli += ` --width ${widthNum}`
      }
    }

    if ($('#opt-divider').is(':checked')) {
      const dividerValue = $('#opt-divider-val').val().trim()
      if (!dividerValue || dividerValue.length !== 1) {
        $('#divider-error').removeClass('d-none')
        runCmdOutput.text('⚠️ Divider must be a single character.')
        updateRunNowState()
        syncFinalAccordionRollups()
        return false
      } else {
        $('#divider-error').addClass('d-none')
        cli += ` --divider "${dividerValue}"`
      }
    }

    runCmdOutput.data('built-command', cli)
    if (!activeRunCommandOverride) {
      runCmdOutput.text(cli)
    }
    updateRunNowState()
    syncFinalAccordionRollups()
    return true
  }

  $('input[name="run-option"]').on('change', function () {
    const value = $(this).val()
    updateLibraryVisibility(value)
    checkMaintenanceWarning(value)
    buildCommand()
  })

  $('#times-input').on('input', buildCommand)

  $('#library-multiselect').on('change', buildCommand)
  $('input[name="mode-flag"]').on('change', buildCommand)
  $('input[name="log-flag"]').on('change', buildCommand)

  const checkboxFlags = [
    'delete-collections', 'delete-labels', 'read-only-config', 'low-priority',
    'no-report', 'no-missing', 'no-countdown', 'ignore-ghost',
    'ignore-schedules', 'no-verify-ssl', 'tests'
  ]

  checkboxFlags.forEach(opt => {
    const checkbox = $(`#opt-${opt}`)
    if (checkbox.length) checkbox.on('change', buildCommand)
  })

  function validateKometaRoot (options = {}) {
    if (KOMETA_VALIDATION_IN_PROGRESS) return
    KOMETA_VALIDATION_IN_PROGRESS = true
    setKometaUpdatePhaseBadge('validating')
    if (typeof showNavigationLoadingOverlay === 'function') {
      showNavigationLoadingOverlay('kometa-check')
    }
    syncKometaRollupBadge()
    const $logBox = $('#kometa-validation-log')
    const $spinner = $('#spinner_validate')
    const $runNow = $('#run-now')
    const $out = $('#run-command-output')

    const configName = $out.data('config-filename')
    const defaultRootPosix = ($out.data('kometa-root-default') || '').toString().trim()
    const defaultRootDisplay = ($out.data('kometa-root-default-display') || defaultRootPosix)
    const appendStatus = Boolean(options.appendStatus)

    if (appendStatus) {
      $logBox.append(
        '\n🔄 Re-validating Kometa after update...\n' +
        'This may take a few seconds as we verify the folder structure, Python environment, and Kometa information.\n\n'
      )
    } else {
      $logBox.text(
        '🔄 Please wait while we validate your Kometa installation...\n' +
        'This may take a few seconds as we verify the folder structure, Python environment, and Kometa information.\n\n'
      )
    }
    if ($spinner.length) $spinner.show()
    $runNow.prop('disabled', true)

    $.ajax({
      type: 'POST',
      url: '/validate-kometa-root',
      contentType: 'application/json',
      // ✅ send the *normalized* path to the backend
      data: JSON.stringify({ path: defaultRootPosix, config_name: configName }),
      success: (res) => {
        KOMETA_LOCAL_CHECK_COMPLETED = true
        if (Array.isArray(res.log)) res.log.forEach(line => $logBox.append(`${line}\n`))

        if (res.success) {
          KOMETA_INSTALLED = true
          $logBox.append('✅ Kometa root validated successfully.\n')
          if (res.kometa_version) $logBox.append(`📦 Local Kometa version: ${res.kometa_version}\n`)

          // ✅ Prefer display paths for UI; keep posix for internal if needed
          const kometaRootDisplay = (res.kometa_root_display || res.kometa_root || defaultRootDisplay)
          const venvPythonDisplay = (res.venv_python_display || res.venv_python || 'python3')
          const kometaRootPosix = (res.kometa_root || defaultRootPosix)
          const venvPythonPosix = (res.venv_python || venvPythonDisplay)

          // For command builder (UI shows native separators)
          $out.data('kometa-root', kometaRootDisplay)
          $out.data('venv-python', venvPythonDisplay)

          // Also keep normalized just in case you need it later
          $out.data('kometa-root-posix', kometaRootPosix)
          $out.data('venv-python-posix', venvPythonPosix)

          // Update the “installed/updated in” line if present
          $('#kometa-install-path').text(kometaRootDisplay)

          // Rebuild command and reveal run section only when all validations pass
          const finalGate = getFinalGateState()
          const allValid = showYAML && (finalGate.configValid || (
            $('#plex_valid').data('plex-valid') === 'True' &&
            $('#tmdb_valid').data('tmdb-valid') === 'True' &&
            $('#libs_valid').data('libs-valid') === 'True' &&
            $('#sett_valid').data('sett-valid') === 'True' &&
            $('#yaml_valid').data('yaml-valid') === 'True'
          ))

          $('#run-command-output').text('')
          try { buildCommand() } catch (_) { }

          if (allValid) {
            KOMETA_VALIDATED = true
            showRunCommandSectionAfterValidated()
          } else {
            KOMETA_VALIDATED = false
            hideRunCommandSectionUntilValidated()
            $runNow.prop('disabled', true)
          }
          if (!KOMETA_UPDATING) setKometaUpdatePhaseBadge(KOMETA_VALIDATED ? 'ready' : 'idle')
        } else {
          KOMETA_INSTALLED = false
          KOMETA_VALIDATED = false
          if (!KOMETA_UPDATING) setKometaUpdatePhaseBadge('failed')
          hideRunCommandSectionUntilValidated()
          $runNow.prop('disabled', true)
        }

        if ($spinner.length) $spinner.hide()
        syncUpdateButtonLabel()
        syncKometaRollupBadge()
      },
      error: (xhr) => {
        KOMETA_LOCAL_CHECK_COMPLETED = true
        const msg = xhr?.responseJSON?.error || 'The Kometa root path is invalid or inaccessible. Please try again.'
        $logBox.append(`❌ ${msg}\n`)
        const lowered = String(msg || '').toLowerCase()
        if (lowered.includes('kometa.py not found') || lowered.includes('requirements.txt not found')) {
          KOMETA_INSTALLED = false
        }
        KOMETA_VALIDATED = false
        if (!KOMETA_UPDATING) setKometaUpdatePhaseBadge('failed')
        hideRunCommandSectionUntilValidated()
        $runNow.prop('disabled', true)
        if ($spinner.length) $spinner.hide()
        syncKometaRollupBadge()
      },
      complete: () => {
        KOMETA_VALIDATION_IN_PROGRESS = false
        updateRunNowState()
        syncUpdateButtonLabel()
        syncKometaRollupBadge()
        if (typeof hideNavigationLoadingOverlay === 'function') {
          hideNavigationLoadingOverlay()
        }
      }
    })
  }

  function probeKometaRoot () {
    const $out = $('#run-command-output')
    const defaultRootPosix = ($out.data('kometa-root-default') || '').toString().trim()
    const defaultRootDisplay = ($out.data('kometa-root-default-display') || defaultRootPosix)
    if (!defaultRootPosix) return Promise.resolve(null)

    return $.ajax({
      type: 'POST',
      url: '/probe-kometa-root',
      contentType: 'application/json',
      data: JSON.stringify({ path: defaultRootPosix }),
      success: (res) => {
        KOMETA_LOCAL_CHECK_COMPLETED = true
        KOMETA_INSTALLED = !!res.kometa_installed
        if (Array.isArray(res.log)) res.log.forEach(line => appendKometaStatusLine(line))

        const kometaRootDisplay = (res.kometa_root_display || res.kometa_root || defaultRootDisplay)
        const venvPythonDisplay = (res.venv_python_display || res.venv_python || 'python3')
        const kometaRootPosix = (res.kometa_root || defaultRootPosix)
        const venvPythonPosix = (res.venv_python || venvPythonDisplay)

        $out.data('kometa-root', kometaRootDisplay)
        $out.data('venv-python', venvPythonDisplay)
        $out.data('kometa-root-posix', kometaRootPosix)
        $out.data('venv-python-posix', venvPythonPosix)
        $('#kometa-install-path').text(kometaRootDisplay)
        syncKometaSourceStatus({ localVersion: res.kometa_version || 'Unknown' })

        if (!KOMETA_INSTALLED) {
          KOMETA_VALIDATED = false
          hideRunCommandSectionUntilValidated()
        }

        syncUpdateButtonLabel()
        syncKometaRollupBadge()
      },
      error: (xhr) => {
        KOMETA_LOCAL_CHECK_COMPLETED = true
        KOMETA_INSTALLED = false
        KOMETA_VALIDATED = false
        const msg = xhr?.responseJSON?.error || 'Unable to probe the Kometa path.'
        appendKometaStatusLine(`❌ ${msg}`)
        syncKometaSourceStatus({ localVersion: 'Unknown' })
        hideRunCommandSectionUntilValidated()
        syncUpdateButtonLabel()
        syncKometaRollupBadge()
      }
    })
  }

  function checkKometaUpdate (forceRefresh = false) {
    const $out = $('#run-command-output')
    const defaultRootPosix = ($out.data('kometa-root-default') || '').toString().trim()
    const branchOverride = getKometaBranchOverride()
    if (!defaultRootPosix) return Promise.resolve(null)

    return fetch('/check-kometa-update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: defaultRootPosix, force: forceRefresh, branch_override: branchOverride })
    })
      .then(async res => {
        const data = await res.json()
        if (!res.ok) throw new Error(data.error || 'Failed to check Kometa update status.')
        return data
      })
      .then(data => {
        KOMETA_LOCAL_CHECK_COMPLETED = true
        KOMETA_INSTALLED = !!data.kometa_installed
        KOMETA_UPDATE_CHECK_COMPLETED = !!data.update_check_completed
        KOMETA_UPDATE_CHECK_SKIPPED = !!data.kometa_update_check_skipped
        KOMETA_UPDATE_AVAILABLE = !!data.kometa_update_available
        if (Array.isArray(data.log)) data.log.forEach(line => appendKometaStatusLine(line))
        syncKometaSourceStatus({
          localVersion: data.local_version || kometaLocalVersionStatus,
          remoteVersion: data.remote_version || '',
          checked: Boolean(data.update_check_completed),
          skipped: Boolean(data.kometa_update_check_skipped)
        })

        if (data.local_version && data.remote_version && data.kometa_update_available) {
          $('#kometa-update-box').removeClass('d-none')
          $('#kometa-local-version').text(data.local_version)
          $('#kometa-remote-version').text(data.remote_version)
        } else {
          $('#kometa-update-box').addClass('d-none')
        }

        syncUpdateButtonLabel()
        syncKometaRollupBadge()
        return data
      })
      .catch(err => {
        appendKometaStatusLine(`❌ ${err.message || 'Failed to check Kometa update status.'}`)
        syncKometaSourceStatus({ checked: false, skipped: false, remoteVersion: '' })
        syncUpdateButtonLabel()
        syncKometaRollupBadge()
        throw err
      })
  }

  if ($('#run-command-output').length > 0) {
    const mainOption = $('input[name="run-option"]:checked').val()
    checkMaintenanceWarning(mainOption)
    updateLibraryVisibility(mainOption)
    buildCommand()
  }

  $('[title]').tooltip({ placement: 'top', trigger: 'hover' })

  const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
  tooltipTriggerList.forEach(function (tooltipTriggerEl) {
    // eslint-disable-next-line no-new
    new bootstrap.Tooltip(tooltipTriggerEl, { html: true })
  })

  function copyTextToClipboard (text) {
    if (!text) return Promise.reject(new Error('Empty text'))
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text)
    }
    return new Promise((resolve, reject) => {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'absolute'
      textarea.style.left = '-9999px'
      document.body.appendChild(textarea)
      textarea.select()
      try {
        const success = document.execCommand('copy')
        document.body.removeChild(textarea)
        if (success) resolve()
        else reject(new Error('Copy failed'))
      } catch (err) {
        document.body.removeChild(textarea)
        reject(err)
      }
    })
  }

  function syncKometaUpdateAttention () {
    if (kometaActionsHeading && kometaActionsToggle) {
      const isCollapsed = kometaActionsToggle.classList.contains('collapsed')
      const needsAttention = KOMETA_UPDATE_AVAILABLE && isCollapsed
      kometaActionsHeading.classList.toggle('kometa-update-attention', needsAttention)
      kometaActionsToggle.classList.toggle('kometa-update-attention', needsAttention)
    }
    syncKometaRollupBadge()
  }

  function getKometaBranchOverride () {
    const raw = ($kometaBranchOverride.val() || '').toString().trim().toLowerCase()
    return ['master', 'develop', 'nightly'].includes(raw) ? raw : ''
  }

  function getQuickstartBranch () {
    return ($updateKometaBtn.data('qs-branch') || 'master').toString().trim().toLowerCase()
  }

  function getAutoKometaBranch () {
    return getQuickstartBranch() === 'master' ? 'master' : 'nightly'
  }

  function getEffectiveKometaBranch () {
    return getKometaBranchOverride() || getAutoKometaBranch()
  }

  function getKometaVersionSourceUrlValue (branch) {
    return `https://raw.githubusercontent.com/Kometa-Team/Kometa/${branch}/VERSION`
  }

  function getKometaZipSourceUrlValue (branch) {
    return `https://codeload.github.com/kometa-team/Kometa/zip/refs/heads/${branch}`
  }

  function loadSavedKometaBranchOverride () {
    try {
      const saved = window.localStorage.getItem(KOMETA_BRANCH_OVERRIDE_STORAGE_KEY) || ''
      if (['master', 'develop', 'nightly'].includes(saved)) {
        $kometaBranchOverride.val(saved)
      } else {
        $kometaBranchOverride.val('')
      }
    } catch (_) {
      $kometaBranchOverride.val('')
    }
  }

  function saveKometaBranchOverride () {
    try {
      const value = getKometaBranchOverride()
      if (value) window.localStorage.setItem(KOMETA_BRANCH_OVERRIDE_STORAGE_KEY, value)
      else window.localStorage.removeItem(KOMETA_BRANCH_OVERRIDE_STORAGE_KEY)
    } catch (_) {}
  }

  function syncKometaSourceStatus (options = {}) {
    if (Object.prototype.hasOwnProperty.call(options, 'localVersion')) {
      kometaLocalVersionStatus = options.localVersion || 'Unknown'
    }
    if (Object.prototype.hasOwnProperty.call(options, 'remoteVersion')) {
      kometaRemoteVersionStatus = options.remoteVersion || ''
    }
    if (Object.prototype.hasOwnProperty.call(options, 'checked')) {
      kometaRemoteVersionChecked = Boolean(options.checked)
    }
    if (Object.prototype.hasOwnProperty.call(options, 'skipped')) {
      kometaRemoteVersionSkipped = Boolean(options.skipped)
    }

    const selected = getKometaBranchOverride()
    const effective = getEffectiveKometaBranch()
    const selectionLabel = selected ? `Override (${selected})` : 'Auto'

    $kometaBranchSelection.text(selectionLabel)
    $kometaEffectiveBranch.text(effective)
    $kometaLocalVersionStatus.text(kometaLocalVersionStatus || 'Unknown')

    if (kometaRemoteVersionSkipped) {
      $kometaRemoteVersionStatus.text('Skipped while running')
    } else if (kometaRemoteVersionChecked) {
      $kometaRemoteVersionStatus.text(kometaRemoteVersionStatus || 'Unknown')
    } else {
      $kometaRemoteVersionStatus.text('Not checked')
    }

    $kometaVersionSourceUrl.text(getKometaVersionSourceUrlValue(effective))
    $kometaZipSourceUrl.text(getKometaZipSourceUrlValue(effective))
    syncKometaBranchRollupBadge()
  }

  function setKometaUpdatePhaseBadge (phase) {
    if (!$kometaUpdatePhaseBadge.length) return

    const phaseMap = {
      idle: { label: 'Idle', klass: 'text-bg-secondary' },
      checking: { label: 'Checking', klass: 'text-bg-info' },
      queued: { label: 'Starting', klass: 'text-bg-primary' },
      downloading: { label: 'Downloading', klass: 'text-bg-primary' },
      extracting: { label: 'Extracting', klass: 'text-bg-warning' },
      preserving: { label: 'Preserving data', klass: 'text-bg-warning' },
      venv: { label: 'Preparing venv', klass: 'text-bg-info' },
      dependencies: { label: 'Installing deps', klass: 'text-bg-warning' },
      validating: { label: 'Validating', klass: 'text-bg-info' },
      ready: { label: 'Ready', klass: 'text-bg-success' },
      failed: { label: 'Failed', klass: 'text-bg-danger' }
    }

    const normalized = Object.prototype.hasOwnProperty.call(phaseMap, phase) ? phase : 'idle'
    const next = phaseMap[normalized]
    kometaUpdatePhaseStatus = normalized
    $kometaUpdatePhaseBadge
      .removeClass('text-bg-secondary text-bg-info text-bg-primary text-bg-warning text-bg-success text-bg-danger')
      .addClass(next.klass)
      .text(next.label)
  }

  function inferKometaUpdatePhaseFromLine (line) {
    const text = String(line || '').trim()
    if (!text) return null
    const lower = text.toLowerCase()

    if (
      lower.startsWith('❌') ||
      lower.includes(' update failed') ||
      lower.includes('error occurred during kometa update') ||
      lower.includes('aborting extraction') ||
      lower.includes('failed to fetch kometa update progress')
    ) {
      return 'failed'
    }
    if (
      lower.includes('kometa root validated successfully') ||
      lower.includes('kometa root is valid and ready') ||
      lower.includes('kometa update completed successfully') ||
      lower.includes('kometa is already up to date') ||
      lower.includes('kometa updated via zip')
    ) {
      return 'ready'
    }
    if (
      lower.includes('re-validating kometa after update') ||
      lower.includes('please wait while we validate') ||
      lower.includes('validate your kometa installation')
    ) {
      return 'validating'
    }
    if (lower.includes('installing requirements') || lower.includes('upgrading pip')) {
      return 'dependencies'
    }
    if (
      lower.includes('creating virtual environment') ||
      lower.includes('existing kometa-venv looks invalid') ||
      lower.includes('venv python') ||
      lower.includes('pyvenv.cfg')
    ) {
      return 'venv'
    }
    if (
      lower.includes('backed up kometa logs/cache') ||
      lower.includes('restored kometa logs/cache') ||
      lower.includes('kometa backup')
    ) {
      return 'preserving'
    }
    if (
      (lower.includes('removed ') && lower.includes('existing entr')) ||
      lower.includes('removing existing kometa contents') ||
      lower.includes('existing path still present after cleanup') ||
      lower.includes('extracted version file') ||
      lower.includes('extracted to:')
    ) {
      return 'extracting'
    }
    if (lower.includes('downloading ') && lower.includes('.zip')) {
      return 'downloading'
    }
    if (
      lower.includes('resolving upstream sha') ||
      (lower.includes('upstream ') && lower.includes(' sha')) ||
      lower.includes('refreshing kometa status') ||
      lower.includes('checking kometa') ||
      lower.includes('kometa branch selected') ||
      lower.includes('quickstart branch:') ||
      lower.includes('remote version source') ||
      lower.includes('kometa branch override selected') ||
      lower.includes('kometa branch selection: auto')
    ) {
      return 'checking'
    }

    return null
  }

  function updateKometaUpdatePhaseFromLine (line) {
    const phase = inferKometaUpdatePhaseFromLine(line)
    if (phase) setKometaUpdatePhaseBadge(phase)
  }

  function setKometaStatusLog (lines, phase = null) {
    const $logBox = $('#kometa-validation-log')
    const text = Array.isArray(lines) ? lines.join('\n') : String(lines || '')
    $logBox.text(text ? `${text}\n` : '')
    if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight
    if (phase) setKometaUpdatePhaseBadge(phase)
  }

  function appendKometaStatusLine (line) {
    const $logBox = $('#kometa-validation-log')
    $logBox.append(`${line}\n`)
    if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight
    updateKometaUpdatePhaseFromLine(line)
  }

  function syncKometaBranchOverrideWarning () {
    if (!kometaBranchOverrideWarning) return
    kometaBranchOverrideWarning.classList.toggle('d-none', !getKometaBranchOverride())
  }

  function invalidateKometaUpdateStatus () {
    KOMETA_UPDATE_AVAILABLE = false
    KOMETA_UPDATE_CHECK_COMPLETED = false
    KOMETA_UPDATE_CHECK_SKIPPED = false
    kometaRemoteVersionStatus = ''
    kometaRemoteVersionChecked = false
    kometaRemoteVersionSkipped = false
    $('#kometa-update-box').addClass('d-none')
    syncKometaSourceStatus()
    syncUpdateButtonLabel()
    syncKometaRollupBadge()
  }

  function runKometaStatusPass (forceRefresh = false) {
    const selection = getKometaBranchOverride()
    const effective = getEffectiveKometaBranch()
    const lines = [
      '🔄 Refreshing Kometa status...',
      `ℹ️ Selected Kometa branch mode: ${selection || 'auto'}`,
      `ℹ️ Effective Kometa branch: ${effective}`,
      `🌐 Remote VERSION source: ${getKometaVersionSourceUrlValue(effective)}`,
      `📥 Kometa ZIP source: ${getKometaZipSourceUrlValue(effective)}`,
      '',
      '🔍 Checking Kometa path and local install state...'
    ]
    setKometaStatusLog(lines, 'checking')
    invalidateKometaUpdateStatus()
    return probeKometaRoot()
      .then((res) => {
        if (!res || !res.kometa_installed) {
          appendKometaStatusLine('')
          appendKometaStatusLine('ℹ️ Remote update check skipped because Kometa is not installed.')
          if (!KOMETA_UPDATING) setKometaUpdatePhaseBadge('idle')
          return res
        }
        appendKometaStatusLine('')
        appendKometaStatusLine('🔎 Checking Kometa update status...')
        return checkKometaUpdate(forceRefresh)
      })
      .then((result) => {
        if (!KOMETA_UPDATING) setKometaUpdatePhaseBadge(KOMETA_INSTALLED ? 'ready' : 'idle')
        return result
      })
      .catch(() => {
        if (!KOMETA_UPDATING) setKometaUpdatePhaseBadge('failed')
        return null
      })
  }

  function stopKometaUpdatePolling () {
    if (kometaUpdatePollInterval) {
      clearInterval(kometaUpdatePollInterval)
      kometaUpdatePollInterval = null
    }
  }

  function pollKometaUpdateProgress () {
    if (!kometaUpdateJobId) return Promise.resolve(null)
    return fetch(`/background-jobs/${encodeURIComponent(kometaUpdateJobId)}?since=${encodeURIComponent(String(kometaUpdateLogIndex))}`)
      .then(async res => {
        const data = await res.json()
        if (!res.ok || !data.success || !data.job) throw new Error(data.error || 'Failed to fetch Kometa update progress.')
        return data
      })
      .then(data => {
        const job = data.job || {}
        if (job.phase === 'queued') setKometaUpdatePhaseBadge('queued')
        if (job.phase === 'error') setKometaUpdatePhaseBadge('failed')
        const lines = Array.isArray(data.lines) ? data.lines : []
        lines.forEach(line => appendKometaStatusLine(line))
        if (typeof data.next_index === 'number') kometaUpdateLogIndex = data.next_index
        if (data.done) {
          stopKometaUpdatePolling()
        }
        return Object.assign({}, job, {
          lines,
          next_index: data.next_index,
          done: data.done
        })
      })
  }

  function getKometaRollupStatus () {
    if (KOMETA_UPDATING) return { state: 'unknown', label: 'Updating...' }
    if (KOMETA_VALIDATION_IN_PROGRESS) return { state: 'unknown', label: 'Checking...' }
    if (!KOMETA_LOCAL_CHECK_COMPLETED) return { state: 'unknown', label: 'Not checked' }
    if (!KOMETA_INSTALLED) return { state: 'error', label: 'Install needed' }
    if (!KOMETA_UPDATE_CHECK_COMPLETED) {
      return { state: KOMETA_VALIDATED ? 'ok' : 'warn', label: KOMETA_VALIDATED ? 'Prepared' : 'Prepare needed' }
    }
    if (KOMETA_UPDATE_CHECK_SKIPPED) return { state: 'unknown', label: 'Skipped while running' }
    if (KOMETA_UPDATE_AVAILABLE) return { state: 'warn', label: 'Update available' }
    return { state: 'ok', label: 'Up to date' }
  }

  function syncKometaRollupBadge () {
    const badge = document.getElementById('kometa-update-rollup-badge')
    if (!badge) return
    const { state, label } = getKometaRollupStatus()
    badge.textContent = label
    badge.classList.remove(
      'qs-validation-rollup-badge--unknown',
      'qs-validation-rollup-badge--ok',
      'qs-validation-rollup-badge--warn',
      'qs-validation-rollup-badge--error'
    )
    badge.classList.add(`qs-validation-rollup-badge--${state}`)
  }

  function syncKometaBranchRollupBadge () {
    const badge = document.getElementById('kometa-branch-rollup-badge')
    if (!badge) return

    const selected = getKometaBranchOverride()
    const effective = getEffectiveKometaBranch()
    const label = (selected || 'auto').toUpperCase()

    badge.textContent = label
    badge.classList.remove('text-bg-secondary', 'text-bg-warning', 'text-dark')
    if (selected) {
      badge.classList.add('text-bg-warning', 'text-dark')
      badge.setAttribute('title', `Kometa branch override selected: ${selected}. Effective branch: ${effective}.`)
    } else {
      badge.classList.add('text-bg-secondary')
      badge.setAttribute('title', `Kometa branch mode: auto. Effective branch: ${effective}.`)
    }
  }

  if (kometaActionsCollapse) {
    kometaActionsCollapse.addEventListener('shown.bs.collapse', syncKometaUpdateAttention)
    kometaActionsCollapse.addEventListener('hidden.bs.collapse', syncKometaUpdateAttention)
  }

  function setKometaPrepareRunningState (isRunning) {
    const accordion = document.getElementById('kometa-actions-accordion')
    if (accordion) accordion.classList.toggle('opacity-50', Boolean(isRunning))
    if (!kometaActionsCollapse || !kometaActionsToggle) return
    if (isRunning && kometaActionsCollapse.classList.contains('show') && typeof bootstrap !== 'undefined' && bootstrap.Collapse) {
      bootstrap.Collapse.getOrCreateInstance(kometaActionsCollapse, { toggle: false }).hide()
    }
    if (isRunning) {
      kometaActionsToggle.classList.add('collapsed')
      kometaActionsToggle.setAttribute('aria-expanded', 'false')
      kometaActionsToggle.setAttribute('title', 'Kometa is running. Prepare Kometa is locked until the run finishes.')
      kometaActionsToggle.disabled = true
      kometaActionsToggle.classList.add('disabled')
    } else {
      kometaActionsToggle.removeAttribute('title')
      kometaActionsToggle.disabled = false
      kometaActionsToggle.classList.remove('disabled')
    }
  }

  function showCopyButtonSuccess (iconSelector, textSelector) {
    const $icon = $(iconSelector)
    const $text = $(textSelector)
    $icon.removeClass('bi-files bi-clipboard').addClass('bi-check2')
    $text.text('Copied')
    setTimeout(() => {
      $icon.removeClass('bi-check2').addClass('bi-files')
      $text.text('Copy')
    }, 1500)
  }

  $('#copy-command').on('click', function () {
    const command = $('#run-command-output').text().trim()
    if (!command || command.startsWith('⚠️')) return

    copyTextToClipboard(command)
      .then(() => showCopyButtonSuccess('#copy-icon', '#copy-text'))
      .catch(() => showToast('error', 'Copy failed. Please copy manually.'))
  })

  $('#copy-recovery-command').on('click', function () {
    const command = $('#recovery-command-output').text().trim()
    if (!command) return
    copyTextToClipboard(command)
      .then(() => showCopyButtonSuccess('#copy-recovery-icon', '#copy-recovery-text'))
      .catch(() => showToast('error', 'Copy failed. Please copy manually.'))
  })

  function getCurrentRunCommand () {
    return $('#run-command-output').text().trim()
  }

  function getRecoveryRunCommand () {
    return $('#recovery-command-output').text().trim()
  }

  function syncIncompleteRunActions () {
    const $runRecovery = $('#run-recovery-command')
    if (!$runRecovery.length) return

    const $incompleteAlert = $('#incomplete-run-alert')
    const recoveryCommand = getRecoveryRunCommand()
    const alertVisible = $incompleteAlert.length > 0 && !$incompleteAlert.hasClass('d-none')
    const recoveryRunnable = Boolean(recoveryCommand) &&
      alertVisible &&
      !KOMETA_VALIDATION_IN_PROGRESS &&
      !KOMETA_UPDATING &&
      !KOMETA_PENDING_START &&
      KOMETA_STATUS !== 'running'

    $runRecovery.toggleClass('d-none', !alertVisible)
    $runRecovery.prop('disabled', !recoveryRunnable)
    if (recoveryRunnable) {
      $runRecovery.removeAttr('title')
    } else if (!alertVisible) {
      $runRecovery.attr('title', 'Recovery actions are only available when an incomplete-run recovery command is visible.')
    } else if (KOMETA_VALIDATION_IN_PROGRESS) {
      $runRecovery.attr('title', 'Wait for Kometa validation to finish before starting a recovery run.')
    } else if (KOMETA_UPDATING) {
      $runRecovery.attr('title', 'Wait for the Kometa update to finish before starting a recovery run.')
    } else if (KOMETA_PENDING_START) {
      $runRecovery.attr('title', 'A Kometa start is already queued for the next Plex maintenance window.')
    } else if (KOMETA_STATUS === 'running') {
      $runRecovery.attr('title', 'Kometa is already running.')
    } else {
      $runRecovery.attr('title', 'No recovery command is available for this incomplete run.')
    }
  }

  function startKometaCommand (command, opts = {}) {
    const startMode = opts.startMode || 'current'
    const requireValidated = opts.requireValidated !== false
    const startMessage = opts.startMessage || 'Starting Kometa...\n'

    if (KOMETA_UPDATING) {
      showToast('warning', 'Kometa is updating. Please wait for it to finish before running.')
      return
    }

    if (KOMETA_VALIDATION_IN_PROGRESS) {
      showToast('info', 'Kometa validation is still running. Please wait.')
      return
    }

    if (requireValidated && !KOMETA_VALIDATED) {
      showToast('warning', 'Kometa has not been validated yet.')
      return
    }

    if (!command || command.startsWith('⚠️')) {
      showToast('error', 'Cannot run invalid command.')
      return
    }

    $('#run-now').prop('disabled', true)
    $('#run-now-label').text('Running...')
    $('#run-recovery-command').prop('disabled', true)
    $('#stop-now').removeClass('d-none')
    $('#run-output').removeClass('d-none')
    $('#run-output-log').text(startMessage)

    fetch('/start-kometa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, start_mode: startMode })
    })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          clearActiveRunCommandState()
          try { buildCommand() } catch (_) {}
          $('#run-output-log').text(`❌ ${data.error}`)
          $('#run-now').prop('disabled', false)
          $('#run-now-label').text('Run Now')
          $('#stop-now').addClass('d-none')
          syncIncompleteRunActions()
          return
        }

        if (data.status === 'queued') {
          applyActiveRunCommandState(command, startMode)
          KOMETA_PENDING_START = true
          const windowLabel = data.maintenance_window ? ` (${data.maintenance_window})` : ''
          const nowLabel = (typeof window.QS_formatTimestamp === 'function') ? window.QS_formatTimestamp() : new Date().toLocaleString()
          const message = `Plex maintenance active${windowLabel} at ${nowLabel}. Kometa will start automatically when it ends.`
          showToast('warning', message)
          $('#run-output-log').text(`${message}\n`)
          $('#run-now').prop('disabled', true).html('<i class="bi bi-hourglass-split me-1"></i> Waiting...')
          $('#stop-now').addClass('d-none')
          if (kometaStatusInterval) clearInterval(kometaStatusInterval)
          kometaStatusInterval = setInterval(checkKometaStatus, 5000)
          syncIncompleteRunActions()
          return
        }

        applyActiveRunCommandState(command, startMode)

        setTimeout(() => {
          kometaPollingStarted = false
          startPollingIfNeeded()
        }, 5500)
      })
      .catch(() => {
        clearActiveRunCommandState()
        try { buildCommand() } catch (_) {}
        $('#run-output-log').append('\n⚠️ Failed to start Kometa.')
        $('#run-now').prop('disabled', false)
        $('#run-now-label').text('Run Now')
        $('#stop-now').addClass('d-none')
        syncIncompleteRunActions()
      })
  }

  function hideRunCommandSectionUntilValidated () {
    const accordion = $('#run-command-output-accordion')
    accordion.removeClass('d-none')
    $('#run-command-output-collapse').removeClass('show')
    $('#run-command-output-heading .accordion-button').addClass('collapsed').attr('aria-expanded', 'false')
    setRunCommandPlaceholderState()
    $('#run-now').prop('disabled', true).html('<i class="bi bi-hourglass-split me-1"></i> Waiting...')
  }

  function revealRunCommandSection () {
    const accordion = $('#run-command-output-accordion')
    const box = $('#run-command-box')

    clearRunCommandPlaceholderState()
    accordion.removeClass('d-none')
    $('#run-command-output-collapse').addClass('show')
    $('#run-command-output-heading .accordion-button').removeClass('collapsed').attr('aria-expanded', 'true')
    box.removeClass('d-none') // Reveal element (opacity still 0)
    setTimeout(() => {
      box.addClass('fade-in') // Let browser register change, then fade in
    }, 10)
  }

  function showRunCommandSectionAfterValidated () {
    clearRunCommandPlaceholderState()
    revealRunCommandSection()
    $('#run-now').html('<i class="bi bi-play-fill me-1"></i> Run Now')
    try { buildCommand() } catch (_) {}
    updateRunNowState()
  }
  function startPollingIfNeeded () {
    if (kometaPollingStarted) return
    kometaPollingStarted = true
    if (kometaInterval) clearInterval(kometaInterval)
    if (kometaStatusInterval) clearInterval(kometaStatusInterval)
    if (kometaProgressInterval) clearInterval(kometaProgressInterval)
    fetchKometaLog()
    fetchRunProgress()
    kometaInterval = setInterval(fetchKometaLog, 3000)
    kometaStatusInterval = setInterval(checkKometaStatus, 5000)
    kometaProgressInterval = setInterval(fetchRunProgress, 5000)
  }

  function stopProgressPolling () {
    if (kometaProgressInterval) {
      clearInterval(kometaProgressInterval)
      kometaProgressInterval = null
    }
  }

  const runPhaseOrder = [
    { key: 'operations', label: 'Operations' },
    { key: 'metadata', label: 'Metadata' },
    { key: 'collections', label: 'Collections' },
    { key: 'overlays', label: 'Overlays' },
    { key: 'playlists', label: 'Playlists' }
  ]

  function renderRunProgress (payload) {
    const container = document.getElementById('run-progress')
    if (!container) return

    if (!payload || !Array.isArray(payload.libraries)) {
      container.classList.add('d-none')
      return
    }

    lastRunProgressPayload = payload
    const libraries = payload.libraries
    const total = payload.total_count || libraries.length
    const completed = payload.completed_count != null
      ? payload.completed_count
      : libraries.filter(entry => entry.status === 'Done').length

    const phaseOrderKeys = Array.isArray(payload.phase_order) && payload.phase_order.length
      ? payload.phase_order
      : runPhaseOrder.map(phase => phase.key)
    const phaseCount = phaseOrderKeys.length || 1
    const currentPhaseIndex = payload.phase_current
      ? Math.max(0, phaseOrderKeys.indexOf(payload.phase_current))
      : 0
    const totalSteps = total * phaseCount
    let completedSteps = completed * phaseCount
    if (payload.current_library && total > 0) {
      completedSteps = Math.min(totalSteps, completedSteps + currentPhaseIndex)
    }
    const percent = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0
    const bar = document.getElementById('run-progress-bar')
    if (bar) {
      bar.style.width = `${percent}%`
      bar.setAttribute('aria-valuenow', String(percent))
    }

    const summary = document.getElementById('run-progress-summary')
    if (summary) {
      const current = payload.current_library ? ` | Current: ${payload.current_library}` : ''
      const stepLabel = totalSteps > 0 ? ` | Step ${completedSteps}/${totalSteps}` : ''
      let lastUpdated = ''
      if (payload.last_log_at) {
        const formatter = typeof window.QS_formatTimestamp === 'function' ? window.QS_formatTimestamp : null
        const label = formatter ? formatter(payload.last_log_at) : new Date(payload.last_log_at).toLocaleString()
        lastUpdated = ` | Last updated: ${label}`
      }
      summary.textContent = `${completed}/${total} libraries complete${current}${stepLabel}${lastUpdated}`
    }

    const prepRow = document.getElementById('run-prep-row')
    if (prepRow) {
      const prepLockedValue = coerceRunSeconds(payload.preparation_seconds)
      const prepLiveValue = coerceRunSeconds(payload.preparation_elapsed_seconds)
      const hasLockedPrep = typeof prepLockedValue === 'number'
      const prepSeconds = hasLockedPrep ? prepLockedValue : prepLiveValue
      if (prepSeconds != null) {
        const prepLabel = formatRunSeconds(prepSeconds) || '0s'
        const prepClass = hasLockedPrep ? 'text-bg-success' : 'text-bg-primary'
        prepRow.innerHTML = `
          <span class="me-2 fw-semibold">Preparation</span>
          <span class="badge ${prepClass}">${prepLabel}</span>
        `
        prepRow.classList.remove('d-none')
      } else {
        prepRow.classList.add('d-none')
      }
    }

    const maintenanceRow = document.getElementById('run-maintenance-row')
    if (maintenanceRow) {
      const statusData = latestKometaStatusPayload || {}
      const windowLabel = statusData.maintenance_window ? ` (${statusData.maintenance_window})` : ''
      if (statusData.maintenance_paused) {
        let pauseLabel = 'Paused'
        const pausedSince = statusData.maintenance_paused_since ? new Date(statusData.maintenance_paused_since) : null
        if (pausedSince && !Number.isNaN(pausedSince.getTime())) {
          const elapsedSeconds = Math.max(0, Math.floor((Date.now() - pausedSince.getTime()) / 1000))
          pauseLabel = formatRunSeconds(elapsedSeconds) || 'Paused'
        }
        maintenanceRow.innerHTML = `
          <span class="me-2 fw-semibold">Maintenance</span>
          <span class="badge text-bg-warning text-dark">Paused${windowLabel}</span>
          <span class="badge text-bg-secondary">${pauseLabel}</span>
        `
        maintenanceRow.classList.remove('d-none')
      } else if (statusData.maintenance_active) {
        maintenanceRow.innerHTML = `
          <span class="me-2 fw-semibold">Maintenance</span>
          <span class="badge text-bg-warning text-dark">Window Active${windowLabel}</span>
        `
        maintenanceRow.classList.remove('d-none')
      } else {
        maintenanceRow.classList.add('d-none')
      }
    }

    const allowed = Array.isArray(payload.allowed_phases) && payload.allowed_phases.length
      ? new Set(payload.allowed_phases)
      : null
    const phaseLookup = new Map(runPhaseOrder.map(phase => [phase.key, phase.label]))
    const phasesToShow = (Array.isArray(phaseOrderKeys) ? phaseOrderKeys : runPhaseOrder.map(phase => phase.key))
      .filter(key => !allowed || allowed.has(key))
      .map(key => ({ key, label: phaseLookup.get(key) || key }))
    const phaseIndexLookup = new Map(phasesToShow.map((phase, idx) => [phase.key, idx]))

    const headerRow = document.getElementById('run-library-header')
    if (headerRow) {
      const phaseHeaders = phasesToShow.map(phase => `<th class="text-end">${phase.label}</th>`).join('')
      headerRow.innerHTML = `<th>Library</th><th>Type</th><th>Status</th>${phaseHeaders}`
    }

    const visibleLibraries = libraries.filter(entry => entry.status !== 'Skipped')
    const rows = document.getElementById('run-library-rows')
    if (rows) {
      rows.innerHTML = visibleLibraries.map(entry => {
        let klass = 'text-bg-secondary'
        if (entry.status === 'Done') klass = 'text-bg-success'
        else if (entry.status === 'In progress') klass = 'text-bg-primary'
        else if (entry.status === 'Stopped') klass = 'text-bg-danger'
        else if (entry.status === 'Skipped') klass = 'text-bg-dark'
        const typeLabel = entry.type ? entry.type : '—'
        const durations = entry.durations || {}
        const currentPhaseForRow = payload.current_library === entry.name ? payload.phase_current : null
        const explicitPhases = new Set(Object.keys(durations))
        let lastSeenIndex = -1
        explicitPhases.forEach(key => {
          const idx = phaseIndexLookup.get(key)
          if (idx != null && idx > lastSeenIndex) lastSeenIndex = idx
        })
        if (currentPhaseForRow) {
          const idx = phaseIndexLookup.get(currentPhaseForRow)
          if (idx != null && idx > lastSeenIndex) lastSeenIndex = idx
        }
        const inferredPhases = new Set()
        if (entry.status !== 'Skipped' && lastSeenIndex >= 0) {
          phasesToShow.forEach(phase => {
            const idx = phaseIndexLookup.get(phase.key)
            if (idx != null && idx < lastSeenIndex && !explicitPhases.has(phase.key)) {
              inferredPhases.add(phase.key)
            }
          })
        }

        const durationCells = phasesToShow.map(phase => {
          if (phase.key === 'playlists') {
            const total = typeof payload.playlist_total_seconds === 'number' ? payload.playlist_total_seconds : null
            const running = Boolean(payload.playlist_running)
            const elapsed = typeof payload.playlist_elapsed_seconds === 'number' ? payload.playlist_elapsed_seconds : null
            const detected = Boolean(payload.playlists_detected)
            if (running) {
              const label = elapsed != null ? formatRunSeconds(elapsed) : 'Running'
              return `<td class="text-end"><span class="badge text-bg-primary">${label || 'Running'}</span></td>`
            }
            if (total != null && (total > 0 || detected)) {
              return `<td class="text-end"><span class="badge text-bg-success">${formatRunSeconds(total) || '0s'}</span></td>`
            }
            if (payload.run_finished) {
              return '<td class="text-end"><span class="badge text-bg-secondary">Not Configured</span></td>'
            }
            return '<td class="text-end text-muted small">—</td>'
          }
          const seconds = durations[phase.key]
          const hasSeconds = typeof seconds === 'number' && Number.isFinite(seconds)
          const isRunning = currentPhaseForRow === phase.key
          const isExplicit = explicitPhases.has(phase.key)
          const isInferred = inferredPhases.has(phase.key)
          if (entry.status === 'Skipped') {
            return '<td class="text-end text-muted small">—</td>'
          }
          if (isRunning) {
            const elapsed = typeof payload.current_phase_elapsed_seconds === 'number'
              ? formatRunSeconds(payload.current_phase_elapsed_seconds)
              : (hasSeconds ? formatRunSeconds(seconds) : 'Running')
            return `<td class="text-end"><span class="badge text-bg-primary">${elapsed || 'Running'}</span></td>`
          }
          if (isExplicit && hasSeconds) {
            return `<td class="text-end"><span class="badge text-bg-success">${formatRunSeconds(seconds)}</span></td>`
          }
          if (isInferred) {
            return '<td class="text-end"><span class="badge text-bg-secondary">Not Configured</span></td>'
          }
          return '<td class="text-end text-muted small">—</td>'
        }).join('')
        return `
          <tr>
            <td>${entry.name}</td>
            <td>${typeLabel}</td>
            <td><span class="badge ${klass}">${entry.status}</span></td>
            ${durationCells}
          </tr>
        `
      }).join('')
    }

    const footer = document.getElementById('run-library-footer')
    const totalRow = document.getElementById('run-library-total-row')
    if (footer && totalRow) {
      if (!libraries.length || !phasesToShow.length) {
        footer.classList.add('d-none')
      } else {
        const totals = new Map(phasesToShow.map(phase => [phase.key, 0]))
        visibleLibraries.forEach(entry => {
          if (entry.status === 'Skipped') return
          const durations = entry.durations || {}
          phasesToShow.forEach(phase => {
            if (phase.key === 'playlists') {
              return
            }
            const seconds = durations[phase.key]
            if (typeof seconds === 'number' && Number.isFinite(seconds)) {
              totals.set(phase.key, (totals.get(phase.key) || 0) + seconds)
            }
          })
        })
        if (phasesToShow.some(phase => phase.key === 'playlists')) {
          const playlistTotal = typeof payload.playlist_total_seconds === 'number' ? payload.playlist_total_seconds : null
          const playlistDetected = Boolean(payload.playlists_detected)
          if (playlistTotal != null && (playlistTotal > 0 || playlistDetected)) {
            totals.set('playlists', playlistTotal)
          }
        }
        const prepSeconds = (() => {
          const locked = coerceRunSeconds(payload.preparation_seconds)
          if (typeof locked === 'number' && Number.isFinite(locked)) return locked
          const live = coerceRunSeconds(payload.preparation_elapsed_seconds)
          return typeof live === 'number' && Number.isFinite(live) ? live : 0
        })()
        let grandTotal = prepSeconds
        totals.forEach((value) => {
          if (typeof value === 'number' && Number.isFinite(value)) {
            grandTotal += value
          }
        })
        const totalCells = phasesToShow.map(phase => {
          const totalSeconds = totals.get(phase.key)
          if (phase.key === 'playlists' && typeof totalSeconds === 'number' && Number.isFinite(totalSeconds)) {
            const detected = Boolean(payload.playlists_detected)
            if (totalSeconds > 0 || detected) {
              return `<td class="text-end"><span class="badge text-bg-success">${formatRunSeconds(totalSeconds) || '0s'}</span></td>`
            }
          }
          if (typeof totalSeconds === 'number' && totalSeconds > 0) {
            return `<td class="text-end"><span class="badge text-bg-success">${formatRunSeconds(totalSeconds)}</span></td>`
          }
          return '<td class="text-end text-muted small">—</td>'
        }).join('')
        const totalLabel = grandTotal > 0 ? `<span class="badge text-bg-success">${formatRunSeconds(grandTotal)}</span>` : '—'
        totalRow.innerHTML = `<td class="fw-semibold">Total</td><td>—</td><td>${totalLabel}</td>${totalCells}`
        footer.classList.remove('d-none')
      }
    }

    container.classList.remove('d-none')
  }

  function clearRunProgress (resetCache = false) {
    const container = document.getElementById('run-progress')
    if (container) {
      container.classList.add('d-none')
    }
    const maintenanceRow = document.getElementById('run-maintenance-row')
    if (maintenanceRow) {
      maintenanceRow.classList.add('d-none')
    }
    if (resetCache) {
      lastRunProgressPayload = null
    }
  }

  function fetchRunProgress () {
    if (runProgressInFlight) return Promise.resolve(null)
    runProgressInFlight = true
    return fetch('/logscan/progress')
      .then(res => {
        if (!res.ok) return null
        return res.json()
      })
      .then(data => {
        if (!data) {
          if (KOMETA_STATUS === 'running' && lastRunProgressPayload) {
            renderRunProgress(lastRunProgressPayload)
          } else {
            clearRunProgress(false)
          }
          return
        }
        renderRunProgress(data)
      })
      .catch(() => {
        if (KOMETA_STATUS === 'running' && lastRunProgressPayload) {
          renderRunProgress(lastRunProgressPayload)
        } else {
          clearRunProgress(false)
        }
      })
      .finally(() => {
        runProgressInFlight = false
      })
  }

  function getUpdateButtonLabel () {
    const force = $forceUpdateToggle.is(':checked')
    const label = force
      ? (KOMETA_INSTALLED ? 'Force Update Kometa' : 'Force Install Kometa')
      : (KOMETA_INSTALLED
          ? (KOMETA_UPDATE_AVAILABLE ? 'Update Available' : (KOMETA_UPDATE_CHECK_COMPLETED ? 'Up to date' : 'Check for Kometa Updates'))
          : 'Install Kometa')
    return `<i class="bi bi-arrow-clockwise me-1"></i> ${label}`
  }

  function syncUpdateButtonLabel () {
    if ($updateKometaBtn.length) {
      $updateKometaBtn.html(getUpdateButtonLabel())
    }
    syncKometaUpdateAttention()
  }

  function callUpdateKometa () {
    if (KOMETA_STATUS === 'running') {
      showToast('info', 'Kometa is currently running; update skipped.')
      return
    }

    const $btn = $updateKometaBtn
    const $logBox = $('#kometa-validation-log')
    const $runNow = $('#run-now')
    const $stopNow = $('#stop-now')
    const $runBox = $('#run-command-box')
    const qsBranch = $btn.data('qs-branch') || 'master'
    const branchOverride = getKometaBranchOverride()
    const forceUpdate = $forceUpdateToggle.is(':checked')

    if (KOMETA_INSTALLED && !forceUpdate && !KOMETA_UPDATE_AVAILABLE) {
      $btn.prop('disabled', true).html('<i class="bi bi-arrow-repeat me-1"></i> Checking...')
      $forceUpdateToggle.prop('disabled', true)
      $kometaBranchOverride.prop('disabled', true)
      runKometaStatusPass(true)
        .then((data) => {
          if (!data) return
          if (data.kometa_update_available) {
            showToast('warning', `Kometa update available: ${data.local_version} → ${data.remote_version}.`)
          } else if (!data.kometa_update_check_skipped) {
            showToast('success', 'Kometa is already up to date.')
          }
        })
        .catch(() => {
          showToast('error', 'Failed to check Kometa update status.')
        })
        .finally(() => {
          $btn.prop('disabled', false)
          $forceUpdateToggle.prop('disabled', false)
          $kometaBranchOverride.prop('disabled', false)
          syncUpdateButtonLabel()
        })
      return
    }

    KOMETA_UPDATING = true
    KOMETA_VALIDATED = false
    KOMETA_UPDATE_CHECK_SKIPPED = false
    KOMETA_UPDATE_CHECK_COMPLETED = false
    setKometaUpdatePhaseBadge('queued')
    syncKometaRollupBadge()
    hideRunCommandSectionUntilValidated()
    syncFinalAccordionRollups()
    const prevRunNowHtml = $runNow.html()
    const prevRunNowDisabled = $runNow.prop('disabled')

    $runBox.addClass('opacity-50 position-relative')
    $runNow.prop('disabled', true).html('<i class="bi bi-hourglass me-1"></i> Updating...')
    $stopNow.prop('disabled', true)

    const inProgressLabel = forceUpdate
      ? (KOMETA_INSTALLED ? 'Force Updating...' : 'Force Installing...')
      : (KOMETA_INSTALLED ? 'Checking for updates...' : 'Installing...')
    $btn.prop('disabled', true).html(`<i class="bi bi-arrow-repeat me-1"></i> ${inProgressLabel}`)
    $forceUpdateToggle.prop('disabled', true)
    $kometaBranchOverride.prop('disabled', true)
    $logBox.append('\nInitializing/Updating Kometa...\n')
    if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight

    // progress heartbeat
    const startTs = Date.now()
    showToast('info', 'Still working on Kometa... (0 seconds elapsed)', 10000)
    const heartbeatId = setInterval(() => {
      const secs = Math.floor((Date.now() - startTs) / 1000)
      showToast('info', `Still working on Kometa... (${secs} seconds elapsed)`, 10000)
    }, 30000) // every 30s

    let postUpdateLabel = null
    const cleanupUI = () => {
      clearInterval(heartbeatId)
      stopKometaUpdatePolling()
      kometaUpdateJobId = null
      kometaUpdateLogIndex = 0
      KOMETA_UPDATING = false
      $runBox.removeClass('opacity-50 position-relative')
      $runNow.prop('disabled', prevRunNowDisabled).html(prevRunNowHtml)
      $stopNow.prop('disabled', false)
      $btn.prop('disabled', false)
      $forceUpdateToggle.prop('disabled', false)
      $kometaBranchOverride.prop('disabled', false)
      syncUpdateButtonLabel()
      updateRunNowState()
      syncFinalAccordionRollups()
      if (postUpdateLabel) {
        $btn.html(postUpdateLabel)
        setTimeout(syncUpdateButtonLabel, 6000)
      }
    }

    fetch('/update-kometa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ branch: qsBranch, branch_override: branchOverride, force: forceUpdate, background: true })
    })
      .then(async res => {
        const data = await res.json()
        if (res.status === 409) {
          setKometaUpdatePhaseBadge('failed')
          showToast('warning', data.error || 'Kometa is running; stop it before updating.')
          $logBox.append(`${data.error || 'Update blocked: Kometa running.'}\n`)
          if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight
          return { success: false, log: data.log || [], blocked: true }
        }
        if (!res.ok) {
          throw new Error(data.error || 'Kometa update failed to start.')
        }
        return data
      })
      .then(data => {
        if (!data) return
        if (data.success && data.job_id) {
          kometaUpdateJobId = data.job_id
          kometaUpdateLogIndex = 0
          stopKometaUpdatePolling()
          const finalize = (progress) => {
            if (!progress || !progress.done) return false
            KOMETA_LOCAL_CHECK_COMPLETED = false
            KOMETA_UPDATE_AVAILABLE = false
            $('#kometa-update-box').addClass('d-none')
            syncUpdateButtonLabel()
            const elapsed = formatElapsed(Date.now() - startTs)
            if (progress.update_success) {
              if (progress.up_to_date) {
                showToast('info', 'Kometa is already up to date.')
                postUpdateLabel = '<i class="bi bi-check-circle me-1"></i> Up to date'
                appendKometaStatusLine('Kometa is already up to date.')
                setKometaUpdatePhaseBadge('ready')
              } else {
                showToast('success', `Kometa update completed in ${elapsed}.`)
                appendKometaStatusLine('Kometa update completed successfully.')
                setKometaUpdatePhaseBadge('validating')
              }
              validateKometaRoot({ appendStatus: true })
            } else {
              showToast('error', 'Kometa update failed.')
              appendKometaStatusLine('Kometa update failed.')
              setKometaUpdatePhaseBadge('failed')
              validateKometaRoot({ appendStatus: true })
            }
            cleanupUI()
            syncKometaRollupBadge()
            return true
          }
          return pollKometaUpdateProgress()
            .then(progress => {
              if (finalize(progress)) return
              kometaUpdatePollInterval = setInterval(() => {
                pollKometaUpdateProgress()
                  .then(finalize)
                  .catch(err => {
                    console.error(err)
                    appendKometaStatusLine(`❌ ${err.message || 'Failed to fetch Kometa update progress.'}`)
                    setKometaUpdatePhaseBadge('failed')
                    stopKometaUpdatePolling()
                    cleanupUI()
                    syncKometaRollupBadge()
                  })
              }, 800)
            })
        }
        if (data.success) {
          KOMETA_LOCAL_CHECK_COMPLETED = false
          KOMETA_UPDATE_AVAILABLE = false
          $('#kometa-update-box').addClass('d-none')
          syncUpdateButtonLabel()
          const elapsed = formatElapsed(Date.now() - startTs)
          if (data.up_to_date) {
            showToast('info', 'Kometa is already up to date.')
            postUpdateLabel = '<i class="bi bi-check-circle me-1"></i> Up to date'
            $logBox.append('Kometa is already up to date.\n')
          } else {
            showToast('success', `Kometa update completed in ${elapsed}.`)
            $logBox.append('Kometa update completed successfully.\n')
          }
          if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight
          validateKometaRoot({ appendStatus: true })
        } else if (!data.blocked) {
          showToast('error', data.error || 'Kometa update failed.')
          $logBox.append('Kometa update failed.\n')
          validateKometaRoot({ appendStatus: true })
          if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight
        }
      })
      .catch(err => {
        console.error(err)
        showToast('error', 'Error during Kometa update.')
        $logBox.append('Error occurred during Kometa update.\n')
        setKometaUpdatePhaseBadge('failed')
        if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight
        cleanupUI()
        syncKometaRollupBadge()
      })
  }

  // Kometa Update Button Click
  $updateKometaBtn.on('click', callUpdateKometa)
  $forceUpdateToggle.on('change', function () {
    if (!KOMETA_UPDATING) syncUpdateButtonLabel()
  })
  $kometaBranchOverride.on('change', function () {
    saveKometaBranchOverride()
    syncKometaBranchOverrideWarning()
    if (!KOMETA_UPDATING) runKometaStatusPass(true)
  })
  loadSavedKometaBranchOverride()
  syncKometaBranchOverrideWarning()
  syncKometaSourceStatus()
  setKometaUpdatePhaseBadge(kometaUpdatePhaseStatus)
  syncUpdateButtonLabel()
  syncKometaRollupBadge()

  // Sync visibility for timeout and divider on page load
  $('#opt-timeout-container').toggleClass('d-none', !$('#opt-timeout').is(':checked'))
  $('#opt-divider-container').toggleClass('d-none', !$('#opt-divider').is(':checked'))
  $('#opt-width-container').toggleClass('d-none', !$('#opt-width').is(':checked'))

  $('#opt-timeout').on('change', function () {
    $('#opt-timeout-container').toggleClass('d-none', !this.checked)
    if (!this.checked) {
      $('#opt-timeout-val').val('')
      $('#timeout-error').addClass('d-none')
    }
    buildCommand()
  })

  $('#opt-width').on('change', function () {
    $('#opt-width-container').toggleClass('d-none', !this.checked)
    if (!this.checked) {
      $('#opt-width-val').val('')
      $('#width-error').addClass('d-none')
    }
    buildCommand()
  })

  // Restrict divider input
  $('#opt-divider-val').on('input', function () {
    this.value = this.value.replace(/\s/g, '').slice(0, 1)
    buildCommand()
  })

  // Prevent non-numeric input for Timeout
  $('#opt-timeout-val').on('input', function () {
    const sanitized = this.value.replace(/[^0-9]/g, '')
    if (this.value !== sanitized) {
      this.value = sanitized
    }
    buildCommand()
  })

  // Prevent non-numeric input for Width
  $('#opt-width-val').on('input', function () {
    const sanitized = this.value.replace(/[^0-9]/g, '')
    if (this.value !== sanitized) {
      this.value = sanitized
    }
    buildCommand()
  })

  $('#opt-divider').on('change', function () {
    $('#opt-divider-container').toggleClass('d-none', !this.checked)
    if (!this.checked) {
      $('#opt-divider-val').val('')
      $('#divider-error').addClass('d-none')
    }
    buildCommand()
  })

  $pauseLogBtn.on('click', function () {
    logPollingPaused = !logPollingPaused
    if (logPollingPaused) {
      $(this).html('<i class="bi bi-play-circle me-1"></i> Resume')
      showToast('info', 'Log polling paused.')
    } else {
      $(this).html('<i class="bi bi-pause-circle me-1"></i> Pause')
      fetchKometaLog()
      startPollingIfNeeded()
    }
  })

  function applyLogFilter (text, filter) {
    if (!filter) return text

    // Support literal matching by default; allow regex if user wraps with /
    const trimmed = filter.trim()
    let re
    try {
      if (trimmed.length > 2 && trimmed.startsWith('/') && trimmed.endsWith('/')) {
        re = new RegExp(trimmed.slice(1, -1), 'i')
      } else {
        const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        re = new RegExp(escaped, 'i')
      }
    } catch (e) {
      return text
    }

    return text.split('\n').filter(line => re.test(line)).join('\n')
  }

  function computeLogStats (text) {
    const stats = {
      cache: 0,
      debug: 0,
      info: 0,
      warning: 0,
      error: 0,
      critical: 0,
      trace: 0
    }
    if (!text) return stats
    const lines = text.split(/\r?\n/)
    lines.forEach(line => {
      if (!line) return
      if (line.toLowerCase().includes('from cache')) stats.cache += 1
      if (line.includes('[DEBUG]')) stats.debug += 1
      if (line.includes('[INFO]')) stats.info += 1
      if (line.includes('[WARNING]')) stats.warning += 1
      if (line.includes('[ERROR]')) stats.error += 1
      if (line.includes('[CRITICAL]')) stats.critical += 1
      if (line.toLowerCase().includes('traceback')) stats.trace += 1
    })
    return stats
  }

  function updateStatRow ($row, stats) {
    if (!$row || !$row.length || !stats) return
    const keys = ['cache', 'debug', 'info', 'warning', 'error', 'critical', 'trace']
    keys.forEach(key => {
      const val = typeof stats[key] === 'number' ? stats[key] : 0
      $row.find(`[data-log-stat="${key}"]`).text(val)
    })
  }

  function renderLogStats () {
    if (!$logStats.length && !$logStatsFiltered.length) return
    const totalStats = lastLogStatsTotal || computeLogStats(lastLogText)
    const filteredText = applyLogFilter(lastLogText, logFilter)
    const filteredStats = computeLogStats(filteredText)
    updateStatRow($logStats, totalStats)
    updateStatRow($logStatsFiltered, filteredStats)
  }

  function formatRunSeconds (seconds) {
    if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return ''
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

  function coerceRunSeconds (value) {
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value !== 'string') return null
    const trimmed = value.trim()
    if (!trimmed) return null
    if (/^\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed)
    const clockMatch = trimmed.match(/^(\d+):(\d{2}):(\d{2})$/)
    if (clockMatch) {
      const hrs = Number(clockMatch[1])
      const mins = Number(clockMatch[2])
      const secs = Number(clockMatch[3])
      if ([hrs, mins, secs].every(num => Number.isFinite(num))) {
        return (hrs * 3600) + (mins * 60) + secs
      }
    }
    let total = 0
    let matched = false
    const hoursMatch = trimmed.match(/(\d+)\s*h\b/i)
    if (hoursMatch) {
      total += Number(hoursMatch[1]) * 3600
      matched = true
    }
    const minsMatch = trimmed.match(/(\d+)\s*m\b/i)
    if (minsMatch) {
      total += Number(minsMatch[1]) * 60
      matched = true
    }
    const secsMatch = trimmed.match(/(\d+)\s*s\b/i)
    if (secsMatch) {
      total += Number(secsMatch[1])
      matched = true
    }
    if (matched && Number.isFinite(total)) return total
    return null
  }

  function escapeHtml (value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
  }

  function linkifyText (value) {
    if (!value) return ''
    const escaped = escapeHtml(value)
    const placeholders = []
    let counter = 0
    const withPlaceholders = escaped.replace(/\[(https?:\/\/[^\s\]]+)\]/g, (_match, url) => {
      const token = `__URLTOKEN${counter}__`
      placeholders.push({ token, url })
      counter += 1
      return token
    })
    let linked = withPlaceholders.replace(/(https?:\/\/[^\s<]+)/g, (url) => {
      return `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`
    })
    placeholders.forEach(({ token, url }) => {
      const anchor = `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`
      linked = linked.replace(token, anchor)
    })
    return linked
  }

  function formatTimestampLocal (value) {
    if (!value) return 'n/a'
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return String(value)
    return parsed.toLocaleString()
  }

  function updateTailNotice () {
    if (!$tailNotice.length) return
    const sizeLabel = tailSize === 'all' ? 'all lines' : `last ${tailSize} lines`
    $tailNotice.text(`Showing ${sizeLabel} from meta.log`)
  }

  const SPARKLINE_WIDTH = 180
  const SPARKLINE_HEIGHT = 48
  const SPARKLINE_PADDING = 2
  const SPARKLINE_MAX_POINTS = 40
  const runSparkState = {
    cpu: { system: [], kometa: [] },
    mem: { system: [], kometa: [] },
    io: { read: [], write: [] }
  }

  function clampPercent (value) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return null
    return Math.max(0, Math.min(100, value))
  }

  function pushSparkValue (series, value) {
    if (value == null) {
      if (!series.length) return false
      series.push(series[series.length - 1])
    } else {
      series.push(value)
    }
    if (series.length > SPARKLINE_MAX_POINTS) series.shift()
    return true
  }

  function buildSparklinePoints (series) {
    if (!series.length) return ''
    const width = SPARKLINE_WIDTH - SPARKLINE_PADDING * 2
    const height = SPARKLINE_HEIGHT - SPARKLINE_PADDING * 2
    const step = series.length > 1 ? width / (series.length - 1) : 0
    return series.map((value, idx) => {
      const x = SPARKLINE_PADDING + (idx * step)
      const y = SPARKLINE_PADDING + (height - (height * (value / 100)))
      return `${x.toFixed(1)},${y.toFixed(1)}`
    }).join(' ')
  }

  function buildSparklinePointsScaled (series, maxValue) {
    if (!series.length) return ''
    const safeMax = typeof maxValue === 'number' && Number.isFinite(maxValue) && maxValue > 0 ? maxValue : 1
    const normalized = series.map(value => {
      if (typeof value !== 'number' || !Number.isFinite(value)) return 0
      return Math.max(0, Math.min(100, (value / safeMax) * 100))
    })
    return buildSparklinePoints(normalized)
  }

  function renderRunSparklines () {
    if (!$runStatusSparklines.length) return
    const hasData = runSparkState.cpu.system.length || runSparkState.cpu.kometa.length ||
      runSparkState.mem.system.length || runSparkState.mem.kometa.length ||
      runSparkState.io.read.length || runSparkState.io.write.length
    $runStatusSparklines.toggleClass('d-none', !hasData)
    if (!hasData) {
      if ($runSparkCpuSystem.length) $runSparkCpuSystem.attr('points', '')
      if ($runSparkCpuKometa.length) $runSparkCpuKometa.attr('points', '')
      if ($runSparkMemSystem.length) $runSparkMemSystem.attr('points', '')
      if ($runSparkMemKometa.length) $runSparkMemKometa.attr('points', '')
      const $runSparkIoRead = $('#run-spark-io-read')
      const $runSparkIoWrite = $('#run-spark-io-write')
      if ($runSparkIoRead.length) $runSparkIoRead.attr('points', '')
      if ($runSparkIoWrite.length) $runSparkIoWrite.attr('points', '')
      return
    }
    if ($runSparkCpuSystem.length) $runSparkCpuSystem.attr('points', buildSparklinePoints(runSparkState.cpu.system))
    if ($runSparkCpuKometa.length) $runSparkCpuKometa.attr('points', buildSparklinePoints(runSparkState.cpu.kometa))
    if ($runSparkMemSystem.length) $runSparkMemSystem.attr('points', buildSparklinePoints(runSparkState.mem.system))
    if ($runSparkMemKometa.length) $runSparkMemKometa.attr('points', buildSparklinePoints(runSparkState.mem.kometa))
    const $runSparkIoRead = $('#run-spark-io-read')
    const $runSparkIoWrite = $('#run-spark-io-write')
    const ioMax = Math.max(0, ...runSparkState.io.read, ...runSparkState.io.write)
    if ($runSparkIoRead.length) $runSparkIoRead.attr('points', buildSparklinePointsScaled(runSparkState.io.read, ioMax))
    if ($runSparkIoWrite.length) $runSparkIoWrite.attr('points', buildSparklinePointsScaled(runSparkState.io.write, ioMax))
  }

  function resetRunSparklines () {
    runSparkState.cpu.system = []
    runSparkState.cpu.kometa = []
    runSparkState.mem.system = []
    runSparkState.mem.kometa = []
    runSparkState.io.read = []
    runSparkState.io.write = []
    renderRunSparklines()
  }

  function updateRunSparklines (data) {
    if (!data || data.status !== 'running') {
      resetRunSparklines()
      return
    }
    const cpuSystem = clampPercent(data.system_cpu_percent)
    const cpuKometa = clampPercent(data.cpu_percent)
    const memSystem = clampPercent(data.system_memory_percent)
    const memKometa = clampPercent(data.memory_percent)
    const ioRead = (typeof data.disk_read_rate_mb_s === 'number' && Number.isFinite(data.disk_read_rate_mb_s))
      ? Math.max(0, data.disk_read_rate_mb_s)
      : null
    const ioWrite = (typeof data.disk_write_rate_mb_s === 'number' && Number.isFinite(data.disk_write_rate_mb_s))
      ? Math.max(0, data.disk_write_rate_mb_s)
      : null
    pushSparkValue(runSparkState.cpu.system, cpuSystem)
    pushSparkValue(runSparkState.cpu.kometa, cpuKometa)
    pushSparkValue(runSparkState.mem.system, memSystem)
    pushSparkValue(runSparkState.mem.kometa, memKometa)
    pushSparkValue(runSparkState.io.read, ioRead)
    pushSparkValue(runSparkState.io.write, ioWrite)
    renderRunSparklines()
  }

  function syncRunStatusVisibility () {
    if (!$runStatusRow.length) return
    const hasText = Boolean($runStatusTimer.text() || $runStatusMetrics.text() || $runStatusLog.text())
    $runStatusRow.toggleClass('d-none', !hasText)
  }

  function updateRunStatus (data) {
    if (!$runStatusRow.length) return
    if (data && data.status === 'running') {
      const startedAt = formatTimestampLocal(data.started_at)
      const elapsed = formatRunSeconds(data.elapsed_seconds)
      const formatMem = (valueMb) => {
        if (typeof valueMb !== 'number' || !Number.isFinite(valueMb)) return 'n/a'
        if (valueMb >= 1024) return `${(valueMb / 1024).toFixed(1)} GB`
        return `${valueMb.toFixed(1)} MB`
      }
      const cpuText = (typeof data.cpu_percent === 'number' && Number.isFinite(data.cpu_percent))
        ? `${data.cpu_percent.toFixed(1)}%`
        : 'n/a'
      const memRss = formatMem(data.memory_rss_mb)
      const memPct = (typeof data.memory_percent === 'number' && Number.isFinite(data.memory_percent))
        ? `${data.memory_percent.toFixed(1)}%`
        : 'n/a'
      const sysCpu = (typeof data.system_cpu_percent === 'number' && Number.isFinite(data.system_cpu_percent))
        ? `${data.system_cpu_percent.toFixed(1)}%`
        : 'n/a'
      const sysUsed = formatMem(data.system_memory_used_mb)
      const sysTotal = formatMem(data.system_memory_total_mb)
      const sysPct = (typeof data.system_memory_percent === 'number' && Number.isFinite(data.system_memory_percent))
        ? `${data.system_memory_percent.toFixed(1)}%`
        : 'n/a'
      const formatDiskMb = (valueMb) => {
        if (typeof valueMb !== 'number' || !Number.isFinite(valueMb)) return 'n/a'
        if (valueMb >= 1024) return `${(valueMb / 1024).toFixed(1)} GB`
        return `${valueMb.toFixed(1)} MB`
      }
      const formatDiskRate = (valueMbS) => {
        if (typeof valueMbS !== 'number' || !Number.isFinite(valueMbS)) return 'n/a'
        if (valueMbS >= 1024) return `${(valueMbS / 1024).toFixed(2)} GB/s`
        return `${valueMbS.toFixed(2)} MB/s`
      }
      const hasDiskData = [data.disk_read_mb, data.disk_write_mb, data.disk_read_rate_mb_s, data.disk_write_rate_mb_s]
        .some(value => typeof value === 'number' && Number.isFinite(value))
      const diskText = hasDiskData
        ? ` | Disk: R ${formatDiskRate(data.disk_read_rate_mb_s)} • W ${formatDiskRate(data.disk_write_rate_mb_s)} • ${formatDiskMb(data.disk_read_mb)} read • ${formatDiskMb(data.disk_write_mb)} written`
        : ''
      $runStatusTimer.text(`Running since: ${startedAt} • Elapsed: ${elapsed || 'n/a'}`)
      $runStatusMetrics.text(`Kometa: ${cpuText} CPU • ${memRss} (${memPct}) | System: ${sysCpu} CPU • ${sysUsed} / ${sysTotal} (${sysPct})${diskText}`)
    } else if (data && data.status === 'done') {
      $runStatusTimer.text('Kometa run complete.')
      $runStatusMetrics.text('')
    } else {
      $runStatusTimer.text('')
      $runStatusMetrics.text('')
    }
    updateRunSparklines(data)
    syncRunStatusVisibility()
  }

  function updateLogRecency (data) {
    if (!$runStatusLog.length) return
    if (!data || typeof data.log_age_seconds !== 'number') {
      $runStatusLog.text('')
      syncRunStatusVisibility()
      return
    }
    const ageText = formatRunSeconds(data.log_age_seconds) || 'n/a'
    let logText = `meta.log updated ${ageText} ago`
    const totalLines = data?.stats?.total_lines ?? lastLogStatsTotal?.total_lines
    if (typeof totalLines === 'number' && Number.isFinite(totalLines)) {
      logText += ` • ${totalLines.toLocaleString()} lines`
    }
    if (data.log_is_stale && KOMETA_STATUS === 'running') {
      logText += ' • waiting for new meta.log entries from this run'
      $runStatusLog.addClass('text-warning').removeClass('text-muted')
    } else {
      $runStatusLog.removeClass('text-warning').addClass('text-muted')
    }
    $runStatusLog.text(logText)
    syncRunStatusVisibility()
  }

  function renderLogscan (data) {
    if (!$logscanPanel.length) return
    if (!data || data.error) {
      $logscanSummary.text('')
      $logscanRecommendations.html('<div class="text-muted">Logscan unavailable.</div>')
      $logscanMissing.addClass('d-none').empty()
      updateLogscanHeaderBadge({ error: true })
      return
    }

    const summary = data.summary || {}
    const finishedAt = summary.finished_at || ''
    const runSeconds = summary.run_time_seconds
    let runtime = ''
    if (typeof runSeconds === 'number' && Number.isFinite(runSeconds) && runSeconds > 0) {
      runtime = formatRunSeconds(runSeconds)
    } else if (runSeconds === 0 || runSeconds == null) {
      runtime = 'n/a'
    }
    let summaryText = ''
    if (finishedAt) summaryText = `Last run: ${finishedAt}`
    if (runtime) summaryText = summaryText ? `${summaryText} • Runtime: ${runtime}` : `Runtime: ${runtime}`
    $logscanSummary.text(summaryText)

    const recs = Array.isArray(data.recommendations) ? data.recommendations : []
    $logscanRecommendations.empty()
    if (!recs.length) {
      $logscanRecommendations.html('<div class="text-muted">No recommendations yet.</div>')
    } else {
      const maxRecs = 8
      recs.slice(0, maxRecs).forEach(rec => {
        const title = rec && rec.first_line ? rec.first_line : 'Recommendation'
        let message = rec && rec.message ? rec.message : ''
        if (message && title) {
          const firstLine = message.split('\n')[0].trim()
          const normalizedFirst = firstLine.replace(/\*/g, '').trim().toLowerCase()
          const normalizedTitle = title.replace(/\*/g, '').trim().toLowerCase()
          if (normalizedFirst === normalizedTitle) {
            message = message.split('\n').slice(1).join('\n').trim()
          }
        }
        const $item = $('<div class="border rounded p-2 mb-2 bg-body-tertiary"></div>')
        $('<div class="fw-semibold mb-1"></div>').text(title).appendTo($item)
        $('<div class="text-muted" style="white-space: pre-wrap;"></div>').html(linkifyText(message)).appendTo($item)
        $logscanRecommendations.append($item)
      })
      if (recs.length > maxRecs) {
        $logscanRecommendations.append(
          $('<div class="text-muted"></div>').text(`Showing ${maxRecs} of ${recs.length} recommendations.`)
        )
      }
    }

    $logscanSections.empty()
    const sections = summary.section_runtimes || {}
    const sectionTotal = summary.section_runtime_total_seconds
    const sectionDelta = summary.section_runtime_delta_seconds
    const runTotal = summary.run_time_seconds
    const sectionEntries = Object.entries(sections)
      .filter(([, value]) => typeof value === 'number' && Number.isFinite(value))
      .sort((a, b) => b[1] - a[1])
    if (sectionEntries.length) {
      let header = 'Section runtimes'
      const metaParts = []
      if (typeof sectionTotal === 'number' && Number.isFinite(sectionTotal)) {
        metaParts.push(`sum: ${formatRunSeconds(sectionTotal)}`)
      }
      if (typeof runTotal === 'number' && Number.isFinite(runTotal)) {
        metaParts.push(`run total: ${formatRunSeconds(runTotal)}`)
      }
      if (typeof sectionDelta === 'number' && Number.isFinite(sectionDelta)) {
        const deltaText = formatRunSeconds(Math.abs(sectionDelta)) || '0s'
        const sign = sectionDelta > 0 ? '+' : sectionDelta < 0 ? '-' : ''
        metaParts.push(`delta: ${sign}${deltaText}`)
      }
      if (metaParts.length) {
        header = `${header} (${metaParts.join(', ')})`
      }
      $('<div class="fw-semibold mb-1"></div>').text(header).appendTo($logscanSections)
      const listLines = sectionEntries.map(([name, seconds]) => `${name}: ${formatRunSeconds(seconds)}`)
      $('<div class="text-muted" style="white-space: pre-wrap;"></div>').text(listLines.join('\n')).appendTo($logscanSections)
    } else {
      $logscanSections.html('<div class="text-muted">No section runtimes yet.</div>')
    }

    const missing = Array.isArray(data.missing_people) ? data.missing_people : []
    $logscanMissing.empty()
    if (missing.length) {
      $logscanMissing.removeClass('d-none')
      const message = data.missing_people_message || 'Missing people posters detected.'
      $('<div class="fw-semibold"></div>').text('Missing people posters').appendTo($logscanMissing)
      $('<div class="text-muted mb-2" style="white-space: pre-wrap;"></div>').html(linkifyText(message)).appendTo($logscanMissing)
      $('<div class="text-muted" style="white-space: pre-wrap;"></div>')
        .text(missing.map(name => `- ${name}`).join('\n'))
        .appendTo($logscanMissing)
    } else {
      $logscanMissing.addClass('d-none')
    }

    updateLogscanHeaderBadge(data)
  }

  function fetchLogscanAnalysis (force = false) {
    if (!$logscanPanel.length) return
    logscanPollCounter += 1
    const shouldFetch = force || (logscanPollCounter % 5 === 0) || !lastLogscanPayload
    if (!shouldFetch || logscanAnalyzeInFlight) return

    logscanAnalyzeInFlight = true

    fetch('/logscan/analyze')
      .then(res => res.json())
      .then(data => {
        lastLogscanPayload = data
        renderLogscan(data)
      })
      .catch(err => {
        console.error('Error fetching logscan analysis:', err)
        $logscanRecommendations.html('<div class="text-muted">Logscan unavailable.</div>')
        updateLogscanHeaderBadge({ error: true })
      })
      .finally(() => {
        logscanAnalyzeInFlight = false
      })
  }

  function updateClearFilterButton () {
    if (!$clearFilterBtn.length) return
    const hasValue = $filterInput.val().trim().length > 0
    $clearFilterBtn.toggleClass('d-none', !hasValue)
  }

  $filterInput.on('input', function () {
    logFilter = $(this).val().trim()
    const filtered = applyLogFilter(lastLogText, logFilter)
    $runLog.text(filtered)
    updateClearFilterButton()
    renderLogStats()
  })

  $clearFilterBtn.on('click', function () {
    logFilter = ''
    $filterInput.val('')
    const filtered = applyLogFilter(lastLogText, logFilter)
    $runLog.text(filtered)
    updateClearFilterButton()
    renderLogStats()
    $filterInput.trigger('focus')
  })

  $levelButtons.on('click', function () {
    const val = $(this).data('level') || ''
    logFilter = val
    $filterInput.val(val)
    const filtered = applyLogFilter(lastLogText, logFilter)
    $runLog.text(filtered)
    updateClearFilterButton()
    renderLogStats()
  })

  $tailSelect.on('change', function () {
    tailSize = $(this).val() || '2000'
    const label = tailSize === 'all' ? 'entire log' : `last ${tailSize} lines of the log`
    $tailNotice.html(`<i class="bi bi-info-circle"></i> Showing ${label}`)
    fetchKometaLog()
  })

  $autoScrollToggle.on('change', function () {
    autoScrollEnabled = $(this).is(':checked')
    if (autoScrollEnabled && $runLog[0]) {
      $runLog[0].scrollTop = $runLog[0].scrollHeight
    }
  })

  $downloadLogBtn.on('click', function () {
    const href = '/tail-log?size=all&download=1'
    fetch(href)
      .then(res => res.blob())
      .then(blob => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'meta.log'
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(url)
      })
      .catch(() => showToast('error', 'Failed to download log.'))
  })
  updateClearFilterButton()
  // Ensure we check Kometa status once on page load to catch unclean exits.
  // Keep the run area hidden until Kometa validation completes.
  hideRunCommandSectionUntilValidated()
  checkKometaStatus()
    .catch(() => null)
    .finally(() => {
      if (!document.getElementById('kometa-validation-log')) return
      if (KOMETA_STATUS === 'running') return
      Promise.resolve(runKometaStatusPass(false))
        .finally(() => {
          const stage = getFinalGateState().stage
          if (stage === 'todo' || stage === 'freshness') return
          if (KOMETA_STATUS === 'running' || KOMETA_UPDATING || KOMETA_VALIDATION_IN_PROGRESS) return
          validateKometaRoot({ appendStatus: true })
        })
    })

  if (kometaActionsCollapse) {
    kometaActionsCollapse.addEventListener('show.bs.collapse', () => {
      const stage = getFinalGateState().stage
      if (stage === 'todo' || stage === 'freshness') return
      if (KOMETA_STATUS === 'running') {
        if (typeof bootstrap !== 'undefined' && bootstrap.Collapse) {
          bootstrap.Collapse.getOrCreateInstance(kometaActionsCollapse, { toggle: false }).hide()
        }
        return
      }
      if (!KOMETA_INSTALLED || KOMETA_VALIDATED || KOMETA_VALIDATION_IN_PROGRESS || KOMETA_UPDATING) return
      validateKometaRoot()
    })
  }

  if (runCommandCollapse) {
    runCommandCollapse.addEventListener('show.bs.collapse', () => {
      if (KOMETA_STATUS === 'running') {
        clearRunCommandPlaceholderState()
        return
      }
      if (!KOMETA_VALIDATED) {
        setRunCommandPlaceholderState()
      }
    })
  }

  if (document.getElementById('header-style')) {
    document.getElementById('header-style').addEventListener('change', function () {
      if (headerStyleSubmitting) return
      headerStyleSubmitting = true
      showToast('info', 'Regenerating section style. Please wait for the page to reload...')
      if (typeof showNavigationLoadingOverlay === 'function') {
        showNavigationLoadingOverlay('header-style')
      }
      if (headerStyleWait) {
        headerStyleWait.textContent = 'Regenerating section style and YAML...'
        headerStyleWait.classList.remove('d-none')
      }
      if (headerGrid) {
        headerGrid.querySelectorAll('.header-style-card').forEach(card => {
          card.disabled = true
        })
      }
      if (finalContentWrapper) finalContentWrapper.classList.add('is-updating')
      setTimeout(() => {
        document.getElementById('configForm').submit()
      }, 150)
    })
  }

  const formatLocalTimestamp = (date) => {
    const pad2 = (value) => String(value).padStart(2, '0')
    return [
      date.getFullYear(),
      pad2(date.getMonth() + 1),
      pad2(date.getDate())
    ].join('-') + ' ' + [
      pad2(date.getHours()),
      pad2(date.getMinutes()),
      pad2(date.getSeconds())
    ].join(':')
  }

  const formatRelativeTimestamp = (date, now) => {
    const base = now || new Date()
    let diffMs = base - date
    if (!Number.isFinite(diffMs) || diffMs < 0) diffMs = 0
    const sec = Math.floor(diffMs / 1000)
    if (sec < 60) return 'Just now'
    const min = Math.floor(sec / 60)
    if (min < 60) return `${min}m ago`
    const hr = Math.floor(min / 60)
    const minLeft = min % 60
    if (hr < 24) return `${hr}h ${minLeft}m ago`
    const days = Math.floor(hr / 24)
    const hrLeft = hr % 24
    if (days < 7) return `${days}d ${hrLeft}h ago`
    const weeks = Math.floor(days / 7)
    const dayLeft = days % 7
    if (weeks < 5) return `${weeks}w ${dayLeft}d ago`
    const months = Math.floor(days / 30)
    if (months < 12) return `${months}mo ago`
    const years = Math.floor(days / 365)
    return `${years}y ago`
  }

  const now = new Date()
  document.querySelectorAll('[data-validation-iso]').forEach(el => {
    const raw = el.dataset.validationIso
    if (!raw) return
    const parsed = new Date(raw)
    if (!Number.isNaN(parsed.getTime())) {
      el.textContent = formatLocalTimestamp(parsed)
    }
  })
  document.querySelectorAll('[data-validation-iso-age]').forEach(el => {
    const raw = el.dataset.validationIsoAge
    if (!raw) return
    const parsed = new Date(raw)
    if (!Number.isNaN(parsed.getTime())) {
      el.textContent = formatRelativeTimestamp(parsed, now)
    }
  })

  const validationReasonLabels = {
    missing_credentials: 'Missing credentials',
    missing_plex_validation: 'Plex not validated',
    no_libraries: 'No libraries selected',
    invalid_paths: 'Invalid paths',
    missing_library_defaults: 'Missing library defaults',
    missing_placeholder_imdb: 'Missing placeholder IMDb ID',
    invalid_fields: 'Invalid fields',
    no_webhooks: 'No webhooks configured',
    disabled: 'Disabled',
    missing_settings: 'Settings missing',
    missing_tokens: 'Missing tokens',
    token_invalid: 'Invalid tokens',
    account_locked: 'Account locked',
    validation_error: 'Validation error'
  }

  function formatValidationResult (status, reason, details) {
    if (!status) return ''
    const label = status.charAt(0).toUpperCase() + status.slice(1)
    if (!reason) return label
    const pretty = validationReasonLabels[reason] || reason.replace(/_/g, ' ')
    if (Array.isArray(details) && details.length) {
      return `${label}: ${pretty}: ${details.join(', ')}`
    }
    if (details) {
      return `${label}: ${pretty}: ${details}`
    }
    return `${label}: ${pretty}`
  }

  function updateValidationRow (key, result) {
    const row = document.querySelector(`[data-validation-key="${key}"]`)
    if (!row || !result) return

    const pill = row.querySelector('.validation-status-pill')
    const timestampEl = row.querySelector('.validation-timestamp')
    const ageEl = row.querySelector('.validation-age')
    const status = result.status
    const validatedAt = result.validated_at || ''

    if (pill) {
      pill.classList.remove(
        'rating-mapping-option-via--validated',
        'rating-mapping-option-via--unvalidated',
        'rating-mapping-option-via--neutral'
      )
      if (status === 'validated') {
        pill.classList.add('rating-mapping-option-via--validated')
      } else if (status === 'failed') {
        pill.classList.add('rating-mapping-option-via--unvalidated')
      } else if (status === 'skipped') {
        pill.classList.add('rating-mapping-option-via--neutral')
      }
    }

    if (validatedAt && timestampEl) {
      timestampEl.dataset.validationIso = validatedAt
      const parsed = new Date(validatedAt)
      if (!Number.isNaN(parsed.getTime())) {
        timestampEl.textContent = formatLocalTimestamp(parsed)
      }
    }

    if (validatedAt && ageEl) {
      ageEl.dataset.validationIsoAge = validatedAt
      const parsed = new Date(validatedAt)
      if (!Number.isNaN(parsed.getTime())) {
        ageEl.textContent = formatRelativeTimestamp(parsed, new Date())
      }
    }

    const resultEl = row.querySelector('.validation-result')
    if (resultEl) {
      const resultText = formatValidationResult(status, result.reason, result.details)
      resultEl.textContent = resultText || (status ? status.charAt(0).toUpperCase() + status.slice(1) : '—')
    }
  }

  const validateAllBtn = document.getElementById('validate-all-services')
  const validateAllStatus = document.getElementById('validate-all-status')
  const validateAllStatusTime = document.getElementById('validate-all-status-time')
  const validateAllStatusBulk = document.getElementById('validate-all-status-bulk')
  const validateAllStatusBulkTime = document.getElementById('validate-all-status-bulk-time')
  const validationStatusLastRun = document.getElementById('validation-status-last-run')
  let previouslyBlocked = false
  let previousStatuses = {}

  if (validateAllBtn) {
    document.addEventListener('qs:bulk-validation-start', function () {
      previouslyBlocked = !showYAML
      previousStatuses = {}
      document.querySelectorAll('[data-validation-key]').forEach(row => {
        const key = row.dataset.validationKey
        const pill = row.querySelector('.validation-status-pill')
        if (key && pill) {
          previousStatuses[key] = pill.classList.contains('rating-mapping-option-via--validated')
        }
      })

      if (validateAllStatus) {
        validateAllStatus.classList.add('d-none')
        validateAllStatus.classList.remove('text-danger', 'text-success', 'text-warning')
        validateAllStatus.textContent = 'Validating configured services...'
        validateAllStatus.classList.remove('d-none')
      }
    })

    document.addEventListener('qs:bulk-validation-complete', function (event) {
      const data = (event && event.detail) ? event.detail : {}
      const results = data.results || {}
      const gateTargets = {
        '010-plex': { id: 'plex_valid', datasetKey: 'plexValid', attrKey: 'plex-valid' },
        '020-tmdb': { id: 'tmdb_valid', datasetKey: 'tmdbValid', attrKey: 'tmdb-valid' },
        '025-libraries': { id: 'libs_valid', datasetKey: 'libsValid', attrKey: 'libs-valid' },
        '150-settings': { id: 'sett_valid', datasetKey: 'settValid', attrKey: 'sett-valid' }
      }

      Object.keys(results).forEach(key => updateValidationRow(key, results[key]))
      Object.keys(results).forEach(key => {
        const target = gateTargets[key]
        const result = results[key]
        if (!target || !result) return
        if (result.status === 'validated') {
          setMetaFlag(target.id, target.datasetKey, target.attrKey, true)
        } else if (result.status === 'failed' || result.status === 'skipped') {
          setMetaFlag(target.id, target.datasetKey, target.attrKey, false)
        }
      })

      const summary = data.summary || {}
      const ok = summary.validated || 0
      const failed = summary.failed || 0
      const skipped = summary.skipped || 0
      const summaryUpdatedAt = data.summary_updated_at || new Date().toISOString()
      if (validateAllStatus) {
        validateAllStatus.classList.remove('d-none', 'text-danger', 'text-success', 'text-warning')
        if (failed > 0) {
          validateAllStatus.classList.add('text-danger')
        } else if (skipped > 0) {
          validateAllStatus.classList.add('text-warning')
        } else {
          validateAllStatus.classList.add('text-success')
        }
        const currentSummaryText = `Current. Validated: ${ok} • Failed: ${failed} • Pending: ${skipped}.`
        validateAllStatus.textContent = currentSummaryText
        if (validateAllStatusTime) {
          validateAllStatusTime.dataset.validationIso = summaryUpdatedAt
          const parsed = new Date(summaryUpdatedAt)
          if (!Number.isNaN(parsed.getTime())) {
            validateAllStatusTime.textContent = formatLocalTimestamp(parsed)
          }
        }
        if (validationStatusLastRun) {
          validationStatusLastRun.dataset.validationIso = summaryUpdatedAt
          const parsed = new Date(summaryUpdatedAt)
          if (!Number.isNaN(parsed.getTime())) {
            validationStatusLastRun.textContent = formatLocalTimestamp(parsed)
          }
        }
      }
      if (validateAllStatusBulk) {
        validateAllStatusBulk.classList.remove('d-none')
        validateAllStatusBulk.textContent = data.summary_text || `Completed. Validated: ${ok} • Failed: ${failed} • Skipped: ${skipped}.`
      }
      if (validateAllStatusBulkTime) {
        validateAllStatusBulkTime.dataset.validationIso = summaryUpdatedAt
        const parsed = new Date(summaryUpdatedAt)
        if (!Number.isNaN(parsed.getTime())) {
          validateAllStatusBulkTime.textContent = formatLocalTimestamp(parsed)
        }
      }

      updateValidationGate()
      const anyNewlyValidated = Object.keys(results).some(key => results[key]?.status === 'validated' && !previousStatuses[key])
      if (previouslyBlocked && showYAML) {
        showToast('info', 'Validation complete. Refreshing YAML output...')
        setTimeout(() => window.location.reload(), 300)
        return
      }
      if (anyNewlyValidated) {
        showToast('info', 'Validation updated. Refreshing YAML output...')
        setTimeout(() => window.location.reload(), 300)
      }
    })

    document.addEventListener('qs:bulk-validation-error', function (event) {
      const detail = (event && event.detail) ? event.detail : {}
      const message = detail.message || 'Validate all failed. Please try again.'
      if (validateAllStatus) {
        validateAllStatus.classList.remove('d-none', 'text-success', 'text-warning')
        validateAllStatus.classList.add('text-danger')
        validateAllStatus.textContent = message
      }
    })

    if (window.QSBulkValidation && typeof window.QSBulkValidation.getSummaryState === 'function') {
      const badge = document.getElementById('validation-status-rollup-badge')
      if (badge) {
        const initialSummary = {
          validated: Number(badge.dataset.validated || 0),
          failed: Number(badge.dataset.failed || 0),
          skipped: Number(badge.dataset.skipped || 0)
        }
        const state = window.QSBulkValidation.getSummaryState(initialSummary)
        badge.classList.remove(
          'qs-validation-rollup-badge--unknown',
          'qs-validation-rollup-badge--ok',
          'qs-validation-rollup-badge--warn',
          'qs-validation-rollup-badge--error'
        )
        badge.classList.add(`qs-validation-rollup-badge--${state}`)
      }
    }

    if (getFinalGateState().autoValidate && window.QSBulkValidation && typeof window.QSBulkValidation.run === 'function') {
      window.QSBulkValidation.run({ source: 'final-freshness', silentToast: true })
        .then(() => {
          showToast('info', 'Validate All complete. Refreshing Kometa...')
          setTimeout(() => window.location.reload(), 300)
        })
        .catch(() => {})
    }
  }

  $('#run-now').on('click', function () {
    startKometaCommand(getCurrentRunCommand(), {
      startMode: 'current',
      requireValidated: true,
      startMessage: 'Starting Kometa...\n'
    })
  })

  $('#run-recovery-command').on('click', function () {
    const command = getRecoveryRunCommand()
    const startMode = String($(this).data('start-mode') || 'recovery').trim().toLowerCase() || 'recovery'
    const contextMismatch = String($(this).data('context-mismatch') || '').toLowerCase() === 'true'
    if (contextMismatch) {
      const confirmed = window.confirm('This incomplete run was recorded under a different config than the one currently loaded. Run the recovery command anyway?')
      if (!confirmed) return
    }
    startKometaCommand(command, {
      startMode,
      requireValidated: false,
      startMessage: startMode === 'logged' ? 'Starting last logged Kometa command...\n' : 'Starting Kometa recovery command...\n'
    })
  })

  // Stop button click handler
  $('#stop-now').on('click', function () {
    if (stopModal) {
      stopModal.show()
      return
    }
    performStopKometa()
  })

  $confirmStopBtn.on('click', function () {
    if (stopModal) stopModal.hide()
    performStopKometa()
  })

  function performStopKometa () {
    $confirmStopBtn.prop('disabled', true)
    fetch('/stop-kometa', { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          $('#run-output-log').append(`\n⚠️ ${data.error}`)
          showToast('error', data.error)
        } else {
          const msg = data.message || data.warning || 'Kometa process stopped.'
          $('#run-output-log').append(`\n🟥 ${msg}`)
          if (data.warning) {
            showToast('warning', data.warning)
          } else {
            showToast('success', msg)
          }
        }
        clearInterval(kometaInterval)
        clearInterval(kometaStatusInterval)
        stopProgressPolling()
        if (lastRunProgressPayload) {
          const stoppedPayload = JSON.parse(JSON.stringify(lastRunProgressPayload))
          const stoppedLibrary = stoppedPayload.current_library
          stoppedPayload.current_library = null
          stoppedPayload.phase_current = null
          if (Array.isArray(stoppedPayload.libraries)) {
            stoppedPayload.libraries = stoppedPayload.libraries.map(entry => {
              if (entry.status === 'In progress') {
                return { ...entry, status: 'Stopped' }
              }
              if (stoppedLibrary && entry.name === stoppedLibrary && !['Done', 'Skipped'].includes(entry.status)) {
                return { ...entry, status: 'Stopped' }
              }
              return entry
            })
          }
          lastRunProgressPayload = stoppedPayload
          renderRunProgress(stoppedPayload)
        }
        KOMETA_STATUS = 'not started'
        $('#run-now').prop('disabled', false)
        $('#run-now-label').text('Run Now')
        $('#stop-now').addClass('d-none') // hide stop again
        updateRunNowState()
      })
      .catch(err => {
        console.error('Error stopping Kometa process:', err) // Optional for debugging
        $('#run-output-log').append('\n⚠️ Error stopping process.')
        showToast('error', 'Error stopping Kometa process.')
      })
      .finally(() => {
        $confirmStopBtn.prop('disabled', false)
      })
  }

  function fetchKometaLog () {
    if (logPollingPaused) return

    const logEl = $runLog[0]
    const wasAtBottom = logEl ? (logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 5) : true

    logStatsPollCounter += 1
    const wantStats = (logStatsPollCounter % 5 === 0) || !lastLogStatsTotal
    const statsQuery = wantStats ? '&stats=1' : ''

    fetch(`/tail-log?size=${encodeURIComponent(tailSize)}${statsQuery}`)
      .then(res => res.json())
      .then(data => {
        if (!$runLog.length) return
        if (data.error) {
          $runLog.text(`❌ ${data.error}`)
          updateLogRecency(null)
          return
        }
        lastLogText = data.log || ''
        updateLogRecency(data)
        if (data.stats) {
          lastLogStatsTotal = data.stats
        }
        const filtered = applyLogFilter(lastLogText, logFilter)
        $runLog.text(filtered)
        renderLogStats()
        fetchLogscanAnalysis()
        const shouldStick = autoScrollEnabled || wasAtBottom
        if (shouldStick && logEl) {
          logEl.scrollTop = logEl.scrollHeight
        }
      })
      .catch(err => {
        console.error('Error fetching Kometa log:', err)
        if ($runLog.length) $runLog.append('\n⚠️ Error fetching log.')
      })
  }

  function checkKometaStatus () {
    return fetch('/kometa-status')
      .then(res => res.json())
      .then(data => {
        latestKometaStatusPayload = data || null
        KOMETA_STATUS = data.status || null
        KOMETA_PENDING_START = Boolean(data.pending_start && data.status !== 'running')
        const $updateBtn = $updateKometaBtn
        const $forceUpdate = $forceUpdateToggle
        const $runNow = $('#run-now')
        const $stopNow = $('#stop-now')
        setKometaPrepareRunningState(data.status === 'running')

        // Disable update if Kometa is running or an update is in progress
        const shouldDisableUpdate = (data.status === 'running') || KOMETA_UPDATING
        if (shouldDisableUpdate) {
          const why = KOMETA_UPDATING ? 'Kometa is updating; wait for it to finish.' : 'Kometa is running; stop it before updating.'
          $updateBtn.prop('disabled', true)
            .attr('title', why)
            .tooltip({ placement: 'top' })
          $forceUpdate.prop('disabled', true)
        } else {
          $updateBtn.prop('disabled', false)
            .removeAttr('title')
            .tooltip('dispose')
          $forceUpdate.prop('disabled', false)
        }

        updateRunStatus(data)
        if (typeof window.QS_handleMaintenanceStatus === 'function') {
          window.QS_handleMaintenanceStatus(data)
        }
        if (lastRunProgressPayload && data.status === 'running') {
          renderRunProgress(lastRunProgressPayload)
        }

        if (data.pending_start && data.status !== 'running') {
          applyActiveRunCommandState(
            data.pending_command || activeRunCommandOverride || getRecoveryRunCommand(),
            data.pending_start_mode || activeRunCommandMode || 'recovery'
          )
          const windowLabel = data.maintenance_window ? ` (${data.maintenance_window})` : ''
          const nowLabel = (typeof window.QS_formatTimestamp === 'function') ? window.QS_formatTimestamp() : new Date().toLocaleString()
          const message = `Plex maintenance active${windowLabel} at ${nowLabel}. Kometa will start automatically when it ends.`
          $runNow.prop('disabled', true).html('<i class="bi bi-hourglass-split me-1"></i> Waiting...')
          $stopNow.addClass('d-none')
          $('#run-output').removeClass('d-none')
          if (!$('#run-output-log').text().includes('Plex maintenance')) {
            $('#run-output-log').append(`\n${message}`)
          }
          syncIncompleteRunActions()
          if (kometaStatusInterval) clearInterval(kometaStatusInterval)
          kometaStatusInterval = setInterval(checkKometaStatus, 5000)
          return
        }

        // Lock the Run UI while updating
        if (KOMETA_UPDATING) {
          $runNow.prop('disabled', true).html('<i class="bi bi-hourglass me-1"></i> Updating...')
          $stopNow.prop('disabled', true)
          syncIncompleteRunActions()
          return // don't do the rest while we're mid-update
        }

        // Handle Kometa process states
        if (data.status === 'running') {
          applyActiveRunCommandState(
            data.active_command || activeRunCommandOverride || getCurrentRunCommand(),
            data.start_mode || activeRunCommandMode || 'current'
          )
          KOMETA_PENDING_START = false
          finalLogscanAnalyzeTriggered = false
          $('#incomplete-run-alert').addClass('d-none')
          // Kometa is actively running → keep Run disabled, allow Stop
          revealRunCommandSection()
          $runNow.prop('disabled', true).html('<i class="bi bi-play-fill me-1"></i> Run Now')
          $stopNow.removeClass('d-none').prop('disabled', false)
          $('#run-output').removeClass('d-none')
          syncIncompleteRunActions()
          startPollingIfNeeded()
          return
        }

        // If we reach here, it's either "done" or "not started"
        if (typeof kometaInterval !== 'undefined' && kometaInterval) clearInterval(kometaInterval)
        if (typeof kometaStatusInterval !== 'undefined' && kometaStatusInterval) clearInterval(kometaStatusInterval)
        stopProgressPolling()
        clearRunProgress(true)
        clearActiveRunCommandState()
        try { buildCommand() } catch (_) {}

        $runNow.html('<i class="bi bi-play-fill me-1"></i> Run Now')
        $stopNow.addClass('d-none').prop('disabled', false)
        updateRunNowState()

        if (data.status === 'done') {
          KOMETA_PENDING_START = false
          if (!finalLogscanAnalyzeTriggered) {
            finalLogscanAnalyzeTriggered = true
            fetchLogscanAnalysis(true)
          }
          if (data.return_code === 0) {
            $('#run-output-log').append('\n✅ Kometa finished successfully.')
          } else {
            $('#run-output-log').append(`\n⚠️ Kometa exited with code ${data.return_code}. Check logs for details.`)
          }
        } else if (data.status === 'not started') {
          KOMETA_PENDING_START = false
          $('#run-output-log').append('\n🟥 Kometa is not running.')
        }
      })
      .catch(err => {
        KOMETA_PENDING_START = false
        console.error('Error checking Kometa status:', err)
        $('#run-output-log').append('\n⚠️ Failed to check Kometa status.')
      })
  }

  function isValidTimesFormat (timesStr) {
    if (!timesStr.trim()) return false
    const times = timesStr.split('|')
    const timeRegex = /^([01]\d|2[0-3]):[0-5]\d$/
    return times.every(t => timeRegex.test(t.trim()))
  }

  function toggleTimesInputVisibility (mainOption) {
    const timesContainer = $('#times-input-container')
    if (mainOption === '--times') {
      timesContainer.removeClass('d-none')
    } else {
      timesContainer.addClass('d-none')
      $('#times-error').addClass('d-none')
    }
  }

  function getMaintenanceWindow () {
    const windowStr = $('#plex-maintenance-window').data('window') // e.g., "03:00–05:00"
    if (!windowStr || !windowStr.includes('–')) return null

    const [start, end] = windowStr.split('–').map(t => t.trim())
    return { start, end } // Strings in "HH:MM" format
  }

  function isTimeWithinRange (time, rangeStart, rangeEnd) {
    const toMinutes = t => {
      const [h, m] = t.split(':').map(Number)
      return h * 60 + m
    }
    const timeMin = toMinutes(time)
    return timeMin >= toMinutes(rangeStart) && timeMin < toMinutes(rangeEnd)
  }

  function checkMaintenanceWarning (mainOption) {
    const warningBox = $('#times-warning')
    const maintenance = getMaintenanceWindow()
    warningBox.addClass('d-none')

    if (!maintenance) return

    if (mainOption === '') {
      const defaultTime = '05:00'
      if (isTimeWithinRange(defaultTime, maintenance.start, maintenance.end)) {
        warningBox.removeClass('d-none')
      }
    }

    if (mainOption === '--times') {
      const timesInput = $('#times-input').val().trim()
      if (isValidTimesFormat(timesInput)) {
        const times = timesInput.split('|').map(t => t.trim())
        const overlaps = times.some(t => isTimeWithinRange(t, maintenance.start, maintenance.end))
        if (overlaps) {
          warningBox.removeClass('d-none')
        }
      }
    }
  }
})
