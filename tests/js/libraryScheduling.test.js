import { beforeEach, describe, expect, it } from 'vitest'
import { decodeLibrarySchedule, initLibraryScheduling, scheduleYamlPreview } from '../../static/local-js/modules/libraryScheduling.js'
import { initProcessingMode, processingModeValue, validateProcessingMode } from '../../static/local-js/modules/processingMode.js'

const rules = [{ schedule: 'weekly(monday)', mode: 'added(7)' }, { schedule: 'weekly(tuesday)', mode: 'index(A-F#)' }, { schedule: 'weekly.not(monday|tuesday)', mode: 'full' }]
const modeMarkup = `<div data-processing-mode>
  <select data-processing-kind>${['', 'full', 'added', 'diff', 'index', 'items', 'custom'].map(kind => `<option>${kind}</option>`).join('')}</select>
  <div data-processing-fields="added"><input data-processing-amount value="7"><select data-processing-unit>${['', 'm', 'h', 'd'].map(unit => `<option>${unit}</option>`).join('')}</select></div>
  <div data-processing-fields="index"><input data-processing-first value="A"><input data-processing-last value="F"><input type="checkbox" data-processing-symbols></div>
  <div data-processing-fields="items"><textarea data-processing-ids></textarea></div>
  <input data-processing-custom><div data-processing-error></div></div>`

function mount (value) {
  document.body.innerHTML = `<div data-library-scheduling data-library-id="mov-library_1">
    <input data-library-schedule-value><select data-library-schedule-format><option>none</option><option>basic</option><option>rules</option></select>
    <div data-library-schedule-editor><div data-library-schedule-rows></div><button data-library-schedule-add></button></div>
    <div data-library-schedule-error></div><details data-library-schedule-repair><textarea data-library-schedule-raw></textarea><button data-library-schedule-load></button></details><code data-library-schedule-preview></code>
    <template data-library-schedule-row-template><div data-library-schedule-row><span data-schedule-row-number></span><button data-schedule-up></button><button data-schedule-down></button><button data-schedule-remove></button>
      <select data-schedule-frequency>${['daily', 'weekly', 'monthly', 'custom'].map(frequency => `<option>${frequency}</option>`).join('')}</select>
      <div data-schedule-fields="weekly">${['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].map(day => `<input type="checkbox" data-schedule-day value="${day}">`).join('')}</div>
      <div data-schedule-fields="monthly"><input data-schedule-dates></div><div data-schedule-exclusion><input type="checkbox" data-schedule-not></div>
      <div data-schedule-fields="custom"><input data-schedule-expression></div><div data-schedule-rule-mode>${modeMarkup}</div></div></template></div>`
  const hidden = document.querySelector('[data-library-schedule-value]')
  hidden.value = typeof value === 'string' ? value : JSON.stringify(value)
  initLibraryScheduling()
  return { hidden, format: document.querySelector('[data-library-schedule-format]'), rows: () => Array.from(document.querySelector('[data-library-schedule-rows]').children) }
}
function change (input, value) {
  input.value = value
  input.dispatchEvent(new Event('change', { bubbles: true }))
}
beforeEach(() => document.body.replaceChildren())

describe('processing mode contract', () => {
  it.each(['full', 'diff', 'added(7)', 'added(30m)', 'added(1h)', 'added(12d)', 'index(A-F#)', 'index(A)', 'items(imdb:tt0133093|plex:42)'])('restores and validates %s', mode => {
    document.body.innerHTML = modeMarkup
    const root = document.querySelector('[data-processing-mode]')
    initProcessingMode(root, mode)
    expect(processingModeValue(root)).toBe(mode)
    expect(validateProcessingMode(mode)).toBe(mode)
  })
  it.each(['added(0)', 'added(-1)', 'added(1w)', 'added(999999999999)', 'index(Z-A)', 'items(42)', 'items(plex:0)', 'items(imdb:123)', 'full; ls'])('rejects %s', mode => {
    expect(() => validateProcessingMode(mode)).toThrow()
  })
  it('accepts comma and newline separated provider IDs', () => {
    document.body.innerHTML = modeMarkup
    const root = document.querySelector('[data-processing-mode]')
    initProcessingMode(root, 'items(plex:42)')
    change(root.querySelector('[data-processing-ids]'), 'imdb:tt0133093, tmdb:550\nplex:42')
    expect(processingModeValue(root)).toBe('items(imdb:tt0133093|tmdb:550|plex:42)')
  })
})

