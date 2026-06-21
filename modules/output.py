import io
import copy
import os
import ast
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
import platform
import psutil

import jsonschema
import pyfiglet
from flask import current_app as app, has_request_context, session
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import PlainScalarString
from ruamel.yaml.comments import CommentedSeq

_EMPTY_OUTPUT = object()

from modules import helpers, persistence, database

LIBRARY_RADARR_FIELDS = {
    "url": "string",
    "token": "string",
    "root_folder_path": "string",
    "quality_profile": "string",
    "availability": "string",
    "tag": "string",
    "monitor": "bool",
    "search": "bool",
    "add_missing": "bool",
    "add_existing": "bool",
    "upgrade_existing": "bool",
    "monitor_existing": "bool",
    "ignore_cache": "bool",
    "radarr_path": "string",
    "plex_path": "string",
}

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
LIBRARY_SONARR_FIELDS = {
    "url": "string",
    "token": "string",
    "root_folder_path": "string",
    "quality_profile": "string",
    "language_profile": "string",
    "series_type": "string",
    "season_folder": "bool",
    "monitor": "string",
    "tag": "string",
    "search": "bool",
    "cutoff_search": "bool",
    "add_missing": "bool",
    "add_existing": "bool",
    "upgrade_existing": "bool",
    "monitor_existing": "bool",
    "ignore_cache": "bool",
    "sonarr_path": "string",
    "plex_path": "string",
}


def add_border_to_ascii_art(art):
    lines = art.split("\n")
    lines = lines[:-1]
    width = max(len(line) for line in lines)
    border_line = "#" * (width + 4)
    bordered_art = [border_line] + [f"# {line.ljust(width)} #" for line in lines] + [border_line]
    return "\n".join(bordered_art)


def section_heading(title, font="standard"):
    if font == "none":
        return ""
    elif font == "single line":
        return f"#==================== {title} ====================#"
    else:
        try:
            return add_border_to_ascii_art(pyfiglet.figlet_format(title, font=font))
        except pyfiglet.FontNotFound:
            return f"#==================== {title} ====================#"


def clean_section_data(section_data, config_attribute):
    """
    Cleans out temporary or irrelevant data before integrating it into the final config.yml
    """
    clean_data = {}

    for key, value in section_data.items():
        if key == config_attribute:
            if isinstance(value, dict):
                clean_sub_data = {}
                for sub_key, sub_value in value.items():
                    if not sub_key.startswith("tmp_"):
                        clean_sub_data[sub_key] = copy.deepcopy(sub_value)
                clean_data[key] = clean_sub_data
            else:
                clean_data[key] = copy.deepcopy(value)

    return clean_data


def _normalize_template_value(value):
    if isinstance(value, dict):
        if "value" in value:
            value = value.get("value")
    if isinstance(value, str):
        return value.strip()
    return value


def _rewrite_custom_font_paths(config_data):
    available_fonts = set(helpers.list_available_fonts(include_static=True, include_custom=True))
    if not available_fonts:
        return config_data

    def normalize_font_value(value):
        if isinstance(value, dict):
            raw = value.get("value")
            if isinstance(raw, str):
                updated = normalize_font_value(raw)
                if updated != raw:
                    value["value"] = updated
            return value
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped:
            return value
        base = os.path.basename(stripped)
        if base in available_fonts:
            return f"config/fonts/{base}"
        return value

    def walk(obj):
        if isinstance(obj, dict):
            for key, val in obj.items():
                if isinstance(key, str) and (key == "font" or key.endswith("_font")):
                    obj[key] = normalize_font_value(val)
                else:
                    walk(val)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(config_data)
    return config_data


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
    return None


def _to_number(value):
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if re.fullmatch(r"-?\d+", cleaned):
            return int(cleaned)
        if re.fullmatch(r"-?\d*\.\d+", cleaned):
            return float(cleaned)
    return None


def _format_playlist_files(libraries_list):
    return {
        "playlist_files": [
            {
                "default": "playlist",
                "template_variables": {"libraries": libraries_list},
            }
        ]
    }


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


def _coerce_string_list(values):
    cleaned = []
    seen = set()
    for item in values:
        if item is None:
            continue
        text = str(item).strip()
        if text in {"[", "]"}:
            continue
        if not text or text in seen:
            continue
        cleaned.append(text)
        seen.add(text)
    return cleaned


def _parse_string_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return _coerce_string_list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return _coerce_string_list(parsed)
            try:
                parsed = ast.literal_eval(stripped)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return _coerce_string_list(parsed)
        return _coerce_string_list([stripped])
    return _coerce_string_list([value])


def _parse_comma_string_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return _coerce_string_list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return _coerce_string_list(parsed)
            try:
                parsed = ast.literal_eval(stripped)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return _coerce_string_list(parsed)
        return _coerce_string_list(part.strip() for part in stripped.split(","))
    return _coerce_string_list([value])


def _parse_string_list_mapping(value):
    if value is None:
        return {}
    parsed = value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
        except Exception:
            try:
                parsed = ast.literal_eval(stripped)
            except Exception:
                parsed = None
    if not isinstance(parsed, dict):
        return {}

    normalized = {}
    for raw_key, raw_values in parsed.items():
        key_text = str(raw_key or "").strip()
        if not key_text:
            continue
        values = _parse_comma_string_list(raw_values)
        if values:
            normalized[key_text] = values
    return normalized


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
    if key in {"tmdb_birthday", "tmdb_deathday"}:
        return _parse_tmdb_person_window(value)
    if key == "remove_suffix":
        list_values = _parse_comma_string_list(value)
        return ",".join(list_values) if list_values else None
    if key in {"radarr_tag", "sonarr_tag", "item_radarr_tag", "item_sonarr_tag"} or key.startswith(("radarr_tag_", "sonarr_tag_", "item_radarr_tag_", "item_sonarr_tag_")):
        list_values = _parse_string_list(value)
        return list_values if list_values else None
    return value


def _parse_template_mapping_dict(value):
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}

    raw_text = str(value).strip()
    if not raw_text:
        return {}

    try:
        parsed = json.loads(raw_text)
    except Exception:
        try:
            parsed = ast.literal_eval(raw_text)
        except Exception:
            return {}

    return parsed if isinstance(parsed, dict) else {}


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


def _normalize_settings_section_value(key, value):
    if key in {"ignore_ids", "ignore_imdb_ids"}:
        list_values = _parse_string_list(value)
        return ",".join(list_values) if list_values else None
    return value


def _normalize_asset_directory_entry(value):
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    # Convert YAML-style escaped Windows paths back to plain paths while preserving UNC prefixes.
    if re.match(r"^[A-Za-z]:\\\\", text):
        while "\\\\" in text:
            text = text.replace("\\\\", "\\")
        return text

    if text.startswith("\\\\"):
        prefix = "\\\\"
        remainder = text[2:]
        while "\\\\" in remainder:
            remainder = remainder.replace("\\\\", "\\")
        return prefix + remainder

    return text


def _normalize_asset_directory_values(value):
    normalized = []
    if isinstance(value, str):
        items = value.splitlines()
    elif isinstance(value, list):
        items = value
    else:
        items = []

    for item in items:
        cleaned = _normalize_asset_directory_entry(item)
        if cleaned:
            normalized.append(cleaned)
    return normalized


def _values_match(default, actual):
    default = _normalize_template_value(default)
    actual = _normalize_template_value(actual)

    if default is None:
        return actual is None or actual == ""

    if isinstance(default, str) and default.lower() == "none":
        if actual is None or actual == "" or actual is False:
            return True
        if isinstance(actual, str) and actual.strip().lower() == "none":
            return True

    default_bool = _coerce_bool(default)
    actual_bool = _coerce_bool(actual)
    if default_bool is not None or actual_bool is not None:
        if default_bool is None:
            default_bool = bool(default)
        if actual_bool is None:
            actual_bool = bool(actual)
        return default_bool == actual_bool

    if isinstance(default, (int, float)):
        actual_num = _to_number(actual)
        return actual_num == default if actual_num is not None else False

    if isinstance(actual, (int, float)):
        default_num = _to_number(default)
        return default_num == actual if default_num is not None else False

    return default == actual


def _infer_default_from_options(options):
    if not options:
        return None
    first = options[0]
    if isinstance(first, dict):
        return first.get("value")
    if isinstance(first, (list, tuple)):
        return first[0] if first else None
    return first


def _default_from_var(var_details):
    if not isinstance(var_details, dict):
        return None
    if "default" in var_details:
        return var_details.get("default")

    var_type = var_details.get("type") or var_details.get("input_type")
    if var_type in {"toggle", "boolean_toggle"}:
        return False
    if var_type == "select":
        return _infer_default_from_options(var_details.get("options") or [])
    return None


def _extract_template_defaults(template_vars):
    defaults = {}
    if isinstance(template_vars, dict):
        for name, details in template_vars.items():
            defaults[name] = _default_from_var(details)
    elif isinstance(template_vars, list):
        for item in template_vars:
            if not isinstance(item, dict):
                continue
            name = item.get("key")
            if not name:
                continue
            defaults[name] = _default_from_var(item)
    return defaults


def _build_collection_defaults():
    defaults = {"movie": {}, "show": {}, "all": {}}
    try:
        data = helpers.load_quickstart_config("quickstart_collections.json")
    except Exception as e:
        helpers.ts_log(f"Failed to load quickstart_collections.json: {e}", level="ERROR")
        return defaults

    for group in data or []:
        for collection in group.get("collections", []):
            collection_id = collection.get("id")
            if not collection_id:
                continue
            key = collection_id.replace("collection_", "", 1)
            tv_defaults = _extract_template_defaults(collection.get("template_variables"))
            media_types = collection.get("media_types") or []
            media_types = [mt for mt in media_types if mt in ("movie", "show")]

            if not media_types:
                defaults["all"][key] = tv_defaults
                continue

            for mt in media_types:
                defaults[mt][key] = tv_defaults
            if len(media_types) > 1:
                defaults["all"][key] = tv_defaults
    return defaults


def _extract_offset_defaults(overlay):
    defaults = {}
    per_type = {}

    offsets = overlay.get("default_offsets")
    if isinstance(offsets, dict):
        if "horizontal" in offsets:
            defaults["horizontal_offset"] = offsets["horizontal"]
        if "vertical" in offsets:
            defaults["vertical_offset"] = offsets["vertical"]

    offsets_by_type = overlay.get("default_offsets_by_type")
    if isinstance(offsets_by_type, dict):
        for level, values in offsets_by_type.items():
            if not isinstance(values, dict):
                continue
            level_defaults = {}
            if "horizontal" in values:
                level_defaults["horizontal_offset"] = values["horizontal"]
            if "vertical" in values:
                level_defaults["vertical_offset"] = values["vertical"]
            if level_defaults:
                per_type[level] = level_defaults

    return defaults, per_type


def _build_overlay_defaults():
    defaults = {}
    try:
        data = helpers.load_quickstart_overlay_config()
    except Exception as e:
        helpers.ts_log(f"Failed to load quickstart_overlays.json: {e}", level="ERROR")
        return defaults

    for group in data or []:
        for overlay in group.get("overlays", []):
            overlay_id = overlay.get("id")
            if not overlay_id:
                continue
            base_key = overlay_id.replace("overlay_", "", 1)
            base_defaults = _extract_template_defaults(overlay.get("template_variables"))
            offset_defaults, per_type_offsets = _extract_offset_defaults(overlay)
            for key, value in offset_defaults.items():
                base_defaults.setdefault(key, value)

            entry = defaults.get(base_key)
            if not entry:
                entry = {"defaults": base_defaults, "offsets_by_type": {}, "defaults_by_type": {}}
                defaults[base_key] = entry
            elif not entry.get("defaults"):
                entry["defaults"] = base_defaults

            defaults[overlay_id] = entry

            media_types = overlay.get("media_types") or []
            for media_type in media_types:
                if media_type not in {"movie", "show", "season", "episode"}:
                    continue
                entry["defaults_by_type"][media_type] = base_defaults
                if offset_defaults:
                    entry["offsets_by_type"][media_type] = offset_defaults
            for media_type, offsets in per_type_offsets.items():
                if media_type in {"movie", "show", "season", "episode"}:
                    entry["offsets_by_type"][media_type] = offsets

            if base_key == "content_rating_commonsense":
                defaults["commonsense"] = entry
            if base_key == "languages_subtitles" and "languages" not in defaults:
                defaults["languages"] = entry

    return defaults


def _build_attribute_defaults():
    defaults = {}
    try:
        data = helpers.load_quickstart_config("quickstart_attributes.json")
    except Exception as e:
        helpers.ts_log(f"Failed to load quickstart_attributes.json: {e}", level="ERROR")
        return defaults

    for section in data.get("sections", []):
        if section.get("yml_location") != "template_variables":
            continue
        key = section.get("key") or section.get("prefix")
        if not key:
            continue
        defaults[key] = _default_from_var(section)
    return defaults


def _prune_template_variables(template_vars, defaults):
    if not isinstance(template_vars, dict) or not isinstance(defaults, dict):
        return template_vars
    pruned = {}
    for key, value in template_vars.items():
        if key in defaults and _values_match(defaults.get(key), value):
            continue
        pruned[key] = value
    return pruned


