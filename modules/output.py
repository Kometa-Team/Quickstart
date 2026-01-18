import io
import os
import json
import re
import shutil
import subprocess
from datetime import datetime
import platform
import psutil

import jsonschema
import pyfiglet
from flask import current_app as app, has_request_context, session
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import PlainScalarString
from ruamel.yaml.comments import CommentedSeq

from modules import helpers, persistence


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
                        clean_sub_data[sub_key] = sub_value
                clean_data[key] = clean_sub_data
            else:
                clean_data[key] = value

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
        data = helpers.load_quickstart_config("quickstart_overlays.json")
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
    def _reorder_ratings_template_vars(entry):
        if not isinstance(entry, dict):
            return
        default_name = entry.get("default", "")
        if not (isinstance(default_name, str) and (default_name == "ratings" or default_name.startswith("overlay_ratings"))):
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
            "rating2",
            "rating2_image",
            "rating2_font",
            "rating2_font_size",
            "rating2_font_color",
            "rating2_stroke_width",
            "rating2_stroke_color",
            "rating3",
            "rating3_image",
            "rating3_font",
            "rating3_font_size",
            "rating3_font_color",
            "rating3_stroke_width",
            "rating3_stroke_color",
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
        entry["template_variables"] = ordered

    libraries_section = config_data.get("libraries", {})
    libraries = libraries_section.get("libraries")
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

                pruned = _prune_template_variables(tv, defaults)
                always_keep = set()
                if entry.get("default") in {"ratings", "overlay_ratings"}:
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


