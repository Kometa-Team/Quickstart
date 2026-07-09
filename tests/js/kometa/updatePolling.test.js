// Tests for static/local-js/modules/kometa/_updatePolling.js
//
// Two exported functions:
//
//   stopKometaUpdatePolling     -- clears interval + nulls state
//   pollKometaUpdateProgress    -- fetches next batch of log lines,
//                                  updates phase badge, appends lines,
//                                  advances cursor, auto-stops on done
//
// COVERAGE STRATEGY:
//
//   stopKometaUpdatePolling: idempotent + reset semantics.
//   pollKometaUpdateProgress: 8 branches through the pipeline:
//     - no job id -> resolves null
//     - fetch rejects -> propagates
//     - !res.ok -> rejects
//     - !data.success -> rejects with server message
//     - phase='queued' -> phase badge updated
//     - phase='error' -> phase badge updated
//     - data.lines forEach appended
//     - data.next_index advances cursor
//     - data.done -> stops polling
//
// _updatePhase.js exports mocked via vi.mock so we can spy on badge
// / status line calls without needing real DOM.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../static/local-js/modules/kometa/_updatePhase.js', () => ({
  setKometaUpdatePhaseBadge: vi.fn(),
  appendKometaStatusLine: vi.fn()
}))

import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'
import {
  stopKometaUpdatePolling,
  pollKometaUpdateProgress
} from '../../../static/local-js/modules/kometa/_updatePolling.js'
import {
  setKometaUpdatePhaseBadge,
  appendKometaStatusLine
} from '../../../static/local-js/modules/kometa/_updatePhase.js'

// ---------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------

let originalFetch

function mockFetchOnce (response) {
  global.fetch = vi.fn(() => Promise.resolve(response))
}

function makeOkResponse (body) {
  return {
    ok: true,
    json: () => Promise.resolve(body)
  }
}

function makeErrorResponse (status, body) {
  return {
    ok: false,
    status,
    json: () => Promise.resolve(body)
  }
}

function resetState () {
  kometaState.kometaUpdateJobId = null
  kometaState.kometaUpdateLogIndex = 0
  kometaState.kometaUpdatePollInterval = null
}

beforeEach(() => {
  setKometaUpdatePhaseBadge.mockClear()
  appendKometaStatusLine.mockClear()
  originalFetch = global.fetch
  resetState()
})

afterEach(() => {
  global.fetch = originalFetch
})

// ---------------------------------------------------------------------
// stopKometaUpdatePolling
// ---------------------------------------------------------------------

describe('stopKometaUpdatePolling', () => {
  it('is a no-op when no interval is active', () => {
    expect(() => stopKometaUpdatePolling()).not.toThrow()
    expect(kometaState.kometaUpdatePollInterval).toBeNull()
  })

  it('clears the interval and nulls the state handle', () => {
    // Install a real interval so we can verify it gets cleared
    const clearIntervalSpy = vi.spyOn(global, 'clearInterval')
    kometaState.kometaUpdatePollInterval = setInterval(() => {}, 10_000)
    const handle = kometaState.kometaUpdatePollInterval
    stopKometaUpdatePolling()
    expect(clearIntervalSpy).toHaveBeenCalledWith(handle)
    expect(kometaState.kometaUpdatePollInterval).toBeNull()
    clearIntervalSpy.mockRestore()
  })

  it('is idempotent (safe to call twice)', () => {
    kometaState.kometaUpdatePollInterval = setInterval(() => {}, 10_000)
    stopKometaUpdatePolling()
    expect(() => stopKometaUpdatePolling()).not.toThrow()
    expect(kometaState.kometaUpdatePollInterval).toBeNull()
  })
})

// ---------------------------------------------------------------------
// pollKometaUpdateProgress
// ---------------------------------------------------------------------

describe('pollKometaUpdateProgress -- short circuits', () => {
  it('resolves null when no job id is set', async () => {
    const result = await pollKometaUpdateProgress()
    expect(result).toBeNull()
    // Fetch should not be called
    expect(global.fetch).toBe(originalFetch)  // still the untouched fetch
  })
})

