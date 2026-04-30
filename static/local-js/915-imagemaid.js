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
    runStatus: $('#imagemaid-run-status'),
    runLog: $('#imagemaid-run-log'),
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

  function syncMaintenanceBadge (data) {
    if (!els.maintenanceBadge.length) return
    maintenanceActive = Boolean(data && data.maintenance_active)
    maintenanceWindowLabel = data && data.maintenance_window ? ` (${data.maintenance_window})` : ''
    const active = maintenanceActive
    const windowLabel = maintenanceWindowLabel
    if (active) {
      els.maintenanceBadge.removeClass('d-none')
      const textEl = els.maintenanceBadge.find('span').last()
      if (textEl.length) textEl.text(`Blocked by Plex maintenance${windowLabel}`)
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
    return {
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

    if (!imagemaidValidated) {
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

  function queueAutosave () {
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
        body: JSON.stringify(collectPayload())
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
    if (!force && (!shouldPollImageMaidPage() || (!imagemaidRunning && !imagemaidStarting))) return Promise.resolve(null)
    imagemaidLogInFlight = true
    return fetch('/tail-imagemaid-log')
      .then(async (res) => ({ ok: res.ok, body: await res.json() }))
      .then(({ ok, body }) => {
        if (!ok || !body.success) {
          els.runLog.text((body && body.error) || 'No ImageMaid log found yet.')
          return
        }
        els.runLog.text(body.text || 'ImageMaid log is empty.')
        els.runLog.scrollTop(els.runLog[0].scrollHeight)
      })
      .catch(() => {
        els.runLog.text('Failed to load the ImageMaid log.')
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
        if (typeof window.QS_handleImageMaidStatus === 'function') {
          window.QS_handleImageMaidStatus(body)
        }
        const status = String(body.status || '').trim().toLowerCase()
        if (status === 'running') {
          const elapsed = typeof body.elapsed_seconds === 'number' ? `Elapsed ${body.elapsed_seconds}s.` : 'ImageMaid is currently running.'
          setRunState('running', elapsed)
          loadLog(true)
          return
        }
        if (status === 'starting') {
          imagemaidStartupDeadline = Date.now() + 10000
          const elapsed = typeof body.elapsed_seconds === 'number' ? `ImageMaid is still starting (${body.elapsed_seconds}s).` : 'ImageMaid is still starting.'
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
          loadLog(true)
          return
        }
        setRunState('idle', 'ImageMaid is not running.')
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
    const currentMode = String(els.mode.val() || 'report').trim().toLowerCase()
    const switchedToBlockedMode = lastImageMaidMode !== currentMode && ['report', 'move', 'remove'].includes(currentMode)
    lastImageMaidMode = currentMode
    restoreFolderModeConflict = false
    imagemaidValidated = false
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
    updatePreviewFromPayload()
    updateModeHelp()
    queueAutosave()
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

  if (window.PathValidation && typeof PathValidation.attach === 'function') {
    PathValidation.attach(document)
  }

  updatePreviewFromPayload()
  updateModeHelp()
  syncOptionalCapabilityRows()
  syncBranchSummary()
  syncUpdateButtonLabel()
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
})
