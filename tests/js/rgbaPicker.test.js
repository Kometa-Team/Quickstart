// Tests for static/local-js/rgbaPicker.js -- the RGBA color-picker driver
// that replaced 4 inline `oninput="(function(...){ ... })(this)"` IIFEs
// in templates/partials/_macros.html.
//
// rgbaPicker.js is loaded as a classic script (sequential loader in
// 025-libraries.js), not an ES module, so we test it by reading the
// file and evaluating it in the jsdom global. The IIFE inside registers
// a single document-level `input` listener on first execution; the
// listener is shared across all .rgba-group widgets on the page.
//
// Each test rebuilds a clean DOM (a fresh .rgba-group fixture), runs
// the file once per test suite, and exercises one of the four input
// elements to verify the cross-element updates fire correctly.

import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

let listenerInstalled = false

function installPickerScript () {
  // Read the file once. Evaluating it twice would register two
  // listeners and cause double-fires, so guard with a module-level flag.
  if (listenerInstalled) return
  const path = resolve(__dirname, '../../static/local-js/rgbaPicker.js')
  const src = readFileSync(path, 'utf-8')
  // eslint-disable-next-line no-new-func
  new Function(src).call(window)
  listenerInstalled = true
}

function buildGroup ({ pickerHex = '#FFAABB', alphaPct = 50, hexAlpha } = {}) {
  // hexAlpha defaults to the picker value + alpha-derived alpha byte
  if (hexAlpha === undefined) {
    const aa = Math.round((alphaPct / 100) * 255).toString(16).padStart(2, '0').toUpperCase()
    hexAlpha = `${pickerHex.toUpperCase()}${aa}`
  }
  document.body.innerHTML = `
    <div class="rgba-group">
      <div class="rgba-bar-wrap">
        <input type="color" class="rgba-color-picker" value="${pickerHex}">
        <label class="rgba-color-bar"></label>
      </div>
      <div class="input-group">
        <input type="text" class="rgba-hex-input" value="${hexAlpha}">
      </div>
      <div class="rgba-opacity-row">
        <input type="number" class="rgba-alpha-input" min="0" max="100" step="1" value="${alphaPct}">
        <input type="range" class="rgba-alpha-slider" min="0" max="100" value="${alphaPct}">
      </div>
    </div>
  `
  return {
    group: document.querySelector('.rgba-group'),
    picker: document.querySelector('.rgba-color-picker'),
    bar: document.querySelector('.rgba-color-bar'),
    hexInput: document.querySelector('.rgba-hex-input'),
    alphaInput: document.querySelector('.rgba-alpha-input'),
    slider: document.querySelector('.rgba-alpha-slider')
  }
}

function fireInput (el, value) {
  if (value !== undefined) el.value = value
  el.dispatchEvent(new Event('input', { bubbles: true }))
}

beforeAll(() => {
  installPickerScript()
})

