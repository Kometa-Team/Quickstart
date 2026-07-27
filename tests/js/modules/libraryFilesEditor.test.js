// Behavioural tests for the shared library-files-editor subsystem
// (#1334 Step 9 dedupe).
//
// This module replaces 43 near-duplicate per-kind functions that used
// to live in static/local-js/025-libraries.js. The unit tests below
// exercise the shared implementation directly with a synthetic per-kind
// config, so a regression in any of the 11 helper families would fail
// here regardless of which kind (metadata / collection / overlay /
// playlist) triggered it.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createLibraryFilesEditor } from '../../../static/local-js/modules/libraryFilesEditor.js'

// A minimal but realistic normalizer: keep entries that have both a
// type and a location, otherwise reject.
const stubNormalize = ({ type, location, validated } = {}) => {
  const t = String(type || '').trim()
  const l = String(location || '').trim()
  if (!t || !l) return null
  return { type: t, location: l, validated: Boolean(validated) }
}

const stubParse = (raw) => {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.map(stubNormalize).filter(Boolean) : []
  } catch { return [] }
}

// A minimal row builder that produces the same DOM shape the real
// buildLibraryFileRow does: the row wrapper, a type <select>, a
// location <input>, a status <div>, and a validate <button>.
const makeStubBuildRow = (domPrefix) => (entry = {}) => {
  const row = document.createElement('div')
  row.setAttribute(`data-${domPrefix}-row`, '')
  row.innerHTML = `
    <select data-${domPrefix}-type>
      <option value="">--</option>
      <option value="file">file</option>
      <option value="repo">repo</option>
      <option value="url">url</option>
    </select>
    <input data-${domPrefix}-location value="${entry.location || ''}">
    <div data-${domPrefix}-status></div>
    <button data-validate-${domPrefix}>Validate</button>
  `
  row.querySelector(`[data-${domPrefix}-type]`).value = entry.type || ''
  if (entry.validated) row.dataset[camel(`${domPrefix}-state`)] = 'success'
  return row
}

const camel = (kebab) => kebab.replace(/-([a-z])/g, (_, c) => c.toUpperCase())

const makeSharedDeps = (overrides = {}) => ({
  getCustomRepoBase: () => '',
  getCustomRepoRaw: () => '',
  appendMetadataSettingsLink: (target) => target.append('[settings]'),
  appendInlineCodeText: (target, text) => target.append(text),
  updateAccordionHighlights: vi.fn(),
  ...overrides
})

const makeConfig = (overrides = {}) => ({
  kind: 'test_files',
  domPrefix: 'test-file',
  editorSelector: '[data-test-files-editor]',
  listSelector: '[data-test-files-list]',
  hiddenInputSelector: 'input[type="hidden"][name="test_files_entries"]',
  customRepoStatusSelector: '[data-test-custom-repo-status]',
  repoDependencyMessage: 'Test file repo entries require Custom Repo...',
  kindWord: 'test',
  entryLabel: 'test files',
  normalizeEntry: stubNormalize,
  parseFilesValue: stubParse,
  buildRow: makeStubBuildRow('test-file'),
  truncateLongFileLists: true,
  showCustomRepoSavedValueDiff: true,
  accordionStateStyle: 'toggle',
  ...overrides
})

const makeEditor = () => {
  const editor = document.createElement('div')
  editor.setAttribute('data-test-files-editor', '')
  editor.innerHTML = `
    <div data-test-custom-repo-status></div>
    <div data-test-files-list></div>
    <input type="hidden" name="test_files_entries" value="">
  `
  // Wrap in an accordion-item so updateAccordionState finds a header
  const accordionItem = document.createElement('div')
  accordionItem.className = 'accordion-item'
  const header = document.createElement('div')
  header.className = 'accordion-header'
  accordionItem.appendChild(header)
  accordionItem.appendChild(editor)
  document.body.appendChild(accordionItem)
  return { editor, header, accordionItem }
}

