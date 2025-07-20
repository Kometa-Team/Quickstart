import namesgenerator
import os
import secrets
import json

from flask import current_app as app
from flask import session
from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError  # noqa
from urllib.parse import urlparse
from werkzeug.datastructures import MultiDict

from modules import database, helpers, iso


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
    # Make sure form_data is MultiDict for compatibility
    if not hasattr(form_data, "getlist"):
        form_data = MultiDict(form_data)

    clean_data = {}

    for key, value in form_data.items():
        # Handle asset_directory as a list
        if key == "asset_directory":
            value_list = form_data.getlist(key)
            clean_data[key] = [v.strip() for v in value_list if v.strip()]

        elif key.endswith("use_separator"):
            prefix = "mov" if key.startswith("mov") else "sho"
            clean_data.setdefault(f"{prefix}-template_variables", {})["use_separator"] = value if value != "none" else None

        elif key.endswith("sep_style"):
            prefix = "mov" if key.startswith("mov") else "sho"
            if form_data.get(f"{prefix}-template_variables[use_separator]", "false") != "none":
                clean_data.setdefault(f"{prefix}-template_variables", {})["sep_style"] = value.strip()

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

        else:
            clean_data[key] = value

    return clean_data


def save_settings(raw_source, form_data):
    # Extract the source and source_name
    source, source_name = extract_names(raw_source)
    path = urlparse(raw_source).path
    source = os.path.basename(path)

    # Ensure session config_name exists once
    if "config_name" not in session:
        session["config_name"] = namesgenerator.get_random_name()
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Initialized missing session config_name: {session['config_name']}", level="DEBUG")

    is_form = hasattr(form_data, "getlist")

    # Debug raw form data
    if app.config["QS_DEBUG"]:
        clean_dict = {k: (form_data.getlist(k) if len(form_data.getlist(k)) > 1 else form_data.get(k)) for k in form_data} if is_form else form_data
        debug_dir = os.path.join(helpers.CONFIG_DIR, "debug_logs")
        os.makedirs(debug_dir, exist_ok=True)
        debug_path = os.path.join(debug_dir, f"{source}_form_data.json")
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(clean_dict, f, indent=2, ensure_ascii=False)
        helpers.ts_log(f"Form data saved to: {debug_path}", level="DEBUG")

    # Respect config_name from form
    if "config_name" in form_data:
        session["config_name"] = form_data["config_name"]
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Received config name in form: {session['config_name']}", level="DEBUG")

    if is_form and "asset_directory" in form_data:
        asset_directories = form_data.getlist("asset_directory")
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"All asset_directory values from form: {asset_directories}", level="DEBUG")

    clean_data = clean_form_data(form_data if is_form else MultiDict(form_data))

    for field in ["plex_url", "plex_token"]:
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Cleaned value for {field}: {clean_data.get(field)}", level="DEBUG")

    if "asset_directory" in clean_data and app.config["QS_DEBUG"]:
        helpers.ts_log(f"Cleaned asset_directory: {clean_data['asset_directory']}", level="DEBUG")

    data = helpers.build_config_dict(source_name, clean_data)

    if app.config["QS_DEBUG"]:
        helpers.ts_log(f"Final data structure to save: {data}", level="DEBUG")
        if source_name == "settings" and "asset_directory" in data.get("settings", {}):
            helpers.ts_log(f"Final asset_directory structure to save: {data['settings']['asset_directory']}", level="DEBUG")

    # Validation
    base_data = get_dummy_data(source_name)
    user_entered = data != base_data
    validated = data.get("validated", False)

    # Save to DB
    database.save_section_data(
        name=session["config_name"],
        section=source_name,
        validated=validated,
        user_entered=user_entered,
        data=data,
    )

    if app.config["QS_DEBUG"]:
        helpers.ts_log(f"Data saved successfully.", level="DEBUG")


def get_stored_plex_credentials(name):
    """Retrieve stored Plex URL & token from the database."""
    try:
        settings = retrieve_settings(name)  # Fetch full settings
        plex_settings = settings.get("plex", {})  # Extract nested 'plex' dictionary
        plex_url = plex_settings.get("url")  # Correct key inside 'plex'
        plex_token = plex_settings.get("token")  # Correct key inside 'plex'

        if plex_url and plex_token:
            return plex_url, plex_token
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Plex URL or Token is missing in stored settings", level="ERROR")
    except Exception as e:
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Failed to retrieve Plex credentials: {e}", level="ERROR")
    return None, None


