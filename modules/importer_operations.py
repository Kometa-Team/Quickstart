"""Library-operation import handlers.

Split out of ``modules.importer.prepare_import_payload`` so the 237
lines of operation-dispatch logic can be reviewed in isolation from
the surrounding mega-function.

Each handler translates one entry from a library's ``operations:``
YAML block into the flat ``lib_id-attribute_*`` keys the DB expects
and records success / failure in the shared ``ImportReport``.

The handlers were nested closures inside ``prepare_import_payload``
that reached into the surrounding scope for:

* ``libraries_data`` -- the per-library flat dict being populated.
* ``report``         -- the ``ImportReport`` collecting mapped /
                        unmapped paths.
* ``*_defs``         -- the operation-type dispatch tables from
                        ``_build_attribute_sets``.

That closure state is now passed in as keyword-only arguments so the
handlers can live at module scope, be tested independently, and stop
inflating the mega-function.

Return convention (unchanged from the closures):

* ``(handled, imported)`` tuple.
* ``handled = True`` -- this handler recognised the op_key.  Caller
  should NOT try later handlers.
* ``handled = False`` -- op_key belongs to a different handler.
  Caller should keep dispatching.
* ``imported = True`` -- at least one importable value found.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from modules import helpers

if TYPE_CHECKING:
    from modules.importer import ImportReport


def _encode_json(values: list) -> str:
    """Compact JSON encoder used by the operation handlers."""
    return json.dumps(values, ensure_ascii=True)


def _clean_custom_value(value: Any) -> Any | None:
    """Normalize a single custom-value entry for mass-update operations.

    None/False collapse to None; numbers pass through; strings get
    stripped and only survive if non-empty.
    """
    if value is None or value is False:
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    return text if text else None


def _normalize_op_items(value: Any) -> list:
    """Coerce an operation's value into a uniform list for iteration."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def handle_mass_update_operation(
    lib_id: str,
    lib_name: str,
    op_key: str,
    op_value: Any,
    *,
    mass_update_defs: dict,
    libraries_data: dict[str, Any],
    report: ImportReport,
) -> tuple[bool, bool]:
    """Dispatch mass-update-style operation values into libraries_data.

    Mass-update operations combine a set of preset "source" toggles
    (``libraries_data[lib_id-attribute_op_key_source] = True``) with
    optional free-form custom strings (``..._custom`` / ``..._custom_string``).
    """
    definition = mass_update_defs.get(op_key)
    if not definition:
        return False, False

    sources = definition.get("sources", set())
    has_custom = definition.get("has_custom_string")
    custom_behavior = definition.get("custom_string_behavior") or "string"
    order: list[str] = []
    custom_values: list[Any] = []
    items = _normalize_op_items(op_value)

    for idx, item in enumerate(items):
        item_path = f"libraries.{lib_name}.operations.{op_key}[{idx}]" if isinstance(op_value, list) else f"libraries.{lib_name}.operations.{op_key}"
        if isinstance(item, list):
            for entry in item:
                custom_value = _clean_custom_value(entry)
                if custom_value is not None:
                    custom_values.append(custom_value)
            if has_custom and item:
                report.add("imported", item_path)
            else:
                report.add("unmapped", item_path, "Unsupported mass update list entry.")
            continue
        if isinstance(item, dict):
            report.add("unmapped", item_path, "Unsupported mass update format.")
            continue

        if isinstance(item, (int, float)):
            if has_custom:
                custom_values.append(item)
                report.add("imported", item_path)
            else:
                report.add("unmapped", item_path, "Custom values are not supported.")
            continue

        text = str(item).strip()
        if not text:
            continue
        if text in sources:
            if text not in order:
                order.append(text)
            libraries_data[f"{lib_id}-attribute_{op_key}_{text}"] = True
            report.add("imported", item_path)
        elif has_custom:
            custom_values.append(text)
            report.add("imported", item_path)
        else:
            report.add("unmapped", item_path, "Custom values are not supported.")

    if order:
        libraries_data[f"{lib_id}-attribute_{op_key}_order"] = _encode_json(order)

    if custom_values:
        if custom_behavior == "list":
            libraries_data[f"{lib_id}-attribute_{op_key}_custom"] = _encode_json(custom_values)
        else:
            libraries_data[f"{lib_id}-attribute_{op_key}_custom_string"] = _clean_custom_value(custom_values[0])
            if len(custom_values) > 1:
                libraries_data[f"{lib_id}-attribute_{op_key}_custom"] = _encode_json(custom_values[1:])

    if order or custom_values:
        report.add("imported", f"libraries.{lib_name}.operations.{op_key}")
        return True, True

    report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}", "No importable values found.")
    return True, False


