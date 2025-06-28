/* global $, bootstrap, alert */

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

  const tooltipMap = {
    '--run': 'Execute all configured features (collections, overlays, operations, metadata) across your libraries.',
    '--run-libraries': 'Run Kometa only on selected libraries—useful for targeting specific libraries rather than all.',
    '--operations-only': 'Only perform operations (e.g., rating/poster updates), skip collections, metadata, overlays.',
    '--collections-only': 'Only build collections without running operations, metadata edits, or overlays.',
    '--metadata-only': 'Only apply metadata edits, skip collections, operations, and overlays.',
    '--playlists-only': 'Only build playlists as defined in playlist files; collections, overlays, and metadata are skipped.',
    '--overlays-only': 'Only generate overlays on posters (e.g., ratings, resolution), skip other functions.',
    '--debug': 'Enable debug-level logging to see detailed runtime information in logs.',
    '--trace': 'Enable trace-level (very verbose) logging for deep troubleshooting.',
    '--log-requests': 'Log all HTTP requests made (e.g. to Plex, TMDb), helpful for diagnosing API issues.',
    '--delete-collections': 'Remove collections in Plex that are not defined by Kometa during this run.',
    '--delete-labels': 'Delete labels added by Kometa that are no longer applied in your config/YAML.',
    '--read-only-config': 'Run in read-only mode—do not write to Plex or make changes; for testing.',
    '--low-priority': 'Run Kometa with lower CPU priority; reduces system load.',
    '--no-report': 'Skip generating the final report YAML file about added/removed/missing items.',
    '--no-missing': 'Do not process items marked as missing; skip missing item actions.',
    '--no-countdown': 'Suppress the countdown prompt before operations begin.',
    '--ignore-ghost': 'Ignore ghost metadata entries (removed items still showing); do not act.',
    '--ignore-schedules': 'Ignore any scheduling settings (library/file), run immediately regardless of schedule.',
    '--no-verify-ssl': 'Disable SSL certificate verification for HTTPS requests (e.g., Plex/TMDb), dangerous!',
    '--tests': 'Run in test mode: perform validation but do not make any changes to Plex.'
  }

  function buildCommand () {
    const baseDocker = 'docker run --rm -v /your/config/dir:/config kometa:nightly'
    const basePython = 'python kometa.py'
    const configFilename = $('#run-command-output').data('config-filename')
    const runMode = $('input[name="run-mode"]:checked').val()
    const mainOption = $('input[name="run-option"]:checked').val()
    const selectedLibs = $('#library-multiselect').length ? $('#library-multiselect').val() || [] : []

    let cli = runMode === 'docker' ? baseDocker : basePython

    if (!mainOption || (mainOption !== '--run' && mainOption !== '--run-libraries')) {
      $('#run-command-output').text('⚠️ Please select a valid run mode (--run or --run-libraries).')
      return
    }

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

  const specialIdMap = {}

  Object.entries(tooltipMap).forEach(([flag, description]) => {
    const inputId = specialIdMap?.[flag] || `opt-${flag.replace(/^--/, '')}`
    const $label = $(`label[for="${inputId}"]`)
    if ($label.length && !$label.find('.bi-info-circle-fill').length) {
      const $tooltipIcon = $(`
        <span class="text-info ms-2" data-bs-toggle="tooltip" data-bs-html="true" data-bs-original-title="${description}">
          <i class="bi bi-info-circle-fill"></i>
        </span>
      `)
      $label.append($tooltipIcon)
    }
  })

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
      alert('Copy failed. Please copy manually.')
    })
  })
})

if (document.getElementById('header-style')) {
  document.getElementById('header-style').addEventListener('change', function () {
    document.getElementById('configForm').submit()
  })
}
