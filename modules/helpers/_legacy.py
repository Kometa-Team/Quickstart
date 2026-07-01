import datetime
import io
import os
import psutil
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
import copy

from pathlib import Path
from plexapi.server import PlexServer
from modules import persistence

import requests
from flask import current_app as app
from flask import has_app_context, has_request_context, session

try:
    from git import Repo
except ImportError:
    Repo = None  # Prevents errors if GitPython is missing


STRING_FIELDS = {"apikey", "token", "username", "password"}
GITHUB_BASE_URL = "https://raw.githubusercontent.com/Kometa-Team/Kometa"
GITHUB_API_BRANCH = "https://api.github.com/repos/kometa-team/Kometa/branches/{branch}"
GITHUB_ZIP_URL = "https://codeload.github.com/kometa-team/Kometa/zip/refs/heads/{branch}"
IMAGEMAID_GITHUB_BASE_URL = "https://raw.githubusercontent.com/Kometa-Team/ImageMaid"
IMAGEMAID_GITHUB_API_BRANCH = "https://api.github.com/repos/kometa-team/ImageMaid/branches/{branch}"
IMAGEMAID_GITHUB_ZIP_URL = "https://codeload.github.com/kometa-team/ImageMaid/zip/refs/heads/{branch}"

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

LOG_DIR = os.path.join("config", "logs")
LOG_FILE = os.path.join(LOG_DIR, "quickstart.log")
MAX_LOG_BACKUPS = 10
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


def _kometa_update_cache_key(kometa_root, branch, local_version, local_sha=None, local_branch=None):
    try:
        root = str(Path(kometa_root).resolve())
    except Exception:
        root = str(kometa_root or "")
    return root, str(branch or "").strip(), str(local_version or "").strip(), str(local_sha or "").strip(), str(local_branch or "").strip()


def normalize_kometa_branch_override(value):
    branch = str(value or "").strip().lower()
    return branch if branch in KOMETA_BRANCH_OVERRIDES else ""


def resolve_kometa_update_branch(branch_override=None):
    branch = normalize_kometa_branch_override(branch_override)
    return branch or get_kometa_branch()


def get_cached_kometa_update(kometa_root=None, force_refresh=False, branch_override=None):
    branch = resolve_kometa_update_branch(branch_override)
    local_version = get_kometa_local_version(kometa_root)
    local_sha = get_kometa_local_sha(kometa_root)
    local_branch = get_kometa_local_branch(kometa_root)
    key = _kometa_update_cache_key(kometa_root or ".", branch, local_version, local_sha=local_sha, local_branch=local_branch)

    if not force_refresh:
        entry = _KOMETA_UPDATE_CACHE.get(key)
        if entry:
            age = time.monotonic() - entry.get("created_at", 0)
            if age <= KOMETA_UPDATE_CACHE_TTL_SECONDS:
                payload = copy.deepcopy(entry.get("payload") or {})
                payload["cached"] = True
                return payload
            _KOMETA_UPDATE_CACHE.pop(key, None)

    payload = check_kometa_update(kometa_root, branch_override=branch_override)
    if isinstance(payload, dict):
        payload = copy.deepcopy(payload)
        payload["cached"] = False
        _KOMETA_UPDATE_CACHE[key] = {
            "created_at": time.monotonic(),
            "payload": copy.deepcopy(payload),
        }
        return payload
    return {
        "local_version": local_version,
        "local_sha": local_sha,
        "local_branch": local_branch,
        "remote_version": None,
        "remote_sha": None,
        "branch": branch,
        "update_available": False,
        "cached": False,
    }


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


def invalidate_cached_kometa_update(kometa_root=None):
    if kometa_root is None:
        _KOMETA_UPDATE_CACHE.clear()
        return
    try:
        target_root = str(Path(kometa_root).resolve())
    except Exception:
        target_root = str(kometa_root or "")
    for key in list(_KOMETA_UPDATE_CACHE.keys()):
        if key[0] == target_root:
            _KOMETA_UPDATE_CACHE.pop(key, None)


def _imagemaid_update_cache_key(imagemaid_root, branch, local_version=None, local_sha=None, local_branch=None):
    try:
        root = str(Path(imagemaid_root).resolve())
    except Exception:
        root = str(imagemaid_root or "")
    return root, str(branch or "").strip(), str(local_version or "").strip(), str(local_sha or "").strip(), str(local_branch or "").strip()


def normalize_imagemaid_branch_override(value):
    branch = str(value or "").strip().lower()
    return branch if branch in IMAGEMAID_BRANCH_OVERRIDES else ""


def resolve_imagemaid_update_branch(branch_override=None):
    branch = normalize_imagemaid_branch_override(branch_override)
    if branch:
        return branch
    from modules.helpers._git import detect_git_branch

    qs_branch = detect_git_branch(get_app_root())
    return "master" if qs_branch == "master" else "develop"


def get_cached_imagemaid_update(imagemaid_root=None, force_refresh=False, branch_override=None):
    branch = resolve_imagemaid_update_branch(branch_override)
    local_version = get_imagemaid_local_version(imagemaid_root)
    local_sha = get_imagemaid_local_sha(imagemaid_root)
    local_branch = get_imagemaid_local_branch(imagemaid_root)
    key = _imagemaid_update_cache_key(imagemaid_root or ".", branch, local_version=local_version, local_sha=local_sha, local_branch=local_branch)

    if not force_refresh:
        entry = _IMAGEMAID_UPDATE_CACHE.get(key)
        if entry:
            age = time.monotonic() - entry.get("created_at", 0)
            if age <= IMAGEMAID_UPDATE_CACHE_TTL_SECONDS:
                payload = copy.deepcopy(entry.get("payload") or {})
                payload["cached"] = True
                return payload
            _IMAGEMAID_UPDATE_CACHE.pop(key, None)

    payload = check_imagemaid_update(imagemaid_root, branch_override=branch_override)
    if isinstance(payload, dict):
        payload = copy.deepcopy(payload)
        payload["cached"] = False
        _IMAGEMAID_UPDATE_CACHE[key] = {
            "created_at": time.monotonic(),
            "payload": copy.deepcopy(payload),
        }
        return payload
    return {
        "local_version": local_version,
        "local_sha": local_sha,
        "local_branch": local_branch,
        "remote_version": None,
        "remote_sha": None,
        "branch": branch,
        "update_available": False,
        "cached": False,
    }


def invalidate_cached_imagemaid_update(imagemaid_root=None):
    if imagemaid_root is None:
        _IMAGEMAID_UPDATE_CACHE.clear()
        return
    try:
        target_root = str(Path(imagemaid_root).resolve())
    except Exception:
        target_root = str(imagemaid_root or "")
    for key in list(_IMAGEMAID_UPDATE_CACHE.keys()):
        if key[0] == target_root:
            _IMAGEMAID_UPDATE_CACHE.pop(key, None)


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


def get_branch():
    """Determine the current branch with Docker support."""


