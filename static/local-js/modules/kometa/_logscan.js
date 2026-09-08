// Logscan rendering + polling for the Kometa run panel.
//
// After a Kometa run finishes (or during polling), Quickstart calls
// /logscan/analyze which parses the meta.log tail and returns a
// summary object with:
//
//   { summary: {
//       finished_at, run_time_seconds,
//       section_runtimes: { name: seconds, ... },
//       section_runtime_total_seconds,
//       section_runtime_delta_seconds
//     },
//     recommendations: [{ first_line, message }, ...],
//     missing_people: [name, ...],
//     missing_people_message: str,
//     error?: bool
//   }
//
// This module renders that payload into three DOM sections and
// updates the header badge with the analysis outcome.
//
// PUBLIC API:
//
//   renderLogscan(data, { updateHeaderBadge })
//     Paint the panel from a payload. Callers pass a callback for
//     header-badge updates so this module stays decoupled from the
//     _headerBadges module (avoids a fake dependency-inversion via
//     window globals).
//
//     Handles error/empty payloads by showing "Logscan unavailable."
//     and clearing sections.
//
//   fetchLogscanAnalysis(force, { updateHeaderBadge, kometaState })
//     Poll /logscan/analyze. Fetches when:
//       - force is true, OR
//       - pollCounter % 5 === 0 (every 5th call), OR
//       - kometaState.lastLogscanPayload is falsy (first run)
//
//     Skips when already in-flight (guards against overlapping fetches).
//     On success stashes the payload into kometaState.lastLogscanPayload
//     and calls renderLogscan.
//
// MODULE-LOCAL STATE:
//
//   pollCounter, analyzeInFlight
//     Kept module-scoped rather than passed in -- they're internal
//     bookkeeping for the poll cadence. Not observable from outside
//     unless the module exports resetLogscanState() (not currently
//     needed).

import { formatRunSeconds, linkifyText } from './_util.js'

// Module-local state (was in 900-kometa.js before extraction).
let pollCounter = 0
let analyzeInFlight = false
let lastAnalyzeAt = 0

/**
 * Resolve the panel DOM references. Called lazily so this module
 * loads cleanly in test environments where the DOM might not exist.
 * @private
 */
function resolvePanel () {
  return {
    panel: document.getElementById('logscan-panel'),
    summary: document.getElementById('logscan-summary'),
    recommendations: document.getElementById('logscan-recommendations'),
    missing: document.getElementById('logscan-missing-people'),
    sections: document.getElementById('logscan-sections')
  }
}

/**
 * Render an analysis payload into the logscan panel.
 *
 * @param {object} data  Payload from /logscan/analyze. Falsy or
 *                        error-flagged payloads render the "unavailable"
 *                        state and forward `{ error: true }` to the badge.
 * @param {object} [opts]
 * @param {(data:object) => void} [opts.updateHeaderBadge]
 *   Callback for the header-badge update. Receives the raw payload
 *   (or `{ error: true }` on failure). Optional -- omitted callers
 *   simply skip badge updates.
 */
export function renderLogscan (data, opts = {}) {
  const { updateHeaderBadge } = opts
  const dom = resolvePanel()
  if (!dom.panel) return

  if (!data || data.error) {
    if (dom.summary) dom.summary.textContent = ''
    if (dom.recommendations) dom.recommendations.innerHTML = '<div class="text-muted">Logscan unavailable.</div>'
    if (dom.missing) {
      dom.missing.classList.add('d-none')
      dom.missing.innerHTML = ''
    }
    if (updateHeaderBadge) updateHeaderBadge({ error: true })
    return
  }

  renderSummary(dom.summary, data.summary || {})
  renderRecommendations(dom.recommendations, data.recommendations)
  renderSections(dom.sections, data.summary || {})
  renderMissingPeople(dom.missing, data.missing_people, data.missing_people_message)

  if (updateHeaderBadge) updateHeaderBadge(data)
}

/**
 * Poll /logscan/analyze on a cadence and re-render the panel.
 *
 * @param {boolean} [force=false]  Bypass the mod-5 counter check.
 * @param {object} opts
 * @param {(data:object) => void} opts.updateHeaderBadge
 *   Forwarded to renderLogscan.
 * @param {object} opts.kometaState  Shared state slot used to cache
 *   the last successful payload (`kometaState.lastLogscanPayload`).
 *   Presence of the cached payload short-circuits the mod-5 gate.
 */
