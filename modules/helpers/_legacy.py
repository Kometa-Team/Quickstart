import os
import sys
import time

from pathlib import Path

import requests
from flask import current_app as app
from flask import has_app_context, has_request_context, session

from modules.helpers._logging import ts_log

STRING_FIELDS = {"apikey", "token", "username", "password"}
GITHUB_BASE_URL = "https://raw.githubusercontent.com/Kometa-Team/Kometa"
IMAGEMAID_GITHUB_BASE_URL = "https://raw.githubusercontent.com/Kometa-Team/ImageMaid"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "bmp"}
FONT_EXTENSIONS = {".ttf", ".otf"}

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
WORKING_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else BASE_DIR
MEIPASS_DIR = sys._MEIPASS if getattr(sys, "frozen", False) else BASE_DIR  # noqa

JSON_SETTINGS = os.path.join(MEIPASS_DIR, "static", "json")

CONFIG_DIR = os.path.join(WORKING_DIR, "config")
os.makedirs(CONFIG_DIR, exist_ok=True)

JSON_SCHEMA_DIR = os.path.join(CONFIG_DIR, ".schema")
os.makedirs(JSON_SCHEMA_DIR, exist_ok=True)

HASH_FILE = os.path.join(JSON_SCHEMA_DIR, "file_hashes.txt")
VERSION_FILE = os.path.join(MEIPASS_DIR, "VERSION")
BUILDNUM_FILE = os.path.join(MEIPASS_DIR, "BUILDNUM")

RESTART_NOTICE_FILE = os.path.join(CONFIG_DIR, ".restart_notice.json")
PLEX_DISCOVERY_CACHE_TTL_SECONDS = int(os.environ.get("QS_PLEX_DISCOVERY_CACHE_TTL_SECONDS", "300"))
JSON_SCHEMA_REFRESH_TTL_SECONDS = int(os.environ.get("QS_JSON_SCHEMA_REFRESH_TTL_SECONDS", "1800"))
_JSON_SCHEMA_LAST_REFRESH_AT = 0.0
QS_UPDATE_CACHE_TTL_SECONDS = int(os.environ.get("QS_UPDATE_CACHE_TTL_SECONDS", "600"))
_QS_UPDATE_CACHE = {}
KOMETA_UPDATE_CACHE_TTL_SECONDS = int(os.environ.get("QS_KOMETA_UPDATE_CACHE_TTL_SECONDS", "600"))
_KOMETA_UPDATE_CACHE = {}
KOMETA_BRANCH_OVERRIDES = {"master", "develop", "nightly"}
IMAGEMAID_UPDATE_CACHE_TTL_SECONDS = int(os.environ.get("QS_IMAGEMAID_UPDATE_CACHE_TTL_SECONDS", "600"))
_IMAGEMAID_UPDATE_CACHE = {}
IMAGEMAID_BRANCH_OVERRIDES = {"master", "develop"}

JSON_SCHEMA_SYNC_FILES = (
    ("README.md", "json-schema/README.md"),
    ("MODULE.md", "json-schema/MODULE.md"),
    ("collection-schema.json", "json-schema/collection-schema.json"),
    ("config-schema.json", "json-schema/config-schema.json"),
    ("kitchen_sink_config.yml", "json-schema/kitchen_sink_config.yml"),
    ("metadata-schema.json", "json-schema/metadata-schema.json"),
    ("overlay-schema.json", "json-schema/overlay-schema.json"),
    ("playlist-schema.json", "json-schema/playlist-schema.json"),
    ("prototype_comprehensive.yml", "json-schema/prototype_comprehensive.yml"),
    ("prototype_config.yml", "json-schema/prototype_config.yml"),
    ("template-schema.json", "json-schema/template-schema.json"),
    ("builders/anidb.yml", "json-schema/builders/anidb.yml"),
    ("builders/anilist.yml", "json-schema/builders/anilist.yml"),
    ("builders/dynamic_collections.yml", "json-schema/builders/dynamic_collections.yml"),
    ("builders/imdb.yml", "json-schema/builders/imdb.yml"),
    ("builders/letterboxd.yml", "json-schema/builders/letterboxd.yml"),
    ("builders/mdblist.yml", "json-schema/builders/mdblist.yml"),
    ("builders/metadata.yml", "json-schema/builders/metadata.yml"),
    ("builders/myanimelist.yml", "json-schema/builders/myanimelist.yml"),
    ("builders/other.yml", "json-schema/builders/other.yml"),
    ("builders/overlays.yml", "json-schema/builders/overlays.yml"),
    ("builders/playlists.yml", "json-schema/builders/playlists.yml"),
    ("builders/plex.yml", "json-schema/builders/plex.yml"),
    ("builders/radarr.yml", "json-schema/builders/radarr.yml"),
    ("builders/sonarr.yml", "json-schema/builders/sonarr.yml"),
    ("builders/tautulli.yml", "json-schema/builders/tautulli.yml"),
    ("builders/tmdb.yml", "json-schema/builders/tmdb.yml"),
    ("builders/trakt.yml", "json-schema/builders/trakt.yml"),
    ("builders/tvdb.yml", "json-schema/builders/tvdb.yml"),
    ("config.yml.template", "config/config.yml.template"),
)


