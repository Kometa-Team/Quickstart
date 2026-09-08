// Tests for static/local-js/modules/kometa/_logscan.js
//
// Two public functions:
//   - renderLogscan(data, { updateHeaderBadge })
//   - fetchLogscanAnalysis(force, { updateHeaderBadge, kometaState })
//
// Plus resetLogscanStateForTests() for test hygiene.
//
// COVERAGE:
//
//   renderLogscan (13):
//     - no-op when panel missing
//     - shows "unavailable" for null/undefined data
//     - shows "unavailable" for data.error === true
//     - calls updateHeaderBadge with { error: true } on failure
//     - populates summary line with finished_at + runtime
//     - runtime "n/a" when run_time_seconds is 0
//     - runtime "n/a" when run_time_seconds is missing
//     - populates recommendations list (up to 8)
//     - "Showing N of M" overflow line when >8 recommendations
//     - "No recommendations yet." when list empty
//     - deduplicates first-line == title in recommendation messages
//     - populates section runtimes with header + delta
//     - populates missing-people section
//     - hides missing-people section when list empty
//     - calls updateHeaderBadge with full payload on success
//
//   fetchLogscanAnalysis (7):
//     - no-op when panel missing
//     - skips fetch when in-flight (guard against overlap)
//     - fetches on force=true
//     - fetches when kometaState.lastLogscanPayload is missing (first call)
//     - respects mod-5 counter after first success
//     - stashes payload into kometaState.lastLogscanPayload on success
//     - shows "unavailable" + calls updateHeaderBadge on fetch error

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  renderLogscan,
  fetchLogscanAnalysis,
  resetLogscanStateForTests
} from '../../../static/local-js/modules/kometa/_logscan.js'

// ---------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------

function installLogscanDom () {
  document.body.innerHTML = `
    <div id="logscan-panel">
      <div id="logscan-summary"></div>
      <div id="logscan-recommendations"></div>
      <div id="logscan-sections"></div>
      <div id="logscan-missing-people" class="d-none"></div>
    </div>
  `
}

function tearDown () {
  document.body.innerHTML = ''
  resetLogscanStateForTests()
  vi.restoreAllMocks()
}

const SAMPLE_PAYLOAD = {
  summary: {
    finished_at: '2024-06-15 12:00:00',
    run_time_seconds: 125,
    section_runtimes: { Movies: 60, Shows: 45 },
    section_runtime_total_seconds: 105,
    section_runtime_delta_seconds: 20
  },
  recommendations: [
    { first_line: 'Config warning', message: 'Config warning\nMore detail here.' }
  ],
  missing_people: ['Alice', 'Bob'],
  missing_people_message: 'Missing posters!'
}

// ---------------------------------------------------------------------
// renderLogscan
// ---------------------------------------------------------------------

