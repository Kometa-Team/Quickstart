// Tests for ImageHandler.getLibraryOverlays.
//
// This is the ~130-line method previously excluded from
// imageHandler.test.js (see note there). It walks a specific wizard-DOM
// shape to build the array of overlays the user has enabled, plus their
// template variables.
//
// DOM contract (reverse-engineered from the source + templates):
//
//   #<libraryId>-overlays
//     input[type="checkbox"][name="<libraryId>-<type>-overlay_<suffix>"]:checked
//       (optional) .template-toggle-group ancestor with
//         data-overlay-template="<libraryId>-<type>-template_overlay_<suffix>"
//         containing template-variable inputs:
//           name="<templatePrefix>[<varName>]"
//           element types: select, checkbox, text, number, color
//
//   #<libraryId>-ContentRatingOverlays
//     .overlay-group[data-type="<type>"]
//       input.template-parent-toggle[data-radio-group="true"]:checked
//         value=<ratingCode> (e.g., "nz", "commonsense")
//       select[name="<libraryId>-<type>-template_overlay_content_rating_<code>[color]"]
//       input[name="<libraryId>-<type>-template_overlay_content_rating_<code>[horizontal_offset]"]
//       input[name="<libraryId>-<type>-template_overlay_content_rating_<code>[vertical_offset]"]
//
//     For value="commonsense" additionally:
//       .template-toggle-group[data-overlay-id="overlay_content_rating_commonsense"]
//         [data-library-id="<libraryId>"]
//         [data-overlay-type="<type>"]
//         data-overlay-template="<templateName>"
//         [name="<templateName>[<key>]"] for keys:
//           post_text, addon_offset, horizontal_offset, vertical_offset
//
// Special carve-outs the tests verify:
// - `text` is dropped when the overlay id is overlay_video_format /
//   overlay_aspect OR suffix is video_format / aspect.
// - For content_rating_commonsense: text/font/font_size/font_color are
//   stripped from templateVariables.

import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

beforeAll(async () => {
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'debug').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})

  window.showToast = vi.fn()
  window.updateFormData = vi.fn()
  globalThis.showToast = window.showToast
  globalThis.updateFormData = window.updateFormData

  document.body.innerHTML = ''
  await import('../../static/local-js/imageHandler.js')
})

beforeEach(() => {
  document.body.innerHTML = ''
})

