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

3. **Dynamic child override expansion** --
   ``_expand_franchise_dynamic_child_overrides`` walks a template_vars
   dict, finds the supported ``child_*_overrides`` mapping keys, and
   expands each mapping into flat ``<prefix><suffix>`` keys on the
   parent dict. ``_normalize_dynamic_child_override_value`` handles
   the per-kind value coercion.

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

from modules import helpers
from modules.output_file_entries import _parse_collection_file_block_entries
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
    "child_use_overrides": ("use_", "boolean"),
    "child_name_overrides": ("name_", "string"),
    "child_summary_overrides": ("summary_", "string"),
    "child_sort_title_overrides": ("sort_title_", "string"),
    "child_order_overrides": ("order_", "string"),
    "child_schedule_overrides": ("schedule_", "string"),
    "child_name_mapping_overrides": ("name_mapping_", "string"),
    "child_emoji_overrides": ("emoji_", "string"),
    "child_sort_by_overrides": ("sort_by_", "select"),
    "child_delete_collections_named_overrides": ("delete_collections_named_", "string_list"),
    "child_discover_with_overrides": ("discover_with_", "string"),
    "child_movie_overrides": ("movie_", "string_list"),
    "child_tmdb_collection_overrides": ("tmdb_collection_", "string_list"),
    "child_tmdb_movie_overrides": ("tmdb_movie_", "string_list"),
    "child_imdb_list_overrides": ("imdb_list_", "string_list"),
    "child_imdb_search_overrides": ("imdb_search_", "json"),
    "child_mdblist_list_overrides": ("mdblist_list_", "string_list"),
    "child_letterboxd_list_overrides": ("letterboxd_list_", "string_list"),
    "child_trakt_list_overrides": ("trakt_list_", "string_list"),
    "child_sync_mode_overrides": ("sync_mode_", "select"),
    "child_collection_order_overrides": ("collection_order_", "select"),
    "child_cache_builders_overrides": ("cache_builders_", "string"),
    "child_image_overrides": ("image_", "string"),
    "child_translation_key_overrides": ("translation_key_", "string"),
    "child_url_poster_overrides": ("url_poster_", "string"),
    "child_file_poster_overrides": ("file_poster_", "string"),
    "child_url_background_overrides": ("url_background_", "string"),
    "child_file_background_overrides": ("file_background_", "string"),
    "child_url_logo_overrides": ("url_logo_", "string"),
    "child_file_logo_overrides": ("file_logo_", "string"),
    "child_url_square_art_overrides": ("url_square_art_", "string"),
    "child_file_square_art_overrides": ("file_square_art_", "string"),
    "child_limit_overrides": ("limit_", "integer"),
    "child_minimum_items_overrides": ("minimum_items_", "integer"),
    "child_tmdb_person_offset_overrides": ("tmdb_person_offset_", "integer"),
    "child_visible_home_overrides": ("visible_home_", "boolean"),
    "child_visible_library_overrides": ("visible_library_", "boolean"),
    "child_visible_shared_overrides": ("visible_shared_", "boolean"),
    "child_hub_priority_overrides": ("hub_priority_", "string"),
    "child_radarr_add_missing_overrides": ("radarr_add_missing_", "boolean"),
    "child_radarr_folder_overrides": ("radarr_folder_", "string"),
    "child_radarr_tag_overrides": ("radarr_tag_", "string_list"),
    "child_item_radarr_tag_overrides": ("item_radarr_tag_", "string_list"),
    "child_radarr_monitor_overrides": ("radarr_monitor_", "boolean"),
    "child_radarr_upgrade_existing_overrides": ("radarr_upgrade_existing_", "boolean"),
    "child_radarr_monitor_existing_overrides": ("radarr_monitor_existing_", "boolean"),
    "child_radarr_search_overrides": ("radarr_search_", "boolean"),
    "child_sonarr_add_missing_overrides": ("sonarr_add_missing_", "boolean"),
    "child_sonarr_folder_overrides": ("sonarr_folder_", "string"),
    "child_sonarr_tag_overrides": ("sonarr_tag_", "string_list"),
    "child_item_sonarr_tag_overrides": ("item_sonarr_tag_", "string_list"),
    "child_sonarr_monitor_overrides": ("sonarr_monitor_", "select"),
    "child_sonarr_upgrade_existing_overrides": ("sonarr_upgrade_existing_", "boolean"),
    "child_sonarr_monitor_existing_overrides": ("sonarr_monitor_existing_", "boolean"),
    "child_sonarr_search_overrides": ("sonarr_search_", "boolean"),
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