describe('renderLogscan', () => {
  beforeEach(installLogscanDom)
  afterEach(tearDown)

  it('no-ops when panel missing', () => {
    document.body.innerHTML = ''
    expect(() => renderLogscan(SAMPLE_PAYLOAD)).not.toThrow()
  })

  it('shows "unavailable" for null data', () => {
    renderLogscan(null)
    expect(document.getElementById('logscan-recommendations').textContent).toContain('unavailable')
  })

  it('shows "unavailable" for undefined data', () => {
    renderLogscan(undefined)
    expect(document.getElementById('logscan-recommendations').textContent).toContain('unavailable')
  })

  it('shows "unavailable" when data.error is truthy', () => {
    renderLogscan({ error: true })
    expect(document.getElementById('logscan-recommendations').textContent).toContain('unavailable')
  })

  it('calls updateHeaderBadge with { error: true } on failure', () => {
    const badge = vi.fn()
    renderLogscan(null, { updateHeaderBadge: badge })
    expect(badge).toHaveBeenCalledWith({ error: true })
  })

  it('populates summary with finished_at + runtime', () => {
    renderLogscan(SAMPLE_PAYLOAD)
    const summary = document.getElementById('logscan-summary').textContent
    expect(summary).toContain('Last run: 2024-06-15 12:00:00')
    expect(summary).toContain('Runtime:')
  })

  it('shows runtime "n/a" when run_time_seconds is 0', () => {
    renderLogscan({ ...SAMPLE_PAYLOAD, summary: { run_time_seconds: 0 } })
    expect(document.getElementById('logscan-summary').textContent).toContain('n/a')
  })

  it('shows runtime "n/a" when run_time_seconds is missing', () => {
    renderLogscan({ ...SAMPLE_PAYLOAD, summary: {} })
    expect(document.getElementById('logscan-summary').textContent).toContain('n/a')
  })

  it('populates recommendations list', () => {
    renderLogscan(SAMPLE_PAYLOAD)
    const recs = document.getElementById('logscan-recommendations')
    expect(recs.textContent).toContain('Config warning')
    expect(recs.textContent).toContain('More detail here.')
  })

  it('shows overflow line when >8 recommendations', () => {
    const manyRecs = Array.from({ length: 12 }, (_, i) => ({
      first_line: `Rec ${i}`,
      message: `Message ${i}`
    }))
    renderLogscan({ ...SAMPLE_PAYLOAD, recommendations: manyRecs })
    expect(document.getElementById('logscan-recommendations').textContent).toContain('Showing 8 of 12')
  })

  it('shows "No recommendations yet." when list is empty', () => {
    renderLogscan({ ...SAMPLE_PAYLOAD, recommendations: [] })
    expect(document.getElementById('logscan-recommendations').textContent).toContain('No recommendations yet.')
  })

  it('deduplicates first-line equal to title', () => {
    // Title matches first line -> first line stripped from message body.
    renderLogscan({
      ...SAMPLE_PAYLOAD,
      recommendations: [{ first_line: 'Same', message: 'Same\nbody-only' }]
    })
    const recs = document.getElementById('logscan-recommendations')
    // "Same" appears once as title. "body-only" is what remains of message.
    expect(recs.textContent).toContain('body-only')
    // Count of "Same" occurrences should be 1 (title only)
    const matches = recs.textContent.match(/Same/g) || []
    expect(matches.length).toBe(1)
  })

  it('populates section runtimes with header + meta', () => {
    renderLogscan(SAMPLE_PAYLOAD)
    const sections = document.getElementById('logscan-sections').textContent
    expect(sections).toContain('Section runtimes')
    expect(sections).toContain('Movies')
    expect(sections).toContain('Shows')
  })

  it('shows "No section runtimes yet." when empty', () => {
    renderLogscan({ ...SAMPLE_PAYLOAD, summary: { section_runtimes: {} } })
    expect(document.getElementById('logscan-sections').textContent).toContain('No section runtimes yet.')
  })

  it('populates missing-people section', () => {
    renderLogscan(SAMPLE_PAYLOAD)
    const missing = document.getElementById('logscan-missing-people')
    expect(missing.classList.contains('d-none')).toBe(false)
    expect(missing.textContent).toContain('Alice')
    expect(missing.textContent).toContain('Bob')
    expect(missing.textContent).toContain('Missing posters!')
  })

  it('hides missing-people section when list empty', () => {
    renderLogscan({ ...SAMPLE_PAYLOAD, missing_people: [] })
    expect(document.getElementById('logscan-missing-people').classList.contains('d-none')).toBe(true)
  })

  it('calls updateHeaderBadge with full payload on success', () => {
    const badge = vi.fn()
    renderLogscan(SAMPLE_PAYLOAD, { updateHeaderBadge: badge })
    expect(badge).toHaveBeenCalledWith(SAMPLE_PAYLOAD)
  })
})

// ---------------------------------------------------------------------
// fetchLogscanAnalysis
// ---------------------------------------------------------------------

