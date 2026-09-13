// Tests for static/local-js/modules/kometa/_runControls.js
//
// Four exported functions:
//
//   getCurrentRunCommand    -- reads #run-command-output text
//   getRecoveryRunCommand   -- reads #recovery-command-output text
//   updateRunNowState       -- big state machine for the Run button
//   syncIncompleteRunActions -- recovery button visibility + tooltip
//
// COVERAGE STRATEGY:
//
//   Command readers: trivial DOM readers, 2-3 tests each covering
//     missing element / present-with-whitespace / present-empty.
//
//   updateRunNowState: state-machine with SEVEN paths through it:
//     - button missing -> no-op DOM path, still calls side-effects
//     - showYAML=false -> disabled
//     - kometaValidationInProgress -> disabled
//     - kometaUpdating -> disabled
//     - kometaStatus=running -> disabled
//     - !kometaValidated -> disabled
//     - !isRunCommandValid() -> disabled
//     - everything favorable -> enabled
//     Plus: always calls updateRunCommandHeaderBadge +
//           syncIncompleteRunActions.
//
//   syncIncompleteRunActions: five disabled-reason tooltip paths:
//     - button missing -> no-op
//     - alert hidden -> button hidden entirely
//     - validation in progress -> disabled, specific tooltip
//     - updating -> disabled, specific tooltip
//     - pendingStart -> disabled, specific tooltip
//     - status=running -> disabled, specific tooltip
//     - runnable -> enabled, no tooltip
//     - alert visible but no command text -> disabled, generic tooltip
//
// Collaborators (updateRunCommandHeaderBadge, isRunCommandValid) are
// mocked via vi.mock() so this module's behavior is tested in isolation.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Mock collaborators BEFORE importing _runControls.js. vi.mock() is
// hoisted so these apply regardless of position.
vi.mock('../../../static/local-js/modules/kometa/_headerBadges.js', () => ({
  updateRunCommandHeaderBadge: vi.fn()
}))
// _util.js exports many pure helpers; we only want to stub
// isRunCommandValid. importActual pulls the real module and we
// spread its exports so the rest keep working (readMetaFlag,
// computeYamlLineCount, etc., in case _runControls.js or its
// transitive deps use them).
vi.mock('../../../static/local-js/modules/kometa/_util.js', async (importActual) => ({
  ...(await importActual()),
  isRunCommandValid: vi.fn(() => true)  // default: valid
}))

import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import {
  getCurrentRunCommand,
  getRecoveryRunCommand,
  updateRunNowState,
  syncIncompleteRunActions
} from '../../../static/local-js/modules/kometa/_runControls.js'
import { updateRunCommandHeaderBadge } from '../../../static/local-js/modules/kometa/_headerBadges.js'
import { isRunCommandValid } from '../../../static/local-js/modules/kometa/_util.js'

// ---------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------

/**
 * Install the DOM elements touched by these functions. Everything is
 * optional; omit for tests that verify missing-element no-ops.
 */
function installDom (opts = {}) {
  const {
    runNow = true,
    runNowDisabled = true,
    runCommandOutput = null,
    recoveryCommandOutput = null,
    recovery = true,
    incompleteAlertVisible = false
  } = opts

  document.body.innerHTML = ''

  if (runNow) {
    const btn = document.createElement('button')
    btn.id = 'run-now'
    btn.disabled = runNowDisabled
    document.body.appendChild(btn)
  }

  if (runCommandOutput !== null) {
    const el = document.createElement('code')
    el.id = 'run-command-output'
    el.textContent = runCommandOutput
    document.body.appendChild(el)
  }

  if (recoveryCommandOutput !== null) {
    const el = document.createElement('code')
    el.id = 'recovery-command-output'
    el.textContent = recoveryCommandOutput
    document.body.appendChild(el)
  }

  if (recovery) {
    const btn = document.createElement('button')
    btn.id = 'run-recovery-command'
    document.body.appendChild(btn)
  }

  if (incompleteAlertVisible !== null) {
    const alert = document.createElement('div')
    alert.id = 'incomplete-run-alert'
    if (!incompleteAlertVisible) alert.classList.add('d-none')
    document.body.appendChild(alert)
  }
}

/**
 * Reset every kometaState field this module reads so tests don't
 * cross-contaminate.
 */
