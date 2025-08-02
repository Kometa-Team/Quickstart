import datetime
import hashlib
import platform
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from plexapi.server import PlexServer
from plexapi.exceptions import BadRequest, NotFound, Unauthorized
from modules import persistence

import requests
from flask import current_app as app
from flask import has_request_context, session

try:
    from git import Repo
except ImportError:
    Repo = None  # Prevents errors if GitPython is missing


STRING_FIELDS = {"apikey", "token", "username", "password"}
GITHUB_BASE_URL = "https://raw.githubusercontent.com/Kometa-Team/Kometa"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "bmp"}

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
    match = re.match(r"(mov|sho)-library_([^-]+(?:-[^-]+)*)-", key)
    return match.group(2) if match else None


def get_pyfiglet_fonts():
    """Retrieve available PyFiglet fonts from static/fonts, sorted with custom order."""
    fonts_dir = "static/fonts"

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
    # branch = get_kometa_branch()
    branch = "nightly"

    previous_hashes = load_previous_hashes()
    new_hashes = {}

    for filename, url in [
        (
            "prototype_config.yml",
            f"{GITHUB_BASE_URL}/{branch}/json-schema/prototype_config.yml",
        ),
        (
            "config-schema.json",
            f"{GITHUB_BASE_URL}/{branch}/json-schema/config-schema.json",
        ),
        (
            "config.yml.template",
            f"{GITHUB_BASE_URL}/{branch}/config/config.yml.template",
        ),
    ]:
        file_path = os.path.join(JSON_SCHEMA_DIR, filename)  # Store everything in json-schema

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            new_content = response.text
            new_hash = calculate_hash(new_content)

            # Compare hash with previous version
            if filename in previous_hashes and previous_hashes[filename] == new_hash:
                new_hashes[filename] = new_hash  # Keep existing hash
                continue

            # Save the new file if hash has changed
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            new_hashes[filename] = new_hash

        except requests.RequestException as e:
            ts_log(f"Failed to download {filename} from {url}: {e}", level="ERROR")
            continue  # Skip to the next file

    # Save updated hashes
    save_hashes(new_hashes)


def get_remote_version(branch):
    """Fetch the latest VERSION file from the correct GitHub branch."""
    try:
        response = requests.get(f"https://raw.githubusercontent.com/Kometa-Team/Quickstart/{branch}/VERSION", timeout=5)
        response.raise_for_status()
        version = response.text.strip()
    except requests.RequestException:
        return None  # If request fails, return None
    try:
        response = requests.get(f"https://raw.githubusercontent.com/Kometa-Team/Quickstart/{branch}/BUILDNUM", timeout=5)
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
    remote_version = get_remote_version(branch)

    update_available = remote_version and remote_version != local_version

    # Determine Kometa branch
    # kometa_branch = "master" if branch == "master" else "nightly"
    kometa_branch = "nightly"

    # Get OS name and correct extension
    os_name, os_ext = get_running_os()

    return {
        "local_version": local_version,
        "remote_version": remote_version,
        "branch": branch,
        "kometa_branch": kometa_branch,
        "update_available": update_available,
        "running_on": os_name,
        "file_ext": os_ext,
    }


def get_running_os():
    # Preserve build for backward compatibility, even if unused
    build = os.getenv("BUILD_OS", "local").lower()

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
            "cache_expiration",
            "localhost_url",
        ]:
            data[source][final_key] = value  # Store outside authorization
        elif final_key == "validated":
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
            if final_key == "validated":
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
        formatted_name = "Final Validation"
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


def get_bits(file):
    file_stem = Path(file).stem
    bits = file_stem.split("-")
    num = bits[0]
    raw_name = bits[1]

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

    for file in file_list:
        if belongs_in_template_list(file):
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

            next_record = get_next(file_list, file)
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


