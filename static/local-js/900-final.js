/* global $, bootstrap, showToast */

$(document).ready(function () {
  const plexValid = $('#plex_valid').data('plex-valid') === 'True'
  const tmdbValid = $('#tmdb_valid').data('tmdb-valid') === 'True'
  const libsValid = $('#libs_valid').data('libs-valid') === 'True'
  const settValid = $('#sett_valid').data('sett-valid') === 'True'
  const yamlValid = $('#yaml_valid').data('yaml-valid') === 'True'

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
      label: 'Run Now',
      description: 'If you want Kometa to run immediately rather than waiting until 5AM, set this flag'
    },
    '--run-libraries': {
      label: 'Run Specific Libraries',
      description: 'Run Kometa only on selected libraries.'
    },
    '--operations-only': {
      label: 'Only Operations',
      description: 'Only perform operations (e.g., rating/poster updates).'
    },
    '--collections-only': {
      label: 'Only Collections',
      description: 'Only build collections.'
    },
    '--playlists-only': {
      label: 'Only Playlists',
      description: 'Only build playlists, skip everything else.'
    },
    '--overlays-only': {
      label: 'Only Overlays',
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
      label: 'Log Requests',
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
      label: 'Read-Only Mode',
      description: 'Kometa reads in and then writes out a properly formatted version of your config.yml on each run;this makes the formatting consistent and ensures that you have visibility into new settings that get added. If you want to disable this behavior and tell Kometa to leave your config.yml as-is, use this flag.'
    },
    '--low-priority': {
      label: 'Low Priority Mode',
      description: 'Run the Kometa process at a lower priority. Will default to normal priority if not specified.'
    },
    '--no-report': {
      label: 'Skip Report',
      description: 'Kometa can produce a report of missing items, collections, and other information. If you have this report enabled but want to disable it for a specific run, use this flag.'
    },
    '--no-missing': {
      label: 'Skip Missing Items',
      description: 'Kometa can take various actions on missing items, such as sending them to Radarr, listing them in the log, or saving a report. If you want to disable all of these actions, use this flag.'
    },
    '--no-countdown': {
      label: 'No Countdown',
      description: 'Typically, when not doing an immediate run, Kometa displays a countdown in the terminal where it is running. If you want to hide this countdown, use this flag.'
    },
    '--ignore-ghost': {
      label: 'Ignore Ghost Metadata',
      description: 'Kometa prints some things to the log that do not actually go into the log file on disk. Typically these are things like status messages while loading and/or filtering. If you want to hide all ghost logging for the run, use this flag.'
    },
    '--ignore-schedules': {
      label: 'Ignore Schedules',
      description: 'Ignore all schedules for the run. Range Scheduled collections (such as Christmas movies) will still be ignored.'
    },
    '--no-verify-ssl': {
      label: 'Skip SSL Verification',
      description: 'Turn SSL Verification off.<br><strong>NOTE</strong>:<br>Set this if your log file shows any errors similar to <code>SSL: CERTIFICATE_VERIFY_FAILED</code>'
    },
    '--tests': {
      label: 'Test Mode',
      description: 'If you set this flag to true, Kometa will run only collections that you have marked as test immediately, like KOMETA_RUN.<br><strong>NOTE</strong>:<br>This will only run collections with <code>test: true</code> in the definition.'
    }
  }

  function updateFlagLabels (showCli) {
    const runOptions = ['--run', '--run-libraries']
    const modeFlags = ['--operations-only', '--collections-only', '--playlists-only', '--overlays-only']
    const logFlags = ['--debug', '--trace', '--log-requests']
    const otherFlags = [
      '--delete-collections', '--delete-labels', '--read-only-config', '--low-priority',
      '--no-report', '--no-missing', '--no-countdown', '--ignore-ghost',
      '--ignore-schedules', '--no-verify-ssl', '--tests'
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

  function buildCommand () {
    const baseDocker = 'docker run --rm -v /your/config/dir:/config kometa:nightly'
    const basePython = 'python kometa.py'
    const configFilename = $('#run-command-output').data('config-filename')
    const runMode = $('input[name="run-mode"]:checked').val()
    const mainOption = $('input[name="run-option"]:checked').val()
    const selectedLibs = $('#library-multiselect').length ? $('#library-multiselect').val() || [] : []

    let cli = runMode === 'docker' ? baseDocker : basePython

    cli += ` ${mainOption}`

    if (mainOption === '--run-libraries') {
      if (!selectedLibs.length) {
        $('#run-command-output').text('⚠️ Please select at least one library when using --run-libraries.')
        return
      }
      cli += ` "${selectedLibs.join(', ')}"`
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
      if (checkbox.length && checkbox.is(':checked')) {
        cli += ` --${opt}`
      }
    })

    cli += runMode === 'docker'
      ? ` --config /config/${configFilename}`
      : ` --config config/${configFilename}`

    $('#run-command-output').text(cli)
  }

  $('input[name="run-mode"]').on('change', buildCommand)
  $('input[name="run-option"]').on('change', function () {
    const value = $(this).val()
    updateLibraryVisibility(value)
    buildCommand()
  })

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
    const rootPath = $('#kometa-root-path').val().trim()
    const $logBox = $('#kometa-validation-log')
    const $spinner = $('#spinner_validate')
    const $runNow = $('#run-now')
    const configName = $('#run-command-output').data('config-filename')

    $logBox.text('🔄 Please wait while we validate your Kometa installation...\nThis may take a few seconds as we verify the folder structure, Python environment, and Kometa information.\n\n')
    $spinner.show()
    $runNow.prop('disabled', true)

    $.ajax({
      type: 'POST',
      url: '/validate-kometa-root',
      contentType: 'application/json',
      data: JSON.stringify({ path: rootPath, config_name: configName }),
      success: (res) => {
        if (res.log && Array.isArray(res.log)) {
          res.log.forEach(line => $logBox.append(`${line}\n`))
        }

        if (res.success) {
          $logBox.append('✅ Kometa root validated successfully.\n')

          // Recheck ALL other validations
          const allValid =
            $('#plex_valid').data('plex-valid') === 'True' &&
            $('#tmdb_valid').data('tmdb-valid') === 'True' &&
            $('#libs_valid').data('libs-valid') === 'True' &&
            $('#sett_valid').data('sett-valid') === 'True' &&
            $('#yaml_valid').data('yaml-valid') === 'True'

          if (allValid) {
            showRunCommandSectionAfterValidated()
          } else {
            $runNow.prop('disabled', true)
          }
        }

        $spinner.hide()
      },
      error: (xhr) => {
        const msg = xhr?.responseJSON?.error || 'The Kometa root path is invalid or inaccessible. Please check the folder and try again.'
        $logBox.append(`❌ ${msg}\n`)
        $runNow.prop('disabled', true)
        $spinner.hide()
      }
    })
  }

  // Run immediately on page load
  validateKometaRoot()

  // Run when clicking "Validate" button
  $('#validateButton').on('click', validateKometaRoot)

  if ($('#run-command-output').length > 0) {
    const mainOption = $('input[name="run-option"]:checked').val()
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

    navigator.clipboard.writeText(command).then(() => {
      $('#copy-icon').removeClass('bi-clipboard').addClass('bi-check2')
      $('#copy-text').text('Copied')

      setTimeout(() => {
        $('#copy-icon').removeClass('bi-check2').addClass('bi-clipboard')
        $('#copy-text').text('Copy')
      }, 1500)
    }).catch(() => {
      showToast('error', 'Copy failed. Please copy manually.')
    })
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

    $('#run-now').prop('disabled', false).html('<i class="bi bi-play-fill me-1"></i> Run Now')
  }

  // Ensure we check Kometa status once on page load to catch unclean exits
  hideRunCommandSectionUntilValidated()
  checkKometaStatus()
})

