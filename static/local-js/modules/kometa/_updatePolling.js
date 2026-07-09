// Background-job polling for Kometa updates.
//
// When callUpdateKometa() (in 900-kometa.js) kicks off a
// background job to download/extract/install Kometa, it stores the
// job id in kometaState.kometaUpdateJobId and starts an interval that
// calls pollKometaUpdateProgress() every few seconds. Each poll
// fetches new log lines from the /background-jobs endpoint and feeds
// them into the phase-inference pipeline (via appendKometaStatusLine).
//
// EXPORTS:
//
//   stopKometaUpdatePolling()
//        -- clear the interval + null out kometaState.kometaUpdatePollInterval.
//           Idempotent: safe to call when no polling is active.
//
//   pollKometaUpdateProgress()
//        -- fetch the next batch of log lines for the current job.
//           Auto-stops polling on `data.done`. Auto-updates the phase
//           badge to 'queued' or 'failed' when the server reports
//           those states.
//
//           Returns a Promise:
//             - Resolves with a merged { ...job, lines, next_index, done }
//               shape on success
//             - Resolves with null when no kometaUpdateJobId is set
//               (nothing to poll)
//             - Rejects with an Error on network / JSON / success=false
//
// STATE TOUCHED:
//
//   Reads:  kometaState.kometaUpdateJobId,
//           kometaState.kometaUpdateLogIndex,
//           kometaState.kometaUpdatePollInterval
//   Writes: kometaState.kometaUpdateLogIndex (advances on each poll),
//           kometaState.kometaUpdatePollInterval (nulled on stop)
//
// SERVER CONTRACT:
//
//   GET /background-jobs/<job_id>?since=<log_index>
//   Response body: {
//     success: true,
//     job: { phase: 'queued'|'running'|'completed'|'error', ... },
//     lines: string[],            // new log lines since `since`
//     next_index: number,         // pass this back as ?since= next time
//     done: boolean               // true when server has no more lines
//   }
//
//   On !success or missing job, we throw with data.error (server
//   supplies a human-readable message).

import { kometaState } from './_state.js'
import { setKometaUpdatePhaseBadge, appendKometaStatusLine } from './_updatePhase.js'

// ---------------------------------------------------------------------
// Polling controls
// ---------------------------------------------------------------------

/**
 * Clear the update-progress polling interval and null out the state
 * handle. Idempotent -- safe to call when polling is already stopped.
 */
export function stopKometaUpdatePolling () {
  if (kometaState.kometaUpdatePollInterval) {
    clearInterval(kometaState.kometaUpdatePollInterval)
    kometaState.kometaUpdatePollInterval = null
  }
}

/**
 * Fetch the next batch of log lines for the currently-running update
 * job. See module docstring for full contract.
 *
 * Short-circuits with `Promise.resolve(null)` when no job id is set --
 * useful for callers that call this from an interval and don't want
 * to error out just because the user cleared / cancelled.
 *
 * @returns {Promise<object | null>}
 */
export function pollKometaUpdateProgress () {
  if (!kometaState.kometaUpdateJobId) return Promise.resolve(null)

  const jobId = encodeURIComponent(kometaState.kometaUpdateJobId)
  const since = encodeURIComponent(String(kometaState.kometaUpdateLogIndex))

  return fetch(`/background-jobs/${jobId}?since=${since}`)
    .then(async res => {
      const data = await res.json()
      if (!res.ok || !data.success || !data.job) {
        throw new Error(data.error || 'Failed to fetch Kometa update progress.')
      }
      return data
    })
    .then(data => {
      const job = data.job || {}

      // Auto-update the phase badge for the two "server-reported"
      // phases. Other phases (downloading / extracting / etc.) get
      // inferred from log-line text via appendKometaStatusLine's
      // built-in phase inference.
      if (job.phase === 'queued') setKometaUpdatePhaseBadge('queued')
      if (job.phase === 'error') setKometaUpdatePhaseBadge('failed')

      const lines = Array.isArray(data.lines) ? data.lines : []
      lines.forEach(line => appendKometaStatusLine(line))

      // Advance our cursor into the server-side log so the next poll
      // asks for lines starting at this index.
      if (typeof data.next_index === 'number') {
        kometaState.kometaUpdateLogIndex = data.next_index
      }

      // Server-side signal that we've drained everything for this
      // job -- stop the interval so we don't keep hammering the
      // endpoint forever.
      if (data.done) stopKometaUpdatePolling()

      return Object.assign({}, job, {
        lines,
        next_index: data.next_index,
        done: data.done
      })
    })
}