def load_quickstart_config(filename: str):
    json_path = os.path.join(JSON_SETTINGS, filename)
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_top_imdb_items(library_id, media_type, placeholder_id=None):
    ts_log(f"Fetching Plex credentials for '010-plex'", level="DEBUG")
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

    saved_item = None
    if placeholder_id and not any(x["id"] == placeholder_id for x in imdb_items):
        saved_item = find_item_by_imdb_id(library_id, placeholder_id, media_type)
        if saved_item:
            ts_log(
                f"Saved placeholder found separately: {saved_item['title']}",
                level="DEBUG",
            )

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


def find_item_by_imdb_id(library_name, imdb_id, media_type):
    from modules import plex_connection

    if not imdb_id:
        return None

    plex = plex_connection.connect_to_plex()
    if not plex:
        return None

    section = plex.library.section(library_name)
    if not section:
        return None

    # Search by IMDb ID
    results = section.search(guid=f"imdb://{imdb_id}")
    if not results:
        return None

    item = results[0]
    return {"id": imdb_id, "title": item.title}


def allowed_extensions_string():
    return ", ".join(sorted(ALLOWED_EXTENSIONS))


def get_plex_summary():
    try:
        plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")
        plex = PlexServer(plex_url, plex_token)

        # Core metadata
        server_name = plex.friendlyName or "Plex Server"
        version = plex.version or "Unknown Version"
        platform = plex.platform or "Unknown OS"
        platform_version = plex.platformVersion or "Unknown Version"

        # Settings
        settings = plex.settings

        # DB Cache
        try:
            db_cache_size = settings.get("DatabaseCacheSize").value
            db_cache_str = f"{db_cache_size} MB"
        except NotFound:
            db_cache_str = "Unknown"

        # Update Channel
        try:
            update_channel = settings.get("butlerUpdateChannel").value
            if update_channel == "16":
                update_channel_str = "Public update channel."
            elif update_channel == "8":
                update_channel_str = "PlexPass update channel."
            else:
                update_channel_str = f"Unknown update channel ({update_channel})."
        except NotFound:
            update_channel_str = "Unknown update channel."

        # Plex Pass Status
        try:
            plex_pass = plex.myPlexAccount().subscriptionActive
        except Exception:
            plex_pass = "Unknown"

        plex_pass_str = f"PlexPass: {plex_pass} on {update_channel_str}"

        # Maintenance Window
        try:
            start_hour = int(settings.get("butlerStartHour").value)
            end_hour = int(settings.get("butlerEndHour").value)
            maintenance_window = f"Scheduled maintenance running between {start_hour}:00 and {end_hour}:00"
        except Exception:
            maintenance_window = "Scheduled maintenance times could not be found."

        # Final summary string
        return (
            f"Connected to server {server_name} version {version}\n"
            f"Running on {platform} version {platform_version}\n"
            f"Plex DB cache setting: {db_cache_str}\n"
            f"{plex_pass_str}\n"
            f"{maintenance_window}"
        )

    except Exception as e:
        return f"Plex summary unavailable due to error: {e}"


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


