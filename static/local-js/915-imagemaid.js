/* global $, bootstrap, PathValidation, showToast */

$(document).ready(function () {
  const metaEl = document.getElementById('imagemaid-page-meta')
  const rootPath = metaEl ? String(metaEl.dataset.root || '').trim() : ''
  let imagemaidSupportsNoVerifySsl = metaEl ? String(metaEl.dataset.supportsNoVerifySsl || '').toLowerCase() === 'true' : false
  let imagemaidSupportsOverlaysOnly = metaEl ? String(metaEl.dataset.supportsOverlaysOnly || '').toLowerCase() === 'true' : false
  let imagemaidValidated = metaEl ? String(metaEl.dataset.validated || '').toLowerCase() === 'true' : false
  let imagemaidInstalled = false
  let imagemaidVenvReady = false
  let imagemaidRunning = false
  let imagemaidStarting = false
  let imagemaidUpdateAvailable = false
  let imagemaidUpdateCheckCompleted = false
  let imagemaidUpdateCheckSkipped = false
  let imagemaidEffectiveBranch = 'develop'
  let maintenanceActive = false
  let maintenanceWindowLabel = ''
  let updateJobId = null
  let updateLogIndex = 0
  let updatePollTimer = null
  let moveConfirmModal = null
  let stopConfirmModal = null
  let autosaveTimer = null
  let imagemaidAutosaveInFlight = false
  let imagemaidAutosavePending = false
  let imagemaidStartupDeadline = 0
  let lastImageMaidMode = String($('#imagemaid_mode').val() || 'report').trim().toLowerCase()
  let restoreFolderModeConflict = false
  let imagemaidProbeInFlight = false
  let imagemaidUpdateCheckInFlight = false
  let imagemaidUpdateProgressInFlight = false
  let imagemaidValidationInFlight = false
  let imagemaidStatusInFlight = false
  let imagemaidLogInFlight = false
  let imagemaidLogPollingPaused = false
  let imagemaidLogAutoScroll = true
  let imagemaidTailSize = '2000'
  let lastImageMaidStatusPayload = null
  let lastImageMaidLogPayload = null
  let lastImageMaidLogText = ''
  let lastImageMaidLogPath = ''
  let imagemaidLastPayloadSignature = ''
  let imagemaidDirty = false
  const SPARKLINE_MAX_POINTS = 40
  const SPARKLINE_WIDTH = 180
  const SPARKLINE_HEIGHT = 48
  const SPARKLINE_PADDING = 6
  const imagemaidSparkState = {
    cpu: { system: [], imagemaid: [] },
    mem: { system: [], imagemaid: [] },
    io: { read: [], write: [] }
  }

  const moveModalEl = document.getElementById('imagemaid-move-confirm-modal')
  if (moveModalEl && typeof bootstrap !== 'undefined') {
    moveConfirmModal = new bootstrap.Modal(moveModalEl)
  }
  const stopModalEl = document.getElementById('imagemaid-stop-confirm-modal')
  if (stopModalEl && typeof bootstrap !== 'undefined') {
    stopConfirmModal = new bootstrap.Modal(stopModalEl)
  }

  const els = {
    installState: $('#imagemaid-install-state'),
    installSummary: $('#imagemaid-install-summary'),
    installLog: $('#imagemaid-install-log'),
    installPath: $('#imagemaid-install-path'),
    branchSelection: $('#imagemaid-branch-selection'),
    effectiveBranch: $('#imagemaid-effective-branch'),
    updatePhaseBadge: $('#imagemaid-update-phase-badge'),
    localVersionStatus: $('#imagemaid-local-version-status'),
    remoteVersionStatus: $('#imagemaid-remote-version-status'),
    localBranchStatus: $('#imagemaid-local-branch-status'),
    localShaStatus: $('#imagemaid-local-sha-status'),
    remoteShaStatus: $('#imagemaid-remote-sha-status'),
    branchSourceUrl: $('#imagemaid-branch-source-url'),
    zipSourceUrl: $('#imagemaid-zip-source-url'),
    branchOverrideWarning: $('#imagemaid-branch-override-warning'),
    updateBox: $('#imagemaid-update-box'),
    localVersionInline: $('#imagemaid-local-version-inline'),
    localBranchInline: $('#imagemaid-local-branch-inline'),
    localShaInline: $('#imagemaid-local-sha-inline'),
    remoteVersionInline: $('#imagemaid-remote-version-inline'),
    remoteShaInline: $('#imagemaid-remote-sha-inline'),
    validationBadge: $('#imagemaid-validation-badge'),
    validationStatus: $('#imagemaid-validation-status'),
    maintenanceBadge: $('#imagemaid-maintenance-page-badge'),
    runGate: $('#imagemaid-run-gate'),
    runGateTitle: $('#imagemaid-run-gate-title'),
    runGateText: $('#imagemaid-run-gate-text'),
    runSurface: $('#imagemaid-run-surface'),
    runState: $('#imagemaid-run-state'),
    runStatusRow: $('#imagemaid-run-status-row'),
    runStatusTimer: $('#imagemaid-run-status-timer'),
    runStatusMetrics: $('#imagemaid-run-status-metrics'),
    runStatusLog: $('#imagemaid-run-status-log'),
    runStatusSparklines: $('#imagemaid-run-status-sparklines'),
    runMaintenanceRow: $('#imagemaid-run-maintenance-row'),
    runStatus: $('#imagemaid-run-status'),
    runLog: $('#imagemaid-run-log'),
    logAutoscroll: $('#imagemaid-log-autoscroll'),
    logTailSize: $('#imagemaid-log-tail-size'),
    tailLabel: $('#imagemaid-tail-label'),
    downloadLog: $('#imagemaid-download-log'),
    pauseLogPolling: $('#imagemaid-pause-log-polling'),
    logFilter: $('#imagemaid-log-filter'),
    logLevelButtons: $('.imagemaid-log-level-btn'),
    logStatValues: $('[data-imagemaid-log-stat]'),
    commandPreview: $('#imagemaid-command-preview'),
    updateBtn: $('#update-imagemaid-btn'),
    forceUpdateToggle: $('#force-update-imagemaid'),
    validateBtn: $('#validate-imagemaid-btn'),
    runBtn: $('#run-imagemaid-btn'),
    stopBtn: $('#stop-imagemaid-btn'),
    confirmMoveRunBtn: $('#confirm-imagemaid-move-run'),
    mode: $('#imagemaid_mode'),
    branch: $('#imagemaid_branch_override'),
    modeHelp: $('#imagemaid-mode-help'),
    modeHelpTitle: $('#imagemaid-mode-help-title'),
    modeHelpText: $('#imagemaid-mode-help-text'),
    modeHelpDetail: $('#imagemaid-mode-help-detail'),
    moveConfirmDetail: $('#imagemaid-move-confirm-detail')
  }

  const optionalRows = {
    noVerifySsl: $('#imagemaid-no-verify-ssl-row'),
    overlaysOnly: $('#imagemaid-overlays-only-row')
  }
  const $runSparkCpuSystem = $('#imagemaid-run-spark-cpu-system')
  const $runSparkCpuImageMaid = $('#imagemaid-run-spark-cpu-imagemaid')
  const $runSparkMemSystem = $('#imagemaid-run-spark-mem-system')
  const $runSparkMemImageMaid = $('#imagemaid-run-spark-mem-imagemaid')

  function syncMaintenanceBadge (data) {
    if (!els.maintenanceBadge.length) return
    maintenanceActive = Boolean(data && data.maintenance_active)
    maintenanceWindowLabel = data && data.maintenance_window ? ` (${data.maintenance_window})` : ''
    const paused = Boolean(data && data.maintenance_paused)
    const active = maintenanceActive || paused
    const windowLabel = maintenanceWindowLabel
    if (active) {
      els.maintenanceBadge.removeClass('d-none')
      const textEl = els.maintenanceBadge.find('span').last()
      if (textEl.length) textEl.text(`${paused ? 'Paused for' : 'Blocked by'} Plex maintenance${windowLabel}`)
    } else {
      els.maintenanceBadge.addClass('d-none')
    }
    syncRunGate()
  }

  document.addEventListener('qs:maintenance-status', function (event) {
    syncMaintenanceBadge(event.detail || null)
  })

  function syncOptionalCapabilityRows () {
    optionalRows.noVerifySsl.toggleClass('d-none', !imagemaidSupportsNoVerifySsl)
    optionalRows.overlaysOnly.toggleClass('d-none', !imagemaidSupportsOverlaysOnly)
  }

  function getRestoreDirPath () {
    const plexPath = String($('#imagemaid_plex_path').val() || '').trim()
    if (!plexPath) return ''
    const normalized = plexPath.replace(/[\\/]+$/, '')
    return `${normalized}\\ImageMaid Restore`
  }

  function updateModeHelp () {
    const mode = String(els.mode.val() || 'report').trim().toLowerCase()
    const restoreDir = getRestoreDirPath()
    const hasRestoreDirPath = Boolean(restoreDir)
    let tone = 'alert-secondary'
    let title = 'Report mode'
    let text = 'ImageMaid will report metadata image changes without moving or deleting them.'
    let detail = ''

    if (mode === 'move') {
      tone = 'alert-warning'
      title = 'Move mode'
      text = 'ImageMaid will move matching metadata images into the ImageMaid Restore folder so they can be restored later.'
      detail = hasRestoreDirPath ? `Destination folder: ${restoreDir}` : 'Enter the Plex path to see the restore folder destination.'
    } else if (mode === 'restore') {
      tone = 'alert-warning'
      title = 'Restore mode'
      text = 'ImageMaid will restore metadata images from the ImageMaid Restore folder back into Plex.'
      detail = hasRestoreDirPath ? `Required restore folder: ${restoreDir}` : 'Enter the Plex path to see the restore folder ImageMaid will use.'
    } else if (mode === 'clear') {
      tone = 'alert-danger'
      title = 'Clear mode'
      text = 'ImageMaid will delete everything currently stored in the ImageMaid Restore folder. This cannot be restored afterward.'
      detail = hasRestoreDirPath ? `Folder to clear: ${restoreDir}` : 'Enter the Plex path to see which restore folder would be cleared.'
    } else if (mode === 'remove') {
      tone = 'alert-danger'
      title = 'Remove mode'
      text = 'ImageMaid will permanently delete matching metadata images instead of moving them to the restore folder.'
      detail = 'This bypasses the restore folder. Removed metadata images cannot be recovered by ImageMaid.'
    } else if (mode === 'nothing') {
      tone = 'alert-secondary'
      title = 'Nothing mode'
      text = 'ImageMaid will skip metadata image cleanup entirely.'
      detail = 'Only the other selected operations will run, such as PhotoTranscoder cleanup, Empty Trash, Clean Bundles, or Optimize DB.'
    }

    if (['report', 'move', 'remove'].includes(mode) && restoreFolderModeConflict) {
      tone = 'alert-danger'
      title = `${mode.charAt(0).toUpperCase()}${mode.slice(1)} mode blocked`
      text = `${mode.charAt(0).toUpperCase()}${mode.slice(1)} mode is not allowed while the ImageMaid Restore folder still exists.`
      detail = hasRestoreDirPath
        ? `Use nothing, restore, or clear while this folder exists: ${restoreDir}`
        : 'Use nothing, restore, or clear while the existing ImageMaid Restore folder is present.'
    }

    els.modeHelp.removeClass('alert-secondary alert-warning alert-danger').addClass(tone)
    els.modeHelpTitle.text(title)
    els.modeHelpText.text(text)
    els.modeHelpDetail.text(detail)
    if (els.moveConfirmDetail.length) {
      const moveDetail = hasRestoreDirPath ? `Destination folder: ${restoreDir}` : 'Enter the Plex path first so Quickstart can show the restore folder.'
      els.moveConfirmDetail.text(moveDetail)
    }
  }

  function setBadge ($el, tone, text) {
    $el.removeClass('text-bg-secondary text-bg-success text-bg-warning text-bg-danger text-bg-primary')
    $el.addClass(tone)
    $el.text(text)
  }

  function shortSha (value) {
    const text = String(value || '').trim()
    return text ? text.slice(0, 12) : ''
  }

  function syncBranchSummary () {
    const override = String(els.branch.val() || '').trim().toLowerCase()
    const selection = override || 'auto'
    let effective = 'develop'
    if (override === 'master' || override === 'develop') {
      effective = override
    } else if (imagemaidEffectiveBranch) {
      effective = imagemaidEffectiveBranch
    }
    els.branchSelection.text(selection === 'auto' ? 'Auto' : selection)
    els.effectiveBranch.text(effective)
    els.branchOverrideWarning.toggleClass('d-none', selection === 'auto')
  }

  function setUpdatePhase (tone, text) {
    setBadge(els.updatePhaseBadge, tone, text)
  }

  function syncUpdateButtonLabel () {
    const force = els.forceUpdateToggle.is(':checked')
    let html = '<i class="bi bi-arrow-clockwise me-1"></i> Check for ImageMaid Updates'
    if (force) {
      html = imagemaidInstalled
        ? '<i class="bi bi-arrow-repeat me-1"></i> Force update'
        : '<i class="bi bi-download me-1"></i> Force install'
    } else if (!imagemaidInstalled) {
      html = '<i class="bi bi-download me-1"></i> Install ImageMaid'
    } else if (imagemaidRunning) {
      html = '<i class="bi bi-pause-circle me-1"></i> Skipped while running'
    } else if (imagemaidUpdateAvailable) {
      html = '<i class="bi bi-arrow-up-circle me-1"></i> Update Available'
    } else if (imagemaidUpdateCheckCompleted && !imagemaidUpdateCheckSkipped) {
      html = '<i class="bi bi-check-circle me-1"></i> Up to date'
    }
    els.updateBtn.html(html)
    els.updateBtn.prop('disabled', imagemaidRunning && !force)
  }

  function syncPrepareSummary (body, options = {}) {
    if (body && body.imagemaid_root_display) els.installPath.text(body.imagemaid_root_display)
    if (body && body.effective_branch) imagemaidEffectiveBranch = String(body.effective_branch || '').trim() || imagemaidEffectiveBranch
    imagemaidInstalled = Boolean(body && body.imagemaid_installed)
    imagemaidVenvReady = Boolean(body && body.venv_python_exists)
    imagemaidRunning = Boolean(body && body.imagemaid_running)
    imagemaidSupportsNoVerifySsl = Boolean(body && body.supports_no_verify_ssl)
    imagemaidSupportsOverlaysOnly = Boolean(body && body.supports_overlays_only)
    if (Object.prototype.hasOwnProperty.call(options, 'updateAvailable')) imagemaidUpdateAvailable = Boolean(options.updateAvailable)
    if (Object.prototype.hasOwnProperty.call(options, 'updateCheckCompleted')) imagemaidUpdateCheckCompleted = Boolean(options.updateCheckCompleted)
    if (Object.prototype.hasOwnProperty.call(options, 'updateCheckSkipped')) imagemaidUpdateCheckSkipped = Boolean(options.updateCheckSkipped)

    const localVersion = String((body && body.local_version) || '').trim()
    const remoteVersion = String((body && body.remote_version) || '').trim()
    els.localVersionStatus.text(localVersion || 'Unknown')
    els.remoteVersionStatus.text(remoteVersion || (imagemaidUpdateCheckCompleted ? 'Unavailable' : 'Not checked'))
    els.localBranchStatus.text((body && body.local_branch) || 'Unknown')
    els.localShaStatus.text(shortSha(body && body.local_sha) || 'Unknown')
    els.remoteShaStatus.text(shortSha(body && body.remote_sha) || (imagemaidUpdateCheckCompleted ? 'Unavailable' : 'Not checked'))
    els.branchSourceUrl.text((body && body.branch_source_url) || '')
    els.zipSourceUrl.text((body && body.zip_source_url) || '')

    const localBranch = (body && body.local_branch) || 'unknown'
    const localSha = shortSha(body && body.local_sha) || 'unknown'
    const remoteSha = shortSha(body && body.remote_sha) || 'unknown'
    els.localVersionInline.text(localVersion || 'unknown')
    els.localBranchInline.text(localBranch)
    els.localShaInline.text(localSha)
    els.remoteVersionInline.text(remoteVersion || 'unknown')
    els.remoteShaInline.text(remoteSha)
    els.updateBox.toggleClass('d-none', !imagemaidUpdateAvailable)

    if (options.phaseTone && options.phaseText) {
      setUpdatePhase(options.phaseTone, options.phaseText)
    } else if (!imagemaidInstalled) {
      setUpdatePhase('text-bg-warning', 'Install needed')
    } else if (!imagemaidVenvReady) {
      setUpdatePhase('text-bg-warning', 'Prepare needed')
    } else if (imagemaidRunning) {
      setUpdatePhase('text-bg-warning', 'Skipped while running')
    } else if (imagemaidUpdateAvailable) {
      setUpdatePhase('text-bg-warning', 'Update available')
    } else if (imagemaidUpdateCheckCompleted && !imagemaidUpdateCheckSkipped) {
      setUpdatePhase('text-bg-success', 'Ready')
    } else {
      setUpdatePhase('text-bg-secondary', 'Idle')
    }

    syncBranchSummary()
    syncUpdateButtonLabel()
    syncOptionalCapabilityRows()
    syncRunGate()
  }

  function boolValue (selector) {
    return $(selector).is(':checked')
  }

  function collectPayload () {
    const activeConfig = String(
      window.pageInfo?.config_name ||
      $('#qs-active-config-input').val() ||
      $('.qs-main-page-meta-value').first().text() ||
      ''
    ).trim()
    return {
      config_name: activeConfig,
      branch_override: String($('#imagemaid_branch_override').val() || '').trim(),
      plex_path: String($('#imagemaid_plex_path').val() || '').trim(),
      mode: String($('#imagemaid_mode').val() || 'report').trim(),
      timeout: String($('#imagemaid_timeout').val() || '').trim(),
      sleep: String($('#imagemaid_sleep').val() || '').trim(),
      photo_transcoder: boolValue('#imagemaid_photo_transcoder'),
      empty_trash: boolValue('#imagemaid_empty_trash'),
      clean_bundles: boolValue('#imagemaid_clean_bundles'),
      optimize_db: boolValue('#imagemaid_optimize_db'),
      local_db: boolValue('#imagemaid_local_db'),
      use_existing: boolValue('#imagemaid_use_existing'),
      ignore_running: boolValue('#imagemaid_ignore_running'),
      trace: boolValue('#imagemaid_trace'),
      log_requests: boolValue('#imagemaid_log_requests'),
      no_verify_ssl: imagemaidSupportsNoVerifySsl ? boolValue('#imagemaid_no_verify_ssl') : false,
      overlays_only: imagemaidSupportsOverlaysOnly ? boolValue('#imagemaid_overlays_only') : false
    }
  }

  function buildPayloadSignature (payload = collectPayload()) {
    return JSON.stringify({
      config_name: String(payload.config_name || '').trim(),
      branch_override: String(payload.branch_override || '').trim(),
      plex_path: String(payload.plex_path || '').trim(),
      mode: String(payload.mode || 'report').trim().toLowerCase(),
      timeout: String(payload.timeout || '').trim(),
      sleep: String(payload.sleep || '').trim(),
      photo_transcoder: Boolean(payload.photo_transcoder),
      empty_trash: Boolean(payload.empty_trash),
      clean_bundles: Boolean(payload.clean_bundles),
      optimize_db: Boolean(payload.optimize_db),
      local_db: Boolean(payload.local_db),
      use_existing: Boolean(payload.use_existing),
      ignore_running: Boolean(payload.ignore_running),
      trace: Boolean(payload.trace),
      log_requests: Boolean(payload.log_requests),
      no_verify_ssl: imagemaidSupportsNoVerifySsl ? Boolean(payload.no_verify_ssl) : false,
      overlays_only: imagemaidSupportsOverlaysOnly ? Boolean(payload.overlays_only) : false
    })
  }

  function escapeCommandValue (value) {
    return `"${String(value || '').replaceAll('"', '\\"')}"`
  }

  function updatePreviewFromPayload () {
    const payload = collectPayload()
    if (!payload.plex_path) {
      els.commandPreview.val('Preview unavailable until the Plex path is provided.')
      return
    }

    const parts = [
      escapeCommandValue(`${rootPath}\\imagemaid-venv\\Scripts\\python.exe`),
      escapeCommandValue(`${rootPath}\\imagemaid.py`),
      '--url',
      escapeCommandValue('(saved Plex URL)'),
      '--token',
      escapeCommandValue('(saved Plex token)'),
      '--plex',
      escapeCommandValue(payload.plex_path),
      '--mode',
      payload.mode || 'report'
    ]

    const boolFlags = [
      [payload.photo_transcoder, '--photo-transcoder'],
      [payload.empty_trash, '--empty-trash'],
      [payload.clean_bundles, '--clean-bundles'],
      [payload.optimize_db, '--optimize-db'],
      [payload.local_db, '--local'],
      [payload.use_existing, '--existing'],
      [payload.ignore_running, '--ignore'],
      [payload.trace, '--trace'],
      [payload.log_requests, '--log-requests']
    ]
    if (imagemaidSupportsNoVerifySsl) boolFlags.push([payload.no_verify_ssl, '--no-verify-ssl'])
    if (imagemaidSupportsOverlaysOnly) boolFlags.push([payload.overlays_only, '--overlays-only'])

    boolFlags.forEach(([enabled, flag]) => {
      if (enabled) parts.push(flag)
    })

    if (payload.timeout) parts.push('--timeout', payload.timeout)
    if (payload.sleep) parts.push('--sleep', payload.sleep)

    els.commandPreview.val(parts.join(' '))
  }

  function setInstallState (state, summary) {
    if (state === 'ready') {
      setBadge(els.installState, 'text-bg-success', 'Ready')
    } else if (state === 'running') {
      setBadge(els.installState, 'text-bg-primary', 'Working')
    } else if (state === 'warn') {
      setBadge(els.installState, 'text-bg-warning', 'Needs install')
    } else if (state === 'error') {
      setBadge(els.installState, 'text-bg-danger', 'Error')
    } else {
      setBadge(els.installState, 'text-bg-secondary', 'Not checked')
    }
    if (summary) els.installSummary.text(summary)
  }

  function syncRunGate () {
    if (imagemaidRunning || imagemaidStarting) {
      els.runGate.addClass('d-none')
      els.runSurface.removeClass('d-none')
      return
    }

    if (maintenanceActive) {
      els.runGate.removeClass('d-none alert-secondary alert-danger').addClass('alert-warning')
      els.runGateTitle.text('Blocked by Plex maintenance')
      els.runGateText.text(`Plex maintenance is active${maintenanceWindowLabel}. Wait for the maintenance window to end before running ImageMaid.`)
      els.runSurface.addClass('d-none')
      return
    }

    if (!imagemaidInstalled || !imagemaidVenvReady) {
      els.runGate.removeClass('d-none alert-warning alert-danger').addClass('alert-secondary')
      els.runGateTitle.text('Prepare ImageMaid first')
      els.runGateText.text('Install or prepare ImageMaid before Quickstart can build the run command and show the run controls.')
      els.runSurface.addClass('d-none')
      return
    }

    if (imagemaidDirty || !imagemaidValidated) {
      els.runGate.removeClass('d-none alert-secondary alert-danger').addClass('alert-warning')
      els.runGateTitle.text('Validate ImageMaid first')
      els.runGateText.text('Configuration changed or has not been validated yet. Validate ImageMaid to unlock the command preview and run controls.')
      els.runSurface.addClass('d-none')
      return
    }

    els.runGate.addClass('d-none')
    els.runSurface.removeClass('d-none')
  }

  function syncValidateButton (state) {
    els.validateBtn.removeClass('btn-success btn-dark btn-warning btn-secondary')
    if (state === 'ok') {
      els.validateBtn.addClass('btn-dark')
      els.validateBtn.prop('disabled', true)
      els.validateBtn.html('<i class="bi bi-check2-circle me-1"></i> Validated')
    } else if (state === 'running') {
      els.validateBtn.addClass('btn-warning')
      els.validateBtn.prop('disabled', true)
      els.validateBtn.html('<i class="bi bi-arrow-repeat me-1"></i> Validating...')
    } else {
      els.validateBtn.addClass('btn-success')
      els.validateBtn.prop('disabled', false)
      els.validateBtn.html('<i class="bi bi-check2-circle me-1"></i> Validate ImageMaid')
    }
  }

  function setValidationState (state, message) {
    if (state === 'ok') {
      setBadge(els.validationBadge, 'text-bg-success', 'Validated')
    } else if (state === 'error') {
      setBadge(els.validationBadge, 'text-bg-danger', 'Needs fixes')
    } else if (state === 'running') {
      setBadge(els.validationBadge, 'text-bg-primary', 'Validating')
    } else {
      setBadge(els.validationBadge, 'text-bg-secondary', 'Not validated')
    }
    els.validationStatus.removeClass('text-muted text-success text-danger text-warning')
    if (state === 'ok') {
      els.validationStatus.addClass('text-success')
    } else if (state === 'error') {
      els.validationStatus.addClass('text-danger')
    } else if (state === 'running') {
      els.validationStatus.addClass('text-warning')
    } else {
      els.validationStatus.addClass('text-muted')
    }
    if (message) els.validationStatus.text(message)
    syncValidateButton(state)
    syncRunGate()
  }

  function queueAutosave (payload = collectPayload(), signature = buildPayloadSignature(payload)) {
    if (autosaveTimer) clearTimeout(autosaveTimer)
    autosaveTimer = setTimeout(() => {
      if (imagemaidAutosaveInFlight) {
        imagemaidAutosavePending = true
        return
      }
      imagemaidAutosaveInFlight = true
      fetch('/autosave-imagemaid', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(async (res) => ({ ok: res.ok, body: await res.json().catch(() => ({})) }))
        .then(({ ok, body }) => {
          if (!ok || !body || body.success === false) return
          imagemaidLastPayloadSignature = signature
          imagemaidDirty = false
          if (body.changed) {
            imagemaidValidated = Boolean(body.validated)
            restoreFolderModeConflict = false
            imagemaidUpdateCheckCompleted = false
            imagemaidUpdateCheckSkipped = false
            imagemaidUpdateAvailable = false
            setValidationState('idle', 'Configuration changed. Validate ImageMaid again.')
            syncPrepareSummary({
              imagemaid_installed: imagemaidInstalled,
              venv_python_exists: imagemaidVenvReady,
              imagemaid_running: imagemaidRunning,
              local_branch: els.localBranchStatus.text(),
              local_sha: els.localShaStatus.text(),
              effective_branch: imagemaidEffectiveBranch,
              branch_source_url: els.branchSourceUrl.text(),
              zip_source_url: els.zipSourceUrl.text(),
              imagemaid_root_display: els.installPath.text()
            }, {
              updateAvailable: false,
              updateCheckCompleted: false,
              updateCheckSkipped: false
            })
          } else if (body.validated) {
            imagemaidValidated = true
            setValidationState('ok', 'ImageMaid is ready to run.')
          }
        })
        .catch(() => {})
        .finally(() => {
          imagemaidAutosaveInFlight = false
          if (imagemaidAutosavePending) {
            imagemaidAutosavePending = false
            queueAutosave()
          }
        })
    }, 300)
  }

  function shouldPollImageMaidPage () {
    return !document.hidden
  }

  function formatRunSeconds (seconds) {
    if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return ''
    const total = Math.max(0, Math.floor(seconds))
    const hours = Math.floor(total / 3600)
    const minutes = Math.floor((total % 3600) / 60)
    const secs = total % 60
    if (hours > 0) return `${hours}h ${minutes}m ${secs}s`
    if (minutes > 0) return `${minutes}m ${secs}s`
    return `${secs}s`
  }

  function formatTimestampLocal (value) {
    if (!value) return ''
    if (typeof window.QS_formatTimestamp === 'function') return window.QS_formatTimestamp(value)
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return String(value)
    return date.toLocaleString()
  }

  function clampPercent (value) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return null
    return Math.max(0, Math.min(100, value))
  }

  function pushSparkValue (series, value) {
    if (value == null) {
      if (!series.length) return
      series.push(series[series.length - 1])
    } else {
      series.push(value)
    }
    if (series.length > SPARKLINE_MAX_POINTS) series.shift()
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
    if (!els.runStatusSparklines.length) return
    const hasData = imagemaidSparkState.cpu.system.length || imagemaidSparkState.cpu.imagemaid.length ||
      imagemaidSparkState.mem.system.length || imagemaidSparkState.mem.imagemaid.length ||
      imagemaidSparkState.io.read.length || imagemaidSparkState.io.write.length
    els.runStatusSparklines.toggleClass('d-none', !hasData)
    $runSparkCpuSystem.attr('points', hasData ? buildSparklinePoints(imagemaidSparkState.cpu.system) : '')
    $runSparkCpuImageMaid.attr('points', hasData ? buildSparklinePoints(imagemaidSparkState.cpu.imagemaid) : '')
    $runSparkMemSystem.attr('points', hasData ? buildSparklinePoints(imagemaidSparkState.mem.system) : '')
    $runSparkMemImageMaid.attr('points', hasData ? buildSparklinePoints(imagemaidSparkState.mem.imagemaid) : '')
    const $runSparkIoRead = $('#imagemaid-run-spark-io-read')
    const $runSparkIoWrite = $('#imagemaid-run-spark-io-write')
    const ioMax = Math.max(0, ...imagemaidSparkState.io.read, ...imagemaidSparkState.io.write)
    $runSparkIoRead.attr('points', hasData ? buildSparklinePointsScaled(imagemaidSparkState.io.read, ioMax) : '')
    $runSparkIoWrite.attr('points', hasData ? buildSparklinePointsScaled(imagemaidSparkState.io.write, ioMax) : '')
  }

  function resetRunSparklines () {
    imagemaidSparkState.cpu.system = []
    imagemaidSparkState.cpu.imagemaid = []
    imagemaidSparkState.mem.system = []
    imagemaidSparkState.mem.imagemaid = []
    imagemaidSparkState.io.read = []
    imagemaidSparkState.io.write = []
    renderRunSparklines()
  }

  function updateRunSparklines (data) {
    if (!data || String(data.status || '').trim().toLowerCase() !== 'running') {
      resetRunSparklines()
      return
    }
    pushSparkValue(imagemaidSparkState.cpu.system, clampPercent(data.system_cpu_percent))
    pushSparkValue(imagemaidSparkState.cpu.imagemaid, clampPercent(data.cpu_percent))
    pushSparkValue(imagemaidSparkState.mem.system, clampPercent(data.system_memory_percent))
    pushSparkValue(imagemaidSparkState.mem.imagemaid, clampPercent(data.memory_percent))
    const ioRead = (typeof data.disk_read_rate_mb_s === 'number' && Number.isFinite(data.disk_read_rate_mb_s))
      ? Math.max(0, data.disk_read_rate_mb_s)
      : null
    const ioWrite = (typeof data.disk_write_rate_mb_s === 'number' && Number.isFinite(data.disk_write_rate_mb_s))
      ? Math.max(0, data.disk_write_rate_mb_s)
      : null
    pushSparkValue(imagemaidSparkState.io.read, ioRead)
    pushSparkValue(imagemaidSparkState.io.write, ioWrite)
    renderRunSparklines()
  }

  function syncRunStatusVisibility () {
    if (!els.runStatusRow.length) return
    const hasText = Boolean(els.runStatusTimer.text() || els.runStatusMetrics.text() || els.runStatusLog.text())
    els.runStatusRow.toggleClass('d-none', !hasText)
  }

  function updateRunStatusDetails (data) {
    if (!els.runStatusRow.length) return
    const status = String((data && data.status) || '').trim().toLowerCase()
    if (status === 'running' || status === 'starting') {
      const startedAt = formatTimestampLocal(data.started_at)
      const elapsed = formatRunSeconds(data.elapsed_seconds)
      const formatMem = (valueMb) => {
        if (typeof valueMb !== 'number' || !Number.isFinite(valueMb)) return 'n/a'
        if (valueMb >= 1024) return `${(valueMb / 1024).toFixed(1)} GB`
        return `${valueMb.toFixed(1)} MB`
      }
      const cpuText = typeof data.cpu_percent === 'number' && Number.isFinite(data.cpu_percent) ? `${data.cpu_percent.toFixed(1)}%` : 'n/a'
      const memRss = formatMem(data.memory_rss_mb)
      const memPct = typeof data.memory_percent === 'number' && Number.isFinite(data.memory_percent) ? `${data.memory_percent.toFixed(1)}%` : 'n/a'
      const sysCpu = typeof data.system_cpu_percent === 'number' && Number.isFinite(data.system_cpu_percent) ? `${data.system_cpu_percent.toFixed(1)}%` : 'n/a'
      const sysUsed = formatMem(data.system_memory_used_mb)
      const sysTotal = formatMem(data.system_memory_total_mb)
      const sysPct = typeof data.system_memory_percent === 'number' && Number.isFinite(data.system_memory_percent) ? `${data.system_memory_percent.toFixed(1)}%` : 'n/a'
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
      els.runStatusTimer.text(`${status === 'starting' ? 'Starting' : 'Running since'}: ${startedAt || 'n/a'}${elapsed ? ` • Elapsed: ${elapsed}` : ''}`)
      els.runStatusMetrics.text(`ImageMaid: ${cpuText} CPU • ${memRss} (${memPct}) | System: ${sysCpu} CPU • ${sysUsed} / ${sysTotal} (${sysPct})${diskText}`)
    } else if (status === 'done') {
      els.runStatusTimer.text('ImageMaid run complete.')
      els.runStatusMetrics.text('')
    } else {
      els.runStatusTimer.text('')
      els.runStatusMetrics.text('')
    }
    updateRunSparklines(data)
    syncRunStatusVisibility()
  }

  function updateMaintenanceRow (data) {
    if (!els.runMaintenanceRow.length) return
    const windowLabel = data && data.maintenance_window ? ` (${data.maintenance_window})` : ''
    if (data && data.maintenance_paused) {
      let pauseLabel = 'Paused'
      const pausedSince = data.maintenance_paused_since ? new Date(data.maintenance_paused_since) : null
      if (pausedSince && !Number.isNaN(pausedSince.getTime())) {
        const elapsedSeconds = Math.max(0, Math.floor((Date.now() - pausedSince.getTime()) / 1000))
        pauseLabel = formatRunSeconds(elapsedSeconds) || 'Paused'
      }
      els.runMaintenanceRow.html(`
        <span class="me-2 fw-semibold">Maintenance</span>
        <span class="badge text-bg-warning text-dark">Paused${windowLabel}</span>
        <span class="badge text-bg-secondary">${pauseLabel}</span>
      `).removeClass('d-none')
      return
    }
    if (data && data.maintenance_active) {
      els.runMaintenanceRow.html(`
        <span class="me-2 fw-semibold">Maintenance</span>
        <span class="badge text-bg-warning text-dark">Window Active${windowLabel}</span>
      `).removeClass('d-none')
      return
    }
    els.runMaintenanceRow.addClass('d-none').empty()
  }

  function computeLogStats (text, matcher) {
    const stats = { filter: 0, cache: 0, debug: 0, info: 0, warn: 0, error: 0, crit: 0, trace: 0 }
    const lines = String(text || '').split(/\r?\n/)
    lines.forEach(line => {
      if (!line) return
      if (matcher && !matcher(line)) return
      stats.filter += 1
      const upper = line.toUpperCase()
      if (upper.includes('[CACHE]') || /\bCACHE\b/.test(upper)) stats.cache += 1
      if (upper.includes('[DEBUG]')) stats.debug += 1
      if (upper.includes('[INFO]')) stats.info += 1
      if (upper.includes('[WARNING]') || upper.includes('[WARN]')) stats.warn += 1
      if (upper.includes('[ERROR]')) stats.error += 1
      if (upper.includes('[CRITICAL]') || upper.includes('[CRIT]')) stats.crit += 1
      if (upper.includes('[TRACE]')) stats.trace += 1
    })
    return stats
  }

  function updateLogStatBadges (stats) {
    els.logStatValues.each(function () {
      const key = String($(this).data('imagemaid-log-stat') || '').trim()
      $(this).text(String((stats && stats[key]) || 0))
    })
  }

  function syncLogLevelButtons () {
    const activeFilter = String(els.logFilter.val() || '').trim()
    els.logLevelButtons.each(function () {
      const level = String($(this).data('level') || '').trim()
      const isActive = Boolean(level) && level === activeFilter
      $(this)
        .toggleClass('btn-primary', isActive)
        .toggleClass('btn-outline-secondary', !isActive)
        .attr('aria-pressed', isActive ? 'true' : 'false')
    })
  }

  function applyLogFilter () {
    const payload = lastImageMaidLogPayload || {}
    const rawText = String(payload.text || lastImageMaidLogText || '')
    const filterText = String(els.logFilter.val() || '').trim()
    let filteredText = rawText
    let textMatcher = null
    if (filterText) {
      try {
        const regex = new RegExp(filterText, 'i')
        textMatcher = line => regex.test(line)
      } catch (_) {
        const lowered = filterText.toLowerCase()
        textMatcher = line => String(line || '').toLowerCase().includes(lowered)
      }
    }
    const matcher = textMatcher || null
    if (matcher) {
      filteredText = rawText.split(/\r?\n/).filter(line => matcher(line)).join('\n')
    }
    els.runLog.text(filteredText || (rawText ? 'No lines matched the current filter.' : 'ImageMaid log is empty.'))
    updateLogStatBadges(computeLogStats(rawText, matcher))
    syncLogLevelButtons()
    if (imagemaidLogAutoScroll && els.runLog.length) {
      els.runLog.scrollTop(els.runLog[0].scrollHeight)
    }
  }

  function updateLogRecency (payload) {
    if (!els.runStatusLog.length) return
    if (!payload || typeof payload.log_age_seconds !== 'number') {
      els.runStatusLog.text('')
      syncRunStatusVisibility()
      return
    }
    const ageText = formatRunSeconds(payload.log_age_seconds) || 'n/a'
    const totalLines = typeof payload.total_lines === 'number' && Number.isFinite(payload.total_lines)
      ? payload.total_lines.toLocaleString()
      : '0'
    els.runStatusLog.text(`${lastImageMaidLogPath ? `${lastImageMaidLogPath.split(/[\\\\/]/).pop()} updated ` : 'Log updated '}${ageText} ago • ${totalLines} lines`)
    syncRunStatusVisibility()
  }

  function setRunState (state, message) {
    if (state === 'running') {
      imagemaidRunning = true
      imagemaidStarting = false
      imagemaidStartupDeadline = 0
      setBadge(els.runState, 'text-bg-success', 'Running')
      els.runBtn.prop('disabled', true)
      els.stopBtn.prop('disabled', false)
    } else if (state === 'starting') {
      imagemaidRunning = false
      imagemaidStarting = true
      setBadge(els.runState, 'text-bg-primary', 'Starting')
      els.runBtn.prop('disabled', true)
      els.stopBtn.prop('disabled', false)
    } else if (state === 'blocked') {
      imagemaidRunning = false
      imagemaidStarting = false
      imagemaidStartupDeadline = 0
      setBadge(els.runState, 'text-bg-warning', 'Blocked')
      els.runBtn.prop('disabled', false)
      els.stopBtn.prop('disabled', true)
    } else if (state === 'error') {
      imagemaidRunning = false
      imagemaidStarting = false
      imagemaidStartupDeadline = 0
      setBadge(els.runState, 'text-bg-danger', 'Error')
      els.runBtn.prop('disabled', false)
      els.stopBtn.prop('disabled', true)
    } else {
      imagemaidRunning = false
      imagemaidStarting = false
      imagemaidStartupDeadline = 0
      setBadge(els.runState, 'text-bg-secondary', 'Idle')
      els.runBtn.prop('disabled', false)
      els.stopBtn.prop('disabled', true)
    }
    if (message) els.runStatus.text(message)
    if (!imagemaidRunning && !imagemaidStarting) {
      updateMaintenanceRow(lastImageMaidStatusPayload)
    }
    syncRunGate()
  }

  function appendInstallLog (lines) {
    if (!Array.isArray(lines) || !lines.length) return
    els.installLog.text(lines.join('\n'))
    els.installLog.scrollTop(els.installLog[0].scrollHeight)
  }

  function probeRoot () {
    if (imagemaidProbeInFlight || !shouldPollImageMaidPage()) return Promise.resolve(null)
    imagemaidProbeInFlight = true
    setInstallState('running', 'Probing local ImageMaid root...')
    return fetch('/probe-imagemaid-root', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: rootPath, branch_override: String(els.branch.val() || '').trim() })
    })
      .then(async (res) => ({ ok: res.ok, body: await res.json() }))
      .then(({ ok, body }) => {
        appendInstallLog(body.log || ['No probe output.'])
        if (!ok || !body.success) {
          setInstallState('error', body.error || 'ImageMaid probe failed.')
          return
        }
        const summary = body.imagemaid_installed
          ? (body.venv_python_exists ? 'ImageMaid files and venv are ready.' : 'ImageMaid files found, but the venv is still missing.')
          : 'ImageMaid is not installed locally yet.'
        setInstallState(body.imagemaid_installed && body.venv_python_exists ? 'ready' : 'warn', summary)
        syncPrepareSummary(body, {
          updateAvailable: imagemaidUpdateAvailable,
          updateCheckCompleted: imagemaidUpdateCheckCompleted,
          updateCheckSkipped: imagemaidUpdateCheckSkipped
        })
      })
      .catch(() => {
        setInstallState('error', 'ImageMaid probe failed.')
      })
      .finally(() => {
        imagemaidProbeInFlight = false
      })
  }

  function checkForImageMaidUpdate (forceRefresh = false) {
    if (imagemaidUpdateCheckInFlight || !shouldPollImageMaidPage()) return Promise.resolve(null)
    imagemaidUpdateCheckInFlight = true
    setInstallState('running', 'Checking ImageMaid update status...')
    setUpdatePhase('text-bg-primary', 'Checking')
    return fetch('/check-imagemaid-update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: rootPath,
        branch_override: String(els.branch.val() || '').trim(),
        force: !!forceRefresh
      })
    })
      .then(async (res) => ({ ok: res.ok, body: await res.json() }))
      .then(({ ok, body }) => {
        appendInstallLog(body.log || ['No update-check output.'])
        if (!ok || !body.success) {
          setInstallState('error', body.error || 'ImageMaid update check failed.')
          setUpdatePhase('text-bg-danger', 'Error')
          return null
        }
        imagemaidUpdateCheckCompleted = Boolean(body.update_check_completed)
        imagemaidUpdateCheckSkipped = Boolean(body.imagemaid_update_check_skipped)
        imagemaidUpdateAvailable = Boolean(body.imagemaid_update_available)
        syncPrepareSummary(body, {
          updateAvailable: imagemaidUpdateAvailable,
          updateCheckCompleted: imagemaidUpdateCheckCompleted,
          updateCheckSkipped: imagemaidUpdateCheckSkipped
        })
        if (!body.imagemaid_installed) {
          setInstallState('warn', 'ImageMaid is not installed locally yet.')
        } else if (body.imagemaid_update_check_skipped) {
          setInstallState('warn', 'ImageMaid is currently running, so update checks are skipped.')
        } else if (body.imagemaid_update_available) {
          setInstallState('warn', 'ImageMaid update is available.')
        } else {
          setInstallState('ready', body.cached ? 'ImageMaid is up to date. Cached check reused.' : 'ImageMaid is up to date.')
        }
        return body
      })
      .catch(() => {
        setInstallState('error', 'ImageMaid update check failed.')
        setUpdatePhase('text-bg-danger', 'Error')
        return null
      })
      .finally(() => {
        imagemaidUpdateCheckInFlight = false
      })
  }

  function pollUpdateProgress () {
    if (!updateJobId || imagemaidUpdateProgressInFlight || !shouldPollImageMaidPage()) return
    imagemaidUpdateProgressInFlight = true
    fetch(`/update-imagemaid-progress?job_id=${encodeURIComponent(updateJobId)}&since=${updateLogIndex}`)
      .then(async (res) => ({ ok: res.ok, body: await res.json() }))
      .then(({ ok, body }) => {
        if (!ok || !body.success) return
        const currentText = String(els.installLog.text() || '')
        const extra = Array.isArray(body.lines) ? body.lines : []
        if (extra.length) {
          els.installLog.text([currentText, ...extra].filter(Boolean).join('\n'))
          els.installLog.scrollTop(els.installLog[0].scrollHeight)
        }
        updateLogIndex = Number(body.next_index || updateLogIndex)
        if (body.done) {
          clearInterval(updatePollTimer)
          updatePollTimer = null
          updateJobId = null
          if (body.update_success) {
            setInstallState('ready', body.up_to_date ? 'ImageMaid is already up to date.' : 'ImageMaid prepare/update completed.')
            showToast('success', body.up_to_date ? 'ImageMaid is already up to date.' : 'ImageMaid prepare/update completed.')
          } else {
            setInstallState('error', 'ImageMaid update failed.')
            showToast('error', 'ImageMaid prepare/update failed.')
          }
          imagemaidUpdateCheckCompleted = false
          imagemaidUpdateCheckSkipped = false
          imagemaidUpdateAvailable = false
          probeRoot()
        }
      })
      .catch(() => {})
      .finally(() => {
        imagemaidUpdateProgressInFlight = false
      })
  }

  function startUpdate (force) {
    setInstallState('running', force ? 'Force updating ImageMaid...' : (imagemaidInstalled ? 'Preparing ImageMaid...' : 'Installing ImageMaid...'))
    setUpdatePhase('text-bg-primary', force ? 'Force update' : (imagemaidInstalled ? 'Preparing' : 'Installing'))
    els.installLog.text('Starting ImageMaid update job...')
    fetch('/update-imagemaid', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        branch_override: String(els.branch.val() || '').trim(),
        force: !!force,
        background: true
      })
    })
      .then(async (res) => ({ status: res.status, body: await res.json() }))
      .then(({ status, body }) => {
        if (status === 409) {
          setInstallState('error', body.error || 'ImageMaid update is blocked.')
          showToast('warning', body.error || 'ImageMaid update is blocked.')
          return
        }
        if (!body.success) {
          setInstallState('error', body.error || 'ImageMaid update failed to start.')
          showToast('error', body.error || 'ImageMaid update failed to start.')
          return
        }
        updateJobId = String(body.job_id || '').trim()
        updateLogIndex = 0
        if (updatePollTimer) clearInterval(updatePollTimer)
        updatePollTimer = setInterval(pollUpdateProgress, 1500)
        pollUpdateProgress()
      })
      .catch(() => {
        setInstallState('error', 'ImageMaid update failed to start.')
      })
  }

  function validateImageMaid () {
    if (imagemaidValidationInFlight) return Promise.resolve(false)
    if (window.PathValidation && typeof PathValidation.validateAll === 'function' && !PathValidation.validateAll(document)) {
      setValidationState('error', 'Fix the highlighted path issues first.')
      return Promise.resolve(false)
    }

    imagemaidValidationInFlight = true
    setValidationState('running', 'Validating ImageMaid configuration...')
    return fetch('/validate-imagemaid', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collectPayload())
    })
      .then(async (res) => ({ ok: res.ok, body: await res.json() }))
      .then(({ ok, body }) => {
        imagemaidValidated = Boolean(body && body.validated)
        imagemaidDirty = false
        imagemaidLastPayloadSignature = buildPayloadSignature()
        restoreFolderModeConflict = Boolean(body && body.reason === 'restore_dir_blocks_mode')
        if (body && body.command_preview) {
          els.commandPreview.val(body.command_preview)
        } else {
          updatePreviewFromPayload()
        }
        updateModeHelp()
        if (ok && body.validated) {
          setValidationState('ok', 'ImageMaid is ready to run.')
          return true
        } else {
          setValidationState('error', body.details || body.error || 'ImageMaid validation failed.')
          return false
        }
      })
      .catch(() => {
        imagemaidValidated = false
        imagemaidDirty = false
        restoreFolderModeConflict = false
        updateModeHelp()
        setValidationState('error', 'ImageMaid validation failed.')
        return false
      })
      .finally(() => {
        imagemaidValidationInFlight = false
      })
  }

  function loadLog (force = false) {
    if (imagemaidLogInFlight) return Promise.resolve(null)
    if (!force && (imagemaidLogPollingPaused || !shouldPollImageMaidPage() || (!imagemaidRunning && !imagemaidStarting))) return Promise.resolve(null)
    imagemaidLogInFlight = true
    return fetch(`/tail-imagemaid-log?lines=${encodeURIComponent(imagemaidTailSize)}`)
      .then(async (res) => ({ ok: res.ok, body: await res.json() }))
      .then(({ ok, body }) => {
        if (!ok || !body.success) {
          lastImageMaidLogPayload = null
          lastImageMaidLogText = ''
          lastImageMaidLogPath = ''
          els.runLog.text((body && body.error) || 'No ImageMaid log found yet.')
          updateLogStatBadges({ filter: 0, cache: 0, debug: 0, info: 0, warn: 0, error: 0, crit: 0, trace: 0 })
          updateLogRecency(null)
          return
        }
        lastImageMaidLogPayload = body
        lastImageMaidLogText = String(body.text || '')
        lastImageMaidLogPath = String(body.path || '')
        const requested = String(body.requested_lines || imagemaidTailSize)
        els.tailLabel.text(requested.toLowerCase() === 'all' ? 'all' : requested)
        updateLogRecency(body)
        applyLogFilter()
      })
      .catch(() => {
        lastImageMaidLogPayload = null
        els.runLog.text('Failed to load the ImageMaid log.')
        updateLogRecency(null)
      })
      .finally(() => {
        imagemaidLogInFlight = false
      })
  }

  function updateStatus (force = false) {
    if (imagemaidStatusInFlight) return Promise.resolve(null)
    if (!force && !shouldPollImageMaidPage()) return Promise.resolve(null)
    imagemaidStatusInFlight = true
    return fetch('/imagemaid-status')
      .then(async (res) => ({ ok: res.ok, body: await res.json() }))
      .then(({ ok, body }) => {
        if (!ok) return
        lastImageMaidStatusPayload = body
        syncMaintenanceBadge(body)
        updateRunStatusDetails(body)
        updateMaintenanceRow(body)
        if (body && body.active_command && (String(body.status || '').trim().toLowerCase() === 'running' || String(body.status || '').trim().toLowerCase() === 'starting')) {
          els.commandPreview.val(body.active_command)
        }
        if (typeof window.QS_handleImageMaidStatus === 'function') {
          window.QS_handleImageMaidStatus(body)
        }
        const status = String(body.status || '').trim().toLowerCase()
        if (status === 'running') {
          const elapsed = typeof body.elapsed_seconds === 'number' ? `Elapsed ${formatRunSeconds(body.elapsed_seconds) || `${body.elapsed_seconds}s`}.` : 'ImageMaid is currently running.'
          setRunState('running', elapsed)
          loadLog(true)
          return
        }
        if (status === 'starting') {
          imagemaidStartupDeadline = Date.now() + 10000
          const elapsed = typeof body.elapsed_seconds === 'number' ? `ImageMaid is still starting (${formatRunSeconds(body.elapsed_seconds) || `${body.elapsed_seconds}s`}).` : 'ImageMaid is still starting.'
          setRunState('starting', elapsed)
          loadLog(true)
          return
        }
        if (imagemaidStarting && Date.now() < imagemaidStartupDeadline) {
          const secondsLeft = Math.max(1, Math.ceil((imagemaidStartupDeadline - Date.now()) / 1000))
          setRunState('starting', `ImageMaid is still starting. Waiting up to ${secondsLeft}s before treating startup as failed.`)
          return
        }
        if (status === 'done') {
          setRunState('idle', 'ImageMaid finished.')
          updatePreviewFromPayload()
          loadLog(true)
          return
        }
        setRunState('idle', 'ImageMaid is not running.')
        updatePreviewFromPayload()
        updateRunStatusDetails(body)
      })
      .catch(() => {})
      .finally(() => {
        imagemaidStatusInFlight = false
      })
  }

  function submitRun () {
    if (!imagemaidValidated) {
      validateImageMaid().then((validated) => {
        if (!validated) return
        submitRun()
      })
      return
    }

    imagemaidStartupDeadline = Date.now() + 10000
    setRunState('starting', 'Starting ImageMaid...')
    fetch('/start-imagemaid', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collectPayload())
    })
      .then(async (res) => ({ status: res.status, body: await res.json() }))
      .then(({ status, body }) => {
        if (status === 409) {
          setRunState('blocked', body.error || 'ImageMaid run is blocked.')
          showToast('warning', body.error || 'ImageMaid run is blocked.')
          return
        }
        if (status >= 400) {
          setRunState('error', body.error || 'ImageMaid failed to start.')
          if (body && body.error) {
            els.runLog.text(body.error)
          }
          loadLog(true)
          showToast('error', body.error || 'ImageMaid failed to start.')
          return
        }
        imagemaidStartupDeadline = Date.now() + 10000
        setRunState('starting', body.status || 'ImageMaid started.')
        showToast('success', 'ImageMaid started.')
        updateStatus(true)
        loadLog(true)
      })
      .catch(() => {
        setRunState('error', 'ImageMaid failed to start.')
      })
  }

  function stopRunConfirmed () {
    fetch('/stop-imagemaid', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
      .then(async (res) => ({ ok: res.ok, body: await res.json() }))
      .then(({ body }) => {
        if (stopConfirmModal) stopConfirmModal.hide()
        if (body.error) {
          showToast('error', body.error)
          return
        }
        showToast('success', body.message || body.warning || 'ImageMaid stop requested.')
        updateStatus(true)
        loadLog(true)
      })
      .catch(() => {
        if (stopConfirmModal) stopConfirmModal.hide()
        showToast('error', 'Failed to stop ImageMaid.')
      })
  }

  function onConfigChanged () {
    const payload = collectPayload()
    const nextSignature = buildPayloadSignature(payload)
    const currentMode = String(payload.mode || 'report').trim().toLowerCase()
    if (!imagemaidLastPayloadSignature) {
      imagemaidLastPayloadSignature = nextSignature
      lastImageMaidMode = currentMode
      updatePreviewFromPayload()
      updateModeHelp()
      return
    }
    if (nextSignature === imagemaidLastPayloadSignature) {
      imagemaidDirty = false
      updatePreviewFromPayload()
      updateModeHelp()
      syncRunGate()
      return
    }
    imagemaidDirty = true
    const switchedToBlockedMode = lastImageMaidMode !== currentMode && ['report', 'move', 'remove'].includes(currentMode)
    lastImageMaidMode = currentMode
    updatePreviewFromPayload()
    updateModeHelp()
    syncRunGate()
    queueAutosave(payload, nextSignature)
    if (switchedToBlockedMode && String($('#imagemaid_plex_path').val() || '').trim()) {
      validateImageMaid()
    }
  }

  els.updateBtn.on('click', () => {
    const force = els.forceUpdateToggle.is(':checked')
    if (force || !imagemaidInstalled || imagemaidUpdateAvailable) {
      startUpdate(force)
      return
    }
    checkForImageMaidUpdate(true).then((body) => {
      if (!body) return
      if (body.imagemaid_update_available) {
        showToast('warning', 'ImageMaid update available.')
      } else if (!body.imagemaid_update_check_skipped) {
        showToast('success', body.cached ? 'ImageMaid is already up to date. Cached result reused.' : 'ImageMaid is already up to date.')
      }
    })
  })
  els.forceUpdateToggle.on('change', syncUpdateButtonLabel)
  els.validateBtn.on('click', validateImageMaid)
  els.stopBtn.on('click', () => {
    if (stopConfirmModal) {
      stopConfirmModal.show()
      return
    }
    stopRunConfirmed()
  })
  els.runBtn.on('click', () => {
    const mode = String(els.mode.val() || 'report').trim().toLowerCase()
    if (mode === 'move' && moveConfirmModal) {
      moveConfirmModal.show()
      return
    }
    submitRun()
  })
  els.confirmMoveRunBtn.on('click', () => {
    if (moveConfirmModal) moveConfirmModal.hide()
    submitRun()
  })
  $('#confirm-stop-imagemaid').on('click', stopRunConfirmed)

  $('#imagemaid_mode, #imagemaid_plex_path, #imagemaid_timeout, #imagemaid_sleep, #imagemaid_branch_override').on('input change', onConfigChanged)
  $('#imagemaid_photo_transcoder, #imagemaid_empty_trash, #imagemaid_clean_bundles, #imagemaid_optimize_db, #imagemaid_local_db, #imagemaid_use_existing, #imagemaid_ignore_running, #imagemaid_trace, #imagemaid_log_requests, #imagemaid_no_verify_ssl, #imagemaid_overlays_only').on('change', onConfigChanged)
  els.logAutoscroll.on('change', function () {
    imagemaidLogAutoScroll = $(this).is(':checked')
  })
  els.logTailSize.on('change', function () {
    const next = String($(this).val() || '2000').trim().toLowerCase()
    imagemaidTailSize = next === 'all' ? 'all' : (['200', '2000', '20000'].includes(next) ? next : '2000')
    els.tailLabel.text(imagemaidTailSize === 'all' ? 'all' : imagemaidTailSize)
    loadLog(true)
  })
  els.logFilter.on('input', applyLogFilter)
  els.logLevelButtons.on('click', function () {
    const nextLevel = String($(this).data('level') || '').trim()
    const currentFilter = String(els.logFilter.val() || '').trim()
    els.logFilter.val(currentFilter === nextLevel ? '' : nextLevel)
    applyLogFilter()
  })
  els.pauseLogPolling.on('click', function () {
    imagemaidLogPollingPaused = !imagemaidLogPollingPaused
    if (imagemaidLogPollingPaused) {
      $(this).html('<i class="bi bi-play-circle me-1"></i> Resume')
    } else {
      $(this).html('<i class="bi bi-pause-circle me-1"></i> Pause')
      loadLog(true)
    }
  })
  els.downloadLog.on('click', function () {
    const text = String((lastImageMaidLogPayload && lastImageMaidLogPayload.text) || lastImageMaidLogText || '')
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = lastImageMaidLogPath ? lastImageMaidLogPath.split(/[\\/]/).pop() : 'imagemaid.log'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  })

  if (window.PathValidation && typeof PathValidation.attach === 'function') {
    PathValidation.attach(document)
  }

  updatePreviewFromPayload()
  updateModeHelp()
  syncOptionalCapabilityRows()
  syncBranchSummary()
  syncUpdateButtonLabel()
  imagemaidLastPayloadSignature = buildPayloadSignature()
  els.tailLabel.text(imagemaidTailSize === 'all' ? 'all' : imagemaidTailSize)
  imagemaidLogAutoScroll = els.logAutoscroll.is(':checked')
  syncLogLevelButtons()
  setValidationState(imagemaidValidated ? 'ok' : 'idle', String(els.validationStatus.text() || '').trim())
  probeRoot()
  updateStatus(true)
  loadLog(true)
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      updateStatus(true)
      loadLog(true)
    }
  })
  setInterval(() => updateStatus(), 7000)
  setInterval(() => loadLog(), 5000)
})