def _parse_json_object_value(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value

    raw_text = value.strip()
    if not raw_text:
        return None

    try:
        parsed = json.loads(raw_text)
    except Exception:
        try:
            parsed = ast.literal_eval(raw_text)
        except Exception:
            return value

    return parsed if isinstance(parsed, (dict, list)) else value


# --- collection template var normalization --------------------------------


def _sort_id_values(values):
    def sort_key(item):
        text = str(item).strip()
        if text.isdigit():
            return (0, int(text), text)
        return (1, text.lower(), text)

    return sorted(values, key=sort_key)


def _normalize_collection_template_var_value(key, value):
    if key == "collection_section" and value in (None, ""):
        return None
    if key in {"ignore_ids", "ignore_imdb_ids"}:
        list_values = _parse_string_list(value)
        return _sort_id_values(list_values) if list_values else None
    if key in {"append_include"}:
        list_values = _parse_string_list(value)
        return list_values if list_values else None
    if key in {"addons", "append_addons"}:
        mapping_values = _parse_string_list_mapping(value)
        return mapping_values if mapping_values else None
    if key == "title_override":
        mapping_values = _parse_string_mapping(value)
        return mapping_values if mapping_values else None
    if key in {"imdb_search", "plex_search"} or key.startswith(("imdb_search_", "plex_search_")):
        return _parse_json_object_value(value)
    if key in {"tmdb_birthday", "tmdb_deathday"}:
        return _parse_tmdb_person_window(value)
    if key == "remove_suffix":
        list_values = _parse_comma_string_list(value)
        return ",".join(list_values) if list_values else None
    if key in {"delete_collections_named"} or key.startswith(("delete_collections_named_", "keywords_")):
        list_values = _parse_string_list(value)
        return list_values if list_values else None
    if key in {
        "trakt_list",
        "imdb_list",
        "imdb_id",
        "mdblist_list",
        "letterboxd_list",
        "tmdb_collection",
        "tmdb_movie",
        "tmdb_show",
        "tmdb_list",
        "tvdb_movie",
        "tvdb_show",
        "tvdb_list",
    } or key.startswith(
        (
            "trakt_list_",
            "imdb_list_",
            "imdb_id_",
            "mdblist_list_",
            "letterboxd_list_",
            "tmdb_collection_",
            "tmdb_movie_",
            "tmdb_show_",
            "tmdb_list_",
            "tvdb_movie_",
            "tvdb_show_",
            "tvdb_list_",
        )
    ):
        list_values = _parse_comma_string_list(value)
        return list_values if list_values else None
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
    if kind == "integer":
        number = _to_number(raw_value)
        if number is None:
            return raw_value
        return int(number) if float(number).is_integer() else number
    if kind == "json":
        return _parse_json_object_value(raw_value)
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
    if key == "ignore_ids":
        list_values = _parse_string_list(value)
        normalized = []
        for item in list_values:
            try:
                normalized.append(int(str(item).strip()))
            except Exception:
                normalized.append(str(item).strip())
        return _sort_id_values(normalized) if normalized else None
    if key == "ignore_imdb_ids":
        list_values = _parse_string_list(value)
        return _sort_id_values(list_values) if list_values else None
    return value


# --- whole-config-tree walks over collection template variables -----------


def _iter_collection_file_template_vars(config_data):
    """Yield every ``template_variables`` dict on every collection_file entry.

    Handles both nested (``config["libraries"]["libraries"][name]``) and
    flat (``config["libraries"][name]``) shapes that appear at different
    stages of the build pipeline.  Yields nothing if the shape doesn't
    match -- callers rely on that behaviour.
    """
    if not isinstance(config_data, dict):
        return
    libraries_section = config_data.get("libraries", {})
    libraries = None
    if isinstance(libraries_section, dict):
        nested = libraries_section.get("libraries")
        libraries = nested if isinstance(nested, dict) else libraries_section
    if not isinstance(libraries, dict):
        return
    for library_data in libraries.values():
        if not isinstance(library_data, dict):
            continue
        collection_files = library_data.get("collection_files")
        if not isinstance(collection_files, list):
            continue
        for entry in collection_files:
            if not isinstance(entry, dict):
                continue
            template_vars = entry.get("template_variables")
            if isinstance(template_vars, dict):
                yield entry, template_vars


def _collapse_collection_data_template_vars(config_data):
    """Fold flat ``data_<sub>`` keys into a nested ``data:`` mapping.

    Kometa's collection defaults accept a ``data:`` mapping (e.g. actors,
    genres) but the quickstart form emits flat ``data_actors``,
    ``data_genres``, ... keys.  This walker collapses them.
    """
    for _entry, template_vars in _iter_collection_file_template_vars(config_data):
        data_block = {}
        for key in list(template_vars.keys()):
            if not isinstance(key, str) or not key.startswith("data_"):
                continue
            subkey = key[5:]
            if not subkey:
                continue
            value = template_vars.pop(key)
            if value is None:
                continue
            if isinstance(value, str):
                cleaned = value.strip()
                if not cleaned:
                    continue
                if cleaned.isdigit():
                    value = int(cleaned)
            data_block[subkey] = value
        if not data_block:
            continue
        existing = template_vars.get("data")
        if isinstance(existing, dict):
            existing.update(data_block)
            template_vars["data"] = existing
        else:
            template_vars["data"] = data_block
    return config_data


# Historic letterboxd rename: the top_250 lists became top_500 upstream.
_LETTERBOXD_LEGACY_KEY_MAP = {
    "use_top_250": "use_top_500",
    "radarr_add_missing_top_250": "radarr_add_missing_top_500",
    "visible_home_top_250": "visible_home_top_500",
    "visible_library_top_250": "visible_library_top_500",
    "visible_shared_top_250": "visible_shared_top_500",
    "limit_top_250": "limit_top_500",
}


def _normalize_legacy_collection_template_vars(config_data):
    """Rename legacy letterboxd ``*_top_250`` keys to ``*_top_500``."""
    for entry, template_vars in _iter_collection_file_template_vars(config_data):
        if entry.get("default") != "letterboxd":
            continue
        for old_key, new_key in _LETTERBOXD_LEGACY_KEY_MAP.items():
            if old_key not in template_vars or new_key in template_vars:
                continue
            template_vars[new_key] = template_vars.pop(old_key)
    return config_data


# ---------------------------------------------------------------------------
# Collection-file assembly.
#
# build_collection_files() is invoked once per library inside
# ``modules.output.build_libraries_section.add_entry`` to translate the
# per-library ``collections`` selection map into the ``collection_files``
# YAML block.
# ---------------------------------------------------------------------------

# Legacy Region key spelling migration.  Older Quickstart runs used
# "South Eastern Asia" (space); Kometa now expects the hyphenated form.
# When both keys exist, the new-key value wins.
_LEGACY_REGION_KEYS = {
    "use_South Eastern Asia": "use_South-Eastern Asia",
    "radarr_add_missing_South Eastern Asia": "radarr_add_missing_South-Eastern Asia",
    "sonarr_add_missing_South Eastern Asia": "sonarr_add_missing_South-Eastern Asia",
}

# Template-var keys that hold delimited lists.  Empty parses drop the key.
_LIST_KEYS = ("include", "exclude", "exclude_prefix")
_LOOKUP_LABELS_SUFFIX = "__lookup_labels"
_TEMPLATE_VARIABLE_COMMENTS_KEY = "__template_variable_comments"


def _coerce_bool_like_string(value):
    """Coerce case-insensitive "true"/"false" strings to bool, pass others through."""
    if isinstance(value, (bool, str)):
        lowered = str(value).lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return value


def _migrate_legacy_region_keys(template_vars):
    """Rewrite legacy ``South Eastern Asia`` region keys to the hyphenated form.

    Mutates *template_vars* in place.  When both the legacy and current keys
    are present, the current-key value wins (legacy is silently dropped).
    """
    for old_key, new_key in _LEGACY_REGION_KEYS.items():
        if old_key not in template_vars:
            continue
        if new_key not in template_vars:
            template_vars[new_key] = template_vars[old_key]
        template_vars.pop(old_key, None)


def _normalize_list_template_vars(template_vars):
    """Normalize ``include`` / ``exclude`` / ``exclude_prefix`` list keys.

    Delegates to ``_parse_string_list`` for the value; drops empty results.
    Mutates *template_vars* in place.
    """
    for list_key in _LIST_KEYS:
        if list_key not in template_vars:
            continue
        list_values = _parse_string_list(template_vars.get(list_key))
        if list_values:
            template_vars[list_key] = list_values
        else:
            template_vars.pop(list_key, None)


def _normalize_template_default_for_compare(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"\s+", "", text)
    return re.sub(r"(?<=[(/,\-|])0+(\d)", r"\1", text)


def _seasonal_child_schedule_defaults():
    defaults = {}
    try:
        groups = helpers.load_quickstart_config("quickstart_collections.json")
    except Exception as exc:
        helpers.ts_log(f"Failed to load quickstart_collections.json for seasonal schedule defaults: {exc}", level="ERROR")
        return defaults

    for group in groups or []:
        if not isinstance(group, dict):
            continue
        for collection in group.get("collections", []) or []:
            if not isinstance(collection, dict) or collection.get("id") != "collection_seasonal":
                continue
            for item in collection.get("template_variables", []) or []:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("key") or "").strip()
                if key.startswith("schedule_") and "default" in item:
                    defaults[key] = _normalize_template_default_for_compare(item.get("default"))
            return defaults
    return defaults


