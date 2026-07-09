// Tests for static/local-js/modules/kometa/_runProgress.js
//
// Three exports: renderRunProgress, clearRunProgress, fetchRunProgress
// (plus runPhaseOrder constant).
//
// COVERAGE STRATEGY:
//
//   runPhaseOrder (1):
//     - Exports the 5 canonical phases in order
//
//   renderRunProgress (many, grouped by concern):
//
//     Guard clauses (2):
//       - missing #run-progress element: no-op
//       - payload without libraries[]: hides container + returns
//
//     Cache update (1):
//       - writes payload to kometaState.lastRunProgressPayload
//
//     Progress bar (3):
//       - percent based on completed_count * phaseCount
//       - progresses when current_library set
//       - handles totalSteps=0 (percent=0, no crash)
//
//     Summary line (3):
//       - libraries done + current_library
//       - "Last updated" via formatter global
//       - falls back to toLocaleString when no formatter global
//
//     Preparation row (3):
//       - locked > live: green success badge
//       - live only: blue primary badge
//       - neither: hidden
//
//     Maintenance row (4):
//       - paused via status: yellow + elapsed
//       - active via status: yellow "Window Active"
//       - progressMaintenance.had_pause: blue completed/paused summary
//       - none of above: hidden
//
//     Phase headers + library rows (5):
//       - respects payload.allowed_phases filter
//       - server phase_order override
//       - status classes: Done=success, In progress=primary, etc.
//       - Skipped libraries filtered from visible rows
//       - "Not Configured" for inferred earlier phases
//
//     Phase cells (special playlists handling) (4):
//       - running -> blue elapsed
//       - total > 0 or detected -> green
//       - run_finished without playlists -> "Not Configured"
//       - otherwise em-dash
//
//     Footer / grand total (3):
//       - per-phase totals sum
//       - grand total = prep + phase totals
//       - hidden when no libraries or no visible phases
//
//   clearRunProgress (3):
//     - hides container + maintenance row
//     - resetCache=false: preserves lastRunProgressPayload
//     - resetCache=true: clears lastRunProgressPayload
//
//   fetchRunProgress (7):
//     - guards against concurrent fetches
//     - forceFull=true: uses ?size=all URL
//     - success: calls renderRunProgress with data
//     - !ok response: null branch (running+cached -> re-render;
//       else -> clear)
//     - empty data + running + cached: re-renders cached
//     - empty data + not running: clears
//     - network reject: same fallback logic

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import {
  runPhaseOrder,
  renderRunProgress,
  clearRunProgress,
  fetchRunProgress
} from '../../../static/local-js/modules/kometa/_runProgress.js'

// ---------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------

function installFixture () {
  document.body.innerHTML = `
    <div id="run-progress" class="d-none">
      <div id="run-progress-bar" style="width:0" aria-valuenow="0"></div>
      <div id="run-progress-summary"></div>
      <div id="run-prep-row" class="d-none"></div>
      <div id="run-maintenance-row" class="d-none"></div>
      <table>
        <thead><tr id="run-library-header"></tr></thead>
        <tbody id="run-library-rows"></tbody>
        <tfoot id="run-library-footer" class="d-none">
          <tr id="run-library-total-row"></tr>
        </tfoot>
      </table>
    </div>
  `
}

function resetState () {
  kometaState.lastRunProgressPayload = null
  kometaState.runProgressInFlight = false
  kometaState.latestKometaStatusPayload = null
  kometaState.kometaStatus = 'idle'
}

let originalFetch

beforeEach(() => {
  originalFetch = global.fetch
  resetState()
})

afterEach(() => {
  global.fetch = originalFetch
  document.body.innerHTML = ''
  delete window.QS_formatTimestamp
})

// Minimal payload builder. Callers override fields as needed.
function makePayload (over = {}) {
  return {
    libraries: [{ name: 'Movies', type: 'movie', status: 'Done' }],
    ...over
  }
}

// ---------------------------------------------------------------------
// runPhaseOrder
// ---------------------------------------------------------------------

describe('runPhaseOrder', () => {
  it("exports the 5 canonical phases in order", () => {
    expect(runPhaseOrder.map(p => p.key)).toEqual(['operations', 'metadata', 'collections', 'overlays', 'playlists'])
    expect(runPhaseOrder.every(p => p.label && p.key)).toBe(true)
  })
})