def get_plex_metadata():
    try:
        plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")
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

        # Per-library info
        library_metadata = get_library_metadata()

        return {
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


def get_library_metadata():
    try:
        plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")
        plex = PlexServer(plex_url, plex_token)

        library_data = {}
        for section in plex.library.sections():
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
                            shows = section.search(libtype="show")
                            lib_info["episode_count"] = sum(show.episodes(totalSize=True).totalSize for show in shows)
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


def save_to_named_config(yaml_text, config_name):
    config_dir = Path(CONFIG_DIR)
    kometa_root = Path(app.config.get("KOMETA_ROOT", "."))
    kometa_config_dir = kometa_root / "config"
    # Normalize config name
    name = config_name.strip().lower().replace(" ", "_") or "default"
    latest_filename = f"{name}_config.yml"
    latest_path = config_dir / latest_filename
    kometa_path = kometa_config_dir / latest_filename

    # If latest exists, archive it to _1, _2, etc.
    if latest_path.exists():
        counter = 1
        while True:
            archive_path = config_dir / f"{name}_config_{counter}.yml"
            if not archive_path.exists():
                latest_path.rename(archive_path)
                ts_log(f"Archived old config to: {archive_path}")
                break
            counter += 1

    # Save the new config to both locations
    config_dir.mkdir(parents=True, exist_ok=True)
    kometa_config_dir.mkdir(parents=True, exist_ok=True)

    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(yaml_text)
    with open(kometa_path, "w", encoding="utf-8") as f:
        f.write(yaml_text)

    ts_log(f"Saved new config to: {latest_path}")
    ts_log(f"Also copied config to: {kometa_path}")

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


def check_kometa_update(kometa_root=None):
    branch = get_kometa_branch()
    local_version = get_kometa_local_version(kometa_root)
    remote_version = get_kometa_remote_version(branch)
    update_available = remote_version and remote_version != local_version

    return {
        "local_version": local_version,
        "remote_version": remote_version,
        "branch": branch,
        "update_available": update_available,
    }


def perform_kometa_update(kometa_root):
    logs = []
    success = True

    try:
        kometa_root = Path(kometa_root).resolve()
        is_windows = sys.platform.startswith("win")

        venv_path = kometa_root / "kometa-venv"
        pip_bin = venv_path / ("Scripts" if is_windows else "bin") / ("pip.exe" if is_windows else "pip")

        # 1. Git pull
        logs.append("🔄 Running: git pull")
        result = subprocess.run(
            ["git", "pull"],
            cwd=kometa_root,
            capture_output=True,
            text=True,
            shell=is_windows,
        )
        logs.append(result.stdout.strip() or "(no output)")
        if result.returncode != 0:
            logs.append(result.stderr.strip())
            success = False

        # 2. Pip install -r requirements.txt
        if success:
            logs.append("\n📦 Reinstalling requirements...")
            pip_cmd = [
                str(pip_bin),
                "install",
                "--no-cache-dir",
                "--upgrade",
                "-r",
                "requirements.txt",
            ]
            result = subprocess.run(
                pip_cmd,
                cwd=kometa_root,
                capture_output=True,
                text=True,
                shell=is_windows,
            )
            logs.append(result.stdout.strip() or "(no output)")
            if result.returncode != 0:
                logs.append(result.stderr.strip())
                success = False

        logs.append("\n✅ Update completed." if success else "\n❌ Update failed.")
        return {"success": success, "log": logs}

    except Exception as e:
        logs.append(f"❌ Exception: {str(e)}")
        return {"success": False, "log": logs}


def check_for_test_libraries(quickstart_root):
    """
    Returns True if 'plex-test-libraries' exists as a sibling to quickstart_root
    """
    if not quickstart_root:
        return {"found": False, "error": "Quickstart root not detected."}

    parent_dir = os.path.dirname(quickstart_root)
    target_path = os.path.join(parent_dir, "plex-test-libraries")

    return {"found": os.path.isdir(target_path)}


def clone_test_libraries(quickstart_root):
    """
    Clones plex-test-libraries as a sibling to Quickstart root.
    """
    import subprocess

    if not quickstart_root:
        return {"success": False, "output": "Quickstart root not detected."}

    parent_dir = os.path.dirname(quickstart_root)
    target_path = os.path.join(parent_dir, "plex-test-libraries")

    if os.path.exists(target_path):
        return {"success": True, "output": "Test libraries already exist."}

    try:
        result = subprocess.run(
            ["git", "clone", "https://github.com/chazlarson/plex-test-libraries"],
            cwd=parent_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        return {"success": True, "output": result.stdout or "Cloned successfully."}
    except subprocess.CalledProcessError as e:
        return {"success": False, "output": e.stderr or "Cloning failed."}


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
    with open(LOG_FILE, "w", encoding="utf-8") as f:
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
