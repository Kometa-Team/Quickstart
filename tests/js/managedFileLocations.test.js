import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const source = readFileSync(resolve(__dirname, '../../static/local-js/025-libraries.js'), 'utf8')
const applySource = source.slice(source.indexOf('function applyNormalizedLibraryFileLocation'), source.indexOf('function buildMetadataFileRow'))
const applyLocation = new Function(`${applySource}; return applyNormalizedLibraryFileLocation`)()
const playlistSource = source.slice(source.indexOf('function normalizePlaylistFileEntry'), source.indexOf('function buildPlaylistFileRow'))
const parsePlaylists = new Function(`${playlistSource}; return parsePlaylistFilesValue`)()
const syncSource = source.slice(source.indexOf('function syncPlaylistFilesEditor'), source.indexOf('function renderPlaylistFilesEditor'))
const syncPlaylists = new Function(
  'normalizePlaylistFileEntry', 'parseOverlayFileTemplateVariables', 'setLibraryFileTemplateVariablesFeedback', 'updatePlaylistFilesAccordionState',
  `${syncSource}; return syncPlaylistFilesEditor`
)(entry => parsePlaylists(JSON.stringify([entry]))[0], raw => ({ value: JSON.parse(raw), errors: [] }), () => {}, () => {})

beforeEach(() => { document.body.replaceChildren() })

describe.each(['collection', 'metadata', 'overlay', 'playlist'])('%s managed file location', kind => {
  it('puts the server location into the visible input and saved payload', () => {
    const editor = document.createElement('div')
    editor.innerHTML = `<div data-row><input data-${kind}-file-location value="/import/original.yml"></div>`
    const row = editor.querySelector('[data-row]')
    const location = `config/custom_main/${kind}_files/shared/file.yml`
    const sync = vi.fn()
    applyLocation(row, `[data-${kind}-file-location]`, { normalized_location: location }, editor, sync)
    expect(row.querySelector('input').value).toBe(location)
    expect(sync).toHaveBeenCalledWith(editor, false)
  })
})

it('retains the managed playlist path, schedule and template variables through save and reload', () => {
  const editor = document.createElement('div')
  editor.innerHTML = `
    <input type="hidden" name="playlist_files_entries">
    <div data-playlist-file-row data-playlist-file-state="success">
      <input data-playlist-file-type value="file">
      <input data-playlist-file-location value="main/playlist_files/shared_playlist_files/playlists_97bfe05e18.yml">
      <input data-playlist-file-schedule value="daily">
      <input data-playlist-file-template-variables value='{"test":"preserved"}'>
    </div>`
  const location = 'config/main/playlist_files/shared_playlist_files/playlists_97bfe05e18.yml'
  applyLocation(editor.querySelector('[data-playlist-file-row]'), '[data-playlist-file-location]', { normalized_location: location }, editor, syncPlaylists)
  const persisted = editor.querySelector('[name="playlist_files_entries"]').value
  expect(parsePlaylists(persisted)).toEqual([{
    type: 'file', location, schedule: 'daily', template_variables: { test: 'preserved' }, validated: true
  }])
})
