"""Playlist section parsing for ``prepare_import_payload``.

Split out of ``modules.importer`` so the ~100-line playlist parsing
block can live next to its own supporting constants (the two
``PLAYLIST_*_IMPORT_FIELDS`` dispatch maps) instead of drowning in
the middle of the mega function.

The parser reads ``config_data["playlist_files"]`` and produces a
:class:`PlaylistImportState` -- four collections that downstream
library-processing code needs to know about:

* ``libraries``                     -- library names that appear in
                                       any playlist entry's
                                       template_variables.libraries.
* ``file_entries``                  -- entries that point at a
                                       file/url/git/repo location
                                       instead of a template block.
* ``template_field_values``         -- flat playlist-scoped template
                                       overrides keyed by field name.
* ``keyed_template_field_values``   -- prefix->suffix->value nested
                                       overrides for keyed fields
                                       (``use_*``, ``name_*``, ...).

Report annotations for imported / unmapped playlist paths are added
in-place onto the caller-supplied ``ImportReport``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from modules.importer_value_coercion import (
    _coerce_import_bool,
    _coerce_import_int,
    _coerce_import_string_list,
    _serialize_playlist_import_value,
)

if TYPE_CHECKING:
    from modules.importer import ImportReport


PLAYLIST_SHARED_IMPORT_FIELDS: dict[str, str] = {
    "sync_to_users": "string_list",
    "exclude_users": "string_list",
    "delete_playlist": "boolean",
    "ignore_ids": "string_list",
    "ignore_imdb_ids": "string_list",
    "item_radarr_tag": "string_list",
    "item_sonarr_tag": "string_list",
    "radarr_add_missing": "boolean",
    "radarr_folder": "string",
    "radarr_tag": "string_list",
    "sonarr_add_missing": "boolean",
    "sonarr_folder": "string",
    "sonarr_tag": "string_list",
    "trakt_list": "string_list",
    "imdb_list": "string_list",
    "mdblist_list": "string_list",
}

PLAYLIST_KEYED_IMPORT_FIELDS: dict[str, str] = {
    "use_": "boolean",
    "name_": "string",
    "summary_": "string",
    "url_poster_": "string",
    "delete_playlist_": "boolean",
    "exclude_users_": "string_list",
    "exclude_user_": "string_list",
    "imdb_list_": "string_list",
    "item_radarr_tag_": "string_list",
    "item_sonarr_tag_": "string_list",
    "mdblist_list_": "string_list",
    "radarr_add_missing_": "boolean",
    "radarr_folder_": "string",
    "radarr_tag_": "string_list",
    "sonarr_add_missing_": "boolean",
    "sonarr_folder_": "string",
    "sonarr_tag_": "string_list",
    "sync_to_users_": "string_list",
    "trakt_list_": "string_list",
}


@dataclass
class PlaylistImportState:
    """Aggregate output of :func:`parse_playlist_config`."""

    libraries: set[str] = field(default_factory=set)
    file_entries: list[dict[str, str]] = field(default_factory=list)
    template_field_values: dict[str, Any] = field(default_factory=dict)
    keyed_template_field_values: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def has_any_data(self) -> bool:
        """True if the parser found at least one usable playlist entry."""
        return bool(self.libraries or self.file_entries)


def parse_playlist_config(config_data: dict, report: ImportReport) -> PlaylistImportState:
    """Read ``config_data['playlist_files']`` into a :class:`PlaylistImportState`.

    Mutates ``report`` in place to record imported / unmapped playlist
    YAML paths.  Returns an empty state (with the same object identity
    for each field) if no ``playlist_files`` key exists.
    """
    state = PlaylistImportState()
    playlist_payload = config_data.get("playlist_files")
    if playlist_payload is None:
        return state

    if not isinstance(playlist_payload, list):
        report.add("unmapped", "playlist_files", "Unsupported playlist_files format.")
        return state

    for idx, entry in enumerate(playlist_payload):
        if not isinstance(entry, dict):
            report.add("unmapped", f"playlist_files[{idx}]", "Unsupported playlist entry format.")
            continue

        # -- File-reference entry (file/url/git/repo) short-circuits --
        raw_entry_type = None
        raw_entry_location = None
        for candidate in ("file", "url", "git", "repo"):
            location = entry.get(candidate)
            if location:
                raw_entry_type = candidate
                raw_entry_location = str(location).strip()
                break
        if raw_entry_type and raw_entry_location:
            state.file_entries.append({"type": raw_entry_type, "location": raw_entry_location})
            report.add("imported", f"playlist_files[{idx}]")
            report.add("imported", f"playlist_files[{idx}].{raw_entry_type}")
            if entry.get("template_variables") not in (None, {}):
                report.add(
                    "unmapped",
                    f"playlist_files[{idx}].template_variables",
                    "Template variables for direct playlist file entries are not supported in Quickstart.",
                )
            continue

        # -- Template-based entry: needs template_variables.libraries --
        tv = entry.get("template_variables", {})
        if not isinstance(tv, dict):
            report.add(
                "unmapped",
                f"playlist_files[{idx}].template_variables",
                "Unsupported template_variables format.",
            )
            continue
        libs = tv.get("libraries")
        entry_libs = _coerce_import_string_list(libs)
        if not entry_libs:
            report.add(
                "unmapped",
                f"playlist_files[{idx}].template_variables.libraries",
                "Missing playlist library entries.",
            )
            continue

        state.libraries.update(entry_libs)
        report.add("imported", f"playlist_files[{idx}]")

        default_value = entry.get("default")
        if default_value == "playlist":
            report.add("imported", f"playlist_files[{idx}].default")
        elif default_value is not None:
            report.add("unmapped", f"playlist_files[{idx}].default", "Unsupported playlist default.")

        report.add("imported", f"playlist_files[{idx}].template_variables")
        report.add("imported", f"playlist_files[{idx}].template_variables.libraries")
        for lib_idx in range(len(entry_libs)):
            report.add("imported", f"playlist_files[{idx}].template_variables.libraries[{lib_idx}]")

        for key, value in tv.items():
            if key == "libraries":
                continue

            # Fold legacy singular aliases onto the plural canonical form.
            if key == "exclude_user":
                key = "exclude_users"
            if key == "exclude_user_":
                key = "exclude_users_"

            if key in PLAYLIST_SHARED_IMPORT_FIELDS:
                value_kind = PLAYLIST_SHARED_IMPORT_FIELDS[key]
                if value_kind == "boolean":
                    normalized_value = _coerce_import_bool(value)
                elif value_kind == "integer":
                    normalized_value = _coerce_import_int(value)
                elif value_kind == "string_list":
                    values = _coerce_import_string_list(value)
                    normalized_value = values if values else None
                else:
                    text = str(value).strip() if value is not None else ""
                    normalized_value = text or None

                if normalized_value is None:
                    report.add(
                        "unmapped",
                        f"playlist_files[{idx}].template_variables.{key}",
                        "Unsupported playlist template variable value.",
                    )
                    continue

                state.template_field_values[key] = normalized_value
                report.add("imported", f"playlist_files[{idx}].template_variables.{key}")
                continue

            matched_prefix = next(
                (prefix for prefix in PLAYLIST_KEYED_IMPORT_FIELDS if key.startswith(prefix)),
                None,
            )
            if matched_prefix:
                suffix = str(key[len(matched_prefix) :] or "").strip()
                if not suffix:
                    report.add(
                        "unmapped",
                        f"playlist_files[{idx}].template_variables.{key}",
                        "Missing playlist key suffix.",
                    )
                    continue
                serialized_value = _serialize_playlist_import_value(
                    PLAYLIST_KEYED_IMPORT_FIELDS[matched_prefix],
                    value,
                )
                if serialized_value is None:
                    report.add(
                        "unmapped",
                        f"playlist_files[{idx}].template_variables.{key}",
                        "Unsupported playlist keyed template variable value.",
                    )
                    continue
                state.keyed_template_field_values.setdefault(matched_prefix, {})[suffix] = serialized_value
                report.add("imported", f"playlist_files[{idx}].template_variables.{key}")
                continue

            report.add(
                "unmapped",
                f"playlist_files[{idx}].template_variables.{key}",
                "Playlist template variable not available in Quickstart.",
            )

    if state.has_any_data:
        report.add("imported", "playlist_files")

    return state
