// Global flag so other handlers know an update is in progress
import {
  computeYamlLineCount,
  formatTimestampLocal,
  formatRunSeconds,
  applyLogFilter,
  computeLogStats,
  copyTextToClipboard,
  setMetaFlag
} from './modules/kometa/_util.js'
import {
  checkMaintenanceWarning
} from './modules/kometa/_maintenanceWindow.js'
import { kometaState } from './modules/kometa/_state.js'
import {
  updateConfigOutputHeaderBadges,
  updateLogscanHeaderBadge,
  syncFinalAccordionRollups
} from './modules/kometa/_headerBadges.js'
import {
  updateHeaderStyleLabel,
  setActiveGridCard,
  loadHeaderGridSamples
} from './modules/kometa/_headerGrid.js'
import {
  getFinalGateState,
  updateValidationGate
} from './modules/kometa/_validationGate.js'
import {
  kometaCanLaunch,
  kometaCanProbeRuntime,
  kometaCanReadLogs
} from './modules/kometa/_runtime.js'
import {
  buildCommand,
  applyActiveRunCommandState,
  clearActiveRunCommandState
} from './modules/kometa/_runCommand.js'
import {
  updateRunSparklines
} from './modules/kometa/_sparklines.js'
import {
  initBootstrapTooltips,
  disposeBootstrapTooltips,
  showCopyButtonSuccess
} from './modules/kometa/_ui.js'
import {
  loadSavedKometaBranchOverride,
  saveKometaBranchOverride,
  syncKometaSourceStatus,
  syncKometaBranchOverrideWarning
} from './modules/kometa/_kometaBranch.js'
import {
  updateRunNowState,
  syncIncompleteRunActions,
  getCurrentRunCommand,
  getRecoveryRunCommand
} from './modules/kometa/_runControls.js'
import {
  setKometaUpdatePhaseBadge,
  appendKometaStatusLine
} from './modules/kometa/_updatePhase.js'
import {
  syncKometaRollupBadge,
  syncKometaUpdateAttention,
  syncUpdateButtonLabel
} from './modules/kometa/_updateRollup.js'
import {
  setRunCommandPlaceholderState,
  clearRunCommandPlaceholderState,
  hideRunCommandSectionUntilValidated,
  revealRunCommandSection
} from './modules/kometa/_runCommandSection.js'
import { validateKometaRoot } from './modules/kometa/_validateRoot.js'
import { runKometaStatusPass } from './modules/kometa/_statusPass.js'
import { callUpdateKometa } from './modules/kometa/_kometaUpdate.js'
import {
  renderRunProgress,
  clearRunProgress,
  fetchRunProgress
} from './modules/kometa/_runProgress.js'
import {
  formatLocalTimestamp,
  formatRelativeTimestamp,
  updateValidationRow
} from './modules/kometa/_validationDisplay.js'
import {
  fetchLogscanAnalysis
} from './modules/kometa/_logscan.js'
import {
  updateFlagLabels,
  updateLibraryVisibility
} from './modules/kometa/_cliFlags.js'
import { buildRunStatusText } from './modules/kometa/_runStatusFormat.js'

// Kometa runtime status flags migrated to modules/kometa/_state.js
// (kometaState.kometaInstalled, kometaValidated, kometaStatus, etc.).
// See _state.js docstring for the state-machine notes.
let autoScrollEnabled = true
let tailSize = '2000'
let logPollingPaused = false
let logFilter = ''
let lastLogText = ''
let lastLogStatsTotal = null
let logStatsPollCounter = 0
let finalLogscanAnalyzeTriggered = false

