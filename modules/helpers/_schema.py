"""Schema/hash utilities and json-schema sync — extracted from _legacy.py.

Owns the on-disk JSON-schema mirror under ``config/.schema/``:

- ``JSON_SCHEMA_DIR`` — target directory for mirrored schema files
- ``HASH_FILE`` — sidecar file storing SHA256 fingerprints per synced file
- ``JSON_SCHEMA_SYNC_FILES`` — canonical list of (local, remote) file pairs
- ``ensure_json_schema()`` — cache-aware refresher; downloads any changed files
"""

from __future__ import annotations

import hashlib
import os
import time

from pathlib import Path

import requests

from modules.helpers._legacy import ALLOWED_EXTENSIONS, CONFIG_DIR, GITHUB_BASE_URL
from modules.helpers._logging import ts_log

JSON_SCHEMA_DIR = os.path.join(CONFIG_DIR, ".schema")
os.makedirs(JSON_SCHEMA_DIR, exist_ok=True)

HASH_FILE = os.path.join(JSON_SCHEMA_DIR, "file_hashes.txt")
JSON_SCHEMA_REFRESH_TTL_SECONDS = int(os.environ.get("QS_JSON_SCHEMA_REFRESH_TTL_SECONDS", "1800"))
_JSON_SCHEMA_LAST_REFRESH_AT = 0.0

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


def allowed_extensions_string():
    return ", ".join(sorted(ALLOWED_EXTENSIONS))


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
