// Global flag so other handlers know an update is in progress
import {
  computeYamlLineCount,
  linkifyText,
  formatTimestampLocal,
  formatRunSeconds,
  coerceRunSeconds,
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
let logscanPollCounter = 0
let finalLogscanAnalyzeTriggered = false
let lastRunProgressPayload = null
let logscanAnalyzeInFlight = false
let runProgressInFlight = false
let latestKometaStatusPayload = null

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
const logscanPanel = document.getElementById('logscan-panel')
const logscanRecommendations = document.getElementById('logscan-recommendations')
const logscanSummary = document.getElementById('logscan-summary')
const logscanMissing = document.getElementById('logscan-missing-people')
const logscanSections = document.getElementById('logscan-sections')
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

function updateLibraryVisibility (mainOption) {
  const libSelect = document.getElementById('library-multiselect')
  const librarySection = libSelect ? libSelect.closest('.mb-2') : null
  if (!librarySection) return
  if (mainOption === '--run-libraries') {
    librarySection.classList.remove('d-none')
  } else {
    librarySection.classList.add('d-none')
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
      const label = document.querySelector(`label[for="${id}"]`)
      if (label) {
        const content = showCli ? flag : (flagsMap[flag]?.label || flag)
        label.innerHTML = `${content} <span class="text-info" data-bs-toggle="tooltip" title="${flagsMap[flag]?.description || ''}"><i class="bi bi-info-circle-fill ms-1"></i></span>`
      }
    })
  }

  updateLabels(runOptions, 'opt-')
  updateLabels(modeFlags, 'opt-')
  updateLabels(logFlags, 'opt-')
  updateLabels(otherFlags, 'opt-')

  initBootstrapTooltips(document)
  syncFinalAccordionRollups()
}

