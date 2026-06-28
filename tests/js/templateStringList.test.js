// Tests for static/local-js/templateStringList.js (#1334 Step 8 — coverage push).
//
// Same side-effect-import pattern as urlValidation.test.js and
// pathValidation.test.js. Public API is on window.QSTemplateStringLists.
//
// SCOPE NOTE: This module exposes three things via QSTemplateStringLists:
//
//   1. presetConfigs — an object of 16 validation presets. Each has
//      a `validate` function (and sometimes `normalize`,
//      `duplicateInsensitive`, `allowedValues`, `lookupService`). These
//      validators are PURE — perfect unit-test targets.
//
//   2. setup(scope) — wires up the [data-template-string-list] widget
//      with text input, add button, item chips, hidden JSON store,
//      lookup caching, fetch-backed async validation, mutual exclusion
//      with sibling lists, etc. This is END-TO-END WIDGET LOGIC and is
//      not covered here — Playwright is the right tool for that.
//
//   3. validateAll(scope) — walks bound widgets and re-runs validation.
//      Smoke-tested with a minimal happy path here; the per-preset
//      coverage is what protects refactors.
//
// 90% of the safety-net value for the price of 10% of the test surface
// comes from the preset validators alone. That's why this file leans
// hard on them.

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

await import('../../static/local-js/templateStringList.js')
const QSTemplateStringLists = window.QSTemplateStringLists
const presets = QSTemplateStringLists.presetConfigs

describe('QSTemplateStringLists exports its public API', () => {
  it('exposes presetConfigs, setup, and validateAll', () => {
    expect(typeof QSTemplateStringLists.setup).toBe('function')
    expect(typeof QSTemplateStringLists.validateAll).toBe('function')
    expect(typeof QSTemplateStringLists.presetConfigs).toBe('object')
  })

  it('defines all 16 known presets', () => {
    const expected = [
      'generic_text', 'name_like',
      'tmdb_collection_id', 'numeric_id', 'imdb_id_tmdb', 'imdb_id_plex',
      'year', 'decade', 'language_code',
      'aspect_key', 'resolution_key', 'streaming_key',
      'universe_key', 'based_key', 'seasonal_key',
      'content_rating'
    ]
    for (const name of expected) {
      expect(presets[name], `missing preset: ${name}`).toBeDefined()
      expect(typeof presets[name].validate, `${name}.validate not a function`).toBe('function')
    }
  })
})

describe('presets.generic_text', () => {
  it('rejects empty string', () => {
    expect(presets.generic_text.validate('')).toEqual({
      valid: false,
      message: 'Enter a value before adding it.'
    })
  })

  it('accepts any non-empty string', () => {
    expect(presets.generic_text.validate('anything goes here')).toEqual({ valid: true })
  })

  it('is duplicate-sensitive (case matters)', () => {
    expect(presets.generic_text.duplicateInsensitive).toBe(false)
  })
})

describe('presets.name_like', () => {
  it('rejects empty string', () => {
    expect(presets.name_like.validate('').valid).toBe(false)
  })

  it('rejects pure punctuation with no letters or numbers', () => {
    const result = presets.name_like.validate('...!!!')
    expect(result.valid).toBe(false)
    expect(result.message).toBe('Enter a text value with letters or numbers.')
  })

  it('accepts a simple alphanumeric name', () => {
    expect(presets.name_like.validate('Star Wars').valid).toBe(true)
  })

  it('accepts names with common punctuation', () => {
    expect(presets.name_like.validate('Mr. & Mrs. Smith').valid).toBe(true)
    expect(presets.name_like.validate('Spider-Man (2002)').valid).toBe(true)
    expect(presets.name_like.validate('Hello, World!').valid).toBe(true)
  })

  it('accepts non-ASCII letters (Unicode-aware)', () => {
    expect(presets.name_like.validate('Amélie').valid).toBe(true)
    expect(presets.name_like.validate('東京物語').valid).toBe(true)
  })

  it('rejects names with unsupported symbols', () => {
    const result = presets.name_like.validate('Star $$$ Wars')
    expect(result.valid).toBe(false)
    expect(result.message).toBe('Use letters, numbers, spaces, or common punctuation only.')
  })

  it('normalizes multiple internal whitespace to single space', () => {
    expect(presets.name_like.normalize('Star    Wars')).toBe('Star Wars')
  })

  it('is duplicate-insensitive', () => {
    expect(presets.name_like.duplicateInsensitive).toBe(true)
  })
})