def optimize_template_variables(config_data, library_types=None):
    def _to_offset_number(value, fallback):
        if isinstance(value, bool):
            return fallback
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return fallback
            try:
                return int(stripped)
            except ValueError:
                try:
                    return float(stripped)
                except ValueError:
                    return fallback
        return fallback

    def _is_ratings_entry(default_name):
        return isinstance(default_name, str) and (default_name == "ratings" or default_name.startswith("overlay_ratings"))

    def _ensure_explicit_ratings_offsets(tv, defaults):
        if not isinstance(tv, dict):
            return
        slot_ids = []
        for idx in ("1", "2", "3"):
            rating_key = f"rating{idx}"
            image_key = f"{rating_key}_image"
            if rating_key in tv and image_key in tv:
                slot_ids.append(idx)
        if not slot_ids:
            return
        defaults = defaults or {}

        def _normalize_choice(value, fallback):
            raw = str(value if value is not None else fallback).strip().lower()
            return raw

        def _slot_enabled(slot):
            rating_val = _normalize_choice(tv.get(f"rating{slot}"), "")
            image_val = _normalize_choice(tv.get(f"rating{slot}_image"), "")
            if rating_val in ("", "none") or image_val in ("", "none"):
                return False
            return True

        alignment = _normalize_choice(tv.get("rating_alignment", defaults.get("rating_alignment", "vertical")), "vertical")
        if alignment not in ("horizontal", "vertical"):
            alignment = "vertical"
        h_pos = _normalize_choice(tv.get("horizontal_position", defaults.get("horizontal_position", "left")), "left")
        if h_pos not in ("left", "center", "right"):
            h_pos = "left"
        v_pos = _normalize_choice(tv.get("vertical_position", defaults.get("vertical_position", "center")), "center")
        if v_pos not in ("top", "center", "bottom"):
            v_pos = "center"

        if isinstance(defaults, dict):
            defaults["back_width"] = 270 if alignment == "horizontal" else 160
            defaults["back_height"] = 80 if alignment == "horizontal" else 160
            defaults["addon_position"] = "left" if alignment == "horizontal" else "top"
            defaults["horizontal_offset"] = 0 if h_pos == "center" else 15
            defaults["vertical_offset"] = 0 if v_pos == "center" else 15

        rating_constants = {
            "standard": 30,
            "center": 0,
            "v2": 235,
            "v3": 440,
            "cv2": 105,
            "cv3": 205,
            "h2": 345,
            "h3": 660,
            "ch2": 160,
            "ch3": 335,
        }

        none1 = not _slot_enabled("1")
        none2 = not _slot_enabled("2")
        none3 = not _slot_enabled("3")

        def r1h():
            if alignment == "vertical" and h_pos == "center":
                return rating_constants["center"]
            if alignment == "horizontal" and h_pos == "center" and none2 and none3:
                return rating_constants["center"]
            if alignment == "horizontal" and h_pos == "center" and none2:
                return -rating_constants["ch2"]
            if alignment == "horizontal" and h_pos == "center" and none3:
                return -rating_constants["ch2"]
            if alignment == "horizontal" and h_pos == "center":
                return -rating_constants["ch3"]
            if alignment == "horizontal" and h_pos == "right" and none2 and none3:
                return rating_constants["standard"]
            if alignment == "horizontal" and h_pos == "right" and none2:
                return rating_constants["h2"]
            if alignment == "horizontal" and h_pos == "right" and none3:
                return rating_constants["h2"]
            if alignment == "horizontal" and h_pos == "right":
                return rating_constants["h3"]
            return rating_constants["standard"]

        def r1v():
            if alignment == "horizontal" and v_pos == "center":
                return rating_constants["center"]
            if alignment == "vertical" and v_pos == "center" and none2 and none3:
                return rating_constants["center"]
            if alignment == "vertical" and v_pos == "center" and none2:
                return -rating_constants["cv2"]
            if alignment == "vertical" and v_pos == "center" and none3:
                return -rating_constants["cv2"]
            if alignment == "vertical" and v_pos == "center":
                return -rating_constants["cv3"]
            if alignment == "vertical" and v_pos == "bottom" and none2 and none3:
                return rating_constants["standard"]
            if alignment == "vertical" and v_pos == "bottom" and none2:
                return rating_constants["v2"]
            if alignment == "vertical" and v_pos == "bottom" and none3:
                return rating_constants["v2"]
            if alignment == "vertical" and v_pos == "bottom":
                return rating_constants["v3"]
            return rating_constants["standard"]

        def r2h():
            if alignment == "vertical" and h_pos == "center":
                return rating_constants["center"]
            if alignment == "horizontal" and h_pos == "center" and none1 and none3:
                return rating_constants["center"]
            if alignment == "horizontal" and h_pos == "center" and none1:
                return -rating_constants["ch2"]
            if alignment == "horizontal" and h_pos == "center" and none3:
                return rating_constants["ch2"]
            if alignment == "horizontal" and h_pos == "center":
                return rating_constants["center"]
            if alignment == "horizontal" and h_pos == "right" and none1 and none3:
                return rating_constants["standard"]
            if alignment == "horizontal" and h_pos == "right" and none3:
                return rating_constants["standard"]
            if alignment == "horizontal" and h_pos == "right":
                return rating_constants["h2"]
            if alignment == "horizontal" and h_pos == "left" and none1:
                return rating_constants["standard"]
            if alignment == "horizontal" and h_pos == "left":
                return rating_constants["h2"]
            return rating_constants["standard"]

        def r2v():
            if alignment == "horizontal" and v_pos == "center":
                return rating_constants["center"]
            if alignment == "vertical" and v_pos == "center" and none1 and none3:
                return rating_constants["center"]
            if alignment == "vertical" and v_pos == "center" and none1:
                return -rating_constants["cv2"]
            if alignment == "vertical" and v_pos == "center" and none3:
                return rating_constants["cv2"]
            if alignment == "vertical" and v_pos == "center":
                return rating_constants["center"]
            if alignment == "vertical" and v_pos == "bottom" and none1 and none3:
                return rating_constants["standard"]
            if alignment == "vertical" and v_pos == "bottom" and none1:
                return rating_constants["v2"]
            if alignment == "vertical" and v_pos == "bottom" and none3:
                return rating_constants["standard"]
            if alignment == "vertical" and v_pos == "bottom":
                return rating_constants["v2"]
            if alignment == "vertical" and v_pos == "top" and none1:
                return rating_constants["standard"]
            if alignment == "vertical" and v_pos == "top":
                return rating_constants["v2"]
            return rating_constants["standard"]

        def r3h():
            if alignment == "vertical" and h_pos == "center":
                return rating_constants["center"]
            if alignment == "horizontal" and h_pos == "center" and none1 and none2:
                return rating_constants["center"]
            if alignment == "horizontal" and h_pos == "center" and none1:
                return rating_constants["ch2"]
            if alignment == "horizontal" and h_pos == "center" and none2:
                return rating_constants["ch2"]
            if alignment == "horizontal" and h_pos == "center":
                return rating_constants["ch3"]
            if alignment == "horizontal" and h_pos == "left" and none1 and none2:
                return rating_constants["standard"]
            if alignment == "horizontal" and h_pos == "left" and none1:
                return rating_constants["h2"]
            if alignment == "horizontal" and h_pos == "left" and none2:
                return rating_constants["h2"]
            if alignment == "horizontal" and h_pos == "left":
                return rating_constants["h3"]
            return rating_constants["standard"]

        def r3v():
            if alignment == "horizontal" and v_pos == "center":
                return rating_constants["center"]
            if alignment == "vertical" and v_pos == "center" and none1 and none2:
                return rating_constants["center"]
            if alignment == "vertical" and v_pos == "center" and none1:
                return rating_constants["cv2"]
            if alignment == "vertical" and v_pos == "center" and none2:
                return rating_constants["cv2"]
            if alignment == "vertical" and v_pos == "center":
                return rating_constants["cv3"]
            if alignment == "vertical" and v_pos == "top" and none1 and none2:
                return rating_constants["standard"]
            if alignment == "vertical" and v_pos == "top" and none1:
                return rating_constants["v2"]
            if alignment == "vertical" and v_pos == "top" and none2:
                return rating_constants["v2"]
            if alignment == "vertical" and v_pos == "top":
                return rating_constants["v3"]
            return rating_constants["standard"]

        computed = {
            "1": {"h": r1h(), "v": r1v()},
            "2": {"h": r2h(), "v": r2v()},
            "3": {"h": r3h(), "v": r3v()},
        }

        for idx in slot_ids:
            h_key = f"rating{idx}_horizontal_offset"
            v_key = f"rating{idx}_vertical_offset"
            if isinstance(defaults, dict):
                defaults[h_key] = int(round(computed[idx]["h"]))
                defaults[v_key] = int(round(computed[idx]["v"]))
            if h_key not in tv:
                tv[h_key] = int(round(computed[idx]["h"]))
            if v_key not in tv:
                tv[v_key] = int(round(computed[idx]["v"]))

    def _reorder_ratings_template_vars(entry):
        if not isinstance(entry, dict):
            return
        default_name = entry.get("default", "")
        if not _is_ratings_entry(default_name):
            return
        tv = entry.get("template_variables")
        if not isinstance(tv, dict) or not tv:
            return
        preferred_order = [
            "builder_level",
            "rating1",
            "rating1_image",
            "rating1_font",
            "rating1_font_size",
            "rating1_font_color",
            "rating1_stroke_width",
            "rating1_stroke_color",
            "rating1_horizontal_offset",
            "rating1_vertical_offset",
            "rating2",
            "rating2_image",
            "rating2_font",
            "rating2_font_size",
            "rating2_font_color",
            "rating2_stroke_width",
            "rating2_stroke_color",
            "rating2_horizontal_offset",
            "rating2_vertical_offset",
            "rating3",
            "rating3_image",
            "rating3_font",
            "rating3_font_size",
            "rating3_font_color",
            "rating3_stroke_width",
            "rating3_stroke_color",
            "rating3_horizontal_offset",
            "rating3_vertical_offset",
            "horizontal_position",
            "vertical_position",
            "horizontal_offset",
            "vertical_offset",
            "back_align",
            "back_color",
            "back_height",
            "back_width",
            "back_line_color",
            "back_line_width",
            "back_padding",
            "back_radius",
            "use_subtitles",
        ]
        ordered = {}
        for key in preferred_order:
            if key in tv:
                ordered[key] = tv[key]
        for key in tv:
            if key not in ordered:
                ordered[key] = tv[key]
        entry["template_variables"] = ordered

    libraries_section = config_data.get("libraries", {})
    if isinstance(libraries_section, dict) and isinstance(libraries_section.get("libraries"), dict):
        libraries = libraries_section.get("libraries")
    elif isinstance(libraries_section, dict):
        libraries = libraries_section
    else:
        libraries = None
    if not isinstance(libraries, dict):
        return config_data

    collection_defaults = _build_collection_defaults()
    overlay_defaults = _build_overlay_defaults()
    attribute_defaults = _build_attribute_defaults()

    for library_name, library_data in libraries.items():
        if not isinstance(library_data, dict):
            continue

        library_type = None
        if isinstance(library_types, dict):
            library_type = library_types.get(library_name)

        tv = library_data.get("template_variables")
        if isinstance(tv, dict):
            pruned = _prune_template_variables(tv, attribute_defaults)
            if pruned:
                library_data["template_variables"] = pruned
            else:
                library_data.pop("template_variables", None)

        collection_files = library_data.get("collection_files")
        if isinstance(collection_files, list):
            for entry in collection_files:
                if not isinstance(entry, dict):
                    continue
                tv = entry.get("template_variables")
                if not isinstance(tv, dict):
                    continue
                defaults = None
                if isinstance(collection_defaults, dict):
                    if library_type in ("movie", "show"):
                        defaults = collection_defaults.get(library_type, {}).get(entry.get("default"))
                    if defaults is None:
                        defaults = collection_defaults.get("all", {}).get(entry.get("default"))
                if not defaults:
                    continue
                pruned = _prune_template_variables(tv, defaults)
                if entry.get("default") == "year" and "data_ending" in tv:
                    pruned["data_ending"] = tv.get("data_ending")
                if pruned:
                    entry["template_variables"] = pruned
                else:
                    entry.pop("template_variables", None)

        overlay_files = library_data.get("overlay_files")
        if isinstance(overlay_files, list):
            for entry in overlay_files:
                if not isinstance(entry, dict):
                    continue
                tv = entry.get("template_variables")
                if not isinstance(tv, dict):
                    continue
                defaults_entry = overlay_defaults.get(entry.get("default"))
                if not defaults_entry:
                    continue
                defaults = dict(defaults_entry.get("defaults", {}))

                overlay_level = None
                if isinstance(tv.get("builder_level"), str) and tv.get("builder_level"):
                    overlay_level = tv.get("builder_level")
                elif library_type:
                    overlay_level = "movie" if library_type == "movie" else "show"

                if overlay_level:
                    type_defaults = defaults_entry.get("defaults_by_type", {}).get(overlay_level)
                    if type_defaults:
                        defaults = dict(type_defaults)
                    offsets = defaults_entry.get("offsets_by_type", {}).get(overlay_level)
                    if offsets:
                        defaults.update(offsets)

                if _is_ratings_entry(entry.get("default")):
                    _ensure_explicit_ratings_offsets(tv, defaults)

                pruned = _prune_template_variables(tv, defaults)
                always_keep = set()
                if _is_ratings_entry(entry.get("default")):
                    always_keep.update(
                        {
                            "builder_level",
                            "rating1",
                            "rating1_image",
                            "rating2",
                            "rating2_image",
                            "rating3",
                            "rating3_image",
                            "horizontal_position",
                            "vertical_position",
                        }
                    )
                if "builder_level" in tv:
                    always_keep.add("builder_level")
                if always_keep:
                    for key in always_keep:
                        if key in tv:
                            pruned[key] = tv[key]
                if pruned:
                    entry["template_variables"] = pruned
                    _reorder_ratings_template_vars(entry)
                else:
                    entry.pop("template_variables", None)

    return config_data


def _collapse_collection_data_template_vars(config_data):
    if not isinstance(config_data, dict):
        return config_data
    libraries_section = config_data.get("libraries", {})
    libraries = None
    if isinstance(libraries_section, dict):
        nested = libraries_section.get("libraries")
        if isinstance(nested, dict):
            libraries = nested
        else:
            libraries = libraries_section
    if not isinstance(libraries, dict):
        return config_data
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
            if not isinstance(template_vars, dict):
                continue
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


