// Maintenance-window helpers extracted from 900-kometa.js as part of
// the god-file split (see modules/kometa/_util.js for context).
//
// These functions coordinate the "Times / maintenance window" UI on
// the Kometa run page:
//   - toggleTimesInputVisibility: show/hide the times input row when
//     the user picks --times as their run mode
//   - getMaintenanceWindow: read the Plex maintenance window that the
//     backend wrote to a data-* attribute on the page
//   - checkMaintenanceWarning: show a warning if the user's chosen
//     schedule overlaps with the Plex maintenance window (Kometa can't
//     talk to Plex during maintenance, so we surface that)
//
// They all touch the DOM but share NO module-scoped state with the
// rest of 900-kometa.js. The `times-input` / `times-error` element
// IDs are also referenced from other functions in 900-kometa.js
// (updateRunOptionHeaderBadge, buildCommand) but those callers touch
// the DOM directly, not through helpers here.

import { isTimeWithinRange, isValidTimesFormat } from './_util.js'

/**
 * Show or hide the "times" input container based on the currently
 * selected main run option. When the user picks a mode other than
 * `--times`, we also proactively hide any lingering times validation
 * error so the UI doesn't look wrong after a mode switch.
 */
export function toggleTimesInputVisibility (mainOption) {
  const timesContainer = document.getElementById('times-input-container')
  if (mainOption === '--times') {
    timesContainer.classList.remove('d-none')
  } else {
    timesContainer.classList.add('d-none')
    document.getElementById('times-error').classList.add('d-none')
  }
}

/**
 * Return the currently-configured Plex maintenance window, as
 * `{ start, end }` HH:MM strings. Reads from the
 * `#plex-maintenance-window` element's `data-window` attribute,
 * which the backend populates with a string like "03:00–05:00".
 * Plain hyphen payloads are accepted too, because older support
 * payloads and tests may use "03:00-05:00".
 *
 * Returns null when the element is present but has no configured
 * window, or when the payload is malformed.
 */
export function getMaintenanceWindow () {
  const windowStr = document.getElementById('plex-maintenance-window')?.dataset.window || ''
  const matches = String(windowStr).match(/([01]\d|2[0-3]):[0-5]\d/g)
  if (!matches || matches.length < 2) return null
  return { start: matches[0], end: matches[1] }
}

export function getMaintenanceScheduleConflict (mainOption) {
  const maintenance = getMaintenanceWindow()
  if (!maintenance) return null

  if (mainOption === '') {
    const defaultTime = '05:00'
    if (isTimeWithinRange(defaultTime, maintenance.start, maintenance.end)) {
      return { maintenance, times: [defaultTime], source: 'default' }
    }
    return null
  }

  if (mainOption === '--times') {
    const timesInput = document.getElementById('times-input')?.value.trim() || ''
    if (!isValidTimesFormat(timesInput)) return null
    const times = timesInput.split('|').map(t => t.trim())
    const overlappingTimes = times.filter(t => isTimeWithinRange(t, maintenance.start, maintenance.end))
    if (overlappingTimes.length) {
      return { maintenance, times: overlappingTimes, source: 'times' }
    }
  }

  return null
}

/**
 * Show or hide the "your schedule overlaps Plex maintenance"
 * warning box. Handles both the implicit-schedule case (main option
 * empty -> Kometa's built-in 05:00 default) and the user's own
 * pipe-separated `--times` list.
 *
 * No-op when there's no configured maintenance window, or when the
 * user's --times input is invalid (they'll get a different, more
 * useful validation error from elsewhere in that case).
 */
export function checkMaintenanceWarning (mainOption) {
  const warningBox = document.getElementById('times-warning')
  if (!warningBox) return null
  warningBox.classList.add('d-none')

  const conflict = getMaintenanceScheduleConflict(mainOption)
  if (conflict) {
    const label = conflict.source === 'default' ? 'Kometa default time 05:00' : `Selected time${conflict.times.length > 1 ? 's' : ''} ${conflict.times.join(', ')}`
    warningBox.textContent = `${label} starts during Plex scheduled maintenance (${conflict.maintenance.start} - ${conflict.maintenance.end}). Choose a time after the window.`
    warningBox.classList.remove('d-none')
  }
  return conflict
}