def get_kometa_branch():
    """Fetch the correct branch (master or nightly)."""
    version_info = check_for_update()
    return version_info.get("kometa_branch", "nightly")  # Default to nightly branch


def get_version(branch):
    """Read the local VERSION file"""
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            version = f.read().strip()
            if branch == "master":
                return version
            build_num = "0"
            if os.path.exists(BUILDNUM_FILE):
                with open(BUILDNUM_FILE, "r", encoding="utf-8") as g:
                    build_num = g.read().strip()
            return f"{version}-build{build_num}"
    return "unknown"


def check_for_update():
    from modules.helpers._version import get_branch, get_remote_version

    """Compare the local version with the remote version and determine Kometa branch."""
    branch = get_branch()
    local_version = get_version(branch)
    cache_key = (branch, local_version)
    cached = _QS_UPDATE_CACHE.get(cache_key)
    if cached:
        age = time.monotonic() - cached.get("created_at", 0)
        if age <= QS_UPDATE_CACHE_TTL_SECONDS:
            return copy.deepcopy(cached.get("payload") or {})

    remote_version = get_remote_version(branch)

    update_available = remote_version and remote_version != local_version

    # Determine Kometa branch
    # kometa_branch = "master" if branch == "master" else "nightly"
    kometa_branch = "nightly"

    # Get OS name and correct extension
    from modules.helpers._os import get_running_os

    os_name, os_ext = get_running_os()

    payload = {
        "local_version": local_version,
        "remote_version": remote_version,
        "branch": branch,
        "kometa_branch": kometa_branch,
        "update_available": update_available,
        "running_on": os_name,
        "file_ext": os_ext,
    }
    _QS_UPDATE_CACHE[cache_key] = {
        "created_at": time.monotonic(),
        "payload": copy.deepcopy(payload),
    }
    return payload


def get_top_imdb_items(library_id, media_type, placeholder_id=None):
    ts_log("Fetching Plex credentials for '010-plex'", level="DEBUG")
    plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")

    ts_log(f"Connecting to Plex with URL: {plex_url}", level="DEBUG")
    plex = PlexServer(plex_url, plex_token)

    for section in plex.library.sections():
        ts_log(f"Section: key={section.key}, title={section.title}", level="DEBUG")

    ts_log(f"Searching for section with ID or title: {library_id}", level="DEBUG")
    section = next(
        (s for s in plex.library.sections() if str(s.key) == str(library_id) or s.title.lower() == str(library_id).lower()),
        None,
    )

    if not section:
        raise ValueError(f"Library ID {library_id} not found.")

    ts_log(f"Fetching items from '{section.title}' sorted by audienceRating", level="DEBUG")
    items = section.search(sort="audienceRating:desc", maxresults=25)

    imdb_items = []
    for item in items:
        imdb_id = None
        for guid in item.guids:
            if guid.id.startswith("imdb://"):
                imdb_id = guid.id.replace("imdb://", "")
                break
        if imdb_id:
            imdb_items.append({"id": imdb_id, "title": item.title})

    # Best-effort placeholder recovery; disabled fallback to avoid missing module issues
    saved_item = None

    ts_log(f"Returning {len(imdb_items)} IMDb items", level="DEBUG")
    return imdb_items, saved_item


def get_plex_key_by_name(full_list, target_name):
    """
    Given a list of dicts with 'name' and 'plex_key', return the matching plex_key by name.
    """
    for lib in full_list:
        if lib.get("name") == target_name:
            return lib.get("plex_key")
    return None  # Or raise an exception if you prefer


def _extract_imdb_id_from_item(item):
    for guid in getattr(item, "guids", []) or []:
        guid_id = str(getattr(guid, "id", "") or "").strip().lower()
        if guid_id.startswith("imdb://"):
            return guid_id.replace("imdb://", "", 1)
    return ""


def _normalize_lookup_title(value):
    normalized = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return normalized


def find_item_by_title(library_name, title):
    normalized_title = _normalize_lookup_title(title)
    if not normalized_title:
        return None

    plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")
    if not plex_url or not plex_token:
        return None

    plex = PlexServer(plex_url, plex_token, timeout=8)

    try:
        section = plex.library.section(library_name)
    except Exception:
        return None

    results = section.search(title=title, maxresults=20)
    for item in results or []:
        item_title = str(getattr(item, "title", "") or "").strip()
        if _normalize_lookup_title(item_title) == normalized_title:
            return {"title": item_title}
    return None


def find_item_by_imdb_id(library_name, imdb_id, media_type, fallback_title=None):
    normalized_imdb_id = str(imdb_id or "").strip().lower()
    if not normalized_imdb_id:
        return None

    plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")
    if not plex_url or not plex_token:
        return None

    plex = PlexServer(plex_url, plex_token, timeout=8)

    try:
        section = plex.library.section(library_name)
    except Exception:
        return None

    def build_match(item, source):
        title = str(getattr(item, "title", "") or "").strip()
        if not title:
            return None
        return {"id": normalized_imdb_id, "title": title, "source": source}

    def find_exact_imdb_match(candidates, source):
        for item in candidates or []:
            if _extract_imdb_id_from_item(item) == normalized_imdb_id:
                return build_match(item, source)
        return None

    direct_guid_match = find_exact_imdb_match(
        section.search(guid=f"imdb://{normalized_imdb_id}"),
        "plex-guid",
    )
    if direct_guid_match:
        return direct_guid_match

    if fallback_title:
        title_results = section.search(title=fallback_title, maxresults=20)
        exact_title_guid_match = find_exact_imdb_match(title_results, "plex-title-guid")
        if exact_title_guid_match:
            return exact_title_guid_match

        normalized_fallback_title = _normalize_lookup_title(fallback_title)
        for item in title_results or []:
            if _normalize_lookup_title(getattr(item, "title", "")) == normalized_fallback_title:
                return build_match(item, "plex-title")

    return None


def get_plex_summary():
    try:
        metadata = get_plex_metadata()
        if not isinstance(metadata, dict):
            return "Plex summary unavailable."

        server_name = metadata.get("server_name") or "Plex Server"
        version = metadata.get("version") or "Unknown Version"
        platform = metadata.get("platform") or "Unknown OS"
        platform_version = metadata.get("platformVersion") or "Unknown Version"
        db_cache_str = metadata.get("db_cache") or "Unknown"

        update_channel = metadata.get("update_channel")
        if update_channel == "Public update channel":
            update_channel_str = "Public update channel."
        elif update_channel == "PlexPass update channel":
            update_channel_str = "PlexPass update channel."
        elif update_channel:
            update_channel_str = f"{update_channel}."
        else:
            update_channel_str = "Unknown update channel."

        plex_pass = metadata.get("plex_pass", "Unknown")
        plex_pass_str = f"PlexPass: {plex_pass} on {update_channel_str}"
        maintenance_window_value = metadata.get("maintenance_window") or "Unavailable"
        if maintenance_window_value and maintenance_window_value != "Unavailable":
            maintenance_window = f"Scheduled maintenance running between {maintenance_window_value}"
        else:
            maintenance_window = "Scheduled maintenance times could not be found."

        # Final summary string
        return (
            f"Connected to Plex server {server_name} version {version}\n"
            f"Running on {platform} version {platform_version}\n"
            f"Plex DB cache setting: {db_cache_str}\n"
            f"{plex_pass_str}\n"
            f"{maintenance_window}"
        )

    except Exception as e:
        return f"Plex summary unavailable due to error: {e}"


