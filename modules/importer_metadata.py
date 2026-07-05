"""Per-library ``metadata_files`` handling for ``prepare_import_payload``.

Split out of ``modules.importer`` following the same pattern as
:mod:`modules.importer_collections` and :mod:`modules.importer_overlays`.

Unlike collections/overlays, ``metadata_files`` entries do not support
Quickstart-bundled ``default`` references or ``template_variables``.
Every entry is treated as a raw file reference and just written into
a JSON blob under ``libraries_data[lib_id-metadata_files]``.

Accepted entry shapes:

* ``{file: <path>}`` -- local file path
* ``{folder: <path>}`` -- local folder path
* ``{url: <http_url>}``
* ``{git: <github_slug_or_url>}``
* ``{repo: <config_repo_key>}``

Any other key (or missing/empty location) records an ``unmapped``
report entry and is skipped.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from modules.importer import ImportReport

_METADATA_ENTRY_TYPES: tuple[str, ...] = ("file", "folder", "git", "repo", "url")


def process_metadata_files(
    lib_id: str,
    lib_name: str,
    lib_cfg: dict,
    *,
    libraries_data: dict[str, Any],
    report: ImportReport,
) -> None:
    """Process ``lib_cfg['metadata_files']`` into libraries_data + report.

    A no-op when the library has no ``metadata_files`` key.  Records an
    unmapped report entry if the key is present but not a list.
    """
    metadata_files = lib_cfg.get("metadata_files")
    if metadata_files is None:
        return

    if not isinstance(metadata_files, list):
        report.add(
            "unmapped",
            f"libraries.{lib_name}.metadata_files",
            "Unsupported metadata_files format.",
        )
        return

    imported_metadata_files: list[dict[str, str]] = []
    for idx, entry in enumerate(metadata_files):
        parsed = _parse_metadata_entry(entry)
        if parsed is None:
            report.add(
                "unmapped",
                f"libraries.{lib_name}.metadata_files[{idx}]",
                "Only file, folder, url, git, and repo metadata files are supported.",
            )
            continue

        entry_type, location = parsed
        if not location:
            report.add(
                "unmapped",
                f"libraries.{lib_name}.metadata_files[{idx}]",
                "Metadata file location is required.",
            )
            continue

        imported_metadata_files.append({"type": entry_type, "location": location})
        report.add(
            "imported",
            f"libraries.{lib_name}.metadata_files[{idx}].{entry_type}",
        )

    if imported_metadata_files:
        libraries_data[f"{lib_id}-metadata_files"] = json.dumps(
            imported_metadata_files, ensure_ascii=True
        )
        report.add("imported", f"libraries.{lib_name}.metadata_files")


def _parse_metadata_entry(entry: Any) -> tuple[str, str] | None:
    """Return ``(entry_type, location)`` for a single metadata entry.

    Returns ``None`` when the entry is not a dict or contains no
    recognised location key.  ``location`` is stripped but not
    validated for non-emptiness -- the caller reports that separately
    to distinguish "no location key" from "location key with empty
    string" for report accuracy.
    """
    if not isinstance(entry, dict):
        return None
    for candidate in _METADATA_ENTRY_TYPES:
        if candidate in entry:
            return candidate, str(entry.get(candidate) or "").strip()
    return None