def ensure_json_schema():
    """Ensure json-schema files exist and are up-to-date based on hash checks."""
    from modules.helpers._schema import _schema_files_present, calculate_hash, load_previous_hashes, save_hashes

    global _JSON_SCHEMA_LAST_REFRESH_AT

    # branch = get_kometa_branch()
    branch = "nightly"

    if _schema_files_present() and _JSON_SCHEMA_LAST_REFRESH_AT <= 0:
        try:
            reference_path = Path(HASH_FILE if os.path.exists(HASH_FILE) else os.path.join(JSON_SCHEMA_DIR, "config-schema.json"))
            _JSON_SCHEMA_LAST_REFRESH_AT = time.monotonic() - max(0, time.time() - reference_path.stat().st_mtime)
        except Exception:
            _JSON_SCHEMA_LAST_REFRESH_AT = time.monotonic()

    if _schema_files_present():
        age = time.monotonic() - _JSON_SCHEMA_LAST_REFRESH_AT
        if _JSON_SCHEMA_LAST_REFRESH_AT > 0 and age <= JSON_SCHEMA_REFRESH_TTL_SECONDS:
            return

    previous_hashes = load_previous_hashes()
    new_hashes = {}

    for filename, remote_path in JSON_SCHEMA_SYNC_FILES:
        url = f"{GITHUB_BASE_URL}/{branch}/{remote_path}"
        file_path = os.path.join(JSON_SCHEMA_DIR, filename)  # Store everything in json-schema

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            new_content = response.text
            new_hash = calculate_hash(new_content)

            # Compare hash with previous version, but re-download if file is missing
            if filename in previous_hashes and previous_hashes[filename] == new_hash and os.path.exists(file_path):
                new_hashes[filename] = new_hash  # Keep existing hash
                continue

            # Save the new file if hash has changed
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            new_hashes[filename] = new_hash

        except requests.RequestException as e:
            ts_log(f"Failed to download {filename} from {url}: {e}", level="ERROR")
            continue  # Skip to the next file

    # Save updated hashes
    save_hashes(new_hashes)
    if _schema_files_present():
        _JSON_SCHEMA_LAST_REFRESH_AT = time.monotonic()


