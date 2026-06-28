// Tests for static/local-js/pathValidation.js (#1334 Step 8 — coverage push).
//
// Same pattern as urlValidation.test.js: side-effect import that runs
// the IIFE in jsdom, then access via window.PathValidation. Switch to
// named imports if/when this module gets a proper `export`.
//
// What makes pathValidation interesting to test:
//   - It fetches rules from /path-validation-rules at attach time, so
//     fetch must be mocked. We use vi.stubGlobal('fetch', ...) for that.
//   - Validation behaviour depends on a per-rule object AND a runtime
//     platform (linux vs windows). The platform comes from the same
//     /path-validation-rules response.
//   - The module has internal cached state (rules, meta, loadPromise)
//     that we can't reset between tests because there is no resetForTests
//     export. Instead each test relies on attach() being callable
//     repeatedly with no surprises, and we are careful to scope DOM
//     and assertions to the test under examination.
//
// CAVEAT: The module caches `loadPromise` after the first attach() call
// so subsequent fetch mocks won't be hit. The tests work around this
// by setting up the desired mock BEFORE the first attach in each block
// and accepting that the rules+meta from that first attach persist
// across the rest of the file. This matches production reality (the
// module is initialised once per page load) but means test ordering
// matters within a file. We deliberately put the linux/posix tests
// first and the windows-specific tests after the platform has been
// set to windows.
//
// Why this module is high value to lock down:
//   - Called from 000-base.js, 001-start.js, 150-settings.js, 915-
//     imagemaid.js, validationHandler.js. Anything that takes a
//     filesystem path uses this.
//   - A regression in validateValue could silently accept "C:\bad"
//     on a Linux user's setup or reject "/var/log" on Linux as
//     Windows-style.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Set up a fetch mock BEFORE importing pathValidation, so the module's
// init paths see a usable global. The first attach() call will pin the
// rules/meta to whatever this mock returns, so we shape it as a
// permissive linux config that most tests can use.
const defaultRulesResponse = {
  rules: [
    { id: 'config-dir', allow_relative: false, ui: { platform_status: true, hint_docker: 'Map this to your config volume.' } },
    { id: 'assets-dir', allow_relative: false, ui: { platform_status: true } },
    { id: 'logs-dir', allow_relative: true, ui: { platform_status: false } }
  ],
  platform: 'linux',
  is_docker: false
}

vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
  ok: true,
  json: () => Promise.resolve(defaultRulesResponse)
})))

await import('../../static/local-js/pathValidation.js')
const PathValidation = window.PathValidation

// Prime the module's internal cache with the default response.
// All subsequent attach() calls reuse this state.
await PathValidation.init()

