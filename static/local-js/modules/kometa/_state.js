// Shared mutable state for the Kometa page.
//
// Why an exported object (rather than exported `let`s)?
//
//   ES module bindings are LIVE but READ-ONLY from the importer's
//   side. That means:
//
//     // _state.js
//     export let kometaInterval = null
//     // 900-kometa.js
//     import { kometaInterval } from './_state.js'
//     kometaInterval = setInterval(...)   // TypeError!
//
//   Exporting an object avoids the assignment-to-import problem
//   because we're mutating a property of the object, not reassigning
//   the binding itself:
//
//     // _state.js
//     export const kometaState = { kometaInterval: null }
//     // 900-kometa.js
//     import { kometaState } from './_state.js'
//     kometaState.kometaInterval = setInterval(...)  // works
//
//   The same `kometaState` object is shared across every module that
//   imports it, so mutations are visible everywhere. That's exactly
//   the semantics the pre-extraction code relied on (top-level
//   `let`s in a single script tag).
//
//   Naming note: we call the export `kometaState` (not just `state`)
//   to avoid shadowing three pre-existing local `state` variables
//   in 900-kometa.js -- a `setHeaderRollupBadge(id, state, label)`
//   parameter, a destructured `const { state } = getKometaRollupStatus()`,
//   and a `const state = window.QSBulkValidation.getSummaryState(...)`.
//   None of those are semantically related to shared page state, so
//   qualifying the import name is the least invasive fix.
//
// SCOPE OF THIS FILE (as of this PR):
//
//   Only the polling-handle group. These are 7 mutable variables
//   that behave as a natural cluster -- they're all timer handles or
//   job coordinators used by the Kometa run + update flows. Extracting
//   them first has three benefits:
//
//     1. Small, reviewable diff (~40 call sites) proves the pattern
//        works end-to-end without needing to touch hot paths
//     2. Establishes the file so future extractions (which will need
//        their own mutable state) have a place to add fields
//     3. Doesn't force any downstream module extraction to happen
//        together with the state move
//
//   Later extractions may add fields here as they need them. When
//   ADDING a field, prefer:
//     - camelCase names (matches the existing legacy names once
//       the SCREAMING_SNAKE_CASE ones migrate)
//     - a comment noting which module(s) are the primary reader(s)
//     - grouping visually with related fields