const runLog = document.getElementById('run-output-log')
const tailNotice = document.getElementById('run-output-notice')
const tailSelect = document.getElementById('run-log-tail')
const autoScrollToggle = document.getElementById('run-log-autoscroll')
const downloadLogBtn = document.getElementById('download-log-btn')
const pauseLogBtn = document.getElementById('pause-log-btn')
const filterInput = document.getElementById('run-log-filter')
const clearFilterBtn = document.getElementById('clear-log-filter')
const levelButtons = Array.from(document.querySelectorAll('.log-level-btn'))
const logStats = document.getElementById('run-log-stats')
const logStatsFiltered = document.getElementById('run-log-stats-filtered')
const updateKometaBtn = document.getElementById('update-kometa-btn')
const forceUpdateToggle = document.getElementById('force-kometa-update')
const kometaBranchOverride = document.getElementById('kometa-branch-override')
const kometaMaintenancePageBadge = document.getElementById('kometa-maintenance-page-badge')
const runStatusRow = document.getElementById('run-status-row')
const runStatusTimer = document.getElementById('run-status-timer')
const runStatusMetrics = document.getElementById('run-status-metrics')
const runStatusLog = document.getElementById('run-status-log')
const yamlOutput = document.getElementById('final-yaml')
const yamlLineCount = document.getElementById('yaml-line-count')
const stopModalEl = document.getElementById('stop-kometa-modal')
const stopModal = (stopModalEl && typeof bootstrap !== 'undefined') ? new bootstrap.Modal(stopModalEl) : null
const confirmStopBtn = document.getElementById('confirm-stop-kometa')
const headerSelect = document.getElementById('header-style')
const headerGrid = document.getElementById('header-style-grid')
const headerGridCollapse = document.getElementById('header-style-grid-collapse')
const headerStyleWait = document.getElementById('header-style-wait')
const finalContentWrapper = document.getElementById('final-content-wrapper')
const kometaActionsCollapse = document.getElementById('kometa-actions-collapse')
const kometaActionsToggle = document.getElementById('kometa-actions-toggle')
const runCommandCollapse = document.getElementById('run-command-output-collapse')
let headerStyleSubmitting = false

function syncKometaMaintenancePageBadge (data) {
  if (!kometaMaintenancePageBadge) return
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
    kometaMaintenancePageBadge.classList.remove('d-none')
    const spans = kometaMaintenancePageBadge.querySelectorAll('span')
    const textEl = spans.length ? spans[spans.length - 1] : null
    if (textEl) textEl.textContent = label
  } else {
    kometaMaintenancePageBadge.classList.add('d-none')
  }
}

document.addEventListener('qs:maintenance-status', function (event) {
  syncKometaMaintenancePageBadge(event.detail || null)
})

updateValidationGate()

if (tailSelect) {
  tailSize = tailSelect.value || tailSize
  updateTailNotice()
  tailSelect?.addEventListener('change', function() {
    tailSize = this.value || tailSize
    updateTailNotice()
    fetchKometaLog()
  })
}

function updateYamlLineCount () {
  if (!yamlLineCount || !yamlOutput) return
  const lineCount = computeYamlLineCount(yamlOutput.value)
  yamlLineCount.textContent = `Line count (includes comments and blank lines): ${lineCount}`
  updateConfigOutputHeaderBadges()
}

updateYamlLineCount()
yamlOutput?.addEventListener('input', updateYamlLineCount)

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
const openKometaActionsBtn = document.getElementById('open-kometa-actions-button')
if (openKometaActionsBtn) {
  openKometaActionsBtn.addEventListener('click', function() {
    if (kometaState.kometaStatus === 'running') return
    if (!kometaActionsCollapse || typeof bootstrap === 'undefined' || !bootstrap.Collapse) return
    bootstrap.Collapse.getOrCreateInstance(kometaActionsCollapse, { toggle: false }).show()
  })
}
const openKometaActionsPanelBtn = document.getElementById('open-kometa-actions-panel-button')
if (openKometaActionsPanelBtn) {
  openKometaActionsPanelBtn.addEventListener('click', function() {
    if (kometaState.kometaStatus === 'running') return
    if (!kometaActionsCollapse || typeof bootstrap === 'undefined' || !bootstrap.Collapse) return
    bootstrap.Collapse.getOrCreateInstance(kometaActionsCollapse, { toggle: false }).show()
  })
}

updateFlagLabels(false, {
  onInitTooltips: initBootstrapTooltips,
  onLabelsUpdated: syncFinalAccordionRollups
}) // Default to friendly labels
const showCliToggle = document.getElementById('show-cli-toggle')
if (showCliToggle) {
  showCliToggle.addEventListener('change', function() {
    const showCli = this.checked
    updateFlagLabels(showCli, {
      onInitTooltips: initBootstrapTooltips,
      onLabelsUpdated: syncFinalAccordionRollups
    })
  })
}

function resolveFreshnessGateAfterBulkValidation () {
  const gateEl = document.getElementById('final-gate-state')
  if (gateEl) {
    gateEl.dataset.stage = 'config'
    gateEl.dataset.autoValidate = 'false'
    gateEl.dataset.bulkFresh = 'true'
  }
  const panel = document.getElementById('final-gate-panel')
  if (panel) panel.classList.add('d-none')
}

document.querySelectorAll('input[name="run-option"]').forEach(el => el.addEventListener('change', function () {
  const value = this.value
  updateLibraryVisibility(value)
  checkMaintenanceWarning(value)
  buildCommand()
}))

document.getElementById('times-input')?.addEventListener('input', buildCommand)

