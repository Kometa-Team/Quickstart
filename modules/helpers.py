import datetime
import hashlib
import io
import platform
import json
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

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
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
_PLEX_DISCOVERY_CACHE = {}
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


def detect_git_branch(repo_root=None, default="develop"):
    root = Path(repo_root or get_app_root()).resolve()

    if Repo is not None:
        try:
            repo = Repo(root, search_parent_directories=True)
            branch_name = str(repo.active_branch.name or "").strip()
            if branch_name:
                return branch_name
        except Exception:
            pass

    git_bin = shutil.which("git")
    if git_bin:
        try:
            result = subprocess.run(
                [git_bin, "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(root),
                capture_output=True,
                text=True,
                shell=False,
            )
            branch_name = (result.stdout or "").strip()
            if result.returncode == 0 and branch_name:
                return branch_name
        except Exception:
            pass

    return default


def _plex_discovery_cache_key(kind, plex_url, plex_token):
    normalized_url = str(plex_url or "").strip().rstrip("/").lower()
    token_digest = hashlib.sha256(str(plex_token or "").encode("utf-8")).hexdigest()
    return kind, normalized_url, token_digest


def _get_plex_discovery_cache(kind, plex_url, plex_token):
    key = _plex_discovery_cache_key(kind, plex_url, plex_token)
    entry = _PLEX_DISCOVERY_CACHE.get(key)
    if not entry:
        return None
    age = time.monotonic() - entry.get("created_at", 0)
    if age > PLEX_DISCOVERY_CACHE_TTL_SECONDS:
        _PLEX_DISCOVERY_CACHE.pop(key, None)
        return None
    return copy.deepcopy(entry.get("payload"))


def _set_plex_discovery_cache(kind, plex_url, plex_token, payload):
    if not plex_url or not plex_token or not isinstance(payload, dict):
        return
    key = _plex_discovery_cache_key(kind, plex_url, plex_token)
    _PLEX_DISCOVERY_CACHE[key] = {
        "created_at": time.monotonic(),
        "payload": copy.deepcopy(payload),
    }


def get_cached_plex_validation(plex_url, plex_token):
    return _get_plex_discovery_cache("validation", plex_url, plex_token)


def set_cached_plex_validation(plex_url, plex_token, payload):
    _set_plex_discovery_cache("validation", plex_url, plex_token, payload)


def get_cached_plex_metadata(plex_url, plex_token):
    return _get_plex_discovery_cache("metadata", plex_url, plex_token)


def set_cached_plex_metadata(plex_url, plex_token, payload):
    _set_plex_discovery_cache("metadata", plex_url, plex_token, payload)


def get_cached_plex_refresh(plex_url, plex_token):
    return _get_plex_discovery_cache("refresh", plex_url, plex_token)


def set_cached_plex_refresh(plex_url, plex_token, payload):
    _set_plex_discovery_cache("refresh", plex_url, plex_token, payload)


def clear_plex_discovery_cache():
    _PLEX_DISCOVERY_CACHE.clear()


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


def normalize_id(name, existing_ids):
    """Convert library names to safe and unique HTML IDs while preserving Unicode."""

    # Step 1: Remove unwanted characters (only keep letters, numbers, - and _)
    safe_id = re.sub(r"[^\w\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7A3-]", "", name)

    # Step 2: Replace spaces with dashes
    safe_id = safe_id.replace(" ", "-").lower()

    # Step 3: Ensure ID is unique by appending a counter if needed
    base_id = safe_id
    counter = 1
    while safe_id in existing_ids:
        safe_id = f"{base_id}-{counter}"
        counter += 1

    existing_ids.add(safe_id)  # Store it to prevent future duplicates
    return safe_id


def is_valid_aspect_ratio(image, target_ratio="2:3", tolerance=0.01):
    """Check if the image has an acceptable aspect ratio within a given tolerance."""
    width, height = image.size
    actual_ratio = width / height

    # Map aspect ratio strings to numeric values
    ratio_map = {
        "2:3": 2 / 3,
        "1:1.5": 2 / 3,  # alias
        "16:9": 16 / 9,
    }

    if target_ratio not in ratio_map:
        raise ValueError(f"Unsupported target_ratio: {target_ratio}")

    expected_ratio = ratio_map[target_ratio]
    return abs(actual_ratio - expected_ratio) < tolerance


def extract_library_name(key):
    """Extracts the actual library name from the key format."""
    if not isinstance(key, str):
        return None
    # Capture only the library-id segment between `-library_` and the next
    # known section marker. This avoids greedy matches when template variable
    # keys themselves contain hyphens (e.g. `use_South-Eastern Asia`).
    match = re.match(
        r"^(?:mov|sho)-library_(.+?)-(?:library$|collection_|template_|attribute_|overlay_|top_level_|metadata_files$)",
        key,
    )
    return match.group(1) if match else None


def get_pyfiglet_fonts():
    """Retrieve available PyFiglet fonts from static/fonts, sorted with custom order."""
    if getattr(sys, "frozen", False):  # running in frozen/packaged mode
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")

    fonts_dir = os.path.join(base_path, "static", "fonts")

    # Ensure predefined fonts are at the top
    predefined_fonts = ["none", "single line", "standard"]
    fonts = set(predefined_fonts)  # Using set to prevent duplicates

    # Append all .flf files, removing extension
    if os.path.exists(fonts_dir):
        fonts.update(f.replace(".flf", "") for f in os.listdir(fonts_dir) if f.endswith(".flf"))

    # Sort remaining fonts (excluding predefined ones)
    sorted_fonts = sorted(fonts - set(predefined_fonts))

    # Combine predefined fonts with sorted remaining fonts
    return predefined_fonts + sorted_fonts


def calculate_hash(content):
    """Compute the SHA256 hash of the given content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _schema_files_present():
    return all(os.path.exists(os.path.join(JSON_SCHEMA_DIR, filename)) for filename, _remote_path in JSON_SCHEMA_SYNC_FILES)


def load_previous_hashes():
    """Load the last known hashes of schema files."""
    if not os.path.exists(HASH_FILE):
        return {}

    hashes = {}
    with open(HASH_FILE, "r", encoding="utf-8") as f:
        for line in f:
            filename, file_hash = line.strip().split(":", 1)
            hashes[filename] = file_hash
    return hashes


def save_hashes(hashes):
    """Save updated hashes to the hash file."""
    with open(HASH_FILE, "w", encoding="utf-8") as f:
        for filename, file_hash in hashes.items():
            f.write(f"{filename}:{file_hash}\n")


def ensure_json_schema():
    """Ensure json-schema files exist and are up-to-date based on hash checks."""
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


def get_remote_version(branch):
    """Fetch the latest VERSION file from the correct GitHub branch."""
    try:
        response = requests.get(
            f"https://raw.githubusercontent.com/Kometa-Team/Quickstart/{branch}/VERSION",
            timeout=5,
        )
        response.raise_for_status()
        version = response.text.strip()
    except requests.RequestException:
        return None  # If request fails, return None
    try:
        response = requests.get(
            f"https://raw.githubusercontent.com/Kometa-Team/Quickstart/{branch}/BUILDNUM",
            timeout=5,
        )
        response.raise_for_status()
        build_num = response.text.strip()
    except requests.RequestException:
        build_num = "0"
    return version if branch == "master" else f"{version}-build{build_num}"


def get_branch():
    """Determine the current branch with Docker support."""
    # If running in Docker, use the environment variable
    if os.getenv("QUICKSTART_DOCKER", "False").lower() in ["true", "1"]:
        return os.getenv("BRANCH_NAME", "master")  # Use environment variable

    # Otherwise, try GitPython (if available)
    if Repo:
        try:
            return Repo(path=".").head.ref.name  # noqa
        except Exception:  # noqa
            pass  # Ignore errors if GitPython fails

    # Fallback: Use BRANCH_NAME from the environment (for non-Docker cases)
    return os.getenv("BRANCH_NAME", "master")


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


def get_running_os():
    # Preserve build for backward compatibility, even if unused
    build = os.getenv("BUILD_OS", "local").lower()  # noqa: F841

    # 1. Docker check via env
    if os.getenv("QUICKSTART_DOCKER", "False").lower() in ["true", "1"]:
        return "Docker", ""

    # 2. Frozen build (e.g., PyInstaller)
    if getattr(sys, "frozen", False):
        system = platform.system()
        if system == "Windows":
            return "Frozen-Windows", ".exe"
        elif system == "Darwin":
            return "Frozen-macOS", ""
        elif system == "Linux":
            return "Frozen-Linux", ""
        else:
            return "Frozen-Unknown", ""

    # 3. Local run
    system = platform.system()
    if system == "Windows":
        return "Local-Windows", ".exe"
    elif system == "Darwin":
        return "Local-macOS", ""
    elif system == "Linux":
        return "Local-Linux", ""
    else:
        return "Local-Unknown", ""


def enforce_string_fields(data, enforce=False):
    """
    Ensure specified fields in a dictionary are of type string.
    """
    if isinstance(data, dict):
        for k, v in data.items():
            data[k] = enforce_string_fields(v, enforce=k in STRING_FIELDS)
    elif isinstance(data, list):
        return [enforce_string_fields(v, enforce=enforce) for v in data]
    elif enforce:
        return str(data)
    return data


def build_oauth_dict(source, form_data):
    data = {source: {"authorization": {}}}
    for key in form_data:
        final_key = key.replace(source + "_", "", 1)
        value = form_data[key]

        if final_key in [
            "client_id",
            "client_secret",
            "pin",
            "force_refresh",
            "cache_expiration",
            "localhost_url",
        ]:
            data[source][final_key] = value  # Store outside authorization
        elif final_key in ["validated", "validated_at"]:
            data[final_key] = value
        else:
            if final_key != "url":
                data[source]["authorization"][final_key] = value  # Everything else goes into authorization

    return data


def build_simple_dict(source, form_data):
    data = {source: {}}
    for key in form_data:
        final_key = key.replace(source + "_", "", 1)  # Retain the original key transformation logic
        value = form_data[key]

        # Handle lists explicitly (e.g., asset_directory)
        if isinstance(value, list):
            data[source][final_key] = value
        elif isinstance(value, dict):
            # Keep valid nested dicts (like template_variables) untouched
            data[source][final_key] = value
        else:
            # Handle individual scalar values
            if value is not None and not isinstance(value, bool):
                if final_key.endswith("_section"):
                    # Preserve as string to avoid stripping leading zeros
                    value = value.strip() if isinstance(value, str) else value
                else:
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        value = value.strip() if isinstance(value, str) else value

            # Assign the value to the appropriate key
            if final_key in ["validated", "validated_at"]:
                data[final_key] = value
            else:
                data[source][final_key] = value

    # Handle run_order specially
    if "run_order" in data[source]:
        run_order = data[source]["run_order"]
        if run_order is not None and isinstance(run_order, str):
            run_order = [item.strip() for item in run_order.split() if item.strip()]
        else:
            run_order = ["operations", "metadata", "collections", "overlays"]
        data[source]["run_order"] = run_order

    return data


def build_config_dict(source, form_data):
    if source in ["trakt", "mal"]:
        return build_oauth_dict(source, form_data)
    else:
        return build_simple_dict(source, form_data)


def belongs_in_template_list(file):
    return (
        file.endswith(".html")
        and file not in ["000-base.html", "001-navigation.html"]
        and file != "027-playlist_files.html"
        and file[:3].isdigit()
        # and file[3] == "-"
        and not file.startswith("999-")
    )


def user_visible_name(raw_name):
    if raw_name == "tmdb":
        formatted_name = "TMDb"
    elif raw_name == "omdb":
        formatted_name = "OMDb"
    elif raw_name == "github":
        formatted_name = "GitHub"
    elif raw_name == "ntfy":
        formatted_name = "ntfy"
    elif raw_name == "mal":
        formatted_name = "MyAnimeList"
    elif raw_name == "mdblist":
        formatted_name = "MDBList"
    elif raw_name == "anidb":
        formatted_name = "AniDB"
    elif raw_name == "playlist_files":
        formatted_name = "Playlists"
    elif raw_name == "libraries":
        formatted_name = "Libraries"
    elif raw_name == "final":
        formatted_name = "Kometa"
    elif raw_name == "kometa":
        formatted_name = "Kometa"
    elif raw_name == "analytics":
        formatted_name = "Analytics"
    elif raw_name == "imagemaid":
        formatted_name = "ImageMaid"
    else:
        if "-" in raw_name:
            formatted_name = raw_name.replace("-", " ").title()
        else:
            # Capitalize the first letter
            formatted_name = raw_name.capitalize()

    return formatted_name


def booler(thing):
    if isinstance(thing, str):
        thing = thing.lower().strip()
        if thing in ("true", "yes", "1"):
            return True
        elif thing in ("false", "no", "0"):
            return False
        else:
            if app.config["QS_DEBUG"]:
                ts_log(
                    f"Warning: Invalid boolean string encountered: {thing}. Defaulting to False.",
                    level="DEBUG",
                )
            return False
    return bool(thing)


def get_quickstart_settings_summary():
    def get_value(key, default=""):
        value = app.config.get(key)
        if value is None or value == "":
            value = os.getenv(key, default)
        return value

    def format_bool(value):
        return "Enabled" if booler(value) else "Disabled"

    def format_keep(value):
        if value is None or str(value).strip() == "":
            return "Keep all (0)"
        try:
            num = int(str(value).strip())
        except (TypeError, ValueError):
            return str(value)
        return "Keep all (0)" if num == 0 else str(num)

    handled = {
        "QS_PORT",
        "QS_DEBUG",
        "QS_THEME",
        "QS_OPTIMIZE_DEFAULTS",
        "QS_CONFIG_HISTORY",
        "QS_KOMETA_LOG_KEEP",
        "QS_IMAGEMAID_LOG_KEEP",
        "QS_TEST_LIBS_TMP",
        "QS_TEST_LIBS_PATH",
    }
    skip = {"QS_FLASK_SESSION_DIR", "QS_CONFIG_CLEANUP_DONE", "QS_SKIP_AUTO_OPEN"}

    summary = [
        ("QS_PORT", "Quickstart Port", lambda v: v or "Unknown"),
        ("QS_DEBUG", "Quickstart Debug", format_bool),
        ("QS_THEME", "Quickstart Theme", lambda v: v or "kometa"),
        ("QS_OPTIMIZE_DEFAULTS", "Quickstart Optimize Template Defaults", format_bool),
        ("QS_CONFIG_HISTORY", "Quickstart Config Archive History", format_keep),
        ("QS_KOMETA_LOG_KEEP", "Quickstart Kometa Log Retention", format_keep),
        ("QS_IMAGEMAID_LOG_KEEP", "Quickstart ImageMaid Log Retention", format_keep),
        ("QS_TEST_LIBS_TMP", "Quickstart Test Libraries Temp Path", lambda v: v or "Default"),
        ("QS_TEST_LIBS_PATH", "Quickstart Test Libraries Install Path", lambda v: v or "Default"),
    ]

    lines = []
    for key, label, formatter in summary:
        value = get_value(key, "")
        lines.append(f"# {label}: {formatter(value)}")

    kometa_mode = get_kometa_install_mode()
    lines.append(f"# Kometa Runtime Mode: {get_kometa_install_mode_label(kometa_mode)}")

    extra_keys = sorted(key for key in app.config.keys() if key.startswith("QS_") and key not in handled and key not in skip)
    for key in extra_keys:
        value = get_value(key, "")
        if value is None or value == "":
            continue
        if isinstance(value, bool) or str(value).strip().lower() in {"true", "false", "yes", "no", "1", "0"}:
            display = format_bool(value)
        else:
            display = str(value)
        label = "Quickstart " + key.replace("QS_", "").replace("_", " ").title()
        lines.append(f"# {label}: {display}")

    return lines


def get_bits(file):
    file_stem = Path(file).stem
    bits = file_stem.split("-")
    num = bits[0] if bits else file_stem
    raw_name = "-".join(bits[1:]) if len(bits) > 1 else file_stem

    return file_stem, num, raw_name


def get_next(file_list, current_file):
    current_index = file_list.index(current_file)
    if current_index + 1 < len(file_list):
        return file_list[current_index + 1].rsplit(".", 1)[0]
    return None


def template_record(file, prev_record, next_record):
    file_stem, num, raw_name = get_bits(file)
    return {
        "num": num,
        "file": file,
        "stem": file_stem,
        "name": user_visible_name(raw_name),
        "raw_name": raw_name,
        "next": next_record,
        "prev": prev_record,
    }


def get_menu_list():
    templates_dir = os.path.join(app.root_path, "templates")
    file_list = sorted(item for item in os.listdir(templates_dir) if os.path.isfile(os.path.join(templates_dir, item)))
    final_list = []

    for file in file_list:
        if belongs_in_template_list(file):
            file_stem, num, raw_name = get_bits(file)
            final_list.append((file, user_visible_name(raw_name)))

    return final_list


def get_template_list():
    templates_dir = os.path.join(app.root_path, "templates")
    file_list = sorted(item for item in os.listdir(templates_dir) if os.path.isfile(os.path.join(templates_dir, item)))

    templates = {}
    type_counter = {"012": 0, "013": 0}  # Counters for movie, show types
    prev_record = "001-start"
    included_files = []

    for file in file_list:
        if not belongs_in_template_list(file):
            continue
        included_files.append(file)

    for idx, file in enumerate(included_files):
        match = re.match(r"^(\d+)-", file)  # Match any length of digits followed by '-'
        if match:
            file_prefix = match.group(1)
        else:
            continue  # Skip files that do not match the pattern

        if file_prefix in type_counter:
            type_counter[file_prefix] += 1
            num = f"{file_prefix}{type_counter[file_prefix]:02d}"
        else:
            num = file_prefix

        next_record = None
        if idx + 1 < len(included_files):
            next_record = included_files[idx + 1].rsplit(".", 1)[0]
        rec = template_record(file, prev_record, next_record)
        rec["num"] = num  # Update the num to include the counter
        templates[num] = rec
        prev_record = rec["stem"]

    return templates


def redact_sensitive_data(yaml_content):
    import re

    # Split the YAML content into lines for line-by-line processing
    lines = yaml_content.splitlines()

    # Process each line to redact sensitive data
    redacted_lines = [
        re.sub(
            r"(token|client.*|url|api_*key|secret|error|delete|run_start|run_end|version|changes|username|password): .+",
            r"\1: (redacted)",
            line.strip("\r\n"),
        )
        for line in lines
    ]

    # Join the lines back together to form the redacted YAML content
    redacted_content = "\n".join(redacted_lines)
    return redacted_content


def update_env_variable(key, value):
    env_path = os.path.join(CONFIG_DIR, ".env")

    env_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as file:
            env_lines = file.readlines()

    with open(env_path, "w") as file:
        key_found = False
        for line in env_lines:
            if line.startswith(f"{key}="):
                file.write(f"{key}={value}\n")
                key_found = True
            else:
                file.write(line)
        if not key_found:
            file.write(f"{key}={value}\n")


def set_restart_notice(reason, message=None):
    if not isinstance(reason, str) or not reason.strip():
        return False
    payload = {
        "reason": reason.strip(),
        "message": message.strip() if isinstance(message, str) and message.strip() else None,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
    }
    try:
        with open(RESTART_NOTICE_FILE, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return True
    except Exception as exc:
        ts_log(f"Failed to write restart notice: {exc}", level="WARNING")
        return False


def consume_restart_notice():
    if not os.path.exists(RESTART_NOTICE_FILE):
        return None
    try:
        with open(RESTART_NOTICE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        ts_log(f"Failed to read restart notice: {exc}", level="WARNING")
        payload = None
    try:
        os.remove(RESTART_NOTICE_FILE)
    except Exception as exc:
        ts_log(f"Failed to remove restart notice: {exc}", level="WARNING")
    return payload


def load_quickstart_config(filename: str):
    json_path = os.path.join(JSON_SETTINGS, filename)
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _overlay_origin_alignment_defaults(origin):
    origin_str = str(origin or "").strip().lower()
    tokens = [token for token in re.split(r"[^a-z]+", origin_str) if token]
    has_center = "center" in tokens

    horizontal = "right" if "right" in tokens else "left"
    if "left" not in tokens and has_center and "right" not in tokens:
        horizontal = "center"

    vertical = "bottom" if "bottom" in tokens else "top"
    if "top" not in tokens and has_center and "bottom" not in tokens:
        vertical = "center"

    return horizontal, vertical


def _overlay_template_var_keys(template_variables):
    keys = set()
    if isinstance(template_variables, dict):
        keys.update(str(key) for key in template_variables.keys())
    elif isinstance(template_variables, list):
        for item in template_variables:
            if isinstance(item, dict) and item.get("key"):
                keys.add(str(item.get("key")))
    return keys


def _insert_overlay_mapping_fields(template_variables, inserted_fields, *, before_keys=None):
    if not isinstance(template_variables, dict) or not inserted_fields:
        return template_variables

    before_keys = set(before_keys or ())
    next_template_variables = {}
    inserted = False

    for key, value in template_variables.items():
        if not inserted and key in before_keys:
            for inserted_key, inserted_value in inserted_fields.items():
                if inserted_key not in template_variables:
                    next_template_variables[inserted_key] = inserted_value
            inserted = True
        next_template_variables[key] = value

    if not inserted:
        for inserted_key, inserted_value in inserted_fields.items():
            if inserted_key not in next_template_variables:
                next_template_variables[inserted_key] = inserted_value

    template_variables.clear()
    template_variables.update(next_template_variables)
    return template_variables


def _insert_overlay_list_fields(template_variables, inserted_fields, *, before_keys=None):
    if not isinstance(template_variables, list) or not inserted_fields:
        return template_variables

    before_keys = set(before_keys or ())
    existing_keys = _overlay_template_var_keys(template_variables)
    next_template_variables = []
    inserted = False

    for item in template_variables:
        item_key = item.get("key") if isinstance(item, dict) else None
        if not inserted and item_key in before_keys:
            for inserted_field in inserted_fields:
                inserted_key = inserted_field.get("key")
                if inserted_key and inserted_key not in existing_keys:
                    next_template_variables.append(copy.deepcopy(inserted_field))
            inserted = True
        next_template_variables.append(item)

    if not inserted:
        for inserted_field in inserted_fields:
            inserted_key = inserted_field.get("key")
            if inserted_key and inserted_key not in existing_keys:
                next_template_variables.append(copy.deepcopy(inserted_field))

    template_variables[:] = next_template_variables
    return template_variables


def enrich_quickstart_overlay_config(config):
    enriched = copy.deepcopy(config or [])

    for group in enriched:
        if not isinstance(group, dict):
            continue
        overlays = group.get("overlays", [])
        if not isinstance(overlays, list):
            continue
        for overlay in overlays:
            if not isinstance(overlay, dict):
                continue
            template_variables = overlay.get("template_variables")
            if template_variables is None:
                template_variables = {}
                overlay["template_variables"] = template_variables
            if not isinstance(template_variables, (dict, list)):
                continue

            existing_keys = _overlay_template_var_keys(template_variables)
            default_offsets = overlay.get("default_offsets")
            offsets_by_type = overlay.get("default_offsets_by_type")

            supports_runtime_offsets = (
                isinstance(default_offsets, dict)
                or (isinstance(offsets_by_type, dict) and any(isinstance(value, dict) for value in offsets_by_type.values()))
                or "initial_horizontal_offset" in existing_keys
                or "initial_vertical_offset" in existing_keys
            )

            offset_defaults = default_offsets if isinstance(default_offsets, dict) else {}
            if not offset_defaults and isinstance(offsets_by_type, dict):
                for candidate in offsets_by_type.values():
                    if isinstance(candidate, dict):
                        offset_defaults = candidate
                        break

            if supports_runtime_offsets:
                horizontal_default = 0
                vertical_default = 0
                if "initial_horizontal_offset" in existing_keys:
                    if isinstance(template_variables, dict):
                        horizontal_default = template_variables.get("initial_horizontal_offset", {}).get(
                            "default",
                            offset_defaults.get("horizontal", 0),
                        )
                    else:
                        for item in template_variables:
                            if isinstance(item, dict) and item.get("key") == "initial_horizontal_offset":
                                horizontal_default = item.get("default", offset_defaults.get("horizontal", 0))
                                break
                else:
                    horizontal_default = offset_defaults.get("horizontal", 0)

                if "initial_vertical_offset" in existing_keys:
                    if isinstance(template_variables, dict):
                        vertical_default = template_variables.get("initial_vertical_offset", {}).get(
                            "default",
                            offset_defaults.get("vertical", 0),
                        )
                    else:
                        for item in template_variables:
                            if isinstance(item, dict) and item.get("key") == "initial_vertical_offset":
                                vertical_default = item.get("default", offset_defaults.get("vertical", 0))
                                break
                else:
                    vertical_default = offset_defaults.get("vertical", 0)

                offset_fields_mapping = {
                    "horizontal_offset": {
                        "input_type": "number",
                        "default": horizontal_default,
                        "label": "Horizontal Offset",
                    },
                    "vertical_offset": {
                        "input_type": "number",
                        "default": vertical_default,
                        "label": "Vertical Offset",
                    },
                }
                offset_fields_list = [
                    {
                        "input_type": "number",
                        "key": "horizontal_offset",
                        "default": horizontal_default,
                        "label": "Horizontal Offset",
                    },
                    {
                        "input_type": "number",
                        "key": "vertical_offset",
                        "default": vertical_default,
                        "label": "Vertical Offset",
                    },
                ]

                if isinstance(template_variables, dict):
                    _insert_overlay_mapping_fields(
                        template_variables,
                        offset_fields_mapping,
                        before_keys={"horizontal_offset", "vertical_offset", "builder_level"},
                    )
                else:
                    _insert_overlay_list_fields(
                        template_variables,
                        offset_fields_list,
                        before_keys={"horizontal_offset", "vertical_offset", "builder_level"},
                    )

            supports_origin_alignment = (
                isinstance(offset_defaults, dict)
                and bool(offset_defaults.get("origin"))
                and "horizontal_position" not in existing_keys
                and "vertical_position" not in existing_keys
            )

            if supports_origin_alignment:
                horizontal_align_default, vertical_align_default = _overlay_origin_alignment_defaults(offset_defaults.get("origin"))
                align_fields_mapping = {
                    "horizontal_align": {
                        "input_type": "select",
                        "default": horizontal_align_default,
                        "label": "Horizontal Alignment",
                        "options": ["left", "center", "right"],
                    },
                    "vertical_align": {
                        "input_type": "select",
                        "default": vertical_align_default,
                        "label": "Vertical Alignment",
                        "options": ["top", "center", "bottom"],
                    },
                }
                align_fields_list = [
                    {
                        "input_type": "select",
                        "key": "horizontal_align",
                        "default": horizontal_align_default,
                        "label": "Horizontal Alignment",
                        "options": ["left", "center", "right"],
                    },
                    {
                        "input_type": "select",
                        "key": "vertical_align",
                        "default": vertical_align_default,
                        "label": "Vertical Alignment",
                        "options": ["top", "center", "bottom"],
                    },
                ]

                if isinstance(template_variables, dict):
                    _insert_overlay_mapping_fields(
                        template_variables,
                        align_fields_mapping,
                        before_keys={"horizontal_offset", "vertical_offset", "builder_level"},
                    )
                else:
                    _insert_overlay_list_fields(
                        template_variables,
                        align_fields_list,
                        before_keys={"horizontal_offset", "vertical_offset", "builder_level"},
                    )

    return enriched


def load_quickstart_overlay_config():
    return enrich_quickstart_overlay_config(load_quickstart_config("quickstart_overlays.json"))


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


def allowed_extensions_string():
    return ", ".join(sorted(ALLOWED_EXTENSIONS))


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

        cached = get_cached_plex_metadata(plex_url, plex_token)
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
        set_cached_plex_metadata(plex_url, plex_token, metadata)
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


def contains_non_latin(text):
    return bool(re.search(r"[^\x00-\x7F]", text))


def _read_text_if_exists(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _directory_tree_signature(root: Path) -> list[tuple[str, int, int]]:
    if not root.exists() or not root.is_dir():
        return []

    entries: list[tuple[str, int, int]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            entries.append((f"{relative}/", 0, 0))
            continue
        try:
            stats = path.stat()
            entries.append((relative, int(stats.st_size), int(stats.st_mtime_ns)))
        except Exception:
            entries.append((relative, -1, -1))
    return entries


def save_to_named_config(yaml_text, config_name, font_refs=None):
    config_dir = Path(CONFIG_DIR)
    kometa_root = get_kometa_root_path()
    kometa_config_dir = get_kometa_config_dir()
    name = require_config_name_for_storage(config_name, context="Saving a named config")
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
        try:
            font_result = copy_fonts_to_kometa(font_refs, kometa_root=kometa_root, kometa_config_dir=kometa_config_dir, config_name=name)
            missing = font_result.get("missing", [])
            errors = font_result.get("errors", [])
            if missing:
                ts_log(f"Missing fonts not copied to Kometa: {', '.join(missing)}", level="WARNING")
            for err in errors:
                ts_log(err, level="WARNING")
        except Exception as exc:
            ts_log(f"Failed to sync fonts to Kometa: {exc}", level="WARNING")

    if kometa_write_ok:
        try:
            artifact_result = sync_managed_library_artifacts_to_kometa(name, kometa_root=kometa_root, kometa_config_dir=kometa_config_dir)
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


def get_legacy_custom_fonts_dir() -> Path:
    return Path(CONFIG_DIR) / "fonts"


def get_custom_fonts_dir(config_name: str | None = None) -> Path:
    if config_name:
        return get_managed_config_artifact_root(config_name) / "fonts"
    return get_legacy_custom_fonts_dir()


def get_kometa_fonts_dir(kometa_root: Path | None = None) -> Path:
    if kometa_root is not None:
        return Path(kometa_root) / "config" / "fonts"
    return get_kometa_config_dir() / "fonts"


def get_font_dirs(include_static: bool = True, include_custom: bool = True, config_name: str | None = None) -> list[Path]:
    dirs: list[Path] = []
    seen: set[str] = set()

    if include_custom:
        custom_paths = []
        if config_name:
            custom_paths.append(get_custom_fonts_dir(config_name))
        custom_paths.extend((get_legacy_custom_fonts_dir(), get_kometa_fonts_dir()))
        for path in custom_paths:
            key = str(path)
            if key not in seen:
                dirs.append(path)
                seen.add(key)

    if include_static:
        for base in (MEIPASS_DIR, BASE_DIR, WORKING_DIR):
            path = Path(base) / "static" / "fonts"
            key = str(path)
            if key not in seen:
                dirs.append(path)
                seen.add(key)

    return dirs


def list_custom_fonts(config_name: str | None = None) -> list[str]:
    fonts: set[str] = set()
    folders = [get_kometa_fonts_dir(), get_legacy_custom_fonts_dir()]
    if config_name:
        folders.insert(0, get_custom_fonts_dir(config_name))
    for folder in folders:
        if not folder.is_dir():
            continue
        for entry in folder.iterdir():
            if entry.is_file() and entry.suffix.lower() in FONT_EXTENSIONS:
                fonts.add(entry.name)
    return sorted(fonts)


def list_available_fonts(include_static: bool = True, include_custom: bool = True, config_name: str | None = None) -> list[str]:
    fonts: set[str] = set()
    for folder in get_font_dirs(include_static=include_static, include_custom=include_custom, config_name=config_name):
        if not folder.is_dir():
            continue
        for entry in folder.iterdir():
            if entry.is_file() and entry.suffix.lower() in FONT_EXTENSIONS:
                fonts.add(entry.name)
    return sorted(fonts)


def migrate_legacy_custom_fonts_to_config(config_name: str | None, font_names: list[str] | tuple[str, ...] | set[str] | None = None) -> dict:
    try:
        normalized = require_config_name_for_storage(config_name, context="Config-scoped font migration")
    except ValueError as exc:
        return {"copied": [], "skipped": [], "errors": [str(exc)]}

    source_dir = get_legacy_custom_fonts_dir()
    destination_dir = get_custom_fonts_dir(normalized)
    copied: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    if not source_dir.is_dir():
        return {"copied": copied, "skipped": skipped, "errors": errors}

    requested: set[str] | None = None
    if font_names is not None:
        requested = {str(name or "").strip() for name in font_names if str(name or "").strip()}
        if not requested:
            return {"copied": copied, "skipped": skipped, "errors": errors}

    destination_dir.mkdir(parents=True, exist_ok=True)

    for entry in sorted(source_dir.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_file() or entry.suffix.lower() not in FONT_EXTENSIONS:
            continue
        if requested is not None and entry.name not in requested:
            continue
        target = destination_dir / entry.name
        if target.exists():
            skipped.append(entry.name)
            continue
        try:
            shutil.copy2(entry, target)
            copied.append(entry.name)
        except Exception as exc:
            errors.append(f"Failed to migrate legacy font {entry} -> {target}: {exc}")

    return {"copied": copied, "skipped": skipped, "errors": errors}


def sync_custom_fonts(kometa_root: Path | None = None, config_name: str | None = None) -> list[str]:
    source_dir = get_custom_fonts_dir(config_name)
    if not source_dir.is_dir():
        return []
    dest_dir = get_kometa_fonts_dir(kometa_root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for entry in source_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() in FONT_EXTENSIONS:
            shutil.copy2(entry, dest_dir / entry.name)
            copied.append(entry.name)
    return copied


def collect_font_references(config_data) -> list[str]:
    fonts: set[str] = set()

    def normalize(value):
        if isinstance(value, dict):
            raw = value.get("value")
            if isinstance(raw, str):
                return raw.strip()
            return None
        if isinstance(value, str):
            return value.strip()
        return None

    def walk(obj):
        if isinstance(obj, dict):
            for key, val in obj.items():
                if isinstance(key, str) and (key == "font" or key.endswith("_font")):
                    norm = normalize(val)
                    if norm and norm.lower() != "none":
                        fonts.add(norm)
                walk(val)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(config_data)
    return sorted(fonts)


def copy_fonts_to_kometa(font_refs, kometa_root: Path | None = None, kometa_config_dir: Path | None = None, config_name: str | None = None) -> dict:
    dest_dir = Path(kometa_config_dir) / "fonts" if kometa_config_dir is not None else get_kometa_fonts_dir(kometa_root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    migration = migrate_legacy_custom_fonts_to_config(config_name, font_refs) if config_name else {"copied": [], "skipped": [], "errors": []}
    sources = get_font_dirs(include_static=True, include_custom=True, config_name=config_name)
    copied: list[str] = []
    missing: list[str] = []
    errors: list[str] = list(migration.get("errors", []))

    for ref in font_refs or []:
        ref_str = str(ref or "").strip()
        if not ref_str:
            continue
        base = os.path.basename(ref_str)
        if not base:
            continue

        source_path = None
        candidate = Path(ref_str)
        if candidate.exists():
            source_path = candidate
        else:
            for folder in sources:
                candidate = Path(folder) / base
                if candidate.exists():
                    source_path = candidate
                    break

        if source_path is None:
            missing.append(base)
            continue

        dest_path = dest_dir / base
        try:
            if dest_path.resolve() == source_path.resolve():
                continue
        except Exception:
            pass

        try:
            shutil.copy2(source_path, dest_path)
            copied.append(base)
        except Exception as exc:
            errors.append(f"Failed to copy {source_path} -> {dest_path}: {exc}")

    return {"copied": copied, "missing": missing, "errors": errors}


def migrate_config_archives(history_limit: int | None = None) -> dict:
    """Move legacy *_config*.yml into config/archives/<name>/ and optionally prune."""
    config_dir = Path(CONFIG_DIR)
    archive_root = config_dir / "archives"
    archive_pattern = re.compile(r"^(?P<name>.+)_config_(?P<suffix>\d+)\.yml$", re.IGNORECASE)
    current_pattern = re.compile(r"^(?P<name>.+)_config\.yml$", re.IGNORECASE)

    moved = 0
    errors: list[str] = []

    if history_limit is None:
        history_limit = 0
    try:
        history_limit = int(str(history_limit).strip())
    except (TypeError, ValueError):
        history_limit = 0
    if history_limit < 0:
        history_limit = 0

    def move_config(path: Path, name: str) -> None:
        nonlocal moved
        dest_dir = archive_root / name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / path.name
        counter = 1
        while dest_path.exists():
            dest_path = dest_dir / f"{path.stem}_moved{counter}{path.suffix}"
            counter += 1
        try:
            shutil.move(str(path), str(dest_path))
            moved += 1
        except Exception as exc:
            errors.append(f"Failed to move {path} -> {dest_path}: {exc}")

    for path in config_dir.glob("*_config_*.yml"):
        if not path.is_file():
            continue
        match = archive_pattern.match(path.name)
        if not match:
            continue
        move_config(path, match.group("name"))

    for path in config_dir.glob("*_config.yml"):
        if not path.is_file():
            continue
        match = current_pattern.match(path.name)
        if not match:
            continue
        move_config(path, match.group("name"))

    if history_limit > 0 and archive_root.exists():
        for dest_dir in archive_root.iterdir():
            if not dest_dir.is_dir():
                continue
            archives = sorted(dest_dir.glob("*.yml"), key=lambda p: p.stat().st_mtime)
            if len(archives) > history_limit:
                for old_path in archives[: len(archives) - history_limit]:
                    try:
                        old_path.unlink()
                    except Exception as exc:
                        errors.append(f"Failed to prune {old_path}: {exc}")

    return {"moved": moved, "errors": errors, "history_limit": history_limit}


def normalize_config_name_for_storage(config_name: str | None) -> str:
    raw = str(config_name or "").strip()
    if not raw:
        return "default"

    name = Path(raw.replace("\\", "/")).name.strip().lower()
    if name.endswith("_config.yml"):
        name = name[:-11]
    elif name.endswith("_config.yaml"):
        name = name[:-12]
    elif name.endswith(".yml"):
        name = name[:-4]
    elif name.endswith(".yaml"):
        name = name[:-5]

    name = name.replace(" ", "_")
    return name or "default"


def require_config_name_for_storage(config_name: str | None, context: str = "Artifact operation") -> str:
    raw = str(config_name or "").strip()
    if not raw:
        raise ValueError(f"{context} requires an explicit config name.")
    normalized = normalize_config_name_for_storage(raw)
    if not normalized:
        raise ValueError(f"{context} requires an explicit config name.")
    return normalized


MANAGED_LIBRARY_FILE_DIRS = ("metadata_files", "collection_files", "overlay_files")
MANAGED_CONFIG_ARTIFACT_DIRS = ("fonts",) + MANAGED_LIBRARY_FILE_DIRS


def get_managed_config_artifact_root(config_name: str | None) -> Path:
    normalized = require_config_name_for_storage(config_name, context="Managed config artifact paths")
    return Path(CONFIG_DIR) / normalized


def get_managed_library_artifact_paths(config_name: str | None) -> list[Path]:
    config_root = get_managed_config_artifact_root(config_name)
    return [config_root / folder for folder in MANAGED_LIBRARY_FILE_DIRS]


def get_legacy_managed_library_artifact_paths(config_name: str | None) -> list[Path]:
    normalized = require_config_name_for_storage(config_name, context="Legacy managed library artifact paths")
    config_dir = Path(CONFIG_DIR)
    return [config_dir / folder / normalized for folder in MANAGED_LIBRARY_FILE_DIRS]


def sync_managed_library_artifacts_to_kometa(config_name: str | None, kometa_root: str | Path | None = None, kometa_config_dir: str | Path | None = None) -> dict:
    normalized = require_config_name_for_storage(config_name, context="Managed library artifact sync")
    source_root = get_managed_config_artifact_root(normalized)
    if kometa_config_dir is not None:
        destination_base = Path(kometa_config_dir)
    elif kometa_root is not None:
        destination_base = Path(kometa_root) / "config"
    else:
        destination_base = get_kometa_config_dir()
    destination_root = destination_base / normalized

    synced: list[str] = []
    removed: list[str] = []
    missing: list[str] = []
    errors: list[str] = []

    for folder in MANAGED_LIBRARY_FILE_DIRS:
        source_dir = source_root / folder
        destination_dir = destination_root / folder

        if source_dir.exists():
            try:
                source_resolved = source_dir.resolve()
                destination_resolved = destination_dir.resolve()
                if source_resolved == destination_resolved:
                    synced.append(str(destination_dir))
                    continue
            except Exception:
                pass

            try:
                if destination_dir.exists() and _directory_tree_signature(source_dir) == _directory_tree_signature(destination_dir):
                    synced.append(str(destination_dir))
                    continue
                destination_dir.parent.mkdir(parents=True, exist_ok=True)
                if destination_dir.exists():
                    shutil.rmtree(destination_dir, onerror=handle_remove_readonly)
                shutil.copytree(source_dir, destination_dir)
                synced.append(str(destination_dir))
            except Exception as exc:
                errors.append(f"Failed to sync {source_dir} -> {destination_dir}: {exc}")
            continue

        missing.append(folder)
        if not destination_dir.exists():
            continue
        try:
            shutil.rmtree(destination_dir, onerror=handle_remove_readonly)
            removed.append(str(destination_dir))
        except Exception as exc:
            errors.append(f"Failed to remove stale Kometa artifact directory {destination_dir}: {exc}")

    if destination_root.exists():
        try:
            if not any(destination_root.iterdir()):
                destination_root.rmdir()
        except Exception:
            pass

    return {"synced": synced, "removed": removed, "missing": missing, "errors": errors}


def delete_config_artifacts(
    config_name: str | None,
    kometa_root: str | Path | None = None,
    kometa_config_dir: str | Path | None = None,
) -> dict:
    normalized = require_config_name_for_storage(config_name, context="Config artifact cleanup")
    config_dir = Path(CONFIG_DIR)
    archive_root = config_dir / "archives"
    removed: list[str] = []
    errors: list[str] = []

    targets = [
        config_dir / f"{normalized}_config.yml",
        archive_root / normalized,
        get_managed_config_artifact_root(normalized),
    ]
    targets.extend(get_managed_library_artifact_paths(normalized))
    targets.extend(get_legacy_managed_library_artifact_paths(normalized))

    if kometa_config_dir is not None:
        targets.append(Path(kometa_config_dir) / f"{normalized}_config.yml")
    elif kometa_root:
        targets.append(Path(kometa_root) / "config" / f"{normalized}_config.yml")
    else:
        targets.append(get_kometa_config_dir() / f"{normalized}_config.yml")

    for target in targets:
        try:
            if not target.exists():
                continue
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            removed.append(str(target))
        except Exception as exc:
            errors.append(f"Failed to remove {target}: {exc}")

    return {"removed": removed, "errors": errors, "config_name": normalized}


def delete_orphaned_artifact_bundle(bundle: dict | None) -> dict:
    bundle = bundle if isinstance(bundle, dict) else {}
    bundle_name = normalize_config_name_for_storage(bundle.get("name"))
    removed: list[str] = []
    errors: list[str] = []
    raw_paths = bundle.get("paths")
    candidate_paths = []

    if isinstance(raw_paths, list):
        for raw_path in raw_paths:
            text = str(raw_path or "").strip()
            if text:
                candidate_paths.append(text)

    seen: set[str] = set()
    for raw_path in candidate_paths:
        try:
            target = Path(raw_path).resolve()
        except Exception as exc:
            errors.append(f"Failed to resolve {raw_path}: {exc}")
            continue
        target_key = str(target)
        if target_key in seen:
            continue
        seen.add(target_key)
        try:
            if not target.exists():
                continue
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            removed.append(target_key)
        except Exception as exc:
            errors.append(f"Failed to remove {target}: {exc}")

    if not removed and not errors:
        errors.append(f"No filesystem artifacts were removed for {bundle_name}.")

    return {"removed": removed, "errors": errors, "config_name": bundle_name}


def list_orphaned_config_artifacts(
    active_config_names: list[str] | None = None,
    kometa_root: str | Path | None = None,
    kometa_config_dir: str | Path | None = None,
) -> dict:
    config_dir = Path(CONFIG_DIR)
    archive_root = config_dir / "archives"
    current_pattern = re.compile(r"^(?P<name>.+)_config\.yml$", re.IGNORECASE)

    if active_config_names is None:
        try:
            from modules import database

            active_config_names = database.get_unique_config_names() or []
        except Exception as exc:
            return {"orphans": [], "errors": [f"Failed to load active config names: {exc}"]}

    active_names = {normalize_config_name_for_storage(name) for name in active_config_names if str(name or "").strip()}
    bundles: dict[str, dict] = {}

    def ensure_bundle(name: str) -> dict:
        normalized = normalize_config_name_for_storage(name)
        bundle = bundles.get(normalized)
        if bundle is None:
            bundle = {
                "name": normalized,
                "has_current_file": False,
                "has_kometa_copy": False,
                "has_archive_dir": False,
                "archive_count": 0,
                "paths": [],
            }
            bundles[normalized] = bundle
        return bundle

    for path in config_dir.iterdir():
        if not path.is_file() or not path.name.lower().endswith("_config.yml"):
            continue
        match = current_pattern.match(path.name)
        if not match:
            continue
        bundle = ensure_bundle(match.group("name"))
        bundle["has_current_file"] = True
        bundle["paths"].append(str(path))

    for path in config_dir.iterdir():
        if not path.is_dir():
            continue
        if any((path / folder_name).exists() and (path / folder_name).is_dir() for folder_name in MANAGED_CONFIG_ARTIFACT_DIRS):
            bundle = ensure_bundle(path.name)
            path_text = str(path)
            if path_text not in bundle["paths"]:
                bundle["paths"].append(path_text)

    for folder_name in MANAGED_LIBRARY_FILE_DIRS:
        managed_root = config_dir / folder_name
        if not managed_root.exists() or not managed_root.is_dir():
            continue
        for path in managed_root.iterdir():
            if not path.is_dir():
                continue
            bundle = ensure_bundle(path.name)
            path_text = str(path)
            if path_text not in bundle["paths"]:
                bundle["paths"].append(path_text)

    if archive_root.exists():
        for path in archive_root.iterdir():
            if not path.is_dir():
                continue
            bundle = ensure_bundle(path.name)
            bundle["has_archive_dir"] = True
            bundle["archive_count"] = sum(1 for child in path.glob("*.yml") if child.is_file())
            bundle["paths"].append(str(path))

    active_kometa_config_dir = None
    if kometa_config_dir is not None:
        active_kometa_config_dir = Path(kometa_config_dir)
    elif kometa_root:
        active_kometa_config_dir = Path(kometa_root) / "config"
    else:
        active_kometa_config_dir = get_kometa_config_dir()

    if active_kometa_config_dir and active_kometa_config_dir.exists():
        for path in active_kometa_config_dir.iterdir():
            if not path.is_file() or not path.name.lower().endswith("_config.yml"):
                continue
            match = current_pattern.match(path.name)
            if not match:
                continue
            bundle = ensure_bundle(match.group("name"))
            bundle["has_kometa_copy"] = True
            bundle["paths"].append(str(path))

    for bundle in bundles.values():
        name = bundle.get("name")
        if not name:
            continue
        current_file = config_dir / f"{name}_config.yml"
        if current_file.exists() and current_file.is_file():
            bundle["has_current_file"] = True
            path_text = str(current_file)
            if path_text not in bundle["paths"]:
                bundle["paths"].append(path_text)

        archive_dir = archive_root / name
        if archive_dir.exists() and archive_dir.is_dir():
            bundle["has_archive_dir"] = True
            bundle["archive_count"] = sum(1 for child in archive_dir.glob("*.yml") if child.is_file())
            path_text = str(archive_dir)
            if path_text not in bundle["paths"]:
                bundle["paths"].append(path_text)

        if active_kometa_config_dir is not None:
            kometa_file = active_kometa_config_dir / f"{name}_config.yml"
            if kometa_file.exists() and kometa_file.is_file():
                bundle["has_kometa_copy"] = True
                path_text = str(kometa_file)
                if path_text not in bundle["paths"]:
                    bundle["paths"].append(path_text)

        for managed_path in get_managed_library_artifact_paths(name):
            if managed_path.exists() and managed_path.is_dir():
                path_text = str(managed_path)
                if path_text not in bundle["paths"]:
                    bundle["paths"].append(path_text)
        managed_root = get_managed_config_artifact_root(name)
        if managed_root.exists() and managed_root.is_dir():
            path_text = str(managed_root)
            if path_text not in bundle["paths"]:
                bundle["paths"].append(path_text)
        for legacy_path in get_legacy_managed_library_artifact_paths(name):
            if legacy_path.exists() and legacy_path.is_dir():
                path_text = str(legacy_path)
                if path_text not in bundle["paths"]:
                    bundle["paths"].append(path_text)

    orphans = [bundle for name, bundle in sorted(bundles.items()) if name not in active_names]
    return {"orphans": orphans, "errors": [], "active_names": sorted(active_names)}


def list_orphaned_config_versions(config_name: str | None) -> dict:
    normalized = normalize_config_name_for_storage(config_name)
    config_dir = Path(CONFIG_DIR)
    archive_dir = config_dir / "archives" / normalized
    versions: list[dict] = []

    def add_version(path: Path, kind: str) -> None:
        try:
            stats = path.stat()
        except Exception:
            return
        versions.append(
            {
                "name": normalized,
                "path": str(path.resolve()),
                "kind": kind,
                "filename": path.name,
                "mtime": stats.st_mtime,
                "modified_at": datetime.datetime.fromtimestamp(stats.st_mtime, datetime.UTC).isoformat().replace("+00:00", "Z"),
                "size": stats.st_size,
            }
        )

    current_file = config_dir / f"{normalized}_config.yml"
    if current_file.exists() and current_file.is_file():
        add_version(current_file, "current")

    if archive_dir.exists() and archive_dir.is_dir():
        for path in archive_dir.glob("*.yml"):
            if path.is_file():
                add_version(path, "archive")

    versions.sort(key=lambda item: (item.get("mtime") or 0, 1 if item.get("kind") == "current" else 0), reverse=True)
    return {"name": normalized, "versions": versions}


def prune_orphaned_config_archives(active_config_names: list[str] | None = None) -> dict:
    archive_root = Path(CONFIG_DIR) / "archives"
    removed: list[str] = []
    errors: list[str] = []

    if active_config_names is None:
        try:
            from modules import database

            active_config_names = database.get_unique_config_names() or []
        except Exception as exc:
            return {"removed": [], "errors": [f"Failed to load active config names: {exc}"]}

    active_names = {normalize_config_name_for_storage(name) for name in active_config_names if str(name or "").strip()}
    if not archive_root.exists():
        return {"removed": [], "errors": []}

    for path in archive_root.iterdir():
        if not path.is_dir():
            continue
        normalized = normalize_config_name_for_storage(path.name)
        should_remove = normalized not in active_names
        if not should_remove:
            try:
                should_remove = not any(path.iterdir())
            except Exception as exc:
                errors.append(f"Failed to inspect archive directory {path}: {exc}")
                continue
        if not should_remove:
            continue
        try:
            shutil.rmtree(path)
            removed.append(str(path))
        except Exception as exc:
            errors.append(f"Failed to remove archive directory {path}: {exc}")

    return {"removed": removed, "errors": errors}


def _unwrap_doublewrap(s: str) -> str:
    """Turn ""Foo Bar"" -> "Foo Bar" (leave normal "Foo Bar" alone)."""
    if len(s) >= 2 and s[0] == s[-1] == '"':
        inner = s[1:-1]
        if len(inner) >= 2 and inner[0] == inner[-1] == '"':
            return inner
    return s


def normalize_cli_args_inplace(argv: list[str]) -> None:
    """
    Fix double-wrapped quoted values produced on Frozen-Windows.
    Works generically, and also ensures flags that take a single value
    (like --run-libraries and --times) have their next arg cleaned.
    """
    if not argv:
        return

    # 1) generic pass: unwrap any fully-double-wrapped token
    for i, tok in enumerate(argv):
        argv[i] = _unwrap_doublewrap(tok)

    # 2) flags with exactly one following value we care about
    single_value_flags = {
        "--run-libraries",
        "--times",
        "--divider",
        "--config",
        "--timeout",
        "--width",
    }
    i = 0
    while i < len(argv):
        if argv[i] in single_value_flags and i + 1 < len(argv):
            argv[i + 1] = _unwrap_doublewrap(argv[i + 1])
            i += 2
        else:
            i += 1


def strip_outer_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


def normalize_flag_values(argv: list[str]) -> None:
    """
    Remove one layer of surrounding quotes from *values* that follow flags which
    take a single argument (no shell; quotes are literal).
    Works for both --run-libraries and --times, and is harmless elsewhere.
    """
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            # flags that take exactly one value next
            if a in {"--run-libraries", "--times", "--divider", "--config", "--width", "--timeout"}:
                if i + 1 < len(argv):
                    argv[i + 1] = strip_outer_quotes(argv[i + 1])
                    i += 2
                    continue
        # also do a generic dequote of any standalone arg that is fully quoted
        argv[i] = strip_outer_quotes(argv[i])
        i += 1