def _drop_default_seasonal_child_schedules(template_vars, raw_id):
    if str(raw_id or "").strip().lower() != "seasonal":
        return
    defaults = _seasonal_child_schedule_defaults()
    if not defaults:
        return
    for key in list(template_vars.keys()):
        if key not in defaults:
            continue
        if _normalize_template_default_for_compare(template_vars.get(key)) == defaults[key]:
            template_vars.pop(key, None)


def _parse_template_lookup_labels(value):
    if isinstance(value, dict):
        return {str(k).strip(): str(v).strip() for k, v in value.items() if str(k).strip() and str(v).strip()}
    if not isinstance(value, str):
        return {}
    raw = value.strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k).strip(): str(v).strip() for k, v in parsed.items() if str(k).strip() and str(v).strip()}


def _split_template_lookup_labels(children):
    template_values = {}
    lookup_labels = {}
    for key, value in children.items():
        key_text = str(key or "")
        if key_text.endswith(_LOOKUP_LABELS_SUFFIX):
            template_key = key_text[: -len(_LOOKUP_LABELS_SUFFIX)]
            labels = _parse_template_lookup_labels(value)
            if template_key and labels:
                lookup_labels[template_key] = labels
            continue
        template_values[key] = value
    return template_values, lookup_labels


def _apply_template_var_normalizers(template_vars, raw_id):
    """Full normalization pass for a collection's template_variables dict.

    Collections with supported ``child_*_overrides`` mappings receive a
    dynamic-child-override expansion pass; every collection receives the
    legacy region key migration, list normalization, and per-value normalization via
    ``_normalize_collection_template_var_value``.
    """
    _expand_franchise_dynamic_child_overrides(template_vars)
    _migrate_legacy_region_keys(template_vars)
    _normalize_list_template_vars(template_vars)
    for template_key in list(template_vars.keys()):
        normalized_value = _normalize_collection_template_var_value(template_key, template_vars.get(template_key))
        if normalized_value is None:
            template_vars.pop(template_key, None)
        else:
            template_vars[template_key] = normalized_value
    _drop_default_seasonal_child_schedules(template_vars, raw_id)