if (document.getElementById('header-style')) {
  document.getElementById('header-style').addEventListener('change', function () {
    document.getElementById('configForm').submit()
  })
}

let kometaInterval = null
let kometaStatusInterval = null

$('#run-now').on('click', function () {
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
        kometaInterval = setInterval(fetchKometaLog, 3000)
        kometaStatusInterval = setInterval(checkKometaStatus, 5000)
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
  fetch('/tail-log')
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        $('#run-output-log').text(`❌ ${data.error}`)
        return
      }
      $('#run-output-log').text(data.log)
    })
}

function checkKometaStatus () {
  fetch('/kometa-status')
    .then(res => res.json())
    .then(data => {
      if (data.status === 'done' || data.status === 'not started') {
        clearInterval(kometaInterval)
        clearInterval(kometaStatusInterval)
        $('#run-now').prop('disabled', false)
        $('#run-now-label').text('Run Now')
        $('#stop-now').addClass('d-none')

        if (data.status === 'done') {
          $('#run-output-log').append(`\n✅ Kometa finished with code ${data.return_code}`)
        } else {
          $('#run-output-log').append('\n🟥 Kometa is not running.')
        }
      }
    })
    .catch(err => {
      console.error('Error checking Kometa status:', err)
      $('#run-output-log').append('\n⚠️ Failed to check Kometa status.')
    })
}
