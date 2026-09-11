// Tests for static/local-js/modules/kometa/_runStatusFormat.js
//
// Four exports (all pure functions):
//   - formatMemoryMB(valueMb)
//   - formatDiskRateMBs(valueMbS)
//   - formatPercent(value)
//   - buildRunStatusText(data, { formatStartedAt, formatElapsed })
//
// COVERAGE:
//
//   formatMemoryMB (6):
//     - 0 MB -> "0.0 MB"
//     - <1024 MB -> "N.N MB"
//     - >=1024 MB -> "N.N GB"
//     - exactly 1024 -> "1.0 GB"
//     - non-finite (NaN / Infinity / undefined / string) -> "n/a"
//
//   formatDiskRateMBs (5):
//     - <1024 MB/s -> "N.NN MB/s" (2 decimals)
//     - >=1024 MB/s -> "N.NN GB/s"
//     - 0 MB/s -> "0.00 MB/s"
//     - non-finite -> "n/a"
//     - preserves 2-decimal precision (unlike memory 1-decimal)
//
//   formatPercent (5):
//     - 0 -> "0.0%"
//     - normal float -> "N.N%"
//     - >100% (spillover) -> exact echo, no clamp
//     - negative -> exact echo
//     - non-finite -> "n/a"
//
//   buildRunStatusText (11):
//     - stage='idle' when data is null/undefined/unknown status
//     - stage='done' for status='done' with completion text
//     - stage='running' for status='running' with full metrics
//     - injects formatStartedAt output into timer line
//     - injects formatElapsed output into timer line
//     - falls back to 'n/a' when formatElapsed returns falsy
//     - includes disk block when any disk metric is finite
//     - omits disk block when all disk metrics missing
//     - handles all-nulls for CPU / memory (shows n/a everywhere)
//     - preserves bullet + section separators verbatim
//     - "done" and "idle" have empty metricsText

import { describe, expect, it, vi } from 'vitest'

import {
  formatMemoryMB,
  formatDiskRateMBs,
  formatPercent,
  buildRunStatusText
} from '../../../static/local-js/modules/kometa/_runStatusFormat.js'

// ---------------------------------------------------------------------
// formatMemoryMB
// ---------------------------------------------------------------------

describe('formatMemoryMB', () => {
  it('formats 0 as "0.0 MB"', () => {
    expect(formatMemoryMB(0)).toBe('0.0 MB')
  })

  it('formats sub-1024 as "N.N MB" with 1 decimal', () => {
    expect(formatMemoryMB(512.7)).toBe('512.7 MB')
    expect(formatMemoryMB(1)).toBe('1.0 MB')
  })

  it('formats >=1024 as GB with 1 decimal', () => {
    expect(formatMemoryMB(2048)).toBe('2.0 GB')
    expect(formatMemoryMB(1536)).toBe('1.5 GB')
  })

  it('formats exactly 1024 as "1.0 GB"', () => {
    expect(formatMemoryMB(1024)).toBe('1.0 GB')
  })

  it('returns "n/a" for non-finite values', () => {
    expect(formatMemoryMB(NaN)).toBe('n/a')
    expect(formatMemoryMB(Infinity)).toBe('n/a')
    expect(formatMemoryMB(-Infinity)).toBe('n/a')
  })

  it('returns "n/a" for non-numeric values', () => {
    expect(formatMemoryMB(undefined)).toBe('n/a')
    expect(formatMemoryMB(null)).toBe('n/a')
    expect(formatMemoryMB('512')).toBe('n/a')
  })
})

// ---------------------------------------------------------------------
// formatDiskRateMBs
// ---------------------------------------------------------------------

describe('formatDiskRateMBs', () => {
  it('formats sub-1024 as "N.NN MB/s" (2 decimals)', () => {
    expect(formatDiskRateMBs(12.345)).toBe('12.35 MB/s')
    expect(formatDiskRateMBs(0.5)).toBe('0.50 MB/s')
  })

  it('formats >=1024 as "N.NN GB/s"', () => {
    expect(formatDiskRateMBs(2048)).toBe('2.00 GB/s')
    expect(formatDiskRateMBs(1500)).toBe('1.46 GB/s')
  })

  it('formats 0 as "0.00 MB/s"', () => {
    expect(formatDiskRateMBs(0)).toBe('0.00 MB/s')
  })

  it('returns "n/a" for non-finite values', () => {
    expect(formatDiskRateMBs(NaN)).toBe('n/a')
    expect(formatDiskRateMBs(undefined)).toBe('n/a')
    expect(formatDiskRateMBs(null)).toBe('n/a')
  })

  it('uses 2-decimal precision (distinct from memory 1-decimal)', () => {
    // Explicit contrast with formatMemoryMB
    expect(formatDiskRateMBs(1.5)).toBe('1.50 MB/s')
    expect(formatMemoryMB(1.5)).toBe('1.5 MB')
  })
})

// ---------------------------------------------------------------------
// formatPercent
// ---------------------------------------------------------------------

