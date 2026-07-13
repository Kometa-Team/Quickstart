"""Import-time value coercion + serialization helpers.

Extracted from :mod:`modules.importer` to isolate the ~179 lines of
tiny, single-purpose helpers that :func:`prepare_import_payload`
(and its extracted siblings) use to turn heterogeneous user YAML
values into the tight, DB-friendly shapes Quickstart stores.

None of these functions know or care about the wider import
pipeline; they're all pure transformations on individual values.
Ideal candidates for their own module so the coercion rules can
be reviewed and unit-tested in isolation.

## Public-ish API (all leading ``_`` -- internal but re-exported
   from :mod:`modules.importer` for test monkeypatching and for
   ``prepare_import_payload`` which stays behind)

### Type coercion

* :func:`_coerce_import_bool` -- Coerce YAML-wide truthy/falsy
  strings (``true``/``yes``/``1``/``on`` / ``false``/``no``/``0``/``off``,
  case-insensitive, whitespace-tolerant) plus native bools to
  ``bool | None``.  Regression-guarded by
  ``tests/test_importer_edge_cases.test_coerce_import_bool_accepts_yaml_wide_truthy_and_falsy_values``.
* :func:`_coerce_import_int` -- Coerce ints and numeric strings
  to ``int | None``.
* :func:`_coerce_import_string_list` -- Coerce a scalar or list
  to a de-duped ``list[str]``.
* :func:`_coerce_import_bool_text` -- Same as
  :func:`_coerce_import_bool` but returns the string
  ``"true"``/``"false"``/``""`` for round-tripping into the DB.

### Template-var / overlay-meta introspection

* :func:`_collect_template_keys` -- Return the set of top-level
  keys in a ``template_variables`` mapping (defensively handling
  dict-or-list shapes).
* :func:`_collect_dynamic_child_field_specs` -- Extract dynamic
  child field specs (name/kind pairs) from a template-variables
  mapping.
* :func:`_collect_overlay_source_override_keys` -- Compute the
  set of keys an overlay-source template exposes for user override.
* :func:`_has_template_string_list_values` -- True iff a value is
  a non-empty list of strings (used to decide include/exclude
  template branching).

### Serialization

* :func:`_serialize_playlist_import_value` -- Coerce a playlist
  field's raw value into the right shape for its
  ``PLAYLIST_KEYED_IMPORT_FIELDS[prefix]`` value_kind (bool/int/list).
* :func:`_serialize_dynamic_child_mapping_value` -- Turn a
  dynamic-child mapping value into its string representation for
  the payload dict, per its declared ``value_kind``.

Dependency direction: ``importer -> importer_value_coercion``
(one way).  Zero imports from ``importer``, so no circular
imports possible.
"""

from __future__ import annotations

import json
import re
from typing import Any


def _collect_template_keys(template_vars: Any) -> set[str]:
    keys = set()
    if isinstance(template_vars, dict):
        keys.update(str(k) for k in template_vars.keys())
    elif isinstance(template_vars, list):
        for item in template_vars:
            if isinstance(item, dict):
                key = item.get("key")
                if key:
                    keys.add(str(key))
    return keys


def _collect_dynamic_child_field_specs(template_vars: Any) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    if not isinstance(template_vars, list):
        return specs

    for item in template_vars:
        if not isinstance(item, dict):
            continue
        field_key = str(item.get("key") or "").strip()
        child_prefix = str(item.get("dynamic_child_prefix") or "").strip()
        if not field_key or not child_prefix:
            continue
        specs.append(
            {
                "field_key": field_key,
                "child_prefix": child_prefix,
                "value_kind": str(item.get("dynamic_child_value_kind") or "string").strip().lower(),
            }
        )
    return specs


def _coerce_import_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    return None


def _coerce_import_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _serialize_playlist_import_value(value_kind: str, value: Any) -> Any:
    kind = str(value_kind or "string").strip().lower()
    if kind == "boolean":
        bool_value = _coerce_import_bool(value)
        return None if bool_value is None else ("true" if bool_value else "false")
    if kind == "integer":
        int_value = _coerce_import_int(value)
        return None if int_value is None else str(int_value)
    if kind == "string_list":
        values = _coerce_import_string_list(value)
        return values if values else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _collect_overlay_source_override_keys(overlay_meta: Any) -> set[str]:
    if not isinstance(overlay_meta, dict):
        return set()

    config = overlay_meta.get("source_overrides")
    if not isinstance(config, dict):
        return set()

    raw_types = config.get("source_types")
    if isinstance(raw_types, list):
        source_types = [str(item).strip() for item in raw_types if str(item).strip()]
    else:
        source_types = ["file", "url", "git", "repo"]

    allowed = set(source_types)
    key_mode = str(config.get("key_mode") or "").strip().lower()
    if key_mode == "from_select_options":
        key_fields = {str(item).strip() for item in (config.get("key_fields") or []) if str(item).strip()}
        template_variables = overlay_meta.get("template_variables")
        if isinstance(template_variables, dict):
            for field_key in key_fields:
                field_meta = template_variables.get(field_key)
                if not isinstance(field_meta, dict):
                    continue
                options = field_meta.get("options")
                if not isinstance(options, list):
                    continue
                for option in options:
                    if isinstance(option, dict):
                        option_value = str(option.get("value") or "").strip()
                    else:
                        option_value = str(option).strip()
                    if not option_value:
                        continue
                    for source_type in source_types:
                        allowed.add(f"{source_type}_{option_value}")
        return allowed

    if key_mode != "from_use_toggles":
        return allowed

    excluded_toggle_keys = {str(item).strip() for item in (config.get("exclude_toggle_keys") or []) if str(item).strip()}
    template_keys = _collect_template_keys(overlay_meta.get("template_variables"))
    for template_key in template_keys:
        if not template_key.startswith("use_") or template_key in excluded_toggle_keys:
            continue
        child_key = template_key[4:]
        if not child_key:
            continue
        for source_type in source_types:
            allowed.add(f"{source_type}_{child_key}")

    return allowed


def _coerce_import_bool_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    lowered = str(value or "").strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return "true"
    if lowered in {"false", "0", "no", "off"}:
        return "false"
    return str(value or "").strip()


def _serialize_dynamic_child_mapping_value(value: Any, value_kind: str) -> str:
    kind = str(value_kind or "string").strip().lower()
    if kind == "string_list":
        if isinstance(value, list):
            return ",".join(str(item).strip() for item in value if str(item).strip())
        return str(value or "").strip()
    if kind == "boolean":
        return _coerce_import_bool_text(value)
    if kind == "json":
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=True)
        return str(value or "").strip()
    return str(value or "").strip()


def _has_template_string_list_values(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return any(str(item).strip() for item in value if item is not None)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return False
        try:
            parsed = json.loads(stripped)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return any(str(item).strip() for item in parsed if item is not None)
        return True
    return bool(value)


def _coerce_import_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "on"}:
            return True
        if lowered in {"false", "no", "0", "off"}:
            return False
    return None
