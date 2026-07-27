// Smoke test for the externalYamlEditor subsystem extraction (#1334 Step 9).
//
// This module was carved out of static/local-js/025-libraries.js as a
// direct-mode dependency-injection subsystem. The bulk of its behaviour
// is DOM manipulation glued to a Bootstrap modal that only makes sense
// on the full libraries page, and is exercised by the existing manual
// QA loop plus the Python route tests under
// tests/test_external_yaml_editor.py.
//
// What we test here is the *contract* of the module: it exports a
// single named factory, the factory is idempotent, and the returned
// subsystem exposes updateExternalYamlEditButton for row builders.
// If someone refactors the module and breaks the export shape,
// 025-libraries.js will fail to boot -- this test catches that before
// the change ships.

import { describe, it, expect } from 'vitest'
import * as mod from '../../../static/local-js/modules/externalYamlEditor.js'

const stubDeps = () => ({
  kinds: {},
  getActiveConfigName: () => '',
  setLibrariesButtonPersistentBusy: () => {},
  prepareLibrariesModal: (el) => el
})

describe('externalYamlEditor module', () => {
  it('exports initExternalYamlEditorSubsystem', () => {
    expect(typeof mod.initExternalYamlEditorSubsystem).toBe('function')
  })

  it('returns an object with updateExternalYamlEditButton', () => {
    const subsystem = mod.initExternalYamlEditorSubsystem(stubDeps())
    expect(typeof subsystem.updateExternalYamlEditButton).toBe('function')
  })

  it('is idempotent -- second call returns the same instance', () => {
    const first = mod.initExternalYamlEditorSubsystem(stubDeps())
    const second = mod.initExternalYamlEditorSubsystem(stubDeps())
    expect(second).toBe(first)
  })

  it('updateExternalYamlEditButton is a safe no-op for unknown kinds', () => {
    const { updateExternalYamlEditButton } = mod.initExternalYamlEditorSubsystem(stubDeps())
    expect(() => updateExternalYamlEditButton(null, 'not_a_real_kind')).not.toThrow()
    const row = document.createElement('div')
    expect(() => updateExternalYamlEditButton(row, 'not_a_real_kind')).not.toThrow()
  })
})
