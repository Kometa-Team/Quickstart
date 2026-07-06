"""Cross-cluster helpers shared between the validations extractions.

These 3 helpers were originally private to ``modules.validations`` but
are called from multiple thematic clusters (overlay-source-override
image handling, YAML file/folder validators, service-connectivity
validators).  Splitting them into their own module lets the thematic
extraction modules import from a single canonical location without
creating a circular dependency with ``modules.validations`` itself.

``modules.validations`` re-exports all three names for backward
compatibility -- external callers (currently ``blueprints/asset_routes.py``
references ``validations._resolve_managed_library_path``) keep working
unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path

from modules import helpers, persistence


def _resolve_managed_library_path(location: str | None) -> str:
    """Resolve a managed-library path token into an absolute filesystem path.

    Handles a bunch of Kometa/Quickstart-specific location shapes:

    * Absolute paths pass through untouched.
    * ``config/xxx`` -> ``<CONFIG_DIR>/xxx``
    * ``<slug>/<managed-dir>/xxx`` -> ``<CONFIG_DIR>/<slug>/<managed-dir>/xxx``
      where ``<managed-dir>`` is a known Kometa asset folder.
    * ``<managed-dir>/xxx`` at top level also resolves under CONFIG_DIR.

    Unrecognised shapes are returned verbatim (so downstream validators
    can flag them properly).
    """
    raw = str(location or "").strip()
    if not raw:
        return raw
    expanded = Path(os.path.expandvars(os.path.expanduser(raw)))
    if expanded.is_absolute():
        return str(expanded)
    normalized_parts = [part for part in str(expanded).replace("\\", "/").split("/") if part]
    if normalized_parts and normalized_parts[0] == "config":
        return str(Path(helpers.CONFIG_DIR) / Path(*normalized_parts[1:]))
    if len(normalized_parts) >= 3 and normalized_parts[1] in helpers.MANAGED_LIBRARY_FILE_DIRS:
        return str(Path(helpers.CONFIG_DIR) / Path(*normalized_parts))
    if len(normalized_parts) >= 3 and normalized_parts[1] == helpers.MANAGED_OVERLAY_IMAGE_DIR:
        return str(Path(helpers.CONFIG_DIR) / Path(*normalized_parts))
    if normalized_parts and normalized_parts[0] in helpers.MANAGED_LIBRARY_FILE_DIRS:
        return str(Path(helpers.CONFIG_DIR) / expanded)
    if normalized_parts and normalized_parts[0] == helpers.MANAGED_OVERLAY_IMAGE_DIR:
        return str(Path(helpers.CONFIG_DIR) / expanded)
    return raw


def _normalize_custom_repo_base(custom_repo: str | None) -> str | None:
    """Normalize a Custom Repo setting into a raw-content base URL.

    Kometa users can paste ``https://github.com/org/repo/tree/branch``
    style URLs; this rewrites them to
    ``https://raw.githubusercontent.com/org/repo/branch/`` for
    downstream ``requests.get()`` calls.  Returns ``None`` for empty
    or "none" values so callers can gate remote-fetch logic.
    """
    repo = str(custom_repo or "").strip()
    if not repo or repo.lower() == "none":
        return None
    if "https://github.com/" in repo:
        repo = repo.replace("https://github.com/", "https://raw.githubusercontent.com/").replace("/tree/", "/")
        if not repo.endswith("/"):
            repo += "/"
    return repo


def _saved_custom_repo_base() -> str | None:
    """Fetch the currently-saved Custom Repo base URL from persisted settings.

    Returns ``None`` when the setting is empty, missing, or explicitly
    ``"none"``.  Callers that need remote content-config fetches use
    this to gate the "repo" source type.
    """
    settings_data = persistence.retrieve_settings("150-settings") or {}
    settings_section = settings_data.get("settings", {}) if isinstance(settings_data, dict) else {}
    return _normalize_custom_repo_base(settings_section.get("custom_repo"))