def _is_collectionless_entry(item):
    """True for the special 'collectionless' pseudo-collection.

    Recognizes 'collectionless', 'collection_collectionless', and any
    default ending in 'collectionless' (case-insensitive after strip).
    """
    default_name = str(item.get("default", "")).strip().lower()
    return default_name in {"collectionless", "collection_collectionless"} or default_name.endswith("collectionless")


def _collection_default_order_map(library_type):
    """Return the canonical collection default order from quickstart_collections.json."""
    media_type = {"mov": "movie", "sho": "show"}.get(library_type)
    order_map = {}
    try:
        groups = helpers.load_quickstart_config("quickstart_collections.json")
    except Exception as exc:
        helpers.ts_log(f"Failed to load quickstart_collections.json for collection order: {exc}", level="ERROR")
        return order_map

    for group in groups or []:
        if not isinstance(group, dict):
            continue
        for collection in group.get("collections", []) or []:
            if not isinstance(collection, dict):
                continue
            collection_id = str(collection.get("id") or "").strip()
            if not collection_id:
                continue
            raw_id = collection_id.replace("collection_", "", 1)
            if raw_id in order_map:
                continue
            media_types = collection.get("media_types") or []
            if media_type and media_types and media_type not in media_types:
                continue
            order_map[raw_id] = len(order_map)
    return order_map


def _sort_generated_collection_entries(collection_files, library_type):
    """Sort generated collection defaults canonically while preserving unknown-key order."""
    order_map = _collection_default_order_map(library_type)
    fallback_start = len(order_map)

    def sort_key(indexed_item):
        index, item = indexed_item
        default_name = str(item.get("default", "")).strip()
        return (
            1 if _is_collectionless_entry(item) else 0,
            order_map.get(default_name, fallback_start + index),
            index,
        )

    collection_files[:] = [item for _index, item in sorted(enumerate(collection_files), key=sort_key)]


