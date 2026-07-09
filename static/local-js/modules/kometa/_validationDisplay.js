// Kometa validation-display helpers: pure formatters + a single
// DOM-mutator (updateValidationRow) shared between the initial
// page-load pass and the qs:bulk-validation-complete event handler.
//
// PURE FUNCTIONS (no DOM access, safe to test in isolation):
//
//   formatLocalTimestamp(date)
//     Returns a fixed "YYYY-MM-DD HH:MM:SS" string using LOCAL time.
//     Not toISOString (that's UTC); not toLocaleString (that's locale-
//     dependent and would break snapshot tests). The wizard rows show
//     this string as-is next to each validated service.
//
//   formatRelativeTimestamp(date, now)
//     Returns "Just now" / "5m ago" / "2h 15m ago" / etc. Bounded
//     lookup with cascading units (seconds -> minutes -> hours ->
//     days -> weeks -> months -> years). Handles negative diffs by
//     clamping to 0 (defensive against clock skew).
//
//   formatValidationResult(status, reason, details)
//     Combines a status ("validated" / "failed" / "skipped") with an
//     optional reason code from VALIDATION_REASON_LABELS and optional
//     details string or array. Empty status returns ''.
//
// CONSTANTS:
//
//   VALIDATION_REASON_LABELS
//     Maps validation reason codes ("missing_credentials",
//     "no_libraries", etc.) to display labels. Any code not in the
//     map falls through to a snake_case -> spaced form.
//
// SIDE-EFFECTFUL:
//
//   updateValidationRow(key, result)
//     Mutates the DOM row matching [data-validation-key="{key}"] to
//     reflect a new validation result. Updates the status pill class,
//     the timestamp text, the relative-age text, and the result text
//     block. Safe when the row or pieces are missing (no-op).
//
// This module has ZERO knowledge of the qs:bulk-validation-* event
// flow -- that lives in 900-kometa.js because it's tightly bound to
// page-load wiring and needs access to a bunch of other page-scoped
// state (kometaState.showYAML, getFinalGateState, etc.). Keeping this
// module pure/small maximizes test coverage.

/**
 * Two-digit zero-padded integer stringification. Private helper.
 * @private
 */
function pad2 (value) {
  return String(value).padStart(2, '0')
}

/**
 * Format a Date as "YYYY-MM-DD HH:MM:SS" in local time.
 *
 * Deliberately not toISOString (UTC) or toLocaleString (locale-
 * dependent). The wizard rows show this exact format.
 *
 * @param {Date} date  Any valid Date. Callers are expected to have
 *                      already validated via Number.isNaN(getTime()).
 * @returns {string}
 */
export function formatLocalTimestamp (date) {
  return [
    date.getFullYear(),
    pad2(date.getMonth() + 1),
    pad2(date.getDate())
  ].join('-') + ' ' + [
    pad2(date.getHours()),
    pad2(date.getMinutes()),
    pad2(date.getSeconds())
  ].join(':')
}

/**
 * Format a Date as a human-relative age string ("Just now",
 * "5m ago", "2h 15m ago", "3d 4h ago", "2w 3d ago", "5mo ago",
 * "2y ago").
 *
 * Uses cascading unit boundaries:
 *   <60s      -> "Just now"
 *   <60min    -> "Nm ago"
 *   <24h      -> "Nh Mm ago"
 *   <7d       -> "Nd Mh ago"
 *   <5w       -> "Nw Md ago"
 *   <12mo     -> "Nmo ago"
 *   else      -> "Ny ago"
 *
 * Weeks/days handled with month approximation (30 days = 1mo,
 * 365 days = 1y). Not calendar-accurate; deliberately loose.
 *
 * Negative diffs (clock skew, future timestamp) clamp to 0 -> "Just now".
 *
 * @param {Date}  date  The past date to describe.
 * @param {Date} [now]  Reference "now" (defaults to `new Date()`).
 *                       Injectable for deterministic tests.
 * @returns {string}
 */