describe('ordered library schedules', () => {
  it.each(['weekly(mon)', ['weekly(mon)'], ['weekly(mon)', 'weekly(fri)'], rules].map(value => ({ value })))('preserves imported data until edited: $value', ({ value }) => {
    const { hidden } = mount(value)
    expect(decodeLibrarySchedule(hidden.value)).toEqual(value)
    expect(scheduleYamlPreview(value)).toContain('schedule:')
    initLibraryScheduling()
    expect(document.querySelectorAll('[data-library-schedule-row]')).toHaveLength(Array.isArray(value) ? value.length : 1)
  })
  it('reorders, removes, and adds rules without losing mode values', () => {
    const { hidden, rows } = mount(rules)
    rows()[1].querySelector('[data-schedule-up]').click()
    expect(JSON.parse(hidden.value)).toEqual([rules[1], rules[0], rules[2]])
    rows()[2].querySelector('[data-schedule-remove]').click()
    expect(JSON.parse(hidden.value)).toEqual([rules[1], rules[0]])
    document.querySelector('[data-library-schedule-add]').click()
    expect(JSON.parse(hidden.value).at(-1)).toEqual({ schedule: 'daily', mode: 'full' })
  })
  it('builds monthly exclusions and minute durations', () => {
    const { hidden, rows } = mount(rules)
    const row = rows()[0]
    change(row.querySelector('[data-schedule-frequency]'), 'monthly')
    change(row.querySelector('[data-schedule-dates]'), '1, 15, last')
    row.querySelector('[data-schedule-not]').click()
    change(row.querySelector('[data-processing-amount]'), '30')
    change(row.querySelector('[data-processing-unit]'), 'm')
    expect(JSON.parse(hidden.value)[0]).toEqual({ schedule: 'monthly.not(1|15|last)', mode: 'added(30m)' })
  })
  it('supports an advanced schedule expression', () => {
    const { hidden, rows } = mount(rules)
    change(rows()[0].querySelector('[data-schedule-frequency]'), 'custom')
    change(rows()[0].querySelector('[data-schedule-expression]'), 'all[weekly(mon), hourly(6)]')
    expect(JSON.parse(hidden.value)[0].schedule).toBe('all[weekly(mon), hourly(6)]')
  })
  it('clears the canonical value when scheduling is disabled', () => {
    const { hidden, format } = mount(rules)
    change(format, 'none')
    expect(hidden.value).toBe('')
  })
  it('refreshes controls after a mirror or reset changes the hidden value', () => {
    const { hidden, rows } = mount(rules)
    change(hidden, JSON.stringify([{ schedule: 'daily', mode: 'diff' }]))
    expect(rows()).toHaveLength(1)
    expect(rows()[0].querySelector('[data-processing-kind]').value).toBe('diff')
  })
  it.each(['[{"schedule":', [{ schedule: 'daily', mode: 'full', future: true }]].map(value => ({ value })))('preserves unsupported imports for repair: $value', ({ value }) => {
    const { hidden } = mount(value)
    expect(hidden.value).toBe(typeof value === 'string' ? value : JSON.stringify(value))
    expect(document.querySelector('[data-library-schedule-error]').textContent).not.toBe('')
    expect(document.querySelector('[data-library-schedule-repair]').classList.contains('d-none')).toBe(false)
  })
})