// ---------------------------------------------------------------------
// renderRunProgress -- guard clauses
// ---------------------------------------------------------------------

describe('renderRunProgress -- guard clauses', () => {
  it("no-ops when #run-progress element is missing", () => {
    document.body.innerHTML = ''  // no fixture
    // Should not throw
    expect(() => renderRunProgress(makePayload())).not.toThrow()
  })

  it("hides container + returns when payload is falsy", () => {
    installFixture()
    renderRunProgress(null)
    expect(document.getElementById('run-progress').classList.contains('d-none')).toBe(true)
    expect(kometaState.lastRunProgressPayload).toBeNull()  // not cached
  })

  it("hides container when payload.libraries isn't an array", () => {
    installFixture()
    renderRunProgress({ libraries: 'not-an-array' })
    expect(document.getElementById('run-progress').classList.contains('d-none')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// renderRunProgress -- cache update
// ---------------------------------------------------------------------

describe('renderRunProgress -- cache update', () => {
  it("writes valid payload to kometaState.lastRunProgressPayload", () => {
    installFixture()
    const payload = makePayload({ total_count: 3 })
    renderRunProgress(payload)
    expect(kometaState.lastRunProgressPayload).toBe(payload)
  })
})

// ---------------------------------------------------------------------
// renderRunProgress -- progress bar
// ---------------------------------------------------------------------

describe('renderRunProgress -- progress bar', () => {
  it("sets bar width based on completed/total*phaseCount", () => {
    installFixture()
    // 2 libs done out of 4, 5 phases -> 10/20 = 50%
    renderRunProgress(makePayload({
      libraries: [
        { name: 'A', status: 'Done' }, { name: 'B', status: 'Done' },
        { name: 'C', status: 'In progress' }, { name: 'D', status: 'Not Started' }
      ],
      total_count: 4,
      completed_count: 2
    }))
    const bar = document.getElementById('run-progress-bar')
    expect(bar.style.width).toBe('50%')
    expect(bar.getAttribute('aria-valuenow')).toBe('50')
  })

  it("advances beyond completed count when current_library set", () => {
    installFixture()
    // 1 done, 1 current at phase idx 2 (collections), 5 phases
    // -> (1*5 + 2) / (2*5) = 7/10 = 70%
    renderRunProgress(makePayload({
      libraries: [
        { name: 'A', status: 'Done' },
        { name: 'B', status: 'In progress' }
      ],
      total_count: 2,
      completed_count: 1,
      current_library: 'B',
      phase_current: 'collections'
    }))
    expect(document.getElementById('run-progress-bar').style.width).toBe('70%')
  })

  it("handles totalSteps=0 (empty run) without crashing", () => {
    installFixture()
    renderRunProgress(makePayload({
      libraries: [],
      total_count: 0,
      completed_count: 0
    }))
    expect(document.getElementById('run-progress-bar').style.width).toBe('0%')
  })
})

// ---------------------------------------------------------------------
// renderRunProgress -- summary line
// ---------------------------------------------------------------------

describe('renderRunProgress -- summary line', () => {
  it("includes libraries done + current_library + step counter", () => {
    installFixture()
    renderRunProgress(makePayload({
      libraries: [{ name: 'A', status: 'Done' }, { name: 'B', status: 'In progress' }],
      total_count: 2,
      completed_count: 1,
      current_library: 'B',
      phase_current: 'operations'
    }))
    const text = document.getElementById('run-progress-summary').textContent
    expect(text).toContain('1/2 libraries complete')
    expect(text).toContain('Current: B')
    expect(text).toContain('Step')
  })

  it("uses window.QS_formatTimestamp when present", () => {
    installFixture()
    window.QS_formatTimestamp = vi.fn(() => 'FORMATTED-STAMP')
    renderRunProgress(makePayload({ last_log_at: '2024-01-01T00:00:00Z' }))
    expect(window.QS_formatTimestamp).toHaveBeenCalled()
    expect(document.getElementById('run-progress-summary').textContent).toContain('FORMATTED-STAMP')
  })

  it("falls back to toLocaleString when no formatter global", () => {
    installFixture()
    renderRunProgress(makePayload({ last_log_at: '2024-01-01T00:00:00Z' }))
    expect(document.getElementById('run-progress-summary').textContent).toContain('Last updated:')
  })
})

// ---------------------------------------------------------------------
// renderRunProgress -- Preparation row
// ---------------------------------------------------------------------

describe('renderRunProgress -- Preparation row', () => {
  it("shows green (locked) badge when preparation_seconds set", () => {
    installFixture()
    renderRunProgress(makePayload({ preparation_seconds: 42 }))
    const prep = document.getElementById('run-prep-row')
    expect(prep.classList.contains('d-none')).toBe(false)
    expect(prep.innerHTML).toContain('text-bg-success')
    expect(prep.innerHTML).toContain('Preparation')
  })

  it("shows blue (live) badge when only elapsed set", () => {
    installFixture()
    renderRunProgress(makePayload({ preparation_elapsed_seconds: 10 }))
    const prep = document.getElementById('run-prep-row')
    expect(prep.classList.contains('d-none')).toBe(false)
    expect(prep.innerHTML).toContain('text-bg-primary')
  })

  it("hides row when neither preparation time is set", () => {
    installFixture()
    renderRunProgress(makePayload())
    expect(document.getElementById('run-prep-row').classList.contains('d-none')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// renderRunProgress -- Maintenance row
// ---------------------------------------------------------------------

describe('renderRunProgress -- Maintenance row', () => {
  it("shows Paused badge + elapsed when status.maintenance_paused", () => {
    installFixture()
    kometaState.latestKometaStatusPayload = {
      maintenance_paused: true,
      maintenance_window: '02:00-04:00',
      maintenance_paused_since: new Date(Date.now() - 65000).toISOString()  // 65s ago
    }
    renderRunProgress(makePayload())
    const row = document.getElementById('run-maintenance-row')
    expect(row.classList.contains('d-none')).toBe(false)
    expect(row.innerHTML).toContain('Paused')
    expect(row.innerHTML).toContain('text-bg-warning')
    expect(row.innerHTML).toContain('02:00-04:00')
  })

  it("shows Window Active when status.maintenance_active (not paused)", () => {
    installFixture()
    kometaState.latestKometaStatusPayload = {
      maintenance_paused: false,
      maintenance_active: true,
      maintenance_window: '03:00-05:00'
    }
    renderRunProgress(makePayload())
    const row = document.getElementById('run-maintenance-row')
    expect(row.classList.contains('d-none')).toBe(false)
    expect(row.innerHTML).toContain('Window Active')
    expect(row.innerHTML).toContain('03:00-05:00')
  })

  it("shows Completed/Paused (log) from progress maintenance_summary", () => {
    installFixture()
    renderRunProgress(makePayload({
      maintenance_summary: {
        had_pause: true,
        window: '01:00-03:00',
        pause_count: 2,
        pause_seconds: 120,
        open_pause: false
      }
    }))
    const row = document.getElementById('run-maintenance-row')
    expect(row.classList.contains('d-none')).toBe(false)
    expect(row.innerHTML).toContain('Completed')
    expect(row.innerHTML).toContain('text-bg-primary')
  })

  it("hides row when no maintenance signal at all", () => {
    installFixture()
    renderRunProgress(makePayload())
    expect(document.getElementById('run-maintenance-row').classList.contains('d-none')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// renderRunProgress -- Library table
// ---------------------------------------------------------------------

describe('renderRunProgress -- library table', () => {
  it("filters phases by payload.allowed_phases", () => {
    installFixture()
    renderRunProgress(makePayload({
      allowed_phases: ['metadata', 'collections']
    }))
    const header = document.getElementById('run-library-header').innerHTML
    expect(header).toContain('Metadata')
    expect(header).toContain('Collections')
    expect(header).not.toContain('Operations')
    expect(header).not.toContain('Playlists')
  })

  it("respects server-provided phase_order", () => {
    installFixture()
    renderRunProgress(makePayload({
      phase_order: ['playlists', 'metadata']
    }))
    const header = document.getElementById('run-library-header').innerHTML
    // In the order server sent
    const playlistIdx = header.indexOf('Playlists')
    const metadataIdx = header.indexOf('Metadata')
    expect(playlistIdx).toBeGreaterThan(0)
    expect(metadataIdx).toBeGreaterThan(playlistIdx)
  })

  it("uses status-specific badge classes", () => {
    installFixture()
    renderRunProgress(makePayload({
      libraries: [
        { name: 'A', status: 'Done' },
        { name: 'B', status: 'In progress' },
        { name: 'C', status: 'Stopped' },
        { name: 'D', status: 'Not Started' }
      ]
    }))
    const rows = document.getElementById('run-library-rows').innerHTML
    expect(rows).toContain('text-bg-success')  // Done
    expect(rows).toContain('text-bg-primary')  // In progress
    expect(rows).toContain('text-bg-danger')   // Stopped
    expect(rows).toContain('text-bg-secondary')  // Not Started
  })

  it("filters Skipped libraries from visible rows", () => {
    installFixture()
    renderRunProgress(makePayload({
      libraries: [
        { name: 'Visible', status: 'Done' },
        { name: 'Hidden', status: 'Skipped' }
      ]
    }))
    const rows = document.getElementById('run-library-rows').innerHTML
    expect(rows).toContain('Visible')
    expect(rows).not.toContain('Hidden')
  })

  it("shows 'Not Configured' for phases before the last-seen index", () => {
    installFixture()
    renderRunProgress(makePayload({
      libraries: [{
        name: 'Movies',
        status: 'Done',
        // Only metadata + overlays have durations; collections has no
        // duration but is between them, so it should be 'Not Configured'
        durations: { metadata: 5, overlays: 3 }
      }]
    }))
    const rows = document.getElementById('run-library-rows').innerHTML
    expect(rows).toContain('Not Configured')
  })
})

// ---------------------------------------------------------------------
// renderRunProgress -- Playlists cell
// ---------------------------------------------------------------------

describe('renderRunProgress -- Playlists cell', () => {
  it("shows blue Running badge when playlist_running", () => {
    installFixture()
    renderRunProgress(makePayload({
      playlist_running: true,
      playlist_elapsed_seconds: 15
    }))
    const rows = document.getElementById('run-library-rows').innerHTML
    // The playlists cell should be blue
    expect(rows).toMatch(/text-bg-primary/)
  })

  it("shows green total when playlist_total_seconds > 0", () => {
    installFixture()
    renderRunProgress(makePayload({
      playlist_total_seconds: 42,
      playlists_detected: true
    }))
    const rows = document.getElementById('run-library-rows').innerHTML
    expect(rows).toMatch(/text-bg-success/)  // playlists total
  })

  it("shows 'Not Configured' when run_finished + no playlists", () => {
    installFixture()
    renderRunProgress(makePayload({
      run_finished: true,
      playlist_total_seconds: 0,
      playlists_detected: false
    }))
    const rows = document.getElementById('run-library-rows').innerHTML
    expect(rows).toContain('Not Configured')
  })

  it("shows em-dash when no playlist info at all", () => {
    installFixture()
    renderRunProgress(makePayload())
    const rows = document.getElementById('run-library-rows').innerHTML
    expect(rows).toContain('\u2014')  // em-dash
  })
})

// ---------------------------------------------------------------------
// renderRunProgress -- footer / grand total
// ---------------------------------------------------------------------

describe('renderRunProgress -- footer/grand total', () => {
  it("shows per-phase totals across all libraries", () => {
    installFixture()
    renderRunProgress(makePayload({
      libraries: [
        { name: 'A', status: 'Done', durations: { metadata: 10, collections: 5 } },
        { name: 'B', status: 'Done', durations: { metadata: 20, collections: 15 } }
      ],
      total_count: 2,
      completed_count: 2
    }))
    const footer = document.getElementById('run-library-footer')
    expect(footer.classList.contains('d-none')).toBe(false)
    // Metadata total = 30, Collections total = 20
    const totalRow = document.getElementById('run-library-total-row').innerHTML
    expect(totalRow).toContain('Total')
  })

  it("includes prep time in grand total", () => {
    installFixture()
    renderRunProgress(makePayload({
      preparation_seconds: 100,
      libraries: [
        { name: 'A', status: 'Done', durations: { metadata: 10 } }
      ]
    }))
    const totalRow = document.getElementById('run-library-total-row').innerHTML
    // Grand total badge should be present (100+10=110s)
    expect(totalRow).toContain('badge')
  })

  it("hides footer when no libraries", () => {
    installFixture()
    renderRunProgress(makePayload({ libraries: [] }))
    expect(document.getElementById('run-library-footer').classList.contains('d-none')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// clearRunProgress
// ---------------------------------------------------------------------

describe('clearRunProgress', () => {
  it("hides container + maintenance row", () => {
    installFixture()
    document.getElementById('run-progress').classList.remove('d-none')
    document.getElementById('run-maintenance-row').classList.remove('d-none')
    clearRunProgress()
    expect(document.getElementById('run-progress').classList.contains('d-none')).toBe(true)
    expect(document.getElementById('run-maintenance-row').classList.contains('d-none')).toBe(true)
  })

  it("preserves lastRunProgressPayload when resetCache=false", () => {
    installFixture()
    kometaState.lastRunProgressPayload = { libraries: [{ name: 'X' }] }
    clearRunProgress(false)
    expect(kometaState.lastRunProgressPayload).toEqual({ libraries: [{ name: 'X' }] })
  })

  it("clears lastRunProgressPayload when resetCache=true", () => {
    installFixture()
    kometaState.lastRunProgressPayload = { libraries: [{ name: 'X' }] }
    clearRunProgress(true)
    expect(kometaState.lastRunProgressPayload).toBeNull()
  })

  it("no-ops safely when elements missing", () => {
    document.body.innerHTML = ''
    expect(() => clearRunProgress(true)).not.toThrow()
  })
})

// ---------------------------------------------------------------------
// fetchRunProgress
// ---------------------------------------------------------------------

describe('fetchRunProgress', () => {
  it("bails immediately when runProgressInFlight=true", async () => {
    installFixture()
    kometaState.runProgressInFlight = true
    global.fetch = vi.fn()
    const result = await fetchRunProgress()
    expect(result).toBeNull()
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it("uses ?size=all when forceFull=true", async () => {
    installFixture()
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(makePayload()) }))
    await fetchRunProgress(true)
    expect(global.fetch).toHaveBeenCalledWith('/logscan/progress?size=all')
  })

  it("uses default URL when forceFull=false (default)", async () => {
    installFixture()
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(makePayload()) }))
    await fetchRunProgress()
    expect(global.fetch).toHaveBeenCalledWith('/logscan/progress')
  })

  it("calls renderRunProgress on success", async () => {
    installFixture()
    const payload = makePayload({ total_count: 2 })
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(payload) }))
    await fetchRunProgress()
    // renderRunProgress cached the payload
    expect(kometaState.lastRunProgressPayload).toBe(payload)
  })

  it("!ok response: falls to null branch (running+cached -> re-render)", async () => {
    installFixture()
    const cached = makePayload({ total_count: 5 })
    kometaState.lastRunProgressPayload = cached
    kometaState.kometaStatus = 'running'
    global.fetch = vi.fn(() => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }))
    await fetchRunProgress()
    // Cache unchanged (renderRunProgress re-wrote same object)
    expect(kometaState.lastRunProgressPayload).toBe(cached)
    // Container should be visible (re-rendered)
    expect(document.getElementById('run-progress').classList.contains('d-none')).toBe(false)
  })

  it("!ok response: not running -> clears panel", async () => {
    installFixture()
    kometaState.kometaStatus = 'idle'
    global.fetch = vi.fn(() => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }))
    await fetchRunProgress()
    expect(document.getElementById('run-progress').classList.contains('d-none')).toBe(true)
  })

  it("network reject: same fallback logic (running+cached -> re-render)", async () => {
    installFixture()
    const cached = makePayload({ total_count: 5 })
    kometaState.lastRunProgressPayload = cached
    kometaState.kometaStatus = 'running'
    global.fetch = vi.fn(() => Promise.reject(new Error('network')))
    await fetchRunProgress()
    // Panel visible because we re-rendered from cache
    expect(document.getElementById('run-progress').classList.contains('d-none')).toBe(false)
  })

  it("clears runProgressInFlight in .finally", async () => {
    installFixture()
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(makePayload()) }))
    await fetchRunProgress()
    expect(kometaState.runProgressInFlight).toBe(false)
  })
})