describe('fetchLogscanAnalysis', () => {
  beforeEach(() => {
    installLogscanDom()
    global.fetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve(SAMPLE_PAYLOAD)
    })
  })
  afterEach(() => {
    tearDown()
    delete global.fetch
  })

  it('no-ops when panel missing', () => {
    document.body.innerHTML = ''
    fetchLogscanAnalysis(true, { kometaState: {} })
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('fetches on force=true even when payload is cached', () => {
    const state = { lastLogscanPayload: {} }
    fetchLogscanAnalysis(true, { kometaState: state })
    expect(global.fetch).toHaveBeenCalledWith('/logscan/analyze')
  })

  it('fetches on first call when kometaState.lastLogscanPayload is missing', () => {
    fetchLogscanAnalysis(false, { kometaState: {} })
    expect(global.fetch).toHaveBeenCalledWith('/logscan/analyze')
  })

  it('respects mod-5 counter after first success', async () => {
    const state = { lastLogscanPayload: null }
    // First call: no cached payload -> fetches, counter goes to 1
    fetchLogscanAnalysis(false, { kometaState: state })
    // Wait for the promise chain to settle
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(global.fetch).toHaveBeenCalledTimes(1)
    // State is now cached; subsequent non-forced calls should only fetch
    // on the 5th (counter goes 2, 3, 4, 5 -> fifth fires)
    fetchLogscanAnalysis(false, { kometaState: state })  // 2
    fetchLogscanAnalysis(false, { kometaState: state })  // 3
    fetchLogscanAnalysis(false, { kometaState: state })  // 4
    expect(global.fetch).toHaveBeenCalledTimes(1)
    fetchLogscanAnalysis(false, { kometaState: state })  // 5 -> fires
    expect(global.fetch).toHaveBeenCalledTimes(2)
  })

  it('honors minIntervalMs for non-forced cadence fetches', async () => {
    const state = { lastLogscanPayload: null }
    vi.spyOn(Date, 'now')
      .mockReturnValueOnce(1000)
      .mockReturnValueOnce(2000)
      .mockReturnValueOnce(3000)
      .mockReturnValueOnce(4000)
      .mockReturnValueOnce(5000)
      .mockReturnValueOnce(61000)
      .mockReturnValueOnce(62000)
      .mockReturnValueOnce(63000)
      .mockReturnValueOnce(64000)
      .mockReturnValueOnce(65000)
    fetchLogscanAnalysis(false, { kometaState: state, minIntervalMs: 60000 })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(global.fetch).toHaveBeenCalledTimes(1)

    fetchLogscanAnalysis(false, { kometaState: state, minIntervalMs: 60000 }) // 2
    fetchLogscanAnalysis(false, { kometaState: state, minIntervalMs: 60000 }) // 3
    fetchLogscanAnalysis(false, { kometaState: state, minIntervalMs: 60000 }) // 4
    fetchLogscanAnalysis(false, { kometaState: state, minIntervalMs: 60000 }) // 5, below interval
    expect(global.fetch).toHaveBeenCalledTimes(1)

    fetchLogscanAnalysis(false, { kometaState: state, minIntervalMs: 60000 }) // 6
    fetchLogscanAnalysis(false, { kometaState: state, minIntervalMs: 60000 }) // 7
    fetchLogscanAnalysis(false, { kometaState: state, minIntervalMs: 60000 }) // 8
    fetchLogscanAnalysis(false, { kometaState: state, minIntervalMs: 60000 }) // 9
    fetchLogscanAnalysis(false, { kometaState: state, minIntervalMs: 60000 }) // 10, interval due
    expect(global.fetch).toHaveBeenCalledTimes(2)
  })

  it('stashes payload into kometaState.lastLogscanPayload on success', async () => {
    const state = {}
    fetchLogscanAnalysis(true, { kometaState: state })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(state.lastLogscanPayload).toEqual(SAMPLE_PAYLOAD)
  })

  it('shows unavailable + calls updateHeaderBadge on fetch error', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('network down'))
    const badge = vi.fn()
    // Silence expected console.error
    vi.spyOn(console, 'error').mockImplementation(() => {})
    fetchLogscanAnalysis(true, { kometaState: {}, updateHeaderBadge: badge })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(document.getElementById('logscan-recommendations').textContent).toContain('unavailable')
    expect(badge).toHaveBeenCalledWith({ error: true })
  })

  it('resets in-flight flag after settle so subsequent calls can fetch', async () => {
    fetchLogscanAnalysis(true, { kometaState: {} })
    await new Promise(resolve => setTimeout(resolve, 0))
    // Second forced call should also fetch (not blocked by in-flight)
    fetchLogscanAnalysis(true, { kometaState: { lastLogscanPayload: {} } })
    expect(global.fetch).toHaveBeenCalledTimes(2)
  })
})