export const kometaState = {
  // ---- Kometa run polling handles -----------------------------------
  // These three intervals are the heart of the "Kometa is running"
  // page: fetchKometaLog, checkKometaStatus, fetchRunProgress. They're
  // set up together in startKometaPolling and torn down together in
  // stopKometaPolling.
  kometaInterval: null,
  kometaStatusInterval: null,
  kometaProgressInterval: null,
  // Sentinel to prevent double-start of the polling group. Also reset
  // when the run finishes so the next run can re-enter the polling
  // setup path.
  kometaPollingStarted: false,

  // ---- Kometa update job coordination -------------------------------
  // These three drive the background-job polling for the git pull /
  // pip install / restart flow. The jobId comes back from the POST
  // that kicks off the job; logIndex tracks how far into the job's
  // rolling log buffer we've already displayed.
  kometaUpdatePollInterval: null,
  kometaUpdateJobId: null,
  kometaUpdateLogIndex: 0,

  // ---- Validation gate ---------------------------------------------
  // showYAML is the master "is the config known-good enough to show
  // the YAML output + run controls" flag. Written by
  // updateValidationGate (in _validationGate.js) after synthesizing
  // five per-page validation flags + the final gate stage. Read by
  // syncFinalAccordionRollups, the run controls, and the update job
  // to gate their UI. Was a top-level `let showYAML` in 900-kometa.js
  // pre-migration.
  showYAML: false,

  // ---- Run command override ---------------------------------------
  // When set, the run-command output panel shows this specific
  // command (instead of the one buildCommand would freshly produce).
  // Used for two paths:
  //   - "recovery": show the command that Kometa was invoked with
  //     when a run was interrupted and needs to be resumed
  //   - "logged": show the command from the last completed log
  //
  // activeRunCommandOverride  = string or null (the frozen command)
  // activeRunCommandMode      = 'current' | 'recovery' | 'logged'
  //
  // Written by applyActiveRunCommandState / clearActiveRunCommandState
  // in _runCommand.js. Read by buildCommand (to decide whether to
  // overwrite the output panel) and by the run-command polling loop
  // (to include mode in the start-run payload).
  activeRunCommandOverride: null,
  activeRunCommandMode: null,

  // ---- Kometa runtime status flags ---------------------------------
  //
  // These ten booleans + one status string are the aggregate view of
  // "where is the Kometa install and what is it doing right now?"
  // They gate every run-related UI interaction (run-now enablement,
  // update-flow visibility, badge state, etc.).
  //
  // Kept together to make the state machine visible in one place.
  // Previously ten top-level `let KOMETA_*` in 900-kometa.js.
  //
  //   kometaInstalled            -- Kometa found at the configured
  //                                 root (kometa.py + venv exist)
  //   kometaValidated            -- validateKometaRoot succeeded
  //                                 and the env is fully usable
  //   kometaValidationInProgress -- validateKometaRoot fetch in flight
  //   kometaLocalCheckCompleted  -- probeKometaRoot has finished at
  //                                 least once this session
  //
  //   kometaUpdating             -- an install/update job is running
  //   kometaUpdateAvailable      -- upstream has a newer version
  //                                 than the local checkout
  //   kometaUpdateCheckSkipped   -- the update check bailed early
  //                                 (offline / external mode / etc.)
  //   kometaUpdateCheckCompleted -- version check has finished at
  //                                 least once this session
  //
  //   kometaStatus               -- 'idle' | 'running' | 'stopping'
  //                                 | 'completed' | 'failed' | null
  //   kometaPendingStart         -- a start-run request is in flight
  //                                 (button was clicked, waiting for
  //                                 the server confirm)
  //
  // NAMING NOTE: the pre-migration versions were SCREAMING_SNAKE_CASE
  // (KOMETA_INSTALLED etc.). The migrated fields use camelCase to
  // match the rest of kometaState. All references were renamed in the
  // same PR that introduced these fields.
  kometaInstalled: false,
  kometaValidated: false,
  kometaValidationInProgress: false,
  kometaLocalCheckCompleted: false,
  kometaUpdating: false,
  kometaUpdateAvailable: false,
  kometaUpdateCheckSkipped: false,
  kometaUpdateCheckCompleted: false,
  kometaStatus: null,
  kometaPendingStart: false,

  // ---- Logscan cache -----------------------------------------------
  // The most recent /logscan payload fetched from the server, kept
  // around so header-badge refreshes and other polling passes can
  // work off a snapshot instead of blocking on a new HTTP round-trip.
  //
  //   null                       -- never fetched successfully yet
  //   { error: '...' }           -- fetch failed; renderers show
  //                                 'Unavailable' state
  //   { recommendations: [...],  -- fetch succeeded; count arrays
  //     missing_people: [...],     drive the 'N items' badge
  //     ... }
  //
  // Written by the polling loop in 900-kometa.js after every
  // successful fetchLogscan(). Read by updateLogscanHeaderBadge (in
  // _headerBadges.js) when it's called without an explicit data arg.
  lastLogscanPayload: null,

  // ---- Kometa branch + version-check status ------------------------
  //
  // Written by syncKometaSourceStatus (in _kometaBranch.js) whenever
  // checkKometaUpdate returns new data. Read by that same function
  // on subsequent calls (so it can preserve unchanged fields) and by
  // runKometaStatusPass (in 900-kometa.js) for the status-log lines.
  //
  //   kometaLocalVersionStatus     -- 'Unknown' | 'v1.2.3' | ...
  //                                    string reflecting what the
  //                                    local checkout reports
  //   kometaRemoteVersionStatus    -- '' if not-yet-checked, else
  //                                    'v1.2.4' | 'Unavailable' | ...
  //   kometaRemoteVersionChecked   -- true iff we've actually fetched
  //                                    the remote VERSION file this
  //                                    session (as opposed to just
  //                                    reading a stale cached value)
  //   kometaRemoteVersionSkipped   -- true if the remote check was
  //                                    intentionally skipped (e.g.
  //                                    because Kometa is running --
  //                                    we don't want to inflate load)
  //
  // The '' vs null vs 'Unknown' distinctions matter for the display
  // logic in syncKometaSourceStatus: '' -> 'Not checked', 'Unknown'
  // -> literal 'Unknown' text (server returned no version), non-empty
  // string -> show it verbatim.
  kometaLocalVersionStatus: 'Unknown',
  kometaRemoteVersionStatus: '',
  kometaRemoteVersionChecked: false,
  kometaRemoteVersionSkipped: false,

  // ---- Update-phase badge status ----------------------------------
  //
  // The 'phase' of a Kometa update in progress. Read by no one
  // currently (the badge display is driven by DOM class manipulation
  // in setKometaUpdatePhaseBadge), but preserved as state for future
  // callers that want to know 'what phase are we in?' without
  // scraping the badge's textContent. Written whenever
  // setKometaUpdatePhaseBadge is called; defaults to 'idle'.
  //
  // Valid values (matches the phaseMap keys in _updatePhase.js):
  //   'idle' | 'checking' | 'queued' | 'downloading' | 'extracting'
  //   | 'preserving' | 'venv' | 'dependencies' | 'validating'
  //   | 'ready' | 'failed'
  kometaUpdatePhaseStatus: 'idle'
}
