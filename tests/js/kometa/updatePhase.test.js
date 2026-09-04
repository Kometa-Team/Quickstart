// Tests for static/local-js/modules/kometa/_updatePhase.js
//
// Five exported functions:
//
//   setKometaUpdatePhaseBadge       -- writes DOM + kometaState
//   inferKometaUpdatePhaseFromLine  -- PURE classifier, big rule set
//   updateKometaUpdatePhaseFromLine -- infer + write
//   setKometaStatusLog              -- replaces log panel content
//   appendKometaStatusLine          -- appends + infers phase
//
// COVERAGE STRATEGY:
//
//   inferKometaUpdatePhaseFromLine gets exhaustive coverage: one test
//   per phase (nine phases have detection rules; the tenth is null),
//   plus edge cases (empty string, null, whitespace).
//
//   setKometaUpdatePhaseBadge gets a test per DOM assertion:
//     - unknown phase coerces to 'idle'
//     - kometaState.kometaUpdatePhaseStatus is written
//     - old text-bg-* classes are removed before adding new one
//     - textContent is set to the phase's label
//     - no-op when badge is missing
//
//   updateKometaUpdatePhaseFromLine is a thin composition; 2 tests
//   suffice (matching line -> phase written; non-matching -> no-op).
//
//   setKometaStatusLog + appendKometaStatusLine get integration-shaped
//   tests: install a log box, call, assert textContent.

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import {
  setKometaUpdatePhaseBadge,
  inferKometaUpdatePhaseFromLine,
  updateKometaUpdatePhaseFromLine,
  setKometaStatusLog,
  appendKometaStatusLine
} from '../../../static/local-js/modules/kometa/_updatePhase.js'

// ---------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------

function installBadge (opts = {}) {
  const { existingClass = '', existingText = '' } = opts
  document.body.innerHTML = ''
  const badge = document.createElement('span')
  badge.id = 'kometa-update-phase-badge'
  if (existingClass) badge.classList.add(existingClass)
  badge.textContent = existingText
  document.body.appendChild(badge)
  return badge
}

function installProgressUi () {
  const progress = document.createElement('div')
  progress.id = 'kometa-update-progress'
  progress.className = 'alert alert-secondary d-none'
  progress.innerHTML = `
    <div id="kometa-update-progress-title"></div>
    <div id="kometa-update-progress-message"></div>
    <span id="kometa-update-progress-percent"></span>
    <div id="kometa-update-progress-bar" class="progress-bar bg-secondary"></div>
  `
  document.body.appendChild(progress)
  return {
    progress,
    title: document.getElementById('kometa-update-progress-title'),
    message: document.getElementById('kometa-update-progress-message'),
    percent: document.getElementById('kometa-update-progress-percent'),
    bar: document.getElementById('kometa-update-progress-bar')
  }
}

function installLogBox (initialText = '') {
  document.body.innerHTML = ''
  const box = document.createElement('pre')
  box.id = 'kometa-validation-log'
  box.textContent = initialText
  document.body.appendChild(box)
  return box
}

beforeEach(() => {
  // Reset the state field this module writes to
  kometaState.kometaUpdatePhaseStatus = 'idle'
})

afterEach(() => {
  document.body.innerHTML = ''
})

// ---------------------------------------------------------------------
// setKometaUpdatePhaseBadge
// ---------------------------------------------------------------------

