import { beforeEach, describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const source = readFileSync(resolve(__dirname, '../../static/local-js/025-libraries.js'), 'utf8')
const omissionSource = source.slice(source.indexOf('function shouldOmitDefaultFieldFromLibraryPayload'), source.indexOf('function buildPayloadFromCard'))
const shouldOmit = new Function('isInternalTemplateMetadataField', 'isCollectionSectionFieldConfigured', `${omissionSource}; return shouldOmitDefaultFieldFromLibraryPayload`)(() => false, () => false)

beforeEach(() => { document.body.replaceChildren() })

describe.each(['movie', 'show', 'episode'])('%s rating payload completeness', builder => {
  it.each(['rating1', 'rating1_image', 'rating2', 'rating2_image', 'rating3', 'rating3_image'])('keeps %s even when it matches the Quickstart default', key => {
    const field = document.createElement('select')
    field.name = `mov-library_1-${builder}-template_overlay_ratings[${key}]`
    field.dataset.default = key.endsWith('_image') ? 'imdb' : 'critic'
    field.add(new Option('None', ''))
    field.add(new Option(field.dataset.default, field.dataset.default))
    field.value = field.dataset.default
    expect(shouldOmit(field)).toBe(false)
  })

  it.each(['', 'none'])('keeps an explicitly disabled slot %j', value => {
    const field = document.createElement('input')
    field.name = `mov-library_1-${builder}-template_overlay_ratings[rating3]`
    field.dataset.default = 'audience'
    field.value = value
    expect(shouldOmit(field)).toBe(false)
  })

  it('still omits default styling and placement fields', () => {
    for (const key of ['rating1_font', 'rating2_horizontal_offset', 'rating3_vertical_offset', 'rating_alignment']) {
      const field = document.createElement('input')
      field.name = `mov-library_1-${builder}-template_overlay_ratings[${key}]`
      field.dataset.default = 'default'
      field.value = 'default'
      expect(shouldOmit(field)).toBe(true)
    }
  })
})