document.getElementById('library-multiselect')?.addEventListener('change', buildCommand)
document.querySelectorAll('input[name="mode-flag"]').forEach(el => el.addEventListener('change', buildCommand))
document.querySelectorAll('input[name="log-flag"]').forEach(el => el.addEventListener('change', buildCommand))

const checkboxFlags = [
  'delete-collections', 'delete-labels', 'read-only-config', 'low-priority',
  'no-report', 'no-missing', 'no-countdown', 'ignore-ghost',
  'ignore-schedules', 'no-verify-ssl', 'tests'
]

checkboxFlags.forEach(opt => {
  const checkbox = document.getElementById(`opt-${opt}`)
  if (checkbox) checkbox.addEventListener('change', buildCommand)
})


if (document.getElementById('run-command-output')) {
  const mainOption = (document.querySelector('input[name="run-option"]:checked') || {}).value
  checkMaintenanceWarning(mainOption)
  updateLibraryVisibility(mainOption)
  buildCommand()
}

initBootstrapTooltips(document, '[title]', { html: false, sanitize: true, placement: 'top', trigger: 'hover' })
initBootstrapTooltips(document)

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

document.getElementById('copy-command')?.addEventListener('click', function() {
  const command = document.getElementById('run-command-output').textContent.trim()
  if (!command || command.startsWith('⚠️')) return

  copyTextToClipboard(command)
    .then(() => showCopyButtonSuccess('#copy-icon', '#copy-text'))
    .catch(() => showToast('error', 'Copy failed. Please copy manually.'))
})

document.getElementById('copy-recovery-command')?.addEventListener('click', function() {
  const command = document.getElementById('recovery-command-output').textContent.trim()
  if (!command) return
  copyTextToClipboard(command)
    .then(() => showCopyButtonSuccess('#copy-recovery-icon', '#copy-recovery-text'))
    .catch(() => showToast('error', 'Copy failed. Please copy manually.'))
})

function startKometaCommand (command, opts = {}) {
  const startMode = opts.startMode || 'current'
  const requireValidated = opts.requireValidated !== false
  const startMessage = opts.startMessage || 'Starting Kometa...\n'

  if (kometaState.kometaUpdating) {
    showToast('warning', 'Kometa is updating. Please wait for it to finish before running.')
    return
  }

  if (kometaState.kometaValidationInProgress) {
    showToast('info', 'Kometa validation is still running. Please wait.')
    return
  }

  if (requireValidated && !kometaState.kometaValidated) {
    showToast('warning', 'Kometa has not been validated yet.')
    return
  }

  if (!command || command.startsWith('⚠️')) {
    showToast('error', 'Cannot run invalid command.')
    return
  }

  document.getElementById('run-now').disabled = true
  document.getElementById('run-now-label').textContent = 'Running...'
  const recoveryBtn = document.getElementById('run-recovery-command')
  if (recoveryBtn) recoveryBtn.disabled = true
  document.getElementById('stop-now').classList.remove('d-none')
  document.getElementById('run-output').classList.remove('d-none')
  document.getElementById('run-output-log').textContent = startMessage
  fetch('/start-kometa', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, start_mode: startMode })
  })
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        clearActiveRunCommandState()
        try { buildCommand() } catch {}
        document.getElementById('run-output-log').textContent = `❌ ${data.error}`
        document.getElementById('run-now').disabled = false
        document.getElementById('run-now-label').textContent = 'Run Now'
        document.getElementById('stop-now').classList.add('d-none')
        syncIncompleteRunActions()
        return
      }

      if (data.status === 'queued') {
        applyActiveRunCommandState(command, startMode)
        kometaState.kometaPendingStart = true
        const windowLabel = data.maintenance_window ? ` (${data.maintenance_window})` : ''
        const nowLabel = (typeof window.QS_formatTimestamp === 'function') ? window.QS_formatTimestamp() : new Date().toLocaleString()
        const message = `Plex maintenance active${windowLabel} at ${nowLabel}. Kometa will start automatically when it ends.`
        showToast('warning', message)
        document.getElementById('run-output-log').textContent = `${message}\n`
        {
          const runNowBtn = document.getElementById('run-now')
          if (runNowBtn) {
            runNowBtn.disabled = true
            runNowBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i> Waiting...'
          }
        }
        document.getElementById('stop-now').classList.add('d-none')
        if (kometaState.kometaStatusInterval) clearInterval(kometaState.kometaStatusInterval)
        kometaState.kometaStatusInterval = setInterval(checkKometaStatus, 5000)
        syncIncompleteRunActions()
        return
      }

      applyActiveRunCommandState(command, startMode)

      setTimeout(() => {
        kometaState.kometaPollingStarted = false
        startPollingIfNeeded()
      }, 5500)
    })
    .catch(() => {
      clearActiveRunCommandState()
      try { buildCommand() } catch {}
      document.getElementById('run-output-log').insertAdjacentHTML('beforeend', '\n⚠️ Failed to start Kometa.')
      document.getElementById('run-now').disabled = false
      document.getElementById('run-now-label').textContent = 'Run Now'
      document.getElementById('stop-now').classList.add('d-none')
      syncIncompleteRunActions()
    })
}