describe('pollKometaUpdateProgress -- URL construction', () => {
  it('encodes the job id and since cursor into the URL', async () => {
    kometaState.kometaUpdateJobId = 'job/with?special&chars'
    kometaState.kometaUpdateLogIndex = 42
    mockFetchOnce(makeOkResponse({
      success: true,
      job: { phase: 'running' },
      lines: [],
      next_index: 42,
      done: false
    }))
    await pollKometaUpdateProgress()
    expect(global.fetch).toHaveBeenCalledTimes(1)
    const url = global.fetch.mock.calls[0][0]
    expect(url).toContain('/background-jobs/')
    expect(url).toContain(encodeURIComponent('job/with?special&chars'))
    expect(url).toContain('since=42')
  })
})

describe('pollKometaUpdateProgress -- error paths', () => {
  it('rejects with a helpful message when res.ok is false', async () => {
    kometaState.kometaUpdateJobId = 'abc'
    mockFetchOnce(makeErrorResponse(500, { success: false, error: 'internal server error' }))
    await expect(pollKometaUpdateProgress()).rejects.toThrow('internal server error')
  })

  it("rejects when the server returns success=false", async () => {
    kometaState.kometaUpdateJobId = 'abc'
    mockFetchOnce(makeOkResponse({ success: false, error: 'job vanished' }))
    await expect(pollKometaUpdateProgress()).rejects.toThrow('job vanished')
  })

  it("rejects when the server returns success=true but no job object", async () => {
    kometaState.kometaUpdateJobId = 'abc'
    mockFetchOnce(makeOkResponse({ success: true, lines: [], next_index: 0 }))
    await expect(pollKometaUpdateProgress()).rejects.toThrow('Failed to fetch Kometa update progress.')
  })

  it('uses a fallback error message when the server omits data.error', async () => {
    kometaState.kometaUpdateJobId = 'abc'
    mockFetchOnce(makeErrorResponse(503, { success: false }))
    await expect(pollKometaUpdateProgress()).rejects.toThrow('Failed to fetch Kometa update progress.')
  })

  it('propagates network errors', async () => {
    kometaState.kometaUpdateJobId = 'abc'
    global.fetch = vi.fn(() => Promise.reject(new Error('network down')))
    await expect(pollKometaUpdateProgress()).rejects.toThrow('network down')
  })
})

describe('pollKometaUpdateProgress -- phase badge updates', () => {
  it("updates badge to 'queued' when server reports phase=queued", async () => {
    kometaState.kometaUpdateJobId = 'abc'
    mockFetchOnce(makeOkResponse({
      success: true,
      job: { phase: 'queued' },
      lines: [],
      next_index: 0,
      done: false
    }))
    await pollKometaUpdateProgress()
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('queued')
  })

  it("updates badge to 'failed' when server reports phase=error", async () => {
    kometaState.kometaUpdateJobId = 'abc'
    mockFetchOnce(makeOkResponse({
      success: true,
      job: { phase: 'error' },
      lines: [],
      next_index: 0,
      done: false
    }))
    await pollKometaUpdateProgress()
    expect(setKometaUpdatePhaseBadge).toHaveBeenCalledWith('failed')
  })

  it('does NOT update badge for other phases (they get inferred from log lines)', async () => {
    kometaState.kometaUpdateJobId = 'abc'
    mockFetchOnce(makeOkResponse({
      success: true,
      job: { phase: 'running' },
      lines: [],
      next_index: 0,
      done: false
    }))
    await pollKometaUpdateProgress()
    expect(setKometaUpdatePhaseBadge).not.toHaveBeenCalled()
  })
})

describe('pollKometaUpdateProgress -- log line appending', () => {
  it('calls appendKometaStatusLine for each line in data.lines', async () => {
    kometaState.kometaUpdateJobId = 'abc'
    mockFetchOnce(makeOkResponse({
      success: true,
      job: { phase: 'running' },
      lines: ['line one', 'line two', 'line three'],
      next_index: 3,
      done: false
    }))
    await pollKometaUpdateProgress()
    expect(appendKometaStatusLine).toHaveBeenCalledTimes(3)
    expect(appendKometaStatusLine).toHaveBeenNthCalledWith(1, 'line one')
    expect(appendKometaStatusLine).toHaveBeenNthCalledWith(2, 'line two')
    expect(appendKometaStatusLine).toHaveBeenNthCalledWith(3, 'line three')
  })

  it('handles missing lines array gracefully (no calls)', async () => {
    kometaState.kometaUpdateJobId = 'abc'
    mockFetchOnce(makeOkResponse({
      success: true,
      job: { phase: 'running' },
      next_index: 0,
      done: false
    }))
    await pollKometaUpdateProgress()
    expect(appendKometaStatusLine).not.toHaveBeenCalled()
  })

  it('handles non-array lines gracefully (no calls)', async () => {
    kometaState.kometaUpdateJobId = 'abc'
    mockFetchOnce(makeOkResponse({
      success: true,
      job: { phase: 'running' },
      lines: null,
      next_index: 0,
      done: false
    }))
    await pollKometaUpdateProgress()
    expect(appendKometaStatusLine).not.toHaveBeenCalled()
  })
})

