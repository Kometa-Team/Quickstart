// Kometa run-progress: the live UI that shows library-by-library
// progress during a `kometa.py` run.
//
// This module owns three things:
//
//   1. renderRunProgress(payload)
//        Paints the entire #run-progress panel from a
//        /logscan/progress response. This is the biggest and most
//        complex function -- ~270 lines -- because it renders:
//          - the top progress bar + summary line ("X/Y libraries...")
//          - the "Preparation" badge row
//          - the "Maintenance" badge row (paused / active / had_pause)
//          - the per-library table with per-phase duration cells
//          - the totals footer (sum per phase + grand total)
//
//   2. clearRunProgress(resetCache = false)
//        Hides the panel + maintenance row. When resetCache=true also
//        clears the module's memory of the last-rendered payload so
//        the next render starts fresh.
//
//   3. fetchRunProgress(forceFull = false)
//        Hits /logscan/progress and paints the result. On failure or
//        empty response: redraws the last successful payload IF
//        Kometa is still running (to avoid flickering the panel off
//        during a transient network hiccup); otherwise clears.
//
// SHARED STATE (via _state.js):
//
//   kometaState.lastRunProgressPayload
//     Last /logscan/progress response successfully rendered. Enables
//     the "keep showing what we had" fallback in fetchRunProgress.
//
//   kometaState.runProgressInFlight
//     Guard against overlapping /logscan/progress fetches.
//
//   kometaState.latestKometaStatusPayload
//     READ ONLY here. Owned by checkKometaStatus in 900-kometa.js.
//     Used by the Maintenance-row logic to decide whether to show
//     Paused / Window Active / had_pause badges.
//
//   kometaState.kometaStatus
//     READ ONLY here. Used by fetchRunProgress to decide whether a
//     transient error should fall back to the cached payload
//     (Kometa still running -> yes) or clear the panel (idle -> no).
//
// PHASE ORDER:
//
//   The 5-phase order (operations / metadata / collections / overlays
//   / playlists) is exported as runPhaseOrder for tests that want to
//   assert against phase labels. Server responses can override the
//   order via payload.phase_order.
//
// TIMESTAMP FORMATTING:
//
//   The "Last updated" line uses window.QS_formatTimestamp when
//   available (defined by shared JS in 000-base.js) so the whole app
//   agrees on timestamp formatting. Falls back to
//   Date#toLocaleString when the global isn't present -- keeps this
//   module importable in test contexts.

import { kometaState } from './_state.js'
import { coerceRunSeconds, formatRunSeconds, nbspLeadingSpaces } from './_util.js'

/**
 * Canonical phase order for the run-progress panel. Server can
 * override via payload.phase_order.
 */
export const runPhaseOrder = [
  { key: 'operations', label: 'Operations' },
  { key: 'metadata', label: 'Metadata' },
  { key: 'collections', label: 'Collections' },
  { key: 'overlays', label: 'Overlays' },
  { key: 'playlists', label: 'Playlists' }
]

/**
 * Paint the #run-progress panel from a /logscan/progress payload.
 *
 * No-ops (silently) when:
 *   - #run-progress element is missing
 *   - payload is falsy OR payload.libraries isn't an array
 *
 * See module docstring for the sections it renders.
 *
 * @param {object} payload  /logscan/progress response
 */
export function renderRunProgress (payload) {
  const container = document.getElementById('run-progress')
  if (!container) return

  if (!payload || !Array.isArray(payload.libraries)) {
    container.classList.add('d-none')
    return
  }

  kometaState.lastRunProgressPayload = payload
  if (typeof window !== 'undefined' && typeof window.QS_handleKometaRunProgress === 'function') {
    window.QS_handleKometaRunProgress(payload)
  }
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

  renderPreparationRow(payload)
  renderMaintenanceRow(payload)

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
  renderLibraryRows(payload, visibleLibraries, phasesToShow, phaseIndexLookup)
  renderLibraryFooter(payload, libraries, visibleLibraries, phasesToShow)

  container.classList.remove('d-none')
}