describe('presets.tmdb_collection_id', () => {
  it('accepts a numeric string', () => {
    expect(presets.tmdb_collection_id.validate('131292').valid).toBe(true)
  })

  it('accepts a single-digit numeric', () => {
    expect(presets.tmdb_collection_id.validate('7').valid).toBe(true)
  })

  it('rejects a non-numeric string', () => {
    const result = presets.tmdb_collection_id.validate('tt1234567')
    expect(result.valid).toBe(false)
    expect(result.message).toBe('Enter a numeric TMDb collection ID like 131292.')
  })

  it('rejects a string with mixed letters and numbers', () => {
    expect(presets.tmdb_collection_id.validate('131292x').valid).toBe(false)
  })

  it('rejects empty string', () => {
    expect(presets.tmdb_collection_id.validate('').valid).toBe(false)
  })

  it('uses the tmdb lookup service', () => {
    expect(presets.tmdb_collection_id.lookupService).toBe('tmdb')
  })
})

describe('presets.numeric_id', () => {
  it('accepts a numeric ID like 603', () => {
    expect(presets.numeric_id.validate('603').valid).toBe(true)
  })

  it('rejects a non-numeric string', () => {
    expect(presets.numeric_id.validate('foo').valid).toBe(false)
  })

  it('rejects negative numbers (no leading sign)', () => {
    expect(presets.numeric_id.validate('-1').valid).toBe(false)
  })
})

describe('presets.imdb_id_tmdb', () => {
  it('accepts a 7-digit IMDb ID', () => {
    expect(presets.imdb_id_tmdb.validate('tt1234567').valid).toBe(true)
  })

  it('accepts an 8-digit IMDb ID', () => {
    expect(presets.imdb_id_tmdb.validate('tt12345678').valid).toBe(true)
  })

  it('accepts uppercase TT prefix (case-insensitive regex)', () => {
    expect(presets.imdb_id_tmdb.validate('TT1234567').valid).toBe(true)
  })

  it('rejects a 6-digit ID (too short)', () => {
    expect(presets.imdb_id_tmdb.validate('tt123456').valid).toBe(false)
  })

  it('rejects a 9-digit ID (too long)', () => {
    expect(presets.imdb_id_tmdb.validate('tt123456789').valid).toBe(false)
  })

  it('rejects an ID without the tt prefix', () => {
    expect(presets.imdb_id_tmdb.validate('1234567').valid).toBe(false)
  })

  it('normalizes to lowercase', () => {
    expect(presets.imdb_id_tmdb.normalize('TT1234567')).toBe('tt1234567')
  })

  it('uses the tmdb lookup service', () => {
    expect(presets.imdb_id_tmdb.lookupService).toBe('tmdb')
  })
})

describe('presets.imdb_id_plex', () => {
  it('shares the validation rules with imdb_id_tmdb', () => {
    expect(presets.imdb_id_plex.validate('tt1234567').valid).toBe(true)
    expect(presets.imdb_id_plex.validate('not-imdb').valid).toBe(false)
  })

  it('uses the plex lookup service (not tmdb)', () => {
    expect(presets.imdb_id_plex.lookupService).toBe('plex')
  })
})

describe('presets.year', () => {
  it('accepts a 4-digit year', () => {
    expect(presets.year.validate('2022').valid).toBe(true)
    expect(presets.year.validate('1900').valid).toBe(true)
  })

  it('rejects a 3-digit year', () => {
    expect(presets.year.validate('999').valid).toBe(false)
  })

  it('rejects a 5-digit year', () => {
    expect(presets.year.validate('20223').valid).toBe(false)
  })

  it('rejects non-numeric input', () => {
    expect(presets.year.validate('twenty').valid).toBe(false)
  })
})

