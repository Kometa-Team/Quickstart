// Tests for static/local-js/validationHandler.js (#1335 Step 8 — coverage push).
//
// validationHandler.js is an ES module (#1346 Step 2 finish) that also
// attaches `ValidationHandler` to `window` for classic-script consumers.
// It runs a few side effects at import time (restoreSelectedLibraries,
// updateValidationState, plus document change/input listeners). Same
// shape as pathValidation / urlValidation / imageHandler, so we use
// the same side-effect-import pattern:
//
//   1. Seed a minimal DOM the module's init calls can safely walk
//   2. `await import('.../validationHandler.js')`
//   3. Access `window.ValidationHandler` for the API surface
//
// Why this module is high-value to lock down:
//   - It's the top-level gate for the libraries wizard: any regression
//     in `validateForm`, `getSelectedLibraryIds`, or `disableNavigation`
//     silently breaks users' ability to advance the wizard
//   - It runs some DOM writes as raw HTML (via `{ html: true }`) — a
//     regression to unconditionally-HTML would open an XSS hole
//   - It was recently reworked to drop jQuery (Step 7); locking down
//     the behaviour prevents future regressions in the vanilla-DOM
//     replacement code

import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

// Silence the module's very chatty console.log output during tests.
// Every branch of every method calls console.log(); the noise buries
// real Vitest output. We keep console.error/warn intact so real problems
// still surface.
beforeAll(async () => {
  vi.spyOn(console, 'log').mockImplementation(() => {})

  // Seed a DOM the module's on-import side effects can safely traverse.
  // Missing #libraries would only trigger a debug log; missing
  // #validation-messages would make showValidationMessage no-op; missing
  // #plex_valid means validatePlexState returns false and calls
  // disableNavigation, which is fine (empty selectors match nothing).
  document.body.innerHTML = `
    <input id="libraries" value="">
    <input id="libraries_validated" value="">
    <input id="libraries_validated_at" value="">
    <div id="validation-messages"></div>
    <div id="plex_valid" data-plex-valid="True"></div>
    <form id="configForm"></form>
  `

  await import('../../static/local-js/validationHandler.js')
})

afterEach(() => {
  document.body.innerHTML = ''
})

// Every test after the module import gets a fresh DOM in the beforeEach,
// so we need to re-create the elements the module's helpers read from.

describe('ValidationHandler: module registration', () => {
  it('attaches ValidationHandler to window', () => {
    expect(window.ValidationHandler).toBeDefined()
    expect(typeof window.ValidationHandler.showValidationMessage).toBe('function')
  })
})

describe('ValidationHandler.showValidationMessage', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="validation-messages"></div>'
  })

  it('renders the message as textContent by default (XSS-safe)', () => {
    window.ValidationHandler.showValidationMessage('<script>bad</script>', 'danger')
    const box = document.getElementById('validation-messages')
    // textContent means the literal string is shown, not evaluated as HTML
    expect(box.textContent).toBe('<script>bad</script>')
    expect(box.querySelector('script')).toBeNull()
  })

  it('renders HTML only when options.html === true', () => {
    window.ValidationHandler.showValidationMessage('plain <strong>bold</strong>', 'success', { html: true })
    const box = document.getElementById('validation-messages')
    expect(box.querySelector('strong')).not.toBeNull()
    expect(box.querySelector('strong').textContent).toBe('bold')
  })

  it('sets the danger alert class for type=danger', () => {
    window.ValidationHandler.showValidationMessage('nope', 'danger')
    const box = document.getElementById('validation-messages')
    expect(box.classList.contains('alert-danger')).toBe(true)
    expect(box.classList.contains('alert-success')).toBe(false)
  })

  it('sets the success alert class for type=success', () => {
    window.ValidationHandler.showValidationMessage('ok', 'success')
    const box = document.getElementById('validation-messages')
    expect(box.classList.contains('alert-success')).toBe(true)
    expect(box.classList.contains('alert-danger')).toBe(false)
  })

  it('toggles between danger and success cleanly on repeated calls', () => {
    const box = document.getElementById('validation-messages')
    window.ValidationHandler.showValidationMessage('bad', 'danger')
    expect(box.classList.contains('alert-danger')).toBe(true)

    window.ValidationHandler.showValidationMessage('good', 'success')
    expect(box.classList.contains('alert-success')).toBe(true)
    expect(box.classList.contains('alert-danger')).toBe(false)

    window.ValidationHandler.showValidationMessage('bad again', 'danger')
    expect(box.classList.contains('alert-danger')).toBe(true)
    expect(box.classList.contains('alert-success')).toBe(false)
  })

  it('makes the box visible via display:block', () => {
    window.ValidationHandler.showValidationMessage('anything', 'success')
    const box = document.getElementById('validation-messages')
    expect(box.style.display).toBe('block')
  })

  it('no-ops silently when #validation-messages is missing', () => {
    document.body.innerHTML = ''
    // Should NOT throw
    expect(() => {
      window.ValidationHandler.showValidationMessage('hi', 'danger')
    }).not.toThrow()
  })

  it('treats falsy options.html as textContent', () => {
    document.body.innerHTML = '<div id="validation-messages"></div>'
    window.ValidationHandler.showValidationMessage('<b>x</b>', 'success', { html: false })
    const box = document.getElementById('validation-messages')
    expect(box.textContent).toBe('<b>x</b>')
    expect(box.querySelector('b')).toBeNull()
  })

  it('treats missing options as textContent', () => {
    document.body.innerHTML = '<div id="validation-messages"></div>'
    window.ValidationHandler.showValidationMessage('<b>x</b>', 'success')
    const box = document.getElementById('validation-messages')
    expect(box.textContent).toBe('<b>x</b>')
  })
})