def handle_toggle_select_operation(
    lib_id: str,
    lib_name: str,
    op_key: str,
    op_value: Any,
    *,
    toggle_select_defs: dict,
    libraries_data: dict[str, Any],
    report: ImportReport,
) -> tuple[bool, bool]:
    """Dispatch operations that pair a select_key with a set of toggle_keys.

    Handles dict, list, and bare-string YAML shapes for the same operation.
    """
    definition = toggle_select_defs.get(op_key)
    if not definition:
        return False, False

    select_key = definition.get("select_key")
    select_options = set(definition.get("select_options") or [])
    toggle_keys = set(definition.get("toggle_keys") or [])
    toggle_aliases = {}
    for key in toggle_keys:
        toggle_aliases[key] = key
        if key.startswith(f"{op_key}_"):
            toggle_aliases[key.replace(f"{op_key}_", "", 1)] = key

    def resolve_toggle_key(raw_key: str) -> str | None:
        return toggle_aliases.get(raw_key)

    source = None
    imported_any = False

    if isinstance(op_value, dict):
        for raw_key, raw_value in op_value.items():
            key = str(raw_key)
            if key == "source":
                candidate = str(raw_value).strip()
                if candidate in select_options:
                    source = candidate
                    report.add("imported", f"libraries.{lib_name}.operations.{op_key}.source")
                    imported_any = True
                else:
                    report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}.source")
                continue
            resolved = resolve_toggle_key(key)
            if resolved:
                if helpers.booler(raw_value):
                    libraries_data[f"{lib_id}-attribute_{resolved}"] = True
                report.add("imported", f"libraries.{lib_name}.operations.{op_key}.{key}")
                imported_any = True
            else:
                report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}.{key}")
        if source and select_key:
            libraries_data[f"{lib_id}-attribute_{select_key}"] = source
        return True, imported_any

    if isinstance(op_value, list):
        for idx, item in enumerate(op_value):
            item_path = f"libraries.{lib_name}.operations.{op_key}[{idx}]"
            if isinstance(item, str):
                text = item.strip()
                if text in select_options:
                    source = text
                    report.add("imported", item_path)
                    imported_any = True
                    continue
                resolved = resolve_toggle_key(text)
                if resolved:
                    libraries_data[f"{lib_id}-attribute_{resolved}"] = True
                    report.add("imported", item_path)
                    imported_any = True
                    continue
            report.add("unmapped", item_path, "Unsupported option.")
        if source and select_key:
            libraries_data[f"{lib_id}-attribute_{select_key}"] = source
        if imported_any:
            report.add("imported", f"libraries.{lib_name}.operations.{op_key}")
        return True, imported_any

    if isinstance(op_value, str):
        candidate = op_value.strip()
        if candidate in select_options and select_key:
            libraries_data[f"{lib_id}-attribute_{select_key}"] = candidate
            report.add("imported", f"libraries.{lib_name}.operations.{op_key}")
            return True, True
        else:
            report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}", "Unsupported option.")
            return True, False

    report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}", "Unsupported operation format.")
    return True, False


