import { beforeEach, describe, expect, it } from 'vitest'
import { enforceUniqueRatingSlots, getRatingChoice, getRatingSourceService } from '../../../static/local-js/modules/ratingSources.js'

let selects
let container

beforeEach(() => {
  document.body.innerHTML = '<div id="ratings"></div>'
  container = document.getElementById('ratings')
  selects = ['user', 'critic', 'audience'].map(value => {
    const select = document.createElement('select')
    select.dataset.default = value
    ;['', 'none', 'critic', 'audience', 'user', 'imdb', 'tmdb', 'floppy'].forEach(source => select.add(new Option(source || 'None', source)))
    select.value = value
    const group = document.createElement('div')
    group.className = 'input-group'
    group.appendChild(select)
    container.appendChild(group)
    return select
  })
})

describe('rating slot choices', () => {
  it.each(['', 'none'])('honors explicit None value %j instead of the original default', value => {
    selects.forEach(select => { select.value = value })
    enforceUniqueRatingSlots(selects, container)
    expect(selects.map(getRatingChoice)).toEqual([value, value, value])
    selects.forEach(select => expect(Array.from(select.options).some(option => option.disabled)).toBe(false))
  })

  it('only falls back to a default when the input itself has no value', () => {
    expect(getRatingChoice({ dataset: { default: 'critic' } })).toBe('critic')
    expect(getRatingChoice(null)).toBe('')
  })

  it('keeps selected values enabled and prevents reuse in other slots', () => {
    enforceUniqueRatingSlots(selects, container)
    selects.forEach(select => {
      expect(select.selectedOptions[0].disabled).toBe(false)
      expect(select.querySelector('option[value=""]').disabled).toBe(false)
      expect(select.querySelector('option[value="imdb"]').disabled).toBe(false)
      selects.filter(other => other !== select).forEach(other => expect(other.querySelector(`option[value="${select.value}"]`).disabled).toBe(true))
    })
  })

  it('releases a source immediately after clearing or changing its slot', () => {
    enforceUniqueRatingSlots(selects, container)
    selects[0].value = ''
    selects[1].value = 'imdb'
    enforceUniqueRatingSlots(selects, container)
    selects.forEach(select => {
      expect(select.querySelector('option[value="user"]').disabled).toBe(false)
      expect(select.querySelector('option[value="critic"]').disabled).toBe(false)
    })
    expect(selects[2].querySelector('option[value="imdb"]').disabled).toBe(true)
  })

  it('warns on imported duplicate values without disabling the selected values', () => {
    selects[0].value = 'imdb'
    selects[1].value = 'imdb'
    enforceUniqueRatingSlots(selects, container)
    enforceUniqueRatingSlots(selects, container)
    expect(container.querySelectorAll('.rating-unique-warning')).toHaveLength(1)
    expect(selects[0].selectedOptions[0].disabled).toBe(false)
    expect(selects[1].selectedOptions[0].disabled).toBe(false)
    selects[1].value = ''
    enforceUniqueRatingSlots(selects, container)
    expect(container.querySelector('.rating-unique-warning')).toBeNull()
  })
})

describe('rating provider requirements', () => {
  it.each([
    ['mdb', 'mdblist'], ['mdb_myanimelist', 'mdblist'], ['mdb_tomatoes', 'mdblist'],
    ['omdb', 'omdb'], ['omdb_tomatoes', 'omdb'], ['anidb', 'anidb'], ['anidb_average', 'anidb'],
    ['mal', 'mal'], ['mal_japanese', 'mal'], ['tmdb', 'tmdb'], ['floppy', 'floppy'],
    ['user', 'plex'], ['critic', 'plex'], ['audience', 'plex'], ['plex_tomatoes', 'plex'],
    ['serializd', 'serializd'], ['imdb', null], ['', null]
  ])('uses the provider for %s, independently of its badge', (source, service) => {
    expect(getRatingSourceService(source)).toBe(service)
  })
})
