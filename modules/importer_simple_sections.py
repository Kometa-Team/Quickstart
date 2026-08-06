"""Top-level "simple section" parsing for ``prepare_import_payload``.

Split out of ``modules.importer`` so the generic per-section handling
(plex, tmdb, omdb, tautulli, notifiarr, ...) has a home separate from
the mega function.

Each section in :data:`SIMPLE_SECTIONS` gets copied straight from the
YAML config into the flat ``payload[section]`` dict.  A couple of
sections need light preprocessing before the copy:

* ``apprise``   -- coerces the various historical shapes
                   (``config`` string / nested dict) into a single
                   ``{location: str}`` mapping.
* ``settings``  -- normalizes ``asset_directory`` from multiline
                   string OR list into a list of stripped strings.
* ``anidb``     -- auto-adds ``enable: true`` when non-empty values
                   are present but the flag is missing (legacy configs).

All other sections in :data:`SIMPLE_SECTIONS` pass through unchanged.

Report annotations are added in place onto the caller-supplied
``ImportReport``; the ``payload`` dict is mutated in place as well.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from modules.importer import ImportReport


SIMPLE_SECTIONS: frozenset[str] = frozenset(
    {
        "plex",
        "tmdb",
        "omdb",
        "mdblist",
        "serializd",
        "floppy",
        "tautulli",
        "tracearr",
        "notifiarr",
        "gotify",
        "ntfy",
        "apprise",
        "yamtrack",
        "github",
        "radarr",
        "sonarr",
        "trakt",
        "mal",
        "anidb",
        "webhooks",
        "settings",
        "playlist_files",
    }
)


def _flatten_dict(
    base: str,
    payload: Any,
    report: ImportReport,
    max_depth: int = 3,
) -> None:
    """Recursively record every leaf of ``payload`` as imported.

    Reports the base path when the recursion bottoms out on either
    a scalar or the ``max_depth`` guard.  Empty dicts/lists count
    as leaves too so the caller can see that yes, we saw them.
    """
    if max_depth <= 0:
        report.add("imported", base)
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            child = f"{base}.{key}"
            _flatten_dict(child, value, report, max_depth - 1)
        if not payload:
            report.add("imported", base)
    elif isinstance(payload, list):
        for idx, value in enumerate(payload):
            child = f"{base}[{idx}]"
            _flatten_dict(child, value, report, max_depth - 1)
        if not payload:
            report.add("imported", base)
    else:
        report.add("imported", base)


def _normalize_apprise_section(section_payload: Any) -> str:
    """Squash the historical apprise config shapes into one location string.

    Returns an empty string when no location could be recovered so
    the caller can flag it as unmapped.
    """
    apprise_location: Any = None
    if isinstance(section_payload, dict):
        if "config" in section_payload:
            apprise_location = section_payload.get("config")
        elif "location" in section_payload:
            apprise_location = section_payload.get("location")
        elif "apprise" in section_payload:
            nested_apprise = section_payload.get("apprise")
            if isinstance(nested_apprise, dict):
                apprise_location = nested_apprise.get("config") or nested_apprise.get("location")
            else:
                apprise_location = nested_apprise
    elif isinstance(section_payload, str):
        apprise_location = section_payload

    return str(apprise_location).strip() if apprise_location is not None else ""


def _record_apprise_source_paths(section_payload: Any, report: ImportReport) -> None:
    """Record the original Apprise YAML key shape as imported.

    Apprise is normalized internally to ``apprise.location`` because that is
    the Quickstart form field, but Kometa configs commonly use
    ``apprise.config``. Recording the source key keeps the annotated import
    report from marking a successfully-normalized source line as unmapped.
    """
    if isinstance(section_payload, dict):
        if "config" in section_payload:
            report.add("imported", "apprise.config")
            return
        if "location" in section_payload:
            report.add("imported", "apprise.location")
            return
        if "apprise" in section_payload:
            nested_apprise = section_payload.get("apprise")
            if isinstance(nested_apprise, dict):
                if "config" in nested_apprise:
                    report.add("imported", "apprise.apprise.config")
                    return
                if "location" in nested_apprise:
                    report.add("imported", "apprise.apprise.location")
                    return
            report.add("imported", "apprise.apprise")
            return
    elif isinstance(section_payload, str):
        report.add("imported", "apprise")


def _normalize_settings_section(section_payload: dict) -> dict:
    """Normalize the settings section's asset_directory (str-or-list to list)."""
    asset_directory = section_payload.get("asset_directory")
    if not isinstance(asset_directory, (str, list)):
        return section_payload

    if isinstance(asset_directory, str):
        normalized = [line.strip() for line in asset_directory.splitlines()]
    else:
        normalized = [str(item).strip() for item in asset_directory]
    normalized = [entry for entry in normalized if entry]

    updated = dict(section_payload)
    updated["asset_directory"] = normalized
    return updated


def _normalize_anidb_section(section_payload: dict) -> dict:
    """Auto-add ``enable: true`` for legacy configs missing the flag."""
    if "enable" in section_payload:
        return section_payload
    has_values = any(value not in [None, "", [], {}] for value in section_payload.values())
    if not has_values:
        return section_payload
    updated = dict(section_payload)
    updated["enable"] = True
    return updated


def process_simple_sections(
    config_data: dict,
    *,
    payload: dict[str, dict],
    report: ImportReport,
) -> None:
    """Copy each top-level SIMPLE_SECTIONS block from config_data into payload.

    Mutates ``payload`` (adds one key per recognized section) and
    ``report`` (records imported / unmapped paths) in place.

    ``playlist_files`` is included in :data:`SIMPLE_SECTIONS` for the
    end-of-function unknown-key sweep but is handled separately by
    :mod:`modules.importer_playlists`; this function skips it explicitly.
    """
    for section in SIMPLE_SECTIONS:
        if section not in config_data:
            continue
        section_payload = config_data.get(section)
        if section == "playlist_files":
            continue

        if section == "apprise":
            apprise_location = _normalize_apprise_section(section_payload)
            if apprise_location:
                normalized_apprise = {"location": apprise_location}
                payload[section] = {section: normalized_apprise}
                _flatten_dict(section, normalized_apprise, report)
                _record_apprise_source_paths(section_payload, report)
            else:
                report.add("unmapped", section, "Unsupported section format.")
            continue

        if isinstance(section_payload, dict):
            if section == "settings":
                section_payload = _normalize_settings_section(section_payload)
            if section == "anidb":
                section_payload = _normalize_anidb_section(section_payload)
            payload[section] = {section: section_payload}
            _flatten_dict(section, section_payload, report)
        else:
            report.add("unmapped", section, "Unsupported section format.")
