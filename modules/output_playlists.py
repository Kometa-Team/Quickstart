"""Playlist file-entry, library-selection, and template-variable helpers for output.py.

Extracted from the original ``modules/output.py`` monolith.  These helpers
all deal with one of three closely-related concerns:

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

3. **Playlist template variable normalization** -- once per-library
   playlist toggles are resolved, the raw ``playlist-template_variables[...]``
   form values need to be coerced/parsed by kind (string_list, boolean,
   integer, string, ignore_ids).  The ``PLAYLIST_*_TEMPLATE_VAR_SPECS``
   dicts declare the expected kinds; ``_normalize_playlist_template_var_value``,
   ``_normalize_playlist_keyed_template_var_value``,
   ``_collect_playlist_template_variables_from_libraries_data``, and
   ``_collect_playlist_file_entries_from_libraries_data`` do the work.

None of these are public API.  ``modules/output.py`` re-exports them via
an explicit ``from modules.output_playlists import ...`` block so the
existing internal call sites keep working.
"""

from __future__ import annotations

import ast
import json
import re

from modules import persistence
from modules.output_values import (
    _coerce_bool,
    _parse_comma_string_list,
    _parse_template_mapping_dict,
    _playlist_scalar_or_list,
    _to_number,
)

# --- template-var kind specs ---------------------------------------------

PLAYLIST_SHARED_TEMPLATE_VAR_SPECS = {
    "sync_to_users": "string_list",
    "exclude_users": "string_list",
    "delete_playlist": "boolean",
    "ignore_ids": "ignore_ids",
    "ignore_imdb_ids": "string_list",
    "item_radarr_tag": "string_list",
    "item_sonarr_tag": "string_list",
    "radarr_add_missing": "boolean",
    "radarr_folder": "string",
    "radarr_tag": "string_list",
    "sonarr_add_missing": "boolean",
    "sonarr_folder": "string",
    "sonarr_tag": "string_list",
    "trakt_list": "string_list",
    "imdb_list": "string_list",
    "mdblist_list": "string_list",
}
PLAYLIST_KEYED_TEMPLATE_VAR_SPECS = {
    "use_": "boolean",
    "name_": "string",
    "summary_": "string",
    "url_poster_": "string",
    "delete_playlist_": "boolean",
    "exclude_users_": "string_list",
    "exclude_user_": "string_list",
    "imdb_list_": "string_list",
    "item_radarr_tag_": "string_list",
    "item_sonarr_tag_": "string_list",
    "mdblist_list_": "string_list",
    "radarr_add_missing_": "boolean",
    "radarr_folder_": "string",
    "radarr_tag_": "string_list",
    "sonarr_add_missing_": "boolean",
    "sonarr_folder_": "string",
    "sonarr_tag_": "string_list",
    "sync_to_users_": "string_list",
    "trakt_list_": "string_list",
}


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


def _playlist_libraries_from_library_toggles(nested_libraries_data, ordered_library_names=None, library_names_by_prefix=None):
    if not isinstance(nested_libraries_data, dict):
        return False, []

    library_names_by_prefix = library_names_by_prefix or {}
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
        mapped_name = library_names_by_prefix.get(prefix)
        if mapped_name is not None:
            library_name = str(mapped_name)
        else:
            library_name = str(value).strip()
        if library_name.strip():
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


# --- template variable normalization ------------------------------------


def _normalize_playlist_template_var_value(key, value):
    if key == "ignore_ids":
        list_values = _parse_comma_string_list(value)
        if not list_values:
            return None
        if len(list_values) == 1:
            number = _to_number(list_values[0])
            if isinstance(number, (int, float)) and float(number).is_integer():
                return int(number)
            return list_values[0]
        return ", ".join(list_values)
    if key in {
        "sync_to_users",
        "exclude_users",
        "exclude_user",
        "ignore_imdb_ids",
        "item_radarr_tag",
        "item_sonarr_tag",
        "radarr_tag",
        "sonarr_tag",
        "trakt_list",
        "imdb_list",
        "mdblist_list",
    }:
        return _playlist_scalar_or_list(_parse_comma_string_list(value))
    if key in {"delete_playlist", "radarr_add_missing", "sonarr_add_missing"}:
        return _coerce_bool(value)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_playlist_keyed_template_var_value(value_kind, raw_value):
    if raw_value in (None, ""):
        return None
    kind = str(value_kind or "string").strip().lower()
    if kind == "string_list":
        return _playlist_scalar_or_list(_parse_comma_string_list(raw_value))
    if kind == "boolean":
        return _coerce_bool(raw_value)
    if kind == "integer":
        number = _to_number(raw_value)
        if isinstance(number, (int, float)) and float(number).is_integer():
            return int(number)
        return None
    text = str(raw_value).strip()
    return text or None


