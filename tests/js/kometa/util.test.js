// Tests for static/local-js/modules/kometa/_util.js
//
// All functions in the module under test are pure or DOM-only (no
// module-scoped state), so tests are dense and unit-shaped.
//
// Coverage strategy: exhaustive on the tricky ones (linkifyText's
// escape-then-linkify order, coerceRunSeconds's four accepted forms,
// applyLogFilter's literal-vs-regex dispatch, buildSparklinePoints'
// pixel math) and representative on the trivial ones.

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  quoteIfNeeded,
  formatElapsed,
  computeYamlLineCount,
  normalizeFontName,
  formatHeaderStyleLabel,
  escapeHtml,
  linkifyText,
  formatTimestampLocal,
  clampPercent,
  formatRunSeconds,
  coerceRunSeconds,
  isValidTimesFormat,
  isTimeWithinRange,
  applyLogFilter,
  computeLogStats,
  filterLogLines,
  findYamlMajorSections,
  buildLineNumberText,
  buildLineNumberedText,
  getLogLineLevel,
  renderLogRows,
  SPARKLINE_WIDTH,
  SPARKLINE_HEIGHT,
  SPARKLINE_PADDING,
  SPARKLINE_MAX_POINTS,
  pushSparkValue,
  buildSparklinePoints,
  buildSparklinePointsScaled,
  copyTextToClipboard,
  isRunCommandValid
} from '../../../static/local-js/modules/kometa/_util.js'

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------
// String / formatting helpers
// ---------------------------------------------------------------------

describe('quoteIfNeeded', () => {
  it('wraps whitespace-containing strings in double quotes', () => {
    expect(quoteIfNeeded('has space')).toBe('"has space"')
    expect(quoteIfNeeded('a\tb')).toBe('"a\tb"')
    expect(quoteIfNeeded('a\nb')).toBe('"a\nb"')
  })
  it('returns whitespace-free strings unchanged', () => {
    expect(quoteIfNeeded('nowhite')).toBe('nowhite')
    expect(quoteIfNeeded('/some/path/to/kometa')).toBe('/some/path/to/kometa')
  })
  it('returns empty string unchanged (no whitespace present)', () => {
    expect(quoteIfNeeded('')).toBe('')
  })
})

describe('formatElapsed', () => {
  it('formats sub-minute as MM:SS with zero-padded minutes', () => {
    expect(formatElapsed(5000)).toBe('00:05')
    expect(formatElapsed(59999)).toBe('00:59')
  })
  it('formats minute-plus correctly', () => {
    expect(formatElapsed(60000)).toBe('01:00')
    expect(formatElapsed(125000)).toBe('02:05')
  })
  it('handles multi-hour without overflow to hours (stays MM:SS)', () => {
    expect(formatElapsed(3600000)).toBe('60:00')
    expect(formatElapsed(3665000)).toBe('61:05')
  })
  it('handles 0ms', () => {
    expect(formatElapsed(0)).toBe('00:00')
  })
})

describe('computeYamlLineCount', () => {
  it('returns 0 for empty or falsy input', () => {
    expect(computeYamlLineCount('')).toBe(0)
    expect(computeYamlLineCount(null)).toBe(0)
    expect(computeYamlLineCount(undefined)).toBe(0)
  })
  it('counts a single non-terminated line as 1', () => {
    expect(computeYamlLineCount('one line')).toBe(1)
  })
  it('counts newline-separated lines', () => {
    expect(computeYamlLineCount('a\nb\nc')).toBe(3)
  })
  it('drops the trailing empty line when input ends with \\n', () => {
    expect(computeYamlLineCount('a\nb\n')).toBe(2)
  })
  it('normalizes \\r\\n to \\n before counting', () => {
    expect(computeYamlLineCount('a\r\nb\r\nc')).toBe(3)
    expect(computeYamlLineCount('a\r\nb\r\n')).toBe(2)
  })
})

describe('normalizeFontName', () => {
  it('trims whitespace and replaces underscores with spaces', () => {
    expect(normalizeFontName('  hello_world  ')).toBe('hello world')
  })
  it('handles null/undefined by returning empty string', () => {
    expect(normalizeFontName(null)).toBe('')
    expect(normalizeFontName(undefined)).toBe('')
  })
  it('leaves already-clean names alone', () => {
    expect(normalizeFontName('roboto')).toBe('roboto')
  })
})

