"""Pure helpers for the config-import routes.

Split out of :mod:`blueprints.import_config_routes` -- these are 12
side-effect-free helpers that the four ``/import-config/*`` routes
share.  Moving them here keeps the route blueprint focused on
request handling while these live where they can be unit-tested
in isolation.

## What lives here

* ``_import_preview_json_default`` -- JSON serializer default for
  ``Path`` and ``set`` types used in the preview cache.
* ``_coerce_validation_response_payload`` -- unwraps a Flask
  validation response into its inner dict.
* ``_parse_csv_or_list_to_set`` -- coerces a CSV string or list
  into a stripped set of strings.
* ``_parse_base_plex_libraries`` -- looks up cached movie/show
  library names from a saved base config.
* Six credential parsers (three each for Plex and TMDb, one each
  for the config-file, base-config, and form-field inputs).
* ``count_annotated_lines`` -- counts YAML lines tagged with
  ``# imported`` or ``# not imported``.
* ``_map_playlist_libraries`` -- rewrites playlist library names
  through a mapping dict, honoring the ``__ignore__`` sentinel.

## Backward compatibility

``blueprints.import_config_routes`` re-exports every helper so
that ``from blueprints.import_config_routes import ...`` and the
``quickstart.py`` re-export chain keep working unchanged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from modules import database


def _import_preview_json_default(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(str(item) for item in value)
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return isoformat()
        except Exception:
            pass
    return str(value)


def _coerce_validation_response_payload(response):
    if isinstance(response, tuple) and response:
        response = response[0]
    if hasattr(response, "get_json"):
        response = response.get_json()
    return response if isinstance(response, dict) else {}


def _parse_csv_or_list_to_set(value):
    """Coerce a library-list value into a set of name strings.

    Leading/trailing whitespace is preserved in list and JSON-list forms
    so that library names like " Movies " survive the round-trip.
    Whitespace is used only as a filter (to skip blank values).
    CSV values are still stripped because comma-delimited items typically
    have spaces around the commas.

    Accepts four forms:
    - Python list of dicts  (fresh validation response: ``[{"id": 10, "name": " Movies "}, ...]``)
    - JSON string           (new format — library names may contain commas)
    - CSV string            (legacy format — backward compat with old stored data)
    - Python list of str    (already decoded)
    """
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return {str(v.get("name", "")) for v in value if str(v.get("name", "")).strip()}
        return {str(v) for v in value if str(v).strip()}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                if parsed and isinstance(parsed[0], dict):
                    return {str(v.get("name", "")) for v in parsed if str(v.get("name", "")).strip()}
                return {str(v) for v in parsed if str(v).strip()}
        except (json.JSONDecodeError, ValueError):
            pass
        return {v.strip() for v in value.split(",") if v.strip()}
    return set()


def _parse_csv_or_list_to_id_map(value):
    """Coerce a library-list value into a ``{id: name}`` map.

    Sibling to :func:`_parse_csv_or_list_to_set`, accepting the same four
    shapes.  Dict items key by their Plex section ID (``{"id": 10, "name":
    "Movies"} -> {"10": "Movies"}``).  Plain-string items (the shape every
    mocked ``validate_plex_server`` in the test suite returns, and the
    legacy stored-settings format) self-map by name, since no ID is known
    for them -- the caller degrades to name-based resolution for those.
    """
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return {str(v.get("id", "")): str(v.get("name", "")) for v in value if str(v.get("name", "")).strip()}
        return {str(v): str(v) for v in value if str(v).strip()}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                if parsed and isinstance(parsed[0], dict):
                    return {str(v.get("id", "")): str(v.get("name", "")) for v in parsed if str(v.get("name", "")).strip()}
                return {str(v): str(v) for v in parsed if str(v).strip()}
        except (json.JSONDecodeError, ValueError):
            pass
        return {v.strip(): v.strip() for v in value.split(",") if v.strip()}
    return {}


def _plex_library_id_maps(plex_data):
    """Return ``(movie_id_map, show_id_map)`` as ``{str(id): name}`` from stored Plex data.

    Handles both the new ID-based format (where ``tmp_library_names`` holds the
    ID→name dict) and the legacy format (where names are stored directly in
    ``tmp_movie_libraries`` / ``tmp_show_libraries``, with no ID available --
    self-mapped by name so callers can degrade gracefully).
    """
    name_map_raw = plex_data.get("tmp_library_names", "")
    if name_map_raw:
        try:
            name_map = {str(k): str(v) for k, v in json.loads(name_map_raw).items()}
        except (json.JSONDecodeError, ValueError):
            name_map = {}
        from modules.persistence import decode_library_ids

        movie_ids = decode_library_ids(plex_data.get("tmp_movie_libraries", ""))
        show_ids = decode_library_ids(plex_data.get("tmp_show_libraries", ""))
        movie_id_map = {i: name_map[i] for i in movie_ids if i in name_map}
        show_id_map = {i: name_map[i] for i in show_ids if i in name_map}
        return movie_id_map, show_id_map
    # Legacy: names stored directly, no IDs known -- self-map.
    movie_names = _parse_csv_or_list_to_set(plex_data.get("tmp_movie_libraries", ""))
    show_names = _parse_csv_or_list_to_set(plex_data.get("tmp_show_libraries", ""))
    return {name: name for name in movie_names}, {name: name for name in show_names}


def _plex_library_name_sets(plex_data):
    """Return ``(movie_name_set, show_name_set)`` from stored Plex data.

    Thin wrapper over :func:`_plex_library_id_maps` for the many callers
    that only need names, not IDs.
    """
    movie_id_map, show_id_map = _plex_library_id_maps(plex_data)
    return set(movie_id_map.values()), set(show_id_map.values())


def _parse_base_plex_library_id_maps(base_name: str):
    """Look up cached movie/show library ``{id: name}`` maps from a saved base config."""
    if not base_name:
        return {}, {}
    try:
        _validated, _user_entered, stored = database.retrieve_section_data(base_name, "plex")
    except Exception:
        return {}, {}
    if not isinstance(stored, dict):
        return {}, {}
    plex_block = stored.get("plex") if isinstance(stored.get("plex"), dict) else stored
    if not isinstance(plex_block, dict):
        return {}, {}
    return _plex_library_id_maps(plex_block)


def _parse_base_plex_libraries(base_name: str):
    """Look up cached movie/show library names from a saved base config.

    DRY refactor: pre-refactor this lived as an inner closure named
    ``parse_base_plex_libraries`` in TWO routes (import_config_preview,
    import_config_confirm) with byte-for-byte identical 13-line bodies
    (26 lines of literal duplication).  Hoisted to module scope.

    Thin wrapper over :func:`_parse_base_plex_library_id_maps` for callers
    that only need names, not IDs.
    """
    movie_id_map, show_id_map = _parse_base_plex_library_id_maps(base_name)
    return set(movie_id_map.values()), set(show_id_map.values())


# --- credential parsers ---------------------------------------------------
#
# Six tiny pure functions that pull ``(url, token)`` / ``api_key`` out of the
# three shapes credentials might arrive in during an import:
#
#   * ``_parse_*_from_config`` -- an already-loaded YAML/dict from the
#     uploaded config file
#   * ``_parse_*_from_base``   -- the persisted section data of a *different*
#     saved config, when the caller is merging into it
#   * ``_parse_*_from_form``   -- the raw form fields submitted alongside
#     the upload
#
# Hoisted from nested closures inside ``import_config_preview`` where they
# were 52 lines of setup that had zero closure state -- the elephant
# function shed ~50 lines and these are now unit-testable in isolation.


def _parse_plex_credentials_from_config(config_data):
    plex_block = config_data.get("plex", {}) if isinstance(config_data, dict) else {}
    if not isinstance(plex_block, dict):
        return "", ""
    url = plex_block.get("url") or plex_block.get("plex_url") or ""
    token = plex_block.get("token") or plex_block.get("plex_token") or ""
    return str(url).strip(), str(token).strip()


def _parse_plex_credentials_from_base(base_name: str):
    if not base_name:
        return "", ""
    try:
        _validated, _user_entered, stored = database.retrieve_section_data(base_name, "plex")
    except Exception:
        return "", ""
    if not isinstance(stored, dict):
        return "", ""
    if "plex" in stored:
        return _parse_plex_credentials_from_config(stored)
    url = stored.get("url") or stored.get("plex_url") or ""
    token = stored.get("token") or stored.get("plex_token") or ""
    return str(url).strip(), str(token).strip()


def _parse_plex_credentials_from_form(form_data):
    url = form_data.get("plex_url", "") or ""
    token = form_data.get("plex_token", "") or ""
    return str(url).strip(), str(token).strip()


def _parse_tmdb_credentials_from_config(config_data):
    tmdb_block = config_data.get("tmdb", {}) if isinstance(config_data, dict) else {}
    if not isinstance(tmdb_block, dict):
        return ""
    api_key = tmdb_block.get("apikey") or tmdb_block.get("api_key") or tmdb_block.get("tmdb_apikey") or tmdb_block.get("token") or ""
    return str(api_key).strip()


def _parse_tmdb_credentials_from_base(base_name: str):
    if not base_name:
        return ""
    try:
        _validated, _user_entered, stored = database.retrieve_section_data(base_name, "tmdb")
    except Exception:
        return ""
    if not isinstance(stored, dict):
        return ""
    if "tmdb" in stored:
        return _parse_tmdb_credentials_from_config(stored)
    api_key = stored.get("apikey") or stored.get("api_key") or stored.get("tmdb_apikey") or stored.get("token") or ""
    return str(api_key).strip()


def _parse_tmdb_credentials_from_form(form_data):
    api_key = form_data.get("tmdb_apikey", "") or ""
    return str(api_key).strip()


def count_annotated_lines(text: str) -> dict:
    """Count YAML lines tagged with ``# imported`` or ``# not imported``.

    DRY refactor: this body existed twice -- once as a module-level
    function in quickstart.py and once as an inner closure inside
    ``import_config_preview``, byte-for-byte identical.  Now the inner
    copy is gone and both call sites use this module-level version.
    """
    imported = 0
    not_imported = 0
    if not isinstance(text, str):
        return {"imported": 0, "not_imported": 0}
    imported_pattern = re.compile(r"(?:#|\|) imported(?:\s*-.*)?$")
    not_imported_pattern = re.compile(r"(?:#|\|) not imported(?:\s*-.*)?$")
    for line in text.splitlines():
        trimmed = line.rstrip()
        if imported_pattern.search(trimmed):
            imported += 1
        elif not_imported_pattern.search(trimmed):
            not_imported += 1
    return {"imported": imported, "not_imported": not_imported}


def _map_playlist_libraries(payload, library_mapping, plex_names, id_lookup=None):
    if not isinstance(payload, dict):
        return
    playlist_payload = payload.get("playlist_files")
    if not isinstance(playlist_payload, list):
        return
    mapped_entries = []
    for entry in playlist_payload:
        if not isinstance(entry, dict):
            mapped_entries.append(entry)
            continue
        tv = entry.get("template_variables")
        if isinstance(tv, dict):
            libs = tv.get("libraries")
            if isinstance(libs, list):
                mapped = []
                for lib in libs:
                    name = str(lib).strip()
                    if not name:
                        continue
                    mapped_name = library_mapping.get(name, name)
                    if mapped_name is None:
                        mapped_name = name
                    mapped_name = str(mapped_name).strip()
                    # Explicit mapping selections are Plex library IDs; resolve
                    # to the current display name.  Passes through unchanged
                    # when mapped_name isn't a known ID (e.g. an exact-name match).
                    mapped_name = (id_lookup or {}).get(mapped_name, mapped_name)
                    if not mapped_name or mapped_name == "__ignore__":
                        continue
                    mapped.append(mapped_name)
                deduped = []
                seen = set()
                for lib_name in mapped:
                    if lib_name in seen:
                        continue
                    seen.add(lib_name)
                    deduped.append(lib_name)
                if plex_names:
                    deduped = [lib_name for lib_name in deduped if lib_name in plex_names]
                tv = dict(tv)
                tv["libraries"] = deduped
                entry = dict(entry)
                entry["template_variables"] = tv
        mapped_entries.append(entry)
    payload["playlist_files"] = mapped_entries
