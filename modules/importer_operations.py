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


def _first_valid_option(raw_value: Any, valid_options: set[str]) -> str | None:
    """Return the first valid option from a scalar or list-like value."""
    for item in _normalize_op_items(raw_value):
        candidate = str(item).strip()
        if candidate in valid_options:
            return candidate
    return None


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
    stripped_prefix = op_key.replace("_update", "_", 1)
    for key in toggle_keys:
        toggle_aliases[key] = key
        if key.startswith(f"{op_key}_"):
            toggle_aliases[key.replace(f"{op_key}_", "", 1)] = key
        if key.startswith(stripped_prefix):
            toggle_aliases[key.replace(stripped_prefix, "", 1)] = key

    def resolve_toggle_key(raw_key: str) -> str | None:
        return toggle_aliases.get(raw_key)

    source = None
    imported_any = False

    if isinstance(op_value, dict):
        for raw_key, raw_value in op_value.items():
            key = str(raw_key)
            if key == "source":
                candidate = _first_valid_option(raw_value, select_options)
                if candidate:
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


def handle_metadata_backup_operation(
    lib_id: str,
    lib_name: str,
    op_key: str,
    op_value: Any,
    *,
    libraries_data: dict[str, Any],
    report: ImportReport,
) -> tuple[bool, bool]:
    """Dispatch the ``metadata_backup`` operation into flat fields."""
    if op_key != "metadata_backup":
        return False, False
    if not isinstance(op_value, dict):
        report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}", "Unsupported metadata_backup format.")
        return True, False

    imported_any = False
    field_map = {
        "path": "metadata_backup_path",
        "exclude": "metadata_backup_exclude",
        "sync_tags": "sync_tags",
        "add_blank_entries": "add_blank_entries",
    }
    for raw_key, raw_value in op_value.items():
        key = str(raw_key)
        target = field_map.get(key)
        if not target:
            report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}.{key}")
            continue
        if key == "exclude":
            values = raw_value if isinstance(raw_value, list) else _normalize_op_items(raw_value)
            cleaned = [str(item).strip() for item in values if str(item).strip()]
            if cleaned:
                libraries_data[f"{lib_id}-attribute_{target}"] = _encode_json(cleaned)
                imported_any = True
        else:
            libraries_data[f"{lib_id}-attribute_{target}"] = raw_value
            imported_any = True
        report.add("imported", f"libraries.{lib_name}.operations.{op_key}.{key}")

    if imported_any:
        report.add("imported", f"libraries.{lib_name}.operations.{op_key}")
    else:
        report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}", "No importable values found.")
    return True, imported_any


_MASS_METADATA_DIRECT_ALIASES = {
    "original_title": "mass_original_title_update",
    "studio": "mass_studio_update",
    "originally_available": "mass_originally_available_update",
    "added_at": "mass_added_at_update",
}

_MASS_METADATA_RATING_ALIASES = {
    "audience": "mass_audience_rating_update",
    "critic": "mass_critic_rating_update",
    "user": "mass_user_rating_update",
    "episode_audience": "mass_episode_audience_rating_update",
    "episode_critic": "mass_episode_critic_rating_update",
    "episode_user": "mass_episode_user_rating_update",
}

_MASS_METADATA_IMAGE_ALIASES = {
    "poster": "mass_poster_update",
    "background": "mass_background_update",
    "logo": "mass_logo_update",
    "square_art": "mass_square_art_update",
    "squart_art": "mass_square_art_update",
}


def _mass_metadata_source(value: Any) -> Any:
    if isinstance(value, dict) and "source" in value:
        return value.get("source")
    return value


def _mass_metadata_dict_keys_as_sources(value: dict, ignored_keys: set[str]) -> list[str]:
    return [str(key) for key in value if str(key) not in ignored_keys]


def handle_mass_image_update_operation(
    lib_id: str,
    lib_name: str,
    op_key: str,
    op_value: Any,
    *,
    toggle_select_defs: dict,
    libraries_data: dict[str, Any],
    report: ImportReport,
) -> tuple[bool, bool]:
    """Dispatch Kometa's grouped ``mass_image_update`` compatibility op."""
    if op_key != "mass_image_update":
        return False, False
    if not isinstance(op_value, dict):
        report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}", "Unsupported mass_image_update format.")
        return True, False

    imported_any = False
    for image_key, image_value in op_value.items():
        old_key = _MASS_METADATA_IMAGE_ALIASES.get(str(image_key))
        if not old_key:
            report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}.{image_key}")
            continue
        _handled, imported = handle_toggle_select_operation(
            lib_id,
            lib_name,
            old_key,
            image_value,
            toggle_select_defs=toggle_select_defs,
            libraries_data=libraries_data,
            report=report,
        )
        imported_any = imported_any or imported

    if imported_any:
        report.add("imported", f"libraries.{lib_name}.operations.{op_key}")
    else:
        report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}", "No importable values found.")
    return True, imported_any


