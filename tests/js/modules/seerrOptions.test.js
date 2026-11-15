// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { handleSeerrInput, updateDuplicateWarning, updateSeerrSwitch, updateTierOverrides } from '../../../static/local-js/modules/seerrOptions.js'

beforeEach(() => { document.body.innerHTML = '' })

describe('Seerr request controls', () => {
  it('distinguishes inheritance from an explicit false value', () => {
    document.body.innerHTML = `<div data-seerr-switch>
      <input type="checkbox" data-seerr-explicit>
      <input type="checkbox" data-seerr-value>
      <input data-seerr-switch-output>
    </div>`
    const row = document.querySelector('[data-seerr-switch]')
    const explicit = row.querySelector('[data-seerr-explicit]')
    const toggle = row.querySelector('[data-seerr-value]')
    const output = row.querySelector('[data-seerr-switch-output]')
    updateSeerrSwitch(row)
    expect(output.value).toBe('')
    explicit.checked = true
    updateSeerrSwitch(row)
    expect(output.value).toBe('false')
    toggle.checked = true
    updateSeerrSwitch(row)
    expect(output.value).toBe('true')
    explicit.checked = false
    updateSeerrSwitch(row)
    expect(output.value).toBe('')
  })

  it('merges tier edits without dropping unknown imported fields', () => {
    document.body.innerHTML = `<details data-seerr-overrides>
      <textarea data-seerr-json>{"standard":{"future":false},"4k":{"quality_profile":4},"future_tier":{"keep":true}}</textarea>
      <input data-seerr-tier="standard" data-seerr-field="server_id" value="1">
      <input data-seerr-tier="standard" data-seerr-field="quality_profile" value="HD-1080p">
      <input data-seerr-tier="4k" data-seerr-field="quality_profile" value="4">
      <input data-seerr-tier="4k" data-seerr-field="root_folder" value="/movies-4k">
    </details>`
    updateTierOverrides(document.querySelector('details'))
    expect(JSON.parse(document.querySelector('textarea').value)).toEqual({
      standard: { server_id: 1, quality_profile: 'HD-1080p', future: false },
      '4k': { quality_profile: 4, root_folder: '/movies-4k' },
      future_tier: { keep: true }
    })
    document.querySelector('[data-seerr-field="server_id"]').value = ''
    updateTierOverrides(document.querySelector('details'))
    expect(JSON.parse(document.querySelector('textarea').value).standard).not.toHaveProperty('server_id')
  })

  it('retains malformed JSON so validation can report it', () => {
    document.body.innerHTML = '<details data-seerr-overrides><textarea data-seerr-json>invalid</textarea><input data-seerr-tier="standard" data-seerr-field="server_id" value="1"></details>'
    updateTierOverrides(document.querySelector('details'))
    expect(document.querySelector('textarea').value).toBe('invalid')
  })

  it('updates JSON before bubbling input listeners serialize an autosave', () => {
    document.body.innerHTML = '<details data-seerr-overrides><textarea data-seerr-json></textarea><input data-seerr-tier="4k" data-seerr-field="server_id" value="2"></details>'
    let saved
    document.body.addEventListener('input', () => { saved = document.querySelector('textarea').value }, { once: true })
    document.querySelector('input').dispatchEvent(new Event('input', { bubbles: true }))
    expect(JSON.parse(saved)).toEqual({ '4k': { server_id: 2 } })
  })

  it('warns about direct add_missing and respects explicit false overrides', () => {
    document.body.innerHTML = `<select name="mov-library_movies-attribute_radarr_add_missing"><option value="true">true</option></select>
      <div data-seerr-options>
        <input data-seerr-switch-output name="mov-library_movies-template_collection_imdb_seerr_add_missing" value="true">
        <input data-seerr-switch-output value="false">
        <div data-seerr-duplicate-warning hidden></div>
      </div>`
    const root = document.querySelector('[data-seerr-options]')
    updateDuplicateWarning(root)
    expect(root.querySelector('[data-seerr-duplicate-warning]').hidden).toBe(false)
    root.querySelector('[data-seerr-switch-output]').value = 'false'
    updateDuplicateWarning(root)
    expect(root.querySelector('[data-seerr-duplicate-warning]').hidden).toBe(true)
    const keyed = document.createElement('input')
    keyed.dataset.seerrKeyedOutput = ''
    keyed.name = 'mov-library_movies-template_collection_imdb_seerr_add_existing_popular'
    keyed.value = 'true'
    root.appendChild(keyed)
    updateDuplicateWarning(root)
    expect(root.querySelector('[data-seerr-duplicate-warning]').hidden).toBe(false)
  })

  it('supports controls inserted after the page loads', () => {
    document.body.innerHTML = '<div data-seerr-switch><input type="checkbox" data-seerr-explicit checked><input type="checkbox" data-seerr-value checked><input data-seerr-switch-output></div>'
    handleSeerrInput({ target: document.querySelector('[data-seerr-value]') })
    expect(document.querySelector('[data-seerr-switch-output]').value).toBe('true')
  })

  it('edits keyed options and explicitly clears removed keys during partial saves', () => {
    document.body.innerHTML = `<div data-seerr-options>
      <textarea data-seerr-keyed data-seerr-prefix="mov-library_1-template_collection_imdb_" data-seerr-suffix=""></textarea>
      <input type="hidden" name="mov-library_1-template_collection_imdb_seerr_add_missing_popular" data-seerr-keyed-output value="true">
      <div data-seerr-keyed-error></div>
    </div>`
    const textarea = document.querySelector('textarea')
    textarea.value = JSON.stringify({ seerr_instance_top: '4k', seerr_add_existing_top: false })
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.getElementsByName('mov-library_1-template_collection_imdb_seerr_add_missing_popular')[0].value).toBe('')
    expect(document.getElementsByName('mov-library_1-template_collection_imdb_seerr_instance_top')[0].value).toBe('4k')
    expect(document.getElementsByName('mov-library_1-template_collection_imdb_seerr_add_existing_top')[0].value).toBe('false')
    textarea.value = 'invalid'
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    expect(textarea.checkValidity()).toBe(false)
    expect(document.getElementsByName('mov-library_1-template_collection_imdb_seerr_instance_top')[0].value).toBe('4k')
  })
})
