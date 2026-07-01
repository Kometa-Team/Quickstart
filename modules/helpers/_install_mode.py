"""Kometa install mode utilities extracted from _legacy.py."""

import os

from pathlib import Path

from flask import current_app as app
from flask import has_app_context, has_request_context, session

from modules import persistence
from modules.helpers._legacy import CONFIG_DIR


def _managed_kometa_root_default() -> Path:
    return Path(os.path.join(CONFIG_DIR, "kometa")).resolve()


def _get_persisted_kometa_runtime_section() -> dict:
    try:
        settings = persistence.retrieve_settings("900-kometa") or {}
    except Exception:
        return {}
    section = settings.get("kometa", {}) if isinstance(settings, dict) else {}
    return section if isinstance(section, dict) else {}


def get_kometa_install_mode() -> str:
    mode = None
    if has_app_context():
        mode = app.config.get("KOMETA_INSTALL_MODE")
    if not mode and has_request_context():
        mode = session.get("kometa_install_mode")
    if not mode and has_request_context():
        mode = _get_persisted_kometa_runtime_section().get("install_mode")
    normalized = str(mode or "").strip().lower()
    if normalized in {"existing", "external"}:
        return normalized
    return "managed"


def get_kometa_install_mode_label(mode=None) -> str:
    normalized = str(mode or get_kometa_install_mode()).strip().lower()
    if normalized == "existing":
        return "Existing direct install"
    if normalized == "external":
        return "External/containerized config+logs"
    return "Quickstart-managed install"