def get_plex_maintenance_hours(plex_url, plex_token):
    if not plex_url or not plex_token:
        return None, None
    try:
        plex = PlexServer(plex_url, plex_token, timeout=8)
        settings = plex.settings
        start_hour = int(settings.get("butlerStartHour").value)
        end_hour = int(settings.get("butlerEndHour").value)
        return start_hour, end_hour
    except Exception:
        return None, None


def get_library_summaries(configured_library_names):
    try:
        metadata = get_plex_metadata()
        lib_metadata = metadata.get("libraries", {})

        output_lines = []
        for lib_name in configured_library_names:
            info = lib_metadata.get(lib_name)
            if not info:
                output_lines.append(f"Library '{lib_name}' not found on Plex server.")
                continue

            output_lines.append(f"Information on library: {lib_name}")
            output_lines.append(f"Type: {info.get('type', 'Unknown').capitalize()}")
            output_lines.append(f"Agent: {info.get('agent', 'Unknown')}")
            output_lines.append(f"Scanner: {info.get('scanner', 'Unknown')}")
            output_lines.append(f"Ratings Source: {info.get('ratings_source', 'N/A')}")

            if info.get("type") == "movie":
                count = info.get("movie_count", 0)
                output_lines.append(f"Content Count: {count} movies")

            elif info.get("type") == "show":
                show_count = info.get("show_count", 0)
                episode_count = info.get("episode_count", 0)
                output_lines.append(f"Content Count: {show_count} shows / {episode_count} episodes")

            else:
                item_count = info.get("item_count", 0)
                output_lines.append(f"Content Count: {item_count} items")

            output_lines.append("")  # Blank line between libraries

        return "\n".join(output_lines).strip()

    except Exception as e:
        return f"Plex library summary unavailable: {str(e)}"


def get_plex_metadata(plex_url=None, plex_token=None):
    try:
        if not plex_url or not plex_token:
            plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")

        from modules import helpers as _h_plex_cache

        cached = _h_plex_cache.get_cached_plex_metadata(plex_url, plex_token)
        if cached:
            ts_log("Using cached Plex metadata payload.", level="DEBUG")
            return cached

        plex = PlexServer(plex_url, plex_token)

        # Plex Pass
        try:
            plex_pass = plex.myPlexAccount().subscriptionActive
        except Exception:
            plex_pass = False

        # Update Channel
        try:
            update_channel_value = plex.settings.get("butlerUpdateChannel").value
            if update_channel_value == "16":
                update_channel = "Public update channel"
            elif update_channel_value == "8":
                update_channel = "PlexPass update channel"
            else:
                update_channel = f"Unknown update channel (raw: {update_channel_value})"
        except Exception:
            update_channel = "Unknown update channel"

        # DB Cache
        try:
            db_cache_size = plex.settings.get("DatabaseCacheSize").value
            db_cache_str = f"{db_cache_size} MB"
        except Exception:
            db_cache_str = "Unknown"

        # Maintenance window
        try:
            start_hour = int(plex.settings.get("butlerStartHour").value)
            end_hour = int(plex.settings.get("butlerEndHour").value)
            maintenance_window = f"{start_hour:02d}:00 – {end_hour:02d}:00"
        except Exception:
            maintenance_window = "Unavailable"

        # Per-library info. Fetch sections once so metadata and counts share the same section list.
        sections = plex.library.sections()
        library_metadata = get_library_metadata(plex=plex, sections=sections)

        metadata = {
            "plex_pass": plex_pass,
            "update_channel": update_channel,
            "server_name": plex.friendlyName,
            "version": plex.version,
            "platform": plex.platform,
            "platformVersion": plex.platformVersion,
            "db_cache": db_cache_str,
            "maintenance_window": maintenance_window,
            "libraries": library_metadata,
        }
        from modules import helpers as _h_plex_cache

        _h_plex_cache.set_cached_plex_metadata(plex_url, plex_token, metadata)
        return metadata

    except Exception as e:
        return {
            "plex_pass": False,
            "update_channel": None,
            "error": str(e),
            "libraries": {},
            "ratings_source": "Unavailable",
            "db_cache": "Unavailable",
            "maintenance_window": "Unavailable",
        }


def get_library_metadata(plex=None, sections=None, plex_url=None, plex_token=None):
    try:
        if plex is None:
            if not plex_url or not plex_token:
                plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")
            plex = PlexServer(plex_url, plex_token)

        library_data = {}
        if sections is None:
            sections = plex.library.sections()

        for section in sections:
            try:
                lib_info = {
                    "agent": section.agent,
                    "scanner": section.scanner,
                    "type": section.type,
                    "ratings_source": "N/A",
                }

                # Ratings source
                try:
                    settings = section.settings()
                    ratings_setting = next((s for s in settings if s.id == "ratingsSource"), None)
                    if ratings_setting:
                        lib_info["ratings_source"] = ratings_setting.enumValues.get(ratings_setting.value, "Unknown")
                except Exception:
                    pass  # Keep "N/A" if ratingsSource isn't available

                # Optimized content counts
                try:
                    if section.type == "movie":
                        lib_info["movie_count"] = section.totalSize
                    elif section.type == "show":
                        lib_info["show_count"] = section.totalSize
                        try:
                            lib_info["episode_count"] = section.totalViewSize(libtype="episode")
                        except Exception as e:
                            lib_info["episode_count"] = 0
                            lib_info["episode_error"] = str(e)
                    else:
                        lib_info["item_count"] = section.totalSize
                except Exception as e:
                    lib_info["error"] = str(e)

                library_data[section.title] = lib_info

            except Exception as lib_err:
                library_data[section.title] = {
                    "agent": "Unknown",
                    "scanner": "Unknown",
                    "type": "Unknown",
                    "ratings_source": f"Error: {lib_err}",
                }

        return library_data

    except Exception as e:
        return {"error": str(e)}


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


def get_kometa_remote_version(branch="nightly"):
    url = f"https://raw.githubusercontent.com/Kometa-Team/Kometa/{branch}/VERSION"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException:
        return None


def get_kometa_local_version(kometa_root=None):
    if kometa_root is None:
        kometa_root = Path(app.config.get("KOMETA_ROOT", "."))
    else:
        kometa_root = Path(kometa_root)

    version_path = kometa_root / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    return "unknown"


def get_kometa_local_sha(kometa_root=None):
    if kometa_root is None:
        kometa_root = Path(app.config.get("KOMETA_ROOT", "."))
    else:
        kometa_root = Path(kometa_root)

    return _read_text(kometa_root / ".kometa_sha")