describe('presets.decade', () => {
  it('accepts a 4-digit decade ending in 0', () => {
    expect(presets.decade.validate('2020').valid).toBe(true)
    expect(presets.decade.validate('1990').valid).toBe(true)
  })

  it('accepts a 5-digit decade ending in 0 (e.g. far-future)', () => {
    // The regex is /^\d{3,4}0$/ which means "3 or 4 digits, then a 0"
    // — total length 4 or 5. So the minimum is 4 chars like "1000"
    // and the max is 5 chars like "10000".
    expect(presets.decade.validate('10000').valid).toBe(true)
  })

  it('rejects a 3-character value (regex requires at least 4 total chars)', () => {
    expect(presets.decade.validate('190').valid).toBe(false)
  })

  it('rejects a year not ending in 0', () => {
    expect(presets.decade.validate('2021').valid).toBe(false)
  })

  it('rejects pure single digit 0', () => {
    expect(presets.decade.validate('0').valid).toBe(false)
  })
})

describe('presets.language_code', () => {
  it('accepts a 2-letter code', () => {
    expect(presets.language_code.validate('en').valid).toBe(true)
    expect(presets.language_code.validate('fr').valid).toBe(true)
  })

  it('accepts a 3-letter code', () => {
    expect(presets.language_code.validate('fil').valid).toBe(true)
    expect(presets.language_code.validate('myn').valid).toBe(true)
  })

  it('rejects an uppercase code (must be lowercase)', () => {
    expect(presets.language_code.validate('EN').valid).toBe(false)
  })

  it('rejects a 1-letter code', () => {
    expect(presets.language_code.validate('a').valid).toBe(false)
  })

  it('rejects a 4-letter code', () => {
    expect(presets.language_code.validate('abcd').valid).toBe(false)
  })

  it('rejects codes with digits', () => {
    expect(presets.language_code.validate('en1').valid).toBe(false)
  })

  it('normalizes uppercase to lowercase', () => {
    expect(presets.language_code.normalize('EN')).toBe('en')
    expect(presets.language_code.normalize('FiL')).toBe('fil')
  })
})

describe('presets.aspect_key', () => {
  it('accepts known aspect ratios', () => {
    expect(presets.aspect_key.validate('1.78').valid).toBe(true)
    expect(presets.aspect_key.validate('2.35').valid).toBe(true)
    expect(presets.aspect_key.validate('1.33').valid).toBe(true)
  })

  it('rejects unknown aspect ratios', () => {
    expect(presets.aspect_key.validate('1.79').valid).toBe(false)
    expect(presets.aspect_key.validate('9:16').valid).toBe(false)
  })

  it('exposes the full allowedValues set', () => {
    expect(presets.aspect_key.allowedValues).toBeInstanceOf(Set)
    expect(presets.aspect_key.allowedValues.has('1.78')).toBe(true)
    expect(presets.aspect_key.allowedValues.has('2.77')).toBe(true)
  })
})

describe('presets.resolution_key', () => {
  it('accepts known resolution keys', () => {
    expect(presets.resolution_key.validate('4k').valid).toBe(true)
    expect(presets.resolution_key.validate('1080').valid).toBe(true)
    expect(presets.resolution_key.validate('sd').valid).toBe(true)
  })

  it('rejects unknown resolutions', () => {
    expect(presets.resolution_key.validate('1440').valid).toBe(false)
    expect(presets.resolution_key.validate('hd').valid).toBe(false)
  })

  it('normalizes to lowercase before validating', () => {
    expect(presets.resolution_key.normalize('4K')).toBe('4k')
    expect(presets.resolution_key.normalize('SD')).toBe('sd')
  })
})

describe('presets.streaming_key', () => {
  it('accepts known streaming services', () => {
    expect(presets.streaming_key.validate('netflix').valid).toBe(true)
    expect(presets.streaming_key.validate('disney').valid).toBe(true)
    expect(presets.streaming_key.validate('hbomax').valid).toBe(true)
  })

  it('rejects unknown services', () => {
    expect(presets.streaming_key.validate('vidangel').valid).toBe(false)
  })

  it('normalizes case before validating', () => {
    expect(presets.streaming_key.normalize('NETFLIX')).toBe('netflix')
  })
})