function startPollingIfNeeded () {
  if (kometaState.kometaPollingStarted) return
  kometaState.kometaPollingStarted = true
  if (kometaState.kometaInterval) clearInterval(kometaState.kometaInterval)
  if (kometaState.kometaStatusInterval) clearInterval(kometaState.kometaStatusInterval)
  if (kometaState.kometaProgressInterval) clearInterval(kometaState.kometaProgressInterval)
  fetchKometaLog()
  fetchRunProgress()
  kometaState.kometaInterval = setInterval(fetchKometaLog, 3000)
  kometaState.kometaStatusInterval = setInterval(checkKometaStatus, 5000)
  kometaState.kometaProgressInterval = setInterval(fetchRunProgress, 5000)
}

function resumeKometaLiveView () {
  if (document.hidden) return
  checkKometaStatus()
    .catch(() => null)
    .finally(() => {
      if (kometaState.kometaStatus === 'running' || kometaState.kometaPendingStart) {
        kometaState.kometaPollingStarted = false
        startPollingIfNeeded()
        fetchRunProgress(true)
        fetchKometaLog()
      }
    })
}

function stopProgressPolling () {
  if (kometaState.kometaProgressInterval) {
    clearInterval(kometaState.kometaProgressInterval)
    kometaState.kometaProgressInterval = null
  }
}

// Kometa Update Button Click
updateKometaBtn?.addEventListener('click', callUpdateKometa)
forceUpdateToggle?.addEventListener('change', function() {
  if (!kometaState.kometaUpdating) syncUpdateButtonLabel()
})
kometaBranchOverride?.addEventListener('change', function() {
  saveKometaBranchOverride()
  syncKometaBranchOverrideWarning()
  if (!kometaState.kometaUpdating) runKometaStatusPass(true)
})
loadSavedKometaBranchOverride()
syncKometaBranchOverrideWarning()
syncKometaSourceStatus()
setKometaUpdatePhaseBadge(kometaState.kometaUpdatePhaseStatus)
syncUpdateButtonLabel()
syncKometaRollupBadge()

// Sync visibility for timeout and divider on page load
const _syncOptContainer = (contId, chkId) => {
  const cont = document.getElementById(contId)
  const chk = document.getElementById(chkId)
  if (cont && chk) cont.classList.toggle('d-none', !chk.checked)
}
_syncOptContainer('opt-timeout-container', 'opt-timeout')
_syncOptContainer('opt-divider-container', 'opt-divider')
_syncOptContainer('opt-width-container', 'opt-width')

document.getElementById('opt-timeout')?.addEventListener('change', function() {
  document.getElementById('opt-timeout-container').classList.toggle('d-none', !this.checked)
  if (!this.checked) {
    document.getElementById('opt-timeout-val').value = ''
    document.getElementById('timeout-error').classList.add('d-none')
  }
  buildCommand()
})

document.getElementById('opt-width')?.addEventListener('change', function() {
  document.getElementById('opt-width-container').classList.toggle('d-none', !this.checked)
  if (!this.checked) {
    document.getElementById('opt-width-val').value = ''
    document.getElementById('width-error').classList.add('d-none')
  }
  buildCommand()
})

// Restrict divider input
document.getElementById('opt-divider-val')?.addEventListener('input', function() {
  this.value = this.value.replace(/\s/g, '').slice(0, 1)
  buildCommand()
})

// Prevent non-numeric input for Timeout
document.getElementById('opt-timeout-val')?.addEventListener('input', function() {
  const sanitized = this.value.replace(/[^0-9]/g, '')
  if (this.value !== sanitized) {
    this.value = sanitized
  }
  buildCommand()
})

// Prevent non-numeric input for Width
document.getElementById('opt-width-val')?.addEventListener('input', function() {
  const sanitized = this.value.replace(/[^0-9]/g, '')
  if (this.value !== sanitized) {
    this.value = sanitized
  }
  buildCommand()
})

document.getElementById('opt-divider')?.addEventListener('change', function() {
  document.getElementById('opt-divider-container').classList.toggle('d-none', !this.checked)
  if (!this.checked) {
    document.getElementById('opt-divider-val').value = ''
    document.getElementById('divider-error').classList.add('d-none')
  }
  buildCommand()
})