def get_kometa_local_branch(kometa_root=None):
    if kometa_root is None:
        kometa_root = Path(app.config.get("KOMETA_ROOT", "."))
    else:
        kometa_root = Path(kometa_root)

    return normalize_kometa_branch_override(_read_text(kometa_root / ".kometa_branch"))


def get_kometa_remote_sha(branch="nightly"):
    return _get_upstream_sha(branch, [])


def get_imagemaid_root_path() -> Path:
    base = None
    if has_app_context():
        base = app.config.get("IMAGEMAID_ROOT")
    if not base and has_request_context():
        base = session.get("imagemaid_root")
    if not base:
        base = os.path.join(CONFIG_DIR, "imagemaid")
    return Path(os.path.normpath(base)).resolve()


def get_imagemaid_local_sha(imagemaid_root=None):
    if imagemaid_root is None:
        imagemaid_root = get_imagemaid_root_path()
    else:
        imagemaid_root = Path(imagemaid_root)
    return _read_text(imagemaid_root / ".imagemaid_sha")


def get_imagemaid_local_version(imagemaid_root=None):
    if imagemaid_root is None:
        imagemaid_root = get_imagemaid_root_path()
    else:
        imagemaid_root = Path(imagemaid_root)
    version_path = imagemaid_root / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    return "unknown"


def get_imagemaid_local_branch(imagemaid_root=None):
    if imagemaid_root is None:
        imagemaid_root = get_imagemaid_root_path()
    else:
        imagemaid_root = Path(imagemaid_root)
    return normalize_imagemaid_branch_override(_read_text(imagemaid_root / ".imagemaid_branch"))


def get_imagemaid_remote_sha(branch="develop"):
    return _get_upstream_sha(branch, [], api_url_template=IMAGEMAID_GITHUB_API_BRANCH, label="ImageMaid")


def get_imagemaid_remote_version(branch="develop"):
    url = f"{IMAGEMAID_GITHUB_BASE_URL}/{branch}/VERSION"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException:
        return None


def check_imagemaid_update(imagemaid_root=None, branch_override=None):
    branch = resolve_imagemaid_update_branch(branch_override)
    local_version = get_imagemaid_local_version(imagemaid_root)
    local_sha = get_imagemaid_local_sha(imagemaid_root)
    local_branch = get_imagemaid_local_branch(imagemaid_root)
    remote_version = get_imagemaid_remote_version(branch)
    remote_sha = get_imagemaid_remote_sha(branch)
    branch_mismatch = bool(local_branch and local_branch != branch)

    if local_sha and remote_sha:
        update_available = branch_mismatch or (local_sha != remote_sha)
        comparison_basis = "sha"
    else:
        update_available = branch_mismatch or bool(remote_version and remote_version != local_version)
        comparison_basis = "version"

    return {
        "local_version": local_version,
        "local_sha": local_sha,
        "local_branch": local_branch,
        "remote_version": remote_version,
        "remote_sha": remote_sha,
        "branch": branch,
        "branch_mismatch": branch_mismatch,
        "comparison_basis": comparison_basis,
        "update_available": update_available,
    }


def check_kometa_update(kometa_root=None, branch_override=None):
    branch = resolve_kometa_update_branch(branch_override)
    local_version = get_kometa_local_version(kometa_root)
    local_sha = get_kometa_local_sha(kometa_root)
    local_branch = get_kometa_local_branch(kometa_root)
    remote_version = get_kometa_remote_version(branch)
    remote_sha = get_kometa_remote_sha(branch)
    branch_mismatch = bool(local_branch and local_branch != branch)

    if local_sha and remote_sha:
        update_available = local_sha != remote_sha
        comparison_basis = "sha"
    else:
        update_available = bool(remote_version and remote_version != local_version)
        comparison_basis = "version"
        if branch_mismatch:
            update_available = True

    return {
        "local_version": local_version,
        "local_sha": local_sha,
        "local_branch": local_branch,
        "remote_version": remote_version,
        "remote_sha": remote_sha,
        "branch": branch,
        "branch_mismatch": branch_mismatch,
        "comparison_basis": comparison_basis,
        "update_available": update_available,
    }


def perform_kometa_update(kometa_root, branch="master"):
    """
    QS 'master'  -> Kometa 'master'
    QS != master -> Kometa 'nightly'
    Deterministic update: fetch -> switch -> reset -> pip upgrade -> requirements
    """
    logs, success = [], True
    try:
        kometa_root = Path(kometa_root).resolve()
        is_windows = sys.platform.startswith("win")
        kometa_branch = "master" if branch == "master" else "nightly"
        logs.append(f"⚙️ Quickstart branch '{branch}' → using Kometa branch '{kometa_branch}'.")

        if not (kometa_root / ".git").exists():
            logs.append("❌ Kometa path is not a Git repository (missing .git).")
            return {"success": False, "log": logs}

        # pick upstream remote if present
        remotes = subprocess.run(
            ["git", "remote"],
            cwd=kometa_root,
            capture_output=True,
            text=True,
            shell=is_windows,
        ).stdout.split()
        upstream = "kometa-team" if "kometa-team" in remotes else "origin"
        logs.append(f"🔗 Using remote: {upstream}")

        # 1) fetch
        logs.append(f"📥 git fetch {upstream} --prune")
        p = subprocess.run(
            ["git", "fetch", upstream, "--prune"],
            cwd=kometa_root,
            capture_output=True,
            text=True,
            shell=is_windows,
        )
        logs.append((p.stdout or "").strip() or "(no output)")
        if p.returncode != 0:
            logs.append((p.stderr or "").strip())
            success = False

        # 2) switch (fallback to checkout)
        if success:
            cmd = [
                "git",
                "switch",
                "-C",
                kometa_branch,
                "--track",
                f"{upstream}/{kometa_branch}",
            ]
            logs.append(f"🔀 {' '.join(cmd)}")
            p = subprocess.run(cmd, cwd=kometa_root, capture_output=True, text=True, shell=is_windows)
            if p.stdout:
                logs.append(p.stdout.strip())
            if p.returncode != 0:
                fallback = [
                    "git",
                    "checkout",
                    "-B",
                    kometa_branch,
                    f"{upstream}/{kometa_branch}",
                ]
                logs.append(f"🔁 fallback: {' '.join(fallback)}")
                p = subprocess.run(
                    fallback,
                    cwd=kometa_root,
                    capture_output=True,
                    text=True,
                    shell=is_windows,
                )
                logs.append((p.stdout or "").strip() or "(no output)")
                if p.returncode != 0:
                    logs.append((p.stderr or "").strip())
                    success = False

        # 3) reset
        if success:
            logs.append(f"↩️ git reset --hard {upstream}/{kometa_branch}")
            p = subprocess.run(
                ["git", "reset", "--hard", f"{upstream}/{kometa_branch}"],
                cwd=kometa_root,
                capture_output=True,
                text=True,
                shell=is_windows,
            )
            logs.append((p.stdout or "").strip() or "(no output)")
            if p.returncode != 0:
                logs.append((p.stderr or "").strip())
                success = False

        # 4) venv pip upgrade
        if success:
            venv_path = kometa_root / "kometa-venv"
            pip_bin = venv_path / ("Scripts" if is_windows else "bin") / ("pip.exe" if is_windows else "pip")
            logs.append("\n⬆️ Upgrading pip in Kometa venv...")
            p = subprocess.run(
                [str(pip_bin), "install", "--upgrade", "pip"],
                cwd=kometa_root,
                capture_output=True,
                text=True,
                shell=is_windows,
            )
            logs.append((p.stdout or "").strip() or "(no output)")
            if p.returncode != 0:
                logs.append((p.stderr or "").strip())
                success = False

        # 5) install requirements
        if success:
            logs.append("\n📦 Installing requirements...")
            p = subprocess.run(
                [
                    str(pip_bin),
                    "install",
                    "--no-cache-dir",
                    "--upgrade",
                    "-r",
                    "requirements.txt",
                ],
                cwd=kometa_root,
                capture_output=True,
                text=True,
                shell=is_windows,
            )
            logs.append((p.stdout or "").strip() or "(no output)")
            if p.returncode != 0:
                logs.append((p.stderr or "").strip())
                success = False

        logs.append("\n✅ Kometa update completed." if success else "\n❌ Kometa update failed.")
        return {"success": success, "log": logs}
    except Exception as e:
        logs.append(f"❌ Exception: {str(e)}")
        return {"success": False, "log": logs}