describe('PathValidation.attach', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('binds an input whose name matches a rule id', async () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="config-dir" value="/etc/kometa">
      </div>
    `
    await PathValidation.attach(document)
    const input = document.querySelector('input[name="config-dir"]')
    expect(input.dataset.pathValidationBound).toBe('true')
    expect(input.dataset.pathValid).toBe('true')
  })

  it('binds an input whose name ends with -<rule-id>', async () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="custom-config-dir" value="/etc/kometa">
      </div>
    `
    await PathValidation.attach(document)
    const input = document.querySelector('input[name="custom-config-dir"]')
    expect(input.dataset.pathValidationBound).toBe('true')
  })

  it('honors data-path-rule as an explicit rule selector', async () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="something-else" data-path-rule="assets-dir" value="/var/assets">
      </div>
    `
    await PathValidation.attach(document)
    const input = document.querySelector('input[name="something-else"]')
    expect(input.dataset.pathValidationBound).toBe('true')
  })

  it('does not bind inputs whose name matches no rule', async () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="random-field" value="anything">
      </div>
    `
    await PathValidation.attach(document)
    const input = document.querySelector('input[name="random-field"]')
    expect(input.dataset.pathValidationBound).toBeUndefined()
  })

  it('marks an invalid path with is-invalid and sets feedback message', async () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="config-dir" value="relative/path">
      </div>
    `
    await PathValidation.attach(document)
    const input = document.querySelector('input[name="config-dir"]')
    expect(input.classList.contains('is-invalid')).toBe(true)
    expect(input.dataset.pathValid).toBe('false')
    const feedback = document.querySelector('.invalid-feedback')
    expect(feedback.textContent).toBe('Path must be absolute.')
  })

  it('accepts a relative path when the rule sets allow_relative: true', async () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="logs-dir" value="relative/path">
      </div>
    `
    await PathValidation.attach(document)
    const input = document.querySelector('input[name="logs-dir"]')
    expect(input.dataset.pathValid).toBe('true')
  })

  it('clears is-invalid when value becomes valid after input event', async () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="config-dir" value="bad/relative">
      </div>
    `
    await PathValidation.attach(document)
    const input = document.querySelector('input[name="config-dir"]')
    expect(input.classList.contains('is-invalid')).toBe(true)

    input.value = '/good/absolute'
    input.dispatchEvent(new Event('input'))

    expect(input.classList.contains('is-invalid')).toBe(false)
    expect(input.dataset.pathValid).toBe('true')
  })

  it('does not double-bind on repeated attach()', async () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="config-dir" value="/etc/kometa">
      </div>
    `
    await PathValidation.attach(document)
    await PathValidation.attach(document)
    await PathValidation.attach(document)
    // Inputs default to listening once per bind, so triple-bind would
    // wire up three listeners. We can't easily count listeners in jsdom,
    // but we can verify the bound flag is still 'true' (idempotent) and
    // no exception fires.
    const input = document.querySelector('input[name="config-dir"]')
    expect(input.dataset.pathValidationBound).toBe('true')
  })
})

describe('PathValidation.validateValue (via validateAll round-trip on linux)', () => {
  // validateValue is not exported. We exercise it through attach + value
  // assignment, then read the .pathValid dataset attribute. This is a
  // less direct but more user-realistic interface.

  beforeEach(() => {
    document.body.innerHTML = ''
  })

  async function checkPath (value, ruleName = 'config-dir') {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="${ruleName}" value="${value}">
      </div>
    `
    await PathValidation.attach(document)
    const input = document.querySelector(`input[name="${ruleName}"]`)
    return input.dataset.pathValid === 'true'
  }

  async function pathError (value, ruleName = 'config-dir') {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="${ruleName}" value="${value}">
      </div>
    `
    await PathValidation.attach(document)
    const feedback = document.querySelector('.invalid-feedback')
    return feedback ? feedback.textContent : null
  }

  it('accepts empty string as valid (caller decides required-ness)', async () => {
    expect(await checkPath('')).toBe(true)
  })

  it('accepts whitespace-only as valid', async () => {
    expect(await checkPath('   ')).toBe(true)
  })

  it('accepts "none" as a valid sentinel', async () => {
    expect(await checkPath('none')).toBe(true)
  })

  it('accepts "null" as a valid sentinel', async () => {
    expect(await checkPath('null')).toBe(true)
  })

  it('accepts "NONE" case-insensitively', async () => {
    expect(await checkPath('NONE')).toBe(true)
  })

  it('accepts a standard linux absolute path', async () => {
    expect(await checkPath('/var/lib/kometa')).toBe(true)
  })

  it('rejects a Windows-style absolute path on linux', async () => {
    expect(await checkPath('C:\\\\Users\\\\bob')).toBe(false)
    expect(await pathError('C:\\\\Users\\\\bob')).toBe('Windows-style paths are not valid on Linux/macOS/Docker.')
  })

  it('rejects a UNC-style path on linux', async () => {
    expect(await checkPath('\\\\\\\\server\\\\share')).toBe(false)
  })

  it('rejects a relative path when rule requires absolute', async () => {
    expect(await checkPath('relative/sub/dir')).toBe(false)
    expect(await pathError('relative/sub/dir')).toBe('Path must be absolute.')
  })

  it('rejects a literal \\0 null sequence', async () => {
    expect(await checkPath('/var/lib/\\0nasty')).toBe(false)
    expect(await pathError('/var/lib/\\0nasty')).toBe('Contains an invalid null sequence.')
  })

  it('rejects a literal \\x00 sequence', async () => {
    expect(await checkPath('/var/lib/\\x00nasty')).toBe(false)
    expect(await pathError('/var/lib/\\x00nasty')).toBe('Contains an invalid null sequence.')
  })

  it('rejects a literal \\u0000 sequence', async () => {
    expect(await checkPath('/var/lib/\\u0000nasty')).toBe(false)
    expect(await pathError('/var/lib/\\u0000nasty')).toBe('Contains an invalid null sequence.')
  })
})

