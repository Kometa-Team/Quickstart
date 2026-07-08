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
  kometaUpdateLogIndex: 0
}
