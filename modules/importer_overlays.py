"""Per-library ``overlay_files`` handling for ``prepare_import_payload``.

Split out of ``modules.importer`` following the same pattern as
:mod:`modules.importer_collections`.  The overlay pipeline is
structurally similar (parse entry -> resolve id -> emit templates)
but adds three overlay-specific concerns:

* **builder_level**  -- overlays can target ``movie``, ``show``,
  ``season`` or ``episode`` scope.  Defaults to the library's
  ``builder_default`` (movie vs. show).  Overrideable per entry
  via ``template_variables.builder_level``.
* **Language subtitles alias** -- when the ``overlay_languages``
  overlay is selected and the config carries
  ``use_subtitles: true``, we transparently swap to the
  ``overlay_languages_subtitles`` alternate overlay.
* **Radio groups** -- some overlays participate in mutually
  exclusive radio groups (only one option per group can be set
  per library).  Handled via the ``overlay_radio`` mapping from
  :func:`modules.importer_library_types._build_overlay_index`.
* **Language weight expansion** -- for the two language overlays
  the allowed-template-keys set is extended with the module-level
  ``LANGUAGE_WEIGHT_TEMPLATE_KEYS`` (81 ``weight_<code>`` keys).

Each library entry's ``overlay_files:`` list can contain:

* **File references** -- ``{file, url, git, repo, folder}`` pointing
  at an external overlay YAML -- collected into a JSON blob under
  ``libraries_data[lib_id-overlay_files]``.
* **Default references** -- ``{default: overlay_id_or_alias}`` (or
  a bare string) selecting one of the Quickstart-bundled overlays.

Report annotations are added in place onto the caller-supplied
``ImportReport``; ``libraries_data`` is mutated in place.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from modules.importer_library_types import _resolve_overlay_id
from modules.importer_value_coercion import (
    _collect_overlay_source_override_keys,
    _collect_template_keys,
)

if TYPE_CHECKING:
    from modules.importer import ImportReport


def process_overlay_files(
    lib_id: str,
    lib_name: str,
    lib_cfg: dict,
    builder_default: str,
    *,
    libraries_data: dict[str, Any],
    report: ImportReport,
    overlay_by_id: dict[str, dict],
    overlay_by_alias: dict[str, str],
    overlay_radio: dict[str, dict],
    language_weight_template_keys: frozenset[str],
) -> None:
    """Process ``lib_cfg['overlay_files']`` into libraries_data + report.

    A no-op when the library has no ``overlay_files`` key.  Records an
    unmapped report entry if the key is present but not a list.

    ``language_weight_template_keys`` is passed in (not imported) so
    this module doesn't reach back into ``modules.importer`` for the
    constant -- keeps the dependency direction one-way.
    """
    overlay_files = lib_cfg.get("overlay_files")
    if overlay_files is None:
        return

    if not isinstance(overlay_files, list):
        report.add(
            "unmapped",
            f"libraries.{lib_name}.overlay_files",
            "Unsupported overlay_files format.",
        )
        return

    imported_overlay_files: list[dict[str, str]] = []
    for idx, entry in enumerate(overlay_files):
        _process_single_overlay_entry(
            idx,
            entry,
            lib_id=lib_id,
            lib_name=lib_name,
            builder_default=builder_default,
            libraries_data=libraries_data,
            report=report,
            overlay_by_id=overlay_by_id,
            overlay_by_alias=overlay_by_alias,
            overlay_radio=overlay_radio,
            language_weight_template_keys=language_weight_template_keys,
            imported_overlay_files=imported_overlay_files,
        )

    if imported_overlay_files:
        libraries_data[f"{lib_id}-overlay_files"] = json.dumps(imported_overlay_files, ensure_ascii=True)
        report.add("imported", f"libraries.{lib_name}.overlay_files")


def _process_single_overlay_entry(
    idx: int,
    entry: Any,
    *,
    lib_id: str,
    lib_name: str,
    builder_default: str,
    libraries_data: dict[str, Any],
    report: ImportReport,
    overlay_by_id: dict[str, dict],
    overlay_by_alias: dict[str, str],
    overlay_radio: dict[str, dict],
    language_weight_template_keys: frozenset[str],
    imported_overlay_files: list[dict[str, str]],
) -> None:
    """Dispatch a single overlay_files[] entry.

    Handles file-ref short-circuit, default resolution (with the
    ``overlay_languages`` -> ``overlay_languages_subtitles`` alias
    when ``use_subtitles: true``), builder_level fallback against
    the overlay's supported media_types, and radio-group vs.
    plain-flag emission.
    """
    default_value: Any = None
    template_values: Any = None
    builder_level = builder_default
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
        if isinstance(template_values, dict) and "builder_level" in template_values:
            level = template_values.get("builder_level")
            if level in {"show", "season", "episode"}:
                builder_level = level
    elif isinstance(entry, str):
        default_value = entry

    if raw_entry_type and raw_entry_location:
        imported_overlay_files.append({"type": raw_entry_type, "location": raw_entry_location})
        report.add(
            "imported",
            f"libraries.{lib_name}.overlay_files[{idx}].{raw_entry_type}",
        )
        return

    if not default_value:
        report.add(
            "unmapped",
            f"libraries.{lib_name}.overlay_files[{idx}]",
            "Missing default.",
        )
        return

    raw_default = str(default_value)
    overlay_id = _resolve_overlay_id(raw_default, overlay_by_id, overlay_by_alias)
    if overlay_id not in overlay_by_id:
        report.add(
            "unmapped",
            f"libraries.{lib_name}.overlay_files[{idx}].default",
            "Overlay not found in Quickstart.",
        )
        return

    overlay_meta = overlay_by_id.get(overlay_id, {})

    # -- Language-subtitles alias: use_subtitles: true swaps the overlay id.
    if (
        overlay_id == "overlay_languages"
        and isinstance(template_values, dict)
        and str(template_values.get("use_subtitles", "")).strip().lower() == "true"
    ):
        subtitles_id = overlay_by_alias.get("languages_subtitles")
        if subtitles_id:
            overlay_id = subtitles_id
            overlay_meta = overlay_by_id.get(overlay_id, {})
            template_values = dict(template_values)
            template_values.pop("use_subtitles", None)
            report.add(
                "imported",
                f"libraries.{lib_name}.overlay_files[{idx}].template_variables.use_subtitles",
            )

    # -- Media-type compatibility check + builder_level fallback.
    media_types = overlay_meta.get("media_types") or []
    if builder_level == "movie" and media_types and "movie" not in media_types:
        report.add(
            "unmapped",
            f"libraries.{lib_name}.overlay_files[{idx}].default",
            "Overlay not available for movie libraries.",
        )
        return
    if builder_level not in media_types and builder_level != "movie":
        if "show" in media_types:
            builder_level = "show"
        elif media_types:
            builder_level = media_types[0]

    # -- Radio-group vs. plain-flag emission.
    radio_info = overlay_radio.get(overlay_id)
    if radio_info:
        radio_key = f"{lib_id}-{builder_level}-{radio_info['group_name']}"
        libraries_data[radio_key] = radio_info.get("value")
    else:
        libraries_data[f"{lib_id}-{builder_level}-{overlay_id}"] = True
    report.add("imported", f"libraries.{lib_name}.overlay_files[{idx}].default")

    if isinstance(template_values, dict):
        _apply_overlay_template_variables(
            idx,
            overlay_id,
            overlay_meta,
            template_values,
            builder_level,
            lib_id=lib_id,
            lib_name=lib_name,
            libraries_data=libraries_data,
            report=report,
            language_weight_template_keys=language_weight_template_keys,
        )


def _apply_overlay_template_variables(
    idx: int,
    overlay_id: str,
    overlay_meta: dict,
    template_values: dict,
    builder_level: str,
    *,
    lib_id: str,
    lib_name: str,
    libraries_data: dict[str, Any],
    report: ImportReport,
    language_weight_template_keys: frozenset[str],
) -> None:
    """Emit template_variables overrides for one overlay entry.

    For language overlays (``overlay_languages`` /
    ``overlay_languages_subtitles``) the allowed-key set is expanded
    with the 81 ``weight_<code>`` language-weight keys so callers can
    supply per-language weights.
    """
    allowed = _collect_template_keys(overlay_meta.get("template_variables"))
    allowed.update(_collect_overlay_source_override_keys(overlay_meta))
    if overlay_id in {"overlay_languages", "overlay_languages_subtitles"}:
        allowed = set(allowed)
        allowed.update(language_weight_template_keys)

    for key, value in template_values.items():
        if key not in allowed:
            if key == "builder_level":
                continue
            report.add(
                "unmapped",
                f"libraries.{lib_name}.overlay_files[{idx}].template_variables.{key}",
                "Template variable not available in Quickstart.",
            )
            continue
        child_name = f"{lib_id}-{builder_level}-template_{overlay_id}[{key}]"
        libraries_data[child_name] = value
        report.add(
            "imported",
            f"libraries.{lib_name}.overlay_files[{idx}].template_variables.{key}",
        )