def get_app_root():
    # Go up one directory to reach the Quickstart root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rotate_logs():
    if not os.path.exists(LOG_FILE):
        return

    # Delete the oldest backup if it would exceed MAX_LOG_BACKUPS
    oldest = os.path.join(LOG_DIR, f"quickstart-{MAX_LOG_BACKUPS:03}.log")
    if os.path.exists(oldest):
        os.remove(oldest)

    # Rotate existing backups
    for i in range(MAX_LOG_BACKUPS - 1, 0, -1):
        src = os.path.join(LOG_DIR, f"quickstart-{i:03}.log")
        dst = os.path.join(LOG_DIR, f"quickstart-{i+1:03}.log")
        if os.path.exists(src):
            if os.path.exists(dst):
                os.remove(dst)
            os.rename(src, dst)

    # Rotate the current log to quickstart-001.log
    dst = os.path.join(LOG_DIR, "quickstart-001.log")
    if os.path.exists(dst):
        os.remove(dst)
    os.rename(LOG_FILE, dst)


def initialize_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    rotate_logs()
    with open(LOG_FILE, "w", encoding="utf-8"):
        pass
    ts_log(f"New log started at {datetime.datetime.now()}", level="INFO")


def redact_string(text):
    redacted = text
    sensitive_keys = [
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "apikey",
        "auth",
        "secret",
        "client_id",
        "client_secret",
        "plex_token",
        "password",
        "pin",
        "username",
    ]

    for key in sensitive_keys:
        key_escaped = re.escape(key)

        patterns = [
            # JSON-style quoted
            (rf'("{key_escaped}"\s*:\s*")[^"]*(")', r"\1(redacted)\2"),
            (rf"('{key_escaped}'\s*:\s*')[^']*(')", r"\1(redacted)\2"),
            # Dict-style key = value
            (rf"({key_escaped}\s*=\s*)[^\s,}}]+", r"\1(redacted)"),
            # YAML/Python-style key: value
            (rf"({key_escaped}\s*:\s*)[^\s,}}]+", r"\1(redacted)"),
            # JSON bare/null values
            (rf"({key_escaped}['\"]?\s*:\s*)(None|null)", r"\1(redacted)"),
        ]

        for pattern, repl in patterns:
            redacted = re.sub(pattern, repl, redacted, flags=re.IGNORECASE)

    return redacted


def ts_log(*args, level="INFO"):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    level_str = f"[{level}]"
    padding = " " * (10 - len(level_str))  # Pad to align

    # Grab session ID if in request context
    user_tag = ""
    if has_request_context() and "qs_session_id" in session:
        user_tag = f"[{session['qs_session_id']}] "

    message = " ".join(str(arg) for arg in args)

    # Console (NOT redacted)
    line_console = f"[{now}] {level_str}{padding}| {user_tag}{message}"
    print(line_console)

    # File (redacted)
    redacted_msg = redact_string(message)
    line_file = f"[{now}] {level_str}{padding}| {user_tag}{redacted_msg}"

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line_file + "\n")
    except Exception:
        pass


