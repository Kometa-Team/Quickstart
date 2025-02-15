from flask import session
import os
import secrets
from ruamel.yaml import YAML
from flask import current_app as app

from .helpers import (
    build_config_dict,
    get_template_list,
    get_bits,
    booler,
    ensure_json_schema,
)
from .iso_639_1 import iso_639_1_languages  # Importing the languages list
from .iso_639_2 import iso_639_2_languages  # Importing the languages list
from .iso_3166_1 import iso_3166_1_regions  # Importing the regions list

from .database import save_section_data, retrieve_section_data, reset_data


def extract_names(raw_source):
    source = raw_source

    # get source from referrer
    if raw_source.startswith("http"):
        source = raw_source.split("/")[-1]
        source = source.split("?")[0]

    source_name = source.split("-")[-1]
    # source will be `010-plex`
    # source_name will be `plex`

    return source, source_name


def clean_form_data(form_data):
    clean_data = {}

    for key, value in form_data.items():
        # Handle asset_directory as a list
        if key == "asset_directory":
            value_list = form_data.getlist(key)
            clean_data[key] = [v.strip() for v in value_list if v.strip()]

        # Handle use_separators & sep_style correctly for both mov & sho
        elif key.endswith("use_separators"):
            prefix = "mov" if key.startswith("mov") else "sho"
            clean_data.setdefault(f"{prefix}-template_variables", {})[
                "use_separators"
            ] = (value if value != "none" else None)

        elif key.endswith("sep_style"):
            prefix = "mov" if key.startswith("mov") else "sho"
            if (
                form_data.get(f"{prefix}-template_variables[use_separators]", "false")
                != "none"
            ):
                clean_data.setdefault(f"{prefix}-template_variables", {})[
                    "sep_style"
                ] = value.strip()

        # Standard processing for other string values
        elif isinstance(value, str):
            lc_value = value.lower().strip()
            if len(value) == 0 or lc_value == "none":
                clean_data[key] = None
            elif lc_value in ["true", "on"]:
                clean_data[key] = True
            elif lc_value == "false":
                clean_data[key] = False
            else:
                clean_data[key] = value.strip()

        # Keep other values unchanged
        else:
            clean_data[key] = value

    return clean_data


def save_settings(raw_source, form_data):
    # Extract the source and source_name
    source, source_name = extract_names(raw_source)
    # Log raw form data
    if app.config["QS_DEBUG"]:
        print(f"[DEBUG] Raw form data received: {form_data}")

    # grab new config name if they entered one:
    if "config_name" in form_data:
        session["config_name"] = form_data["config_name"]
        if app.config["QS_DEBUG"]:
            print(f"[DEBUG] Received config name in form: {session['config_name']}")

    # Handle asset_directory specifically
    if "asset_directory" in form_data:
        # Use getlist to retrieve all values for asset_directory
        asset_directories = form_data.getlist("asset_directory")
        if app.config["QS_DEBUG"]:
            print(f"[DEBUG] All asset_directory values from form: {asset_directories}")

    # Clean the data
    clean_data = clean_form_data(form_data)

    # Debug specific fields for Plex
    for field in ["plex_url", "plex_token"]:
        if app.config["QS_DEBUG"]:
            print(f"[DEBUG] Cleaned value for {field}: {clean_data.get(field)}")

    # Log the cleaned asset_directory
    if "asset_directory" in clean_data:
        if app.config["QS_DEBUG"]:
            print(f"[DEBUG] Cleaned asset_directory: {clean_data['asset_directory']}")

    # Build the dictionary to save
    data = build_config_dict(source_name, clean_data)

    # Debug final data to be saved
    if app.config["QS_DEBUG"]:
        print(f"[DEBUG] Final data structure to save: {data}")

    # Log the final data structure for asset_directory
    if source_name == "settings" and "asset_directory" in data.get("settings", {}):
        if app.config["QS_DEBUG"]:
            print(
                f"[DEBUG] Final asset_directory structure to save: {data['settings']['asset_directory']}"
            )

    # Proceed with saving
    base_data = get_dummy_data(source_name)
    user_entered = data != base_data
    validated = data.get("validated", False)

    save_section_data(
        name=session["config_name"],
        section=source_name,
        validated=validated,
        user_entered=user_entered,
        data=data,
    )

    # Confirm successful save
    if app.config["QS_DEBUG"]:
        print(f"[DEBUG] Data saved successfully.")


def retrieve_settings(target):
    # target will be `010-plex`
    data = {}

    # Get source from referrer
    source, source_name = extract_names(target)
    # source will be `010-plex`
    # source_name will be `plex`

    # Fetch stored data from DB
    db_data = retrieve_section_data(name=session["config_name"], section=source_name)
    # db_data is a tuple of validated, user_entered, data

    # Extract validation flags
    data["validated"] = booler(db_data[0])
    data["user_entered"] = booler(db_data[1])
    data[source_name] = db_data[2].get(source_name, {}) if db_data[2] else {}

    if not data[source_name]:
        data[source_name] = get_dummy_data(source_name)

    # Only modify if the target is 'libraries'
    if source_name == "libraries":
        # Ensure mov-template_variables and sho-template_variables are always present
        data[source_name].setdefault("mov-template_variables", {})
        data[source_name].setdefault("sho-template_variables", {})

        # Migrate incorrectly stored flat keys into the correct nested structure
        for key in list(data[source_name].keys()):
            if key.startswith("mov-template_variables[") or key.startswith(
                "sho-template_variables["
            ):
                prefix, variable = key.split("[")
                variable = variable.strip(
                    "]"
                )  # Extract 'use_separators' or 'sep_style'
                data[source_name][prefix][variable] = data[source_name].pop(key)

    data["code_verifier"] = secrets.token_urlsafe(100)[:128]
    data["iso_639_1_languages"] = iso_639_1_languages
    data["iso_3166_1_regions"] = iso_3166_1_regions
    data["iso_639_2_languages"] = iso_639_2_languages

    return data


def retrieve_status(target):
    # target will be `010-plex`
    # get source from referrer
    source, source_name = extract_names(target)
    # source will be `010-plex`
    # source_name will be `plex`

    db_data = retrieve_section_data(name=session["config_name"], section=source_name)
    # db_data is a tuple of validated, user_entered, data

    validated = booler(db_data[0])
    user_entered = booler(db_data[1])

    return validated, user_entered


def get_dummy_data(target):

    yaml = YAML(typ="safe", pure=True)

    ensure_json_schema()

    with open("json-schema/prototype_config.yml", "r") as file:
        base_config = yaml.load(file)

    data = {}
    try:
        data = base_config[target]
    except:
        data = {}

    return data


def check_minimum_settings():
    plex_valid, plex_user_entered = retrieve_status("plex")
    tmdb_valid, tmdb_user_entered = retrieve_status("tmdb")
    libs_valid, libs_user_entered = retrieve_status("libraries")
    sett_valid, sett_user_entered = retrieve_status("settings")

    return plex_valid, tmdb_valid, libs_valid, sett_valid


def flush_session_storage(name):
    if not name:
        name = session["config_name"]
    [
        session.pop(key)
        for key in list(session.keys())
        if not key.startswith("config_name")
    ]
    reset_data(name)


def notification_systems_available():
    notifiarr_available, notifiarr_user_entered = retrieve_status("notifiarr")
    gotify_available, gotify_user_entered = retrieve_status("gotify")
    ntfy_available, ntfy_user_entered = retrieve_status("ntfy")

    return notifiarr_available, gotify_available, ntfy_available