def _normalize_legacy_collection_template_vars(config_data):
    if not isinstance(config_data, dict):
        return config_data
    libraries_section = config_data.get("libraries", {})
    libraries = None
    if isinstance(libraries_section, dict):
        nested = libraries_section.get("libraries")
        if isinstance(nested, dict):
            libraries = nested
        else:
            libraries = libraries_section
    if not isinstance(libraries, dict):
        return config_data

    letterboxd_key_map = {
        "use_top_250": "use_top_500",
        "radarr_add_missing_top_250": "radarr_add_missing_top_500",
        "visible_home_top_250": "visible_home_top_500",
        "visible_library_top_250": "visible_library_top_500",
        "visible_shared_top_250": "visible_shared_top_500",
        "limit_top_250": "limit_top_500",
    }

    for library_data in libraries.values():
        if not isinstance(library_data, dict):
            continue
        collection_files = library_data.get("collection_files")
        if not isinstance(collection_files, list):
            continue
        for entry in collection_files:
            if not isinstance(entry, dict) or entry.get("default") != "letterboxd":
                continue
            template_vars = entry.get("template_variables")
            if not isinstance(template_vars, dict):
                continue
            for old_key, new_key in letterboxd_key_map.items():
                if old_key not in template_vars or new_key in template_vars:
                    continue
                template_vars[new_key] = template_vars.pop(old_key)
    return config_data


def _parse_metadata_file_entries(raw_value):
    if isinstance(raw_value, list):
        entries = raw_value
    elif isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return []
        try:
            entries = json.loads(text)
        except Exception:
            return []
    else:
        return []

    if not isinstance(entries, list):
        return []

    normalized = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip().lower()
        location = str(entry.get("location") or "").strip()
        if entry_type not in {"file", "folder", "url", "git", "repo"} or not location:
            continue
        normalized.append({entry_type: location})

    normalized.sort(key=lambda item: (next(iter(item.keys())), next(iter(item.values())).casefold()))
    return normalized


def _parse_collection_file_block_entries(raw_value):
    if isinstance(raw_value, list):
        entries = raw_value
    elif isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return []
        try:
            entries = json.loads(text)
        except Exception:
            return []
    else:
        return []

    if not isinstance(entries, list):
        return []

    normalized = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip().lower()
        location = str(entry.get("location") or "").strip()
        if entry_type not in {"file", "folder", "url", "git", "repo"} or not location:
            continue
        normalized.append({entry_type: location})

    normalized.sort(key=lambda item: (next(iter(item.keys())), next(iter(item.values())).casefold()))
    return normalized


def _parse_overlay_file_block_entries(raw_value):
    if isinstance(raw_value, list):
        entries = raw_value
    elif isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return []
        try:
            entries = json.loads(text)
        except Exception:
            return []
    else:
        return []

    if not isinstance(entries, list):
        return []

    normalized = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip().lower()
        location = str(entry.get("location") or "").strip()
        if entry_type not in {"file", "folder", "url", "git", "repo"} or not location:
            continue
        normalized.append({entry_type: location})

    normalized.sort(key=lambda item: (next(iter(item.keys())), next(iter(item.values())).casefold()))
    return normalized