updateFlagLabels(false) // Default to friendly labels
const showCliToggle = document.getElementById('show-cli-toggle')
if (showCliToggle) {
  showCliToggle.addEventListener('change', function() {
    const showCli = this.checked
    updateFlagLabels(showCli)
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
    const progressMaintenance = payload && payload.maintenance_summary && typeof payload.maintenance_summary === 'object'
      ? payload.maintenance_summary
      : {}
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
    } else if (progressMaintenance.had_pause) {
      const summaryWindow = progressMaintenance.window ? ` (${progressMaintenance.window})` : ''
      const pauseCount = Number(progressMaintenance.pause_count || 0)
      const pauseSeconds = Number(progressMaintenance.pause_seconds || 0)
      const summaryLabel = pauseSeconds > 0
        ? (formatRunSeconds(pauseSeconds) || `${pauseCount || 1} pause${(pauseCount || 1) === 1 ? '' : 's'}`)
        : `${pauseCount || 1} pause${(pauseCount || 1) === 1 ? '' : 's'}`
      const stateLabel = progressMaintenance.open_pause ? 'Paused (log)' : 'Completed'
      maintenanceRow.innerHTML = `
        <span class="me-2 fw-semibold">Maintenance</span>
        <span class="badge text-bg-primary">${stateLabel}${summaryWindow}</span>
        <span class="badge text-bg-secondary">${summaryLabel}</span>
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
          const playlistTotal = typeof payload.playlist_total_seconds === 'number' ? payload.playlist_total_seconds : null
          const running = Boolean(payload.playlist_running)
          const elapsed = typeof payload.playlist_elapsed_seconds === 'number' ? payload.playlist_elapsed_seconds : null
          const detected = Boolean(payload.playlists_detected)
          if (running) {
            const label = elapsed != null ? formatRunSeconds(elapsed) : 'Running'
            return `<td class="text-end"><span class="badge text-bg-primary">${label || 'Running'}</span></td>`
          }
          if (playlistTotal != null && (playlistTotal > 0 || detected)) {
            return `<td class="text-end"><span class="badge text-bg-success">${formatRunSeconds(playlistTotal) || '0s'}</span></td>`
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

function fetchRunProgress (forceFull = false) {
  if (runProgressInFlight) return Promise.resolve(null)
  runProgressInFlight = true
  const url = forceFull ? '/logscan/progress?size=all' : '/logscan/progress'
  return fetch(url)
    .then(res => {
      if (!res.ok) return null
      return res.json()
    })
    .then(data => {
      if (!data) {
        if (kometaState.kometaStatus === 'running' && lastRunProgressPayload) {
          renderRunProgress(lastRunProgressPayload)
        } else {
          clearRunProgress(false)
        }
        return
      }
      renderRunProgress(data)
    })
    .catch(() => {
      if (kometaState.kometaStatus === 'running' && lastRunProgressPayload) {
        renderRunProgress(lastRunProgressPayload)
      } else {
        clearRunProgress(false)
      }
    })
    .finally(() => {
      runProgressInFlight = false
    })
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
    runStatusTimer.textContent = `Running since: ${startedAt} • Elapsed: ${elapsed || 'n/a'}`
    runStatusMetrics.textContent = `Kometa: ${cpuText} CPU • ${memRss} (${memPct}) | System: ${sysCpu} CPU • ${sysUsed} / ${sysTotal} (${sysPct})${diskText}`
  } else if (data && data.status === 'done') {
    runStatusTimer.textContent = 'Kometa run complete.'
    runStatusMetrics.textContent = ''
  } else {
    runStatusTimer.textContent = ''
    runStatusMetrics.textContent = ''
  }
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

function renderLogscan (data) {
  if (!logscanPanel) return
  if (!data || data.error) {
    logscanSummary.textContent = ''
    logscanRecommendations.innerHTML = '<div class="text-muted">Logscan unavailable.</div>'
    logscanMissing.classList.add('d-none')
    logscanMissing.innerHTML = ''
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
  logscanSummary.textContent = summaryText
  const recs = Array.isArray(data.recommendations) ? data.recommendations : []
  logscanRecommendations.innerHTML = ''
  if (!recs.length) {
    logscanRecommendations.innerHTML = '<div class="text-muted">No recommendations yet.</div>'
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
      const item = document.createElement('div')
      item.className = 'border rounded p-2 mb-2 bg-body-tertiary'
      const titleDiv = document.createElement('div')
      titleDiv.className = 'fw-semibold mb-1'
      titleDiv.textContent = title
      item.appendChild(titleDiv)
      const messageDiv = document.createElement('div')
      messageDiv.className = 'text-muted'
      messageDiv.style.whiteSpace = 'pre-wrap'
      messageDiv.innerHTML = linkifyText(message)
      item.appendChild(messageDiv)
      logscanRecommendations.appendChild(item)
    })
    if (recs.length > maxRecs) {
      const overflow = document.createElement('div')
      overflow.className = 'text-muted'
      overflow.textContent = `Showing ${maxRecs} of ${recs.length} recommendations.`
      logscanRecommendations.appendChild(overflow)
    }
  }

  logscanSections.innerHTML = ''
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
    const headerDiv = document.createElement('div')
    headerDiv.className = 'fw-semibold mb-1'
    headerDiv.textContent = header
    logscanSections.appendChild(headerDiv)
    const listLines = sectionEntries.map(([name, seconds]) => `${name}: ${formatRunSeconds(seconds)}`)
    const listDiv = document.createElement('div')
    listDiv.className = 'text-muted'
    listDiv.style.whiteSpace = 'pre-wrap'
    listDiv.textContent = listLines.join('\n')
    logscanSections.appendChild(listDiv)
  } else {
    logscanSections.innerHTML = '<div class="text-muted">No section runtimes yet.</div>'
  }

  const missing = Array.isArray(data.missing_people) ? data.missing_people : []
  logscanMissing.innerHTML = ''
  if (missing.length) {
    logscanMissing.classList.remove('d-none')
    const message = data.missing_people_message || 'Missing people posters detected.'
    const titleDiv = document.createElement('div')
    titleDiv.className = 'fw-semibold'
    titleDiv.textContent = 'Missing people posters'
    logscanMissing.appendChild(titleDiv)
    const msgDiv = document.createElement('div')
    msgDiv.className = 'text-muted mb-2'
    msgDiv.style.whiteSpace = 'pre-wrap'
    msgDiv.innerHTML = linkifyText(message)
    logscanMissing.appendChild(msgDiv)
    const listDiv = document.createElement('div')
    listDiv.className = 'text-muted'
    listDiv.style.whiteSpace = 'pre-wrap'
    listDiv.textContent = missing.map(name => `- ${name}`).join('\n')
    logscanMissing.appendChild(listDiv)
  } else {
    logscanMissing.classList.add('d-none')
  }

  updateLogscanHeaderBadge(data)
}

function fetchLogscanAnalysis (force = false) {
  if (!logscanPanel) return
  logscanPollCounter += 1
  const shouldFetch = force || (logscanPollCounter % 5 === 0) || !kometaState.lastLogscanPayload
  if (!shouldFetch || logscanAnalyzeInFlight) return

  logscanAnalyzeInFlight = true

  fetch('/logscan/analyze')
    .then(res => res.json())
    .then(data => {
      kometaState.lastLogscanPayload = data
      renderLogscan(data)
    })
    .catch(err => {
      console.error('Error fetching logscan analysis:', err)
      logscanRecommendations.innerHTML = '<div class="text-muted">Logscan unavailable.</div>'
      updateLogscanHeaderBadge({ error: true })
    })
    .finally(() => {
      logscanAnalyzeInFlight = false
    })
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
  missing_separator_placeholder: 'Missing separator placeholder',
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
      fetchLogscanAnalysis()
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
      latestKometaStatusPayload = data || null
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
      if (lastRunProgressPayload && data.status === 'running') {
        renderRunProgress(lastRunProgressPayload)
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
          fetchLogscanAnalysis(true)
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
