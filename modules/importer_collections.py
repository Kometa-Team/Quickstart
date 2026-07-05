"""Per-library ``collection_files`` handling for ``prepare_import_payload``.

Split out of ``modules.importer`` so the ~120-line collection-file
processing block for each library lives next to the constants and
helpers it uses, instead of buried inside the mega function.

Each library entry in the YAML config can carry a ``collection_files``
list.  Entries in that list can be either:

* **File references** -- ``{file: ...}`` / ``{url: ...}`` / ``{git: ...}``
  / ``{repo: ...}`` / ``{folder: ...}`` mappings that point at an
  external collection definition file.  These are collected into a
  JSON blob under ``libraries_data[lib_id-collection_files]``.

* **Default references** -- ``{default: <collection_id_or_alias>}``
  mappings (or bare strings) that select one of the Quickstart-bundled
  collection templates.  Each resolves to a specific
  ``libraries_data[lib_id-<collection_id>] = True`` flag plus optional
  ``template_variables`` overrides written to
  ``libraries_data[lib_id-template_collection_<clean_id>_<key>]``.

Template-variable overrides support:

* Flat overrides (top-level keys that appear in the collection's
  ``template_variables`` schema).
* Nested ``data.*`` overrides, promoted to ``data_*`` flat keys
  when the schema allows them.
* Dynamic-child mappings (e.g. ``ratings_<suffix>``) that get
  collected into a single JSON blob per parent field.
* Include/exclude "both set" warning (Kometa allows it, wiki says
  don't) surfaced as a ``skipped`` report line.

Report annotations are added in place onto the caller-supplied
``ImportReport``; ``libraries_data`` is mutated in place.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from modules.importer_library_types import _resolve_collection_id
from modules.importer_value_coercion import (
    _collect_dynamic_child_field_specs,
    _collect_template_keys,
    _has_template_string_list_values,
    _serialize_dynamic_child_mapping_value,
)

if TYPE_CHECKING:
    from modules.importer import ImportReport


def process_collection_files(
    lib_id: str,
    lib_name: str,
    lib_cfg: dict,
    *,
    libraries_data: dict[str, Any],
    report: ImportReport,
    collection_by_id: dict[str, dict],
    collection_by_alias: dict[str, str],
) -> None:
    """Process ``lib_cfg['collection_files']`` into libraries_data + report.

    A no-op when the library has no ``collection_files`` key.  When
    the key is present but not a list, records an unmapped report entry.
    """
    collection_files = lib_cfg.get("collection_files")
    if collection_files is None:
        return

    if not isinstance(collection_files, list):
        report.add(
            "unmapped",
            f"libraries.{lib_name}.collection_files",
            "Unsupported collection_files format.",
        )
        return

    imported_collection_files: list[dict[str, str]] = []
    for idx, entry in enumerate(collection_files):
        _process_single_collection_entry(
            idx,
            entry,
            lib_id=lib_id,
            lib_name=lib_name,
            libraries_data=libraries_data,
            report=report,
            collection_by_id=collection_by_id,
            collection_by_alias=collection_by_alias,
            imported_collection_files=imported_collection_files,
        )

    if imported_collection_files:
        libraries_data[f"{lib_id}-collection_files"] = json.dumps(imported_collection_files, ensure_ascii=True)
        report.add("imported", f"libraries.{lib_name}.collection_files")


def _process_single_collection_entry(
    idx: int,
    entry: Any,
    *,
    lib_id: str,
    lib_name: str,
    libraries_data: dict[str, Any],
    report: ImportReport,
    collection_by_id: dict[str, dict],
    collection_by_alias: dict[str, str],
    imported_collection_files: list[dict[str, str]],
) -> None:
    """Dispatch a single collection_files[] entry.

    Populates ``imported_collection_files`` for file-ref entries and
    writes into ``libraries_data`` for default-based entries.
    """
    default_value: Any = None
    template_values: Any = None
    raw_entry_type: str | None = None
    raw_entry_location: str | None = None

    if isinstance(entry, dict):
        default_value = entry.get("default")
        template_values = entry.get("template_variables")
        for candidate in ("file", "folder", "url", "git", "repo"):
            location = entry.get(candidate)
            if location:
                raw_entry_type = candidate
                raw_entry_location = str(location)
                break
    elif isinstance(entry, str):
        default_value = entry

    if raw_entry_type and raw_entry_location:
        imported_collection_files.append({"type": raw_entry_type, "location": raw_entry_location})
        report.add(
            "imported",
            f"libraries.{lib_name}.collection_files[{idx}].{raw_entry_type}",
        )
        return

    if not default_value:
        report.add(
            "unmapped",
            f"libraries.{lib_name}.collection_files[{idx}]",
            "Missing default.",
        )
        return

    raw_default = str(default_value)
    collection_id = _resolve_collection_id(raw_default, collection_by_id, collection_by_alias)
    if not collection_id or collection_id not in collection_by_id:
        report.add(
            "unmapped",
            f"libraries.{lib_name}.collection_files[{idx}].default",
            "Collection not found in Quickstart.",
        )
        return

    libraries_data[f"{lib_id}-{collection_id}"] = True
    report.add(
        "imported",
        f"libraries.{lib_name}.collection_files[{idx}].default",
    )

    if isinstance(template_values, dict):
        _apply_collection_template_variables(
            idx,
            collection_id,
            template_values,
            lib_id=lib_id,
            lib_name=lib_name,
            libraries_data=libraries_data,
            report=report,
            collection_by_id=collection_by_id,
        )


def _apply_collection_template_variables(
    idx: int,
    collection_id: str,
    template_values: dict,
    *,
    lib_id: str,
    lib_name: str,
    libraries_data: dict[str, Any],
    report: ImportReport,
    collection_by_id: dict[str, dict],
) -> None:
    """Write template_variables overrides for one collection entry.

    Handles data-block promotion, include/exclude "both set" warning,
    schema-matching flat overrides, and dynamic-child prefix mappings.
    """
    allowed = _collect_template_keys(collection_by_id[collection_id].get("template_variables"))
    dynamic_child_fields = _collect_dynamic_child_field_specs(collection_by_id[collection_id].get("template_variables"))
    clean_id = collection_id.replace("collection_", "", 1)

    expanded_template_values = dict(template_values)
    data_block = expanded_template_values.get("data")
    data_reported: set = set()
    pending_dynamic_child_maps: dict[str, dict[str, str]] = {}

    # -- Promote data.<subkey> to data_<subkey> when the schema allows it.
    if isinstance(data_block, dict):
        for subkey, subval in data_block.items():
            flat_key = f"data_{subkey}"
            if flat_key in allowed and flat_key not in expanded_template_values:
                expanded_template_values[flat_key] = subval
            if flat_key in allowed:
                report.add(
                    "imported",
                    f"libraries.{lib_name}.collection_files[{idx}].template_variables.data.{subkey}",
                )
                data_reported.add(subkey)
        if "data" in expanded_template_values and "data" not in allowed:
            expanded_template_values.pop("data", None)
        if data_reported:
            report.add(
                "imported",
                f"libraries.{lib_name}.collection_files[{idx}].template_variables.data",
            )

    # -- Warn on the include+exclude combo (Kometa allows, wiki says no).
    if _has_template_string_list_values(expanded_template_values.get("include")) and _has_template_string_list_values(expanded_template_values.get("exclude")):
        report.add(
            "skipped",
            f"libraries.{lib_name}.collection_files[{idx}].template_variables.include_exclude_warning",
            "Warning - include and exclude were both imported. Kometa code allows this, but the wiki says not to combine them.",
        )

    # -- Emit each override into libraries_data if the schema allows it.
    for key, value in expanded_template_values.items():
        if key in allowed:
            child_name = f"{lib_id}-template_collection_{clean_id}_{key}"
            if isinstance(value, list):
                libraries_data[child_name] = json.dumps(value, ensure_ascii=True)
            else:
                libraries_data[child_name] = value
            report.add(
                "imported",
                f"libraries.{lib_name}.collection_files[{idx}].template_variables.{key}",
            )
        else:
            matched_dynamic_child = next(
                (spec for spec in dynamic_child_fields if key.startswith(spec["child_prefix"]) and key != spec["child_prefix"]),
                None,
            )
            if matched_dynamic_child:
                suffix = key[len(matched_dynamic_child["child_prefix"]) :].strip()
                serialized_value = _serialize_dynamic_child_mapping_value(
                    value,
                    matched_dynamic_child["value_kind"],
                )
                if suffix and serialized_value:
                    pending_dynamic_child_maps.setdefault(
                        matched_dynamic_child["field_key"],
                        {},
                    )[suffix] = serialized_value
                    report.add(
                        "imported",
                        f"libraries.{lib_name}.collection_files[{idx}].template_variables.{key}",
                    )
                    continue
            report.add(
                "unmapped",
                f"libraries.{lib_name}.collection_files[{idx}].template_variables.{key}",
                "Template variable not available in Quickstart.",
            )

    # -- Collapse any accumulated dynamic-child maps into JSON blobs.
    for field_key, field_map in pending_dynamic_child_maps.items():
        if not field_map:
            continue
        libraries_data[f"{lib_id}-template_collection_{clean_id}_{field_key}"] = json.dumps(field_map, ensure_ascii=True)
