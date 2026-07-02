"""Collection / franchise template-variable normalization for output.py.

Extracted from the original ``modules/output.py`` monolith.  This module
handles four related concerns around **collection-shaped** template
variables (mirroring what ``output_playlists.py`` does for playlists):

1. **Per-key value normalization** -- ``_normalize_collection_template_var_value``
   dispatches by field name (ignore_ids / addons / title_override / etc.)
   to the appropriate parser.  Special-cases ``tmdb_birthday`` and
   ``tmdb_deathday`` through the dedicated
   ``_parse_tmdb_person_window`` parser.

2. **TMDb person window parsing** -- ``_parse_tmdb_person_window``
   accepts a JSON string, python literal, or ``key=value`` /
   ``key: value`` newline-or-comma-separated shorthand, and emits a
   normalized dict.  Handles the ``this_month`` boolean and
   ``before`` / ``after`` numeric windows.

3. **Franchise 'dynamic child override' expansion** --
   ``_expand_franchise_dynamic_child_overrides`` walks a template_vars
   dict, finds the ``child_*_overrides`` mapping keys declared in
   ``FRANCHISE_DYNAMIC_CHILD_FIELD_SPECS``, and expands each mapping
   into flat ``<prefix><suffix>`` keys on the parent dict.
   ``_normalize_dynamic_child_override_value`` handles the per-kind
   value coercion.

4. **Settings-block ignore-list normalization** --
   ``_normalize_settings_section_value`` handles ignore_ids /
   ignore_imdb_ids for the top-level settings block (kept here rather
   than in output_values because it's tightly coupled to the collection
   normalization pipeline).

None of these are public API.  ``modules/output.py`` re-imports them via
``# noqa: F401`` so historical call sites like
``output._normalize_collection_template_var_value(...)`` keep working
(tests reach for it directly).
"""

from __future__ import annotations

import ast
import json
import re

from modules.output_values import (
    _coerce_bool,
    _parse_comma_string_list,
    _parse_string_list,
    _parse_string_list_mapping,
    _parse_string_mapping,
    _parse_template_mapping_dict,
    _to_number,
)

# --- franchise dynamic-child override specs -------------------------------

FRANCHISE_DYNAMIC_CHILD_FIELD_SPECS = {
    "child_name_overrides": ("name_", "string"),
    "child_summary_overrides": ("summary_", "string"),
    "child_sort_title_overrides": ("sort_title_", "string"),
    "child_sync_mode_overrides": ("sync_mode_", "select"),
    "child_collection_order_overrides": ("collection_order_", "select"),
    "child_url_poster_overrides": ("url_poster_", "string"),
    "child_radarr_add_missing_overrides": ("radarr_add_missing_", "boolean"),
    "child_radarr_folder_overrides": ("radarr_folder_", "string"),
    "child_radarr_tag_overrides": ("radarr_tag_", "string_list"),
    "child_item_radarr_tag_overrides": ("item_radarr_tag_", "string_list"),
    "child_radarr_monitor_overrides": ("radarr_monitor_", "boolean"),
    "child_sonarr_add_missing_overrides": ("sonarr_add_missing_", "boolean"),
    "child_sonarr_folder_overrides": ("sonarr_folder_", "string"),
    "child_sonarr_tag_overrides": ("sonarr_tag_", "string_list"),
    "child_item_sonarr_tag_overrides": ("item_sonarr_tag_", "string_list"),
    "child_sonarr_monitor_overrides": ("sonarr_monitor_", "select"),
}


# --- TMDb person window ---------------------------------------------------