export function fetchLogscanAnalysis (force = false, opts = {}) {
  const { updateHeaderBadge, kometaState } = opts
  const dom = resolvePanel()
  if (!dom.panel) return
  pollCounter += 1
  const now = Date.now()
  const minIntervalMs = Math.max(0, Number(opts.minIntervalMs || 0) || 0)
  const intervalDue = !lastAnalyzeAt || minIntervalMs <= 0 || (now - lastAnalyzeAt) >= minIntervalMs
  const shouldFetch = force || ((pollCounter % 5 === 0) && intervalDue) || !(kometaState && kometaState.lastLogscanPayload)
  if (!shouldFetch || analyzeInFlight) return

  analyzeInFlight = true
  lastAnalyzeAt = now

  fetch('/logscan/analyze')
    .then(res => res.json())
    .then(data => {
      if (kometaState) kometaState.lastLogscanPayload = data
      renderLogscan(data, { updateHeaderBadge })
    })
    .catch(err => {
      console.error('Error fetching logscan analysis:', err)
      if (dom.recommendations) {
        dom.recommendations.innerHTML = '<div class="text-muted">Logscan unavailable.</div>'
      }
      if (updateHeaderBadge) updateHeaderBadge({ error: true })
    })
    .finally(() => {
      analyzeInFlight = false
    })
}

/**
 * Reset the poll counter and in-flight flag. Test-only export.
 * @private (for tests)
 */
export function resetLogscanStateForTests () {
  pollCounter = 0
  analyzeInFlight = false
  lastAnalyzeAt = 0
}

// ---------------------------------------------------------------------
// Private renderers (one per DOM section)
// ---------------------------------------------------------------------

function renderSummary (el, summary) {
  if (!el) return
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
  el.textContent = summaryText
}

function renderRecommendations (el, rawRecs) {
  if (!el) return
  const recs = Array.isArray(rawRecs) ? rawRecs : []
  el.innerHTML = ''
  if (!recs.length) {
    el.innerHTML = '<div class="text-muted">No recommendations yet.</div>'
    return
  }
  const MAX_RECS = 8
  recs.slice(0, MAX_RECS).forEach(rec => {
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
    el.appendChild(item)
  })
  if (recs.length > MAX_RECS) {
    const overflow = document.createElement('div')
    overflow.className = 'text-muted'
    overflow.textContent = `Showing ${MAX_RECS} of ${recs.length} recommendations.`
    el.appendChild(overflow)
  }
}

function renderSections (el, summary) {
  if (!el) return
  el.innerHTML = ''
  const sections = summary.section_runtimes || {}
  const sectionTotal = summary.section_runtime_total_seconds
  const sectionDelta = summary.section_runtime_delta_seconds
  const runTotal = summary.run_time_seconds
  const sectionEntries = Object.entries(sections)
    .filter(([, value]) => typeof value === 'number' && Number.isFinite(value))
    .sort((a, b) => b[1] - a[1])
  if (!sectionEntries.length) {
    el.innerHTML = '<div class="text-muted">No section runtimes yet.</div>'
    return
  }
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
  el.appendChild(headerDiv)
  const listLines = sectionEntries.map(([name, seconds]) => `${name}: ${formatRunSeconds(seconds)}`)
  const listDiv = document.createElement('div')
  listDiv.className = 'text-muted'
  listDiv.style.whiteSpace = 'pre-wrap'
  listDiv.textContent = listLines.join('\n')
  el.appendChild(listDiv)
}

function renderMissingPeople (el, rawMissing, rawMessage) {
  if (!el) return
  const missing = Array.isArray(rawMissing) ? rawMissing : []
  el.innerHTML = ''
  if (!missing.length) {
    el.classList.add('d-none')
    return
  }
  el.classList.remove('d-none')
  const message = rawMessage || 'Missing people posters detected.'
  const titleDiv = document.createElement('div')
  titleDiv.className = 'fw-semibold'
  titleDiv.textContent = 'Missing people posters'
  el.appendChild(titleDiv)
  const msgDiv = document.createElement('div')
  msgDiv.className = 'text-muted mb-2'
  msgDiv.style.whiteSpace = 'pre-wrap'
  msgDiv.innerHTML = linkifyText(message)
  el.appendChild(msgDiv)
  const listDiv = document.createElement('div')
  listDiv.className = 'text-muted'
  listDiv.style.whiteSpace = 'pre-wrap'
  listDiv.textContent = missing.map(name => `- ${name}`).join('\n')
  el.appendChild(listDiv)
}
