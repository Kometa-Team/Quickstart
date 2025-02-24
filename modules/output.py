import io
import jsonschema
import json
import pyfiglet
from ruamel.yaml import YAML
from flask import current_app as app

from .persistence import (
    save_settings,
    retrieve_settings,
    check_minimum_settings,
    flush_session_storage,
    notification_systems_available,
)
from .helpers import (
    build_config_dict,
    get_template_list,
    get_bits,
    check_for_update,
    enforce_string_fields,
    ensure_json_schema,
    STRING_FIELDS,
)


def add_border_to_ascii_art(art):
    lines = art.split("\n")
    lines = lines[:-1]
    width = max(len(line) for line in lines)
    border_line = "#" * (width + 4)
    bordered_art = (
        [border_line] + [f"# {line.ljust(width)} #" for line in lines] + [border_line]
    )
    return "\n".join(bordered_art)


def section_heading(title, font="standard"):
    if font == "none":
        return ""
    elif font == "single line":
        return f"#==================== {title} ====================#"
    else:
        try:
            return add_border_to_ascii_art(pyfiglet.figlet_format(title, font=font))
        except pyfiglet.FontNotFound:
            return f"#==================== {title} ====================#"


def clean_section_data(section_data, config_attribute):
    """
    Cleans out temporary or irrelevant data before integrating it into the final config.
    """
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


def build_libraries_section(
    movie_libraries,
    show_libraries,
    movie_collections,
    show_collections,
    movie_overlays,
    show_overlays,
    movie_attributes,
    show_attributes,
):
    libraries_section = {}

    def add_entry(library_name, library_type, collections, overlays, attributes):
        entry = {}

        # Ensure overlay_files are added if any are selected
        overlay_files = [
            {"default": overlay.replace(f"{library_type}-overlay_", "")}
            for overlay, selected in overlays.items()
            if selected
        ]

        # Add selected_content_rating to overlays
        selected_content_rating_key = (
            f"{library_type}-attribute_selected_content_rating"
        )
        selected_content_rating = attributes.get(selected_content_rating_key)

        if selected_content_rating not in [None, "", "None", False]:
            if selected_content_rating == "commonsense":
                overlay_files.append({"default": "commonsense"})
            else:
                overlay_files.append(
                    {"default": f"content_rating_{selected_content_rating}"}
                )

            if app.config["QS_DEBUG"]:
                print(
                    f"[DEBUG] Added selected_content_rating: {overlay_files[-1]['default']} to overlay_files"
                )

        if overlay_files:
            entry["overlay_files"] = overlay_files

        # Ensure collection_files are added if any are selected
        collection_files = [
            {"default": collection.replace(f"{library_type}-collection_", "")}
            for collection, selected in collections.items()
            if selected
        ]
        if collection_files:
            entry["collection_files"] = collection_files

        # Retrieve template variables properly
        template_vars = {}

        # Ensure we correctly access `mov-template_variables` or `sho-template_variables`
        template_data = attributes.get(f"{library_type}-template_variables", {})

        # Normalize `use_separators`
        use_separators = template_data.get("use_separators", False)
        if use_separators in [
            None,
            "None",
            "",
        ]:  # Convert None, "None", and empty string to False
            use_separators = False
        elif isinstance(use_separators, str):  # Convert non-empty string values to True
            use_separators = True
        elif not isinstance(use_separators, bool):  # Ensure it's either True or False
            use_separators = False

        template_vars["use_separators"] = use_separators  # Always include this key

        # Normalize `sep_style`
        sep_style = template_data.get("sep_style", "")
        if sep_style not in [
            None,
            "None",
            "",
        ]:  # Ignore None, "None", and empty string values
            template_vars["sep_style"] = sep_style.strip()

        # Only add `template_variables` if it contains valid keys
        if template_vars:
            entry["template_variables"] = template_vars

        # Ensure remove_overlays & reset_overlays appear at the correct level
        remove_overlays_key = f"{library_type}-attribute_remove_overlays"
        reset_overlays_key = f"{library_type}-attribute_reset_overlays"

        if attributes.get(remove_overlays_key, False):  # Only add if True
            entry["remove_overlays"] = True

        if attributes.get(reset_overlays_key):  # Only add if value is not empty
            entry["reset_overlays"] = attributes[reset_overlays_key]

        # Add entry only if it has data
        if entry:
            libraries_section[library_name] = reorder_library_section(entry)

    # Process movie libraries
    for library_key, library_name in movie_libraries.items():
        add_entry(
            library_name, "mov", movie_collections, movie_overlays, movie_attributes
        )

    # Process show libraries
    for library_key, library_name in show_libraries.items():
        add_entry(library_name, "sho", show_collections, show_overlays, show_attributes)

    return {"libraries": libraries_section}