describe('formatHeaderStyleLabel', () => {
  it('returns "Single line" for empty input', () => {
    expect(formatHeaderStyleLabel('')).toBe('Single line')
    expect(formatHeaderStyleLabel(null)).toBe('Single line')
  })
  it('title-cases the normalized name', () => {
    expect(formatHeaderStyleLabel('open_sans')).toBe('Open Sans')
    expect(formatHeaderStyleLabel('roboto_condensed')).toBe('Roboto Condensed')
  })
})

describe('escapeHtml', () => {
  it('escapes the five standard HTML entities', () => {
    expect(escapeHtml('<a href="x&y">it\'s</a>'))
      .toBe('&lt;a href=&quot;x&amp;y&quot;&gt;it&#39;s&lt;/a&gt;')
  })
  it('returns empty string for falsy input', () => {
    expect(escapeHtml(null)).toBe('')
    expect(escapeHtml(undefined)).toBe('')
    expect(escapeHtml('')).toBe('')
  })
  it('coerces non-string values to string first', () => {
    expect(escapeHtml(42)).toBe('42')
  })
})

describe('linkifyText', () => {
  it('returns empty string for falsy input', () => {
    expect(linkifyText('')).toBe('')
    expect(linkifyText(null)).toBe('')
  })
  it('escapes text and linkifies http URLs', () => {
    const out = linkifyText('see https://example.com/x for more')
    expect(out).toContain('<a href="https://example.com/x"')
    expect(out).toContain('target="_blank"')
    expect(out).toContain('rel="noopener noreferrer"')
  })
  it('handles bracket-wrapped URLs (removes the brackets from anchor)', () => {
    const out = linkifyText('go to [https://example.com] now')
    expect(out).toContain('<a href="https://example.com"')
    // The literal `[` and `]` do NOT appear around the anchor.
    expect(out).not.toContain('[<a')
    expect(out).not.toContain('a>]')
  })
  it('escapes untrusted markup BEFORE linkifying (no HTML injection)', () => {
    const out = linkifyText('<script>alert(1)</script> https://x.example.com')
    // Script tag must be escaped:
    expect(out).toContain('&lt;script&gt;')
    // The URL must still be linkified:
    expect(out).toContain('<a href="https://x.example.com"')
  })
  it('handles multiple URLs in one input', () => {
    const out = linkifyText('a https://x.com and https://y.com')
    const anchorCount = (out.match(/<a href="/g) || []).length
    expect(anchorCount).toBe(2)
  })
})

describe('formatTimestampLocal', () => {
  it('returns "n/a" for null/undefined/empty', () => {
    expect(formatTimestampLocal(null)).toBe('n/a')
    expect(formatTimestampLocal('')).toBe('n/a')
  })
  it('returns the original string when parsing fails', () => {
    expect(formatTimestampLocal('not-a-date')).toBe('not-a-date')
  })
  it('formats a valid ISO timestamp using toLocaleString', () => {
    const iso = '2026-06-30T12:34:56.000Z'
    const expected = new Date(iso).toLocaleString()
    expect(formatTimestampLocal(iso)).toBe(expected)
  })
})

// ---------------------------------------------------------------------
// Numeric / time helpers
// ---------------------------------------------------------------------

describe('clampPercent', () => {
  it('clamps to [0, 100]', () => {
    expect(clampPercent(-5)).toBe(0)
    expect(clampPercent(0)).toBe(0)
    expect(clampPercent(42.5)).toBe(42.5)
    expect(clampPercent(100)).toBe(100)
    expect(clampPercent(500)).toBe(100)
  })
  it('returns null for non-finite or non-number inputs', () => {
    expect(clampPercent(null)).toBeNull()
    expect(clampPercent(undefined)).toBeNull()
    expect(clampPercent('42')).toBeNull()
    expect(clampPercent(NaN)).toBeNull()
    expect(clampPercent(Infinity)).toBeNull()
  })
})

describe('formatRunSeconds', () => {
  it('returns empty string for non-finite / non-number', () => {
    expect(formatRunSeconds(null)).toBe('')
    expect(formatRunSeconds(NaN)).toBe('')
    expect(formatRunSeconds('12')).toBe('')
    expect(formatRunSeconds(Infinity)).toBe('')
  })
  it('formats seconds-only', () => {
    expect(formatRunSeconds(0)).toBe('0s')
    expect(formatRunSeconds(45)).toBe('45s')
    expect(formatRunSeconds(59)).toBe('59s')
  })
  it('formats minutes and seconds', () => {
    expect(formatRunSeconds(60)).toBe('1m 0s')
    expect(formatRunSeconds(125)).toBe('2m 5s')
  })
  it('formats hours/minutes/seconds', () => {
    expect(formatRunSeconds(3661)).toBe('1h 1m 1s')
    expect(formatRunSeconds(7200)).toBe('2h 0m 0s')
  })
  it('floors and clamps negatives to zero', () => {
    expect(formatRunSeconds(-5)).toBe('0s')
    expect(formatRunSeconds(1.9)).toBe('1s')
  })
})

describe('coerceRunSeconds', () => {
  it('passes through finite numbers', () => {
    expect(coerceRunSeconds(42)).toBe(42)
    expect(coerceRunSeconds(3.14)).toBe(3.14)
  })
  it('rejects non-finite numbers', () => {
    expect(coerceRunSeconds(NaN)).toBeNull()
    expect(coerceRunSeconds(Infinity)).toBeNull()
  })
  it('returns null for non-string non-number inputs', () => {
    expect(coerceRunSeconds(null)).toBeNull()
    expect(coerceRunSeconds(undefined)).toBeNull()
    expect(coerceRunSeconds({})).toBeNull()
  })
  it('returns null for empty / whitespace strings', () => {
    expect(coerceRunSeconds('')).toBeNull()
    expect(coerceRunSeconds('   ')).toBeNull()
  })
  it('parses plain integer strings', () => {
    expect(coerceRunSeconds('42')).toBe(42)
    expect(coerceRunSeconds('3.14')).toBe(3.14)
  })
  it('parses HH:MM:SS clock strings', () => {
    expect(coerceRunSeconds('01:02:03')).toBe(3723)
    expect(coerceRunSeconds('0:00:45')).toBe(45)
    expect(coerceRunSeconds('10:00:00')).toBe(36000)
  })
  it('parses "1h 2m 3s" mixed forms', () => {
    expect(coerceRunSeconds('1h 2m 3s')).toBe(3723)
    expect(coerceRunSeconds('5m')).toBe(300)
    expect(coerceRunSeconds('45s')).toBe(45)
    expect(coerceRunSeconds('2h')).toBe(7200)
  })
  it('is case-insensitive on the h/m/s suffixes', () => {
    expect(coerceRunSeconds('1H 2M 3S')).toBe(3723)
  })
  it('returns null for strings with no recognizable form', () => {
    expect(coerceRunSeconds('yesterday')).toBeNull()
    expect(coerceRunSeconds('12:34')).toBeNull()  // MM:SS is NOT recognized
  })
})

describe('isValidTimesFormat', () => {
  it('accepts a single HH:MM (24h, zero-padded)', () => {
    expect(isValidTimesFormat('05:00')).toBe(true)
    expect(isValidTimesFormat('23:59')).toBe(true)
  })
  it('accepts pipe-delimited multi-time', () => {
    expect(isValidTimesFormat('05:00|17:30')).toBe(true)
    expect(isValidTimesFormat('05:00 | 17:30')).toBe(true)  // whitespace-trimmed
  })
  it('rejects times with hour out of range', () => {
    expect(isValidTimesFormat('24:00')).toBe(false)
    expect(isValidTimesFormat('99:00')).toBe(false)
  })
  it('rejects times with minute out of range', () => {
    expect(isValidTimesFormat('12:60')).toBe(false)
  })
  it('rejects non-padded hours', () => {
    expect(isValidTimesFormat('5:00')).toBe(false)
  })
  it('rejects empty or whitespace-only', () => {
    expect(isValidTimesFormat('')).toBe(false)
    expect(isValidTimesFormat('   ')).toBe(false)
  })
  it('rejects if any part is invalid', () => {
    expect(isValidTimesFormat('05:00|garbage')).toBe(false)
  })
})

describe('isTimeWithinRange', () => {
  it('returns true when time is inside a normal range', () => {
    expect(isTimeWithinRange('03:00', '02:00', '04:00')).toBe(true)
  })
  it('returns true at the start of the range (inclusive)', () => {
    expect(isTimeWithinRange('02:00', '02:00', '04:00')).toBe(true)
  })
  it('returns false at the end of the range (exclusive)', () => {
    expect(isTimeWithinRange('04:00', '02:00', '04:00')).toBe(false)
  })
  it('returns false when time is before the range', () => {
    expect(isTimeWithinRange('01:59', '02:00', '04:00')).toBe(false)
  })
  it('returns false when time is after the range', () => {
    expect(isTimeWithinRange('04:01', '02:00', '04:00')).toBe(false)
  })
})

// ---------------------------------------------------------------------
// Log helpers
// ---------------------------------------------------------------------

describe('applyLogFilter', () => {
  it('returns text unchanged when filter is empty', () => {
    expect(applyLogFilter('a\nb\nc', '')).toBe('a\nb\nc')
    expect(applyLogFilter('a\nb\nc', null)).toBe('a\nb\nc')
  })
  it('applies a literal case-insensitive filter', () => {
    expect(applyLogFilter('AAA\nbbb\nCcC', 'a')).toBe('AAA')
  })
  it('escapes regex metacharacters in literal filters', () => {
    // Without escaping, `.` would match any character. With escaping,
    // it should only match literal periods.
    const log = 'foo.bar\nfoo_bar'
    expect(applyLogFilter(log, 'foo.bar')).toBe('foo.bar')
  })
  it('treats bracketed level shortcuts as named filters, not raw regex character classes', () => {
    const log = '[ERROR] actual failure\nordinary row\nrecipe row'
    expect(applyLogFilter(log, '[ERROR]')).toBe('[ERROR] actual failure')
  })
  it('matches exact warning and critical level markers', () => {
    const log = '[WARNING] marked warning\nWARNING plain text\n[CRITICAL] marked critical\n[CRIT] short text'
    expect(applyLogFilter(log, 'warning')).toBe('[WARNING] marked warning')
    expect(applyLogFilter(log, 'critical')).toBe('[CRITICAL] marked critical')
  })
  it('treats /.../ as a case-insensitive regex', () => {
    const log = 'AAA\nbbb\nCcC'
    expect(applyLogFilter(log, '/a|b/')).toBe('AAA\nbbb')
  })
  it('falls back to original text on invalid regex', () => {
    const log = 'AAA\nbbb'
    expect(applyLogFilter(log, '/[/')).toBe('AAA\nbbb')
  })
  it('returns empty string when no lines match', () => {
    expect(applyLogFilter('AAA\nbbb', 'zzz')).toBe('')
  })
})

describe('filterLogLines', () => {
  it('keeps source line numbers when filtering a tailed log', () => {
    const result = filterLogLines('[INFO] one\n[ERROR] two\n[WARNING] three', 'warning', { startLine: 98 })
    expect(result.text).toBe('[WARNING] three')
    expect(result.lineNumbers).toEqual([100])
  })
})

describe('computeLogStats', () => {
  it('returns all zeros for empty/falsy input', () => {
    const stats = computeLogStats('')
    expect(stats).toEqual({
      cache: 0, debug: 0, info: 0, warning: 0, error: 0, critical: 0, trace: 0
    })
  })
  it('counts bracketed level tags', () => {
    const log = '[DEBUG] a\n[INFO] b\n[INFO] c\n[WARNING] d\n[ERROR] e\n[CRITICAL] f'
    const stats = computeLogStats(log)
    expect(stats.debug).toBe(1)
    expect(stats.info).toBe(2)
    expect(stats.warning).toBe(1)
    expect(stats.error).toBe(1)
    expect(stats.critical).toBe(1)
  })
  it('counts "from cache" (case-insensitive) as cache hits', () => {
    const log = 'loaded FROM CACHE\nSomething from cache\nnope'
    expect(computeLogStats(log).cache).toBe(2)
  })
  it('counts exact trace level markers', () => {
    const log = '[TRACE] enabled\nTraceback (most recent call last):\ntrace detail'
    expect(computeLogStats(log).trace).toBe(1)
  })
  it('handles CRLF line endings', () => {
    const log = '[DEBUG] a\r\n[INFO] b\r\n'
    const stats = computeLogStats(log)
    expect(stats.debug).toBe(1)
    expect(stats.info).toBe(1)
  })
  it('skips empty lines', () => {
    const log = '\n\n[INFO] one\n\n'
    expect(computeLogStats(log).info).toBe(1)
  })
  it('does not count unbracketed and short log-level-looking text as level markers', () => {
    const log = 'ERROR plain\n[WARN] short\n[CRIT] short\ntrace detail\ncached lookup'
    const stats = computeLogStats(log)
    expect(stats.error).toBe(0)
    expect(stats.warning).toBe(0)
    expect(stats.critical).toBe(0)
    expect(stats.trace).toBe(0)
    expect(stats.cache).toBe(0)
  })
})

describe('getLogLineLevel', () => {
  it('returns exact marker severity classes', () => {
    expect(getLogLineLevel('[CRITICAL] no api key')).toBe('critical')
    expect(getLogLineLevel('[ERROR] failed')).toBe('error')
    expect(getLogLineLevel('[WARNING] check config')).toBe('warning')
    expect(getLogLineLevel('[TRACE] detail')).toBe('trace')
    expect(getLogLineLevel('loaded from cache')).toBe('cache')
  })
  it('ignores loose or shortened marker text', () => {
    expect(getLogLineLevel('WARNING plain text')).toBe('')
    expect(getLogLineLevel('[WARN] short marker')).toBe('')
    expect(getLogLineLevel('[CRIT] short marker')).toBe('')
    expect(getLogLineLevel('trace detail')).toBe('')
  })
})

describe('findYamlMajorSections', () => {
  it('finds generated divider comment sections', () => {
    const yaml = [
      '#==================== Libraries ====================#',
      'libraries:',
      '  Movies:',
      '',
      '#==================== Settings ====================#',
      'settings:',
      '  cache: true'
    ].join('\n')
    expect(findYamlMajorSections(yaml)).toEqual([
      { line: 1, label: 'Libraries' },
      { line: 5, label: 'Settings' }
    ])
  })

  it('uses top-level keys when no nearby divider is present', () => {
    const yaml = [
      'plex:',
      '  url: http://example.test',
      'tmdb:',
      '  apikey: redacted'
    ].join('\n')
    expect(findYamlMajorSections(yaml)).toEqual([
      { line: 1, label: 'plex:' },
      { line: 3, label: 'tmdb:' }
    ])
  })
})

describe('buildLineNumberText', () => {
  it('builds padded line numbers from text and a start line', () => {
    expect(buildLineNumberText('a\nb\nc', { startLine: 98 })).toBe(' 98\n 99\n100')
  })
  it('can render sparse source line numbers from a filtered result', () => {
    expect(buildLineNumberText('a\nb', { lineNumbers: [7, 120] })).toBe('  7\n120')
  })
})

describe('buildLineNumberedText', () => {
  it('prefixes line numbers inside the log text', () => {
    expect(buildLineNumberedText('alpha\nbeta', { startLine: 9 })).toBe(' 9 | alpha\n10 | beta')
  })
  it('uses sparse source line numbers from filtered results', () => {
    expect(buildLineNumberedText('[ERROR] a\n[ERROR] b', { lineNumbers: [12, 48] })).toBe('12 | [ERROR] a\n48 | [ERROR] b')
  })
})

describe('renderLogRows', () => {
  it('renders source-numbered log rows without prefixing the log content', () => {
    const container = document.createElement('div')
    renderLogRows(container, '[INFO] one\n[WARNING] two', { startLine: 41 })

    const rows = container.querySelectorAll('.qs-log-line')
    expect(rows).toHaveLength(2)
    expect(rows[0].dataset.line).toBe('41')
    expect(rows[0].querySelector('.qs-log-line-number').dataset.line).toBe('41')
    expect(rows[0].querySelector('.qs-log-line-number').textContent).toBe('')
    expect(rows[0].querySelector('.qs-log-line-content').textContent).toBe('[INFO] one')
    expect(rows[1].dataset.line).toBe('42')
    expect(rows[1].classList.contains('qs-log-line--warning')).toBe(true)
    expect(rows[1].querySelector('.qs-log-line-content').textContent).toBe('[WARNING] two')
  })

  it('renders sparse filtered source line numbers', () => {
    const container = document.createElement('div')
    renderLogRows(container, '[ERROR] one\n[ERROR] two', { lineNumbers: [12, 48] })

    expect(Array.from(container.querySelectorAll('.qs-log-line-number')).map(el => el.dataset.line))
      .toEqual(['12', '48'])
    expect(container.textContent).toBe('[ERROR] one[ERROR] two')
  })

  it('can render numbered config rows without log-level highlighting', () => {
    const container = document.createElement('div')
    renderLogRows(container, '[ERROR] allowed yaml value', { highlightLevels: false })

    const row = container.querySelector('.qs-log-line')
    expect(row.classList.contains('qs-log-line--error')).toBe(false)
    expect(row.querySelector('.qs-log-line-content').textContent).toBe('[ERROR] allowed yaml value')
  })
})

// ---------------------------------------------------------------------
// Sparkline helpers
// ---------------------------------------------------------------------

describe('SPARKLINE constants', () => {
  it('exports the expected fixed values', () => {
    expect(SPARKLINE_WIDTH).toBe(180)
    expect(SPARKLINE_HEIGHT).toBe(48)
    expect(SPARKLINE_PADDING).toBe(2)
    expect(SPARKLINE_MAX_POINTS).toBe(40)
  })
})

describe('pushSparkValue', () => {
  it('appends a value to the series', () => {
    const series = [10, 20]
    pushSparkValue(series, 30)
    expect(series).toEqual([10, 20, 30])
  })
  it('returns true when a value was appended', () => {
    expect(pushSparkValue([10], 20)).toBe(true)
  })
  it('repeats the previous value when passed null/undefined', () => {
    const series = [10, 20]
    pushSparkValue(series, null)
    expect(series).toEqual([10, 20, 20])
    pushSparkValue(series, undefined)
    expect(series).toEqual([10, 20, 20, 20])
  })
  it('does NOT push and returns false when series is empty AND value is null', () => {
    const series = []
    expect(pushSparkValue(series, null)).toBe(false)
    expect(series).toEqual([])
  })
  it('trims to at most SPARKLINE_MAX_POINTS by shifting from front', () => {
    const series = Array.from({ length: SPARKLINE_MAX_POINTS }, (_, i) => i)
    pushSparkValue(series, 999)
    expect(series).toHaveLength(SPARKLINE_MAX_POINTS)
    expect(series[series.length - 1]).toBe(999)
    expect(series[0]).toBe(1)  // 0 was shifted off
  })
})

describe('buildSparklinePoints', () => {
  it('returns empty string for empty series', () => {
    expect(buildSparklinePoints([])).toBe('')
  })
  it('renders a single point in the middle of the y-axis for value 50', () => {
    // With value=50 and step=0 (only one point), x = SPARKLINE_PADDING,
    // y = SPARKLINE_PADDING + (H - H*0.5) where H = SPARKLINE_HEIGHT-2*PAD
    const height = SPARKLINE_HEIGHT - SPARKLINE_PADDING * 2
    const expectedY = SPARKLINE_PADDING + (height - (height * 0.5))
    expect(buildSparklinePoints([50])).toBe(
      `${SPARKLINE_PADDING.toFixed(1)},${expectedY.toFixed(1)}`
    )
  })
  it('places value=0 at the bottom of the plot area', () => {
    const height = SPARKLINE_HEIGHT - SPARKLINE_PADDING * 2
    const expectedY = SPARKLINE_PADDING + height
    expect(buildSparklinePoints([0])).toContain(`,${expectedY.toFixed(1)}`)
  })
  it('places value=100 at the top of the plot area', () => {
    expect(buildSparklinePoints([100])).toContain(`,${SPARKLINE_PADDING.toFixed(1)}`)
  })
  it('spaces multi-point series evenly across the plot width', () => {
    const out = buildSparklinePoints([100, 100, 100])
    const points = out.split(' ')
    expect(points).toHaveLength(3)
    // With 3 points, step = (W - 2*PAD) / 2. First x = PAD, last x = W - PAD.
    const firstX = parseFloat(points[0].split(',')[0])
    const lastX = parseFloat(points[points.length - 1].split(',')[0])
    expect(firstX).toBeCloseTo(SPARKLINE_PADDING, 1)
    expect(lastX).toBeCloseTo(SPARKLINE_WIDTH - SPARKLINE_PADDING, 1)
  })
})

describe('buildSparklinePointsScaled', () => {
  it('returns empty string for empty series', () => {
    expect(buildSparklinePointsScaled([], 100)).toBe('')
  })
  it('scales values proportionally to maxValue', () => {
    // [50] with maxValue=100 should look identical to [50] in buildSparklinePoints
    expect(buildSparklinePointsScaled([50], 100))
      .toBe(buildSparklinePoints([50]))
  })
  it('normalizes to 0-100 range even for maxValue > 100', () => {
    // [500] with maxValue=1000 should look like [50]
    expect(buildSparklinePointsScaled([500], 1000))
      .toBe(buildSparklinePoints([50]))
  })
  it('uses maxValue=1 as a safe fallback when maxValue is 0/negative/non-finite', () => {
    // With safeMax=1, [0.5] should render as (0.5/1)*100 = 50%
    expect(buildSparklinePointsScaled([0.5], 0))
      .toBe(buildSparklinePoints([50]))
    expect(buildSparklinePointsScaled([0.5], -100))
      .toBe(buildSparklinePoints([50]))
    expect(buildSparklinePointsScaled([0.5], NaN))
      .toBe(buildSparklinePoints([50]))
  })
  it('clamps values outside [0, safeMax] into [0, 100] after normalization', () => {
    // 200 with maxValue=100 -> 200%, clamped to 100
    expect(buildSparklinePointsScaled([200], 100))
      .toBe(buildSparklinePoints([100]))
    // -10 with maxValue=100 -> -10%, clamped to 0
    expect(buildSparklinePointsScaled([-10], 100))
      .toBe(buildSparklinePoints([0]))
  })
  it('treats non-finite entries as 0', () => {
    expect(buildSparklinePointsScaled([NaN], 100))
      .toBe(buildSparklinePoints([0]))
    expect(buildSparklinePointsScaled([Infinity], 100))
      .toBe(buildSparklinePoints([0]))
  })
})

// ---------------------------------------------------------------------
// Clipboard
// ---------------------------------------------------------------------

describe('copyTextToClipboard', () => {
  it('rejects with an Error for empty text', async () => {
    await expect(copyTextToClipboard('')).rejects.toThrow('Empty text')
    await expect(copyTextToClipboard(null)).rejects.toThrow('Empty text')
    await expect(copyTextToClipboard(undefined)).rejects.toThrow('Empty text')
  })

  it('uses navigator.clipboard.writeText when available', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    // Install a fake clipboard for this test
    const originalClipboard = navigator.clipboard
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText }
    })
    try {
      await copyTextToClipboard('hello')
      expect(writeText).toHaveBeenCalledWith('hello')
    } finally {
      // Restore
      if (originalClipboard !== undefined) {
        Object.defineProperty(navigator, 'clipboard', {
          configurable: true,
          value: originalClipboard
        })
      } else {
        delete navigator.clipboard
      }
    }
  })

  it('falls back to hidden textarea + execCommand("copy") when clipboard API is missing', async () => {
    const originalClipboard = navigator.clipboard
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: undefined
    })
    // execCommand is not a real thing in jsdom; install as a plain property.
    const execFn = vi.fn().mockReturnValue(true)
    document.execCommand = execFn
    try {
      await copyTextToClipboard('hi')
      expect(execFn).toHaveBeenCalledWith('copy')
    } finally {
      delete document.execCommand
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: originalClipboard
      })
    }
  })

  it('rejects when the execCommand fallback returns false', async () => {
    const originalClipboard = navigator.clipboard
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: undefined
    })
    document.execCommand = vi.fn().mockReturnValue(false)
    try {
      await expect(copyTextToClipboard('hi')).rejects.toThrow('Copy failed')
    } finally {
      delete document.execCommand
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: originalClipboard
      })
    }
  })
})

// ---------------------------------------------------------------------
// isRunCommandValid (moved from _runCommand.js in PR #1572)
// ---------------------------------------------------------------------
//
// A "valid" run command has non-empty text and doesn't start with the
// '??' placeholder sentinel that server-side rendering uses when
// required config paths are still missing. All four combinations of
// (present/missing element) x (valid/invalid content) are covered.

describe('isRunCommandValid', () => {
  it('is true when the run-command-output has real content', () => {
    document.body.innerHTML = '<div id="run-command-output">python kometa.py --config config.yml</div>'
    expect(isRunCommandValid()).toBe(true)
  })

  it("is false when the content starts with '??' placeholder", () => {
    document.body.innerHTML = '<div id="run-command-output">?? no kometa root ??</div>'
    expect(isRunCommandValid()).toBe(false)
  })

  it('is false when the content is empty/whitespace', () => {
    document.body.innerHTML = '<div id="run-command-output">   </div>'
    expect(isRunCommandValid()).toBe(false)
  })

  it('is false when the element is missing', () => {
    document.body.innerHTML = ''
    expect(isRunCommandValid()).toBe(false)
  })
})
