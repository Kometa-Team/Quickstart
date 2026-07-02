"""Template file listing and menu utilities extracted from the original helpers.py monolith."""

import os
import re

from pathlib import Path
from flask import current_app as app


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