def handle_mass_metadata_update_operation(
    lib_id: str,
    lib_name: str,
    op_key: str,
    op_value: Any,
    *,
    mass_update_defs: dict,
    toggle_select_defs: dict,
    libraries_data: dict[str, Any],
    report: ImportReport,
) -> tuple[bool, bool]:
    """Dispatch grouped ``mass_metadata_update`` into legacy flat UI keys."""
    if op_key != "mass_metadata_update":
        return False, False
    if not isinstance(op_value, dict):
        report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}", "Unsupported mass_metadata_update format.")
        return True, False

    imported_any = False

    for new_key, old_key in _MASS_METADATA_DIRECT_ALIASES.items():
        if new_key not in op_value:
            continue
        _handled, imported = handle_mass_update_operation(
            lib_id,
            lib_name,
            old_key,
            _mass_metadata_source(op_value[new_key]),
            mass_update_defs=mass_update_defs,
            libraries_data=libraries_data,
            report=report,
        )
        imported_any = imported_any or imported
        if imported:
            report.add("imported", f"libraries.{lib_name}.operations.{op_key}.{new_key}")

    if "genre" in op_value:
        genre_value = op_value["genre"]
        if isinstance(genre_value, dict):
            if isinstance(genre_value.get("mappings"), dict) and genre_value["mappings"]:
                libraries_data[f"{lib_id}-attribute_genre_mapper"] = json.dumps(genre_value["mappings"], ensure_ascii=True)
                report.add("imported", f"libraries.{lib_name}.operations.{op_key}.genre.mappings")
                imported_any = True
            source_value = genre_value.get("source")
            if source_value is None:
                source_value = _mass_metadata_dict_keys_as_sources(genre_value, {"mappings", "schedule"})
        else:
            source_value = genre_value
        if source_value:
            _handled, imported = handle_mass_update_operation(
                lib_id,
                lib_name,
                "mass_genre_update",
                source_value,
                mass_update_defs=mass_update_defs,
                libraries_data=libraries_data,
                report=report,
            )
            imported_any = imported_any or imported
            if imported:
                report.add("imported", f"libraries.{lib_name}.operations.{op_key}.genre")

    if "content_rating" in op_value:
        rating_value = op_value["content_rating"]
        if isinstance(rating_value, dict):
            if isinstance(rating_value.get("mappings"), dict) and rating_value["mappings"]:
                libraries_data[f"{lib_id}-attribute_content_rating_mapper"] = json.dumps(rating_value["mappings"], ensure_ascii=True)
                report.add("imported", f"libraries.{lib_name}.operations.{op_key}.content_rating.mappings")
                imported_any = True
            source_value = rating_value.get("source")
            if source_value is None:
                source_value = _mass_metadata_dict_keys_as_sources(rating_value, {"mappings", "schedule"})
        else:
            source_value = rating_value
        if source_value:
            _handled, imported = handle_mass_update_operation(
                lib_id,
                lib_name,
                "mass_content_rating_update",
                source_value,
                mass_update_defs=mass_update_defs,
                libraries_data=libraries_data,
                report=report,
            )
            imported_any = imported_any or imported
            if imported:
                report.add("imported", f"libraries.{lib_name}.operations.{op_key}.content_rating")

    labels = op_value.get("labels")
    if labels is not None:
        label_value = labels.get("severity") if isinstance(labels, dict) else labels
        if label_value not in (None, ""):
            libraries_data[f"{lib_id}-attribute_mass_imdb_parental_labels"] = label_value
            report.add("imported", f"libraries.{lib_name}.operations.{op_key}.labels")
            imported_any = True

    collections = op_value.get("collections")
    if collections is not None:
        collection_mode = collections.get("mode") if isinstance(collections, dict) else collections
        if collection_mode not in (None, ""):
            libraries_data[f"{lib_id}-attribute_mass_collection_mode"] = collection_mode
            report.add("imported", f"libraries.{lib_name}.operations.{op_key}.collections")
            imported_any = True

    ratings = op_value.get("ratings")
    if isinstance(ratings, dict):
        for new_key, old_key in _MASS_METADATA_RATING_ALIASES.items():
            if new_key not in ratings:
                continue
            _handled, imported = handle_mass_update_operation(
                lib_id,
                lib_name,
                old_key,
                _mass_metadata_source(ratings[new_key]),
                mass_update_defs=mass_update_defs,
                libraries_data=libraries_data,
                report=report,
            )
            imported_any = imported_any or imported
            if imported:
                report.add("imported", f"libraries.{lib_name}.operations.{op_key}.ratings.{new_key}")
    elif ratings is not None:
        report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}.ratings", "Unsupported ratings format.")

    for new_key, old_key in _MASS_METADATA_IMAGE_ALIASES.items():
        if new_key not in op_value:
            continue
        _handled, imported = handle_toggle_select_operation(
            lib_id,
            lib_name,
            old_key,
            op_value[new_key],
            toggle_select_defs=toggle_select_defs,
            libraries_data=libraries_data,
            report=report,
        )
        imported_any = imported_any or imported
        if imported:
            report.add("imported", f"libraries.{lib_name}.operations.{op_key}.{new_key}")

    if "backup" in op_value:
        _handled, imported = handle_metadata_backup_operation(
            lib_id,
            lib_name,
            "metadata_backup",
            op_value["backup"],
            libraries_data=libraries_data,
            report=report,
        )
        imported_any = imported_any or imported
        if imported:
            report.add("imported", f"libraries.{lib_name}.operations.{op_key}.backup")

    known_keys = set(_MASS_METADATA_DIRECT_ALIASES) | {"genre", "content_rating", "labels", "collections", "ratings", "backup"} | set(_MASS_METADATA_IMAGE_ALIASES)
    for key in op_value:
        if str(key) not in known_keys and str(key) != "schedule":
            report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}.{key}", "Unsupported mass_metadata_update field.")

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

        handled, imported = handle_mass_metadata_update_operation(
            lib_id,
            lib_name,
            key,
            value,
            mass_update_defs=mass_update_defs,
            toggle_select_defs=toggle_select_defs,
            libraries_data=libraries_data,
            report=report,
        )
        if handled:
            imported_ops = imported_ops or imported
            continue

        handled, imported = handle_metadata_backup_operation(
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

        handled, imported = handle_mass_image_update_operation(
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
