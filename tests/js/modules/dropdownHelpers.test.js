import { describe, it, expect, beforeEach } from 'vitest'
import { resetDropdown, populateDropdown, setStatusMessageLines } from '../../../static/local-js/modules/dropdownHelpers.js'

describe('dropdownHelpers.resetDropdown', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('replaces all children with a single placeholder option', () => {
    document.body.innerHTML = `
      <select id="d">
        <option value="a">A</option>
        <option value="b">B</option>
      </select>
    `
    resetDropdown(document.getElementById('d'), 'Pick one')

    const dropdown = document.getElementById('d')
    expect(dropdown.children.length).toBe(1)
    expect(dropdown.children[0].value).toBe('')
    expect(dropdown.children[0].textContent).toBe('Pick one')
  })

  it('does not throw when dropdown is null', () => {
    expect(() => resetDropdown(null, 'Placeholder')).not.toThrow()
  })

  it('works on an empty dropdown', () => {
    document.body.innerHTML = '<select id="d"></select>'
    resetDropdown(document.getElementById('d'), 'Empty')
    expect(document.getElementById('d').children.length).toBe(1)
  })
})

describe('dropdownHelpers.populateDropdown', () => {
  beforeEach(() => {
    document.body.innerHTML = '<select id="d"></select>'
  })

  it('populates options from data using valueField and textField', () => {
    populateDropdown('d', [
      { path: '/movies', label: 'Movies' },
      { path: '/tv', label: 'TV Shows' }
    ], 'path', 'label')

    const dropdown = document.getElementById('d')
    // Placeholder option + 2 data options
    expect(dropdown.children.length).toBe(3)
    expect(dropdown.children[1].value).toBe('/movies')
    expect(dropdown.children[1].textContent).toBe('Movies')
    expect(dropdown.children[2].value).toBe('/tv')
    expect(dropdown.children[2].textContent).toBe('TV Shows')
  })

  it('pre-selects the matching option when selectedValue is provided', () => {
    populateDropdown('d', [
      { path: '/a' }, { path: '/b' }, { path: '/c' }
    ], 'path', 'path', '/b')

    expect(document.getElementById('d').value).toBe('/b')
  })

  it('uses the default placeholder when none is provided', () => {
    populateDropdown('d', [{ name: 'x' }], 'name', 'name')
    expect(document.getElementById('d').children[0].textContent).toBe('Select an option')
  })

  it('accepts a custom placeholder text', () => {
    populateDropdown('d', [{ name: 'x' }], 'name', 'name', '', 'Choose your fighter')
    expect(document.getElementById('d').children[0].textContent).toBe('Choose your fighter')
  })

  it('is a no-op when element id is missing', () => {
    expect(() => populateDropdown('nonexistent', [{ name: 'x' }], 'name', 'name')).not.toThrow()
  })

  it('only adds placeholder when data is null or undefined', () => {
    populateDropdown('d', null, 'path', 'path')
    expect(document.getElementById('d').children.length).toBe(1)

    populateDropdown('d', undefined, 'path', 'path')
    expect(document.getElementById('d').children.length).toBe(1)
  })

  it('only adds placeholder when data is not an array', () => {
    populateDropdown('d', { not: 'array' }, 'path', 'path')
    expect(document.getElementById('d').children.length).toBe(1)
  })

  it('handles empty array data', () => {
    populateDropdown('d', [], 'path', 'path')
    expect(document.getElementById('d').children.length).toBe(1)
    expect(document.getElementById('d').children[0].value).toBe('')
  })

  it('does not pre-select when selectedValue is empty string', () => {
    populateDropdown('d', [{ path: '/a' }, { path: '/b' }], 'path', 'path', '')
    expect(document.getElementById('d').value).toBe('') // placeholder
  })

  it('does not pre-select when selectedValue does not match any option', () => {
    populateDropdown('d', [{ path: '/a' }], 'path', 'path', '/missing')
    expect(document.getElementById('d').value).toBe('') // placeholder
  })
})

describe('dropdownHelpers.setStatusMessageLines', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="status"></div>'
  })

  it('sets a single message without any <br>', () => {
    setStatusMessageLines(document.getElementById('status'), ['Just one'])
    const status = document.getElementById('status')
    expect(status.textContent).toBe('Just one')
    expect(status.querySelectorAll('br').length).toBe(0)
  })

  it('separates multiple messages with <br>', () => {
    setStatusMessageLines(document.getElementById('status'), ['First', 'Second', 'Third'])
    const status = document.getElementById('status')
    expect(status.querySelectorAll('br').length).toBe(2)
    expect(status.textContent).toBe('FirstSecondThird')
  })

  it('clears existing content before writing new lines', () => {
    const status = document.getElementById('status')
    status.textContent = 'old content here'
    setStatusMessageLines(status, ['new'])
    expect(status.textContent).toBe('new')
  })

  it('handles empty messages array (clears the element)', () => {
    const status = document.getElementById('status')
    status.textContent = 'old'
    setStatusMessageLines(status, [])
    expect(status.textContent).toBe('')
  })

  it('does not throw when element is null', () => {
    expect(() => setStatusMessageLines(null, ['anything'])).not.toThrow()
  })

  it('uses textContent (not innerHTML) -- safe against HTML injection', () => {
    setStatusMessageLines(document.getElementById('status'), ['<img src=x onerror=alert(1)>'])
    const status = document.getElementById('status')
    // The img tag should be rendered as literal text, not parsed
    expect(status.querySelectorAll('img').length).toBe(0)
    expect(status.textContent).toContain('<img src=x onerror=alert(1)>')
  })
})
