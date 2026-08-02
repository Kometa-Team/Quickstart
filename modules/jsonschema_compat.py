"""Compatibility helpers for validating YAML data with jsonschema.

JSON Schema validators expect object keys to be strings. YAML parsers can
produce booleans, numbers, or null as mapping keys when users leave those
values unquoted, so normalize only the validation copy before calling
``jsonschema``.
"""

from __future__ import annotations

from collections.abc import Mapping


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
