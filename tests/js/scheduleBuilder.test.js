import { beforeEach, describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const source = readFileSync(resolve(__dirname, '../../static/local-js/025-libraries.js'), 'utf8')
const builderSource = source.slice(source.indexOf('function initScheduleBuilders ('), source.indexOf('\nconst languageCollectionKeys'))
const initScheduleBuilders = new Function(`${builderSource}; return initScheduleBuilders`)()
const rulesSource = source.slice(source.indexOf('function setupCollectionTemplateFieldRules ('), source.indexOf('\nfunction initStylePreviewGrids'))
const setupCollectionTemplateFieldRules = new Function(`${rulesSource}; return setupCollectionTemplateFieldRules`)()

function mountBuilder (value, allowBoolean = true) {
  document.body.innerHTML = `
    <div data-collection-config="true">
      <div data-schedule-builder data-hidden-input="visibility" data-default-value="false" data-allow-boolean="${allowBoolean}">
        <select data-schedule-mode-select>
          ${allowBoolean ? '<option value="true">Always visible</option><option value="false">Hidden</option>' : ''}
          ${['range', 'weekly', 'monthly', 'yearly', 'date', 'hourly', 'daily', 'never', 'non_existing', 'custom'].map(mode => `<option value="${mode}">${mode}</option>`).join('')}
        </select>
        <div data-schedule-mode="range"><input data-schedule-range-values></div>
        <div data-schedule-mode="weekly"><input type="checkbox" value="mon" data-schedule-week-day><input type="checkbox" value="fri" data-schedule-week-day></div>
        <div data-schedule-mode="monthly"><input data-schedule-month-values></div>
        <div data-schedule-mode="yearly"><input data-schedule-year-values></div>
        <div data-schedule-mode="date"><input type="date" data-schedule-date></div>
        <div data-schedule-mode="hourly"><input data-schedule-hour-values></div>
        <input data-schedule-raw>
        <code data-schedule-preview></code>
        <input type="hidden" id="visibility" name="visibility" data-template-variable-key="visible_home">
      </div>
      <div data-collection-field-wrapper="true">
        <input id="priority" data-template-variable-key="hub_priority" data-requires-any-of-template-keys="visible_home">
      </div>
    </div>`
  const hidden = document.getElementById('visibility')
  hidden.value = value
  initScheduleBuilders(document)
  return {
    hidden,
    mode: document.querySelector('[data-schedule-mode-select]'),
    raw: document.querySelector('[data-schedule-raw]'),
    preview: document.querySelector('[data-schedule-preview]')
  }
}

beforeEach(() => document.body.replaceChildren())

describe('visibility schedules reuse the schedule builder', () => {
  it.each([
    ['true', 'true'], ['false', 'false'], ['False', 'false'],
    ['range(02/01-02/21)', 'range'], ['weekly(mon|fri)', 'weekly'],
    ['monthly(1|21-last)', 'monthly'], ['yearly(02/14)', 'yearly'],
    ['date(02/14/2027)', 'date'], ['hourly(17-04)', 'hourly'],
    ['daily', 'daily'], ['never', 'never'], ['non_existing', 'non_existing'],
    ['all[weekly(friday), hourly(17)]', 'custom']
  ])('restores %s', (value, expectedMode) => {
    const { hidden, mode, preview } = mountBuilder(value)
    expect(mode.value).toBe(expectedMode)
    expect(hidden.value).toBe(value === 'False' ? 'false' : value)
    expect(preview.textContent).toBe(hidden.value)
  })

  it('switches between a boolean and a range, and restores reset values', () => {
    const { hidden, mode } = mountBuilder('false')
    mode.value = 'range'
    mode.dispatchEvent(new Event('change', { bubbles: true }))
    const range = document.querySelector('[data-schedule-range-values]')
    range.value = '02/01-02/21'
    range.dispatchEvent(new Event('input', { bubbles: true }))
    expect(hidden.value).toBe('range(02/01-02/21)')
    mode.value = 'true'
    mode.dispatchEvent(new Event('change', { bubbles: true }))
    expect(hidden.value).toBe('true')
    hidden.value = 'false'
    hidden.dispatchEvent(new Event('change', { bubbles: true }))
    expect(mode.value).toBe('false')
    expect(hidden.value).toBe('false')
  })

  it('accepts advanced boolean and schedule values', () => {
    const { hidden, mode, raw } = mountBuilder('true')
    for (const [value, expectedMode] of [['false', 'false'], ['weekly(mon|fri)', 'weekly'], ['all[weekly(friday), hourly(17)]', 'custom']]) {
      raw.value = value
      raw.dispatchEvent(new Event('change', { bubbles: true }))
      expect(mode.value).toBe(expectedMode)
      expect(hidden.value).toBe(value)
    }
  })

  it('updates hub-priority availability when visibility changes', () => {
    const { mode, raw } = mountBuilder('false')
    setupCollectionTemplateFieldRules(document)
    const priority = document.getElementById('priority')
    expect(priority.disabled).toBe(true)
    for (const [value, disabled] of [['true', false], ['never', true], ['daily', false], ['false', true]]) {
      mode.value = value
      mode.dispatchEvent(new Event('change', { bubbles: true }))
      expect(priority.disabled).toBe(disabled)
    }
    raw.value = 'all[weekly(friday), hourly(17)]'
    raw.dispatchEvent(new Event('change', { bubbles: true }))
    expect(priority.disabled).toBe(false)
  })

  it('keeps ordinary update schedules free of boolean modes', () => {
    const { hidden, mode } = mountBuilder('daily', false)
    expect(mode.querySelector('option[value="true"]')).toBeNull()
    expect(mode.querySelector('option[value="false"]')).toBeNull()
    expect(hidden.value).toBe('daily')
  })
})