describe('setKometaUpdatePhaseBadge', () => {
  it("is a no-op when the badge element is missing", () => {
    document.body.innerHTML = ''
    expect(() => setKometaUpdatePhaseBadge('checking')).not.toThrow()
    // State field should still get written even though there's no DOM
    // ...wait, actually the impl returns early when badge is missing.
    // Verify that's what happens.
    expect(kometaState.kometaUpdatePhaseStatus).toBe('idle')  // unchanged
  })

  it("writes label + info class for phase 'checking'", () => {
    const badge = installBadge()
    setKometaUpdatePhaseBadge('checking')
    expect(badge.textContent).toBe('Checking')
    expect(badge.classList.contains('text-bg-info')).toBe(true)
  })

  it("writes label + primary class for phase 'downloading'", () => {
    const badge = installBadge()
    setKometaUpdatePhaseBadge('downloading')
    expect(badge.textContent).toBe('Downloading')
    expect(badge.classList.contains('text-bg-primary')).toBe(true)
  })

  it("writes label + warning class for phase 'extracting'", () => {
    const badge = installBadge()
    setKometaUpdatePhaseBadge('extracting')
    expect(badge.textContent).toBe('Extracting')
    expect(badge.classList.contains('text-bg-warning')).toBe(true)
  })

  it("writes label + success class for phase 'ready'", () => {
    const badge = installBadge()
    setKometaUpdatePhaseBadge('ready')
    expect(badge.textContent).toBe('Ready')
    expect(badge.classList.contains('text-bg-success')).toBe(true)
  })

  it("writes label + danger class for phase 'failed'", () => {
    const badge = installBadge()
    setKometaUpdatePhaseBadge('failed')
    expect(badge.textContent).toBe('Failed')
    expect(badge.classList.contains('text-bg-danger')).toBe(true)
  })

  it("coerces unknown phase to 'idle'", () => {
    const badge = installBadge()
    setKometaUpdatePhaseBadge('bogus-phase-name')
    expect(badge.textContent).toBe('Idle')
    expect(badge.classList.contains('text-bg-secondary')).toBe(true)
    expect(kometaState.kometaUpdatePhaseStatus).toBe('idle')
  })

  it('removes previous text-bg-* class before adding the new one', () => {
    // Start with a warning class from a prior phase
    const badge = installBadge({ existingClass: 'text-bg-warning' })
    setKometaUpdatePhaseBadge('ready')
    expect(badge.classList.contains('text-bg-warning')).toBe(false)
    expect(badge.classList.contains('text-bg-success')).toBe(true)
  })

  it('writes the normalized phase to kometaState.kometaUpdatePhaseStatus', () => {
    installBadge()
    setKometaUpdatePhaseBadge('validating')
    expect(kometaState.kometaUpdatePhaseStatus).toBe('validating')
  })

  it("preserves classes that aren't in the managed set (e.g. layout classes)", () => {
    const badge = installBadge()
    badge.classList.add('ms-2', 'rounded-pill')  // typical Bootstrap layout classes
    setKometaUpdatePhaseBadge('ready')
    expect(badge.classList.contains('ms-2')).toBe(true)
    expect(badge.classList.contains('rounded-pill')).toBe(true)
  })

  it("shows inline progress for phase 'queued'", () => {
    installBadge()
    const ui = installProgressUi()
    setKometaUpdatePhaseBadge('queued')
    expect(ui.progress.classList.contains('d-none')).toBe(false)
    expect(ui.progress.classList.contains('alert-info')).toBe(true)
    expect(ui.title.textContent).toBe('Kometa update progress')
    expect(ui.message.textContent).toBe('Starting Kometa update job.')
    expect(ui.percent.textContent).toBe('5%')
    expect(ui.bar.style.width).toBe('5%')
    expect(ui.bar.getAttribute('aria-valuenow')).toBe('5')
    expect(ui.bar.classList.contains('progress-bar-striped')).toBe(true)
    expect(ui.bar.classList.contains('progress-bar-animated')).toBe(true)
  })

  it("hides inline progress for phase 'idle'", () => {
    installBadge()
    const ui = installProgressUi()
    setKometaUpdatePhaseBadge('queued')
    setKometaUpdatePhaseBadge('idle')
    expect(ui.progress.classList.contains('d-none')).toBe(true)
    expect(ui.message.textContent).toBe('No Kometa update is running.')
    expect(ui.percent.textContent).toBe('0%')
    expect(ui.bar.style.width).toBe('0%')
  })

  it("shows terminal success progress without animation", () => {
    installBadge()
    const ui = installProgressUi()
    setKometaUpdatePhaseBadge('ready')
    expect(ui.progress.classList.contains('d-none')).toBe(false)
    expect(ui.progress.classList.contains('alert-success')).toBe(true)
    expect(ui.message.textContent).toBe('Kometa update is complete.')
    expect(ui.percent.textContent).toBe('100%')
    expect(ui.bar.classList.contains('bg-success')).toBe(true)
    expect(ui.bar.classList.contains('progress-bar-animated')).toBe(false)
  })

  it('uses an explicit inline progress message when provided', () => {
    installBadge()
    const ui = installProgressUi()
    setKometaUpdatePhaseBadge('downloading', 'Downloading build archive...')
    expect(ui.message.textContent).toBe('Downloading build archive...')
  })
})

// ---------------------------------------------------------------------
// inferKometaUpdatePhaseFromLine  (pure classifier)
// ---------------------------------------------------------------------

