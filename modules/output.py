import io
import jsonschema
import pyfiglet
from ruamel.yaml import YAML

from .persistence import (
    save_settings,
    retrieve_settings,
    check_minimum_settings,
    flush_session_storage,
    notification_systems_available,
)
from .helpers import build_config_dict, get_template_list, get_bits


def add_border_to_ascii_art(art):
    lines = art.split("\n")
    lines = lines[:-1]
    width = max(len(line) for line in lines)
    border_line = "#" * (width + 4)
    bordered_art = (
        [border_line] + [f"# {line.ljust(width)} #" for line in lines] + [border_line]
    )
    return "\n".join(bordered_art)


def section_heading(title):
    return add_border_to_ascii_art(pyfiglet.figlet_format(title))


def clean_section_data(section_data, config_attribute):
    clean_data = {}

    for key, value in section_data.items():
        if key == config_attribute:
            if isinstance(value, dict):
                clean_sub_data = {}
                for sub_key, sub_value in value.items():
                    if not sub_key.startswith("tmp_"):
                        clean_sub_data[sub_key] = sub_value
                clean_data[key] = clean_sub_data
            else:
                clean_data[key] = value

    return clean_data


def build_config(header_style="ascii"):
    sections = get_template_list()

    config_data = {}
    header_art = {}

    for name in sections:
        item = sections[name]
        # {'num': '001', 'file': '001-start.html', 'stem': '001-start', 'name': 'Start', 'raw_name': 'start', 'next': '010-plex', 'prev': '001-start'}
        persistence_key = item["stem"]
        config_attribute = item["raw_name"]
        if header_style == "ascii":
            header_art[config_attribute] = section_heading(item["name"])
        elif header_style == "divider":
            header_art[config_attribute] = (
                "#==================== " + item["name"] + " ====================#"
            )
        else:
            header_art[config_attribute] = ""

        section_data = retrieve_settings(persistence_key)

        # {'mal': {'authorization': {'code_verifier': 'OEOOZwnH8RWLczgahkUbo__vabgHl7XyvWkDx0twLB4FCaxPY88C9tNXnmxzBq946vSekKbPc3WhW4SwWrq0ld5xKpm27foQx4RXfnXY25iL7Pm0WCCuYkO-iQga69jv', 'localhost_url': '', 'access_token': 'None', 'token_type': 'None', 'expires_in': 'None', 'refresh_token': 'None'}, 'client_id': 'Enter MyAnimeList Client ID', 'client_secret': 'Enter MyAnimeList Client Secret'}, 'valid': True}

        if "validated" in section_data and section_data["validated"]:
            # it's valid data and needs to end up in the config
            # but first clear some chaff
            clean_data = clean_section_data(section_data, config_attribute)

            config_data[config_attribute] = clean_data

    header_comment = (
        "### We highly recommend using Visual Studio Code with indent-rainbow by oderwat extension "
        "and YAML by Red Hat extension. VSC will also leverage the above link to enhance Kometa yml edits."
    )

    # Configure the YAML instance
    yaml = YAML(typ="safe", pure=True)

    with open("json-schema/config-schema.json", "r") as file:
        schema = yaml.load(file)

    yaml.default_flow_style = False
    yaml.sort_keys = False

    # Prepare the final YAML content
    yaml_content = (
        "# yaml-language-server: $schema=https://raw.githubusercontent.com/Kometa-Team/Kometa/nightly/json-schema/config-schema.json\n\n"
        f"{section_heading('KOMETA') if header_style == 'ascii' else ('#==================== KOMETA ====================#' if header_style == 'divider' else '')}\n\n"
        f"{header_comment}\n\n"
    )

    def dump_section(title, name, data):
        # Convert 'true' and 'false' strings to boolean values
        #  this should be handled in the persistence
        for key, value in data.items():
            if value == "true":
                data[key] = True
            elif value == "false":
                data[key] = False

        # Remove 'valid' key if present
        data = {k: v for k, v in data.items() if k != "valid"}

        yaml = YAML()

        with io.StringIO() as stream:
            yaml.dump(data, stream)
            return f"{title}\n{stream.getvalue().strip()}\n\n"

    ordered_sections = [
        ("playlist_files", "160-playlist_files"),
        ("settings", "150-settings"),
        ("webhooks", "140-webhooks"),
        ("plex", "010-plex"),
        ("tmdb", "020-tmdb"),
        ("tautulli", "030-tautulli"),
        ("github", "040-github"),
        ("omdb", "050-omdb"),
        ("mdblist", "060-mdblist"),
        ("notifiarr", "070-notifiarr"),
        ("gotify", "080-gotify"),
        ("anidb", "090-anidb"),
        ("radarr", "100-radarr"),
        ("sonarr", "110-sonarr"),
        ("trakt", "120-trakt"),
        ("mal", "130-mal"),
    ]

    for section_key, section_stem in ordered_sections:
        if section_key in config_data:
            section_data = config_data[section_key]
            section_art = header_art[section_key]

            yaml_content += dump_section(section_art, section_key, section_data)

    print("\n==================================================\n")
    print(f"config_data:\n{config_data}")
    print("\n==================================================\n")
    print(f"yaml_content:\n{yaml_content}")
    print("\n==================================================\n")

    validated = False
    validation_error = None

    try:
        jsonschema.validate(yaml.load(yaml_content), schema)
        validated = True
    except jsonschema.exceptions.ValidationError as e:
        validation_error = e

    return validated, validation_error, config_data, yaml_content