def save_to_named_config(yaml_text, config_name, font_refs=None):
    config_dir = Path(CONFIG_DIR)
    kometa_root = get_kometa_root_path()
    kometa_config_dir = get_kometa_config_dir()
    from modules import helpers as _h_artifacts

    name = _h_artifacts.require_config_name_for_storage(config_name, context="Saving a named config")
    latest_filename = f"{name}_config.yml"
    latest_path = config_dir / latest_filename
    kometa_path = kometa_config_dir / latest_filename
    history_limit = app.config.get("QS_CONFIG_HISTORY", 0)
    try:
        history_limit = int(str(history_limit).strip())
    except (TypeError, ValueError):
        history_limit = 0
    if history_limit < 0:
        history_limit = 0

    from modules.helpers._file_utils import _read_text_if_exists

    existing_local_yaml = _read_text_if_exists(latest_path)
    local_needs_write = existing_local_yaml != yaml_text

    config_dir.mkdir(parents=True, exist_ok=True)
    kometa_write_ok = True
    try:
        kometa_config_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        kometa_write_ok = False
        ts_log(f"Failed to create Kometa config directory {kometa_config_dir}: {exc}", level="WARNING")

    if kometa_write_ok:
        existing_kometa_yaml = _read_text_if_exists(kometa_path)
        kometa_needs_write = existing_kometa_yaml != yaml_text
    else:
        kometa_needs_write = False

    # Only rotate config history when the generated YAML actually changed.
    if local_needs_write and latest_path.exists():
        archive_dir = config_dir / "archives" / name
        archive_dir.mkdir(parents=True, exist_ok=True)
        counter = 1
        while True:
            archive_path = archive_dir / f"{name}_config_{counter}.yml"
            if not archive_path.exists():
                latest_path.rename(archive_path)
                ts_log(f"Archived old config to: {archive_path}")
                break
            counter += 1
        if history_limit > 0:
            archives = sorted(archive_dir.glob(f"{name}_config_*.yml"), key=lambda p: p.stat().st_mtime)
            if len(archives) > history_limit:
                for old_path in archives[: len(archives) - history_limit]:
                    try:
                        old_path.unlink()
                    except Exception as exc:
                        ts_log(f"Failed to prune archive {old_path}: {exc}", level="WARNING")

    if local_needs_write:
        try:
            with open(latest_path, "w", encoding="utf-8") as f:
                f.write(yaml_text)
        except OSError as exc:
            ts_log(f"Failed to write Quickstart config to {latest_path}: {exc}", level="WARNING")
            raise

    if kometa_write_ok and kometa_needs_write:
        try:
            with open(kometa_path, "w", encoding="utf-8") as f:
                f.write(yaml_text)
        except OSError as exc:
            kometa_write_ok = False
            ts_log(f"Failed to write Kometa config to {kometa_path}: {exc}", level="WARNING")

    if font_refs and kometa_write_ok:
        from modules import helpers as _helpers

        try:
            font_result = _helpers.copy_fonts_to_kometa(font_refs, kometa_root=kometa_root, kometa_config_dir=kometa_config_dir, config_name=name)
            missing = font_result.get("missing", [])
            errors = font_result.get("errors", [])
            if missing:
                ts_log(f"Missing fonts not copied to Kometa: {', '.join(missing)}", level="WARNING")
            for err in errors:
                ts_log(err, level="WARNING")
        except Exception as exc:
            ts_log(f"Failed to sync fonts to Kometa: {exc}", level="WARNING")

    if kometa_write_ok:
        from modules import helpers as _h_artifacts

        try:
            artifact_result = _h_artifacts.sync_managed_library_artifacts_to_kometa(name, kometa_root=kometa_root, kometa_config_dir=kometa_config_dir)
            synced = artifact_result.get("synced", [])
            removed = artifact_result.get("removed", [])
            errors = artifact_result.get("errors", [])
            if synced:
                ts_log(f"Synced {len(synced)} managed library artifact tree(s) to Kometa target/{name}.")
            if removed:
                ts_log(f"Removed {len(removed)} stale managed library artifact tree(s) from Kometa target/{name}.")
            for err in errors:
                ts_log(err, level="WARNING")
        except Exception as exc:
            ts_log(f"Failed to sync managed library artifacts to Kometa: {exc}", level="WARNING")

    if local_needs_write:
        ts_log(f"Saved new config to: {latest_path}")
    else:
        ts_log(f"Config unchanged; reused existing Quickstart config at: {latest_path}")
    if kometa_write_ok and kometa_needs_write:
        ts_log(f"Also copied config to: {kometa_path}")
    elif kometa_write_ok:
        ts_log(f"Kometa config unchanged; reused existing copy at: {kometa_path}")

    # Return POSIX-style filename (used for CLI path like --config config/name_config.yml)
    return latest_path.name


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