pauseLogBtn?.addEventListener('click', function() {
  logPollingPaused = !logPollingPaused
  if (logPollingPaused) {
    this.innerHTML = '<i class="bi bi-play-circle me-1"></i> Resume'
    showToast('info', 'Log polling paused.')
  } else {
    this.innerHTML = '<i class="bi bi-pause-circle me-1"></i> Pause'
    fetchKometaLog()
    startPollingIfNeeded()
  }
})

function updateStatRow (row, stats) {
  if (!row || !stats) return
  const keys = ['cache', 'debug', 'info', 'warning', 'error', 'critical', 'trace']
  keys.forEach(key => {
    const val = typeof stats[key] === 'number' ? stats[key] : 0
    const cell = row.querySelector(`[data-log-stat="${key}"]`)
    if (cell) cell.textContent = val
  })
}

function renderLogStats () {
  if (!logStats && !logStatsFiltered) return
  const totalStats = lastLogStatsTotal || computeLogStats(lastLogText)
  const filteredText = applyLogFilter(lastLogText, logFilter)
  const filteredStats = computeLogStats(filteredText)
  updateStatRow(logStats, totalStats)
  updateStatRow(logStatsFiltered, filteredStats)
}

function updateTailNotice () {
  if (!tailNotice) return
  const sizeLabel = tailSize === 'all' ? 'all lines' : `last ${tailSize} lines`
  tailNotice.textContent = `Showing ${sizeLabel} from meta.log`
}

function syncRunStatusVisibility () {
  if (!runStatusRow) return
  const hasText = Boolean(runStatusTimer.textContent || runStatusMetrics.textContent || runStatusLog.textContent)
  runStatusRow.classList.toggle('d-none', !hasText)
}

function updateRunStatus (data) {
  if (!runStatusRow) return
  const { timerText, metricsText } = buildRunStatusText(data, {
    formatStartedAt: formatTimestampLocal,
    formatElapsed: formatRunSeconds
  })
  runStatusTimer.textContent = timerText
  runStatusMetrics.textContent = metricsText
  updateRunSparklines(data)
  syncRunStatusVisibility()
}

function updateLogRecency (data) {
  if (!runStatusLog) return
  if (!data || typeof data.log_age_seconds !== 'number') {
    runStatusLog.textContent = ''
    syncRunStatusVisibility()
    return
  }
  const ageText = formatRunSeconds(data.log_age_seconds) || 'n/a'
  let logText = `meta.log updated ${ageText} ago`
  const totalLines = data?.stats?.total_lines ?? lastLogStatsTotal?.total_lines
  if (typeof totalLines === 'number' && Number.isFinite(totalLines)) {
    logText += ` • ${totalLines.toLocaleString()} lines`
  }
  if (data.log_is_stale && kometaState.kometaStatus === 'running') {
    logText += ' • waiting for new meta.log entries from this run'
    runStatusLog.classList.add('text-warning')
    runStatusLog.classList.remove('text-muted')
  } else {
    runStatusLog.classList.remove('text-warning')
    runStatusLog.classList.add('text-muted')
  }
  runStatusLog.textContent = logText
  syncRunStatusVisibility()
}

function updateClearFilterButton () {
  if (!clearFilterBtn) return
  const hasValue = filterInput.value.trim().length > 0
  clearFilterBtn.classList.toggle('d-none', !hasValue)
}

filterInput?.addEventListener('input', function() {
  logFilter = this.value.trim()
  const filtered = applyLogFilter(lastLogText, logFilter)
  runLog.textContent = filtered
  updateClearFilterButton()
  renderLogStats()
})

clearFilterBtn?.addEventListener('click', function() {
  logFilter = ''
  filterInput.value = ''
  const filtered = applyLogFilter(lastLogText, logFilter)
  runLog.textContent = filtered
  updateClearFilterButton()
  renderLogStats()
  if (filterInput) filterInput.focus()
})

if (levelButtons && levelButtons.length) {
  levelButtons.forEach(btn => btn.addEventListener('click', function() {
    const val = this.dataset.level || ''
    logFilter = val
    if (filterInput) filterInput.value = val
    const filtered = applyLogFilter(lastLogText, logFilter)
    if (runLog) runLog.textContent = filtered
    updateClearFilterButton()
    renderLogStats()
  }))
}

tailSelect?.addEventListener('change', function() {
  tailSize = this.value || '2000'
  const label = tailSize === 'all' ? 'entire log' : `last ${tailSize} lines of the log`
  if (tailNotice) tailNotice.innerHTML = `<i class="bi bi-info-circle"></i> Showing ${label}`
  fetchKometaLog()
})