def _parse_tmdb_person_window(value):
    if value is None:
        return None

    raw_text = None
    parsed = value
    if isinstance(value, str):
        raw_text = value.strip()
        if not raw_text:
            return None
        try:
            parsed = json.loads(raw_text)
        except Exception:
            try:
                parsed = ast.literal_eval(raw_text)
            except Exception:
                candidate = {}
                valid_candidate = True
                for part in re.split(r"[\n;,]+", raw_text):
                    piece = str(part or "").strip()
                    if not piece:
                        continue
                    if "=" in piece:
                        key_text, raw_val = piece.split("=", 1)
                    elif ":" in piece:
                        key_text, raw_val = piece.split(":", 1)
                    else:
                        valid_candidate = False
                        break
                    key_text = key_text.strip()
                    raw_val = raw_val.strip()
                    if not key_text:
                        valid_candidate = False
                        break
                    candidate[key_text] = raw_val
                parsed = candidate if valid_candidate and candidate else raw_text

    if not isinstance(parsed, dict):
        return raw_text if raw_text is not None else value

    normalized = {}
    raw_this_month = parsed.get("this_month")
    if raw_this_month not in (None, ""):
        bool_value = _coerce_bool(raw_this_month)
        normalized["this_month"] = bool_value if bool_value is not None else raw_this_month

    for key in ("before", "after"):
        raw_number = parsed.get(key)
        if raw_number in (None, ""):
            continue
        number = _to_number(raw_number)
        if number is None:
            normalized[key] = raw_number
        elif float(number).is_integer():
            normalized[key] = int(number)
        else:
            normalized[key] = number

    for raw_key, raw_value in parsed.items():
        key_text = str(raw_key or "").strip()
        if not key_text or key_text in normalized or key_text in {"this_month", "before", "after"}:
            continue
        if raw_value in (None, ""):
            continue
        normalized[key_text] = raw_value

    return normalized or (raw_text if raw_text is not None else value)


# --- collection template var normalization --------------------------------


def _normalize_collection_template_var_value(key, value):
    if key in {"ignore_ids", "ignore_imdb_ids"}:
        list_values = _parse_string_list(value)
        return ",".join(list_values) if list_values else None
    if key in {"append_include"}:
        list_values = _parse_string_list(value)
        return list_values if list_values else None
    if key in {"addons", "append_addons"}:
        mapping_values = _parse_string_list_mapping(value)
        return mapping_values if mapping_values else None
    if key == "title_override":
        mapping_values = _parse_string_mapping(value)
        return mapping_values if mapping_values else None
    if key in {"tmdb_birthday", "tmdb_deathday"}:
        return _parse_tmdb_person_window(value)
    if key == "remove_suffix":
        list_values = _parse_comma_string_list(value)
        return ",".join(list_values) if list_values else None
    if key in {"radarr_tag", "sonarr_tag", "item_radarr_tag", "item_sonarr_tag"} or key.startswith(("radarr_tag_", "sonarr_tag_", "item_radarr_tag_", "item_sonarr_tag_")):
        list_values = _parse_string_list(value)
        return list_values if list_values else None
    return value


# --- franchise dynamic child overrides ------------------------------------


def _normalize_dynamic_child_override_value(value_kind, raw_value):
    if raw_value in (None, ""):
        return None

    kind = str(value_kind or "string").strip().lower()
    if kind == "string_list":
        list_values = _parse_comma_string_list(raw_value)
        return list_values if list_values else None
    if kind == "boolean":
        bool_value = _coerce_bool(raw_value)
        return bool_value if bool_value is not None else raw_value
    return raw_value


def _expand_franchise_dynamic_child_overrides(template_vars):
    if not isinstance(template_vars, dict):
        return

    for field_key, (child_prefix, value_kind) in FRANCHISE_DYNAMIC_CHILD_FIELD_SPECS.items():
        if field_key not in template_vars:
            continue

        raw_mapping = template_vars.pop(field_key, None)
        mapping = _parse_template_mapping_dict(raw_mapping)
        if not mapping:
            continue

        for raw_suffix, raw_value in mapping.items():
            suffix = str(raw_suffix or "").strip()
            if not suffix:
                continue
            normalized_value = _normalize_dynamic_child_override_value(value_kind, raw_value)
            if normalized_value is None:
                continue
            template_vars[f"{child_prefix}{suffix}"] = normalized_value


# --- top-level settings section normalization -----------------------------


def _normalize_settings_section_value(key, value):
    if key in {"ignore_ids", "ignore_imdb_ids"}:
        list_values = _parse_string_list(value)
        return ",".join(list_values) if list_values else None
    return value
