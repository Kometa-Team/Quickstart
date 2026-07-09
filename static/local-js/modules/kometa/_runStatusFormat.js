// Formatters for the "run status" bar shown while Kometa is running.
//
// While Kometa is executing, /kometa-status returns a live snapshot
// with CPU/memory/disk metrics for the Kometa process AND the host
// system, plus started-at + elapsed-seconds. Rendering this into the
// UI's timer + metrics rows involves a bunch of tiny formatting
// helpers -- all pure, all easy to test in isolation.
//
// PUBLIC API:
//
//   formatMemoryMB(valueMb)
//     Format a memory number in MB. Returns "N.N MB" below 1024,
//     "N.N GB" at or above 1024, "n/a" for non-finite input.
//
//   formatDiskRateMBs(valueMbS)
//     Same idea but for disk throughput. Two decimal places.
//     "MB/s" or "GB/s" suffix.
//
//   formatPercent(value)
//     Format a percentage. "N.N%" for finite numbers, "n/a" otherwise.
//
//   buildRunStatusText(data, { formatStartedAt, formatElapsed })
//     Compose the two text lines shown in the run-status bar:
//       { timerText, metricsText, stage }
//     `stage` is 'running' | 'done' | 'idle' and determines which
//     text lines are populated.
//
//     Callers inject `formatStartedAt` (typically formatTimestampLocal)
//     and `formatElapsed` (typically formatRunSeconds) so this module
//     doesn't depend on _util.js -- pure functions all the way down.

/**
 * Format a memory value in MB. Auto-scales to GB at 1024 MB.
 * @param {number} valueMb
 * @returns {string}
 */
export function formatMemoryMB (valueMb) {
  if (typeof valueMb !== 'number' || !Number.isFinite(valueMb)) return 'n/a'
  if (valueMb >= 1024) return `${(valueMb / 1024).toFixed(1)} GB`
  return `${valueMb.toFixed(1)} MB`
}

/**
 * Format a disk throughput value in MB/s. Two decimals; scales to GB/s at 1024.
 * @param {number} valueMbS
 * @returns {string}
 */
export function formatDiskRateMBs (valueMbS) {
  if (typeof valueMbS !== 'number' || !Number.isFinite(valueMbS)) return 'n/a'
  if (valueMbS >= 1024) return `${(valueMbS / 1024).toFixed(2)} GB/s`
  return `${valueMbS.toFixed(2)} MB/s`
}

/**
 * Format a percentage as "N.N%" or "n/a" for non-finite input.
 * @param {number} value
 * @returns {string}
 */
export function formatPercent (value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'n/a'
  return `${value.toFixed(1)}%`
}

/**
 * Compose the run-status bar text lines from a /kometa-status payload.
 *
 * Three possible states:
 *
 *   data.status === 'running'
 *     Renders the live snapshot: started-at, elapsed, CPU/mem/disk
 *     for both Kometa and the host system.
 *
 *   data.status === 'done'
 *     Renders "Kometa run complete." with empty metrics.
 *
 *   Any other status / null / undefined
 *     Both lines are empty (caller typically hides the row).
 *
 * @param {object|null} data
 * @param {object} opts
 * @param {(iso:string) => string} opts.formatStartedAt
 *   Format the started_at timestamp for the timer line. Typically
 *   `formatTimestampLocal` from _util.js.
 * @param {(seconds:number) => string} opts.formatElapsed
 *   Format the elapsed-seconds count. Typically `formatRunSeconds`
 *   from _util.js. Falsy return value is replaced with 'n/a'.
 * @returns {{ timerText:string, metricsText:string, stage:string }}
 *   stage is 'running' | 'done' | 'idle'.
 */
export function buildRunStatusText (data, opts) {
  const { formatStartedAt, formatElapsed } = opts

  if (data && data.status === 'running') {
    const startedAt = formatStartedAt(data.started_at)
    const elapsed = formatElapsed(data.elapsed_seconds)
    const cpuText = formatPercent(data.cpu_percent)
    const memRss = formatMemoryMB(data.memory_rss_mb)
    const memPct = formatPercent(data.memory_percent)
    const sysCpu = formatPercent(data.system_cpu_percent)
    const sysUsed = formatMemoryMB(data.system_memory_used_mb)
    const sysTotal = formatMemoryMB(data.system_memory_total_mb)
    const sysPct = formatPercent(data.system_memory_percent)
    const hasDiskData = [
      data.disk_read_mb, data.disk_write_mb,
      data.disk_read_rate_mb_s, data.disk_write_rate_mb_s
    ].some(value => typeof value === 'number' && Number.isFinite(value))
    const diskText = hasDiskData
      ? ` | Disk: R ${formatDiskRateMBs(data.disk_read_rate_mb_s)} • W ${formatDiskRateMBs(data.disk_write_rate_mb_s)} • ${formatMemoryMB(data.disk_read_mb)} read • ${formatMemoryMB(data.disk_write_mb)} written`
      : ''

    return {
      timerText: `Running since: ${startedAt} • Elapsed: ${elapsed || 'n/a'}`,
      metricsText: `Kometa: ${cpuText} CPU • ${memRss} (${memPct}) | System: ${sysCpu} CPU • ${sysUsed} / ${sysTotal} (${sysPct})${diskText}`,
      stage: 'running'
    }
  }

  if (data && data.status === 'done') {
    return {
      timerText: 'Kometa run complete.',
      metricsText: '',
      stage: 'done'
    }
  }

  return { timerText: '', metricsText: '', stage: 'idle' }
}
