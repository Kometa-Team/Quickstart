// Unit tests for the Commonsense content-rating overlay preview
// helpers extracted from static/local-js/overlayHandler.js.
//
// These are pure cfg-in / value-out functions: they read from
// cfg.container (an HTMLElement) and either return a derived value or
// mutate a single input. No listeners, no module state.

import { describe, it, expect } from 'vitest'
import {
  isCommonsenseContentRatingOverlay,
  getCommonsensePreviewTextInput,
  getCommonsensePreviewOptions,
  pickDefaultCommonsensePreviewValue,
  getCommonsensePreviewValue,
  setCommonsensePreviewValue,
  normalizeCommonsensePreviewText
} from '../../../static/local-js/modules/commonsenseContentRatingPreview.js'

// A container shaped like the real thing: `data-overlay-template` on the
// wrapper, a hidden `[name="<template>[text]"]` input, and one or more
// `[name="<template>[use_<age>]"]` checkboxes wrapped in .form-check
// with a .form-check-label sibling.
const makeContainer = ({ template = 'ov_commonsense', text = '', ages = [] } = {}) => {
  const container = document.createElement('div')
  container.dataset.overlayTemplate = template
  const textInput = document.createElement('input')
  textInput.type = 'text'
  textInput.name = `${template}[text]`
  textInput.value = text
  container.appendChild(textInput)
  ages.forEach(({ age, enabled = false, label }) => {
    const wrap = document.createElement('div')
    wrap.className = 'form-check'
    const cb = document.createElement('input')
    cb.type = 'checkbox'
    cb.name = `${template}[use_${age}]`
    cb.checked = enabled
    const lab = document.createElement('label')
    lab.className = 'form-check-label'
    lab.textContent = label ?? `Use ${age}+`
    wrap.appendChild(cb)
    wrap.appendChild(lab)
    container.appendChild(wrap)
  })
  return container
}

const cfgFor = (opts) => ({
  id: 'overlay_content_rating_commonsense',
  container: makeContainer(opts)
})

describe('isCommonsenseContentRatingOverlay', () => {
  it('matches the exact server-rendered id', () => {
    expect(isCommonsenseContentRatingOverlay({ id: 'overlay_content_rating_commonsense' })).toBe(true)
  })
  it('is false for other overlay ids', () => {
    expect(isCommonsenseContentRatingOverlay({ id: 'overlay_content_rating_us' })).toBe(false)
  })
  it('is false for null/undefined/missing id', () => {
    expect(isCommonsenseContentRatingOverlay(null)).toBe(false)
    expect(isCommonsenseContentRatingOverlay({})).toBe(false)
    expect(isCommonsenseContentRatingOverlay({ id: '  ' })).toBe(false)
  })
})

describe('getCommonsensePreviewTextInput', () => {
  it('returns the [name="<template>[text]"] input', () => {
    const cfg = cfgFor({ template: 'ov1', text: 'PG' })
    const input = getCommonsensePreviewTextInput(cfg)
    expect(input?.name).toBe('ov1[text]')
    expect(input?.value).toBe('PG')
  })
  it('returns null when container is missing or has no template dataset', () => {
    expect(getCommonsensePreviewTextInput(null)).toBeNull()
    const bareContainer = document.createElement('div')
    expect(getCommonsensePreviewTextInput({ container: bareContainer })).toBeNull()
  })
})