describe('formatPercent', () => {
  it('formats 0 as "0.0%"', () => {
    expect(formatPercent(0)).toBe('0.0%')
  })

  it('formats normal floats with 1 decimal', () => {
    expect(formatPercent(45.67)).toBe('45.7%')
    expect(formatPercent(99.9)).toBe('99.9%')
  })

  it('echoes >100% without clamping (spillover allowed)', () => {
    // system_cpu_percent can exceed 100 on multi-core systems
    expect(formatPercent(250.5)).toBe('250.5%')
  })

  it('echoes negative values without clamping', () => {
    expect(formatPercent(-1.5)).toBe('-1.5%')
  })

  it('returns "n/a" for non-finite / non-numeric', () => {
    expect(formatPercent(NaN)).toBe('n/a')
    expect(formatPercent(undefined)).toBe('n/a')
    expect(formatPercent(null)).toBe('n/a')
    expect(formatPercent('50')).toBe('n/a')
  })
})

// ---------------------------------------------------------------------
// buildRunStatusText
// ---------------------------------------------------------------------

describe('buildRunStatusText', () => {
  const STARTED = vi.fn((iso) => `formatted(${iso})`)
  const ELAPSED = vi.fn((sec) => `${sec}s`)
  const opts = { formatStartedAt: STARTED, formatElapsed: ELAPSED }

  it('returns stage=idle for null data', () => {
    expect(buildRunStatusText(null, opts)).toEqual({
      timerText: '', metricsText: '', stage: 'idle'
    })
  })

  it('returns stage=idle for undefined data', () => {
    expect(buildRunStatusText(undefined, opts)).toEqual({
      timerText: '', metricsText: '', stage: 'idle'
    })
  })

  it('returns stage=idle for unknown status', () => {
    expect(buildRunStatusText({ status: 'starting' }, opts).stage).toBe('idle')
  })

  it('returns stage=done with completion text for status=done', () => {
    const result = buildRunStatusText({ status: 'done' }, opts)
    expect(result.stage).toBe('done')
    expect(result.timerText).toBe('Kometa run complete.')
    expect(result.metricsText).toBe('')
  })

  it('returns stage=scheduled_waiting with next scheduled run text', () => {
    const result = buildRunStatusText({
      status: 'scheduled_waiting',
      scheduled_run_local: '2026-09-12 05:00 AM',
      message: 'Kometa finished the current scheduled run and is waiting for the next scheduled time.'
    }, opts)
    expect(result.stage).toBe('scheduled_waiting')
    expect(result.timerText).toContain('Kometa scheduler is waiting.')
    expect(result.timerText).toContain('Next scheduled run: 2026-09-12 05:00 AM.')
    expect(result.metricsText).toContain('waiting for the next scheduled time')
  })

  it('returns stage=running for status=running', () => {
    const data = { status: 'running', started_at: 'T', elapsed_seconds: 30 }
    expect(buildRunStatusText(data, opts).stage).toBe('running')
  })

  it('injects formatStartedAt output into timer line', () => {
    const data = { status: 'running', started_at: 'ISO_STAMP', elapsed_seconds: 10 }
    expect(buildRunStatusText(data, opts).timerText).toContain('formatted(ISO_STAMP)')
  })

  it('injects formatElapsed output into timer line', () => {
    const data = { status: 'running', started_at: 'T', elapsed_seconds: 45 }
    expect(buildRunStatusText(data, opts).timerText).toContain('45s')
  })

  it('falls back to "n/a" when formatElapsed returns empty string', () => {
    const emptyElapsed = { formatStartedAt: STARTED, formatElapsed: () => '' }
    const data = { status: 'running', started_at: 'T', elapsed_seconds: 0 }
    expect(buildRunStatusText(data, emptyElapsed).timerText).toContain('Elapsed: n/a')
  })

  it('includes disk block when any disk metric is finite', () => {
    const data = {
      status: 'running',
      started_at: 'T',
      elapsed_seconds: 10,
      disk_read_rate_mb_s: 12.5,
      disk_write_rate_mb_s: 3.4
    }
    expect(buildRunStatusText(data, opts).metricsText).toContain('Disk:')
    expect(buildRunStatusText(data, opts).metricsText).toContain('12.50 MB/s')
  })

  it('omits disk block when all disk metrics are missing', () => {
    const data = { status: 'running', started_at: 'T', elapsed_seconds: 10 }
    expect(buildRunStatusText(data, opts).metricsText).not.toContain('Disk:')
  })

  it('shows n/a for missing CPU / memory / percent', () => {
    const data = { status: 'running', started_at: 'T', elapsed_seconds: 10 }
    const text = buildRunStatusText(data, opts).metricsText
    // n/a should appear multiple times (kometa cpu, mem, mem%, sys cpu, sys used, sys total, sys%)
    expect((text.match(/n\/a/g) || []).length).toBeGreaterThanOrEqual(6)
  })

  it('preserves bullet + pipe separators verbatim', () => {
    const data = {
      status: 'running',
      started_at: 'T',
      elapsed_seconds: 10,
      cpu_percent: 25.5,
      memory_rss_mb: 500,
      memory_percent: 12.3
    }
    const text = buildRunStatusText(data, opts).metricsText
    expect(text).toContain('•')  // section separator
    expect(text).toContain('|')  // major separator between Kometa/System
  })
})
