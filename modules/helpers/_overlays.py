"""Overlay configuration enrichment utilities extracted from the original helpers.py monolith."""

import copy
import json
import os
import re

from modules.helpers._constants import JSON_SETTINGS


def load_quickstart_config(filename: str):
    json_path = os.path.join(JSON_SETTINGS, filename)
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _overlay_origin_alignment_defaults(origin):
    origin_str = str(origin or "").strip().lower()
    tokens = [token for token in re.split(r"[^a-z]+", origin_str) if token]
    has_center = "center" in tokens

    horizontal = "right" if "right" in tokens else "left"
    if "left" not in tokens and has_center and "right" not in tokens:
        horizontal = "center"

    vertical = "bottom" if "bottom" in tokens else "top"
    if "top" not in tokens and has_center and "bottom" not in tokens:
        vertical = "center"

    return horizontal, vertical


def _overlay_template_var_keys(template_variables):
    keys = set()
    if isinstance(template_variables, dict):
        keys.update(str(key) for key in template_variables.keys())
    elif isinstance(template_variables, list):
        for item in template_variables:
            if isinstance(item, dict) and item.get("key"):
                keys.add(str(item.get("key")))
    return keys


def _insert_overlay_mapping_fields(template_variables, inserted_fields, *, before_keys=None):
    if not isinstance(template_variables, dict) or not inserted_fields:
        return template_variables

    before_keys = set(before_keys or ())
    next_template_variables = {}
    inserted = False

    for key, value in template_variables.items():
        if not inserted and key in before_keys:
            for inserted_key, inserted_value in inserted_fields.items():
                if inserted_key not in template_variables:
                    next_template_variables[inserted_key] = inserted_value
            inserted = True
        next_template_variables[key] = value

    if not inserted:
        for inserted_key, inserted_value in inserted_fields.items():
            if inserted_key not in next_template_variables:
                next_template_variables[inserted_key] = inserted_value

    template_variables.clear()
    template_variables.update(next_template_variables)
    return template_variables


def _insert_overlay_list_fields(template_variables, inserted_fields, *, before_keys=None):
    if not isinstance(template_variables, list) or not inserted_fields:
        return template_variables

    before_keys = set(before_keys or ())
    existing_keys = _overlay_template_var_keys(template_variables)
    next_template_variables = []
    inserted = False

    for item in template_variables:
        item_key = item.get("key") if isinstance(item, dict) else None
        if not inserted and item_key in before_keys:
            for inserted_field in inserted_fields:
                inserted_key = inserted_field.get("key")
                if inserted_key and inserted_key not in existing_keys:
                    next_template_variables.append(copy.deepcopy(inserted_field))
            inserted = True
        next_template_variables.append(item)

    if not inserted:
        for inserted_field in inserted_fields:
            inserted_key = inserted_field.get("key")
            if inserted_key and inserted_key not in existing_keys:
                next_template_variables.append(copy.deepcopy(inserted_field))

    template_variables[:] = next_template_variables
    return template_variables