describe('ValidationHandler.getSelectedLibraryIds', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('returns ids for movie library inputs with non-empty values', () => {
    document.body.innerHTML = `
      <input id="mov-library_1-library-value" value="Movies">
      <input id="mov-library_2-library-value" value="Anime">
    `
    const ids = window.ValidationHandler.getSelectedLibraryIds('mov')
    expect(ids).toEqual(['mov-library_1', 'mov-library_2'])
  })

  it('filters out inputs whose value is empty', () => {
    document.body.innerHTML = `
      <input id="mov-library_1-library-value" value="Movies">
      <input id="mov-library_2-library-value" value="">
    `
    const ids = window.ValidationHandler.getSelectedLibraryIds('mov')
    expect(ids).toEqual(['mov-library_1'])
  })

  it('filters out inputs whose value is whitespace-only', () => {
    document.body.innerHTML = `
      <input id="mov-library_1-library-value" value="   ">
      <input id="mov-library_2-library-value" value="Movies">
    `
    const ids = window.ValidationHandler.getSelectedLibraryIds('mov')
    expect(ids).toEqual(['mov-library_2'])
  })

  it('scopes matches to the mov prefix and ignores sho inputs', () => {
    document.body.innerHTML = `
      <input id="mov-library_1-library-value" value="Movies">
      <input id="sho-library_9-library-value" value="Shows">
    `
    const movIds = window.ValidationHandler.getSelectedLibraryIds('mov')
    const shoIds = window.ValidationHandler.getSelectedLibraryIds('sho')
    expect(movIds).toEqual(['mov-library_1'])
    expect(shoIds).toEqual(['sho-library_9'])
  })

  it('returns [] when no matching inputs are present', () => {
    document.body.innerHTML = ''
    expect(window.ValidationHandler.getSelectedLibraryIds('mov')).toEqual([])
  })

  it('returns [] when all matching inputs are empty', () => {
    document.body.innerHTML = `
      <input id="mov-library_1-library-value" value="">
      <input id="mov-library_2-library-value" value="   ">
    `
    expect(window.ValidationHandler.getSelectedLibraryIds('mov')).toEqual([])
  })
})

describe('ValidationHandler.getSelectedLibraryNames', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('returns trimmed values for matching inputs', () => {
    document.body.innerHTML = `
      <input id="mov-library_1-library-value" value="  Movies  ">
      <input id="mov-library_2-library-value" value="Anime">
    `
    const names = window.ValidationHandler.getSelectedLibraryNames('mov')
    expect(names).toEqual(['Movies', 'Anime'])
  })

  it('filters out empty/whitespace values', () => {
    document.body.innerHTML = `
      <input id="mov-library_1-library-value" value="Movies">
      <input id="mov-library_2-library-value" value="">
      <input id="mov-library_3-library-value" value="   ">
    `
    const names = window.ValidationHandler.getSelectedLibraryNames('mov')
    expect(names).toEqual(['Movies'])
  })

  it('returns [] when no matches', () => {
    expect(window.ValidationHandler.getSelectedLibraryNames('mov')).toEqual([])
  })
})

describe('ValidationHandler.getSelectedLibraries (backward-compat alias)', () => {
  it('delegates to getSelectedLibraryNames', () => {
    document.body.innerHTML = `
      <input id="mov-library_1-library-value" value="Movies">
    `
    expect(window.ValidationHandler.getSelectedLibraries('mov'))
      .toEqual(window.ValidationHandler.getSelectedLibraryNames('mov'))
  })
})