def handle_remove_readonly(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def get_kometa_pid_file():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    return os.path.join(CONFIG_DIR, "kometa.pid")


def get_kometa_pid():
    pid_file = get_kometa_pid_file()
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f:
                return int(f.read().strip())
        except Exception:
            return None
    return None


def is_kometa_running():
    pid = get_kometa_pid()
    if not pid:
        return False
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and "kometa.py" in " ".join(proc.cmdline())
    except psutil.NoSuchProcess:
        try:
            os.remove(get_kometa_pid_file())
        except Exception:
            pass
        return False


def perform_quickstart_update(qs_root, branch="master"):
    """
    Deterministic Quickstart update (mirrors Kometa updater):
        - Choose upstream remote: prefer 'kometa-team', else 'origin'
        - git fetch <upstream> --prune
        - git switch -C <branch> --track <upstream>/<branch>  (fallback to checkout)
        - git reset --hard <upstream>/<branch>
        - python -m pip install --upgrade pip
        - python -m pip install --no-cache-dir --upgrade -r requirements.txt
    Returns: {"success": bool, "log": [str, ...]}
    """
    logs, success = [], True
    try:
        qs_root = Path(qs_root).resolve()
        is_windows = sys.platform.startswith("win")

        # pick upstream remote (prefer official)
        remotes_out = subprocess.run(
            ["git", "remote"],
            cwd=qs_root,
            capture_output=True,
            text=True,
            shell=is_windows,
        )
        remotes = (remotes_out.stdout or "").split()
        upstream = "kometa-team" if "kometa-team" in remotes else "origin"
        logs.append(f"🔗 Using Quickstart remote: {upstream}")
        logs.append(f"⚙️ Target Quickstart branch: {branch}")

        def run(cmd, label=None):
            if label:
                logs.append(label)
            p = subprocess.run(cmd, cwd=qs_root, capture_output=True, text=True, shell=is_windows)
            out = (p.stdout or "").strip()
            err = (p.stderr or "").strip()
            if out:
                logs.append(out)
            if p.returncode != 0 and err:
                logs.append(err)
            return p

        # 1) fetch (ensure upstream/<branch> exists)
        p = run(["git", "fetch", upstream, "--prune"], f"📥 git fetch {upstream} --prune")
        success &= p.returncode == 0

        # 2) switch to branch (fallback to checkout)
        if success:
            p = run(
                ["git", "switch", "-C", branch, "--track", f"{upstream}/{branch}"],
                f"🔀 git switch -C {branch} --track {upstream}/{branch}",
            )
            if p.returncode != 0:
                p = run(
                    ["git", "checkout", "-B", branch, f"{upstream}/{branch}"],
                    f"🔁 fallback: git checkout -B {branch} {upstream}/{branch}",
                )
                success &= p.returncode == 0

        # 3) hard reset to upstream tip
        if success:
            p = run(
                ["git", "reset", "--hard", f"{upstream}/{branch}"],
                f"↩️ git reset --hard {upstream}/{branch}",
            )
            success &= p.returncode == 0

        # 4) upgrade pip for this interpreter (QS uses its own Python)
        if success:
            logs.append("\n⬆️ Upgrading pip...")
            p = subprocess.run(
                [str(Path(sys.executable)), "-m", "pip", "install", "--upgrade", "pip"],
                cwd=qs_root,
                capture_output=True,
                text=True,
                shell=is_windows,
            )
            logs.append((p.stdout or "").strip() or "(no output)")
            if p.returncode != 0:
                logs.append((p.stderr or "").strip())
                success = False

        # 5) install requirements
        if success:
            logs.append("\n📦 Installing requirements...")
            p = subprocess.run(
                [
                    str(Path(sys.executable)),
                    "-m",
                    "pip",
                    "install",
                    "--no-cache-dir",
                    "--upgrade",
                    "-r",
                    "requirements.txt",
                ],
                cwd=qs_root,
                capture_output=True,
                text=True,
                shell=is_windows,
            )
            logs.append((p.stdout or "").strip() or "(no output)")
            if p.returncode != 0:
                logs.append((p.stderr or "").strip())
                success = False

        logs.append("\n✅ Update completed." if success else "\n❌ Update failed.")
        return {"success": success, "log": logs}

    except Exception as e:
        logs.append(f"❌ Exception: {e}")
        return {"success": False, "log": logs}


def _ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def _read_text(p: Path):
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def _write_text(p: Path, s: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _get_upstream_sha(branch: str, logs: list[str], api_url_template: str = GITHUB_API_BRANCH, label: str = "Kometa") -> str | None:
    try:
        url = api_url_template.format(branch=branch)
        if label == "Kometa":
            logs.append(f"🔎 Resolving upstream SHA from: {url}")
        else:
            logs.append(f"🔎 Resolving upstream {label} SHA from: {url}")
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            logs.append(f"❌ GitHub API {r.status_code} for {url}")
            return None
        sha = (r.json().get("commit") or {}).get("sha")
        if sha:
            logs.append(f"🔎 Upstream {branch} SHA: {sha[:12]}")
        else:
            logs.append("❌ Unable to parse upstream SHA.")
        return sha
    except Exception as e:
        logs.append(f"❌ Exception fetching SHA: {e}")
        return None


def _download_zip(branch: str, logs: list[str], zip_url_template: str = GITHUB_ZIP_URL, label: str = "Kometa") -> bytes | None:
    try:
        url = zip_url_template.format(branch=branch)
        if label == "Kometa":
            logs.append(f"📥 Downloading {branch}.zip from: {url}")
        else:
            logs.append(f"📥 Downloading {label} {branch}.zip from: {url}")
        r = requests.get(url, timeout=60)
        if r.status_code != 200:
            logs.append(f"❌ ZIP download failed ({r.status_code})")
            return None
        return r.content
    except Exception as e:
        logs.append(f"❌ Exception during ZIP download: {e}")
        return None


def _backup_kometa_runtime_assets(kometa_dir: Path, logs: list[str]) -> Path | None:
    config_dir = kometa_dir / "config"
    if not config_dir.exists():
        return None

    logs_dir = config_dir / "logs"
    cache_files = list(config_dir.glob("*.cache"))
    if not logs_dir.is_dir() and not cache_files:
        return None

    backup_root = Path(CONFIG_DIR) / "kometa-backup"
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    backup_dir = backup_root / f"kometa-config-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    try:
        if logs_dir.is_dir():
            shutil.copytree(logs_dir, backup_dir / "logs", dirs_exist_ok=True)
        if cache_files:
            cache_dir = backup_dir / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            for cache_file in cache_files:
                shutil.copy2(cache_file, cache_dir / cache_file.name)
        logs.append(f"?? Backed up Kometa logs/cache to {backup_dir}")
        return backup_dir
    except Exception as e:
        logs.append(f"? Failed to back up Kometa logs/cache: {e}")
        return None


def _restore_kometa_runtime_assets(kometa_dir: Path, backup_dir: Path, logs: list[str]) -> bool:
    if not backup_dir or not backup_dir.exists():
        return False

    restored = False
    try:
        config_dir = kometa_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        logs_backup = backup_dir / "logs"
        if logs_backup.is_dir():
            target_logs = config_dir / "logs"
            if target_logs.exists():
                shutil.rmtree(target_logs, ignore_errors=True)
            shutil.copytree(logs_backup, target_logs, dirs_exist_ok=True)
            restored = True

        cache_backup = backup_dir / "cache"
        if cache_backup.is_dir():
            for cache_file in cache_backup.glob("*.cache"):
                shutil.copy2(cache_file, config_dir / cache_file.name)
            restored = True

        if restored:
            logs.append(f"?? Restored Kometa logs/cache from {backup_dir}")
        return restored
    except Exception as e:
        logs.append(f"? Failed to restore Kometa logs/cache: {e}")
        return False


def _cleanup_kometa_backup(backup_dir: Path, logs: list[str]):
    try:
        shutil.rmtree(backup_dir, ignore_errors=True)
    except Exception as e:
        logs.append(f"? Failed to remove Kometa backup: {e}")


def _clear_directory_contents(dest_dir: Path, logs: list[str], label: str = "Kometa") -> bool:
    logs.append(f"🧹 Removing existing {label} contents from: {dest_dir}")
    removed_count = 0
    failed_paths = []

    for child in list(dest_dir.iterdir()):
        try:
            if child.is_file() or child.is_symlink():
                child.unlink()
            else:
                shutil.rmtree(child)
            removed_count += 1
        except Exception as e:
            failed_paths.append((child, e))
            logs.append(f"❌ Failed to remove existing path: {child} ({e})")

    leftovers = list(dest_dir.iterdir())
    if leftovers:
        for leftover in leftovers:
            if all(str(leftover) != str(path) for path, _err in failed_paths):
                logs.append(f"❌ Existing path still present after cleanup: {leftover}")
        logs.append(f"❌ Aborting extraction because the {label} directory is not empty after cleanup.")
        return False

    logs.append(f"🧹 Removed {removed_count} existing entr{'y' if removed_count == 1 else 'ies'}.")
    return True


def _extract_zip_bytes(zip_bytes: bytes, dest_dir: Path, logs: list[str], label: str = "Kometa") -> bool:
    try:
        _ensure_dir(dest_dir)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            root_name = zf.namelist()[0].split("/")[0]  # e.g., Kometa-nightly
            # Use a stable tmp under CONFIG_DIR to avoid /tmp RAM constraints
            tmp_base = Path(CONFIG_DIR) / "tmp"
            if tmp_base.is_dir():
                for entry in tmp_base.iterdir():
                    shutil.rmtree(entry, ignore_errors=True)
            tmp_base.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=tmp_base) as td:
                tmp_root = Path(td) / root_name
                zf.extractall(Path(td))
                if not _clear_directory_contents(dest_dir, logs, label=label):
                    return False
                # Copy over
                for item in tmp_root.iterdir():
                    target = dest_dir / item.name
                    if item.is_dir():
                        shutil.copytree(item, target, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, target)
        version_file = dest_dir / "VERSION"
        if version_file.exists():
            version_value = _read_text(version_file)
            if version_value:
                logs.append(f"📦 Extracted VERSION file: {version_value}")
        logs.append(f"📦 Extracted to: {dest_dir}")
        return True
    except Exception as e:
        logs.append(f"❌ Extraction failed: {e}")
        return False


def _ensure_venv(kometa_dir: Path, logs: list[str], venv_name: str = "kometa-venv") -> tuple[Path, Path] | None:
    """
    Create (if missing) and validate a venv at <kometa_dir>/kometa-venv.
    Returns (python_bin, pip_bin) or None on failure.
    """
    import shutil
    import time

    is_windows = os.name == "nt"
    venv_dir = kometa_dir / venv_name

    def _venv_ok() -> bool:
        # A valid venv should have pyvenv.cfg and a python binary
        cfg_ok = (venv_dir / "pyvenv.cfg").exists()
        bin_dir = venv_dir / ("Scripts" if is_windows else "bin")
        py = bin_dir / ("python.exe" if is_windows else "python3")
        if not py.exists():
            # allow 'python' as a fallback name on some platforms
            py = bin_dir / ("python.exe" if is_windows else "python")
        return cfg_ok and py.exists()

    # Build command to create venv
    cmd: list[str] | None = None
    if getattr(sys, "frozen", False):
        # Prefer a *real* system Python when running frozen
        if is_windows and shutil.which("py"):
            cmd = ["py", "-3", "-m", "venv", str(venv_dir)]
        else:
            for cand in ("python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"):
                if shutil.which(cand):
                    cmd = [cand, "-m", "venv", str(venv_dir)]
                    break
        if cmd is None:
            logs.append("❌ Could not find a system Python 3 (3.10+) to create a virtualenv. " "Please install Python and ensure it is on PATH.")
            return None
    else:
        # Non-frozen: current interpreter is fine
        cmd = [sys.executable, "-m", "venv", str(venv_dir)]

    # Create venv if needed
    if not venv_dir.exists() or not _venv_ok():
        if venv_dir.exists() and not _venv_ok():
            logs.append(f"⚠️ Existing {venv_name} looks invalid; recreating...")
            try:
                shutil.rmtree(venv_dir, ignore_errors=True)
            except Exception as e:
                logs.append(f"❌ Failed to remove invalid venv: {e}")
                return None

        logs.append(f"🐍 Creating virtual environment with: {' '.join(cmd)}")
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(kometa_dir),
            shell=False,
        )
        if p.stdout.strip():
            logs.append(p.stdout.strip())
        if p.returncode != 0:
            logs.append((p.stderr or "").strip() or "venv creation failed")
            return None

        # Some AV tools on Windows can delay file appearance; give it a moment
        for _ in range(10):
            if _venv_ok():
                break
            time.sleep(0.2)

    # Validate venv structure
    if not _venv_ok():
        cfg_present = (venv_dir / "pyvenv.cfg").exists()
        logs.append(f"❌ Invalid venv: pyvenv.cfg present? {cfg_present}; " f"bin/Scripts present? {(venv_dir / ('Scripts' if is_windows else 'bin')).exists()}")
        return None

    bin_dir = venv_dir / ("Scripts" if is_windows else "bin")
    python_bin = bin_dir / ("python.exe" if is_windows else "python3")
    if not python_bin.exists():
        alt = bin_dir / ("python.exe" if is_windows else "python")
        if alt.exists():
            python_bin = alt

    pip_bin = bin_dir / ("pip.exe" if is_windows else "pip")

    # Extra sanity: print interpreter identity
    try:
        p = subprocess.run(
            [str(python_bin), "-c", "import sys; print(sys.executable); import sysconfig; print(sysconfig.get_platform())"], capture_output=True, text=True, shell=False
        )
        diag = (p.stdout or "").strip().replace("\n", " | ")
        if diag:
            logs.append(f"🔎 venv python: {diag}")
    except Exception:
        pass

    # Final guard: ensure pyvenv.cfg really exists, else pip will emit “No pyvenv.cfg file”
    if not (venv_dir / "pyvenv.cfg").exists():
        logs.append("❌ No pyvenv.cfg file after venv creation; aborting.")
        return None

    return python_bin, pip_bin