def handle_delete_collections_operation(
    lib_id: str,
    lib_name: str,
    op_key: str,
    op_value: Any,
    *,
    libraries_data: dict[str, Any],
    report: ImportReport,
) -> tuple[bool, bool]:
    """Dispatch the delete_collections operation.

    Unlike the other handlers this one only claims a single op_key
    ("delete_collections") -- for anything else it returns
    (False, False) so the caller keeps dispatching.
    """
    if op_key != "delete_collections":
        return False, False
    if not isinstance(op_value, dict):
        report.add(
            "unmapped",
            f"libraries.{lib_name}.operations.{op_key}",
            "Unsupported delete_collections format.",
        )
        return True, False

    mapping = {
        "configured": "delete_collections_configured",
        "managed": "delete_collections_managed",
        "ignore_empty_smart_collections": "delete_collections_ignore_empty_smart_collections",
        "less": "delete_collections_less",
    }
    imported_any = False

    for raw_key, raw_value in op_value.items():
        key = str(raw_key)
        target = mapping.get(key)
        if not target:
            report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}.{key}")
            continue
        if key == "less":
            try:
                if raw_value is None or raw_value == "":
                    report.add(
                        "unmapped",
                        f"libraries.{lib_name}.operations.{op_key}.{key}",
                        "Missing numeric value.",
                    )
                    continue
                libraries_data[f"{lib_id}-attribute_{target}"] = int(raw_value)
                report.add("imported", f"libraries.{lib_name}.operations.{op_key}.{key}")
                imported_any = True
            except Exception:
                report.add(
                    "unmapped",
                    f"libraries.{lib_name}.operations.{op_key}.{key}",
                    "Invalid numeric value.",
                )
            continue
        bool_value = None
        if isinstance(raw_value, bool):
            bool_value = raw_value
        elif isinstance(raw_value, str):
            lowered = raw_value.strip().lower()
            if lowered in {"true", "yes", "1"}:
                bool_value = True
            elif lowered in {"false", "no", "0"}:
                bool_value = False
        if bool_value is None:
            report.add(
                "unmapped",
                f"libraries.{lib_name}.operations.{op_key}.{key}",
                "Invalid boolean value.",
            )
            continue
        libraries_data[f"{lib_id}-attribute_{target}"] = bool_value
        report.add("imported", f"libraries.{lib_name}.operations.{op_key}.{key}")
        imported_any = True

    if imported_any:
        report.add("imported", f"libraries.{lib_name}.operations.{op_key}")
    else:
        report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}", "No importable values found.")
    return True, imported_any


def process_operations_block(
    lib_id: str,
    lib_name: str,
    lib_cfg: dict,
    *,
    libraries_data: dict[str, Any],
    report: ImportReport,
    simple_attrs: set[str],
    mass_update_defs: dict[str, dict],
    toggle_select_defs: dict[str, dict],
) -> None:
    """Process ``lib_cfg['operations']`` into libraries_data + report.

    Dispatches each operation key to the appropriate handler:

    1. **Simple scalar attributes** (``simple_attrs``) get written
       directly as ``libraries_data[lib_id-attribute_<key>]``.
    2. **``delete_collections`` operation** -- handled specially via
       :func:`handle_delete_collections_operation`.
    3. **Mass-update operations** (``mass_update_defs``) -- dispatched
       to :func:`handle_mass_update_operation`.
    4. **Toggle/select operations** (``toggle_select_defs``) --
       dispatched to :func:`handle_toggle_select_operation`.
    5. Anything else records an ``unmapped`` "Complex operation" note.

    A no-op when the library has no ``operations`` key.  Records an
    unmapped report entry if the key is present but not a dict.
    Emits a top-level ``libraries.<name>.operations`` imported entry
    when at least one operation inside was importable.
    """
    operations = lib_cfg.get("operations")
    if operations is None:
        return

    if not isinstance(operations, dict):
        report.add(
            "unmapped",
            f"libraries.{lib_name}.operations",
            "Unsupported operations format.",
        )
        return

    imported_ops = False
    for key, value in operations.items():
        if key in simple_attrs and not isinstance(value, (dict, list)):
            libraries_data[f"{lib_id}-attribute_{key}"] = value
            report.add("imported", f"libraries.{lib_name}.operations.{key}")
            imported_ops = True
            continue

        handled, imported = handle_delete_collections_operation(
            lib_id,
            lib_name,
            key,
            value,
            libraries_data=libraries_data,
            report=report,
        )
        if handled:
            imported_ops = imported_ops or imported
            continue

        handled, imported = handle_mass_update_operation(
            lib_id,
            lib_name,
            key,
            value,
            mass_update_defs=mass_update_defs,
            libraries_data=libraries_data,
            report=report,
        )
        if handled:
            imported_ops = imported_ops or imported
            continue

        handled, imported = handle_toggle_select_operation(
            lib_id,
            lib_name,
            key,
            value,
            toggle_select_defs=toggle_select_defs,
            libraries_data=libraries_data,
            report=report,
        )
        if handled:
            imported_ops = imported_ops or imported
            continue

        report.add(
            "unmapped",
            f"libraries.{lib_name}.operations.{key}",
            "Complex operation not supported for import.",
        )

    if imported_ops:
        report.add("imported", f"libraries.{lib_name}.operations")
