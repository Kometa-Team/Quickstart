// Tests for static/local-js/modules/kometa/_maintenanceWindow.js
//
// These functions all touch the DOM but share no module-scoped state
// with the rest of 900-kometa.js. Every test builds a fresh fixture
// DOM in beforeEach and inspects the .d-none class transitions after
// calling the module's functions. That mirrors the actual runtime
// behavior: Bootstrap uses .d-none for show/hide.
//
// Coverage strategy:
//   - toggleTimesInputVisibility: verify both branches AND the side
//     effect of hiding the error box when the mode changes away from
//     --times
//   - getMaintenanceWindow: exhaustive on the parse-or-null contract
//     (well-formed, missing attribute, missing separator, non-ASCII
//     en-dash boundary)
//   - checkMaintenanceWarning: 3 x 3 matrix covering (implicit
//     default / --times valid / --times invalid) x (window unset /
//     overlaps / doesn't overlap)

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  toggleTimesInputVisibility,
  getMaintenanceWindow,
  checkMaintenanceWarning
} from '../../../static/local-js/modules/kometa/_maintenanceWindow.js'

// ---------------------------------------------------------------------
// Fixture DOM
// ---------------------------------------------------------------------
//
// Mirrors the shape of the real templates: a container div with the
// times input inside, a hidden validation-error row, a maintenance
// data-carrier div, and a warning box. All start hidden (d-none)
// except the container, which the real template shows only when the
// user has selected --times.

function installFixtureDom ({ maintenanceWindow = '' } = {}) {
  document.body.innerHTML = `
    <div id="times-input-container" class="d-none">
      <input id="times-input" type="text" value="" />
      <div id="times-error" class="d-none">Invalid time format</div>
    </div>
    <div id="plex-maintenance-window" data-window="${maintenanceWindow}"></div>
    <div id="times-warning" class="d-none">Overlaps with Plex maintenance</div>
  `
}

afterEach(() => {
  document.body.innerHTML = ''
})

// ---------------------------------------------------------------------
// toggleTimesInputVisibility
// ---------------------------------------------------------------------

describe('toggleTimesInputVisibility', () => {
  beforeEach(() => {
    installFixtureDom()
  })

  it('reveals the times container when mainOption is --times', () => {
    const container = document.getElementById('times-input-container')
    expect(container.classList.contains('d-none')).toBe(true) // sanity
    toggleTimesInputVisibility('--times')
    expect(container.classList.contains('d-none')).toBe(false)
  })

  it('hides the times container for any other mainOption', () => {
    const container = document.getElementById('times-input-container')
    container.classList.remove('d-none') // pretend it was visible
    toggleTimesInputVisibility('--run')
    expect(container.classList.contains('d-none')).toBe(true)
  })

  it('hides the times container when mainOption is empty', () => {
    const container = document.getElementById('times-input-container')
    container.classList.remove('d-none')
    toggleTimesInputVisibility('')
    expect(container.classList.contains('d-none')).toBe(true)
  })

  it('also hides the times-error box when switching away from --times', () => {
    // Simulate an in-progress error state: container visible, error visible
    const container = document.getElementById('times-input-container')
    const error = document.getElementById('times-error')
    container.classList.remove('d-none')
    error.classList.remove('d-none')

    toggleTimesInputVisibility('--run')

    expect(container.classList.contains('d-none')).toBe(true)
    expect(error.classList.contains('d-none')).toBe(true)
  })

  it('does NOT touch times-error when switching TO --times (only when switching away)', () => {
    // If the user is coming back to --times and there was a lingering
    // error, we want to preserve it so they still see it. The function
    // deliberately only hides the error in the else branch.
    const error = document.getElementById('times-error')
    error.classList.remove('d-none')

    toggleTimesInputVisibility('--times')

    expect(error.classList.contains('d-none')).toBe(false)
  })
})

// ---------------------------------------------------------------------
// getMaintenanceWindow
// ---------------------------------------------------------------------

describe('getMaintenanceWindow', () => {
  it('returns { start, end } for a well-formed window', () => {
    installFixtureDom({ maintenanceWindow: '03:00–05:00' })
    expect(getMaintenanceWindow()).toEqual({ start: '03:00', end: '05:00' })
  })

  it('trims whitespace around the times', () => {
    installFixtureDom({ maintenanceWindow: '  03:00 – 05:00  ' })
    expect(getMaintenanceWindow()).toEqual({ start: '03:00', end: '05:00' })
  })

  it('returns null when the data-window attribute is empty', () => {
    installFixtureDom({ maintenanceWindow: '' })
    expect(getMaintenanceWindow()).toBeNull()
  })

  it('returns null when the payload lacks the en-dash separator', () => {
    // A hyphen (`-`) is NOT the same as the en-dash (`–`). The backend
    // deliberately uses the en-dash to make the separator visually
    // distinct in the maintenance summary UI.
    installFixtureDom({ maintenanceWindow: '03:00-05:00' })
    expect(getMaintenanceWindow()).toBeNull()
  })

  it('returns null when the payload has garbage', () => {
    installFixtureDom({ maintenanceWindow: 'not-a-window' })
    expect(getMaintenanceWindow()).toBeNull()
  })

  it('handles a payload that is just the en-dash (empty start/end)', () => {
    installFixtureDom({ maintenanceWindow: '–' })
    // Splitting '–' by '–' produces ['', ''] which are trimmed to '' each.
    // The contract is "the string included a separator", so this is a
    // known-degenerate but non-null case. Both fields are empty strings.
    expect(getMaintenanceWindow()).toEqual({ start: '', end: '' })
  })
})

