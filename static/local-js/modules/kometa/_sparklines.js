// Run-status sparklines: the tiny inline SVG line-charts that appear
// above the run-status panel while Kometa is running. Six series in
// total, arranged as three pairs:
//
//   CPU:  system %      | kometa %
//   MEM:  system %      | kometa %
//   IO:   read MB/s     | write MB/s
//
// The CPU + MEM series are percentages 0-100 and rendered on a shared
// 0-100 scale. The IO series are raw MB/s and get normalized against
// the max of BOTH read+write for the current window, so the two lines
// stay visually comparable regardless of absolute magnitude.
//
// DATA FLOW:
//
//   fetchRunProgress (900-kometa.js) -> updateRunStatus (900-kometa.js)
//       -> updateRunSparklines(data)  [this module]
//           -> pushSparkValue (from _util.js) into the ring buffers
//           -> renderRunSparklines()
//               -> writeAttribute('points', ...) on 6 <polyline>s
//
//   When status flips to !running, updateRunSparklines calls
//   resetRunSparklines which clears the buffers + re-renders (which
//   hides the panel by adding .d-none).
//
// MODULE STATE:
//
//   sparkBuffers  private object holding the 6 ring buffers. Not
//                 exported -- callers should mutate it only through
//                 updateRunSparklines / resetRunSparklines.
//
//   getSparkBuffers  read-only accessor for tests to snapshot buffer
//                    state without needing kometaState-level plumbing
//                    (this module doesn't need cross-module sharing;
//                    the buffers are truly private).
//
// The three CPU/MEM/IO DOM elements are looked up lazily on each
// render so the module doesn't hard-depend on DOM readiness at import
// time. Cheap. Keeps the module trivially unit-testable.

import { buildSparklinePoints, buildSparklinePointsScaled, clampPercent, pushSparkValue } from './_util.js'

// Ring buffers for each series. Populated by pushSparkValue (which
// bounds them at N samples -- see _util.js for N). The nested shape
// exactly mirrors the pre-extraction top-level `runSparkState` const
// so any test/debug snippet can still recognize it.
const sparkBuffers = {
  cpu: { system: [], kometa: [] },
  mem: { system: [], kometa: [] },
  io: { read: [], write: [] }
}

/**
 * Test-only accessor. Returns the LIVE buffer object so callers can
 * inspect current samples without going through render (which would
 * require a DOM). Do NOT rely on this from production code -- prefer
 * exposing an API that tests + prod both use.
 *
 * @returns {typeof sparkBuffers}
 */
export function getSparkBuffers () {
  return sparkBuffers
}

/**
 * Whether any of the six buffers has at least one sample.
 * @returns {boolean}
 */
function hasAnyData () {
  return (
    sparkBuffers.cpu.system.length > 0 ||
    sparkBuffers.cpu.kometa.length > 0 ||
    sparkBuffers.mem.system.length > 0 ||
    sparkBuffers.mem.kometa.length > 0 ||
    sparkBuffers.io.read.length > 0 ||
    sparkBuffers.io.write.length > 0
  )
}

/**
 * Repaint all six sparklines. Toggles the .d-none class on the
 * enclosing container so an empty state hides the whole widget.
 *
 * No-op if #run-status-sparklines container is missing (page hasn't
 * rendered yet).
 */