/**
 * "Preparation" badge row. Green when locked, blue when live-updating.
 * Hidden when no preparation timing is available.
 */
function renderPreparationRow (payload) {
  const prepRow = document.getElementById('run-prep-row')
  if (!prepRow) return
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

/**
 * "Maintenance" badge row. Priority (highest to lowest):
 *   1. status.maintenance_paused  -> yellow "Paused (elapsed)" badge
 *   2. status.maintenance_active  -> yellow "Window Active" badge
 *   3. payload.maintenance_summary.had_pause -> blue "Completed / Paused (log)"
 *   4. otherwise hidden
 */
function renderMaintenanceRow (payload) {
  const maintenanceRow = document.getElementById('run-maintenance-row')
  if (!maintenanceRow) return
  const statusData = kometaState.latestKometaStatusPayload || {}
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

/**
 * Per-library table rows. Each row: name / type / status badge /
 * one duration cell per visible phase.
 *
 * Phase cells fall into 5 flavors:
 *   - Playlists cell (special): live "Running Xs" while playlist is
 *     running, green total when done, "Not Configured" when finished
 *     with no playlists detected, em-dash otherwise
 *   - Skipped library: em-dash
 *   - Currently running phase: blue "Running (elapsed)" badge
 *   - Explicit phase with seconds: green "Xs" badge
 *   - Inferred completed phase (no seconds but past): "Not Configured"
 *   - Default: em-dash
 */
function renderLibraryRows (payload, visibleLibraries, phasesToShow, phaseIndexLookup) {
  const rows = document.getElementById('run-library-rows')
  if (!rows) return
  rows.innerHTML = visibleLibraries.map(entry => {
    let klass = 'text-bg-secondary'
    if (entry.status === 'Done') klass = 'text-bg-success'
    else if (entry.status === 'In progress') klass = 'text-bg-primary'
    else if (entry.status === 'Stopped') klass = 'text-bg-danger'
    else if (entry.status === 'Skipped') klass = 'text-bg-dark'
    const typeLabel = entry.type ? entry.type : '\u2014'
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
    // "Inferred" = phases before the last-seen index that don't have
    // explicit durations. These get a "Not Configured" badge because
    // if we didn't see them explicitly but we're past them, Kometa
    // must have skipped them (config didn't enable them for this lib).
    const inferredPhases = new Set()
    if (entry.status !== 'Skipped' && lastSeenIndex >= 0) {
      phasesToShow.forEach(phase => {
        const idx = phaseIndexLookup.get(phase.key)
        if (idx != null && idx < lastSeenIndex && !explicitPhases.has(phase.key)) {
          inferredPhases.add(phase.key)
        }
      })
    }

    const durationCells = phasesToShow
      .map(phase => renderPhaseCell(payload, entry, phase, durations, currentPhaseForRow, explicitPhases, inferredPhases))
      .join('')

    return `
        <tr>
          <td><code>${nbspLeadingSpaces(entry.name)}</code></td>
          <td>${typeLabel}</td>
          <td><span class="badge ${klass}">${entry.status}</span></td>
          ${durationCells}
        </tr>
      `
  }).join('')
}

/**
 * Render a single per-library, per-phase duration cell. See the
 * "5 flavors" note in renderLibraryRows for the branching logic.
 */
function renderPhaseCell (payload, entry, phase, durations, currentPhaseForRow, explicitPhases, inferredPhases) {
  // Playlists cell is special: it comes from top-level payload fields,
  // not from per-library durations.
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
    return '<td class="text-end text-muted small">\u2014</td>'
  }
  const seconds = durations[phase.key]
  const hasSeconds = typeof seconds === 'number' && Number.isFinite(seconds)
  const isRunning = currentPhaseForRow === phase.key
  const isExplicit = explicitPhases.has(phase.key)
  const isInferred = inferredPhases.has(phase.key)
  if (entry.status === 'Skipped') {
    return '<td class="text-end text-muted small">\u2014</td>'
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
  return '<td class="text-end text-muted small">\u2014</td>'
}

/**
 * Table footer: per-phase totals + grand total row. Hidden when
 * there are no libraries or no visible phases.
 *
 * Grand total = preparation seconds (locked > live) + sum of per-phase
 * totals across all visible non-Skipped libraries.
 */
function renderLibraryFooter (payload, libraries, visibleLibraries, phasesToShow) {
  const footer = document.getElementById('run-library-footer')
  const totalRow = document.getElementById('run-library-total-row')
  if (!footer || !totalRow) return
  if (!libraries.length || !phasesToShow.length) {
    footer.classList.add('d-none')
    return
  }
  const totals = new Map(phasesToShow.map(phase => [phase.key, 0]))
  visibleLibraries.forEach(entry => {
    if (entry.status === 'Skipped') return
    const durations = entry.durations || {}
    phasesToShow.forEach(phase => {
      // Playlists total comes from payload, not from per-library durations.
      if (phase.key === 'playlists') return
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
    return '<td class="text-end text-muted small">\u2014</td>'
  }).join('')
  const totalLabel = grandTotal > 0 ? `<span class="badge text-bg-success">${formatRunSeconds(grandTotal)}</span>` : '\u2014'
  totalRow.innerHTML = `<td class="fw-semibold">Total</td><td>\u2014</td><td>${totalLabel}</td>${totalCells}`
  footer.classList.remove('d-none')
}

/**
 * Hide the run-progress panel + maintenance row.
 *
 * @param {boolean} [resetCache=false]  When true also clears
 *   kometaState.lastRunProgressPayload so the next render starts
 *   fresh. Callers set this true when a run ends; leave false when
 *   the hide is transient (e.g. between polls).
 */
export function clearRunProgress (resetCache = false) {
  const container = document.getElementById('run-progress')
  if (container) container.classList.add('d-none')
  const maintenanceRow = document.getElementById('run-maintenance-row')
  if (maintenanceRow) maintenanceRow.classList.add('d-none')
  if (resetCache) kometaState.lastRunProgressPayload = null
}

/**
 * Fetch /logscan/progress and render. Guarded against overlapping
 * fetches via kometaState.runProgressInFlight.
 *
 * Failure modes:
 *   - overlap (already in flight): resolves null immediately, no fetch
 *   - non-ok response: falls through to null branch (see below)
 *   - null / empty payload OR fetch reject:
 *       * if Kometa is still running AND we have a cached payload:
 *         redraw the cached payload (avoid flicker)
 *       * otherwise: clearRunProgress(false)
 *
 * @param {boolean} [forceFull=false]  When true asks the server for
 *   the full library set (bypasses server-side windowing).
 * @returns {Promise}
 */
export function fetchRunProgress (forceFull = false) {
  if (kometaState.runProgressInFlight) return Promise.resolve(null)
  kometaState.runProgressInFlight = true
  const url = forceFull ? '/logscan/progress?size=all' : '/logscan/progress'
  return fetch(url)
    .then(res => {
      if (!res.ok) return null
      return res.json()
    })
    .then(data => {
      if (!data) {
        if (kometaState.kometaStatus === 'running' && kometaState.lastRunProgressPayload) {
          renderRunProgress(kometaState.lastRunProgressPayload)
        } else {
          clearRunProgress(false)
        }
        return
      }
      if (data.status === 'queued' || data.status === 'waiting_for_log' || data.pending_start) {
        clearRunProgress(false)
        return
      }
      renderRunProgress(data)
    })
    .catch(() => {
      if (kometaState.kometaStatus === 'running' && kometaState.lastRunProgressPayload) {
        renderRunProgress(kometaState.lastRunProgressPayload)
      } else {
        clearRunProgress(false)
      }
    })
    .finally(() => {
      kometaState.runProgressInFlight = false
    })
}
