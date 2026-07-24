"""Config-section normalization for the generated Kometa config.

Extracted from ``modules.output.build_config``.

Kometa accepts a handful of top-level config sections in slightly
inconsistent shapes -- users may have historical persistence data
that stores them nested twice, or as a bare string, or with empty
values that need to disappear.  This module contains three focused
normalizers that mutate ``config_data`` in place to canonicalize
those shapes before YAML dump time.

Public entry points:

* :func:`normalize_playlist_files_section` -- flatten possibly-nested
  playlist_files data and format via ``_format_playlist_file_entries``.
* :func:`normalize_webhooks_section` -- strip empty values, unwrap
  extra ``webhooks.webhooks`` nesting, delete the section when
  entirely empty.
* :func:`normalize_apprise_section` -- extract the apprise
  ``location`` from any of the three legacy shapes and rewrite
  it into the canonical ``{apprise: {config: <location>}}`` form.

Each function mutates ``config_data`` in place and returns ``None``.
All three are safe to call whether or not their section is present
in ``config_data``.
"""

from __future__ import annotations

from modules import helpers
from modules.output_playlists import _format_playlist_file_entries

# Values that count as "empty" during webhook cleanup.  Kometa's
# YAML dumper would happily emit these, but Kometa's runtime treats
# them as missing, so we drop them at generation time to avoid
# confusing diagnostics.
_WEBHOOK_EMPTY_VALUES = (None, "", [], {})


def _debug(debug, message):
    """Emit *message* via helpers.ts_log when debug is truthy."""
    if debug:
        helpers.ts_log(message, level="DEBUG")


def normalize_playlist_files_section(config_data, *, debug=False):
    """Normalize ``config_data['playlist_files']`` in place.

    Handles two historical persistence shapes:

    1. ``{playlist_files: {libraries: <list-or-string>, ...tvars}}``
       -- the canonical shape.
    2. ``{playlist_files: {playlist_files: {libraries: ..., ...tvars}}}``
       -- an extra layer of nesting that some older persistence rows
       still carry.  Unwrapped before parsing.

    The ``libraries`` value may be either a list or a
    comma-separated string.  Both are split, stripped, and filtered
    for empties.  All remaining keys become the shared template
    variables (empty containers dropped).

    The whole normalized structure is then piped through
    :func:`_format_playlist_file_entries` (already extracted), which
    produces the final list emitted to YAML.

    No-op when ``playlist_files`` is not in *config_data*.
    """
    if "playlist_files" not in config_data:
        return

    playlist_data = config_data["playlist_files"]
    _debug(debug, f"Raw config_data['playlist_files'] content (Level 1): {playlist_data}")

    # Legacy shape may double-nest the payload; unwrap once when so.
    inner = playlist_data.get("playlist_files") if isinstance(playlist_data, dict) else None
    if isinstance(inner, dict):
        playlist_data = inner
        _debug(debug, f" playlist_data after extra nesting: {playlist_data}")

    libraries_value = playlist_data.get("libraries", "")
    _debug(debug, f"Extracted libraries value: {libraries_value}")

    if isinstance(libraries_value, list):
        libraries_list = [str(lib) for lib in libraries_value if str(lib)]
    else:
        libraries_list = [lib for lib in str(libraries_value or "").split(",") if lib]
    _debug(debug, f"Processed libraries list: {libraries_value}")

    playlist_template_variables = {key: value for key, value in playlist_data.items() if key != "libraries" and value not in (None, "", [], {})}

    formatted_playlist_files = _format_playlist_file_entries(
        libraries_list=libraries_list,
        template_variables=playlist_template_variables,
    )
    _debug(debug, f"Formatted playlist_files data: {formatted_playlist_files}")

    config_data["playlist_files"] = formatted_playlist_files


def normalize_webhooks_section(config_data, *, debug=False):
    """Normalize ``config_data['webhooks']`` in place.

    * Unwrap the ``{webhooks: {webhooks: ...}}`` extra nesting when
      present (persistence-side shape mismatch).
    * Drop any key whose value is in :data:`_WEBHOOK_EMPTY_VALUES`.
    * When nothing remains, remove the ``webhooks`` section entirely
      so the YAML file stays tidy.
    * Otherwise re-wrap into the canonical
      ``{webhooks: {webhooks: <cleaned>}}`` shape Kometa expects.

    No-op when ``webhooks`` is not in *config_data*.
    """
    if "webhooks" not in config_data:
        return

    webhooks_data = config_data["webhooks"]
    if isinstance(webhooks_data, dict) and "webhooks" in webhooks_data:
        webhooks_data = webhooks_data["webhooks"]

    cleaned_webhooks = {key: value for key, value in webhooks_data.items() if value not in _WEBHOOK_EMPTY_VALUES}

    if cleaned_webhooks:
        config_data["webhooks"] = {"webhooks": cleaned_webhooks}
    else:
        config_data.pop("webhooks", None)

    _debug(debug, f"Cleaned Webhooks Data AFTER Removing Empty Values: {cleaned_webhooks}")
    if debug and "webhooks" not in config_data:
        helpers.ts_log("Webhooks section completely removed.", level="DEBUG")


def _extract_apprise_location(apprise_data):
    """Pull the apprise ``location`` value out of any legacy shape.

    Recognized inputs:

    * ``str`` -- treated as the location directly.
    * ``{apprise: {location: <val>}}`` -- doubly-nested canonical.
    * ``{apprise: <val>}`` -- bare scalar under the wrapper key.
    * ``{location: <val>}`` -- single-nested older shape.
    * anything else -- returns ``None``.

    Returned value is left as-is; the caller strips + rewrites.
    """
    if isinstance(apprise_data, str):
        return apprise_data
    if not isinstance(apprise_data, dict):
        return None
    if "apprise" in apprise_data:
        nested_apprise = apprise_data["apprise"]
        if isinstance(nested_apprise, dict):
            return nested_apprise.get("location")
        return nested_apprise
    if "location" in apprise_data:
        return apprise_data.get("location")
    return None


def normalize_apprise_section(config_data):
    """Normalize ``config_data['apprise']`` in place.

    Extracts the location from any of the four legacy shapes (see
    :func:`_extract_apprise_location`) and rewrites into the canonical
    ``{apprise: {config: <location>}}`` form.  When the location is
    empty / missing, removes the ``apprise`` section entirely.

    No-op when ``apprise`` is not in *config_data*.
    """
    if "apprise" not in config_data:
        return

    apprise_location = _extract_apprise_location(config_data["apprise"])
    apprise_location = str(apprise_location).strip() if apprise_location is not None else ""

    if apprise_location:
        config_data["apprise"] = {"apprise": {"config": apprise_location}}
    else:
        config_data.pop("apprise", None)
