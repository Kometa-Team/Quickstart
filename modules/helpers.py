import os
import re
from flask import current_app as app
from pathlib import Path
from PIL import Image, ImageDraw


STRING_FIELDS = {
    "apikey",
    "token",
    "username",
    "password",
}


def is_default_image(image_path):
    try:
        img = Image.open(image_path)
        grey_img = Image.new("RGBA", (1000, 1500), (128, 128, 128, 255))
        return list(img.getdata()) == list(grey_img.getdata())
    except Exception:
        return False


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

        if (
            (final_key == "client_id")
            or (final_key == "client_secret")
            or (final_key == "pin")
        ):
            data[source][final_key] = value
        elif final_key == "validated":
            data[final_key] = value
        else:
            if final_key != "url":
                data[source]["authorization"][final_key] = value

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
