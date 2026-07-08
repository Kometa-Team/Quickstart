// Pure utility helpers extracted from 900-kometa.js as Step 1 of the
// classic-god-file split (see PR title / commit body for context).
//
// Everything in this file MUST be:
//   1. Referentially transparent OR only touching document-level DOM
//      APIs (no module-scoped state, no cached DOM refs)
//   2. Independently unit-testable via Vitest
//   3. Free of any imports from 900-kometa.js (this is a leaf module)
//
// If a helper needs KOMETA_STATUS, a cached DOM element, or a
// polling handle, it does NOT belong here — it belongs in the future
// _state.js or a feature-specific module. Keeping this file strictly
// pure means every future extraction can freely import from it without
// pulling in the whole god-file's transitive state.

// ---------------------------------------------------------------------
// String / formatting helpers
// ---------------------------------------------------------------------

export function quoteIfNeeded (s) {
  return /\s/.test(s) ? `"${s}"` : s
}

export function formatElapsed (ms) {
  const sec = Math.floor(ms / 1000)
  const mm = String(Math.floor(sec / 60)).padStart(2, '0')
  const ss = String(sec % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

export function computeYamlLineCount (text) {
  if (!text) return 0
  const normalized = String(text).replace(/\r\n/g, '\n')
  let count = normalized.split('\n').length
  if (normalized.endsWith('\n')) count -= 1
  return Math.max(0, count)
}

export function normalizeFontName (value) {
  return String(value || '').trim().replace(/_/g, ' ')
}

export function formatHeaderStyleLabel (value) {
  const text = normalizeFontName(value)
  if (!text) return 'Single line'
  return text.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase())
}

export function escapeHtml (value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * Turn plain text into HTML with any http(s) URLs converted to
 * anchor tags. `[https://...]` bracket-wrapped URLs are also
 * detected (the brackets are stripped from the display text).
 *
 * All non-URL text is escaped first, so this is safe to inject into
 * innerHTML.
 */
export function linkifyText (value) {
  if (!value) return ''
  const escaped = escapeHtml(value)
  const placeholders = []
  let counter = 0
  const withPlaceholders = escaped.replace(/\[(https?:\/\/[^\s\]]+)\]/g, (_match, url) => {
    const token = `__URLTOKEN${counter}__`
    placeholders.push({ token, url })
    counter += 1
    return token
  })
  let linked = withPlaceholders.replace(/(https?:\/\/[^\s<]+)/g, (url) => {
    return `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`
  })
  placeholders.forEach(({ token, url }) => {
    const anchor = `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`
    linked = linked.replace(token, anchor)
  })
  return linked
}

export function formatTimestampLocal (value) {
  if (!value) return 'n/a'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return String(value)
  return parsed.toLocaleString()
}

// ---------------------------------------------------------------------
// Numeric / time helpers
// ---------------------------------------------------------------------

export function clampPercent (value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return Math.max(0, Math.min(100, value))
}

/**
 * Format an integer number of seconds as e.g. "1h 5m 12s".
 * Non-finite values return an empty string.
 */
export function formatRunSeconds (seconds) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return ''
  const total = Math.max(0, Math.floor(seconds))
  const hrs = Math.floor(total / 3600)
  const mins = Math.floor((total % 3600) / 60)
  const secs = total % 60
  const parts = []
  if (hrs) parts.push(`${hrs}h`)
  if (mins || hrs) parts.push(`${mins}m`)
  parts.push(`${secs}s`)
  return parts.join(' ')
}

/**
 * Best-effort parse of a seconds value that might come in as a
 * number, a plain integer string, an HH:MM:SS clock string, or a
 * mixed "Nh Nm Ns" form. Returns null if nothing sensible matches.
 */
export function coerceRunSeconds (value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed) return null
  if (/^\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed)
  const clockMatch = trimmed.match(/^(\d+):(\d{2}):(\d{2})$/)
  if (clockMatch) {
    const hrs = Number(clockMatch[1])
    const mins = Number(clockMatch[2])
    const secs = Number(clockMatch[3])
    if ([hrs, mins, secs].every(num => Number.isFinite(num))) {
      return (hrs * 3600) + (mins * 60) + secs
    }
  }
  let total = 0
  let matched = false
  const hoursMatch = trimmed.match(/(\d+)\s*h\b/i)
  if (hoursMatch) {
    total += Number(hoursMatch[1]) * 3600
    matched = true
  }
  const minsMatch = trimmed.match(/(\d+)\s*m\b/i)
  if (minsMatch) {
    total += Number(minsMatch[1]) * 60
    matched = true
  }
  const secsMatch = trimmed.match(/(\d+)\s*s\b/i)
  if (secsMatch) {
    total += Number(secsMatch[1])
    matched = true
  }
  if (matched && Number.isFinite(total)) return total
  return null
}

