/* global $, bootstrap, showToast */

// Global flag so other handlers know an update is in progress
let KOMETA_UPDATING = false
let KOMETA_VALIDATED = false
let KOMETA_VALIDATION_IN_PROGRESS = false
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
  const plexValid = $('#plex_valid').data('plex-valid') === 'True'
  const tmdbValid = $('#tmdb_valid').data('tmdb-valid') === 'True'
  const libsValid = $('#libs_valid').data('libs-valid') === 'True'
  const settValid = $('#sett_valid').data('sett-valid') === 'True'
  const yamlValid = $('#yaml_valid').data('yaml-valid') === 'True'
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
  const $yamlOutput = $('#final-yaml')
  const $yamlLineCount = $('#yaml-line-count')

  const showYAML = plexValid && tmdbValid && libsValid && settValid && yamlValid

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
          $logBox.append('✅ Kometa root validated successfully.\n')
          if (res.kometa_version) $logBox.append(`📦 Local Kometa version: ${res.kometa_version}\n`)

          if (res.remote_version && res.local_version) {
            if (res.kometa_update_available) {
              $logBox.append(`⬆️ Update available: ${res.local_version} → ${res.remote_version}\n`)
              $('#kometa-update-box').removeClass('d-none')
              $('#kometa-local-version').text(res.local_version)
              $('#kometa-remote-version').text(res.remote_version)
            } else {
              $logBox.append('✅ Kometa is up to date.\n')
              $('#kometa-update-box').addClass('d-none')
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
          KOMETA_VALIDATED = false
          hideRunCommandSectionUntilValidated()
          $runNow.prop('disabled', true)
        }

        if ($spinner.length) $spinner.hide()
      },
      error: (xhr) => {
        const msg = xhr?.responseJSON?.error || 'The Kometa root path is invalid or inaccessible. Please try again.'
        $logBox.append(`❌ ${msg}\n`)
        KOMETA_VALIDATED = false
        hideRunCommandSectionUntilValidated()
        $runNow.prop('disabled', true)
        if ($spinner.length) $spinner.hide()
      },
      complete: () => {
        KOMETA_VALIDATION_IN_PROGRESS = false
        updateRunNowState()
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

  function callUpdateKometa () {
    if (KOMETA_STATUS === 'running') {
      showToast('info', 'Kometa is currently running; update skipped.')
      return
    }

    const $btn = $('#update-kometa-btn')
    const $logBox = $('#kometa-validation-log')
    const $runNow = $('#run-now')
    const $stopNow = $('#stop-now')
    const $runBox = $('#run-command-box')
    const branch = $btn.data('branch') || 'master'

    KOMETA_UPDATING = true
    KOMETA_VALIDATED = false
    hideRunCommandSectionUntilValidated()
    const prevRunNowHtml = $runNow.html()
    const prevRunNowDisabled = $runNow.prop('disabled')

    $runBox.addClass('opacity-50 position-relative')
    $runNow.prop('disabled', true).html('<i class="bi bi-hourglass me-1"></i> Updating...')
    $stopNow.prop('disabled', true)

    $btn.prop('disabled', true).html('<i class="bi bi-arrow-repeat me-1"></i> Updating...')
    $logBox.append('\n🔧 Initializing/Updating Kometa...\n')
    if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight

    // progress heartbeat
    const startTs = Date.now()
    showToast('info', 'Still working on Kometa... (0 seconds elapsed)', 10000)
    const heartbeatId = setInterval(() => {
      const secs = Math.floor((Date.now() - startTs) / 1000)
      showToast('info', `Still working on Kometa... (${secs} seconds elapsed)`, 10000)
    }, 30000) // every 30s

    const cleanupUI = () => {
      clearInterval(heartbeatId)
      KOMETA_UPDATING = false
      $runBox.removeClass('opacity-50 position-relative')
      $runNow.prop('disabled', prevRunNowDisabled).html(prevRunNowHtml)
      $stopNow.prop('disabled', false)
      $btn.prop('disabled', false).html('🔄 Update Kometa Now')
      updateRunNowState()
    }

    fetch('/update-kometa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ branch })
    })
      .then(async res => {
        const data = await res.json()
        if (res.status === 409) {
          showToast('warning', data.error || 'Kometa is running; stop it before updating.')
          $logBox.append(`❌ ${data.error || 'Update blocked: Kometa running.'}\n`)
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
          const elapsed = formatElapsed(Date.now() - startTs)
          showToast('success', `Kometa update completed in ${elapsed}.`)
          $logBox.append('✅ Kometa update completed successfully.\n')
          if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight
          validateKometaRoot()
        } else if (!data.blocked) {
          showToast('error', data.error || 'Kometa update failed.')
          $logBox.append('❌ Kometa update failed.\n')
          validateKometaRoot()
          if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight
        }
      })
      .catch(err => {
        console.error(err)
        showToast('error', 'Error during Kometa update.')
        $logBox.append('❌ Error occurred during Kometa update.\n')
        if ($logBox[0]) $logBox[0].scrollTop = $logBox[0].scrollHeight
      })
      .finally(() => {
        cleanupUI()
      })
  }

  // Kometa Update Button Click
  $('#update-kometa-btn').on('click', callUpdateKometa)

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
    const keys = ['debug', 'info', 'warning', 'error', 'critical', 'trace']
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
      document.getElementById('configForm').submit()
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
          return
        }
        lastLogText = data.log || ''
        if (data.stats) {
          lastLogStatsTotal = data.stats
        }
        const filtered = applyLogFilter(lastLogText, logFilter)
        $runLog.text(filtered)
        renderLogStats()
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
        const $updateBtn = $('#update-kometa-btn')
        const $runNow = $('#run-now')
        const $stopNow = $('#stop-now')

        // Disable update if Kometa is running or an update is in progress
        const shouldDisableUpdate = (data.status === 'running') || KOMETA_UPDATING
        if (shouldDisableUpdate) {
          const why = KOMETA_UPDATING ? 'Kometa is updating; wait for it to finish.' : 'Kometa is running; stop it before updating.'
          $updateBtn.prop('disabled', true)
            .attr('title', why)
            .tooltip({ placement: 'top' })
        } else {
          $updateBtn.prop('disabled', false)
            .removeAttr('title')
            .tooltip('dispose')
        }

        // Lock the Run UI while updating
        if (KOMETA_UPDATING) {
          $runNow.prop('disabled', true).html('<i class="bi bi-hourglass me-1"></i> Updating...')
          $stopNow.prop('disabled', true)
          return // don’t do the rest while we’re mid-update
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
