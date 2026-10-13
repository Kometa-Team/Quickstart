"""Compatibility helpers for validating YAML data with jsonschema.

JSON Schema validators expect object keys to be strings. YAML parsers can
produce booleans, numbers, or null as mapping keys when users leave those
values unquoted, so normalize only the validation copy before calling
``jsonschema``.
"""

from __future__ import annotations

from collections.abc import Mapping


def extend_asset_directory_schema(schema):
    """Allow Kometa's grouped paths when the local schema cache predates them."""
    # Older collection schemas omit this supported override entirely.
    if isinstance(schema, dict):
        definition = schema.get("definitions", {}).get("collection-definition")
        if isinstance(definition, dict) and isinstance(definition.get("properties"), dict):
            definition["properties"].setdefault(
                "asset_directory",
                {"anyOf": [{"type": "string"}, {"type": "array", "uniqueItems": True, "items": {"type": "string"}}]},
            )
    if isinstance(schema, list):
        for child in schema:
            extend_asset_directory_schema(child)
    elif isinstance(schema, dict):
        properties = schema.get("properties", {})
        asset_schema = properties.get("asset_directory") if isinstance(properties, dict) else None
        if isinstance(asset_schema, dict):
            options = asset_schema.get("anyOf", asset_schema.get("oneOf"))
            if not isinstance(options, list):
                options = []
            if options and not any(option.get("type") == "object" for option in options):
                path_schema = {"anyOf": [{"type": "string"}, {"type": "array", "uniqueItems": True, "items": {"type": "string"}}, {"type": "null"}]}
                options.append(
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {group: path_schema for group in ("movies", "shows", "music", "collections")},
                    }
                )
        for child in list(schema.values()):
            extend_asset_directory_schema(child)


def stringify_mapping_keys_for_jsonschema(value):
    """Return a JSON-Schema-safe copy with every mapping key stringified."""
    if isinstance(value, Mapping):
        return {key if isinstance(key, str) else str(key): stringify_mapping_keys_for_jsonschema(child) for key, child in value.items()}
    if isinstance(value, list):
        return [stringify_mapping_keys_for_jsonschema(child) for child in value]
    return value


def find_non_string_mapping_key_paths(value, path=()):
    """Return paths to mapping keys YAML parsed as non-strings."""
    paths = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = (*path, key)
            if not isinstance(key, str):
                paths.append(child_path)
            paths.extend(find_non_string_mapping_key_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(find_non_string_mapping_key_paths(child, (*path, index)))
    return paths
