// Kometa update-phase badge + status log.
//
// This module owns the small cluster of functions that render a
// "which phase of the update is Kometa in?" badge, inline progress
// panel, and status log. The badge's phase is inferred from log-line
// text via a rule-based classifier.
//
// EXPORTS:
//
//   setKometaUpdatePhaseBadge(phase, progressMessage = null)
//        -- write a phase to the #kometa-update-phase-badge (updates
//           text + style class). Unknown phases coerce to 'idle'.
//           Also writes kometaState.kometaUpdatePhaseStatus.
//
//   inferKometaUpdatePhaseFromLine(line)
//        -- PURE FUNCTION. Given a log line, returns the phase it
//           implies (or null if it doesn't match any pattern).
//           Rule ordering matters: failed / ready / validating are
//           checked before dependencies / venv / preserving /
//           extracting / downloading / checking. The last-matching
//           rule wins if we ever have overlapping keywords -- but
//           the rules are designed so overlap doesn't happen in
//           practice.
//
//   updateKometaUpdatePhaseFromLine(line)
//        -- convenience: infers a phase from a log line and sets
//           the badge if the phase is non-null. No-op if the line
//           doesn't match any rule (preserves the last phase).
//
//   setKometaStatusLog(lines, phase = null)
//        -- replace the entire validation-log panel's contents.
//           lines can be a single string OR an array. If phase is
//           provided, also updates the badge.
//
//   appendKometaStatusLine(line)
//        -- append a single line to the validation-log and let the
//           panel scroll to the bottom. Auto-detects a phase from
//           the line via updateKometaUpdatePhaseFromLine.
//
// DOM ELEMENTS TOUCHED:
//
//   #kometa-update-phase-badge  (span, gets text + text-bg-* class)
//   #kometa-update-progress     (inline progress panel for long updates)
//   #kometa-validation-log      (pre or div, gets textContent /
//                                 insertAdjacentHTML)
//
// DOM lookups are lazy (per-call getElementById) so this module has
// zero cached DOM refs -- same pattern as _sparklines / _ui /
// _kometaBranch.

import { kometaState } from './_state.js'

// ---------------------------------------------------------------------
// Phase badge
// ---------------------------------------------------------------------

/**
 * Maps a phase name to its user-facing label + Bootstrap text-bg-*
 * class. Any phase not in this map coerces to 'idle' (safest default).
 *
 * Kept module-private (not exported) because callers should only ever
 * pass one of the eleven phase names, not roll their own.
 */
const PHASE_MAP = {
  idle: { label: 'Idle', klass: 'text-bg-secondary' },
  checking: { label: 'Checking', klass: 'text-bg-info' },
  queued: { label: 'Starting', klass: 'text-bg-primary' },
  downloading: { label: 'Downloading', klass: 'text-bg-primary' },
  extracting: { label: 'Extracting', klass: 'text-bg-warning' },
  preserving: { label: 'Preserving data', klass: 'text-bg-warning' },
  venv: { label: 'Preparing venv', klass: 'text-bg-info' },
  dependencies: { label: 'Installing deps', klass: 'text-bg-warning' },
  validating: { label: 'Validating', klass: 'text-bg-info' },
  ready: { label: 'Ready', klass: 'text-bg-success' },
  failed: { label: 'Failed', klass: 'text-bg-danger' }
}

/**
 * The full set of Bootstrap text-bg-* classes we manage on the badge.
 * Removed en masse before adding the current phase's class to keep
 * the badge visually consistent (only one at a time).
 */
const PHASE_BADGE_CLASSES = [
  'text-bg-secondary',
  'text-bg-info',
  'text-bg-primary',
  'text-bg-warning',
  'text-bg-success',
  'text-bg-danger'
]

const PHASE_PROGRESS = {
  idle: {
    percent: 0,
    message: 'No Kometa update is running.',
    alertClass: 'alert-secondary',
    barClass: 'bg-secondary',
    hidden: true
  },
  checking: {
    percent: 10,
    message: 'Checking Kometa version and update status.',
    alertClass: 'alert-info',
    barClass: 'bg-info',
    animated: true
  },
  queued: {
    percent: 5,
    message: 'Starting Kometa update job.',
    alertClass: 'alert-info',
    barClass: 'bg-primary',
    animated: true
  },
  downloading: {
    percent: 25,
    message: 'Downloading Kometa package.',
    alertClass: 'alert-info',
    barClass: 'bg-primary',
    animated: true
  },
  extracting: {
    percent: 40,
    message: 'Extracting Kometa files.',
    alertClass: 'alert-warning',
    barClass: 'bg-warning',
    animated: true
  },
  preserving: {
    percent: 55,
    message: 'Preserving Kometa logs and cache.',
    alertClass: 'alert-warning',
    barClass: 'bg-warning',
    animated: true
  },
  venv: {
    percent: 70,
    message: 'Preparing Kometa virtual environment.',
    alertClass: 'alert-info',
    barClass: 'bg-info',
    animated: true
  },
  dependencies: {
    percent: 85,
    message: 'Installing Kometa dependencies.',
    alertClass: 'alert-warning',
    barClass: 'bg-warning',
    animated: true
  },
  validating: {
    percent: 95,
    message: 'Validating Kometa after update.',
    alertClass: 'alert-info',
    barClass: 'bg-info',
    animated: true
  },
  ready: {
    percent: 100,
    message: 'Kometa update is complete.',
    alertClass: 'alert-success',
    barClass: 'bg-success'
  },
  failed: {
    percent: 100,
    message: 'Kometa update failed. Review the log below.',
    alertClass: 'alert-danger',
    barClass: 'bg-danger'
  }
}

