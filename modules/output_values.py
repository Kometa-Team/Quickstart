"""Pure value-coercion and parsing primitives for config-YAML generation.

Extracted from the original ``modules/output.py`` monolith.  Each helper
is small (< 40 lines) and dependency-free -- they take raw config
values (strings, dicts, lists, ints, floats, ``None``) and return a
normalized shape.  Nothing here touches Flask, the database,
persistence, helpers, or any other repo state.

Public surface (nothing here is a public API -- each name starts with
an underscore).  ``modules/output.py`` re-exports them via
``from modules.output_values import *`` so historical call sites like
``output._parse_string_list(...)`` continue to work unchanged.

Groups:
  * ``_normalize_template_value`` -- unwrap ``{"value": X}`` and trim strings
  * ``_coerce_bool`` / ``_to_number`` -- scalar coercion with fallback
  * ``_coerce_string_list`` / ``_parse_string_list`` /
    ``_parse_comma_string_list`` -- list-of-string normalizers
  * ``_parse_string_list_mapping`` / ``_parse_string_mapping`` /
    ``_parse_template_mapping_dict`` -- dict-shaped normalizers
  * ``_playlist_scalar_or_list`` -- collapse 1-element lists to scalars
  * ``_normalize_asset_directory_entry`` /
    ``_normalize_asset_directory_values`` -- unescape Windows/UNC paths
"""

from __future__ import annotations

import ast
import json
import re


def _normalize_template_value(value):
    if isinstance(value, dict):
        if "value" in value:
            value = value.get("value")
    if isinstance(value, str):
        return value.strip()
    return value


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


def _parse_string_mapping(value):
    parsed = _parse_template_mapping_dict(value)
    if not parsed:
        return {}

    normalized = {}
    for raw_key, raw_value in parsed.items():
        key_text = str(raw_key or "").strip()
        if not key_text:
            continue
        if isinstance(raw_value, (list, tuple, set)):
            parts = _coerce_string_list(raw_value)
            value_text = ", ".join(parts)
        else:
            value_text = str(raw_value or "").strip()
        if value_text:
            normalized[key_text] = value_text
    return normalized


def _playlist_scalar_or_list(values):
    if not values:
        return None
    return values[0] if len(values) == 1 else values


# --- asset directory path normalization -----------------------------------
#
# Kometa's ``asset_directory:`` config accepts multi-line strings or lists.
# On Windows, users often paste YAML-escaped paths like ``C:\\Users\\me``
# where the double-backslashes are the YAML wire form of a single one.
# UNC paths keep their leading ``\\`` prefix (that's the UNC marker).


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
