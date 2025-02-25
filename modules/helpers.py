import hashlib
import os
import re
import subprocess
import time
from pathlib import Path

import requests
from flask import current_app as app

STRING_FIELDS = {
    "apikey",
    "token",
    "username",
    "password",
}

JSON_SCHEMA_DIR = "json-schema"
GITHUB_BASE_URL = "https://raw.githubusercontent.com/Kometa-Team/Kometa"
HASH_FILE = os.path.join(JSON_SCHEMA_DIR, "file_hashes.txt")  # Stores previous file hashes


def get_pyfiglet_fonts():
    """Retrieve available PyFiglet fonts from static/fonts, sorted with custom order."""
    fonts_dir = "static/fonts"

    # Ensure predefined fonts are at the top
    predefined_fonts = ["none", "single line", "standard"]
    fonts = set(predefined_fonts)  # Using set to prevent duplicates

    # Append all .flf files, removing extension
    if os.path.exists(fonts_dir):
        fonts.update(
            f.replace(".flf", "") for f in os.listdir(fonts_dir) if f.endswith(".flf")
        )

    # Sort remaining fonts (excluding predefined ones)
    sorted_fonts = sorted(fonts - set(predefined_fonts))

    # Combine predefined fonts with sorted remaining fonts
    return predefined_fonts + sorted_fonts


def get_kometa_branch():
    """Fetch the correct branch (master or nightly)."""
    version_info = check_for_update()
    return version_info.get("kometa_branch", "nightly")  # Default to nightly


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

    # Ensure json-schema directory exists
    os.makedirs(JSON_SCHEMA_DIR, exist_ok=True)

    # Define source locations for each file
    FILE_LOCATIONS = {
        "prototype_config.yml": f"{GITHUB_BASE_URL}/{branch}/json-schema/prototype_config.yml",
        "config-schema.json": f"{GITHUB_BASE_URL}/{branch}/json-schema/config-schema.json",
        "config.yml.template": f"{GITHUB_BASE_URL}/{branch}/config/config.yml.template",
    }

    previous_hashes = load_previous_hashes()
    new_hashes = {}

    for filename, url in FILE_LOCATIONS.items():
        file_path = os.path.join(
            JSON_SCHEMA_DIR, filename
        )  # Store everything in json-schema

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


def get_local_version():
    """Read the local VERSION file and determine the branch."""
    version_file = "VERSION"
    if not os.path.exists(version_file):
        return "unknown", "custom"

    with open(version_file, "r", encoding="utf-8") as f:
        local_version = f.read().strip()

    # Use Git to determine the current branch
    try:
        branch = (
            subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode("utf-8")
            .strip()
        )
    except subprocess.CalledProcessError:
        branch = "unknown"  # Fallback if not a git repo

    return local_version, branch


def get_remote_version(branch):
    """Fetch the latest VERSION file from the correct GitHub branch."""
    url = f"https://raw.githubusercontent.com/Kometa-Team/Quickstart/{branch}/VERSION"

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException:
        return None  # If request fails, return None


def check_for_update():
    """Compare the local version with the remote version and determine Kometa branch."""
    local_version, branch = get_local_version()
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


def update_checker_loop(app):
    """Runs an update check every 24 hours in the background."""
    with app.app_context():  # Ensure Flask app context is available
        while True:
            app.config["VERSION_CHECK"] = check_for_update()
            time.sleep(86400)  # Sleep for 24 hours


def enforce_string_fields(data, string_fields):
    """
    Ensure specified fields in a dictionary are of type string.
    """
    for key, value in data.items():
        if isinstance(value, dict):
            # Recursively enforce string fields in nested dictionaries
            enforce_string_fields(value, string_fields)
        elif isinstance(value, list):
            # Process lists and ensure string enforcement within
            data[key] = [str(item) if key in string_fields else item for item in value]
        elif key in string_fields:
            original_type = type(value)
            data[key] = str(value)
    return data


def build_oauth_dict(source, form_data):
    data = {source: {"authorization": {}}}
    for key in form_data:
        final_key = key.replace(source + "_", "", 1)
        value = form_data[key]

        if final_key in (
            "client_id",
            "client_secret",
            "pin",
            "cache_expiration",
            "localhost_url",
        ):
            data[source][final_key] = value  # Store outside authorization
        elif final_key == "validated":
            data[final_key] = value
        else:
            if final_key != "url":
                data[source]["authorization"][
                    final_key
                ] = value  # Everything else goes into authorization

    return data


def build_simple_dict(source, form_data):
    data = {source: {}}
    for key in form_data:
        final_key = key.replace(
            source + "_", "", 1
        )  # Retain the original key transformation logic
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
                    value = (
                        value.strip() if isinstance(value, str) else value
                    )  # Clean strings

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
    if (source == "trakt") or (source == "mal"):
        return build_oauth_dict(source, form_data)
    else:
        return build_simple_dict(source, form_data)


def belongs_in_template_list(file):
    return (
        file.endswith(".html")
        and file != "000-base.html"
        and file != "001-navigation.html"
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
        # Normalize the string
        thing = thing.lower().strip()
        if thing in ("true", "yes", "1"):
            return True
        elif thing in ("false", "no", "0"):
            return False
        else:
            # Default to False for invalid strings
            if app.config["QS_DEBUG"]:
                print(
                    f"[DEBUG] Warning: Invalid boolean string encountered: {thing}. Defaulting to False."
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


def template_record(file, prev, next):
    rec = {}
    file_stem, num, raw_name = get_bits(file)
    rec["num"] = num
    rec["file"] = file
    rec["stem"] = file_stem
    rec["name"] = user_visible_name(raw_name)
    rec["raw_name"] = raw_name
    rec["next"] = next
    rec["prev"] = prev

    return rec


def get_menu_list():
    templates_dir = os.path.join(app.root_path, "templates")
    file_list = sorted(
        item
        for item in os.listdir(templates_dir)
        if os.path.isfile(os.path.join(templates_dir, item))
    )
    final_list = []

    for file in file_list:
        if belongs_in_template_list(file):
            file_stem, num, raw_name = get_bits(file)
            final_list.append((file, user_visible_name(raw_name)))

    return final_list


def get_template_list():
    templates_dir = os.path.join(app.root_path, "templates")
    file_list = sorted(
        item
        for item in os.listdir(templates_dir)
        if os.path.isfile(os.path.join(templates_dir, item))
    )

    templates = {}
    type_counter = {
        "012": 0,
        "013": 0,
    }  # Counters for movie, show types
    prev_item = "001-start"

    for file in file_list:
        if belongs_in_template_list(file):
            match = re.match(
                r"^(\d+)-", file
            )  # Match any length of digits followed by '-'
            if match:
                file_prefix = match.group(1)
            else:
                continue  # Skip files that do not match the pattern

            if file_prefix in type_counter:
                type_counter[file_prefix] += 1
                num = f"{file_prefix}{type_counter[file_prefix]:02d}"
            else:
                num = file_prefix

            next = get_next(file_list, file)
            prev = prev_item
            rec = template_record(file, prev, next)
            rec["num"] = num  # Update the num to include the counter
            templates[num] = rec
            prev_item = rec["stem"]

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
