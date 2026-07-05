"""Per-library ``settings`` handling for ``prepare_import_payload``.

Split out of ``modules.importer`` following the same pattern as the
other per-library sub-handlers.  Kometa's ``libraries.<name>.settings:``
block accepts many keys but only two are importable into Quickstart's
form-oriented model today:

* ``asset_directory`` -- accepts either a list of paths or a
  multi-line string; both shapes normalize to a stripped list.
  Emitted as ``libraries_data[lib_id-attribute_asset_directory]``.
* ``prioritize_assets`` -- boolean.  Accepts native ``bool`` or
  the string variants ``"true" / "yes" / "1"`` / ``"false" / "no" / "0"``
  (all case-insensitive).  Note this is intentionally MORE
  RESTRICTIVE than :func:`modules.importer_value_coercion._coerce_import_bool`,
  which also accepts ``"on"``/``"off"`` -- the settings section
  historically did not, and this module preserves that behavior.

Everything else in the ``settings`` block is currently marked as
unmapped.  ``asset_directory`` with no importable entries is also
marked unmapped so users see an explicit "empty" report entry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from modules.importer import ImportReport


def process_library_settings(
    lib_id: str,
    lib_name: str,
    lib_cfg: dict,
    *,
    libraries_data: dict[str, Any],
    report: ImportReport,
) -> None:
    """Process ``lib_cfg['settings']`` into libraries_data + report.

    A no-op when the library has no ``settings`` key.  Records an
    unmapped report entry if the key is present but not a dict.
    Emits a top-level ``libraries.<name>.settings`` imported entry
    when at least one setting inside was importable.
    """
    settings_section = lib_cfg.get("settings")
    if settings_section is None:
        return

    if not isinstance(settings_section, dict):
        report.add(
            "unmapped",
            f"libraries.{lib_name}.settings",
            "Unsupported settings format.",
        )
        return

    imported_settings = False
    for key, value in settings_section.items():
        if key == "asset_directory":
            imported = _handle_asset_directory(
                key,
                value,
                lib_id=lib_id,
                lib_name=lib_name,
                libraries_data=libraries_data,
                report=report,
            )
            imported_settings = imported_settings or imported
            continue

        if key == "prioritize_assets" and not isinstance(value, (dict, list)):
            imported = _handle_prioritize_assets(
                key,
                value,
                lib_id=lib_id,
                lib_name=lib_name,
                libraries_data=libraries_data,
                report=report,
            )
            imported_settings = imported_settings or imported
            continue

        report.add(
            "unmapped",
            f"libraries.{lib_name}.settings.{key}",
            "Library setting not supported for import.",
        )

    if imported_settings:
        report.add("imported", f"libraries.{lib_name}.settings")


def _handle_asset_directory(
    key: str,
    value: Any,
    *,
    lib_id: str,
    lib_name: str,
    libraries_data: dict[str, Any],
    report: ImportReport,
) -> bool:
    """Normalize an ``asset_directory`` value to a stripped list.

    Accepts a list of path-like items or a multi-line string.  Empty
    lists / all-empty strings record an unmapped report.  Returns
    ``True`` when a non-empty list was written to ``libraries_data``.
    """
    if isinstance(value, list):
        normalized = [str(item).strip() for item in value if str(item).strip()]
    elif isinstance(value, str):
        normalized = [line.strip() for line in value.splitlines() if line.strip()]
    else:
        normalized = []

    if normalized:
        libraries_data[f"{lib_id}-attribute_{key}"] = normalized
        report.add("imported", f"libraries.{lib_name}.settings.{key}")
        return True

    report.add(
        "unmapped",
        f"libraries.{lib_name}.settings.{key}",
        "No importable asset directory entries found.",
    )
    return False


def _handle_prioritize_assets(
    key: str,
    value: Any,
    *,
    lib_id: str,
    lib_name: str,
    libraries_data: dict[str, Any],
    report: ImportReport,
) -> bool:
    """Coerce ``prioritize_assets`` to bool via the settings-specific rules.

    Accepts native ``bool`` or ``"true"/"yes"/"1"/"false"/"no"/"0"``
    (case-insensitive, stripped).  Intentionally does NOT accept
    ``"on"``/``"off"`` -- the settings section historically has been
    stricter than the generic ``_coerce_import_bool`` used elsewhere.
    Returns ``True`` when a bool was written to ``libraries_data``.
    """
    bool_value = _coerce_settings_bool(value)
    if bool_value is None:
        report.add(
            "unmapped",
            f"libraries.{lib_name}.settings.{key}",
            "Invalid boolean value.",
        )
        return False

    libraries_data[f"{lib_id}-attribute_{key}"] = bool_value
    report.add("imported", f"libraries.{lib_name}.settings.{key}")
    return True


def _coerce_settings_bool(value: Any) -> bool | None:
    """Restricted boolean coercion used only inside library settings.

    Distinct from :func:`modules.importer_value_coercion._coerce_import_bool`
    because ``settings`` values do not accept ``"on"``/``"off"``.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None