describe('pollKometaUpdateProgress -- cursor advancement', () => {
  it('advances kometaUpdateLogIndex from next_index', async () => {
    kometaState.kometaUpdateJobId = 'abc'
    kometaState.kometaUpdateLogIndex = 0
    mockFetchOnce(makeOkResponse({
      success: true,
      job: { phase: 'running' },
      lines: ['a', 'b'],
      next_index: 2,
      done: false
    }))
    await pollKometaUpdateProgress()
    expect(kometaState.kometaUpdateLogIndex).toBe(2)
  })

  it('does not advance when next_index is not a number', async () => {
    kometaState.kometaUpdateJobId = 'abc'
    kometaState.kometaUpdateLogIndex = 5
    mockFetchOnce(makeOkResponse({
      success: true,
      job: { phase: 'running' },
      lines: [],
      next_index: null,
      done: false
    }))
    await pollKometaUpdateProgress()
    expect(kometaState.kometaUpdateLogIndex).toBe(5)  // unchanged
  })
})

describe('pollKometaUpdateProgress -- done handling', () => {
  it('stops polling when data.done is true', async () => {
    kometaState.kometaUpdateJobId = 'abc'
    kometaState.kometaUpdatePollInterval = setInterval(() => {}, 10_000)
    const clearIntervalSpy = vi.spyOn(global, 'clearInterval')
    mockFetchOnce(makeOkResponse({
      success: true,
      job: { phase: 'completed' },
      lines: [],
      next_index: 42,
      done: true
    }))
    await pollKometaUpdateProgress()
    expect(clearIntervalSpy).toHaveBeenCalled()
    expect(kometaState.kometaUpdatePollInterval).toBeNull()
    clearIntervalSpy.mockRestore()
  })

  it('does NOT stop polling when data.done is false', async () => {
    kometaState.kometaUpdateJobId = 'abc'
    kometaState.kometaUpdatePollInterval = setInterval(() => {}, 10_000)
    const handleBefore = kometaState.kometaUpdatePollInterval
    mockFetchOnce(makeOkResponse({
      success: true,
      job: { phase: 'running' },
      lines: [],
      next_index: 0,
      done: false
    }))
    await pollKometaUpdateProgress()
    expect(kometaState.kometaUpdatePollInterval).toBe(handleBefore)
    // Clean up so we don't leak an interval
    clearInterval(kometaState.kometaUpdatePollInterval)
    kometaState.kometaUpdatePollInterval = null
  })
})

describe('pollKometaUpdateProgress -- return shape', () => {
  it('returns a merged {job, lines, next_index, done} object', async () => {
    kometaState.kometaUpdateJobId = 'abc'
    mockFetchOnce(makeOkResponse({
      success: true,
      job: { phase: 'running', started_at: 123 },
      lines: ['x'],
      next_index: 1,
      done: false
    }))
    const result = await pollKometaUpdateProgress()
    expect(result).toEqual({
      phase: 'running',
      started_at: 123,
      lines: ['x'],
      next_index: 1,
      done: false
    })
  })

  it('handles missing job field with an empty object fallback', async () => {
    kometaState.kometaUpdateJobId = 'abc'
    // Server returns success=true and a job field, but the job is
    // an empty object -- the merge should still work.
    mockFetchOnce(makeOkResponse({
      success: true,
      job: {},
      lines: [],
      next_index: 0,
      done: false
    }))
    const result = await pollKometaUpdateProgress()
    expect(result).toMatchObject({
      lines: [],
      next_index: 0,
      done: false
    })
  })
})