def _collect_playlist_template_variables_from_libraries_data(nested_libraries_data):
    if not isinstance(nested_libraries_data, dict):
        return {}

    template_vars = {}

    for raw_key, raw_value in nested_libraries_data.items():
        if not isinstance(raw_key, str):
            continue
        match = re.fullmatch(r"playlist-template_variables\[(.+)\]", raw_key)
        if not match:
            continue

        field_key = str(match.group(1) or "").strip()
        if not field_key or field_key == "libraries":
            continue

        if field_key == "exclude_user":
            field_key = "exclude_users"
        if field_key == "exclude_user_":
            field_key = "exclude_users_"

        if field_key in PLAYLIST_KEYED_TEMPLATE_VAR_SPECS:
            mapping = _parse_template_mapping_dict(raw_value)
            if not mapping:
                continue
            value_kind = PLAYLIST_KEYED_TEMPLATE_VAR_SPECS[field_key]
            for raw_suffix, mapping_value in mapping.items():
                suffix = str(raw_suffix or "").strip()
                if not suffix:
                    continue
                normalized_value = _normalize_playlist_keyed_template_var_value(value_kind, mapping_value)
                if normalized_value is None:
                    continue
                template_vars[f"{field_key}{suffix}"] = normalized_value
            continue

        if field_key not in PLAYLIST_SHARED_TEMPLATE_VAR_SPECS:
            continue

        normalized_value = _normalize_playlist_template_var_value(field_key, raw_value)
        if field_key in {"delete_playlist", "radarr_add_missing", "sonarr_add_missing"} and normalized_value is False:
            continue
        if normalized_value is not None:
            template_vars[field_key] = normalized_value

    return template_vars


def _collect_playlist_file_entries_from_libraries_data(nested_libraries_data):
    if not isinstance(nested_libraries_data, dict):
        return []
    return _parse_playlist_file_entries_value(nested_libraries_data.get("playlist_files_entries"))


def apply_playlist_libraries_toggle(config_data, nested_libraries_data, libraries_section, library_names_by_prefix=None):
    """Compute ``config_data['playlist_files']`` from library-level toggles.

    Runs AFTER :func:`build_libraries_section` has produced the ordered
    library set.  Two branches:

    * **New shape** (``has_playlist_toggle`` is True) -- the user
      opted into playlists via per-library ``playlist_files`` toggles.
      Use the toggle-derived library list.  When neither libraries
      nor raw file-block entries exist, the playlist_files section
      is stripped entirely (any stale value from the earlier
      ``normalize_playlist_files_section`` pass is discarded).

    * **Legacy shape** (no toggle present) -- fall back to the older
      ``_legacy_playlist_libraries_for_selected_libraries`` derivation.
      When neither libraries nor raw entries exist, leaves any earlier
      normalize result in place (legacy configs may still populate
      the section without a library-level toggle).

    Mutates *config_data* in place.  No-op when
    *nested_libraries_data* isn't a dict.
    """
    ordered_library_names = _library_names_in_output_order(libraries_section)
    has_playlist_toggle, playlist_libraries = _playlist_libraries_from_library_toggles(
        nested_libraries_data,
        ordered_library_names=ordered_library_names,
        library_names_by_prefix=library_names_by_prefix,
    )
    playlist_template_variables = _collect_playlist_template_variables_from_libraries_data(nested_libraries_data)
    playlist_file_entries = _collect_playlist_file_entries_from_libraries_data(nested_libraries_data)

    if has_playlist_toggle:
        if playlist_libraries or playlist_file_entries:
            config_data["playlist_files"] = _format_playlist_file_entries(
                libraries_list=playlist_libraries,
                template_variables=playlist_template_variables,
                extra_entries=playlist_file_entries,
            )
        else:
            config_data.pop("playlist_files", None)
        return

    # Legacy: no library-toggle present.
    legacy_libraries = _legacy_playlist_libraries_for_selected_libraries(
        nested_libraries_data,
        ordered_library_names=ordered_library_names,
    )
    if legacy_libraries or playlist_file_entries:
        config_data["playlist_files"] = _format_playlist_file_entries(
            libraries_list=legacy_libraries,
            template_variables=playlist_template_variables,
            extra_entries=playlist_file_entries,
        )
