"""Default-values discovery and template-variable pruning for output.py.

Extracted from the original ``modules/output.py`` monolith.  These nine
helpers form one coherent flow: given the collection/overlay/attribute
schema files under ``static/json/``, compute the per-variable default
values, then diff a user's actual template_variables against those
defaults so the emitted YAML only carries **non-default** overrides.

The typical caller does something like::

    defaults = _build_collection_defaults()
    for library in ...:
        pruned = _prune_template_variables(actual_tv, defaults[media_type][key])

Sub-flow:

* ``_values_match``           -- default-equality with type coercion
* ``_infer_default_from_options`` -- pull first choice from a select
* ``_default_from_var``       -- ``{"default": X}`` > toggle-false > select-first
* ``_extract_template_defaults`` -- run ``_default_from_var`` over a dict/list
* ``_build_collection_defaults`` -- crawl ``quickstart_collections.json``
* ``_extract_offset_defaults`` -- read the overlay-specific offset schema
* ``_build_overlay_defaults`` -- crawl ``quickstart_overlays.json``
* ``_build_attribute_defaults`` -- crawl ``quickstart_attributes.json``
* ``_prune_template_variables`` -- drop keys whose value == default

Nothing here is public API.  ``modules/output.py`` re-imports them via
``# noqa: F401`` so historical call sites like
``output._build_overlay_defaults(...)`` keep working.
"""

from __future__ import annotations

from modules import helpers
from modules.output_values import _coerce_bool, _normalize_template_value, _to_number


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