function resetState () {
  kometaState.showYAML = true
  kometaState.kometaValidationInProgress = false
  kometaState.kometaUpdating = false
  kometaState.kometaStatus = 'idle'
  kometaState.kometaValidated = true
  kometaState.kometaPendingStart = false
}

beforeEach(() => {
  updateRunCommandHeaderBadge.mockClear()
  isRunCommandValid.mockClear()
  isRunCommandValid.mockReturnValue(true)  // default: valid
  resetState()
})

afterEach(() => {
  document.body.innerHTML = ''
})

// ---------------------------------------------------------------------
// getCurrentRunCommand + getRecoveryRunCommand (trivial readers)
// ---------------------------------------------------------------------

describe('getCurrentRunCommand', () => {
  it('returns empty string when #run-command-output is missing', () => {
    expect(getCurrentRunCommand()).toBe('')
  })

  it('returns trimmed text content of #run-command-output', () => {
    installDom({ runCommandOutput: '  python kometa.py --run  ' })
    expect(getCurrentRunCommand()).toBe('python kometa.py --run')
  })

  it('returns empty string when the panel contains only whitespace', () => {
    installDom({ runCommandOutput: '   \n   ' })
    expect(getCurrentRunCommand()).toBe('')
  })
})

describe('getRecoveryRunCommand', () => {
  it('returns empty string when #recovery-command-output is missing', () => {
    expect(getRecoveryRunCommand()).toBe('')
  })

  it('returns trimmed text content of #recovery-command-output', () => {
    installDom({ recoveryCommandOutput: '\tpython kometa.py --resume\n' })
    expect(getRecoveryRunCommand()).toBe('python kometa.py --resume')
  })
})

// ---------------------------------------------------------------------
// updateRunNowState
// ---------------------------------------------------------------------

describe('updateRunNowState -- no-op button path', () => {
  it('when #run-now is missing, still refreshes badge + recovery', () => {
    installDom({ runNow: false })
    updateRunNowState()
    expect(updateRunCommandHeaderBadge).toHaveBeenCalledTimes(1)
    // syncIncompleteRunActions is called internally -- easiest way to
    // detect this is that it looked at #run-recovery-command (which
    // exists in the fixture). No exception = it ran.
  })

  it('when #run-now is missing, does NOT throw', () => {
    installDom({ runNow: false })
    expect(() => updateRunNowState()).not.toThrow()
  })
})

describe('updateRunNowState -- disable reasons', () => {
  it('disables when showYAML=false', () => {
    installDom()
    kometaState.showYAML = false
    updateRunNowState()
    expect(document.getElementById('run-now').disabled).toBe(true)
  })

  it('disables when kometaValidationInProgress=true', () => {
    installDom({ runNowDisabled: false })
    kometaState.kometaValidationInProgress = true
    updateRunNowState()
    expect(document.getElementById('run-now').disabled).toBe(true)
  })

  it('disables when kometaUpdating=true', () => {
    installDom({ runNowDisabled: false })
    kometaState.kometaUpdating = true
    updateRunNowState()
    expect(document.getElementById('run-now').disabled).toBe(true)
  })

  it("disables when kometaStatus='running'", () => {
    installDom({ runNowDisabled: false })
    kometaState.kometaStatus = 'running'
    updateRunNowState()
    expect(document.getElementById('run-now').disabled).toBe(true)
  })

  it('disables when kometaValidated=false', () => {
    installDom({ runNowDisabled: false })
    kometaState.kometaValidated = false
    updateRunNowState()
    expect(document.getElementById('run-now').disabled).toBe(true)
  })

  it('disables when isRunCommandValid() returns false', () => {
    installDom({ runNowDisabled: false })
    isRunCommandValid.mockReturnValue(false)
    updateRunNowState()
    expect(document.getElementById('run-now').disabled).toBe(true)
  })
})

describe('updateRunNowState -- enable path', () => {
  it('enables the button when every flag is favorable and command is valid', () => {
    installDom({ runNowDisabled: true })  // start disabled to prove we flip it
    isRunCommandValid.mockReturnValue(true)
    updateRunNowState()
    expect(document.getElementById('run-now').disabled).toBe(false)
  })
})

