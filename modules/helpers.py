import hashlib
import os
import re
import sys
from pathlib import Path

import requests
from flask import current_app as app

try:
    from git import Repo
except ImportError:
    Repo = None  # Prevents errors if GitPython is missing.


STRING_FIELDS = {"apikey", "token", "username", "password"}
GITHUB_BASE_URL = "https://raw.githubusercontent.com/Kometa-Team/Kometa"

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WORKING_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else BASE_DIR
MEIPASS_DIR = sys._MEIPASS if getattr(sys, "frozen", False) else BASE_DIR  # noqa
JSON_SCHEMA_DIR = os.path.join(WORKING_DIR, "json-schema")
os.makedirs(JSON_SCHEMA_DIR, exist_ok=True)
CONFIG_DIR = os.path.join(WORKING_DIR, "config")
os.makedirs(CONFIG_DIR, exist_ok=True)
HASH_FILE = os.path.join(JSON_SCHEMA_DIR, "file_hashes.txt")
VERSION_FILE = os.path.join(MEIPASS_DIR, "VERSION")


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


def is_valid_aspect_ratio(image):
    """Check if the image has an aspect ratio of approximately 1:1.5."""
    width, height = image.size
    return abs((width / height) - (2 / 3)) < 0.01  # Ensure it's approximately 1000x1500


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
    branch = get_kometa_branch()

    previous_hashes = load_previous_hashes()
    new_hashes = {}

    for filename, url in [
        ("prototype_config.yml", f"{GITHUB_BASE_URL}/{branch}/json-schema/prototype_config.yml"),
        ("config-schema.json", f"{GITHUB_BASE_URL}/{branch}/json-schema/config-schema.json"),
        ("config.yml.template", f"{GITHUB_BASE_URL}/{branch}/config/config.yml.template"),
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
            print(f"[ERROR] Failed to download {filename} from {url}: {e}")
            continue  # Skip to the next file

    # Save updated hashes
    save_hashes(new_hashes)


def get_remote_version(branch):
    """Fetch the latest VERSION file from the correct GitHub branch."""
    url = f"https://raw.githubusercontent.com/Kometa-Team/Quickstart/{branch}/VERSION"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException:
        return None  # If request fails, return None


def get_branch():
    """Determine the current branch with Docker support."""
    # ✅ If running in Docker, use the environment variable
    if os.getenv("QUICKSTART_DOCKER", "False").lower() in ["true", "1"]:
        return os.getenv("BRANCH_NAME", "master")  # Use environment variable

    # ✅ Otherwise, try GitPython (if available)
    if Repo:
        try:
            return Repo(path=".").head.ref.name  # noqa
        except Exception:  # noqa
            pass  # Ignore errors if GitPython fails

    # ✅ Fallback: Use BRANCH_NAME from the environment (for non-Docker cases)
    return os.getenv("BRANCH_NAME", "master")


def get_kometa_branch():
    """Fetch the correct branch (master or nightly)."""
    version_info = check_for_update()
    return version_info.get("kometa_branch", "nightly")  # Default to nightly


def get_version():
    """Read the local VERSION file"""
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "unknown"


def check_for_update():
    """Compare the local version with the remote version and determine Kometa branch."""
    local_version = get_version()
    branch = get_branch()
    remote_version = get_remote_version(branch)

    update_available = remote_version and remote_version != local_version

    # Determine Kometa branch
    kometa_branch = "master" if branch == "master" else "nightly"

    return {
        "local_version": local_version,
        "remote_version": remote_version,
        "branch": branch,
        "kometa_branch": kometa_branch,
        "update_available": update_available,
    }


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

        if final_key in ["client_id", "client_secret", "pin", "cache_expiration", "localhost_url"]:
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
            data[source][final_key] = value  # Retain lists as-is
        else:
            # Handle individual values
            if value is not None and not isinstance(value, bool):
                try:
                    value = int(value)  # Convert numbers to integers
                except ValueError:
                    value = value.strip() if isinstance(value, str) else value  # Clean strings

            # Assign the value to the appropriate place
            if final_key == "validated":
                data[final_key] = value
            else:
                data[source][final_key] = value

    # Special handling for run_order to split and clean it into a list
    if "run_order" in data[source]:
        run_order = data[source]["run_order"]
        if run_order is not None:
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
                print(f"[DEBUG] Warning: Invalid boolean string encountered: {thing}. Defaulting to False.")
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
