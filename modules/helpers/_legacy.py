import datetime
import os
import re
import subprocess
import sys
import time

from pathlib import Path
from plexapi.server import PlexServer
from modules import persistence

import requests
from flask import current_app as app
from flask import has_app_context, has_request_context, session

from modules.helpers._logging import ts_log

try:
    from git import Repo
except ImportError:
    Repo = None  # Prevents errors if GitPython is missing


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