afterEach(() => {
  vi.restoreAllMocks()
  // Restore silent console spies after restoreAllMocks nukes them.
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'debug').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

// -----------------------------------------------------------------------
// Fixture builders. Keep them DRY and readable — you'll see them used
// many times below with just the interesting knob varied.
// -----------------------------------------------------------------------

/**
 * Build a #<libraryId>-overlays container hosting a single overlay
 * checkbox (checked by default) with an optional template group.
 *
 * @param {object} opts
 * @param {string} opts.libraryId    e.g. "mov-library_1"
 * @param {string} opts.type         "movie" | "show" | "episode"
 * @param {string} opts.suffix       e.g. "ribbon" (produces overlay_ribbon)
 * @param {boolean} [opts.checked]   defaults to true
 * @param {object|null} [opts.templateVars]
 *        map of {varName: {type, value}} where type is 'text' | 'number'
 *        | 'checkbox' | 'color' | 'select'
 * @param {string|null} [opts.overrideTemplateName]
 *        if provided, sets data-overlay-template on the group instead of
 *        letting the code derive it from the checkbox name.
 * @param {boolean} [opts.wrapInTemplateGroup]  defaults to true
 */
function buildOverlayCheckbox ({
  libraryId,
  type,
  suffix,
  checked = true,
  templateVars = null,
  overrideTemplateName = null,
  wrapInTemplateGroup = true
}) {
  const checkboxName = `${libraryId}-${type}-overlay_${suffix}`
  const templateName = overrideTemplateName || `${libraryId}-${type}-template_overlay_${suffix}`

  const varsMarkup = templateVars
    ? Object.entries(templateVars).map(([varName, spec]) => {
        const nm = `${templateName}[${varName}]`
        if (spec.type === 'select') {
          return `<select name="${nm}"><option value="${spec.value}" selected>${spec.value}</option></select>`
        }
        if (spec.type === 'checkbox') {
          return `<input type="checkbox" name="${nm}" value="${spec.value ?? 'true'}"${spec.checked ? ' checked' : ''}>`
        }
        return `<input type="${spec.type}" name="${nm}" value="${spec.value ?? ''}">`
      }).join('\n')
    : ''

  const checkboxMarkup = `<input type="checkbox" name="${checkboxName}"${checked ? ' checked' : ''}>`

  if (!wrapInTemplateGroup) return checkboxMarkup

  return `
    <div class="template-toggle-group" data-overlay-template="${templateName}">
      ${checkboxMarkup}
      ${varsMarkup}
    </div>
  `
}

function mountOverlaysContainer (libraryId, innerHTML) {
  const wrap = document.createElement('div')
  wrap.id = `${libraryId}-overlays`
  wrap.innerHTML = innerHTML
  document.body.appendChild(wrap)
  return wrap
}

function mountContentRatingContainer (libraryId, type, innerHTML) {
  const wrap = document.createElement('div')
  wrap.id = `${libraryId}-ContentRatingOverlays`
  wrap.innerHTML = `<div class="overlay-group" data-type="${type}">${innerHTML}</div>`
  document.body.appendChild(wrap)
  return wrap
}

// -----------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------

describe('ImageHandler.getLibraryOverlays: setup', () => {
  it('is exposed on window.ImageHandler', () => {
    expect(typeof window.ImageHandler.getLibraryOverlays).toBe('function')
  })
})

describe('ImageHandler.getLibraryOverlays: empty / missing inputs', () => {
  it('returns [] when no overlays container exists', () => {
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result).toEqual([])
  })

  it('returns [] when the overlays container has no checked checkboxes', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      checked: false
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result).toEqual([])
  })

  it('skips overlays whose name does not include the requested `-<type>-`', () => {
    // Container has a checkbox for a `-show-` overlay but we ask for `movie`.
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'show',
      suffix: 'ribbon'
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result).toEqual([])
  })

  it('skips checkboxes whose name does not match /overlay_[A-Za-z0-9_]+/', () => {
    // Craft a checkbox that is checked and has the right library/type
    // prefix but lacks the overlay_ segment.
    const html = `
      <input type="checkbox" name="mov-library_1-movie-something_else" checked>
    `
    mountOverlaysContainer('mov-library_1', html)
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result).toEqual([])
  })
})

describe('ImageHandler.getLibraryOverlays: single overlay, no template vars', () => {
  it('returns a bare {id, template_variables: {}} entry when no vars are present', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      templateVars: {}
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result).toHaveLength(1)
    expect(result[0]).toEqual({
      id: 'overlay_ribbon',
      template_variables: {}
    })
  })
})