def build_libraries_section(
    movie_libraries,
    show_libraries,
    movie_collections,
    show_collections,
    movie_collection_files,
    show_collection_files,
    movie_overlays,
    show_overlays,
    movie_attributes,
    show_attributes,
    movie_metadata_files,
    show_metadata_files,
    movie_templates,
    show_templates,
    movie_top_level,
    show_top_level,
):
    libraries_section = {}

    def sorted_library_items(libraries):
        """Return deterministic library ordering by display name, then key."""
        if not isinstance(libraries, dict):
            return []
        return sorted(
            libraries.items(),
            key=lambda item: (str(item[1]).casefold(), str(item[0]).casefold()),
        )

    def add_entry(
        library_key,
        library_name,
        library_type,
        collections,
        overlays,
        attributes,
        templates,
        top_level,
    ):
        """Processes a single library and adds valid data to the output."""
        entry = {}

        lib_id = helpers.extract_library_name(library_key)

        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Processing Library: {library_key} -> {library_name}", level="DEBUG")

        # Process Library Settings and Operations Attributes
        library_settings_fields = [
            "asset_directory",
            "prioritize_assets",
        ]
        operations_fields = [
            "assets_for_all",
            "assets_for_all_collections",
            "mass_imdb_parental_labels",
            "mass_collection_mode",
            "update_blank_track_titles",
            "remove_title_parentheses",
            "split_duplicates",
            "radarr_add_all",
            "sonarr_add_all",
        ]
        library_settings = {}
        service_overrides = {}
        operations = {}
        attr_group = attributes.get(lib_id, {})
        # Begin: Mass Genre Update Section
        mass_genre_update_keys = [
            "tmdb",
            "tvdb",
            "imdb",
            "omdb",
            "anidb",
            "anidb_3_0",
            "anidb_2_5",
            "anidb_2_0",
            "anidb_1_5",
            "anidb_1_0",
            "anidb_0_5",
            "mal",
            "lock",
            "unlock",
            "remove",
            "reset",
        ]
        mass_genre_update = []

        # Grab the full reordered list from hidden input
        custom_key = f"{library_type}-library_{lib_id}-attribute_mass_genre_update_order"
        order_value = attr_group.get(custom_key)

        if order_value:
            try:
                parsed = json.loads(order_value)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, str) and item.startswith("[") and item.endswith("]"):
                            # Probably malformed nested list — skip
                            continue
                        elif isinstance(item, str):
                            mass_genre_update.append(item)
                        elif isinstance(item, list):  # rare case
                            mass_genre_update.extend(item)
            except Exception as e:
                helpers.ts_log(f"Skipping invalid JSON in custom genre: {order_value} — {e}", level="ERROR")

        # Also include custom genre strings (if any) from the other hidden input
        custom_strings_key = f"{library_type}-library_{lib_id}-attribute_mass_genre_update_custom"
        custom_strings_value = attr_group.get(custom_strings_key)

        if custom_strings_value:
            try:
                parsed_custom = json.loads(custom_strings_value)
                if isinstance(parsed_custom, list) and parsed_custom:
                    # Wrap it in a CommentedSeq to enforce flow style
                    custom_flow_list = CommentedSeq(parsed_custom)
                    custom_flow_list.fa.set_flow_style()  # Force [ "Thriller", "Action" ] formatting
                    mass_genre_update.append(custom_flow_list)
            except Exception as e:
                helpers.ts_log(f"Skipping invalid JSON in custom genre strings: {custom_strings_value} — {e}", level="ERROR")

        if mass_genre_update:
            operations["mass_genre_update"] = mass_genre_update

        # Begin: Mass Content Rating Update Section
        mass_content_rating_update = []

        # Get the ordered source list (sortable)
        rating_custom_order_key = f"{library_type}-library_{lib_id}-attribute_mass_content_rating_update_order"
        rating_custom_order_value = attr_group.get(rating_custom_order_key)

        if rating_custom_order_value:
            try:
                parsed = json.loads(rating_custom_order_value)
                if isinstance(parsed, list):
                    mass_content_rating_update.extend(parsed)
            except Exception as e:
                helpers.ts_log(f"Skipping invalid JSON in content rating sources: {rating_custom_order_value} — {e}", level="ERROR")

        rating_custom_list_key = f"{library_type}-library_{lib_id}-attribute_mass_content_rating_update_custom"
        rating_custom_list_value = attr_group.get(rating_custom_list_key)
        if rating_custom_list_value:
            try:
                parsed_custom = json.loads(rating_custom_list_value)
                if isinstance(parsed_custom, list):
                    for item in parsed_custom:
                        if isinstance(item, (int, float)):
                            mass_content_rating_update.append(item)
                        elif isinstance(item, str) and item.strip():
                            mass_content_rating_update.append(item.strip())
            except Exception as e:
                helpers.ts_log(f"Skipping invalid JSON in content rating custom list: {rating_custom_list_value} — {e}", level="ERROR")

        # Get the optional custom string (e.g., "NR")
        rating_custom_string_key = f"{library_type}-library_{lib_id}-attribute_mass_content_rating_update_custom_string"
        rating_custom_string_value = None
        if attr_group and rating_custom_string_key in attr_group:
            raw_value = attr_group.get(rating_custom_string_key)
            if raw_value:
                rating_custom_string_value = raw_value.strip()

        if rating_custom_string_value:
            mass_content_rating_update.append(rating_custom_string_value)

        # Only add to operations if we have any items
        if mass_content_rating_update:
            mcru_list = CommentedSeq(mass_content_rating_update)
            mcru_list.fa.set_block_style()  # ensures YAML list style
            operations["mass_content_rating_update"] = mcru_list

        # Begin: Mass Original Title Update Section
        mass_original_title_update = []

        # Handle the toggle order list
        original_title_order_key = f"{library_type}-library_{lib_id}-attribute_mass_original_title_update_order"
        original_title_order_value = attr_group.get(original_title_order_key)

        if original_title_order_value:
            try:
                parsed = json.loads(original_title_order_value)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, str):
                            mass_original_title_update.append(item)
                        elif isinstance(item, list):  # nested list — flatten it
                            mass_original_title_update.extend(item)
            except Exception as e:
                helpers.ts_log(f"Skipping invalid JSON in original title order: {original_title_order_value} — {e}", level="DEBUG")

        original_title_custom_list_key = f"{library_type}-library_{lib_id}-attribute_mass_original_title_update_custom"
        original_title_custom_list_value = attr_group.get(original_title_custom_list_key)
        if original_title_custom_list_value:
            try:
                parsed_custom = json.loads(original_title_custom_list_value)
                if isinstance(parsed_custom, list):
                    for item in parsed_custom:
                        if isinstance(item, str) and item.strip():
                            mass_original_title_update.append(item.strip())
            except Exception as e:
                helpers.ts_log(
                    f"Skipping invalid JSON in original title custom list: {original_title_custom_list_value} — {e}",
                    level="ERROR",
                )

        # Handle the optional custom string (e.g., "Unknown")
        original_title_custom_key = f"{library_type}-library_{lib_id}-attribute_mass_original_title_update_custom_string"
        original_title_custom_value = attr_group.get(original_title_custom_key)

        if original_title_custom_value:
            try:
                stripped = original_title_custom_value.strip()
                if stripped:
                    mass_original_title_update.append(stripped)
            except Exception as e:
                helpers.ts_log(f"Skipping invalid original title custom string: {original_title_custom_value} — {e}", level="ERROR")

        if mass_original_title_update:
            motu_list = CommentedSeq(mass_original_title_update)
            motu_list.fa.set_block_style()
            operations["mass_original_title_update"] = motu_list

        for field in library_settings_fields:
            attr_key = f"{library_type}-library_{lib_id}-attribute_{field}"
            value = attr_group.get(attr_key, None)
            if value in [None, ""] and field == "asset_directory":
                legacy_attr_key = f"{library_type}-library_{lib_id}-{field}"
                value = attr_group.get(legacy_attr_key, None)

            if field == "asset_directory":
                normalized = _normalize_asset_directory_values(value)

                if normalized:
                    asset_dirs = CommentedSeq(normalized)
                    asset_dirs.fa.set_block_style()
                    library_settings[field] = asset_dirs
                continue

            if field == "prioritize_assets":
                bool_value = _coerce_bool(value)
                if bool_value is not None:
                    library_settings[field] = bool_value
                continue

            if value not in [None, "", False]:
                library_settings[field] = value

        for field in operations_fields:
            attr_key = f"{library_type}-library_{lib_id}-attribute_{field}"
            value = attr_group.get(attr_key, None)
            if value not in [None, "", False]:
                operations[field] = value

        service_field_map = LIBRARY_RADARR_FIELDS if library_type == "mov" else LIBRARY_SONARR_FIELDS
        service_name = "radarr" if library_type == "mov" else "sonarr"
        for field, field_type in service_field_map.items():
            attr_key = f"{library_type}-library_{lib_id}-attribute_{service_name}_{field}"
            value = attr_group.get(attr_key, None)
            if field_type == "bool":
                bool_value = _coerce_bool(value)
                if bool_value is not None:
                    service_overrides[field] = bool_value
                continue
            if value not in [None, "", False]:
                service_overrides[field] = value

        # Handle nested delete_collections block
        delete_collections = {}
        configured_key = f"{library_type}-library_{lib_id}-attribute_delete_collections_configured"
        managed_key = f"{library_type}-library_{lib_id}-attribute_delete_collections_managed"
        ignore_key = f"{library_type}-library_{lib_id}-attribute_delete_collections_ignore_empty_smart_collections"
        less_key = f"{library_type}-library_{lib_id}-attribute_delete_collections_less"

        configured_value = _coerce_bool(attr_group.get(configured_key, None))
        managed_value = _coerce_bool(attr_group.get(managed_key, None))
        ignore_value = _coerce_bool(attr_group.get(ignore_key, None))
        less_value = None
        raw_less = attr_group.get(less_key, None)
        if raw_less not in [None, "", "None", "none"]:
            try:
                less_value = int(raw_less)
            except Exception:
                helpers.ts_log(f"Skipping invalid delete_collections_less value: {raw_less}", level="DEBUG")

        delete_collections_enabled = any(
            [
                configured_value is True,
                managed_value is True,
                ignore_value is True,
                less_value is not None,
            ]
        )

        if delete_collections_enabled:
            delete_collections["configured"] = configured_value if configured_value is not None else False
            delete_collections["managed"] = managed_value if managed_value is not None else False
            if less_value is not None:
                delete_collections["less"] = less_value
            if ignore_value is True:
                delete_collections["ignore_empty_smart_collections"] = True

        if delete_collections:
            operations["delete_collections"] = delete_collections

        if library_settings:
            entry["settings"] = library_settings

        if service_overrides:
            entry[service_name] = service_overrides

        if operations:
            entry["operations"] = operations

        # Process Collections
        has_collectionless = False
        collection_key = helpers.extract_library_name(library_key)
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"collections keys for {collection_key}: {list(collections.get(collection_key, {}).keys())}", level="DEBUG")
            helpers.ts_log(f"templates keys for {collection_key}: {list(templates.get(collection_key, {}).keys())}", level="DEBUG")

        if collection_key:
            collection_files = []

            for key, selected in collections.get(collection_key, {}).items():
                if "template_collection_" in key:
                    if app.config["QS_DEBUG"]:
                        helpers.ts_log(f"Skipping invalid collection key (template child): {key}", level="DEBUG")
                    continue

                if selected is not True:
                    continue

                raw_id = key.split(f"{library_type}-library_{collection_key}-collection_")[-1]
                if isinstance(raw_id, str) and raw_id.strip().lower().endswith("collectionless"):
                    has_collectionless = True
                file_entry = {"default": raw_id}

                # IMPORTANT: Template collection children do NOT contain '-library-' in key
                prefix = f"{library_key}_collection_{raw_id}_"

                # Build flattened version of all template keys across libraries
                all_template_entries = {}
                for section in templates.values():
                    all_template_entries.update(section)

                # Collect matching keys from prefix styles
                # Find matching template children manually instead of prefix-matching
                child_prefix = f"{library_key}-template_collection_{raw_id}_".replace(f"-library-template_collection_{raw_id}_", f"-template_collection_{raw_id}_")
                all_children = {k[len(child_prefix) :]: v for k, v in collections[collection_key].items() if k.startswith(child_prefix)}

                if app.config["QS_DEBUG"]:
                    helpers.ts_log(f"Collection: {raw_id}", level="DEBUG")
                    helpers.ts_log(f"Prefix:       {prefix}", level="DEBUG")
                    helpers.ts_log(f"Child Prefix: {child_prefix}", level="DEBUG")
                    helpers.ts_log(f"Found {len(all_children)} child template_variables: {all_children}", level="DEBUG")

                if all_children:
                    template_vars = {
                        k: (True if isinstance(v, (bool, str)) and str(v).lower() == "true" else False if isinstance(v, (bool, str)) and str(v).lower() == "false" else v)
                        for k, v in all_children.items()
                    }
                    if raw_id == "franchise":
                        _expand_franchise_dynamic_child_overrides(template_vars)
                    # Normalize legacy Region key spelling so final YAML always uses
                    # the current Kometa key with a hyphen.
                    legacy_region_keys = {
                        "use_South Eastern Asia": "use_South-Eastern Asia",
                        "radarr_add_missing_South Eastern Asia": "radarr_add_missing_South-Eastern Asia",
                        "sonarr_add_missing_South Eastern Asia": "sonarr_add_missing_South-Eastern Asia",
                    }
                    for old_key, new_key in legacy_region_keys.items():
                        if old_key not in template_vars:
                            continue
                        # If both exist, prefer the new key's explicit value.
                        if new_key not in template_vars:
                            template_vars[new_key] = template_vars[old_key]
                        template_vars.pop(old_key, None)
                    for list_key in ("include", "exclude", "exclude_prefix"):
                        if list_key not in template_vars:
                            continue
                        list_values = _parse_string_list(template_vars.get(list_key))
                        if list_values:
                            template_vars[list_key] = list_values
                        else:
                            template_vars.pop(list_key, None)
                    for template_key in list(template_vars.keys()):
                        normalized_value = _normalize_collection_template_var_value(template_key, template_vars.get(template_key))
                        if normalized_value is None:
                            template_vars.pop(template_key, None)
                        else:
                            template_vars[template_key] = normalized_value
                    if template_vars:
                        file_entry["template_variables"] = template_vars

                collection_files.append(file_entry)

            raw_collection_group = movie_collection_files.get(collection_key, {}) if library_type == "mov" else show_collection_files.get(collection_key, {})
            library_prefix = library_key[: -len("-library")] if isinstance(library_key, str) and library_key.endswith("-library") else library_key
            raw_collection_entries = _parse_collection_file_block_entries(raw_collection_group.get(f"{library_prefix}-collection_files"))

            if collection_files:

                def is_collectionless(item):
                    default_name = str(item.get("default", "")).strip().lower()
                    return default_name in {"collectionless", "collection_collectionless"} or default_name.endswith("collectionless")

                collection_files.sort(key=lambda item: (is_collectionless(item)))

            if raw_collection_entries:
                collection_files.extend(raw_collection_entries)

            if collection_files:
                entry["collection_files"] = collection_files

            # Process Overlays
            # Process Overlays
            overlay_key = helpers.extract_library_name(library_key)
            overlay_entries = []
            overlay_name_order = []

            def prune_rating_template_vars(overlay_entry):
                """
                Drop rating template variables explicitly set to "none" so they don't emit in YAML.
                Applies to overlay_ratings and overlay_ratings_episode.
                """
                if not isinstance(overlay_entry, dict):
                    return
                default_name = overlay_entry.get("default", "")
                # Handle both default strings and overlay IDs (e.g., "overlay_ratings" or "overlay_ratings_episode")
                if isinstance(default_name, str):
                    is_ratings = default_name.startswith("overlay_ratings") or default_name == "ratings" or default_name == "overlay_ratings_episode"
                else:
                    is_ratings = False
                if not is_ratings:
                    return
                tv = overlay_entry.get("template_variables")
                if not isinstance(tv, dict):
                    return
                cleaned = {}
                for k, v in tv.items():
                    if v is None or v is False:
                        continue
                    # Handle dict values from select options like {"value": "", "label": "None"}
                    if isinstance(v, dict):
                        raw_val = v.get("value", "")
                        if not raw_val or (isinstance(raw_val, str) and raw_val.strip().lower() == "none"):
                            continue
                        cleaned[k] = raw_val
                        continue
                    if isinstance(v, str):
                        stripped = v.strip()
                        if stripped == "" or stripped.lower() == "none":
                            continue
                    cleaned[k] = v

                def _is_empty(val):
                    if val is None or val is False:
                        return True
                    if isinstance(val, str):
                        return val.strip() == "" or val.strip().lower() == "none"
                    return False

                # Enforce ratingN <-> ratingN_image dependency; if either side is empty, drop the slot entirely,
                # including any stale slot-specific style or offset fields left behind from a previous count.
                for idx in ["1", "2", "3"]:
                    r_key = f"rating{idx}"
                    i_key = f"{r_key}_image"
                    r_val = cleaned.get(r_key)
                    i_val = cleaned.get(i_key)
                    if r_key in cleaned or i_key in cleaned:
                        if _is_empty(r_val) or _is_empty(i_val):
                            for key in [k for k in list(cleaned.keys()) if k == r_key or k.startswith(f"{r_key}_")]:
                                cleaned.pop(key, None)
                            continue

                def _offset_number(value, fallback):
                    if isinstance(value, bool):
                        return fallback
                    if isinstance(value, (int, float)):
                        return value
                    if isinstance(value, str):
                        stripped = value.strip()
                        if not stripped:
                            return fallback
                        try:
                            return int(stripped)
                        except ValueError:
                            try:
                                return float(stripped)
                            except ValueError:
                                return fallback
                    return fallback

                explicit_slot_offset_keys = {
                    "rating1_horizontal_offset",
                    "rating1_vertical_offset",
                    "rating2_horizontal_offset",
                    "rating2_vertical_offset",
                    "rating3_horizontal_offset",
                    "rating3_vertical_offset",
                }
                had_explicit_slot_offsets = any(key in cleaned for key in explicit_slot_offset_keys)

                # Compact the configured rating slots so the emitted YAML always matches the
                # contiguous stack shown on the Quickstart canvas, even after reducing the
                # rating count or clearing a middle slot.
                slot_payloads = []
                for idx in ["1", "2", "3"]:
                    rating_key = f"rating{idx}"
                    image_key = f"{rating_key}_image"
                    if rating_key not in cleaned or image_key not in cleaned:
                        continue
                    slot_payload = {}
                    for key in [k for k in list(cleaned.keys()) if k == rating_key or k.startswith(f"{rating_key}_")]:
                        suffix = "" if key == rating_key else key[len(rating_key) :]
                        slot_payload[suffix] = cleaned.pop(key)
                    if slot_payload:
                        slot_payloads.append(slot_payload)

                back_height = _offset_number(cleaned.get("back_height"), 160)
                back_padding = max(0, _offset_number(cleaned.get("back_padding"), 15))
                alignment_raw = str(cleaned.get("rating_alignment", "vertical")).strip().lower()
                alignment = "horizontal" if alignment_raw == "horizontal" else "vertical"
                h_pos_raw = str(cleaned.get("horizontal_position", "left")).strip().lower()
                h_pos = h_pos_raw if h_pos_raw in {"left", "center", "right"} else "left"
                v_pos_raw = str(cleaned.get("vertical_position", "center")).strip().lower()
                v_pos = v_pos_raw if v_pos_raw in {"top", "center", "bottom"} else "center"
                vertical_step = back_height + (back_padding * 3)
                center_index = (len(slot_payloads) - 1) / 2 if slot_payloads else 0
                shared_horizontal_base = _offset_number(cleaned.get("horizontal_offset"), 15)
                shared_vertical_base = _offset_number(cleaned.get("vertical_offset"), 0)
                for axis in ["horizontal", "vertical"]:
                    shared_key = f"{axis}_offset"
                    axis_default = 15 if axis == "horizontal" else 0
                    shared_val = cleaned.get(shared_key, axis_default)
                    shared_number = _offset_number(shared_val, axis_default)
                    for slot_position, slot_payload in enumerate(slot_payloads):
                        slot_key = f"_{axis}_offset"
                        if slot_key in slot_payload:
                            continue
                        if axis == "horizontal":
                            slot_payload[slot_key] = int(round(shared_number + back_padding))
                        else:
                            relative_index = slot_position - center_index
                            slot_payload[slot_key] = int(round(shared_number + (vertical_step * relative_index)))
                    cleaned.pop(shared_key, None)

                preserve_explicit_multi_slot_offsets = had_explicit_slot_offsets and len(slot_payloads) > 1

                # If all explicit per-slot vertical offsets are identical, they
                # still represent a single shared anchor from Quickstart's composite preview.
                # Re-expand them to match the preview stack used on the canvas.
                vertical_values = [_offset_number(slot_payload.get("_vertical_offset"), None) for slot_payload in slot_payloads]
                horizontal_values = [_offset_number(slot_payload.get("_horizontal_offset"), None) for slot_payload in slot_payloads]
                if not preserve_explicit_multi_slot_offsets and alignment == "vertical" and len(slot_payloads) > 1 and all(value is not None for value in vertical_values):
                    if len(set(vertical_values)) == 1:
                        base_vertical = vertical_values[0]
                        for slot_position, slot_payload in enumerate(slot_payloads):
                            relative_index = slot_position - center_index
                            slot_payload["_vertical_offset"] = int(round(base_vertical + (vertical_step * relative_index)))

                if not preserve_explicit_multi_slot_offsets and len(slot_payloads) > 1 and all(value is not None for value in horizontal_values):
                    if len(set(horizontal_values)) == 1:
                        base_horizontal = horizontal_values[0]
                        if base_horizontal == shared_horizontal_base:
                            for slot_payload in slot_payloads:
                                slot_payload["_horizontal_offset"] = int(round(base_horizontal + back_padding))

                if not preserve_explicit_multi_slot_offsets and alignment == "vertical" and len(slot_payloads) > 1 and all(value is not None for value in vertical_values):
                    old_vertical_step = back_height + back_padding
                    legacy_matches = True
                    for slot_position, explicit_vertical in enumerate(vertical_values):
                        relative_index = slot_position - center_index
                        expected_legacy = int(round(shared_vertical_base + (old_vertical_step * relative_index)))
                        if explicit_vertical != expected_legacy:
                            legacy_matches = False
                            break
                    if legacy_matches:
                        for slot_position, slot_payload in enumerate(slot_payloads):
                            relative_index = slot_position - center_index
                            slot_payload["_vertical_offset"] = int(round(shared_vertical_base + (vertical_step * relative_index)))

                # Kometa enforces non-negative "distance from edge" offsets for right/bottom anchors.
                # Left/top anchors can still legitimately be negative (intentional nudge past the edge).
                if h_pos == "right":
                    for slot_payload in slot_payloads:
                        value = _offset_number(slot_payload.get("_horizontal_offset"), None)
                        if value is not None and value < 0:
                            slot_payload["_horizontal_offset"] = int(round(abs(value)))
                if v_pos == "bottom":
                    for slot_payload in slot_payloads:
                        value = _offset_number(slot_payload.get("_vertical_offset"), None)
                        if value is not None and value < 0:
                            slot_payload["_vertical_offset"] = int(round(abs(value)))

                for slot_position, slot_payload in enumerate(slot_payloads, start=1):
                    rating_key = f"rating{slot_position}"
                    for suffix, value in slot_payload.items():
                        target_key = rating_key if suffix == "" else f"{rating_key}{suffix}"
                        cleaned[target_key] = value

                if cleaned:
                    overlay_entry["template_variables"] = cleaned
                else:
                    overlay_entry.pop("template_variables", None)

            def overlay_lookup_name(name):
                if not isinstance(name, str):
                    return name
                if name in {"commonsense", "overlay_content_rating_commonsense", "content_rating_commonsense"}:
                    return "content_rating_commonsense"
                return name

            def reorder_rating_template_vars(overlay_entry):
                if not isinstance(overlay_entry, dict):
                    return
                default_name = overlay_entry.get("default", "")
                if not (isinstance(default_name, str) and (default_name == "ratings" or default_name.startswith("overlay_ratings"))):
                    return
                tv = overlay_entry.get("template_variables")
                if not isinstance(tv, dict) or not tv:
                    return
                preferred_order = [
                    "builder_level",
                    "rating1",
                    "rating1_image",
                    "rating1_font",
                    "rating1_font_size",
                    "rating1_font_color",
                    "rating1_stroke_width",
                    "rating1_stroke_color",
                    "rating1_horizontal_offset",
                    "rating1_vertical_offset",
                    "rating2",
                    "rating2_image",
                    "rating2_font",
                    "rating2_font_size",
                    "rating2_font_color",
                    "rating2_stroke_width",
                    "rating2_stroke_color",
                    "rating2_horizontal_offset",
                    "rating2_vertical_offset",
                    "rating3",
                    "rating3_image",
                    "rating3_font",
                    "rating3_font_size",
                    "rating3_font_color",
                    "rating3_stroke_width",
                    "rating3_stroke_color",
                    "rating3_horizontal_offset",
                    "rating3_vertical_offset",
                    "horizontal_position",
                    "horizontal_offset",
                    "vertical_offset",
                    "back_align",
                    "back_color",
                    "back_height",
                    "back_width",
                    "back_line_color",
                    "back_line_width",
                    "back_padding",
                    "back_radius",
                    "use_subtitles",
                ]
                ordered = {}
                for key in preferred_order:
                    if key in tv:
                        ordered[key] = tv[key]
                for key in tv:
                    if key not in ordered:
                        ordered[key] = tv[key]
                overlay_entry["template_variables"] = ordered

            default_language_flag_codes = ["en", "de", "fr", "es", "pt", "ja"]
            default_language_flag_weights = {
                "en": 610,
                "de": 600,
                "fr": 590,
                "es": 580,
                "pt": 570,
                "ja": 560,
                "ko": 550,
                "zh": 540,
                "da": 530,
                "ru": 520,
                "it": 510,
                "hi": 500,
                "te": 490,
                "fa": 480,
                "th": 470,
                "nl": 460,
                "no": 450,
                "is": 440,
                "sv": 430,
                "tr": 420,
                "pl": 410,
                "cs": 400,
                "uk": 390,
                "hu": 380,
                "ar": 370,
                "bg": 360,
                "bn": 350,
                "bs": 340,
                "ca": 330,
                "cy": 320,
                "el": 310,
                "et": 300,
                "eu": 290,
                "fi": 280,
                "tl": 270,
                "fil": 265,
                "gl": 260,
                "he": 250,
                "hr": 240,
                "id": 230,
                "ka": 220,
                "kk": 210,
                "kn": 200,
                "la": 190,
                "lt": 180,
                "lv": 170,
                "mk": 160,
                "ml": 150,
                "mr": 140,
                "ms": 130,
                "nb": 120,
                "nn": 110,
                "pa": 100,
                "ro": 90,
                "sk": 80,
                "sl": 70,
                "sq": 60,
                "sr": 50,
                "so": 45,
                "sw": 40,
                "ta": 30,
                "ur": 20,
                "ay": 19,
                "ga": 18,
                "li": 17,
                "kh": 16,
                "vi": 15,
                "mn": 14,
                "af": 13,
                "bm": 12,
                "ln": 11,
                "wo": 10,
                "lo": 9,
                "myn": 8,
                "iu": 7,
                "rom": 6,
                "am": 5,
                "su": 4,
                "zu": 3,
                "lb": 2,
                "mos": 1,
            }

            if overlay_key and overlay_key in overlays:
                raw_overlay_entries = overlays[overlay_key]

                if library_type == "mov":
                    overlay_groups = {}
                    for key, value in raw_overlay_entries.items():
                        if not key.startswith(f"{library_type}-library_{overlay_key}-movie-overlay_"):
                            continue
                        if not value:
                            continue

                        raw_name = key.split("-overlay_")[-1]
                        is_subtitles = raw_name == "languages_subtitles"

                        overlay_name = (
                            "languages_subtitles"
                            if is_subtitles
                            else "commonsense" if value == "commonsense" else f"content_rating_{value}" if "content_rating" in raw_name and isinstance(value, str) else raw_name
                        )

                        key_tuple = (overlay_name, is_subtitles)
                        overlay_groups.setdefault(key_tuple, {})

                    for overlay_name, is_subtitles in overlay_groups:
                        entry_obj = {"default": overlay_name}
                        if is_subtitles:
                            entry_obj["template_variables"] = {"use_subtitles": True}
                        overlay_entries.append(entry_obj)

                    for overlay_entry in overlay_entries:
                        overlay_name = overlay_entry["default"]
                        lookup_name = overlay_lookup_name(overlay_name)
                        full_key_prefix = f"{library_type}-library_{overlay_key}-movie-template_overlay_{lookup_name}"

                        if overlay_name.startswith("content_rating_"):
                            variant = overlay_name[len("content_rating_") :]
                            color_key = f"{library_type}-library_{overlay_key}-movie-template_overlay_content_rating_{variant}[color]"
                            color_value = raw_overlay_entries.get(color_key, False)
                            if isinstance(color_value, str):
                                color_value = color_value.lower() == "true"
                            overlay_entry.setdefault("template_variables", {})["color"] = color_value

                        for raw_key, raw_value in raw_overlay_entries.items():
                            if not raw_key.startswith(full_key_prefix + "["):
                                continue
                            var_name = raw_key[len(full_key_prefix) + 1 : -1]
                            if var_name == "languages":
                                raw_value = _parse_string_list(raw_value)
                            elif isinstance(var_name, str) and var_name.startswith("weight_"):
                                try:
                                    raw_value = int(str(raw_value).strip())
                                except (TypeError, ValueError):
                                    pass
                            elif isinstance(raw_value, str):
                                raw_value = True if raw_value.lower() == "true" else False if raw_value.lower() == "false" else raw_value
                            overlay_entry.setdefault("template_variables", {})[var_name] = raw_value

                        prune_rating_template_vars(overlay_entry)

                    # Strip _subtitles for final YAML output consistency
                    for overlay_entry in overlay_entries:
                        if overlay_entry["default"] == "languages_subtitles":
                            overlay_entry["default"] = "languages"

                # [UPDATED BLOCK] Show overlay handling in `add_entry()` (no collisions, clean logic)

                elif library_type == "sho":
                    overlay_groups = {}
                    builder_levels = ["show", "season", "episode"]

                    for level in builder_levels:
                        prefix = f"{library_type}-library_{overlay_key}-{level}-overlay_"
                        for key, value in raw_overlay_entries.items():
                            if not key.startswith(prefix) or not value:
                                continue

                            raw_name = key.split("-overlay_")[-1]
                            is_subtitles = raw_name == "languages_subtitles"

                            overlay_name = (
                                "languages_subtitles"
                                if is_subtitles
                                else "commonsense" if value == "commonsense" else f"content_rating_{value}" if "content_rating" in raw_name and isinstance(value, str) else raw_name
                            )

                            sort_name = "languages" if is_subtitles else overlay_name
                            if sort_name not in overlay_name_order:
                                overlay_name_order.append(sort_name)

                            key_tuple = (overlay_name, is_subtitles, level)
                            overlay_groups.setdefault(key_tuple, True)

                    for overlay_name, is_subtitles, level in overlay_groups:
                        entry_obj = {"default": overlay_name}
                        tv = {}

                        if level != "show":
                            tv["builder_level"] = level
                        if is_subtitles:
                            tv["use_subtitles"] = True
                        if tv:
                            entry_obj["template_variables"] = tv

                        overlay_entries.append(entry_obj)

                    for overlay_entry in overlay_entries:
                        overlay_name = overlay_entry["default"]
                        level = overlay_entry.get("template_variables", {}).get("builder_level", "show")
                        lookup_name = overlay_lookup_name(overlay_name)
                        full_key_prefix = f"{library_type}-library_{overlay_key}-{level}-template_overlay_{lookup_name}"

                        if overlay_name.startswith("content_rating_"):
                            variant = overlay_name[len("content_rating_") :]
                            color_key = f"{library_type}-library_{overlay_key}-{level}-template_overlay_content_rating_{variant}[color]"
                            color_value = raw_overlay_entries.get(color_key, False)
                            if isinstance(color_value, str):
                                color_value = color_value.lower() == "true"
                            overlay_entry.setdefault("template_variables", {})["color"] = color_value

                        for raw_key, raw_value in raw_overlay_entries.items():
                            if not raw_key.startswith(full_key_prefix + "["):
                                continue
                            var_name = raw_key[len(full_key_prefix) + 1 : -1]
                            if var_name == "languages":
                                raw_value = _parse_string_list(raw_value)
                            elif isinstance(var_name, str) and var_name.startswith("weight_"):
                                try:
                                    raw_value = int(str(raw_value).strip())
                                except (TypeError, ValueError):
                                    pass
                            elif isinstance(raw_value, str):
                                raw_value = True if raw_value.lower() == "true" else False if raw_value.lower() == "false" else raw_value
                            overlay_entry.setdefault("template_variables", {})[var_name] = raw_value

                        prune_rating_template_vars(overlay_entry)

                    # Strip _subtitles at the end (just for YAML output cleanliness)
                    for overlay_entry in overlay_entries:
                        if overlay_entry["default"] == "languages_subtitles":
                            overlay_entry["default"] = "languages"

                # Final cleanup for specific overlays (e.g., drop text for aspect/video_format)
                for ov in overlay_entries:
                    default_name = ov.get("default", "")
                    tv = ov.get("template_variables")
                    if not isinstance(tv, dict):
                        continue
                    for key, value in list(tv.items()):
                        if value is None:
                            tv.pop(key, None)
                    if tv.get("builder_level") == "show":
                        tv.pop("builder_level", None)
                        if not tv:
                            ov.pop("template_variables", None)
                            continue
                    if isinstance(default_name, str) and default_name in {"resolution", "overlay_resolution"}:
                        use_edition_val = tv.get("use_edition")
                        use_resolution_val = tv.get("use_resolution")
                        if isinstance(use_edition_val, str):
                            use_edition_val = use_edition_val.lower() == "true"
                        if isinstance(use_resolution_val, str):
                            use_resolution_val = use_resolution_val.lower() == "true"
                        if use_edition_val is None:
                            tv["use_edition"] = True
                            use_edition_val = True
                        elif use_edition_val is False:
                            tv["use_edition"] = False
                            use_edition_val = False
                        if use_resolution_val is None:
                            tv["use_resolution"] = True
                            use_resolution_val = True
                        elif use_resolution_val is False:
                            tv["use_resolution"] = False
                            use_resolution_val = False
                        if use_edition_val is True:
                            resolution_levels = ["4k", "1080p", "720p", "576p", "480p"]
                            resolution_variants = ["dvhdrplus", "dvhdr", "plus", "dv", "hlg", "hdr"]
                            keep_keys = {
                                "builder_level",
                                "use_edition",
                                "use_resolution",
                                "use_4k",
                                "use_1080p",
                                "use_720p",
                                "use_576p",
                                "use_480p",
                                "use_dv",
                                "use_hlg",
                                "use_hdr",
                                "use_plus",
                                "use_dvhdr",
                                "use_dvhdrplus",
                                "use_extended",
                                "use_uncut",
                                "use_unrated",
                                "use_special",
                                "use_anniversary",
                                "use_collector",
                                "use_diamond",
                                "use_platinum",
                                "use_directors",
                                "use_final",
                                "use_international",
                                "use_theatrical",
                                "use_ultimate",
                                "use_alternate",
                                "use_coda",
                                "use_enhanced",
                                "use_imax",
                                "use_remastered",
                                "use_criterion",
                                "use_richarddonner",
                                "use_blackchrome",
                                "use_definitive",
                                "use_openmatte",
                                "use_ulysses",
                                "use_producers",
                                "horizontal_offset",
                                "vertical_offset",
                            }
                            keep_keys.update(
                                {f"use_{resolution_level}_{resolution_variant}" for resolution_level in resolution_levels for resolution_variant in resolution_variants}
                            )
                            for key in list(tv.keys()):
                                if key not in keep_keys:
                                    tv.pop(key, None)
                            if not tv:
                                ov.pop("template_variables", None)
                                continue
                    if isinstance(default_name, str) and default_name in {"commonsense", "overlay_content_rating_commonsense", "content_rating_commonsense"}:
                        for key in ["text", "font", "font_size", "font_color"]:
                            tv.pop(key, None)
                        if not tv:
                            ov.pop("template_variables", None)
                        continue
                    if isinstance(default_name, str) and default_name in {"episode_info", "overlay_episode_info"}:
                        tv.pop("text", None)
                        if not tv:
                            ov.pop("template_variables", None)
                        continue
                    if isinstance(default_name, str) and default_name in {"languages", "overlay_languages"}:
                        languages_value = tv.get("languages")
                        if languages_value is not None:
                            normalized_languages = _parse_string_list(languages_value)
                            if normalized_languages == default_language_flag_codes or not normalized_languages:
                                tv.pop("languages", None)
                            else:
                                tv["languages"] = normalized_languages
                        for key in list(tv.keys()):
                            if not (isinstance(key, str) and key.startswith("weight_")):
                                continue
                            language_key = key[len("weight_") :]
                            default_weight = default_language_flag_weights.get(language_key)
                            try:
                                numeric_value = int(str(tv.get(key)).strip())
                            except (TypeError, ValueError):
                                continue
                            tv[key] = numeric_value
                            if default_weight is not None and numeric_value == default_weight:
                                tv.pop(key, None)
                        if not tv:
                            ov.pop("template_variables", None)
                            continue
                    if isinstance(default_name, str) and default_name in {"aspect", "video_format", "overlay_aspect", "overlay_video_format"}:
                        tv.pop("text", None)
                        if not tv:
                            ov.pop("template_variables", None)

                if overlay_entries:
                    # Final cleanup: drop rating pairs if either side is empty
                    for ov in overlay_entries:
                        default_name = ov.get("default", "")
                        if not (isinstance(default_name, str) and (default_name == "ratings" or default_name.startswith("overlay_ratings"))):
                            continue
                        tv = ov.get("template_variables")
                        if not isinstance(tv, dict):
                            continue
                        for idx in ["1", "2", "3"]:
                            r_key = f"rating{idx}"
                            i_key = f"{r_key}_image"
                            r_val = tv.get(r_key)
                            i_val = tv.get(i_key)

                            def _is_empty(val):
                                if val is None or val is False:
                                    return True
                                if isinstance(val, dict):
                                    raw_val = val.get("value", "")
                                    return raw_val is None or (isinstance(raw_val, str) and (raw_val.strip() == "" or raw_val.strip().lower() == "none"))
                                if isinstance(val, str):
                                    return val.strip() == "" or val.strip().lower() == "none"
                                return False

                            if _is_empty(r_val):
                                tv.pop(r_key, None)
                                tv.pop(i_key, None)
                                continue
                            if _is_empty(i_val):
                                tv.pop(r_key, None)
                                tv.pop(i_key, None)
                        if not tv:
                            ov.pop("template_variables", None)

                    for ov in overlay_entries:
                        reorder_rating_template_vars(ov)

                    if overlay_name_order:
                        order_map = {name: idx for idx, name in enumerate(overlay_name_order)}
                        level_order = {"show": 0, "season": 1, "episode": 2}

                        def overlay_sort_key(overlay_entry):
                            name = overlay_entry.get("default", "")
                            sort_name = "languages" if name == "languages_subtitles" else name
                            name_index = order_map.get(sort_name, len(order_map))
                            tv = overlay_entry.get("template_variables") or {}
                            if not isinstance(tv, dict):
                                tv = {}
                            level = tv.get("builder_level", "show")
                            level_index = level_order.get(level, 0)
                            subtitles_index = 1 if tv.get("use_subtitles") else 0
                            return (name_index, level_index, subtitles_index)

                        overlay_entries.sort(key=overlay_sort_key)

                overlay_library_prefix = library_key[: -len("-library")] if isinstance(library_key, str) and library_key.endswith("-library") else library_key
                raw_overlay_file_entries = _parse_overlay_file_block_entries(overlays.get(overlay_key, {}).get(f"{overlay_library_prefix}-overlay_files"))
                if raw_overlay_file_entries:
                    overlay_entries.extend(raw_overlay_file_entries)

                if overlay_entries:
                    entry["overlay_files"] = overlay_entries

        metadata_group = (
            movie_metadata_files.get(helpers.extract_library_name(library_key), {})
            if library_type == "mov"
            else show_metadata_files.get(helpers.extract_library_name(library_key), {})
        )
        library_prefix = library_key[: -len("-library")] if isinstance(library_key, str) and library_key.endswith("-library") else library_key
        metadata_entries = _parse_metadata_file_entries(metadata_group.get(f"{library_prefix}-metadata_files"))
        if metadata_entries:
            entry["metadata_files"] = metadata_entries

        # Template Variables
        template_key = helpers.extract_library_name(library_key)
        template_data = templates.get(template_key, {})

        sep_color_key = None
        placeholder_key = None
        language_key = None
        collection_mode_key = None

        for key in template_data.keys():
            if key.endswith("-template_variables[use_separator]") and key.startswith(f"{library_type}-library_{template_key}"):
                sep_color_key = key
            if key.endswith("-attribute_template_variables[placeholder_imdb_id]") and key.startswith(f"{library_type}-library_{template_key}"):
                placeholder_key = key
            if key.endswith("-template_variables[language]") and key.startswith(f"{library_type}-library_{template_key}"):
                language_key = key
            if key.endswith("-template_variables[collection_mode]") and key.startswith(f"{library_type}-library_{template_key}"):
                collection_mode_key = key

        sep_color = template_data.get(sep_color_key)
        placeholder_id = template_data.get(placeholder_key)
        language_value = template_data.get(language_key)
        collection_mode_value = template_data.get(collection_mode_key)

        template_vars = {"use_separator": True if sep_color else False}

        if sep_color:
            template_vars["sep_style"] = sep_color

        if placeholder_id:
            template_vars["placeholder_imdb_id"] = placeholder_id

        if language_value:
            template_vars["language"] = language_value
        if collection_mode_value:
            template_vars["collection_mode"] = collection_mode_value

        if has_collectionless:
            template_vars["collection_mode"] = "hide"

        entry["template_variables"] = template_vars

        # Grouped mass update operations (excluding mass_genre_update, handled earlier)
        grouped_operations = [
            "mass_content_rating_update",
            "mass_original_title_update",
            "mass_studio_update",
            "mass_tagline_update",
            "mass_originally_available_update",
            "mass_added_at_update",
            "mass_audience_rating_update",
            "mass_critic_rating_update",
            "mass_user_rating_update",
            "mass_episode_audience_rating_update",
            "mass_episode_critic_rating_update",
            "mass_episode_user_rating_update",
            "mass_background_update",
            "mass_poster_update",
            "radarr_remove_by_tag",
            "sonarr_remove_by_tag",
        ]

        for op in grouped_operations:
            custom_list_key = f"{library_type}-library_{lib_id}-attribute_{op}_custom"
            custom_string_key = f"{library_type}-library_{lib_id}-attribute_{op}_custom_string"
            order_key = f"{library_type}-library_{lib_id}-attribute_{op}_order"

            op_values = []

            # 1. Ordered source list (sortable)
            order_value = attr_group.get(order_key)
            if order_value:
                try:
                    parsed = json.loads(order_value)
                    if isinstance(parsed, list):
                        for item in parsed:
                            if isinstance(item, (int, float)):
                                op_values.append(item)
                            elif isinstance(item, str) and item.strip():
                                # Preserve valid date strings (e.g. "2023-01-01")
                                op_values.append(item.strip())
                except Exception as e:
                    helpers.ts_log(f"Skipping invalid JSON in {op}_order: {order_value} — {e}", level="ERROR")

            # 2. Custom list (JSON array from UI)
            custom_list_value = attr_group.get(custom_list_key)
            if custom_list_value:
                try:
                    parsed_custom = json.loads(custom_list_value)
                    if isinstance(parsed_custom, list):
                        for item in parsed_custom:
                            if isinstance(item, (int, float)):
                                op_values.append(item)
                            elif isinstance(item, str) and item.strip():
                                op_values.append(item.strip())
                except Exception as e:
                    helpers.ts_log(f"Skipping invalid JSON in {op}_custom: {custom_list_value} — {e}", level="ERROR")

            # 3. Fallback to single custom string (if defined)
            elif custom_string_key in attr_group:
                raw_value = attr_group.get(custom_string_key)
                if isinstance(raw_value, str) and raw_value.strip():
                    if op in [
                        "mass_critic_rating_update",
                        "mass_user_rating_update",
                        "mass_audience_rating_update",
                        "mass_episode_critic_rating_update",
                        "mass_episode_user_rating_update",
                        "mass_episode_audience_rating_update",
                    ]:
                        try:
                            op_values.append(float(raw_value.strip()))
                        except ValueError:
                            pass  # Invalid float, skip
                    else:
                        op_values.append(raw_value.strip())
                elif isinstance(raw_value, (int, float)):
                    op_values.append(raw_value)

            # 4. Output formatting
            if op_values:
                seq = CommentedSeq(op_values)
                seq.fa.set_block_style()
                for i in range(len(seq)):
                    if isinstance(seq[i], float) and seq[i].is_integer():
                        seq[i] = float(f"{seq[i]:.1f}")
                operations[op] = seq

        # genre_mapper and content_rating_mapper
        for mapper_key in ["genre_mapper", "content_rating_mapper"]:
            full_key = f"{library_type}-library_{lib_id}-attribute_{mapper_key}"
            mapping_value = attr_group.get(full_key)
            if mapping_value:
                try:
                    parsed_mapping = json.loads(mapping_value)
                    if isinstance(parsed_mapping, dict) and parsed_mapping:
                        operations[mapper_key] = parsed_mapping
                except Exception as e:
                    helpers.ts_log(f"Skipping invalid JSON for {mapper_key}: {mapping_value} — {e}", level="ERROR")

        # metadata_backup
        backup = {}
        path_key = f"{library_type}-library_{lib_id}-attribute_metadata_backup_path"
        exclude_key = f"{library_type}-library_{lib_id}-attribute_metadata_backup_exclude"
        sync_key = f"{library_type}-library_{lib_id}-attribute_sync_tags"
        blank_key = f"{library_type}-library_{lib_id}-attribute_add_blank_entries"

        if attr_group.get(path_key):
            backup["path"] = attr_group.get(path_key)

        # Only add exclude if it is a non-empty list
        if attr_group.get(exclude_key):
            val = attr_group.get(exclude_key)
            try:
                parsed = json.loads(val) if isinstance(val, str) else val
                if isinstance(parsed, list) and parsed:  # non-empty list only
                    backup["exclude"] = parsed
            except Exception as e:
                helpers.ts_log(f"Skipping invalid exclude value: {val} — {e}", level="ERROR")

        if attr_group.get(sync_key) is True:
            backup["sync_tags"] = True
        if attr_group.get(blank_key) is True:
            backup["add_blank_entries"] = True

        # Only add to operations if backup has any keys
        if backup:
            operations["metadata_backup"] = backup

        # mass_poster_update
        poster = {}
        for key in [
            "seasons",
            "episodes",
            "ignore_locked",
            "ignore_overlays",
            "source",
        ]:
            full_key = f"{library_type}-library_{lib_id}-attribute_mass_poster_{key}"
            val = attr_group.get(full_key)
            if val not in [None, False, ""]:
                poster[key] = val
        if poster:
            operations["mass_poster_update"] = poster

        # mass_background_update
        background = {}
        for key in ["seasons", "episodes", "ignore_locked", "source"]:
            full_key = f"{library_type}-library_{lib_id}-attribute_mass_background_{key}"
            val = attr_group.get(full_key)
            if val not in [None, False, ""]:
                background[key] = val
        if background:
            operations["mass_background_update"] = background

        # Remove/Reset Overlays
        top_group = top_level.get(lib_id, {})

        remove_key = f"{library_type}-library_{lib_id}-top_level_remove_overlays"
        reset_key = f"{library_type}-library_{lib_id}-top_level_reset_overlays"
        schedule_key = f"{library_type}-library_{lib_id}-top_level_schedule"
        schedule_overlays_key = f"{library_type}-library_{lib_id}-top_level_schedule_overlays"
        report_path_key = f"{library_type}-library_{lib_id}-top_level_report_path"

        remove_overlays = top_group.get(remove_key)
        reset_overlays = top_group.get(reset_key)
        schedule = top_group.get(schedule_key)
        schedule_overlays = top_group.get(schedule_overlays_key)
        report_path = top_group.get(report_path_key)

        if report_path not in [None, ""]:
            entry["report_path"] = report_path
        if schedule not in [None, ""]:
            entry["schedule"] = schedule
        if remove_overlays:
            entry["remove_overlays"] = True
        if reset_overlays not in [None, "None", ""]:
            entry["reset_overlays"] = reset_overlays
        if schedule_overlays not in [None, ""]:
            entry["schedule_overlays"] = schedule_overlays

        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Top Level for {lib_id}: {top_group}", level="DEBUG")
            helpers.ts_log(f"{report_path_key} = {report_path}", level="DEBUG")
            helpers.ts_log(f"{schedule_key} = {schedule}", level="DEBUG")
            helpers.ts_log(f"{remove_key} = {remove_overlays}", level="DEBUG")
            helpers.ts_log(f"{reset_key} = {reset_overlays}", level="DEBUG")
            helpers.ts_log(f"{schedule_overlays_key} = {schedule_overlays}", level="DEBUG")

        if operations:
            entry["operations"] = operations

        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Entry for {library_name}: {entry}", level="DEBUG")

        libraries_section[library_name] = reorder_library_section(entry)

    #############################################################################################

    # Process movie libraries (A->Z by display name, deterministic on key ties)
    for lk, ln in sorted_library_items(movie_libraries):
        add_entry(
            lk,
            ln,
            "mov",
            movie_collections,
            movie_overlays,
            movie_attributes,
            movie_templates,
            movie_top_level,
        )

    # Process show libraries (A->Z by display name, deterministic on key ties)
    for lk, ln in sorted_library_items(show_libraries):
        add_entry(
            lk,
            ln,
            "sho",
            show_collections,
            show_overlays,
            show_attributes,
            show_templates,
            show_top_level,
        )

    if app.config["QS_DEBUG"]:
        helpers.ts_log(f"Generated YAML Output:\n", level="DEBUG")
        buf = io.BytesIO()
        YAML().dump({"libraries": libraries_section}, buf)
        helpers.ts_log(buf.getvalue().decode("utf-8"))

    return {"libraries": libraries_section}


