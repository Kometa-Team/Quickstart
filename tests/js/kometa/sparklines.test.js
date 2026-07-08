// Tests for static/local-js/modules/kometa/_sparklines.js
//
// Coverage strategy per exported function:
//
//   renderRunSparklines
//     - no container in DOM -> silent no-op
//     - empty buffers -> hides container (.d-none) and clears each
//       polyline's `points` attribute
//     - populated buffers -> shows container and writes points
//       attribute on each polyline
//     - IO polylines get the scaled-points geometry (based on max
//       of read+write)
//
//   resetRunSparklines
//     - empties all six buffers
//     - triggers a re-render (adds .d-none)
//
//   updateRunSparklines
//     - null/undefined data -> resets (delegates to resetRunSparklines)
//     - data.status !== 'running' -> resets
//     - data.status === 'running' -> pushes six samples + renders
//     - missing/non-numeric disk rates get pushed as null (gap marker)
//     - negative rates get clamped to 0

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  renderRunSparklines,
  resetRunSparklines,
  updateRunSparklines,
  getSparkBuffers
} from '../../../static/local-js/modules/kometa/_sparklines.js'

// ---------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------

function installSparklineDom () {
  document.body.innerHTML = `
    <div id="run-status-sparklines" class="d-none">
      <svg><polyline id="run-spark-cpu-system"/></svg>
      <svg><polyline id="run-spark-cpu-kometa"/></svg>
      <svg><polyline id="run-spark-mem-system"/></svg>
      <svg><polyline id="run-spark-mem-kometa"/></svg>
      <svg><polyline id="run-spark-io-read"/></svg>
      <svg><polyline id="run-spark-io-write"/></svg>
    </div>
  `
}

// Reset the internal buffers BEFORE every test so state doesn't
// leak across the module-level ring buffers. resetRunSparklines
// happens to be exactly that reset (plus a render), so it's the
// simplest way to fixture. If it ever breaks, tests catch each
// other's state -- which is the right failure mode.
beforeEach(() => {
  installSparklineDom()
  resetRunSparklines()
})

afterEach(() => {
  document.body.innerHTML = ''
})

// ---------------------------------------------------------------------
// renderRunSparklines
// ---------------------------------------------------------------------

describe('renderRunSparklines', () => {
  it('is a no-op when the container is missing from the DOM', () => {
    document.body.innerHTML = ''
    expect(() => renderRunSparklines()).not.toThrow()
  })

  it('hides the container and clears polylines when all buffers empty', () => {
    // Force the container to visible so we can prove render toggles it back
    const container = document.getElementById('run-status-sparklines')
    container.classList.remove('d-none')
    // Give the polylines stale point data
    document.getElementById('run-spark-cpu-system').setAttribute('points', 'STALE')
    document.getElementById('run-spark-io-write').setAttribute('points', 'STALE')

    renderRunSparklines()

    expect(container.classList.contains('d-none')).toBe(true)
    expect(document.getElementById('run-spark-cpu-system').getAttribute('points')).toBe('')
    expect(document.getElementById('run-spark-io-write').getAttribute('points')).toBe('')
  })

  it('shows the container and writes points when at least one buffer has data', () => {
    updateRunSparklines({ status: 'running', system_cpu_percent: 42 })
    const container = document.getElementById('run-status-sparklines')
    expect(container.classList.contains('d-none')).toBe(false)
    // system CPU line got a value; kometa CPU line got a null (from
    // missing key) so its polyline shape depends on the util --
    // just prove SOMETHING got written.
    const cpuSysPoints = document.getElementById('run-spark-cpu-system').getAttribute('points')
    expect(cpuSysPoints).toBeTruthy()
    expect(cpuSysPoints.length).toBeGreaterThan(0)
  })
})

// ---------------------------------------------------------------------
// resetRunSparklines
// ---------------------------------------------------------------------

describe('resetRunSparklines', () => {
  it('empties all six buffer arrays', () => {
    // Prime with a value
    updateRunSparklines({
      status: 'running',
      system_cpu_percent: 50,
      cpu_percent: 40,
      system_memory_percent: 60,
      memory_percent: 55,
      disk_read_rate_mb_s: 10,
      disk_write_rate_mb_s: 5
    })

    // Sanity: each buffer has 1 sample
    const before = getSparkBuffers()
    expect(before.cpu.system.length).toBe(1)
    expect(before.io.write.length).toBe(1)

    resetRunSparklines()

    const after = getSparkBuffers()
    expect(after.cpu.system).toEqual([])
    expect(after.cpu.kometa).toEqual([])
    expect(after.mem.system).toEqual([])
    expect(after.mem.kometa).toEqual([])
    expect(after.io.read).toEqual([])
    expect(after.io.write).toEqual([])
  })

  it('re-renders (adds .d-none to the container)', () => {
    // First populate + render to visible
    updateRunSparklines({ status: 'running', cpu_percent: 10 })
    const container = document.getElementById('run-status-sparklines')
    expect(container.classList.contains('d-none')).toBe(false)

    resetRunSparklines()
    expect(container.classList.contains('d-none')).toBe(true)
  })
})