def _pip_install(python_bin: Path, kometa_dir: Path, logs: list[str], requirements_file: str = "requirements.txt") -> bool:
    is_windows = os.name == "nt"

    logs.append("⬆️ Upgrading pip...")
    p = subprocess.run(
        [str(python_bin), "-m", "pip", "install", "--upgrade", "pip"],
        capture_output=True,
        text=True,
        cwd=str(kometa_dir),
        shell=is_windows,
    )
    if p.stdout.strip():
        logs.append(p.stdout.strip())
    if p.returncode != 0:
        logs.append((p.stderr or p.stdout or "").strip() or "pip upgrade failed")
        return False

    logs.append("📦 Installing requirements...")
    p = subprocess.run(
        [str(python_bin), "-m", "pip", "install", "--no-cache-dir", "--upgrade", "-r", requirements_file],
        capture_output=True,
        text=True,
        cwd=str(kometa_dir),
        shell=is_windows,
    )
    if p.stdout.strip():
        logs.append(p.stdout.strip())
    if p.returncode != 0:
        logs.append((p.stderr or p.stdout or "").strip() or "requirements install failed")
        return False

    return True


def perform_kometa_update_zip_only(config_root: str | Path, branch: str = "nightly", force: bool = False, logs=None):
    """
    Update Kometa by downloading/extracting the branch ZIP into:
        {config_root}/kometa
    Uses upstream commit SHA to skip when up-to-date unless force is True.
    Works identically for local, PyInstaller, and Docker installs.
    """
    logs = logs if logs is not None else []
    try:
        config_root = Path(config_root).resolve()
        kometa_dir = config_root / "kometa"
        sha_file = kometa_dir / ".kometa_sha"
        branch_file = kometa_dir / ".kometa_branch"

        logs.append(f"⚙️ ZIP updater → branch '{branch}'")
        _ensure_dir(kometa_dir)

        upstream_sha = _get_upstream_sha(branch, logs)
        if not upstream_sha:
            return {"success": False, "log": logs}

        local_sha = _read_text(sha_file)
        if local_sha == upstream_sha and not force:
            logs.append("✅ Up to date (SHA matches). Skipping download.")
            return {"success": True, "log": logs, "up_to_date": True, "skipped": True}
        if force:
            logs.append("Force update requested; proceeding without SHA match check.")

        zip_bytes = _download_zip(branch, logs)
        if not zip_bytes:
            return {"success": False, "log": logs}

        backup_dir = _backup_kometa_runtime_assets(kometa_dir, logs)

        if not _extract_zip_bytes(zip_bytes, kometa_dir, logs):
            if backup_dir:
                restored = _restore_kometa_runtime_assets(kometa_dir, backup_dir, logs)
                if restored:
                    _cleanup_kometa_backup(backup_dir, logs)
            return {"success": False, "log": logs}

        if backup_dir:
            restored = _restore_kometa_runtime_assets(kometa_dir, backup_dir, logs)
            if restored:
                _cleanup_kometa_backup(backup_dir, logs)

        res = _ensure_venv(kometa_dir, logs)
        if not res:
            return {"success": False, "log": logs}
        python_bin, _pip_bin_unused = res
        if not _pip_install(python_bin, kometa_dir, logs):
            return {"success": False, "log": logs}

        _write_text(sha_file, upstream_sha)
        _write_text(branch_file, branch)
        logs.append("✅ Kometa updated via ZIP.")
        return {"success": True, "log": logs}

    except Exception as e:
        logs.append(f"❌ Exception: {e}")
        return {"success": False, "log": logs}