/**
 * Return true when `timesStr` is a `|`-separated list of HH:MM
 * clock strings (24h, zero-padded). Empty or whitespace-only strings
 * return false.
 */
export function isValidTimesFormat (timesStr) {
  if (!timesStr.trim()) return false
  const times = timesStr.split('|')
  const timeRegex = /^([01]\d|2[0-3]):[0-5]\d$/
  return times.every(t => timeRegex.test(t.trim()))
}

/**
 * True when `time` (HH:MM) is >= rangeStart and < rangeEnd.
 * Half-open interval — matches the maintenance-window semantics
 * the original inline function used.
 */
export function isTimeWithinRange (time, rangeStart, rangeEnd) {
  const toMinutes = t => {
    const [h, m] = t.split(':').map(Number)
    return h * 60 + m
  }
  const timeMin = toMinutes(time)
  return timeMin >= toMinutes(rangeStart) && timeMin < toMinutes(rangeEnd)
}

// ---------------------------------------------------------------------
// Log helpers (pure text -> text / text -> counts)
// ---------------------------------------------------------------------

/**
 * Filter a multi-line log string, returning only lines matching
 * `filter`. If the filter is empty, the input is returned unchanged.
 * A filter wrapped in `/.../` is treated as a case-insensitive
 * regex; otherwise it's literal (with all regex metacharacters
 * escaped). Invalid regex silently falls back to returning the
 * unfiltered text.
 */
export function applyLogFilter (text, filter) {
  if (!filter) return text
  const trimmed = filter.trim()
  let re
  try {
    if (trimmed.length > 2 && trimmed.startsWith('/') && trimmed.endsWith('/')) {
      re = new RegExp(trimmed.slice(1, -1), 'i')
    } else {
      const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      re = new RegExp(escaped, 'i')
    }
  } catch {
    return text
  }
  return text.split('\n').filter(line => re.test(line)).join('\n')
}

/**
 * Count log lines by level marker.
 * Recognises Kometa's bracketed level tags: [DEBUG] [INFO] [WARNING]
 * [ERROR] [CRITICAL]. `cache` counts lines containing "from cache"
 * (case-insensitive) and `trace` counts lines containing "traceback".
 */
export function computeLogStats (text) {
  const stats = {
    cache: 0,
    debug: 0,
    info: 0,
    warning: 0,
    error: 0,
    critical: 0,
    trace: 0
  }
  if (!text) return stats
  const lines = text.split(/\r?\n/)
  lines.forEach(line => {
    if (!line) return
    if (line.toLowerCase().includes('from cache')) stats.cache += 1
    if (line.includes('[DEBUG]')) stats.debug += 1
    if (line.includes('[INFO]')) stats.info += 1
    if (line.includes('[WARNING]')) stats.warning += 1
    if (line.includes('[ERROR]')) stats.error += 1
    if (line.includes('[CRITICAL]')) stats.critical += 1
    if (line.toLowerCase().includes('traceback')) stats.trace += 1
  })
  return stats
}

// ---------------------------------------------------------------------
// Sparkline geometry (pure)
// ---------------------------------------------------------------------
//
// The stateful runSparkState buffer and the rendering functions that
// wire these into the DOM (renderRunSparklines, updateRunSparklines,
// resetRunSparklines) stay in the god file for now — they'll come out
// in a later PR alongside their DOM cache-refs. What lives HERE is
// purely the pixel-math + the shift-and-push buffer helper.

export const SPARKLINE_WIDTH = 180
export const SPARKLINE_HEIGHT = 48
export const SPARKLINE_PADDING = 2
export const SPARKLINE_MAX_POINTS = 40

/**
 * Push a sample onto a bounded series. `null`/`undefined` values
 * repeat the previous sample (or are dropped if the series is empty).
 * The series is trimmed to at most SPARKLINE_MAX_POINTS entries by
 * shifting from the front.
 *
 * Returns true if a sample was appended, false otherwise (empty
 * series + null value).
 */
export function pushSparkValue (series, value) {
  if (value == null) {
    if (!series.length) return false
    series.push(series[series.length - 1])
  } else {
    series.push(value)
  }
  if (series.length > SPARKLINE_MAX_POINTS) series.shift()
  return true
}

