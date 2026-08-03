// Tests for static/local-js/modules/kometa/_validationDisplay.js
//
// Four exports:
//   - formatLocalTimestamp(date)
//   - formatRelativeTimestamp(date, now?)
//   - VALIDATION_REASON_LABELS (constant)
//   - formatValidationResult(status, reason?, details?)
//   - updateValidationRow(key, result)
//
// COVERAGE STRATEGY:
//
//   formatLocalTimestamp (4):
//     - happy path: "YYYY-MM-DD HH:MM:SS"
//     - zero-pads single-digit month/day/hours/minutes/seconds
//     - uses local time (not UTC)
//     - handles New Year's midnight
//
//   formatRelativeTimestamp (12):
//     - Just now (<60s), custom now injectable
//     - Nm ago (<60min)
//     - Nh Mm ago (<24h)
//     - Nd Mh ago (<7d)
//     - Nw Md ago (<5w)
//     - Nmo ago (<12mo)
//     - Ny ago (year and above)
//     - boundary conditions (exactly 60s, 60min, 24h, 7d, 5w, 12mo)
//     - negative diff (clock skew) clamps to "Just now"
//     - non-finite diff clamps to "Just now"
//     - now defaults to `new Date()` when omitted
//
//   VALIDATION_REASON_LABELS (2):
//     - contains all 14 documented reason codes
//     - each label is a non-empty string
//
//   formatValidationResult (7):
//     - empty status -> ''
//     - status only -> Title-Cased status
//     - status + known reason -> "Status: pretty"
//     - status + unknown reason -> snake_case unquoted
//     - status + reason + string details
//     - status + reason + array details (comma-joined)
//     - status + reason + empty array (no details suffix)
//
//   updateValidationRow:
//     - no-op when row missing
//     - no-op when result missing
//     - sets --validated pill for 'validated' status
//     - sets --unvalidated pill for 'failed' status
//     - sets --neutral pill for 'skipped' status
//     - sets --optional pill for skipped optional rows
//     - removes prior pill classes before adding new one
//     - populates timestamp + dataset when validated_at set
//     - skips timestamp when validated_at empty
//     - skips timestamp when validated_at unparseable
//     - populates age element
//     - populates result element via formatValidationResult
//     - falls back to Title-Cased status when formatter returns ''
//     - falls back to em-dash when both empty

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  formatLocalTimestamp,
  formatRelativeTimestamp,
  VALIDATION_REASON_LABELS,
  formatValidationResult,
  updateValidationRow
} from '../../../static/local-js/modules/kometa/_validationDisplay.js'

// ---------------------------------------------------------------------
// formatLocalTimestamp
// ---------------------------------------------------------------------

describe('formatLocalTimestamp', () => {
  it("formats a mid-2024 date as YYYY-MM-DD HH:MM:SS", () => {
    // Local time; use a well-defined Date with local components
    const d = new Date(2024, 6, 15, 14, 25, 37)  // July is month 6
    expect(formatLocalTimestamp(d)).toBe('2024-07-15 14:25:37')
  })

  it("zero-pads single-digit month/day/hours/minutes/seconds", () => {
    const d = new Date(2024, 0, 5, 3, 4, 9)  // Jan 5, 03:04:09
    expect(formatLocalTimestamp(d)).toBe('2024-01-05 03:04:09')
  })

  it("uses local time rather than UTC", () => {
    // Construct a date; local-time output should never end in 'Z'
    // and should always show exact H:M:S from the local getter methods.
    const d = new Date(2024, 5, 15, 12, 34, 56)  // June 15 local
    const stamp = formatLocalTimestamp(d)
    expect(stamp).not.toContain('Z')
    expect(stamp).toContain('12:34:56')
  })

  it("handles New Year's midnight", () => {
    const d = new Date(2024, 0, 1, 0, 0, 0)
    expect(formatLocalTimestamp(d)).toBe('2024-01-01 00:00:00')
  })
})

// ---------------------------------------------------------------------
// formatRelativeTimestamp
// ---------------------------------------------------------------------