describe('ValidationHandler.restoreSelectedLibraries', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('checks matching library checkboxes from the #libraries CSV', () => {
    document.body.innerHTML = `
      <input id="libraries" value="Movies, Anime, Shows">
      <input type="checkbox" class="library-checkbox" value="Movies">
      <input type="checkbox" class="library-checkbox" value="Anime">
      <input type="checkbox" class="library-checkbox" value="Documentaries">
    `
    window.ValidationHandler.restoreSelectedLibraries()

    const [movies, anime, docs] = document.querySelectorAll('.library-checkbox')
    expect(movies.checked).toBe(true)
    expect(anime.checked).toBe(true)
    // Not in the CSV — should stay unchecked
    expect(docs.checked).toBe(false)
  })

  it('handles trimmed values in the CSV (spaces around commas)', () => {
    document.body.innerHTML = `
      <input id="libraries" value="  Movies  ,   Shows   ">
      <input type="checkbox" class="library-checkbox" value="Movies">
      <input type="checkbox" class="library-checkbox" value="Shows">
    `
    window.ValidationHandler.restoreSelectedLibraries()

    document.querySelectorAll('.library-checkbox').forEach(cb => {
      expect(cb.checked).toBe(true)
    })
  })

  it('no-ops when #libraries element is absent', () => {
    document.body.innerHTML = `
      <input type="checkbox" class="library-checkbox" value="Movies">
    `
    // Should not throw
    expect(() => window.ValidationHandler.restoreSelectedLibraries()).not.toThrow()
    // And the checkbox should NOT be checked (no CSV to consult)
    expect(document.querySelector('.library-checkbox').checked).toBe(false)
  })

  it('handles an empty #libraries value gracefully', () => {
    document.body.innerHTML = `
      <input id="libraries" value="">
      <input type="checkbox" class="library-checkbox" value="Movies">
    `
    expect(() => window.ValidationHandler.restoreSelectedLibraries()).not.toThrow()
    expect(document.querySelector('.library-checkbox').checked).toBe(false)
  })
})

describe('ValidationHandler.disableNavigation', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <form id="configForm">
        <button class="dropdown-toggle">Dropdown</button>
        <button data-nav-action="next">Next</button>
        <button data-nav-action="prev">Previous</button>
      </form>
      <button class="accordion-button">Accordion</button>
    `
  })

  it('disables dropdown toggles and Next buttons in #configForm', () => {
    window.ValidationHandler.disableNavigation()
    const dd = document.querySelector('.dropdown-toggle')
    const next = document.querySelector('[data-nav-action="next"]')
    expect(dd.disabled).toBe(true)
    expect(next.disabled).toBe(true)
  })

  it('keeps the Previous button enabled', () => {
    window.ValidationHandler.disableNavigation()
    const prev = document.querySelector('[data-nav-action="prev"]')
    expect(prev.disabled).toBe(false)
  })

  it('leaves .accordion-button disabled by default (lockAccordions=true)', () => {
    const accordion = document.querySelector('.accordion-button')
    accordion.disabled = true
    window.ValidationHandler.disableNavigation() // default true
    expect(accordion.disabled).toBe(true)
  })

  it('re-enables .accordion-button when lockAccordions=false', () => {
    const accordion = document.querySelector('.accordion-button')
    accordion.disabled = true
    window.ValidationHandler.disableNavigation(false)
    expect(accordion.disabled).toBe(false)
  })
})

describe('ValidationHandler.enableNavigation', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <form id="configForm">
        <button class="dropdown-toggle" disabled>Dropdown</button>
        <button data-nav-action="next" disabled>Next</button>
        <button data-nav-action="prev" disabled>Previous</button>
        <button class="some-other-button" disabled>Other</button>
      </form>
    `
  })

  it('enables every button inside #configForm', () => {
    window.ValidationHandler.enableNavigation()
    document.querySelectorAll('#configForm button').forEach(btn => {
      expect(btn.disabled).toBe(false)
    })
  })

  it('enables .dropdown-toggle inside #configForm', () => {
    window.ValidationHandler.enableNavigation()
    expect(document.querySelector('.dropdown-toggle').disabled).toBe(false)
  })
})