describe('inferKometaUpdatePhaseFromLine -- edge cases', () => {
  it('returns null for empty string', () => {
    expect(inferKometaUpdatePhaseFromLine('')).toBeNull()
  })

  it('returns null for whitespace-only string', () => {
    expect(inferKometaUpdatePhaseFromLine('   \n\t  ')).toBeNull()
  })

  it('returns null for null input', () => {
    expect(inferKometaUpdatePhaseFromLine(null)).toBeNull()
  })

  it('returns null for a line matching no rules', () => {
    expect(inferKometaUpdatePhaseFromLine('some totally neutral log line')).toBeNull()
  })

  it('is case-insensitive', () => {
    expect(inferKometaUpdatePhaseFromLine('DOWNLOADING KOMETA.ZIP')).toBe('downloading')
  })
})

describe('inferKometaUpdatePhaseFromLine -- terminal phases', () => {
  it("detects 'failed' from the red-X emoji prefix", () => {
    expect(inferKometaUpdatePhaseFromLine('\u274c Something went wrong')).toBe('failed')
  })

  it("detects 'failed' from ' update failed'", () => {
    expect(inferKometaUpdatePhaseFromLine('The Kometa update failed at step 3')).toBe('failed')
  })

  it("detects 'failed' from 'aborting extraction'", () => {
    expect(inferKometaUpdatePhaseFromLine('Aborting extraction due to conflict')).toBe('failed')
  })

  it("detects 'ready' from 'kometa update completed successfully'", () => {
    expect(inferKometaUpdatePhaseFromLine('Kometa update completed successfully')).toBe('ready')
  })

  it("detects 'ready' from 'kometa is already up to date'", () => {
    expect(inferKometaUpdatePhaseFromLine('Kometa is already up to date')).toBe('ready')
  })

  it("detects 'ready' from 'kometa root validated successfully'", () => {
    expect(inferKometaUpdatePhaseFromLine('Kometa root validated successfully')).toBe('ready')
  })
})

describe('inferKometaUpdatePhaseFromLine -- in-progress phases', () => {
  it("detects 'validating' from 're-validating kometa after update'", () => {
    expect(inferKometaUpdatePhaseFromLine('Re-validating Kometa after update')).toBe('validating')
  })

  it("detects 'dependencies' from 'installing requirements'", () => {
    expect(inferKometaUpdatePhaseFromLine('Installing requirements from requirements.txt')).toBe('dependencies')
  })

  it("detects 'dependencies' from 'upgrading pip'", () => {
    expect(inferKometaUpdatePhaseFromLine('Upgrading pip to latest')).toBe('dependencies')
  })

  it("detects 'venv' from 'creating virtual environment'", () => {
    expect(inferKometaUpdatePhaseFromLine('Creating virtual environment at kometa-venv/')).toBe('venv')
  })

  it("detects 'preserving' from 'backed up kometa logs/cache'", () => {
    expect(inferKometaUpdatePhaseFromLine('Backed up Kometa logs/cache to /tmp/backup')).toBe('preserving')
  })

  it("detects 'extracting' from 'removed X existing entries'", () => {
    expect(inferKometaUpdatePhaseFromLine('Removed 47 existing entries in kometa/')).toBe('extracting')
  })

  it("detects 'extracting' from 'extracted to:'", () => {
    expect(inferKometaUpdatePhaseFromLine('Extracted to: /path/to/kometa')).toBe('extracting')
  })

  it("detects 'downloading' from 'downloading foo.zip'", () => {
    expect(inferKometaUpdatePhaseFromLine('Downloading kometa-master.zip')).toBe('downloading')
  })

  it("detects 'checking' from 'refreshing kometa status'", () => {
    expect(inferKometaUpdatePhaseFromLine('Refreshing Kometa status...')).toBe('checking')
  })

  it("detects 'checking' from 'checking kometa'", () => {
    expect(inferKometaUpdatePhaseFromLine('Checking Kometa update...')).toBe('checking')
  })
})

describe('inferKometaUpdatePhaseFromLine -- rule precedence', () => {
  // Terminal states should win over in-progress states, so a line
  // like 'update failed during extraction' returns 'failed' not
  // 'extracting'.
  it("returns 'failed' when a line matches both failed and extracting", () => {
    expect(inferKometaUpdatePhaseFromLine('Kometa update failed during aborting extraction')).toBe('failed')
  })

  it("returns 'ready' when a line matches both ready and validating patterns", () => {
    expect(inferKometaUpdatePhaseFromLine('Kometa update completed successfully after re-validating kometa after update')).toBe('ready')
  })
})

// ---------------------------------------------------------------------
// updateKometaUpdatePhaseFromLine
// ---------------------------------------------------------------------

