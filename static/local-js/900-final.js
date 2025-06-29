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

  if (!showYAML) {
    $('#validation-messages').html(validationMessages.join('<br>')).show()
    $('#no-validation-warning, #yaml-warnings, #yaml-warning-msg, #validation-error').removeClass('d-none')
    $('#download-btn, #download-redacted-btn').addClass('d-none')
  } else {
    $('#no-validation-warning, #yaml-warnings, #yaml-warning-msg, #validation-error').addClass('d-none')
    $('#yaml-content, #final-yaml, #download-btn, #download-redacted-btn').removeClass('d-none')
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
      label: 'Run Everything',
      description: 'Execute all configured features (collections, overlays, operations, metadata).'
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
      description: 'Log all HTTP requests (to Plex, TMDb, etc.).'
    },
    '--delete-collections': {
      label: 'Delete Collections',
      description: 'Remove collections in Plex not defined in config.'
    },
    '--delete-labels': {
      label: 'Delete Labels',
      description: 'Delete Kometa labels that are no longer used.'
    },
    '--read-only-config': {
      label: 'Read-Only Mode',
      description: 'Validate but don’t change Plex.'
    },
    '--low-priority': {
      label: 'Low Priority Mode',
      description: 'Lower CPU usage while running.'
    },
    '--no-report': {
      label: 'Skip Report',
      description: 'Skip generating the final report file.'
    },
    '--no-missing': {
      label: 'Skip Missing Items',
      description: 'Do not process missing items.'
    },
    '--no-countdown': {
      label: 'No Countdown',
      description: 'Skip the countdown before starting.'
    },
    '--ignore-ghost': {
      label: 'Ignore Ghost Metadata',
      description: 'Skip removed-but-visible Plex items.'
    },
    '--ignore-schedules': {
      label: 'Ignore Schedules',
      description: 'Run now regardless of scheduling settings.'
    },
    '--no-verify-ssl': {
      label: 'Skip SSL Verification',
      description: 'Disable HTTPS cert validation (⚠ dangerous!).'
    },
    '--tests': {
      label: 'Test Mode',
      description: 'Validate but don’t update Plex.'
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

    $('[data-bs-toggle="tooltip"]').tooltip()
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

    $logBox.text('🔄 Please wait while we validate your Kometa installation...\nThis may take a few seconds as we verify the folder structure, Python environment, and Kometa version.\n\n')
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
          $runNow.prop('disabled', false)
        } else {
          $logBox.append(`❌ ${res.error || 'Validation failed.'}\n`)
          $runNow.prop('disabled', true)
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
    new bootstrap.Tooltip(tooltipTriggerEl)
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
})

if (document.getElementById('header-style')) {
  document.getElementById('header-style').addEventListener('change', function () {
    document.getElementById('configForm').submit()
  })
}

let kometaInterval = null

$('#run-now').on('click', function () {
  const command = $('#run-command-output').text().trim()

  if (!command || command.startsWith('⚠️')) {
    showToast('error', 'Cannot run invalid command.')
    return
  }

  $('#run-now').prop('disabled', true).text('Running...')
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
        $('#run-now').prop('disabled', false).text('Run Now')
        $('#stop-now').addClass('d-none') // hide stop on error
        return
      }

      kometaInterval = setInterval(fetchKometaLog, 5000)
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
      $('#run-now').prop('disabled', false).text('Run Now')
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
        clearInterval(kometaInterval)
        $('#run-now').prop('disabled', false).text('Run Now')
        return
      }

      $('#run-output-log').text(data.log)
    })
}