describe('createLibraryFilesEditor', () => {
  beforeEach(() => { document.body.innerHTML = '' })

  it('exposes all 11 helper methods', () => {
    const ed = createLibraryFilesEditor(makeConfig(), makeSharedDeps())
    for (const name of [
      'updateValidateButton', 'setButtonState', 'applyDependencyState',
      'renderStatusMessage', 'setStatus', 'updateCustomRepoStatus',
      'updateAccordionState', 'applyServerErrors', 'syncEditor',
      'renderEditor', 'initEditors'
    ]) {
      expect(typeof ed[name]).toBe('function')
    }
  })

  describe('updateValidateButton', () => {
    const setup = () => {
      const ed = createLibraryFilesEditor(makeConfig(), makeSharedDeps())
      const row = makeStubBuildRow('test-file')({ type: 'file', location: 'x.yml' })
      return { ed, row, btn: row.querySelector('[data-validate-test-file]') }
    }

    it('renders "Validate" when idle', () => {
      const { ed, row, btn } = setup()
      ed.updateValidateButton(row, false)
      expect(btn.textContent).toBe('Validate')
      expect(btn.disabled).toBe(false)
      expect(btn.classList.contains('btn-success')).toBe(true)
    })

    it('renders "Validated" when isValidated', () => {
      const { ed, row, btn } = setup()
      ed.updateValidateButton(row, true)
      expect(btn.textContent).toBe('Validated')
      expect(btn.disabled).toBe(true)
      expect(btn.classList.contains('btn-secondary')).toBe(true)
    })

    it('renders "Needs Repo" when blocked', () => {
      const { ed, row, btn } = setup()
      row.dataset.testFileButtonState = 'blocked'
      ed.updateValidateButton(row, false)
      expect(btn.textContent).toBe('Needs Repo')
      expect(btn.disabled).toBe(true)
    })

    it('renders "Validating..." when loading', () => {
      const { ed, row, btn } = setup()
      row.dataset.testFileButtonState = 'loading'
      ed.updateValidateButton(row, false)
      expect(btn.textContent).toBe('Validating...')
    })

    it('is a safe no-op for a null row', () => {
      const { ed } = setup()
      expect(() => ed.updateValidateButton(null, false)).not.toThrow()
    })
  })

  describe('applyDependencyState', () => {
    it('flags a repo-typed row when Custom Repo base is missing', () => {
      const ed = createLibraryFilesEditor(makeConfig(), makeSharedDeps())
      const row = makeStubBuildRow('test-file')({ type: 'repo', location: 'x' })
      const target = document.createElement('div'); row.appendChild(target)
      row.querySelector('[data-test-file-status]').replaceWith(target)
      target.setAttribute('data-test-file-status', '')
      expect(ed.applyDependencyState(row, { skipStatus: true })).toBe(true)
      expect(row.dataset.testFileDependency).toBe('repo-missing')
    })

    it('clears the flag once Custom Repo base is configured', () => {
      const deps = makeSharedDeps({ getCustomRepoBase: () => 'https://x' })
      const ed = createLibraryFilesEditor(makeConfig(), deps)
      const row = makeStubBuildRow('test-file')({ type: 'repo', location: 'x' })
      row.dataset.testFileDependency = 'repo-missing'
      ed.applyDependencyState(row)
      expect(row.dataset.testFileDependency).toBe('')
    })

    it('returns false for non-repo types', () => {
      const ed = createLibraryFilesEditor(makeConfig(), makeSharedDeps())
      const row = makeStubBuildRow('test-file')({ type: 'file', location: 'x' })
      expect(ed.applyDependencyState(row)).toBe(false)
    })
  })

  describe('renderStatusMessage', () => {
    it('truncates >5 file lists into a <details> when truncateLongFileLists is on', () => {
      const ed = createLibraryFilesEditor(makeConfig({ truncateLongFileLists: true }), makeSharedDeps())
      const target = document.createElement('div')
      ed.renderStatusMessage(target, { text: 'boom', files: ['a', 'b', 'c', 'd', 'e', 'f'] })
      expect(target.querySelector('details')).not.toBeNull()
    })

    it('always inlines file lists when truncateLongFileLists is off', () => {
      const ed = createLibraryFilesEditor(makeConfig({ truncateLongFileLists: false }), makeSharedDeps())
      const target = document.createElement('div')
      ed.renderStatusMessage(target, { text: 'boom', files: Array.from({ length: 20 }, (_, i) => `f${i}`) })
      expect(target.querySelector('details')).toBeNull()
      expect(target.querySelectorAll('li').length).toBe(20)
    })

    it('rewrites the repo-dependency message into humane prose with a settings link', () => {
      const cfg = makeConfig({ repoDependencyMessage: 'MAGIC_DEPS', kindWord: 'metadata' })
      const ed = createLibraryFilesEditor(cfg, makeSharedDeps())
      const target = document.createElement('div')
      ed.renderStatusMessage(target, 'MAGIC_DEPS')
      expect(target.textContent).toContain('Metadata file repo entries require Custom Repo')
      expect(target.textContent).toContain('[settings]')
    })
  })

  describe('updateCustomRepoStatus', () => {
    it('renders the "not configured" warning when Custom Repo base is empty', () => {
      const ed = createLibraryFilesEditor(makeConfig(), makeSharedDeps())
      const { editor } = makeEditor()
      ed.updateCustomRepoStatus(editor)
      const target = editor.querySelector('[data-test-custom-repo-status]')
      expect(target.classList.contains('alert-warning')).toBe(true)
      expect(target.textContent).toContain('Custom Repo is not configured')
      expect(target.textContent).toContain('test files.')
    })

    it('renders the "base used" summary when Custom Repo base is set', () => {
      const deps = makeSharedDeps({
        getCustomRepoBase: () => 'https://repo/base',
        getCustomRepoRaw: () => 'https://repo/base'
      })
      const ed = createLibraryFilesEditor(makeConfig(), deps)
      const { editor } = makeEditor()
      ed.updateCustomRepoStatus(editor)
      const target = editor.querySelector('[data-test-custom-repo-status]')
      expect(target.classList.contains('alert-secondary')).toBe(true)
      expect(target.textContent).toContain('https://repo/base')
    })

    it('shows the saved-value drift only when showCustomRepoSavedValueDiff is on', () => {
      const deps = makeSharedDeps({
        getCustomRepoBase: () => 'https://repo/base',
        getCustomRepoRaw: () => 'https://repo/base/trailing'
      })

      const withDiff = createLibraryFilesEditor(makeConfig({ showCustomRepoSavedValueDiff: true }), deps)
      const { editor: e1 } = makeEditor()
      withDiff.updateCustomRepoStatus(e1)
      expect(e1.querySelector('[data-test-custom-repo-status]').textContent).toContain('https://repo/base/trailing')

      const withoutDiff = createLibraryFilesEditor(makeConfig({ showCustomRepoSavedValueDiff: false }), deps)
      const { editor: e2 } = makeEditor()
      withoutDiff.updateCustomRepoStatus(e2)
      expect(e2.querySelector('[data-test-custom-repo-status]').textContent).not.toContain('trailing')
    })
  })

  describe('updateAccordionState', () => {
    it('toggles .invalid and .selected under the "toggle" style', () => {
      const ed = createLibraryFilesEditor(makeConfig({ accordionStateStyle: 'toggle' }), makeSharedDeps())
      const { editor, header } = makeEditor()
      // Empty editor -> no .selected
      ed.updateAccordionState(editor)
      expect(header.classList.contains('selected')).toBe(false)
      // Add a real row
      editor.querySelector('[data-test-files-list]').appendChild(
        makeStubBuildRow('test-file')({ type: 'file', location: 'x.yml' })
      )
      ed.updateAccordionState(editor)
      expect(header.classList.contains('selected')).toBe(true)
      expect(header.classList.contains('invalid')).toBe(false)
    })

    it('flips to .invalid when any row is in an error/warning state', () => {
      const ed = createLibraryFilesEditor(makeConfig(), makeSharedDeps())
      const { editor, header } = makeEditor()
      const row = makeStubBuildRow('test-file')({ type: 'file', location: 'x.yml' })
      row.dataset.testFileState = 'error'
      editor.querySelector('[data-test-files-list]').appendChild(row)
      ed.updateAccordionState(editor)
      expect(header.classList.contains('invalid')).toBe(true)
    })

    it('calls updateAccordionHighlights when the editor drains empty (toggle style)', () => {
      const deps = makeSharedDeps()
      const ed = createLibraryFilesEditor(makeConfig({ accordionStateStyle: 'toggle' }), deps)
      const { editor } = makeEditor()
      ed.updateAccordionState(editor)
      expect(deps.updateAccordionHighlights).toHaveBeenCalled()
    })

    it('does NOT call updateAccordionHighlights under "early-return" style', () => {
      const deps = makeSharedDeps()
      const ed = createLibraryFilesEditor(makeConfig({ accordionStateStyle: 'early-return' }), deps)
      const { editor } = makeEditor()
      ed.updateAccordionState(editor)
      expect(deps.updateAccordionHighlights).not.toHaveBeenCalled()
    })
  })

  describe('applyServerErrors', () => {
    it('routes indexed errors to the correct row', () => {
      const ed = createLibraryFilesEditor(makeConfig(), makeSharedDeps())
      const { editor } = makeEditor()
      const list = editor.querySelector('[data-test-files-list]')
      list.appendChild(makeStubBuildRow('test-file')({ type: 'file', location: 'a.yml' }))
      list.appendChild(makeStubBuildRow('test-file')({ type: 'file', location: 'b.yml' }))
      const applied = ed.applyServerErrors(editor, ['test_files[2]: nope'])
      expect(applied).toBe(true)
      const rows = list.querySelectorAll('[data-test-file-row]')
      expect(rows[1].dataset.testFileState).toBe('error')
      expect(rows[0].dataset.testFileState).toBe('')
    })

    it('is a no-op for an empty error list', () => {
      const ed = createLibraryFilesEditor(makeConfig(), makeSharedDeps())
      const { editor } = makeEditor()
      expect(ed.applyServerErrors(editor, [])).toBe(false)
    })
  })

  describe('syncEditor', () => {
    it('writes the filtered entry list into the hidden input', () => {
      const ed = createLibraryFilesEditor(makeConfig(), makeSharedDeps())
      const { editor } = makeEditor()
      const list = editor.querySelector('[data-test-files-list]')
      list.appendChild(makeStubBuildRow('test-file')({ type: 'file', location: 'a.yml' }))
      list.appendChild(makeStubBuildRow('test-file')({ type: '', location: '' })) // gets normalized away
      const entries = ed.syncEditor(editor, false)
      expect(entries).toEqual([{ type: 'file', location: 'a.yml', validated: false }])
      const hidden = editor.querySelector('input[type="hidden"]')
      expect(JSON.parse(hidden.value)).toEqual([{ type: 'file', location: 'a.yml', validated: false }])
    })

    it('emits input/change events when emitEvents is true', () => {
      const ed = createLibraryFilesEditor(makeConfig(), makeSharedDeps())
      const { editor } = makeEditor()
      const hidden = editor.querySelector('input[type="hidden"]')
      let inputs = 0, changes = 0
      hidden.addEventListener('input', () => inputs++)
      hidden.addEventListener('change', () => changes++)
      ed.syncEditor(editor, true)
      expect(inputs).toBe(1); expect(changes).toBe(1)
    })

    it('suppresses re-entrant emits when syncingGuardKey is set', () => {
      const ed = createLibraryFilesEditor(makeConfig({ syncingGuardKey: 'testSyncing' }), makeSharedDeps())
      const { editor } = makeEditor()
      const hidden = editor.querySelector('input[type="hidden"]')
      let emits = 0
      // A listener that recursively triggers a sync during the first emit.
      hidden.addEventListener('input', () => {
        emits++
        if (emits === 1) ed.syncEditor(editor, true)  // should NOT re-emit
      })
      ed.syncEditor(editor, true)
      expect(emits).toBe(1)
    })
  })

  describe('renderEditor + initEditors', () => {
    it('renders rows from the hidden input value on first init', () => {
      const ed = createLibraryFilesEditor(makeConfig(), makeSharedDeps())
      const { editor } = makeEditor()
      editor.querySelector('input[type="hidden"]').value = JSON.stringify([
        { type: 'file', location: 'a.yml' },
        { type: 'file', location: 'b.yml' }
      ])
      ed.initEditors(document)
      const rows = editor.querySelectorAll('[data-test-file-row]')
      expect(rows.length).toBe(2)
      expect(editor.dataset.testFilesReady).toBe('true')
    })

    it('is idempotent -- initEditors() re-run leaves the editor untouched', () => {
      const ed = createLibraryFilesEditor(makeConfig(), makeSharedDeps())
      const { editor } = makeEditor()
      editor.querySelector('input[type="hidden"]').value = JSON.stringify([{ type: 'file', location: 'a.yml' }])
      ed.initEditors(document)
      const firstRow = editor.querySelector('[data-test-file-row]')
      ed.initEditors(document)
      expect(editor.querySelector('[data-test-file-row]')).toBe(firstRow)
    })
  })
})