def update_stored_plex_libraries(name, movie_libraries, show_libraries, music_libraries):
    """Update the stored Plex libraries in the database and preserve `validated`."""
    try:
        # Fetch existing settings from DB before updating
        settings_before = retrieve_settings(name)
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Settings before update:", settings_before, level="DEBUG")

        if "plex" not in settings_before:
            settings_before["plex"] = {}

        # Preserve `validated` status
        validated_before = settings_before.get("validated", True)

        # Update library data
        settings_before["plex"]["tmp_movie_libraries"] = ",".join(movie_libraries) if movie_libraries else ""
        settings_before["plex"]["tmp_show_libraries"] = ",".join(show_libraries) if show_libraries else ""
        settings_before["plex"]["tmp_music_libraries"] = ",".join(music_libraries) if music_libraries else ""

        # Convert to a format that `save_settings()` expects
        settings_formatted = settings_before["plex"]  # Pass only the `plex` section

        # Restore `validated` before saving
        settings_formatted["validated"] = validated_before  # Prevents losing validation state

        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Sending updated Plex settings to save_settings(): {settings_formatted}", level="DEBUG")

        # Corrected function call (use "010-plex" as the raw_source)
        save_settings("010-plex", settings_formatted)  # Pass only `plex` settings, not full config

        # Fetch updated settings from DB after updating
        settings_after = retrieve_settings(name)
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Settings after update:", settings_after, level="DEBUG")

    except Exception as e:
        helpers.ts_log(f"Failed to update Plex libraries in DB: {e}", level="ERROR")


def retrieve_settings(target):
    # Ensure session config_name is set
    if "config_name" not in session:
        session["config_name"] = namesgenerator.get_random_name()

    # target will be `010-plex`
    data = {}

    # Get source from referrer
    source, source_name = extract_names(target)
    # source will be `010-plex`
    # source_name will be `plex`

    # Fetch stored data from DB
    db_data = database.retrieve_section_data(name=session["config_name"], section=source_name)
    # db_data is a tuple of validated, user_entered, data

    # Extract validation flags
    data["validated"] = helpers.booler(db_data[0])
    data["user_entered"] = helpers.booler(db_data[1])
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
            if key.startswith("mov-template_variables[") or key.startswith("sho-template_variables["):
                prefix, variable = key.split("[")
                variable = variable.strip("]")  # Extract 'use_separator' or 'sep_style'
                data[source_name][prefix][variable] = data[source_name].pop(key)

    data["code_verifier"] = secrets.token_urlsafe(100)[:128]
    data["iso_639_1_languages"] = [(la.alpha2, la.name) for la in iso.languages]
    data["iso_3166_1_regions"] = [(c.alpha2, c.name) for c in iso.countries]
    data["iso_639_2_languages"] = [(la.alpha3, la.name) for la in iso.languages]

    return data


def retrieve_status(target):
    # target will be `010-plex`
    # get source from referrer
    source, source_name = extract_names(target)
    # source will be `010-plex`
    # source_name will be `plex`

    db_data = database.retrieve_section_data(name=session["config_name"], section=source_name)
    # db_data is a tuple of validated, user_entered, data

    validated = helpers.booler(db_data[0])
    user_entered = helpers.booler(db_data[1])

    return validated, user_entered


def get_dummy_data(target):
    """
    Load dummy data from config.yml.template while handling duplicate keys gracefully.
    """

    yaml = YAML(typ="safe", pure=True)  # Safe loading mode

    helpers.ensure_json_schema()

    try:
        with open(os.path.join(helpers.JSON_SCHEMA_DIR, "config.yml.template"), "r") as file:
            base_config = yaml.load(file)
    except DuplicateKeyError as e:
        helpers.ts_log(f"Duplicate key detected in config.yml.template: {e}", level="WARNING")
        return {}  # Return empty data instead of crashing

    # Safely retrieve target data
    return base_config.get(target, {})


def check_minimum_settings():
    plex_valid, plex_user_entered = retrieve_status("plex")
    tmdb_valid, tmdb_user_entered = retrieve_status("tmdb")
    libs_valid, libs_user_entered = retrieve_status("libraries")
    sett_valid, sett_user_entered = retrieve_status("settings")

    return plex_valid, tmdb_valid, libs_valid, sett_valid


def flush_session_storage(name):
    if not name:
        name = session["config_name"]
    [session.pop(key) for key in list(session.keys()) if not key.startswith("config_name")]
    database.reset_data(name)


def notification_systems_available():
    notifiarr_available, notifiarr_user_entered = retrieve_status("notifiarr")
    gotify_available, gotify_user_entered = retrieve_status("gotify")
    ntfy_available, ntfy_user_entered = retrieve_status("ntfy")

    return notifiarr_available, gotify_available, ntfy_available