describe('getCommonsensePreviewOptions', () => {
  it('sorts numerically then alphabetically and strips "Use " from labels', () => {
    const cfg = cfgFor({ ages: [
      { age: '13', label: 'Use 13+' },
      { age: '3', label: 'Use 3+', enabled: true },
      { age: '18', label: 'Use 18+' },
      { age: '7', label: 'Use 7+' }
    ]})
    const opts = getCommonsensePreviewOptions(cfg)
    expect(opts.map(o => o.value)).toEqual(['3', '7', '13', '18'])
    expect(opts.map(o => o.label)).toEqual(['3+', '7+', '13+', '18+'])
    expect(opts.find(o => o.value === '3').enabled).toBe(true)
  })
  it('pushes NaN sort values to the end', () => {
    const cfg = cfgFor({ ages: [
      { age: 'nr', label: 'Use NR' },
      { age: '10', label: 'Use 10+' }
    ]})
    const opts = getCommonsensePreviewOptions(cfg)
    expect(opts[0].value).toBe('10')
    expect(opts[1].value).toBe('nr')
  })
  it('returns [] when container / template is missing', () => {
    expect(getCommonsensePreviewOptions({})).toEqual([])
    const bare = document.createElement('div')
    expect(getCommonsensePreviewOptions({ container: bare })).toEqual([])
  })
})

describe('pickDefaultCommonsensePreviewValue', () => {
  it('prefers the first enabled option', () => {
    const cfg = cfgFor({ ages: [
      { age: '13' },
      { age: '18', enabled: true },
      { age: '7' }
    ]})
    expect(pickDefaultCommonsensePreviewValue(cfg)).toBe('18')
  })
  it('falls back to the first option when nothing is enabled', () => {
    const cfg = cfgFor({ ages: [{ age: '13' }, { age: '18' }] })
    expect(pickDefaultCommonsensePreviewValue(cfg)).toBe('13')
  })
  it('returns "" when there are no options at all', () => {
    expect(pickDefaultCommonsensePreviewValue(cfgFor({ ages: [] }))).toBe('')
  })
})

describe('getCommonsensePreviewValue', () => {
  it('returns the current text when it matches an option', () => {
    const cfg = cfgFor({ text: '13', ages: [{ age: '7' }, { age: '13' }] })
    expect(getCommonsensePreviewValue(cfg)).toBe('13')
  })
  it('self-heals: rewrites the input to the default when current value is invalid', () => {
    const cfg = cfgFor({ text: 'garbage', ages: [{ age: '10', enabled: true }, { age: '18' }] })
    expect(getCommonsensePreviewValue(cfg)).toBe('10')
    expect(getCommonsensePreviewTextInput(cfg).value).toBe('10')
  })
  it('does not blow up when the input is missing entirely', () => {
    const container = document.createElement('div')
    container.dataset.overlayTemplate = 'ov'
    expect(getCommonsensePreviewValue({ container })).toBe('')
  })
})

describe('setCommonsensePreviewValue', () => {
  it('writes a trimmed value to the input', () => {
    const cfg = cfgFor({ ages: [{ age: '7' }] })
    setCommonsensePreviewValue(cfg, '  7  ')
    expect(getCommonsensePreviewTextInput(cfg).value).toBe('7')
  })
  it('is a no-op when the input is missing', () => {
    expect(() => setCommonsensePreviewValue({}, 'anything')).not.toThrow()
  })
})

describe('normalizeCommonsensePreviewText', () => {
  it('trims whitespace', () => {
    expect(normalizeCommonsensePreviewText('  13  ')).toBe('13')
  })
  it('upper-cases the "nr" sentinel (case-insensitively)', () => {
    expect(normalizeCommonsensePreviewText('nr')).toBe('NR')
    expect(normalizeCommonsensePreviewText('Nr')).toBe('NR')
    expect(normalizeCommonsensePreviewText('NR')).toBe('NR')
  })
  it('passes through other values unchanged', () => {
    expect(normalizeCommonsensePreviewText('13')).toBe('13')
    expect(normalizeCommonsensePreviewText('PG-13')).toBe('PG-13')
  })
  it('returns "" for empty / null / undefined', () => {
    expect(normalizeCommonsensePreviewText('')).toBe('')
    expect(normalizeCommonsensePreviewText(null)).toBe('')
    expect(normalizeCommonsensePreviewText(undefined)).toBe('')
  })
})