describe('ValidationHandler.validatePlexState', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="validation-messages"></div>'
  })

  it('returns true when #plex_valid has data-plex-valid="True"', () => {
    document.body.innerHTML += '<div id="plex_valid" data-plex-valid="True"></div>'
    expect(window.ValidationHandler.validatePlexState()).toBe(true)
  })

  it('returns false when #plex_valid has data-plex-valid="False"', () => {
    document.body.innerHTML += '<div id="plex_valid" data-plex-valid="False"></div>'
    expect(window.ValidationHandler.validatePlexState()).toBe(false)
  })

  it('returns false when #plex_valid element is missing entirely', () => {
    // No #plex_valid at all
    expect(window.ValidationHandler.validatePlexState()).toBe(false)
  })

  it('shows a danger message when Plex is not valid', () => {
    document.body.innerHTML += '<div id="plex_valid" data-plex-valid="False"></div>'
    window.ValidationHandler.validatePlexState()
    const box = document.getElementById('validation-messages')
    expect(box.classList.contains('alert-danger')).toBe(true)
    // Uses html:true so the "return to Plex page" link is rendered
    expect(box.querySelector('a')).not.toBeNull()
  })

  it('is case-sensitive on data-plex-valid (only "True" counts)', () => {
    // Any casing besides literal "True" should fail. The dataset comes
    // from Jinja rendering a Python True/False, which always produces
    // exactly those cased strings.
    document.body.innerHTML += '<div id="plex_valid" data-plex-valid="true"></div>'
    expect(window.ValidationHandler.validatePlexState()).toBe(false)
  })
})

describe('ValidationHandler.showAccordionForField', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('no-ops when passed null/undefined', () => {
    expect(() => window.ValidationHandler.showAccordionForField(null)).not.toThrow()
    expect(() => window.ValidationHandler.showAccordionForField(undefined)).not.toThrow()
  })

  it('clicks the accordion button when the collapse is not shown', () => {
    document.body.innerHTML = `
      <div class="accordion-item">
        <div class="accordion-header">
          <button class="accordion-button" type="button">Header</button>
        </div>
        <div class="accordion-collapse">
          <input class="is-invalid" id="target">
        </div>
      </div>
    `
    const field = document.getElementById('target')
    const button = document.querySelector('button.accordion-button')
    const clickSpy = vi.spyOn(button, 'click')
    window.ValidationHandler.showAccordionForField(field)
    expect(clickSpy).toHaveBeenCalledTimes(1)
  })

  it('does not click the button if the collapse already has .show', () => {
    document.body.innerHTML = `
      <div class="accordion-item">
        <div class="accordion-header">
          <button class="accordion-button" type="button">Header</button>
        </div>
        <div class="accordion-collapse show">
          <input class="is-invalid" id="target">
        </div>
      </div>
    `
    const field = document.getElementById('target')
    const button = document.querySelector('button.accordion-button')
    const clickSpy = vi.spyOn(button, 'click')
    window.ValidationHandler.showAccordionForField(field)
    expect(clickSpy).not.toHaveBeenCalled()
  })

  it('falls back to adding .show when no accordion button is present', () => {
    document.body.innerHTML = `
      <div class="accordion-collapse">
        <input class="is-invalid" id="target">
      </div>
    `
    const field = document.getElementById('target')
    const collapse = document.querySelector('.accordion-collapse')
    window.ValidationHandler.showAccordionForField(field)
    expect(collapse.classList.contains('show')).toBe(true)
  })

  it('walks up nested accordions and opens each closed ancestor', () => {
    document.body.innerHTML = `
      <div class="accordion-item">
        <div class="accordion-header">
          <button class="accordion-button" id="outer-btn" type="button">Outer</button>
        </div>
        <div class="accordion-collapse">
          <div class="accordion-item">
            <div class="accordion-header">
              <button class="accordion-button" id="inner-btn" type="button">Inner</button>
            </div>
            <div class="accordion-collapse">
              <input class="is-invalid" id="target">
            </div>
          </div>
        </div>
      </div>
    `
    const field = document.getElementById('target')
    const outerBtn = document.getElementById('outer-btn')
    const innerBtn = document.getElementById('inner-btn')
    const outerSpy = vi.spyOn(outerBtn, 'click')
    const innerSpy = vi.spyOn(innerBtn, 'click')

    window.ValidationHandler.showAccordionForField(field)

    // Both ancestors should be opened
    expect(innerSpy).toHaveBeenCalledTimes(1)
    expect(outerSpy).toHaveBeenCalledTimes(1)
  })
})

