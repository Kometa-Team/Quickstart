import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { applyLibraryFileServerErrors, libraryFileRowMatches } from '../../static/local-js/modules/libraryFileErrors.js'

const source = readFileSync(resolve(__dirname, '../../static/local-js/025-libraries.js'), 'utf8')
const omissionSource = source.slice(source.indexOf('function shouldOmitDefaultFieldFromLibraryPayload'), source.indexOf('function buildPayloadFromCard'))
const shouldOmit = new Function('isInternalTemplateMetadataField', 'isCollectionSectionFieldConfigured', `${omissionSource}; return shouldOmitDefaultFieldFromLibraryPayload`)(() => false, () => false)

beforeEach(() => { document.body.replaceChildren() })

describe.each(['collection_files', 'metadata_files', 'overlay_files'])('%s error identity', kind => {
  const prefix = kind.replace(/_files$/, '-file')
  function editorWith (entries) {
    const editor = document.createElement('div')
    editor.dataset.libraryId = 'mov-library_1'
    entries.forEach(entry => {
      const row = document.createElement('div')
      row.setAttribute(`data-${prefix}-row`, '')
      row.innerHTML = `<input data-${prefix}-type><input data-${prefix}-location>`
      row.querySelector(`[data-${prefix}-type]`).value = entry.type
      row.querySelector(`[data-${prefix}-location]`).value = entry.location
      editor.append(row)
    })
    document.body.append(editor)
    return editor
  }
  const file = { type: 'file', location: 'config/local.yml' }
  const url = { type: 'url', location: 'https://example.test/missing.yml' }

  it('keeps an explicit empty list in the save payload', () => {
    const field = document.createElement('input')
    field.type = 'hidden'
    field.name = `mov-library_1-${kind}`
    field.dataset.default = '[]'
    field.value = '[]'
    expect(shouldOmit(field)).toBe(false)
  })

  it('does not change default omission for unrelated fields', () => {
    const field = document.createElement('input')
    field.name = 'mov-library_1-attribute_cache'
    field.dataset.default = 'true'
    expect(shouldOmit(field)).toBe(true)
  })

  it('ignores another library error at the same row index', () => {
    const editor = editorWith([file])
    const setStatus = vi.fn()
    expect(applyLibraryFileServerErrors(editor, [`sho-library_2 ${kind}[1]: failed`], kind, [file], setStatus)).toBe(false)
    expect(setStatus).not.toHaveBeenCalled()
  })

  it('finds the original source after a preceding row is removed', () => {
    const editor = editorWith([url])
    const setStatus = vi.fn()
    expect(applyLibraryFileServerErrors(editor, [`mov-library_1 ${kind}[2]: missing`], kind, [file, url], setStatus)).toBe(true)
    expect(setStatus).toHaveBeenCalledWith(editor.firstElementChild, 'error', 'missing')
  })

  it('does not apply a removed URL error to the remaining local file', () => {
    const editor = editorWith([file])
    const setStatus = vi.fn()
    expect(applyLibraryFileServerErrors(editor, [`mov-library_1 ${kind}[1]: missing`], kind, [url, file], setStatus)).toBe(false)
    expect(setStatus).not.toHaveBeenCalled()
  })

  it('does not apply stale errors after editing a location or source type', () => {
    const editor = editorWith([{ ...url, location: 'https://example.test/new.yml' }])
    const setStatus = vi.fn()
    expect(applyLibraryFileServerErrors(editor, [`mov-library_1 ${kind}[1]: missing`], kind, [url], setStatus)).toBe(false)
    expect(libraryFileRowMatches(editor.firstElementChild, kind, url)).toBe(false)
    expect(setStatus).not.toHaveBeenCalled()
  })

  it('handles filtered blank rows without shifting the error', () => {
    const editor = editorWith([{ type: 'file', location: '' }, url])
    const setStatus = vi.fn()
    applyLibraryFileServerErrors(editor, [`mov-library_1 ${kind}[1]: missing`], kind, [url], setStatus)
    expect(setStatus).toHaveBeenCalledWith(editor.lastElementChild, 'error', 'missing')
  })

  it('matches duplicate sources by occurrence', () => {
    const editor = editorWith([url, url])
    const setStatus = vi.fn()
    applyLibraryFileServerErrors(editor, [`mov-library_1 ${kind}[2]: missing`], kind, [url, url], setStatus)
    expect(setStatus).toHaveBeenCalledWith(editor.lastElementChild, 'error', 'missing')
  })
})
