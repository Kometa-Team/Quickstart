// Tests for static/local-js/modules/kometa/_state.js
//
// The module has zero behavior of its own -- it just exports a
// mutable object. That means the tests exist to prove three things
// that WILL matter as future PRs extract more feature modules that
// read/write this state:
//
//   1. Initial values are correct on first import (defensive: a stray
//      typo like `kometaPollingStarted: 'false'` would silently break
//      the polling guards downstream)
//   2. Property mutation works end-to-end (which is the whole point
//      of the object-vs-`let` design decision documented in _state.js)
//   3. The same object identity is shared across importers (proves
//      the "shared mutable state" contract that lets extracted modules
//      coordinate with 900-kometa.js without extra plumbing)
//
// Because ES module instances are cached per specifier, importing
// `_state.js` from two different `import` statements returns the
// exact same object reference. That's easy to verify.

import { describe, expect, it, beforeEach } from 'vitest'
import { kometaState } from '../../../static/local-js/modules/kometa/_state.js'

// Snapshot the initial defaults so any test that mutates kometaState
// can restore it. Without this, test order would matter.
const INITIAL_STATE = { ...kometaState }

beforeEach(() => {
  // Reset every field to its declared initial value. Using Object.assign
  // rather than reassigning `kometaState` because reassignment wouldn't
  // affect the shared reference held by any other importer.
  Object.assign(kometaState, INITIAL_STATE)
})

describe('kometaState initial values', () => {
  it('kometaInterval starts as null (no polling handle)', () => {
    expect(kometaState.kometaInterval).toBeNull()
  })

  it('kometaStatusInterval starts as null', () => {
    expect(kometaState.kometaStatusInterval).toBeNull()
  })

  it('kometaProgressInterval starts as null', () => {
    expect(kometaState.kometaProgressInterval).toBeNull()
  })

  it('kometaPollingStarted starts as false (not the string "false")', () => {
    // Explicit strict check: a typo like `false` -> `'false'` would
    // silently break the `if (kometaState.kometaPollingStarted) return`
    // guard in startKometaPolling because the string 'false' is truthy.
    expect(kometaState.kometaPollingStarted).toBe(false)
    expect(typeof kometaState.kometaPollingStarted).toBe('boolean')
  })

  it('kometaUpdatePollInterval starts as null', () => {
    expect(kometaState.kometaUpdatePollInterval).toBeNull()
  })

  it('kometaUpdateJobId starts as null', () => {
    expect(kometaState.kometaUpdateJobId).toBeNull()
  })

  it('kometaUpdateLogIndex starts as 0 (not null, not "0")', () => {
    // The log index is used as a numeric offset in the log-tail fetch;
    // if it were null we'd send "null" over the wire.
    expect(kometaState.kometaUpdateLogIndex).toBe(0)
    expect(typeof kometaState.kometaUpdateLogIndex).toBe('number')
  })

  it('showYAML starts as false (gate defaults to hidden)', () => {
    // The default matches the pre-migration `let showYAML = false`
    // top-level in 900-kometa.js. This is important: on page load,
    // before any validation runs, we must NOT show YAML output or
    // run controls.
    expect(kometaState.showYAML).toBe(false)
    expect(typeof kometaState.showYAML).toBe('boolean')
  })

  it('activeRunCommandOverride starts as null', () => {
    // Null (not '' or undefined) so buildCommand's
    // `if (!kometaState.activeRunCommandOverride)` short-circuit
    // works uniformly on first load.
    expect(kometaState.activeRunCommandOverride).toBeNull()
  })

  it('activeRunCommandMode starts as null', () => {
    // Callers fall back to 'current' or 'recovery' explicitly when
    // no mode is set, so null (rather than 'current') keeps the
    // "never been set" state distinguishable from "set to current".
    expect(kometaState.activeRunCommandMode).toBeNull()
  })

  it('all 8 kometa boolean status flags start as false', () => {
    // Every KOMETA_* flag migrated from 900-kometa.js was pre-set to
    // false at page load and updated on user actions / polling. The
    // migration preserves that default so no code path sees a
    // permissive 'true' before its first real evaluation.
    expect(kometaState.kometaInstalled).toBe(false)
    expect(kometaState.kometaValidated).toBe(false)
    expect(kometaState.kometaValidationInProgress).toBe(false)
    expect(kometaState.kometaLocalCheckCompleted).toBe(false)
    expect(kometaState.kometaUpdating).toBe(false)
    expect(kometaState.kometaUpdateAvailable).toBe(false)
    expect(kometaState.kometaUpdateCheckSkipped).toBe(false)
    expect(kometaState.kometaUpdateCheckCompleted).toBe(false)
    expect(kometaState.kometaPendingStart).toBe(false)
  })

  it('kometaStatus starts as null (not "idle")', () => {
    // Null distinguishes "never polled" from "polled and got 'idle'".
    // Some code paths gate on `kometaStatus === 'running'` -- if we
    // defaulted to 'idle', a first-page-load state check might
    // report a stale status before the real status arrives.
    expect(kometaState.kometaStatus).toBeNull()
  })

  it('lastLogscanPayload starts as null', () => {
    // The logscan header badge distinguishes "no data yet" (Pending)
    // from "data with 0 issues" (No issues) -- both are legit states.
    // Null (rather than {}) keeps that distinction sharp on first
    // page load, before the first /logscan poll returns.
    expect(kometaState.lastLogscanPayload).toBeNull()
  })

  it('Kometa branch/version fields start in their pre-check defaults', () => {
    // These four fields drive the source-status panel in _kometaBranch.js.
    //
    //   kometaLocalVersionStatus  -- 'Unknown' (not '' or null) so
    //                                 first-render shows 'Unknown'
    //                                 verbatim; empty would fall back
    //                                 to 'Unknown' anyway but that
    //                                 obscures intent.
    //   kometaRemoteVersionStatus -- '' (empty means 'never fetched');
    //                                 combined with checked=false the
    //                                 UI shows 'Not checked'.
    //   kometaRemoteVersionChecked -- false until we've actually hit
    //                                  the remote endpoint at least once.
    //   kometaRemoteVersionSkipped -- false unless the check was
    //                                  intentionally skipped (running).
    expect(kometaState.kometaLocalVersionStatus).toBe('Unknown')
    expect(kometaState.kometaRemoteVersionStatus).toBe('')
    expect(kometaState.kometaRemoteVersionChecked).toBe(false)
    expect(kometaState.kometaRemoteVersionSkipped).toBe(false)
  })

  it("kometaUpdatePhaseStatus starts as 'idle'", () => {
    // Written by setKometaUpdatePhaseBadge (in _updatePhase.js) every
    // time a phase is set. 'idle' is the visual default -- gray badge,
    // 'Idle' label -- so starting here gives a clean first paint
    // before any update flow kicks off.
    expect(kometaState.kometaUpdatePhaseStatus).toBe('idle')
  })

  it('exports exactly the fields the runtime relies on (guards against typos)', () => {
    // Sorted alphabetically for a stable comparison
    expect(Object.keys(kometaState).sort()).toEqual([
      'activeRunCommandMode',
      'activeRunCommandOverride',
      'kometaInstalled',
      'kometaInterval',
      'kometaLocalCheckCompleted',
      'kometaLocalVersionStatus',
      'kometaPendingStart',
      'kometaPollingStarted',
      'kometaProgressInterval',
      'kometaRemoteVersionChecked',
      'kometaRemoteVersionSkipped',
      'kometaRemoteVersionStatus',
      'kometaStatus',
      'kometaStatusInterval',
      'kometaUpdateAvailable',
      'kometaUpdateCheckCompleted',
      'kometaUpdateCheckSkipped',
      'kometaUpdateJobId',
      'kometaUpdateLogIndex',
      'kometaUpdatePhaseStatus',
      'kometaUpdatePollInterval',
      'kometaUpdating',
      'kometaValidated',
      'kometaValidationInProgress',
      'lastLogscanPayload',
      'lastRunProgressPayload',
      'latestKometaStatusPayload',
      'runProgressInFlight',
      'showYAML'
    ])
  })
})

