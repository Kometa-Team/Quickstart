"""Per-library service-override (radarr / sonarr) handling.

Split out of ``modules.importer`` following the same pattern as the
other per-library sub-handlers.  Kometa lets each library override
Radarr / Sonarr settings via ``libraries.<name>.radarr:`` and
``libraries.<name>.sonarr:`` blocks -- Quickstart imports a
whitelisted subset of those keys into per-library
``lib_id-attribute_<service>_<key>`` DB entries.

Key features preserved from the inline block:

* **Library-type gate**: Radarr overrides are rejected on non-movie
  libraries; Sonarr overrides are rejected on non-show libraries.
* **Whitelisted keys only**: :data:`LIBRARY_RADARR_IMPORT_FIELDS` and
  :data:`LIBRARY_SONARR_IMPORT_FIELDS` define which keys are importable
  and their expected type (``"string"`` or ``"bool"``).
* **String coercion**: bool fields serialize as the string ``"true"``
  or ``"false"`` (matching the DB format the form uses), non-bool
  fields get ``str(...).strip()``.
* **Empty string rejection**: whitespace-only overrides are recorded
  as unmapped rather than silently written.

The two field-map dicts are re-exported from ``modules.importer``
because external tooling might import them by name; keeping the
canonical definition in this module means ``importer`` re-imports
them rather than duplicating.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from modules.importer_value_coercion import _coerce_import_bool

if TYPE_CHECKING:
    from modules.importer import ImportReport


LIBRARY_RADARR_IMPORT_FIELDS: dict[str, str] = {
    "url": "string",
    "token": "string",
    "root_folder_path": "string",
    "quality_profile": "string",
    "availability": "string",
    "tag": "string",
    "monitor": "bool",
    "search": "bool",
    "add_missing": "bool",
    "add_existing": "bool",
    "upgrade_existing": "bool",
    "monitor_existing": "bool",
    "ignore_cache": "bool",
    "radarr_path": "string",
    "plex_path": "string",
}

LIBRARY_SONARR_IMPORT_FIELDS: dict[str, str] = {
    "url": "string",
    "token": "string",
    "root_folder_path": "string",
    "quality_profile": "string",
    "language_profile": "string",
    "series_type": "string",
    "season_folder": "bool",
    "monitor": "string",
    "tag": "string",
    "search": "bool",
    "cutoff_search": "bool",
    "add_missing": "bool",
    "add_existing": "bool",
    "upgrade_existing": "bool",
    "monitor_existing": "bool",
    "ignore_cache": "bool",
    "sonarr_path": "string",
    "plex_path": "string",
}


# lib_id prefix -> service name mapping.  The lib_id has the shape
# "<type>-library_<slug>" where type is "mov" or "sho".  Radarr goes
# with movie, Sonarr with show.
_SERVICE_LIBRARY_TYPE_PREFIX: dict[str, str] = {
    "radarr": "mov-library_",
    "sonarr": "sho-library_",
}


def process_service_overrides(
    lib_id: str,
    lib_name: str,
    lib_cfg: dict,
    *,
    libraries_data: dict[str, Any],
    report: ImportReport,
) -> None:
    """Process both ``radarr:`` and ``sonarr:`` sub-blocks in one call.

    Iterates the two services, delegating each to
    :func:`_process_single_service_override`.
    """
    for service_name, field_map in (
        ("radarr", LIBRARY_RADARR_IMPORT_FIELDS),
        ("sonarr", LIBRARY_SONARR_IMPORT_FIELDS),
    ):
        _process_single_service_override(
            service_name,
            field_map,
            lib_id=lib_id,
            lib_name=lib_name,
            lib_cfg=lib_cfg,
            libraries_data=libraries_data,
            report=report,
        )


def _process_single_service_override(
    service_name: str,
    field_map: dict[str, str],
    *,
    lib_id: str,
    lib_name: str,
    lib_cfg: dict,
    libraries_data: dict[str, Any],
    report: ImportReport,
) -> None:
    """Handle one library's ``<service>:`` block (radarr OR sonarr).

    Applies the library-type gate first, then iterates each key in
    the service block, dispatching to ``_apply_service_field``.
    """
    service_section = lib_cfg.get(service_name)
    if not isinstance(service_section, dict):
        if service_section is not None:
            report.add(
                "unmapped",
                f"libraries.{lib_name}.{service_name}",
                "Unsupported service override format.",
            )
        return

    expected_prefix = _SERVICE_LIBRARY_TYPE_PREFIX[service_name]
    if not str(lib_id).startswith(expected_prefix):
        wrong_type = "movie" if service_name == "radarr" else "show"
        report.add(
            "unmapped",
            f"libraries.{lib_name}.{service_name}",
            f"{service_name.capitalize()} overrides are only supported on {wrong_type} libraries.",
        )
        return

    imported_service = False
    for key, value in service_section.items():
        if _apply_service_field(
            service_name,
            field_map,
            key,
            value,
            lib_id=lib_id,
            lib_name=lib_name,
            libraries_data=libraries_data,
            report=report,
        ):
            imported_service = True

    if imported_service:
        report.add("imported", f"libraries.{lib_name}.{service_name}")


def _apply_service_field(
    service_name: str,
    field_map: dict[str, str],
    key: str,
    value: Any,
    *,
    lib_id: str,
    lib_name: str,
    libraries_data: dict[str, Any],
    report: ImportReport,
) -> bool:
    """Emit one service-override key/value into libraries_data + report.

    Returns ``True`` when the value was successfully written (so the
    caller can flip its ``imported_service`` accumulator).  Bool fields
    serialize as the string ``"true"``/``"false"`` to match the form's
    on-disk format; string fields get stripped.
    """
    field_type = field_map.get(str(key))
    if not field_type:
        report.add(
            "unmapped",
            f"libraries.{lib_name}.{service_name}.{key}",
            "Library service override not supported for import.",
        )
        return False

    target_key = f"{lib_id}-attribute_{service_name}_{key}"
    if field_type == "bool":
        bool_value = _coerce_import_bool(value)
        if bool_value is None:
            report.add(
                "unmapped",
                f"libraries.{lib_name}.{service_name}.{key}",
                "Invalid boolean value.",
            )
            return False
        libraries_data[target_key] = "true" if bool_value else "false"
    else:
        if isinstance(value, (dict, list)):
            report.add(
                "unmapped",
                f"libraries.{lib_name}.{service_name}.{key}",
                "Unsupported override value format.",
            )
            return False
        text_value = str(value).strip()
        if not text_value:
            report.add(
                "unmapped",
                f"libraries.{lib_name}.{service_name}.{key}",
                "Override value is empty.",
            )
            return False
        libraries_data[target_key] = text_value

    report.add("imported", f"libraries.{lib_name}.{service_name}.{key}")
    return True