def reorder_library_section(library_data):
    """
    Reorders library data so that:
    - `report_path` appears first.
    - `schedule` comes next.
    - `remove_overlays`, `reset_overlays`, and `schedule_overlays` come after that.
    - `template_variables` next.
    - `settings` appears before `radarr` / `sonarr` / `operations`.
    - `metadata_files` appears after library settings and operations.
    - `metadata_files` appears before `collection_files`.
    - `collection_files` appears before `overlay_files`.
    - Keys inside `operations` are ordered as per Kometa Wiki.
    - Other keys retain their natural order.
    """
    reordered_data = {}

    # 1. Place report_path first if it exists
    if "report_path" in library_data:
        reordered_data["report_path"] = library_data["report_path"]

    # 2. Then library schedule
    if "schedule" in library_data:
        reordered_data["schedule"] = library_data["schedule"]

    # 3. Then remove/reset overlays
    if "remove_overlays" in library_data:
        reordered_data["remove_overlays"] = library_data["remove_overlays"]
    if "reset_overlays" in library_data:
        reordered_data["reset_overlays"] = library_data["reset_overlays"]
    if "schedule_overlays" in library_data:
        reordered_data["schedule_overlays"] = library_data["schedule_overlays"]

    # 4. Then template_variables
    if "template_variables" in library_data:
        reordered_data["template_variables"] = library_data["template_variables"]

    # 5. Then library settings
    if "settings" in library_data:
        reordered_data["settings"] = library_data["settings"]

    # 6. Then per-library Arr overrides
    if "radarr" in library_data:
        reordered_data["radarr"] = library_data["radarr"]
    if "sonarr" in library_data:
        reordered_data["sonarr"] = library_data["sonarr"]

    # 7. Reorder operations
    operations_order = [
        "assets_for_all",
        "assets_for_all_collections",
        "delete_collections",
        "mass_genre_update",
        "mass_content_rating_update",
        "mass_original_title_update",
        "mass_studio_update",
        "mass_originally_available_update",
        "mass_added_at_update",
        "mass_audience_rating_update",
        "mass_critic_rating_update",
        "mass_user_rating_update",
        "mass_episode_audience_rating_update",
        "mass_episode_critic_rating_update",
        "mass_episode_user_rating_update",
        "mass_poster_update",
        "mass_background_update",
        "mass_imdb_parental_labels",
        "mass_collection_mode",
        "update_blank_track_titles",
        "remove_title_parentheses",
        "split_duplicates",
        "radarr_add_all",
        "radarr_remove_by_tag",
        "sonarr_add_all",
        "sonarr_remove_by_tag",
        "genre_mapper",
        "content_rating_mapper",
        "metadata_backup",
    ]

    if "operations" in library_data:
        ordered_ops = {}
        ops = library_data["operations"]
        for key in operations_order:
            if key in ops:
                ordered_ops[key] = ops[key]
        # Include any unknown keys at the end
        for k, v in ops.items():
            if k not in ordered_ops:
                ordered_ops[k] = v
        reordered_data["operations"] = ordered_ops

    # 8. Then library-level metadata/collections/overlays in explicit YAML order
    if "metadata_files" in library_data:
        reordered_data["metadata_files"] = library_data["metadata_files"]
    if "collection_files" in library_data:
        reordered_data["collection_files"] = library_data["collection_files"]
    if "overlay_files" in library_data:
        reordered_data["overlay_files"] = library_data["overlay_files"]

    # 9. Finally add any other keys that weren't handled
    for key, value in library_data.items():
        if key not in reordered_data:
            reordered_data[key] = value

    return reordered_data