describe('ImageHandler.getLibraryOverlays: template variable types', () => {
  it('captures a text variable as-is', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      templateVars: { text: { type: 'text', value: 'HELLO' } }
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].template_variables).toEqual({ text: 'HELLO' })
  })

  it('captures a numeric variable as a JS number', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      templateVars: { horizontal_offset: { type: 'number', value: '42' } }
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].template_variables).toEqual({ horizontal_offset: 42 })
  })

  it('coerces an empty numeric input to 0 (Number("") is finite)', () => {
    // Note: for <input type="number"> the DOM refuses to hold non-numeric
    // strings — a value like "abc" gets normalized to "". Number("") is
    // 0, which is finite, so we take the finite branch. The `el.value`
    // fallback string in the source is effectively defensive dead code
    // for a real type=number input, so we don't try to exercise it here.
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      templateVars: { horizontal_offset: { type: 'number', value: '' } }
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].template_variables).toEqual({ horizontal_offset: 0 })
  })

  it('captures a color variable', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      templateVars: { color: { type: 'color', value: '#ff0000' } }
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].template_variables).toEqual({ color: '#ff0000' })
  })

  it('captures a checkbox variable as its value string when checked', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      templateVars: {
        use_edition: { type: 'checkbox', value: 'yes', checked: true }
      }
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].template_variables).toEqual({ use_edition: 'yes' })
  })

  it('captures a checkbox variable as "true" when checked and value is empty', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      templateVars: {
        use_edition: { type: 'checkbox', value: '', checked: true }
      }
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].template_variables).toEqual({ use_edition: 'true' })
  })

  it('captures a checkbox variable as "false" when unchecked', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      templateVars: {
        use_edition: { type: 'checkbox', value: 'yes', checked: false }
      }
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].template_variables).toEqual({ use_edition: 'false' })
  })

  it('captures a select variable value', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      templateVars: { position: { type: 'select', value: 'top-left' } }
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].template_variables).toEqual({ position: 'top-left' })
  })

  it('captures multiple template variables side-by-side', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      templateVars: {
        text: { type: 'text', value: 'HELLO' },
        horizontal_offset: { type: 'number', value: '10' },
        color: { type: 'color', value: '#0000ff' }
      }
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].template_variables).toEqual({
      text: 'HELLO',
      horizontal_offset: 10,
      color: '#0000ff'
    })
  })
})

describe('ImageHandler.getLibraryOverlays: text-suppression carve-outs', () => {
  it('does not emit text for suffix=video_format', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'video_format',
      templateVars: {
        text: { type: 'text', value: 'ignored' },
        color: { type: 'color', value: '#ff0000' }
      }
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].id).toBe('overlay_video_format')
    expect(result[0].template_variables).toEqual({ color: '#ff0000' })
    expect(result[0].template_variables.text).toBeUndefined()
  })

  it('does not emit text for suffix=aspect', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'aspect',
      templateVars: {
        text: { type: 'text', value: 'ignored' }
      }
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].id).toBe('overlay_aspect')
    expect(result[0].template_variables.text).toBeUndefined()
  })

  it('DOES emit text for a normal overlay like ribbon', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      templateVars: {
        text: { type: 'text', value: 'BADGE' }
      }
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].template_variables).toEqual({ text: 'BADGE' })
  })

  it('strips text/font/font_size/font_color for suffix=content_rating_commonsense', () => {
    // Note: content_rating_commonsense overlays are NORMALLY emitted via
    // the ContentRating radio flow, but the checkbox flow guards this
    // suffix explicitly too. Cover both.
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'content_rating_commonsense',
      templateVars: {
        text: { type: 'text', value: 'x' },
        font: { type: 'text', value: 'y' },
        font_size: { type: 'number', value: '42' },
        font_color: { type: 'color', value: '#000000' },
        horizontal_offset: { type: 'number', value: '5' }
      }
    }))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].id).toBe('overlay_content_rating_commonsense')
    expect(result[0].template_variables).toEqual({ horizontal_offset: 5 })
  })
})

