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
 * which the backend populates with a string like "03:00–05:00"
 * (note the EN-DASH separator, not a hyphen).
 *
 * Returns null when the element is present but has no configured
 * window, or when the payload is malformed.
 */
export function getMaintenanceWindow () {
  const windowStr = document.getElementById('plex-maintenance-window').dataset.window
  if (!windowStr || !windowStr.includes('–')) return null
  const [start, end] = windowStr.split('–').map(t => t.trim())
  return { start, end }
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
  const maintenance = getMaintenanceWindow()
  warningBox.classList.add('d-none')

  if (!maintenance) return

  if (mainOption === '') {
    // Kometa's implicit default schedule fires at 05:00.
    const defaultTime = '05:00'
    if (isTimeWithinRange(defaultTime, maintenance.start, maintenance.end)) {
      warningBox.classList.remove('d-none')
    }
    return
  }

  if (mainOption === '--times') {
    const timesInput = document.getElementById('times-input').value.trim()
    if (isValidTimesFormat(timesInput)) {
      const times = timesInput.split('|').map(t => t.trim())
      const overlaps = times.some(t => isTimeWithinRange(t, maintenance.start, maintenance.end))
      if (overlaps) {
        warningBox.classList.remove('d-none')
      }
    }
  }
}