export function renderRunSparklines () {
  const container = document.getElementById('run-status-sparklines')
  if (!container) return

  // Lazily resolve each polyline. Two paths below (empty vs data)
  // both need the CPU + MEM elements; IO elements only when we're
  // painting data.
  const cpuSystem = document.getElementById('run-spark-cpu-system')
  const cpuKometa = document.getElementById('run-spark-cpu-kometa')
  const memSystem = document.getElementById('run-spark-mem-system')
  const memKometa = document.getElementById('run-spark-mem-kometa')
  const ioRead = document.getElementById('run-spark-io-read')
  const ioWrite = document.getElementById('run-spark-io-write')

  const dataPresent = hasAnyData()
  container.classList.toggle('d-none', !dataPresent)

  if (!dataPresent) {
    // Clear every polyline so a subsequent "has data" render doesn't
    // briefly show stale lines during the layout flush.
    if (cpuSystem) cpuSystem.setAttribute('points', '')
    if (cpuKometa) cpuKometa.setAttribute('points', '')
    if (memSystem) memSystem.setAttribute('points', '')
    if (memKometa) memKometa.setAttribute('points', '')
    if (ioRead) ioRead.setAttribute('points', '')
    if (ioWrite) ioWrite.setAttribute('points', '')
    return
  }

  // CPU + MEM lines share the fixed 0-100 scale (buildSparklinePoints).
  if (cpuSystem) cpuSystem.setAttribute('points', buildSparklinePoints(sparkBuffers.cpu.system))
  if (cpuKometa) cpuKometa.setAttribute('points', buildSparklinePoints(sparkBuffers.cpu.kometa))
  if (memSystem) memSystem.setAttribute('points', buildSparklinePoints(sparkBuffers.mem.system))
  if (memKometa) memKometa.setAttribute('points', buildSparklinePoints(sparkBuffers.mem.kometa))

  // IO lines share a dynamically-computed scale based on the max of
  // BOTH read + write across the current window. Ensures the two
  // lines stay visually comparable when magnitudes differ (e.g.
  // 50 MB/s read + 3 MB/s write should NOT flatten the write line
  // to zero).
  const ioMax = Math.max(0, ...sparkBuffers.io.read, ...sparkBuffers.io.write)
  if (ioRead) ioRead.setAttribute('points', buildSparklinePointsScaled(sparkBuffers.io.read, ioMax))
  if (ioWrite) ioWrite.setAttribute('points', buildSparklinePointsScaled(sparkBuffers.io.write, ioMax))
}

/**
 * Empty every ring buffer and repaint. Called when a run stops.
 */
export function resetRunSparklines () {
  sparkBuffers.cpu.system = []
  sparkBuffers.cpu.kometa = []
  sparkBuffers.mem.system = []
  sparkBuffers.mem.kometa = []
  sparkBuffers.io.read = []
  sparkBuffers.io.write = []
  renderRunSparklines()
}

/**
 * Ingest one polling payload from the run-progress endpoint. If the
 * payload indicates the run is stopped, we reset instead. Otherwise
 * pushes six samples (four percentages + two rates) and renders.
 *
 * The IO rates are pushed as `null` when the server omits them
 * (typical during warm-up before the first delta is computed) -- the
 * ring-buffer code in pushSparkValue handles null as "gap".
 *
 * @param {{
 *   status?: string,
 *   system_cpu_percent?: number,
 *   cpu_percent?: number,
 *   system_memory_percent?: number,
 *   memory_percent?: number,
 *   disk_read_rate_mb_s?: number,
 *   disk_write_rate_mb_s?: number
 * } | null | undefined} data
 */
export function updateRunSparklines (data) {
  if (!data || data.status !== 'running') {
    resetRunSparklines()
    return
  }

  const cpuSystem = clampPercent(data.system_cpu_percent)
  const cpuKometa = clampPercent(data.cpu_percent)
  const memSystem = clampPercent(data.system_memory_percent)
  const memKometa = clampPercent(data.memory_percent)

  // Rates: server may omit them during the first tick after start,
  // when there's no previous sample to compute a delta from. Push
  // null rather than 0 -- pushSparkValue handles null by repeating
  // the previous sample (or dropping the push entirely if the buffer
  // is still empty). Either way, no spurious "dip to zero" appears.
  const ioRead = (typeof data.disk_read_rate_mb_s === 'number' && Number.isFinite(data.disk_read_rate_mb_s))
    ? Math.max(0, data.disk_read_rate_mb_s)
    : null
  const ioWrite = (typeof data.disk_write_rate_mb_s === 'number' && Number.isFinite(data.disk_write_rate_mb_s))
    ? Math.max(0, data.disk_write_rate_mb_s)
    : null

  pushSparkValue(sparkBuffers.cpu.system, cpuSystem)
  pushSparkValue(sparkBuffers.cpu.kometa, cpuKometa)
  pushSparkValue(sparkBuffers.mem.system, memSystem)
  pushSparkValue(sparkBuffers.mem.kometa, memKometa)
  pushSparkValue(sparkBuffers.io.read, ioRead)
  pushSparkValue(sparkBuffers.io.write, ioWrite)

  renderRunSparklines()
}