describe('ImageHandler.getLibraryOverlays: content-rating radio flow', () => {
  it('emits a content_rating_<code> overlay when a radio is selected', () => {
    mountContentRatingContainer('mov-library_1', 'movie', `
      <input type="radio" class="template-parent-toggle"
             data-radio-group="true" value="nz" checked>
      <select name="mov-library_1-movie-template_overlay_content_rating_nz[color]">
        <option value="red" selected>red</option>
      </select>
    `)
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result).toHaveLength(1)
    expect(result[0]).toEqual({
      id: 'overlay_content_rating_nz',
      template_variables: { color: 'red' }
    })
  })

  it('captures horizontal_offset and vertical_offset when present', () => {
    mountContentRatingContainer('mov-library_1', 'movie', `
      <input type="radio" class="template-parent-toggle"
             data-radio-group="true" value="us" checked>
      <select name="mov-library_1-movie-template_overlay_content_rating_us[color]">
        <option value="green" selected>green</option>
      </select>
      <input type="number"
             name="mov-library_1-movie-template_overlay_content_rating_us[horizontal_offset]"
             value="12">
      <input type="number"
             name="mov-library_1-movie-template_overlay_content_rating_us[vertical_offset]"
             value="34">
    `)
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].template_variables).toEqual({
      color: 'green',
      horizontal_offset: 12,
      vertical_offset: 34
    })
  })

  it('falls back to raw string for non-finite numeric offsets', () => {
    mountContentRatingContainer('mov-library_1', 'movie', `
      <input type="radio" class="template-parent-toggle"
             data-radio-group="true" value="us" checked>
      <input type="text"
             name="mov-library_1-movie-template_overlay_content_rating_us[horizontal_offset]"
             value="not-a-number">
    `)
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result[0].template_variables.horizontal_offset).toBe('not-a-number')
  })

  it('does not emit a content-rating overlay when no radio is checked', () => {
    mountContentRatingContainer('mov-library_1', 'movie', `
      <input type="radio" class="template-parent-toggle"
             data-radio-group="true" value="nz">
    `)
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result).toEqual([])
  })

  it('only picks radios inside the .overlay-group with matching data-type', () => {
    // Put a radio in a "show" overlay-group even though we ask for movie.
    mountContentRatingContainer('mov-library_1', 'show', `
      <input type="radio" class="template-parent-toggle"
             data-radio-group="true" value="nz" checked>
    `)
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result).toEqual([])
  })
})

describe('ImageHandler.getLibraryOverlays: content_rating_commonsense special path', () => {
  it('pulls additional post_text/addon_offset/offset fields from the commonsense template group', () => {
    // First: the radio + basic color/offset block.
    mountContentRatingContainer('mov-library_1', 'movie', `
      <input type="radio" class="template-parent-toggle"
             data-radio-group="true" value="commonsense" checked>
      <select name="mov-library_1-movie-template_overlay_content_rating_commonsense[color]">
        <option value="blue" selected>blue</option>
      </select>
      <input type="number"
             name="mov-library_1-movie-template_overlay_content_rating_commonsense[horizontal_offset]"
             value="5">
    `)
    // Second: the separate template-toggle-group container the special
    // path looks up via the [data-overlay-id][data-library-id][data-overlay-type]
    // triple-attribute selector.
    const commonsenseGroup = document.createElement('div')
    commonsenseGroup.className = 'template-toggle-group'
    commonsenseGroup.dataset.overlayId = 'overlay_content_rating_commonsense'
    commonsenseGroup.dataset.libraryId = 'mov-library_1'
    commonsenseGroup.dataset.overlayType = 'movie'
    commonsenseGroup.dataset.overlayTemplate = 'commonsense-tpl'
    commonsenseGroup.innerHTML = `
      <input type="text" name="commonsense-tpl[post_text]" value="hello">
      <input type="number" name="commonsense-tpl[addon_offset]" value="7">
      <input type="number" name="commonsense-tpl[horizontal_offset]" value="99">
      <input type="number" name="commonsense-tpl[vertical_offset]" value="100">
    `
    document.body.appendChild(commonsenseGroup)

    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result).toHaveLength(1)
    // The extras from the commonsense group OVERRIDE the offsets from
    // the basic block (since maybeSet runs after setNum).
    expect(result[0]).toEqual({
      id: 'overlay_content_rating_commonsense',
      template_variables: {
        color: 'blue',
        post_text: 'hello',
        addon_offset: 7,
        horizontal_offset: 99,
        vertical_offset: 100
      }
    })
  })

  it('gracefully skips the extras when the commonsense group is missing', () => {
    mountContentRatingContainer('mov-library_1', 'movie', `
      <input type="radio" class="template-parent-toggle"
             data-radio-group="true" value="commonsense" checked>
    `)
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('overlay_content_rating_commonsense')
    // No color, no offsets, no extras — just an empty vars object.
    expect(result[0].template_variables).toEqual({})
  })
})

