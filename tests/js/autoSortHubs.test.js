import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearAutoSortHubs, initAutoSortHubs } from '../../static/local-js/modules/autoSortHubs.js'

afterEach(() => document.body.replaceChildren())

describe.each(['auto_sort_hubs', 'mov-library_movies-top_level_auto_sort_hubs', 'sho-library_tv-top_level_auto_sort_hubs'])('clearing %s', id => {
  it.each(['alpha', 'bogus', ''])('clears the submitted value %s while leaving other settings intact', value => {
    document.body.innerHTML = `
      <form>
        <select id="${id}" disabled><option value="">Disabled / Not Set</option><option selected value="${value}">${value}</option></select>
        <input type="hidden" id="${id}_preserved" name="${id}" value="${value}">
        <button type="button" data-clear-auto-sort-hubs="${id}">Clear saved value</button>
        <input name="other_library_auto_sort_hubs" value="random">
        <input name="asset_directory[movies]" value="/assets/movies">
      </form>`
    const form = document.querySelector('form')
    const changed = vi.fn()
    form.addEventListener('change', changed)
    clearAutoSortHubs(document.querySelector('button'))
    expect(document.getElementById(id).disabled).toBe(true)
    expect(document.getElementById(id).value).toBe('')
    expect(new FormData(form).get(id)).toBe('')
    expect(new FormData(form).get('other_library_auto_sort_hubs')).toBe('random')
    expect(new FormData(form).get('asset_directory[movies]')).toBe('/assets/movies')
    expect(changed).toHaveBeenCalledOnce()
  })
})

it('handles a dynamically loaded library fragment and nested button content', () => {
  initAutoSortHubs()
  document.body.innerHTML = '<select id="hub"><option value=""></option><option value="alpha" selected>Alpha</option></select><input id="hub_preserved" value="alpha"><button data-clear-auto-sort-hubs="hub"><span>Clear saved value</span></button>'
  document.querySelector('span').click()
  expect(document.getElementById('hub_preserved').value).toBe('')
})