// ---------------------------------------------------------------------
// updateRunSparklines
// ---------------------------------------------------------------------

describe('updateRunSparklines', () => {
  it('resets when data is null/undefined', () => {
    // Prime state first so we can prove the reset actually happens
    updateRunSparklines({ status: 'running', cpu_percent: 99 })
    expect(getSparkBuffers().cpu.kometa.length).toBe(1)

    updateRunSparklines(null)
    expect(getSparkBuffers().cpu.kometa).toEqual([])

    updateRunSparklines({ status: 'running', cpu_percent: 99 })
    updateRunSparklines(undefined)
    expect(getSparkBuffers().cpu.kometa).toEqual([])
  })

  it("resets when data.status is not 'running'", () => {
    updateRunSparklines({ status: 'running', cpu_percent: 42 })
    expect(getSparkBuffers().cpu.kometa.length).toBe(1)

    updateRunSparklines({ status: 'idle', cpu_percent: 42 })
    expect(getSparkBuffers().cpu.kometa).toEqual([])
  })

  it('pushes all six samples when status is running', () => {
    updateRunSparklines({
      status: 'running',
      system_cpu_percent: 25,
      cpu_percent: 30,
      system_memory_percent: 40,
      memory_percent: 45,
      disk_read_rate_mb_s: 10,
      disk_write_rate_mb_s: 5
    })

    const b = getSparkBuffers()
    expect(b.cpu.system).toEqual([25])
    expect(b.cpu.kometa).toEqual([30])
    expect(b.mem.system).toEqual([40])
    expect(b.mem.kometa).toEqual([45])
    expect(b.io.read).toEqual([10])
    expect(b.io.write).toEqual([5])
  })

  it('appends across multiple ticks (accumulates a series)', () => {
    updateRunSparklines({ status: 'running', cpu_percent: 10 })
    updateRunSparklines({ status: 'running', cpu_percent: 20 })
    updateRunSparklines({ status: 'running', cpu_percent: 30 })
    expect(getSparkBuffers().cpu.kometa).toEqual([10, 20, 30])
  })

  it('does not push null when the buffer is empty (leading null is dropped)', () => {
    // pushSparkValue skips a null value when the series is empty --
    // a "gap" before any data is meaningless. Prove that the io
    // buffers stay empty when the first tick has no disk rates.
    updateRunSparklines({ status: 'running', cpu_percent: 50 })
    // No disk_read_rate_mb_s / disk_write_rate_mb_s
    expect(getSparkBuffers().io.read).toEqual([])
    expect(getSparkBuffers().io.write).toEqual([])
  })

  it('duplicates the last sample when a null follows real data', () => {
    // Tick 1: real data. Tick 2: null (missing). pushSparkValue
    // repeats the previous sample so the line stays continuous
    // rather than exhibiting a spurious dip to zero.
    updateRunSparklines({
      status: 'running',
      cpu_percent: 50,
      disk_read_rate_mb_s: 10,
      disk_write_rate_mb_s: 3
    })
    updateRunSparklines({ status: 'running', cpu_percent: 55 })
    // Missing disk rates -> re-push the prior samples
    expect(getSparkBuffers().io.read).toEqual([10, 10])
    expect(getSparkBuffers().io.write).toEqual([3, 3])
  })

  it('drops non-numeric disk rate values (same gap-null semantics)', () => {
    updateRunSparklines({
      status: 'running',
      cpu_percent: 50,
      disk_read_rate_mb_s: 'garbage',
      disk_write_rate_mb_s: NaN
    })
    // Same as "missing" -- coerced to null, dropped when buffer empty
    expect(getSparkBuffers().io.read).toEqual([])
    expect(getSparkBuffers().io.write).toEqual([])
  })

  it('clamps negative disk rates to 0', () => {
    // Negative rates are physically impossible but the server has
    // been known to emit them for a first-sample-after-restart edge
    // case. Max(0, x) safety-net.
    updateRunSparklines({
      status: 'running',
      cpu_percent: 50,
      disk_read_rate_mb_s: -100,
      disk_write_rate_mb_s: -1
    })
    expect(getSparkBuffers().io.read).toEqual([0])
    expect(getSparkBuffers().io.write).toEqual([0])
  })

  it('after populating, container is visible and polylines have points', () => {
    updateRunSparklines({
      status: 'running',
      system_cpu_percent: 50, cpu_percent: 60,
      system_memory_percent: 70, memory_percent: 80,
      disk_read_rate_mb_s: 5, disk_write_rate_mb_s: 3
    })
    const container = document.getElementById('run-status-sparklines')
    expect(container.classList.contains('d-none')).toBe(false)
    // Every polyline should have a non-empty points attribute
    const ids = [
      'run-spark-cpu-system', 'run-spark-cpu-kometa',
      'run-spark-mem-system', 'run-spark-mem-kometa',
      'run-spark-io-read', 'run-spark-io-write'
    ]
    for (const id of ids) {
      const pts = document.getElementById(id).getAttribute('points')
      expect(pts, `polyline ${id} should have points`).toBeTruthy()
      expect(pts.length, `polyline ${id} points not empty`).toBeGreaterThan(0)
    }
  })
})