export function formatRelativeTimestamp (date, now) {
  const base = now || new Date()
  let diffMs = base - date
  if (!Number.isFinite(diffMs) || diffMs < 0) diffMs = 0
  const sec = Math.floor(diffMs / 1000)
  if (sec < 60) return 'Just now'
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  const minLeft = min % 60
  if (hr < 24) return `${hr}h ${minLeft}m ago`
  const days = Math.floor(hr / 24)
  const hrLeft = hr % 24
  if (days < 7) return `${days}d ${hrLeft}h ago`
  const weeks = Math.floor(days / 7)
  const dayLeft = days % 7
  if (weeks < 5) return `${weeks}w ${dayLeft}d ago`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}mo ago`
  const years = Math.floor(days / 365)
  return `${years}y ago`
}

/**
 * Human-readable labels for validation reason codes. Reason codes not
 * in this map fall back to `code.replace(/_/g, ' ')`.
 */
export const VALIDATION_REASON_LABELS = {
  missing_credentials: 'Missing credentials',
  missing_plex_validation: 'Plex not validated',
  no_libraries: 'No libraries selected',
  invalid_paths: 'Invalid paths',
  missing_library_defaults: 'Missing library defaults',
  missing_separator_placeholder: 'Missing separator placeholder',
  invalid_fields: 'Invalid fields',
  no_webhooks: 'No webhooks configured',
  disabled: 'Disabled',
  missing_settings: 'Settings missing',
  missing_tokens: 'Missing tokens',
  token_invalid: 'Invalid tokens',
  account_locked: 'Account locked',
  validation_error: 'Validation error'
}

/**
 * Format a validation result as a display string.
 *
 * Returns '' when status is falsy (used by callers to detect
 * "nothing to show"). Otherwise the status is Title-Cased and
 * optionally suffixed with a reason and details.
 *
 * Shape:
 *   ""                           when status is falsy
 *   "Validated"                  when reason is falsy
 *   "Validated: <reason>"        when reason is set, no details
 *   "Validated: <reason>: <d>"   when both are set (d = joined array or scalar)
 *
 * @param {string} status                   e.g. "validated" | "failed" | "skipped"
 * @param {string} [reason]                 code looked up in VALIDATION_REASON_LABELS
 * @param {(string|string[])} [details]     optional detail text or array of strings
 * @returns {string}
 */
export function formatValidationResult (status, reason, details) {
  if (!status) return ''
  const label = status.charAt(0).toUpperCase() + status.slice(1)
  if (!reason) return label
  const pretty = VALIDATION_REASON_LABELS[reason] || reason.replace(/_/g, ' ')
  if (Array.isArray(details) && details.length) {
    return `${label}: ${pretty}: ${details.join(', ')}`
  }
  if (details) {
    return `${label}: ${pretty}: ${details}`
  }
  return `${label}: ${pretty}`
}

/**
 * Update the DOM row for a validation key with a fresh result.
 *
 * Looks up `[data-validation-key="{key}"]`. Silently no-ops if the
 * row or `result` is missing.
 *
 * Updates (in order):
 *   1. The .validation-status-pill CSS class (removes prior, adds one
 *      of --validated / --unvalidated / --neutral based on status).
 *   2. The .validation-timestamp textContent + dataset.validationIso
 *      when result.validated_at is set + parseable.
 *   3. The .validation-age textContent + dataset.validationIsoAge
 *      (same logic).
 *   4. The .validation-result textContent via formatValidationResult.
 *      Falls back to Title-Cased status if formatValidationResult
 *      returned '' but status is set. Falls back to em-dash if not.
 *
 * @param {string} key  Value of the row's data-validation-key attr.
 * @param {object} result  { status, validated_at?, reason?, details? }
 */
export function updateValidationRow (key, result) {
  const row = document.querySelector(`[data-validation-key="${key}"]`)
  if (!row || !result) return

  const pill = row.querySelector('.validation-status-pill')
  const timestampEl = row.querySelector('.validation-timestamp')
  const ageEl = row.querySelector('.validation-age')
  const status = result.status
  const validatedAt = result.validated_at || ''

  if (pill) {
    pill.classList.remove(
      'rating-mapping-option-via--validated',
      'rating-mapping-option-via--unvalidated',
      'rating-mapping-option-via--neutral'
    )
    if (status === 'validated') {
      pill.classList.add('rating-mapping-option-via--validated')
    } else if (status === 'failed') {
      pill.classList.add('rating-mapping-option-via--unvalidated')
    } else if (status === 'skipped') {
      pill.classList.add('rating-mapping-option-via--neutral')
    }
  }

  if (validatedAt && timestampEl) {
    timestampEl.dataset.validationIso = validatedAt
    const parsed = new Date(validatedAt)
    if (!Number.isNaN(parsed.getTime())) {
      timestampEl.textContent = formatLocalTimestamp(parsed)
    }
  }

  if (validatedAt && ageEl) {
    ageEl.dataset.validationIsoAge = validatedAt
    const parsed = new Date(validatedAt)
    if (!Number.isNaN(parsed.getTime())) {
      ageEl.textContent = formatRelativeTimestamp(parsed, new Date())
    }
  }

  const resultEl = row.querySelector('.validation-result')
  if (resultEl) {
    const resultText = formatValidationResult(status, result.reason, result.details)
    resultEl.textContent = resultText || (status ? status.charAt(0).toUpperCase() + status.slice(1) : '\u2014')
  }
}