describe('ValidationHandler.focusFirstInvalidField', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('no-ops on null scope', () => {
    expect(() => window.ValidationHandler.focusFirstInvalidField(null)).not.toThrow()
  })

  it('no-ops when nothing has .is-invalid', () => {
    document.body.innerHTML = '<div><input id="clean"></div>'
    const clean = document.getElementById('clean')
    const focusSpy = vi.spyOn(clean, 'focus')
    window.ValidationHandler.focusFirstInvalidField(document)
    vi.runAllTimers()
    expect(focusSpy).not.toHaveBeenCalled()
  })

  it('focuses the first .is-invalid input inside the scope (after timeout)', () => {
    document.body.innerHTML = `
      <input id="a">
      <input id="b" class="is-invalid">
      <input id="c" class="is-invalid">
    `
    const first = document.getElementById('b')
    // jsdom doesn't implement scrollIntoView; stub it so the deferred
    // callback doesn't throw before reaching the focus() line.
    first.scrollIntoView = vi.fn()
    const focusSpy = vi.spyOn(first, 'focus')
    window.ValidationHandler.focusFirstInvalidField(document)

    // Focus is deferred via window.setTimeout(fn, 180)
    expect(focusSpy).not.toHaveBeenCalled()
    vi.advanceTimersByTime(200)
    expect(focusSpy).toHaveBeenCalledTimes(1)
    expect(focusSpy).toHaveBeenCalledWith({ preventScroll: true })
  })

  it('defaults scope to document when called with no argument', () => {
    document.body.innerHTML = `<input id="b" class="is-invalid">`
    const first = document.getElementById('b')
    first.scrollIntoView = vi.fn()
    const focusSpy = vi.spyOn(first, 'focus')
    window.ValidationHandler.focusFirstInvalidField()
    vi.advanceTimersByTime(200)
    expect(focusSpy).toHaveBeenCalledTimes(1)
  })

  it('opens the enclosing accordion for the invalid field', () => {
    document.body.innerHTML = `
      <div class="accordion-item">
        <div class="accordion-header">
          <button class="accordion-button" type="button">Header</button>
        </div>
        <div class="accordion-collapse">
          <input id="bad" class="is-invalid">
        </div>
      </div>
    `
    const button = document.querySelector('button.accordion-button')
    const clickSpy = vi.spyOn(button, 'click')
    window.ValidationHandler.focusFirstInvalidField(document)
    // showAccordionForField runs synchronously; the focus itself is deferred
    expect(clickSpy).toHaveBeenCalledTimes(1)
  })
})

describe('ValidationHandler.validateForm (integration surface)', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="validation-messages"></div>
      <form id="configForm">
        <button data-nav-action="next">Next</button>
        <button data-nav-action="prev">Previous</button>
      </form>
    `
  })

  it('returns false and shows a danger message when no libraries are selected', () => {
    // No library-value inputs at all
    const result = window.ValidationHandler.validateForm()
    expect(result).toBe(false)
    const box = document.getElementById('validation-messages')
    expect(box.classList.contains('alert-danger')).toBe(true)
  })

  it('returns false and disables Next when a selected library has no highlighted item', () => {
    document.body.innerHTML += `
      <input id="mov-library_1-library-value" value="Movies">
      <div id="mov-library_1-container">
        <!-- no .accordion-header.selected here -->
      </div>
    `
    const result = window.ValidationHandler.validateForm()
    expect(result).toBe(false)
    const next = document.querySelector('[data-nav-action="next"]')
    expect(next.disabled).toBe(true)
  })

  it('returns true when libraries are selected and each has a highlighted item', () => {
    document.body.innerHTML += `
      <input id="mov-library_1-library-value" value="Movies">
      <div id="mov-library_1-container">
        <div class="accordion-header selected"></div>
      </div>
    `
    const result = window.ValidationHandler.validateForm()
    expect(result).toBe(true)
    const box = document.getElementById('validation-messages')
    expect(box.classList.contains('alert-success')).toBe(true)
  })

  it('assumes valid when the selected library has no container in the DOM', () => {
    // No matching *-container element — the module logs and skips it
    document.body.innerHTML += `
      <input id="mov-library_1-library-value" value="Movies">
    `
    const result = window.ValidationHandler.validateForm()
    expect(result).toBe(true)
  })

  it('ignores .accordion-header.selected nested under data-qs-minimal-yaml="false"', () => {
    // A "selected" header inside a minimal-yaml=false subtree should NOT
    // count as a valid highlight for the parent container.
    document.body.innerHTML += `
      <input id="mov-library_1-library-value" value="Movies">
      <div id="mov-library_1-container">
        <div data-qs-minimal-yaml="false">
          <div class="accordion-header selected"></div>
        </div>
      </div>
    `
    const result = window.ValidationHandler.validateForm()
    expect(result).toBe(false)
  })
})