def _build_child_prefix(library_key, raw_id):
    """Compute the template-child-key prefix for a collection.

    Template collection children do NOT contain '-library-' in their key,
    so we strip that segment when present.
    """
    child_prefix = f"{library_key}-template_collection_{raw_id}_"
    return child_prefix.replace(
        f"-library-template_collection_{raw_id}_",
        f"-template_collection_{raw_id}_",
    )


def build_collection_files(
    library_key,
    library_type,
    collections,
    templates,
    movie_collection_files,
    show_collection_files,
    *,
    debug=False,
):
    """Assemble the ``collection_files`` list for a single library.

    Returns ``(collection_files, has_collectionless)`` where:

    * ``collection_files`` is a list of dicts each shaped like
      ``{"default": <id>, "template_variables": {...}}`` (the
      ``template_variables`` key is omitted when empty).
    * ``has_collectionless`` is True iff at least one selected
      collection is the special 'collectionless' pseudo-collection.

    Selected collections are followed by any raw-block file entries
    parsed out of ``<library_prefix>-collection_files`` from the raw
    collection group; user-authored ordering wins for those.

    Generated defaults are sorted by quickstart_collections.json so
    imported/saved insertion order does not affect final YAML diffs.
    'collectionless' still sinks to the end of generated defaults
    (Kometa expects it last within a library).
    """
    collection_key = helpers.extract_library_name(library_key)
    if debug:
        helpers.ts_log(
            f"collections keys for {collection_key}: " f"{list(collections.get(collection_key, {}).keys())}",
            level="DEBUG",
        )
        helpers.ts_log(
            f"templates keys for {collection_key}: " f"{list(templates.get(collection_key, {}).keys())}",
            level="DEBUG",
        )

    has_collectionless = False
    if not collection_key:
        return [], has_collectionless

    collection_files = []
    for key, selected in collections.get(collection_key, {}).items():
        if "template_collection_" in key:
            if debug:
                helpers.ts_log(
                    f"Skipping invalid collection key (template child): {key}",
                    level="DEBUG",
                )
            continue
        if selected is not True:
            continue

        raw_id = key.split(f"{library_type}-library_{collection_key}-collection_")[-1]
        if isinstance(raw_id, str) and raw_id.strip().lower().endswith("collectionless"):
            has_collectionless = True
        file_entry = {"default": raw_id}

        child_prefix = _build_child_prefix(library_key, raw_id)
        all_children = {k[len(child_prefix) :]: v for k, v in collections[collection_key].items() if k.startswith(child_prefix)}

        if debug:
            prefix = f"{library_key}_collection_{raw_id}_"
            helpers.ts_log(f"Collection: {raw_id}", level="DEBUG")
            helpers.ts_log(f"Prefix:       {prefix}", level="DEBUG")
            helpers.ts_log(f"Child Prefix: {child_prefix}", level="DEBUG")
            helpers.ts_log(
                f"Found {len(all_children)} child template_variables: {all_children}",
                level="DEBUG",
            )

        if all_children:
            template_values, lookup_labels = _split_template_lookup_labels(all_children)
            template_vars = {k: _coerce_bool_like_string(v) for k, v in template_values.items()}
            _apply_template_var_normalizers(template_vars, raw_id)
            if template_vars:
                file_entry["template_variables"] = template_vars
                if lookup_labels:
                    file_entry[_TEMPLATE_VARIABLE_COMMENTS_KEY] = lookup_labels

        collection_files.append(file_entry)

    raw_collection_group = movie_collection_files.get(collection_key, {}) if library_type == "mov" else show_collection_files.get(collection_key, {})
    library_prefix = helpers.strip_library_suffix(library_key)
    raw_collection_entries = _parse_collection_file_block_entries(raw_collection_group.get(f"{library_prefix}-collection_files"))

    if collection_files:
        _sort_generated_collection_entries(collection_files, library_type)

    if raw_collection_entries:
        collection_files.extend(raw_collection_entries)

    collectionless_entries = [entry for entry in collection_files if _is_collectionless_entry(entry)]
    if collectionless_entries:
        collection_files = [entry for entry in collection_files if not _is_collectionless_entry(entry)]
        collection_files.extend(collectionless_entries)

    return collection_files, has_collectionless