const PROGRESS_ALERT_CLASSES = [
  'alert-secondary',
  'alert-info',
  'alert-primary',
  'alert-warning',
  'alert-success',
  'alert-danger'
]

const PROGRESS_BAR_CLASSES = [
  'bg-secondary',
  'bg-info',
  'bg-primary',
  'bg-warning',
  'bg-success',
  'bg-danger',
  'progress-bar-striped',
  'progress-bar-animated'
]

function renderKometaUpdateProgress (phase, progressMessage = null) {
  const container = document.getElementById('kometa-update-progress')
  if (!container) return

  const progress = PHASE_PROGRESS[phase] || PHASE_PROGRESS.idle
  const percent = Math.max(0, Math.min(100, Number(progress.percent) || 0))
  container.classList.toggle('d-none', Boolean(progress.hidden) && !progressMessage)
  container.classList.remove(...PROGRESS_ALERT_CLASSES)
  container.classList.add(progress.alertClass || 'alert-secondary')

  const title = document.getElementById('kometa-update-progress-title')
  const message = document.getElementById('kometa-update-progress-message')
  const percentBadge = document.getElementById('kometa-update-progress-percent')
  const bar = document.getElementById('kometa-update-progress-bar')

  if (title) title.textContent = 'Kometa update progress'
  if (message) message.textContent = progressMessage || progress.message
  if (percentBadge) percentBadge.textContent = `${percent}%`
  if (bar) {
    bar.style.width = `${percent}%`
    bar.setAttribute('aria-valuenow', String(percent))
    bar.classList.remove(...PROGRESS_BAR_CLASSES)
    bar.classList.add(progress.barClass || 'bg-secondary')
    if (progress.animated) bar.classList.add('progress-bar-striped', 'progress-bar-animated')
  }
}

/**
 * Write a phase to the update-phase badge. Unknown phases silently
 * coerce to 'idle'. Also updates kometaState.kometaUpdatePhaseStatus
 * so future callers can read the current phase without scraping DOM.
 *
 * No-op when the badge element is missing.
 *
 * @param {string} phase  See PHASE_MAP keys.
 * @param {?string} progressMessage  Optional message for the inline progress panel.
 */
export function setKometaUpdatePhaseBadge (phase, progressMessage = null) {
  const badge = document.getElementById('kometa-update-phase-badge')
  if (!badge) return

  const normalized = Object.prototype.hasOwnProperty.call(PHASE_MAP, phase) ? phase : 'idle'
  const next = PHASE_MAP[normalized]
  kometaState.kometaUpdatePhaseStatus = normalized

  badge.classList.remove(...PHASE_BADGE_CLASSES)
  badge.classList.add(next.klass)
  badge.textContent = next.label
  renderKometaUpdateProgress(normalized, progressMessage)
}

// ---------------------------------------------------------------------
// Phase inference from log lines
// ---------------------------------------------------------------------

/**
 * Given a log line, return the phase it implies (or null).
 *
 * Rule ordering is important: earlier rules take precedence. The
 * design is roughly "outcome first, then reverse-chronological through
 * the update flow", so a line like "Kometa update completed successfully"
 * classifies as 'ready' even if it also happens to contain the word
 * "extracting" somewhere.
 *
 * PURE FUNCTION -- no DOM, no state reads. Safe to call in a hot loop.
 *
 * @param {string} line
 * @returns {'failed' | 'ready' | 'validating' | 'dependencies' | 'venv' |
 *           'preserving' | 'extracting' | 'downloading' | 'checking' |
 *           null}
 */
