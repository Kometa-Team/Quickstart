import argparse
import gzip
import inspect
import io
import json
import os
import hashlib
import platform
import psutil
import re
import shutil
import shlex
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
import zipfile
import secrets
from io import BytesIO
from threading import Thread
from pathlib import Path
from collections import deque

import namesgenerator
import requests
from cachelib.file import FileSystemCache
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_file,
    abort,
    has_request_context,
)
from waitress import serve
from ruamel.yaml import YAML
from werkzeug.datastructures import MultiDict
from werkzeug.utils import secure_filename

from werkzeug.wrappers import Request
from flask_session import Session
from modules import validations, output, persistence, helpers, database, logscan, importer, path_validation, url_validation
from modules.background_jobs import (
    JOB_TARGET_PAGES,
    create_background_job as _create_background_job,  # noqa: F401 (used directly by tests as qs_module._create_background_job)
    get_background_job as _get_background_job,
    get_active_background_job as _get_active_background_job,
    get_active_background_jobs as _get_active_background_jobs,
    update_background_job as _update_background_job,
    clear_active_background_job as _clear_active_background_job,
    ensure_background_job as _ensure_background_job,
    complete_background_job as _complete_background_job,  # noqa: F401 (used directly by tests as qs_module._complete_background_job)
)
from blueprints.validation_routes import bp as validation_routes_bp, refresh_plex_libraries
from blueprints.asset_routes import bp as asset_routes_bp
from blueprints.kometa_updates import bp as kometa_updates_bp
from blueprints.imagemaid_updates import bp as imagemaid_updates_bp
from blueprints.config_routes import bp as config_routes_bp
from blueprints.test_libraries_routes import bp as test_libraries_routes_bp
from modules.assets import build_preview_image_data as _build_preview_image_data, list_overlay_fonts
from modules.test_libraries import (
    resolve_test_libraries_paths as _resolve_test_libraries_paths,  # noqa: F401 (used directly by tests as qs_module._resolve_test_libraries_paths)
    paths_overlap as _paths_overlap,  # noqa: F401 (used directly by tests as qs_module._paths_overlap)
    safe_to_replace_test_libraries as _safe_to_replace_test_libraries,  # noqa: F401 (used directly by tests as qs_module._safe_to_replace_test_libraries)
)
from modules.logscan_cache import (
    get_logscan_cache_dir as _get_logscan_cache_dir,
    normalize_logscan_tool_name as _normalize_logscan_tool_name,
    get_logscan_live_dir as _get_logscan_live_dir,
    get_logscan_archive_root_dir as _get_logscan_archive_root_dir,
    get_logscan_archive_dir as _get_logscan_archive_dir,
    detect_logscan_tool_from_path as _detect_logscan_tool_from_path,
    build_logscan_archive_destination as _build_logscan_archive_destination,
    iter_logscan_candidate_files as _iter_logscan_candidate_files,
    get_logscan_log_files as _get_logscan_log_files,
    logscan_cache_entry_matches as _logscan_cache_entry_matches,
    get_logscan_delta_files as _get_logscan_delta_files,
    classify_logscan_file_location as _classify_logscan_file_location,
    format_archived_log_retention_label as _format_archived_log_retention_label,
    get_logscan_keep_limit as _get_logscan_keep_limit,
    load_logscan_ingest_cache as _load_logscan_ingest_cache,  # noqa: F401 (used directly by tests as qs_module._load_logscan_ingest_cache)
    save_logscan_ingest_cache as _save_logscan_ingest_cache,  # noqa: F401 (used directly by tests as qs_module._save_logscan_ingest_cache)
    clear_logscan_ingest_cache as _clear_logscan_ingest_cache,
    remove_logscan_ingest_cache_entries as _remove_logscan_ingest_cache_entries,
)
from modules.kometa_install import (
    KOMETA_INSTALL_MODE_MANAGED,
    KOMETA_INSTALL_MODE_EXTERNAL,
    canonicalize_kometa_section as _canonicalize_kometa_section,
    validate_saved_kometa_selection as _validate_saved_kometa_selection,
    build_kometa_install_context as _build_kometa_install_context,
    get_kometa_settings_section as _get_kometa_settings_section,
    resolve_kometa_selection as _resolve_kometa_selection,
    probe_kometa_root_state as _probe_kometa_root_state,  # noqa: F401 (used directly by tests as qs_module._probe_kometa_root_state)
)
from modules.imagemaid import (
    probe_imagemaid_root_state as _probe_imagemaid_root_state,
    imagemaid_settings_to_form_payload as _imagemaid_settings_to_form_payload,
    get_stored_plex_credentials_for_config as _get_stored_plex_credentials_for_config,
    save_imagemaid_settings_for_config as _save_imagemaid_settings_for_config,
    get_imagemaid_settings_section as _get_imagemaid_settings_section,
    persist_imagemaid_validation as _persist_imagemaid_validation,
    build_imagemaid_command_parts as _build_imagemaid_command_parts,
    build_imagemaid_command as _build_imagemaid_command,
    validate_imagemaid_settings as _validate_imagemaid_settings,
    get_latest_imagemaid_log_path as _get_latest_imagemaid_log_path,
    get_imagemaid_supported_options as _get_imagemaid_supported_options,  # noqa: F401 (used directly by tests as qs_module._get_imagemaid_supported_options)
)
from modules.process_control import (
    MAINTENANCE_STATE,
    MAINTENANCE_STATE_LOCK,
    RUN_CONTEXT,
    RUN_CONTEXT_LOCK,
    IMAGEMAID_RUN_CONTEXT,  # noqa: F401 (used directly by tests as qs_module.IMAGEMAID_RUN_CONTEXT)
    IMAGEMAID_RUN_CONTEXT_LOCK,  # noqa: F401 (used directly by tests as qs_module.IMAGEMAID_RUN_CONTEXT_LOCK)
    calculate_process_cpu_percent as _calculate_process_cpu_percent,
    calculate_system_cpu_percent as _calculate_system_cpu_percent,
    calculate_process_io_stats as _calculate_process_io_stats,
    clear_process_metric_cache as _clear_process_metric_cache,
    is_within_maintenance_window as _is_within_maintenance_window,
    get_maintenance_window_from_db as _get_maintenance_window_from_db,  # noqa: F401 (used directly by tests as qs_module._get_maintenance_window_from_db)
    get_maintenance_window_live as _get_maintenance_window_live,  # noqa: F401 (used directly by tests as qs_module._get_maintenance_window_live)
    resolve_maintenance_window_live as _resolve_maintenance_window_live,
    resolve_maintenance_window_from_db as _resolve_maintenance_window_from_db,
    refresh_maintenance_window_availability as _refresh_maintenance_window_availability,  # noqa: F401 (used directly by tests as qs_module._refresh_maintenance_window_availability)
    normalize_kometa_start_mode as _normalize_kometa_start_mode,
    set_pending_kometa_start as _set_pending_kometa_start,  # noqa: F401 (used directly by tests as qs_module._set_pending_kometa_start)
    peek_pending_kometa_start as _peek_pending_kometa_start,
    pop_pending_kometa_start as _pop_pending_kometa_start,  # noqa: F401 (used directly by tests as qs_module._pop_pending_kometa_start)
    clear_pending_kometa_start as _clear_pending_kometa_start,  # noqa: F401 (used directly by tests as qs_module._clear_pending_kometa_start)
    find_running_kometa_processes as _find_running_kometa_processes,  # noqa: F401 (used directly by tests as qs_module._find_running_kometa_processes)
    find_running_kometa_process as _find_running_kometa_process,
    find_running_imagemaid_processes as _find_running_imagemaid_processes,
    find_running_imagemaid_process as _find_running_imagemaid_process,
    stop_process_tree as _stop_process_tree,
    launch_kometa_command as _launch_kometa_command,
    launch_imagemaid_command as _launch_imagemaid_command,
    reset_imagemaid_runtime_env as _reset_imagemaid_runtime_env,  # noqa: F401 (used directly by tests as qs_module._reset_imagemaid_runtime_env)
    extract_selected_libraries as _extract_selected_libraries,
    update_run_context as _update_run_context,
    get_run_context as _get_run_context,
    clear_run_context as _clear_run_context,
    get_imagemaid_run_context as _get_imagemaid_run_context,
    clear_imagemaid_run_context as _clear_imagemaid_run_context,
    suspend_process_tree as _suspend_process_tree,  # noqa: F401 (used directly by tests as qs_module._suspend_process_tree)
    resume_process_tree as _resume_process_tree,  # noqa: F401 (used directly by tests as qs_module._resume_process_tree)
    maintenance_guard_loop as _maintenance_guard_loop,
    append_quickstart_meta_log_line as _append_quickstart_meta_log_line,  # noqa: F401 (used directly by tests as qs_module._append_quickstart_meta_log_line)
    get_kometa_maintenance_sidecar_path as _get_kometa_maintenance_sidecar_path,  # noqa: F401 (used directly by tests as qs_module._get_kometa_maintenance_sidecar_path)
    is_logscan_maintenance_sidecar as _is_logscan_maintenance_sidecar,
    write_quickstart_maintenance_marker as _write_quickstart_maintenance_marker,  # noqa: F401 (used directly by tests as qs_module._write_quickstart_maintenance_marker)
    write_quickstart_imagemaid_run_marker as _write_quickstart_imagemaid_run_marker,
    write_quickstart_stop_marker as _write_quickstart_stop_marker,
    write_quickstart_imagemaid_stop_marker as _write_quickstart_imagemaid_stop_marker,
    write_quickstart_imagemaid_maintenance_marker as _write_quickstart_imagemaid_maintenance_marker,
)

Request.max_form_parts = 100000  # Allow more form fields if needed

_resolve_request_config_name = persistence.resolve_request_config_name
utc_now_iso = helpers.utc_now_iso
_safe_join = helpers.safe_join
_safe_rel_path = helpers.safe_rel_path
_resolve_user_dir = helpers.resolve_user_dir
_retrieve_settings_for_config = persistence.retrieve_settings_for_config
apply_validation_metadata = persistence.apply_validation_metadata
_is_logscan_gzip_path = helpers.is_logscan_gzip_path
_read_logscan_text = helpers.read_logscan_text

ACTIVE_WORK_POLICIES = {
    "kometa_run": [
        {
            "kind": "process",
            "id": "imagemaid_run",
            "message": "Cannot start Kometa while ImageMaid is running.",
            "target_page": JOB_TARGET_PAGES.get("imagemaid_update"),
        },
        {
            "kind": "job",
            "id": "kometa_update",
            "message": "Cannot start Kometa while a Kometa update is running.",
            "target_page": JOB_TARGET_PAGES.get("kometa_update"),
        },
    ],
    "kometa_update": [
        {
            "kind": "process",
            "id": "kometa_run",
            "message": "Cannot update Kometa while Kometa is running.",
            "target_page": JOB_TARGET_PAGES.get("kometa_update"),
        }
    ],
    "imagemaid_run": [
        {
            "kind": "process",
            "id": "kometa_run",
            "message": "Cannot start ImageMaid while Kometa is running.",
            "target_page": JOB_TARGET_PAGES.get("kometa_update"),
        },
        {
            "kind": "job",
            "id": "imagemaid_update",
            "message": "Cannot start ImageMaid while an ImageMaid update is running.",
            "target_page": JOB_TARGET_PAGES.get("imagemaid_update"),
        },
    ],
    "imagemaid_update": [
        {
            "kind": "process",
            "id": "imagemaid_run",
            "message": "Cannot update ImageMaid while ImageMaid is running.",
            "target_page": JOB_TARGET_PAGES.get("imagemaid_update"),
        }
    ],
}
LOG_STATS_CACHE = {"mtime": None, "size": None, "stats": None}
LOGSCAN_ANALYSIS_CACHE = {"mtime": None, "size": None, "data": None}
LOGSCAN_PROGRESS_CACHE = {"mtime": None, "size": None, "data": None}
IMAGEMAID_STARTUP_GRACE_SECONDS = 10

VALIDATION_DOC_BASE = "/step/"
VALIDATION_DOC_FALLBACK = "/step/900-kometa"
VALIDATION_DOCS = {
    "settings": f"{VALIDATION_DOC_BASE}150-settings",
    "libraries": f"{VALIDATION_DOC_BASE}025-libraries",
    "plex": f"{VALIDATION_DOC_BASE}010-plex",
    "tmdb": f"{VALIDATION_DOC_BASE}020-tmdb",
    "trakt": f"{VALIDATION_DOC_BASE}130-trakt",
    "radarr": f"{VALIDATION_DOC_BASE}110-radarr",
    "sonarr": f"{VALIDATION_DOC_BASE}120-sonarr",
    "tautulli": f"{VALIDATION_DOC_BASE}030-tautulli",
    "omdb": f"{VALIDATION_DOC_BASE}050-omdb",
    "mdblist": f"{VALIDATION_DOC_BASE}060-mdblist",
    "notifiarr": f"{VALIDATION_DOC_BASE}070-notifiarr",
    "github": f"{VALIDATION_DOC_BASE}040-github",
    "gotify": f"{VALIDATION_DOC_BASE}080-gotify",
    "ntfy": f"{VALIDATION_DOC_BASE}085-ntfy",
    "apprise": f"{VALIDATION_DOC_BASE}087-apprise",
    "mal": f"{VALIDATION_DOC_BASE}140-mal",
    "anidb": f"{VALIDATION_DOC_BASE}100-anidb",
    "webhooks": f"{VALIDATION_DOC_BASE}090-webhooks",
    "collections": f"{VALIDATION_DOC_BASE}025-libraries",
    "overlays": f"{VALIDATION_DOC_BASE}025-libraries",
    "playlist_files": f"{VALIDATION_DOC_BASE}027-playlist_files",
}
VALIDATION_REASON_LABELS = {
    "missing_credentials": "Missing credentials",
    "missing_plex_validation": "Plex not validated",
    "no_libraries": "No libraries selected",
    "invalid_paths": "Invalid paths",
    "invalid_arr_overrides": "Invalid Arr overrides",
    "missing_library_defaults": "Missing library defaults",
    "missing_separator_placeholder": "Missing separator placeholder",
    "invalid_metadata_files": "Invalid metadata files",
    "invalid_collection_files": "Invalid collection files",
    "invalid_overlay_files": "Invalid overlay files",
    "invalid_fields": "Invalid fields",
    "no_webhooks": "No webhooks configured",
    "disabled": "Disabled",
    "missing_settings": "Settings missing",
    "missing_location": "Missing location",
    "missing_tokens": "Missing tokens",
    "token_invalid": "Invalid tokens",
    "account_locked": "Account locked",
    "validation_error": "Validation error",
}
SETTINGS_AUTO_SORT_HUBS_VALUES = {
    "sort_title",
    "sort_title.desc",
    "alpha",
    "alpha.desc",
    "configured",
    "configured.desc",
    "random",
}


def _get_active_work_blocker(subject):
    normalized_subject = str(subject or "").strip()
    if not normalized_subject:
        return None

    for rule in ACTIVE_WORK_POLICIES.get(normalized_subject, []):
        kind = str(rule.get("kind") or "").strip().lower()
        identifier = str(rule.get("id") or "").strip()
        if not identifier:
            continue

        if kind == "job":
            active_job = _get_active_background_job(identifier)
            if active_job:
                blocker = dict(rule)
                blocker["job"] = active_job
                blocker["blocked_by"] = identifier
                blocker["status"] = active_job.get("status")
                blocker["phase"] = active_job.get("phase")
                blocker["job_id"] = active_job.get("job_id")
                return blocker
        elif kind == "process":
            process_lookup = {
                "kometa_run": (helpers.is_kometa_running, helpers.get_kometa_pid),
                "imagemaid_run": (helpers.is_imagemaid_running, helpers.get_imagemaid_pid),
            }
            resolver = process_lookup.get(identifier)
            if resolver:
                is_running, get_pid = resolver
                if is_running():
                    blocker = dict(rule)
                    blocker["blocked_by"] = identifier
                    blocker["pid"] = get_pid()
                    return blocker

    return None


VALIDATION_KEY_SUGGESTIONS = {
    "settings": {
        "playlist_sync_to_user": "playlist_sync_to_users",
    }
}
QS_REQUIRED_STEP_KEYS = ["001-start", "010-plex", "020-tmdb", "025-libraries", "150-settings"]
QS_REVIEW_STEP_KEYS = ["900-kometa", "905-analytics", "910-sponsor", "915-imagemaid"]
QS_VALIDATION_STEP_KEYS = {
    "010-plex",
    "020-tmdb",
    "025-libraries",
    "030-tautulli",
    "040-github",
    "050-omdb",
    "060-mdblist",
    "070-notifiarr",
    "080-gotify",
    "085-ntfy",
    "087-apprise",
    "090-webhooks",
    "100-anidb",
    "110-radarr",
    "120-sonarr",
    "130-trakt",
    "140-mal",
    "150-settings",
}
QS_STATUS_ORDER = {"unknown": 0, "ok": 1, "warn": 2, "error": 3}
QS_WARN_REASONS = {
    "missing_credentials",
    "missing_tokens",
    "no_libraries",
    "missing_settings",
    "disabled",
    "no_webhooks",
}
QS_ERROR_REASONS = {
    "missing_plex_validation",
    "missing_location",
    "token_invalid",
    "account_locked",
    "validation_error",
    "invalid_paths",
    "invalid_arr_overrides",
    "invalid_collection_files",
    "invalid_overlay_files",
    "invalid_fields",
    "invalid_metadata_files",
    "missing_library_defaults",
    "missing_separator_placeholder",
}
LIBRARY_RADARR_FIELDS = [
    "url",
    "token",
    "root_folder_path",
    "quality_profile",
    "availability",
    "tag",
    "monitor",
    "search",
    "add_missing",
    "add_existing",
    "upgrade_existing",
    "monitor_existing",
    "ignore_cache",
    "radarr_path",
    "plex_path",
]
LIBRARY_RADARR_BOOL_FIELDS = {
    "monitor",
    "search",
    "add_missing",
    "add_existing",
    "upgrade_existing",
    "monitor_existing",
    "ignore_cache",
}
LIBRARY_RADARR_AVAILABILITY_VALUES = {"announced", "cinemas", "released", "db"}
LIBRARY_SONARR_FIELDS = [
    "url",
    "token",
    "root_folder_path",
    "quality_profile",
    "language_profile",
    "series_type",
    "season_folder",
    "monitor",
    "tag",
    "search",
    "cutoff_search",
    "add_missing",
    "add_existing",
    "upgrade_existing",
    "monitor_existing",
    "ignore_cache",
    "sonarr_path",
    "plex_path",
]
LIBRARY_SONARR_BOOL_FIELDS = {
    "season_folder",
    "search",
    "cutoff_search",
    "add_missing",
    "add_existing",
    "upgrade_existing",
    "monitor_existing",
    "ignore_cache",
}
LIBRARY_SONARR_MONITOR_VALUES = {"all", "none", "future", "missing", "existing", "pilot", "first", "latest"}
LIBRARY_SONARR_SERIES_TYPE_VALUES = {"standard", "daily", "anime"}
QS_TAUTULLI_REQUIRED_STEP_KEY = "030-tautulli"
QS_OMDB_REQUIRED_STEP_KEY = "050-omdb"
QS_MDBLIST_REQUIRED_STEP_KEY = "060-mdblist"
QS_ANIDB_REQUIRED_STEP_KEY = "100-anidb"
QS_RADARR_REQUIRED_STEP_KEY = "110-radarr"
QS_SONARR_REQUIRED_STEP_KEY = "120-sonarr"
QS_TRAKT_REQUIRED_STEP_KEY = "130-trakt"
QS_MAL_REQUIRED_STEP_KEY = "140-mal"
QS_TAUTULLI_DEP_COLLECTION_IDS = {"collection_tautulli"}
QS_TRAKT_DEP_COLLECTION_IDS = {"collection_trakt"}
QS_MAL_DEP_COLLECTION_IDS = {"collection_myanimelist"}
QS_OMDB_DEP_SOURCE_PREFIXES = ("omdb",)
QS_MDBLIST_DEP_SOURCE_PREFIXES = ("mdb",)
QS_ANIDB_DEP_SOURCE_PREFIXES = ("anidb",)
QS_MDBLIST_OVERLAY_IMAGE_VALUES = {"letterboxd", "metacritic", "rt_tomato", "rt_popcorn", "mdb"}
QS_ANIDB_OVERLAY_IMAGE_VALUES = {"anidb"}
QS_TRAKT_OVERLAY_IMAGE_VALUES = {"trakt"}
QS_MAL_OVERLAY_IMAGE_VALUES = {"mal"}
QS_RADARR_DEP_ATTRIBUTE_PREFIXES = ("radarr_add_all", "radarr_remove_by_tag")
QS_RADARR_DEP_COLLECTION_PREFIXES = ("collection_radarr_",)
QS_RADARR_DEP_TEMPLATE_COLLECTION_PREFIXES = ("radarr_add_missing_",)
QS_SONARR_DEP_ATTRIBUTE_PREFIXES = ("sonarr_add_all", "sonarr_remove_by_tag")
QS_SONARR_DEP_COLLECTION_PREFIXES = ("collection_sonarr_",)
QS_SONARR_DEP_TEMPLATE_COLLECTION_PREFIXES = ("sonarr_add_missing_",)
QS_MAL_DEP_ATTRIBUTE_OPERATIONS = {
    "mass_genre_update",
    "mass_content_rating_update",
    "mass_original_title_update",
    "mass_studio_update",
    "mass_originally_available_update",
    "mass_added_at_update",
    "mass_audience_rating_update",
    "mass_critic_rating_update",
    "mass_user_rating_update",
}
QS_MAL_DEP_ATTRIBUTE_VALUES = {"mal", "mal_english", "mal_japanese"}
QS_FINAL_VALIDATION_TTL_HOURS = 12


def _normalize_auto_sort_hubs_value(value):
    text = str(value or "").strip()
    return text or None


def _is_valid_auto_sort_hubs_value(value):
    normalized = _normalize_auto_sort_hubs_value(value)
    if normalized is None:
        return True
    return normalized in SETTINGS_AUTO_SORT_HUBS_VALUES


def build_validation_summary(errors):
    def infer_section_from_text(text):
        lowered = str(text or "").strip().lower()
        if any(token in lowered for token in ("metadata_files[", "collection_files[", "overlay_files[")):
            return "libraries"
        if "playlist_files[" in lowered:
            return "playlist_files"
        if lowered.startswith("plex"):
            return "plex"
        if lowered.startswith("tmdb"):
            return "tmdb"
        if lowered.startswith("settings"):
            return "settings"
        return "config"

    summary = []
    if not errors:
        return summary
    for err in errors[:20]:
        if isinstance(err, str):
            section = infer_section_from_text(err)
            summary.append(
                {
                    "title": err,
                    "details": "",
                    "doc_url": VALIDATION_DOCS.get(section, VALIDATION_DOC_FALLBACK),
                    "section": section,
                    "suggestions": [],
                }
            )
            continue

        if isinstance(err, dict):
            section = str(err.get("section") or infer_section_from_text(err.get("title") or err.get("message") or "") or "config")
            summary.append(
                {
                    "title": str(err.get("title") or err.get("message") or "Validation error"),
                    "details": str(err.get("details") or ""),
                    "doc_url": err.get("doc_url") or VALIDATION_DOCS.get(section, VALIDATION_DOC_FALLBACK),
                    "section": section,
                    "suggestions": list(err.get("suggestions") or []),
                }
            )
            continue

        path_parts = [str(p) for p in getattr(err, "path", [])]
        section = path_parts[0] if path_parts else ""
        path_display = ".".join(path_parts) if path_parts else (section or "config")
        doc_url = VALIDATION_DOCS.get(section, VALIDATION_DOC_FALLBACK)
        message = str(getattr(err, "message", err) or "Validation error")
        title = f"{path_display}: {message}"
        details = ""
        suggestions = []

        validator = getattr(err, "validator", "")
        validator_value = getattr(err, "validator_value", None)

        if validator == "additionalProperties":
            extras = []
            try:
                extras = list(err.params.get("additionalProperties") or [])
            except Exception:
                extras = []
            if extras:
                title = f"{section or 'config'}: Unexpected key(s)"
                details = f"Unknown keys: {', '.join(extras)}."
                for key in extras:
                    suggestion = VALIDATION_KEY_SUGGESTIONS.get(section, {}).get(key)
                    if suggestion:
                        suggestions.append(f"{key} → {suggestion}")
        elif validator == "type":
            expected = validator_value
            details = f"Expected type: {expected}."
        elif validator == "enum":
            values = validator_value or []
            details = f"Expected one of: {', '.join(map(str, values))}."
        elif validator == "minimum":
            details = f"Minimum allowed: {validator_value}."
        elif validator == "maximum":
            details = f"Maximum allowed: {validator_value}."
        elif validator == "pattern":
            details = "Value does not match the expected format."

        summary.append(
            {
                "title": title,
                "details": details,
                "doc_url": doc_url,
                "section": section or "config",
                "suggestions": suggestions,
            }
        )

    return summary


def _normalize_status(value):
    status = str(value or "").strip().lower()
    if status in ("unknown", "ok", "warn", "error"):
        return status
    return "warn"


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_truthy_setting_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"", "0", "false", "none", "null", "[]", "{}"}:
            return False
        return True
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return bool(value)


def _parse_json_array(value):
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return []
    text = value.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _parse_metadata_file_entries(value):
    if isinstance(value, list):
        raw_entries = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            raw_entries = json.loads(text)
        except (TypeError, ValueError):
            return None
    else:
        return []

    if not isinstance(raw_entries, list):
        return None

    entries = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip().lower()
        location = str(entry.get("location") or "").strip()
        validated = helpers.booler(entry.get("validated"))
        if not entry_type and not location:
            continue
        parsed_entry = {"type": entry_type, "location": location}
        if validated:
            parsed_entry["validated"] = True
        entries.append(parsed_entry)
    return entries


def _parse_collection_file_entries(value):
    if isinstance(value, list):
        raw_entries = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            raw_entries = json.loads(text)
        except (TypeError, ValueError):
            return None
    else:
        return []

    if not isinstance(raw_entries, list):
        return None

    entries = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip().lower()
        location = str(entry.get("location") or "").strip()
        validated = helpers.booler(entry.get("validated"))
        if not entry_type and not location:
            continue
        parsed_entry = {"type": entry_type, "location": location}
        if validated:
            parsed_entry["validated"] = True
        entries.append(parsed_entry)
    return entries


def _parse_overlay_file_entries(value):
    if isinstance(value, list):
        raw_entries = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            raw_entries = json.loads(text)
        except (TypeError, ValueError):
            return None
    else:
        return []

    if not isinstance(raw_entries, list):
        return None

    entries = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip().lower()
        location = str(entry.get("location") or "").strip()
        validated = helpers.booler(entry.get("validated"))
        if not entry_type and not location:
            continue
        parsed_entry = {"type": entry_type, "location": location}
        if validated:
            parsed_entry["validated"] = True
        entries.append(parsed_entry)
    return entries


LIBRARY_FILE_KINDS = ("metadata_files", "collection_files", "overlay_files")
LOCAL_LIBRARY_FILE_TYPES = {"file", "folder"}
LIBRARY_FILE_VALIDATORS = {
    "metadata_files": (
        "metadata_file_type",
        "metadata_file_location",
        validations.validate_metadata_file_payload,
    ),
    "collection_files": (
        "collection_file_type",
        "collection_file_location",
        validations.validate_collection_file_payload,
    ),
    "overlay_files": (
        "overlay_file_type",
        "overlay_file_location",
        validations.validate_overlay_file_payload,
    ),
}
LIBRARY_FILE_PARSE_FUNCTIONS = {
    "metadata_files": _parse_metadata_file_entries,
    "collection_files": _parse_collection_file_entries,
    "overlay_files": _parse_overlay_file_entries,
}


def _format_library_file_validation_error(lib_id, kind, idx, message, entry, details=None):
    location = str((entry or {}).get("location") or "").strip()
    detail_text = ""
    if isinstance(details, dict):
        detail_text = str(details.get("message") or "").strip()
    if location:
        path_label = "Path"
        if detail_text and detail_text not in message:
            return f"{lib_id} {kind}[{idx}]: {message} {detail_text} {path_label}: {location}"
        return f"{lib_id} {kind}[{idx}]: {message} {path_label}: {location}"
    if detail_text and detail_text not in message:
        return f"{lib_id} {kind}[{idx}]: {message} {detail_text}"
    return f"{lib_id} {kind}[{idx}]: {message}"


def _safe_external_artifact_slug(value, fallback="artifact"):
    safe = secure_filename(str(value or "").strip())
    return safe or fallback


def _managed_library_folder_slug(source_path, kind):
    raw_name = str(getattr(source_path, "name", "") or "").strip().lower()
    folder_name = _safe_external_artifact_slug(getattr(source_path, "name", ""), "folder")
    if raw_name in set(LIBRARY_FILE_KINDS):
        parent_name = _safe_external_artifact_slug(getattr(source_path.parent, "name", ""), "")
        if parent_name:
            return f"{parent_name}_{folder_name}"
    return folder_name


def _managed_library_config_root(config_name):
    config_slug = helpers.require_config_name_for_storage(config_name, context="Managed library artifact paths")
    return (Path(helpers.CONFIG_DIR) / config_slug).resolve()


def _managed_library_file_root(kind, config_name):
    return (_managed_library_config_root(config_name) / kind).resolve()


def _parse_managed_library_relative_path(path_value):
    raw = str(path_value or "").strip().replace("\\", "/")
    if not raw:
        return None
    parts = [part for part in raw.split("/") if part]
    if not parts:
        return None
    has_config_prefix = parts[0] == "config"
    if has_config_prefix:
        parts = parts[1:]
    if len(parts) >= 3 and parts[1] in LIBRARY_FILE_KINDS:
        return {
            "layout": "config_first",
            "config_name": parts[0],
            "kind": parts[1],
            "remainder": parts[2:],
            "has_config_prefix": has_config_prefix,
            "parts": parts,
        }
    if len(parts) >= 3 and parts[0] in LIBRARY_FILE_KINDS:
        return {
            "layout": "type_first",
            "config_name": parts[1],
            "kind": parts[0],
            "remainder": parts[2:],
            "has_config_prefix": has_config_prefix,
            "parts": parts,
        }
    return None


def _normalized_managed_library_relative_path(path_value):
    info = _parse_managed_library_relative_path(path_value)
    if not info:
        return None
    return Path(info["config_name"], info["kind"], *info["remainder"]).as_posix()


def _is_bundled_library_archive_member(path_value):
    return _normalized_managed_library_relative_path(str(path_value or "").replace("\\", "/").lstrip("/")) is not None


def _yaml_path_suffix(path_value):
    return str(path_value or "").strip().lower().endswith((".yml", ".yaml"))


def _normalize_bundle_member_name(path_value):
    normalized = str(path_value or "").replace("\\", "/").lstrip("/")
    return "/".join(part for part in normalized.split("/") if part)


def _is_allowed_bundle_member(path_value):
    normalized = _normalize_bundle_member_name(path_value)
    if not normalized:
        return True
    lowered = normalized.lower()
    if _is_bundled_library_archive_member(normalized):
        return _yaml_path_suffix(normalized)
    if _yaml_path_suffix(normalized):
        return True
    if lowered.endswith((".ttf", ".otf")):
        return True
    if lowered == "readme.txt":
        return True
    return False


def _dump_yaml_text(data):
    buffer = io.StringIO()
    YAML().dump(data, buffer)
    return buffer.getvalue()


def _resolve_local_library_source(location):
    raw = str(location or "").strip()
    if not raw:
        return None
    expanded = Path(os.path.expandvars(os.path.expanduser(raw)))
    if expanded.is_absolute():
        try:
            return expanded.resolve()
        except OSError:
            return expanded
    managed_info = _parse_managed_library_relative_path(expanded)
    if managed_info:
        if managed_info["layout"] == "config_first":
            managed_relative = Path(managed_info["config_name"], managed_info["kind"], *managed_info["remainder"])
        else:
            managed_relative = Path(*managed_info["parts"])
        try:
            return (Path(helpers.CONFIG_DIR) / managed_relative).resolve()
        except OSError:
            return Path(helpers.CONFIG_DIR) / managed_relative
    normalized_parts = [part for part in str(expanded).replace("\\", "/").split("/") if part]
    if normalized_parts and normalized_parts[0] in LIBRARY_FILE_KINDS:
        try:
            return (Path(helpers.CONFIG_DIR) / expanded).resolve()
        except OSError:
            return Path(helpers.CONFIG_DIR) / expanded
    try:
        return (Path.cwd() / expanded).resolve()
    except OSError:
        return Path.cwd() / expanded


def _managed_bundle_location_for_path(path):
    config_root = Path(helpers.CONFIG_DIR).resolve()
    try:
        relative = Path(path).resolve().relative_to(config_root)
    except Exception:
        return None
    normalized_relative = _normalized_managed_library_relative_path(Path(*relative.parts).as_posix())
    if not normalized_relative:
        return None
    info = _parse_managed_library_relative_path(normalized_relative)
    if not info or info["layout"] != "config_first":
        return None
    return normalized_relative


def _display_library_managed_location(location):
    raw = str(location or "").strip().replace("\\", "/")
    if not raw:
        return raw
    normalized_relative = _normalized_managed_library_relative_path(raw)
    if normalized_relative:
        return Path("config", *normalized_relative.split("/")).as_posix()
    return raw


def _validate_library_file_entry(kind, entry):
    validator_info = LIBRARY_FILE_VALIDATORS.get(kind)
    if not validator_info:
        return False, f"Unsupported library file kind: {kind}", {}
    type_key, location_key, validator = validator_info
    payload = {
        type_key: str((entry or {}).get("type") or "").strip().lower(),
        location_key: str((entry or {}).get("location") or "").strip(),
    }
    return validations._normalize_metadata_validation_result(validator(payload))


def _remove_managed_path(path, root):
    resolved_root = Path(root).resolve()
    resolved_path = Path(path).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except Exception as exc:
        raise RuntimeError(f"Refusing to remove unmanaged path: {resolved_path}") from exc
    if resolved_path.is_dir():
        shutil.rmtree(resolved_path, ignore_errors=False)
    elif resolved_path.exists():
        resolved_path.unlink()


def _copy_library_artifact_to_managed_store(kind, entry_type, location, config_name, library_scope, force_clone_managed=False):
    source_path = _resolve_local_library_source(location)
    if source_path is None:
        raise RuntimeError("Path is required.")

    managed_location = _managed_bundle_location_for_path(source_path)
    if managed_location and not force_clone_managed:
        return managed_location

    managed_root = _managed_library_file_root(kind, config_name)
    library_slug = _safe_external_artifact_slug(library_scope, "library")
    source_token = str(source_path).replace("\\", "/").lower()
    digest = hashlib.sha1(source_token.encode("utf-8", errors="ignore")).hexdigest()[:10]
    target_dir = managed_root / library_slug
    target_dir.mkdir(parents=True, exist_ok=True)

    if entry_type == "file":
        stem = _safe_external_artifact_slug(source_path.stem, "file")
        suffix = source_path.suffix or ".yml"
        target_path = (target_dir / f"{stem}_{digest}{suffix}").resolve()
        if source_path != target_path:
            shutil.copy2(source_path, target_path)
    else:
        folder_name = _managed_library_folder_slug(source_path, kind)
        target_path = (target_dir / f"{folder_name}_{digest}").resolve()
        if source_path != target_path:
            if target_path.exists():
                _remove_managed_path(target_path, managed_root)
            shutil.copytree(source_path, target_path)

    try:
        relative = target_path.relative_to(Path(helpers.CONFIG_DIR).resolve())
    except Exception as exc:
        raise RuntimeError(f"Managed artifact path escaped config directory: {target_path}") from exc
    return Path(*relative.parts).as_posix()


def _normalize_library_external_entry(kind, entry, config_name, library_scope, validate_local=True, force_clone_managed=False, require_managed_context=False):
    parsed_entry = dict(entry) if isinstance(entry, dict) else {}
    entry_type = str(parsed_entry.get("type") or "").strip().lower()
    location = str(parsed_entry.get("location") or "").strip()
    is_validated = helpers.booler(parsed_entry.get("validated"))
    if entry_type not in {"file", "folder", "url", "git", "repo"} or not location:
        return parsed_entry, False, None
    if entry_type in LOCAL_LIBRARY_FILE_TYPES and require_managed_context:
        if not str(config_name or "").strip():
            return None, False, "Managed library files require an explicit config name."
        if not str(library_scope or "").strip():
            return None, False, "Managed library files require a library scope."
    if entry_type not in LOCAL_LIBRARY_FILE_TYPES or not config_name or not library_scope:
        normalized_entry = {"type": entry_type, "location": location}
        if is_validated:
            normalized_entry["validated"] = True
        return normalized_entry, False, None

    if validate_local:
        valid, message, _details = _validate_library_file_entry(kind, {"type": entry_type, "location": location})
        if not valid:
            return None, False, message

    try:
        normalized_location = _copy_library_artifact_to_managed_store(
            kind,
            entry_type,
            location,
            config_name,
            library_scope,
            force_clone_managed=force_clone_managed,
        )
    except Exception as exc:
        return None, False, f"Unable to organize {kind}: {exc}"

    display_location = _display_library_managed_location(normalized_location)
    changed = display_location != location
    normalized_entry = {"type": entry_type, "location": display_location}
    if is_validated:
        normalized_entry["validated"] = True
    return normalized_entry, changed, None


def _clone_library_file_entries_for_target(kind, raw_value, config_name, target_library_id):
    parser = LIBRARY_FILE_PARSE_FUNCTIONS.get(kind)
    if not parser:
        return raw_value
    entries = parser(raw_value)
    if entries is None:
        return raw_value
    cloned_entries = []
    for idx, entry in enumerate(entries, start=1):
        normalized_entry, _changed, entry_error = _normalize_library_external_entry(
            kind,
            entry,
            config_name,
            target_library_id,
            validate_local=False,
            force_clone_managed=True,
            require_managed_context=True,
        )
        if entry_error:
            raise RuntimeError(_format_library_file_validation_error(target_library_id, kind, idx, entry_error, entry))
        cloned_entries.append(normalized_entry if normalized_entry is not None else entry)
    return json.dumps(cloned_entries, ensure_ascii=True)


def _normalize_library_file_entries_payload(libraries_data, config_name, validate_local=True):
    if not isinstance(libraries_data, dict):
        return {}, [], False

    normalized = dict(libraries_data)
    errors = []
    changed = False
    for kind in LIBRARY_FILE_KINDS:
        parser = LIBRARY_FILE_PARSE_FUNCTIONS[kind]
        suffix = f"-{kind}"
        for key, raw_value in list(normalized.items()):
            if not isinstance(key, str) or not key.endswith(suffix):
                continue
            library_scope = key[: -len(suffix)]
            entries = parser(raw_value)
            if entries is None:
                errors.append(f"{library_scope}: {kind} must be a valid list.")
                continue
            new_entries = []
            for idx, entry in enumerate(entries, start=1):
                normalized_entry, entry_changed, entry_error = _normalize_library_external_entry(
                    kind,
                    entry,
                    config_name,
                    library_scope,
                    validate_local=validate_local,
                    require_managed_context=True,
                )
                if entry_error:
                    errors.append(_format_library_file_validation_error(library_scope, kind, idx, entry_error, entry))
                    continue
                if normalized_entry:
                    new_entries.append(normalized_entry)
                changed = changed or bool(entry_changed)
            normalized[key] = json.dumps(new_entries, ensure_ascii=True)
    return normalized, errors, changed


def _normalize_imported_libraries_payload(payload_section, config_name):
    if not isinstance(payload_section, dict):
        return payload_section, []
    libraries_data = payload_section.get("libraries") if isinstance(payload_section.get("libraries"), dict) else payload_section
    if not isinstance(libraries_data, dict):
        return payload_section, []
    normalized, errors, _changed = _normalize_library_file_entries_payload(libraries_data, config_name, validate_local=True)
    if errors:
        return None, errors
    updated = dict(payload_section)
    if "libraries" in updated and isinstance(updated.get("libraries"), dict):
        updated["libraries"] = normalized
    else:
        updated = normalized
    return updated, []


def _rewrite_bundle_library_paths(config_data, bundle_root):
    if not isinstance(config_data, dict):
        return config_data
    libraries = config_data.get("libraries")
    if not isinstance(libraries, dict):
        return config_data
    root = Path(bundle_root).resolve()
    for lib_cfg in libraries.values():
        if not isinstance(lib_cfg, dict):
            continue
        for kind in LIBRARY_FILE_KINDS:
            entries = lib_cfg.get(kind)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                for entry_type in LOCAL_LIBRARY_FILE_TYPES:
                    location = entry.get(entry_type)
                    if not location:
                        continue
                    raw_location = str(location).strip()
                    candidate = root / Path(raw_location)
                    if not candidate.exists():
                        normalized_relative = _normalized_managed_library_relative_path(raw_location)
                        if normalized_relative:
                            candidate = root / Path(normalized_relative)
                    if not candidate.exists():
                        continue
                    entry[entry_type] = str(candidate.resolve())
                    break
    return config_data


def _normalize_generated_config_library_files(config_data, config_name):
    if not isinstance(config_data, dict):
        return config_data, False, []
    libraries = config_data.get("libraries")
    if not isinstance(libraries, dict):
        return config_data, False, []

    changed = False
    errors = []
    for library_name, lib_cfg in libraries.items():
        if not isinstance(lib_cfg, dict):
            continue
        for kind in LIBRARY_FILE_KINDS:
            entries = lib_cfg.get(kind)
            if not isinstance(entries, list):
                continue
            new_entries = []
            for idx, entry in enumerate(entries, start=1):
                if not isinstance(entry, dict):
                    new_entries.append(entry)
                    continue
                handled = False
                for entry_type in LOCAL_LIBRARY_FILE_TYPES:
                    location = entry.get(entry_type)
                    if not location:
                        continue
                    normalized_entry, entry_changed, entry_error = _normalize_library_external_entry(
                        kind,
                        {"type": entry_type, "location": location},
                        config_name,
                        library_name,
                        validate_local=True,
                        require_managed_context=True,
                    )
                    if entry_error:
                        errors.append(
                            _format_library_file_validation_error(
                                library_name,
                                kind,
                                idx,
                                entry_error,
                                {"type": entry_type, "location": location},
                            )
                        )
                        new_entries.append(entry)
                    else:
                        new_entries.append({entry_type: normalized_entry["location"]})
                        changed = changed or bool(entry_changed)
                    handled = True
                    break
                if not handled:
                    new_entries.append(entry)
            lib_cfg[kind] = new_entries
    return config_data, changed, errors


def _iter_bundle_artifacts(config_data):
    seen = set()
    if not isinstance(config_data, dict):
        return []
    libraries = config_data.get("libraries")
    if not isinstance(libraries, dict):
        return []
    artifacts = []
    for lib_cfg in libraries.values():
        if not isinstance(lib_cfg, dict):
            continue
        for kind in LIBRARY_FILE_KINDS:
            entries = lib_cfg.get(kind)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                for entry_type in LOCAL_LIBRARY_FILE_TYPES:
                    location = entry.get(entry_type)
                    if not location:
                        continue
                    raw_location = str(location).strip()
                    if not raw_location:
                        continue
                    source_path = _resolve_local_library_source(raw_location)
                    if source_path is None:
                        continue
                    if not source_path.exists():
                        continue
                    archive_path = _managed_bundle_location_for_path(source_path)
                    if not archive_path:
                        archive_path = _normalized_managed_library_relative_path(raw_location) or Path(raw_location).as_posix()
                    dedupe_key = (str(source_path), archive_path)
                    if dedupe_key in seen:
                        break
                    seen.add(dedupe_key)
                    artifacts.append(
                        {
                            "source": source_path,
                            "archive": archive_path,
                            "type": entry_type,
                        }
                    )
                    break
    return artifacts


def _bundle_write_path(zf, archive_name, source_path, redacted=False):
    source_path = Path(source_path)
    archive_name = Path(archive_name).as_posix()
    if redacted and source_path.is_file() and _yaml_path_suffix(source_path.name):
        text = source_path.read_text(encoding="utf-8", errors="replace")
        zf.writestr(archive_name, helpers.redact_sensitive_data(text))
        return
    zf.write(source_path, archive_name)


def _bundle_write_artifact(zf, artifact, redacted=False):
    source_path = Path((artifact or {}).get("source", ""))
    archive_path = Path(str((artifact or {}).get("archive", "")).replace("\\", "/"))
    if not source_path.exists() or not str(archive_path):
        return
    if source_path.is_dir():
        for child in sorted(source_path.rglob("*"), key=lambda item: item.as_posix().lower()):
            if not child.is_file():
                continue
            relative_child = child.relative_to(source_path)
            _bundle_write_path(zf, (archive_path / relative_child).as_posix(), child, redacted=redacted)
        return
    _bundle_write_path(zf, archive_path.as_posix(), source_path, redacted=redacted)


def _is_blank_override_value(value):
    if value is None:
        return True
    if isinstance(value, str):
        text = value.strip()
        return text == "" or text.lower() == "none"
    return False


def _coerce_override_bool(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "on"}:
            return True
        if lowered in {"false", "no", "0", "off"}:
            return False
    return None


def _library_service_definition(service_name):
    if service_name == "radarr":
        return {
            "template_key": "110-radarr",
            "section_name": "radarr",
            "fields": LIBRARY_RADARR_FIELDS,
            "bool_fields": LIBRARY_RADARR_BOOL_FIELDS,
            "label": "Radarr",
        }
    if service_name == "sonarr":
        return {
            "template_key": "120-sonarr",
            "section_name": "sonarr",
            "fields": LIBRARY_SONARR_FIELDS,
            "bool_fields": LIBRARY_SONARR_BOOL_FIELDS,
            "label": "Sonarr",
        }
    return None


def _extract_library_service_overrides(libraries_data, library_id, service_name):
    definition = _library_service_definition(service_name)
    if not definition or not isinstance(libraries_data, dict):
        return {}
    overrides = {}
    for field in definition["fields"]:
        value = libraries_data.get(f"{library_id}-attribute_{service_name}_{field}")
        if field in definition["bool_fields"]:
            bool_value = _coerce_override_bool(value)
            if bool_value is not None:
                overrides[field] = bool_value
            continue
        if not _is_blank_override_value(value):
            overrides[field] = str(value).strip() if isinstance(value, str) else value
    return overrides


def _validate_library_service_overrides(library_id, libraries_data, force_validate=False):
    service_name = "radarr" if str(library_id or "").startswith("mov-library_") else "sonarr" if str(library_id or "").startswith("sho-library_") else None
    definition = _library_service_definition(service_name)
    if not definition:
        return {"valid": True, "skipped": True, "service": None, "errors": []}

    overrides = _extract_library_service_overrides(libraries_data, library_id, service_name)
    if not overrides and not force_validate:
        return {"valid": True, "skipped": True, "service": service_name, "overrides": {}, "errors": []}

    settings = persistence.retrieve_settings(definition["template_key"]) or {}
    global_section = settings.get(definition["section_name"], {}) if isinstance(settings, dict) else {}
    if not isinstance(global_section, dict):
        global_section = {}

    effective_url = overrides.get("url") or global_section.get("url")
    effective_token = overrides.get("token") or global_section.get("token")
    library_name = libraries_data.get(f"{library_id}-library") if isinstance(libraries_data, dict) else None
    display_name = str(library_name or library_id or "").strip() or str(library_id or "")
    scoped_label = f"{display_name} {definition['label']}"

    if _is_blank_override_value(effective_url) or _is_blank_override_value(effective_token):
        return {
            "valid": False,
            "skipped": False,
            "service": service_name,
            "overrides": overrides,
            "errors": [f"{scoped_label}: URL and token are required after applying overrides."],
        }

    if service_name == "radarr":
        response_data, _status = validations.validate_radarr_payload({"url": effective_url, "token": effective_token})
    else:
        response_data, _status = validations.validate_sonarr_payload({"url": effective_url, "token": effective_token})

    if not response_data.get("valid"):
        return {
            "valid": False,
            "skipped": False,
            "service": service_name,
            "overrides": overrides,
            "errors": [f"{scoped_label}: {response_data.get('error') or 'Validation failed.'}"],
        }

    errors = []
    root_folders = response_data.get("root_folders", []) if isinstance(response_data, dict) else []
    quality_profiles = response_data.get("quality_profiles", []) if isinstance(response_data, dict) else []
    language_profiles = response_data.get("language_profiles", []) if isinstance(response_data, dict) else []

    root_folder_names = {str(item.get("path") or "").strip() for item in root_folders if isinstance(item, dict)}
    quality_profile_names = {str(item.get("name") or "").strip() for item in quality_profiles if isinstance(item, dict)}
    language_profile_names = {str(item.get("name") or "").strip() for item in language_profiles if isinstance(item, dict)}

    root_folder_path = overrides.get("root_folder_path")
    if root_folder_path and root_folder_path not in root_folder_names:
        errors.append(f"{scoped_label}: unknown root folder path '{root_folder_path}'.")

    quality_profile = overrides.get("quality_profile")
    if quality_profile and quality_profile not in quality_profile_names:
        errors.append(f"{scoped_label}: unknown quality profile '{quality_profile}'.")

    if service_name == "radarr":
        availability = overrides.get("availability")
        if availability and availability not in LIBRARY_RADARR_AVAILABILITY_VALUES:
            errors.append(f"{scoped_label}: unsupported availability '{availability}'.")
    else:
        language_profile = overrides.get("language_profile")
        if language_profile and language_profile not in language_profile_names:
            errors.append(f"{scoped_label}: unknown language profile '{language_profile}'.")

        series_type = overrides.get("series_type")
        if series_type and series_type not in LIBRARY_SONARR_SERIES_TYPE_VALUES:
            errors.append(f"{scoped_label}: unsupported series_type '{series_type}'.")

        monitor_value = overrides.get("monitor")
        if monitor_value and monitor_value not in LIBRARY_SONARR_MONITOR_VALUES:
            errors.append(f"{scoped_label}: unsupported monitor value '{monitor_value}'.")

    return {
        "valid": not errors,
        "skipped": False,
        "service": service_name,
        "overrides": overrides,
        "errors": errors,
        "root_folders": root_folders,
        "quality_profiles": quality_profiles,
        "language_profiles": language_profiles,
    }


def _validate_library_metadata_files(libraries_data, selected_library_ids):
    if not isinstance(libraries_data, dict):
        return []

    errors = []
    for lib_id in selected_library_ids or []:
        raw_value = libraries_data.get(f"{lib_id}-metadata_files")
        if raw_value in [None, "", "[]"]:
            continue

        entries = _parse_metadata_file_entries(raw_value)
        if entries is None:
            errors.append(f"{lib_id}: metadata_files must be a valid list.")
            continue

        for idx, entry in enumerate(entries, start=1):
            valid, message, details = validations._normalize_metadata_validation_result(
                validations.validate_metadata_file_payload(
                    {
                        "metadata_file_type": entry.get("type"),
                        "metadata_file_location": entry.get("location"),
                    }
                )
            )
            if not valid:
                errors.append(_format_library_file_validation_error(lib_id, "metadata_files", idx, message, entry, details))

    return errors


def _validate_library_collection_files(libraries_data, selected_library_ids):
    if not isinstance(libraries_data, dict):
        return []

    errors = []
    for lib_id in selected_library_ids or []:
        raw_value = libraries_data.get(f"{lib_id}-collection_files")
        if raw_value in [None, "", "[]"]:
            continue

        entries = _parse_collection_file_entries(raw_value)
        if entries is None:
            errors.append(f"{lib_id}: collection_files must be a valid list.")
            continue

        for idx, entry in enumerate(entries, start=1):
            valid, message, details = validations._normalize_metadata_validation_result(
                validations.validate_collection_file_payload(
                    {
                        "collection_file_type": entry.get("type"),
                        "collection_file_location": entry.get("location"),
                    }
                )
            )
            if not valid:
                errors.append(_format_library_file_validation_error(lib_id, "collection_files", idx, message, entry, details))

    return errors


def _validate_library_overlay_files(libraries_data, selected_library_ids):
    if not isinstance(libraries_data, dict):
        return []

    errors = []
    for lib_id in selected_library_ids or []:
        raw_value = libraries_data.get(f"{lib_id}-overlay_files")
        if raw_value in [None, "", "[]"]:
            continue

        entries = _parse_overlay_file_entries(raw_value)
        if entries is None:
            errors.append(f"{lib_id}: overlay_files must be a valid list.")
            continue

        for idx, entry in enumerate(entries, start=1):
            valid, message, details = validations._normalize_metadata_validation_result(
                validations.validate_overlay_file_payload(
                    {
                        "overlay_file_type": entry.get("type"),
                        "overlay_file_location": entry.get("location"),
                    }
                )
            )
            if not valid:
                errors.append(_format_library_file_validation_error(lib_id, "overlay_files", idx, message, entry, details))

    return errors


def _validate_library_auto_sort_hubs(libraries_data, selected_library_ids):
    if not isinstance(libraries_data, dict):
        return []

    errors = []
    allowed_values = ", ".join(sorted(SETTINGS_AUTO_SORT_HUBS_VALUES))
    for lib_id in selected_library_ids or []:
        value = libraries_data.get(f"{lib_id}-top_level_auto_sort_hubs")
        if _is_valid_auto_sort_hubs_value(value):
            continue
        library_name = libraries_data.get(f"{lib_id}-library") or lib_id
        errors.append(f"{library_name}: auto_sort_hubs must be one of: {allowed_values}")

    return errors


def _validate_and_organize_library_file_request(kind, data, type_key, location_key):
    validator_info = LIBRARY_FILE_VALIDATORS.get(kind)
    if not validator_info:
        return jsonify({"valid": False, "error": f"Unsupported library file kind: {kind}"}), 400

    _payload_type_key, _payload_location_key, validator = validator_info
    valid, message, details = validations._normalize_metadata_validation_result(validator(data))
    if not valid:
        payload = {"valid": False, "error": message}
        if details.get("message") or isinstance(details.get("files"), list):
            payload["error_details"] = {
                "text": details.get("message") or message,
                "files": details.get("files") if isinstance(details.get("files"), list) else [],
            }
        if isinstance(details.get("files"), list):
            payload["files"] = details["files"]
        return jsonify(payload), 400

    payload = {"valid": True}
    if details.get("message"):
        payload["message"] = details["message"]
    if "validated_files" in details:
        payload["validated_files"] = details["validated_files"]
    if isinstance(details.get("files"), list):
        payload["files"] = details["files"]

    config_name = _resolve_request_config_name(data if isinstance(data, dict) else {})
    library_scope = str((data or {}).get("library_id") or (data or {}).get("library_scope") or "").strip()
    entry_type = str((data or {}).get(type_key) or "").strip().lower()
    entry_location = str((data or {}).get(location_key) or "").strip()
    if entry_type in LOCAL_LIBRARY_FILE_TYPES and entry_location and config_name and library_scope:
        normalized_entry, changed, normalize_error = _normalize_library_external_entry(
            kind,
            {"type": entry_type, "location": entry_location},
            config_name,
            library_scope,
            validate_local=False,
        )
        if normalize_error:
            return jsonify({"valid": False, "error": normalize_error}), 400
        payload["normalized_location"] = normalized_entry["location"]
        payload["organized"] = bool(changed)
        if changed:
            payload["message"] = payload.get("message") or f"Source validated and organized into Quickstart {kind}."

    return jsonify(payload)


def _selected_library_ids_from_libraries_data(libraries_data):
    if not isinstance(libraries_data, dict):
        return []

    return [
        key[: -len("-library")]
        for key, value in libraries_data.items()
        if isinstance(key, str) and key.startswith(("mov-library_", "sho-library_")) and key.endswith("-library") and _is_truthy_setting_value(value)
    ]


def _library_prefix_from_key(key):
    if not isinstance(key, str) or not key.startswith(("mov-library_", "sho-library_")):
        return None
    for marker in (
        "-movie-template_",
        "-show-template_",
        "-season-template_",
        "-episode-template_",
        "-movie-overlay_",
        "-show-overlay_",
        "-season-overlay_",
        "-episode-overlay_",
    ):
        if marker in key:
            return key.split(marker, 1)[0]
    if "-template_" in key:
        return key.split("-template_", 1)[0]
    if "-attribute_" in key:
        return key.split("-attribute_", 1)[0]
    if "-collection_" in key:
        return key.split("-collection_", 1)[0]
    if "-overlay_" in key:
        return key.split("-overlay_", 1)[0]
    if "-top_level_" in key:
        return key.split("-top_level_", 1)[0]
    if key.endswith("-library"):
        return key[: -len("-library")]
    return None


def _active_library_prefixes(libraries_data):
    if not isinstance(libraries_data, dict):
        return set()

    active_prefixes = set()
    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        if not key.endswith("-library"):
            continue
        prefix = _library_prefix_from_key(key)
        if prefix and _is_truthy_setting_value(raw_value):
            active_prefixes.add(prefix)
    return active_prefixes


def _dependency_reason_label(libraries_data, prefix):
    library_name = libraries_data.get(f"{prefix}-library") if isinstance(libraries_data, dict) else None
    if isinstance(library_name, str) and library_name.strip():
        return library_name.strip()
    return prefix


def _append_dependency_reason(reasons, seen, libraries_data, prefix, detail):
    label = _dependency_reason_label(libraries_data, prefix)
    reason = f"{label}: {detail}"
    normalized = reason.lower()
    if normalized in seen:
        return
    seen.add(normalized)
    reasons.append(reason)


def _libraries_data_collection_dependency_reasons(libraries_data, collection_ids, detail):
    if not isinstance(libraries_data, dict):
        return []

    active_prefixes = _active_library_prefixes(libraries_data)
    reasons = []
    seen = set()

    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        if not key or "-collection_" not in key or not _is_truthy_setting_value(raw_value):
            continue

        prefix = _library_prefix_from_key(key)
        if prefix and prefix not in active_prefixes:
            continue

        collection_id = f"collection_{key.rsplit('-collection_', 1)[1]}"
        if collection_id in collection_ids:
            _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)

    return reasons


def _libraries_data_template_collection_dependency_reasons(libraries_data, child_ids, detail):
    if not isinstance(libraries_data, dict):
        return []

    active_prefixes = _active_library_prefixes(libraries_data)
    reasons = []
    seen = set()
    normalized_child_ids = tuple(str(child_id or "").strip().lower() for child_id in child_ids if str(child_id or "").strip())
    if not normalized_child_ids:
        return reasons

    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        if not key or "-template_collection_" not in key or not _is_truthy_setting_value(raw_value):
            continue

        prefix = _library_prefix_from_key(key)
        if prefix and prefix not in active_prefixes:
            continue

        matched_child_id = None
        for child_id in normalized_child_ids:
            if re.search(rf"-template_collection_[a-z0-9_]+_{re.escape(child_id)}$", key):
                matched_child_id = child_id
                break
        if matched_child_id:
            _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)

    return reasons


def _libraries_data_service_dependency_reasons(libraries_data, attribute_prefixes, collection_prefixes, template_collection_prefixes=()):
    if not isinstance(libraries_data, dict):
        return []

    active_prefixes = _active_library_prefixes(libraries_data)
    reasons = []
    seen = set()
    normalized_attribute_prefixes = tuple(str(prefix or "").strip().lower() for prefix in attribute_prefixes if str(prefix or "").strip())
    normalized_collection_prefixes = tuple(str(prefix or "").strip().lower() for prefix in collection_prefixes if str(prefix or "").strip())
    normalized_template_collection_prefixes = tuple(str(prefix or "").strip().lower() for prefix in template_collection_prefixes if str(prefix or "").strip())

    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        if not key or not _is_truthy_setting_value(raw_value):
            continue

        prefix = _library_prefix_from_key(key)
        if prefix and prefix not in active_prefixes:
            continue

        if "-attribute_" in key:
            attribute_key = key.split("-attribute_", 1)[1]
            matched_attribute = next(
                (attr_prefix for attr_prefix in normalized_attribute_prefixes if attribute_key == attr_prefix or attribute_key.startswith(f"{attr_prefix}_")),
                None,
            )
            if matched_attribute:
                detail = f"{matched_attribute} configured" if attribute_key.endswith("_custom") else f"{attribute_key} enabled"
                _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)
                continue

        if "-collection_" in key:
            collection_id = f"collection_{key.rsplit('-collection_', 1)[1]}"
            if any(collection_id.startswith(collection_prefix) for collection_prefix in normalized_collection_prefixes):
                detail = f"{collection_id} enabled"
                _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)
                continue

        if "-template_collection_" in key:
            matched_child_key = None
            for template_prefix in normalized_template_collection_prefixes:
                match = re.search(
                    rf"-template_collection_[a-z0-9_]+_({re.escape(template_prefix)}[a-z0-9_]*)$",
                    key,
                )
                if match:
                    matched_child_key = match.group(1)
                    break
            if matched_child_key:
                detail = f"{matched_child_key} enabled"
                _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)

    return reasons


def _libraries_data_overlay_rating_dependency_reasons(libraries_data, image_values):
    if not isinstance(libraries_data, dict):
        return []

    active_prefixes = _active_library_prefixes(libraries_data)
    reasons = []
    seen = set()
    normalized_images = {str(value or "").strip().lower() for value in image_values if str(value or "").strip()}
    if not normalized_images:
        return reasons

    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        selected_image = str(raw_value or "").strip().lower()
        if selected_image not in normalized_images:
            continue

        match = re.match(
            r"^(?P<prefix>(?:mov|sho)-library_[a-z0-9_]+)-(?P<builder>movie|show|season|episode)-template_overlay_ratings\[rating[123]_image\]$",
            key,
        )
        if not match:
            continue

        prefix = match.group("prefix")
        builder = match.group("builder")
        if prefix not in active_prefixes:
            continue

        overlay_toggle_key = f"{prefix}-{builder}-overlay_ratings"
        if not _is_truthy_setting_value(libraries_data.get(overlay_toggle_key)):
            continue

        detail = f"{builder} ratings overlay uses {selected_image}"
        _append_dependency_reason(reasons, seen, libraries_data, prefix, detail)

    return reasons


def _attribute_dependency_source_reasons(libraries_data, source_prefixes):
    if not isinstance(libraries_data, dict):
        return []

    active_prefixes = _active_library_prefixes(libraries_data)
    reasons = []
    seen = set()
    normalized_prefixes = tuple(str(prefix or "").strip().lower() for prefix in source_prefixes if str(prefix or "").strip())
    if not normalized_prefixes:
        return reasons

    def matches_source(source_value):
        normalized = str(source_value or "").strip().lower()
        if not normalized:
            return False
        return any(normalized == prefix or normalized.startswith(f"{prefix}_") for prefix in normalized_prefixes)

    def extract_operation_and_source(key):
        attr_body = key.split("-attribute_", 1)[1] if "-attribute_" in key else ""
        if not attr_body or attr_body.endswith("_order"):
            return None, None
        parts = [part for part in attr_body.split("_") if part]
        if len(parts) < 3:
            return None, None
        for split_index in range(2, len(parts)):
            operation = "_".join(parts[:split_index])
            source_value = "_".join(parts[split_index:])
            if operation.startswith("mass_") and matches_source(source_value):
                return operation, source_value
        return None, None

    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        if not key or "-attribute_" not in key:
            continue

        prefix = _library_prefix_from_key(key)
        if prefix and prefix not in active_prefixes:
            continue

        operation, source_value = extract_operation_and_source(key)
        if operation and source_value and _is_truthy_setting_value(raw_value):
            detail = f"{operation} uses {source_value}"
            _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)
            continue

        order_match = re.search(r"-attribute_(mass_[a-z0-9_]+)_order$", key)
        if not order_match:
            continue

        operation = order_match.group(1)
        matched_sources = []
        for entry in _parse_json_array(raw_value):
            source_value = str(entry or "").strip().lower()
            if matches_source(source_value):
                matched_sources.append(source_value)
        if matched_sources:
            joined_sources = ", ".join(sorted(set(matched_sources)))
            detail = f"{operation} order includes {joined_sources}"
            _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)

    return reasons


def _config_dependency_reasons(section_rows, dependency_resolver):
    if not isinstance(section_rows, dict):
        return []
    libraries_row = section_rows.get("libraries")
    if not isinstance(libraries_row, dict):
        return []
    libraries_payload = libraries_row.get("data")
    if not isinstance(libraries_payload, dict):
        return []
    libraries_data = libraries_payload.get("libraries", {})
    return dependency_resolver(libraries_data)


def _libraries_data_requires_mal(libraries_data):
    return bool(_libraries_data_mal_dependency_reasons(libraries_data))


def _libraries_data_tautulli_dependency_reasons(libraries_data):
    return _libraries_data_collection_dependency_reasons(
        libraries_data,
        QS_TAUTULLI_DEP_COLLECTION_IDS,
        "Tautulli Charts collection enabled",
    )


def _libraries_data_trakt_dependency_reasons(libraries_data):
    collection_reasons = _libraries_data_collection_dependency_reasons(
        libraries_data,
        QS_TRAKT_DEP_COLLECTION_IDS,
        "Trakt Charts collection enabled",
    )
    overlay_reasons = _libraries_data_overlay_rating_dependency_reasons(
        libraries_data,
        QS_TRAKT_OVERLAY_IMAGE_VALUES,
    )
    return collection_reasons + [reason for reason in overlay_reasons if reason not in collection_reasons]


def _libraries_data_omdb_dependency_reasons(libraries_data):
    return _attribute_dependency_source_reasons(
        libraries_data,
        QS_OMDB_DEP_SOURCE_PREFIXES,
    )


def _libraries_data_mdblist_dependency_reasons(libraries_data):
    attribute_reasons = _attribute_dependency_source_reasons(
        libraries_data,
        QS_MDBLIST_DEP_SOURCE_PREFIXES,
    )
    overlay_reasons = _libraries_data_overlay_rating_dependency_reasons(
        libraries_data,
        QS_MDBLIST_OVERLAY_IMAGE_VALUES,
    )
    return attribute_reasons + [reason for reason in overlay_reasons if reason not in attribute_reasons]


def _libraries_data_anidb_dependency_reasons(libraries_data):
    attribute_reasons = _attribute_dependency_source_reasons(
        libraries_data,
        QS_ANIDB_DEP_SOURCE_PREFIXES,
    )
    overlay_reasons = _libraries_data_overlay_rating_dependency_reasons(
        libraries_data,
        QS_ANIDB_OVERLAY_IMAGE_VALUES,
    )
    return attribute_reasons + [reason for reason in overlay_reasons if reason not in attribute_reasons]


def _libraries_data_radarr_dependency_reasons(libraries_data):
    return _libraries_data_service_dependency_reasons(
        libraries_data,
        QS_RADARR_DEP_ATTRIBUTE_PREFIXES,
        QS_RADARR_DEP_COLLECTION_PREFIXES,
        QS_RADARR_DEP_TEMPLATE_COLLECTION_PREFIXES,
    )


def _libraries_data_sonarr_dependency_reasons(libraries_data):
    return _libraries_data_service_dependency_reasons(
        libraries_data,
        QS_SONARR_DEP_ATTRIBUTE_PREFIXES,
        QS_SONARR_DEP_COLLECTION_PREFIXES,
        QS_SONARR_DEP_TEMPLATE_COLLECTION_PREFIXES,
    )


def _libraries_data_mal_dependency_reasons(libraries_data):
    if not isinstance(libraries_data, dict):
        return []

    active_prefixes = _active_library_prefixes(libraries_data)
    reasons = []
    seen = set()

    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        if not key:
            continue

        prefix = _library_prefix_from_key(key)
        if prefix and prefix not in active_prefixes:
            continue

        if "-collection_" in key and _is_truthy_setting_value(raw_value):
            collection_id = f"collection_{key.rsplit('-collection_', 1)[1]}"
            if collection_id in QS_MAL_DEP_COLLECTION_IDS:
                _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", "MyAnimeList Charts collection enabled")
                continue

        attr_match = re.search(r"-attribute_(mass_[a-z0-9_]+)_(mal(?:_english|_japanese)?)$", key)
        if attr_match and _is_truthy_setting_value(raw_value):
            operation = attr_match.group(1)
            source_value = attr_match.group(2)
            if operation in QS_MAL_DEP_ATTRIBUTE_OPERATIONS and source_value in QS_MAL_DEP_ATTRIBUTE_VALUES:
                detail = f"{operation} uses {source_value}"
                _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)
                continue

        order_match = re.search(r"-attribute_(mass_[a-z0-9_]+)_order$", key)
        if not order_match:
            continue
        operation = order_match.group(1)
        if operation not in QS_MAL_DEP_ATTRIBUTE_OPERATIONS:
            continue
        matched_sources = []
        for entry in _parse_json_array(raw_value):
            source_value = str(entry or "").strip().lower()
            if source_value in QS_MAL_DEP_ATTRIBUTE_VALUES:
                matched_sources.append(source_value)
        if matched_sources:
            joined_sources = ", ".join(sorted(set(matched_sources)))
            detail = f"{operation} order includes {joined_sources}"
            _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)

    overlay_reasons = _libraries_data_overlay_rating_dependency_reasons(
        libraries_data,
        QS_MAL_OVERLAY_IMAGE_VALUES,
    )
    return reasons + [reason for reason in overlay_reasons if reason not in reasons]


def _config_requires_mal(section_rows):
    if not isinstance(section_rows, dict):
        return False
    libraries_row = section_rows.get("libraries")
    if not isinstance(libraries_row, dict):
        return False
    libraries_payload = libraries_row.get("data")
    if not isinstance(libraries_payload, dict):
        return False
    libraries_data = libraries_payload.get("libraries", {})
    return _libraries_data_requires_mal(libraries_data)


def _config_tautulli_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_tautulli_dependency_reasons)


def _config_omdb_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_omdb_dependency_reasons)


def _config_mdblist_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_mdblist_dependency_reasons)


def _config_anidb_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_anidb_dependency_reasons)


def _config_radarr_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_radarr_dependency_reasons)


def _config_sonarr_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_sonarr_dependency_reasons)


def _config_trakt_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_trakt_dependency_reasons)


def _config_mal_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_mal_dependency_reasons)


def _worst_status(statuses):
    worst = "ok"
    for status in statuses:
        normalized = _normalize_status(status)
        if QS_STATUS_ORDER.get(normalized, 1) > QS_STATUS_ORDER.get(worst, 1):
            worst = normalized
    return worst


def _derive_live_final_validation_status(step_statuses, template_keys):
    validation_states = []
    for key in template_keys:
        if key not in QS_VALIDATION_STEP_KEYS:
            continue
        if key not in step_statuses:
            continue
        validation_states.append(_normalize_status(step_statuses.get(key)))

    if not validation_states:
        return "warn"
    if any(state == "error" for state in validation_states):
        return "error"
    if any(state == "warn" for state in validation_states):
        return "warn"
    if any(state == "ok" for state in validation_states):
        return "ok"
    return "warn"


def _build_live_validation_rollup(step_statuses, template_keys):
    counts = {"validated": 0, "failed": 0, "skipped": 0, "unknown": 0}
    for key in template_keys:
        if key not in QS_VALIDATION_STEP_KEYS:
            continue
        state = _normalize_status(step_statuses.get(key))
        if state == "ok":
            counts["validated"] += 1
        elif state == "error":
            counts["failed"] += 1
        elif state == "warn":
            counts["skipped"] += 1
        else:
            counts["unknown"] += 1

    if counts["failed"] > 0:
        state = "error"
    elif counts["skipped"] > 0:
        state = "warn"
    elif counts["validated"] > 0:
        state = "ok"
    else:
        state = "unknown"

    summary_text = f"Current. Validated: {counts['validated']} \u2022 " f"Failed: {counts['failed']} \u2022 " f"Pending: {counts['skipped']}"
    if counts["unknown"] > 0:
        summary_text += f" \u2022 Not checked: {counts['unknown']}"
    summary_text += "."

    return {"counts": counts, "state": state, "summary_text": summary_text}


def _latest_iso_timestamp(values):
    latest_dt = None
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if latest_dt is None or parsed > latest_dt:
            latest_dt = parsed
    return latest_dt.isoformat().replace("+00:00", "Z") if latest_dt else None


def _format_validation_age(iso_text):
    text = str(iso_text or "").strip()
    if not text:
        return "Never", "never"
    try:
        dt_value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return "Unknown", "never"
    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=timezone.utc)
    now_utc = datetime.now(timezone.utc)
    delta = now_utc - dt_value.astimezone(timezone.utc)
    if delta.total_seconds() < 0:
        delta = timedelta(0)
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "Just now", "fresh"
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago", "fresh"
    if seconds < 86400:
        hours = max(1, seconds // 3600)
        return f"{hours}h ago", "stale"
    days = max(1, seconds // 86400)
    return f"{days}d ago", "stale"


def _parse_iso_datetime(iso_text):
    text = str(iso_text or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bulk_validation_is_fresh(iso_text, ttl_hours=QS_FINAL_VALIDATION_TTL_HOURS):
    parsed = _parse_iso_datetime(iso_text)
    if parsed is None:
        return False
    return datetime.now(timezone.utc) - parsed <= timedelta(hours=ttl_hours)


def _build_final_gate(workspace_status, template_list, validation_bulk_rollup_at):
    label_map = {file.rsplit(".", 1)[0]: display_name for file, display_name in template_list or []}
    step_statuses = workspace_status.get("step_statuses", {}) if isinstance(workspace_status, dict) else {}
    required_keys = workspace_status.get("required_keys", []) if isinstance(workspace_status, dict) else []
    optional_keys = workspace_status.get("optional_keys", []) if isinstance(workspace_status, dict) else []

    blockers = []
    seen = set()
    for key in required_keys:
        state = step_statuses.get(key, "warn")
        if state == "ok":
            continue
        blockers.append({"key": key, "label": label_map.get(key, key), "state": state, "group": "required"})
        seen.add(key)

    for key in optional_keys:
        state = step_statuses.get(key, "unknown")
        if state not in {"warn", "error"} or key in seen:
            continue
        blockers.append({"key": key, "label": label_map.get(key, key), "state": state, "group": "optional"})
        seen.add(key)

    dependency_defs = [
        ("tautulli", QS_TAUTULLI_REQUIRED_STEP_KEY, "Tautulli", "tautulli_requirement_reasons", "qs-tautulli-required-hint"),
        ("omdb", QS_OMDB_REQUIRED_STEP_KEY, "OMDb", "omdb_requirement_reasons", "qs-omdb-required-hint"),
        ("mdblist", QS_MDBLIST_REQUIRED_STEP_KEY, "MDBList", "mdblist_requirement_reasons", "qs-mdblist-required-hint"),
        ("anidb", QS_ANIDB_REQUIRED_STEP_KEY, "AniDB", "anidb_requirement_reasons", "qs-anidb-required-hint"),
        ("radarr", QS_RADARR_REQUIRED_STEP_KEY, "Radarr", "radarr_requirement_reasons", "qs-radarr-required-hint"),
        ("sonarr", QS_SONARR_REQUIRED_STEP_KEY, "Sonarr", "sonarr_requirement_reasons", "qs-sonarr-required-hint"),
        ("trakt", QS_TRAKT_REQUIRED_STEP_KEY, "Trakt", "trakt_requirement_reasons", "qs-trakt-required-hint"),
        ("mal", QS_MAL_REQUIRED_STEP_KEY, "MyAnimeList", "mal_requirement_reasons", "qs-mal-required-hint"),
    ]
    dependency_cards = []
    for provider, step_key, label, reasons_key, css_class in dependency_defs:
        reasons = workspace_status.get(reasons_key, []) if isinstance(workspace_status, dict) else []
        if not reasons or step_statuses.get(step_key) == "ok":
            continue
        dependency_cards.append(
            {
                "provider": provider,
                "key": step_key,
                "label": label,
                "title": f"{label} required by",
                "reasons": reasons,
                "state": step_statuses.get(step_key, "warn"),
                "css_class": css_class,
            }
        )
    dependency_keys = {card["key"] for card in dependency_cards}
    setup_blockers = [blocker for blocker in blockers if blocker.get("key") not in dependency_keys]

    bulk_fresh = _bulk_validation_is_fresh(validation_bulk_rollup_at)
    if blockers:
        stage = "todo"
    elif not bulk_fresh:
        stage = "freshness"
    else:
        stage = "config"

    return {
        "stage": stage,
        "todo_count": len(blockers),
        "todo_blockers": blockers,
        "dependency_cards": dependency_cards,
        "setup_blockers": setup_blockers,
        "bulk_validation_fresh": bulk_fresh,
        "bulk_validation_at": validation_bulk_rollup_at or "",
        "validation_ttl_hours": QS_FINAL_VALIDATION_TTL_HOURS,
        "can_build_config": not blockers and bulk_fresh,
        "config_valid": False,
    }


def _step_href(step_key):
    target = str(step_key or "").strip()
    if not target:
        target = "001-start"
    if has_request_context():
        try:
            return url_for("step", name=target)
        except Exception:
            return f"/step/{target}"
    return f"/step/{target}"


def _latest_bulk_validation_timestamp(config_name):
    if not config_name:
        return ""
    try:
        stored_validation = database.retrieve_section_data(config_name, "validation_summary")
        stored_payload = stored_validation[2] if stored_validation else None
        if isinstance(stored_payload, dict):
            return str(stored_payload.get("updated_at") or "").strip()
    except Exception:
        return ""
    return ""


def _workspace_step_status_from_app_readiness(state):
    normalized = str(state or "").strip().lower()
    if normalized in {"ready", "review", "running", "queued"}:
        return "ok"
    if normalized == "needs_validation":
        return "warn"
    if normalized in {"needs_prepare", "needs_setup", "blocked", "error"}:
        return "error"
    return "unknown"


def _build_workspace_app_readiness_from_status(config_name, workspace_status, template_list=None):
    template_list = template_list or helpers.get_menu_list()
    final_gate = _build_final_gate(
        workspace_status,
        template_list,
        _latest_bulk_validation_timestamp(config_name),
    )
    install_context = _build_kometa_install_context(config_name)

    first_blocker = {}
    todo_blockers = final_gate.get("todo_blockers") or []
    if todo_blockers:
        first_blocker = todo_blockers[0] if isinstance(todo_blockers[0], dict) else {}
    blocker_key = first_blocker.get("key") or "001-start"
    blocker_label = first_blocker.get("label") or "setup"
    todo_count = int(final_gate.get("todo_count") or 0)

    kometa = {
        "name": "Kometa",
        "href": _step_href("900-kometa"),
        "action_label": "Open Kometa",
        "state": "review",
        "summary": "Open Kometa",
        "detail": "Use the Kometa page to review build status, prepare the runtime, and run this config.",
        "target_step": "900-kometa",
        "final_gate_stage": final_gate.get("stage") or "todo",
        "todo_count": todo_count,
        "install_mode": install_context.get("kometa_install_mode") or "",
        "mode_label": install_context.get("kometa_mode_label") or "",
        "can_launch": bool(install_context.get("kometa_can_launch")),
        "can_sync_config": bool(install_context.get("kometa_can_sync_config")),
    }

    if final_gate.get("stage") == "todo":
        noun = "item" if todo_count == 1 else "items"
        kometa.update(
            state="needs_setup",
            summary=f"{todo_count} setup {noun} left" if todo_count else "Finish setup first",
            detail=f"Finish {blocker_label} before Kometa is ready to review in Quickstart.",
            action_label="Finish setup",
            href=_step_href(blocker_key),
            target_step=blocker_key,
        )
    elif final_gate.get("stage") == "freshness":
        kometa.update(
            state="review",
            summary="Validation refresh recommended",
            detail=f"Open Kometa to refresh bulk validation before running. Quickstart expects validation within the last {QS_FINAL_VALIDATION_TTL_HOURS} hours, but the app itself is still available.",
            action_label="Open Kometa",
            href=_step_href("900-kometa"),
            target_step="900-kometa",
        )
    elif install_context.get("kometa_can_launch"):
        kometa.update(
            state="ready",
            summary="Ready in Quickstart",
            detail="Open Kometa to prepare the runtime if needed, then review or run this config.",
        )
    elif install_context.get("kometa_can_sync_config"):
        detail = "Open Kometa to review and sync this config."
        if install_context.get("kometa_is_external_install"):
            detail = "Open Kometa to review and sync this config for your external Kometa install."
        kometa.update(
            state="review",
            summary="Config ready",
            detail=detail,
        )

    imagemaid_settings, imagemaid_section = _get_imagemaid_settings_section(config_name)
    imagemaid_state = _probe_imagemaid_root_state(helpers.get_imagemaid_root_path())
    imagemaid_row = database.retrieve_section_data(config_name, "imagemaid") if config_name else None
    imagemaid_validated = helpers.booler(imagemaid_row[0]) if imagemaid_row else helpers.booler(imagemaid_settings.get("validated", False))
    imagemaid_is_valid, imagemaid_reason, imagemaid_details = _validate_imagemaid_settings(imagemaid_section, config_name=config_name)

    imagemaid = {
        "name": "ImageMaid",
        "href": _step_href("915-imagemaid"),
        "action_label": "Open ImageMaid",
        "state": "needs_prepare",
        "summary": "Prepare ImageMaid",
        "detail": "Install or prepare ImageMaid before validating and running it in Quickstart.",
        "target_step": "915-imagemaid",
        "validated": bool(imagemaid_validated),
        "settings_valid": bool(imagemaid_is_valid),
        "installed": bool(imagemaid_state.get("imagemaid_installed")),
        "venv_ready": bool(imagemaid_state.get("venv_python_exists")),
    }

    if imagemaid_state.get("imagemaid_installed") and imagemaid_state.get("venv_python_exists"):
        if imagemaid_is_valid and imagemaid_validated:
            imagemaid.update(
                state="ready",
                summary="Ready to run",
                detail="Open ImageMaid to review the command preview and run it.",
            )
        elif imagemaid_is_valid:
            imagemaid.update(
                state="needs_validation",
                summary="Ready to validate",
                detail="Open ImageMaid and validate the saved settings to unlock run controls.",
            )
        else:
            summary_map = {
                "missing_plex_validation": "Plex validation required",
                "missing_credentials": "Saved Plex credentials required",
                "invalid_path": "Plex path needs attention",
            }
            imagemaid.update(
                state="needs_setup",
                summary=summary_map.get(imagemaid_reason, "ImageMaid needs attention"),
                detail=str(imagemaid_details or "Open ImageMaid to finish setup.").strip(),
            )
            if imagemaid_reason == "missing_plex_validation":
                imagemaid.update(
                    href=_step_href("010-plex"),
                    action_label="Open Plex",
                    target_step="010-plex",
                )

    return {
        "generated_at": utc_now_iso(),
        "kometa": kometa,
        "imagemaid": imagemaid,
    }


def _build_workspace_app_readiness(config_name, template_list=None, available_configs=None):
    template_list = template_list or helpers.get_menu_list()
    available_configs = available_configs or database.get_unique_config_names() or []
    workspace_status = _build_workspace_status_context(
        config_name,
        template_list,
        available_configs=available_configs,
        include_app_readiness_overrides=False,
    )
    return _build_workspace_app_readiness_from_status(config_name, workspace_status, template_list=template_list)


def _is_nonblank_setting(value):
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return True
    text = str(value).strip()
    if not text:
        return False
    return text.lower() not in {"none", "null", "false"}


def _is_meaningful_optional_status_input(value):
    if not _is_nonblank_setting(value):
        return False
    text = str(value).strip().lower()
    # UI template placeholders can be persisted as defaults; they should not
    # make an optional page look user-configured in the workspace menu
    return not (text.startswith("enter ") and any(token in text for token in ("token", "api key", "url", "client")))


def _has_meaningful_optional_input(template_key, payload):
    if not isinstance(payload, dict):
        return False

    # Playlists intentionally treat pass-through differently (handled in its own branch).
    if template_key == "027-playlist_files":
        return True

    if template_key == "100-anidb":
        anidb = payload.get("anidb", {})
        return isinstance(anidb, dict) and helpers.booler(anidb.get("enable"))

    if template_key == "087-apprise":
        apprise = payload.get("apprise", {})
        if not isinstance(apprise, dict):
            return False
        return _is_meaningful_optional_status_input(apprise.get("location"))

    simple_key_requirements = {
        "030-tautulli": ("tautulli", ("url", "apikey")),
        "040-github": ("github", ("token",)),
        "050-omdb": ("omdb", ("apikey",)),
        "060-mdblist": ("mdblist", ("apikey",)),
        "070-notifiarr": ("notifiarr", ("apikey",)),
        "080-gotify": ("gotify", ("url", "token")),
        "085-ntfy": ("ntfy", ("url", "token", "topic")),
        "090-webhooks": ("webhooks", ("notifiarr", "gotify", "ntfy", "slack", "discord", "webhook", "url")),
        "110-radarr": ("radarr", ("url", "token")),
        "120-sonarr": ("sonarr", ("url", "token")),
    }

    req = simple_key_requirements.get(template_key)
    if req:
        section_name, keys = req
        section_data = payload.get(section_name, {})
        if isinstance(section_data, dict):
            if template_key == "090-webhooks":
                return any(_is_meaningful_optional_status_input(value) for value in section_data.values())
            return any(_is_meaningful_optional_status_input(section_data.get(key)) for key in keys)
        return False

    if template_key == "130-trakt":
        trakt = payload.get("trakt", {})
        if not isinstance(trakt, dict):
            return False
        auth = trakt.get("authorization", {}) if isinstance(trakt.get("authorization"), dict) else {}
        return any(
            _is_meaningful_optional_status_input(value)
            for value in (
                trakt.get("client_id"),
                trakt.get("client_secret"),
                trakt.get("pin"),
                auth.get("access_token"),
                auth.get("refresh_token"),
            )
        )

    if template_key == "140-mal":
        mal = payload.get("mal", {})
        if not isinstance(mal, dict):
            return False
        auth = mal.get("authorization", {}) if isinstance(mal.get("authorization"), dict) else {}
        return any(
            _is_meaningful_optional_status_input(value)
            for value in (
                mal.get("client_id"),
                mal.get("client_secret"),
                mal.get("localhost_url"),
                auth.get("access_token"),
                auth.get("refresh_token"),
            )
        )

    # For unknown validation-backed optional steps, keep prior behavior.
    return True


def _derive_step_status(template_key, group, section_rows, config_exists):
    if template_key == "001-start":
        if not config_exists:
            return "error"
        kometa_entry = section_rows.get("kometa") if isinstance(section_rows, dict) else None
        kometa_entry = kometa_entry if isinstance(kometa_entry, dict) else {}
        kometa_payload = kometa_entry.get("data")
        kometa_payload = kometa_payload if isinstance(kometa_payload, dict) else {}
        kometa_section = kometa_payload.get("kometa") if isinstance(kometa_payload.get("kometa"), dict) else {}
        kometa_selection = _canonicalize_kometa_section(kometa_section)
        if kometa_selection.get("install_mode") == KOMETA_INSTALL_MODE_MANAGED:
            return "ok"
        is_valid, _reason, _details = _validate_saved_kometa_selection(kometa_selection)
        return "ok" if is_valid else "error"

    if template_key == "900-kometa":
        return "warn"

    if template_key in {"905-analytics", "910-sponsor"}:
        return "ok"

    section_name = template_key.split("-", 1)[1] if "-" in template_key else template_key
    section_entry = section_rows.get(section_name) if isinstance(section_rows, dict) else None
    section_entry = section_entry if isinstance(section_entry, dict) else {}
    section_row_present = bool(section_entry)

    validated = helpers.booler(section_entry.get("validated", False))
    user_entered = helpers.booler(section_entry.get("user_entered", False))
    payload = section_entry.get("data")
    payload = payload if isinstance(payload, dict) else {}
    validation_status = str(payload.get("validation_status") or "").strip().lower()
    validation_reason = str(payload.get("validation_reason") or "").strip().lower()
    was_previously_validated = bool(payload.get("validated_at"))
    if template_key == "027-playlist_files":
        playlist_payload = payload.get("playlist_files", payload if isinstance(payload, dict) else {})
        if isinstance(playlist_payload, dict) and isinstance(playlist_payload.get("playlist_files"), dict):
            playlist_payload = playlist_payload.get("playlist_files", {})
        playlist_libraries = ""
        if isinstance(playlist_payload, dict):
            raw_libraries = playlist_payload.get("libraries")
            if isinstance(raw_libraries, list):
                selected_libraries = [str(item).strip() for item in raw_libraries if str(item).strip()]
            else:
                playlist_libraries = str(raw_libraries or "")
                selected_libraries = [item.strip() for item in playlist_libraries.split(",") if item.strip()]
        else:
            selected_libraries = []

        if validation_status == "failed":
            return "error"
        if selected_libraries:
            # Playlist selection itself is the completion signal for this optional page.
            return "ok"

        # If user has visited/passed-through this page (even with no libraries selected),
        # treat it as intentionally acknowledged/valid.
        was_visited = section_row_present and (user_entered or bool(validation_status) or bool(payload.get("validation_updated_at")) or bool(payload.get("validated_at")))
        if was_visited:
            return "ok"
        return "unknown"

    if template_key in QS_VALIDATION_STEP_KEYS:
        if group == "optional" and not _has_meaningful_optional_input(template_key, payload):
            return "unknown"

        if validated or validation_status == "validated":
            return "ok"

        if validation_status == "failed":
            return "error"

        if validation_status == "skipped":
            if template_key == "027-playlist_files" and validation_reason == "no_libraries":
                return "unknown"
            if validation_reason in QS_ERROR_REASONS:
                return "error"
            if group == "optional":
                # Optional sections should remain neutral when users simply pass through
                # or when validation is skipped due to missing optional inputs.
                return "unknown"
            if validation_reason in QS_WARN_REASONS:
                return "warn"
            return "warn" if group == "required" else ("warn" if user_entered else "ok")

        if group == "required":
            if not user_entered:
                return "error"
            if was_previously_validated:
                return "error"
            return "warn"

        if not user_entered and not was_previously_validated and not validation_status:
            return "unknown"
        if was_previously_validated:
            return "error"
        return "warn" if user_entered else "ok"

    if group == "required":
        return "warn" if user_entered else "error"
    if group == "optional":
        return "warn" if user_entered else "unknown"
    return "ok"


def _build_workspace_status_context(config_name, template_list, available_configs=None, include_app_readiness_overrides=True):
    template_keys = []
    for file_entry, _ in template_list or []:
        template_key = file_entry.rsplit(".", 1)[0]
        template_keys.append(template_key)

    section_rows = {}
    if config_name:
        try:
            for row in database.retrieve_config_sections(config_name):
                section_name = row.get("section")
                if section_name:
                    section_rows[section_name] = row
        except Exception:
            section_rows = {}

    available_set = set(available_configs or [])
    config_exists = bool(config_name) and (config_name in available_set or bool(section_rows))

    required_seed = set(QS_REQUIRED_STEP_KEYS)
    tautulli_requirement_reasons = _config_tautulli_dependency_reasons(section_rows) if QS_TAUTULLI_REQUIRED_STEP_KEY in template_keys else []
    omdb_requirement_reasons = _config_omdb_dependency_reasons(section_rows) if QS_OMDB_REQUIRED_STEP_KEY in template_keys else []
    mdblist_requirement_reasons = _config_mdblist_dependency_reasons(section_rows) if QS_MDBLIST_REQUIRED_STEP_KEY in template_keys else []
    anidb_requirement_reasons = _config_anidb_dependency_reasons(section_rows) if QS_ANIDB_REQUIRED_STEP_KEY in template_keys else []
    radarr_requirement_reasons = _config_radarr_dependency_reasons(section_rows) if QS_RADARR_REQUIRED_STEP_KEY in template_keys else []
    sonarr_requirement_reasons = _config_sonarr_dependency_reasons(section_rows) if QS_SONARR_REQUIRED_STEP_KEY in template_keys else []
    trakt_requirement_reasons = _config_trakt_dependency_reasons(section_rows) if QS_TRAKT_REQUIRED_STEP_KEY in template_keys else []
    mal_requirement_reasons = _config_mal_dependency_reasons(section_rows) if QS_MAL_REQUIRED_STEP_KEY in template_keys else []
    if QS_TAUTULLI_REQUIRED_STEP_KEY in template_keys and tautulli_requirement_reasons:
        required_seed.add(QS_TAUTULLI_REQUIRED_STEP_KEY)
    if QS_OMDB_REQUIRED_STEP_KEY in template_keys and omdb_requirement_reasons:
        required_seed.add(QS_OMDB_REQUIRED_STEP_KEY)
    if QS_MDBLIST_REQUIRED_STEP_KEY in template_keys and mdblist_requirement_reasons:
        required_seed.add(QS_MDBLIST_REQUIRED_STEP_KEY)
    if QS_ANIDB_REQUIRED_STEP_KEY in template_keys and anidb_requirement_reasons:
        required_seed.add(QS_ANIDB_REQUIRED_STEP_KEY)
    if QS_RADARR_REQUIRED_STEP_KEY in template_keys and radarr_requirement_reasons:
        required_seed.add(QS_RADARR_REQUIRED_STEP_KEY)
    if QS_SONARR_REQUIRED_STEP_KEY in template_keys and sonarr_requirement_reasons:
        required_seed.add(QS_SONARR_REQUIRED_STEP_KEY)
    if QS_TRAKT_REQUIRED_STEP_KEY in template_keys and trakt_requirement_reasons:
        required_seed.add(QS_TRAKT_REQUIRED_STEP_KEY)
    if QS_MAL_REQUIRED_STEP_KEY in template_keys and mal_requirement_reasons:
        required_seed.add(QS_MAL_REQUIRED_STEP_KEY)
    review_seed = set(QS_REVIEW_STEP_KEYS)

    required_keys = [key for key in template_keys if key in required_seed]
    review_keys = [key for key in template_keys if key in review_seed]
    optional_keys = [key for key in template_keys if key not in required_seed and key not in review_seed]

    step_statuses = {}
    for template_key in template_keys:
        if template_key == "900-kometa":
            continue
        if template_key in required_keys:
            group = "required"
        elif template_key in optional_keys:
            group = "optional"
        else:
            group = "review"
        step_statuses[template_key] = _derive_step_status(template_key, group, section_rows, config_exists)
    if "900-kometa" in template_keys:
        step_statuses["900-kometa"] = _derive_live_final_validation_status(step_statuses, template_keys)

    if include_app_readiness_overrides and config_name:
        provisional_status = {
            "step_statuses": dict(step_statuses),
            "required_keys": list(required_keys),
            "optional_keys": list(optional_keys),
            "review_keys": list(review_keys),
            "tautulli_requirement_reasons": tautulli_requirement_reasons,
            "omdb_requirement_reasons": omdb_requirement_reasons,
            "mdblist_requirement_reasons": mdblist_requirement_reasons,
            "anidb_requirement_reasons": anidb_requirement_reasons,
            "radarr_requirement_reasons": radarr_requirement_reasons,
            "sonarr_requirement_reasons": sonarr_requirement_reasons,
            "trakt_requirement_reasons": trakt_requirement_reasons,
            "mal_requirement_reasons": mal_requirement_reasons,
        }
        app_readiness = _build_workspace_app_readiness_from_status(config_name, provisional_status, template_list=template_list)
        kometa_readiness = app_readiness.get("kometa") if isinstance(app_readiness, dict) else None
        imagemaid_readiness = app_readiness.get("imagemaid") if isinstance(app_readiness, dict) else None
        if "900-kometa" in step_statuses and isinstance(kometa_readiness, dict):
            step_statuses["900-kometa"] = _workspace_step_status_from_app_readiness(kometa_readiness.get("state"))
        if "915-imagemaid" in step_statuses and isinstance(imagemaid_readiness, dict):
            step_statuses["915-imagemaid"] = _workspace_step_status_from_app_readiness(imagemaid_readiness.get("state"))

    required_rollup = _worst_status(step_statuses.get(key, "warn") for key in required_keys) if required_keys else "ok"
    review_rollup = _worst_status(step_statuses.get(key, "ok") for key in review_keys) if review_keys else "ok"

    optional_status_values = [step_statuses.get(key, "unknown") for key in optional_keys]
    if not optional_status_values:
        optional_rollup = "ok"
    elif any(status == "error" for status in optional_status_values):
        optional_rollup = "error"
    elif any(status == "warn" for status in optional_status_values):
        optional_rollup = "warn"
    elif any(status == "unknown" for status in optional_status_values):
        optional_rollup = "unknown"
    else:
        optional_rollup = "ok"

    section_statuses = {
        "required": required_rollup,
        "optional": optional_rollup,
        "review": review_rollup,
    }

    jump_to_validations = {}
    for key in QS_VALIDATION_STEP_KEYS:
        if key in step_statuses:
            jump_to_validations[key] = step_statuses.get(key) == "ok"

    required_total = len(required_keys)
    required_ready = sum(1 for key in required_keys if step_statuses.get(key) == "ok")
    required_percent = round((required_ready / required_total) * 100) if required_total else 0

    optional_total = len(optional_keys)
    optional_configured = sum(1 for key in optional_keys if step_statuses.get(key) != "unknown")
    optional_issue_count = sum(1 for key in optional_keys if step_statuses.get(key) in {"warn", "error"})

    optional_summary = f"Optional {optional_configured}/{optional_total} configured" if optional_total else "No optional pages"
    if optional_issue_count > 0:
        optional_summary += f" • {optional_issue_count} issue{'s' if optional_issue_count != 1 else ''}"

    validation_timestamps = []
    for row in section_rows.values():
        if not isinstance(row, dict):
            continue
        data = row.get("data")
        if not isinstance(data, dict):
            continue
        for key in ("validation_updated_at", "validated_at"):
            value = data.get(key)
            if value:
                validation_timestamps.append(value)
        if row.get("section") == "validation_summary":
            summary_updated = data.get("updated_at")
            if summary_updated:
                validation_timestamps.append(summary_updated)
    latest_validation_at = _latest_iso_timestamp(validation_timestamps)
    validation_age_label, validation_freshness = _format_validation_age(latest_validation_at)

    readiness = {
        "required_total": required_total,
        "required_ready": required_ready,
        "required_percent": required_percent,
        "required_state": required_rollup,
        "optional_total": optional_total,
        "optional_configured": optional_configured,
        "optional_issue_count": optional_issue_count,
        "optional_summary": optional_summary,
        "latest_validation_at": latest_validation_at,
        "validation_age_label": validation_age_label,
        "validation_freshness": validation_freshness,
    }

    return {
        "step_statuses": step_statuses,
        "section_statuses": section_statuses,
        "jump_to_validations": jump_to_validations,
        "required_keys": required_keys,
        "optional_keys": optional_keys,
        "review_keys": review_keys,
        "tautulli_requirement_reasons": tautulli_requirement_reasons,
        "omdb_requirement_reasons": omdb_requirement_reasons,
        "mdblist_requirement_reasons": mdblist_requirement_reasons,
        "anidb_requirement_reasons": anidb_requirement_reasons,
        "radarr_requirement_reasons": radarr_requirement_reasons,
        "sonarr_requirement_reasons": sonarr_requirement_reasons,
        "trakt_requirement_reasons": trakt_requirement_reasons,
        "mal_requirement_reasons": mal_requirement_reasons,
        "readiness": readiness,
    }


DOTENV = os.path.relpath(os.path.join(helpers.CONFIG_DIR, ".env"))
load_dotenv(DOTENV, override=True)


# Initialize logging
helpers.initialize_logging()

GITHUB_MASTER_VERSION_URL = "https://raw.githubusercontent.com/Kometa-Team/Quickstart/master/VERSION"
GITHUB_DEVELOP_VERSION_URL = "https://raw.githubusercontent.com/Kometa-Team/Quickstart/develop/VERSION"

basedir = os.path.abspath
kometa_process = None

app = Flask(__name__)

app.register_blueprint(validation_routes_bp)
app.register_blueprint(asset_routes_bp)
app.register_blueprint(kometa_updates_bp)
app.register_blueprint(imagemaid_updates_bp)
app.register_blueprint(config_routes_bp)
app.register_blueprint(test_libraries_routes_bp)

# Run version check at startup
app.config["VERSION_CHECK"] = helpers.check_for_update()

# Default Kometa root lives under Quickstart's config directory
kometa_path = os.path.abspath(os.path.join(helpers.CONFIG_DIR, "kometa"))

app.config["KOMETA_ROOT"] = os.environ.get("QS_KOMETA_PATH", kometa_path)


def start_update_thread():
    """Ensure update_checker_loop runs inside the Flask app context."""
    with app.app_context():
        while True:
            app.config["VERSION_CHECK"] = helpers.check_for_update()
            time.sleep(86400)  # Sleep for 24 hours


# Start the background version checker safely
threading.Thread(target=start_update_thread, daemon=True).start()


@app.context_processor
def inject_version_info():
    """Ensure latest version info is injected dynamically in templates"""
    return {
        "version_info": app.config.get("VERSION_CHECK") or {},
        "overlay_fonts": list_overlay_fonts(),
    }


# Use booler() for FLASK_DEBUG conversion
app.config["QS_DEBUG"] = helpers.booler(os.getenv("QS_DEBUG", "0"))
app.config["QS_THEME"] = os.getenv("QS_THEME", "kometa").strip() or "kometa"
app.config["QS_OPTIMIZE_DEFAULTS"] = helpers.booler(os.getenv("QS_OPTIMIZE_DEFAULTS", "1"))
try:
    app.config["QS_CONFIG_HISTORY"] = max(0, int(str(os.getenv("QS_CONFIG_HISTORY", "0")).strip()))
except (TypeError, ValueError):
    app.config["QS_CONFIG_HISTORY"] = 0
try:
    app.config["QS_KOMETA_LOG_KEEP"] = max(0, int(str(os.getenv("QS_KOMETA_LOG_KEEP", "0")).strip()))
except (TypeError, ValueError):
    app.config["QS_KOMETA_LOG_KEEP"] = 0
try:
    app.config["QS_IMAGEMAID_LOG_KEEP"] = max(0, int(str(os.getenv("QS_IMAGEMAID_LOG_KEEP", "0")).strip()))
except (TypeError, ValueError):
    app.config["QS_IMAGEMAID_LOG_KEEP"] = 0
default_test_libs_path = os.path.join(helpers.CONFIG_DIR, "plex_test_libraries")
default_test_libs_tmp = os.path.join(helpers.CONFIG_DIR, "tmp")
app.config["QS_TEST_LIBS_PATH"] = os.getenv("QS_TEST_LIBS_PATH", default_test_libs_path).strip() or default_test_libs_path
app.config["QS_TEST_LIBS_TMP"] = os.getenv("QS_TEST_LIBS_TMP", default_test_libs_tmp).strip() or default_test_libs_tmp
app.config["QUICKSTART_DOCKER"] = helpers.booler(os.getenv("QUICKSTART_DOCKER", "0"))
restart_notice = helpers.consume_restart_notice()
app.config["QS_RESTART_NOTICE"] = restart_notice
app.config["QS_SKIP_AUTO_OPEN"] = bool(restart_notice and restart_notice.get("reason") == "update")

cleanup_flag = os.getenv("QS_CONFIG_CLEANUP_DONE", "").strip().lower()
if cleanup_flag not in {"1", "true", "yes"}:
    result = helpers.migrate_config_archives(history_limit=app.config.get("QS_CONFIG_HISTORY", 0))
    if result.get("moved"):
        helpers.ts_log(f"Config cleanup moved {result['moved']} archived file(s).", level="INFO")
    if result.get("errors"):
        for msg in result["errors"]:
            helpers.ts_log(msg, level="WARNING")
    else:
        helpers.update_env_variable("QS_CONFIG_CLEANUP_DONE", "1")
        os.environ["QS_CONFIG_CLEANUP_DONE"] = "1"


def _load_or_create_secret_key():
    env_key = os.getenv("QS_SECRET_KEY", "").strip()
    if env_key:
        return env_key
    secret_path = os.path.join(helpers.CONFIG_DIR, ".secret_key")
    try:
        if os.path.exists(secret_path):
            with open(secret_path, "r", encoding="utf-8") as handle:
                existing = handle.read().strip()
            if existing:
                return existing
        new_key = secrets.token_hex(32)
        with open(secret_path, "w", encoding="utf-8") as handle:
            handle.write(new_key)
        return new_key
    except Exception:
        return secrets.token_hex(32)


def _get_session_lifetime_days():
    raw_days = os.getenv("QS_SESSION_LIFETIME_DAYS", "").strip()
    if raw_days:
        try:
            days = max(1, int(raw_days))
        except (TypeError, ValueError):
            days = 30
    else:
        days = 30
    return days


def _get_session_lifetime_seconds():
    return int(timedelta(days=_get_session_lifetime_days()).total_seconds())


app.config["SECRET_KEY"] = _load_or_create_secret_key()
app.config["SESSION_TYPE"] = "cachelib"

# Flask session cache dir (portable default)
flask_cache_dir = os.environ.get("QS_FLASK_SESSION_DIR", os.path.join(helpers.CONFIG_DIR, "flask_session"))
flask_cache_dir = os.path.abspath(os.path.expanduser(flask_cache_dir))
os.makedirs(flask_cache_dir, exist_ok=True)

logscan_reingest_lock = threading.Lock()
logscan_ingest_lock = threading.Lock()
logscan_reingest_state = {
    "status": "idle",
    "job_id": None,
}

# Bump this integer when a release needs a one-time Analytics reset + log reingest
# on startup. Quickstart persists the highest successful level to config/.env so
# skipped releases still catch up automatically.
REQUIRED_LOGSCAN_MIGRATION_LEVEL = 9
LOGSCAN_STARTUP_MIGRATIONS_ENV = "QS_LOGSCAN_STARTUP_MIGRATIONS"
LOGSCAN_MIGRATION_LEVEL_DONE_ENV = "QS_LOGSCAN_MIGRATION_LEVEL_DONE"
LOGSCAN_STARTUP_MIGRATION_JOB_ID = "startup-logscan-migration"

session_ttl = _get_session_lifetime_seconds()
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=session_ttl)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["QS_SESSION_LIFETIME_DAYS"] = _get_session_lifetime_days()
app.config["QS_FLASK_SESSION_DIR"] = flask_cache_dir
app.config["SESSION_CACHELIB"] = FileSystemCache(cache_dir=flask_cache_dir, threshold=500, default_timeout=session_ttl)
app.config["SESSION_PERMANENT"] = True
app.config["SESSION_USE_SIGNER"] = False

app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB, adjust as needed
app.config["MAX_FORM_MEMORY_SIZE"] = 16 * 1024 * 1024  # 16 MB


@app.before_request
def before_request():
    # Assign user UUID if not already present
    if "qs_session_id" not in session:
        session["qs_session_id"] = str(uuid.uuid4())[:8]

    # Log request size if applicable
    if request.content_length:
        helpers.ts_log(f"Incoming request size: {request.content_length / 1024:.2f} KB", level="DEBUG")

    # Only applies to form-encoded POSTs
    if request.method == "POST" and (request.content_type or "").startswith("application/x-www-form-urlencoded"):
        try:
            form_data = request.form
            helpers.ts_log(f"Form field count: {len(form_data)}", level="DEBUG")
        except Exception as e:
            helpers.ts_log(f"Failed to parse form: {e}", level="ERROR")

    try:
        ua = request.user_agent
        session["qs_user_agent"] = ua.string or ""
        session["qs_user_agent_browser"] = ua.browser or ""
        session["qs_user_agent_version"] = ua.version or ""
        session["qs_user_agent_platform"] = ua.platform or ""
        session["qs_user_agent_raw"] = request.headers.get("User-Agent", "") or ""
    except Exception:
        pass


def _render_header_style_preview(font: str) -> str:
    if font == "none":
        return "No header will be added."
    return output.section_heading("Quickstart", font=font)


@app.route("/update-quickstart", methods=["POST"])
def update_quickstart():
    logs = []

    try:
        data = request.get_json(silent=True) or {}
        branch = data.get("branch", "master")

        result = helpers.perform_quickstart_update(app.root_path, branch=branch)
        logs.extend(result.get("log", []))
        status = 200 if result.get("success") else 500

        return (
            jsonify(
                {
                    "success": result.get("success", False),
                    "log": logs,
                    "branch": branch,
                }
            ),
            status,
        )

    except Exception as e:
        helpers.ts_log(f"Quickstart update failed: {e}", level="ERROR")
        logs.append("Exception during Quickstart update.")
        return jsonify({"success": False, "log": logs}), 500


@app.route("/check-quickstart-update", methods=["POST"])
def check_quickstart_update():
    try:
        version_info = helpers.check_for_update()
        app.config["VERSION_CHECK"] = version_info
        return jsonify({"success": True, "version_info": version_info})
    except Exception as e:
        helpers.ts_log(f"Quickstart update check failed: {e}", level="ERROR")
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Failed to check for Quickstart updates.",
                    "version_info": app.config.get("VERSION_CHECK") or {},
                }
            ),
            500,
        )


# Initialize Flask-Session
server_session = Session(app)
server_thread = None
shutdown_event = threading.Event()

# Ensure json-schema files are up to date at startup
helpers.ensure_json_schema()
sanitized_section_count = database.sanitize_all_section_data()
if sanitized_section_count:
    helpers.ts_log(f"Sanitized transient config-manager fields from {sanitized_section_count} persisted section(s).", level="INFO")

parser = argparse.ArgumentParser(description="Run Quickstart Flask App")
parser.add_argument("--port", type=int, help="Specify the port number to run the server")
parser.add_argument("--debug", action="store_true", help="Enable debug mode")

if __name__ == "__main__":
    args = parser.parse_args()
else:
    args = argparse.Namespace(port=None, debug=False)

port = args.port if args.port else int(os.getenv("QS_PORT", "7171"))
running_port = port
app.config["QS_PORT"] = running_port
debug_mode = args.debug if args.debug else helpers.booler(os.getenv("QS_DEBUG", "0"))

helpers.ts_log(f"Running on port: {port} | Debug Mode: {'Enabled' if debug_mode else 'Disabled'}", level="INFO")


@app.route("/")
def start():
    return redirect(url_for("step", name="001-start"))


def _build_logscan_resolution_context(log_dir=None, include_candidate_files=True):
    cache_entries = []
    ingest_cache = _load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    if isinstance(cache_logs, dict):
        for raw_path, entry in cache_logs.items():
            if not isinstance(entry, dict):
                continue
            try:
                path = Path(raw_path).resolve()
            except Exception:
                continue
            if not path.exists() or not path.is_file():
                continue
            try:
                stats = path.stat()
            except Exception:
                continue
            cache_entries.append(
                {
                    "path": path,
                    "mtime": float(stats.st_mtime),
                    "size": int(stats.st_size),
                    "run_key": entry.get("run_key"),
                    "tool_name": _normalize_logscan_tool_name(entry.get("tool_name") or _detect_logscan_tool_from_path(path, log_dir=log_dir)),
                }
            )

    candidate_files = []
    if include_candidate_files:
        for path in _iter_logscan_candidate_files(log_dir=log_dir, include_archive=True, include_compressed=True):
            try:
                stats = path.stat()
            except Exception:
                continue
            candidate_files.append(
                {
                    "path": path,
                    "mtime": float(stats.st_mtime),
                    "size": int(stats.st_size),
                    "location": _classify_logscan_file_location(path, log_dir=log_dir),
                    "tool_name": _detect_logscan_tool_from_path(path, log_dir=log_dir),
                }
            )
    return {"cache_entries": cache_entries, "candidate_files": candidate_files}


def _find_logscan_cache_entry_for_run(run_key):
    if not run_key:
        return None
    ingest_cache = _load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    if not isinstance(cache_logs, dict):
        return None
    for raw_path, entry in cache_logs.items():
        if not isinstance(entry, dict) or entry.get("run_key") != run_key:
            continue
        try:
            path = Path(raw_path).resolve()
        except Exception:
            continue
        if not path.exists() or not path.is_file():
            continue
        try:
            stats = path.stat()
            mtime = float(stats.st_mtime)
            size = int(stats.st_size)
        except Exception:
            mtime = float(entry.get("mtime", 0) or 0)
            size = int(entry.get("size", 0) or 0)
        return {
            "path": path,
            "mtime": mtime,
            "size": size,
            "run_key": entry.get("run_key"),
            "tool_name": _normalize_logscan_tool_name(entry.get("tool_name") or _detect_logscan_tool_from_path(path)),
        }
    return None


def _match_logscan_run_to_file(run_record, context=None, log_dir=None, allow_live_fallback=True):
    if not isinstance(run_record, dict):
        return None
    context = context or _build_logscan_resolution_context(log_dir=log_dir)
    run_key = run_record.get("run_key")
    run_tool_name = _normalize_logscan_tool_name(run_record.get("tool_name"))
    if run_key:
        cache_matches = [
            entry for entry in context.get("cache_entries", []) if entry.get("run_key") == run_key and _normalize_logscan_tool_name(entry.get("tool_name")) == run_tool_name
        ]
        if cache_matches:
            cache_matches.sort(key=lambda entry: entry.get("mtime", 0), reverse=True)
            match = cache_matches[0]
            return {
                "path": match["path"],
                "location": _classify_logscan_file_location(match["path"], log_dir=log_dir),
                "size": match.get("size"),
                "mtime": match.get("mtime"),
                "source": "cache",
            }

    target_mtime = run_record.get("log_mtime")
    target_size = run_record.get("log_size")
    candidates = []
    for entry in context.get("candidate_files", []):
        if _normalize_logscan_tool_name(entry.get("tool_name")) != run_tool_name:
            continue
        if not allow_live_fallback and entry.get("location") == "live":
            continue
        size_matches = target_size is not None and entry.get("size") == target_size
        mtime_delta = None
        mtime_matches = False
        if target_mtime is not None:
            try:
                mtime_delta = abs(float(entry.get("mtime", 0)) - float(target_mtime))
                mtime_matches = mtime_delta <= 1.0
            except Exception:
                mtime_delta = None
        if not size_matches and not mtime_matches:
            continue
        rank = 0
        if size_matches:
            rank += 2
        if mtime_matches:
            rank += 2
        candidates.append((rank, mtime_delta if mtime_delta is not None else 999999, -entry.get("mtime", 0), entry))
    if not candidates:
        return None
    candidates.sort()
    match = candidates[0][3]
    return {
        "path": match["path"],
        "location": match.get("location") or _classify_logscan_file_location(match["path"], log_dir=log_dir),
        "size": match.get("size"),
        "mtime": match.get("mtime"),
        "source": "fallback",
    }


def _resolve_logscan_run_log_info(run_key, run_record=None, context=None):
    if not run_key:
        return None
    run_tool_name = _normalize_logscan_tool_name(run_record.get("tool_name")) if isinstance(run_record, dict) else None
    cache_matches = []
    if isinstance(context, dict):
        cache_matches = [
            entry
            for entry in context.get("cache_entries", [])
            if entry.get("run_key") == run_key and (not run_tool_name or _normalize_logscan_tool_name(entry.get("tool_name")) == run_tool_name)
        ]
    else:
        direct_match = _find_logscan_cache_entry_for_run(run_key)
        if direct_match and (not run_tool_name or _normalize_logscan_tool_name(direct_match.get("tool_name")) == run_tool_name):
            cache_matches = [direct_match]
    if cache_matches:
        cache_matches.sort(key=lambda entry: entry.get("mtime", 0), reverse=True)
        match = cache_matches[0]
        location = _classify_logscan_file_location(match["path"])
        if not (isinstance(run_record, dict) and location == "live"):
            return {
                "path": match["path"],
                "location": location,
                "size": match.get("size"),
                "mtime": match.get("mtime"),
                "source": "cache",
            }
    run_record = run_record if isinstance(run_record, dict) else database.get_log_run(run_key)
    if not run_record:
        if cache_matches:
            match = cache_matches[0]
            return {
                "path": match["path"],
                "location": _classify_logscan_file_location(match["path"]),
                "size": match.get("size"),
                "mtime": match.get("mtime"),
                "source": "cache",
            }
        return None
    full_context = context
    if not isinstance(full_context, dict) or not isinstance(full_context.get("candidate_files"), list) or not full_context.get("candidate_files"):
        full_context = _build_logscan_resolution_context(include_candidate_files=True)
    info = _match_logscan_run_to_file(run_record, context=full_context, allow_live_fallback=False)
    if info:
        return info
    if cache_matches:
        match = cache_matches[0]
        return {
            "path": match["path"],
            "location": _classify_logscan_file_location(match["path"]),
            "size": match.get("size"),
            "mtime": match.get("mtime"),
            "source": "cache",
        }
    return None


def _resolve_logscan_run_log_path(run_key):
    info = _resolve_logscan_run_log_info(run_key)
    return info.get("path") if isinstance(info, dict) else None


def _resolve_logscan_run_archive_action_info(run_key, prefer_uncompressed=False):
    run_key = str(run_key or "").strip()
    if not run_key:
        return None
    run_record = database.get_log_run(run_key)
    run_tool_name = _normalize_logscan_tool_name(run_record.get("tool_name")) if isinstance(run_record, dict) else None
    ingest_cache = _load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    if isinstance(cache_logs, dict):
        archive_matches = []
        for raw_path, entry in cache_logs.items():
            if not isinstance(entry, dict) or entry.get("run_key") != run_key:
                continue
            try:
                path = Path(raw_path).resolve()
            except Exception:
                continue
            if not path.exists() or not path.is_file():
                continue
            location = _classify_logscan_file_location(path)
            if location != "archive":
                continue
            if run_tool_name and _normalize_logscan_tool_name(entry.get("tool_name") or _detect_logscan_tool_from_path(path)) != run_tool_name:
                continue
            try:
                stats = path.stat()
                size = int(stats.st_size)
                mtime = float(stats.st_mtime)
            except Exception:
                size = int(entry.get("size", 0) or 0)
                mtime = float(entry.get("mtime", 0) or 0)
            archive_matches.append(
                {
                    "path": path,
                    "location": location,
                    "size": size,
                    "mtime": mtime,
                    "source": "cache",
                    "is_compressed": _is_logscan_gzip_path(path),
                }
            )
        if archive_matches:
            if prefer_uncompressed:
                plain_matches = [item for item in archive_matches if not item.get("is_compressed")]
                if plain_matches:
                    plain_matches.sort(key=lambda item: item.get("mtime", 0), reverse=True)
                    return plain_matches[0]
            archive_matches.sort(key=lambda item: item.get("mtime", 0), reverse=True)
            return archive_matches[0]
    return None


def _delete_logscan_run_artifact(run_key):
    run_key = str(run_key or "").strip()
    if not run_key:
        return False, {"error": "run_key required"}, 400
    run_record = database.get_log_run(run_key)
    incomplete_run = None if run_record else _get_logscan_incomplete_run(run_key)
    if not run_record and not incomplete_run:
        return False, {"error": "Run not found.", "run_key": run_key}, 404
    target_run = run_record if run_record else incomplete_run
    info = _resolve_logscan_run_log_info(run_key, run_record=target_run)
    if not info or not info.get("path"):
        return False, {"error": "Archived log file for this run could not be found.", "run_key": run_key}, 404
    if info.get("location") != "archive":
        return False, {"error": "Only archived logs can be deleted from Analytics.", "run_key": run_key}, 409
    deleted_file = False
    try:
        Path(info["path"]).unlink()
        deleted_file = True
    except FileNotFoundError:
        deleted_file = False
    except Exception as exc:
        return False, {"error": f"Failed to delete archived log: {exc}", "run_key": run_key}, 500

    if run_record:
        database.delete_log_run(run_key)
    _remove_logscan_ingest_cache_entries(run_key=run_key, raw_path=str(Path(info["path"]).resolve()))
    return (
        True,
        {
            "success": True,
            "run_key": run_key,
            "deleted_file": deleted_file,
            "deleted_run": bool(run_record),
        },
        200,
    )


def _compress_logscan_run_artifact(run_key):
    run_key = str(run_key or "").strip()
    if not run_key:
        return False, {"error": "run_key required"}, 400
    run_record = database.get_log_run(run_key)
    incomplete_run = None if run_record else _get_logscan_incomplete_run(run_key)
    if not run_record and not incomplete_run:
        return False, {"error": "Run not found.", "run_key": run_key}, 404
    target_run = run_record if run_record else incomplete_run
    info = _resolve_logscan_run_archive_action_info(run_key, prefer_uncompressed=True) or _resolve_logscan_run_log_info(run_key, run_record=target_run)
    if not info or not info.get("path"):
        return False, {"error": "Archived log file for this run could not be found.", "run_key": run_key}, 404
    source_path = Path(info["path"])
    if info.get("location") != "archive":
        return False, {"error": "Only archived logs can be compressed from Analytics.", "run_key": run_key}, 409
    if _is_logscan_gzip_path(source_path):
        return False, {"error": "Archived log is already compressed.", "run_key": run_key}, 409

    tool_name = _normalize_logscan_tool_name((target_run or {}).get("tool_name") or _detect_logscan_tool_from_path(source_path))
    archive_dir = _get_logscan_archive_dir(tool_name)
    compressed_path = _archive_log_file(source_path, archive_dir)
    if not compressed_path or not compressed_path.exists():
        return False, {"error": "Failed to compress archived log.", "run_key": run_key}, 500

    cache = _load_logscan_ingest_cache()
    cache_logs = cache.get("logs", {}) if isinstance(cache, dict) else {}
    if not isinstance(cache_logs, dict):
        cache_logs = {}
    source_key = str(source_path.resolve())
    compressed_key = str(compressed_path.resolve())
    cache_entry = cache_logs.pop(source_key, None)
    if not isinstance(cache_entry, dict):
        cache_entry = {
            "run_key": run_key,
            "run_complete": not bool(incomplete_run),
        }
    cache_entry["tool_name"] = tool_name
    try:
        compressed_stats = compressed_path.stat()
        cache_entry["mtime"] = compressed_stats.st_mtime
        cache_entry["size"] = compressed_stats.st_size
    except Exception:
        pass
    cache_entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    cache_logs[compressed_key] = cache_entry
    cache["logs"] = cache_logs
    _save_logscan_ingest_cache(cache)

    return (
        True,
        {
            "success": True,
            "run_key": run_key,
            "compressed_file": True,
            "compressed_path": compressed_key,
        },
        200,
    )


def _annotate_logscan_runs(runs, context=None):
    if not isinstance(runs, list) or not runs:
        return [] if isinstance(runs, list) else []
    context = context or _build_logscan_resolution_context()
    annotated = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        row = dict(run)
        if str(row.get("tool_name") or "").strip().lower() == "imagemaid":
            row["config_name"] = _resolve_imagemaid_run_config_name(row)
        info = _resolve_logscan_run_log_info(row.get("run_key"), run_record=row, context=context)
        row["log_available"] = bool(info and info.get("path"))
        row["log_location"] = info.get("location") if info else "missing"
        row["log_resolved_size"] = info.get("size") if info and isinstance(info.get("size"), int) else row.get("log_size")
        row["log_is_compressed"] = bool(info and info.get("path") and _is_logscan_gzip_path(info["path"]))
        row["log_can_delete"] = row["log_location"] == "archive" and row["log_available"]
        row["log_can_compress"] = row["log_location"] == "archive" and row["log_available"] and not row["log_is_compressed"]
        annotated.append(row)
    return annotated


@app.route("/logscan/trends/log", methods=["GET"])
def logscan_trends_log_download():
    run_key = request.args.get("run_key")
    if not run_key:
        return jsonify({"error": "run_key required"}), 400
    log_path = _resolve_logscan_run_log_path(run_key)
    if not log_path:
        return jsonify({"error": "Log file for this run could not be found."}), 404
    mimetype = "application/gzip" if _is_logscan_gzip_path(log_path) else "text/plain"
    return send_file(
        str(log_path),
        as_attachment=True,
        download_name=log_path.name,
        mimetype=mimetype,
    )


@app.route("/logscan/trends/log/delete", methods=["POST"])
def logscan_trends_log_delete():
    payload = request.get_json(silent=True) or {}
    raw_run_keys = payload.get("run_keys")
    if isinstance(raw_run_keys, list):
        run_keys = [str(value or "").strip() for value in raw_run_keys if str(value or "").strip()]
    else:
        run_key = str(payload.get("run_key", "")).strip()
        run_keys = [run_key] if run_key else []
    unique_run_keys = list(dict.fromkeys(run_keys))
    if not unique_run_keys:
        return jsonify({"error": "run_key required"}), 400

    deleted = []
    failures = []
    for run_key in unique_run_keys:
        success, result, status = _delete_logscan_run_artifact(run_key)
        if success:
            deleted.append(result)
        else:
            result["status"] = status
            failures.append(result)

    if not deleted and failures:
        first = failures[0]
        return jsonify({"success": False, "error": first.get("error"), "failures": failures}), int(first.get("status", 400))

    response = {
        "success": not failures,
        "deleted": len(deleted),
        "results": deleted,
        "deleted_file_count": sum(1 for item in deleted if item.get("deleted_file")),
        "deleted_run_count": sum(1 for item in deleted if item.get("deleted_run")),
        "failures": failures,
    }
    if len(unique_run_keys) == 1 and deleted:
        response["deleted_file"] = bool(deleted[0].get("deleted_file"))
        response["deleted_run"] = bool(deleted[0].get("deleted_run"))
    return jsonify(response)


@app.route("/logscan/trends/log/invalid/delete", methods=["POST"])
def logscan_trends_log_invalid_delete():
    invalid_entries = _get_logscan_invalid_archived_logs()
    if not invalid_entries:
        return jsonify({"success": True, "deleted": 0, "results": [], "failures": []})

    deleted = []
    failures = []
    for entry in invalid_entries:
        raw_path = entry.get("path")
        if not raw_path:
            failures.append({"error": "Invalid archived log path missing.", "name": entry.get("name"), "status": 500})
            continue
        path = Path(raw_path)
        deleted_file = False
        try:
            path.unlink()
            deleted_file = True
        except FileNotFoundError:
            deleted_file = False
        except Exception as exc:
            failures.append({"error": f"Failed to delete invalid archived log: {exc}", "name": entry.get("name"), "path": raw_path, "status": 500})
            continue
        _remove_logscan_ingest_cache_entries(raw_path=str(path.resolve()))
        deleted.append(
            {
                "name": entry.get("name"),
                "path": raw_path,
                "tool_name": entry.get("tool_name"),
                "reason": entry.get("reason"),
                "deleted_file": deleted_file,
            }
        )

    if not deleted and failures:
        first = failures[0]
        return jsonify({"success": False, "error": first.get("error"), "failures": failures}), int(first.get("status", 500))

    return jsonify(
        {
            "success": not failures,
            "deleted": len(deleted),
            "deleted_file_count": sum(1 for item in deleted if item.get("deleted_file")),
            "results": deleted,
            "failures": failures,
        }
    )


@app.route("/logscan/trends/log/compress", methods=["POST"])
def logscan_trends_log_compress():
    payload = request.get_json(silent=True) or {}
    raw_run_keys = payload.get("run_keys")
    if isinstance(raw_run_keys, list):
        run_keys = [str(value or "").strip() for value in raw_run_keys if str(value or "").strip()]
    else:
        run_key = str(payload.get("run_key", "")).strip()
        run_keys = [run_key] if run_key else []
    unique_run_keys = list(dict.fromkeys(run_keys))
    if not unique_run_keys:
        return jsonify({"error": "run_key required"}), 400

    compressed = []
    failures = []
    for run_key in unique_run_keys:
        success, result, status = _compress_logscan_run_artifact(run_key)
        if success:
            compressed.append(result)
        else:
            result["status"] = status
            failures.append(result)

    if not compressed and failures:
        first = failures[0]
        return jsonify({"success": False, "error": first.get("error"), "failures": failures}), int(first.get("status", 400))

    response = {
        "success": not failures,
        "compressed": len(compressed),
        "results": compressed,
        "failures": failures,
    }
    if len(unique_run_keys) == 1 and compressed:
        response["compressed_file"] = bool(compressed[0].get("compressed_file"))
        response["compressed_path"] = compressed[0].get("compressed_path")
    return jsonify(response)


def count_annotated_lines(text: str) -> dict:
    imported = 0
    not_imported = 0
    if not isinstance(text, str):
        return {"imported": 0, "not_imported": 0}
    imported_pattern = re.compile(r"(?:#|\|) imported(?:\s*-.*)?$")
    not_imported_pattern = re.compile(r"(?:#|\|) not imported(?:\s*-.*)?$")
    for line in text.splitlines():
        trimmed = line.rstrip()
        if imported_pattern.search(trimmed):
            imported += 1
        elif not_imported_pattern.search(trimmed):
            not_imported += 1
    return {"imported": imported, "not_imported": not_imported}


def _import_preview_json_default(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(str(item) for item in value)
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return isoformat()
        except Exception:
            pass
    return str(value)


def _coerce_validation_response_payload(response):
    if isinstance(response, tuple) and response:
        response = response[0]
    if hasattr(response, "get_json"):
        response = response.get_json()
    return response if isinstance(response, dict) else {}


@app.route("/import-config/preview", methods=["POST"])
def import_config_preview():
    def count_comment_lines(text: str) -> int:
        if not isinstance(text, str):
            return 0
        return sum(1 for line in text.splitlines() if line.lstrip().startswith("#"))

    def count_blank_lines(text: str) -> int:
        if not isinstance(text, str):
            return 0
        return sum(1 for line in text.splitlines() if not line.strip())

    def count_annotated_lines(text: str) -> dict:
        imported = 0
        not_imported = 0
        if not isinstance(text, str):
            return {"imported": 0, "not_imported": 0}
        imported_pattern = re.compile(r"(?:#|\|) imported(?:\s*-.*)?$")
        not_imported_pattern = re.compile(r"(?:#|\|) not imported(?:\s*-.*)?$")
        for line in text.splitlines():
            trimmed = line.rstrip()
            if imported_pattern.search(trimmed):
                imported += 1
            elif not_imported_pattern.search(trimmed):
                not_imported += 1
        return {"imported": imported, "not_imported": not_imported}

    upload = request.files.get("file")
    raw_name = request.form.get("config_name")
    config_name = importer.sanitize_config_name(raw_name)
    merge_mode = str(request.form.get("merge_mode") or "").strip().lower() in {"1", "true", "yes", "merge"}
    base_config = (request.form.get("base_config") or "").strip()

    if not upload or not upload.filename:
        return jsonify(success=False, message="No config file uploaded."), 400
    file_name = upload.filename.lower()
    if not file_name.endswith((".yml", ".yaml", ".zip")):
        return jsonify(success=False, message="Only .yml, .yaml, or .zip files are supported."), 400
    if not config_name:
        return jsonify(success=False, message="Config name is required."), 400

    available = database.get_unique_config_names() or []
    if any(name.lower() == config_name.lower() for name in available):
        return jsonify(success=False, message="Config name already exists."), 400
    if merge_mode:
        base_match = next((name for name in available if name.lower() == base_config.lower()), "")
        if not base_match:
            return jsonify(success=False, message="Base config not found. Select an existing config to merge."), 400
        base_config = base_match

    raw_text = upload.read()
    config_text = ""
    extracted_fonts = []
    extracted_dir = None
    if file_name.endswith(".zip"):
        try:
            with zipfile.ZipFile(BytesIO(raw_text)) as archive:
                archive_members = archive.namelist()
                unexpected_members = []
                bundled_library_files = []
                config_files = []
                font_files = []

                for member_name in archive_members:
                    normalized_member = _normalize_bundle_member_name(member_name)
                    if not normalized_member:
                        continue
                    if not _is_allowed_bundle_member(normalized_member):
                        unexpected_members.append(normalized_member)
                        continue
                    if _is_bundled_library_archive_member(normalized_member):
                        bundled_library_files.append(member_name)
                    elif _yaml_path_suffix(normalized_member):
                        config_files.append(member_name)
                    elif normalized_member.lower().endswith((".ttf", ".otf")):
                        font_files.append(member_name)

                if unexpected_members:
                    preview = ", ".join(unexpected_members[:5])
                    if len(unexpected_members) > 5:
                        preview += ", ..."
                    return jsonify(success=False, message=f"Zip file contains unsupported entries: {preview}"), 400
                if not config_files:
                    return jsonify(success=False, message="No YAML config found in zip file."), 400
                if len(config_files) > 1:
                    return jsonify(success=False, message="Zip file must contain exactly one YAML config."), 400

                try:
                    with archive.open(config_files[0]) as handle:
                        config_text = handle.read().decode("utf-8", errors="ignore")
                except Exception:
                    return jsonify(success=False, message="Unable to read config from zip."), 400

                if font_files or bundled_library_files:
                    cache_dir = Path(helpers.CONFIG_DIR) / "import_cache"
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    extracted_dir = cache_dir / f"bundle_{secrets.token_urlsafe(8)}"
                    extracted_dir.mkdir(parents=True, exist_ok=True)
                    if font_files:
                        fonts_dir = extracted_dir / "fonts"
                        fonts_dir.mkdir(parents=True, exist_ok=True)
                        seen_names = set()
                        for font_name in font_files:
                            base_name = os.path.basename(font_name)
                            if not base_name:
                                continue
                            safe_name = base_name
                            counter = 1
                            while safe_name in seen_names:
                                stem, ext = os.path.splitext(base_name)
                                safe_name = f"{stem}_{counter}{ext}"
                                counter += 1
                            seen_names.add(safe_name)
                            try:
                                with archive.open(font_name) as source:
                                    target = fonts_dir / safe_name
                                    with open(target, "wb") as dest:
                                        dest.write(source.read())
                                    extracted_fonts.append(safe_name)
                            except Exception:
                                continue
                    for member_name in bundled_library_files:
                        normalized_member = str(member_name).replace("\\", "/").lstrip("/")
                        if not normalized_member or normalized_member.endswith("/"):
                            continue
                        target = (extracted_dir / Path(normalized_member)).resolve()
                        try:
                            target.relative_to(extracted_dir.resolve())
                        except Exception:
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            with archive.open(member_name) as source, open(target, "wb") as dest:
                                dest.write(source.read())
                        except Exception:
                            continue
        except Exception:
            return jsonify(success=False, message="Unable to read zip file."), 400
    else:
        try:
            config_text = raw_text.decode("utf-8")
        except UnicodeDecodeError:
            config_text = raw_text.decode("utf-8", errors="ignore")

    parsed = importer.load_yaml_config(config_text)
    if not parsed:
        if extracted_dir:
            try:
                shutil.rmtree(extracted_dir)
            except OSError:
                pass
        return jsonify(success=False, message="Unable to parse config file."), 400
    if extracted_dir:
        parsed = _rewrite_bundle_library_paths(parsed, extracted_dir)

    def parse_list(value):
        if isinstance(value, str):
            return {v.strip() for v in value.split(",") if v.strip()}
        if isinstance(value, list):
            return {str(v).strip() for v in value if str(v).strip()}
        return set()

    def parse_base_plex_libraries(base_name: str):
        if not base_name:
            return set(), set()
        try:
            _validated, _user_entered, stored = database.retrieve_section_data(base_name, "plex")
        except Exception:
            return set(), set()
        if not isinstance(stored, dict):
            return set(), set()
        plex_block = stored.get("plex") if isinstance(stored.get("plex"), dict) else stored
        if not isinstance(plex_block, dict):
            return set(), set()
        return parse_list(plex_block.get("tmp_movie_libraries", "")), parse_list(plex_block.get("tmp_show_libraries", ""))

    def parse_plex_credentials(config_data):
        plex_block = config_data.get("plex", {}) if isinstance(config_data, dict) else {}
        if not isinstance(plex_block, dict):
            return "", ""
        url = plex_block.get("url") or plex_block.get("plex_url") or ""
        token = plex_block.get("token") or plex_block.get("plex_token") or ""
        return str(url).strip(), str(token).strip()

    def parse_base_plex_credentials(base_name: str):
        if not base_name:
            return "", ""
        try:
            _validated, _user_entered, stored = database.retrieve_section_data(base_name, "plex")
        except Exception:
            return "", ""
        if not isinstance(stored, dict):
            return "", ""
        if "plex" in stored:
            return parse_plex_credentials(stored)
        url = stored.get("url") or stored.get("plex_url") or ""
        token = stored.get("token") or stored.get("plex_token") or ""
        return str(url).strip(), str(token).strip()

    def parse_form_plex_credentials(form_data):
        url = form_data.get("plex_url", "") or ""
        token = form_data.get("plex_token", "") or ""
        return str(url).strip(), str(token).strip()

    def parse_tmdb_credentials(config_data):
        tmdb_block = config_data.get("tmdb", {}) if isinstance(config_data, dict) else {}
        if not isinstance(tmdb_block, dict):
            return ""
        api_key = tmdb_block.get("apikey") or tmdb_block.get("api_key") or tmdb_block.get("tmdb_apikey") or tmdb_block.get("token") or ""
        return str(api_key).strip()

    def parse_base_tmdb_credentials(base_name: str):
        if not base_name:
            return ""
        try:
            _validated, _user_entered, stored = database.retrieve_section_data(base_name, "tmdb")
        except Exception:
            return ""
        if not isinstance(stored, dict):
            return ""
        if "tmdb" in stored:
            return parse_tmdb_credentials(stored)
        api_key = stored.get("apikey") or stored.get("api_key") or stored.get("tmdb_apikey") or stored.get("token") or ""
        return str(api_key).strip()

    def parse_form_tmdb_credentials(form_data):
        api_key = form_data.get("tmdb_apikey", "") or ""
        return str(api_key).strip()

    needs_plex = isinstance(parsed.get("libraries"), dict) and bool(parsed.get("libraries"))
    needs_tmdb = isinstance(parsed, dict) and bool(parsed.get("tmdb") or parsed.get("libraries") or parsed.get("collections") or parsed.get("overlays"))
    plex_data = persistence.retrieve_settings("010-plex").get("plex", {})
    movie_names = parse_list(plex_data.get("tmp_movie_libraries", ""))
    show_names = parse_list(plex_data.get("tmp_show_libraries", ""))
    plex_libraries = {"movie": sorted(movie_names), "show": sorted(show_names)}

    if needs_plex:
        base_movie_names, base_show_names = (set(), set())
        skip_plex_validation = False
        if merge_mode and base_config:
            base_movie_names, base_show_names = parse_base_plex_libraries(base_config)
            if base_movie_names or base_show_names:
                movie_names = base_movie_names
                show_names = base_show_names
                plex_libraries = {"movie": sorted(movie_names), "show": sorted(show_names)}
                skip_plex_validation = True

        form_plex_url, form_plex_token = parse_form_plex_credentials(request.form or {})
        imported_plex_url, imported_plex_token = parse_plex_credentials(parsed)
        base_plex_url, base_plex_token = parse_base_plex_credentials(base_config) if merge_mode else ("", "")
        has_form = bool(form_plex_url and form_plex_token)
        has_imported = bool(imported_plex_url and imported_plex_token)
        has_base = bool(base_plex_url and base_plex_token)
        used_plex_url = ""
        used_plex_token = ""

        if not skip_plex_validation and not has_form and not has_imported and not has_base:
            if extracted_dir:
                try:
                    shutil.rmtree(extracted_dir)
                except OSError:
                    pass
            return (
                jsonify(
                    success=False,
                    needs_plex_credentials=True,
                    message=("Plex credentials are required to import library settings. " "Enter a Plex URL and token to continue."),
                    plex_url="",
                    plex_token="",
                ),
                400,
            )

        if not skip_plex_validation:
            plex_result = None
            last_error = None
            if has_form:
                used_plex_url = form_plex_url
                used_plex_token = form_plex_token
                plex_response = validations.validate_plex_server({"plex_url": form_plex_url, "plex_token": form_plex_token})
                plex_result = _coerce_validation_response_payload(plex_response)
                if not plex_result or not plex_result.get("validated"):
                    if isinstance(plex_result, dict):
                        last_error = plex_result.get("error")
                    if extracted_dir:
                        try:
                            shutil.rmtree(extracted_dir)
                        except OSError:
                            pass
                    return (
                        jsonify(
                            success=False,
                            needs_plex_credentials=True,
                            message=last_error or "Plex validation failed. Please enter valid credentials.",
                            plex_url=form_plex_url or "",
                            plex_token=form_plex_token or "",
                        ),
                        400,
                    )
            else:
                candidates = []
                if merge_mode and has_base:
                    candidates.append((base_plex_url, base_plex_token))
                if has_imported:
                    candidates.append((imported_plex_url, imported_plex_token))
                if not candidates:
                    candidates.append((imported_plex_url or base_plex_url, imported_plex_token or base_plex_token))
                for candidate_url, candidate_token in candidates:
                    used_plex_url = candidate_url
                    used_plex_token = candidate_token
                    plex_response = validations.validate_plex_server({"plex_url": used_plex_url, "plex_token": used_plex_token})
                    plex_result = _coerce_validation_response_payload(plex_response)
                    if plex_result and plex_result.get("validated"):
                        last_error = None
                        break
                    if isinstance(plex_result, dict):
                        last_error = plex_result.get("error")
                if not plex_result or not plex_result.get("validated"):
                    if extracted_dir:
                        try:
                            shutil.rmtree(extracted_dir)
                        except OSError:
                            pass
                    return (
                        jsonify(
                            success=False,
                            needs_plex_credentials=True,
                            message=last_error or ("Plex credentials from the import/base config could not be validated. " "Please enter a valid Plex URL and token."),
                            plex_url=imported_plex_url or base_plex_url or "",
                            plex_token=imported_plex_token or base_plex_token or "",
                        ),
                        400,
                    )
        if not skip_plex_validation:
            session["import_preview_plex_url"] = used_plex_url
            session["import_preview_plex_token"] = used_plex_token
        if used_plex_url and used_plex_token:
            plex_block = parsed.get("plex")
            if not isinstance(plex_block, dict):
                plex_block = {}
                parsed["plex"] = plex_block
            plex_block["url"] = used_plex_url
            plex_block["token"] = used_plex_token
        if not skip_plex_validation:
            movie_names = parse_list(plex_result.get("movie_libraries", []))
            show_names = parse_list(plex_result.get("show_libraries", []))
            plex_libraries = {"movie": sorted(movie_names), "show": sorted(show_names)}
            if not movie_names and not show_names:
                if extracted_dir:
                    try:
                        shutil.rmtree(extracted_dir)
                    except OSError:
                        pass
                return (
                    jsonify(
                        success=False,
                        message="No movie or show libraries found in Plex.",
                    ),
                    400,
                )

    if needs_tmdb:
        form_tmdb_key = parse_form_tmdb_credentials(request.form or {})
        imported_tmdb_key = parse_tmdb_credentials(parsed)
        base_tmdb_key = parse_base_tmdb_credentials(base_config) if merge_mode else ""
        has_form = bool(form_tmdb_key)
        has_imported = bool(imported_tmdb_key)
        has_base = bool(base_tmdb_key)
        used_tmdb_key = ""

        if not has_form and not has_imported and not has_base:
            if extracted_dir:
                try:
                    shutil.rmtree(extracted_dir)
                except OSError:
                    pass
            return (
                jsonify(
                    success=False,
                    needs_tmdb_credentials=True,
                    message="TMDb API key is required to import metadata settings. Enter a valid TMDb API key to continue.",
                    tmdb_apikey="",
                ),
                400,
            )

        tmdb_result = None
        last_error = None
        if has_form:
            used_tmdb_key = form_tmdb_key
            tmdb_response = validations.validate_tmdb_server({"tmdb_apikey": form_tmdb_key})
            tmdb_result = _coerce_validation_response_payload(tmdb_response)
            if not tmdb_result or not tmdb_result.get("valid"):
                if isinstance(tmdb_result, dict):
                    last_error = tmdb_result.get("message")
                if extracted_dir:
                    try:
                        shutil.rmtree(extracted_dir)
                    except OSError:
                        pass
                return (
                    jsonify(
                        success=False,
                        needs_tmdb_credentials=True,
                        message=last_error or "TMDb validation failed. Please enter a valid API key.",
                        tmdb_apikey=form_tmdb_key or "",
                    ),
                    400,
                )
        else:
            candidates = []
            if merge_mode and has_base:
                candidates.append(base_tmdb_key)
            if has_imported:
                candidates.append(imported_tmdb_key)
            if not candidates:
                candidates.append(imported_tmdb_key or base_tmdb_key)
            for candidate_key in candidates:
                used_tmdb_key = candidate_key
                tmdb_response = validations.validate_tmdb_server({"tmdb_apikey": used_tmdb_key})
                tmdb_result = _coerce_validation_response_payload(tmdb_response)
                if tmdb_result and tmdb_result.get("valid"):
                    last_error = None
                    break
                if isinstance(tmdb_result, dict):
                    last_error = tmdb_result.get("message")
            if not tmdb_result or not tmdb_result.get("valid"):
                if extracted_dir:
                    try:
                        shutil.rmtree(extracted_dir)
                    except OSError:
                        pass
                return (
                    jsonify(
                        success=False,
                        needs_tmdb_credentials=True,
                        message=last_error or "TMDb API key from the import/base config could not be validated. Please enter a valid key.",
                        tmdb_apikey=imported_tmdb_key or base_tmdb_key or "",
                    ),
                    400,
                )
        session["import_preview_tmdb_apikey"] = used_tmdb_key
        if used_tmdb_key:
            tmdb_block = parsed.get("tmdb")
            if not isinstance(tmdb_block, dict):
                tmdb_block = {}
                parsed["tmdb"] = tmdb_block
            tmdb_block["apikey"] = used_tmdb_key

    try:
        _library_types, library_inference, _ = importer.build_library_type_plan(parsed, movie_names, show_names)
        payload, report = importer.prepare_import_payload(
            parsed,
            movie_names,
            show_names,
        )
        if not payload:
            if extracted_dir:
                try:
                    shutil.rmtree(extracted_dir)
                except OSError:
                    pass
            return jsonify(success=False, message="No importable sections found."), 400
        importable_sections = sorted(payload.keys())

        report_lines = list(report.lines)
        if extracted_fonts:
            for font in extracted_fonts:
                report_lines.append(f"imported: bundle.fonts.{font}")
        annotated_report = importer.annotate_yaml_with_report(config_text, report_lines, binary=True)
        comments_count = count_comment_lines(config_text)
        blank_count = count_blank_lines(config_text)
        total_lines = len(config_text.splitlines()) if isinstance(config_text, str) else 0
        annotated_counts = count_annotated_lines(annotated_report)
        diff_count = total_lines - (annotated_counts.get("imported", 0) + annotated_counts.get("not_imported", 0) + blank_count + comments_count)
        line_counts = {
            "imported_lines": annotated_counts.get("imported", 0),
            "not_imported_lines": annotated_counts.get("not_imported", 0),
            "comments": comments_count,
            "blank": blank_count,
            "total": total_lines,
            "diff": diff_count,
        }

        previous_path = session.get("import_preview_path")
        if previous_path:
            try:
                os.remove(previous_path)
            except OSError:
                pass
        previous_dir = session.get("import_preview_bundle_dir")
        if previous_dir:
            try:
                shutil.rmtree(previous_dir)
            except OSError:
                pass

        cache_dir = Path(helpers.CONFIG_DIR) / "import_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(12)
        cache_path = cache_dir / f"import_{token}.json"
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "config_name": config_name,
                    "config_data": parsed,
                    "config_text": config_text,
                    "payload": payload,
                    "bundle_dir": str(extracted_dir) if extracted_dir else None,
                    "fonts_dir": str((extracted_dir / "fonts").resolve()) if extracted_dir and extracted_fonts else None,
                    "fonts": extracted_fonts,
                    "report_lines": report_lines,
                    "report_summary": report.summary(),
                    "annotated_report": annotated_report,
                    "comments_count": comments_count,
                    "line_counts": line_counts,
                    "plex_movie_names": sorted(movie_names) if isinstance(movie_names, (set, list)) else [],
                    "plex_show_names": sorted(show_names) if isinstance(show_names, (set, list)) else [],
                    "merge_mode": merge_mode,
                    "base_config": base_config,
                    "importable_sections": importable_sections,
                },
                handle,
                ensure_ascii=True,
                default=_import_preview_json_default,
            )
    except Exception as exc:
        if extracted_dir:
            try:
                shutil.rmtree(extracted_dir)
            except OSError:
                pass
        helpers.ts_log(f"Import preview failed: {exc}", level="ERROR")
        return jsonify(success=False, message=f"Import preview failed: {exc}"), 500

    session["import_preview_token"] = token
    session["import_preview_path"] = str(cache_path)
    session["import_preview_name"] = config_name
    session["import_preview_bundle_dir"] = str(extracted_dir) if extracted_dir else ""

    lines = list(report_lines)
    max_lines = 500
    if len(lines) > max_lines:
        truncated = len(lines) - max_lines
        lines = lines[:max_lines] + [f"skipped: report truncated ({truncated} more lines)"]

    library_mapping = []
    if needs_plex and isinstance(parsed.get("libraries"), dict):
        inference_map = {item.get("name"): item for item in library_inference}
        for lib_name in parsed.get("libraries", {}).keys():
            name = str(lib_name)
            if name in movie_names or name in show_names:
                continue
            info = inference_map.get(lib_name, {})
            library_mapping.append(
                {
                    "name": lib_name,
                    "inferred_type": info.get("type"),
                    "confidence": info.get("confidence"),
                    "movie_score": info.get("movie_score", 0),
                    "show_score": info.get("show_score", 0),
                }
            )

    return jsonify(
        success=True,
        token=token,
        config_name=config_name,
        summary=report.summary(),
        comments_count=comments_count,
        line_counts=line_counts,
        report_lines=lines,
        annotated_report=annotated_report,
        report_url=f"/import-config/report?token={token}",
        library_mapping=library_mapping,
        plex_libraries=plex_libraries,
        merge_mode=merge_mode,
        base_config=base_config,
        importable_sections=importable_sections,
    )


@app.route("/import-config/report", methods=["GET"])
def import_config_report():
    token = request.args.get("token")
    if not token or token != session.get("import_preview_token"):
        return jsonify(success=False, message="Import token is invalid."), 400

    cache_path = session.get("import_preview_path")
    if not cache_path:
        return jsonify(success=False, message="Import preview not found."), 400

    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
    except Exception:
        return jsonify(success=False, message="Import preview is unavailable."), 400

    config_name = cached.get("config_name") or "import"
    report_lines = cached.get("report_lines") or []
    summary = cached.get("report_summary") or {}
    annotated_report = cached.get("annotated_report")
    line_counts = cached.get("line_counts") or {}
    imported_count = line_counts.get("imported_lines", summary.get("imported", 0))
    not_imported_count = line_counts.get(
        "not_imported_lines",
        (summary.get("unmapped", 0) + summary.get("skipped", 0)),
    )
    comments_count = line_counts.get("comments", cached.get("comments_count", 0))
    blank_count = line_counts.get("blank", 0)
    total_count = line_counts.get("total", 0)
    diff_count = line_counts.get(
        "diff",
        total_count - (imported_count + not_imported_count + blank_count + comments_count),
    )

    if annotated_report:
        header = [
            f"# Import Report for {config_name}",
            f"# Imported: {imported_count}",
            f"# Not Imported: {not_imported_count}",
            f"# Comments: {comments_count}",
            f"# Blank: {blank_count}",
            f"# Total: {total_count}",
            f"# Diff: {diff_count}",
            "",
        ]
        text = "\n".join(header) + str(annotated_report)
    else:
        header = [
            f"Import Report for {config_name}",
            f"Imported: {imported_count}",
            f"Not Imported: {not_imported_count}",
            f"Comments: {comments_count}",
            f"Blank: {blank_count}",
            f"Total: {total_count}",
            f"Diff: {diff_count}",
            "",
        ]
        text = "\n".join(header + [str(line) for line in report_lines])
    response = app.response_class(text, mimetype="text/plain")
    response.headers["Content-Disposition"] = f'attachment; filename="{config_name}_import_report.txt"'
    return response


def _map_playlist_libraries(payload, library_mapping, plex_names):
    if not isinstance(payload, dict):
        return
    playlist_payload = payload.get("playlist_files")
    if not isinstance(playlist_payload, list):
        return
    mapped_entries = []
    for entry in playlist_payload:
        if not isinstance(entry, dict):
            mapped_entries.append(entry)
            continue
        tv = entry.get("template_variables")
        if isinstance(tv, dict):
            libs = tv.get("libraries")
            if isinstance(libs, list):
                mapped = []
                for lib in libs:
                    name = str(lib).strip()
                    if not name:
                        continue
                    mapped_name = library_mapping.get(name, name)
                    if mapped_name is None:
                        mapped_name = name
                    mapped_name = str(mapped_name).strip()
                    if not mapped_name or mapped_name == "__ignore__":
                        continue
                    mapped.append(mapped_name)
                deduped = []
                seen = set()
                for lib_name in mapped:
                    if lib_name in seen:
                        continue
                    seen.add(lib_name)
                    deduped.append(lib_name)
                if plex_names:
                    deduped = [lib_name for lib_name in deduped if lib_name in plex_names]
                tv = dict(tv)
                tv["libraries"] = deduped
                entry = dict(entry)
                entry["template_variables"] = tv
        mapped_entries.append(entry)
    payload["playlist_files"] = mapped_entries


@app.route("/import-config/preview-mapped", methods=["POST"])
def import_config_preview_mapped():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    library_mapping = data.get("library_mapping") or {}
    if not token or token != session.get("import_preview_token"):
        return jsonify(success=False, message="Import token is invalid."), 400
    if library_mapping and not isinstance(library_mapping, dict):
        return jsonify(success=False, message="Invalid library mapping."), 400

    cache_path = session.get("import_preview_path")
    if not cache_path:
        return jsonify(success=False, message="Import preview not found."), 400

    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
    except Exception:
        return jsonify(success=False, message="Import preview is unavailable."), 400

    config_data = cached.get("config_data") or {}
    if not isinstance(config_data, dict):
        config_data = {}
    config_text = cached.get("config_text") or ""

    def parse_list(value):
        if isinstance(value, str):
            return {v.strip() for v in value.split(",") if v.strip()}
        if isinstance(value, list):
            return {str(v).strip() for v in value if str(v).strip()}
        return set()

    movie_names = parse_list(cached.get("plex_movie_names") or [])
    show_names = parse_list(cached.get("plex_show_names") or [])
    needs_plex = isinstance(config_data.get("libraries"), dict) and bool(config_data.get("libraries"))

    if needs_plex and not movie_names and not show_names:
        plex_url = session.get("import_preview_plex_url") or ""
        plex_token = session.get("import_preview_plex_token") or ""
        if plex_url and plex_token:
            plex_response = validations.validate_plex_server({"plex_url": plex_url, "plex_token": plex_token})
            plex_result = _coerce_validation_response_payload(plex_response)
            if plex_result and plex_result.get("validated"):
                movie_names = parse_list(plex_result.get("movie_libraries", []))
                show_names = parse_list(plex_result.get("show_libraries", []))

    plex_lookup = {name: name for name in movie_names}
    plex_lookup.update({name: name for name in show_names})
    plex_names = set(plex_lookup.values())

    mapping_skip_reasons = {}
    alias_map = {}
    mapping_stats = {"mapped": 0, "ignored": 0, "missing": 0, "invalid": 0, "duplicate": 0}
    if isinstance(config_data.get("libraries"), dict):
        mapped_libraries = {}
        used_targets = set()
        for lib_name, lib_cfg in config_data.get("libraries", {}).items():
            name = str(lib_name)
            if name in plex_lookup:
                target = plex_lookup[name]
            else:
                mapped = library_mapping.get(name)
                if mapped is None or str(mapped).strip() == "":
                    mapping_skip_reasons[name] = "Library mapping not provided."
                    mapping_stats["missing"] += 1
                    continue
                mapped = str(mapped).strip()
                if mapped == "__ignore__":
                    mapping_skip_reasons[name] = "Mapping set to ignore library."
                    mapping_stats["ignored"] += 1
                    continue
                if mapped not in plex_lookup:
                    mapping_skip_reasons[name] = "Mapped library not found in Plex."
                    mapping_stats["invalid"] += 1
                    continue
                target = plex_lookup[mapped]

            if target != name:
                alias_map[name] = target

            if target in used_targets:
                mapping_skip_reasons[name] = "Mapped library already assigned to another entry."
                if name not in plex_names:
                    mapping_stats["duplicate"] += 1
                continue
            used_targets.add(target)
            mapped_libraries[target] = lib_cfg
            if name not in plex_names:
                mapping_stats["mapped"] += 1

        config_copy = json.loads(json.dumps(config_data))
        if mapped_libraries:
            config_copy["libraries"] = mapped_libraries
        else:
            config_copy.pop("libraries", None)
    else:
        config_copy = config_data

    _map_playlist_libraries(config_copy, library_mapping, plex_names)

    payload, report = importer.prepare_import_payload(config_copy, movie_names, show_names)
    importable_sections = sorted(payload.keys()) if isinstance(payload, dict) else []
    report_lines = list(report.lines)
    if mapping_skip_reasons:
        seen = set(report_lines)
        for lib_name, reason in mapping_skip_reasons.items():
            if not lib_name:
                continue
            line = f"skipped: libraries.{lib_name} :: {reason}"
            if line not in seen:
                report_lines.append(line)
                seen.add(line)
    if alias_map and isinstance(config_data.get("libraries"), dict):
        alias_lines = []
        seen = set(report_lines)
        for original_name, mapped_name in alias_map.items():
            if not original_name:
                continue
            mapped_name = str(mapped_name).strip()
            if not mapped_name or mapped_name == "__ignore__":
                continue
            if mapped_name == original_name:
                continue
            prefix = f"libraries.{mapped_name}"
            for line in report_lines:
                if not isinstance(line, str) or ":" not in line:
                    continue
                status, rest = line.split(":", 1)
                status = status.strip()
                path = rest.strip()
                suffix = ""
                if " :: " in path:
                    path, reason = path.split(" :: ", 1)
                    path = path.strip()
                    suffix = f" :: {reason}"
                elif status != "imported" and " - " in path:
                    path, reason = path.split(" - ", 1)
                    path = path.strip()
                    suffix = f" - {reason}"
                if path == prefix or path.startswith(prefix + "."):
                    alias_path = f"libraries.{original_name}{path[len(prefix):]}"
                    alias_line = f"{status}: {alias_path}{suffix}"
                    if alias_line not in seen:
                        alias_lines.append(alias_line)
                        seen.add(alias_line)
        if alias_lines:
            report_lines.extend(alias_lines)
    annotated_report = importer.annotate_yaml_with_report(config_text, report_lines, binary=True)
    comments_count = cached.get("comments_count")
    if not isinstance(comments_count, int):
        comments_count = sum(1 for line in str(config_text).splitlines() if line.lstrip().startswith("#"))
    blank_count = sum(1 for line in str(config_text).splitlines() if not line.strip())
    total_lines = len(str(config_text).splitlines())
    annotated_counts = count_annotated_lines(str(annotated_report))
    imported_lines = annotated_counts.get("imported", 0)
    not_imported_lines = annotated_counts.get("not_imported", 0)
    diff_count = total_lines - (imported_lines + not_imported_lines + blank_count + comments_count)
    line_counts = {
        "imported_lines": imported_lines,
        "not_imported_lines": not_imported_lines,
        "comments": comments_count,
        "blank": blank_count,
        "total": total_lines,
        "diff": diff_count,
    }

    cached["payload"] = payload
    cached["report_lines"] = report_lines
    cached["report_summary"] = report.summary()
    cached["annotated_report"] = annotated_report
    cached["comments_count"] = comments_count
    cached["line_counts"] = line_counts
    cached["plex_movie_names"] = sorted(movie_names)
    cached["plex_show_names"] = sorted(show_names)
    cached["importable_sections"] = importable_sections

    with open(cache_path, "w", encoding="utf-8") as handle:
        json.dump(cached, handle, ensure_ascii=True, default=_import_preview_json_default)

    lines = list(report_lines)
    max_lines = 500
    if len(lines) > max_lines:
        truncated = len(lines) - max_lines
        lines = lines[:max_lines] + [f"skipped: report truncated ({truncated} more lines)"]

    mapping_total = sum(mapping_stats.values())
    mapping_summary = mapping_stats if mapping_total else {}

    return jsonify(
        success=True,
        config_name=cached.get("config_name") or "",
        summary=report.summary(),
        comments_count=comments_count,
        line_counts=line_counts,
        report_lines=lines,
        annotated_report=annotated_report,
        mapping_summary=mapping_summary,
        report_url=f"/import-config/report?token={token}",
        importable_sections=importable_sections,
    )


@app.route("/import-config/confirm", methods=["POST"])
def import_config_confirm():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    library_mapping = data.get("library_mapping") or {}
    raw_merge_mode = data.get("merge_mode")
    base_config = (data.get("base_config") or "").strip()
    merge_sections = data.get("merge_sections")
    if not token or token != session.get("import_preview_token"):
        return jsonify(success=False, message="Import token is invalid."), 400
    if library_mapping and not isinstance(library_mapping, dict):
        return jsonify(success=False, message="Invalid library mapping."), 400

    def _boolish(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "merge", "on"}
        return False

    merge_mode = _boolish(raw_merge_mode)

    cache_path = session.get("import_preview_path")
    if not cache_path:
        return jsonify(success=False, message="Import preview not found."), 400

    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
    except Exception:
        return jsonify(success=False, message="Import preview is unavailable."), 400

    config_name = cached.get("config_name")
    payload = cached.get("payload") or {}
    config_data = cached.get("config_data") or {}
    bundle_dir = cached.get("bundle_dir")
    fonts_dir = cached.get("fonts_dir")
    fonts = cached.get("fonts") or []
    cached_merge_mode = helpers.booler(cached.get("merge_mode"))
    if not merge_mode:
        merge_mode = cached_merge_mode
    if not base_config:
        base_config = cached.get("base_config") or ""
    if merge_sections is None:
        merge_sections = cached.get("merge_sections")
    if isinstance(merge_sections, str):
        merge_sections = [entry.strip() for entry in merge_sections.split(",") if entry.strip()]
    elif not isinstance(merge_sections, list):
        merge_sections = []
    merge_sections = [str(entry).strip() for entry in merge_sections if str(entry).strip()]
    if not isinstance(config_data, dict):
        config_data = {}
    importable_sections = set(cached.get("importable_sections") or payload.keys())
    selected_sections = set()
    if merge_mode:
        if not base_config:
            return jsonify(success=False, message="Base config is required for merge."), 400
        available = database.get_unique_config_names() or []
        base_match = next((name for name in available if name.lower() == base_config.lower()), "")
        if not base_match:
            return jsonify(success=False, message="Base config not found. Select an existing config to merge."), 400
        base_config = base_match
        if merge_sections:
            selected_sections = {section for section in merge_sections if section in importable_sections}
        else:
            selected_sections = set(importable_sections)
        if "playlist_files" in selected_sections:
            selected_sections.discard("playlist_files")
            selected_sections.add("libraries")
        if not selected_sections:
            return jsonify(success=False, message="Select at least one section to merge."), 400
        selected_config_sections = set(selected_sections)
        if "libraries" in selected_config_sections:
            selected_config_sections.add("playlist_files")
        config_data = {key: value for key, value in config_data.items() if key in selected_config_sections}
    if not config_name:
        return jsonify(success=False, message="Import payload is invalid."), 400

    available = database.get_unique_config_names() or []
    if any(name.lower() == str(config_name).lower() for name in available):
        return jsonify(success=False, message="Config name already exists."), 400

    def parse_list(value):
        if isinstance(value, str):
            return {v.strip() for v in value.split(",") if v.strip()}
        if isinstance(value, list):
            return {str(v).strip() for v in value if str(v).strip()}
        return set()

    def parse_base_plex_libraries(base_name: str):
        if not base_name:
            return set(), set()
        try:
            _validated, _user_entered, stored = database.retrieve_section_data(base_name, "plex")
        except Exception:
            return set(), set()
        if not isinstance(stored, dict):
            return set(), set()
        plex_block = stored.get("plex") if isinstance(stored.get("plex"), dict) else stored
        if not isinstance(plex_block, dict):
            return set(), set()
        return parse_list(plex_block.get("tmp_movie_libraries", "")), parse_list(plex_block.get("tmp_show_libraries", ""))

    movie_names = set()
    show_names = set()
    if config_data:
        libraries_payload = config_data.get("libraries")
        needs_plex = isinstance(libraries_payload, dict) and bool(libraries_payload)
        needs_tmdb = isinstance(config_data, dict) and bool(
            config_data.get("tmdb") or config_data.get("libraries") or config_data.get("collections") or config_data.get("overlays")
        )
        if needs_plex:
            skip_plex_validation = False
            if merge_mode and base_config:
                base_movie_names, base_show_names = parse_base_plex_libraries(base_config)
                if base_movie_names or base_show_names:
                    movie_names = base_movie_names
                    show_names = base_show_names
                    skip_plex_validation = True

            if skip_plex_validation:
                plex_names = set(movie_names) | set(show_names)
                if not plex_names:
                    skip_plex_validation = False
            if skip_plex_validation:
                # Skip Plex validation when base config provides library cache.
                pass
            else:
                plex_url = session.get("import_preview_plex_url") or ""
                plex_token = session.get("import_preview_plex_token") or ""
                if not plex_url or not plex_token:
                    return (
                        jsonify(
                            success=False,
                            message="Plex credentials are required to confirm the import. Re-run Preview Import.",
                        ),
                        400,
                    )

                plex_response = validations.validate_plex_server({"plex_url": plex_url, "plex_token": plex_token})
                plex_result = plex_response.get_json() if isinstance(plex_response, Flask.response_class) else plex_response
                if not plex_result or not plex_result.get("validated"):
                    error_message = plex_result.get("error") if isinstance(plex_result, dict) else None
                    return (
                        jsonify(
                            success=False,
                            message=error_message or "Plex validation failed. Re-run Preview Import.",
                        ),
                        400,
                    )
                movie_names = parse_list(plex_result.get("movie_libraries", []))
                show_names = parse_list(plex_result.get("show_libraries", []))
                if not movie_names and not show_names:
                    return (
                        jsonify(
                            success=False,
                            message="No movie or show libraries found in Plex.",
                        ),
                        400,
                    )
        else:
            plex_data = persistence.retrieve_settings("010-plex").get("plex", {})
            movie_names = parse_list(plex_data.get("tmp_movie_libraries", ""))
            show_names = parse_list(plex_data.get("tmp_show_libraries", ""))

        if needs_tmdb:
            tmdb_apikey = session.get("import_preview_tmdb_apikey") or ""
            if not tmdb_apikey:
                return (
                    jsonify(
                        success=False,
                        message="TMDb API key is required to confirm the import. Re-run Preview Import.",
                    ),
                    400,
                )
            tmdb_response = validations.validate_tmdb_server({"tmdb_apikey": tmdb_apikey})
            tmdb_result = tmdb_response.get_json() if isinstance(tmdb_response, Flask.response_class) else tmdb_response
            if not tmdb_result or not tmdb_result.get("valid"):
                error_message = tmdb_result.get("message") if isinstance(tmdb_result, dict) else None
                return (
                    jsonify(
                        success=False,
                        message=error_message or "TMDb validation failed. Re-run Preview Import.",
                    ),
                    400,
                )

        plex_lookup = {name: name for name in movie_names}
        plex_lookup.update({name: name for name in show_names})
        plex_names = set(plex_lookup.values())

        if isinstance(libraries_payload, dict):
            if needs_plex and not plex_names:
                return (
                    jsonify(
                        success=False,
                        message="Plex libraries are unavailable. Validate Plex and preview the import again.",
                    ),
                    400,
                )

            missing = []
            invalid_targets = []
            duplicates = []
            used_targets = set()
            mapped_libraries = {}

            for lib_name, lib_cfg in libraries_payload.items():
                name = str(lib_name)
                if name in plex_lookup:
                    target = plex_lookup[name]
                else:
                    mapped = library_mapping.get(name)
                    if mapped is None:
                        missing.append(name)
                        continue
                    mapped = str(mapped).strip()
                    if not mapped:
                        missing.append(name)
                        continue
                    if mapped == "__ignore__":
                        continue
                    if mapped not in plex_lookup:
                        invalid_targets.append(mapped)
                        continue
                    target = plex_lookup[mapped]

                if target in used_targets:
                    duplicates.append(target)
                    continue
                used_targets.add(target)
                mapped_libraries[target] = lib_cfg

            if missing:
                return (
                    jsonify(
                        success=False,
                        message=f"Library mapping required for: {', '.join(missing)}",
                    ),
                    400,
                )
            if invalid_targets:
                unique_targets = sorted(set(invalid_targets))
                return (
                    jsonify(
                        success=False,
                        message=f"Invalid Plex libraries selected: {', '.join(unique_targets)}",
                    ),
                    400,
                )
            if duplicates:
                unique_targets = sorted(set(duplicates))
                return (
                    jsonify(
                        success=False,
                        message=f"Multiple imports mapped to the same Plex library: {', '.join(unique_targets)}",
                    ),
                    400,
                )

            if mapped_libraries:
                config_data["libraries"] = mapped_libraries
            else:
                config_data.pop("libraries", None)

        _map_playlist_libraries(config_data, library_mapping, plex_names)

        payload, report = importer.prepare_import_payload(config_data, movie_names, show_names)
        if merge_mode and selected_sections:
            payload = {section: data_blob for section, data_blob in payload.items() if section in selected_sections}
        if not payload:
            return jsonify(success=False, message="No importable sections found."), 400

    if merge_mode and selected_sections:
        payload = {section: data_blob for section, data_blob in payload.items() if section in selected_sections}
    if not payload:
        return jsonify(success=False, message="No importable sections found."), 400

    if "libraries" in payload:
        normalized_libraries_section, normalize_errors = _normalize_imported_libraries_payload(payload.get("libraries"), config_name)
        if normalize_errors:
            return jsonify(success=False, message="Imported library files could not be organized.", errors=normalize_errors), 400
        payload["libraries"] = normalized_libraries_section

    imported_sections = []
    if merge_mode:
        base_sections = database.retrieve_config_sections(base_config)
        if not base_sections:
            return jsonify(success=False, message="Base config has no saved data to merge."), 400
        for entry in base_sections:
            section = entry.get("section")
            data_blob = entry.get("data")
            if not section or data_blob is None:
                continue
            database.save_section_data(
                name=config_name,
                section=section,
                validated=helpers.booler(entry.get("validated")),
                user_entered=helpers.booler(entry.get("user_entered")),
                data=data_blob,
            )
    for section, data_blob in payload.items():
        database.save_section_data(
            name=config_name,
            section=section,
            validated=False,
            user_entered=True,
            data=data_blob,
        )
        imported_sections.append(section)

    fonts_copied = []
    fonts_skipped = []
    fonts_skipped_existing = []
    fonts_skipped_failed = []
    if fonts_dir and fonts:
        config_fonts_dir = helpers.get_custom_fonts_dir(config_name)
        os.makedirs(config_fonts_dir, exist_ok=True)
        for font_name in fonts:
            src_path = os.path.join(fonts_dir, font_name)
            dest_path = os.path.join(str(config_fonts_dir), font_name)
            if os.path.exists(dest_path):
                fonts_skipped.append(font_name)
                fonts_skipped_existing.append(font_name)
                continue
            try:
                shutil.copy2(src_path, dest_path)
                fonts_copied.append(font_name)
            except OSError:
                fonts_skipped.append(font_name)
                fonts_skipped_failed.append(font_name)
        if fonts_copied:
            global _FONT_CACHE
            _FONT_CACHE = {}

    try:
        os.remove(cache_path)
    except OSError:
        pass
    if bundle_dir:
        try:
            shutil.rmtree(bundle_dir)
        except OSError:
            pass

    session.pop("import_preview_token", None)
    session.pop("import_preview_path", None)
    session.pop("import_preview_name", None)
    session.pop("import_preview_bundle_dir", None)
    session.pop("import_preview_plex_url", None)
    session.pop("import_preview_plex_token", None)
    session.pop("import_preview_tmdb_apikey", None)
    session["config_name"] = config_name
    importable_sections = sorted(str(section) for section in (cached.get("importable_sections") or payload.keys()))
    skipped_sections = sorted(section for section in importable_sections if section not in set(imported_sections))
    report_summary = report.summary() if "report" in locals() else (cached.get("report_summary") or {})
    mapping_values = [str(value).strip() for value in library_mapping.values()] if isinstance(library_mapping, dict) else []
    mapping_summary = {
        "mapped": sum(1 for value in mapping_values if value and value != "__ignore__"),
        "ignored": sum(1 for value in mapping_values if value == "__ignore__"),
    }

    return jsonify(
        success=True,
        config_name=config_name,
        imported_sections=imported_sections,
        skipped_sections=skipped_sections,
        report_summary=report_summary,
        mapping_summary=mapping_summary,
        fonts_copied=fonts_copied,
        fonts_skipped=fonts_skipped,
        fonts_skipped_existing=fonts_skipped_existing,
        fonts_skipped_failed=fonts_skipped_failed,
    )


@app.route("/step/<name>", methods=["GET", "POST"])
def step(name):
    page_info = {}
    header_style = "single line"
    save_error = None
    autosave_only = request.method == "POST" and request.headers.get("X-QS-Autosave-Only") == "1"
    if name == "900-final":
        return redirect(url_for("step", name="900-kometa"), code=302)
    persistence.ensure_session_config_name()
    requested_query_config = request.args.get("config_name")
    if request.method == "GET" and requested_query_config:
        normalized_query_config = helpers.normalize_config_name_for_storage(requested_query_config)
        available_query_configs = database.get_unique_config_names() or []
        if normalized_query_config in available_query_configs:
            session["config_name"] = normalized_query_config
    previous_config = session.get("config_name")

    posted_config = request.form.get("configSelector")
    posted_new_config_name = request.form.get("newConfigName")
    if posted_config == "add_config" and posted_new_config_name:
        posted_config = posted_new_config_name.strip()

    # Ensure saves happen against the currently selected config.
    if request.method == "POST" and posted_config:
        session["config_name"] = posted_config

    if request.method == "POST":
        path_errors = path_validation.validate_payload(request.form)
        url_errors = url_validation.validate_payload(request.form)
        validation_errors = path_errors + url_errors
        save_source, save_source_name = persistence.extract_names(request.referrer or name)
        normalized_library_payload = None
        if save_source_name == "libraries":
            clean_payload = persistence.clean_form_data(request.form)
            incoming_libraries = helpers.build_config_dict("libraries", clean_payload).get("libraries", {})
            selected_library_ids = _selected_library_ids_from_libraries_data(incoming_libraries)
            validation_errors += _validate_library_collection_files(incoming_libraries, selected_library_ids)
            validation_errors += _validate_library_metadata_files(incoming_libraries, selected_library_ids)
            validation_errors += _validate_library_overlay_files(incoming_libraries, selected_library_ids)
            validation_errors += _validate_library_auto_sort_hubs(incoming_libraries, selected_library_ids)
            for lib_id in selected_library_ids:
                override_result = _validate_library_service_overrides(lib_id, incoming_libraries)
                if not override_result.get("valid") and not override_result.get("skipped"):
                    validation_errors += list(override_result.get("errors") or [])
            if not validation_errors:
                normalized_library_payload, normalization_errors, _ = _normalize_library_file_entries_payload(
                    incoming_libraries,
                    session.get("config_name") or request.form.get("config_name") or request.form.get("configSelector"),
                    validate_local=False,
                )
                if normalization_errors:
                    validation_errors += normalization_errors
        elif save_source_name == "settings" and not _is_valid_auto_sort_hubs_value(request.form.get("auto_sort_hubs")):
            validation_errors.append("auto_sort_hubs must be one of: sort_title, sort_title.desc, alpha, alpha.desc, configured, configured.desc, random")
        if validation_errors:
            save_error = "Invalid values: " + " ".join(validation_errors)
        else:
            if save_source_name == "imagemaid":
                request_payload = request.form.to_dict(flat=True)
                request_payload["config_name"] = session.get("config_name") or request_payload.get("config_name") or request_payload.get("configSelector")
                config_name = _resolve_request_config_name(request_payload)
                existing_settings, _existing_section = _get_imagemaid_settings_section(config_name)
                was_validated = helpers.booler(existing_settings.get("validated", False))
                # Step navigation posts the page's native form field names (imagemaid_*),
                # unlike the JSON autosave/validate routes, so save those directly.
                form_payload = dict(request.form)
                form_payload["config_name"] = config_name
                changed = False
                if form_payload:
                    _saved_payload, changed = _save_imagemaid_settings_for_config(config_name, form_payload)
                _settings_after, section_data = _get_imagemaid_settings_section(config_name)
                if changed and was_validated:
                    _persist_imagemaid_validation(
                        config_name,
                        section_data,
                        False,
                        reason="config_changed",
                        details="Configuration changed. Validate ImageMaid again.",
                    )
            elif save_source_name == "libraries" and normalized_library_payload is not None:
                libraries_form = {key: (request.form.getlist(key) if len(request.form.getlist(key)) > 1 else request.form.get(key)) for key in request.form}
                libraries_form.update(normalized_library_payload)
                persistence.save_settings("025-libraries", libraries_form)
            else:
                persistence.save_settings(request.referrer, request.form)
            header_style = request.form.get("header_style", "single line")

        if autosave_only:
            if save_error:
                return jsonify(success=False, error=save_error), 400
            return jsonify(success=True, config_name=session.get("config_name"))

    # --- Detect config change ---
    selected_config = request.form.get("configSelector") or previous_config
    new_config_name = request.form.get("newConfigName")

    if selected_config == "add_config" and new_config_name:
        selected_config = new_config_name.strip()

    if not selected_config:
        selected_config = previous_config or namesgenerator.get_random_name()

    config_changed = selected_config != previous_config

    # Retrieve available fonts (ensuring "none" and "single line" are always included)
    available_fonts = helpers.get_pyfiglet_fonts()

    page_info["available_fonts"] = available_fonts

    # Retrieve stored settings from DB
    saved_settings = persistence.retrieve_settings(name)  # Retrieve from DB

    saved_header_style = None
    if "kometa" in saved_settings and "header_style" in saved_settings["kometa"]:
        saved_header_style = saved_settings["kometa"]["header_style"]
    elif "final" in saved_settings and "header_style" in saved_settings["final"]:
        saved_header_style = saved_settings["final"]["header_style"]
    if saved_header_style is not None:
        header_style = saved_header_style

    if header_style == "single_line":
        header_style = "single line"

    if header_style is None:
        header_style = "single line" if "single line" in available_fonts else "standard"

    # Ensure the selected font is valid
    if header_style not in available_fonts:
        header_style = "single line" if "single line" in available_fonts else "standard"

    page_info["header_style"] = header_style  # Now properly restored

    # Get selected config from form data (sent from the dropdown)
    selected_config = request.form.get("configSelector")  # Comes from the dropdown
    new_config_name = request.form.get("newConfigName")  # If "Add Config" is used

    # If "Add Config" is selected, use newConfigName instead
    if selected_config == "add_config" and new_config_name:
        selected_config = new_config_name.strip()

    # If no config is selected, fall back to the session or generate a new one
    if not selected_config:
        selected_config = session.get("config_name") or namesgenerator.get_random_name()

    # Update session with the chosen config
    session["config_name"] = selected_config
    page_info["config_name"] = selected_config
    page_info["running_port"] = running_port
    page_info["qs_debug"] = app.config["QS_DEBUG"]
    page_info["qs_theme"] = app.config.get("QS_THEME", "kometa")
    page_info["qs_optimize_defaults"] = app.config.get("QS_OPTIMIZE_DEFAULTS", True)
    page_info["qs_config_history"] = app.config.get("QS_CONFIG_HISTORY", 0)
    page_info["qs_kometa_log_keep"] = app.config.get("QS_KOMETA_LOG_KEEP", 0)
    page_info["qs_imagemaid_log_keep"] = app.config.get("QS_IMAGEMAID_LOG_KEEP", 0)
    page_info["qs_session_lifetime_days"] = app.config.get("QS_SESSION_LIFETIME_DAYS", 30)
    page_info["qs_flask_session_dir"] = app.config.get("QS_FLASK_SESSION_DIR", "")
    _, test_libs_path, test_libs_tmp, _, _ = _resolve_test_libraries_paths(helpers.get_app_root())
    page_info["qs_test_libs_path"] = test_libs_path
    page_info["qs_test_libs_tmp"] = test_libs_tmp
    page_info["header_style"] = header_style
    page_info["save_error"] = save_error
    page_info["template_name"] = name
    page_info.update(_build_kometa_install_context(selected_config))
    settings_payload = persistence.retrieve_settings("150-settings") or {}
    settings_section = settings_payload.get("settings", {}) if isinstance(settings_payload, dict) else {}
    custom_repo_setting = str(settings_section.get("custom_repo") or "").strip()
    custom_repo_base = validations._normalize_custom_repo_base(custom_repo_setting) or ""
    page_info["settings_custom_repo"] = custom_repo_setting
    page_info["settings_custom_repo_base"] = custom_repo_base
    if "shutdown_nonce" not in session:
        session["shutdown_nonce"] = secrets.token_urlsafe(16)
    if "restart_nonce" not in session:
        session["restart_nonce"] = secrets.token_urlsafe(16)
    page_info["shutdown_nonce"] = session["shutdown_nonce"]
    page_info["restart_nonce"] = session["restart_nonce"]
    if name == "905-analytics":
        return redirect(url_for("logscan_trends_page"))

    # Generate a placeholder name for "Add Config"
    page_info["new_config_name"] = namesgenerator.get_random_name()

    # Fetch available configurations from the database
    available_configs = database.get_unique_config_names() or []

    # Ensure the selected config is either in the dropdown or newly created
    if selected_config not in available_configs:
        page_info["new_config_name"] = selected_config  # Use the new config name

    file_list = helpers.get_menu_list()
    template_list = helpers.get_template_list()
    progress_excludes = {"sponsor", "analytics"}
    progress_keys = [key for key in template_list if template_list[key].get("raw_name") not in progress_excludes]
    total_steps = len(progress_keys)

    stem, num, b = helpers.get_bits(name)

    try:
        item = template_list[num]
    except (ValueError, IndexError, KeyError):
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Invalid step name '{name}' (stem={stem}, num={num}, b={b}).", level="ERROR")
        return abort(404)

    if num in progress_keys and total_steps:
        progress_index = progress_keys.index(num)
    else:
        progress_index = max(total_steps - 1, 0)
    page_info["progress"] = round(((progress_index + 1) / total_steps) * 100) if total_steps else 0
    page_info["title"] = item["name"]
    page_info["next_page"] = item["next"]
    page_info["prev_page"] = item["prev"]

    try:
        # Only split if the value is not None or empty
        if page_info["next_page"]:
            next_num = page_info["next_page"].split("-")[0]
            page_info["next_page_name"] = template_list.get(next_num, {}).get("name", "Next")
        else:
            page_info["next_page_name"] = "Next"

        if page_info["prev_page"]:
            prev_num = page_info["prev_page"].split("-")[0]
            page_info["prev_page_name"] = template_list.get(prev_num, {}).get("name", "Previous")
        else:
            page_info["prev_page_name"] = "Previous"

    except Exception as e:
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Failed to get page names: {e}", level="ERROR")
        page_info["next_page_name"] = "Next"
        page_info["prev_page_name"] = "Previous"

    # Retrieve data from storage
    data = persistence.retrieve_settings(name)
    debug_dir = os.path.join(helpers.CONFIG_DIR, "debug_logs")
    os.makedirs(debug_dir, exist_ok=True)

    debug_path = os.path.join(debug_dir, f"{name}_retrieved_data.json")

    if app.config["QS_DEBUG"]:
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        helpers.ts_log(f"Raw data written to {debug_path}", level="DEBUG")

    # Check for kometa_root
    if "kometa_root" not in session:
        session["kometa_root"] = app.config.get("KOMETA_ROOT", "")

    # Fetch Plex settings (reuse already loaded payload on Plex step)
    all_libraries = data if name == "010-plex" else persistence.retrieve_settings("010-plex")

    # Ensure 'plex' key exists before accessing sub-keys
    plex_data = all_libraries.get("plex", {})

    cached_user_list = plex_data.get("tmp_user_list", "")
    if isinstance(cached_user_list, str):
        has_cached_user_list = any(user.strip() for user in cached_user_list.split(","))
    elif isinstance(cached_user_list, list):
        has_cached_user_list = any(str(user).strip() for user in cached_user_list)
    else:
        has_cached_user_list = False

    plex_url = plex_data.get("url")
    plex_token = plex_data.get("token")
    dummy_plex = persistence.get_dummy_data("plex") or {}
    has_plex_credentials = bool(
        plex_url and plex_token and str(plex_url).strip() != str(dummy_plex.get("url", "")).strip() and str(plex_token).strip() != str(dummy_plex.get("token", "")).strip()
    )
    settings_needs_user_refresh = name == "150-settings" and not has_cached_user_list and has_plex_credentials

    # --- Refresh Plex data if needed ---
    should_refresh_plex = name in ["010-plex", "025-libraries", "900-kometa"] or config_changed or settings_needs_user_refresh
    if should_refresh_plex:
        if all_libraries.get("validated") or settings_needs_user_refresh:
            if settings_needs_user_refresh and app.config["QS_DEBUG"]:
                helpers.ts_log("Auto-refreshing Plex cache for settings page because tmp_user_list is empty.", level="DEBUG")
            refresh_plex_libraries()
            all_libraries = persistence.retrieve_settings("010-plex")
            plex_data = all_libraries.get("plex", {})

    telemetry_payload = {}
    try:
        telemetry_section = database.retrieve_section_data(name=selected_config, section="plex_telemetry")
        if telemetry_section and isinstance(telemetry_section[2], dict):
            telemetry_payload = telemetry_section[2].get("plex_telemetry", {}) or {}
    except Exception:
        telemetry_payload = {}
    telemetry = {"plex_telemetry": telemetry_payload}

    # If telemetry is fresher in plex_data, use that
    telemetry_data = plex_data.get("telemetry")
    if not isinstance(telemetry_data, dict) or "plex_pass" not in telemetry_data:
        telemetry_data = telemetry_payload

        # Fallback if DB is also missing it
        if not isinstance(telemetry_data, dict) or "plex_pass" not in telemetry_data:
            telemetry_data = {
                "plex_pass": None,
                "server_name": "Unavailable",
                "version": "Unavailable",
                "platform": "Unavailable",
                "update_channel": "Unavailable",
                "libraries": {},
            }
            helpers.ts_log(f"Telemetry fallback triggered due to missing or invalid telemetry for config: {selected_config}", level="WARNING")
    else:
        if app.config["QS_DEBUG"]:
            helpers.ts_log("Using telemetry from fresh plex_data", level="DEBUG")

    page_info["telemetry"] = telemetry_data

    # Extract the movie and show libraries
    movie_libraries_raw = plex_data.get("tmp_movie_libraries", "")
    show_libraries_raw = plex_data.get("tmp_show_libraries", "")

    # Debugging extracted values
    if app.config["QS_DEBUG"]:
        helpers.ts_log("Extracted movie libraries:", movie_libraries_raw, level="DEBUG")
        helpers.ts_log("Extracted show libraries:", show_libraries_raw, level="DEBUG")

    # Ensure it's a string before splitting
    if not isinstance(movie_libraries_raw, str):
        if app.config["QS_DEBUG"]:
            helpers.ts_log("tmp_movie_libraries is not a string!", level="ERROR")

        movie_libraries_raw = ""

    if not isinstance(show_libraries_raw, str):
        if app.config["QS_DEBUG"]:
            helpers.ts_log("tmp_show_libraries is not a string!", level="ERROR")

        show_libraries_raw = ""

    existing_ids = set()  # Track used IDs to prevent duplicates

    movie_libraries = [
        {
            "id": f"mov-library_{helpers.normalize_id(lib.strip(), existing_ids)}",
            "name": lib.strip(),
            "type": "movie",
        }
        for lib in movie_libraries_raw.split(",")
        if lib.strip()
    ]

    show_libraries = [
        {
            "id": f"sho-library_{helpers.normalize_id(lib.strip(), existing_ids)}",
            "name": lib.strip(),
            "type": "show",
        }
        for lib in show_libraries_raw.split(",")
        if lib.strip()
    ]

    # Ensure `libraries` dictionary exists
    if "libraries" not in data:
        data["libraries"] = {}

    # Ensure `mov-template_variables` and `sho-template_variables` exist inside `libraries`
    if "mov-template_variables" not in data["libraries"]:
        data["libraries"]["mov-template_variables"] = {}

    if "sho-template_variables" not in data["libraries"]:
        data["libraries"]["sho-template_variables"] = {}

    if app.config["QS_DEBUG"]:
        helpers.ts_log("************************************************************************", level="DEBUG")
        helpers.ts_log(f"Data retrieved for {name}", level="DEBUG")

    (
        page_info["plex_valid"],
        page_info["tmdb_valid"],
        page_info["libs_valid"],
        page_info["sett_valid"],
    ) = persistence.check_minimum_settings()

    (
        page_info["notifiarr_available"],
        page_info["gotify_available"],
        page_info["ntfy_available"],
        page_info["apprise_available"],
    ) = persistence.notification_systems_available()

    # Ensure template variables exist
    if "mov-template_variables" not in data:
        data["mov-template_variables"] = {}
    if "sho-template_variables" not in data:
        data["sho-template_variables"] = {}

    # Ensure these are lists
    plex_data["tmp_movie_libraries"] = plex_data.get("tmp_movie_libraries", "").split(",") if isinstance(plex_data.get("tmp_movie_libraries"), str) else []
    plex_data["tmp_show_libraries"] = plex_data.get("tmp_show_libraries", "").split(",") if isinstance(plex_data.get("tmp_show_libraries"), str) else []
    plex_data["tmp_music_libraries"] = plex_data.get("tmp_music_libraries", "").split(",") if isinstance(plex_data.get("tmp_music_libraries"), str) else []
    plex_data["tmp_user_list"] = plex_data.get("tmp_user_list", "").split(",") if isinstance(plex_data.get("tmp_user_list"), str) else []

    # Ensure correct rendering for the Kometa page
    config_name = session.get("config_name") or page_info.get("config_name", "default")
    if app.config["QS_DEBUG"]:
        helpers.ts_log(f"Start render_template for {name}", level="DEBUG")

    start_time = time.perf_counter()

    needs_library_payload = name == "025-libraries"
    attribute_config = {}
    collection_config = []
    overlay_config = []
    service_validations = {
        "plex": False,
        "tmdb": False,
        "omdb": False,
        "mdblist": False,
        "anidb": False,
        "trakt": False,
        "mal": False,
    }
    overlay_fonts = []
    image_data = {}
    service_validation_sources = [
        ("010-plex", "plex"),
        ("020-tmdb", "tmdb"),
        ("050-omdb", "omdb"),
        ("060-mdblist", "mdblist"),
        ("100-anidb", "anidb"),
        ("130-trakt", "trakt"),
        ("140-mal", "mal"),
    ]
    for section, key in service_validation_sources:
        settings = persistence.retrieve_settings(section)
        service_validations[key] = helpers.booler(settings.get("validated", False))

    if needs_library_payload:
        helpers.ts_log("Loading attribute_config...", level="TIMING")
        attribute_config = helpers.load_quickstart_config("quickstart_attributes.json")
        helpers.ts_log("Loading collection_config...", level="TIMING")
        collection_config = helpers.load_quickstart_config("quickstart_collections.json")
        helpers.ts_log("Loading overlay_config...", level="TIMING")
        overlay_config = helpers.load_quickstart_overlay_config()
        helpers.ts_log("Loading preview image data...", level="TIMING")
        image_data = _build_preview_image_data()
        overlay_fonts = list_overlay_fonts()

    workspace_status = _build_workspace_status_context(config_name, file_list, available_configs=available_configs)
    jump_to_validations = workspace_status.get("jump_to_validations", {})
    step_statuses = workspace_status.get("step_statuses", {})
    section_statuses = workspace_status.get("section_statuses", {})

    if name == "915-imagemaid":
        imagemaid_section = data.get("imagemaid", {}) if isinstance(data.get("imagemaid"), dict) else {}
        imagemaid_state = _probe_imagemaid_root_state(helpers.get_imagemaid_root_path())
        imagemaid_section_row = database.retrieve_section_data(config_name, "imagemaid")
        imagemaid_section_validated = helpers.booler(imagemaid_section_row[0]) if imagemaid_section_row else False
        page_info["imagemaid_root"] = str(helpers.get_imagemaid_root_path())
        page_info["imagemaid_branch_override"] = helpers.normalize_imagemaid_branch_override(imagemaid_section.get("branch_override"))
        page_info["imagemaid_mode"] = str(imagemaid_section.get("mode") or "report").strip().lower() or "report"
        page_info["imagemaid_validated"] = imagemaid_section_validated
        page_info["imagemaid_supports_no_verify_ssl"] = bool(imagemaid_state.get("supports_no_verify_ssl"))
        page_info["imagemaid_supports_overlays_only"] = bool(imagemaid_state.get("supports_overlays_only"))

    if name == "900-kometa":
        validation_meta = []
        validation_bulk_rollup = None
        validation_bulk_rollup_at = None
        try:
            stored_validation = database.retrieve_section_data(config_name, "validation_summary")
            stored_payload = stored_validation[2] if stored_validation else None
            if isinstance(stored_payload, dict):
                validation_bulk_rollup = stored_payload.get("summary_text")
                validation_bulk_rollup_at = stored_payload.get("updated_at")
        except Exception:
            validation_bulk_rollup = None
            validation_bulk_rollup_at = None

        final_gate = _build_final_gate(workspace_status, file_list, validation_bulk_rollup_at)
        template_keys_for_rollup = [file.rsplit(".", 1)[0] for file, _ in file_list]
        validation_rollup = None
        validation_rollup_summary = {}
        validation_rollup_state = "unknown"
        validation_rollup_at = None
        if final_gate.get("stage") != "todo":
            for file, display_name in file_list:
                template_key = file.rsplit(".", 1)[0]
                settings = persistence.retrieve_settings(template_key)
                has_validation = template_key in QS_VALIDATION_STEP_KEYS
                validation_status = None
                validation_reason = None
                validation_details = None
                validation_updated_at = None
                if has_validation:
                    section_name = template_key.split("-", 1)[1]
                    stored_section = database.retrieve_section_data(config_name, section_name)
                    stored_payload = stored_section[2] if stored_section else None
                    if isinstance(stored_payload, dict):
                        validation_status = stored_payload.get("validation_status")
                        validation_reason = stored_payload.get("validation_reason")
                        validation_details = stored_payload.get("validation_details")
                        validation_updated_at = stored_payload.get("validation_updated_at")
                if not validation_status and has_validation:
                    if helpers.booler(settings.get("validated", False)):
                        validation_status = "validated"
                    elif settings.get("validated_at"):
                        validation_status = "failed"
                if not validation_updated_at and has_validation:
                    validation_updated_at = settings.get("validated_at")

                validation_result = ""
                if validation_status:
                    label = validation_status.capitalize()
                    if validation_reason:
                        pretty = VALIDATION_REASON_LABELS.get(validation_reason, validation_reason.replace("_", " "))
                        detail_text = ""
                        if isinstance(validation_details, (list, tuple)):
                            detail_text = ", ".join(str(item) for item in validation_details if str(item))
                        elif validation_details is not None:
                            detail_text = str(validation_details)
                        if detail_text:
                            validation_result = f"{label}: {pretty}: {detail_text}"
                        else:
                            validation_result = f"{label}: {pretty}"
                    else:
                        validation_result = label

                validation_meta.append(
                    {
                        "key": template_key,
                        "label": display_name,
                        "page": template_key,
                        "has_validation": has_validation,
                        "validated": helpers.booler(settings.get("validated", False)) if has_validation else None,
                        "validated_at": settings.get("validated_at", "") if has_validation else "",
                        "validation_updated_at": validation_updated_at if has_validation else "",
                        "validation_result": validation_result,
                    }
                )
            live_rollup = _build_live_validation_rollup(step_statuses, template_keys_for_rollup)
            validation_rollup = live_rollup.get("summary_text")
            validation_rollup_summary = live_rollup.get("counts", {})
            validation_rollup_state = live_rollup.get("state", "unknown")
            validation_rollup_at = _latest_iso_timestamp([entry.get("validation_updated_at") for entry in validation_meta])
        validated = False
        validation_error = None
        config_data = {}
        yaml_content = ""
        validation_errors = []
        validation_summary = []
        saved_filename = ""

        if final_gate.get("can_build_config"):
            validated, validation_error, config_data, yaml_content, validation_errors = output.build_config(header_style, config_name=config_name)
            if isinstance(config_data, dict):
                config_data, _normalized_changed, normalization_errors = _normalize_generated_config_library_files(config_data, config_name)
                if normalization_errors:
                    validation_errors = list(validation_errors or []) + normalization_errors
                    validated = False
                if not isinstance(yaml_content, str) or not yaml_content.strip():
                    yaml_content = _dump_yaml_text(config_data)
            validation_summary = build_validation_summary(validation_errors)
            used_fonts = helpers.collect_font_references(config_data)
            saved_filename = helpers.save_to_named_config(yaml_content, config_name, used_fonts)
            final_gate["config_valid"] = bool(validated)
            final_gate["stage"] = "kometa" if validated else "config"
        elif final_gate.get("stage") == "freshness":
            validation_rollup_state = "warn"
            if not validation_bulk_rollup:
                validation_bulk_rollup = f"Validation is stale. Bulk validation has not run in the last {QS_FINAL_VALIDATION_TTL_HOURS} hours."
        page_info["saved_filename"] = saved_filename
        page_info["yaml_valid"] = validated
        page_info["quickstart_root"] = helpers.get_app_root()
        page_info["kometa_sync_target_display"] = str((helpers.get_kometa_config_dir() / saved_filename).resolve()) if saved_filename else ""
        kometa_log_dir = helpers.get_kometa_log_dir()
        page_info["kometa_log_dir_exists"] = bool(kometa_log_dir.exists())
        page_info["kometa_log_dir_resolved_display"] = str(kometa_log_dir.resolve()) if kometa_log_dir else ""
        kometa_is_running = helpers.is_kometa_running()
        incomplete_resume_hint = None if kometa_is_running else _build_latest_incomplete_resume_hint()
        session["yaml_content"] = yaml_content
        library_settings = persistence.retrieve_settings("025-libraries").get("libraries", {})
        movie_libraries = []
        show_libraries = []
        library_dropdown = []
        existing_ids = set()

        for key, value in library_settings.items():
            if key.startswith("mov-library_") and key.endswith("-library"):
                movie_libraries.append({"id": key.split("-library")[0], "name": value, "type": "movie"})
            elif key.startswith("sho-library_") and key.endswith("-library"):
                show_libraries.append({"id": key.split("-library")[0], "name": value, "type": "show"})

        if saved_filename:
            try:
                config_path = Path(helpers.CONFIG_DIR) / saved_filename
                config_for_dropdown = _load_progress_config(config_path)
                library_dropdown = _get_progress_library_list(config_data=config_for_dropdown)
            except Exception:
                library_dropdown = []
        if not library_dropdown:
            library_dropdown = movie_libraries + show_libraries

        html = render_template(
            "900-kometa.html",
            page_info=page_info,
            data=data,
            yaml_content=yaml_content,
            validation_error=validation_error,
            validation_summary=validation_summary,
            validation_rollup=validation_rollup,
            validation_rollup_at=validation_rollup_at,
            validation_rollup_summary=validation_rollup_summary,
            validation_rollup_state=validation_rollup_state,
            validation_bulk_rollup=validation_bulk_rollup,
            validation_bulk_rollup_at=validation_bulk_rollup_at,
            template_list=file_list,
            available_configs=available_configs,
            movie_libraries=movie_libraries,
            show_libraries=show_libraries,
            library_dropdown=library_dropdown,
            config_dir=str(Path(helpers.CONFIG_DIR).resolve()),
            overlay_fonts=overlay_fonts,
            service_validations=service_validations,
            validation_meta=validation_meta,
            jump_to_validations=jump_to_validations,
            step_statuses=step_statuses,
            section_statuses=section_statuses,
            required_keys=workspace_status.get("required_keys", []),
            optional_keys=workspace_status.get("optional_keys", []),
            review_keys=workspace_status.get("review_keys", []),
            tautulli_requirement_reasons=workspace_status.get("tautulli_requirement_reasons", []),
            omdb_requirement_reasons=workspace_status.get("omdb_requirement_reasons", []),
            mdblist_requirement_reasons=workspace_status.get("mdblist_requirement_reasons", []),
            anidb_requirement_reasons=workspace_status.get("anidb_requirement_reasons", []),
            radarr_requirement_reasons=workspace_status.get("radarr_requirement_reasons", []),
            sonarr_requirement_reasons=workspace_status.get("sonarr_requirement_reasons", []),
            trakt_requirement_reasons=workspace_status.get("trakt_requirement_reasons", []),
            mal_requirement_reasons=workspace_status.get("mal_requirement_reasons", []),
            workspace_readiness=workspace_status.get("readiness", {}),
            final_gate=final_gate,
            incomplete_resume_hint=incomplete_resume_hint,
        )

        end_time = time.perf_counter()
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Rendered 900-kometa.html in {end_time - start_time:.2f} seconds", level="PROFILE")
        return html

    else:
        helpers.ts_log("Loading quickstart_root...", level="TIMING")
        page_info["quickstart_root"] = helpers.get_app_root()
        helpers.ts_log("Start render_template...", level="TIMING")

    configured_ids = _configured_library_ids(data.get("libraries", {}))
    configured_counts = {
        "movie": sum(1 for lib in movie_libraries if lib["id"] in configured_ids),
        "show": sum(1 for lib in show_libraries if lib["id"] in configured_ids),
    }
    html = render_template(
        name + ".html",
        page_info=page_info,
        data=data,
        telemetry=telemetry,
        plex_data=plex_data,
        movie_libraries=movie_libraries,
        show_libraries=show_libraries,
        attribute_config=attribute_config,
        collection_config=collection_config,
        overlay_config=overlay_config,
        template_list=file_list,
        available_configs=available_configs,
        overlay_fonts=overlay_fonts,
        service_validations=service_validations,
        jump_to_validations=jump_to_validations,
        step_statuses=step_statuses,
        section_statuses=section_statuses,
        required_keys=workspace_status.get("required_keys", []),
        optional_keys=workspace_status.get("optional_keys", []),
        review_keys=workspace_status.get("review_keys", []),
        tautulli_requirement_reasons=workspace_status.get("tautulli_requirement_reasons", []),
        omdb_requirement_reasons=workspace_status.get("omdb_requirement_reasons", []),
        mdblist_requirement_reasons=workspace_status.get("mdblist_requirement_reasons", []),
        anidb_requirement_reasons=workspace_status.get("anidb_requirement_reasons", []),
        radarr_requirement_reasons=workspace_status.get("radarr_requirement_reasons", []),
        sonarr_requirement_reasons=workspace_status.get("sonarr_requirement_reasons", []),
        trakt_requirement_reasons=workspace_status.get("trakt_requirement_reasons", []),
        mal_requirement_reasons=workspace_status.get("mal_requirement_reasons", []),
        workspace_readiness=workspace_status.get("readiness", {}),
        image_data=image_data,
        config_dir=str(Path(helpers.CONFIG_DIR).resolve()),
        configured_ids=configured_ids,
        configured_counts=configured_counts,
    )

    end_time = time.perf_counter()
    if app.config["QS_DEBUG"]:
        helpers.ts_log(f"Rendered {name}.html in {end_time - start_time:.2f} seconds", level="PROFILE")
    return html


@app.route("/workspace_status", methods=["GET"])
def workspace_status():
    """Return live workspace step/group/readiness state for sidebar updates."""
    persistence.ensure_session_config_name()
    config_name = request.args.get("config_name") or session.get("config_name")
    available_configs = database.get_unique_config_names() or []
    menu_templates = helpers.get_menu_list()
    status = _build_workspace_status_context(config_name, menu_templates, available_configs=available_configs)
    return jsonify(
        success=True,
        config_name=config_name,
        step_statuses=status.get("step_statuses", {}),
        section_statuses=status.get("section_statuses", {}),
        required_keys=status.get("required_keys", []),
        optional_keys=status.get("optional_keys", []),
        review_keys=status.get("review_keys", []),
        tautulli_requirement_reasons=status.get("tautulli_requirement_reasons", []),
        omdb_requirement_reasons=status.get("omdb_requirement_reasons", []),
        mdblist_requirement_reasons=status.get("mdblist_requirement_reasons", []),
        anidb_requirement_reasons=status.get("anidb_requirement_reasons", []),
        radarr_requirement_reasons=status.get("radarr_requirement_reasons", []),
        sonarr_requirement_reasons=status.get("sonarr_requirement_reasons", []),
        trakt_requirement_reasons=status.get("trakt_requirement_reasons", []),
        mal_requirement_reasons=status.get("mal_requirement_reasons", []),
        readiness=status.get("readiness", {}),
    )


@app.route("/workspace_app_readiness", methods=["GET"])
def workspace_app_readiness():
    persistence.ensure_session_config_name()
    config_name = request.args.get("config_name") or session.get("config_name")
    payload = _build_workspace_app_readiness(config_name)
    return jsonify(success=True, config_name=config_name, apps=payload)


@app.route("/get_top_imdb_items/<library_name>")
def get_top_imdb_items_route(library_name):
    media_type = request.args.get("type", "movie")
    placeholder_id = request.args.get("placeholder_id")
    settings = persistence.retrieve_settings("010-plex")
    plex_settings = settings.get("plex", {})

    tmp_key = f"tmp_{media_type}_libraries"
    raw_libraries = plex_settings.get(tmp_key, "")
    library_names = [lib.strip() for lib in raw_libraries.split(",") if lib.strip()]

    helpers.ts_log(f"Searching for library name: {library_name}", level="DEBUG")
    helpers.ts_log(f"Available libraries of type '{media_type}': {library_names}", level="DEBUG")

    if library_name not in library_names:
        return jsonify(
            {
                "status": "error",
                "message": f"Library '{library_name}' not found in Plex settings.",
            }
        )

    # Call with placeholder_id
    items, saved_item = helpers.get_top_imdb_items(library_name, media_type, placeholder_id)

    return jsonify({"status": "success", "items": items, "saved_item": saved_item})


def _configured_library_ids(library_data):
    """Return set of library IDs that have an active '-library' value saved."""
    if not isinstance(library_data, dict):
        return set()
    return {key.rsplit("-library", 1)[0] for key, value in library_data.items() if key.endswith("-library") and value not in [None, "", False]}


def _build_library_lists():
    """Shared helper to return movie/show library descriptors and telemetry data."""
    all_libraries = persistence.retrieve_settings("010-plex")
    plex_data = all_libraries.get("plex", {})
    telemetry = persistence.retrieve_settings("plex_telemetry")

    telemetry_data = plex_data.get("telemetry")
    if not isinstance(telemetry_data, dict) or "plex_pass" not in telemetry_data:
        telemetry_data = telemetry.get("plex_telemetry", {})

    movie_raw = plex_data.get("tmp_movie_libraries", "") if isinstance(plex_data.get("tmp_movie_libraries"), str) else ""
    show_raw = plex_data.get("tmp_show_libraries", "") if isinstance(plex_data.get("tmp_show_libraries"), str) else ""

    existing_ids = set()

    movie_libraries = [
        {
            "id": f"mov-library_{helpers.normalize_id(lib.strip(), existing_ids)}",
            "name": lib.strip(),
            "type": "movie",
        }
        for lib in movie_raw.split(",")
        if lib.strip()
    ]

    show_libraries = [
        {
            "id": f"sho-library_{helpers.normalize_id(lib.strip(), existing_ids)}",
            "name": lib.strip(),
            "type": "show",
        }
        for lib in show_raw.split(",")
        if lib.strip()
    ]

    return movie_libraries, show_libraries, telemetry_data


def _legacy_playlist_library_names():
    settings = persistence.retrieve_settings("027-playlist_files") or {}
    playlist_payload = settings.get("playlist_files", {}) if isinstance(settings, dict) else {}
    if isinstance(playlist_payload, dict) and isinstance(playlist_payload.get("playlist_files"), dict):
        playlist_payload = playlist_payload.get("playlist_files", {})
    raw_libraries = playlist_payload.get("libraries", "") if isinstance(playlist_payload, dict) else ""
    if isinstance(raw_libraries, list):
        return {str(item).strip() for item in raw_libraries if str(item).strip()}
    return {item.strip() for item in str(raw_libraries or "").split(",") if item.strip()}


def _migrate_legacy_playlist_libraries_to_library_toggles(movie_libraries=None, show_libraries=None):
    legacy_names = _legacy_playlist_library_names()
    if not legacy_names:
        return set()

    settings = persistence.retrieve_settings("025-libraries") or {}
    libraries_data = settings.get("libraries", {}) if isinstance(settings, dict) else {}
    if not isinstance(libraries_data, dict):
        return legacy_names

    if any(isinstance(key, str) and key.endswith("-playlist") for key in libraries_data):
        return set()

    if movie_libraries is None or show_libraries is None:
        movie_libraries, show_libraries, _telemetry = _build_library_lists()

    migrated = {}
    for library in list(movie_libraries or []) + list(show_libraries or []):
        library_id = library.get("id")
        library_name = library.get("name")
        if not library_id or not library_name:
            continue
        if library_name not in legacy_names:
            continue
        if not _is_truthy_setting_value(libraries_data.get(f"{library_id}-library")):
            continue
        migrated[f"{library_id}-playlist"] = "true"

    if not migrated:
        return legacy_names

    updated_libraries = libraries_data.copy()
    updated_libraries.update(migrated)
    settings["libraries"] = updated_libraries
    config_name = session.get("config_name")
    if not config_name:
        return legacy_names
    try:
        database.save_section_data(
            name=config_name,
            section="libraries",
            validated=helpers.booler(settings.get("validated", False)),
            user_entered=True,
            data=settings,
        )
    except Exception as e:
        helpers.ts_log(f"Failed to migrate legacy playlist libraries: {e}", level="ERROR")
        return legacy_names

    return legacy_names


@app.route("/library_fragment/<library_id>")
def library_fragment(library_id):
    """Return a single library form fragment so we can lazy-load library settings on the page."""
    movie_libraries, show_libraries, telemetry_data = _build_library_lists()
    all_libraries = {lib["id"]: lib for lib in movie_libraries + show_libraries}
    library = all_libraries.get(library_id)

    if not library:
        return jsonify({"error": "Library not found"}), 404

    attribute_config = helpers.load_quickstart_config("quickstart_attributes.json")
    collection_config = helpers.load_quickstart_config("quickstart_collections.json")
    overlay_config = helpers.load_quickstart_overlay_config()

    legacy_playlist_libraries = _migrate_legacy_playlist_libraries_to_library_toggles(movie_libraries, show_libraries)
    data = persistence.retrieve_settings("025-libraries")
    configured_ids = _configured_library_ids(data.get("libraries", {}))

    image_data = _build_preview_image_data()

    page_info = {"telemetry": telemetry_data}

    html = render_template(
        "partials/_library_card.html",
        library=library,
        data=data,
        page_info=page_info,
        attribute_config=attribute_config,
        collection_config=collection_config,
        overlay_config=overlay_config,
        image_data=image_data,
        movie_images=image_data["movie"],
        configured_ids=configured_ids,
        legacy_playlist_libraries=legacy_playlist_libraries,
    )

    return html


@app.route("/autosave_library/<library_id>", methods=["POST"])
def autosave_library(library_id):
    """Merge-save a single library when switching cards without requiring full navigation submit."""
    try:
        incoming = request.get_json(silent=True) or request.form
        config_name = _resolve_request_config_name(incoming if isinstance(incoming, dict) else {})
        errors = path_validation.validate_payload(incoming)
        if errors:
            return jsonify({"success": False, "error": "Invalid path values.", "errors": errors}), 400
        clean_payload = persistence.clean_form_data(MultiDict(incoming))
        incoming_libraries = helpers.build_config_dict("libraries", clean_payload).get("libraries", {})
        selected_library_ids = _selected_library_ids_from_libraries_data(incoming_libraries)
        collection_errors = _validate_library_collection_files(incoming_libraries, selected_library_ids)
        metadata_errors = _validate_library_metadata_files(incoming_libraries, selected_library_ids)
        overlay_errors = _validate_library_overlay_files(incoming_libraries, selected_library_ids)
        auto_sort_hubs_errors = _validate_library_auto_sort_hubs(incoming_libraries, selected_library_ids)
        if collection_errors:
            return jsonify({"success": False, "error": "Invalid collection files.", "errors": collection_errors}), 400
        if metadata_errors:
            return jsonify({"success": False, "error": "Invalid metadata files.", "errors": metadata_errors}), 400
        if overlay_errors:
            return jsonify({"success": False, "error": "Invalid overlay files.", "errors": overlay_errors}), 400
        if auto_sort_hubs_errors:
            return jsonify({"success": False, "error": "Invalid library settings.", "errors": auto_sort_hubs_errors}), 400
        normalized_libraries, normalization_errors, changed = _normalize_library_file_entries_payload(
            incoming_libraries,
            config_name,
            validate_local=False,
        )
        if normalization_errors:
            return jsonify({"success": False, "error": "Unable to organize library files.", "errors": normalization_errors}), 400
        save_payload = dict(incoming) if isinstance(incoming, dict) else {}
        save_payload.update(normalized_libraries)
        save_payload["config_name"] = config_name
        persistence.save_settings("025-libraries", save_payload)
        return jsonify({"success": True, "normalized": bool(changed), "libraries": normalized_libraries})
    except Exception as e:
        helpers.ts_log(f"Autosave failed for library {library_id}: {e}", level="ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


def _build_merged_libraries_hint_payload(payload):
    source_library_id = str(payload.get("source_library_id") or "").strip()
    source_payload = payload.get("source_payload") if isinstance(payload.get("source_payload"), dict) else {}

    settings = persistence.retrieve_settings("025-libraries")
    libraries_data = settings.get("libraries", {}) if isinstance(settings, dict) else {}
    merged = libraries_data.copy() if isinstance(libraries_data, dict) else {}

    if not source_payload:
        return merged

    clean_payload = persistence.clean_form_data(MultiDict(source_payload))
    incoming_dict = helpers.build_config_dict("libraries", clean_payload).get("libraries", {})
    incoming_dict = incoming_dict if isinstance(incoming_dict, dict) else {}

    prefixes = set()
    if source_library_id:
        source_prefix = source_library_id.split("-card-container")[0] if source_library_id.endswith("-card-container") else source_library_id
        if source_prefix:
            prefixes.add(source_prefix)

    for key in incoming_dict:
        prefix = _library_prefix_from_key(key)
        if prefix:
            prefixes.add(prefix)

    for prefix in prefixes:
        for existing_key in list(merged.keys()):
            if existing_key == f"{prefix}-library" or existing_key.startswith(prefix + "-"):
                merged.pop(existing_key, None)

    for key, value in incoming_dict.items():
        if (key.endswith("-library") or key.endswith("-playlist")) and not _is_truthy_setting_value(value):
            continue
        merged[key] = value

    return merged


def _libraries_dependency_hint_response(payload, resolver):
    merged = _build_merged_libraries_hint_payload(payload)
    reasons = resolver(merged)
    return jsonify({"success": True, "required": bool(reasons), "reasons": reasons})


@app.route("/libraries_tautulli_dependency_hint", methods=["POST"])
def libraries_tautulli_dependency_hint():
    """Preview Tautulli-required dependency reasons using current in-page library edits."""
    try:
        payload = request.get_json(silent=True) or {}
        return _libraries_dependency_hint_response(payload, _libraries_data_tautulli_dependency_reasons)
    except Exception as e:
        helpers.ts_log(f"Failed to build Tautulli dependency hint: {e}", level="ERROR")
        return jsonify({"success": False, "required": False, "reasons": [], "error": str(e)}), 500


@app.route("/libraries_omdb_dependency_hint", methods=["POST"])
def libraries_omdb_dependency_hint():
    """Preview OMDb-required dependency reasons using current in-page library edits."""
    try:
        payload = request.get_json(silent=True) or {}
        return _libraries_dependency_hint_response(payload, _libraries_data_omdb_dependency_reasons)
    except Exception as e:
        helpers.ts_log(f"Failed to build OMDb dependency hint: {e}", level="ERROR")
        return jsonify({"success": False, "required": False, "reasons": [], "error": str(e)}), 500


@app.route("/libraries_mdblist_dependency_hint", methods=["POST"])
def libraries_mdblist_dependency_hint():
    """Preview MDBList-required dependency reasons using current in-page library edits."""
    try:
        payload = request.get_json(silent=True) or {}
        return _libraries_dependency_hint_response(payload, _libraries_data_mdblist_dependency_reasons)
    except Exception as e:
        helpers.ts_log(f"Failed to build MDBList dependency hint: {e}", level="ERROR")
        return jsonify({"success": False, "required": False, "reasons": [], "error": str(e)}), 500


@app.route("/libraries_anidb_dependency_hint", methods=["POST"])
def libraries_anidb_dependency_hint():
    """Preview AniDB-required dependency reasons using current in-page library edits."""
    try:
        payload = request.get_json(silent=True) or {}
        return _libraries_dependency_hint_response(payload, _libraries_data_anidb_dependency_reasons)
    except Exception as e:
        helpers.ts_log(f"Failed to build AniDB dependency hint: {e}", level="ERROR")
        return jsonify({"success": False, "required": False, "reasons": [], "error": str(e)}), 500


@app.route("/libraries_radarr_dependency_hint", methods=["POST"])
def libraries_radarr_dependency_hint():
    """Preview Radarr-required dependency reasons using current in-page library edits."""
    try:
        payload = request.get_json(silent=True) or {}
        return _libraries_dependency_hint_response(payload, _libraries_data_radarr_dependency_reasons)
    except Exception as e:
        helpers.ts_log(f"Failed to build Radarr dependency hint: {e}", level="ERROR")
        return jsonify({"success": False, "required": False, "reasons": [], "error": str(e)}), 500


@app.route("/libraries_sonarr_dependency_hint", methods=["POST"])
def libraries_sonarr_dependency_hint():
    """Preview Sonarr-required dependency reasons using current in-page library edits."""
    try:
        payload = request.get_json(silent=True) or {}
        return _libraries_dependency_hint_response(payload, _libraries_data_sonarr_dependency_reasons)
    except Exception as e:
        helpers.ts_log(f"Failed to build Sonarr dependency hint: {e}", level="ERROR")
        return jsonify({"success": False, "required": False, "reasons": [], "error": str(e)}), 500


@app.route("/libraries_trakt_dependency_hint", methods=["POST"])
def libraries_trakt_dependency_hint():
    """Preview Trakt-required dependency reasons using current in-page library edits."""
    try:
        payload = request.get_json(silent=True) or {}
        return _libraries_dependency_hint_response(payload, _libraries_data_trakt_dependency_reasons)
    except Exception as e:
        helpers.ts_log(f"Failed to build Trakt dependency hint: {e}", level="ERROR")
        return jsonify({"success": False, "required": False, "reasons": [], "error": str(e)}), 500


@app.route("/libraries_mal_dependency_hint", methods=["POST"])
def libraries_mal_dependency_hint():
    """Preview MAL-required dependency reasons using current in-page library edits."""
    try:
        payload = request.get_json(silent=True) or {}
        return _libraries_dependency_hint_response(payload, _libraries_data_mal_dependency_reasons)
    except Exception as e:
        helpers.ts_log(f"Failed to build MAL dependency hint: {e}", level="ERROR")
        return jsonify({"success": False, "required": False, "reasons": [], "error": str(e)}), 500


@app.route("/copy_library_settings", methods=["POST"])
def copy_library_settings():
    """Copy saved settings from one library to multiple targets of the same type."""
    try:
        payload = request.get_json(force=True, silent=True) or {}
        source_id = payload.get("source_library_id")
        target_ids = payload.get("target_library_ids") or []
        source_payload = payload.get("source_payload") or {}

        if not source_id or not target_ids:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Missing source or targets (source={source_id}, targets={target_ids})",
                    }
                ),
                400,
            )

        source_prefix = source_id.split("-card-container")[0] if source_id.endswith("-card-container") else source_id
        source_type = source_prefix[:3]  # mov or sho

        if any(not str(t).startswith(source_type) for t in target_ids):
            helpers.ts_log(
                f"Copy aborted: targets must match source type '{source_type}', got targets={target_ids}",
                level="ERROR",
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Targets must match source type '{source_type}'",
                        "targets": target_ids,
                    }
                ),
                400,
            )

        settings = persistence.retrieve_settings("025-libraries")
        libraries_data = settings.get("libraries", {}) if isinstance(settings, dict) else {}

        # If the client sent a fresh payload for the source card, merge it in before copying
        if isinstance(source_payload, dict) and source_payload:
            payload_errors = path_validation.validate_payload(source_payload)
            if payload_errors:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Invalid path values in source payload: " + " ".join(payload_errors),
                            "errors": payload_errors,
                        }
                    ),
                    400,
                )
            try:
                clean_payload = persistence.clean_form_data(MultiDict(source_payload))
                incoming_dict = helpers.build_config_dict("libraries", clean_payload).get("libraries", {})
                normalized_incoming, normalization_errors, _ = _normalize_library_file_entries_payload(
                    incoming_dict,
                    session.get("config_name") or source_payload.get("config_name"),
                    validate_local=False,
                )
                if normalization_errors:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "Unable to organize library files in source payload.",
                                "errors": normalization_errors,
                            }
                        ),
                        400,
                    )
                incoming_dict = normalized_incoming

                merged = libraries_data.copy()

                def _library_prefix(key):
                    if not isinstance(key, str) or not key.startswith(("mov-library_", "sho-library_")):
                        return None
                    if "-template_" in key:
                        return key.split("-template_", 1)[0]
                    if "-attribute_" in key:
                        return key.split("-attribute_", 1)[0]
                    if "-collection_" in key:
                        return key.split("-collection_", 1)[0]
                    if "-overlay_" in key:
                        return key.split("-overlay_", 1)[0]
                    if "-top_level_" in key:
                        return key.split("-top_level_", 1)[0]
                    if key.endswith("-library"):
                        return key[: -len("-library")]
                    return None

                prefixes = set()
                for key in incoming_dict:
                    prefix = _library_prefix(key)
                    if prefix:
                        prefixes.add(prefix)

                for prefix in prefixes:
                    for existing_key in list(merged.keys()):
                        if existing_key.startswith(prefix + "-") or existing_key == f"{prefix}-library":
                            merged.pop(existing_key, None)

                for k, v in incoming_dict.items():
                    if k.endswith("-library") and (v in [None, False, ""]):
                        continue
                    merged[k] = v

                libraries_data = merged
                helpers.ts_log(f"Copy request merged live source payload for {source_prefix}: {len(incoming_dict)} fields", level="DEBUG")
            except Exception as merge_err:
                helpers.ts_log(f"Failed to merge live source payload during copy: {merge_err}", level="ERROR")

        source_items = {k: v for k, v in libraries_data.items() if k.startswith(f"{source_prefix}-")}
        source_errors = path_validation.validate_payload(source_items)
        source_collection_errors = _validate_library_collection_files(libraries_data, [source_prefix])
        source_metadata_errors = _validate_library_metadata_files(libraries_data, [source_prefix])
        source_overlay_errors = _validate_library_overlay_files(libraries_data, [source_prefix])
        source_auto_sort_hubs_errors = _validate_library_auto_sort_hubs(libraries_data, [source_prefix])
        if source_errors:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid path values found in source library: " + " ".join(source_errors),
                        "errors": source_errors,
                    }
                ),
                400,
            )
        if source_collection_errors:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid collection files found in source library: " + " ".join(source_collection_errors),
                        "errors": source_collection_errors,
                    }
                ),
                400,
            )
        if source_metadata_errors:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid metadata files found in source library: " + " ".join(source_metadata_errors),
                        "errors": source_metadata_errors,
                    }
                ),
                400,
            )
        if source_overlay_errors:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid overlay files found in source library: " + " ".join(source_overlay_errors),
                        "errors": source_overlay_errors,
                    }
                ),
                400,
            )
        if source_auto_sort_hubs_errors:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid library settings found in source library: " + " ".join(source_auto_sort_hubs_errors),
                        "errors": source_auto_sort_hubs_errors,
                    }
                ),
                400,
            )
        if not source_items:
            helpers.ts_log(f"Copy aborted: no saved settings found for source {source_prefix}", level="ERROR")
            return jsonify({"success": False, "error": "No saved settings found for source library"}), 404

        movie_libraries, show_libraries, _telemetry = _build_library_lists()
        name_map = {lib["id"]: lib["name"] for lib in (movie_libraries + show_libraries)}

        helpers.ts_log(
            f"Copy request for config={session.get('config_name')} source={source_prefix} targets={target_ids} "
            f"source_items={len(source_items)} existing_keys={len(libraries_data)}",
            level="DEBUG",
        )

        filtered_targets = [tid for tid in target_ids if str(tid).startswith(source_type)]
        if len(filtered_targets) != len(target_ids):
            helpers.ts_log(
                f"Copy filtering targets for type '{source_type}': accepted={filtered_targets} dropped={set(target_ids) - set(filtered_targets)}",
                level="WARNING",
            )
        if not filtered_targets:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"No valid target libraries of type '{source_type}' were selected.",
                    }
                ),
                400,
            )

        merged = libraries_data.copy()
        targets_to_process = [source_prefix] + [tid for tid in filtered_targets if tid != source_prefix]
        config_name = session.get("config_name") or source_payload.get("config_name") or namesgenerator.get_random_name()

        for target_id in targets_to_process:
            target_name = name_map.get(target_id, "")
            # Wipe any existing settings for this target before copying fresh
            for existing_key in list(merged.keys()):
                if existing_key.startswith(f"{target_id}-"):
                    merged.pop(existing_key, None)

            for key, value in source_items.items():
                # Do not mirror the include toggle; require explicit include after mirroring
                if target_id != source_prefix and key.endswith("-library"):
                    merged[f"{target_id}-library"] = ""
                    continue
                new_key = key.replace(source_prefix, target_id, 1)
                new_value = value
                if key.endswith("-library"):
                    new_value = target_name or value
                elif target_id != source_prefix:
                    if key.endswith("-metadata_files"):
                        new_value = _clone_library_file_entries_for_target("metadata_files", value, config_name, target_id)
                    elif key.endswith("-collection_files"):
                        new_value = _clone_library_file_entries_for_target("collection_files", value, config_name, target_id)
                    elif key.endswith("-overlay_files"):
                        new_value = _clone_library_file_entries_for_target("overlay_files", value, config_name, target_id)
                merged[new_key] = new_value

        # Update the aggregated libraries list to include all configured library names
        configured_names = []
        for key, val in merged.items():
            if key.endswith("-library") and val not in [None, "", False]:
                configured_names.append(str(val))
        merged["libraries"] = ",".join(sorted(set(configured_names)))

        # Persist directly to the DB to avoid any loss of data during merge
        database.save_section_data(
            name=config_name,
            section="libraries",
            validated=settings.get("validated", False),
            user_entered=True,
            data={"libraries": merged, "validated": settings.get("validated", False)},
        )

        helpers.ts_log(
            f"Copy complete for config={session.get('config_name')} source={source_prefix} targets={target_ids} " f"merged_keys={len(merged)}",
            level="DEBUG",
        )

        return jsonify({"success": True, "updated": target_ids})

    except Exception as e:
        helpers.ts_log(f"Failed to copy library settings: {e}", level="ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


def _normalize_config_name(raw_name: str | None) -> str:
    name = (raw_name or "").strip().lower().replace(" ", "_")
    return name or "default"


def _safe_bundle_name(raw_name: str | None) -> str:
    safe = secure_filename(_normalize_config_name(raw_name))
    return safe or "default"


def _get_custom_font_files(config_name: str | None = None) -> list[Path]:
    font_files: list[Path] = []
    seen: set[str] = set()
    candidate_dirs: list[Path] = []
    if config_name:
        helpers.migrate_legacy_custom_fonts_to_config(config_name)
        candidate_dirs.append(helpers.get_custom_fonts_dir(config_name))
    candidate_dirs.append(helpers.get_legacy_custom_fonts_dir())
    for custom_dir in candidate_dirs:
        if not custom_dir.is_dir():
            continue
        for entry in sorted(custom_dir.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_file() or entry.suffix.lower() not in helpers.FONT_EXTENSIONS:
                continue
            if entry.name in seen:
                continue
            font_files.append(entry)
            seen.add(entry.name)
    return font_files


def _bundle_artifacts_from_yaml(yaml_text):
    parsed = importer.load_yaml_config(yaml_text)
    return _iter_bundle_artifacts(parsed)


def _build_config_bundle(
    config_text: str,
    config_filename: str,
    font_files: list[Path],
    artifact_files: list[dict] | None = None,
    config_name: str | None = None,
    redacted: bool = False,
) -> BytesIO | None:
    artifact_files = artifact_files or []
    if not config_text or (not font_files and not artifact_files):
        return None
    name = _normalize_config_name(config_name)
    font_names = [font.name for font in font_files]
    has_artifacts = bool(artifact_files)
    readme_lines = [
        "Quickstart config bundle",
        f"Config name: {name}",
        "",
        "This bundle includes:",
        f"- {config_filename}",
    ]
    if font_names:
        readme_lines.append(f"- {name}/fonts/ (custom fonts uploaded in Quickstart)")
        readme_lines.append(f"- Fonts included: {', '.join(font_names)}")
    if has_artifacts:
        readme_lines.append(f"- {name}/metadata_files/, {name}/collection_files/, {name}/overlay_files/ (config-owned library files)")
    readme_lines += [
        "",
        "Install steps:",
        "1) Copy the config file into your Kometa config folder (config/).",
    ]
    if font_names:
        readme_lines.append(f"2) Copy the font files from {name}/fonts/ into your Kometa config/fonts/ folder.")
    if has_artifacts:
        readme_lines.append(f"3) Copy {name}/ into your Kometa config/ folder.")
    readme_lines += [
        "",
        "Note: Validate Kometa and Run Now both sync config-owned library files automatically.",
        "Note: The Quickstart Run Now button also syncs referenced fonts automatically.",
        "This bundle is for manual installs.",
    ]
    if redacted:
        readme_lines += [
            "",
            "This bundle uses a redacted config and is safe to share.",
            "Review before sharing in case you manually added sensitive data.",
        ]
    readme_lines.append("")
    bundle = BytesIO()
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(config_filename, config_text)
        for font_path in font_files:
            zf.write(font_path, f"{name}/fonts/{font_path.name}")
        for artifact in artifact_files:
            _bundle_write_artifact(zf, artifact, redacted=redacted)
        zf.writestr("README.txt", "\n".join(readme_lines))
    bundle.seek(0)
    return bundle


@app.route("/download")
def download():
    yaml_content = session.get("yaml_content", "")
    if yaml_content:
        config_name = session.get("config_name")
        custom_fonts = _get_custom_font_files(config_name)
        artifact_files = _bundle_artifacts_from_yaml(yaml_content)
        if custom_fonts or artifact_files:
            bundle = _build_config_bundle(
                yaml_content,
                "config.yml",
                custom_fonts,
                artifact_files=artifact_files,
                config_name=config_name,
            )
            if bundle:
                bundle_name = f"{_safe_bundle_name(config_name)}_config_bundle.zip"
                return send_file(
                    bundle,
                    mimetype="application/zip",
                    as_attachment=True,
                    download_name=bundle_name,
                )
        return send_file(
            io.BytesIO(yaml_content.encode("utf-8")),
            mimetype="text/yaml",
            as_attachment=True,
            download_name="config.yml",
        )
    flash("No configuration to download", "danger")
    return redirect(url_for("step", name="900-kometa"))


@app.route("/download_redacted")
def download_redacted():
    yaml_content = session.get("yaml_content", "")
    if yaml_content:
        # Redact sensitive information
        redacted_content = helpers.redact_sensitive_data(yaml_content)

        # Serve the redacted YAML as a file download
        config_name = session.get("config_name")
        custom_fonts = _get_custom_font_files(config_name)
        artifact_files = _bundle_artifacts_from_yaml(yaml_content)
        if custom_fonts or artifact_files:
            bundle = _build_config_bundle(
                redacted_content,
                "config_redacted.yml",
                custom_fonts,
                artifact_files=artifact_files,
                config_name=config_name,
                redacted=True,
            )
            if bundle:
                bundle_name = f"{_safe_bundle_name(config_name)}_config_bundle_redacted.zip"
                return send_file(
                    bundle,
                    mimetype="application/zip",
                    as_attachment=True,
                    download_name=bundle_name,
                )
        return send_file(
            io.BytesIO(redacted_content.encode("utf-8")),
            mimetype="text/yaml",
            as_attachment=True,
            download_name="config_redacted.yml",
        )
    flash("No configuration to download", "danger")
    return redirect(url_for("step", name="900-kometa"))


@app.route("/path-validation-rules", methods=["GET"])
def path_validation_rules():
    rules = path_validation.load_rules()
    return jsonify(
        {
            "rules": rules,
            "platform": path_validation.get_platform_key(),
            "is_docker": bool(app.config.get("QUICKSTART_DOCKER")),
        }
    )


@app.route("/validate_library_service_overrides/<library_id>", methods=["POST"])
def validate_library_service_overrides(library_id):
    payload = request.get_json(silent=True) or request.form or {}
    clean_payload = persistence.clean_form_data(MultiDict(payload))
    libraries_data = helpers.build_config_dict("libraries", clean_payload).get("libraries", {})
    if not isinstance(libraries_data, dict):
        libraries_data = {}
    result = _validate_library_service_overrides(library_id, libraries_data, force_validate=True)
    status_code = 200 if result.get("valid") else 400
    return jsonify(result), status_code


def _get_active_tmdb_api_key():
    config_name = session.get("config_name")
    if not config_name:
        return ""
    try:
        _validated, _user_entered, stored = database.retrieve_section_data(config_name, "tmdb")
    except Exception:
        return ""
    if not isinstance(stored, dict):
        return ""
    tmdb_block = stored.get("tmdb", stored)
    if not isinstance(tmdb_block, dict):
        return ""
    api_key = tmdb_block.get("apikey") or tmdb_block.get("api_key") or tmdb_block.get("tmdb_apikey") or tmdb_block.get("token") or ""
    return str(api_key).strip()


def _lookup_tmdb_by_imdb_id(imdb_id, media_type=""):
    api_key = _get_active_tmdb_api_key()
    if not api_key:
        return {"valid": False, "verified": False, "message": "TMDb is not configured for the active config."}

    try:
        response = requests.get(
            f"https://api.themoviedb.org/3/find/{imdb_id}",
            params={"api_key": api_key, "external_source": "imdb_id"},
            timeout=10,
        )
    except requests.RequestException as exc:
        return {"valid": False, "verified": False, "message": f"TMDb lookup failed: {exc}."}

    if response.status_code in {401, 403}:
        return {"valid": False, "verified": False, "message": "TMDb lookup could not be verified with the configured API key."}

    if response.status_code == 404:
        return {"valid": False, "verified": True, "message": "TMDb did not find a matching IMDb ID."}

    if response.status_code != 200:
        return {"valid": False, "verified": False, "message": f"TMDb lookup failed with status {response.status_code}."}

    payload = response.json() if response.content else {}
    movie_results = payload.get("movie_results") if isinstance(payload.get("movie_results"), list) else []
    tv_results = payload.get("tv_results") if isinstance(payload.get("tv_results"), list) else []

    preferred_media_type = str(media_type or "").strip().lower()
    ordered_results = []
    if preferred_media_type == "movie":
        ordered_results.extend(("movie", item) for item in movie_results)
        ordered_results.extend(("show", item) for item in tv_results)
    elif preferred_media_type == "show":
        ordered_results.extend(("show", item) for item in tv_results)
        ordered_results.extend(("movie", item) for item in movie_results)
    else:
        ordered_results.extend(("movie", item) for item in movie_results)
        ordered_results.extend(("show", item) for item in tv_results)

    for result_type, item in ordered_results:
        if not isinstance(item, dict):
            continue
        label = str(item.get("title") or item.get("name") or "").strip()
        if not label:
            continue
        tmdb_id = item.get("id")
        tmdb_suffix = f" (TMDb {tmdb_id})" if tmdb_id not in [None, ""] else ""
        media_label = "movie" if result_type == "movie" else "show"
        return {
            "valid": True,
            "verified": True,
            "label": label,
            "result_type": result_type,
            "message": f"TMDb {media_label}: {label}{tmdb_suffix}",
        }

    return {"valid": False, "verified": True, "message": "TMDb did not find a matching IMDb ID."}


def _lookup_tmdb_external_ids(endpoint, tmdb_id, api_key):
    if endpoint not in {"movie", "tv"} or not tmdb_id or not api_key:
        return {}

    try:
        response = requests.get(
            f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}/external_ids",
            params={"api_key": api_key},
            timeout=10,
        )
    except requests.RequestException:
        return {}

    if response.status_code != 200:
        return {}

    payload = response.json() if response.content else {}
    return payload if isinstance(payload, dict) else {}


def _lookup_tmdb_numeric_id(tmdb_id, media_type=""):
    api_key = _get_active_tmdb_api_key()
    if not api_key:
        return {"valid": False, "verified": False, "message": "TMDb is not configured for the active config."}

    preferred_media_type = str(media_type or "").strip().lower()
    endpoint_order = []
    if preferred_media_type == "movie":
        endpoint_order = [("movie", "movie"), ("tv", "show"), ("collection", "collection"), ("person", "person")]
    elif preferred_media_type == "show":
        endpoint_order = [("tv", "show"), ("movie", "movie"), ("collection", "collection"), ("person", "person")]
    else:
        endpoint_order = [("movie", "movie"), ("tv", "show"), ("collection", "collection"), ("person", "person")]

    for endpoint, result_type in endpoint_order:
        try:
            response = requests.get(
                f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}",
                params={"api_key": api_key},
                timeout=10,
            )
        except requests.RequestException as exc:
            return {"valid": False, "verified": False, "message": f"TMDb lookup failed: {exc}."}

        if response.status_code in {401, 403}:
            return {"valid": False, "verified": False, "message": "TMDb lookup could not be verified with the configured API key."}

        if response.status_code == 404:
            continue

        if response.status_code != 200:
            return {"valid": False, "verified": False, "message": f"TMDb lookup failed with status {response.status_code}."}

        payload = response.json() if response.content else {}
        label = str(payload.get("title") or payload.get("name") or "").strip()
        if not label:
            label = f"TMDb {result_type} {tmdb_id}"
        external_ids = _lookup_tmdb_external_ids(endpoint, tmdb_id, api_key) if endpoint in {"movie", "tv"} else {}
        tvdb_id = external_ids.get("tvdb_id")
        id_suffix = f" (TMDb {tmdb_id})"
        if tvdb_id not in [None, "", 0, "0"]:
            id_suffix = f" (TMDb {tmdb_id}, TVDb {tvdb_id})"

        return {
            "valid": True,
            "verified": True,
            "label": label,
            "result_type": result_type,
            "tvdb_id": tvdb_id,
            "message": f"TMDb {result_type}: {label}{id_suffix}",
        }

    return {"valid": False, "verified": True, "message": "TMDb did not find a matching numeric ID."}


def _normalize_tmdb_library_media_type(value):
    normalized = str(value or "").strip().lower()
    if normalized in {"movie", "movies", "mov"}:
        return "movie"
    if normalized in {"show", "shows", "sho", "tv", "season", "seasons", "episode", "episodes"}:
        return "show"
    return normalized


def _build_tmdb_library_type_warning(tmdb_message, tmdb_result_type, expected_media_type, value_label="ID"):
    resolved_type = _normalize_tmdb_library_media_type(tmdb_result_type)
    expected_type = _normalize_tmdb_library_media_type(expected_media_type)
    if not resolved_type or expected_type not in {"movie", "show"}:
        return ""
    if resolved_type == expected_type:
        return ""

    library_label = "movie library" if expected_type == "movie" else "show/season/episode library"
    readable_type = {
        "movie": "movie",
        "show": "show",
        "collection": "collection",
        "person": "person",
    }.get(resolved_type, resolved_type)
    return f"{tmdb_message}. This {value_label} resolves to a {readable_type}, but the active library is a {library_label}."


def _parse_optional_id_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    text = str(value).strip()
    if not text or text.lower() == "none":
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]

    return [item.strip() for item in text.split(",") if item.strip()]


@app.route("/lookup_template_string_value", methods=["POST"])
def lookup_template_string_value():
    data = request.get_json(silent=True) or {}
    preset = str(data.get("preset") or "").strip()
    value = str(data.get("value") or "").strip()
    library_name = str(data.get("library_name") or "").strip()
    media_type = str(data.get("media_type") or "").strip()

    if not preset or not value:
        return jsonify({"error": "Lookup preset and value are required."}), 400

    if preset == "tmdb_collection_id":
        api_key = _get_active_tmdb_api_key()
        if not api_key:
            return jsonify({"valid": False, "verified": False, "message": "TMDb is not configured for the active config."})
        try:
            response = requests.get(
                f"https://api.themoviedb.org/3/collection/{value}",
                params={"api_key": api_key},
                timeout=10,
            )
        except requests.RequestException as exc:
            return jsonify({"valid": False, "verified": False, "message": f"TMDb lookup failed: {exc}."})

        if response.status_code == 200:
            payload = response.json() if response.content else {}
            label = str(payload.get("name") or "").strip()
            if label:
                return jsonify({"valid": True, "verified": True, "label": label, "message": f"TMDb: {label}"})
            return jsonify({"valid": False, "verified": True, "message": "TMDb collection found, but no collection name was returned."})

        if response.status_code == 404:
            return jsonify({"valid": False, "verified": True, "message": "TMDb collection ID not found."})

        if response.status_code in {401, 403}:
            return jsonify({"valid": False, "verified": False, "message": "TMDb lookup could not be verified with the configured API key."})

        return jsonify({"valid": False, "verified": False, "message": f"TMDb lookup failed with status {response.status_code}."})

    if preset == "numeric_id":
        tmdb_result = _lookup_tmdb_numeric_id(value, media_type=media_type)
        tmdb_label = str(tmdb_result.get("label") or "").strip()
        tmdb_message = str(tmdb_result.get("message") or "").strip()
        tmdb_result_type = str(tmdb_result.get("result_type") or "").strip().lower()
        expected_media_type = str(media_type or "").strip().lower()

        warning_message = _build_tmdb_library_type_warning(tmdb_message, tmdb_result_type, expected_media_type, value_label="numeric ID")
        if tmdb_result.get("valid") and tmdb_result.get("verified") and warning_message:
            return jsonify(
                {
                    "valid": True,
                    "verified": True,
                    "label": tmdb_label,
                    "level": "warning",
                    "message": warning_message,
                }
            )

        if tmdb_result.get("valid") and tmdb_result.get("verified") and tmdb_label and library_name and tmdb_result_type in {"movie", "show"}:
            try:
                plex_match = helpers.find_item_by_title(library_name, tmdb_label)
            except Exception as exc:
                return jsonify({"valid": False, "verified": False, "message": f"Plex lookup failed: {exc}."})

            if plex_match and plex_match.get("title"):
                plex_title = str(plex_match.get("title")).strip()
                return jsonify(
                    {
                        "valid": True,
                        "verified": True,
                        "label": plex_title,
                        "message": f"Plex title match: {plex_title}. {tmdb_message}",
                    }
                )

            return jsonify(
                {
                    "valid": True,
                    "verified": True,
                    "label": tmdb_label,
                    "level": "warning",
                    "message": f"{tmdb_message}. Plex could not confirm a match in the active library.",
                }
            )

        return jsonify(tmdb_result)

    if preset in {"imdb_id_plex", "imdb_id_tmdb"}:
        tmdb_result = _lookup_tmdb_by_imdb_id(value, media_type=media_type)
        tmdb_label = str(tmdb_result.get("label") or "").strip()
        tmdb_message = str(tmdb_result.get("message") or "").strip()
        tmdb_result_type = str(tmdb_result.get("result_type") or "").strip().lower()
        expected_media_type = str(media_type or "").strip().lower()

        warning_message = _build_tmdb_library_type_warning(tmdb_message, tmdb_result_type, expected_media_type, value_label="IMDb ID")
        if tmdb_result.get("valid") and tmdb_result.get("verified") and warning_message:
            return jsonify(
                {
                    "valid": True,
                    "verified": True,
                    "label": tmdb_label,
                    "level": "warning",
                    "message": warning_message,
                }
            )

        if preset == "imdb_id_tmdb":
            return jsonify(tmdb_result)

        if not library_name:
            return jsonify({"valid": False, "verified": False, "message": "Active Plex library is required for IMDb lookup."})

        find_item_by_imdb_id = helpers.find_item_by_imdb_id
        try:
            supports_fallback_title = "fallback_title" in inspect.signature(find_item_by_imdb_id).parameters
        except (TypeError, ValueError):
            supports_fallback_title = True

        try:
            if supports_fallback_title:
                result = find_item_by_imdb_id(library_name, value, media_type, fallback_title=tmdb_label)
            else:
                result = find_item_by_imdb_id(library_name, value, media_type)
        except Exception as exc:
            return jsonify({"valid": False, "verified": False, "message": f"Plex lookup failed: {exc}."})

        if result and result.get("title"):
            title = str(result.get("title")).strip()
            return jsonify({"valid": True, "verified": True, "label": title, "message": f"Plex: {title}"})

        if tmdb_result.get("valid") and tmdb_result.get("verified"):
            if tmdb_label and tmdb_message:
                return jsonify(
                    {
                        "valid": True,
                        "verified": True,
                        "label": tmdb_label,
                        "level": "warning",
                        "message": f"{tmdb_message}. Plex could not confirm a match in the active library.",
                    }
                )
            return jsonify(tmdb_result)

        fallback_message = "IMDb ID format is valid, but no matching item was found in the active Plex library."
        if tmdb_message:
            fallback_message = f"{fallback_message} {tmdb_message}"
        return jsonify(
            {
                "valid": False,
                "verified": bool(tmdb_result.get("verified")),
                "message": fallback_message,
            }
        )

    return jsonify({"error": f"Unsupported lookup preset: {preset}"}), 400


@app.route("/validate_all_services", methods=["POST"])
def validate_all_services():
    config_name = session.get("config_name") or persistence.ensure_session_config_name()

    def is_blank_value(value):
        if value is None:
            return True
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed == "":
                return True
            if trimmed.lower() == "none":
                return True
        return False

    def has_required_credentials(payload, required_keys):
        for key in required_keys:
            value = payload.get(key)
            if value is None:
                return False
            if isinstance(value, str) and not value.strip():
                return False
            if isinstance(value, str) and value.strip().lower() == "none":
                return False
        return True

    def apply_validation_metadata(stored_data, status, reason=None, details=None, updated_at=None):
        if not isinstance(stored_data, dict):
            stored_data = {}
        stored_data["validation_status"] = status
        if reason is not None:
            stored_data["validation_reason"] = reason
        if details is not None:
            stored_data["validation_details"] = details
        stored_data["validation_updated_at"] = updated_at or utc_now_iso()
        return stored_data

    def persist_validation_metadata(section, status, reason=None, details=None, validated_override=None):
        stored_validated, user_entered, stored_data = database.retrieve_section_data(config_name, section)
        stored_data = apply_validation_metadata(stored_data, status, reason=reason, details=details)
        validated_value = stored_validated if validated_override is None else validated_override
        database.save_section_data(
            name=config_name,
            section=section,
            validated=validated_value,
            user_entered=user_entered,
            data=stored_data,
        )

    targets = [
        (
            "010-plex",
            "plex",
            validations.validate_plex_server,
            lambda s: {"plex_url": s.get("plex", {}).get("url"), "plex_token": s.get("plex", {}).get("token")},
            ["plex_url", "plex_token"],
        ),
        ("020-tmdb", "tmdb", validations.validate_tmdb_server, lambda s: {"tmdb_apikey": s.get("tmdb", {}).get("apikey")}, ["tmdb_apikey"]),
        (
            "030-tautulli",
            "tautulli",
            validations.validate_tautulli_server,
            lambda s: {"tautulli_url": s.get("tautulli", {}).get("url"), "tautulli_apikey": s.get("tautulli", {}).get("apikey")},
            ["tautulli_url", "tautulli_apikey"],
        ),
        ("040-github", "github", validations.validate_github_server, lambda s: {"github_token": s.get("github", {}).get("token")}, ["github_token"]),
        ("050-omdb", "omdb", validations.validate_omdb_server, lambda s: {"omdb_apikey": s.get("omdb", {}).get("apikey")}, ["omdb_apikey"]),
        ("060-mdblist", "mdblist", validations.validate_mdblist_server, lambda s: {"mdblist_apikey": s.get("mdblist", {}).get("apikey")}, ["mdblist_apikey"]),
        ("070-notifiarr", "notifiarr", validations.validate_notifiarr_server, lambda s: {"notifiarr_apikey": s.get("notifiarr", {}).get("apikey")}, ["notifiarr_apikey"]),
        (
            "080-gotify",
            "gotify",
            validations.validate_gotify_server,
            lambda s: {"gotify_url": s.get("gotify", {}).get("url"), "gotify_token": s.get("gotify", {}).get("token")},
            ["gotify_url", "gotify_token"],
        ),
        (
            "085-ntfy",
            "ntfy",
            validations.validate_ntfy_server,
            lambda s: {"ntfy_url": s.get("ntfy", {}).get("url"), "ntfy_token": s.get("ntfy", {}).get("token"), "ntfy_topic": s.get("ntfy", {}).get("topic")},
            ["ntfy_url", "ntfy_token", "ntfy_topic"],
        ),
        (
            "087-apprise",
            "apprise",
            validations.validate_apprise_server,
            lambda s: {"apprise_location": s.get("apprise", {}).get("location")},
            ["apprise_location"],
        ),
        (
            "110-radarr",
            "radarr",
            validations.validate_radarr_server,
            lambda s: {"radarr_url": s.get("radarr", {}).get("url"), "radarr_token": s.get("radarr", {}).get("token")},
            ["radarr_url", "radarr_token"],
        ),
        (
            "120-sonarr",
            "sonarr",
            validations.validate_sonarr_server,
            lambda s: {"sonarr_url": s.get("sonarr", {}).get("url"), "sonarr_token": s.get("sonarr", {}).get("token")},
            ["sonarr_url", "sonarr_token"],
        ),
    ]

    results = {}
    summary = {"validated": 0, "failed": 0, "skipped": 0}

    for template_key, section, validator, payload_builder, required_keys in targets:
        settings = persistence.retrieve_settings(template_key)
        validated_at = settings.get("validated_at")
        payload = payload_builder(settings) or {}
        if section == "apprise":
            apprise_settings = settings.get("apprise", {}) if isinstance(settings, dict) else {}
            apprise_location = apprise_settings.get("location") if isinstance(apprise_settings, dict) else None
            if is_blank_value(apprise_location):
                results[template_key] = {
                    "status": "skipped",
                    "validated_at": validated_at or "",
                    "reason": "missing_location",
                }
                persist_validation_metadata(section, "skipped", reason="missing_location")
                summary["skipped"] += 1
                continue
        if not has_required_credentials(payload, required_keys):
            results[template_key] = {
                "status": "skipped",
                "validated_at": validated_at or "",
                "reason": "missing_credentials",
            }
            persist_validation_metadata(section, "skipped", reason="missing_credentials")
            summary["skipped"] += 1
            continue
        try:
            response = validator(payload)
            if isinstance(response, tuple) and response:
                response = response[0]
            response_data = response.get_json() if hasattr(response, "get_json") else response
            if not isinstance(response_data, dict):
                response_data = {}
        except Exception as e:
            response_data = {"valid": False, "error": str(e)}

        is_valid = helpers.booler(response_data.get("validated", response_data.get("valid", False)))
        stored_validated, user_entered, stored_data = database.retrieve_section_data(config_name, section)
        if not isinstance(stored_data, dict):
            stored_data = {}
        existing_validated_at = stored_data.get("validated_at") or validated_at or ""

        if is_valid:
            new_validated_at = utc_now_iso()
            stored_data["validated"] = True
            stored_data["validated_at"] = new_validated_at
            stored_data = apply_validation_metadata(stored_data, "validated")
            database.save_section_data(
                name=config_name,
                section=section,
                validated=True,
                user_entered=user_entered,
                data=stored_data,
            )
            results[template_key] = {"status": "validated", "validated_at": new_validated_at}
            summary["validated"] += 1
        else:
            stored_data["validated"] = False
            if existing_validated_at:
                stored_data["validated_at"] = existing_validated_at
            message = response_data.get("message") or response_data.get("error")
            fail_reason = None
            if isinstance(message, str) and "invalid" in message.lower():
                fail_reason = "token_invalid"
            else:
                fail_reason = "validation_error"
            stored_data = apply_validation_metadata(stored_data, "failed", reason=fail_reason, details=message)
            database.save_section_data(
                name=config_name,
                section=section,
                validated=False,
                user_entered=user_entered,
                data=stored_data,
            )
            results[template_key] = {"status": "failed", "validated_at": existing_validated_at, "reason": fail_reason}
            if message:
                results[template_key]["details"] = message
            summary["failed"] += 1

    def update_section_validation(template_key, section, is_valid, reason=None, details=None):
        stored_validated, user_entered, stored_data = database.retrieve_section_data(config_name, section)
        if not isinstance(stored_data, dict):
            stored_data = {}
        existing_validated_at = stored_data.get("validated_at") or ""

        if is_valid:
            new_validated_at = utc_now_iso()
            stored_data["validated"] = True
            stored_data["validated_at"] = new_validated_at
            stored_data = apply_validation_metadata(stored_data, "validated")
            database.save_section_data(
                name=config_name,
                section=section,
                validated=True,
                user_entered=user_entered,
                data=stored_data,
            )
            results[template_key] = {"status": "validated", "validated_at": new_validated_at}
            summary["validated"] += 1
            return

        stored_data["validated"] = False
        if existing_validated_at:
            stored_data["validated_at"] = existing_validated_at
        stored_data = apply_validation_metadata(stored_data, "failed", reason=reason, details=details)
        database.save_section_data(
            name=config_name,
            section=section,
            validated=False,
            user_entered=user_entered,
            data=stored_data,
        )
        result = {"status": "failed", "validated_at": existing_validated_at}
        if reason:
            result["reason"] = reason
        if details:
            result["details"] = details
        results[template_key] = result
        summary["failed"] += 1

    def skip_section_validation(template_key, section, reason=None, details=None):
        stored_validated, user_entered, stored_data = database.retrieve_section_data(config_name, section)
        if not isinstance(stored_data, dict):
            stored_data = {}
        existing_validated_at = stored_data.get("validated_at") or ""
        stored_data = apply_validation_metadata(stored_data, "skipped", reason=reason, details=details)
        database.save_section_data(
            name=config_name,
            section=section,
            validated=stored_validated,
            user_entered=user_entered,
            data=stored_data,
        )
        result = {"status": "skipped", "validated_at": existing_validated_at}
        if reason:
            result["reason"] = reason
        if details:
            result["details"] = details
        results[template_key] = result
        summary["skipped"] += 1

    kometa_settings, kometa_section = _get_kometa_settings_section(config_name)
    del kometa_settings
    kometa_valid, kometa_reason, kometa_details = _validate_saved_kometa_selection(kometa_section)
    update_section_validation(
        "001-start",
        "kometa",
        kometa_valid,
        reason=kometa_reason,
        details=kometa_details,
    )

    # Bulk validation for libraries
    plex_settings = persistence.retrieve_settings("010-plex") or {}
    plex_is_valid = helpers.booler(plex_settings.get("validated", False)) if isinstance(plex_settings, dict) else False
    if not plex_is_valid:
        skip_section_validation("025-libraries", "libraries", reason="missing_plex_validation")
    else:
        libraries_settings = persistence.retrieve_settings("025-libraries") or {}
        libraries_data = libraries_settings.get("libraries", {}) if isinstance(libraries_settings, dict) else {}
        selected_library_ids = [
            key[: -len("-library")]
            for key, value in libraries_data.items()
            if isinstance(key, str) and key.startswith(("mov-library_", "sho-library_")) and key.endswith("-library") and not is_blank_value(value)
        ]

        if not selected_library_ids:
            skip_section_validation("025-libraries", "libraries", reason="no_libraries")
        else:
            libraries_reason = None
            path_errors = path_validation.validate_payload(libraries_data)
            collection_file_errors = _validate_library_collection_files(libraries_data, selected_library_ids)
            metadata_file_errors = _validate_library_metadata_files(libraries_data, selected_library_ids)
            overlay_file_errors = _validate_library_overlay_files(libraries_data, selected_library_ids)
            auto_sort_hubs_errors = _validate_library_auto_sort_hubs(libraries_data, selected_library_ids)
            arr_override_errors = []
            if path_errors:
                libraries_reason = "invalid_paths"
            elif collection_file_errors:
                libraries_reason = "invalid_collection_files"
            elif overlay_file_errors:
                libraries_reason = "invalid_overlay_files"
            elif metadata_file_errors:
                libraries_reason = "invalid_metadata_files"
            elif auto_sort_hubs_errors:
                libraries_reason = "invalid_library_settings"
            else:

                def has_minimal_library_yaml_selection(lib_id):
                    allowed_markers = ("-collection_", "-overlay_", "-attribute_", "-top_level_", "-metadata_files", "-collection_files", "-overlay_files")
                    for key, value in libraries_data.items():
                        if not isinstance(key, str) or not key.startswith(f"{lib_id}-"):
                            continue
                        if key in {f"{lib_id}-library", f"{lib_id}-playlist"}:
                            continue
                        if "-playlist" in key:
                            continue
                        if not any(marker in key for marker in allowed_markers):
                            continue
                        if not is_blank_value(value) and str(value).strip().lower() != "false":
                            return True
                    return False

                missing_minimal_yaml = [lib_id for lib_id in selected_library_ids if not has_minimal_library_yaml_selection(lib_id)]
                if missing_minimal_yaml:
                    libraries_reason = "missing_library_defaults"

                missing_placeholders = []
                library_names = {}
                for lib_id in selected_library_ids:
                    name = libraries_data.get(f"{lib_id}-library")
                    library_names[lib_id] = name if isinstance(name, str) and name.strip() else lib_id

                def find_library_value(lib_id, suffixes):
                    for suffix in suffixes:
                        direct = f"{lib_id}-{suffix}"
                        if direct in libraries_data:
                            return libraries_data.get(direct)
                    for key, value in libraries_data.items():
                        if not isinstance(key, str) or not key.startswith(f"{lib_id}-"):
                            continue
                        if any(key.endswith(suffix) for suffix in suffixes):
                            return value
                    return None

                if libraries_reason is None:
                    for lib_id in selected_library_ids:
                        use_separator = find_library_value(lib_id, ["template_variables[use_separator]", "attribute_use_separator"])
                        if is_blank_value(use_separator) or str(use_separator).strip().lower() == "none":
                            continue
                        placeholder_keys = [
                            "attribute_template_variables[placeholder_imdb_id]",
                            "template_variables[placeholder_imdb_id]",
                        ]
                        if str(lib_id).startswith("mov-"):
                            placeholder_keys.extend(
                                [
                                    "attribute_template_variables[placeholder_tmdb_movie]",
                                    "template_variables[placeholder_tmdb_movie]",
                                ]
                            )
                        else:
                            placeholder_keys.extend(
                                [
                                    "attribute_template_variables[placeholder_tvdb_show]",
                                    "template_variables[placeholder_tvdb_show]",
                                ]
                            )
                        placeholder = find_library_value(lib_id, placeholder_keys)
                        if is_blank_value(placeholder):
                            missing_placeholders.append(library_names.get(lib_id, lib_id))
                if libraries_reason is None and missing_placeholders:
                    libraries_reason = "missing_separator_placeholder"

                if libraries_reason is None:
                    for lib_id in selected_library_ids:
                        override_result = _validate_library_service_overrides(lib_id, libraries_data)
                        if not override_result.get("valid") and not override_result.get("skipped"):
                            arr_override_errors.extend(list(override_result.get("errors") or []))
                if libraries_reason is None and arr_override_errors:
                    libraries_reason = "invalid_arr_overrides"

            update_section_validation(
                "025-libraries",
                "libraries",
                libraries_reason is None,
                reason=libraries_reason,
                details=(
                    missing_placeholders
                    if libraries_reason == "missing_separator_placeholder"
                    else arr_override_errors if libraries_reason == "invalid_arr_overrides" else auto_sort_hubs_errors if libraries_reason == "invalid_library_settings" else None
                ),
            )

    # Bulk validation for settings
    settings_settings = persistence.retrieve_settings("150-settings") or {}
    settings_section = settings_settings.get("settings", {}) if isinstance(settings_settings, dict) else {}
    if not isinstance(settings_section, dict) or not settings_section:
        skip_section_validation("150-settings", "settings", reason="missing_settings")
    else:
        invalid_fields = []

        def check_regex(key, pattern, flags=0, allow_blank=False):
            if key not in settings_section:
                return
            value = settings_section.get(key)
            if value is None:
                return
            if isinstance(value, str) and not value.strip():
                if allow_blank:
                    return
                invalid_fields.append(key)
                return
            value_text = str(value).strip()
            if not re.match(pattern, value_text, flags):
                invalid_fields.append(key)

        check_regex("asset_depth", r"^(0|[1-9]\d*)$")
        check_regex("overlay_artwork_quality", r"^(100|[1-9][0-9]?)$", allow_blank=True)
        check_regex("cache_expiration", r"^[1-9]\d*$")
        check_regex("item_refresh_delay", r"^(0|[1-9]\d*)$")
        check_regex("minimum_items", r"^[1-9]\d*$")
        check_regex("run_again_delay", r"^(0|[1-9]\d*)$")
        ignore_ids_values = _parse_optional_id_list(settings_section.get("ignore_ids"))
        if any(not re.match(r"^\d{1,8}$", item) for item in ignore_ids_values):
            invalid_fields.append("ignore_ids")

        ignore_imdb_ids_values = _parse_optional_id_list(settings_section.get("ignore_imdb_ids"))
        if any(not re.match(r"^tt\d{7,8}$", item, re.IGNORECASE) for item in ignore_imdb_ids_values):
            invalid_fields.append("ignore_imdb_ids")

        if not _is_valid_auto_sort_hubs_value(settings_section.get("auto_sort_hubs")):
            invalid_fields.append("auto_sort_hubs")

        check_regex("custom_repo", r"^(None|https?:\/\/[\da-z.-]+\.[a-z.]{2,6}([/\w.-]*)*\/?)$", flags=re.IGNORECASE, allow_blank=True)

        asset_dirs = settings_section.get("asset_directory") if isinstance(settings_section, dict) else None
        if isinstance(asset_dirs, str):
            asset_dirs = [line.strip() for line in asset_dirs.splitlines() if line.strip()]
        elif isinstance(asset_dirs, list):
            asset_dirs = [str(item).strip() for item in asset_dirs if str(item).strip()]
        else:
            asset_dirs = []

        if asset_dirs:
            md = MultiDict()
            for entry in asset_dirs:
                md.add("asset_directory", entry)
            path_errors = path_validation.validate_payload(md)
            if path_errors:
                invalid_fields.append("asset_directory")

        if invalid_fields:
            update_section_validation("150-settings", "settings", False, reason="invalid_fields")
        else:
            update_section_validation("150-settings", "settings", True)

    # Bulk validation for AniDB
    anidb_settings = persistence.retrieve_settings("100-anidb") or {}
    anidb_data = anidb_settings.get("anidb", {}) if isinstance(anidb_settings, dict) else {}
    anidb_enabled = helpers.booler(anidb_data.get("enable")) if isinstance(anidb_data, dict) else False
    if anidb_enabled:
        update_section_validation("100-anidb", "anidb", True)
    else:
        skip_section_validation("100-anidb", "anidb", reason="disabled")

    # Bulk validation for Webhooks
    webhooks_settings = persistence.retrieve_settings("090-webhooks") or {}
    webhooks_data = webhooks_settings.get("webhooks", {}) if isinstance(webhooks_settings, dict) else {}
    configured_webhooks = False
    if isinstance(webhooks_data, dict):
        for value in webhooks_data.values():
            if is_blank_value(value):
                continue
            configured_webhooks = True
            break
    if configured_webhooks:
        update_section_validation("090-webhooks", "webhooks", True)
    else:
        skip_section_validation("090-webhooks", "webhooks", reason="no_webhooks")

    # Bulk validation for Trakt (token check if present)
    trakt_settings = persistence.retrieve_settings("130-trakt") or {}
    trakt_data = trakt_settings.get("trakt", {}) if isinstance(trakt_settings, dict) else {}
    trakt_auth = trakt_data.get("authorization", {}) if isinstance(trakt_data, dict) else {}
    trakt_access = trakt_auth.get("access_token") if isinstance(trakt_auth, dict) else None
    trakt_client_id = trakt_data.get("client_id") if isinstance(trakt_data, dict) else None
    if is_blank_value(trakt_access) or is_blank_value(trakt_client_id):
        skip_section_validation("130-trakt", "trakt", reason="missing_tokens")
    else:
        try:
            response = requests.get(
                "https://api.trakt.tv/users/settings",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {trakt_access}",
                    "trakt-api-version": "2",
                    "trakt-api-key": trakt_client_id,
                },
                timeout=10,
            )
            if response.status_code == 200:
                update_section_validation("130-trakt", "trakt", True)
            elif response.status_code == 423:
                update_section_validation("130-trakt", "trakt", False, reason="account_locked")
            elif response.status_code in (401, 403):
                update_section_validation("130-trakt", "trakt", False, reason="token_invalid")
            else:
                update_section_validation("130-trakt", "trakt", False, reason="validation_error")
        except requests.exceptions.RequestException:
            update_section_validation("130-trakt", "trakt", False, reason="validation_error")

    # Bulk validation for MAL (token check if present)
    mal_settings = persistence.retrieve_settings("140-mal") or {}
    mal_data = mal_settings.get("mal", {}) if isinstance(mal_settings, dict) else {}
    mal_auth = mal_data.get("authorization", {}) if isinstance(mal_data, dict) else {}
    mal_access = mal_auth.get("access_token") if isinstance(mal_auth, dict) else None
    if is_blank_value(mal_access):
        skip_section_validation("140-mal", "mal", reason="missing_tokens")
    else:
        try:
            response = requests.get(
                "https://api.myanimelist.net/v2/users/@me",
                headers={"Authorization": f"Bearer {mal_access}"},
                timeout=10,
            )
            if response.status_code == 200:
                update_section_validation("140-mal", "mal", True)
            elif response.status_code in (401, 403):
                update_section_validation("140-mal", "mal", False, reason="token_invalid")
            else:
                update_section_validation("140-mal", "mal", False, reason="validation_error")
        except requests.exceptions.RequestException:
            update_section_validation("140-mal", "mal", False, reason="validation_error")

    reason_labels = {
        "missing_credentials": "Missing credentials",
        "missing_plex_validation": "Plex not validated",
        "no_libraries": "No libraries selected",
        "missing_location": "Missing location",
        "invalid_paths": "Invalid paths",
        "invalid_arr_overrides": "Invalid Arr overrides",
        "missing_library_defaults": "Missing library defaults",
        "missing_separator_placeholder": "Missing separator placeholder",
        "invalid_fields": "Invalid fields",
        "no_webhooks": "No webhooks configured",
        "disabled": "Disabled",
        "missing_settings": "Settings missing",
        "missing_tokens": "Missing tokens",
        "token_invalid": "Invalid tokens",
        "account_locked": "Account locked",
        "validation_error": "Validation error",
    }
    label_map = {}
    try:
        for file, display_name in helpers.get_menu_list():
            label_map[file.rsplit(".", 1)[0]] = display_name
    except Exception:
        label_map = {}

    def label_for_key(key):
        return label_map.get(key, key)

    def format_with_reason(key, result):
        label = label_for_key(key)
        reason = result.get("reason")
        details = result.get("details")
        if not reason:
            return label
        pretty = reason_labels.get(reason, reason.replace("_", " "))
        detail_text = ""
        if isinstance(details, (list, tuple)):
            detail_text = ", ".join(str(item) for item in details if str(item))
        elif details is not None:
            detail_text = str(details)
        if detail_text:
            return f"{label} ({pretty}: {detail_text})"
        return f"{label} ({pretty})"

    failed_keys = [key for key, result in results.items() if result.get("status") == "failed"]
    failed_labels = [format_with_reason(key, results[key]) for key in failed_keys]
    failed_detail = f" Failed: {', '.join(failed_labels)}." if failed_labels else ""  # noqa: F841
    skipped_keys = [key for key, result in results.items() if result.get("status") == "skipped"]
    skipped_labels = [format_with_reason(key, results[key]) for key in skipped_keys]
    skipped_detail = f" Skipped: {', '.join(skipped_labels)}." if skipped_labels else ""  # noqa: F841
    ok = summary.get("validated", 0)
    failed = summary.get("failed", 0)
    skipped = summary.get("skipped", 0)
    separator = "\u2022"
    summary_text = f"Completed. Validated: {ok} {separator} Failed: {failed} {separator} Skipped: {skipped}."
    summary_updated_at = utc_now_iso()
    summary_payload = {
        "summary_text": summary_text,
        "summary": summary,
        "results": results,
        "updated_at": summary_updated_at,
    }
    database.save_section_data(
        name=config_name,
        section="validation_summary",
        validated=True,
        user_entered=True,
        data=summary_payload,
    )
    return jsonify({"success": True, "results": results, "summary": summary, "summary_text": summary_text, "summary_updated_at": summary_updated_at})


@app.route("/shutdown", methods=["POST"])
def shutdown():
    if app.config.get("QUICKSTART_DOCKER"):
        return jsonify(success=False, message="Shutdown is disabled in Docker."), 403

    data = request.get_json(silent=True) or {}
    nonce = data.get("nonce")
    confirmed = data.get("confirmed") is True
    session_nonce = session.get("shutdown_nonce")

    if not confirmed or not nonce or nonce != session_nonce:
        return jsonify(success=False, message="Shutdown not authorized."), 403

    session.pop("shutdown_nonce", None)

    shutdown_func = request.environ.get("werkzeug.server.shutdown")

    def shutdown_later():
        # Allow the response to flush before stopping the process.
        time.sleep(0.5)

        if shutdown_func:
            try:
                shutdown_func()
            except Exception as e:
                helpers.ts_log(f"Werkzeug shutdown failed: {e}", level="DEBUG")

        shutdown_event.set()

        try:
            from PyQt5.QtCore import QTimer
            from PyQt5.QtWidgets import QApplication

            qt_app = QApplication.instance()
            if qt_app:
                QTimer.singleShot(0, qt_app.quit)
        except Exception:
            pass

        # Fallback: ensure the process exits even if threads linger.
        time.sleep(2)
        os._exit(0)

    threading.Thread(target=shutdown_later, daemon=True).start()
    return jsonify(success=True, message="Shutting down..."), 200


@app.route("/start-kometa", methods=["POST"])
def start_kometa():
    data = request.get_json() or {}
    command = data.get("command", "").strip()
    start_mode = _normalize_kometa_start_mode(data.get("start_mode"))
    if not command:
        return jsonify({"error": "No command provided"}), 400
    config_name = session.get("config_name") if has_request_context() else None
    _settings, kometa_section = _get_kometa_settings_section(config_name)
    selection = _resolve_kometa_selection(kometa_section)
    if selection.get("install_mode") == KOMETA_INSTALL_MODE_EXTERNAL:
        return jsonify({"error": "External Kometa mode cannot launch Kometa from Quickstart. Quickstart can only sync config and optional logs in this mode."}), 400

    if helpers.is_kometa_running():
        pid = helpers.get_kometa_pid()
        try:
            proc = psutil.Process(pid)
            started_at = datetime.fromtimestamp(proc.create_time()).isoformat()
            return jsonify({"error": f"Kometa is already running (PID: {pid}) since {started_at}.", "status": "running", "pid": pid, "started_at": started_at}), 400
        except Exception:
            return jsonify({"error": f"Kometa is already running (PID: {pid}).", "status": "running", "pid": pid}), 400
    else:
        proc = _find_running_kometa_process()
        if proc:
            try:
                with open(helpers.get_kometa_pid_file(), "w", encoding="utf-8") as f:
                    f.write(str(proc.pid))
                started_at = datetime.fromtimestamp(proc.create_time()).isoformat()
            except Exception:
                started_at = None
            payload = {"error": f"Kometa is already running (PID: {proc.pid}).", "status": "running", "pid": proc.pid}
            if started_at:
                payload["started_at"] = started_at
            return jsonify(payload), 400

    blocker = _get_active_work_blocker("kometa_run")
    if blocker:
        job = blocker.get("job") if isinstance(blocker.get("job"), dict) else {}
        payload = {
            "error": blocker.get("message") or "Cannot start Kometa right now.",
            "status": "blocked",
            "blocked_by": blocker.get("blocked_by"),
            "target_page": blocker.get("target_page"),
        }
        if job.get("job_id"):
            payload["job_id"] = job.get("job_id")
        if job.get("phase"):
            payload["phase"] = job.get("phase")
        return jsonify(payload), 409

    _update_run_context(command, start_mode=start_mode)

    maintenance_config_name = session.get("config_name")
    start_min, end_min, window_str = _resolve_maintenance_window_live(config_name=maintenance_config_name)
    if start_min is None or end_min is None:
        start_min, end_min, window_str = _resolve_maintenance_window_from_db(config_name=maintenance_config_name)
    if _is_within_maintenance_window(datetime.now(), start_min, end_min):
        _set_pending_kometa_start(command, session.get("config_name"), start_mode=start_mode)
        return jsonify({"status": "queued", "maintenance_window": window_str, "start_mode": start_mode}), 202

    ok, result = _launch_kometa_command(command, session.get("config_name"), start_mode=start_mode)
    if ok:
        return jsonify({"status": "Kometa started", "pid": result, "start_mode": start_mode})
    code = 500
    if isinstance(result, str) and result.lower().startswith("kometa.py not found"):
        code = 404
    return jsonify({"error": result}), code


@app.route("/stop-kometa", methods=["POST"])
def stop_kometa():
    _clear_pending_kometa_start()
    pid = helpers.get_kometa_pid()
    pid_file = helpers.get_kometa_pid_file()

    if not pid:
        procs = _find_running_kometa_processes()
        if not procs:
            return jsonify({"warning": "No active Kometa PID"}), 200
    else:
        procs = [_find_running_kometa_process()]
        procs = [p for p in procs if p is not None]

    try:
        if not procs:
            return jsonify({"warning": "No active Kometa process found."}), 200

        with RUN_CONTEXT_LOCK:
            RUN_CONTEXT["stop_requested_at"] = datetime.now(timezone.utc).isoformat()
            run_config_name = RUN_CONTEXT.get("config_name")

        not_kometa = []
        alive_after = []
        for proc in procs:
            # Ensure this really looks like a Kometa run before killing
            cmdline = " ".join(proc.cmdline() or [])
            if "kometa.py" not in cmdline:
                not_kometa.append(proc.pid)
                continue
            alive_after.extend(_stop_process_tree(proc))

        # Cleanup PID file regardless
        try:
            os.remove(pid_file)
        except Exception:
            pass
        _clear_process_metric_cache(pid, "kometa")
        _clear_run_context()
        try:
            _write_quickstart_stop_marker(helpers.get_kometa_root_path(), config_name=run_config_name, reason="user_stop")
        except Exception:
            pass

        if alive_after:
            alive_pids = ", ".join(str(p.pid) for p in alive_after if p is not None)
            return jsonify({"warning": f"Kometa stop requested, but some processes are still running: {alive_pids}"}), 200
        if not_kometa:
            return jsonify({"warning": f"Cleaned PID file. Non-Kometa PIDs detected: {', '.join(map(str, not_kometa))}"}), 200
        return jsonify({"success": True, "message": "Kometa stopped and cleaned up."}), 200

    except psutil.NoSuchProcess:
        # Process already gone; just clean up PID file
        try:
            os.remove(pid_file)
        except Exception:
            pass
        _clear_run_context()
        try:
            _write_quickstart_stop_marker(helpers.get_kometa_root_path(), config_name=session.get("config_name"), reason="process_missing")
        except Exception:
            pass
        return jsonify({"warning": "Process not found. Cleaned up PID file."}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to stop Kometa: {str(e)}"}), 500


@app.route("/kometa-status", methods=["GET"])
def kometa_status():
    try:
        _refresh_maintenance_window_availability(preserve_active_state=True)
    except Exception:
        pass
    pending = _peek_pending_kometa_start()
    pending_start = bool(pending)
    pending_requested_at = pending.get("requested_at") if pending else None
    pending_start_mode = _normalize_kometa_start_mode(pending.get("start_mode")) if pending else "current"
    pending_command = pending.get("command") if pending else None
    ctx = _get_run_context()
    pid = helpers.get_kometa_pid()
    if not pid:
        proc = _find_running_kometa_process()
        if proc:
            try:
                with open(helpers.get_kometa_pid_file(), "w", encoding="utf-8") as f:
                    f.write(str(proc.pid))
                pid = proc.pid
            except Exception:
                pid = None
    if not pid:
        try:
            _ingest_completed_live_logs("kometa")
        except Exception:
            pass
        _clear_run_context()
        with MAINTENANCE_STATE_LOCK:
            maintenance_active = MAINTENANCE_STATE["active"]
            maintenance_paused = MAINTENANCE_STATE["paused"]
            maintenance_window = MAINTENANCE_STATE["window"]
            maintenance_paused_since = MAINTENANCE_STATE["paused_since"]
            queued_started_at = MAINTENANCE_STATE["queued_started_at"]
            window_unavailable = MAINTENANCE_STATE["window_unavailable"]
            window_unavailable_since = MAINTENANCE_STATE["window_unavailable_since"]
        return jsonify(
            status="not started",
            maintenance_active=maintenance_active,
            maintenance_paused=maintenance_paused,
            maintenance_window=maintenance_window,
            maintenance_paused_since=maintenance_paused_since,
            queued_started_at=queued_started_at,
            window_unavailable=window_unavailable,
            window_unavailable_since=window_unavailable_since,
            pending_start=pending_start,
            pending_requested_at=pending_requested_at,
            pending_start_mode=pending_start_mode,
            pending_command=pending_command,
        )

    try:
        proc = psutil.Process(pid)
        # psutil can raise if finished between checks
        if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
            # Extra guard: ensure it's actually kometa.py
            cmdline = " ".join(proc.cmdline() or [])
            if "kometa.py" in cmdline:
                started_at_ts = proc.create_time()
                started_at = datetime.fromtimestamp(started_at_ts).isoformat()
                elapsed_seconds = max(0, int(time.time() - started_at_ts))
                cpu_percent = _calculate_process_cpu_percent(proc)
                io_stats = _calculate_process_io_stats(proc, "kometa") or {}
                mem_rss = proc.memory_info().rss
                try:
                    for child in proc.children(recursive=True):
                        try:
                            mem_rss += child.memory_info().rss
                        except Exception:
                            continue
                except Exception:
                    pass
                mem_rss_mb = mem_rss / (1024 * 1024)
                system_cpu_percent = _calculate_system_cpu_percent()
                vm = psutil.virtual_memory()
                system_mem_used_mb = (vm.total - vm.available) / (1024 * 1024)
                system_mem_total_mb = vm.total / (1024 * 1024)
                mem_percent = (mem_rss / vm.total) * 100.0 if vm.total else None
                with MAINTENANCE_STATE_LOCK:
                    maintenance_active = MAINTENANCE_STATE["active"]
                    maintenance_paused = MAINTENANCE_STATE["paused"]
                    maintenance_window = MAINTENANCE_STATE["window"]
                    maintenance_paused_since = MAINTENANCE_STATE["paused_since"]
                    queued_started_at = MAINTENANCE_STATE["queued_started_at"]
                    window_unavailable = MAINTENANCE_STATE["window_unavailable"]
                    window_unavailable_since = MAINTENANCE_STATE["window_unavailable_since"]
                return jsonify(
                    status="running",
                    pid=pid,
                    started_at=started_at,
                    started_at_ts=started_at_ts,
                    elapsed_seconds=elapsed_seconds,
                    cpu_percent=round(cpu_percent, 1) if cpu_percent is not None else None,
                    memory_rss_mb=round(mem_rss_mb, 1),
                    memory_percent=round(mem_percent, 2) if mem_percent is not None else None,
                    disk_read_mb=round(io_stats.get("disk_read_mb"), 1) if io_stats.get("disk_read_mb") is not None else None,
                    disk_write_mb=round(io_stats.get("disk_write_mb"), 1) if io_stats.get("disk_write_mb") is not None else None,
                    disk_read_rate_mb_s=round(io_stats.get("disk_read_rate_mb_s"), 2) if io_stats.get("disk_read_rate_mb_s") is not None else None,
                    disk_write_rate_mb_s=round(io_stats.get("disk_write_rate_mb_s"), 2) if io_stats.get("disk_write_rate_mb_s") is not None else None,
                    system_cpu_percent=round(system_cpu_percent, 1) if system_cpu_percent is not None else None,
                    system_memory_percent=round(vm.percent, 1),
                    system_memory_used_mb=round(system_mem_used_mb, 1),
                    system_memory_total_mb=round(system_mem_total_mb, 1),
                    maintenance_active=maintenance_active,
                    maintenance_paused=maintenance_paused,
                    maintenance_window=maintenance_window,
                    maintenance_paused_since=maintenance_paused_since,
                    queued_started_at=queued_started_at,
                    window_unavailable=window_unavailable,
                    window_unavailable_since=window_unavailable_since,
                    pending_start=pending_start,
                    pending_requested_at=pending_requested_at,
                    start_mode=_normalize_kometa_start_mode(ctx.get("start_mode")),
                    active_command=ctx.get("command"),
                )
        # If we're here, it likely ended; try to get a return code
        try:
            rc = proc.wait(timeout=0.1)
        except psutil.TimeoutExpired:
            rc = None
        finally:
            # Clean PID if no longer an active kometa proc
            try:
                os.remove(helpers.get_kometa_pid_file())
            except Exception:
                pass
        try:
            _ingest_completed_live_logs("kometa")
        except Exception:
            pass
        _clear_process_metric_cache(pid, "kometa")
        _clear_run_context()
        with MAINTENANCE_STATE_LOCK:
            maintenance_active = MAINTENANCE_STATE["active"]
            maintenance_paused = MAINTENANCE_STATE["paused"]
            maintenance_window = MAINTENANCE_STATE["window"]
            maintenance_paused_since = MAINTENANCE_STATE["paused_since"]
            queued_started_at = MAINTENANCE_STATE["queued_started_at"]
            window_unavailable = MAINTENANCE_STATE["window_unavailable"]
            window_unavailable_since = MAINTENANCE_STATE["window_unavailable_since"]
        return jsonify(
            status="done",
            return_code=rc if rc is not None else -1,
            maintenance_active=maintenance_active,
            maintenance_paused=maintenance_paused,
            maintenance_window=maintenance_window,
            maintenance_paused_since=maintenance_paused_since,
            queued_started_at=queued_started_at,
            window_unavailable=window_unavailable,
            window_unavailable_since=window_unavailable_since,
            pending_start=pending_start,
            pending_requested_at=pending_requested_at,
            start_mode=_normalize_kometa_start_mode(ctx.get("start_mode")),
            active_command=ctx.get("command"),
        )
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        _clear_process_metric_cache(pid, "kometa")
        try:
            os.remove(helpers.get_kometa_pid_file())
        except Exception:
            pass
        _clear_run_context()
        with MAINTENANCE_STATE_LOCK:
            maintenance_active = MAINTENANCE_STATE["active"]
            maintenance_paused = MAINTENANCE_STATE["paused"]
            maintenance_window = MAINTENANCE_STATE["window"]
            maintenance_paused_since = MAINTENANCE_STATE["paused_since"]
            queued_started_at = MAINTENANCE_STATE["queued_started_at"]
            window_unavailable = MAINTENANCE_STATE["window_unavailable"]
            window_unavailable_since = MAINTENANCE_STATE["window_unavailable_since"]
        return jsonify(
            status="not started",
            maintenance_active=maintenance_active,
            maintenance_paused=maintenance_paused,
            maintenance_window=maintenance_window,
            maintenance_paused_since=maintenance_paused_since,
            queued_started_at=queued_started_at,
            window_unavailable=window_unavailable,
            window_unavailable_since=window_unavailable_since,
            pending_start=pending_start,
            pending_requested_at=pending_requested_at,
            pending_start_mode=pending_start_mode,
            pending_command=pending_command,
        )


@app.route("/tail-log")
def tail_log():
    log_path = helpers.get_kometa_log_dir() / "meta.log"

    if not log_path.exists():
        return jsonify({"error": f"Log file not found at: {log_path}"}), 404

    try:
        from collections import deque

        size_param = request.args.get("size", "2000")
        download = request.args.get("download")
        stats_param = request.args.get("stats", "")
        include_stats = str(stats_param).lower() in ("1", "true", "yes", "on", "total")
        max_lines = None
        if size_param.lower() not in ("all", "full"):
            try:
                max_lines = max(1, min(int(size_param), 20000))
            except Exception:
                max_lines = 2000

        log_stats = None
        try:
            log_stats = log_path.stat()
        except Exception:
            log_stats = None

        if max_lines:
            with log_path.open("r", encoding="utf-8", errors="replace") as f:
                lines = deque(f, maxlen=max_lines)
            log_content = "".join(lines)
        else:
            log_content = log_path.read_text(encoding="utf-8", errors="replace")

        if download:
            return send_file(
                io.BytesIO(log_content.encode("utf-8")),
                mimetype="text/plain",
                as_attachment=True,
                download_name="meta.log",
            )

        def get_log_stats(path):
            try:
                stats = path.stat()
            except Exception:
                return None

            cached = LOG_STATS_CACHE
            if cached.get("mtime") == stats.st_mtime and cached.get("size") == stats.st_size:
                return cached.get("stats")

            counts = {
                "total_lines": 0,
                "cache": 0,
                "debug": 0,
                "info": 0,
                "warning": 0,
                "error": 0,
                "critical": 0,
                "trace": 0,
            }
            try:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        counts["total_lines"] += 1
                        upper = line.upper()
                        if "FROM CACHE" in upper:
                            counts["cache"] += 1
                        if "[DEBUG]" in upper:
                            counts["debug"] += 1
                        if "[INFO]" in upper:
                            counts["info"] += 1
                        if "[WARNING]" in upper:
                            counts["warning"] += 1
                        if "[ERROR]" in upper:
                            counts["error"] += 1
                        if "[CRITICAL]" in upper:
                            counts["critical"] += 1
                        if "TRACEBACK" in upper:
                            counts["trace"] += 1
            except Exception:
                return None

            LOG_STATS_CACHE.update({"mtime": stats.st_mtime, "size": stats.st_size, "stats": counts})
            return counts

        log_mtime = log_stats.st_mtime if log_stats else None
        log_age_seconds = None
        if log_mtime is not None:
            log_age_seconds = max(0, int(time.time() - log_mtime))

        kometa_started_at = None
        pid = helpers.get_kometa_pid()
        if pid:
            try:
                proc = psutil.Process(pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    cmdline = " ".join(proc.cmdline() or [])
                    if "kometa.py" in cmdline:
                        kometa_started_at = proc.create_time()
            except Exception:
                kometa_started_at = None

        log_is_stale = False
        if log_mtime is not None and kometa_started_at is not None:
            log_is_stale = log_mtime < (kometa_started_at - 30)

        response = {
            "log": log_content,
            "log_mtime": log_mtime,
            "log_age_seconds": log_age_seconds,
            "log_is_stale": log_is_stale,
            "log_path": str(log_path),
        }
        if include_stats:
            stats = get_log_stats(log_path)
            if stats:
                response["stats"] = stats

        return jsonify(response)
    except Exception as e:
        return jsonify({"error": f"Failed to read log: {str(e)}"}), 500


@app.route("/logscan/analyze", methods=["GET"])
def logscan_analyze():
    log_path = helpers.get_kometa_log_dir() / "meta.log"
    config_name = session.get("config_name")
    normalized_name = (config_name or "").strip().lower().replace(" ", "_") or "default"
    config_path = helpers.get_kometa_config_dir() / f"{normalized_name}_config.yml"

    if not log_path.exists():
        return jsonify({"error": f"Log file not found at: {log_path}"}), 404

    try:
        stats = log_path.stat()
    except Exception as e:
        return jsonify({"error": f"Failed to stat log: {str(e)}"}), 500

    cached = LOGSCAN_ANALYSIS_CACHE
    if cached.get("mtime") == stats.st_mtime and cached.get("size") == stats.st_size:
        data = cached.get("data") or {}
        data["cached"] = True
        return jsonify(data)

    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return jsonify({"error": f"Failed to read log: {str(e)}"}), 500

    analyzer = logscan.LogscanAnalyzer()
    result = analyzer.analyze_log_file(
        log_path,
        config_name=config_name,
        config_path=config_path,
    )
    summary = result.get("summary") if isinstance(result, dict) else None
    if summary:
        is_running = helpers.is_kometa_running()
        has_finish = bool(summary.get("finished_at"))
        run_complete = bool(summary.get("run_complete"))
        can_ingest = run_complete and has_finish and not is_running
        result["ingest_skipped"] = not can_ingest
        if can_ingest:
            if str(summary.get("tool_name") or "kometa").strip().lower() == "kometa":
                summary["progress_snapshot"] = _build_completed_log_progress_snapshot(
                    summary=summary,
                    content=content,
                    analyzer=analyzer,
                )
            ingest_cache = _load_logscan_ingest_cache()
            cache_logs = ingest_cache["logs"]
            cache_key = str(log_path.resolve())
            cached_entry = cache_logs.get(cache_key, {})
            cached_run_key = cached_entry.get("run_key")
            if not (cached_entry.get("run_complete") is True and cached_run_key == summary.get("run_key")):
                database.save_log_run(summary, recommendations=result.get("recommendations"))
            cache_logs[cache_key] = {
                "mtime": stats.st_mtime,
                "size": stats.st_size,
                "run_key": summary.get("run_key"),
                "run_complete": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            _save_logscan_ingest_cache(ingest_cache)
            try:
                _archive_finished_live_meta_log_if_idle(log_path.parent)
            except Exception:
                pass
            try:
                _archive_rotated_logs(log_path.parent)
            except Exception:
                pass
            if _logscan_needs_reingest(cache_logs, log_path.parent):
                _start_logscan_auto_reingest(log_path.parent)

    LOGSCAN_ANALYSIS_CACHE.update({"mtime": stats.st_mtime, "size": stats.st_size, "data": result})
    result["cached"] = False
    return jsonify(result)


def _load_progress_config(config_path=None):
    if not config_path:
        return None
    try:
        yaml_parser = YAML(typ="safe", pure=True)
        with Path(config_path).open("r", encoding="utf-8", errors="ignore") as handle:
            return yaml_parser.load(handle) or {}
    except Exception:
        return None


def _normalize_run_order_value(value):
    lowered = str(value or "").strip().lower()
    if not lowered:
        return None
    if lowered.startswith("operation"):
        return "operations"
    if lowered.startswith("overlay"):
        return "overlays"
    if lowered.startswith("collection"):
        return "collections"
    if lowered.startswith("metadata"):
        return "metadata"
    return None


def _get_progress_run_order(config_data=None):
    if not isinstance(config_data, dict):
        return []
    settings = config_data.get("settings") if isinstance(config_data.get("settings"), dict) else {}
    run_order = settings.get("run_order") if isinstance(settings, dict) else None
    if not isinstance(run_order, list):
        return []
    normalized = []
    for item in run_order:
        key = _normalize_run_order_value(item)
        if key and key not in normalized:
            normalized.append(key)
    return normalized


def _get_progress_library_list(selected_libraries=None, config_path=None, config_data=None, config_name=None):
    library_settings = {}
    if has_request_context():
        settings = persistence.retrieve_settings("025-libraries")
        library_settings = settings.get("libraries", {}) if isinstance(settings, dict) else {}
    elif config_name:
        try:
            _validated, _user_entered, stored = database.retrieve_section_data(config_name, "libraries")
            if not isinstance(stored, dict):
                _validated, _user_entered, stored = database.retrieve_section_data(config_name, "025-libraries")
            if isinstance(stored, dict):
                if isinstance(stored.get("libraries"), dict):
                    library_settings = stored.get("libraries", {})
                else:
                    library_settings = stored
        except Exception:
            library_settings = {}
    libraries = []
    type_by_name = {}
    if isinstance(library_settings, dict):
        for key, value in library_settings.items():
            if not value:
                continue
            if key.startswith("mov-library_") and key.endswith("-library"):
                type_by_name[value] = "movie"
            elif key.startswith("sho-library_") and key.endswith("-library"):
                type_by_name[value] = "show"
    parsed = config_data if isinstance(config_data, dict) else _load_progress_config(config_path)
    if isinstance(parsed, dict):
        lib_section = parsed.get("libraries")
        if isinstance(lib_section, dict):
            for lib_name in lib_section.keys():
                if lib_name:
                    libraries.append({"name": lib_name, "type": type_by_name.get(lib_name)})
    if not libraries:
        for name, lib_type in type_by_name.items():
            libraries.append({"name": name, "type": lib_type})
    if selected_libraries:
        existing = {lib["name"] for lib in libraries}
        for name in selected_libraries:
            if name and name not in existing:
                libraries.append({"name": name, "type": None})
                existing.add(name)
    return libraries


@app.route("/logscan/progress", methods=["GET"])
def logscan_progress():
    kometa_root = helpers.get_kometa_root_path()
    log_path = helpers.get_kometa_log_dir() / "meta.log"
    sidecar_path = _get_kometa_maintenance_sidecar_path(kometa_root)

    if not log_path.exists():
        return jsonify({"error": f"Log file not found at: {log_path}"}), 404

    try:
        from collections import deque
        from copy import deepcopy

        size_arg = request.args.get("size")
        size_param = size_arg if size_arg is not None else "4000"
        max_lines = None
        if size_param.lower() not in ("all", "full"):
            try:
                max_lines = max(1, min(int(size_param), 20000))
            except Exception:
                max_lines = 4000
        force_full_read = max_lines is None

        log_stats = None
        try:
            log_stats = log_path.stat()
        except Exception:
            log_stats = None
        sidecar_stats = None
        try:
            if sidecar_path.exists():
                sidecar_stats = sidecar_path.stat()
        except Exception:
            sidecar_stats = None

        cached = LOGSCAN_PROGRESS_CACHE

        def _cache_matches_progress_signature():
            if not log_stats:
                return False
            if cached.get("mtime") != log_stats.st_mtime or cached.get("size") != log_stats.st_size:
                return False
            cached_sidecar_mtime = cached.get("sidecar_mtime")
            cached_sidecar_size = cached.get("sidecar_size")
            current_sidecar_mtime = sidecar_stats.st_mtime if sidecar_stats else None
            current_sidecar_size = sidecar_stats.st_size if sidecar_stats else None
            return cached_sidecar_mtime == current_sidecar_mtime and cached_sidecar_size == current_sidecar_size

        def _read_progress_log_content():
            if force_full_read:
                return _read_logscan_text(log_path)
            with log_path.open("r", encoding="utf-8", errors="replace") as handle:
                lines = deque(handle, maxlen=max_lines)
            content = "".join(lines)
            try:
                if sidecar_path.exists() and sidecar_path.is_file():
                    sidecar_content = sidecar_path.read_text(encoding="utf-8", errors="replace").strip()
                    if sidecar_content:
                        content = f"{content.rstrip()}\n{sidecar_content}\n"
            except Exception:
                pass
            return content

        def _coerce_progress_datetime(value):
            if not value:
                return None
            try:
                ts = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if ts.tzinfo is not None:
                    ts = ts.astimezone().replace(tzinfo=None)
                return ts
            except Exception:
                return None

        def refresh_live_progress_elapsed(data, running, started_at):
            if not isinstance(data, dict) or not running:
                return data
            data = deepcopy(data)
            now_ts = datetime.now()

            prep_locked = data.get("preparation_seconds")
            if not isinstance(prep_locked, (int, float)):
                prep_start = _coerce_progress_datetime(started_at)
                if prep_start and now_ts > prep_start:
                    data["preparation_elapsed_seconds"] = max(0, int((now_ts - prep_start).total_seconds()))

            current_library = data.get("current_library")
            phase_current = data.get("phase_current")
            phase_starts = data.get("phase_starts") or {}
            if current_library and phase_current and isinstance(phase_starts, dict):
                phase_key = f"{current_library}||{phase_current}"
                start_ts = _coerce_progress_datetime(phase_starts.get(phase_key))
                if start_ts:
                    base = 0
                    for entry in data.get("libraries") or []:
                        if entry.get("name") == current_library:
                            durations = entry.get("durations") or {}
                            if isinstance(durations.get(phase_current), (int, float)):
                                base = int(durations.get(phase_current) or 0)
                            break
                    data["current_phase_elapsed_seconds"] = base + max(0, int((now_ts - start_ts).total_seconds()))

            if data.get("playlist_running"):
                playlist_started_at = _coerce_progress_datetime(data.get("playlist_started_at"))
                if playlist_started_at:
                    playlist_total = data.get("playlist_total_seconds")
                    base = int(playlist_total or 0) if isinstance(playlist_total, (int, float)) else 0
                    data["playlist_elapsed_seconds"] = base + max(0, int((now_ts - playlist_started_at).total_seconds()))

            return data

        def normalize_progress_for_stopped(data, running, stopped_requested):
            if not isinstance(data, dict) or running:
                return data
            data = deepcopy(data)
            stopped_library = data.get("current_library")
            data["current_library"] = None
            data["phase_current"] = None
            libraries = data.get("libraries")
            if isinstance(libraries, list):
                for entry in libraries:
                    status = entry.get("status")
                    name = entry.get("name")
                    if status == "In progress":
                        if stopped_requested:
                            entry["status"] = "Stopped"
                    elif stopped_library and name == stopped_library and status not in ("Done", "Skipped"):
                        if stopped_requested:
                            entry["status"] = "Stopped"
            return data

        ctx = _get_run_context()
        selected = ctx.get("selected_libraries")
        started_at = ctx.get("started_at")
        config_path = ctx.get("config_path")
        run_mode = ctx.get("run_mode") or "all"
        running = helpers.is_kometa_running()
        stopped_requested = bool(ctx.get("stop_requested_at"))
        cached_data = LOGSCAN_PROGRESS_CACHE.get("data")
        cache_matches_run = bool(cached_data and cached_data.get("run_started_at") == started_at)

        # Seed progress from the full log when no explicit size was requested and
        # the current run has no matching cached progress state yet. After the
        # cache is warm, later polls can safely use the faster tail parse.
        if size_arg is None and not cache_matches_run:
            max_lines = None
            force_full_read = True

        if not force_full_read and _cache_matches_progress_signature():
            data = cached.get("data") or {}
            data = refresh_live_progress_elapsed(data, running, started_at)
            data = normalize_progress_for_stopped(data, running, stopped_requested)
            return jsonify(data)

        if cached_data and cached_data.get("run_started_at") != started_at:
            LOGSCAN_PROGRESS_CACHE.update({"mtime": None, "size": None, "sidecar_mtime": None, "sidecar_size": None, "data": None})
        analyzer = logscan.LogscanAnalyzer()
        config_data = _load_progress_config(config_path)
        log_content = _read_progress_log_content()
        progress = analyzer.extract_progress(
            log_content,
            library_list=_get_progress_library_list(
                selected_libraries=selected,
                config_path=config_path,
                config_data=config_data,
            ),
            selected_libraries=selected,
            previous=LOGSCAN_PROGRESS_CACHE.get("data"),
            run_started_at=started_at,
            now_ts=datetime.now(timezone.utc),
            is_running=running,
        )
        phase_order = _get_progress_run_order(config_data=config_data)
        allowed_phases = phase_order or ["operations", "metadata", "collections", "overlays"]
        playlists_configured = bool(config_data.get("playlists")) if isinstance(config_data, dict) else False
        if run_mode in ("collections", "overlays", "operations", "metadata", "playlists"):
            allowed_phases = [run_mode]
            progress["phase_current"] = run_mode
            progress["phases_completed"] = []
        elif "playlists" not in allowed_phases:
            allowed_phases = allowed_phases + ["playlists"]
        progress["allowed_phases"] = allowed_phases
        progress["phase_order"] = allowed_phases
        progress["playlists_configured"] = playlists_configured
        maintenance_summary = analyzer.extract_maintenance_summary(log_content)
        progress["maintenance_summary"] = maintenance_summary if isinstance(maintenance_summary, dict) else {}
        progress["maintenance_had_pause"] = bool((progress.get("maintenance_summary") or {}).get("had_pause"))
        progress = normalize_progress_for_stopped(progress, running, stopped_requested)
        if log_stats:
            progress["last_log_at"] = datetime.fromtimestamp(log_stats.st_mtime, tz=timezone.utc).isoformat()
            progress["run_started_at"] = started_at
            LOGSCAN_PROGRESS_CACHE.update(
                {
                    "mtime": log_stats.st_mtime,
                    "size": log_stats.st_size,
                    "sidecar_mtime": sidecar_stats.st_mtime if sidecar_stats else None,
                    "sidecar_size": sidecar_stats.st_size if sidecar_stats else None,
                    "data": progress,
                }
            )
        return jsonify(progress)
    except Exception as e:
        return jsonify({"error": f"Failed to analyze log progress: {str(e)}"}), 500


@app.route("/logscan/trends", methods=["GET"])
def logscan_trends():
    try:
        _ingest_completed_live_logs("imagemaid")
        _archive_finished_live_meta_log_if_idle()
    except Exception:
        pass
    raw_limit = str(request.args.get("limit", "50")).strip().lower()
    if raw_limit == "all":
        limit = None
    else:
        try:
            limit = int(raw_limit)
        except Exception:
            limit = 50
        limit = max(1, min(limit, 500))
    total_runs = database.get_log_runs_count()
    ingest_health = _logscan_ingest_health()
    resolution_context = _build_logscan_resolution_context()
    runs = _annotate_logscan_runs(database.get_log_runs(limit=limit), context=resolution_context)
    incomplete_runs = _annotate_logscan_runs(_get_logscan_incomplete_runs(limit=limit), context=resolution_context)
    all_runs = database.get_log_runs(limit=None) if total_runs else []
    all_incomplete_runs = _get_logscan_incomplete_runs(limit=None)
    return jsonify(
        {
            "runs": runs,
            "incomplete_runs": incomplete_runs,
            "total_runs": total_runs,
            "total_incomplete_runs": len(all_incomplete_runs),
            "ingest_health": ingest_health,
            "archive_storage": _get_logscan_archive_storage_summary(
                all_runs=all_runs,
                incomplete_runs=all_incomplete_runs,
                context=resolution_context,
            ),
        }
    )


@app.route("/logscan/trends/recommendations", methods=["GET"])
def logscan_trends_recommendations():
    run_key = request.args.get("run_key")
    if not run_key:
        return jsonify({"error": "run_key required"}), 400
    recommendations = database.get_log_run_recommendations(run_key)
    run_record = database.get_log_run(run_key)
    if not recommendations:
        incomplete_run = _get_logscan_incomplete_run(run_key)
        if incomplete_run:
            recommendations = incomplete_run.get("recommendations") if isinstance(incomplete_run.get("recommendations"), list) else []
            if not run_record:
                run_record = incomplete_run
    return jsonify({"run_key": run_key, "recommendations": recommendations, "run": run_record})


@app.route("/logscan/trends/reset", methods=["POST"])
def logscan_trends_reset():
    database.clear_log_runs()
    _clear_logscan_ingest_cache()
    try:
        missing_log = _get_logscan_cache_dir() / "meta_people_missing.log"
        if missing_log.exists():
            missing_log.unlink()
    except Exception:
        pass
    return jsonify({"success": True})


def _logscan_reingest_snapshot():
    with logscan_reingest_lock:
        active = _get_active_background_job("logscan_reingest")
        if active:
            return active
        last_job_id = logscan_reingest_state.get("job_id")
        if last_job_id:
            payload = _get_background_job(last_job_id)
            if payload:
                return payload
        return dict(logscan_reingest_state)


def _update_logscan_reingest_state(**updates):
    with logscan_reingest_lock:
        job_id = str(updates.get("job_id") or logscan_reingest_state.get("job_id") or "").strip() or None
        status = str(updates.get("status") or "").strip().lower()
        create_if_missing = bool(job_id or status in {"queued", "running", "complete", "error"})
        payload = _ensure_background_job(
            "logscan_reingest",
            job_id=job_id,
            create_if_missing=create_if_missing,
            trigger=str(updates.get("trigger") or "manual").strip() or "manual",
            phase=str(updates.get("phase") or "queued").strip() or "queued",
            status=status or "running",
            target_page=JOB_TARGET_PAGES.get("logscan_reingest"),
        )
        if payload:
            next_job_id = payload.get("job_id")
            shared_updates = dict(updates)
            shared_updates.pop("job_id", None)
            payload = _update_background_job(next_job_id, **shared_updates) or payload
            logscan_reingest_state.clear()
            logscan_reingest_state.update(payload)
            return
        logscan_reingest_state.update(updates)


def _reset_logscan_reingest_state():
    with logscan_reingest_lock:
        job_id = logscan_reingest_state.get("job_id")
        _clear_active_background_job("logscan_reingest", job_id=job_id)
        logscan_reingest_state.clear()
        logscan_reingest_state.update(
            {
                "status": "idle",
                "job_id": None,
                "trigger": None,
                "migration_level": None,
            }
        )


def _iter_logscan_text_lines(path, encoding="utf-8", errors="replace"):
    path = Path(path)
    if _is_logscan_gzip_path(path):
        with gzip.open(path, "rt", encoding=encoding, errors=errors) as handle:
            for line in handle:
                yield line
        return
    with path.open("r", encoding=encoding, errors=errors) as handle:
        for line in handle:
            yield line


def _parse_imagemaid_runtime_seconds(runtime_text):
    text = str(runtime_text or "").strip()
    if not text:
        return None
    analyzer = logscan.LogscanAnalyzer()
    try:
        delta = analyzer._parse_run_time_from_line(f"Run Time: {text}")
    except Exception:
        delta = None
    if delta is None:
        return None
    return int(delta.total_seconds())


def _extract_imagemaid_error_lines(lines):
    errors = []
    in_error_report = False
    for raw_line in lines:
        line = str(raw_line or "")
        if "Error Report" in line:
            in_error_report = True
            continue
        if in_error_report and "ImageMaid Summary" in line:
            break
        if not in_error_report:
            continue
        stripped = line.strip().strip("|").strip()
        if not stripped or stripped.startswith("="):
            continue
        if "Generic Errors:" in stripped:
            continue
        if "Error" not in stripped:
            continue
        errors.append(stripped)
    return errors


def _parse_imagemaid_bytes(text):
    value = str(text or "").strip()
    if not value:
        return None
    match = re.match(r"^([\d.]+)\s*([A-Za-z]+)$", value, re.IGNORECASE)
    if match:
        try:
            number = float(match.group(1))
        except (TypeError, ValueError):
            return None
        unit = str(match.group(2) or "").strip().lower().rstrip("s")
        multipliers = {
            "byte": 1,
            "b": 1,
            "kb": 1024,
            "mb": 1024**2,
            "gb": 1024**3,
            "tb": 1024**4,
        }
        multiplier = multipliers.get(unit)
        if multiplier is None:
            return None
        try:
            return int(number * multiplier)
        except (TypeError, ValueError):
            return None
    return None


def _normalize_imagemaid_snapshot_path(value):
    text = str(value or "").strip().strip('"').strip("'")
    if not text:
        return ""
    try:
        return os.path.normcase(os.path.normpath(text))
    except Exception:
        return text.lower()


def _parse_imagemaid_command_snapshot(run_command_text, fallback_mode=None):
    snapshot = {}
    mode = str(fallback_mode or "").strip().lower()
    if mode:
        snapshot["mode"] = mode

    command = str(run_command_text or "").strip()
    if not command:
        return snapshot

    try:
        parts = shlex.split(command, posix=False)
    except Exception:
        parts = command.split()

    flag_map = {
        "--photo-transcoder": "photo_transcoder",
        "--empty-trash": "empty_trash",
        "--clean-bundles": "clean_bundles",
        "--optimize-db": "optimize_db",
        "--local": "local_db",
        "--existing": "use_existing",
        "--ignore-running": "ignore_running",
        "--trace": "trace",
        "--log-requests": "log_requests",
        "--no-verify-ssl": "no_verify_ssl",
        "--overlays-only": "overlays_only",
    }
    value_map = {
        "--plex": "plex_path",
        "--mode": "mode",
        "--timeout": "timeout",
        "--sleep": "sleep",
    }

    idx = 0
    while idx < len(parts):
        part = str(parts[idx] or "").strip()
        if not part:
            idx += 1
            continue

        matched = False
        for flag, key in flag_map.items():
            if part == flag:
                snapshot[key] = True
                matched = True
                break
        if matched:
            idx += 1
            continue

        for flag, key in value_map.items():
            if part == flag and idx + 1 < len(parts):
                raw_value = str(parts[idx + 1] or "").strip()
                if key == "plex_path":
                    snapshot[key] = _normalize_imagemaid_snapshot_path(raw_value)
                elif key in {"timeout", "sleep"}:
                    snapshot[key] = str(raw_value).strip()
                else:
                    snapshot[key] = str(raw_value).strip().lower()
                idx += 2
                matched = True
                break
            if part.startswith(f"{flag}="):
                raw_value = part.split("=", 1)[1].strip()
                if key == "plex_path":
                    snapshot[key] = _normalize_imagemaid_snapshot_path(raw_value)
                elif key in {"timeout", "sleep"}:
                    snapshot[key] = str(raw_value).strip()
                else:
                    snapshot[key] = str(raw_value).strip().lower()
                idx += 1
                matched = True
                break
        if matched:
            continue

        idx += 1

    return snapshot


def _build_imagemaid_section_snapshot(section_data):
    section = section_data if isinstance(section_data, dict) else {}
    snapshot = {}

    mode = str(section.get("mode") or "").strip().lower()
    if mode:
        snapshot["mode"] = mode

    plex_path = _normalize_imagemaid_snapshot_path(section.get("plex_path"))
    if plex_path:
        snapshot["plex_path"] = plex_path

    for key in (
        "photo_transcoder",
        "empty_trash",
        "clean_bundles",
        "optimize_db",
        "local_db",
        "use_existing",
        "ignore_running",
        "trace",
        "log_requests",
        "no_verify_ssl",
        "overlays_only",
    ):
        snapshot[key] = helpers.booler(section.get(key))

    for key in ("timeout", "sleep"):
        value = section.get(key)
        if value not in [None, ""]:
            snapshot[key] = str(value).strip()

    return snapshot


def _infer_imagemaid_config_name(mode=None, run_command_text=None):
    command_snapshot = _parse_imagemaid_command_snapshot(run_command_text, fallback_mode=mode)
    relevant_keys = [key for key, value in command_snapshot.items() if value not in [None, ""]]
    discriminators = [key for key in relevant_keys if key != "mode"]
    if not discriminators:
        return None

    matches = []
    for config_name in database.get_unique_config_names() or []:
        try:
            _validated, _user_entered, stored = database.retrieve_section_data(config_name, "imagemaid")
        except Exception:
            continue
        if not isinstance(stored, dict):
            continue
        section = stored.get("imagemaid") if isinstance(stored.get("imagemaid"), dict) else stored
        if not isinstance(section, dict) or not section:
            continue
        section_snapshot = _build_imagemaid_section_snapshot(section)

        score = 0
        matched = True
        for key in relevant_keys:
            expected = command_snapshot.get(key)
            actual = section_snapshot.get(key)
            if actual != expected:
                matched = False
                break
            score += 5 if key == "plex_path" else 1
        if matched:
            matches.append((score, str(config_name)))

    if not matches:
        return None
    matches.sort(key=lambda item: (-item[0], item[1]))
    if len(matches) == 1:
        return matches[0][1]
    if matches[0][0] > matches[1][0]:
        return matches[0][1]
    return None


def _resolve_imagemaid_run_config_name(run_record):
    if not isinstance(run_record, dict):
        return "unknown"
    tool_name = str(run_record.get("tool_name") or "").strip().lower()
    config_name = str(run_record.get("config_name") or "").strip()
    if tool_name != "imagemaid":
        return config_name
    if config_name and config_name.lower() not in {"imagemaid", "unknown"}:
        return config_name
    inferred = _infer_imagemaid_config_name(
        mode=run_record.get("imagemaid_mode"),
        run_command_text=run_record.get("run_command"),
    )
    return inferred or "unknown"


def _build_imagemaid_recommendations(summary, error_lines=None, completion_reason=None):
    recommendations = []
    completion_reason = str(completion_reason or "").strip().lower()
    if completion_reason == "user_stop":
        recommendations.append(
            {
                "first_line": "ImageMaid run stopped by user",
                "message": "Quickstart recorded an explicit stop request for this ImageMaid run.",
            }
        )
    elif completion_reason == "maintenance_blocked_start":
        window = ""
        maintenance_summary = summary.get("maintenance_summary") if isinstance(summary, dict) else {}
        if isinstance(maintenance_summary, dict):
            events = maintenance_summary.get("events")
            if isinstance(events, list) and events:
                window = str((events[0] or {}).get("window") or "").strip()
        suffix = f" during the Plex maintenance window ({window})" if window else " during the Plex maintenance window"
        recommendations.append(
            {
                "first_line": "ImageMaid start blocked by Plex maintenance",
                "message": f"Quickstart did not start ImageMaid{suffix}.",
            }
        )
    elif completion_reason and completion_reason != "completed":
        recommendations.append(
            {
                "first_line": "ImageMaid run appears incomplete",
                "message": f"Quickstart detected an incomplete ImageMaid run with reason: {completion_reason}.",
            }
        )
    if error_lines:
        recommendations.append(
            {
                "first_line": "ImageMaid reported errors",
                "message": "\n".join(error_lines[:8]),
            }
        )
    return recommendations


def _analyze_imagemaid_log_content(content, log_path=None):
    if not content:
        return None
    path = Path(log_path) if log_path else None
    try:
        stats = path.stat() if path and path.exists() else None
    except Exception:
        stats = None
    lines = content.splitlines()
    run_marker_pattern = re.compile(
        r"\[Quickstart\]\s+Run marker:\s+started=([^\s]+)\s+config=([^\s]+).*?\btool=imagemaid\b(?:\s+mode=([^\s]+))?",
        re.IGNORECASE,
    )
    stop_pattern = re.compile(
        r"\[Quickstart\]\s+Run event:\s+event=stopped\s+at=([^\s]+)\s+config=([^\s]+).*?\btool=imagemaid\b(?:\s+mode=([^\s]+))?(?:\s+reason=([^\s]+))?",
        re.IGNORECASE,
    )
    blocked_pattern = re.compile(
        r"\[Quickstart\]\s+Maintenance marker:\s+event=blocked_start\s+at=([^\s]+)\s+local_at=[^\s]+\s+config=([^\s]+).*?\btool=imagemaid\b(?:\s+mode=([^\s]+))?.*?(?:\s+window=([^\s]+))?",
        re.IGNORECASE,
    )
    timestamp_pattern = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),")
    total_runtime_pattern = re.compile(r"\|\s*Total Runtime\s*\|\s*(.*?)\s*\|?$", re.IGNORECASE)
    summary_header_pattern = re.compile(r"\|\s*=+\s*(.*?)\s*=+\s*\|?$")
    summary_runtime_row_pattern = re.compile(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|?$")

    started_at = None
    config_name = ""
    mode = ""
    stop_at = None
    stop_reason = ""
    blocked_at = None
    blocked_window = ""
    first_timestamp = None
    finished_at = None
    finished_seen = False
    run_time_seconds = None
    cache_count = 0
    debug_count = 0
    info_count = 0
    warning_count = 0
    error_count = 0
    critical_count = 0
    trace_count = 0
    quickstart_run_marker = False
    local_version = ""
    run_command_text = ""
    photo_scan_runtime = None
    photo_remove_runtime = None
    photo_found_files = 0
    photo_removed_files = 0
    photo_recovered_bytes = 0
    restore_scan_runtime = None
    restore_action_runtime = None
    restore_found_files = 0
    restore_removed_files = 0
    restore_recovered_bytes = 0
    generic_error_lines = []
    database_downloaded_new = False
    database_download_failed = False
    database_section_seen = False
    photo_transcoder_enabled = False
    empty_trash_enabled = False
    clean_bundles_enabled = False
    optimize_db_enabled = False
    local_db_enabled = False
    use_existing_enabled = False
    no_verify_ssl_enabled = False
    overlays_only_enabled = False
    current_runtime_section = ""
    summary_section = ""
    summary_section_runtimes = {}
    operation_started = {
        "empty_trash": False,
        "clean_bundles": False,
        "optimize_db": False,
    }

    for line in lines:
        timestamp_match = timestamp_pattern.search(line)
        if timestamp_match and not first_timestamp:
            first_timestamp = timestamp_match.group(1)
        if "[CACHE]" in line:
            cache_count += 1
        if "[DEBUG]" in line:
            debug_count += 1
        if "[INFO]" in line:
            info_count += 1
        if "[WARNING]" in line:
            warning_count += 1
        if "[ERROR]" in line:
            error_count += 1
        if "[CRITICAL]" in line:
            critical_count += 1
        if "Traceback" in line:
            trace_count += 1
        stripped_line = line.strip().strip("|").strip()
        if stripped_line and "Error:" in stripped_line and stripped_line not in generic_error_lines:
            generic_error_lines.append(stripped_line)

        if not quickstart_run_marker:
            marker_match = run_marker_pattern.search(line)
            if marker_match:
                started_at = marker_match.group(1)
                config_name = marker_match.group(2) or config_name
                mode = marker_match.group(3) or mode
                quickstart_run_marker = True

        stop_match = stop_pattern.search(line)
        if stop_match:
            stop_at = stop_match.group(1)
            config_name = stop_match.group(2) or config_name
            mode = stop_match.group(3) or mode
            stop_reason = stop_match.group(4) or stop_reason or "user_stop"

        blocked_match = blocked_pattern.search(line)
        if blocked_match:
            blocked_at = blocked_match.group(1)
            config_name = blocked_match.group(2) or config_name
            mode = blocked_match.group(3) or mode
            blocked_window = blocked_match.group(4) or blocked_window

        if "ImageMaid Finished" in line:
            finished_seen = True
            if timestamp_match:
                finished_at = timestamp_match.group(1)

        summary_header_match = summary_header_pattern.search(line)
        if summary_header_match:
            header_text = str(summary_header_match.group(1) or "").strip().lower()
            if header_text in {
                "database",
                "reporting bloat images",
                "remove phototranscoder images",
                "remove imagemaid restore bloat images",
                "empty trash plex operation",
                "clean bundles plex operation",
                "optimize db plex operation",
                "imagemaid summary",
            }:
                summary_section = header_text

        summary_runtime_match = summary_runtime_row_pattern.search(line)
        if summary_runtime_match:
            summary_label = str(summary_runtime_match.group(1) or "").strip().lower()
            parsed_summary_runtime = _parse_imagemaid_runtime_seconds(summary_runtime_match.group(2))
            if parsed_summary_runtime is not None:
                if summary_section == "database":
                    if summary_label == "downloaded":
                        summary_section_runtimes["database_download"] = parsed_summary_runtime
                    elif summary_label == "query":
                        summary_section_runtimes["database_query"] = parsed_summary_runtime
                elif summary_section == "reporting bloat images":
                    if summary_label == "scan time":
                        summary_section_runtimes["report_bloat_scan"] = parsed_summary_runtime
                    elif summary_label == "report time":
                        summary_section_runtimes["report_bloat_action"] = parsed_summary_runtime
                elif summary_section == "remove phototranscoder images":
                    if summary_label == "scan time":
                        summary_section_runtimes["photo_transcoder_scan"] = parsed_summary_runtime
                    elif summary_label == "remove time":
                        summary_section_runtimes["photo_transcoder_remove"] = parsed_summary_runtime
                elif summary_section == "remove imagemaid restore bloat images":
                    if summary_label == "scan time":
                        summary_section_runtimes["restore_dir_scan"] = parsed_summary_runtime
                    elif summary_label == "remove time":
                        summary_section_runtimes["restore_dir_action"] = parsed_summary_runtime
                elif summary_section == "empty trash plex operation" and summary_label == "runtime":
                    summary_section_runtimes["empty_trash_action"] = parsed_summary_runtime
                elif summary_section == "clean bundles plex operation" and summary_label == "runtime":
                    summary_section_runtimes["clean_bundles_action"] = parsed_summary_runtime
                elif summary_section == "optimize db plex operation" and summary_label == "runtime":
                    summary_section_runtimes["optimize_db_action"] = parsed_summary_runtime

        runtime_match = total_runtime_pattern.search(line)
        if runtime_match:
            parsed_runtime = _parse_imagemaid_runtime_seconds(runtime_match.group(1))
            if parsed_runtime is not None:
                run_time_seconds = parsed_runtime

        if not mode and "Running in " in line and " Mode" in line:
            mode_match = re.search(r"Running in\s+([A-Za-z]+)\s+Mode", line, re.IGNORECASE)
            if mode_match:
                mode = (mode_match.group(1) or "").strip().lower()

        version_match = re.search(r"\|\s*Version:\s*([^\s|]+)", line, re.IGNORECASE)
        if version_match and not local_version:
            local_version = str(version_match.group(1) or "").strip()

        command_match = re.search(r"\|\s*Run Command:\s*(.*?)\s*\|?$", line, re.IGNORECASE)
        if command_match and not run_command_text:
            run_command_text = str(command_match.group(1) or "").strip()

        if "Downloading Database via the Plex API" in line:
            database_section_seen = True
            current_runtime_section = "database_download"
        if "Downloaded New Database" in line:
            database_downloaded_new = True
        if "Database File Could not Downloaded" in line:
            database_download_failed = True
        if "Database Opened Querying For In-Use Images" in line or "Querying For In-Use Images" in line:
            current_runtime_section = "database_query"

        if "PhotoTranscoder set to True" in line:
            photo_transcoder_enabled = True

        if "Empty Trash Plex Operation Started" in line:
            operation_started["empty_trash"] = True
            empty_trash_enabled = True
        if "Clean Bundles Plex Operation Started" in line:
            operation_started["clean_bundles"] = True
            clean_bundles_enabled = True
        if "Optimize DB Plex Operation Started" in line:
            operation_started["optimize_db"] = True
            optimize_db_enabled = True

        if "Scanning ImageMaid Restore for Bloat Images to Remove" in line:
            current_runtime_section = "restore_scan"
        elif "Removing ImageMaid Restore Bloat Images" in line or ("Removing Complete:" in line and "ImageMaid Restore Bloat Images" in line):
            current_runtime_section = "restore_action"
        elif "Scanning Metadata Directory For Bloat Images" in line:
            current_runtime_section = "report_bloat_scan"
        elif "Reporting Bloat Images" in line or ("Reporting Complete:" in line and "Bloat Images" in line):
            current_runtime_section = "report_bloat_action"
        elif "Scanning for PhotoTranscoder Images" in line or ("Scanning Complete:" in line and "PhotoTranscoder Images" in line):
            current_runtime_section = "photo_scan"
        elif "Removing PhotoTranscoder Images" in line or ("Remove Complete:" in line and "PhotoTranscoder Images" in line):
            current_runtime_section = "photo_remove"
        elif "Empty Trash Plex Operation Started" in line:
            current_runtime_section = "empty_trash_action"
        elif "Clean Bundles Plex Operation Started" in line:
            current_runtime_section = "clean_bundles_action"
        elif "Optimize DB Plex Operation Started" in line:
            current_runtime_section = "optimize_db_action"

        restore_found_match = re.search(
            r"Found\s+(\d+)\s+Bloat Images in the ImageMaid Directory to Remove",
            line,
            re.IGNORECASE,
        )
        if restore_found_match:
            try:
                restore_found_files = int(restore_found_match.group(1))
            except (TypeError, ValueError):
                pass
        restore_removed_match = re.search(
            r"Removed\s+(\d+)\s+ImageMaid Restore Bloat Images",
            line,
            re.IGNORECASE,
        )
        if restore_removed_match:
            try:
                restore_removed_files = int(restore_removed_match.group(1))
            except (TypeError, ValueError):
                pass
        found_match = re.search(r"Found\s+(\d+)\s+PhotoTranscoder Images to Remove", line, re.IGNORECASE)
        if found_match:
            try:
                photo_found_files = int(found_match.group(1))
            except (TypeError, ValueError):
                pass
        removed_match = re.search(r"Removed\s+(\d+)\s+PhotoTranscoder Images", line, re.IGNORECASE)
        if removed_match:
            try:
                photo_removed_files = int(removed_match.group(1))
            except (TypeError, ValueError):
                pass
        bytes_match = re.search(r"Space Recovered:\s*(.*?)\s*\|?$", line, re.IGNORECASE)
        if bytes_match:
            parsed_bytes = _parse_imagemaid_bytes(bytes_match.group(1))
            if parsed_bytes is not None:
                if current_runtime_section in {"restore_scan", "restore_action"}:
                    restore_recovered_bytes = parsed_bytes
                elif current_runtime_section in {"photo_scan", "photo_remove"}:
                    photo_recovered_bytes = parsed_bytes
        runtime_line_match = re.search(r"\|\s*Runtime:\s*(.*?)\s*\|?$", line, re.IGNORECASE)
        if runtime_line_match:
            parsed_runtime = _parse_imagemaid_runtime_seconds(runtime_line_match.group(1))
            if parsed_runtime is not None:
                if current_runtime_section == "database_download":
                    summary_section_runtimes.setdefault("database_download", parsed_runtime)
                elif current_runtime_section == "database_query":
                    summary_section_runtimes.setdefault("database_query", parsed_runtime)
                elif current_runtime_section == "restore_scan":
                    restore_scan_runtime = parsed_runtime
                elif current_runtime_section == "restore_action":
                    restore_action_runtime = parsed_runtime
                elif current_runtime_section == "report_bloat_scan":
                    summary_section_runtimes.setdefault("report_bloat_scan", parsed_runtime)
                elif current_runtime_section == "report_bloat_action":
                    summary_section_runtimes.setdefault("report_bloat_action", parsed_runtime)
                elif current_runtime_section == "photo_scan":
                    photo_scan_runtime = parsed_runtime
                elif current_runtime_section == "photo_remove":
                    photo_remove_runtime = parsed_runtime
                elif current_runtime_section == "empty_trash_action":
                    summary_section_runtimes.setdefault("empty_trash_action", parsed_runtime)
                elif current_runtime_section == "clean_bundles_action":
                    summary_section_runtimes.setdefault("clean_bundles_action", parsed_runtime)
                elif current_runtime_section == "optimize_db_action":
                    summary_section_runtimes.setdefault("optimize_db_action", parsed_runtime)

    if finished_seen and not finished_at:
        finished_at = _iso_from_mtime(stats.st_mtime if stats else None)

    if not started_at and first_timestamp:
        started_at = first_timestamp

    if not config_name:
        inferred_config_name = _infer_imagemaid_config_name(mode=mode, run_command_text=run_command_text)
        if inferred_config_name:
            config_name = inferred_config_name

    completion_reason = "completed"
    run_complete = bool(finished_at and run_time_seconds is not None)
    if not run_complete:
        if stop_at:
            completion_reason = stop_reason or "user_stop"
            finished_at = finished_at or stop_at
        elif blocked_at:
            completion_reason = "maintenance_blocked_start"
            finished_at = finished_at or blocked_at
        else:
            completion_reason = "unknown_incomplete"

    maintenance_events = []
    if blocked_at:
        maintenance_events.append(
            {
                "event": "blocked_start",
                "at": blocked_at,
                "local_at": "",
                "window": blocked_window or "",
                "paused_seconds": None,
            }
        )
    maintenance_summary = {
        "had_pause": False,
        "pause_count": 0,
        "pause_seconds": 0,
        "open_pause": False,
        "window": blocked_window or "",
        "events": maintenance_events,
    }
    error_lines = _extract_imagemaid_error_lines(lines)
    if generic_error_lines:
        for item in generic_error_lines:
            if item not in error_lines:
                error_lines.append(item)
    if error_lines and error_count == 0:
        error_count = len(error_lines)
    if run_complete and (error_count > 0 or error_lines):
        completion_reason = "completed_with_errors"
    mode = (mode or "report").strip().lower() or "report"
    config_name = str(config_name or "").strip() or "unknown"
    command_signature = f"--mode {mode}"
    run_command = run_command_text or f"imagemaid {command_signature}"
    command_snapshot = _parse_imagemaid_command_snapshot(run_command_text, fallback_mode=mode)
    photo_transcoder_enabled = bool(photo_transcoder_enabled or command_snapshot.get("photo_transcoder"))
    empty_trash_enabled = bool(empty_trash_enabled or command_snapshot.get("empty_trash"))
    clean_bundles_enabled = bool(clean_bundles_enabled or command_snapshot.get("clean_bundles"))
    optimize_db_enabled = bool(optimize_db_enabled or command_snapshot.get("optimize_db"))
    local_db_enabled = bool(local_db_enabled or command_snapshot.get("local_db"))
    use_existing_enabled = bool(use_existing_enabled or command_snapshot.get("use_existing"))
    no_verify_ssl_enabled = bool(no_verify_ssl_enabled or command_snapshot.get("no_verify_ssl"))
    overlays_only_enabled = bool(overlays_only_enabled or command_snapshot.get("overlays_only"))
    timestamp_seed = started_at or finished_at or (stats.st_mtime if stats else 0)
    run_key_seed = f"imagemaid|{timestamp_seed}|{mode}|{path.name if path else 'imagemaid.log'}"
    created_at = finished_at or started_at or _iso_from_mtime(stats.st_mtime if stats else None)
    section_runtimes = {}
    if summary_section_runtimes.get("database_download") is not None:
        section_runtimes["database_download"] = summary_section_runtimes["database_download"]
    if summary_section_runtimes.get("database_query") is not None:
        section_runtimes["database_query"] = summary_section_runtimes["database_query"]
    if summary_section_runtimes.get("report_bloat_scan") is not None:
        section_runtimes["report_bloat_scan"] = summary_section_runtimes["report_bloat_scan"]
    if summary_section_runtimes.get("report_bloat_action") is not None:
        section_runtimes["report_bloat_action"] = summary_section_runtimes["report_bloat_action"]
    if restore_scan_runtime is not None:
        section_runtimes["restore_dir_scan"] = restore_scan_runtime
    if restore_action_runtime is not None:
        section_runtimes["restore_dir_action"] = restore_action_runtime
    if photo_scan_runtime is not None:
        section_runtimes["photo_transcoder_scan"] = photo_scan_runtime
    if photo_remove_runtime is not None:
        section_runtimes["photo_transcoder_remove"] = photo_remove_runtime
    if summary_section_runtimes.get("empty_trash_action") is not None:
        section_runtimes["empty_trash_action"] = summary_section_runtimes["empty_trash_action"]
    if summary_section_runtimes.get("clean_bundles_action") is not None:
        section_runtimes["clean_bundles_action"] = summary_section_runtimes["clean_bundles_action"]
    if summary_section_runtimes.get("optimize_db_action") is not None:
        section_runtimes["optimize_db_action"] = summary_section_runtimes["optimize_db_action"]
    total_found_files = restore_found_files + photo_found_files
    total_removed_files = restore_removed_files + photo_removed_files
    total_recovered_bytes = restore_recovered_bytes + photo_recovered_bytes
    analysis_counts = {
        "imagemaid_error_lines": len(error_lines),
        "imagemaid_database_seen": int(database_section_seen),
        "imagemaid_database_downloaded_new": int(database_downloaded_new),
        "imagemaid_database_download_failed": int(database_download_failed),
        "imagemaid_restore_found_files": restore_found_files,
        "imagemaid_restore_removed_files": restore_removed_files,
        "imagemaid_restore_recovered_bytes": restore_recovered_bytes,
        "imagemaid_photo_found_files": photo_found_files,
        "imagemaid_photo_removed_files": photo_removed_files,
        "imagemaid_photo_recovered_bytes": photo_recovered_bytes,
        "imagemaid_total_found_files": total_found_files,
        "imagemaid_total_removed_files": total_removed_files,
        "imagemaid_total_recovered_bytes": total_recovered_bytes,
        "imagemaid_empty_trash_enabled": int(empty_trash_enabled),
        "imagemaid_clean_bundles_enabled": int(clean_bundles_enabled),
        "imagemaid_optimize_db_enabled": int(optimize_db_enabled),
        "imagemaid_photo_transcoder_enabled": int(photo_transcoder_enabled),
        "imagemaid_local_db_enabled": int(local_db_enabled),
        "imagemaid_use_existing_enabled": int(use_existing_enabled),
        "imagemaid_no_verify_ssl_enabled": int(no_verify_ssl_enabled),
        "imagemaid_overlays_only_enabled": int(overlays_only_enabled),
        "imagemaid_empty_trash_started": int(operation_started["empty_trash"]),
        "imagemaid_clean_bundles_started": int(operation_started["clean_bundles"]),
        "imagemaid_optimize_db_started": int(operation_started["optimize_db"]),
        "imagemaid_enabled_operation_count": int(database_section_seen)
        + int(photo_transcoder_enabled)
        + int(empty_trash_enabled)
        + int(clean_bundles_enabled)
        + int(optimize_db_enabled),
        "imagemaid_completed_with_errors": int(completion_reason == "completed_with_errors"),
    }
    summary = {
        "run_key": hashlib.sha256(run_key_seed.encode("utf-8")).hexdigest(),
        "tool_name": "imagemaid",
        "started_at": started_at,
        "finished_at": finished_at,
        "run_time_seconds": run_time_seconds,
        "kometa_version": local_version or helpers.get_imagemaid_local_version() or "",
        "kometa_newest_version": "",
        "config_name": config_name,
        "config_hash": None,
        "run_command": run_command,
        "command_signature": command_signature,
        "section_runtimes": section_runtimes,
        "log_size": int(stats.st_size) if stats else None,
        "log_counts": {
            "cache": cache_count,
            "debug": debug_count,
            "info": info_count,
            "warning": warning_count,
            "error": error_count,
            "critical": critical_count,
            "trace": trace_count,
        },
        "analysis_counts": analysis_counts,
        "library_counts": {},
        "maintenance_summary": maintenance_summary,
        "maintenance_had_pause": False,
        "quiet_period_summary": {},
        "quickstart_run_marker": quickstart_run_marker,
        "config_line_count": None,
        "cache_line_count": cache_count,
        "created_at": created_at,
        "run_complete": run_complete,
        "completion_reason": completion_reason,
        "imagemaid_mode": mode,
    }
    summary["progress_snapshot"] = _build_imagemaid_progress_snapshot(summary)
    recommendations = _build_imagemaid_recommendations(summary, error_lines=error_lines, completion_reason=completion_reason)
    return {"summary": summary, "recommendations": recommendations}


def _get_logscan_archive_storage_summary(all_runs=None, incomplete_runs=None, context=None):
    context = context or _build_logscan_resolution_context()
    archive_paths = {}
    for entry in context.get("candidate_files", []):
        path = entry.get("path")
        if not path or _classify_logscan_file_location(path) != "archive":
            continue
        archive_paths[str(path.resolve())] = entry

    tracked_paths = set()
    tracked_bytes = 0
    for run in list(all_runs or []) + list(incomplete_runs or []):
        if not isinstance(run, dict):
            continue
        info = _resolve_logscan_run_log_info(run.get("run_key"), run_record=run, context=context)
        if not info or info.get("location") != "archive" or not info.get("path"):
            continue
        path_key = str(Path(info["path"]).resolve())
        if path_key in tracked_paths:
            continue
        tracked_paths.add(path_key)
        if isinstance(info.get("size"), int):
            tracked_bytes += info["size"]
        else:
            entry = archive_paths.get(path_key)
            tracked_bytes += int(entry.get("size", 0)) if isinstance(entry, dict) else 0

    total_archived_bytes = 0
    for entry in archive_paths.values():
        if isinstance(entry.get("size"), int):
            total_archived_bytes += entry["size"]

    total_archived_files = len(archive_paths)
    tracked_archived_files = len(tracked_paths)
    extra_archived_files = max(0, total_archived_files - tracked_archived_files)
    extra_archived_bytes = max(0, total_archived_bytes - tracked_bytes)
    kometa_keep_limit = _get_logscan_keep_limit("kometa")
    imagemaid_keep_limit = _get_logscan_keep_limit("imagemaid")
    return {
        "archived_bytes": tracked_bytes,
        "archived_files": tracked_archived_files,
        "disk_archived_bytes": total_archived_bytes,
        "disk_archived_files": total_archived_files,
        "extra_archived_files": extra_archived_files,
        "extra_archived_bytes": extra_archived_bytes,
        "keep_limit": kometa_keep_limit,
        "retention_label": f"Kometa: {_format_archived_log_retention_label(kometa_keep_limit)} | ImageMaid: {_format_archived_log_retention_label(imagemaid_keep_limit)}",
        "kometa_keep_limit": kometa_keep_limit,
        "imagemaid_keep_limit": imagemaid_keep_limit,
        "kometa_retention_label": _format_archived_log_retention_label(kometa_keep_limit),
        "imagemaid_retention_label": _format_archived_log_retention_label(imagemaid_keep_limit),
        "compression_ready": True,
    }


def _normalize_logscan_archive_filenames(archive_dir=None):
    ingest_cache = _load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    if not isinstance(cache_logs, dict):
        cache_logs = {}
    renamed = 0
    skipped = 0
    errors = []
    cache_dirty = False

    archive_dirs = []
    if archive_dir:
        archive_dirs.append(Path(archive_dir))
    else:
        archive_dirs.extend([_get_logscan_archive_dir("kometa"), _get_logscan_archive_dir("imagemaid"), _get_logscan_archive_root_dir()])

    for current_archive_dir in archive_dirs:
        if not current_archive_dir.exists():
            continue
        for sidecar_path in current_archive_dir.glob("*.quickstart-maintenance.log"):
            try:
                source_key = str(sidecar_path.resolve())
                sidecar_path.unlink()
                if source_key in cache_logs:
                    cache_logs.pop(source_key, None)
                    cache_dirty = True
                renamed += 1
            except Exception as exc:
                errors.append(f"Failed to remove archived maintenance sidecar {sidecar_path}: {exc}")

    for path in sorted(_iter_logscan_candidate_files(include_archive=True, include_compressed=True), key=lambda item: item.name.lower()):
        if _classify_logscan_file_location(path) != "archive":
            continue
        try:
            stats = path.stat()
            current_tool = _detect_logscan_tool_from_path(path)
            target_archive_dir = Path(archive_dir) if archive_dir else _get_logscan_archive_dir(current_tool)
            target_archive_dir.mkdir(parents=True, exist_ok=True)
            target = _build_logscan_archive_destination(
                path,
                target_archive_dir,
                stats=stats,
                preferred_suffix=".log.gz" if not _is_logscan_gzip_path(path) else None,
            )
            if target.resolve() == path.resolve():
                skipped += 1
                continue
            source_key = str(path.resolve())
            target_key = str(target.resolve())
            if _is_logscan_gzip_path(path):
                shutil.move(str(path), str(target))
            else:
                archived_path = _archive_log_file(path, target_archive_dir)
                if not archived_path:
                    raise RuntimeError("archive compression failed")
                target = archived_path
                target_key = str(target.resolve())
            if source_key in cache_logs:
                cache_logs[target_key] = cache_logs.pop(source_key)
                cache_dirty = True
            renamed += 1
        except Exception as exc:
            errors.append(f"Failed to normalize archived log {path}: {exc}")
    if cache_dirty:
        ingest_cache["logs"] = cache_logs
        _save_logscan_ingest_cache(ingest_cache)
    return {"renamed": renamed, "skipped": skipped, "errors": errors}


def _normalize_cli_whitespace(command):
    return re.sub(r"\s+", " ", str(command or "")).strip()


def _command_has_flag(command, flag):
    if not command or not flag:
        return False
    pattern = re.compile(rf"(^|\s){re.escape(flag)}(?=\s|$)")
    return bool(pattern.search(command))


def _remove_cli_switch(command, flag):
    if not command or not flag:
        return command
    pattern = re.compile(rf"(^|\s){re.escape(flag)}(?=\s|$)")
    return pattern.sub(" ", command)


def _remove_cli_option_with_value(command, flag):
    if not command or not flag:
        return command
    pattern = re.compile(rf"(^|\s){re.escape(flag)}(?:=(?:\"[^\"]*\"|'[^']*'|[^\s]+)|\s+(?:\"[^\"]*\"|'[^']*'|[^\s]+))?")
    return pattern.sub(" ", command)


def _quote_cli_value(value):
    text = str(value or "")
    escaped = text.replace('"', '\\"')
    return f'"{escaped}"'


def _normalize_library_scope_values(current_library=None, library_scope=None):
    values = []
    seen = set()

    def add_value(raw):
        candidate = str(raw or "").strip()
        if not candidate:
            return
        normalized = candidate.casefold()
        if normalized in seen:
            return
        seen.add(normalized)
        values.append(candidate)

    if isinstance(library_scope, (list, tuple, set)):
        for item in library_scope:
            add_value(item)
    elif library_scope:
        if isinstance(library_scope, str) and "|" in library_scope:
            for item in library_scope.split("|"):
                add_value(item)
        else:
            add_value(library_scope)
    elif current_library:
        add_value(current_library)

    return values


def _build_resume_library_scope(original_command, progress_libraries=None, current_library=None, allow_current_fallback=False):
    run_option, selected_libraries = _extract_selected_libraries(original_command)
    progress_libraries = progress_libraries if isinstance(progress_libraries, list) else []

    status_by_name = {}
    ordered_library_names = []
    for entry in progress_libraries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        ordered_library_names.append(name)
        status_by_name[name.casefold()] = str(entry.get("status") or "").strip()

    base_scope = []
    if isinstance(selected_libraries, list) and selected_libraries:
        base_scope = [str(name).strip() for name in selected_libraries if str(name).strip()]
    elif run_option != "--run-libraries":
        base_scope = ordered_library_names[:]

    remaining = []
    seen = set()
    for name in base_scope:
        key = name.casefold()
        status = status_by_name.get(key, "")
        if status in ("Done", "Skipped"):
            continue
        if key in seen:
            continue
        seen.add(key)
        remaining.append(name)

    current_name = str(current_library or "").strip()
    if current_name:
        current_key = current_name.casefold()
        if current_key not in seen:
            current_status = status_by_name.get(current_key, "")
            current_in_base_scope = (not base_scope) or any(str(name).strip().casefold() == current_key for name in base_scope)
            if current_in_base_scope and current_status not in ("Done", "Skipped"):
                if current_key in status_by_name or allow_current_fallback:
                    remaining.insert(0, current_name)

    return remaining


def _should_suppress_recovery_for_completed_scope(original_command, progress_libraries=None, current_library=None):
    progress_libraries = progress_libraries if isinstance(progress_libraries, list) else []
    if not progress_libraries:
        return False

    run_option, selected_libraries = _extract_selected_libraries(original_command)
    explicit_phase = _detect_explicit_phase_from_command(original_command)
    if explicit_phase not in ("collections", "operations", "metadata", "overlays", "playlists") and run_option != "--run-libraries":
        return False

    remaining = _build_resume_library_scope(
        original_command,
        progress_libraries=progress_libraries,
        current_library=current_library,
        allow_current_fallback=False,
    )
    return len(remaining) == 0


def _resolve_config_path_for_command(config_name=None):
    normalized_name = str(config_name or "").strip().lower().replace(" ", "_")
    if not normalized_name:
        if has_request_context():
            normalized_name = str(session.get("config_name") or "default").strip().lower().replace(" ", "_") or "default"
        else:
            normalized_name = "default"
    return str((helpers.get_kometa_config_dir() / f"{normalized_name}_config.yml").resolve())


def _inject_config_path_for_command(command, config_name=None):
    cleaned = _normalize_cli_whitespace(command)
    if not cleaned:
        return ""
    if "<config>" not in cleaned and "--config" not in cleaned and "-c" not in cleaned and not str(config_name or "").strip():
        return cleaned
    config_path = _resolve_config_path_for_command(config_name=config_name)
    quoted = _quote_cli_value(config_path)
    if "<config>" in cleaned:
        return _normalize_cli_whitespace(cleaned.replace("<config>", quoted))
    cleaned = _remove_cli_option_with_value(cleaned, "--config")
    cleaned = _remove_cli_option_with_value(cleaned, "-c")
    return _normalize_cli_whitespace(f"{cleaned} --config {quoted}")


def _build_recovery_command(base_command, phase=None, current_library=None, library_scope=None):
    command = _normalize_cli_whitespace(base_command)
    if not command:
        return ""

    phase_modes = {
        "operations": "--operations-only",
        "metadata": "--metadata-only",
        "collections": "--collections-only",
        "overlays": "--overlays-only",
        "playlists": "--playlists-only",
    }
    mode_flags = list(phase_modes.values())
    scoped_flags = ["--run-libraries", "--run-collections", "--resume"]

    for flag in mode_flags:
        command = _remove_cli_switch(command, flag)
    for flag in scoped_flags:
        command = _remove_cli_option_with_value(command, flag)

    phase_flag = phase_modes.get((phase or "").strip().lower())
    if phase_flag:
        command = f"{command} {phase_flag}"
    library_values = _normalize_library_scope_values(current_library=current_library, library_scope=library_scope)
    if library_scope is not None and not library_values:
        return ""
    if library_values:
        command = f"{command} --run-libraries {_quote_cli_value('|'.join(library_values))}"
    if not _command_has_flag(command, "--run") and not _command_has_flag(command, "--times"):
        command = f"{command} --run"

    return _normalize_cli_whitespace(command)


def _build_collection_resume_command(base_command, current_collection=None, current_library=None):
    command = _build_recovery_command(base_command, phase="collections", current_library=current_library)
    if not command or not current_collection:
        return ""
    command = _remove_cli_option_with_value(command, "--resume")
    command = f"{command} --resume {_quote_cli_value(current_collection)}"
    return _normalize_cli_whitespace(command)


def _build_resume_command_preserving_scope(base_command, current_collection=None, current_library=None, library_scope=None):
    command = _normalize_cli_whitespace(base_command)
    if not command or not current_collection:
        return ""

    explicit_phase = _detect_explicit_phase_from_command(command)
    preserved_phase = explicit_phase if explicit_phase not in (None, "mixed") else None
    command = _build_recovery_command(
        command,
        phase=preserved_phase,
        current_library=current_library,
        library_scope=library_scope,
    )
    if not command:
        return ""
    command = _remove_cli_option_with_value(command, "--resume")
    command = f"{command} --resume {_quote_cli_value(current_collection)}"
    return _normalize_cli_whitespace(command)


def _iso_from_mtime(value):
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            return None
    return None


def _extract_first_log_timestamp(content):
    if not content:
        return None
    match = re.search(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}\]", str(content), re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def _extract_last_log_timestamp(content):
    if not content:
        return None
    matches = re.findall(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}\]", str(content), re.MULTILINE)
    if not matches:
        return None
    return str(matches[-1]).strip()


def _parse_log_display_datetime(value):
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S",):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            continue
    return None


def _format_duration_brief(total_seconds):
    if not isinstance(total_seconds, (int, float)):
        return ""
    seconds = max(0, int(total_seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def _format_compact_count_brief(value):
    if not isinstance(value, (int, float)):
        return ""
    count = max(0, int(value))
    if count >= 1000000:
        return f"{(count / 1000000):.1f}".rstrip("0").rstrip(".") + "M"
    if count >= 1000:
        return f"{(count / 1000):.1f}".rstrip("0").rstrip(".") + "K"
    return str(count)


def _format_imagemaid_bytes_brief(value):
    if not isinstance(value, (int, float)):
        return ""
    total = max(0, int(value))
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(total)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        display = str(int(size))
    elif size >= 10:
        display = f"{size:.1f}".rstrip("0").rstrip(".")
    else:
        display = f"{size:.2f}".rstrip("0").rstrip(".")
    return f"{display} {units[unit_index]}"


def _build_imagemaid_progress_snapshot(summary=None):
    summary = summary if isinstance(summary, dict) else {}
    if str(summary.get("tool_name") or "").strip().lower() != "imagemaid":
        return {}

    analysis_counts = summary.get("analysis_counts") if isinstance(summary.get("analysis_counts"), dict) else {}
    section_runtimes = summary.get("section_runtimes") if isinstance(summary.get("section_runtimes"), dict) else {}
    mode = str(summary.get("imagemaid_mode") or "report").strip().lower() or "report"
    run_complete = bool(summary.get("run_complete"))
    completion_reason = str(summary.get("completion_reason") or "").strip().lower()
    error_total = 0
    log_counts = summary.get("log_counts") if isinstance(summary.get("log_counts"), dict) else {}
    for key in ("error", "critical", "trace"):
        if isinstance(log_counts.get(key), (int, float)):
            error_total += int(log_counts.get(key) or 0)
    if isinstance(analysis_counts.get("imagemaid_error_lines"), (int, float)):
        error_total = max(error_total, int(analysis_counts.get("imagemaid_error_lines") or 0))

    rows = []
    total_scan_seconds = 0
    total_action_seconds = 0

    def _runtime_cell(value):
        if not isinstance(value, (int, float)):
            return {}
        seconds = max(0, int(value))
        return {"label": _format_duration_brief(seconds), "tone": "primary"}

    def _badge_cell(label, tone="success"):
        text = str(label or "").strip()
        return {"label": text, "tone": tone} if text else {}

    def _row_status(observed=False, enabled=False):
        if completion_reason == "maintenance_blocked_start":
            return "Blocked", " text-bg-warning"
        if observed:
            if run_complete:
                if error_total > 0:
                    return "Completed", " text-bg-warning"
                return "Completed", " text-bg-success"
            if completion_reason == "user_stop":
                return "Stopped", " text-bg-warning"
            return "Observed", " text-bg-primary"
        if enabled:
            if completion_reason == "maintenance_blocked_start":
                return "Blocked", " text-bg-warning"
            return "Pending", " text-bg-secondary"
        return "Skipped", " text-bg-secondary"

    def _append_row(name, row_type, scan_seconds=None, action_seconds=None, items_label="", outcome_label="", enabled=False, items_tone="success", outcome_tone="success"):
        nonlocal total_scan_seconds, total_action_seconds
        observed = any(
            [
                isinstance(scan_seconds, (int, float)),
                isinstance(action_seconds, (int, float)),
                bool(str(items_label or "").strip()),
                bool(str(outcome_label or "").strip()),
            ]
        )
        if not enabled and not observed:
            return
        if isinstance(scan_seconds, (int, float)):
            total_scan_seconds += max(0, int(scan_seconds))
        if isinstance(action_seconds, (int, float)):
            total_action_seconds += max(0, int(action_seconds))
        status, status_class = _row_status(observed=observed, enabled=enabled)
        rows.append(
            {
                "name": name,
                "type": row_type,
                "status": status,
                "status_class": status_class,
                "phase_cells": [
                    _runtime_cell(scan_seconds),
                    _runtime_cell(action_seconds),
                    _badge_cell(items_label, tone=items_tone),
                    _badge_cell(outcome_label, tone=outcome_tone),
                ],
            }
        )

    database_seen = bool(analysis_counts.get("imagemaid_database_seen"))
    local_db_enabled = bool(analysis_counts.get("imagemaid_local_db_enabled"))
    use_existing_enabled = bool(analysis_counts.get("imagemaid_use_existing_enabled"))
    database_downloaded_new = bool(analysis_counts.get("imagemaid_database_downloaded_new"))
    database_download_failed = bool(analysis_counts.get("imagemaid_database_download_failed"))
    database_enabled = database_seen or "database_download" in section_runtimes or "database_query" in section_runtimes
    database_items = ""
    if local_db_enabled:
        database_items = "Local DB"
    elif use_existing_enabled:
        database_items = "Existing DB"
    elif database_downloaded_new:
        database_items = "Downloaded"
    elif database_seen:
        database_items = "Plex API"
    database_outcome = "Failed" if database_download_failed else ("Ready" if database_enabled else "")
    _append_row(
        "Database Prep",
        "Source",
        scan_seconds=section_runtimes.get("database_download"),
        action_seconds=section_runtimes.get("database_query"),
        items_label=database_items,
        outcome_label=database_outcome,
        enabled=database_enabled,
        items_tone="secondary",
        outcome_tone="danger" if database_download_failed else "success",
    )

    report_enabled = mode == "report" or "report_bloat_scan" in section_runtimes or "report_bloat_action" in section_runtimes
    report_outcome = "Reported" if report_enabled and run_complete else ""
    _append_row(
        "Bloat Report",
        "Metadata",
        scan_seconds=section_runtimes.get("report_bloat_scan"),
        action_seconds=section_runtimes.get("report_bloat_action"),
        items_label="Mode report" if report_enabled else "",
        outcome_label=report_outcome,
        enabled=report_enabled,
        items_tone="secondary",
        outcome_tone="success",
    )

    restore_found = int(analysis_counts.get("imagemaid_restore_found_files") or 0) if isinstance(analysis_counts.get("imagemaid_restore_found_files"), (int, float)) else 0
    restore_removed = int(analysis_counts.get("imagemaid_restore_removed_files") or 0) if isinstance(analysis_counts.get("imagemaid_restore_removed_files"), (int, float)) else 0
    restore_recovered = (
        int(analysis_counts.get("imagemaid_restore_recovered_bytes") or 0) if isinstance(analysis_counts.get("imagemaid_restore_recovered_bytes"), (int, float)) else 0
    )
    restore_enabled = mode in {"clear", "restore"} or "restore_dir_scan" in section_runtimes or "restore_dir_action" in section_runtimes or restore_found > 0 or restore_removed > 0
    restore_items = ""
    if restore_removed > 0:
        restore_items = f"Removed {_format_compact_count_brief(restore_removed)}"
    elif restore_found > 0:
        restore_items = f"Found {_format_compact_count_brief(restore_found)}"
    restore_outcome = _format_imagemaid_bytes_brief(restore_recovered) if restore_recovered > 0 else ""
    _append_row(
        "Restore Cache",
        "File cleanup",
        scan_seconds=section_runtimes.get("restore_dir_scan"),
        action_seconds=section_runtimes.get("restore_dir_action"),
        items_label=restore_items,
        outcome_label=restore_outcome,
        enabled=restore_enabled,
        items_tone="primary",
        outcome_tone="success",
    )

    photo_found = int(analysis_counts.get("imagemaid_photo_found_files") or 0) if isinstance(analysis_counts.get("imagemaid_photo_found_files"), (int, float)) else 0
    photo_removed = int(analysis_counts.get("imagemaid_photo_removed_files") or 0) if isinstance(analysis_counts.get("imagemaid_photo_removed_files"), (int, float)) else 0
    photo_recovered = int(analysis_counts.get("imagemaid_photo_recovered_bytes") or 0) if isinstance(analysis_counts.get("imagemaid_photo_recovered_bytes"), (int, float)) else 0
    photo_enabled = (
        bool(analysis_counts.get("imagemaid_photo_transcoder_enabled"))
        or "photo_transcoder_scan" in section_runtimes
        or "photo_transcoder_remove" in section_runtimes
        or photo_found > 0
        or photo_removed > 0
    )
    photo_items = ""
    if photo_removed > 0:
        photo_items = f"Removed {_format_compact_count_brief(photo_removed)}"
    elif photo_found > 0:
        photo_items = f"Found {_format_compact_count_brief(photo_found)}"
    photo_outcome = _format_imagemaid_bytes_brief(photo_recovered) if photo_recovered > 0 else ""
    _append_row(
        "PhotoTranscoder",
        "File cleanup",
        scan_seconds=section_runtimes.get("photo_transcoder_scan"),
        action_seconds=section_runtimes.get("photo_transcoder_remove"),
        items_label=photo_items,
        outcome_label=photo_outcome,
        enabled=photo_enabled,
        items_tone="primary",
        outcome_tone="success",
    )

    for label, enabled_key, started_key, runtime_key in [
        ("Empty Trash", "imagemaid_empty_trash_enabled", "imagemaid_empty_trash_started", "empty_trash_action"),
        ("Clean Bundles", "imagemaid_clean_bundles_enabled", "imagemaid_clean_bundles_started", "clean_bundles_action"),
        ("Optimize DB", "imagemaid_optimize_db_enabled", "imagemaid_optimize_db_started", "optimize_db_action"),
    ]:
        enabled = bool(analysis_counts.get(enabled_key)) or bool(analysis_counts.get(started_key)) or runtime_key in section_runtimes
        runtime_value = section_runtimes.get(runtime_key)
        items_label = "Enabled" if enabled else ""
        outcome_label = "Done" if isinstance(runtime_value, (int, float)) and run_complete else ""
        _append_row(
            label,
            "Plex task",
            scan_seconds=None,
            action_seconds=runtime_value,
            items_label=items_label,
            outcome_label=outcome_label,
            enabled=enabled,
            items_tone="secondary",
            outcome_tone="success",
        )

    if not rows:
        return {}

    total_removed = int(analysis_counts.get("imagemaid_total_removed_files") or 0) if isinstance(analysis_counts.get("imagemaid_total_removed_files"), (int, float)) else 0
    total_recovered = int(analysis_counts.get("imagemaid_total_recovered_bytes") or 0) if isinstance(analysis_counts.get("imagemaid_total_recovered_bytes"), (int, float)) else 0
    completed_count = 0
    for row in rows:
        if row.get("status") in {"Completed", "Skipped"}:
            completed_count += 1

    return {
        "name_label": "Operation",
        "type_label": "Area",
        "columns": [
            {"key": "scan", "label": "Scan Time"},
            {"key": "action", "label": "Action Time"},
            {"key": "items", "label": "Observed"},
            {"key": "outcome", "label": "Result"},
        ],
        "rows": rows,
        "completed_count": completed_count,
        "total_count": len(rows),
        "preparation_label": "",
        "footer_cells": [
            _format_duration_brief(total_scan_seconds) if total_scan_seconds > 0 else "",
            _format_duration_brief(total_action_seconds) if total_action_seconds > 0 else "",
            f"Removed {_format_compact_count_brief(total_removed)}" if total_removed > 0 else "",
            _format_imagemaid_bytes_brief(total_recovered) if total_recovered > 0 else "",
        ],
        "total_label": (
            _format_duration_brief(summary.get("run_time_seconds")) if isinstance(summary.get("run_time_seconds"), (int, float)) and summary.get("run_time_seconds") else ""
        ),
    }


def _build_incomplete_run_timing_summary(started_at=None, last_log_at=None, maintenance_summary=None):
    summary = maintenance_summary if isinstance(maintenance_summary, dict) else {}
    started_dt = _parse_log_display_datetime(started_at)
    last_log_dt = _parse_log_display_datetime(last_log_at)
    pause_seconds = int(summary.get("pause_seconds") or 0) if isinstance(summary.get("pause_seconds"), (int, float)) else 0
    observed_seconds = None
    active_seconds = None
    if started_dt and last_log_dt and last_log_dt >= started_dt:
        observed_seconds = int((last_log_dt - started_dt).total_seconds())
        active_seconds = max(0, observed_seconds - pause_seconds)
    return {
        "started_at": started_at or "",
        "last_log_at": last_log_at or "",
        "window": summary.get("window") or "",
        "pause_count": int(summary.get("pause_count") or 0) if isinstance(summary.get("pause_count"), (int, float)) else 0,
        "pause_seconds": pause_seconds,
        "pause_label": _format_duration_brief(pause_seconds) if pause_seconds else "",
        "pause_display": _format_duration_brief(pause_seconds) if pause_seconds else "Not observed",
        "observed_seconds": observed_seconds,
        "observed_label": _format_duration_brief(observed_seconds) if observed_seconds is not None else "",
        "active_seconds": active_seconds,
        "active_label": _format_duration_brief(active_seconds) if active_seconds is not None else "",
        "had_pause": bool(summary.get("had_pause")),
    }


def _dedupe_preserve_order(values):
    seen = set()
    ordered = []
    for value in values or []:
        name = str(value or "").strip()
        if not name:
            continue
        lowered = name.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(name)
    return ordered


def _build_incomplete_scope_summary(original_command="", suggested_command="", progress_libraries=None):
    progress_libraries = progress_libraries if isinstance(progress_libraries, list) else []
    original_selected = _extract_selected_libraries(original_command)[1] or []
    recovery_selected = _extract_selected_libraries(suggested_command)[1] or []
    progress_names = _dedupe_preserve_order(entry.get("name") for entry in progress_libraries if isinstance(entry, dict))
    completed = _dedupe_preserve_order(entry.get("name") for entry in progress_libraries if isinstance(entry, dict) and str(entry.get("status") or "").strip() == "Done")

    original_scope = _dedupe_preserve_order(original_selected or progress_names)
    recovery_scope = _dedupe_preserve_order(recovery_selected or original_scope)
    pruned = []
    if original_scope and recovery_scope:
        recovery_lookup = {name.casefold() for name in recovery_scope}
        pruned = [name for name in original_scope if name.casefold() not in recovery_lookup]

    return {
        "original_scope": original_scope,
        "recovery_scope": recovery_scope,
        "completed_libraries": completed,
        "pruned_libraries": pruned,
        "original_scope_label": " | ".join(original_scope) if original_scope else "",
        "recovery_scope_label": " | ".join(recovery_scope) if recovery_scope else "",
        "completed_label": " | ".join(completed) if completed else "",
        "pruned_label": " | ".join(pruned) if pruned else "",
    }


def _build_maintenance_event_rows(maintenance_summary=None):
    summary = maintenance_summary if isinstance(maintenance_summary, dict) else {}
    rows = []
    for event in summary.get("events") or []:
        if not isinstance(event, dict):
            continue
        event_name = str(event.get("event") or "").strip().lower()
        if event_name not in ("paused", "resumed"):
            continue
        label = "Paused" if event_name == "paused" else "Resumed"
        at_value = str(event.get("local_at") or event.get("at") or "").strip()
        pause_label = _format_duration_brief(event.get("paused_seconds")) if isinstance(event.get("paused_seconds"), (int, float)) else ""
        window = str(event.get("window") or "").strip()
        rows.append(
            {
                "label": label,
                "at": at_value,
                "pause_label": pause_label,
                "window": window,
            }
        )
    return rows


def _build_incomplete_progress_snapshot(progress=None, last_log_at=None, config_data=None, original_command="", config_name=None):
    progress = progress if isinstance(progress, dict) else {}
    libraries = progress.get("libraries") if isinstance(progress.get("libraries"), list) else []
    if not libraries:
        return {}
    phase_lookup = {
        "operations": "Operations",
        "metadata": "Metadata",
        "collections": "Collections",
        "overlays": "Overlays",
        "playlists": "Playlists",
    }
    current_phase = str(progress.get("phase_current") or "").strip().lower()
    current_library = str(progress.get("current_library") or "").strip()
    preparation_seconds = progress.get("preparation_seconds")
    if not isinstance(preparation_seconds, (int, float)):
        preparation_seconds = progress.get("preparation_elapsed_seconds")
    current_phase_elapsed_seconds = progress.get("current_phase_elapsed_seconds") if isinstance(progress.get("current_phase_elapsed_seconds"), (int, float)) else None
    explicit_phase = _detect_explicit_phase_from_command(original_command)
    run_mode = explicit_phase if explicit_phase in ("collections", "operations", "metadata", "overlays", "playlists") else "all"
    allowed_phases = _get_progress_run_order(config_data=config_data)
    if not allowed_phases:
        allowed_phases = ["operations", "metadata", "collections", "overlays"]
    playlists_configured = bool(config_data.get("playlists")) if isinstance(config_data, dict) else False
    if run_mode in ("collections", "overlays", "operations", "metadata", "playlists"):
        allowed_phases = [run_mode]
    elif "playlists" not in allowed_phases:
        allowed_phases = allowed_phases + ["playlists"]
    columns = [{"key": key, "label": phase_lookup.get(key, key.title())} for key in allowed_phases]
    configured_library_entries = []
    configured_library_names = []
    configured_type_by_name = {}
    config_path = _extract_cli_option_value(original_command, "--config")
    selected_libraries = _extract_selected_libraries(original_command)[1]
    for entry in _get_progress_library_list(
        selected_libraries=selected_libraries,
        config_path=config_path,
        config_data=config_data,
        config_name=config_name,
    ):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        lib_type = str(entry.get("type") or "").strip()
        if name:
            configured_type_by_name[name] = lib_type or None
    if isinstance(config_data, dict):
        config_libraries = config_data.get("libraries")
        if isinstance(config_libraries, dict):
            configured_library_names = [str(name).strip() for name in config_libraries.keys() if str(name).strip()]
            configured_library_entries = [{"name": name, "type": configured_type_by_name.get(name)} for name in configured_library_names]
    elif configured_type_by_name:
        configured_library_names = list(configured_type_by_name.keys())
        configured_library_entries = [{"name": name, "type": configured_type_by_name.get(name)} for name in configured_library_names]

    def _normalize_snapshot_library_name(raw_name):
        name = str(raw_name or "").strip()
        if not name:
            return ""
        if configured_library_entries:
            matched = logscan.LogscanAnalyzer()._match_library_name(name, configured_library_entries)
            if matched:
                return matched
            if name.lower().startswith("finished "):
                alternate = name[9:].strip()
                matched = logscan.LogscanAnalyzer()._match_library_name(alternate, configured_library_entries)
                if matched:
                    return matched
        if name.lower().startswith("finished "):
            return name[9:].strip()
        return name

    current_library = _normalize_snapshot_library_name(current_library)

    rows = []
    totals = {column["key"]: 0 for column in columns}
    visible_libraries = [entry for entry in libraries if str((entry or {}).get("status") or "").strip() != "Skipped"]
    for entry in visible_libraries:
        name = _normalize_snapshot_library_name(entry.get("name"))
        status = str(entry.get("status") or "Pending").strip() or "Pending"
        status_class = "text-bg-secondary"
        if status == "Done":
            status_class = "text-bg-success"
        elif status == "In progress":
            status_class = "text-bg-primary"
        elif status == "Stopped":
            status_class = "text-bg-danger"

        durations = entry.get("durations") if isinstance(entry.get("durations"), dict) else {}
        phase_cells = []
        for column in columns:
            phase_key = column["key"]
            label = ""
            tone = ""
            seconds = durations.get(phase_key)
            if phase_key == "playlists":
                playlist_total = progress.get("playlist_total_seconds") if isinstance(progress.get("playlist_total_seconds"), (int, float)) else None
                playlist_running = bool(progress.get("playlist_running"))
                playlist_elapsed = progress.get("playlist_elapsed_seconds") if isinstance(progress.get("playlist_elapsed_seconds"), (int, float)) else None
                if playlist_running:
                    label = _format_duration_brief(playlist_elapsed)
                    tone = "primary"
                elif isinstance(playlist_total, (int, float)) and (playlist_total > 0 or playlists_configured):
                    label = _format_duration_brief(playlist_total)
                    tone = "success" if label else ""
                    if label:
                        totals[phase_key] = max(0, int(playlist_total))
                phase_cells.append({"label": label, "tone": tone})
                continue
            if current_library and current_phase and current_library == name and current_phase == phase_key and isinstance(current_phase_elapsed_seconds, (int, float)):
                label = _format_duration_brief(current_phase_elapsed_seconds)
                tone = "primary"
            elif isinstance(seconds, (int, float)):
                label = _format_duration_brief(seconds)
                tone = "success"
                totals[phase_key] = totals.get(phase_key, 0) + int(seconds or 0)
            phase_cells.append({"label": label, "tone": tone})

        row_type = configured_type_by_name.get(name) or entry.get("type")
        rows.append(
            {
                "name": name,
                "type": str(row_type or "—").strip() or "—",
                "status": status,
                "status_class": status_class,
                "phase_cells": phase_cells,
            }
        )

    total_seconds = 0
    if isinstance(preparation_seconds, (int, float)):
        total_seconds += int(preparation_seconds or 0)
    for value in totals.values():
        if isinstance(value, (int, float)):
            total_seconds += int(value or 0)

    return {
        "columns": columns,
        "rows": rows,
        "completed_count": progress.get("completed_count"),
        "total_count": progress.get("total_count"),
        "current_library": current_library,
        "phase_current": current_phase,
        "last_log_at": last_log_at or "",
        "preparation_label": _format_duration_brief(preparation_seconds) if isinstance(preparation_seconds, (int, float)) else "",
        "footer_cells": [
            _format_duration_brief(totals.get(column["key"])) if isinstance(totals.get(column["key"]), (int, float)) and totals.get(column["key"]) > 0 else "" for column in columns
        ],
        "total_label": _format_duration_brief(total_seconds) if total_seconds > 0 else "",
    }


def _build_completed_log_progress_snapshot(summary=None, content="", analyzer=None):
    summary = summary if isinstance(summary, dict) else {}
    if not content:
        return {}
    tool_name = str(summary.get("tool_name") or "kometa").strip().lower() or "kometa"
    if tool_name != "kometa":
        return {}

    original_command = summary.get("run_command") or ""
    if not original_command:
        return {}
    config_name = str(summary.get("config_name") or "").strip()
    original_command = _inject_config_path_for_command(
        original_command,
        config_name=config_name,
    )
    config_path = _extract_cli_option_value(original_command, "--config")
    if not config_path and config_name:
        config_path = _resolve_config_path_for_command(config_name=config_name)
    config_data = _load_progress_config(config_path) if config_path else {}
    selected_libraries = _extract_selected_libraries(original_command)[1]
    progress_analyzer = analyzer if analyzer is not None else logscan.LogscanAnalyzer()
    progress = progress_analyzer.extract_progress(
        content,
        library_list=_get_progress_library_list(
            selected_libraries=selected_libraries,
            config_path=config_path,
            config_data=config_data,
            config_name=config_name,
        ),
        selected_libraries=selected_libraries,
        previous=None,
        run_started_at=summary.get("started_at"),
        now_ts=datetime.now(timezone.utc),
        is_running=False,
    )
    snapshot = _build_incomplete_progress_snapshot(
        progress=progress,
        last_log_at=summary.get("finished_at") or summary.get("started_at"),
        config_data=config_data,
        original_command=original_command,
        config_name=config_name,
    )
    if not snapshot:
        return {}
    return snapshot


def _build_incomplete_resume_message(phase_current=None, current_library=None, finished_at=None):
    if phase_current and current_library:
        message = f"Run appears incomplete during {phase_current} in library '{current_library}'."
    elif phase_current:
        message = f"Run appears incomplete during {phase_current}."
    elif current_library:
        message = f"Run appears incomplete while processing library '{current_library}'."
    else:
        message = "Run appears incomplete."

    if finished_at:
        return f"{message} Last finished marker: {finished_at}."
    return f"{message} No Finished Run marker was found."


def _build_completed_scope_resume_message(phase_current=None, current_library=None, finished_at=None):
    if current_library:
        message = f"The original run scope appears fully completed through library '{current_library}'."
    elif phase_current:
        message = f"The original run scope appears fully completed through the {phase_current} phase."
    else:
        message = "The original run scope appears fully completed."

    if finished_at:
        return f"{message} Last finished marker: {finished_at}."
    return message


def _build_recovery_suggestions(original_command, phase_current=None, current_library=None, current_collection=None, progress_libraries=None):
    suggestions = []
    if not original_command:
        return suggestions

    if _should_suppress_recovery_for_completed_scope(
        original_command,
        progress_libraries=progress_libraries,
        current_library=current_library,
    ):
        return []

    phase_key = (phase_current or "").strip().lower()
    explicit_phase = _detect_explicit_phase_from_command(original_command)
    resume_library_scope = _build_resume_library_scope(
        original_command,
        progress_libraries=progress_libraries,
        current_library=current_library,
        allow_current_fallback=bool(phase_key == "collections" or explicit_phase == "collections"),
    )
    scoped_library_scope = resume_library_scope or None

    if phase_key == "collections" and current_collection:
        suggestions.append(
            _build_resume_command_preserving_scope(
                original_command,
                current_collection=current_collection,
                current_library=current_library,
                library_scope=scoped_library_scope,
            )
        )
        if scoped_library_scope is not None:
            suggestions.append(
                _build_resume_command_preserving_scope(
                    original_command,
                    current_collection=current_collection,
                    current_library=None,
                    library_scope=None,
                )
            )

    phase_scope = explicit_phase if explicit_phase not in (None, "mixed") else None

    if phase_scope:
        suggestions.append(_build_recovery_command(original_command, phase=phase_scope, library_scope=scoped_library_scope))
        if scoped_library_scope is not None:
            suggestions.append(_build_recovery_command(original_command, phase=phase_scope, library_scope=None))
    elif scoped_library_scope is not None:
        suggestions.append(_build_recovery_command(original_command, phase=None, library_scope=scoped_library_scope))
    suggestions.append(_normalize_cli_whitespace(original_command))

    deduped = []
    seen = set()
    for item in suggestions:
        normalized = _normalize_cli_whitespace(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:4]


def _extract_cli_option_value(command, flag):
    normalized = _normalize_cli_whitespace(command)
    if not normalized or not flag:
        return ""
    pattern = re.compile(rf"(?:^|\s){re.escape(flag)}(?:=(\"[^\"]*\"|'[^']*'|[^\s]+)|\s+(\"[^\"]*\"|'[^']*'|[^\s]+))")
    match = pattern.search(normalized)
    if not match:
        return ""
    raw = match.group(1) or match.group(2) or ""
    if len(raw) >= 2 and ((raw[0] == '"' and raw[-1] == '"') or (raw[0] == "'" and raw[-1] == "'")):
        return raw[1:-1]
    return raw


def _detect_explicit_phase_from_command(command):
    normalized = _normalize_cli_whitespace(command)
    if not normalized:
        return None
    phase_modes = {
        "operations": "--operations-only",
        "metadata": "--metadata-only",
        "collections": "--collections-only",
        "overlays": "--overlays-only",
        "playlists": "--playlists-only",
    }
    matches = [phase for phase, flag in phase_modes.items() if _command_has_flag(normalized, flag)]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return "mixed"


def _build_resume_explanation(
    original_command,
    suggested_command,
    phase_current=None,
    current_library=None,
    current_collection=None,
    finished_at=None,
    progress_libraries=None,
):
    lines = []
    if finished_at:
        lines.append(f"Last finished marker seen in the log: {finished_at}.")
        lines.append("A final Finished Run block was not found after that point, so this run was treated as incomplete.")
    else:
        lines.append("No Finished Run marker was found in this log, so the run was treated as incomplete.")

    phase_modes = {
        "operations": "--operations-only",
        "metadata": "--metadata-only",
        "collections": "--collections-only",
        "overlays": "--overlays-only",
        "playlists": "--playlists-only",
    }
    phase_key = (phase_current or "").strip().lower()
    phase_flag = phase_modes.get(phase_key)
    explicit_phase = _detect_explicit_phase_from_command(original_command)
    explicit_phase_flag = phase_modes.get(explicit_phase)
    if phase_flag and explicit_phase == phase_key:
        lines.append(f"Original logged command already targeted {phase_key} via {phase_flag}; recovery kept that same scope.")
    elif phase_key == "collections":
        if explicit_phase == "collections":
            lines.append("Detected active phase 'collections', and the original logged command was already collections-only.")
        else:
            lines.append("Detected active phase 'collections', but the original logged command was not collections-only; recovery kept the original run scope.")
    elif phase_flag:
        if explicit_phase == phase_key:
            lines.append(f"Detected active phase '{phase_key}', and the original logged command already used {phase_flag}.")
        elif explicit_phase in (None, "mixed"):
            lines.append(f"Detected active phase '{phase_key}', but the original logged command was not phase-only; recovery kept the original run scope.")
        else:
            lines.append(f"Detected active phase '{phase_key}', while the original logged command already targeted {explicit_phase}; recovery kept the original run scope.")
    elif phase_current:
        lines.append(f"Detected phase '{phase_current}', but no phase-only flag mapping was found.")
    else:
        if explicit_phase and explicit_phase != "mixed":
            lines.append(f"Detected explicit phase mode in the logged command: {phase_modes.get(explicit_phase, explicit_phase)}.")
        elif explicit_phase == "mixed":
            lines.append("Detected multiple phase-only flags in the logged command; mode flags were normalized.")

    effective_phase = phase_key or (explicit_phase if explicit_phase not in (None, "mixed") else "")
    resume_value = _extract_cli_option_value(original_command, "--resume")
    has_resume_flag = _command_has_flag(original_command, "--resume")
    suggested_resume = _extract_cli_option_value(suggested_command, "--resume")
    suggested_library = _extract_cli_option_value(suggested_command, "--run-libraries")

    if effective_phase and effective_phase != "collections":
        lines.append(f"Kometa --resume was not used because this run is {effective_phase}-phase; --resume only applies to collections.")
    elif suggested_resume:
        if suggested_resume:
            if explicit_phase_flag == "--collections-only":
                if current_collection and suggested_resume == current_collection:
                    lines.append(f'Collections-only run preserved; using --resume "{suggested_resume}" from latest in-progress collection activity.')
                else:
                    lines.append(f'Collections-only run preserved; suggestion uses --resume "{suggested_resume}".')
            else:
                if current_collection and suggested_resume == current_collection:
                    lines.append(f'Run was interrupted during collections, so recovery adds --resume "{suggested_resume}" while keeping the original run scope.')
                else:
                    lines.append(f'Recovery adds --resume "{suggested_resume}" while keeping the original run scope.')
            if suggested_library:
                lines.append(f'Used scoped resume (--run-libraries "{suggested_library}") instead of blind resume across all libraries.')
    elif has_resume_flag and resume_value:
        lines.append(f"Logged command already included --resume {resume_value}; it was not auto-carried forward to avoid stale checkpoints.")
    elif effective_phase == "collections" or phase_key == "collections":
        lines.append("Collections phase was detected. --resume can apply here, but no reliable resume checkpoint was found in this log.")
    else:
        lines.append("Kometa --resume was not used because phase could not be confirmed as collections.")

    if current_library:
        lines.append(f"Detected in-progress library '{current_library}', so the suggestion scopes with --run-libraries.")

    if isinstance(progress_libraries, list):
        completed_libraries = [
            str(entry.get("name")).strip() for entry in progress_libraries if str(entry.get("status") or "").strip() == "Done" and str(entry.get("name") or "").strip()
        ]
        if completed_libraries:
            lines.append(f"Completed libraries already seen in the log: {' | '.join(completed_libraries)}.")

    config_path = _extract_cli_option_value(suggested_command, "--config")
    if config_path:
        lines.append(f"Config path in the suggested command is: {config_path}.")

    normalized_original = _normalize_cli_whitespace(original_command)
    normalized_suggested = _normalize_cli_whitespace(suggested_command)
    if normalized_original and normalized_suggested and normalized_original != normalized_suggested:
        lines.append("Conflicting mode/scope flags were normalized before applying the detected phase/library scope.")
    return lines


def _analyze_incomplete_log_for_resume(log_path, cache_entry=None, config_name=None):
    try:
        content = _read_logscan_text(log_path, encoding="utf-8", errors="replace")
    except Exception:
        return None
    started_at_fallback = _extract_first_log_timestamp(content)

    analyzer = logscan.LogscanAnalyzer()
    try:
        analysis = analyzer.analyze_content(
            content,
            log_path=log_path,
            config_name=config_name,
            include_people_scan=False,
        )
    except Exception:
        return None

    summary = analysis.get("summary") if isinstance(analysis, dict) else None
    recommendations = analysis.get("recommendations") if isinstance(analysis, dict) else None
    if not isinstance(recommendations, list):
        recommendations = []
    if not isinstance(summary, dict):
        return None
    if summary.get("run_complete"):
        return None

    try:
        original_command = _inject_config_path_for_command(
            summary.get("run_command") or "",
            config_name=summary.get("config_name") or config_name,
        )
        config_path = _extract_cli_option_value(original_command, "--config")
        config_data = _load_progress_config(config_path) if config_path else {}
        selected_libraries = _extract_selected_libraries(original_command)[1]
        progress = analyzer.extract_progress(
            content,
            library_list=_get_progress_library_list(
                selected_libraries=selected_libraries,
                config_path=config_path,
                config_data=config_data,
            ),
            selected_libraries=selected_libraries,
        )
    except Exception:
        progress = {}
    if not isinstance(progress, dict):
        progress = {}

    phase_current = (progress.get("phase_current") or "").strip().lower() or None
    current_library = (progress.get("current_library") or "").strip() or None
    if not current_library:
        for entry in progress.get("libraries", []) or []:
            if entry.get("status") == "In progress" and entry.get("name"):
                current_library = str(entry.get("name")).strip()
                break

    current_collection = None
    collection_in_library_re = re.compile(r"^\s*(.+?)\s+Collection\s+in\s+.+$", re.IGNORECASE)
    running_collection_re = re.compile(r"^\s*Running\s+(.+?)\s+Collection\b", re.IGNORECASE)
    try:
        for raw_line in content.splitlines():
            if not raw_line:
                continue
            msg = raw_line.split("|", 1)[1].strip() if "|" in raw_line else raw_line.strip()
            msg = analyzer._strip_divider_wrappers(msg)
            match = running_collection_re.search(msg) or collection_in_library_re.search(msg)
            if match:
                candidate = str(match.group(1) or "").strip()
                if candidate:
                    current_collection = candidate
    except Exception:
        current_collection = None

    progress_libraries = progress.get("libraries") if isinstance(progress.get("libraries"), list) else []
    last_log_at = _extract_last_log_timestamp(content)
    timing_summary = _build_incomplete_run_timing_summary(
        started_at=summary.get("started_at") or started_at_fallback,
        last_log_at=last_log_at,
        maintenance_summary=summary.get("maintenance_summary"),
    )

    suggestions = _build_recovery_suggestions(
        original_command,
        phase_current=phase_current,
        current_library=current_library,
        current_collection=current_collection,
        progress_libraries=progress_libraries,
    )
    primary = suggestions[0] if suggestions else ""
    scope_completed = not primary and not suggestions
    explanation = []
    if primary:
        explanation = _build_resume_explanation(
            original_command,
            primary,
            phase_current=phase_current,
            current_library=current_library,
            current_collection=current_collection,
            finished_at=summary.get("finished_at"),
            progress_libraries=progress_libraries,
        )
    reason = _build_incomplete_resume_message(
        phase_current=phase_current,
        current_library=current_library,
        finished_at=summary.get("finished_at"),
    )
    if scope_completed:
        reason = _build_completed_scope_resume_message(
            phase_current=phase_current,
            current_library=current_library,
            finished_at=summary.get("finished_at"),
        )
    counts = summary.get("log_counts") if isinstance(summary.get("log_counts"), dict) else {}
    mtime = summary.get("log_mtime")
    if not isinstance(mtime, (int, float)) and isinstance(cache_entry, dict):
        mtime = cache_entry.get("mtime")
    created_at = summary.get("created_at")
    if not created_at and isinstance(cache_entry, dict):
        created_at = cache_entry.get("updated_at") or _iso_from_mtime(cache_entry.get("mtime"))
    if not created_at:
        created_at = _iso_from_mtime(mtime)
    run_key = summary.get("run_key")
    if not run_key:
        run_key_seed = f"incomplete|{log_path}|{mtime or 0}"
        run_key = hashlib.sha256(run_key_seed.encode("utf-8")).hexdigest()
    started_at = summary.get("started_at") or started_at_fallback
    scope_summary = _build_incomplete_scope_summary(
        original_command=original_command,
        suggested_command=primary,
        progress_libraries=progress_libraries,
    )
    progress_snapshot = _build_incomplete_progress_snapshot(
        progress,
        last_log_at=last_log_at,
        config_data=config_data,
        original_command=original_command,
    )
    maintenance_events = _build_maintenance_event_rows(summary.get("maintenance_summary"))

    return {
        "run_key": run_key,
        "started_at": started_at,
        "last_log_at": last_log_at,
        "finished_at": summary.get("finished_at"),
        "run_time_seconds": summary.get("run_time_seconds"),
        "kometa_version": summary.get("kometa_version"),
        "kometa_newest_version": summary.get("kometa_newest_version"),
        "config_name": summary.get("config_name") or config_name or "",
        "config_hash": summary.get("config_hash"),
        "run_command": original_command,
        "command_signature": summary.get("command_signature"),
        "section_runtimes": summary.get("section_runtimes") or {},
        "recommendations_count": len(recommendations),
        "recommendations": recommendations,
        "log_mtime": mtime,
        "log_size": summary.get("log_size"),
        "debug_count": counts.get("debug", 0),
        "info_count": counts.get("info", 0),
        "warning_count": counts.get("warning", 0),
        "error_count": counts.get("error", 0),
        "critical_count": counts.get("critical", 0),
        "trace_count": counts.get("trace", 0),
        "analysis_counts": summary.get("analysis_counts") if isinstance(summary.get("analysis_counts"), dict) else {},
        "library_counts": summary.get("library_counts") if isinstance(summary.get("library_counts"), dict) else {},
        "maintenance_summary": summary.get("maintenance_summary") if isinstance(summary.get("maintenance_summary"), dict) else {},
        "maintenance_had_pause": bool((summary.get("maintenance_summary") or {}).get("had_pause")),
        "quiet_period_summary": summary.get("quiet_period_summary") if isinstance(summary.get("quiet_period_summary"), dict) else {},
        "quickstart_run_marker": bool(summary.get("quickstart_run_marker")),
        "start_mode": summary.get("start_mode"),
        "config_line_count": summary.get("config_line_count"),
        "cache_line_count": summary.get("cache_line_count"),
        "created_at": created_at,
        "run_complete": False,
        "is_incomplete": True,
        "incomplete_log_name": Path(log_path).name,
        "incomplete_log_path": str(Path(log_path)),
        "phase_current": phase_current,
        "current_library": current_library,
        "current_collection": current_collection,
        "resume_reason": reason,
        "resume_primary": primary,
        "resume_recommendations": suggestions,
        "resume_explanation": explanation,
        "resume_scope_completed": scope_completed,
        "resume_timing_summary": timing_summary,
        "resume_scope_summary": scope_summary,
        "resume_progress_snapshot": progress_snapshot,
        "resume_maintenance_events": maintenance_events,
    }


def _build_incomplete_run_from_cache_entry(log_path, cache_entry=None, config_name=None):
    path = Path(log_path)
    cache_entry = cache_entry if isinstance(cache_entry, dict) else {}
    summary = cache_entry.get("summary") if isinstance(cache_entry.get("summary"), dict) else {}
    tool_name = _normalize_logscan_tool_name(summary.get("tool_name") or cache_entry.get("tool_name"))
    recommendations = cache_entry.get("recommendations")
    if not isinstance(recommendations, list):
        recommendations = []
    try:
        stats = path.stat()
        mtime = stats.st_mtime
        size = stats.st_size
    except Exception:
        mtime = cache_entry.get("mtime") if isinstance(cache_entry.get("mtime"), (int, float)) else None
        size = cache_entry.get("size") if isinstance(cache_entry.get("size"), int) else None
    counts = summary.get("log_counts") if isinstance(summary.get("log_counts"), dict) else {}
    run_key = summary.get("run_key") or cache_entry.get("run_key")
    if not run_key:
        run_key_seed = f"incomplete|cached|{path}|{mtime or 0}|{size or 0}"
        run_key = hashlib.sha256(run_key_seed.encode("utf-8")).hexdigest()
    created_at = summary.get("created_at")
    if not created_at:
        created_at = cache_entry.get("updated_at") or _iso_from_mtime(mtime)
    started_at = summary.get("started_at")
    if not started_at:
        try:
            started_at = _extract_first_log_timestamp(_read_logscan_text(path, encoding="utf-8", errors="replace"))
        except Exception:
            started_at = None
    original_command = summary.get("run_command") or ""
    if tool_name == "kometa":
        original_command = _inject_config_path_for_command(
            original_command,
            config_name=summary.get("config_name") or config_name,
        )
    progress_snapshot = summary.get("progress_snapshot") if isinstance(summary.get("progress_snapshot"), dict) else {}
    if not progress_snapshot:
        progress_snapshot = cache_entry.get("resume_progress_snapshot") if isinstance(cache_entry.get("resume_progress_snapshot"), dict) else {}
    return {
        "run_key": run_key,
        "tool_name": tool_name,
        "started_at": started_at,
        "finished_at": summary.get("finished_at"),
        "run_time_seconds": summary.get("run_time_seconds"),
        "kometa_version": summary.get("kometa_version"),
        "kometa_newest_version": summary.get("kometa_newest_version"),
        "config_name": summary.get("config_name") or config_name or "",
        "config_hash": summary.get("config_hash"),
        "run_command": original_command,
        "command_signature": summary.get("command_signature"),
        "section_runtimes": summary.get("section_runtimes") or {},
        "recommendations_count": len(recommendations),
        "recommendations": recommendations,
        "log_mtime": mtime,
        "log_size": summary.get("log_size") if isinstance(summary.get("log_size"), int) else size,
        "debug_count": counts.get("debug", 0),
        "info_count": counts.get("info", 0),
        "warning_count": counts.get("warning", 0),
        "error_count": counts.get("error", 0),
        "critical_count": counts.get("critical", 0),
        "trace_count": counts.get("trace", 0),
        "analysis_counts": summary.get("analysis_counts") if isinstance(summary.get("analysis_counts"), dict) else {},
        "library_counts": summary.get("library_counts") if isinstance(summary.get("library_counts"), dict) else {},
        "maintenance_summary": summary.get("maintenance_summary") if isinstance(summary.get("maintenance_summary"), dict) else {},
        "maintenance_had_pause": bool((summary.get("maintenance_summary") or {}).get("had_pause")),
        "quiet_period_summary": summary.get("quiet_period_summary") if isinstance(summary.get("quiet_period_summary"), dict) else {},
        "quickstart_run_marker": bool(summary.get("quickstart_run_marker")),
        "start_mode": summary.get("start_mode") or cache_entry.get("start_mode"),
        "config_line_count": summary.get("config_line_count"),
        "cache_line_count": summary.get("cache_line_count"),
        "created_at": created_at,
        "run_complete": False,
        "is_incomplete": True,
        "incomplete_log_name": path.name,
        "incomplete_log_path": str(path),
        "phase_current": cache_entry.get("phase_current"),
        "current_library": cache_entry.get("current_library"),
        "current_collection": cache_entry.get("current_collection"),
        "progress_snapshot": progress_snapshot,
        "resume_progress_snapshot": (progress_snapshot if isinstance(progress_snapshot, dict) else {}),
        "resume_reason": cache_entry.get("resume_reason") or "Run appears incomplete. Open the report for more detail or download the log for investigation.",
        "resume_primary": cache_entry.get("resume_primary") or "",
        "resume_recommendations": cache_entry.get("resume_recommendations") if isinstance(cache_entry.get("resume_recommendations"), list) else [],
        "resume_explanation": cache_entry.get("resume_explanation") if isinstance(cache_entry.get("resume_explanation"), list) else [],
    }


def _build_incomplete_resume_cache_fields(log_path, cache_entry=None, config_name=None):
    cache_entry = cache_entry if isinstance(cache_entry, dict) else {}
    parsed = _analyze_incomplete_log_for_resume(log_path, cache_entry=cache_entry, config_name=config_name)
    if not isinstance(parsed, dict):
        return {}
    fields = {}
    for key in (
        "phase_current",
        "current_library",
        "current_collection",
        "resume_reason",
        "resume_primary",
        "resume_recommendations",
        "resume_explanation",
        "resume_progress_snapshot",
        "resume_scope_completed",
        "resume_timing_summary",
        "resume_scope_summary",
        "resume_maintenance_events",
    ):
        value = parsed.get(key)
        if value is None:
            continue
        fields[key] = value
    return fields


def _build_incomplete_log_fallback(log_path, cache_entry=None, config_name=None):
    path = Path(log_path)
    cache_entry = cache_entry if isinstance(cache_entry, dict) else {}
    tool_name = _normalize_logscan_tool_name(cache_entry.get("tool_name"))
    try:
        stats = path.stat()
        mtime = stats.st_mtime
        size = stats.st_size
    except Exception:
        mtime = cache_entry.get("mtime") if isinstance(cache_entry.get("mtime"), (int, float)) else None
        size = cache_entry.get("size") if isinstance(cache_entry.get("size"), int) else None
    run_key = cache_entry.get("run_key")
    if not run_key:
        run_key_seed = f"incomplete|fallback|{path}|{mtime or 0}|{size or 0}"
        run_key = hashlib.sha256(run_key_seed.encode("utf-8")).hexdigest()
    created_at = cache_entry.get("updated_at") or _iso_from_mtime(mtime)
    try:
        started_at = _extract_first_log_timestamp(_read_logscan_text(path, encoding="utf-8", errors="replace"))
    except Exception:
        started_at = None
    return {
        "run_key": run_key,
        "tool_name": tool_name,
        "started_at": started_at,
        "finished_at": None,
        "run_time_seconds": None,
        "kometa_version": "",
        "kometa_newest_version": "",
        "config_name": config_name or "",
        "config_hash": None,
        "run_command": "",
        "command_signature": "",
        "section_runtimes": {},
        "recommendations_count": 0,
        "recommendations": [],
        "log_mtime": mtime,
        "log_size": size,
        "debug_count": 0,
        "info_count": 0,
        "warning_count": 0,
        "error_count": 0,
        "critical_count": 0,
        "trace_count": 0,
        "analysis_counts": {},
        "library_counts": {},
        "maintenance_summary": {},
        "maintenance_had_pause": False,
        "quiet_period_summary": {},
        "quickstart_run_marker": False,
        "start_mode": cache_entry.get("start_mode"),
        "config_line_count": None,
        "cache_line_count": None,
        "created_at": created_at,
        "run_complete": False,
        "is_incomplete": True,
        "incomplete_log_name": path.name,
        "incomplete_log_path": str(path),
        "phase_current": None,
        "current_library": None,
        "current_collection": None,
        "resume_reason": "Run appears incomplete. Detailed parse data is not available, but the log is preserved for investigation.",
        "resume_primary": "",
        "resume_recommendations": [],
        "resume_explanation": ["Quickstart preserved this incomplete log file even though detailed parsing was unavailable."],
    }


def _get_logscan_incomplete_runs(limit=100, config_name=None):
    if limit is None:
        safe_limit = None
    else:
        safe_limit = max(0, min(int(limit or 0), 1000000))
    if safe_limit == 0:
        return []
    ingest_cache = _load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    if not isinstance(cache_logs, dict):
        return []

    candidates = []
    for path_key, entry in cache_logs.items():
        if not isinstance(entry, dict) or entry.get("run_complete") is True:
            continue
        try:
            path = Path(path_key).resolve()
        except Exception:
            continue
        if not path.exists() or not path.is_file():
            continue
        try:
            mtime = path.stat().st_mtime
        except Exception:
            mtime = entry.get("mtime") if isinstance(entry.get("mtime"), (int, float)) else 0
        candidates.append((float(mtime or 0), path, entry))

    candidates.sort(key=lambda item: item[0], reverse=True)
    parsed_runs = []
    selected_candidates = candidates if safe_limit is None else candidates[:safe_limit]
    for _, path, entry in selected_candidates:
        if isinstance(entry.get("summary"), dict):
            parsed = _build_incomplete_run_from_cache_entry(path, cache_entry=entry, config_name=config_name)
        else:
            parsed = _build_incomplete_log_fallback(path, cache_entry=entry, config_name=config_name)
        if parsed:
            parsed_runs.append(parsed)
    return parsed_runs


def _get_logscan_incomplete_run(run_key, config_name=None):
    if not run_key:
        return None
    ingest_cache = _load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    if not isinstance(cache_logs, dict):
        return None
    for path_key, entry in cache_logs.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("run_complete") is True:
            continue
        if entry.get("run_key") != run_key:
            continue
        path = Path(path_key)
        if not path.exists() or not path.is_file():
            return None
        if isinstance(entry.get("summary"), dict):
            return _build_incomplete_run_from_cache_entry(path, cache_entry=entry, config_name=config_name)
        if _normalize_logscan_tool_name(entry.get("tool_name")) != "kometa":
            return _build_incomplete_log_fallback(path, cache_entry=entry, config_name=config_name)
        parsed = _analyze_incomplete_log_for_resume(path, cache_entry=entry, config_name=config_name)
        if parsed:
            return parsed
        return _build_incomplete_log_fallback(path, cache_entry=entry, config_name=config_name)
    return None


def _get_incomplete_resume_runs(limit=25, config_name=None):
    safe_limit = max(0, min(int(limit or 0), 100))
    if safe_limit == 0:
        return []
    ingest_cache = _load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    if not isinstance(cache_logs, dict):
        return []

    is_running = helpers.is_kometa_running()
    candidates = []
    for path_key, entry in cache_logs.items():
        if not isinstance(entry, dict):
            continue
        if _normalize_logscan_tool_name(entry.get("tool_name")) != "kometa":
            continue
        try:
            path = Path(path_key).resolve()
        except Exception:
            continue
        if not path.exists() or not path.is_file():
            continue
        if is_running and path.name.lower() == "meta.log":
            continue
        # Prefer ingest-cache mtime to preserve analyzed-run ordering; live
        # meta.log is refreshed separately below when Kometa is not running.
        mtime = entry.get("mtime")
        if not isinstance(mtime, (int, float)):
            try:
                mtime = path.stat().st_mtime
            except Exception:
                mtime = 0
        candidates.append((float(mtime), path, entry))

    try:
        live_meta = (helpers.get_kometa_log_dir() / "meta.log").resolve()
    except Exception:
        live_meta = None
    if live_meta and live_meta.exists() and live_meta.is_file():
        if not is_running:
            try:
                live_mtime = live_meta.stat().st_mtime
            except Exception:
                live_mtime = 0
            # Replace any cached candidate for live meta with a fresh mtime candidate.
            candidates = [item for item in candidates if item[1] != live_meta]
            live_entry = cache_logs.get(str(live_meta), {}) if isinstance(cache_logs, dict) else {}
            if not isinstance(live_entry, dict):
                live_entry = {}
            if not isinstance(live_entry.get("mtime"), (int, float)):
                live_entry["mtime"] = live_mtime
            live_entry.setdefault("run_complete", False)
            candidates.append((float(live_mtime), live_meta, live_entry))

    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates:
        return []

    # Only evaluate the latest run candidate. Older incomplete logs may no longer
    # be actionable once a newer run has completed.
    _, path, entry = candidates[0]
    parsed = _analyze_incomplete_log_for_resume(path, cache_entry=entry, config_name=config_name)
    if not parsed:
        return []
    return [parsed]


def _build_latest_incomplete_resume_hint():
    incomplete_runs = _get_incomplete_resume_runs(limit=1, config_name=session.get("config_name"))
    if not incomplete_runs:
        return None
    latest = incomplete_runs[0]

    session_config = (session.get("config_name") or "default").strip()
    summary_config = (latest.get("config_name") or "").strip()
    context_mismatch = bool(summary_config and session_config and summary_config != session_config)

    return {
        "message": latest.get("resume_reason") or "Last run appears incomplete.",
        "phase_current": latest.get("phase_current"),
        "current_library": latest.get("current_library"),
        "current_collection": latest.get("current_collection"),
        "original_command": latest.get("run_command") or "",
        "suggested_command": latest.get("resume_primary") or "",
        "log_name": latest.get("incomplete_log_name") or "",
        "log_path": latest.get("incomplete_log_path") or "",
        "config_name": summary_config,
        "context_mismatch": context_mismatch,
        "explanation": latest.get("resume_explanation") if isinstance(latest.get("resume_explanation"), list) else [],
        "scope_completed": bool(latest.get("resume_scope_completed")),
        "timing_summary": latest.get("resume_timing_summary") if isinstance(latest.get("resume_timing_summary"), dict) else {},
        "scope_summary": latest.get("resume_scope_summary") if isinstance(latest.get("resume_scope_summary"), dict) else {},
        "progress_snapshot": latest.get("resume_progress_snapshot") if isinstance(latest.get("resume_progress_snapshot"), dict) else {},
        "maintenance_events": latest.get("resume_maintenance_events") if isinstance(latest.get("resume_maintenance_events"), list) else [],
    }


def _logscan_needs_reingest(cache_logs, log_dir):
    return bool(_get_logscan_delta_files(log_dir=log_dir, include_archive=True))


def _get_logscan_invalid_archived_logs(log_dir=None, limit=None):
    log_dir = Path(log_dir) if log_dir else helpers.get_kometa_log_dir()
    ingest_cache = _load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    if not isinstance(cache_logs, dict):
        cache_logs = {}

    invalid_logs = []
    kometa_analyzer = None
    for path in _get_logscan_log_files(log_dir=log_dir, include_archive=True):
        if _classify_logscan_file_location(path, log_dir=log_dir) != "archive":
            continue
        cache_key = str(path.resolve())
        cache_entry = cache_logs.get(cache_key)
        if _logscan_cache_entry_matches(path, cache_entry=cache_entry):
            continue

        tool_name = _detect_logscan_tool_from_path(path, log_dir=log_dir)
        reason = "unrecognized"
        reason_detail = None
        try:
            content = _read_logscan_text(path, encoding="utf-8", errors="replace")
            if tool_name == "imagemaid":
                result = _analyze_imagemaid_log_content(content, log_path=path)
            else:
                if kometa_analyzer is None:
                    kometa_analyzer = logscan.LogscanAnalyzer()
                result = kometa_analyzer.analyze_content(content, log_path=path, include_people_scan=False)
            summary = result.get("summary") if isinstance(result, dict) else None
            if summary:
                continue
            if not str(content or "").strip():
                reason = "empty"
        except Exception as exc:
            reason = "read_error"
            reason_detail = str(exc)

        try:
            stats = path.stat()
            size = int(stats.st_size)
            mtime = stats.st_mtime
        except Exception:
            size = None
            mtime = None
        invalid_logs.append(
            {
                "name": path.name,
                "path": cache_key,
                "tool_name": tool_name,
                "reason": reason,
                "reason_detail": reason_detail,
                "size": size,
                "mtime": mtime,
            }
        )

    invalid_logs.sort(key=lambda item: item.get("mtime") or 0, reverse=True)
    if limit is None:
        return invalid_logs
    try:
        safe_limit = max(0, int(limit))
    except (TypeError, ValueError):
        safe_limit = 0
    return invalid_logs[:safe_limit]


def _logscan_ingest_health(log_dir=None):
    log_dir = Path(log_dir) if log_dir else helpers.get_kometa_log_dir()
    log_dir_exists = log_dir.exists()
    imagemaid_log_dir = _get_logscan_live_dir("imagemaid")
    imagemaid_dir_exists = imagemaid_log_dir.exists()
    log_files = _get_logscan_log_files(log_dir=log_dir, include_archive=True) if (log_dir_exists or imagemaid_dir_exists) else []
    ingest_cache = _load_logscan_ingest_cache()
    cache_logs = ingest_cache["logs"]
    missing = []
    incomplete = []
    tracked = 0
    complete = 0
    pending_active = False
    latest_updated = None
    kometa_running = helpers.is_kometa_running()
    imagemaid_running = helpers.is_imagemaid_running()

    for path in log_files:
        tool_name = _detect_logscan_tool_from_path(path, log_dir=log_dir)
        if tool_name == "kometa" and kometa_running and path.name.lower() == "meta.log":
            pending_active = True
            continue
        if tool_name == "imagemaid" and imagemaid_running and _classify_logscan_file_location(path, log_dir=log_dir) == "live":
            pending_active = True
            continue
        entry = cache_logs.get(str(path.resolve()))
        if not entry:
            missing.append(path.name)
            continue
        tracked += 1
        updated_at = entry.get("updated_at")
        if updated_at and (latest_updated is None or updated_at > latest_updated):
            latest_updated = updated_at
        if entry.get("run_complete"):
            complete += 1
        else:
            incomplete.append(path.name)

    total = len(log_files) - (1 if pending_active else 0)
    if total < 0:
        total = 0
    needs_reingest = bool(missing or incomplete)
    invalid_archived = _get_logscan_invalid_archived_logs(log_dir=log_dir)

    return {
        "source": "health",
        "log_dir_missing": not log_dir_exists and not imagemaid_dir_exists,
        "total": total,
        "tracked": tracked,
        "complete": complete,
        "missing": len(missing),
        "incomplete": len(incomplete),
        "missing_sample": missing[:5],
        "incomplete_sample": incomplete[:5],
        "invalid_archived_count": len(invalid_archived),
        "invalid_archived_sample": [entry.get("name") for entry in invalid_archived[:5] if entry.get("name")],
        "needs_reingest": needs_reingest,
        "pending_active": pending_active,
        "last_updated": latest_updated,
    }


def _start_logscan_auto_reingest(log_dir):
    if logscan_ingest_lock.locked():
        return False
    snapshot = _logscan_reingest_snapshot()
    if snapshot.get("status") == "running":
        return False
    job_id = secrets.token_urlsafe(8)
    _update_logscan_reingest_state(
        status="running",
        job_id=job_id,
        trigger="auto",
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=None,
        total=0,
        scanned=0,
        ingested=0,
        duplicates=0,
        skipped_incomplete=0,
        skipped_invalid=0,
        errors=0,
        current_file=None,
        missing_people_unique=0,
        missing_people_logs=0,
        missing_people_log_ready=False,
        missing_people_log_lines=0,
        sample_incomplete=[],
        sample_errors=[],
    )
    thread = threading.Thread(target=_run_logscan_reingest_job, args=(job_id, False), daemon=True, name="logscan-auto-reingest")
    thread.start()
    return True


def _ingest_completed_live_logs(tool_name="kometa", log_dir=None):
    tool_name = _normalize_logscan_tool_name(tool_name)
    if tool_name == "kometa" and helpers.is_kometa_running():
        return {"ingested": 0, "archived": 0}
    if tool_name == "imagemaid" and helpers.is_imagemaid_running():
        return {"ingested": 0, "archived": 0}

    live_dir = _get_logscan_live_dir(tool_name, log_dir=log_dir if tool_name == "kometa" else None)
    if not live_dir.exists():
        return {"ingested": 0, "archived": 0}

    if tool_name == "kometa":
        candidates = [live_dir / "meta.log"]
    else:
        candidates = [
            path for path in sorted(live_dir.glob("*.log*"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True) if path.is_file() and ".log" in path.name.lower()
        ]

    ingest_cache = _load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    if not isinstance(cache_logs, dict):
        cache_logs = {}
    cache_dirty = False
    ingested = 0
    archived = 0

    analyzer = logscan.LogscanAnalyzer()
    archive_dir = _get_logscan_archive_dir(tool_name)

    for path in candidates:
        try:
            path = Path(path)
            if not path.exists() or not path.is_file():
                continue
            stats = path.stat()
            cache_key = str(path.resolve())
            cached_entry = cache_logs.get(cache_key, {})
            if _logscan_cache_entry_matches(path, cache_entry=cached_entry, stats=stats):
                continue

            content = _read_logscan_text(path, encoding="utf-8", errors="replace")
            if tool_name == "imagemaid":
                result = _analyze_imagemaid_log_content(content, log_path=path)
            else:
                result = analyzer.analyze_content(content, log_path=path, include_people_scan=False)
            summary = result.get("summary") if isinstance(result, dict) else None
            recommendations = result.get("recommendations") if isinstance(result, dict) else None
            if not isinstance(recommendations, list):
                recommendations = []
            if not isinstance(summary, dict):
                continue
            if not summary.get("run_complete"):
                incomplete_cache_fields = {}
                if tool_name == "kometa":
                    incomplete_cache_fields = _build_incomplete_resume_cache_fields(
                        path,
                        cache_entry={
                            "mtime": stats.st_mtime,
                            "size": stats.st_size,
                            "run_key": summary.get("run_key"),
                            "tool_name": tool_name,
                            "run_complete": False,
                            "summary": summary,
                            "recommendations": recommendations,
                        },
                        config_name=summary.get("config_name"),
                    )
                cache_logs[cache_key] = {
                    "mtime": stats.st_mtime,
                    "size": stats.st_size,
                    "run_key": summary.get("run_key"),
                    "tool_name": tool_name,
                    "run_complete": False,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "summary": summary,
                    "recommendations": recommendations,
                    **incomplete_cache_fields,
                }
                cache_dirty = True
                continue

            if tool_name == "kometa":
                summary["progress_snapshot"] = _build_completed_log_progress_snapshot(
                    summary=summary,
                    content=content,
                    analyzer=analyzer,
                )
            cached_run_key = cached_entry.get("run_key")
            if not (cached_entry.get("run_complete") is True and cached_run_key == summary.get("run_key")):
                if database.save_log_run(summary, recommendations=recommendations):
                    ingested += 1

            cache_logs[cache_key] = {
                "mtime": stats.st_mtime,
                "size": stats.st_size,
                "run_key": summary.get("run_key"),
                "tool_name": tool_name,
                "run_complete": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            cache_dirty = True

            if tool_name == "kometa":
                archived_path = _archive_log_file(path, archive_dir, log_dir=live_dir, allow_live_meta=True)
            else:
                archived_path = _archive_log_file(path, archive_dir, log_dir=live_dir)
            if archived_path:
                try:
                    archived_stats = archived_path.stat()
                    cache_logs.pop(cache_key, None)
                    cache_logs[str(archived_path.resolve())] = {
                        "mtime": archived_stats.st_mtime,
                        "size": archived_stats.st_size,
                        "run_key": summary.get("run_key"),
                        "tool_name": tool_name,
                        "run_complete": True,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    cache_dirty = True
                    archived += 1
                except Exception:
                    pass
        except Exception:
            continue

    if cache_dirty:
        ingest_cache["logs"] = cache_logs
        _save_logscan_ingest_cache(ingest_cache)
        _prune_logscan_archive(archive_dir)
    return {"ingested": ingested, "archived": archived}


def _archive_log_file(path, archive_dir, log_dir=None, allow_live_meta=False):
    try:
        path = Path(path)
        if not path.exists() or not path.is_file():
            return None
        if _is_logscan_maintenance_sidecar(path):
            return None
        if path.name.lower() == "meta.log" and not allow_live_meta:
            return None
        if log_dir and path.resolve().parent != Path(log_dir).resolve():
            return None
        archive_dir = Path(archive_dir)
        archive_dir.mkdir(parents=True, exist_ok=True)
        src_stats = path.stat()
        should_compress = not _is_logscan_gzip_path(path)
        preferred_suffix = ".log.gz" if should_compress else None
        dest = _build_logscan_archive_destination(path, archive_dir, stats=src_stats, preferred_suffix=preferred_suffix)
        if dest.exists():
            path.unlink()
            return dest
        if should_compress:
            try:
                with path.open("rb") as source, gzip.open(dest, "wb") as target:
                    shutil.copyfileobj(source, target)
                os.utime(dest, (src_stats.st_atime, src_stats.st_mtime))
                path.unlink()
            except Exception:
                try:
                    if dest.exists():
                        dest.unlink()
                except Exception:
                    pass
                raise
        else:
            shutil.move(str(path), str(dest))
        return dest
    except Exception:
        return None


logscan_archive_result = _normalize_logscan_archive_filenames()
if logscan_archive_result.get("renamed"):
    helpers.ts_log(
        f"Normalized {logscan_archive_result['renamed']} archived log file(s) to the canonical archive layout.",
        level="INFO",
    )
if logscan_archive_result.get("errors"):
    for msg in logscan_archive_result["errors"]:
        helpers.ts_log(msg, level="WARNING")


def _archive_finished_live_meta_log_if_idle(log_dir=None):
    log_dir = Path(log_dir) if log_dir else helpers.get_kometa_log_dir()
    live_path = (log_dir / "meta.log").resolve()
    if helpers.is_kometa_running():
        return None
    if not live_path.exists() or not live_path.is_file():
        return None

    ingest_cache = _load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    if not isinstance(cache_logs, dict):
        return None

    live_key = str(live_path)
    live_entry = cache_logs.get(live_key)
    if not isinstance(live_entry, dict):
        return None
    if live_entry.get("run_complete") is not True:
        return None
    if not live_entry.get("run_key"):
        return None

    archive_dir = _get_logscan_archive_dir()
    archived_path = _archive_log_file(live_path, archive_dir, log_dir=log_dir, allow_live_meta=True)
    if not archived_path:
        return None

    try:
        archived_stats = archived_path.stat()
        archived_key = str(archived_path.resolve())
    except Exception:
        return None

    updated_entry = dict(live_entry)
    updated_entry["mtime"] = archived_stats.st_mtime
    updated_entry["size"] = archived_stats.st_size
    updated_entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    cache_logs.pop(live_key, None)
    cache_logs[archived_key] = updated_entry
    ingest_cache["logs"] = cache_logs
    _save_logscan_ingest_cache(ingest_cache)
    _prune_logscan_archive(archive_dir)
    return archived_path


def _archive_rotated_logs(log_dir):
    archived = 0
    archive_dir = _get_logscan_archive_dir()
    for path in Path(log_dir).glob("*meta*.log*"):
        if not path.is_file():
            continue
        suffixes = [suffix.lower() for suffix in path.suffixes]
        if suffixes and suffixes[-1] in (".gz", ".zip", ".7z"):
            continue
        if ".log" not in path.name.lower():
            continue
        if path.name.lower() == "meta.log":
            continue
        if _archive_log_file(path, archive_dir, log_dir=log_dir):
            archived += 1
    _prune_logscan_archive(archive_dir)
    return archived


def _archive_rotated_log_and_update_cache(path, cache_logs, archive_dir, run_key=None, run_complete=False):
    try:
        source_path = Path(path).resolve()
    except Exception:
        return None
    if source_path.name.lower() == "meta.log":
        return None
    archived_path = _archive_log_file(source_path, archive_dir, log_dir=source_path.parent)
    if not archived_path:
        return None
    try:
        archived_stats = archived_path.stat()
        archived_key = str(archived_path.resolve())
    except Exception:
        return None
    source_key = str(source_path)
    existing_entry = cache_logs.get(source_key, {}) if isinstance(cache_logs, dict) else {}
    if not isinstance(existing_entry, dict):
        existing_entry = {}
    updated_entry = dict(existing_entry)
    updated_entry["mtime"] = archived_stats.st_mtime
    updated_entry["size"] = archived_stats.st_size
    updated_entry["run_complete"] = bool(run_complete)
    updated_entry["tool_name"] = _detect_logscan_tool_from_path(source_path)
    updated_entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    if run_key:
        updated_entry["run_key"] = run_key
    if isinstance(cache_logs, dict):
        cache_logs.pop(source_key, None)
        cache_logs[archived_key] = updated_entry
    return archived_path


def _prune_logscan_archive(archive_dir):
    tool_name = _detect_logscan_tool_from_path(Path(archive_dir))
    keep_limit = _get_logscan_keep_limit(tool_name)
    if keep_limit <= 0:
        return 0
    archive_dir = Path(archive_dir)
    if not archive_dir.exists():
        return 0
    candidates = []
    for path in archive_dir.glob("*.log*"):
        if not path.is_file():
            continue
        if _is_logscan_maintenance_sidecar(path):
            continue
        suffixes = [suffix.lower() for suffix in path.suffixes]
        if suffixes and suffixes[-1] in (".zip", ".7z"):
            continue
        if ".log" not in path.name.lower():
            continue
        candidates.append(path)
    if len(candidates) <= keep_limit:
        return 0
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    to_remove = candidates[keep_limit:]
    removed = 0
    for path in to_remove:
        try:
            path.unlink()
            removed += 1
        except Exception:
            continue
    if removed:
        cache = _load_logscan_ingest_cache()
        logs = cache.get("logs", {})
        changed = False
        for path in to_remove:
            key = str(path.resolve())
            if key in logs:
                logs.pop(key, None)
                changed = True
        if changed:
            cache["logs"] = logs
            _save_logscan_ingest_cache(cache)
    return removed


def _perform_logscan_reingest(reset, job_id=None, update_state=True):
    if not logscan_ingest_lock.acquire(blocking=False):
        message = "Logscan ingest already running."
        if update_state:
            _update_logscan_reingest_state(status="error", error=message, finished_at=datetime.now(timezone.utc).isoformat())
        return {"success": False, "error": message}
    started_at = datetime.now(timezone.utc).isoformat()
    if update_state:
        _update_logscan_reingest_state(
            status="running",
            job_id=job_id,
            started_at=started_at,
            finished_at=None,
            total=0,
            scanned=0,
            ingested=0,
            duplicates=0,
            skipped_incomplete=0,
            skipped_invalid=0,
            errors=0,
            current_file=None,
            missing_people_unique=0,
            missing_people_logs=0,
            missing_people_log_ready=False,
            missing_people_log_lines=0,
            sample_incomplete=[],
            sample_errors=[],
        )

    def _extract_fake_people_header(text, max_lines=200):
        header_lines = []
        for line in text.splitlines():
            header_lines.append(line)
            if "Locating config..." in line:
                break
            if len(header_lines) >= max_lines:
                break
        return "\n".join(header_lines).rstrip()

    try:
        ingest_cache = _load_logscan_ingest_cache()
        cache_dirty = False
        if reset:
            database.clear_log_runs()
            ingest_cache = {"version": 1, "logs": {}}
            _clear_logscan_ingest_cache()
            cache_dirty = True
        cache_logs = ingest_cache["logs"]

        kometa_log_dir = helpers.get_kometa_log_dir()
        imagemaid_log_dir = _get_logscan_live_dir("imagemaid")
        if not kometa_log_dir.exists() and not imagemaid_log_dir.exists():
            message = f"Log folders not found at: {kometa_log_dir} or {imagemaid_log_dir}"
            if update_state:
                _update_logscan_reingest_state(status="error", error=message, finished_at=datetime.now(timezone.utc).isoformat())
            return {"success": False, "error": message}

        log_files = _get_logscan_log_files(log_dir=kometa_log_dir, include_archive=True) if reset else _get_logscan_delta_files(log_dir=kometa_log_dir, include_archive=True)
        total_files = len(log_files)
        if update_state:
            _update_logscan_reingest_state(total=total_files)

        analyzer = logscan.LogscanAnalyzer()
        preload_path = next((path for path in log_files if _detect_logscan_tool_from_path(path, log_dir=kometa_log_dir) == "kometa"), None)
        if preload_path:
            analyzer.preload_people_index(preload_path)
        ingested = 0
        duplicates = 0
        skipped_incomplete = 0
        skipped_invalid = 0
        errors = 0
        missing_people_unique = set()
        missing_people_logs = 0
        missing_people_blocks = []
        missing_people_seen_blocks = set()
        missing_people_seen_names = set()
        missing_people_header = None
        sample_incomplete = []
        sample_errors = []

        for idx, path in enumerate(log_files, start=1):
            if update_state:
                _update_logscan_reingest_state(current_file=path.name, scanned=max(0, idx - 1))
            try:
                stats = path.stat()
                cache_key = str(path.resolve())
                cached_entry = cache_logs.get(cache_key, {})
                cached_run_key = cached_entry.get("run_key")
                skip_save_if_cached = cached_entry.get("run_complete") is True and cached_run_key
                tool_name = _detect_logscan_tool_from_path(path, log_dir=kometa_log_dir)
                live_dir = _get_logscan_live_dir(tool_name, log_dir=kometa_log_dir if tool_name == "kometa" else None)
                archive_dir = _get_logscan_archive_dir(tool_name)

                content = _read_logscan_text(path, encoding="utf-8", errors="replace")
                if tool_name == "imagemaid":
                    result = _analyze_imagemaid_log_content(content, log_path=path)
                else:
                    result = analyzer.analyze_content(
                        content,
                        log_path=path,
                        include_people_scan=True,
                    )
                summary = result.get("summary") if isinstance(result, dict) else None
                if not summary:
                    skipped_invalid += 1
                    if path.parent.resolve() == live_dir.resolve() and path.name.lower() != "meta.log":
                        archived_path = _archive_rotated_log_and_update_cache(
                            path,
                            cache_logs,
                            archive_dir,
                            run_key=cached_run_key,
                            run_complete=False,
                        )
                        if archived_path:
                            cache_dirty = True
                    continue
                if not summary.get("started_at"):
                    first_log_timestamp = _extract_first_log_timestamp(content)
                    if first_log_timestamp:
                        summary["started_at"] = first_log_timestamp
                if not summary.get("run_complete"):
                    skipped_incomplete += 1
                    if len(sample_incomplete) < 5:
                        sample_incomplete.append(path.name)
                    incomplete_recommendations = result.get("recommendations") if isinstance(result, dict) else None
                    if not isinstance(incomplete_recommendations, list):
                        incomplete_recommendations = []
                    incomplete_cache_fields = {}
                    if tool_name == "kometa":
                        incomplete_cache_fields = _build_incomplete_resume_cache_fields(
                            path,
                            cache_entry={
                                "mtime": stats.st_mtime,
                                "size": stats.st_size,
                                "run_key": summary.get("run_key"),
                                "tool_name": tool_name,
                                "run_complete": False,
                                "summary": summary,
                                "recommendations": incomplete_recommendations,
                                "start_mode": summary.get("start_mode"),
                            },
                            config_name=summary.get("config_name"),
                        )
                    cache_logs[cache_key] = {
                        "mtime": stats.st_mtime,
                        "size": stats.st_size,
                        "run_key": summary.get("run_key"),
                        "tool_name": tool_name,
                        "run_complete": False,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "summary": {
                            "run_key": summary.get("run_key"),
                            "tool_name": tool_name,
                            "started_at": summary.get("started_at"),
                            "finished_at": summary.get("finished_at"),
                            "run_time_seconds": summary.get("run_time_seconds"),
                            "kometa_version": summary.get("kometa_version"),
                            "kometa_newest_version": summary.get("kometa_newest_version"),
                            "config_name": summary.get("config_name"),
                            "config_hash": summary.get("config_hash"),
                            "run_command": summary.get("run_command"),
                            "command_signature": summary.get("command_signature"),
                            "section_runtimes": summary.get("section_runtimes") if isinstance(summary.get("section_runtimes"), dict) else {},
                            "log_size": summary.get("log_size"),
                            "log_counts": summary.get("log_counts") if isinstance(summary.get("log_counts"), dict) else {},
                            "analysis_counts": summary.get("analysis_counts") if isinstance(summary.get("analysis_counts"), dict) else {},
                            "library_counts": summary.get("library_counts") if isinstance(summary.get("library_counts"), dict) else {},
                            "maintenance_summary": summary.get("maintenance_summary") if isinstance(summary.get("maintenance_summary"), dict) else {},
                            "quiet_period_summary": summary.get("quiet_period_summary") if isinstance(summary.get("quiet_period_summary"), dict) else {},
                            "progress_snapshot": summary.get("progress_snapshot") if isinstance(summary.get("progress_snapshot"), dict) else {},
                            "quickstart_run_marker": bool(summary.get("quickstart_run_marker")),
                            "start_mode": summary.get("start_mode"),
                            "config_line_count": summary.get("config_line_count"),
                            "cache_line_count": summary.get("cache_line_count"),
                            "created_at": summary.get("created_at"),
                        },
                        "start_mode": summary.get("start_mode"),
                        "recommendations": incomplete_recommendations,
                        **incomplete_cache_fields,
                    }
                    cache_dirty = True
                    if path.parent.resolve() == live_dir.resolve() and path.name.lower() != "meta.log":
                        archived_path = _archive_rotated_log_and_update_cache(
                            path,
                            cache_logs,
                            archive_dir,
                            run_key=summary.get("run_key"),
                            run_complete=False,
                        )
                        if archived_path:
                            cache_dirty = True
                    continue
                missing_people = result.get("missing_people") if tool_name == "kometa" and isinstance(result, dict) else None
                if missing_people:
                    missing_people_logs += 1
                    missing_people_unique.update({name.lower() for name in missing_people})
                    if missing_people_header is None:
                        missing_people_header = _extract_fake_people_header(content)
                people_items = analyzer.collect_missing_people_lines(content, available_index=analyzer._people_index)
                if people_items:
                    for item in people_items:
                        names = {name for name in item.get("names", set()) if name in missing_people_unique}
                        if not names:
                            continue
                        if names.issubset(missing_people_seen_names):
                            continue
                        block = item.get("block")
                        if block and block not in missing_people_seen_blocks:
                            missing_people_blocks.append(block)
                            missing_people_seen_blocks.add(block)
                        missing_people_seen_names.update(names)
                if skip_save_if_cached and cached_run_key == summary.get("run_key"):
                    duplicates += 1
                else:
                    if tool_name == "kometa":
                        summary["progress_snapshot"] = _build_completed_log_progress_snapshot(
                            summary=summary,
                            content=content,
                            analyzer=analyzer,
                        )
                    if database.save_log_run(summary, recommendations=result.get("recommendations")):
                        ingested += 1
                    else:
                        duplicates += 1
                cache_logs[cache_key] = {
                    "mtime": stats.st_mtime,
                    "size": stats.st_size,
                    "run_key": summary.get("run_key"),
                    "tool_name": tool_name,
                    "run_complete": True,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                cache_dirty = True
                is_live_source = path.parent.resolve() == live_dir.resolve()
                should_archive_live = (
                    is_live_source and not (tool_name == "kometa" and path.name.lower() == "meta.log") and not (tool_name == "imagemaid" and helpers.is_imagemaid_running())
                )
                if should_archive_live:
                    archived_path = _archive_log_file(path, archive_dir, log_dir=live_dir)
                    if archived_path:
                        try:
                            archived_stats = archived_path.stat()
                            cache_logs[str(archived_path.resolve())] = {
                                "mtime": archived_stats.st_mtime,
                                "size": archived_stats.st_size,
                                "run_key": summary.get("run_key"),
                                "tool_name": tool_name,
                                "run_complete": True,
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }
                            cache_dirty = True
                        except Exception:
                            pass
            except Exception as exc:
                errors += 1
                if len(sample_errors) < 5:
                    sample_errors.append(f"{path.name}: {exc}")
            if update_state:
                _update_logscan_reingest_state(
                    scanned=idx,
                    ingested=ingested,
                    duplicates=duplicates,
                    skipped_incomplete=skipped_incomplete,
                    skipped_invalid=skipped_invalid,
                    errors=errors,
                    missing_people_unique=len(missing_people_unique),
                    missing_people_logs=missing_people_logs,
                    sample_incomplete=sample_incomplete,
                    sample_errors=sample_errors,
                )

        cache_dir = _get_logscan_cache_dir()
        missing_people_log = cache_dir / "meta_people_missing.log"
        missing_people_meta = cache_dir / "meta_people_missing.json"
        missing_people_log_ready = False
        missing_people_log_lines = 0
        if missing_people_blocks:
            try:
                missing_people_log_lines = sum(len(block.splitlines()) for block in missing_people_blocks)
                output_parts = []
                if missing_people_header:
                    output_parts.append(missing_people_header)
                    missing_people_log_lines += len(missing_people_header.splitlines())
                output_parts.extend(missing_people_blocks)
                missing_people_log.write_text("\n".join(output_parts).rstrip() + "\n", encoding="utf-8")
                missing_people_log_ready = True
                try:
                    missing_people_meta.write_text(
                        json.dumps(
                            {
                                "missing_people_unique": len(missing_people_unique),
                                "missing_people_logs": missing_people_logs,
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            },
                            ensure_ascii=True,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                except Exception:
                    pass
            except Exception as exc:
                errors += 1
                if len(sample_errors) < 5:
                    sample_errors.append(f"{missing_people_log.name}: {exc}")
        else:
            try:
                if missing_people_log.exists():
                    missing_people_log.unlink()
                if missing_people_meta.exists():
                    missing_people_meta.unlink()
            except Exception:
                pass

        result = {
            "success": True,
            "scanned": len(log_files),
            "ingested": ingested,
            "duplicates": duplicates,
            "skipped_incomplete": skipped_incomplete,
            "skipped_invalid": skipped_invalid,
            "errors": errors,
            "missing_people_unique": len(missing_people_unique),
            "missing_people_logs": missing_people_logs,
            "missing_people_log_ready": missing_people_log_ready,
            "missing_people_log_lines": missing_people_log_lines,
            "sample_incomplete": sample_incomplete,
            "sample_errors": sample_errors,
        }
        if update_state:
            _update_logscan_reingest_state(
                status="complete",
                finished_at=datetime.now(timezone.utc).isoformat(),
                current_file=None,
                **result,
            )
        if cache_dirty:
            _save_logscan_ingest_cache(ingest_cache)
        return result
    finally:
        logscan_ingest_lock.release()


def _logscan_startup_migrations_enabled():
    raw = str(os.getenv(LOGSCAN_STARTUP_MIGRATIONS_ENV, "1") or "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _get_logscan_migration_level_done():
    raw = str(os.getenv(LOGSCAN_MIGRATION_LEVEL_DONE_ENV, "0") or "").strip()
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _set_logscan_migration_level_done(level):
    normalized = str(max(0, int(level)))
    helpers.update_env_variable(LOGSCAN_MIGRATION_LEVEL_DONE_ENV, normalized)
    os.environ[LOGSCAN_MIGRATION_LEVEL_DONE_ENV] = normalized


def _get_pending_logscan_startup_migration():
    enabled = _logscan_startup_migrations_enabled()
    completed_level = _get_logscan_migration_level_done()
    required_level = max(0, int(REQUIRED_LOGSCAN_MIGRATION_LEVEL or 0))
    state = {
        "enabled": enabled,
        "completed_level": completed_level,
        "required_level": required_level,
        "should_run": False,
        "reason": "up_to_date",
    }
    if not enabled:
        state["reason"] = "disabled"
        return state
    if required_level <= 0:
        state["reason"] = "not_configured"
        return state
    if completed_level >= required_level:
        state["reason"] = "up_to_date"
        return state
    log_dir = helpers.get_kometa_log_dir()
    if not log_dir.exists():
        state["reason"] = "waiting_for_logs"
        return state
    candidate_files = _get_logscan_log_files(log_dir=log_dir, include_archive=True)
    if not candidate_files:
        state["reason"] = "waiting_for_logs"
        return state
    state["should_run"] = True
    state["reason"] = "pending"
    state["candidate_files"] = len(candidate_files)
    return state


def _run_logscan_startup_migration(app_in, required_level, completed_level):
    helpers.ts_log(
        (
            f"Starting one-time Analytics migration level {required_level} "
            f"(completed level: {completed_level}). Quickstart will reset stored "
            "trend data and reingest Kometa logs in the background."
        ),
        level="INFO",
    )
    try:
        with app_in.app_context():
            result = _perform_logscan_reingest(
                reset=True,
                job_id=LOGSCAN_STARTUP_MIGRATION_JOB_ID,
                update_state=True,
            )
        if result.get("success"):
            _set_logscan_migration_level_done(required_level)
            helpers.ts_log(
                (f"Completed Analytics migration level {required_level}. " f"Persisted {LOGSCAN_MIGRATION_LEVEL_DONE_ENV}={required_level}."),
                level="INFO",
            )
        else:
            helpers.ts_log(
                (f"Analytics migration level {required_level} did not complete: " f"{result.get('error', 'Unknown error')}."),
                level="WARNING",
            )
        return result
    except Exception as exc:
        _update_logscan_reingest_state(
            status="error",
            error=f"Startup Analytics migration failed: {exc}",
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        helpers.ts_log(f"Startup Analytics migration failed: {exc}", level="ERROR")
        return {"success": False, "error": str(exc)}


def _start_pending_logscan_startup_migration(app_in):
    state = _get_pending_logscan_startup_migration()
    if not state.get("should_run"):
        reason = state.get("reason")
        required_level = state.get("required_level", 0)
        completed_level = state.get("completed_level", 0)
        if reason == "disabled":
            helpers.ts_log(
                (f"Skipping startup Analytics migration because " f"{LOGSCAN_STARTUP_MIGRATIONS_ENV}=0."),
                level="INFO",
            )
        elif reason == "waiting_for_logs":
            helpers.ts_log(
                (f"Deferring Analytics migration level {required_level} until Kometa " "log files exist. This is expected on a first-time Quickstart setup."),
                level="INFO",
            )
        elif required_level > 0 and completed_level >= required_level:
            helpers.ts_log(f"Analytics migration level {required_level} already applied.", level="DEBUG")
        return state

    started_at = datetime.now(timezone.utc).isoformat()
    _update_logscan_reingest_state(
        status="running",
        job_id=LOGSCAN_STARTUP_MIGRATION_JOB_ID,
        trigger="startup_migration",
        migration_level=state["required_level"],
        started_at=started_at,
        finished_at=None,
        total=0,
        scanned=0,
        ingested=0,
        duplicates=0,
        skipped_incomplete=0,
        skipped_invalid=0,
        errors=0,
        current_file=None,
        missing_people_unique=0,
        missing_people_logs=0,
        missing_people_log_ready=False,
        missing_people_log_lines=0,
        sample_incomplete=[],
        sample_errors=[],
    )
    thread = threading.Thread(
        target=_run_logscan_startup_migration,
        args=(app_in, state["required_level"], state["completed_level"]),
        daemon=True,
        name="logscan-startup-migration",
    )
    thread.start()
    state["started"] = True
    state["job_id"] = LOGSCAN_STARTUP_MIGRATION_JOB_ID
    return state


def _run_logscan_reingest_job(job_id, reset):
    try:
        with app.app_context():
            _perform_logscan_reingest(reset=reset, job_id=job_id, update_state=True)
    except Exception as exc:
        _update_logscan_reingest_state(
            status="error",
            error=str(exc),
            finished_at=datetime.now(timezone.utc).isoformat(),
            current_file=None,
        )


@app.route("/logscan/trends/reingest/status", methods=["GET"])
def logscan_trends_reingest_status():
    job_id = request.args.get("job")
    snapshot = _logscan_reingest_snapshot()
    if not snapshot or snapshot.get("status") == "idle":
        return jsonify({"status": "idle"})
    if job_id and snapshot.get("job_id") != job_id:
        return jsonify({"status": "idle"}), 404
    return jsonify(snapshot)


@app.route("/background-jobs/active", methods=["GET"])
def background_jobs_active():
    job_type = str(request.args.get("job_type", "") or request.args.get("type", "")).strip()
    if job_type:
        active = _get_active_background_job(job_type)
        return jsonify(success=True, active=bool(active), job=active)
    jobs = sorted(
        _get_active_background_jobs(),
        key=lambda job: str(job.get("started_at") or ""),
        reverse=True,
    )
    return jsonify(success=True, jobs=jobs)


@app.route("/background-jobs/<job_id>", methods=["GET"])
def background_job_status(job_id):
    job = _get_background_job(job_id)
    if not job:
        return jsonify(success=False, error="Unknown job_id."), 404
    since = request.args.get("since", "0").strip()
    try:
        start_idx = max(int(since or "0"), 0)
    except ValueError:
        start_idx = 0
    logs = list(job.get("logs") or [])
    return jsonify(
        success=True,
        job=job,
        lines=logs[start_idx:],
        next_index=len(logs),
        done=job.get("status") in {"complete", "error"},
        update_success=bool(job.get("success")),
    )


@app.route("/logscan/trends/reingest", methods=["POST"])
def logscan_trends_reingest():
    data = request.get_json(silent=True) or {}
    reset = data.get("reset") is True
    background = data.get("background") is True
    if logscan_ingest_lock.locked():
        snapshot = _logscan_reingest_snapshot()
        return (
            jsonify(
                {
                    "error": "Reingest already running.",
                    "job_id": snapshot.get("job_id"),
                    "status": snapshot.get("status") or "running",
                    "trigger": snapshot.get("trigger"),
                    "migration_level": snapshot.get("migration_level"),
                }
            ),
            409,
        )
    if background:
        snapshot = _logscan_reingest_snapshot()
        if snapshot.get("status") == "running":
            return (
                jsonify(
                    {
                        "error": "Reingest already running.",
                        "job_id": snapshot.get("job_id"),
                        "status": snapshot.get("status"),
                        "trigger": snapshot.get("trigger"),
                        "migration_level": snapshot.get("migration_level"),
                    }
                ),
                409,
            )
        job_id = secrets.token_urlsafe(8)
        _update_logscan_reingest_state(
            status="running",
            job_id=job_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            total=0,
            scanned=0,
            ingested=0,
            duplicates=0,
            skipped_incomplete=0,
            skipped_invalid=0,
            errors=0,
            current_file=None,
            missing_people_unique=0,
            missing_people_logs=0,
            missing_people_log_ready=False,
            missing_people_log_lines=0,
            sample_incomplete=[],
            sample_errors=[],
        )
        thread = threading.Thread(target=_run_logscan_reingest_job, args=(job_id, reset), daemon=True)
        thread.start()
        return jsonify({"success": True, "job_id": job_id, "status": "running"})

    result = _perform_logscan_reingest(reset=reset, job_id=None, update_state=True)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@app.route("/logscan-trends", methods=["GET"])
def logscan_trends_page():
    persistence.ensure_session_config_name()
    if "shutdown_nonce" not in session:
        session["shutdown_nonce"] = secrets.token_urlsafe(16)
    if "restart_nonce" not in session:
        session["restart_nonce"] = secrets.token_urlsafe(16)

    page_info = {
        "title": "Analytics",
        "template_name": "905-analytics",
        "config_name": session.get("config_name"),
        "running_port": running_port,
        "qs_debug": app.config["QS_DEBUG"],
        "qs_theme": app.config.get("QS_THEME", "kometa"),
        "qs_optimize_defaults": app.config.get("QS_OPTIMIZE_DEFAULTS", True),
        "qs_config_history": app.config.get("QS_CONFIG_HISTORY", 0),
        "qs_kometa_log_keep": app.config.get("QS_KOMETA_LOG_KEEP", 0),
        "qs_imagemaid_log_keep": app.config.get("QS_IMAGEMAID_LOG_KEEP", 0),
        "qs_session_lifetime_days": app.config.get("QS_SESSION_LIFETIME_DAYS", 30),
        "qs_flask_session_dir": app.config.get("QS_FLASK_SESSION_DIR", ""),
        "shutdown_nonce": session["shutdown_nonce"],
        "restart_nonce": session["restart_nonce"],
        "hide_step_nav": False,
    }

    template_list = helpers.get_menu_list()
    step_templates = helpers.get_template_list()
    _, num, _ = helpers.get_bits(page_info["template_name"])
    item = step_templates.get(num)
    if item:
        page_info["next_page"] = item["next"]
        page_info["prev_page"] = item["prev"]
        if page_info["next_page"]:
            next_num = page_info["next_page"].split("-")[0]
            page_info["next_page_name"] = step_templates.get(next_num, {}).get("name", "Next")
        else:
            page_info["next_page_name"] = "Next"

        if page_info["prev_page"]:
            prev_num = page_info["prev_page"].split("-")[0]
            page_info["prev_page_name"] = step_templates.get(prev_num, {}).get("name", "Previous")
        else:
            page_info["prev_page_name"] = "Previous"

    progress_excludes = {"sponsor", "analytics"}
    progress_keys = [key for key in step_templates if step_templates[key].get("raw_name") not in progress_excludes]
    total_steps = len(progress_keys)
    if num in progress_keys and total_steps:
        progress_index = progress_keys.index(num)
    else:
        progress_index = max(total_steps - 1, 0)
    page_info["progress"] = round(((progress_index + 1) / total_steps) * 100) if total_steps else 0
    available_configs = database.get_unique_config_names() or []
    page_info.update(_build_kometa_install_context(page_info.get("config_name")))
    workspace_status = _build_workspace_status_context(page_info.get("config_name"), template_list, available_configs=available_configs)
    return render_template(
        "905-analytics.html",
        page_info=page_info,
        template_list=template_list,
        available_configs=available_configs,
        jump_to_validations=workspace_status.get("jump_to_validations", {}),
        step_statuses=workspace_status.get("step_statuses", {}),
        section_statuses=workspace_status.get("section_statuses", {}),
        required_keys=workspace_status.get("required_keys", []),
        optional_keys=workspace_status.get("optional_keys", []),
        review_keys=workspace_status.get("review_keys", []),
        tautulli_requirement_reasons=workspace_status.get("tautulli_requirement_reasons", []),
        omdb_requirement_reasons=workspace_status.get("omdb_requirement_reasons", []),
        mdblist_requirement_reasons=workspace_status.get("mdblist_requirement_reasons", []),
        anidb_requirement_reasons=workspace_status.get("anidb_requirement_reasons", []),
        radarr_requirement_reasons=workspace_status.get("radarr_requirement_reasons", []),
        sonarr_requirement_reasons=workspace_status.get("sonarr_requirement_reasons", []),
        trakt_requirement_reasons=workspace_status.get("trakt_requirement_reasons", []),
        mal_requirement_reasons=workspace_status.get("mal_requirement_reasons", []),
        workspace_readiness=workspace_status.get("readiness", {}),
    )


@app.route("/logscan/trends/preferences", methods=["GET"])
def logscan_trends_preferences():
    config_name = request.args.get("config_name", "").strip() or "all"
    preferences = database.get_analytics_preferences(config_name)
    return jsonify({"success": True, "config_name": config_name, "preferences": preferences})


@app.route("/logscan/trends/preferences", methods=["POST"])
def logscan_trends_preferences_update():
    payload = request.get_json(silent=True) or {}
    config_name = str(payload.get("config_name", "")).strip() or "all"
    preferences = payload.get("preferences")
    saved = database.save_analytics_preferences(config_name, preferences)
    result = database.get_analytics_preferences(config_name)
    status_code = 200 if saved else 400
    return jsonify({"success": saved, "config_name": config_name, "preferences": result}), status_code


@app.route("/logscan/trends/people-missing", methods=["GET"])
def logscan_trends_people_missing():
    missing_log = _get_logscan_cache_dir() / "meta_people_missing.log"
    if not missing_log.exists():
        return jsonify({"error": "Missing people log not found."}), 404
    return send_file(
        missing_log,
        mimetype="text/plain",
        as_attachment=True,
        download_name="meta_people_missing.log",
    )


@app.route("/logscan/trends/people-missing/status", methods=["GET"])
def logscan_trends_people_missing_status():
    cache_dir = _get_logscan_cache_dir()
    missing_log = cache_dir / "meta_people_missing.log"
    if not missing_log.exists():
        return jsonify({"exists": False, "missing_people_unique": 0})
    meta_path = cache_dir / "meta_people_missing.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}
    return jsonify(
        {
            "exists": True,
            "missing_people_unique": meta.get("missing_people_unique"),
            "updated_at": meta.get("updated_at"),
        }
    )


@app.route("/support-info")
def support_info():
    def format_mb(value):
        return int(value / (1024 * 1024))

    def normalize_config_name(name):
        cleaned = (name or "").strip().lower().replace(" ", "_")
        return cleaned or "default"

    config_name = session.get("config_name") or "default"
    normalized_name = normalize_config_name(config_name)
    config_path = Path(helpers.CONFIG_DIR) / f"{normalized_name}_config.yml"

    if config_path.exists():
        created_ts = datetime.fromtimestamp(config_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        created_line = f"# {config_name} config created by Quickstart on {created_ts}"
    else:
        created_line = f"# {config_name} config created by Quickstart on Unavailable"

    version_info = app.config.get("VERSION_CHECK") or helpers.check_for_update()
    quickstart_version = version_info.get("local_version", "unknown")
    quickstart_branch = version_info.get("branch", "unknown")
    quickstart_environment = version_info.get("running_on", "unknown")

    system_name = platform.system() or "Unknown OS"
    system_release = platform.release() or ""
    cpu_name = platform.processor() or platform.uname().processor or "Unknown CPU"
    cpu_cores = psutil.cpu_count(logical=True) or 0
    vm = psutil.virtual_memory()
    mem_total = format_mb(vm.total)
    mem_available = format_mb(vm.available)
    mem_used = format_mb(vm.total - vm.available)
    mem_percent = int(vm.percent)
    is_docker = bool(app.config.get("QUICKSTART_DOCKER")) or "Docker" in str(quickstart_environment)
    python_version = platform.python_version() or sys.version.split()[0]
    git_version = "Unavailable"
    git_path = shutil.which("git")
    if git_path:
        try:
            git_result = subprocess.run(
                [git_path, "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            git_output = (git_result.stdout or git_result.stderr or "").strip()
            if git_output:
                git_version = git_output
        except Exception:
            git_version = "Unavailable"

    ua = request.user_agent
    browser_name = ua.browser or ""
    browser_version = ua.version or ""
    browser_platform = ua.platform or ""
    browser_line = browser_name
    if browser_name:
        if browser_version:
            browser_line = f"{browser_line} {browser_version}"
        if browser_platform:
            browser_line = f"{browser_line} ({browser_platform})"
    else:
        browser_line = request.headers.get("User-Agent", "") or session.get("qs_user_agent_raw") or session.get("qs_user_agent") or "Unknown"

    plex_summary = helpers.get_plex_summary()
    if not plex_summary or plex_summary.lower().startswith("plex summary unavailable"):
        plex_summary = "Plex info unavailable."

    library_settings = persistence.retrieve_settings("025-libraries").get("libraries", {})
    movie_libraries = []
    show_libraries = []
    for key, value in library_settings.items():
        if not key.endswith("-library") or value in [None, "", False]:
            continue
        if key.startswith("mov-library_"):
            movie_libraries.append(str(value))
        elif key.startswith("sho-library_"):
            show_libraries.append(str(value))

    movie_libraries = sorted((name.strip() for name in movie_libraries if str(name).strip()), key=lambda value: value.casefold())
    show_libraries = sorted((name.strip() for name in show_libraries if str(name).strip()), key=lambda value: value.casefold())
    library_names = movie_libraries + show_libraries
    if library_names:
        library_details = helpers.get_library_summaries(library_names)
        if library_details.lower().startswith("plex library summary unavailable"):
            library_details = "Library details unavailable."
    else:
        library_details = "No libraries configured."

    lines = []
    lines.append(f"#==================== {config_name} ====================#")
    lines.append(created_line)
    lines.append("# System Information")
    lines.append(f"# OS: {system_name} {system_release}".strip())
    lines.append(f"# Docker: {is_docker}")
    lines.append(f"# CPU: {cpu_name} ({cpu_cores} cores)")
    lines.append(f"# Memory: {mem_used} MB / {mem_total} MB ({mem_percent}%) | {mem_available} MB Free")
    lines.append(f"# Python: {python_version}")
    lines.append(f"# Git: {git_version}")
    lines.append(f"# Browser: {browser_line}")
    lines.extend(helpers.get_quickstart_settings_summary())
    lines.extend([f"# {line}" for line in plex_summary.splitlines()])
    lines.append(f"# Quickstart: {quickstart_version} | Branch: {quickstart_branch} | Environment: {quickstart_environment}")
    lines.append("###")
    lines.append(f"# Libraries configured with Quickstart: {len(movie_libraries)} movie, {len(show_libraries)} show")
    if library_details:
        for line in library_details.splitlines():
            if line.strip():
                lines.append(f"# {line}")
            else:
                lines.append("#")
    lines.append("###")

    log_path = Path(helpers.LOG_FILE).resolve()
    log_lines = []

    if log_path.exists():
        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as f:
                tail = deque(f, maxlen=200)
            for line in tail:
                log_lines.append(helpers.redact_string(line.rstrip("\n")))
            if not log_lines:
                log_lines.append("Quickstart log is empty.")
        except Exception:
            log_lines.append("Quickstart log unavailable.")
    else:
        log_lines.append("Quickstart log unavailable.")

    lines.append("# Quickstart log tail (last 200 lines)")
    lines.append("")

    text = "\n".join(lines + log_lines)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({"text": text, "generated_at": generated_at})


@app.route("/update-quickstart-settings", methods=["POST"])
def update_quickstart_settings():
    data = request.get_json(silent=True) or {}
    errors = []
    restart_required = False
    changes_applied = False
    theme_changed = False

    allowed_themes = {
        "kometa",
        "dark",
        "plex",
        "jellyfin",
        "emby",
        "seerr",
        "mind",
        "power",
        "reality",
        "soul",
        "space",
        "time",
    }

    new_port = None
    if "port" in data:
        try:
            new_port = int(str(data.get("port", "")).strip())
        except (TypeError, ValueError):
            new_port = None
        if not new_port or new_port < 1 or new_port > 65535:
            errors.append("Port must be a number between 1 and 65535.")

    debug_raw = data.get("debug")
    debug_value = None
    if debug_raw is not None:
        debug_value = helpers.booler(str(debug_raw))

    optimize_raw = data.get("optimize_defaults")
    optimize_value = None
    if optimize_raw is not None:
        optimize_value = helpers.booler(str(optimize_raw))

    history_raw = data.get("config_history")
    history_value = None
    if history_raw is not None:
        try:
            history_value = int(str(history_raw).strip())
        except (TypeError, ValueError):
            errors.append("Config history must be a non-negative number.")
            history_value = None
        if history_value is not None and history_value < 0:
            errors.append("Config history must be a non-negative number.")

    log_keep_raw = data.get("kometa_log_keep")
    log_keep_value = None
    if log_keep_raw is not None:
        try:
            log_keep_value = int(str(log_keep_raw).strip())
        except (TypeError, ValueError):
            errors.append("Kometa log retention must be a non-negative number.")
            log_keep_value = None
        if log_keep_value is not None and log_keep_value < 0:
            errors.append("Kometa log retention must be a non-negative number.")

    imagemaid_log_keep_raw = data.get("imagemaid_log_keep")
    imagemaid_log_keep_value = None
    if imagemaid_log_keep_raw is not None:
        try:
            imagemaid_log_keep_value = int(str(imagemaid_log_keep_raw).strip())
        except (TypeError, ValueError):
            errors.append("ImageMaid log retention must be a non-negative number.")
            imagemaid_log_keep_value = None
        if imagemaid_log_keep_value is not None and imagemaid_log_keep_value < 0:
            errors.append("ImageMaid log retention must be a non-negative number.")

    session_lifetime_raw = data.get("session_lifetime_days")
    session_lifetime_value = None
    if session_lifetime_raw is not None:
        try:
            session_lifetime_value = int(str(session_lifetime_raw).strip())
        except (TypeError, ValueError):
            errors.append("Session lifetime must be a positive number of days.")
            session_lifetime_value = None
        if session_lifetime_value is not None and session_lifetime_value < 1:
            errors.append("Session lifetime must be at least 1 day.")

    session_dir_raw = data.get("session_dir")
    session_dir_value = None
    if session_dir_raw is not None:
        session_dir_value = str(session_dir_raw).strip()

    regenerate_secret = data.get("regenerate_secret") is True

    theme_raw = data.get("theme")
    theme_value = None
    if theme_raw is not None:
        theme_value = str(theme_raw).strip().lower()
        if not theme_value:
            theme_value = "kometa"
        if theme_value not in allowed_themes:
            errors.append("Theme must be one of: " + ", ".join(sorted(allowed_themes)) + ".")

    if errors:
        return jsonify(success=False, message=" ".join(errors)), 400

    if new_port and new_port != running_port:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if sock.connect_ex(("localhost", new_port)) == 0:
                return jsonify(success=False, message=f"Port {new_port} is already in use."), 409
        finally:
            sock.close()

        helpers.update_env_variable("QS_PORT", str(new_port))
        app.config["QS_PORT"] = new_port
        restart_required = True
        changes_applied = True

    if debug_value is not None and debug_value != app.config["QS_DEBUG"]:
        helpers.update_env_variable("QS_DEBUG", "1" if debug_value else "0")
        app.config["QS_DEBUG"] = debug_value
        changes_applied = True

    if theme_value and theme_value != app.config.get("QS_THEME", "kometa"):
        helpers.update_env_variable("QS_THEME", theme_value)
        app.config["QS_THEME"] = theme_value
        changes_applied = True
        theme_changed = True

    if optimize_value is not None and optimize_value != app.config.get("QS_OPTIMIZE_DEFAULTS", True):
        helpers.update_env_variable("QS_OPTIMIZE_DEFAULTS", "1" if optimize_value else "0")
        app.config["QS_OPTIMIZE_DEFAULTS"] = optimize_value
        changes_applied = True

    if history_value is not None and history_value != app.config.get("QS_CONFIG_HISTORY", 0):
        helpers.update_env_variable("QS_CONFIG_HISTORY", str(history_value))
        app.config["QS_CONFIG_HISTORY"] = history_value
        changes_applied = True

    if log_keep_value is not None and log_keep_value != app.config.get("QS_KOMETA_LOG_KEEP", 0):
        helpers.update_env_variable("QS_KOMETA_LOG_KEEP", str(log_keep_value))
        app.config["QS_KOMETA_LOG_KEEP"] = log_keep_value
        changes_applied = True

    if imagemaid_log_keep_value is not None and imagemaid_log_keep_value != app.config.get("QS_IMAGEMAID_LOG_KEEP", 0):
        helpers.update_env_variable("QS_IMAGEMAID_LOG_KEEP", str(imagemaid_log_keep_value))
        app.config["QS_IMAGEMAID_LOG_KEEP"] = imagemaid_log_keep_value
        changes_applied = True

    if session_lifetime_value is not None and session_lifetime_value != app.config.get("QS_SESSION_LIFETIME_DAYS", 30):
        helpers.update_env_variable("QS_SESSION_LIFETIME_DAYS", str(session_lifetime_value))
        app.config["QS_SESSION_LIFETIME_DAYS"] = session_lifetime_value
        app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=session_lifetime_value)
        cache_dir = app.config.get("QS_FLASK_SESSION_DIR", flask_cache_dir)
        app.config["SESSION_CACHELIB"] = FileSystemCache(
            cache_dir=cache_dir,
            threshold=500,
            default_timeout=int(timedelta(days=session_lifetime_value).total_seconds()),
        )
        changes_applied = True

    if session_dir_value is not None:
        default_session_dir = os.path.abspath(os.path.expanduser(os.path.join(helpers.CONFIG_DIR, "flask_session")))
        desired_session_dir = os.path.abspath(os.path.expanduser(session_dir_value or default_session_dir))
        current_session_dir = app.config.get("QS_FLASK_SESSION_DIR", default_session_dir)
        if desired_session_dir != current_session_dir:
            try:
                os.makedirs(desired_session_dir, exist_ok=True)
            except Exception:
                return jsonify(success=False, message="Failed to create the session storage directory."), 500
            helpers.update_env_variable("QS_FLASK_SESSION_DIR", desired_session_dir)
            app.config["QS_FLASK_SESSION_DIR"] = desired_session_dir
            app.config["SESSION_CACHELIB"] = FileSystemCache(
                cache_dir=desired_session_dir,
                threshold=500,
                default_timeout=int(timedelta(days=app.config.get("QS_SESSION_LIFETIME_DAYS", 30)).total_seconds()),
            )
            changes_applied = True

    if regenerate_secret:
        new_secret = secrets.token_hex(32)
        helpers.update_env_variable("QS_SECRET_KEY", new_secret)
        app.config["SECRET_KEY"] = new_secret
        app.secret_key = new_secret
        try:
            with open(os.path.join(helpers.CONFIG_DIR, ".secret_key"), "w", encoding="utf-8") as handle:
                handle.write(new_secret)
        except Exception:
            pass
        changes_applied = True

    if not changes_applied:
        return jsonify(
            success=True,
            message="No changes applied.",
            restart=False,
            theme=app.config.get("QS_THEME", "kometa"),
            optimize_defaults=app.config.get("QS_OPTIMIZE_DEFAULTS", True),
            config_history=app.config.get("QS_CONFIG_HISTORY", 0),
            kometa_log_keep=app.config.get("QS_KOMETA_LOG_KEEP", 0),
            imagemaid_log_keep=app.config.get("QS_IMAGEMAID_LOG_KEEP", 0),
            session_lifetime_days=app.config.get("QS_SESSION_LIFETIME_DAYS", 30),
            session_dir=app.config.get("QS_FLASK_SESSION_DIR", ""),
        )

    if restart_required:
        return jsonify(
            success=True,
            message="Settings updated. Restarting Quickstart...",
            restart=True,
            new_port=new_port or running_port,
            theme=app.config.get("QS_THEME", "kometa"),
            theme_changed=theme_changed,
            optimize_defaults=app.config.get("QS_OPTIMIZE_DEFAULTS", True),
            config_history=app.config.get("QS_CONFIG_HISTORY", 0),
            kometa_log_keep=app.config.get("QS_KOMETA_LOG_KEEP", 0),
            imagemaid_log_keep=app.config.get("QS_IMAGEMAID_LOG_KEEP", 0),
            session_lifetime_days=app.config.get("QS_SESSION_LIFETIME_DAYS", 30),
            session_dir=app.config.get("QS_FLASK_SESSION_DIR", ""),
        )

    return jsonify(
        success=True,
        message="Settings updated.",
        restart=False,
        theme=app.config.get("QS_THEME", "kometa"),
        theme_changed=theme_changed,
        optimize_defaults=app.config.get("QS_OPTIMIZE_DEFAULTS", True),
        config_history=app.config.get("QS_CONFIG_HISTORY", 0),
        kometa_log_keep=app.config.get("QS_KOMETA_LOG_KEEP", 0),
        imagemaid_log_keep=app.config.get("QS_IMAGEMAID_LOG_KEEP", 0),
        session_lifetime_days=app.config.get("QS_SESSION_LIFETIME_DAYS", 30),
        session_dir=app.config.get("QS_FLASK_SESSION_DIR", ""),
    )


@app.route("/header-style-preview", methods=["GET"])
def header_style_preview():
    font = str(request.args.get("font", "") or "").strip()
    available_fonts = helpers.get_pyfiglet_fonts()
    if not font:
        font = "single line"
    if font == "single_line":
        font = "single line"
    if font not in available_fonts:
        return jsonify(success=False, message="Unknown header style."), 404

    preview = _render_header_style_preview(font)

    return jsonify(success=True, font=font, preview=preview)


@app.route("/header-style-previews", methods=["POST"])
def header_style_previews():
    data = request.get_json(silent=True) or {}
    fonts = data.get("fonts") or []
    if not isinstance(fonts, list):
        return jsonify(success=False, message="Fonts must be a list."), 400

    available = set(helpers.get_pyfiglet_fonts())
    previews = []
    for font in fonts:
        font_name = str(font or "").strip()
        if not font_name or font_name not in available:
            continue
        previews.append({"font": font_name, "preview": _render_header_style_preview(font_name)})

    return jsonify(success=True, previews=previews)


@app.route("/validate-imagemaid", methods=["POST"])
def validate_imagemaid():
    payload = request.get_json(silent=True) or {}
    config_name = _resolve_request_config_name(payload)
    form_payload = _imagemaid_settings_to_form_payload(payload)
    if form_payload:
        _save_imagemaid_settings_for_config(config_name, form_payload)

    settings, section_data = _get_imagemaid_settings_section(config_name)
    is_valid, reason, details = _validate_imagemaid_settings(section_data, config_name=config_name)
    _persist_imagemaid_validation(config_name, section_data, is_valid, reason=reason, details=details)

    plex_url, plex_token = _get_stored_plex_credentials_for_config(config_name)
    preview_command = _build_imagemaid_command(section_data, plex_url or "", plex_token or "", redact=True)
    return jsonify(success=is_valid, validated=is_valid, reason=reason, details=details, command_preview=preview_command), (200 if is_valid else 400)


@app.route("/autosave-imagemaid", methods=["POST"])
def autosave_imagemaid():
    payload = request.get_json(silent=True) or {}
    config_name = _resolve_request_config_name(payload)
    form_payload = _imagemaid_settings_to_form_payload(payload)
    changed = False
    if form_payload:
        _saved_payload, changed = _save_imagemaid_settings_for_config(config_name, form_payload)

    settings, section_data = _get_imagemaid_settings_section(config_name)
    if changed and helpers.booler(settings.get("validated", False)):
        _persist_imagemaid_validation(
            config_name,
            section_data,
            False,
            reason="config_changed",
            details="Configuration changed. Validate ImageMaid again.",
        )
        validated = False
    else:
        validated = helpers.booler(settings.get("validated", False))

    return jsonify(success=True, changed=changed, validated=validated)


@app.route("/start-imagemaid", methods=["POST"])
def start_imagemaid():
    payload = request.get_json(silent=True) or {}
    config_name = _resolve_request_config_name(payload)
    form_payload = _imagemaid_settings_to_form_payload(payload)
    if form_payload:
        _save_imagemaid_settings_for_config(config_name, form_payload)

    if helpers.is_imagemaid_running():
        pid = helpers.get_imagemaid_pid()
        try:
            proc = psutil.Process(pid)
            started_at = datetime.fromtimestamp(proc.create_time()).isoformat()
            return jsonify({"error": f"ImageMaid is already running (PID: {pid}) since {started_at}.", "status": "running", "pid": pid, "started_at": started_at}), 400
        except Exception:
            return jsonify({"error": f"ImageMaid is already running (PID: {pid}).", "status": "running", "pid": pid}), 400
    else:
        proc = _find_running_imagemaid_process()
        if proc:
            try:
                with open(helpers.get_imagemaid_pid_file(), "w", encoding="utf-8") as f:
                    f.write(str(proc.pid))
                started_at = datetime.fromtimestamp(proc.create_time()).isoformat()
            except Exception:
                started_at = None
            payload = {"error": f"ImageMaid is already running (PID: {proc.pid}).", "status": "running", "pid": proc.pid}
            if started_at:
                payload["started_at"] = started_at
            return jsonify(payload), 400

    blocker = _get_active_work_blocker("imagemaid_run")
    if blocker:
        job = blocker.get("job") if isinstance(blocker.get("job"), dict) else {}
        response = {
            "error": blocker.get("message") or "Cannot start ImageMaid right now.",
            "status": "blocked",
            "blocked_by": blocker.get("blocked_by"),
            "target_page": blocker.get("target_page"),
        }
        if blocker.get("pid"):
            response["pid"] = blocker.get("pid")
        if job.get("job_id"):
            response["job_id"] = job.get("job_id")
        if job.get("phase"):
            response["phase"] = job.get("phase")
        return jsonify(response), 409

    settings, section_data = _get_imagemaid_settings_section(config_name)
    is_valid, reason, details = _validate_imagemaid_settings(section_data, config_name=config_name)
    _persist_imagemaid_validation(config_name, section_data, is_valid, reason=reason, details=details)
    if not is_valid:
        return jsonify({"error": details or "ImageMaid settings are not valid.", "status": "invalid", "reason": reason}), 400

    start_min, end_min, window_str = _resolve_maintenance_window_live(config_name=config_name)
    if start_min is None or end_min is None:
        start_min, end_min, window_str = _resolve_maintenance_window_from_db(config_name=config_name)
    if _is_within_maintenance_window(datetime.now(), start_min, end_min):
        try:
            _write_quickstart_imagemaid_maintenance_marker(
                helpers.get_imagemaid_root_path(),
                "blocked_start",
                mode=section_data.get("mode"),
                config_name=config_name,
                window=window_str,
                log_path=_get_latest_imagemaid_log_path(),
            )
        except Exception:
            pass
        window_label = f" ({window_str})" if window_str else ""
        return (
            jsonify(
                {
                    "error": f"ImageMaid cannot start during the Plex maintenance window{window_label}.",
                    "status": "maintenance_blocked",
                    "maintenance_window": window_str,
                }
            ),
            409,
        )

    plex_url, plex_token = _get_stored_plex_credentials_for_config(config_name)
    command = _build_imagemaid_command_parts(section_data, plex_url, plex_token, redact=False)
    ok, result = _launch_imagemaid_command(command, mode=section_data.get("mode"), config_name=config_name)
    if ok:
        return jsonify({"status": "ImageMaid started", "pid": result, "command_preview": _build_imagemaid_command(section_data, plex_url, plex_token, redact=True)})
    code = 500
    if isinstance(result, str):
        lowered = result.lower()
        if lowered.startswith("imagemaid.py not found"):
            code = 404
        elif "exited immediately" in lowered or "finished immediately" in lowered:
            code = 400
    return jsonify({"error": result}), code


@app.route("/stop-imagemaid", methods=["POST"])
def stop_imagemaid():
    config_name = session.get("config_name") or persistence.ensure_session_config_name()
    pid = helpers.get_imagemaid_pid()
    pid_file = helpers.get_imagemaid_pid_file()

    if not pid:
        procs = _find_running_imagemaid_processes()
        if not procs:
            return jsonify({"warning": "No active ImageMaid PID"}), 200
    else:
        proc = _find_running_imagemaid_process()
        procs = [proc] if proc is not None else []

    try:
        if not procs:
            return jsonify({"warning": "No active ImageMaid process found."}), 200

        _settings, section_data = _get_imagemaid_settings_section()
        imagemaid_mode = section_data.get("mode") if isinstance(section_data, dict) else None
        not_imagemaid = []
        alive_after = []
        for proc in procs:
            cmdline = " ".join(proc.cmdline() or [])
            if "imagemaid.py" not in cmdline:
                not_imagemaid.append(proc.pid)
                continue
            alive_after.extend(_stop_process_tree(proc))

        try:
            os.remove(pid_file)
        except Exception:
            pass
        _clear_imagemaid_run_context()
        try:
            _write_quickstart_imagemaid_stop_marker(
                helpers.get_imagemaid_root_path(),
                mode=imagemaid_mode,
                config_name=config_name,
                log_path=_get_latest_imagemaid_log_path(),
                reason="user_stop",
            )
        except Exception:
            pass

        if alive_after:
            alive_pids = ", ".join(str(p.pid) for p in alive_after if p is not None)
            return jsonify({"warning": f"ImageMaid stop requested, but some processes are still running: {alive_pids}"}), 200
        if not_imagemaid:
            return jsonify({"warning": f"Cleaned PID file. Non-ImageMaid PIDs detected: {', '.join(map(str, not_imagemaid))}"}), 200
        return jsonify({"success": True, "message": "ImageMaid stopped and cleaned up."}), 200
    except psutil.NoSuchProcess:
        try:
            os.remove(pid_file)
        except Exception:
            pass
        _clear_imagemaid_run_context()
        try:
            _settings, section_data = _get_imagemaid_settings_section()
            imagemaid_mode = section_data.get("mode") if isinstance(section_data, dict) else None
            _write_quickstart_imagemaid_stop_marker(
                helpers.get_imagemaid_root_path(),
                mode=imagemaid_mode,
                config_name=config_name,
                log_path=_get_latest_imagemaid_log_path(),
                reason="process_missing",
            )
        except Exception:
            pass
        return jsonify({"warning": "Process not found. Cleaned up PID file."}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to stop ImageMaid: {str(e)}"}), 500


@app.route("/imagemaid-status", methods=["GET"])
def imagemaid_status():
    try:
        _refresh_maintenance_window_availability(preserve_active_state=True)
    except Exception:
        pass
    pid = helpers.get_imagemaid_pid()
    pid_file = Path(helpers.get_imagemaid_pid_file())
    imagemaid_ctx = _get_imagemaid_run_context()
    with MAINTENANCE_STATE_LOCK:
        maintenance_active = MAINTENANCE_STATE["active"]
        maintenance_window = MAINTENANCE_STATE["window"]
        maintenance_paused = MAINTENANCE_STATE["imagemaid_paused"]
        maintenance_paused_since = MAINTENANCE_STATE["imagemaid_paused_since"]

    def pid_file_age_seconds():
        try:
            if pid_file.exists():
                return max(0.0, time.time() - pid_file.stat().st_mtime)
        except Exception:
            return None
        return None

    if not pid:
        proc = _find_running_imagemaid_process()
        if proc:
            try:
                with open(pid_file, "w", encoding="utf-8") as f:
                    f.write(str(proc.pid))
                pid = proc.pid
            except Exception:
                pid = None
    if not pid:
        try:
            _ingest_completed_live_logs("imagemaid")
        except Exception:
            pass
        _clear_imagemaid_run_context()
        return jsonify(
            status="not started",
            maintenance_active=maintenance_active,
            maintenance_paused=maintenance_paused,
            maintenance_window=maintenance_window,
            maintenance_paused_since=maintenance_paused_since,
        )

    try:
        proc = psutil.Process(pid)
        started_at_ts = None
        elapsed_seconds = None
        within_grace = False
        try:
            started_at_ts = proc.create_time()
            elapsed_seconds = max(0, int(time.time() - started_at_ts))
            within_grace = elapsed_seconds < IMAGEMAID_STARTUP_GRACE_SECONDS
        except Exception:
            age = pid_file_age_seconds()
            if age is not None:
                elapsed_seconds = max(0, int(age))
                within_grace = age < IMAGEMAID_STARTUP_GRACE_SECONDS
        if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
            try:
                cmdline = " ".join(proc.cmdline() or [])
            except Exception:
                cmdline = ""
            if "imagemaid.py" in cmdline:
                started_at = datetime.fromtimestamp(started_at_ts).isoformat()
                cpu_percent = _calculate_process_cpu_percent(proc)
                io_stats = _calculate_process_io_stats(proc, "imagemaid") or {}
                mem_rss = proc.memory_info().rss
                try:
                    for child in proc.children(recursive=True):
                        try:
                            mem_rss += child.memory_info().rss
                        except Exception:
                            continue
                except Exception:
                    pass
                mem_rss_mb = mem_rss / (1024 * 1024)
                system_cpu_percent = _calculate_system_cpu_percent()
                vm = psutil.virtual_memory()
                system_mem_used_mb = (vm.total - vm.available) / (1024 * 1024)
                system_mem_total_mb = vm.total / (1024 * 1024)
                mem_percent = (mem_rss / vm.total) * 100.0 if vm.total else None
                return jsonify(
                    status="running",
                    pid=pid,
                    started_at=started_at,
                    started_at_ts=started_at_ts,
                    elapsed_seconds=elapsed_seconds,
                    cpu_percent=round(cpu_percent, 1) if cpu_percent is not None else None,
                    memory_rss_mb=round(mem_rss_mb, 1),
                    memory_percent=round(mem_percent, 2) if mem_percent is not None else None,
                    disk_read_mb=round(io_stats.get("disk_read_mb"), 1) if io_stats.get("disk_read_mb") is not None else None,
                    disk_write_mb=round(io_stats.get("disk_write_mb"), 1) if io_stats.get("disk_write_mb") is not None else None,
                    disk_read_rate_mb_s=round(io_stats.get("disk_read_rate_mb_s"), 2) if io_stats.get("disk_read_rate_mb_s") is not None else None,
                    disk_write_rate_mb_s=round(io_stats.get("disk_write_rate_mb_s"), 2) if io_stats.get("disk_write_rate_mb_s") is not None else None,
                    system_cpu_percent=round(system_cpu_percent, 1) if system_cpu_percent is not None else None,
                    system_memory_percent=round(vm.percent, 1),
                    system_memory_used_mb=round(system_mem_used_mb, 1),
                    system_memory_total_mb=round(system_mem_total_mb, 1),
                    maintenance_active=maintenance_active,
                    maintenance_paused=maintenance_paused,
                    maintenance_window=maintenance_window,
                    maintenance_paused_since=maintenance_paused_since,
                    active_command=imagemaid_ctx.get("command"),
                    mode=imagemaid_ctx.get("mode"),
                    config_name=imagemaid_ctx.get("config_name"),
                )
            if within_grace:
                payload = {"status": "starting", "pid": pid, "elapsed_seconds": elapsed_seconds}
                if started_at_ts is not None:
                    payload["started_at"] = datetime.fromtimestamp(started_at_ts).isoformat()
                    payload["started_at_ts"] = started_at_ts
                payload["maintenance_active"] = maintenance_active
                payload["maintenance_paused"] = maintenance_paused
                payload["maintenance_window"] = maintenance_window
                payload["maintenance_paused_since"] = maintenance_paused_since
                return jsonify(payload)
        try:
            rc = proc.wait(timeout=0.1)
        except psutil.TimeoutExpired:
            if within_grace:
                payload = {"status": "starting", "pid": pid, "elapsed_seconds": elapsed_seconds}
                if started_at_ts is not None:
                    payload["started_at"] = datetime.fromtimestamp(started_at_ts).isoformat()
                    payload["started_at_ts"] = started_at_ts
                payload["maintenance_active"] = maintenance_active
                payload["maintenance_paused"] = maintenance_paused
                payload["maintenance_window"] = maintenance_window
                payload["maintenance_paused_since"] = maintenance_paused_since
                return jsonify(payload)
            rc = None
        finally:
            if not within_grace:
                try:
                    os.remove(pid_file)
                except Exception:
                    pass
                _clear_process_metric_cache(pid, "imagemaid")
                _clear_imagemaid_run_context()
        if not within_grace:
            try:
                _ingest_completed_live_logs("imagemaid")
            except Exception:
                pass
        return jsonify(
            status="done",
            return_code=rc if rc is not None else -1,
            maintenance_active=maintenance_active,
            maintenance_paused=maintenance_paused,
            maintenance_window=maintenance_window,
            maintenance_paused_since=maintenance_paused_since,
        )
    except psutil.NoSuchProcess:
        age = pid_file_age_seconds()
        if age is not None and age < IMAGEMAID_STARTUP_GRACE_SECONDS:
            return jsonify(
                status="starting",
                pid=pid,
                elapsed_seconds=max(0, int(age)),
                maintenance_active=maintenance_active,
                maintenance_paused=maintenance_paused,
                maintenance_window=maintenance_window,
                maintenance_paused_since=maintenance_paused_since,
            )
        try:
            os.remove(pid_file)
        except Exception:
            pass
        _clear_process_metric_cache(pid, "imagemaid")
        _clear_imagemaid_run_context()
        return jsonify(
            status="not started",
            maintenance_active=maintenance_active,
            maintenance_paused=maintenance_paused,
            maintenance_window=maintenance_window,
            maintenance_paused_since=maintenance_paused_since,
        )


def _schedule_quickstart_imagemaid_run_marker(imagemaid_root, mode=None, config_name=None, timeout_seconds=20):
    root = Path(imagemaid_root)
    log_dir = root / "config" / "logs"
    initial = {}
    if log_dir.exists():
        for path in log_dir.glob("*.log"):
            try:
                stat = path.stat()
                initial[str(path)] = (stat.st_mtime, stat.st_size)
            except OSError:
                continue

    def worker():
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                if log_dir.exists():
                    candidates = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
                    for path in candidates:
                        try:
                            stat = path.stat()
                        except OSError:
                            continue
                        prev = initial.get(str(path))
                        if prev is None:
                            if stat.st_size > 0:
                                _write_quickstart_imagemaid_run_marker(root, mode=mode, config_name=config_name, log_path=path)
                                return
                        elif (stat.st_mtime, stat.st_size) != prev and stat.st_size > 0:
                            _write_quickstart_imagemaid_run_marker(root, mode=mode, config_name=config_name, log_path=path)
                            return
            except Exception:
                pass
            time.sleep(0.5)
        _write_quickstart_imagemaid_run_marker(root, mode=mode, config_name=config_name)

    threading.Thread(target=worker, daemon=True).start()


@app.route("/validate_metadata_file", methods=["POST"])
def validate_metadata_file():
    data = request.get_json(silent=True) or {}
    return _validate_and_organize_library_file_request(
        "metadata_files",
        data,
        "metadata_file_type",
        "metadata_file_location",
    )


@app.route("/validate_collection_file", methods=["POST"])
def validate_collection_file():
    data = request.get_json(silent=True) or {}
    return _validate_and_organize_library_file_request(
        "collection_files",
        data,
        "collection_file_type",
        "collection_file_location",
    )


@app.route("/validate_overlay_file", methods=["POST"])
def validate_overlay_file():
    data = request.get_json(silent=True) or {}
    return _validate_and_organize_library_file_request(
        "overlay_files",
        data,
        "overlay_file_type",
        "overlay_file_location",
    )


@app.route("/restart", methods=["POST"])
def restart_quickstart():
    data = request.get_json(silent=True) or {}
    nonce = data.get("nonce")
    session_nonce = session.get("restart_nonce")

    if not nonce or nonce != session_nonce:
        return jsonify(success=False, message="Restart not authorized."), 403

    session.pop("restart_nonce", None)
    reason = data.get("reason")
    if reason == "update":
        helpers.set_restart_notice(
            "update",
            "Update complete. Quickstart restarted.",
        )

    def restart():
        # Give time for the response to complete before restarting
        time.sleep(1)
        python = sys.executable
        os.execv(python, [python] + sys.argv)

    threading.Thread(target=restart).start()
    return jsonify(success=True, message="Quickstart is restarting...")


server_thread = None
update_thread = None
if __name__ == "__main__":

    def start_flask_app():
        serve(app, host="0.0.0.0", port=port, max_request_body_size=16 * 1024 * 1024)

    def start_update_thread(app_in):
        with app_in.app_context():
            while True:
                app_in.config["VERSION_CHECK"] = helpers.check_for_update()
                helpers.ts_log("Checked for updates.", level="INFO")
                time.sleep(86400)

    update_thread = threading.Thread(target=start_update_thread, args=(app,), daemon=True)
    update_thread.start()

    maintenance_thread = threading.Thread(target=_maintenance_guard_loop, args=(app,), daemon=True)
    maintenance_thread.start()

    _start_pending_logscan_startup_migration(app)

    def get_lan_ip():
        try:
            # Connect to a dummy address to get the local IP used
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "localhost"

    try:
        from PyQt5.QtGui import QIcon
        from PyQt5.QtWidgets import (
            QApplication,
            QSystemTrayIcon,
            QMenu,
            QAction,
            QInputDialog,
            QMessageBox,
            QWidget,
        )
        from PyQt5.QtCore import Qt, QTimer

        if app.config["QUICKSTART_DOCKER"]:
            has_tray = False
        elif sys.platform.startswith("linux"):
            has_tray = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        elif sys.platform == "darwin" or sys.platform.startswith("win"):
            has_tray = True
        else:
            has_tray = False
    except (ModuleNotFoundError, ImportError):
        has_tray = False

    if not has_tray:
        # Headless mode: skip system tray
        helpers.ts_log("Running in headless mode — no system tray will be shown...", level="INFO")
        if app.config["QUICKSTART_DOCKER"]:
            helpers.ts_log("Quickstart is Running inside Docker.", level="INFO")
            helpers.ts_log(f"Access it at http://<your-server-ip>:{running_port}", level="INFO")
            helpers.ts_log("Note: This IP is the HOST machine IP, not the container IP.", level="INFO")
        else:
            ip_address = get_lan_ip()
            helpers.ts_log("Quickstart is Running", level="INFO")
            helpers.ts_log(f"Access it at http://{ip_address}:{running_port}", level="INFO")

        helpers.ts_log(
            f"Port and Debug Settings can be amended via the Settings cog in the UI or by editing your {DOTENV} file",
            level="INFO",
        )
        server_thread = Thread(target=start_flask_app)
        server_thread.daemon = True
        server_thread.start()

        try:
            while not shutdown_event.is_set():
                time.sleep(1)  # Keep main thread alive
        except KeyboardInterrupt:
            helpers.ts_log("\nShutting down Quickstart...", level="INFO")
            sys.exit(0)

        helpers.ts_log("Shutting down Quickstart...", level="INFO")
        sys.exit(0)

    else:
        # GUI mode: show tray

        server_thread = Thread(target=start_flask_app)
        server_thread.daemon = True
        server_thread.start()

        class QuickstartTrayApp:
            def __init__(self):
                self.app = QApplication(sys.argv)
                self.app.setQuitOnLastWindowClosed(False)
                self.app.setApplicationName("Quickstart")

                self.dialog_parent = QWidget()
                self.dialog_parent.setWindowTitle("Quickstart")
                self.dialog_parent.setAttribute(Qt.WA_DontShowOnScreen, True)

                self.tray = QSystemTrayIcon()
                self.icon_path = os.path.join(helpers.MEIPASS_DIR, "static", "favicon.png")

                self.tray.setIcon(QIcon(self.icon_path))
                self.tray.setToolTip(f"Quickstart (Port: {running_port})")

                self.menu = QMenu()

                self.open_action = QAction(f"Open Quickstart (Port: {running_port})")
                self.open_action.triggered.connect(self.open_quickstart)

                self.github_action = QAction("Quickstart GitHub")
                self.github_action.triggered.connect(lambda: webbrowser.open("https://github.com/Kometa-Team/Quickstart"))

                self.toggle_debug_action = QAction(f"{'Disable' if debug_mode else 'Enable'} Debug")
                self.toggle_debug_action.triggered.connect(self.toggle_debug)

                self.change_port_action = QAction("Change Port")
                self.change_port_action.triggered.connect(self.change_port)

                self.quit_action = QAction("Exit")
                self.quit_action.triggered.connect(self.quit_app)

                self.menu.addAction(self.open_action)
                self.menu.addAction(self.github_action)
                self.menu.addSeparator()
                self.menu.addAction(self.toggle_debug_action)
                self.menu.addAction(self.change_port_action)
                self.menu.addSeparator()
                self.menu.addAction(self.quit_action)

                self.tray.setContextMenu(self.menu)
                self.tray.show()

                ip_address = get_lan_ip()

                self.tray.showMessage(
                    "Quickstart is Running",
                    f"Local: http://localhost:{running_port}\nLAN: http://{ip_address}:{running_port}",
                    QSystemTrayIcon.NoIcon,
                    8000,
                )

                helpers.ts_log("Quickstart is Running", level="INFO")
                helpers.ts_log(f"Access it locally at: http://localhost:{running_port}", level="INFO")
                helpers.ts_log(f"Access it from other devices at: http://{ip_address}:{running_port}", level="INFO")
                helpers.ts_log(
                    f"Port and Debug Settings can be amended via the Settings cog in the UI, " f"right-clicking the system tray icon, or by editing your {DOTENV} file",
                    level="INFO",
                )
                if app.config.get("QS_SKIP_AUTO_OPEN"):
                    helpers.ts_log("Skipping auto-open after update restart.", level="INFO")
                else:
                    # Open the browser automatically
                    webbrowser.open(f"http://localhost:{running_port}")

                # Keep the invisible parent alive
                self.dialog_parent.showMinimized()
                self.dialog_parent.hide()

                # Ensure Qt stays alive (important in tray-only apps)
                QTimer.singleShot(0, lambda: None)  # No-op to lock event loop

            def exec(self):
                """Run the Qt app loop."""
                self.app.exec()

            def open_quickstart(self):
                webbrowser.open(f"http://localhost:{running_port}")

            def toggle_debug(self):
                global debug_mode
                debug_mode = not debug_mode
                helpers.update_env_variable("QS_DEBUG", "1" if debug_mode else "0")
                app.config["QS_DEBUG"] = debug_mode
                self.toggle_debug_action.setText(f"{'Disable' if debug_mode else 'Enable'} Debug")

            def show_messagebox(self, box_type, title, text):
                box = QMessageBox(self.dialog_parent)
                box.setWindowTitle(title)
                box.setText(text)
                box.setIcon(box_type)
                box.setStandardButtons(QMessageBox.Ok)
                box.setWindowFlags(box.windowFlags() & ~Qt.WindowContextHelpButtonHint)
                box.setWindowIcon(QIcon(self.icon_path))
                box.exec()

            def change_port(self):
                global port
                try:
                    helpers.ts_log("Launching custom port input dialog...", level="DEBUG")

                    dialog = QInputDialog(self.dialog_parent)
                    dialog.setWindowTitle("Change Port")
                    dialog.setLabelText("Enter a new port number:")
                    dialog.setInputMode(QInputDialog.IntInput)
                    dialog.setIntMinimum(1)
                    dialog.setIntMaximum(65535)
                    dialog.setIntValue(port)

                    # Remove help button and set custom icon
                    dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
                    dialog.setWindowIcon(QIcon(self.icon_path))

                    # Execute dialog
                    if dialog.exec() != QInputDialog.Accepted:
                        helpers.ts_log("Port change canceled by user.", level="INFO")
                        return

                    new_port = dialog.intValue()
                    helpers.ts_log(f"User entered new port: {new_port}", level="INFO")

                    if new_port == port:
                        self.show_messagebox(
                            QMessageBox.Information,
                            "Port Already Selected",
                            f"Port {new_port} is already selected.",
                        )
                    else:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                            if sock.connect_ex(("localhost", new_port)) == 0:
                                self.show_messagebox(
                                    QMessageBox.Warning,
                                    "Port Conflict",
                                    f"Port {new_port} is already in use.\nClose any conflicting applications or choose another port.",
                                )
                            else:
                                helpers.update_env_variable("QS_PORT", new_port)
                                self.show_messagebox(
                                    QMessageBox.Information,
                                    "Port Updated",
                                    f"Port number updated to {new_port}.\nQuickstart will now restart automatically.",
                                )
                                self.restart_quickstart()

                except Exception as e:
                    helpers.ts_log(f"Port change error: {e}", level="ERROR")

            def quit_app(self):
                global server_thread, update_thread

                helpers.ts_log("Shutting down Quickstart...", level="INFO")

                # Stop tray icon
                self.tray.hide()

                # Optionally stop Flask server (if you have added a stop hook)
                # For now, just wait for background threads to finish
                if server_thread and server_thread.is_alive():
                    helpers.ts_log("Waiting for server thread to exit...", level="DEBUG")
                    server_thread.join(timeout=2)

                if update_thread and update_thread.is_alive():
                    helpers.ts_log("Waiting for update thread to exit...", level="DEBUG")
                    update_thread.join(timeout=2)

                # Exit the Qt app loop
                self.app.quit()

            def restart_quickstart(self):
                """Cleanly restart the Quickstart application."""
                helpers.ts_log("Restarting Quickstart...", level="INFO")
                self.tray.hide()

                python = sys.executable
                os.execl(python, python, *sys.argv)

        QuickstartTrayApp().exec()