def enrich_quickstart_overlay_config(config):
    enriched = copy.deepcopy(config or [])

    for group in enriched:
        if not isinstance(group, dict):
            continue
        overlays = group.get("overlays", [])
        if not isinstance(overlays, list):
            continue
        for overlay in overlays:
            if not isinstance(overlay, dict):
                continue
            template_variables = overlay.get("template_variables")
            if template_variables is None:
                template_variables = {}
                overlay["template_variables"] = template_variables
            if not isinstance(template_variables, (dict, list)):
                continue

            existing_keys = _overlay_template_var_keys(template_variables)
            default_offsets = overlay.get("default_offsets")
            offsets_by_type = overlay.get("default_offsets_by_type")

            supports_runtime_offsets = (
                isinstance(default_offsets, dict)
                or (isinstance(offsets_by_type, dict) and any(isinstance(value, dict) for value in offsets_by_type.values()))
                or "initial_horizontal_offset" in existing_keys
                or "initial_vertical_offset" in existing_keys
            )

            offset_defaults = default_offsets if isinstance(default_offsets, dict) else {}
            if not offset_defaults and isinstance(offsets_by_type, dict):
                for candidate in offsets_by_type.values():
                    if isinstance(candidate, dict):
                        offset_defaults = candidate
                        break

            if supports_runtime_offsets:
                horizontal_default = 0
                vertical_default = 0
                if "initial_horizontal_offset" in existing_keys:
                    if isinstance(template_variables, dict):
                        horizontal_default = template_variables.get("initial_horizontal_offset", {}).get(
                            "default",
                            offset_defaults.get("horizontal", 0),
                        )
                    else:
                        for item in template_variables:
                            if isinstance(item, dict) and item.get("key") == "initial_horizontal_offset":
                                horizontal_default = item.get("default", offset_defaults.get("horizontal", 0))
                                break
                else:
                    horizontal_default = offset_defaults.get("horizontal", 0)

                if "initial_vertical_offset" in existing_keys:
                    if isinstance(template_variables, dict):
                        vertical_default = template_variables.get("initial_vertical_offset", {}).get(
                            "default",
                            offset_defaults.get("vertical", 0),
                        )
                    else:
                        for item in template_variables:
                            if isinstance(item, dict) and item.get("key") == "initial_vertical_offset":
                                vertical_default = item.get("default", offset_defaults.get("vertical", 0))
                                break
                else:
                    vertical_default = offset_defaults.get("vertical", 0)

                offset_fields_mapping = {
                    "horizontal_offset": {
                        "input_type": "number",
                        "default": horizontal_default,
                        "label": "Horizontal Offset",
                    },
                    "vertical_offset": {
                        "input_type": "number",
                        "default": vertical_default,
                        "label": "Vertical Offset",
                    },
                }
                offset_fields_list = [
                    {
                        "input_type": "number",
                        "key": "horizontal_offset",
                        "default": horizontal_default,
                        "label": "Horizontal Offset",
                    },
                    {
                        "input_type": "number",
                        "key": "vertical_offset",
                        "default": vertical_default,
                        "label": "Vertical Offset",
                    },
                ]

                if isinstance(template_variables, dict):
                    _insert_overlay_mapping_fields(
                        template_variables,
                        offset_fields_mapping,
                        before_keys={"horizontal_offset", "vertical_offset", "builder_level"},
                    )
                else:
                    _insert_overlay_list_fields(
                        template_variables,
                        offset_fields_list,
                        before_keys={"horizontal_offset", "vertical_offset", "builder_level"},
                    )

            supports_origin_alignment = (
                isinstance(offset_defaults, dict)
                and bool(offset_defaults.get("origin"))
                and "horizontal_position" not in existing_keys
                and "vertical_position" not in existing_keys
            )

            if supports_origin_alignment:
                horizontal_align_default, vertical_align_default = _overlay_origin_alignment_defaults(offset_defaults.get("origin"))
                align_fields_mapping = {
                    "horizontal_align": {
                        "input_type": "select",
                        "default": horizontal_align_default,
                        "label": "Horizontal Alignment",
                        "options": ["left", "center", "right"],
                    },
                    "vertical_align": {
                        "input_type": "select",
                        "default": vertical_align_default,
                        "label": "Vertical Alignment",
                        "options": ["top", "center", "bottom"],
                    },
                }
                align_fields_list = [
                    {
                        "input_type": "select",
                        "key": "horizontal_align",
                        "default": horizontal_align_default,
                        "label": "Horizontal Alignment",
                        "options": ["left", "center", "right"],
                    },
                    {
                        "input_type": "select",
                        "key": "vertical_align",
                        "default": vertical_align_default,
                        "label": "Vertical Alignment",
                        "options": ["top", "center", "bottom"],
                    },
                ]

                if isinstance(template_variables, dict):
                    _insert_overlay_mapping_fields(
                        template_variables,
                        align_fields_mapping,
                        before_keys={"horizontal_offset", "vertical_offset", "builder_level"},
                    )
                else:
                    _insert_overlay_list_fields(
                        template_variables,
                        align_fields_list,
                        before_keys={"horizontal_offset", "vertical_offset", "builder_level"},
                    )

    return enriched


def load_quickstart_overlay_config():
    return enrich_quickstart_overlay_config(load_quickstart_config("quickstart_overlays.json"))