describe('presets.universe_key', () => {
  it('accepts known universe keys', () => {
    expect(presets.universe_key.validate('mcu').valid).toBe(true)
    expect(presets.universe_key.validate('star').valid).toBe(true)
    expect(presets.universe_key.validate('wizard').valid).toBe(true)
  })

  it('rejects unknown universe keys', () => {
    expect(presets.universe_key.validate('starwars').valid).toBe(false)
  })
})

describe('presets.based_key', () => {
  it('accepts the four valid based keys', () => {
    expect(presets.based_key.validate('books').valid).toBe(true)
    expect(presets.based_key.validate('comics').valid).toBe(true)
    expect(presets.based_key.validate('true_story').valid).toBe(true)
    expect(presets.based_key.validate('video_games').valid).toBe(true)
  })

  it('rejects unknown based keys', () => {
    expect(presets.based_key.validate('manga').valid).toBe(false)
  })
})

describe('presets.seasonal_key', () => {
  it('accepts known seasonal keys', () => {
    expect(presets.seasonal_key.validate('halloween').valid).toBe(true)
    expect(presets.seasonal_key.validate('christmas').valid).toBe(true)
    expect(presets.seasonal_key.validate('lgbtq').valid).toBe(true)
  })

  it('rejects unknown seasonal keys', () => {
    expect(presets.seasonal_key.validate('birthday').valid).toBe(false)
  })
})

describe('presets.content_rating', () => {
  it('accepts standard MPAA ratings', () => {
    expect(presets.content_rating.validate('PG-13').valid).toBe(true)
    expect(presets.content_rating.validate('R').valid).toBe(true)
  })

  it('accepts TV ratings', () => {
    expect(presets.content_rating.validate('TV-14').valid).toBe(true)
    expect(presets.content_rating.validate('TV-MA').valid).toBe(true)
  })

  it('accepts age-as-number ratings', () => {
    expect(presets.content_rating.validate('15').valid).toBe(true)
    expect(presets.content_rating.validate('18').valid).toBe(true)
  })

  it('accepts single-letter ratings', () => {
    expect(presets.content_rating.validate('M').valid).toBe(true)
  })

  it('rejects ratings starting with a non-alphanumeric character', () => {
    expect(presets.content_rating.validate('-13').valid).toBe(false)
    expect(presets.content_rating.validate('(unrated)').valid).toBe(false)
  })

  it('rejects ratings with unsupported symbols', () => {
    expect(presets.content_rating.validate('R**').valid).toBe(false)
    expect(presets.content_rating.validate('PG@13').valid).toBe(false)
  })

  it('normalizes whitespace runs to single space', () => {
    expect(presets.content_rating.normalize('PG  13')).toBe('PG 13')
  })
})

describe('QSTemplateStringLists.validateAll smoke test', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('returns true when called with a scope containing no widgets', () => {
    expect(QSTemplateStringLists.validateAll(document)).toBe(true)
  })

  it('handles a missing scope gracefully (defaults to document)', () => {
    // We are mostly checking that this doesn't throw — validateAll
    // is called from form submit handlers where a missing scope
    // would otherwise crash submission.
    expect(() => QSTemplateStringLists.validateAll()).not.toThrow()
  })
})

describe('QSTemplateStringLists.setup smoke test', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('does not throw when scope contains no widget wrappers', () => {
    expect(() => QSTemplateStringLists.setup(document)).not.toThrow()
  })

  it('does not bind incomplete wrappers (missing required children)', () => {
    document.body.innerHTML = `
      <div data-template-string-list>
        <!-- intentionally missing input, addBtn, list, hidden -->
      </div>
    `
    expect(() => QSTemplateStringLists.setup(document)).not.toThrow()
    const wrapper = document.querySelector('[data-template-string-list]')
    expect(wrapper.dataset.listenerAdded).toBeUndefined()
  })

  // Full widget interaction (typing, clicking add, removing chips, etc.)
  // is covered by Playwright. The unit-test guarantee here is just
  // "setup does not crash on common edge cases."
})