autoScrollToggle?.addEventListener('change', function() {
  autoScrollEnabled = this.checked
  if (autoScrollEnabled && runLog) {
    runLog.scrollTop = runLog.scrollHeight
  }
})

downloadLogBtn?.addEventListener('click', function() {
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
if (!kometaCanReadLogs() && downloadLogBtn) {
  downloadLogBtn.disabled = true
}
updateClearFilterButton()
document.addEventListener('visibilitychange', function () {
  if (!document.hidden) {
    resumeKometaLiveView()
  }
})
window.addEventListener('pageshow', function () {
  resumeKometaLiveView()
})
// Ensure we check Kometa status once on page load to catch unclean exits.
// Keep the run area hidden until Kometa validation completes.
hideRunCommandSectionUntilValidated()
checkKometaStatus()
  .catch(() => null)
  .finally(() => {
    if (!document.getElementById('kometa-validation-log')) return
    if (kometaState.kometaStatus === 'running') return
    if (!kometaCanProbeRuntime()) {
      appendKometaStatusLine('ℹ️ External Kometa mode active. Runtime validation, launch, and update controls are disabled; generated config still syncs to the configured Kometa path.')
      return
    }
    Promise.resolve(runKometaStatusPass(false))
      .finally(() => {
        const stage = getFinalGateState().stage
        if (stage === 'todo' || stage === 'freshness') return
        if (kometaState.kometaStatus === 'running' || kometaState.kometaUpdating || kometaState.kometaValidationInProgress) return
        validateKometaRoot({ appendStatus: true })
      })
  })

if (kometaActionsCollapse) {
  kometaActionsCollapse.addEventListener('show.bs.collapse', () => {
    const stage = getFinalGateState().stage
    if (stage === 'todo' || stage === 'freshness') return
    if (!kometaCanProbeRuntime()) return
    if (kometaState.kometaStatus === 'running') {
      if (typeof bootstrap !== 'undefined' && bootstrap.Collapse) {
        bootstrap.Collapse.getOrCreateInstance(kometaActionsCollapse, { toggle: false }).hide()
      }
      return
    }
    if (!kometaState.kometaInstalled || kometaState.kometaValidated || kometaState.kometaValidationInProgress || kometaState.kometaUpdating) return
    validateKometaRoot()
  })
}

if (runCommandCollapse) {
  runCommandCollapse.addEventListener('show.bs.collapse', () => {
    if (!kometaCanLaunch()) {
      setRunCommandPlaceholderState()
      return
    }
    if (kometaState.kometaStatus === 'running') {
      clearRunCommandPlaceholderState()
      return
    }
    if (!kometaState.kometaValidated) {
      setRunCommandPlaceholderState()
    }
  })
}

if (document.getElementById('header-style')) {
  document.getElementById('header-style')?.addEventListener('change', function () {
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
    previouslyBlocked = !kometaState.showYAML
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
    const finalGateState = getFinalGateState()
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

    if (finalGateState.stage === 'freshness') {
      resolveFreshnessGateAfterBulkValidation()
      showToast('info', 'Validation complete. Refreshing Kometa...')
      setTimeout(() => window.location.reload(), 300)
      return
    }

    updateValidationGate()
    const anyNewlyValidated = Object.keys(results).some(key => results[key]?.status === 'validated' && !previousStatuses[key])
    if (previouslyBlocked && kometaState.showYAML) {
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

document.getElementById('run-now')?.addEventListener('click', function() {
  if (!kometaCanLaunch()) {
    showToast('info', 'External Kometa mode cannot launch Kometa from Quickstart. Quickstart can only sync config and optional logs in this mode.')
    return
  }
  startKometaCommand(getCurrentRunCommand(), {
    startMode: 'current',
    requireValidated: true,
    startMessage: 'Starting Kometa...\n'
  })
})

document.getElementById('run-recovery-command')?.addEventListener('click', function() {
  const command = getRecoveryRunCommand()
  const startMode = String(this.dataset.startMode || 'recovery').trim().toLowerCase() || 'recovery'
  const contextMismatch = String(this.dataset.contextMismatch || '').toLowerCase() === 'true'
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
document.getElementById('stop-now')?.addEventListener('click', function() {
  if (stopModal) {
    stopModal.show()
    return
  }
  performStopKometa()
})

confirmStopBtn?.addEventListener('click', function() {
  if (stopModal) stopModal.hide()
  performStopKometa()
})

function performStopKometa () {
  confirmStopBtn.disabled = true
  fetch('/stop-kometa', { method: 'POST' })
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        document.getElementById('run-output-log').insertAdjacentHTML('beforeend', `\n⚠️ ${data.error}`)
        showToast('error', data.error)
      } else {
        const msg = data.message || data.warning || 'Kometa process stopped.'
        document.getElementById('run-output-log').insertAdjacentHTML('beforeend', `\n🟥 ${msg}`)
        if (data.warning) {
          showToast('warning', data.warning)
        } else {
          showToast('success', msg)
        }
      }
      clearInterval(kometaState.kometaInterval)
      clearInterval(kometaState.kometaStatusInterval)
      stopProgressPolling()
      if (kometaState.lastRunProgressPayload) {
        const stoppedPayload = JSON.parse(JSON.stringify(kometaState.lastRunProgressPayload))
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
        kometaState.lastRunProgressPayload = stoppedPayload
        renderRunProgress(stoppedPayload)
      }
      kometaState.kometaStatus = 'not started'
      document.getElementById('run-now').disabled = false
      document.getElementById('run-now-label').textContent = 'Run Now'
      document.getElementById('stop-now').classList.add('d-none') // hide stop again
      updateRunNowState()
    })
    .catch(err => {
      console.error('Error stopping Kometa process:', err) // Optional for debugging
      document.getElementById('run-output-log').insertAdjacentHTML('beforeend', '\n⚠️ Error stopping process.')
      showToast('error', 'Error stopping Kometa process.')
    })
    .finally(() => {
      confirmStopBtn.disabled = false
    })
}

function fetchKometaLog () {
  if (logPollingPaused) return

  const logEl = runLog[0]
  const wasAtBottom = logEl ? (logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 5) : true

  logStatsPollCounter += 1
  const wantStats = (logStatsPollCounter % 5 === 0) || !lastLogStatsTotal
  const statsQuery = wantStats ? '&stats=1' : ''

  fetch(`/tail-log?size=${encodeURIComponent(tailSize)}${statsQuery}`)
    .then(res => res.json())
    .then(data => {
      if (!runLog) return
      if (data.error) {
        runLog.textContent = `❌ ${data.error}`
        updateLogRecency(null)
        return
      }
      lastLogText = data.log || ''
      updateLogRecency(data)
      if (data.stats) {
        lastLogStatsTotal = data.stats
      }
      const filtered = applyLogFilter(lastLogText, logFilter)
      runLog.textContent = filtered
      renderLogStats()
      fetchLogscanAnalysis(false, { updateHeaderBadge: updateLogscanHeaderBadge, kometaState })
      const shouldStick = autoScrollEnabled || wasAtBottom
      if (shouldStick && logEl) {
        logEl.scrollTop = logEl.scrollHeight
      }
    })
    .catch(err => {
      console.error('Error fetching Kometa log:', err)
      if (runLog) runLog.textContent = (runLog.textContent || '') + '\n⚠️ Error fetching log.'
    })
}

function checkKometaStatus () {
  return fetch('/kometa-status')
    .then(res => res.json())
    .then(data => {
      kometaState.latestKometaStatusPayload = data || null
      kometaState.kometaStatus = data.status || null
      kometaState.kometaPendingStart = Boolean(data.pending_start && data.status !== 'running')
      const updateBtn = updateKometaBtn
      const forceUpdate = forceUpdateToggle
      const runNow = document.getElementById('run-now')
      const stopNow = document.getElementById('stop-now')
      setKometaPrepareRunningState(data.status === 'running')

      // Disable update if Kometa is running or an update is in progress
      const shouldDisableUpdate = (data.status === 'running') || kometaState.kometaUpdating
      if (shouldDisableUpdate) {
        const why = kometaState.kometaUpdating ? 'Kometa is updating; wait for it to finish.' : 'Kometa is running; stop it before updating.'
        if (updateBtn) {
          updateBtn.disabled = true
          updateBtn.setAttribute('title', why)
          initBootstrapTooltips(updateBtn, '[title]', { html: false, sanitize: true, placement: 'top', trigger: 'hover' })
        }
        if (forceUpdate) forceUpdate.disabled = true
      } else {
        if (updateBtn) {
          updateBtn.disabled = false
          updateBtn.removeAttribute('title')
          disposeBootstrapTooltips(updateBtn, '[title]')
        }
        if (forceUpdate) forceUpdate.disabled = false
      }

      updateRunStatus(data)
      if (typeof window.QS_handleMaintenanceStatus === 'function') {
        window.QS_handleMaintenanceStatus(data)
      }
      if (kometaState.lastRunProgressPayload && data.status === 'running') {
        renderRunProgress(kometaState.lastRunProgressPayload)
      }

      if (data.pending_start && data.status !== 'running') {
        applyActiveRunCommandState(
          data.pending_command || kometaState.activeRunCommandOverride || getRecoveryRunCommand(),
          data.pending_start_mode || kometaState.activeRunCommandMode || 'recovery'
        )
        const windowLabel = data.maintenance_window ? ` (${data.maintenance_window})` : ''
        const nowLabel = (typeof window.QS_formatTimestamp === 'function') ? window.QS_formatTimestamp() : new Date().toLocaleString()
        const message = `Plex maintenance active${windowLabel} at ${nowLabel}. Kometa will start automatically when it ends.`
        runNow.disabled = true
        runNow.innerHTML = '<i class="bi bi-hourglass-split me-1"></i> Waiting...'
        stopNow.classList.add('d-none')
        document.getElementById('run-output').classList.remove('d-none')
        if (!document.getElementById('run-output-log').textContent.includes('Plex maintenance')) {
          document.getElementById('run-output-log').insertAdjacentHTML('beforeend', `\n${message}`)
        }
        syncIncompleteRunActions()
        if (kometaState.kometaStatusInterval) clearInterval(kometaState.kometaStatusInterval)
        kometaState.kometaStatusInterval = setInterval(checkKometaStatus, 5000)
        return
      }

      // Lock the Run UI while updating
      if (kometaState.kometaUpdating) {
        runNow.disabled = true
        runNow.innerHTML = '<i class="bi bi-hourglass me-1"></i> Updating...'
        stopNow.disabled = true
        syncIncompleteRunActions()
        return // don't do the rest while we're mid-update
      }

      // Handle Kometa process states
      if (data.status === 'running') {
        applyActiveRunCommandState(
          data.active_command || kometaState.activeRunCommandOverride || getCurrentRunCommand(),
          data.start_mode || kometaState.activeRunCommandMode || 'current'
        )
        kometaState.kometaPendingStart = false
        finalLogscanAnalyzeTriggered = false
        const _iralert = document.getElementById('incomplete-run-alert')
        if (_iralert) _iralert.classList.add('d-none')
        // Kometa is actively running → keep Run disabled, allow Stop
        revealRunCommandSection()
        runNow.disabled = true
        runNow.innerHTML = '<i class="bi bi-play-fill me-1"></i> <span id="run-now-label">Run Now</span>'
        stopNow.classList.remove('d-none')
        stopNow.disabled = false
        document.getElementById('run-output').classList.remove('d-none')
        syncIncompleteRunActions()
        startPollingIfNeeded()
        return
      }

      // If we reach here, it's either "done" or "not started"
      if (typeof kometaState.kometaInterval !== 'undefined' && kometaState.kometaInterval) clearInterval(kometaState.kometaInterval)
      if (typeof kometaState.kometaStatusInterval !== 'undefined' && kometaState.kometaStatusInterval) clearInterval(kometaState.kometaStatusInterval)
      stopProgressPolling()
      clearRunProgress(true)
      clearActiveRunCommandState()
      try { buildCommand() } catch {}

      if (runNow) runNow.innerHTML = '<i class="bi bi-play-fill me-1"></i> <span id="run-now-label">Run Now</span>'
      if (stopNow) {
        stopNow.classList.add('d-none')
        stopNow.disabled = false
      }
      updateRunNowState()

      if (data.status === 'done') {
        kometaState.kometaPendingStart = false
        if (!finalLogscanAnalyzeTriggered) {
          finalLogscanAnalyzeTriggered = true
          fetchLogscanAnalysis(true, { updateHeaderBadge: updateLogscanHeaderBadge, kometaState })
        }
        if (data.return_code === 0) {
          document.getElementById('run-output-log').insertAdjacentHTML('beforeend', '\n✅ Kometa finished successfully.')
        } else {
          document.getElementById('run-output-log').insertAdjacentHTML('beforeend', `\n⚠️ Kometa exited with code ${data.return_code}. Check logs for details.`)
        }
      } else if (data.status === 'not started') {
        kometaState.kometaPendingStart = false
        const outLog = document.getElementById('run-output-log')
        if (outLog) outLog.insertAdjacentHTML('beforeend', '\n🟥 Kometa is not running.')
      }
    })
    .catch(err => {
      kometaState.kometaPendingStart = false
      console.error('Error checking Kometa status:', err)
      const outLog = document.getElementById('run-output-log')
      if (outLog) outLog.insertAdjacentHTML('beforeend', '\n️  Failed to check Kometa status.')
    })
}