def build_config(header_style="standard", config_name=None):
    """
    Build the final configuration, including all sections and headers,
    ensuring the libraries section is properly processed.
    """
    if not config_name and has_request_context():
        config_name = session.get("config_name")

    sections = helpers.get_template_list()
    config_data = {}
    header_art = {}
    library_types = {}

    def header_for_section(section_key, display_name):
        if section_key in header_art:
            return header_art[section_key]
        if header_style == "none":
            return ""
        if header_style == "single line" or helpers.contains_non_latin(display_name):
            return "#==================== " + display_name + " ====================#"
        try:
            return add_border_to_ascii_art(pyfiglet.figlet_format(display_name, font=header_style))
        except pyfiglet.FontNotFound:
            return "#==================== " + display_name + " ====================#"

    # Process sections and generate header art
    for name in sections:
        item = sections[name]
        persistence_key = item["stem"]
        config_attribute = item["raw_name"]

        # Handle all header styles
        if header_style == "none":
            header_art[config_attribute] = ""  # No headers at all
        elif header_style == "single line" or helpers.contains_non_latin(item["name"]):  # Standardizes "single line" as divider format
            header_art[config_attribute] = "#==================== " + item["name"] + " ====================#"
        else:
            # Handle custom PyFiglet fonts dynamically (including "standard")
            try:
                figlet_text = pyfiglet.figlet_format(item["name"], font=header_style)
                header_art[config_attribute] = add_border_to_ascii_art(figlet_text)
            except pyfiglet.FontNotFound:
                # Fallback to "single line" divider format instead of basic text
                header_art[config_attribute] = "#==================== " + item["name"] + " ====================#"

        # Retrieve settings for each section.
        # Deep-copy here so YAML normalization cannot mutate the in-memory
        # structure returned from persistence for this request lifecycle.
        section_data = copy.deepcopy(persistence.retrieve_settings(persistence_key))

        if "validated" in section_data and section_data["validated"]:
            config_data[config_attribute] = clean_section_data(section_data, config_attribute)

    # Process playlist_files section
    if "playlist_files" in config_data:
        playlist_data = config_data["playlist_files"]

        # Debug raw data
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Raw config_data['playlist_files'] content (Level 1): {playlist_data}", level="DEBUG")

        # Adjust for possible extra nesting
        if "playlist_files" in playlist_data and isinstance(playlist_data["playlist_files"], dict):
            playlist_data = playlist_data["playlist_files"]
            if app.config["QS_DEBUG"]:
                helpers.ts_log(f" playlist_data after extra nesting: {playlist_data}", level="DEBUG")

        # Extract and process libraries
        libraries_value = playlist_data.get("libraries", "")
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Extracted libraries value: {libraries_value}", level="DEBUG")

        libraries_list = [lib.strip() for lib in libraries_value.split(",") if lib.strip()]
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Processed libraries list: {libraries_value}", level="DEBUG")

        # Format playlist_files data
        formatted_playlist_files = _format_playlist_files(libraries_list)
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Formatted playlist_files data:", formatted_playlist_files, level="DEBUG")

        # Replace in config_data
        config_data["playlist_files"] = formatted_playlist_files

    if "webhooks" in config_data:
        webhooks_data = config_data["webhooks"]

        # Handle case where `webhooks` is nested inside itself
        if isinstance(webhooks_data, dict) and "webhooks" in webhooks_data:
            webhooks_data = webhooks_data["webhooks"]  # Fix: Handle extra nesting

        # Remove empty values
        cleaned_webhooks = {key: value for key, value in webhooks_data.items() if value is not None and value != "" and value != [] and value != {}}

        # If no valid webhooks exist, remove the "webhooks" section entirely
        if cleaned_webhooks:
            config_data["webhooks"] = {"webhooks": cleaned_webhooks}  # Preserve webhooks key
        else:
            config_data.pop("webhooks", None)  # Fully remove empty webhooks

        # Debugging: Ensure webhooks are correctly cleaned
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Cleaned Webhooks Data AFTER Removing Empty Values: {cleaned_webhooks}", level="DEBUG")
            if "webhooks" not in config_data:
                helpers.ts_log(f"Webhooks section completely removed.", level="DEBUG")

    if "apprise" in config_data:
        apprise_data = config_data["apprise"]
        apprise_location = None

        if isinstance(apprise_data, dict):
            if "apprise" in apprise_data:
                nested_apprise = apprise_data["apprise"]
                if isinstance(nested_apprise, dict):
                    apprise_location = nested_apprise.get("location")
                else:
                    apprise_location = nested_apprise
            elif "location" in apprise_data:
                apprise_location = apprise_data.get("location")
        elif isinstance(apprise_data, str):
            apprise_location = apprise_data

        apprise_location = str(apprise_location).strip() if apprise_location is not None else ""
        if apprise_location:
            config_data["apprise"] = {"apprise": {"config": apprise_location}}
        else:
            config_data.pop("apprise", None)

    # Initialize movie and show libraries
    movie_libraries = {}
    show_libraries = {}

    # Process the libraries section
    if "libraries" in config_data and "libraries" in config_data["libraries"]:
        nested_libraries_data = config_data["libraries"]["libraries"]

        # Debugging
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Raw nested libraries data:", nested_libraries_data, level="DEBUG")

        # Extract selected libraries
        movie_libraries = {
            key: value
            for key, value in nested_libraries_data.items()
            if key and isinstance(key, str) and key.startswith("mov-library_") and key.endswith("-library") and value not in [None, "", False]
        }
        show_libraries = {
            key: value
            for key, value in nested_libraries_data.items()
            if key and isinstance(key, str) and key.startswith("sho-library_") and key.endswith("-library") and value not in [None, "", False]
        }

        # Extract **correct** movie and show library names
        movie_library_names = {helpers.extract_library_name(k) for k in movie_libraries}
        show_library_names = {helpers.extract_library_name(k) for k in show_libraries}
        library_types = {name: "movie" for name in movie_libraries.values()}
        library_types.update({name: "show" for name in show_libraries.values()})

        # Debugging
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Movie Library Names:", movie_library_names, level="DEBUG")
            helpers.ts_log(f"Show Library Names:", show_library_names, level="DEBUG")

        def group_by_library(prefix, names, normalize_overlays=False):
            """
            Groups data (collections, overlays, attributes, etc.) by base library name.

            If `normalize_overlays` is True, it strips builder-level suffixes
            (e.g. `tv_shows-show` → `tv_shows`) to match show library names.
            """
            grouped = {}

            def matches_group_prefix(key):
                if not isinstance(key, str):
                    return False
                # Keep library-level *_files blocks isolated from the default
                # collection/overlay groups so they do not suppress built-in
                # defaults during YAML emission.
                if prefix == "collection_":
                    return "-collection_" in key or "-template_collection_" in key
                if prefix == "overlay_":
                    return "-overlay_" in key or "-template_overlay_" in key
                if prefix == "attribute_":
                    return "-attribute_" in key
                if prefix == "template_variables":
                    return "-template_variables" in key or "-attribute_template_variables" in key
                if prefix == "top_level_":
                    return "-top_level_" in key
                if prefix in {"collection_files", "overlay_files", "metadata_files"}:
                    return key.endswith(f"-{prefix}")
                return prefix in key

            for key, value in nested_libraries_data.items():
                if not matches_group_prefix(key):
                    continue

                lib_name_raw = helpers.extract_library_name(key)

                # Normalize overlays by trimming builder-level suffix (movie/show/season/episode),
                # without losing hyphenated library names.
                lib_name = lib_name_raw
                if normalize_overlays and isinstance(lib_name_raw, str):
                    for suffix in ("-movie", "-show", "-season", "-episode"):
                        if lib_name_raw.endswith(suffix):
                            lib_name = lib_name_raw[: -len(suffix)]
                            break

                if lib_name in names:
                    grouped.setdefault(lib_name, {})[key] = value

            return grouped

        # Group collections, overlays, attributes, and templates only for selected libraries
        movie_collections = group_by_library("collection_", movie_library_names)
        show_collections = group_by_library("collection_", show_library_names)
        movie_collection_files = group_by_library("collection_files", movie_library_names)
        show_collection_files = group_by_library("collection_files", show_library_names)
        movie_overlay_file_blocks = group_by_library("overlay_files", movie_library_names)
        show_overlay_file_blocks = group_by_library("overlay_files", show_library_names)
        # movie_overlays = group_by_library("overlay_", movie_library_names)
        # show_overlays = group_by_library("overlay_", show_library_names)
        movie_overlays = group_by_library("overlay_", movie_library_names, normalize_overlays=True)
        show_overlays = group_by_library("overlay_", show_library_names, normalize_overlays=True)
        for lib_name, payload in movie_overlay_file_blocks.items():
            movie_overlays.setdefault(lib_name, {}).update(payload)
        for lib_name, payload in show_overlay_file_blocks.items():
            show_overlays.setdefault(lib_name, {}).update(payload)
        movie_attributes = group_by_library("attribute_", movie_library_names)
        show_attributes = group_by_library("attribute_", show_library_names)
        movie_metadata_files = group_by_library("metadata_files", movie_library_names)
        show_metadata_files = group_by_library("metadata_files", show_library_names)
        movie_templates = group_by_library("template_variables", movie_library_names)
        show_templates = group_by_library("template_variables", show_library_names)
        movie_top_level = group_by_library("top_level_", movie_library_names)
        show_top_level = group_by_library("top_level_", show_library_names)

        # Debugging
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Extracted Movie Libraries: {movie_libraries}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Libraries: {show_libraries}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Collections: {movie_collections}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Collections: {show_collections}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Collection Files: {movie_collection_files}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Collection Files: {show_collection_files}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Overlay File Blocks: {movie_overlay_file_blocks}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Overlay File Blocks: {show_overlay_file_blocks}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Overlays: {movie_overlays}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Overlays: {show_overlays}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Attributes: {movie_attributes}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Attributes: {show_attributes}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Metadata Files: {movie_metadata_files}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Metadata Files: {show_metadata_files}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Templates: {movie_templates}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Templates: {show_templates}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Top Level: {movie_top_level}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Top Level: {show_top_level}", level="DEBUG")

        # Build nested libraries structure
        libraries_section = build_libraries_section(
            movie_libraries,
            show_libraries,
            movie_collections,
            show_collections,
            movie_collection_files,
            show_collection_files,
            movie_overlays,
            show_overlays,
            movie_attributes,
            show_attributes,
            movie_metadata_files,
            show_metadata_files,
            movie_templates,
            show_templates,
            movie_top_level,
            show_top_level,
        )
        config_data["libraries"] = libraries_section.get("libraries", {}) if isinstance(libraries_section, dict) else {}
        ordered_library_names = _library_names_in_output_order(libraries_section)
        has_playlist_toggle, playlist_libraries = _playlist_libraries_from_library_toggles(
            nested_libraries_data,
            ordered_library_names=ordered_library_names,
        )
        if has_playlist_toggle:
            if playlist_libraries:
                config_data["playlist_files"] = _format_playlist_files(playlist_libraries)
            else:
                config_data.pop("playlist_files", None)
        else:
            legacy_playlist_libraries = _legacy_playlist_libraries_for_selected_libraries(
                nested_libraries_data,
                ordered_library_names=ordered_library_names,
            )
            if legacy_playlist_libraries:
                config_data["playlist_files"] = _format_playlist_files(legacy_playlist_libraries)
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Final Libraries Section: {libraries_section}", level="DEBUG")

    # Header comment for YAML file
    header_comment = (
        "### \n# We highly recommend using Visual Studio Code with indent-rainbow by oderwat extension "
        "and YAML by Red Hat extension. Visual Studio Code will also leverage the above link (yaml-language-server) to enhance Kometa yml edits.\n###"
    )

    # Build YAML content
    yaml = YAML(typ="safe", pure=True)
    yaml.default_flow_style = False
    yaml.sort_keys = False

    helpers.ensure_json_schema()

    with open(os.path.join(helpers.JSON_SCHEMA_DIR, "config-schema.json"), "r") as file:
        schema = yaml.load(file)

    # Reuse the shared update snapshot instead of re-checking on every final-page render.
    version_info = app.config.get("VERSION_CHECK") or helpers.check_for_update()
    kometa_branch = version_info.get("kometa_branch", "nightly")  # Default to nightly if not found

    # Fetch other Quickstart details
    quickstart_branch = version_info.get("branch", "unknown")
    quickstart_version = version_info.get("local_version", "unknown")
    quickstart_environment = version_info.get("running_on", "unknown")

    system_name = platform.system() or "Unknown OS"
    system_release = platform.release() or ""
    cpu_name = platform.processor() or platform.uname().processor or "Unknown CPU"
    cpu_cores = psutil.cpu_count(logical=True) or 0
    vm = psutil.virtual_memory()
    mem_total = int(vm.total / (1024 * 1024))
    mem_available = int(vm.available / (1024 * 1024))
    mem_used = int((vm.total - vm.available) / (1024 * 1024))
    mem_percent = int(vm.percent)
    is_docker = bool(app.config.get("QUICKSTART_DOCKER")) or "Docker" in str(quickstart_environment)
    python_version = platform.python_version() or platform.python_version_tuple()[0]
    git_version = "Unavailable"
    git_path = shutil.which("git")
    if git_path:
        try:
            git_result = subprocess.run(
                [git_path, "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            git_output = (git_result.stdout or git_result.stderr or "").strip()
            if git_output:
                git_version = git_output
        except Exception:
            git_version = "Unavailable"
    os_line = f"# OS: {system_name} {system_release}".strip()
    browser_line = "Unknown"
    if has_request_context():
        browser_name = session.get("qs_user_agent_browser") or ""
        browser_version = session.get("qs_user_agent_version") or ""
        browser_platform = session.get("qs_user_agent_platform") or ""
        if browser_name:
            browser_line = browser_name
            if browser_version:
                browser_line = f"{browser_line} {browser_version}"
            if browser_platform:
                browser_line = f"{browser_line} ({browser_platform})"
        else:
            browser_line = session.get("qs_user_agent_raw") or session.get("qs_user_agent") or "Unknown"

    # Get the current timestamp in a readable format
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Get plex info
    plex_summary = helpers.get_plex_summary()
    qs_settings_lines = helpers.get_quickstart_settings_summary()
    qs_settings_block = "\n".join(qs_settings_lines) if qs_settings_lines else ""
    movie_summary_names = sorted(
        (str(name).strip() for name in movie_libraries.values() if str(name).strip()),
        key=lambda value: value.casefold(),
    )
    show_summary_names = sorted(
        (str(name).strip() for name in show_libraries.values() if str(name).strip()),
        key=lambda value: value.casefold(),
    )
    library_names = movie_summary_names + show_summary_names
    library_details = helpers.get_library_summaries(library_names)
    schema_header = f"# yaml-language-server: $schema=https://raw.githubusercontent.com/Kometa-Team/Kometa/{kometa_branch}/json-schema/config-schema.json"

    yaml_content = (
        f"{schema_header}\n\n"
        f"{add_border_to_ascii_art(section_heading('KOMETA', font=header_style)) if header_style not in ['none', 'single line'] else section_heading('KOMETA', font=header_style)}\n\n"
        f"#==================== {config_name} ====================#\n"
        f"# {config_name} config created by Quickstart on {timestamp}\n"
        f"# System Information\n"
        f"{os_line}\n"
        f"# Docker: {is_docker}\n"
        f"# CPU: {cpu_name} ({cpu_cores} cores)\n"
        f"# Memory: {mem_used} MB / {mem_total} MB ({mem_percent}%) | {mem_available} MB Free\n"
        f"# Python: {python_version}\n"
        f"# Git: {git_version}\n"
        f"# Browser: {browser_line}\n"
        f"{qs_settings_block}\n"
        f"{'# ' + plex_summary.replace(chr(10), chr(10) + '# ')}\n"
        f"# Quickstart: {quickstart_version} | Branch: {quickstart_branch} | Environment: {quickstart_environment}\n"
        f"###\n"
        f"# Libraries configured with Quickstart: {len(movie_libraries)} movie, {len(show_libraries)} show\n"
        f"{'# ' + library_details.replace(chr(10), chr(10) + '# ')}\n"
        f"{header_comment}\n\n"
        f"# This file is auto-generated by Quickstart. Do not edit manually unless you know what you are doing.\n"
        f"#==================== {config_name} ====================#\n"
        f"\n\n"
    )

    def inject_section_headers(yaml_string, font):
        def art(title):
            if font in ["none", "single line"] or helpers.contains_non_latin(title):
                return f"#==================== {title} ====================#"
            try:
                return add_border_to_ascii_art(pyfiglet.figlet_format(title, font=font))
            except pyfiglet.FontNotFound:
                return f"#==================== {title} ====================#"

        lines = yaml_string.splitlines()
        output = []
        in_libraries_block = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Detect when we've entered the top-level libraries block
            if stripped == "libraries:":
                in_libraries_block = True
                output.append(line)
                continue

            # Exit the block once indentation resets or we hit a new top-level key
            if in_libraries_block and not line.startswith("  ") and not line.strip().startswith("#") and ":" in line:
                in_libraries_block = False

            # Only inject header for lines like "  Movies:" or "  TV Shows:" inside the libraries block
            if in_libraries_block and line.startswith("  ") and not line.startswith("   ") and line.strip().endswith(":") and not line.strip().startswith("-"):
                library_name = line.strip().rstrip(":")
                output.append(art(library_name))

            elif stripped.startswith("collection_files:"):
                output.append(art("Collections"))
            elif stripped.startswith("metadata_files:"):
                output.append(art("Metadata Files"))
            elif stripped.startswith("overlay_files:"):
                output.append(art("Overlays"))

            output.append(line)

        return "\n".join(output)

    # Function to dump YAML sections
    def dump_section(title, dump_name, data):

        dump_yaml = YAML()
        dump_yaml.default_flow_style = False
        dump_yaml.sort_keys = False  # Preserve original key order
        dump_yaml.width = 4096  # avoid folding long tokens/secrets

        # Custom representation for `None` values
        dump_yaml.representer.add_representer(
            type(None),
            lambda self, _: self.represent_scalar("tag:yaml.org,2002:null", ""),
        )

        def _prune_empty_output_values(obj):
            if isinstance(obj, dict):
                pruned = {}
                for key, value in obj.items():
                    if key == "valid":
                        continue
                    cleaned_value = _prune_empty_output_values(value)
                    if cleaned_value is _EMPTY_OUTPUT:
                        continue
                    pruned[key] = cleaned_value
                return pruned if pruned else _EMPTY_OUTPUT
            if isinstance(obj, list):
                cleaned_items = []
                for value in obj:
                    cleaned_value = _prune_empty_output_values(value)
                    if cleaned_value is _EMPTY_OUTPUT:
                        continue
                    cleaned_items.append(cleaned_value)
                return cleaned_items if cleaned_items else _EMPTY_OUTPUT
            if obj is None:
                return _EMPTY_OUTPUT
            if isinstance(obj, str) and obj.strip() == "":
                return _EMPTY_OUTPUT
            return obj

        def clean_data(obj):
            if isinstance(obj, dict):
                # Sort specific sections alphabetically
                if dump_name in [
                    "settings",
                    "webhooks",
                    "plex",
                    "tmdb",
                    "tautulli",
                    "github",
                    "omdb",
                    "mdblist",
                    "notifiarr",
                    "gotify",
                    "ntfy",
                    "apprise",
                    "anidb",
                    "radarr",
                    "sonarr",
                    "trakt",
                    "mal",
                ]:
                    obj = dict(sorted(obj.items()))  # Alphabetically sort keys in the section
                cleaned_dict = {}
                for k, v in obj.items():
                    if k == "valid":
                        continue
                    cleaned_value = clean_data(v)
                    if cleaned_value is _EMPTY_OUTPUT:
                        continue
                    cleaned_dict[k] = cleaned_value
                return cleaned_dict if cleaned_dict else _EMPTY_OUTPUT
            elif isinstance(obj, list):
                cleaned_list = []
                for v in obj:
                    cleaned_value = clean_data(v)
                    if cleaned_value is _EMPTY_OUTPUT:
                        continue
                    cleaned_list.append(cleaned_value)
                return cleaned_list if cleaned_list else _EMPTY_OUTPUT
            else:
                return _prune_empty_output_values(obj)

        # Clean the data
        cleaned_data = clean_data(data)
        if cleaned_data is _EMPTY_OUTPUT:
            cleaned_data = {}
        if dump_name == "libraries" and isinstance(cleaned_data, dict) and "libraries" not in cleaned_data:
            cleaned_data = {"libraries": cleaned_data}
        if dump_name == "anidb":
            section = cleaned_data.get("anidb")
            if isinstance(section, dict):
                section.pop("enable", None)

        # Force long/scalar strings to emit in plain style (avoid folded multi-line) for sensitive sections
        plain_scalar_sections = {
            "plex",
            "tmdb",
            "tautulli",
            "github",
            "omdb",
            "mdblist",
            "notifiarr",
            "gotify",
            "ntfy",
            "apprise",
            "anidb",
            "radarr",
            "sonarr",
            "trakt",
            "mal",
        }

        def plainify_strings(obj):
            if isinstance(obj, dict):
                return {k: plainify_strings(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [plainify_strings(v) for v in obj]
            if isinstance(obj, str):
                return PlainScalarString(obj)
            return obj

        if dump_name in plain_scalar_sections:
            cleaned_data = plainify_strings(cleaned_data)

        # Normalize MAL/TRAKT numeric fields
        if dump_name in ("mal", "trakt"):
            section = cleaned_data.get(dump_name, {})
            auth = section.get("authorization", {})

            if isinstance(auth, dict) and "expires_in" in auth:
                try:
                    auth["expires_in"] = int(auth["expires_in"])
                except Exception:
                    pass

            if "cache_expiration" in section:
                try:
                    section["cache_expiration"] = int(section["cache_expiration"])
                except Exception:
                    pass

        if dump_name == "trakt":
            section = cleaned_data.get("trakt", {})
            if isinstance(section, dict):
                auth = section.get("authorization")
                if isinstance(auth, dict) and "force_refresh" in auth and "force_refresh" not in section:
                    section["force_refresh"] = auth.pop("force_refresh")

                preferred_order = ["authorization", "client_id", "client_secret", "pin", "force_refresh"]
                ordered_section = {}
                for key in preferred_order:
                    if key in section:
                        ordered_section[key] = section[key]
                for key, value in section.items():
                    if key not in ordered_section:
                        ordered_section[key] = value
                cleaned_data["trakt"] = ordered_section

        # Ensure settings multi-value inputs are normalized for YAML output.
        if dump_name == "settings" and isinstance(cleaned_data.get("settings"), dict):
            settings_block = cleaned_data["settings"]
            for setting_key in list(settings_block.keys()):
                normalized_value = _normalize_settings_section_value(setting_key, settings_block.get(setting_key))
                if normalized_value is None:
                    settings_block.pop(setting_key, None)
                else:
                    settings_block[setting_key] = normalized_value

            if "asset_directory" in settings_block:
                if isinstance(settings_block["asset_directory"], str):
                    # Convert multi-line string into a list
                    settings_block["asset_directory"] = _normalize_asset_directory_values(settings_block["asset_directory"])
                elif isinstance(settings_block["asset_directory"], list):
                    # Ensure all list items are strings
                    settings_block["asset_directory"] = _normalize_asset_directory_values(settings_block["asset_directory"])

        # Dump the cleaned data to YAML
        with io.StringIO() as stream:
            dump_yaml.dump(cleaned_data, stream)
            section_output = stream.getvalue().strip()
            if header_style != "none":
                section_output = inject_section_headers(section_output, header_style)

            validation_comment = build_validation_comment(dump_name)
            blocks = []
            if title:
                blocks.append(title)
            if validation_comment:
                blocks.append(validation_comment)
            blocks.append(section_output)
            return "\n".join(blocks) + "\n\n"

    def format_validation_timestamp(raw):
        if not raw:
            return ""
        try:
            normalized = raw.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            local = parsed.astimezone()
            return local.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return raw

    def build_validation_comment(section_key):
        if not config_name:
            return ""
        stored = database.retrieve_section_data(config_name, section_key)
        if not stored or not isinstance(stored[2], dict):
            return ""
        stored_validated = helpers.booler(stored[0])
        payload = stored[2]
        status = payload.get("validation_status")
        if not status:
            if stored_validated:
                status = "validated"
            else:
                fallback_timestamp = payload.get("validated_at")
                status = "failed" if fallback_timestamp else ""
        if not status:
            return ""
        updated_at = payload.get("validation_updated_at") or payload.get("validated_at")
        last_validated = format_validation_timestamp(updated_at)
        if last_validated:
            return f"# validation: {status} (last_validated: {last_validated})"
        return f"# validation: {status}"

    ordered_sections = [
        ("libraries", "025-libraries"),
        ("playlist_files", "027-playlist_files"),
        ("settings", "150-settings"),
        ("webhooks", "140-webhooks"),
        ("plex", "010-plex"),
        ("tmdb", "020-tmdb"),
        ("tautulli", "030-tautulli"),
        ("github", "040-github"),
        ("omdb", "050-omdb"),
        ("mdblist", "060-mdblist"),
        ("notifiarr", "070-notifiarr"),
        ("gotify", "080-gotify"),
        ("ntfy", "085-ntfy"),
        ("apprise", "087-apprise"),
        ("anidb", "090-anidb"),
        ("radarr", "100-radarr"),
        ("sonarr", "110-sonarr"),
        ("trakt", "120-trakt"),
        ("mal", "130-mal"),
    ]

    # Ensure `code_verifier` is removed from mal.authorization (wherever it exists)
    if "mal" in config_data and "mal" in config_data["mal"]:
        authorization_data = config_data["mal"]["mal"].get("authorization", {})
        authorization_data.pop("code_verifier", None)  # Remove safely

    config_data = _normalize_legacy_collection_template_vars(config_data)
    optimize_defaults = helpers.booler(app.config.get("QS_OPTIMIZE_DEFAULTS", True))
    if optimize_defaults:
        config_data = optimize_template_variables(config_data, library_types)
    config_data = _collapse_collection_data_template_vars(config_data)

    # Apply enforce_string_fields to ensure proper formatting
    config_data = helpers.enforce_string_fields(config_data, helpers.STRING_FIELDS)
    config_data = _rewrite_custom_font_paths(config_data)

    for section_key, section_stem in ordered_sections:
        if section_key in config_data:
            section_data = config_data[section_key]
            section_art = header_for_section(section_key, helpers.user_visible_name(section_key))
            yaml_content += dump_section(section_art, section_key, section_data)

    validated = False
    validation_error = None
    validation_errors = []
    parsed_yaml = yaml.load(yaml_content)
    validator = jsonschema.Draft7Validator(schema)
    validation_errors = sorted(validator.iter_errors(parsed_yaml), key=lambda err: list(err.path))
    if validation_errors:
        validation_error = validation_errors[0]
    else:
        validated = True

    return validated, validation_error, config_data, yaml_content, validation_errors