describe('updateKometaUpdatePhaseFromLine', () => {
  it('writes the inferred phase to the badge when the line matches', () => {
    const badge = installBadge()
    updateKometaUpdatePhaseFromLine('Downloading kometa-master.zip')
    expect(badge.textContent).toBe('Downloading')
  })

  it('is a no-op when the line does not match any rule', () => {
    installBadge({ existingText: 'Idle', existingClass: 'text-bg-secondary' })
    updateKometaUpdatePhaseFromLine('some neutral prose without keywords')
    const badge = document.getElementById('kometa-update-phase-badge')
    // Text and class should be unchanged (no coerce-to-idle side effect)
    expect(badge.textContent).toBe('Idle')
  })
})

// ---------------------------------------------------------------------
// setKometaStatusLog
// ---------------------------------------------------------------------

describe('setKometaStatusLog', () => {
  it('is a no-op when the log box is missing', () => {
    document.body.innerHTML = ''
    expect(() => setKometaStatusLog(['hi'])).not.toThrow()
  })

  it('accepts a single string and appends a trailing newline', () => {
    const box = installLogBox()
    setKometaStatusLog('one line')
    expect(box.textContent).toBe('one line\n')
  })

  it('accepts an array and joins with newlines + trailing newline', () => {
    const box = installLogBox()
    setKometaStatusLog(['line one', 'line two', 'line three'])
    expect(box.textContent).toBe('line one\nline two\nline three\n')
  })

  it('empty input results in empty string (no trailing newline)', () => {
    const box = installLogBox('previous content')
    setKometaStatusLog('')
    expect(box.textContent).toBe('')
  })

  it('replaces any prior content', () => {
    const box = installLogBox('stale line\n')
    setKometaStatusLog('fresh line')
    expect(box.textContent).toBe('fresh line\n')
  })

  it('scrolls to the bottom after replacing the log', () => {
    const box = installLogBox()
    Object.defineProperty(box, 'scrollHeight', { configurable: true, value: 500 })
    setKometaStatusLog('fresh line')
    expect(box.scrollTop).toBe(500)
  })

  it('updates the phase badge when a phase is passed', () => {
    installLogBox()
    installBadge()  // add badge alongside log box
    // Need to re-append log box since installBadge cleared innerHTML.
    // Simpler: install both together.
    document.body.innerHTML = '<pre id="kometa-validation-log"></pre><span id="kometa-update-phase-badge"></span>'
    setKometaStatusLog(['starting update...'], 'checking')
    expect(document.getElementById('kometa-update-phase-badge').textContent).toBe('Checking')
    expect(document.getElementById('kometa-validation-log').textContent).toBe('starting update...\n')
  })

  it('does not touch the phase badge when phase is null', () => {
    document.body.innerHTML = '<pre id="kometa-validation-log"></pre><span id="kometa-update-phase-badge" class="text-bg-secondary">Idle</span>'
    setKometaStatusLog(['some line'])
    // Badge unchanged
    expect(document.getElementById('kometa-update-phase-badge').textContent).toBe('Idle')
  })
})

// ---------------------------------------------------------------------
// appendKometaStatusLine
// ---------------------------------------------------------------------

describe('appendKometaStatusLine', () => {
  it('is a no-op when the log box is missing', () => {
    document.body.innerHTML = ''
    expect(() => appendKometaStatusLine('hi')).not.toThrow()
  })

  it('appends a line with a trailing newline', () => {
    const box = installLogBox('first line\n')
    appendKometaStatusLine('second line')
    expect(box.textContent).toBe('first line\nsecond line\n')
  })

  it('preserves an initially-empty box (appends single line + newline)', () => {
    const box = installLogBox('')
    appendKometaStatusLine('lonely line')
    expect(box.textContent).toBe('lonely line\n')
  })

  it('auto-updates the phase badge when the line matches a rule', () => {
    document.body.innerHTML = '<pre id="kometa-validation-log"></pre><span id="kometa-update-phase-badge"></span>'
    appendKometaStatusLine('Downloading kometa-master.zip')
    expect(document.getElementById('kometa-update-phase-badge').textContent).toBe('Downloading')
  })

  it('leaves the badge alone when the line matches no rule', () => {
    document.body.innerHTML = '<pre id="kometa-validation-log"></pre><span id="kometa-update-phase-badge" class="text-bg-warning">Extracting</span>'
    appendKometaStatusLine('some neutral line without keywords')
    expect(document.getElementById('kometa-update-phase-badge').textContent).toBe('Extracting')
  })

  it('supports HTML in the line via insertAdjacentHTML', () => {
    const box = installLogBox('')
    appendKometaStatusLine('<a href="/x">click me</a>')
    // Should render as an actual anchor
    expect(box.querySelector('a')?.getAttribute('href')).toBe('/x')
  })
})
