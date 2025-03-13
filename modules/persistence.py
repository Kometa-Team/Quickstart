import secrets

from flask import current_app as app
from flask import session
from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError

from modules import database, helpers
from modules.iso_3166_1 import iso_3166_1_regions  # Importing the regions list
from modules.iso_639_1 import iso_639_1_languages  # Importing the languages list
from modules.iso_639_2 import iso_639_2_languages  # Importing the languages list


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
    data = helpers.build_config_dict(source_name, clean_data)

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

    database.save_section_data(
        name=session["config_name"],
        section=source_name,
        validated=validated,
        user_entered=user_entered,
        data=data,
    )

    # Confirm successful save
    if app.config["QS_DEBUG"]:
        print(f"[DEBUG] Data saved successfully.")


def get_stored_plex_credentials(name):
    """Retrieve stored Plex URL & token from the database."""
    try:
        settings = retrieve_settings(name)  # Fetch full settings
        plex_settings = settings.get("plex", {})  # ✅ Extract nested 'plex' dictionary
        plex_url = plex_settings.get("url")  # ✅ Correct key inside 'plex'
        plex_token = plex_settings.get("token")  # ✅ Correct key inside 'plex'

        if not plex_url or not plex_token:
            print("[ERROR] Plex URL or Token is missing in stored settings")
            return None, None

        return plex_url, plex_token

    except Exception as e:
        print(f"[ERROR] Failed to retrieve Plex credentials: {e}")
        return None, None


def update_stored_plex_libraries(
    name, movie_libraries, show_libraries, music_libraries
):
    """Update the stored Plex libraries in the database and preserve `validated`."""
    try:
        # ✅ Fetch existing settings from DB before updating
        settings_before = retrieve_settings(name)
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Settings before update:", settings_before)

        if "plex" not in settings_before:
            settings_before["plex"] = {}

        # ✅ Preserve `validated` status
        validated_before = settings_before.get("validated", True)

        # ✅ Update library data
        settings_before["plex"]["tmp_movie_libraries"] = (
            ",".join(movie_libraries) if movie_libraries else ""
        )
        settings_before["plex"]["tmp_show_libraries"] = (
            ",".join(show_libraries) if show_libraries else ""
        )
        settings_before["plex"]["tmp_music_libraries"] = (
            ",".join(music_libraries) if music_libraries else ""
        )

        # ✅ Convert to a format that `save_settings()` expects
        settings_formatted = settings_before["plex"]  # ✅ Pass only the `plex` section

        # ✅ Restore `validated` before saving
        settings_formatted["validated"] = (
            validated_before  # 🔥 Prevents losing validation state
        )

        if app.config["QS_DEBUG"]:
            print(
                f"[DEBUG] Sending updated Plex settings to save_settings(): {settings_formatted}"
            )

        # ✅ Corrected function call (use "010-plex" as the raw_source)
        save_settings(
            "010-plex", settings_formatted
        )  # 🔥 Pass only `plex` settings, not full config

        # ✅ Fetch updated settings from DB after updating
        settings_after = retrieve_settings(name)
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Settings after update:", settings_after)

    except Exception as e:
        print(f"[ERROR] Failed to update Plex libraries in DB: {e}")


def retrieve_settings(target):
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
        with open("json-schema/config.yml.template", "r") as file:
            base_config = yaml.load(file)
    except DuplicateKeyError as e:
        print(f"[WARNING] Duplicate key detected in config.yml.template: {e}")
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
    [
        session.pop(key)
        for key in list(session.keys())
        if not key.startswith("config_name")
    ]
    database.reset_data(name)


def notification_systems_available():
    notifiarr_available, notifiarr_user_entered = retrieve_status("notifiarr")
    gotify_available, gotify_user_entered = retrieve_status("gotify")
    ntfy_available, ntfy_user_entered = retrieve_status("ntfy")

    return notifiarr_available, gotify_available, ntfy_available