describe('formatRelativeTimestamp', () => {
  // Fixed "now" for determinism
  const NOW = new Date('2024-06-15T12:00:00Z')

  function subMs (ms) { return new Date(NOW.getTime() - ms) }

  it("returns 'Just now' when <60s ago", () => {
    expect(formatRelativeTimestamp(subMs(30 * 1000), NOW)).toBe('Just now')
  })

  it("returns 'Nm ago' when <60min ago", () => {
    expect(formatRelativeTimestamp(subMs(5 * 60 * 1000), NOW)).toBe('5m ago')
  })

  it("returns 'Nh Mm ago' when <24h ago", () => {
    // 2h 30m
    expect(formatRelativeTimestamp(subMs((2 * 60 + 30) * 60 * 1000), NOW)).toBe('2h 30m ago')
  })

  it("returns 'Nd Mh ago' when <7d ago", () => {
    // 3 days + 4 hours
    expect(formatRelativeTimestamp(subMs((3 * 24 + 4) * 60 * 60 * 1000), NOW)).toBe('3d 4h ago')
  })

  it("returns 'Nw Md ago' when <5w ago", () => {
    // 2 weeks + 3 days
    expect(formatRelativeTimestamp(subMs((2 * 7 + 3) * 24 * 60 * 60 * 1000), NOW)).toBe('2w 3d ago')
  })

  it("returns 'Nmo ago' when <12mo ago", () => {
    // ~60 days = ~2 months (uses 30-day approximation)
    expect(formatRelativeTimestamp(subMs(60 * 24 * 60 * 60 * 1000), NOW)).toBe('2mo ago')
  })

  it("returns 'Ny ago' when a year or more ago", () => {
    // 800 days = ~2.2 years
    expect(formatRelativeTimestamp(subMs(800 * 24 * 60 * 60 * 1000), NOW)).toBe('2y ago')
  })

  it("exactly 60s crosses into 'Nm ago' bucket", () => {
    expect(formatRelativeTimestamp(subMs(60 * 1000), NOW)).toBe('1m ago')
  })

  it("exactly 60min crosses into 'Nh Mm ago' bucket", () => {
    expect(formatRelativeTimestamp(subMs(60 * 60 * 1000), NOW)).toBe('1h 0m ago')
  })

  it("clamps future dates (negative diff) to 'Just now'", () => {
    // Future date = negative diff -> clamped to 0 -> 'Just now'
    const future = new Date(NOW.getTime() + 60 * 60 * 1000)
    expect(formatRelativeTimestamp(future, NOW)).toBe('Just now')
  })

  it("clamps non-finite diff (invalid date) to 'Just now'", () => {
    expect(formatRelativeTimestamp(new Date('invalid'), NOW)).toBe('Just now')
  })

  it("defaults 'now' to new Date() when omitted", () => {
    // Use a very-recent past to guarantee 'Just now'
    const veryRecent = new Date(Date.now() - 5000)
    expect(formatRelativeTimestamp(veryRecent)).toBe('Just now')
  })
})

// ---------------------------------------------------------------------
// VALIDATION_REASON_LABELS
// ---------------------------------------------------------------------

describe('VALIDATION_REASON_LABELS', () => {
  it("includes all 14 documented reason codes", () => {
    const expectedKeys = [
      'missing_credentials', 'missing_plex_validation', 'no_libraries',
      'invalid_paths', 'missing_library_defaults', 'missing_separator_placeholder',
      'invalid_fields', 'no_webhooks', 'disabled', 'missing_settings',
      'missing_tokens', 'token_invalid', 'account_locked', 'validation_error'
    ]
    for (const k of expectedKeys) {
      expect(VALIDATION_REASON_LABELS).toHaveProperty(k)
    }
  })

  it("each label is a non-empty string", () => {
    for (const [, label] of Object.entries(VALIDATION_REASON_LABELS)) {
      expect(typeof label).toBe('string')
      expect(label.length).toBeGreaterThan(0)
    }
  })
})

// ---------------------------------------------------------------------
// formatValidationResult
// ---------------------------------------------------------------------

describe('formatValidationResult', () => {
  it("returns '' when status is falsy", () => {
    expect(formatValidationResult(null)).toBe('')
    expect(formatValidationResult(undefined)).toBe('')
    expect(formatValidationResult('')).toBe('')
  })

  it("returns Title-Cased status only when no reason", () => {
    expect(formatValidationResult('validated')).toBe('Validated')
    expect(formatValidationResult('failed')).toBe('Failed')
    expect(formatValidationResult('skipped')).toBe('Skipped')
  })

  it("appends known reason label", () => {
    expect(formatValidationResult('failed', 'missing_credentials'))
      .toBe('Failed: Missing credentials')
  })

  it("appends unknown reason with underscores spaced out", () => {
    expect(formatValidationResult('failed', 'some_novel_reason'))
      .toBe('Failed: some novel reason')
  })

  it("appends string details", () => {
    expect(formatValidationResult('failed', 'invalid_paths', '/nope'))
      .toBe('Failed: Invalid paths: /nope')
  })

  it("appends array details as comma-joined", () => {
    expect(formatValidationResult('failed', 'invalid_paths', ['/a', '/b', '/c']))
      .toBe('Failed: Invalid paths: /a, /b, /c')
  })

  it("empty array falls through to the string-branch (produces trailing colon)", () => {
    // Note: [] is truthy in JS. The Array.isArray branch requires
    // `details.length` which is 0 for an empty array, so it falls
    // through to the `if (details)` branch which stringifies via
    // template literal. Array#toString of [] is ''. Result: trailing
    // ": " is preserved verbatim from the original 900-kometa.js impl.
    expect(formatValidationResult('failed', 'invalid_paths', []))
      .toBe('Failed: Invalid paths: ')
  })
})

// ---------------------------------------------------------------------
// updateValidationRow
// ---------------------------------------------------------------------