/**
 * Convert a 0-100 series into an SVG polyline `points` attribute
 * string within the sparkline's fixed viewport.
 * Empty series -> empty string (safe to assign to points).
 */
export function buildSparklinePoints (series) {
  if (!series.length) return ''
  const width = SPARKLINE_WIDTH - SPARKLINE_PADDING * 2
  const height = SPARKLINE_HEIGHT - SPARKLINE_PADDING * 2
  const step = series.length > 1 ? width / (series.length - 1) : 0
  return series.map((value, idx) => {
    const x = SPARKLINE_PADDING + (idx * step)
    const y = SPARKLINE_PADDING + (height - (height * (value / 100)))
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

/**
 * Same as buildSparklinePoints but for a series with an arbitrary
 * max (e.g. I/O throughput where percent doesn't apply). Values are
 * normalized to 0-100 before delegating.
 */
export function buildSparklinePointsScaled (series, maxValue) {
  if (!series.length) return ''
  const safeMax = typeof maxValue === 'number' && Number.isFinite(maxValue) && maxValue > 0 ? maxValue : 1
  const normalized = series.map(value => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return 0
    return Math.max(0, Math.min(100, (value / safeMax) * 100))
  })
  return buildSparklinePoints(normalized)
}

// ---------------------------------------------------------------------
// Clipboard (uses DOM but no module-scoped state)
// ---------------------------------------------------------------------

/**
 * Copy the given text to the clipboard using navigator.clipboard when
 * available, falling back to a hidden textarea + execCommand('copy')
 * for older browsers / non-secure contexts.
 *
 * Returns a Promise that resolves on success and rejects with an
 * Error on failure (empty input, permission denied, or copy failure).
 */
export function copyTextToClipboard (text) {
  if (!text) return Promise.reject(new Error('Empty text'))
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text)
  }
  return new Promise((resolve, reject) => {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'absolute'
    textarea.style.left = '-9999px'
    document.body.appendChild(textarea)
    textarea.select()
    try {
      const success = document.execCommand('copy')
      document.body.removeChild(textarea)
      if (success) resolve()
      else reject(new Error('Copy failed'))
    } catch (err) {
      document.body.removeChild(textarea)
      reject(err)
    }
  })
}

// ---------------------------------------------------------------------
// DOM dataset flag helpers
// ---------------------------------------------------------------------
//
// Each wizard step page embeds its "has this been validated?" flag as
// a data attribute on a hidden <meta>-ish element. Server-rendered
// markup writes the initial value; JS reads it during gate evaluation
// and re-writes it after successful in-page validation.
//
// The dual-source read (`el.dataset[datasetKey] || el.getAttribute(...)`)
// exists because older templates set data-plex-valid via kebab-case
// attribute directly, while newer templates go through dataset. The
// pair of writes on set keeps both in sync so subsequent reads via
// either path stay consistent.
//
// These are pure DOM I/O with no module-scoped state, so they belong
// in _util.js rather than a state-holding module.

/**
 * Read a boolean flag stored on an element as both a data-attribute
 * and (redundantly) as a dataset property.
 *
 * @param {string} id          The element's id.
 * @param {string} datasetKey  Camel-case dataset key (e.g. 'plexValid').
 * @param {string} attrKey     Kebab-case attribute stem (e.g. 'plex-valid';
 *                             the function prepends 'data-').
 * @returns {boolean}          True iff the value string is 'true'
 *                             (case-insensitive). Missing element or
 *                             empty value returns false.
 */
export function readMetaFlag (id, datasetKey, attrKey) {
  const el = document.getElementById(id)
  if (!el) return false
  const raw = (el.dataset && el.dataset[datasetKey]) || el.getAttribute(`data-${attrKey}`) || ''
  return String(raw).toLowerCase() === 'true'
}

/**
 * Write a boolean flag to an element. Serializes as the Python-flavored
 * 'True'/'False' string (matching what Flask/Jinja renders) so that
 * subsequent server-side reads see identical values.
 *
 * @param {string}  id          The element's id.
 * @param {string}  datasetKey  Camel-case dataset key.
 * @param {string}  attrKey     Kebab-case attribute stem.
 * @param {boolean} value       Truthy => 'True', falsy => 'False'.
 */
export function setMetaFlag (id, datasetKey, attrKey, value) {
  const el = document.getElementById(id)
  if (!el) return
  const serialized = value ? 'True' : 'False'
  if (el.dataset) el.dataset[datasetKey] = serialized
  el.setAttribute(`data-${attrKey}`, serialized)
}