// ---------------------------------------------------------------------
// checkMaintenanceWarning
// ---------------------------------------------------------------------

describe('checkMaintenanceWarning', () => {
  function warningIsVisible () {
    return !document.getElementById('times-warning').classList.contains('d-none')
  }

  describe('when there is no configured maintenance window', () => {
    beforeEach(() => {
      installFixtureDom({ maintenanceWindow: '' })
    })

    it('hides the warning for the implicit-default mode', () => {
      // Pre-set warning to visible to prove the function actively hides
      document.getElementById('times-warning').classList.remove('d-none')
      checkMaintenanceWarning('')
      expect(warningIsVisible()).toBe(false)
    })

    it('hides the warning for --times mode', () => {
      document.getElementById('times-warning').classList.remove('d-none')
      document.getElementById('times-input').value = '05:00|17:00'
      checkMaintenanceWarning('--times')
      expect(warningIsVisible()).toBe(false)
    })
  })

  describe('with mainOption="" (Kometa\'s implicit 05:00 default)', () => {
    it('shows the warning when 05:00 falls inside the maintenance window', () => {
      installFixtureDom({ maintenanceWindow: '04:00–06:00' })
      checkMaintenanceWarning('')
      expect(warningIsVisible()).toBe(true)
    })

    it('hides the warning when 05:00 is outside the maintenance window', () => {
      installFixtureDom({ maintenanceWindow: '01:00–02:00' })
      checkMaintenanceWarning('')
      expect(warningIsVisible()).toBe(false)
    })

    it('hides the warning when 05:00 is exactly AT the window end (exclusive)', () => {
      // Range check is [start, end) - end is exclusive
      installFixtureDom({ maintenanceWindow: '03:00–05:00' })
      checkMaintenanceWarning('')
      expect(warningIsVisible()).toBe(false)
    })

    it('shows the warning when 05:00 is exactly AT the window start (inclusive)', () => {
      installFixtureDom({ maintenanceWindow: '05:00–07:00' })
      checkMaintenanceWarning('')
      expect(warningIsVisible()).toBe(true)
    })
  })

  describe('with mainOption="--times" (user-supplied schedule)', () => {
    it('shows the warning when any user time falls inside the window', () => {
      installFixtureDom({ maintenanceWindow: '04:00–06:00' })
      document.getElementById('times-input').value = '05:00|17:00'
      checkMaintenanceWarning('--times')
      expect(warningIsVisible()).toBe(true)
    })

    it('hides the warning when all user times are outside the window', () => {
      installFixtureDom({ maintenanceWindow: '04:00–06:00' })
      document.getElementById('times-input').value = '10:00|17:00'
      checkMaintenanceWarning('--times')
      expect(warningIsVisible()).toBe(false)
    })

    it('hides the warning when the user\'s --times input is empty', () => {
      installFixtureDom({ maintenanceWindow: '04:00–06:00' })
      document.getElementById('times-input').value = ''
      // Warning starts hidden by installFixtureDom
      checkMaintenanceWarning('--times')
      expect(warningIsVisible()).toBe(false)
    })

    it('hides the warning when the user\'s --times input is invalid', () => {
      installFixtureDom({ maintenanceWindow: '04:00–06:00' })
      document.getElementById('times-input').value = 'garbage|nope'
      checkMaintenanceWarning('--times')
      expect(warningIsVisible()).toBe(false)
    })

    it('trims whitespace around individual times before checking', () => {
      installFixtureDom({ maintenanceWindow: '04:00–06:00' })
      document.getElementById('times-input').value = ' 05:00 | 17:00 '
      checkMaintenanceWarning('--times')
      expect(warningIsVisible()).toBe(true)
    })
  })

  describe('with unrecognized mainOption values', () => {
    it('always hides the warning (no --times, no default)', () => {
      installFixtureDom({ maintenanceWindow: '04:00–06:00' })
      // Pre-set warning visible so we can prove it's hidden
      document.getElementById('times-warning').classList.remove('d-none')
      checkMaintenanceWarning('--run')
      expect(warningIsVisible()).toBe(false)
    })

    it('hides for --collections mode', () => {
      installFixtureDom({ maintenanceWindow: '04:00–06:00' })
      document.getElementById('times-warning').classList.remove('d-none')
      checkMaintenanceWarning('--collections')
      expect(warningIsVisible()).toBe(false)
    })
  })

  it('always starts by hiding the warning (idempotent on repeated calls)', () => {
    installFixtureDom({ maintenanceWindow: '04:00–06:00' })
    // First call: overlap -> shows
    checkMaintenanceWarning('')
    expect(warningIsVisible()).toBe(true)
    // Change conditions so the second call should hide it
    document.getElementById('plex-maintenance-window').dataset.window = '01:00–02:00'
    checkMaintenanceWarning('')
    expect(warningIsVisible()).toBe(false)
  })
})
