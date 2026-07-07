/**
 * elementGroup(...selectors) — wraps N DOM elements that share behavior.
 *
 * Used by 905-analytics where certain filter controls have a "top"
 * and "bottom" copy that must always stay in sync. Rather than
 * repeating forEach loops at every read/write site, the group exposes
 * a small, native-shaped API mirroring the underlying DOM properties.
 *
 * The API is deliberately vanilla-DOM shaped, NOT jQuery shaped:
 *   .value           read from first element (empty string if none)
 *   .setValue(x)     assign .value on every element
 *   .setHTML(x)      assign .innerHTML on every element
 *   .setText(x)      assign .textContent on every element
 *   .setProp(k, v)   assign an arbitrary property on every element
 *   .setAttr(k, v)   setAttribute on every element
 *   .setDisabled(b)  shortcut for setProp('disabled', b)
 *   .on(evt, fn)     addEventListener on every element (evt may be
 *                    space-separated: 'input change')
 *   .toggleClass(name, force)   classList.toggle on every element
 *   .addClass(name) / .removeClass(name)
 *   .length          number of matched elements
 *   iterable         for-of yields raw elements
 *   .elements        raw array (escape hatch)
 *
 * Missing elements are silently dropped. Callers should check
 * `.length` before assuming any element was found.
 *
 * @param  {...string} selectors  CSS selectors. Elements resolved
 *                                via document.querySelector.
 */
export function elementGroup (...selectors) {
  const elements = selectors
    .map((s) => String(s).trim())
    .filter(Boolean)
    .map((s) => document.querySelector(s))
    .filter(Boolean)

  return {
    elements,
    get length () { return elements.length },
    [Symbol.iterator] () { return elements[Symbol.iterator]() },

    get value () {
      return elements.length ? (elements[0].value ?? '') : ''
    },

    setValue (value) {
      elements.forEach((el) => { el.value = value })
    },

    setHTML (value) {
      elements.forEach((el) => { el.innerHTML = value })
    },

    setText (value) {
      elements.forEach((el) => { el.textContent = value })
    },

    setProp (name, value) {
      elements.forEach((el) => { el[name] = value })
    },

    setAttr (name, value) {
      elements.forEach((el) => el.setAttribute(name, value))
    },

    setDisabled (disabled) {
      elements.forEach((el) => { el.disabled = disabled })
    },

    on (event, handler) {
      // Support space-separated event names like 'input change'
      const events = String(event).split(/\s+/).filter(Boolean)
      elements.forEach((el) => {
        events.forEach((evt) => el.addEventListener(evt, handler))
      })
    },

    addClass (name) {
      elements.forEach((el) => el.classList.add(name))
    },

    removeClass (name) {
      elements.forEach((el) => el.classList.remove(name))
    },

    toggleClass (name, force) {
      elements.forEach((el) => el.classList.toggle(name, force))
    }
  }
}
