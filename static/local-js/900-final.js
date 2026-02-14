/* global $, bootstrap, showToast */

// Global flag so other handlers know an update is in progress
let KOMETA_UPDATING = false
let KOMETA_VALIDATED = false
let KOMETA_VALIDATION_IN_PROGRESS = false
let KOMETA_UPDATE_AVAILABLE = false
let KOMETA_INSTALLED = false
// Polling handles (hoist to top so all handlers see them safely)
let kometaInterval = null
let kometaStatusInterval = null
let kometaPollingStarted = false
let autoScrollEnabled = true
let tailSize = '2000'
let KOMETA_STATUS = null
let logPollingPaused = false
let logFilter = ''
let lastLogText = ''
let lastLogStatsTotal = null
let logStatsPollCounter = 0
let lastLogscanPayload = null
let logscanPollCounter = 0

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
  const headerSelect = document.getElementById('header-style')
  const headerPreview = document.getElementById('header-style-preview')
  const headerGrid = document.getElementById('header-style-grid')
  const headerGridCollapse = document.getElementById('header-style-grid-collapse')
  const headerStyleWait = document.getElementById('header-style-wait')
  const finalContentWrapper = document.getElementById('final-content-wrapper')
  const headerGridStatus = document.getElementById('header-style-grid-status')
  const headerGridProgress = document.getElementById('header-style-grid-progress')
  const headerGridProgressBar = headerGridProgress ? headerGridProgress.querySelector('.progress-bar') : null

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

  function updateValidationGate () {
    const plexValid = readMetaFlag('plex_valid', 'plexValid', 'plex-valid')
    const tmdbValid = readMetaFlag('tmdb_valid', 'tmdbValid', 'tmdb-valid')
    const libsValid = readMetaFlag('libs_valid', 'libsValid', 'libs-valid')
    const settValid = readMetaFlag('sett_valid', 'settValid', 'sett-valid')
    const yamlValid = readMetaFlag('yaml_valid', 'yamlValid', 'yaml-valid')

    showYAML = plexValid && tmdbValid && libsValid && settValid && yamlValid

    const validationMessages = []
    if (!plexValid) validationMessages.push('Plex settings have not been validated successfully...<br>')
    if (!tmdbValid) validationMessages.push('TMDb settings have not been validated successfully...<br>')
    if (!libsValid) validationMessages.push('Libraries page settings have not been validated successfully...<br>')
    if (!settValid) validationMessages.push('Settings page values have likely been skipped...<br>')

    $('#run-now').prop('disabled', true)
    $('#run-now-label').text('Run Now')

    if (!showYAML) {
      $('#validation-messages').html(validationMessages.join('<br>')).show()
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
  }

  updateYamlLineCount()
  $yamlOutput.on('input', updateYamlLineCount)

  async function updateHeaderPreview (fontValue) {
    if (!headerPreview) return
    const font = fontValue || (headerSelect ? headerSelect.value : '')
    headerPreview.textContent = 'Loading preview...'
    try {
      const res = await fetch(`/header-style-preview?font=${encodeURIComponent(font || '')}`)
      const data = await res.json()
      if (!res.ok || !data.success) {
        throw new Error(data.message || 'Preview unavailable.')
      }
      headerPreview.textContent = data.preview || ''
    } catch (err) {
      headerPreview.textContent = 'Preview unavailable.'
    }
  }

  if (headerSelect && headerPreview) {
    updateHeaderPreview(headerSelect.value)
    headerSelect.addEventListener('change', () => updateHeaderPreview(headerSelect.value))
  }

  function normalizeFontName (value) {
    return String(value || '').trim()
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
      headerGrid.innerHTML = '<div class="text-muted small">No fonts available.</div>'
      updateGridStatus('')
      updateGridProgress(0, 0)
      return
    }

    updateGridStatus(`Loading ${fonts.length} font previews...`)
    updateGridProgress(0, fonts.length)

    headerGrid.innerHTML = ''
    fonts.forEach(font => {
      const card = document.createElement('button')
      card.type = 'button'
      card.className = 'header-style-card'
      card.dataset.font = font
      card.innerHTML = `
        <div class="header-style-card-title">${font.replace(/_/g, ' ')}</div>
        <pre class="header-style-card-preview">Loading...</pre>
      `
      card.addEventListener('click', () => {
        if (headerSelect) {
          headerSelect.value = font
          headerSelect.dispatchEvent(new Event('change'))
        }
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
    const modeFlags = ['--operations-only', '--collections-only', '--playlists-only', '--overlays-only']
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

  function updateRunNowState () {
    const $runNow = $('#run-now')
    if (!$runNow.length) return

    if (!showYAML || KOMETA_VALIDATION_IN_PROGRESS || KOMETA_UPDATING || KOMETA_STATUS === 'running' || !KOMETA_VALIDATED) {
      $runNow.prop('disabled', true)
      return
    }

    if (!isRunCommandValid()) {
      $runNow.prop('disabled', true)
      return
    }

    $runNow.prop('disabled', false)
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
        return false
      } else {
        $('#divider-error').addClass('d-none')
        cli += ` --divider "${dividerValue}"`
      }
    }

    runCmdOutput.text(cli)
    updateRunNowState()
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

  function validateKometaRoot () {
    if (KOMETA_VALIDATION_IN_PROGRESS) return
    KOMETA_VALIDATION_IN_PROGRESS = true
    const $logBox = $('#kometa-validation-log')
    const $spinner = $('#spinner_validate')
    const $runNow = $('#run-now')
    const $out = $('#run-command-output')

    const configName = $out.data('config-filename')
    const defaultRootPosix = ($out.data('kometa-root-default') || '').toString().trim()
    const defaultRootDisplay = ($out.data('kometa-root-default-display') || defaultRootPosix)

    $logBox.text(
      '🔄 Please wait while we validate your Kometa installation...\n' +
      'This may take a few seconds as we verify the folder structure, Python environment, and Kometa information.\n\n'
    )
    if ($spinner.length) $spinner.show()
    $runNow.prop('disabled', true)

    $.ajax({
      type: 'POST',
      url: '/validate-kometa-root',
      contentType: 'application/json',
      // ✅ send the *normalized* path to the backend
      data: JSON.stringify({ path: defaultRootPosix, config_name: configName }),
      success: (res) => {
        if (Array.isArray(res.log)) res.log.forEach(line => $logBox.append(`${line}\n`))

        if (res.success) {
          KOMETA_INSTALLED = true
          $logBox.append('✅ Kometa root validated successfully.\n')
          if (res.kometa_version) $logBox.append(`📦 Local Kometa version: ${res.kometa_version}\n`)

          if (res.remote_version && res.local_version) {
            const hadUpdate = KOMETA_UPDATE_AVAILABLE
            if (res.kometa_update_available) {
              KOMETA_UPDATE_AVAILABLE = true
              $logBox.append(`⬆️ Update available: ${res.local_version} → ${res.remote_version}\n`)
              $('#kometa-update-box').removeClass('d-none')
              $('#kometa-local-version').text(res.local_version)
              $('#kometa-remote-version').text(res.remote_version)
              syncUpdateButtonLabel()
              if (!hadUpdate) {
                showToast('warning', `Kometa update available: ${res.local_version} → ${res.remote_version}.`)
              }
            } else {
              KOMETA_UPDATE_AVAILABLE = false
              $logBox.append('✅ Kometa is up to date.\n')
              $('#kometa-update-box').addClass('d-none')
              syncUpdateButtonLabel()
            }
          }

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
          const allValid =
            $('#plex_valid').data('plex-valid') === 'True' &&
            $('#tmdb_valid').data('tmdb-valid') === 'True' &&
            $('#libs_valid').data('libs-valid') === 'True' &&
            $('#sett_valid').data('sett-valid') === 'True' &&
            $('#yaml_valid').data('yaml-valid') === 'True'

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
        } else {
          KOMETA_INSTALLED = false
          KOMETA_VALIDATED = false
          hideRunCommandSectionUntilValidated()
          $runNow.prop('disabled', true)
        }

        if ($spinner.length) $spinner.hide()
      },
      error: (xhr) => {
        const msg = xhr?.responseJSON?.error || 'The Kometa root path is invalid or inaccessible. Please try again.'
        $logBox.append(`❌ ${msg}\n`)
        const lowered = String(msg || '').toLowerCase()
        if (lowered.includes('kometa.py not found') || lowered.includes('requirements.txt not found')) {
          KOMETA_INSTALLED = false
        }
        KOMETA_VALIDATED = false
        hideRunCommandSectionUntilValidated()
        $runNow.prop('disabled', true)
        if ($spinner.length) $spinner.hide()
      },
      complete: () => {
        KOMETA_VALIDATION_IN_PROGRESS = false
        updateRunNowState()
        syncUpdateButtonLabel()
      }
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

  $('#copy-command').on('click', function () {
    const command = $('#run-command-output').text().trim()
    if (!command || command.startsWith('⚠️')) return

    // Try clipboard API
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(command).then(() => {
        showCopySuccess()
      }).catch(() => {
        fallbackCopy(command)
      })
    } else {
      fallbackCopy(command)
    }

    function showCopySuccess () {
      $('#copy-icon').removeClass('bi-clipboard').addClass('bi-check2')
      $('#copy-text').text('Copied')
      setTimeout(() => {
        $('#copy-icon').removeClass('bi-check2').addClass('bi-clipboard')
        $('#copy-text').text('Copy')
      }, 1500)
    }

    function fallbackCopy (text) {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'absolute'
      textarea.style.left = '-9999px'
      document.body.appendChild(textarea)
      textarea.select()

      try {
        const success = document.execCommand('copy')
        if (success) {
          showCopySuccess()
        } else {
          showToast('error', 'Copy failed. Please copy manually.')
        }
      } catch (err) {
        showToast('error', 'Copy failed. Please copy manually.')
      }

      document.body.removeChild(textarea)
    }
  })

  function hideRunCommandSectionUntilValidated () {
    const box = $('#run-command-box')
    box.removeClass('fade-in').addClass('d-none') // Hide instantly
    $('#run-now').prop('disabled', true).html('<i class="bi bi-hourglass-split me-1"></i> Waiting...')
  }

  function showRunCommandSectionAfterValidated () {
    const box = $('#run-command-box')

    box.removeClass('d-none') // Reveal element (opacity still 0)
    setTimeout(() => {
      box.addClass('fade-in') // Let browser register change, then fade in
    }, 10)

    $('#run-now').html('<i class="bi bi-play-fill me-1"></i> Run Now')
    try { buildCommand() } catch (_) {}
    updateRunNowState()
  }
  function startPollingIfNeeded () {
    if (kometaPollingStarted) return
    kometaPollingStarted = true
    if (kometaInterval) clearInterval(kometaInterval)
    if (kometaStatusInterval) clearInterval(kometaStatusInterval)
    fetchKometaLog()
    kometaInterval = setInterval(fetchKometaLog, 3000)
    kometaStatusInterval = setInterval(checkKometaStatus, 5000)
  }

  function getUpdateButtonLabel () {
    const force = $forceUpdateToggle.is(':checked')
    const label = force
      ? (KOMETA_INSTALLED ? 'Force Update Kometa' : 'Force Install Kometa')
      : (KOMETA_INSTALLED
          ? (KOMETA_UPDATE_AVAILABLE ? 'Update Available' : 'Check for Kometa Updates')
          : 'Install Kometa')
    return `<i class="bi bi-arrow-clockwise me-1"></i> ${label}`
  }

  function syncUpdateButtonLabel () {
    if ($updateKometaBtn.length) {
      $updateKometaBtn.html(getUpdateButtonLabel())
    }
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
    const branch = $btn.data('branch') || 'master'
    const forceUpdate = $forceUpdateToggle.is(':checked')

    KOMETA_UPDATING = true
    KOMETA_VALIDATED = false
    hideRunCommandSectionUntilValidated()
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
      KOMETA_UPDATING = false
      $runBox.removeClass('opacity-50 position-relative')
      $runNow.prop('disabled', prevRunNowDisabled).html(prevRunNowHtml)
      $stopNow.prop('disabled', false)
      $btn.prop('disabled', false)
      $forceUpdateToggle.prop('disabled', false)
      syncUpdateButtonLabel()
      updateRunNowState()
      if (postUpdateLabel) {
        $btn.html(postUpdateLabel)
        setTimeout(syncUpdateButtonLabel, 6000)
      }
    }

    fetch('/update-kometa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ branch, force: forceUpdate })
    })
      .then(async res => {
        const data = await res.json()
        if (res.status === 409) {
          showToast('warning', data.error || 'Kometa is running; stop it before updating.')
          $logBox.append(`${data.error || 'Update blocked: Kometa running.'}\n`)
          if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight
          return { success: false, log: data.log || [], blocked: true }
        }
        return data
      })
      .then(data => {
        if (!data) return
        if (Array.isArray(data.log)) {
          data.log.forEach(line => $logBox.append(`${line}\n`))
          if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight
        }
        if (data.success) {
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
          validateKometaRoot()
        } else if (!data.blocked) {
          showToast('error', data.error || 'Kometa update failed.')
          $logBox.append('Kometa update failed.\n')
          validateKometaRoot()
          if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight
        }
      })
      .catch(err => {
        console.error(err)
        showToast('error', 'Error during Kometa update.')
        $logBox.append('Error occurred during Kometa update.\n')
        if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight
      })
      .finally(() => {
        cleanupUI()
      })
  }

  // Kometa Update Button Click
  $updateKometaBtn.on('click', callUpdateKometa)
  $forceUpdateToggle.on('change', function () {
    if (!KOMETA_UPDATING) syncUpdateButtonLabel()
  })
  syncUpdateButtonLabel()

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
    mem: { system: [], kometa: [] }
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

  function renderRunSparklines () {
    if (!$runStatusSparklines.length) return
    const hasData = runSparkState.cpu.system.length || runSparkState.cpu.kometa.length ||
      runSparkState.mem.system.length || runSparkState.mem.kometa.length
    $runStatusSparklines.toggleClass('d-none', !hasData)
    if (!hasData) {
      if ($runSparkCpuSystem.length) $runSparkCpuSystem.attr('points', '')
      if ($runSparkCpuKometa.length) $runSparkCpuKometa.attr('points', '')
      if ($runSparkMemSystem.length) $runSparkMemSystem.attr('points', '')
      if ($runSparkMemKometa.length) $runSparkMemKometa.attr('points', '')
      return
    }
    if ($runSparkCpuSystem.length) $runSparkCpuSystem.attr('points', buildSparklinePoints(runSparkState.cpu.system))
    if ($runSparkCpuKometa.length) $runSparkCpuKometa.attr('points', buildSparklinePoints(runSparkState.cpu.kometa))
    if ($runSparkMemSystem.length) $runSparkMemSystem.attr('points', buildSparklinePoints(runSparkState.mem.system))
    if ($runSparkMemKometa.length) $runSparkMemKometa.attr('points', buildSparklinePoints(runSparkState.mem.kometa))
  }

  function resetRunSparklines () {
    runSparkState.cpu.system = []
    runSparkState.cpu.kometa = []
    runSparkState.mem.system = []
    runSparkState.mem.kometa = []
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
    pushSparkValue(runSparkState.cpu.system, cpuSystem)
    pushSparkValue(runSparkState.cpu.kometa, cpuKometa)
    pushSparkValue(runSparkState.mem.system, memSystem)
    pushSparkValue(runSparkState.mem.kometa, memKometa)
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
      $runStatusTimer.text(`Running since: ${startedAt} • Elapsed: ${elapsed || 'n/a'}`)
      $runStatusMetrics.text(`Kometa: ${cpuText} CPU • ${memRss} (${memPct}) | System: ${sysCpu} CPU • ${sysUsed} / ${sysTotal} (${sysPct})`)
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
  }

  function fetchLogscanAnalysis () {
    if (!$logscanPanel.length) return
    logscanPollCounter += 1
    const shouldFetch = (logscanPollCounter % 5 === 0) || !lastLogscanPayload
    if (!shouldFetch) return

    fetch('/logscan/analyze')
      .then(res => res.json())
      .then(data => {
        lastLogscanPayload = data
        renderLogscan(data)
      })
      .catch(err => {
        console.error('Error fetching logscan analysis:', err)
        $logscanRecommendations.html('<div class="text-muted">Logscan unavailable.</div>')
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

  // First-run: validate Kometa root once the log box is present.
  if (document.getElementById('kometa-validation-log')) {
    validateKometaRoot()
  }

  if (document.getElementById('header-style')) {
    document.getElementById('header-style').addEventListener('change', function () {
      showToast('info', 'Updating header style. Please wait for the page to reload...')
      if (headerStyleWait) headerStyleWait.classList.remove('d-none')
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
  }

  const validateAllBtn = document.getElementById('validate-all-services')
  const validateAllSpinner = document.getElementById('validate-all-spinner')
  const validateAllStatus = document.getElementById('validate-all-status')
  if (validateAllBtn) {
    validateAllBtn.addEventListener('click', function () {
      if (validateAllBtn.disabled) return
      validateAllBtn.disabled = true
      if (validateAllSpinner) validateAllSpinner.classList.remove('d-none')
      if (validateAllStatus) {
        validateAllStatus.classList.add('d-none', 'text-danger')
        validateAllStatus.classList.remove('text-success')
        validateAllStatus.textContent = 'Validating configured services...'
        validateAllStatus.classList.remove('d-none')
      }

      fetch('/validate_all_services', { method: 'POST' })
        .then(async (res) => {
          let data = null
          try {
            data = await res.json()
          } catch (err) {
            data = null
          }

          if (!res.ok) {
            const message = (data && (data.message || data.error)) || `Request failed (${res.status}).`
            throw new Error(message)
          }

          if (!data || !data.success) {
            throw new Error((data && (data.message || data.error)) || 'Validation failed. Please try again.')
          }

          const results = data.results || {}
          const gateTargets = {
            '010-plex': { id: 'plex_valid', datasetKey: 'plexValid', attrKey: 'plex-valid' },
            '020-tmdb': { id: 'tmdb_valid', datasetKey: 'tmdbValid', attrKey: 'tmdb-valid' }
          }
          Object.keys(results).forEach(key => updateValidationRow(key, results[key]))
          Object.keys(results).forEach(key => {
            const target = gateTargets[key]
            const result = results[key]
            if (!target || !result) return
            if (result.status === 'validated') {
              setMetaFlag(target.id, target.datasetKey, target.attrKey, true)
            } else if (result.status === 'failed') {
              setMetaFlag(target.id, target.datasetKey, target.attrKey, false)
            }
          })
          const summary = data.summary || {}
          const ok = summary.validated || 0
          const failed = summary.failed || 0
          const skipped = summary.skipped || 0
          showToast('info', `Validate all complete. Validated: ${ok} • Failed: ${failed} • Skipped: ${skipped}`)
          if (validateAllStatus) {
            const labelForKey = (key) => {
              const row = document.querySelector(`[data-validation-key="${key}"]`)
              const labelEl = row ? row.querySelector('.validation-status-pill') : null
              const label = labelEl ? labelEl.textContent.trim() : ''
              return label || key
            }
            const failedKeys = Object.keys(results).filter(key => results[key]?.status === 'failed')
            const failedLabels = failedKeys.map(labelForKey).filter(Boolean)
            const failedDetail = failedLabels.length ? ` Failed: ${failedLabels.join(', ')}.` : ''
            const skippedKeys = Object.keys(results).filter(key => results[key]?.status === 'skipped' && results[key]?.reason === 'missing_credentials')
            const skippedLabels = skippedKeys.map(labelForKey).filter(Boolean)
            const skippedDetail = skippedLabels.length ? ` Skipped (missing credentials): ${skippedLabels.join(', ')}.` : ''
            validateAllStatus.classList.remove('d-none', 'text-danger')
            validateAllStatus.classList.add('text-success')
            validateAllStatus.textContent = `Completed. Validated: ${ok} • Failed: ${failed} • Skipped: ${skipped}.${failedDetail}${skippedDetail}`
          }
          updateValidationGate()
        })
        .catch((err) => {
          const message = err && err.message ? err.message : 'Validate all failed. Please try again.'
          showToast('error', message)
          if (validateAllStatus) {
            validateAllStatus.classList.remove('d-none', 'text-success')
            validateAllStatus.classList.add('text-danger')
            validateAllStatus.textContent = message
          }
        })
        .finally(() => {
          validateAllBtn.disabled = false
          if (validateAllSpinner) validateAllSpinner.classList.add('d-none')
        })
    })
  }

  $('#run-now').on('click', function () {
    if (KOMETA_UPDATING) {
      showToast('warning', 'Kometa is updating. Please wait for it to finish before running.')
      return
    }

    if (KOMETA_VALIDATION_IN_PROGRESS) {
      showToast('info', 'Kometa validation is still running. Please wait.')
      return
    }

    if (!KOMETA_VALIDATED) {
      showToast('warning', 'Kometa has not been validated yet.')
      return
    }

    const command = $('#run-command-output').text().trim()
    if (!command || command.startsWith('⚠️')) {
      showToast('error', 'Cannot run invalid command.')
      return
    }

    $('#run-now').prop('disabled', true)
    $('#run-now-label').text('Running...')
    $('#stop-now').removeClass('d-none') // SHOW stop button here
    $('#run-output').removeClass('d-none')
    $('#run-output-log').text('Starting Kometa...\n')

    fetch('/start-kometa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command })
    })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          $('#run-output-log').text(`❌ ${data.error}`)
          $('#run-now').prop('disabled', false)
          $('#run-now-label').text('Run Now')
          $('#stop-now').addClass('d-none')
          return
        }

        // ✅ Delay polling slightly to allow Kometa to start
        setTimeout(() => {
          kometaPollingStarted = false
          startPollingIfNeeded()
        }, 5500) // <-- 1.5 second delay
      })
  })

  // Stop button click handler
  $('#stop-now').on('click', function () {
    fetch('/stop-kometa', { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          $('#run-output-log').append(`\n⚠️ ${data.error}`)
        } else {
          $('#run-output-log').append('\n🟥 Kometa process stopped.')
        }
        clearInterval(kometaInterval)
        clearInterval(kometaStatusInterval)
        $('#run-now').prop('disabled', false)
        $('#run-now-label').text('Run Now')
        $('#stop-now').addClass('d-none') // hide stop again
      })
      .catch(err => {
        console.error('Error stopping Kometa process:', err) // Optional for debugging
        $('#run-output-log').append('\n⚠️ Error stopping process.')
      })
  })

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
        KOMETA_STATUS = data.status || null
        const $updateBtn = $updateKometaBtn
        const $forceUpdate = $forceUpdateToggle
        const $runNow = $('#run-now')
        const $stopNow = $('#stop-now')

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

        // Lock the Run UI while updating
        if (KOMETA_UPDATING) {
          $runNow.prop('disabled', true).html('<i class="bi bi-hourglass me-1"></i> Updating...')
          $stopNow.prop('disabled', true)
          return // don't do the rest while we're mid-update
        }

        // Handle Kometa process states
        if (data.status === 'running') {
          // Kometa is actively running → keep Run disabled, allow Stop
          $runNow.prop('disabled', true).html('<i class="bi bi-play-fill me-1"></i> Run Now')
          $stopNow.removeClass('d-none').prop('disabled', false)
          $('#run-output').removeClass('d-none')
          startPollingIfNeeded()
          fetchKometaLog()
          return
        }

        // If we reach here, it's either "done" or "not started"
        if (typeof kometaInterval !== 'undefined' && kometaInterval) clearInterval(kometaInterval)
        if (typeof kometaStatusInterval !== 'undefined' && kometaStatusInterval) clearInterval(kometaStatusInterval)

        $runNow.html('<i class="bi bi-play-fill me-1"></i> Run Now')
        $stopNow.addClass('d-none').prop('disabled', false)
        updateRunNowState()

        if (data.status === 'done') {
          if (data.return_code === 0) {
            $('#run-output-log').append('\n✅ Kometa finished successfully.')
          } else {
            $('#run-output-log').append(`\n⚠️ Kometa exited with code ${data.return_code}. Check logs for details.`)
          }
        } else if (data.status === 'not started') {
          $('#run-output-log').append('\n🟥 Kometa is not running.')
        }
      })
      .catch(err => {
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