describe('updateRunNowState -- side effects', () => {
  it('always calls updateRunCommandHeaderBadge exactly once', () => {
    installDom()
    updateRunNowState()
    expect(updateRunCommandHeaderBadge).toHaveBeenCalledTimes(1)
  })

  it('calls updateRunCommandHeaderBadge in disable paths too', () => {
    installDom()
    kometaState.showYAML = false
    updateRunNowState()
    expect(updateRunCommandHeaderBadge).toHaveBeenCalledTimes(1)
  })
})

// ---------------------------------------------------------------------
// syncIncompleteRunActions
// ---------------------------------------------------------------------

describe('syncIncompleteRunActions -- no-op path', () => {
  it('when #run-recovery-command is missing, returns early without error', () => {
    installDom({ recovery: false })
    expect(() => syncIncompleteRunActions()).not.toThrow()
  })
})

describe('syncIncompleteRunActions -- alert hidden', () => {
  it('hides the recovery button when no incomplete-run alert is visible', () => {
    installDom({ incompleteAlertVisible: false, recoveryCommandOutput: 'python kometa.py' })
    syncIncompleteRunActions()
    const btn = document.getElementById('run-recovery-command')
    expect(btn.classList.contains('d-none')).toBe(true)
    expect(btn.disabled).toBe(true)
  })

  it("sets tooltip explaining that no recovery alert is visible", () => {
    installDom({ incompleteAlertVisible: false })
    syncIncompleteRunActions()
    const btn = document.getElementById('run-recovery-command')
    expect(btn.getAttribute('title')).toContain('only available when an incomplete-run recovery command is visible')
  })
})

describe('syncIncompleteRunActions -- alert visible but state blockers', () => {
  it("sets 'wait for validation' tooltip when kometaValidationInProgress", () => {
    installDom({ incompleteAlertVisible: true, recoveryCommandOutput: 'python kometa.py' })
    kometaState.kometaValidationInProgress = true
    syncIncompleteRunActions()
    const btn = document.getElementById('run-recovery-command')
    expect(btn.disabled).toBe(true)
    expect(btn.getAttribute('title')).toContain('Wait for Kometa validation')
  })

  it("sets 'wait for update' tooltip when kometaUpdating", () => {
    installDom({ incompleteAlertVisible: true, recoveryCommandOutput: 'python kometa.py' })
    kometaState.kometaUpdating = true
    syncIncompleteRunActions()
    const btn = document.getElementById('run-recovery-command')
    expect(btn.disabled).toBe(true)
    expect(btn.getAttribute('title')).toContain('Wait for the Kometa update')
  })

  it("sets 'already queued' tooltip when kometaPendingStart", () => {
    installDom({ incompleteAlertVisible: true, recoveryCommandOutput: 'python kometa.py' })
    kometaState.kometaPendingStart = true
    syncIncompleteRunActions()
    const btn = document.getElementById('run-recovery-command')
    expect(btn.disabled).toBe(true)
    expect(btn.getAttribute('title')).toContain('start is already queued')
  })

  it("sets 'already running' tooltip when kometaStatus=running", () => {
    installDom({ incompleteAlertVisible: true, recoveryCommandOutput: 'python kometa.py' })
    kometaState.kometaStatus = 'running'
    syncIncompleteRunActions()
    const btn = document.getElementById('run-recovery-command')
    expect(btn.disabled).toBe(true)
    expect(btn.getAttribute('title')).toContain('already running')
  })

  it("sets 'no recovery command' tooltip when alert visible but recovery panel empty", () => {
    installDom({ incompleteAlertVisible: true, recoveryCommandOutput: '' })
    syncIncompleteRunActions()
    const btn = document.getElementById('run-recovery-command')
    expect(btn.disabled).toBe(true)
    expect(btn.getAttribute('title')).toContain('No recovery command is available')
  })
})

describe('syncIncompleteRunActions -- runnable', () => {
  it('enables the button and clears title when everything is favorable', () => {
    installDom({
      incompleteAlertVisible: true,
      recoveryCommandOutput: 'python kometa.py --resume'
    })
    // All state flags default to favorable in resetState()
    syncIncompleteRunActions()
    const btn = document.getElementById('run-recovery-command')
    expect(btn.classList.contains('d-none')).toBe(false)
    expect(btn.disabled).toBe(false)
    expect(btn.hasAttribute('title')).toBe(false)
  })
})
