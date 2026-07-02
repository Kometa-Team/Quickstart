"""Playlist file-entry and library-selection helpers for output.py.

Extracted from the original ``modules/output.py`` monolith.  These nine
helpers all deal with one of two closely-related concerns:

1. **Playlist file entries** -- the ``playlist_files:`` YAML block that
   Kometa consumes.  Entries come in as raw JSON/py-literal strings,
   dicts, or lists, and need to be normalized into
   ``{file|url|git|repo: <location>}`` shapes.  ``_format_*`` /
   ``_normalize_*`` / ``_parse_playlist_file_entries_value`` cover this.

2. **Selecting which libraries feed a playlist** -- pulling library
   names out of the nested per-library toggle data, honouring the order
   from ``build_libraries_section``, and falling back to the older
   settings-level playlist_files.libraries CSV when the per-library
   toggles are absent.  ``_ordered_selected_libraries``,
   ``_library_names_in_output_order``, and the four
   ``_*_playlist_libraries_*`` helpers cover this.

None of these are public API.  ``modules/output.py`` re-exports them via
an explicit ``from modules.output_playlists import ...`` block so the
existing internal call sites keep working.
"""

from __future__ import annotations

import ast
import json

from modules import persistence
from modules.output_values import _coerce_bool


def _normalize_playlist_file_entry_for_output(entry):
    if not isinstance(entry, dict):
        return None
    direct_entry = next(((key, value) for key, value in entry.items() if key in {"file", "url", "git", "repo"}), None)
    if direct_entry:
        entry_type, location = direct_entry
        location = str(location or "").strip()
        if location:
            return {entry_type: location}
        return None
    entry_type = str(entry.get("type") or "").strip().lower()
    location = str(entry.get("location") or "").strip()
    if entry_type not in {"file", "url", "git", "repo"} or not location:
        return None
    return {entry_type: location}


def _parse_playlist_file_entries_value(value):
    if value in [None, "", "[]"]:
        return []
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            try:
                parsed = ast.literal_eval(value)
            except Exception:
                return []
    if not isinstance(parsed, list):
        return []
    entries = []
    for entry in parsed:
        normalized = _normalize_playlist_file_entry_for_output(entry)
        if normalized:
            entries.append(normalized)
    return entries


def _format_playlist_file_entries(libraries_list=None, template_variables=None, extra_entries=None):
    entries = []

    if libraries_list:
        normalized_template_variables = {}
        if isinstance(template_variables, dict):
            normalized_template_variables.update(template_variables)
        normalized_template_variables["libraries"] = libraries_list
        entries.append(
            {
                "default": "playlist",
                "template_variables": normalized_template_variables,
            }
        )

    for entry in extra_entries or []:
        normalized_entry = _normalize_playlist_file_entry_for_output(entry)
        if normalized_entry:
            entries.append(normalized_entry)

    return {"playlist_files": entries}


# --- library selection ----------------------------------------------------


def _ordered_selected_libraries(selected_names, ordered_library_names):
    if not selected_names:
        return []

    ordered = []
    seen = set()

    for library_name in ordered_library_names or []:
        if library_name in selected_names and library_name not in seen:
            ordered.append(library_name)
            seen.add(library_name)

    for library_name in selected_names:
        if library_name not in seen:
            ordered.append(library_name)
            seen.add(library_name)

    return ordered


def _library_names_in_output_order(libraries_section):
    if isinstance(libraries_section, dict) and isinstance(libraries_section.get("libraries"), dict):
        return list(libraries_section["libraries"].keys())
    return []


def _playlist_libraries_from_library_toggles(nested_libraries_data, ordered_library_names=None):
    if not isinstance(nested_libraries_data, dict):
        return False, []

    has_playlist_toggle = any(isinstance(key, str) and key.endswith("-playlist") for key in nested_libraries_data)
    playlist_libraries = []

    for key, value in nested_libraries_data.items():
        if not isinstance(key, str) or not key.endswith("-library"):
            continue
        if value in [None, "", False]:
            continue
        prefix = key[: -len("-library")]
        include_playlist = _coerce_bool(nested_libraries_data.get(f"{prefix}-playlist"))
        if include_playlist is not True:
            continue
        library_name = str(value).strip()
        if library_name:
            playlist_libraries.append(library_name)

    return has_playlist_toggle, _ordered_selected_libraries(playlist_libraries, ordered_library_names)


def _legacy_playlist_libraries_from_settings():
    settings = persistence.retrieve_settings("027-playlist_files") or {}
    playlist_payload = settings.get("playlist_files", {}) if isinstance(settings, dict) else {}
    if isinstance(playlist_payload, dict) and isinstance(playlist_payload.get("playlist_files"), dict):
        playlist_payload = playlist_payload.get("playlist_files", {})
    raw_libraries = playlist_payload.get("libraries", "") if isinstance(playlist_payload, dict) else ""
    if isinstance(raw_libraries, list):
        return [str(item).strip() for item in raw_libraries if str(item).strip()]
    return [item.strip() for item in str(raw_libraries or "").split(",") if item.strip()]


def _legacy_playlist_libraries_for_selected_libraries(nested_libraries_data, ordered_library_names=None):
    legacy_names = set(_legacy_playlist_libraries_from_settings())
    if not legacy_names or not isinstance(nested_libraries_data, dict):
        return []

    selected_libraries = []
    for key, value in nested_libraries_data.items():
        if not isinstance(key, str) or not key.endswith("-library"):
            continue
        library_name = str(value or "").strip()
        if library_name and library_name in legacy_names:
            selected_libraries.append(library_name)

    return _ordered_selected_libraries(selected_libraries, ordered_library_names)
