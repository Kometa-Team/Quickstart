"""Assemble the ``libraries:`` YAML block for the emitted Kometa config.

Extracted from ``modules.output``.

This module owns the biggest single function in the output pipeline:
:func:`build_libraries_section` walks selected movie and show
libraries in a deterministic order and, for each one, composes a
per-library entry dict from ~15 different builders (settings,
operations, collections, overlays, templates, top-level fields, ...).

Every per-library builder lives in :mod:`modules.output_library_ops`
so this module is a thin orchestrator that:

1. Sorts libraries deterministically (:func:`_sorted_library_items`).
2. Loops movies (A->Z by display name), then shows.
3. For each library, delegates to :func:`_add_library_entry` which
   composes the entry using the extracted builders.

The full 16-slot signature accepts each grouped per-kind dict as a
keyword argument (all default to empty ``{}``).  ``build_config``
passes everything from a :class:`LibrariesBundle`; tests typically
supply only one or two slots to isolate a specific builder path.
"""

from __future__ import annotations

import io

from flask import current_app as app
from ruamel.yaml import YAML

from modules import helpers
from modules.output_collections import _TEMPLATE_VARIABLE_COMMENTS_KEY
from modules.output_collections import build_collection_files
from modules.output_file_entries import _parse_metadata_file_entries
from modules.output_library_ops import (
    build_delete_collections_operation,
    build_grouped_mass_update_operations,
    build_library_operations,
    build_library_settings,
    build_mass_metadata_update_operation,
    build_metadata_backup_operation,
    build_service_overrides,
    build_template_variables,
    build_top_level_fields,
)
from modules.output_overlay_builder import build_overlay_files_for_library
from modules.output_reorder import reorder_library_section


def _sorted_library_items(libraries):
    """Return deterministic library ordering by display name, then key.

    Case-insensitive on both.  Non-dict input yields an empty list --
    matches ``build_config``'s guard that libraries may legitimately
    be missing.
    """
    if not isinstance(libraries, dict):
        return []
    return sorted(
        libraries.items(),
        key=lambda item: (str(item[1]).casefold(), str(item[0]).casefold()),
    )


