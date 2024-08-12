from flask import session
import os
import secrets
from ruamel.yaml import YAML
from flask import current_app as app

from .helpers import build_config_dict, get_template_list, get_bits, booler
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

    for key in form_data:
        value = form_data[key]
        lc_value = value.lower() if isinstance(value, str) else None
        if len(value) == 0 or lc_value == "none":
            clean_data[key] = None
        elif lc_value == "true" or lc_value == "on":
            clean_data[key] = True
        elif lc_value == "false":
            clean_data[key] = False
        else:
            clean_data[key] = value

    return clean_data


def save_settings(raw_source, form_data):
    # get source from referrer
    source, source_name = extract_names(raw_source)
    # source will be `010-plex`
    # source_name will be `plex`

    # grab new config name if they entered one:
    if "config_name" in form_data:
        session["config_name"] = form_data["config_name"]
        print(f"received config name in form: {session['config_name']}")

    clean_data = clean_form_data(form_data)

    if len(source) > 0:
        data = build_config_dict(source_name, clean_data)

        base_data = get_dummy_data(source_name)

        user_entered = data != base_data

        validated = data["validated"] if "validated" in data else False

        print(f"saving under config_name: {session['config_name']}")

        save_section_data(
            name=session["config_name"],
            section=source_name,
            validated=validated,
            user_entered=user_entered,
            data=data,
        )

        print(f"data saved for {source}")


def retrieve_settings(target):
    # target will be `010-plex`
    data = {}

    # get source from referrer
    source, source_name = extract_names(target)
    # source will be `010-plex`
    # source_name will be `plex`

    db_data = retrieve_section_data(name=session["config_name"], section=source_name)
    # db_data is a tuple of validated, user_entered, data

    data["validated"] = booler(db_data[0])
    data["user_entered"] = booler(db_data[1])
    data[source_name] = db_data[2][source_name] if db_data[2] else None

    if not data[source_name]:
        data[source_name] = get_dummy_data(source_name)

    data["code_verifier"] = secrets.token_urlsafe(100)[:128]
    data["iso_639_1_languages"] = iso_639_1_languages
    data["iso_3166_1_regions"] = iso_3166_1_regions
    data["iso_639_1_languages"] = iso_639_1_languages
    data["iso_639_2_languages"] = iso_639_2_languages

    # if source_name == 'mal':
    #     data['code_verifier'] = secrets.token_urlsafe(100)[:128]

    # if source_name == 'tmdb':
    #     data['iso_639_1_languages'] = iso_639_1_languages
    #     data['iso_3166_1_regions'] = iso_3166_1_regions

    # if source_name == 'anidb':
    #     data['iso_639_1_languages'] = iso_639_1_languages

    # if target == '150-settings':
    #     data['iso_639_2_languages'] = iso_639_2_languages

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

    return plex_valid, tmdb_valid


def flush_session_storage():
    reset_data(name=session["config_name"])


def notification_systems_available():
    notifiarr_available, notifiarr_user_entered = retrieve_status("notifiarr")
    gotify_available, gotify_user_entered = retrieve_status("gotify")

    return notifiarr_available, gotify_available