export function inferKometaUpdatePhaseFromLine (line) {
  const text = String(line || '').trim()
  if (!text) return null
  const lower = text.toLowerCase()

  // Terminal states first -- an update that finished (successfully or
  // not) should not be reclassified as 'checking' just because the
  // final line happens to mention 'kometa branch'.
  if (
    lower.startsWith('\u274c') || // red X emoji (server prefixes failures with this)
    lower.includes(' update failed') ||
    lower.includes('error occurred during kometa update') ||
    lower.includes('aborting extraction') ||
    lower.includes('failed to fetch kometa update progress')
  ) {
    return 'failed'
  }
  if (
    lower.includes('kometa root validated successfully') ||
    lower.includes('kometa root is valid and ready') ||
    lower.includes('kometa update completed successfully') ||
    lower.includes('kometa is already up to date') ||
    lower.includes('kometa updated via zip')
  ) {
    return 'ready'
  }

  // In-progress phases, checked in reverse-workflow order: something
  // that mentions "validating" AFTER "installing deps" is more useful
  // than the earlier "installing" hint.
  if (
    lower.includes('re-validating kometa after update') ||
    lower.includes('please wait while we validate') ||
    lower.includes('validate your kometa installation')
  ) {
    return 'validating'
  }
  if (lower.includes('installing requirements') || lower.includes('upgrading pip')) {
    return 'dependencies'
  }
  if (
    lower.includes('creating virtual environment') ||
    lower.includes('existing kometa-venv looks invalid') ||
    lower.includes('venv python') ||
    lower.includes('pyvenv.cfg')
  ) {
    return 'venv'
  }
  if (
    lower.includes('backed up kometa logs/cache') ||
    lower.includes('restored kometa logs/cache') ||
    lower.includes('kometa backup')
  ) {
    return 'preserving'
  }
  if (
    (lower.includes('removed ') && lower.includes('existing entr')) ||
    lower.includes('removing existing kometa contents') ||
    lower.includes('existing path still present after cleanup') ||
    lower.includes('extracted version file') ||
    lower.includes('extracted to:')
  ) {
    return 'extracting'
  }
  if (lower.includes('downloading ') && lower.includes('.zip')) {
    return 'downloading'
  }
  if (
    lower.includes('resolving upstream sha') ||
    (lower.includes('upstream ') && lower.includes(' sha')) ||
    lower.includes('refreshing kometa status') ||
    lower.includes('checking kometa') ||
    lower.includes('kometa branch selected') ||
    lower.includes('quickstart branch:') ||
    lower.includes('remote version source') ||
    lower.includes('kometa branch override selected') ||
    lower.includes('kometa branch selection: auto')
  ) {
    return 'checking'
  }

  return null
}

/**
 * Infer a phase from a log line and, if the phase is non-null,
 * update the badge. No-op for lines that don't match any rule --
 * this preserves whatever phase was set previously, which is what
 * we want (many log lines are neutral prose, e.g. blank lines,
 * separators, or arbitrary info).
 *
 * @param {string} line
 */
export function updateKometaUpdatePhaseFromLine (line) {
  const phase = inferKometaUpdatePhaseFromLine(line)
  if (phase) setKometaUpdatePhaseBadge(phase)
}

// ---------------------------------------------------------------------
// Status log
// ---------------------------------------------------------------------

/**
 * Replace the entire status-log panel's contents with `lines` (a
 * string or array of strings). If `phase` is provided, also update
 * the badge.
 *
 * Empty text becomes ''. Non-empty text gets a trailing newline so
 * the last line renders cleanly in a <pre>-styled container.
 *
 * @param {string | string[]} lines
 * @param {string | null} [phase]
 */
export function setKometaStatusLog (lines, phase = null) {
  const logBox = document.getElementById('kometa-validation-log')
  if (!logBox) return
  const text = Array.isArray(lines) ? lines.join('\n') : String(lines || '')
  logBox.textContent = text ? `${text}\n` : ''
  // NOTE: the original code did `if (logBox[0]) logBox[0].scrollTop = ...`
  // which is jQuery-style indexing on a plain DOM node -- always
  // undefined, so the scroll-to-bottom never actually happened here.
  // Preserving that (non-)behavior verbatim to keep this refactor
  // 100% behavior-compatible. If you WANT the scroll (which
  // appendKometaStatusLine below does correctly), fix it in a
  // follow-up so the diff stays clear.
  if (logBox[0]) logBox[0].scrollTop = logBox[0].scrollHeight
  if (phase) setKometaUpdatePhaseBadge(phase)
}

/**
 * Append a single line to the status-log panel and scroll to keep
 * it in view. Also auto-updates the phase badge if the line matches
 * a phase-inference rule.
 *
 * Uses insertAdjacentHTML('beforeend', ...) so callers can embed
 * limited HTML (e.g. links) in status lines. Callers that pass
 * user-supplied text should escape it first.
 *
 * @param {string} line
 */
export function appendKometaStatusLine (line) {
  const logBox = document.getElementById('kometa-validation-log')
  if (!logBox) return
  logBox.insertAdjacentHTML('beforeend', `${line}\n`)
  logBox.scrollTop = logBox.scrollHeight
  updateKometaUpdatePhaseFromLine(line)
}