describe('ImageHandler.getLibraryOverlays: mixing checkbox + content-rating flows', () => {
  it('returns both a regular overlay and a content-rating overlay when both are configured', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      templateVars: { text: { type: 'text', value: 'HELLO' } }
    }))
    mountContentRatingContainer('mov-library_1', 'movie', `
      <input type="radio" class="template-parent-toggle"
             data-radio-group="true" value="us" checked>
      <select name="mov-library_1-movie-template_overlay_content_rating_us[color]">
        <option value="green" selected>green</option>
      </select>
    `)
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result).toHaveLength(2)
    const ids = result.map(o => o.id).sort()
    expect(ids).toEqual(['overlay_content_rating_us', 'overlay_ribbon'])
  })

  it('returns multiple checkbox overlays in DOM order', () => {
    mountOverlaysContainer('mov-library_1', [
      buildOverlayCheckbox({
        libraryId: 'mov-library_1',
        type: 'movie',
        suffix: 'ribbon',
        templateVars: {}
      }),
      buildOverlayCheckbox({
        libraryId: 'mov-library_1',
        type: 'movie',
        suffix: 'resolution',
        templateVars: {}
      })
    ].join('\n'))
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result.map(o => o.id)).toEqual(['overlay_ribbon', 'overlay_resolution'])
  })
})

describe('ImageHandler.getLibraryOverlays: type differentiation', () => {
  it('picks only the overlays matching the requested type', () => {
    // Put two overlays in the container — one for movie, one for show.
    // Ask for movie; only that one should come back.
    mountOverlaysContainer('mov-library_1', [
      buildOverlayCheckbox({
        libraryId: 'mov-library_1',
        type: 'movie',
        suffix: 'ribbon',
        templateVars: {}
      }),
      buildOverlayCheckbox({
        libraryId: 'mov-library_1',
        type: 'show',
        suffix: 'ribbon',
        templateVars: {}
      })
    ].join('\n'))
    const movResult = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(movResult.map(o => o.id)).toEqual(['overlay_ribbon'])

    // Ask for show; only that one should come back.
    const showResult = window.ImageHandler.getLibraryOverlays('mov-library_1', false, 'show')
    expect(showResult.map(o => o.id)).toEqual(['overlay_ribbon'])
  })

  it('defaults type to "movie" when not supplied', () => {
    mountOverlaysContainer('mov-library_1', buildOverlayCheckbox({
      libraryId: 'mov-library_1',
      type: 'movie',
      suffix: 'ribbon',
      templateVars: {}
    }))
    // No third arg — should still find the movie overlay via the default.
    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true)
    expect(result.map(o => o.id)).toEqual(['overlay_ribbon'])
  })
})

describe('ImageHandler.getLibraryOverlays: fallback when template group is missing', () => {
  it('collects template variables from the DOCUMENT when the checkbox lacks a template-toggle-group ancestor', () => {
    // The source's selectors branch: `container ? container.querySelectorAll(...)
    //   : document.querySelectorAll(...)`. Cover the document fallback.
    const container = document.createElement('div')
    container.id = 'mov-library_1-overlays'
    container.innerHTML = `<input type="checkbox"
        name="mov-library_1-movie-overlay_ribbon" checked>`
    document.body.appendChild(container)

    // Template variables scattered elsewhere in the document (NOT inside
    // .template-toggle-group).
    const stray = document.createElement('div')
    stray.innerHTML = `
      <input type="text"
             name="mov-library_1-movie-template_overlay_ribbon[text]"
             value="stray">
    `
    document.body.appendChild(stray)

    const result = window.ImageHandler.getLibraryOverlays('mov-library_1', true, 'movie')
    expect(result).toHaveLength(1)
    expect(result[0].template_variables).toEqual({ text: 'stray' })
  })
})