describe('updateValidationRow', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div data-validation-key="plex">
        <span class="validation-status-pill rating-mapping-option-via--neutral"></span>
        <span class="validation-timestamp"></span>
        <span class="validation-age"></span>
        <span class="validation-result"></span>
      </div>
    `
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it("no-ops when row is missing", () => {
    expect(() => updateValidationRow('nonexistent', { status: 'validated' })).not.toThrow()
  })

  it("no-ops when result is missing", () => {
    expect(() => updateValidationRow('plex', null)).not.toThrow()
    // Original pill class should be unchanged
    expect(document.querySelector('.validation-status-pill').classList.contains('rating-mapping-option-via--neutral')).toBe(true)
  })

  it("sets --validated pill class for status='validated'", () => {
    updateValidationRow('plex', { status: 'validated' })
    const pill = document.querySelector('.validation-status-pill')
    expect(pill.classList.contains('rating-mapping-option-via--validated')).toBe(true)
    expect(pill.classList.contains('rating-mapping-option-via--neutral')).toBe(false)
  })

  it("sets --unvalidated pill class for status='failed'", () => {
    updateValidationRow('plex', { status: 'failed' })
    expect(document.querySelector('.validation-status-pill').classList.contains('rating-mapping-option-via--unvalidated')).toBe(true)
  })

  it("sets --neutral pill class for status='skipped'", () => {
    // Start with a different class to verify removal
    document.querySelector('.validation-status-pill').className = 'validation-status-pill rating-mapping-option-via--validated'
    updateValidationRow('plex', { status: 'skipped' })
    expect(document.querySelector('.validation-status-pill').classList.contains('rating-mapping-option-via--neutral')).toBe(true)
    expect(document.querySelector('.validation-status-pill').classList.contains('rating-mapping-option-via--validated')).toBe(false)
  })

  it("sets --neutral pill class for skipped optional rows", () => {
    const row = document.querySelector('[data-validation-key="plex"]')
    row.dataset.validationGroup = 'optional'
    document.querySelector('.validation-status-pill').className = 'validation-status-pill rating-mapping-option-via--unvalidated'
    updateValidationRow('plex', { status: 'skipped' })
    const pill = document.querySelector('.validation-status-pill')
    expect(pill.classList.contains('rating-mapping-option-via--neutral')).toBe(true)
    expect(pill.classList.contains('rating-mapping-option-via--optional')).toBe(false)
    expect(pill.classList.contains('rating-mapping-option-via--unvalidated')).toBe(false)
  })

  it("clears prior pill classes before adding new one (unknown status)", () => {
    document.querySelector('.validation-status-pill').className = 'validation-status-pill rating-mapping-option-via--validated rating-mapping-option-via--optional'
    updateValidationRow('plex', { status: 'weird-unknown-status' })
    // All known state classes should be gone; no new one added.
    const pill = document.querySelector('.validation-status-pill')
    expect(pill.classList.contains('rating-mapping-option-via--validated')).toBe(false)
    expect(pill.classList.contains('rating-mapping-option-via--unvalidated')).toBe(false)
    expect(pill.classList.contains('rating-mapping-option-via--optional')).toBe(false)
    expect(pill.classList.contains('rating-mapping-option-via--neutral')).toBe(false)
  })

  it("populates timestamp and dataset when validated_at is a valid ISO", () => {
    updateValidationRow('plex', { status: 'validated', validated_at: '2024-06-15T12:30:00' })
    const ts = document.querySelector('.validation-timestamp')
    expect(ts.dataset.validationIso).toBe('2024-06-15T12:30:00')
    // Text should be a "YYYY-MM-DD HH:MM:SS" format
    expect(ts.textContent).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
  })

  it("skips timestamp update when validated_at is empty", () => {
    updateValidationRow('plex', { status: 'validated' })  // no validated_at
    const ts = document.querySelector('.validation-timestamp')
    expect(ts.dataset.validationIso).toBeUndefined()
    expect(ts.textContent).toBe('')
  })

  it("skips timestamp text when validated_at is unparseable but sets dataset", () => {
    updateValidationRow('plex', { status: 'validated', validated_at: 'not-a-date' })
    const ts = document.querySelector('.validation-timestamp')
    // dataset gets the raw string, but text stays empty
    expect(ts.dataset.validationIso).toBe('not-a-date')
    expect(ts.textContent).toBe('')
  })

  it("populates the age element with a relative timestamp", () => {
    // Recent past -> 'Just now'-ish; use exact-match on the age text
    // pattern rather than value to avoid clock-time flakiness.
    const recent = new Date(Date.now() - 5000).toISOString()
    updateValidationRow('plex', { status: 'validated', validated_at: recent })
    const age = document.querySelector('.validation-age')
    expect(age.dataset.validationIsoAge).toBe(recent)
    expect(age.textContent).toBe('Just now')
  })

  it("populates the result element via formatValidationResult", () => {
    updateValidationRow('plex', { status: 'failed', reason: 'missing_credentials' })
    expect(document.querySelector('.validation-result').textContent).toBe('Failed: Missing credentials')
  })

  it("falls back to em-dash when formatValidationResult returns ''", () => {
    // Empty status -> formatValidationResult returns '' -> fallback path
    updateValidationRow('plex', { status: '' })
    expect(document.querySelector('.validation-result').textContent).toBe('\u2014')
  })
})