describe('kometaState mutation semantics', () => {
  it('allows reassigning fields to non-null values', () => {
    // Simulates startKometaPolling storing a setInterval handle
    const fakeHandle = { fake: 'interval handle' }
    kometaState.kometaInterval = fakeHandle
    expect(kometaState.kometaInterval).toBe(fakeHandle)
  })

  it('allows resetting fields to null (stopKometaPolling flow)', () => {
    kometaState.kometaProgressInterval = { fake: 'handle' }
    kometaState.kometaProgressInterval = null
    expect(kometaState.kometaProgressInterval).toBeNull()
  })

  it('allows numeric increment of kometaUpdateLogIndex', () => {
    // Mirrors: if (typeof data.next_index === 'number')
    //           kometaState.kometaUpdateLogIndex = data.next_index
    kometaState.kometaUpdateLogIndex = 42
    expect(kometaState.kometaUpdateLogIndex).toBe(42)
    kometaState.kometaUpdateLogIndex = 128
    expect(kometaState.kometaUpdateLogIndex).toBe(128)
  })

  it('allows storing an arbitrary string jobId', () => {
    kometaState.kometaUpdateJobId = 'abc-123-def-456'
    expect(kometaState.kometaUpdateJobId).toBe('abc-123-def-456')
  })

  it('allows toggling kometaPollingStarted (guard flag)', () => {
    expect(kometaState.kometaPollingStarted).toBe(false)
    kometaState.kometaPollingStarted = true
    expect(kometaState.kometaPollingStarted).toBe(true)
    kometaState.kometaPollingStarted = false
    expect(kometaState.kometaPollingStarted).toBe(false)
  })
})

describe('kometaState shared identity across importers', () => {
  it('re-importing returns the same object reference (module caching)', async () => {
    // ES module instance caching means the second import returns the
    // exact same object -- not a copy, not a new instance.
    const second = await import('../../../static/local-js/modules/kometa/_state.js')
    expect(second.kometaState).toBe(kometaState)
  })

  it('mutations made through one import are visible through another', async () => {
    const second = await import('../../../static/local-js/modules/kometa/_state.js')
    kometaState.kometaUpdateJobId = 'shared-through-imports'
    expect(second.kometaState.kometaUpdateJobId).toBe('shared-through-imports')
    // And symmetrically -- writing through the second import is seen
    // through the first
    second.kometaState.kometaUpdateLogIndex = 9999
    expect(kometaState.kometaUpdateLogIndex).toBe(9999)
  })
})