describe('PathValidation.validateAll', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('returns true when all bound inputs are valid', async () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="config-dir" value="/etc/kometa">
      </div>
      <div class="input-group">
        <input type="text" name="assets-dir" value="/var/assets">
      </div>
    `
    await PathValidation.attach(document)
    expect(PathValidation.validateAll(document)).toBe(true)
  })

  it('returns false when any bound input is invalid', async () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="config-dir" value="/etc/kometa">
      </div>
      <div class="input-group">
        <input type="text" name="assets-dir" value="not absolute">
      </div>
    `
    await PathValidation.attach(document)
    expect(PathValidation.validateAll(document)).toBe(false)
  })

  it('returns true when container has no path inputs at all', async () => {
    document.body.innerHTML = '<div></div>'
    expect(PathValidation.validateAll(document)).toBe(true)
  })

  it('scopes validation to the passed container', async () => {
    document.body.innerHTML = `
      <div id="card-a" class="input-group">
        <input type="text" name="config-dir" value="bad relative">
      </div>
      <div id="card-b" class="input-group">
        <input type="text" name="assets-dir" value="/var/assets">
      </div>
    `
    await PathValidation.attach(document)
    const cardB = document.getElementById('card-b')
    expect(PathValidation.validateAll(cardB)).toBe(true)
  })
})

describe('PathValidation platform-status hint rendering', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('renders both Windows and Linux/macOS/Docker lines for rules that opt in', async () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="config-dir" value="/etc/kometa">
      </div>
    `
    await PathValidation.attach(document)
    const hintEl = document.querySelector('[data-path-hint="platform-status"]')
    expect(hintEl).not.toBeNull()
    expect(hintEl.textContent).toMatch(/Windows.*OK/)
    expect(hintEl.textContent).toMatch(/Linux\/macOS\/Docker.*OK/)
  })

  it('omits the platform-status hint when rule.ui.platform_status is false', async () => {
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="logs-dir" value="relative/ok">
      </div>
    `
    await PathValidation.attach(document)
    const hintEl = document.querySelector('[data-path-hint="platform-status"]')
    expect(hintEl).toBeNull()
  })

  it('shows the Windows line as failed when the value contains a reserved Windows segment', async () => {
    // Path must be Windows-absolute AND contain a reserved name, or the
    // "must be absolute" check runs first and we never reach the
    // reserved-segment branch. (The value is also invalid on linux
    // because Windows-style paths are rejected there — but we're only
    // asserting the Windows line here.)
    document.body.innerHTML = `
      <div class="input-group">
        <input type="text" name="config-dir" value="C:\\\\path\\\\with\\\\CON">
      </div>
    `
    await PathValidation.attach(document)
    const hintEl = document.querySelector('[data-path-hint="platform-status"]')
    const windowsLine = hintEl.querySelector('.text-danger')
    expect(windowsLine).not.toBeNull()
    expect(windowsLine.textContent).toMatch(/Windows.*reserved/)
  })
})