def perform_kometa_update_zip_only_at_root(kometa_root: str | Path, branch: str = "nightly", force: bool = False, logs=None):
    """
    Update Kometa by downloading/extracting the branch ZIP into an explicit Kometa root.
    """
    logs = logs if logs is not None else []
    try:
        kometa_dir = Path(kometa_root).resolve()
        sha_file = kometa_dir / ".kometa_sha"
        branch_file = kometa_dir / ".kometa_branch"

        logs.append(f"⚙️ ZIP updater → branch '{branch}'")
        _ensure_dir(kometa_dir)

        upstream_sha = _get_upstream_sha(branch, logs)
        if not upstream_sha:
            return {"success": False, "log": logs}

        local_sha = _read_text(sha_file)
        if local_sha == upstream_sha and not force:
            logs.append("✅ Up to date (SHA matches). Skipping download.")
            return {"success": True, "log": logs, "up_to_date": True, "skipped": True}
        if force:
            logs.append("Force update requested; proceeding without SHA match check.")

        zip_bytes = _download_zip(branch, logs)
        if not zip_bytes:
            return {"success": False, "log": logs}

        backup_dir = _backup_kometa_runtime_assets(kometa_dir, logs)

        if not _extract_zip_bytes(zip_bytes, kometa_dir, logs):
            if backup_dir:
                restored = _restore_kometa_runtime_assets(kometa_dir, backup_dir, logs)
                if restored:
                    _cleanup_kometa_backup(backup_dir, logs)
            return {"success": False, "log": logs}

        if backup_dir:
            restored = _restore_kometa_runtime_assets(kometa_dir, backup_dir, logs)
            if restored:
                _cleanup_kometa_backup(backup_dir, logs)

        res = _ensure_venv(kometa_dir, logs, venv_name="kometa-venv")
        if not res:
            return {"success": False, "log": logs}
        python_bin, _pip_bin_unused = res
        if not _pip_install(python_bin, kometa_dir, logs):
            return {"success": False, "log": logs}

        _write_text(sha_file, upstream_sha)
        _write_text(branch_file, branch)
        logs.append("✅ Kometa updated via ZIP.")
        return {"success": True, "log": logs}

    except Exception as e:
        logs.append(f"❌ Exception: {e}")
        return {"success": False, "log": logs}


def perform_imagemaid_update_zip_only(config_root: str | Path, branch: str = "develop", force: bool = False, logs=None):
    """
    Update ImageMaid by downloading/extracting the branch ZIP into:
        {config_root}/imagemaid
    Uses upstream commit SHA to skip when up-to-date unless force is True.
    """
    logs = logs if logs is not None else []
    try:
        config_root = Path(config_root).resolve()
        imagemaid_dir = config_root / "imagemaid"
        sha_file = imagemaid_dir / ".imagemaid_sha"
        branch_file = imagemaid_dir / ".imagemaid_branch"

        logs.append(f"⚙️ ZIP updater → ImageMaid branch '{branch}'")
        _ensure_dir(imagemaid_dir)

        upstream_sha = _get_upstream_sha(branch, logs, api_url_template=IMAGEMAID_GITHUB_API_BRANCH, label="ImageMaid")
        if not upstream_sha:
            return {"success": False, "log": logs}

        local_sha = _read_text(sha_file)
        if local_sha == upstream_sha and not force:
            logs.append("✅ ImageMaid is up to date (SHA matches). Skipping download.")
            return {"success": True, "log": logs, "up_to_date": True, "skipped": True}
        if force:
            logs.append("Force update requested; proceeding without SHA match check.")

        zip_bytes = _download_zip(branch, logs, zip_url_template=IMAGEMAID_GITHUB_ZIP_URL, label="ImageMaid")
        if not zip_bytes:
            return {"success": False, "log": logs}

        if not _extract_zip_bytes(zip_bytes, imagemaid_dir, logs, label="ImageMaid"):
            return {"success": False, "log": logs}

        res = _ensure_venv(imagemaid_dir, logs, venv_name="imagemaid-venv")
        if not res:
            return {"success": False, "log": logs}
        python_bin, _pip_bin_unused = res
        if not _pip_install(python_bin, imagemaid_dir, logs):
            return {"success": False, "log": logs}

        _write_text(sha_file, upstream_sha)
        _write_text(branch_file, branch)
        logs.append("✅ ImageMaid updated via ZIP.")
        return {"success": True, "log": logs}

    except Exception as e:
        logs.append(f"❌ Exception: {e}")
        return {"success": False, "log": logs}


def get_kometa_root_path() -> Path:
    """
    Resolve the Kometa root folder consistently.
    Priority:
        1) app.config["KOMETA_ROOT"] if it differs from the managed default
        2) session["kometa_root"] if it differs from the managed default
        3) persisted existing-install override for the active config
        4) managed default under <CONFIG_DIR>/kometa
    """
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


def get_imagemaid_pid_file():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    return os.path.join(CONFIG_DIR, "imagemaid.pid")


def get_imagemaid_launch_log_file():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    return os.path.join(CONFIG_DIR, "imagemaid-launch.log")


def get_imagemaid_pid():
    pid_file = get_imagemaid_pid_file()
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except Exception:
            return None
    return None


def is_imagemaid_running():
    pid = get_imagemaid_pid()
    if not pid:
        return False
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and "imagemaid.py" in " ".join(proc.cmdline())
    except psutil.NoSuchProcess:
        try:
            os.remove(get_imagemaid_pid_file())
        except Exception:
            pass
        return False