def build_libraries_section(
    movie_libraries,
    show_libraries,
    movie_collections,
    show_collections,
    movie_overlays,
    show_overlays,
    movie_attributes,
    show_attributes,
    movie_templates,
    show_templates,
    movie_top_level,
    show_top_level,
):
    libraries_section = {}

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

        # Process Operations Attributes
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

        for field in operations_fields:
            attr_key = f"{library_type}-library_{lib_id}-attribute_{field}"
            value = attr_group.get(attr_key, None)
            if value not in [None, "", False]:
                operations[field] = value

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

        if operations:
            entry["operations"] = operations

        # Process Collections
        has_collectionless = False
        collection_key = helpers.extract_library_name(library_key)
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"collections keys for {collection_key}: {list(collections.get(collection_key, {}).keys())}", level="DEBUG")
            helpers.ts_log(f"templates keys for {collection_key}: {list(templates.get(collection_key, {}).keys())}", level="DEBUG")

        if collection_key and collection_key in collections:
            collection_files = []

            for key, selected in collections[collection_key].items():
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
                    file_entry["template_variables"] = {
                        k: (True if isinstance(v, (bool, str)) and str(v).lower() == "true" else False if isinstance(v, (bool, str)) and str(v).lower() == "false" else v)
                        for k, v in all_children.items()
                    }

                collection_files.append(file_entry)

            if collection_files:

                def is_collectionless(item):
                    default_name = str(item.get("default", "")).strip().lower()
                    return default_name in {"collectionless", "collection_collectionless"} or default_name.endswith("collectionless")

                collection_files.sort(key=lambda item: (is_collectionless(item)))
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

                # Enforce ratingN <-> ratingN_image dependency; if either side is empty, drop both
                for idx in ["1", "2", "3"]:
                    r_key = f"rating{idx}"
                    i_key = f"{r_key}_image"
                    r_val = cleaned.get(r_key)
                    i_val = cleaned.get(i_key)
                    if r_key in cleaned or i_key in cleaned:

                        def _is_empty(val):
                            if val is None or val is False:
                                return True
                            if isinstance(val, str):
                                return val.strip() == "" or val.strip().lower() == "none"
                            return False

                        if _is_empty(r_val):
                            cleaned.pop(r_key, None)
                            cleaned.pop(i_key, None)
                            continue
                        if _is_empty(i_val):
                            cleaned.pop(r_key, None)
                            cleaned.pop(i_key, None)

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
                    "rating2",
                    "rating2_image",
                    "rating2_font",
                    "rating2_font_size",
                    "rating2_font_color",
                    "rating2_stroke_width",
                    "rating2_stroke_color",
                    "rating3",
                    "rating3_image",
                    "rating3_font",
                    "rating3_font_size",
                    "rating3_font_color",
                    "rating3_stroke_width",
                    "rating3_stroke_color",
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
                            if isinstance(raw_value, str):
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
                            if isinstance(raw_value, str):
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
                    if tv.get("builder_level") == "show":
                        tv.pop("builder_level", None)
                        if not tv:
                            ov.pop("template_variables", None)
                            continue
                    if isinstance(default_name, str) and default_name in {"resolution", "overlay_resolution"}:
                        use_edition_val = tv.get("use_edition")
                        if isinstance(use_edition_val, str):
                            use_edition_val = use_edition_val.lower() == "true"
                        if use_edition_val is None or use_edition_val is False:
                            tv["use_edition"] = False
                            use_edition_val = False
                        if use_edition_val is True:
                            keep_keys = {"use_edition", "horizontal_offset", "vertical_offset"}
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

                    entry["overlay_files"] = overlay_entries

        # Template Variables
        template_key = helpers.extract_library_name(library_key)
        template_data = templates.get(template_key, {})

        sep_color_key = None
        placeholder_key = None
        language_key = None

        for key in template_data.keys():
            if key.endswith("-template_variables[use_separator]") and key.startswith(f"{library_type}-library_{template_key}"):
                sep_color_key = key
            if key.endswith("-attribute_template_variables[placeholder_imdb_id]") and key.startswith(f"{library_type}-library_{template_key}"):
                placeholder_key = key
            if key.endswith("-template_variables[language]") and key.startswith(f"{library_type}-library_{template_key}"):
                language_key = key

        sep_color = template_data.get(sep_color_key)
        placeholder_id = template_data.get(placeholder_key)
        language_value = template_data.get(language_key)

        template_vars = {"use_separator": True if sep_color else False}

        if sep_color:
            template_vars["sep_style"] = sep_color

        if placeholder_id:
            template_vars["placeholder_imdb_id"] = placeholder_id

        if language_value:
            template_vars["language"] = language_value

        if has_collectionless:
            template_vars["collection_mode"] = "hide_items"

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
        report_path_key = f"{library_type}-library_{lib_id}-top_level_report_path"

        remove_overlays = top_group.get(remove_key)
        reset_overlays = top_group.get(reset_key)
        report_path = top_group.get(report_path_key)

        if report_path not in [None, ""]:
            entry["report_path"] = report_path
        if remove_overlays:
            entry["remove_overlays"] = True
        if reset_overlays not in [None, "None", ""]:
            entry["reset_overlays"] = reset_overlays

        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Top Level for {lib_id}: {top_group}", level="DEBUG")
            helpers.ts_log(f"{report_path_key} = {report_path}", level="DEBUG")
            helpers.ts_log(f"{remove_key} = {remove_overlays}", level="DEBUG")
            helpers.ts_log(f"{reset_key} = {reset_overlays}", level="DEBUG")

        if operations:
            entry["operations"] = operations

        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Entry for {library_name}: {entry}", level="DEBUG")

        libraries_section[library_name] = reorder_library_section(entry)

    #############################################################################################

    # Process movie libraries
    for lk, ln in movie_libraries.items():
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

    # Process show libraries
    for lk, ln in show_libraries.items():
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
    - `remove_overlays` and `reset_overlays` come next.
    - `template_variables` next.
    - Keys inside `operations` are ordered as per Kometa Wiki.
    - Other keys retain their natural order.
    """
    reordered_data = {}

    # 1. Place report_path first if it exists
    if "report_path" in library_data:
        reordered_data["report_path"] = library_data["report_path"]

    # 2. Then remove/reset overlays
    if "remove_overlays" in library_data:
        reordered_data["remove_overlays"] = library_data["remove_overlays"]
    if "reset_overlays" in library_data:
        reordered_data["reset_overlays"] = library_data["reset_overlays"]

    # 3. Then template_variables
    if "template_variables" in library_data:
        reordered_data["template_variables"] = library_data["template_variables"]

    # 4. Reorder operations
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

    # 5. Finally add any other keys that weren't handled
    for key, value in library_data.items():
        if key not in reordered_data:
            reordered_data[key] = value

    return reordered_data


def build_config(header_style="standard", config_name=None):
    """
    Build the final configuration, including all sections and headers,
    ensuring the libraries section is properly processed.
    """
    sections = helpers.get_template_list()
    config_data = {}
    header_art = {}
    library_types = {}

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

        # Retrieve settings for each section
        section_data = persistence.retrieve_settings(persistence_key)

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
        formatted_playlist_files = {
            "playlist_files": [
                {
                    "default": "playlist",
                    "template_variables": {"libraries": libraries_list},
                }
            ]
        }
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

            for key, value in nested_libraries_data.items():
                if prefix not in key:
                    continue

                lib_name_raw = helpers.extract_library_name(key)

                # Normalize if overlay and builder level suffix is present
                if normalize_overlays and "-" in lib_name_raw:
                    lib_name = lib_name_raw.split("-")[0]
                else:
                    lib_name = lib_name_raw

                if lib_name in names:
                    grouped.setdefault(lib_name, {})[key] = value

            return grouped

        # Group collections, overlays, attributes, and templates only for selected libraries
        movie_collections = group_by_library("collection_", movie_library_names)
        show_collections = group_by_library("collection_", show_library_names)
        # movie_overlays = group_by_library("overlay_", movie_library_names)
        # show_overlays = group_by_library("overlay_", show_library_names)
        movie_overlays = group_by_library("overlay_", movie_library_names, normalize_overlays=True)
        show_overlays = group_by_library("overlay_", show_library_names, normalize_overlays=True)
        movie_attributes = group_by_library("attribute_", movie_library_names)
        show_attributes = group_by_library("attribute_", show_library_names)
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
            helpers.ts_log(f"Extracted Movie Overlays: {movie_overlays}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Overlays: {show_overlays}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Attributes: {movie_attributes}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Attributes: {show_attributes}", level="DEBUG")
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
            movie_overlays,
            show_overlays,
            movie_attributes,
            show_attributes,
            movie_templates,
            show_templates,
            movie_top_level,
            show_top_level,
        )
        config_data["libraries"] = libraries_section
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

    # Fetch kometa_branch dynamically
    version_info = helpers.check_for_update()
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
    qs_port = app.config.get("QS_PORT", "Unknown")
    qs_debug = "Enabled" if app.config.get("QS_DEBUG") else "Disabled"
    qs_theme = app.config.get("QS_THEME", "kometa")
    qs_config_history = app.config.get("QS_CONFIG_HISTORY", 0)
    if qs_config_history == 0:
        qs_config_history_display = "Keep all (0)"
    else:
        qs_config_history_display = str(qs_config_history)
    library_names = list(movie_libraries.values()) + list(show_libraries.values())
    library_details = helpers.get_library_summaries(library_names)

    yaml_content = (
        f"# yaml-language-server: $schema=https://raw.githubusercontent.com/Kometa-Team/Kometa/{kometa_branch}/json-schema/config-schema.json\n\n"
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
        f"# Quickstart Port: {qs_port}\n"
        f"# Quickstart Debug: {qs_debug}\n"
        f"# Quickstart Theme: {qs_theme}\n"
        f"# Quickstart Optimize Template Defaults: {'Enabled' if app.config.get('QS_OPTIMIZE_DEFAULTS', True) else 'Disabled'}\n"
        f"# Quickstart Config Archive History: {qs_config_history_display}\n"
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
                    "anidb",
                    "radarr",
                    "sonarr",
                    "trakt",
                    "mal",
                ]:
                    obj = dict(sorted(obj.items()))  # Alphabetically sort keys in the section
                return {k: clean_data(v) for k, v in obj.items() if k != "valid"}
            elif isinstance(obj, list):
                return [clean_data(v) for v in obj]
            else:
                return obj

        # Clean the data
        cleaned_data = clean_data(data)

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

        # Ensure `asset_directory` is serialized as a proper YAML list
        if dump_name == "settings" and "asset_directory" in cleaned_data.get("settings", {}):
            if isinstance(cleaned_data["settings"]["asset_directory"], str):
                # Convert multi-line string into a list
                cleaned_data["settings"]["asset_directory"] = [line.strip() for line in cleaned_data["settings"]["asset_directory"].splitlines() if line.strip()]
            elif isinstance(cleaned_data["settings"]["asset_directory"], list):
                # Ensure all list items are strings
                cleaned_data["settings"]["asset_directory"] = [str(i).strip() for i in cleaned_data["settings"]["asset_directory"]]

        # Dump the cleaned data to YAML
        with io.StringIO() as stream:
            dump_yaml.dump(cleaned_data, stream)
            section_output = stream.getvalue().strip()
            if header_style != "none":
                section_output = inject_section_headers(section_output, header_style)
            return f"{title}\n{section_output}\n\n"

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

    optimize_defaults = helpers.booler(app.config.get("QS_OPTIMIZE_DEFAULTS", True))
    if optimize_defaults:
        config_data = optimize_template_variables(config_data, library_types)

    # Apply enforce_string_fields to ensure proper formatting
    config_data = helpers.enforce_string_fields(config_data, helpers.STRING_FIELDS)
    config_data = _rewrite_custom_font_paths(config_data)

    for section_key, section_stem in ordered_sections:
        if section_key in config_data:
            section_data = config_data[section_key]
            section_art = header_art[section_key]
            yaml_content += dump_section(section_art, section_key, section_data)

    validated = False
    validation_error = None

    try:
        jsonschema.validate(yaml.load(yaml_content), schema)
        validated = True
    except jsonschema.exceptions.ValidationError as e:
        validation_error = e

    return validated, validation_error, config_data, yaml_content
