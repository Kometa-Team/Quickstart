"""Install-mode-aware Kometa path resolvers — extracted from _legacy.py.

Resolve Kometa's on-disk locations, honoring:

- app.config overrides (per-worker)
- session overrides (per-request)
- persisted install-mode settings from the ``900-kometa`` runtime section
- managed default under ``<CONFIG_DIR>/kometa``

The three public helpers are chained: ``get_kometa_log_dir`` calls
``get_kometa_config_dir`` which calls ``get_kometa_root_path``.
"""

from __future__ import annotations

import os

from pathlib import Path

from flask import current_app as app
from flask import has_app_context, has_request_context, session


def get_kometa_root_path() -> Path:
    """
    Resolve the Kometa root folder consistently.
    Priority:
        1) app.config["KOMETA_ROOT"] if it differs from the managed default
        2) session["kometa_root"] if it differs from the managed default
        3) persisted existing-install override for the active config
        4) managed default under <CONFIG_DIR>/kometa
    """
    from modules.helpers._install_mode import _managed_kometa_root_default, get_kometa_install_mode, _get_persisted_kometa_runtime_section

    managed_default = str(_managed_kometa_root_default())
    base = None
    install_mode = get_kometa_install_mode()
    if has_app_context():
        configured = app.config.get("KOMETA_ROOT")
        if configured and os.path.normpath(str(configured)) != managed_default:
            base = configured
    if not base and has_request_context():
        session_root = session.get("kometa_root")
        if session_root and os.path.normpath(str(session_root)) != managed_default:
            base = session_root
    if not base and has_request_context():
        try:
            section = _get_persisted_kometa_runtime_section()
            if isinstance(section, dict):
                mode = str(section.get("install_mode") or "").strip().lower()
                existing_root = str(section.get("existing_root") or "").strip()
                if mode == "existing" and existing_root:
                    base = existing_root
        except Exception:
            base = None
    if not base:
        if has_app_context():
            base = app.config.get("KOMETA_ROOT")
        if not base and has_request_context():
            base = session.get("kometa_root")
    if not base:
        if install_mode == "external":
            config_dir = None
            if has_app_context():
                config_dir = app.config.get("KOMETA_CONFIG_DIR")
            if not config_dir and has_request_context():
                config_dir = session.get("kometa_config_dir")
            if not config_dir and has_request_context():
                config_dir = _get_persisted_kometa_runtime_section().get("external_config_root")
            if config_dir:
                return Path(os.path.normpath(str(config_dir))).resolve()
        base = managed_default
    return Path(os.path.normpath(base)).resolve()


def get_kometa_config_dir() -> Path:
    from modules.helpers._install_mode import get_kometa_install_mode, _get_persisted_kometa_runtime_section

    install_mode = get_kometa_install_mode()
    if install_mode != "external":
        if has_request_context():
            section = _get_persisted_kometa_runtime_section()
            mode = str(section.get("install_mode") or "").strip().lower()
            external_config_root = str(section.get("external_config_root") or "").strip()
            session_config_dir = str(session.get("kometa_config_dir") or "").strip()
            app_config_dir = str(app.config.get("KOMETA_CONFIG_DIR") or "") if has_app_context() else ""
            if mode == "external" and external_config_root and not session_config_dir and not app_config_dir:
                return Path(os.path.normpath(external_config_root)).resolve()
        return get_kometa_root_path() / "config"

    configured = None
    if has_app_context():
        configured = app.config.get("KOMETA_CONFIG_DIR")
    if not configured and has_request_context():
        configured = session.get("kometa_config_dir")
    if not configured and has_request_context():
        section = _get_persisted_kometa_runtime_section()
        mode = str(section.get("install_mode") or "").strip().lower()
        if mode == "external":
            configured = section.get("external_config_root")
    if configured:
        return Path(os.path.normpath(str(configured))).resolve()
    return get_kometa_root_path() / "config"


def get_kometa_log_dir() -> Path:
    from modules.helpers._install_mode import get_kometa_install_mode, _get_persisted_kometa_runtime_section

    install_mode = get_kometa_install_mode()
    if install_mode != "external":
        if has_request_context():
            section = _get_persisted_kometa_runtime_section()
            mode = str(section.get("install_mode") or "").strip().lower()
            external_log_root = str(section.get("external_log_root") or "").strip()
            external_config_root = str(section.get("external_config_root") or "").strip()
            session_log_dir = str(session.get("kometa_log_dir") or "").strip()
            app_log_dir = str(app.config.get("KOMETA_LOG_DIR") or "") if has_app_context() else ""
            if mode == "external" and not session_log_dir and not app_log_dir:
                if external_log_root:
                    return Path(os.path.normpath(external_log_root)).resolve()
                if external_config_root:
                    return Path(os.path.normpath(external_config_root)).resolve() / "logs"
        return get_kometa_config_dir() / "logs"

    configured = None
    if has_app_context():
        configured = app.config.get("KOMETA_LOG_DIR")
    if not configured and has_request_context():
        configured = session.get("kometa_log_dir")
    if not configured and has_request_context():
        section = _get_persisted_kometa_runtime_section()
        mode = str(section.get("install_mode") or "").strip().lower()
        if mode == "external":
            configured = section.get("external_log_root") or ""
            if not configured:
                config_dir = section.get("external_config_root") or ""
                if config_dir:
                    return Path(os.path.normpath(str(config_dir))).resolve() / "logs"
    if configured:
        return Path(os.path.normpath(str(configured))).resolve()
    return get_kometa_config_dir() / "logs"