def reorder_library_section(library_data):
    """
    Reorders library data so that:
    - `template_variables` appears just below the library name.
    - `remove_overlays` and `reset_overlays` appear above `overlay_files`.
    - Other keys remain in their default order.
    """
    ordered_keys = [
        "template_variables",
        "remove_overlays",
        "reset_overlays",
        "overlay_files",
    ]

    reordered_data = {}

    # Ensure template_variables is placed first (if it exists)
    if "template_variables" in library_data:
        reordered_data["template_variables"] = library_data.pop("template_variables")

    # Add all remaining keys except overlay_files (keep existing order)
    for key, value in list(library_data.items()):
        if key not in ordered_keys:
            reordered_data[key] = value

    # Ensure remove_overlays and reset_overlays appear before overlay_files
    if "remove_overlays" in library_data:
        reordered_data["remove_overlays"] = library_data.pop("remove_overlays")
    if "reset_overlays" in library_data:
        reordered_data["reset_overlays"] = library_data.pop("reset_overlays")

    # Finally, add overlay_files at the correct position
    if "overlay_files" in library_data:
        reordered_data["overlay_files"] = library_data.pop("overlay_files")

    return reordered_data


def build_config(header_style="standard", config_name=None):
    """
    Build the final configuration, including all sections and headers,
    ensuring the libraries section is properly processed.
    """
    sections = get_template_list()
    config_data = {}
    header_art = {}

    # Process sections and generate header art
    for name in sections:
        item = sections[name]
        persistence_key = item["stem"]
        config_attribute = item["raw_name"]

        # Handle all header styles
        if header_style == "none":
            header_art[config_attribute] = ""  # No headers at all
        elif (
            header_style == "single line"
        ):  # 🔥 Standardizes "single line" as divider format
            header_art[config_attribute] = (
                "#==================== " + item["name"] + " ====================#"
            )
        else:
            # 🔥 Handle custom PyFiglet fonts dynamically (including "standard")
            try:
                figlet_text = pyfiglet.figlet_format(item["name"], font=header_style)
                header_art[config_attribute] = add_border_to_ascii_art(figlet_text)
            except pyfiglet.FontNotFound:
                # Fallback to "single line" divider format instead of basic text
                header_art[config_attribute] = (
                    "#==================== " + item["name"] + " ====================#"
                )

        # Retrieve settings for each section
        section_data = retrieve_settings(persistence_key)

        if "validated" in section_data and section_data["validated"]:
            # Clean and store data
            clean_data = clean_section_data(section_data, config_attribute)
            config_data[config_attribute] = clean_data

    # Process playlist_files section
    if "playlist_files" in config_data:
        playlist_data = config_data["playlist_files"]

        # Debug raw data
        if app.config["QS_DEBUG"]:
            print(
                "[DEBUG] Raw config_data['playlist_files'] content (Level 1):",
                playlist_data,
            )

        # Adjust for possible extra nesting
        if "playlist_files" in playlist_data and isinstance(
            playlist_data["playlist_files"], dict
        ):
            playlist_data = playlist_data["playlist_files"]
            if app.config["QS_DEBUG"]:
                print(
                    "[DEBUG] Adjusted playlist_data after extra nesting:", playlist_data
                )

        # Extract and process libraries
        libraries_value = playlist_data.get("libraries", "")
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Extracted libraries value:", libraries_value)

        libraries_list = [
            lib.strip() for lib in libraries_value.split(",") if lib.strip()
        ]
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Processed libraries list:", libraries_list)

        # Format playlist_files data
        formatted_playlist_files = {
            "playlist_files": [
                {
                    "default": "playlist",
                    "template_variables": {"libraries": libraries_list},
                }
            ]
        }
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Formatted playlist_files data:", formatted_playlist_files)

        # Replace in config_data
        config_data["playlist_files"] = formatted_playlist_files

    if "webhooks" in config_data:
        webhooks_data = config_data["webhooks"]

        # Handle case where `webhooks` is nested inside itself
        if isinstance(webhooks_data, dict) and "webhooks" in webhooks_data:
            webhooks_data = webhooks_data["webhooks"]  # 🔥 Fix: Handle extra nesting

        # Remove empty values
        cleaned_webhooks = {
            key: value
            for key, value in webhooks_data.items()
            if value is not None and value != "" and value != [] and value != {}
        }

        # If no valid webhooks exist, remove the "webhooks" section entirely
        if cleaned_webhooks:
            config_data["webhooks"] = {
                "webhooks": cleaned_webhooks
            }  # 🔥 Preserve webhooks key
        else:
            config_data.pop("webhooks", None)  # 🚀 Fully remove empty webhooks

        # 🔍 Debugging: Ensure webhooks are correctly cleaned
        if app.config["QS_DEBUG"]:
            print(
                "[DEBUG] Cleaned Webhooks Data AFTER Removing Empty Values:",
                cleaned_webhooks,
            )
            if "webhooks" not in config_data:
                print("[DEBUG] Webhooks section completely removed.")

    # Process the libraries section
    if "libraries" in config_data and "libraries" in config_data["libraries"]:
        nested_libraries_data = config_data["libraries"]["libraries"]

        # Debugging
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Raw nested libraries data:", nested_libraries_data)

        # Separate data by prefix
        movie_libraries = {
            key: value
            for key, value in nested_libraries_data.items()
            if key.startswith("mov-library_")
        }
        show_libraries = {
            key: value
            for key, value in nested_libraries_data.items()
            if key.startswith("sho-library_")
        }
        movie_collections = {
            key: value
            for key, value in nested_libraries_data.items()
            if key.startswith("mov-collection_")
        }
        show_collections = {
            key: value
            for key, value in nested_libraries_data.items()
            if key.startswith("sho-collection_")
        }
        movie_overlays = {
            key: value
            for key, value in nested_libraries_data.items()
            if key.startswith("mov-overlay_")
        }
        show_overlays = {
            key: value
            for key, value in nested_libraries_data.items()
            if key.startswith("sho-overlay_")
        }
        movie_attributes = {
            key: value
            for key, value in nested_libraries_data.items()
            if key.startswith("mov-attribute_") or key == "mov-template_variables"
        }
        show_attributes = {
            key: value
            for key, value in nested_libraries_data.items()
            if key.startswith("sho-attribute_") or key == "sho-template_variables"
        }

        # Debugging
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Extracted Movie Libraries:", movie_libraries)
            print("[DEBUG] Extracted Show Libraries:", show_libraries)
            print("[DEBUG] Extracted Movie Collections:", movie_collections)
            print("[DEBUG] Extracted Show Collections:", show_collections)
            print("[DEBUG] Extracted Movie Overlays:", movie_overlays)
            print("[DEBUG] Extracted Show Overlays:", show_overlays)
            print("[DEBUG] Extracted Movie Attributes:", movie_attributes)
            print("[DEBUG] Extracted Show Attributes:", show_attributes)

        # Build nested libraries structure
        libraries_section = build_libraries_section(
            movie_libraries,
            show_libraries,
            movie_collections,
            show_collections,
            movie_overlays,
            show_overlays,
            movie_attributes,
            show_attributes,
        )
        config_data["libraries"] = libraries_section
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Final Libraries Section:", libraries_section)

    # Header comment for YAML file
    header_comment = (
        "### We highly recommend using Visual Studio Code with indent-rainbow by oderwat extension "
        "and YAML by Red Hat extension. VSC will also leverage the above link to enhance Kometa yml edits."
    )

    # Build YAML content
    yaml = YAML(typ="safe", pure=True)
    yaml.default_flow_style = False
    yaml.sort_keys = False

    ensure_json_schema()

    with open("json-schema/config-schema.json", "r") as file:
        schema = yaml.load(file)

    # Fetch kometa_branch dynamically
    version_info = check_for_update()
    kometa_branch = version_info.get(
        "kometa_branch", "nightly"
    )  # Default to nightly if not found

    yaml_content = (
        f"# yaml-language-server: $schema=https://raw.githubusercontent.com/Kometa-Team/Kometa/{kometa_branch}/json-schema/config-schema.json\n\n"
        f"{add_border_to_ascii_art(section_heading('KOMETA', font=header_style)) if header_style not in ['none', 'single line'] else section_heading('KOMETA', font=header_style)}\n\n"
        f"{add_border_to_ascii_art(section_heading(config_name, font=header_style)) if header_style not in ['none', 'single line'] else section_heading(config_name, font=header_style)}\n\n"
        f"{header_comment}\n\n"
    )

    # Function to dump YAML sections
    def dump_section(title, name, data):
        import ruamel.yaml

        yaml = ruamel.yaml.YAML()
        yaml.default_flow_style = False  # Use block-style formatting
        yaml.sort_keys = False  # Preserve original key order

        # Custom representation for `None` values
        yaml.representer.add_representer(
            type(None),
            lambda self, _: self.represent_scalar("tag:yaml.org,2002:null", ""),
        )

        def clean_data(obj):
            if isinstance(obj, dict):
                # Sort specific sections alphabetically
                if name in [
                    "settings",
                    "webhooks",
                    "plex",
                    "tmdb",
                    "tautulli",
                    "github",
                    "omdb",
                    "mdblist",
                    "notifiarr",
                    "gotify",
                    "ntfy",
                    "anidb",
                    "radarr",
                    "sonarr",
                    "trakt",
                    "mal",
                ]:
                    obj = dict(
                        sorted(obj.items())
                    )  # Alphabetically sort keys in the section
                return {k: clean_data(v) for k, v in obj.items() if k != "valid"}
            elif isinstance(obj, list):
                return [clean_data(v) for v in obj]
            else:
                return obj

        # Clean the data
        cleaned_data = clean_data(data)

        # Ensure `asset_directory` is serialized as a proper YAML list
        if name == "settings" and "asset_directory" in cleaned_data.get("settings", {}):
            if isinstance(cleaned_data["settings"]["asset_directory"], str):
                # Convert multi-line string into a list
                cleaned_data["settings"]["asset_directory"] = [
                    line.strip()
                    for line in cleaned_data["settings"]["asset_directory"].splitlines()
                    if line.strip()
                ]
            elif isinstance(cleaned_data["settings"]["asset_directory"], list):
                # Ensure all list items are strings
                cleaned_data["settings"]["asset_directory"] = [
                    str(item).strip()
                    for item in cleaned_data["settings"]["asset_directory"]
                ]

        # Dump the cleaned data to YAML
        with io.StringIO() as stream:
            yaml.dump(cleaned_data, stream)
            return f"{title}\n{stream.getvalue().strip()}\n\n"

    ordered_sections = [
        ("libraries", "025-libraries"),
        ("playlist_files", "027-playlist_files"),
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
        ("ntfy", "085-ntfy"),
        ("anidb", "090-anidb"),
        ("radarr", "100-radarr"),
        ("sonarr", "110-sonarr"),
        ("trakt", "120-trakt"),
        ("mal", "130-mal"),
    ]

    # Ensure `code_verifier` is removed from mal.authorization (wherever it exists)
    if "mal" in config_data and "mal" in config_data["mal"]:
        authorization_data = config_data["mal"]["mal"].get("authorization", {})
        authorization_data.pop("code_verifier", None)  # ✅ Remove safely

    # Apply enforce_string_fields to ensure proper formatting
    config_data = enforce_string_fields(config_data, STRING_FIELDS)

    for section_key, section_stem in ordered_sections:
        if section_key in config_data:
            section_data = config_data[section_key]
            section_art = header_art[section_key]
            yaml_content += dump_section(section_art, section_key, section_data)

    validated = False
    validation_error = None

    try:
        jsonschema.validate(yaml.load(yaml_content), schema)
        validated = True
    except jsonschema.exceptions.ValidationError as e:
        validation_error = e

    return validated, validation_error, config_data, yaml_content
