import { describe, it, expect, beforeEach } from 'vitest'
import { elementGroup } from '../../../static/local-js/modules/elementGroup.js'

describe('elementGroup', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  describe('construction', () => {
    it('returns an empty group when no selectors match', () => {
      const group = elementGroup('#nonexistent')
      expect(group.length).toBe(0)
      expect(group.elements).toEqual([])
    })

    it('resolves each selector via querySelector and filters out misses', () => {
      document.body.innerHTML = '<input id="a"><input id="c">'
      const group = elementGroup('#a', '#b', '#c')
      expect(group.length).toBe(2)
      expect(group.elements.map((el) => el.id)).toEqual(['a', 'c'])
    })

    it('trims whitespace in selectors', () => {
      document.body.innerHTML = '<input id="x">'
      const group = elementGroup('  #x  ')
      expect(group.length).toBe(1)
    })

    it('ignores empty selector strings', () => {
      document.body.innerHTML = '<input id="x">'
      const group = elementGroup('#x', '', '  ')
      expect(group.length).toBe(1)
    })

    it('is iterable via for-of', () => {
      document.body.innerHTML = '<input id="a"><input id="b">'
      const group = elementGroup('#a', '#b')
      const ids = []
      for (const el of group) ids.push(el.id)
      expect(ids).toEqual(['a', 'b'])
    })
  })

  describe('.value getter', () => {
    it('reads from the first element', () => {
      document.body.innerHTML = '<input id="a" value="first"><input id="b" value="second">'
      expect(elementGroup('#a', '#b').value).toBe('first')
    })

    it('returns empty string when group is empty', () => {
      expect(elementGroup('#nope').value).toBe('')
    })

    it('returns empty string when first element has no value', () => {
      document.body.innerHTML = '<div id="a"></div>'
      // div.value is undefined; getter should coalesce to ''
      expect(elementGroup('#a').value).toBe('')
    })
  })

  describe('.setValue()', () => {
    it('sets value on every element', () => {
      document.body.innerHTML = '<input id="a"><input id="b">'
      elementGroup('#a', '#b').setValue('hello')
      expect(document.getElementById('a').value).toBe('hello')
      expect(document.getElementById('b').value).toBe('hello')
    })

    it('is a no-op on empty groups', () => {
      expect(() => elementGroup('#nope').setValue('x')).not.toThrow()
    })
  })

  describe('.setHTML()', () => {
    it('assigns innerHTML on every element', () => {
      document.body.innerHTML = '<div id="a"></div><div id="b"></div>'
      elementGroup('#a', '#b').setHTML('<span>x</span>')
      expect(document.getElementById('a').innerHTML).toBe('<span>x</span>')
      expect(document.getElementById('b').innerHTML).toBe('<span>x</span>')
    })
  })

  describe('.setText()', () => {
    it('assigns textContent on every element', () => {
      document.body.innerHTML = '<div id="a"></div><div id="b"></div>'
      elementGroup('#a', '#b').setText('hello')
      expect(document.getElementById('a').textContent).toBe('hello')
      expect(document.getElementById('b').textContent).toBe('hello')
    })
  })

  describe('.setProp() / .setDisabled()', () => {
    it('assigns arbitrary property on every element', () => {
      document.body.innerHTML = '<input id="a"><input id="b">'
      elementGroup('#a', '#b').setProp('checked', true)
      expect(document.getElementById('a').checked).toBe(true)
      expect(document.getElementById('b').checked).toBe(true)
    })

    it('setDisabled is a shortcut for setProp("disabled", ...)', () => {
      document.body.innerHTML = '<button id="a"></button><button id="b"></button>'
      elementGroup('#a', '#b').setDisabled(true)
      expect(document.getElementById('a').disabled).toBe(true)
      expect(document.getElementById('b').disabled).toBe(true)
    })

    it('setAttr sets HTML attribute on every element', () => {
      document.body.innerHTML = '<input id="a"><input id="b">'
      elementGroup('#a', '#b').setAttr('min', '2024-01-01')
      expect(document.getElementById('a').getAttribute('min')).toBe('2024-01-01')
      expect(document.getElementById('b').getAttribute('min')).toBe('2024-01-01')
    })
  })

  describe('.on()', () => {
    it('attaches event listener on every element', () => {
      document.body.innerHTML = '<button id="a"></button><button id="b"></button>'
      const clicks = []
      elementGroup('#a', '#b').on('click', function () {
        clicks.push(this.id)
      })
      document.getElementById('a').click()
      document.getElementById('b').click()
      expect(clicks).toEqual(['a', 'b'])
    })

    it('supports space-separated event names', () => {
      document.body.innerHTML = '<input id="a">'
      const events = []
      elementGroup('#a').on('input change', (e) => events.push(e.type))
      const el = document.getElementById('a')
      el.dispatchEvent(new Event('input'))
      el.dispatchEvent(new Event('change'))
      expect(events).toEqual(['input', 'change'])
    })
  })

  describe('classList helpers', () => {
    it('addClass adds on every element', () => {
      document.body.innerHTML = '<div id="a"></div><div id="b"></div>'
      elementGroup('#a', '#b').addClass('active')
      expect(document.getElementById('a').classList.contains('active')).toBe(true)
      expect(document.getElementById('b').classList.contains('active')).toBe(true)
    })

    it('removeClass removes from every element', () => {
      document.body.innerHTML = '<div id="a" class="x"></div><div id="b" class="x y"></div>'
      elementGroup('#a', '#b').removeClass('x')
      expect(document.getElementById('a').classList.contains('x')).toBe(false)
      expect(document.getElementById('b').classList.contains('x')).toBe(false)
      expect(document.getElementById('b').classList.contains('y')).toBe(true)
    })

    it('toggleClass toggles on every element (force respected)', () => {
      document.body.innerHTML = '<div id="a" class="on"></div><div id="b"></div>'
      elementGroup('#a', '#b').toggleClass('on', false)
      expect(document.getElementById('a').classList.contains('on')).toBe(false)
      expect(document.getElementById('b').classList.contains('on')).toBe(false)
      elementGroup('#a', '#b').toggleClass('on', true)
      expect(document.getElementById('a').classList.contains('on')).toBe(true)
      expect(document.getElementById('b').classList.contains('on')).toBe(true)
    })
  })
})
