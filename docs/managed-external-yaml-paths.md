# Managed external YAML paths

Investigation of [Quickstart #1941](https://github.com/Kometa-Team/Quickstart/issues/1941), based on develop at `ede6e4f9`.

## Confirmed cause and impact

Managed copies are stored beneath Quickstart's `CONFIG_DIR`, for example
`<CONFIG_DIR>/main/playlist_files/shared_playlist_files/playlists_97bfe05e18.yml`.
The copy helper returns a storage-relative path. The display helper previously
recognized only metadata, collection and overlay directories, so it did not
convert playlist paths into Kometa references. The serializer emitted that
incorrect value unchanged.

The same omission existed in the directories synced to Kometa and in bundle
export/import, which also assumed every external file belonged to a library.
Playlist files belong at the top level of the main configuration. This was an
incomplete shared implementation, rather than an incorrect user selection.

The three library file types already received the expected `config/` prefix for
the standard runtime layout. All four types lacked destination-aware output
for an external config directory that differed from `<Kometa root>/config`.

## Path contract

Kometa's [DataFile.load_file](https://github.com/Kometa-Team/Kometa/blob/develop/modules/meta.py)
uses `os.path.abspath(file_path)` for local YAML files. Its
[util.load_files](https://github.com/Kometa-Team/Kometa/blob/develop/modules/util.py)
checks local folders against the working directory too. `external_templates`
uses those same functions. The parent directory of the main config or containing
external YAML file does not become an implicit base directory. Kometa defaults,
URLs, Git and Repo entries have their own resolution rules.

Quickstart launches managed/existing Kometa processes with `cwd=kometa_root`
in `modules/process_lifecycle.py`. Therefore:

| Purpose | Example |
| --- | --- |
| Quickstart storage | `<CONFIG_DIR>/main/playlist_files/shared_playlist_files/playlists_97bfe05e18.yml` |
| UI and database | `config/main/playlist_files/shared_playlist_files/playlists_97bfe05e18.yml` |
| Standard Kometa YAML | `config/main/playlist_files/shared_playlist_files/playlists_97bfe05e18.yml` |
| Synced standard destination | `<Kometa root>/config/main/playlist_files/shared_playlist_files/playlists_97bfe05e18.yml` |
| Custom external target | An absolute reference beneath the configured Kometa config directory |
| ZIP member | `main/playlist_files/shared_playlist_files/playlists_97bfe05e18.yml` |

Bundles use portable `config/...` references and explain where to install the
included tree. External runtimes must be able to see the configured target path;
Quickstart cannot infer a different container's volume mapping.

## Trace and shared implementation

1. `static/local-js/025-libraries.js` sends the selected file or folder to its
   validation endpoint. `applyNormalizedLibraryFileLocation` uses the returned
   location in both the visible input and the hidden form payload. Playlist
   entries use `playlist_files_entries`; library entries use library-prefixed
   fields. The editor saves the contents through `/external_yaml_file/save`.
2. `modules/library_file_entries.py` resolves local paths, validates them and
   copies unmanaged sources into the config-owned store. Existing managed
   sources are recognized on subsequent validations, avoiding another hashed
   copy. Playlist import normalization now uses this same implementation.
3. `modules/managed_file_paths.py` defines the shared managed YAML kinds, parses
   managed references, converts storage/display tokens into runtime references,
   and enumerates file blocks at the correct configuration scope.
4. `modules/validations_shared.py` resolves managed tokens against Quickstart
   storage. `modules/validations_yaml_files.py` checks content; playlist folders
   now use the common folder scanner instead of falling through to Repo.
5. `modules/persistence.py` saves and reloads the JSON entry lists in the named
   configuration's `libraries` database section. No database migration is needed.
6. `modules/output_file_entries.py` and `modules/output_playlists.py` use the same
   runtime conversion. This also corrects previously saved bare playlist tokens
   during export. `quickstart.py` validates generated references against storage,
   retaining schedule and template variables instead of replacing whole entries.
7. `modules/helpers/_artifacts.py` includes playlists when syncing config-owned
   artifacts. Existing playlist destination trees are adopted without deleting
   other files. `modules/bundle_artifacts.py` handles top-level playlists as well
   as library blocks, and restores portable references when bundling custom
   runtime paths.

Absolute user paths, unrelated relative paths, remote references, Kometa
defaults and existing type-first serialization remain unchanged. No migration
moves, renames or deletes previously appended source files.

Changed production files: `modules/managed_file_paths.py`,
`modules/library_file_entries.py`, `modules/output_file_entries.py`,
`modules/output_playlists.py`, `modules/bundle_artifacts.py`,
`modules/helpers/_artifacts.py`, `modules/validations_shared.py`,
`modules/validations_yaml_files.py`, and `quickstart.py`. The three new regression
files are listed below; this document records the audit.

## Additional audit findings

- Playlist imports previously skipped managed-file organization. Fixed.
- Playlist folder validation previously fell through to Repo validation. Fixed.
- Playlist form parsing and generated-file normalization could discard schedules
  and template variables. They now preserve those fields; overlay schedules
  retain their existing supported output behavior.
- The final page could normalize file references in application state while
  saving an older rendered YAML string. It now renders the updated state when
  normalization changes references, with a route regression for this case.
- Reusing files from older type-first stores could substitute a canonical
  archive location for the actual physical location. Existing files now retain
  their on-disk layout during normalization; bundle paths remain portable.
- External templates inside managed YAML are opaque content. Existing references
  are preserved. Quickstart does not recursively import or bundle dependencies
  outside an imported file/folder. A sibling template filename alone is not
  relative to that YAML file in Kometa. Users must provide runtime-valid paths
  and make those dependencies available. This remains a separate limitation.
- Overlay image overrides have their own managed store and bundle handling;
  custom fonts are copied separately. Their serializers still use `config/...`
  paths. Nonstandard external target directories can require separate handling
  for those assets; this change addresses external YAML file blocks, without
  rewriting arbitrary asset paths or YAML contents.

## Regression coverage

`tests/test_managed_file_paths.py` covers all four types as files and folders,
standard and custom destinations, editor saves, repeated validation, database
save/reload, final YAML generation, runtime artifact sync and ZIP export/import.
It checks old tokens, both path separators, custom config names, preservation of
appended content, existing destination files and unrelated valid references.
Pure path cases cover Windows drives, Linux and separate Docker config mounts.

`tests/test_kometa_file_path_contract.py` executes the actual installed Kometa
loader functions with filesystem/request adapters, checking generated local file,
folder and external-template references. It skips when only Kometa defaults are
installed. These cases also run inside a Linux container with a read-only source
mount and no network access.

`tests/js/managedFileLocations.test.js` checks that server-normalized locations
reach the visible controls and persisted playlist payload, including reload.

## Validation results

- Final focused Python run: 153 passed, including the final-page and legacy
  layout compatibility regressions added after the broader run.
- Full Python run: 2,458 passed, one skipped, one failed, 165 deselected (browser
  tests). The failure is `test_logscan_analyze_missing_log`: it expects HTTP 404
  but a live Kometa process produces HTTP 200 with `waiting_for_log`. The same
  response was reproduced using the unchanged develop route and wait helper.
  Removing the waiting condition yields the expected 404. No running user
  process was stopped or changed.
- JavaScript: all 1,857 tests passed across 58 files.
- ESLint, Ruff, Black formatting and Vite production build passed. Vite reports
  its existing warning about native config loading and the CommonJS config.
- Actual upstream Kometa loader: 16 Windows cases and 16 Linux/Docker cases
  passed, including file/folder references and external templates.
- The old-token and playlist-bundle regressions fail on untouched develop.
  A final-normalization regression also exposes the discarded entry options.

The first restricted full-suite attempt encountered ESLint subprocess startup
timeouts. All 19 ESLint subprocess tests passed when rerun outside that runner;
the completed full run above also passed those tests.