def build_libraries_section(
    movie_libraries=None,
    show_libraries=None,
    movie_collections=None,
    show_collections=None,
    movie_collection_files=None,
    show_collection_files=None,
    movie_overlays=None,
    show_overlays=None,
    movie_attributes=None,
    show_attributes=None,
    movie_metadata_files=None,
    show_metadata_files=None,
    movie_templates=None,
    show_templates=None,
    movie_top_level=None,
    show_top_level=None,
):
    """Build the ``libraries:`` YAML block from per-kind grouped dicts.

    All 16 arguments are optional and default to an empty dict when
    omitted -- ``build_config`` passes everything; tests typically
    populate only one or two slots.  Passing ``None`` is treated as an
    explicit empty dict so callers can rely on the same defaults.
    """
    # Coerce None -> {} for all 16 slots so downstream code can rely
    # on dict semantics without guarding at every .get().
    movie_libraries = movie_libraries or {}
    show_libraries = show_libraries or {}
    movie_collections = movie_collections or {}
    show_collections = show_collections or {}
    movie_collection_files = movie_collection_files or {}
    show_collection_files = show_collection_files or {}
    movie_overlays = movie_overlays or {}
    show_overlays = show_overlays or {}
    movie_attributes = movie_attributes or {}
    show_attributes = show_attributes or {}
    movie_metadata_files = movie_metadata_files or {}
    show_metadata_files = show_metadata_files or {}
    movie_templates = movie_templates or {}
    show_templates = show_templates or {}
    movie_top_level = movie_top_level or {}
    show_top_level = show_top_level or {}

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
        """Process a single library and add its valid data to the output.

        Composes an entry dict from ~15 per-library builders, all of
        which live in :mod:`modules.output_library_ops`.  Uses closures
        for the both-kinds ``*_collection_files`` and
        ``*_metadata_files`` maps because they're read for both movie
        and show loops -- passing them explicitly would balloon the
        signature to 12 args.
        """
        entry = {}
        lib_id = helpers.extract_library_name(library_key)
        debug = app.config["QS_DEBUG"]

        if debug:
            helpers.ts_log(f"Processing Library: {library_key} -> {library_name}", level="DEBUG")

        # Library Settings + Operations attributes
        operations = {}
        attr_group = attributes.get(lib_id, {})
        library_settings = build_library_settings(attr_group, library_type, lib_id)
        operations.update(build_library_operations(attr_group, library_type, lib_id))
        service_name, service_overrides = build_service_overrides(attr_group, library_type, lib_id)

        delete_collections = build_delete_collections_operation(attr_group, library_type, lib_id)
        if delete_collections:
            operations["delete_collections"] = delete_collections

        if library_settings:
            entry["settings"] = library_settings
        if service_overrides:
            entry[service_name] = service_overrides
        if operations:
            entry["operations"] = operations

        # Collections
        collection_files, has_collectionless = build_collection_files(
            library_key,
            library_type,
            collections,
            templates,
            movie_collection_files,
            show_collection_files,
            debug=debug,
        )
        if collection_files:
            entry["collection_files"] = collection_files

        # Overlays
        collection_key = helpers.extract_library_name(library_key)
        if collection_key:
            overlay_files = build_overlay_files_for_library(library_key, library_type, overlays)
            if overlay_files:
                entry["overlay_files"] = overlay_files

        # Metadata files
        metadata_group = (
            movie_metadata_files.get(helpers.extract_library_name(library_key), {})
            if library_type == "mov"
            else show_metadata_files.get(helpers.extract_library_name(library_key), {})
        )
        library_prefix = helpers.strip_library_suffix(library_key)
        metadata_entries = _parse_metadata_file_entries(metadata_group.get(f"{library_prefix}-metadata_files"))
        if metadata_entries:
            entry["metadata_files"] = metadata_entries

        # Template variables
        template_variables = build_template_variables(templates, library_type, library_key, has_collectionless)
        template_variable_comments = template_variables.pop(_TEMPLATE_VARIABLE_COMMENTS_KEY, None) if isinstance(template_variables, dict) else None
        entry["template_variables"] = template_variables
        if template_variable_comments:
            entry[_TEMPLATE_VARIABLE_COMMENTS_KEY] = template_variable_comments

        # Grouped mass metadata output.  Quickstart's DB/UI still stores
        # these as flat operation fields, matching Kometa's parsed runtime
        # fields, but final YAML should use the canonical grouped key.
        mass_metadata = build_mass_metadata_update_operation(attr_group, library_type, lib_id)
        if mass_metadata:
            operations["mass_metadata_update"] = mass_metadata

        operations.update(build_grouped_mass_update_operations(attr_group, library_type, lib_id, include_mass_metadata_legacy=False))

        backup = build_metadata_backup_operation(attr_group, library_type, lib_id)
        if backup and not mass_metadata:
            operations["metadata_backup"] = backup

        # Top-level fields (Remove/Reset Overlays, etc.)
        top_group = top_level.get(lib_id, {})
        entry.update(build_top_level_fields(top_group, library_type, lib_id))

        if debug:
            helpers.ts_log(f"Top Level for {lib_id}: {top_group}", level="DEBUG")

        if operations:
            entry["operations"] = operations

        if debug:
            helpers.ts_log(f"Entry for {library_name}: {entry}", level="DEBUG")

        libraries_section[library_name] = reorder_library_section(entry)

    # Movie libraries (A->Z by display name, deterministic on key ties)
    for lk, ln in _sorted_library_items(movie_libraries):
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

    # Show libraries
    for lk, ln in _sorted_library_items(show_libraries):
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
        helpers.ts_log("Generated YAML Output:\n", level="DEBUG")
        buf = io.BytesIO()
        YAML().dump({"libraries": libraries_section}, buf)
        helpers.ts_log(buf.getvalue().decode("utf-8"))

    return {"libraries": libraries_section}