beforeEach(() => {
  document.body.innerHTML = ''
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('rgbaPicker: color-picker input handler', () => {
  it('updates the hex input with the picker color + slider-derived alpha', () => {
    const { picker, hexInput } = buildGroup({ pickerHex: '#112233', alphaPct: 80 })
    // Slider starts at 80, so 80% alpha -> 0xCC. Force the picker to a new
    // value and fire input; hex should reflect new color + CC alpha.
    fireInput(picker, '#445566')
    expect(hexInput.value).toBe('#445566CC')
  })

  it('repaints the color bar with the new rgb + slider alpha', () => {
    const { picker, bar } = buildGroup({ pickerHex: '#000000', alphaPct: 100 })
    fireInput(picker, '#ff0000')
    // When alpha=1, the browser canonicalises rgba(...,1) to rgb(...).
    expect(bar.style.background).toBe('rgb(255, 0, 0)')
  })

  it('rounds and writes the alpha number input from the slider value', () => {
    const { picker, alphaInput } = buildGroup({ pickerHex: '#abcdef', alphaPct: 50 })
    // alphaInput starts at 50; after the picker handler runs it should
    // still be 50 (slider unchanged). The mirror exists for byte-equivalence
    // with the prior IIFE -- this test pins the behaviour.
    fireInput(picker, '#abcdef')
    expect(alphaInput.value).toBe('50')
  })
})

describe('rgbaPicker: hex input handler', () => {
  it('normalizes a 7-char hex by appending FF and uppercasing', () => {
    const { hexInput } = buildGroup()
    fireInput(hexInput, '#aabbcc')
    expect(hexInput.value).toBe('#AABBCCFF')
  })

  it('uppercases a 9-char hex without changing its contents', () => {
    const { hexInput } = buildGroup()
    fireInput(hexInput, '#aabbccdd')
    expect(hexInput.value).toBe('#AABBCCDD')
  })

  it('updates picker, slider, alpha-input, and bar from a 9-char hex', () => {
    const { hexInput, picker, slider, alphaInput, bar } = buildGroup()
    fireInput(hexInput, '#11223380')
    // 0x80 = 128 / 255 * 100 = 50.196... -> Math.round => 50
    expect(picker.value).toBe('#112233')
    expect(slider.value).toBe('50')
    expect(slider.title).toBe('Opacity: 50%')
    expect(alphaInput.value).toBe('50')
    expect(bar.style.background).toBe('rgba(17, 34, 51, 0.5)')
  })

  it('ignores incomplete hex strings so the user can keep typing', () => {
    const { hexInput, picker } = buildGroup({ pickerHex: '#FFAABB' })
    const startingPicker = picker.value
    fireInput(hexInput, '#112')
    // No updates should have happened.
    expect(picker.value).toBe(startingPicker)
  })

  it('ignores strings that do not start with #', () => {
    const { hexInput, picker } = buildGroup({ pickerHex: '#FFAABB' })
    const startingPicker = picker.value
    fireInput(hexInput, 'aabbccdd')
    expect(picker.value).toBe(startingPicker)
  })
})

describe('rgbaPicker: alpha-number input handler', () => {
  it('clamps values below 0 to 0', () => {
    const { alphaInput, hexInput } = buildGroup({ pickerHex: '#FFFFFF', alphaPct: 50 })
    fireInput(alphaInput, '-25')
    expect(alphaInput.value).toBe('0')
    // 0% alpha -> 0x00
    expect(hexInput.value).toBe('#FFFFFF00')
  })

  it('clamps values above 100 to 100', () => {
    const { alphaInput, hexInput } = buildGroup({ pickerHex: '#FFFFFF', alphaPct: 50 })
    fireInput(alphaInput, '250')
    expect(alphaInput.value).toBe('100')
    expect(hexInput.value).toBe('#FFFFFFFF')
  })

  it('mirrors the value to the slider and updates the slider title', () => {
    const { alphaInput, slider } = buildGroup({ pickerHex: '#FFFFFF', alphaPct: 50 })
    fireInput(alphaInput, '33')
    expect(slider.value).toBe('33')
    expect(slider.title).toBe('Opacity: 33%')
  })
})

describe('rgbaPicker: slider input handler', () => {
  it('writes the hex input with the picker color + new alpha', () => {
    const { slider, hexInput } = buildGroup({ pickerHex: '#aabbcc', alphaPct: 50 })
    fireInput(slider, '75')
    // 75% -> 0.75 * 255 = 191.25 -> Math.round = 191 -> 0xBF
    expect(hexInput.value).toBe('#AABBCCBF')
  })

  it('mirrors the slider value to the alpha number input', () => {
    const { slider, alphaInput } = buildGroup({ pickerHex: '#ffffff', alphaPct: 50 })
    fireInput(slider, '20')
    expect(alphaInput.value).toBe('20')
  })

  it('updates the color bar background', () => {
    const { slider, bar } = buildGroup({ pickerHex: '#ff0000', alphaPct: 50 })
    fireInput(slider, '40')
    expect(bar.style.background).toBe('rgba(255, 0, 0, 0.4)')
  })

  it('updates the slider title for accessibility', () => {
    const { slider } = buildGroup({ pickerHex: '#ffffff', alphaPct: 50 })
    fireInput(slider, '60')
    expect(slider.title).toBe('Opacity: 60%')
  })
})

describe('rgbaPicker: delegation', () => {
  it('handles multiple .rgba-group widgets independently on the same page', () => {
    document.body.innerHTML = `
      <div class="rgba-group" id="g1">
        <input type="color" class="rgba-color-picker" value="#111111">
        <label class="rgba-color-bar"></label>
        <input type="text" class="rgba-hex-input" value="#111111FF">
        <input type="number" class="rgba-alpha-input" value="100">
        <input type="range" class="rgba-alpha-slider" value="100">
      </div>
      <div class="rgba-group" id="g2">
        <input type="color" class="rgba-color-picker" value="#222222">
        <label class="rgba-color-bar"></label>
        <input type="text" class="rgba-hex-input" value="#222222FF">
        <input type="number" class="rgba-alpha-input" value="100">
        <input type="range" class="rgba-alpha-slider" value="100">
      </div>
    `
    const g1Slider = document.querySelector('#g1 .rgba-alpha-slider')
    const g1Hex = document.querySelector('#g1 .rgba-hex-input')
    const g2Hex = document.querySelector('#g2 .rgba-hex-input')
    fireInput(g1Slider, '50')
    // Only g1's hex should have changed.
    expect(g1Hex.value).toBe('#11111180')
    expect(g2Hex.value).toBe('#222222FF')
  })

  it('handles a .rgba-group that did not exist at script load time', () => {
    // The delegated listener was installed in beforeAll(). This test
    // builds a fresh group AFTER that and verifies the listener still
    // applies. Demonstrates the event-delegation advantage over the
    // old per-element inline-oninput pattern.
    const fresh = buildGroup({ pickerHex: '#abcdef', alphaPct: 30 })
    fireInput(fresh.slider, '90')
    // 90% -> 0xE6
    expect(fresh.hexInput.value).toBe('#ABCDEFE6')
  })
})
