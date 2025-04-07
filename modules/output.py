import io
import os
import json
from datetime import datetime

import jsonschema
import pyfiglet
from flask import current_app as app
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq

from modules import helpers, persistence


def add_border_to_ascii_art(art):
    lines = art.split("\n")
    lines = lines[:-1]
    width = max(len(line) for line in lines)
    border_line = "#" * (width + 4)
    bordered_art = [border_line] + [f"# {line.ljust(width)} #" for line in lines] + [border_line]
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
    movie_templates,
    show_templates,
    movie_top_level,
    show_top_level,
):
    libraries_section = {}

    def add_entry(
        library_key,
        library_name,
        library_type,
        collections,
        overlays,
        attributes,
        templates,
        top_level,
    ):
        """Processes a single library and adds valid data to the output."""
        entry = {}

        lib_id = helpers.extract_library_name(library_key)

        if app.config["QS_DEBUG"]:
            print(f"[DEBUG] Processing Library: {library_key} -> {library_name}")

        # Process Operations Attributes
        operations_fields = [
            "assets_for_all",
            "mass_imdb_parental_labels",
            "mass_collection_mode",
            "update_blank_track_titles",
            "remove_title_parentheses",
            "split_duplicates",
            "radarr_add_all",
            "sonarr_add_all",
        ]
        operations = {}
        attr_group = attributes.get(lib_id, {})
        # Begin: Mass Genre Update Section
        mass_genre_update_keys = [
            "tmdb",
            "tvdb",
            "imdb",
            "omdb",
            "anidb",
            "anidb_3_0",
            "anidb_2_5",
            "anidb_2_0",
            "anidb_1_5",
            "anidb_1_0",
            "anidb_0_5",
            "mal",
            "lock",
            "unlock",
            "remove",
            "reset",
        ]
        mass_genre_update = []

        # Grab the full reordered list from hidden input
        custom_key = f"{library_type}-library_{lib_id}-attribute_mass_genre_update_order"
        order_value = attr_group.get(custom_key)

        if order_value:
            try:
                parsed = json.loads(order_value)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, str) and item.startswith("[") and item.endswith("]"):
                            # Probably malformed nested list — skip
                            continue
                        elif isinstance(item, str):
                            mass_genre_update.append(item)
                        elif isinstance(item, list):  # rare case
                            mass_genre_update.extend(item)
            except Exception as e:
                print(f"[DEBUG] Skipping invalid JSON in custom genre: {order_value} — {e}")

        # Also include custom genre strings (if any) from the other hidden input
        custom_strings_key = f"{library_type}-library_{lib_id}-attribute_mass_genre_update_custom"
        custom_strings_value = attr_group.get(custom_strings_key)

        if custom_strings_value:
            try:
                parsed_custom = json.loads(custom_strings_value)
                if isinstance(parsed_custom, list) and parsed_custom:
                    # Wrap it in a CommentedSeq to enforce flow style
                    custom_flow_list = CommentedSeq(parsed_custom)
                    custom_flow_list.fa.set_flow_style()  # Force [ "Thriller", "Action" ] formatting
                    mass_genre_update.append(custom_flow_list)
            except Exception as e:
                print(f"[DEBUG] Skipping invalid JSON in custom genre strings: {custom_strings_value} — {e}")

        if mass_genre_update:
            operations["mass_genre_update"] = mass_genre_update

        # Begin: Mass Content Rating Update Section
        mass_content_rating_update = []

        # Get the ordered source list (sortable)
        rating_custom_order_key = f"{library_type}-library_{lib_id}-attribute_mass_content_rating_update_order"
        rating_custom_order_value = attr_group.get(rating_custom_order_key)

        if rating_custom_order_value:
            try:
                parsed = json.loads(rating_custom_order_value)
                if isinstance(parsed, list):
                    mass_content_rating_update.extend(parsed)
            except Exception as e:
                print(f"[DEBUG] Skipping invalid JSON in content rating sources: {rating_custom_order_value} — {e}")

        # Get the optional custom string (e.g., "NR")
        rating_custom_string_key = f"{library_type}-library_{lib_id}-attribute_mass_content_rating_update_custom_string"
        rating_custom_string_value = None
        if attr_group and rating_custom_string_key in attr_group:
            raw_value = attr_group.get(rating_custom_string_key)
            if raw_value:
                rating_custom_string_value = raw_value.strip()

        if rating_custom_string_value:
            mass_content_rating_update.append(rating_custom_string_value)

        # Only add to operations if we have any items
        if mass_content_rating_update:
            mcru_list = CommentedSeq(mass_content_rating_update)
            mcru_list.fa.set_block_style()  # ensures YAML list style
            operations["mass_content_rating_update"] = mcru_list

        # Begin: Mass Original Title Update Section
        mass_original_title_update = []

        # Handle the toggle order list
        original_title_order_key = f"{library_type}-library_{lib_id}-attribute_mass_original_title_update_order"
        original_title_order_value = attr_group.get(original_title_order_key)

        if original_title_order_value:
            try:
                parsed = json.loads(original_title_order_value)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, str):
                            mass_original_title_update.append(item)
                        elif isinstance(item, list):  # nested list — flatten it
                            mass_original_title_update.extend(item)
            except Exception as e:
                print(f"[DEBUG] Skipping invalid JSON in original title order: {original_title_order_value} — {e}")

        # Handle the optional custom string (e.g., "Unknown")
        original_title_custom_key = f"{library_type}-library_{lib_id}-attribute_mass_original_title_update_custom_string"
        original_title_custom_value = attr_group.get(original_title_custom_key)

        if original_title_custom_value:
            try:
                stripped = original_title_custom_value.strip()
                if stripped:
                    mass_original_title_update.append(stripped)
            except Exception as e:
                print(f"[DEBUG] Skipping invalid original title custom string: {original_title_custom_value} — {e}")

        if mass_original_title_update:
            motu_list = CommentedSeq(mass_original_title_update)
            motu_list.fa.set_block_style()
            operations["mass_original_title_update"] = motu_list

        for field in operations_fields:
            attr_key = f"{library_type}-library_{lib_id}-attribute_{field}"
            value = attr_group.get(attr_key, None)
            if value not in [None, "", False]:
                operations[field] = value

        # Handle nested delete_collections block
        delete_fields = [
            "delete_collections_configured",
            "delete_collections_managed",
            "delete_collections_less",
            "delete_collections_ignore_empty_smart_collections",
        ]
        delete_collections = {}
        for df in delete_fields:
            attr_key = f"{library_type}-library_{lib_id}-attribute_{df}"
            value = attr_group.get(attr_key, None)
            if value not in [None, "", False]:
                yaml_key = df.replace("delete_collections_", "")
                delete_collections[yaml_key] = value

        if delete_collections:
            operations["delete_collections"] = delete_collections

        if operations:
            entry["operations"] = operations

        # Process Collections
        collection_key = helpers.extract_library_name(library_key)
        if collection_key and collection_key in collections:
            collection_files = [
                {"default": key.split(f"{library_type}-library_{collection_key}-collection_")[-1]} for key, selected in collections[collection_key].items() if selected is True
            ]
            if collection_files:
                entry["collection_files"] = collection_files

        # Process Overlays
        overlay_key = helpers.extract_library_name(library_key)
        if overlay_key and overlay_key in overlays:
            overlay_files = []
            for key, value in overlays[overlay_key].items():
                if isinstance(value, bool) and value:
                    overlay_files.append({"default": key.split(f"{library_type}-library_{overlay_key}-overlay_")[-1]})
                elif isinstance(value, str) and value:
                    if value.lower() == "commonsense":
                        overlay_files.append({"default": "commonsense"})
                    else:
                        overlay_files.append({"default": f"content_rating_{value}"})
            if overlay_files:
                entry["overlay_files"] = overlay_files

        # Template Variables
        template_key = helpers.extract_library_name(library_key)
        template_data = templates.get(template_key, {})
        sep_color_key = None
        for key in template_data.keys():
            if key.endswith("-template_variables[use_separator]") and key.startswith(f"{library_type}-library_{template_key}"):
                sep_color_key = key
                break

        sep_color = template_data.get(sep_color_key)
        template_vars = {"use_separator": True if sep_color else False}
        if sep_color:
            template_vars["sep_style"] = sep_color
        entry["template_variables"] = template_vars

        # Grouped mass update operations (excluding mass_genre_update, handled earlier)
        grouped_operations = [
            "mass_content_rating_update",
            "mass_original_title_update",
            "mass_studio_update",
            "mass_tagline_update",
            "mass_originally_available_update",
            "mass_added_at_update",
            "mass_audience_rating_update",
            "mass_critic_rating_update",
            "mass_user_rating_update",
            "mass_episode_audience_rating_update",
            "mass_episode_critic_rating_update",
            "mass_episode_user_rating_update",
            "mass_background_update",
            "mass_poster_update",
            "radarr_remove_by_tag",
            "sonarr_remove_by_tag",
        ]

        for op in grouped_operations:
            custom_list_key = f"{library_type}-library_{lib_id}-attribute_{op}_custom"
            custom_string_key = f"{library_type}-library_{lib_id}-attribute_{op}_custom_string"
            order_key = f"{library_type}-library_{lib_id}-attribute_{op}_order"

            op_values = []

            # 1. Ordered source list (sortable)
            order_value = attr_group.get(order_key)
            if order_value:
                try:
                    parsed = json.loads(order_value)
                    if isinstance(parsed, list):
                        for item in parsed:
                            if isinstance(item, (int, float)):
                                op_values.append(item)
                            elif isinstance(item, str) and item.strip():
                                # Preserve valid date strings (e.g. "2023-01-01")
                                op_values.append(item.strip())
                except Exception as e:
                    print(f"[DEBUG] Skipping invalid JSON in {op}_order: {order_value} — {e}")

            # 2. Custom list (JSON array from UI)
            custom_list_value = attr_group.get(custom_list_key)
            if custom_list_value:
                try:
                    parsed_custom = json.loads(custom_list_value)
                    if isinstance(parsed_custom, list):
                        for item in parsed_custom:
                            if isinstance(item, (int, float)):
                                op_values.append(item)
                            elif isinstance(item, str) and item.strip():
                                op_values.append(item.strip())
                except Exception as e:
                    print(f"[DEBUG] Skipping invalid JSON in {op}_custom: {custom_list_value} — {e}")

            # 3. Fallback to single custom string (if defined)
            elif custom_string_key in attr_group:
                raw_value = attr_group.get(custom_string_key)
                if isinstance(raw_value, str) and raw_value.strip():
                    if op in [
                        "mass_critic_rating_update",
                        "mass_user_rating_update",
                        "mass_audience_rating_update",
                        "mass_episode_critic_rating_update",
                        "mass_episode_user_rating_update",
                        "mass_episode_audience_rating_update",
                    ]:
                        try:
                            op_values.append(float(raw_value.strip()))
                        except ValueError:
                            pass  # Invalid float, skip
                    else:
                        op_values.append(raw_value.strip())
                elif isinstance(raw_value, (int, float)):
                    op_values.append(raw_value)

            # 4. Output formatting
            if op_values:
                seq = CommentedSeq(op_values)
                seq.fa.set_block_style()
                for i in range(len(seq)):
                    if isinstance(seq[i], float) and seq[i].is_integer():
                        seq[i] = float(f"{seq[i]:.1f}")
                operations[op] = seq

        # metadata_backup
        backup = {}
        path_key = f"{library_type}-library_{lib_id}-attribute_metadata_backup_path"
        exclude_key = f"{library_type}-library_{lib_id}-attribute_metadata_backup_exclude"
        sync_key = f"{library_type}-library_{lib_id}-attribute_sync_tags"
        blank_key = f"{library_type}-library_{lib_id}-attribute_add_blank_entries"

        if attr_group.get(path_key):
            backup["path"] = attr_group.get(path_key)
        if attr_group.get(exclude_key):
            val = attr_group.get(exclude_key)
            try:
                parsed = json.loads(val) if isinstance(val, str) else val
                if isinstance(parsed, list):
                    backup["exclude"] = parsed
            except Exception as e:
                print(f"[DEBUG] Skipping invalid exclude value: {val} — {e}")
        if attr_group.get(sync_key) is True:
            backup["sync_tags"] = True
        if attr_group.get(blank_key) is True:
            backup["add_blank_entries"] = True

        if backup:
            operations["metadata_backup"] = backup

        # mass_poster_update
        poster = {}
        for key in [
            "seasons",
            "episodes",
            "ignore_locked",
            "ignore_overlays",
            "source",
        ]:
            full_key = f"{library_type}-library_{lib_id}-attribute_mass_poster_{key}"
            val = attr_group.get(full_key)
            if val not in [None, False, ""]:
                poster[key] = val
        if poster:
            operations["mass_poster_update"] = poster

        # mass_background_update
        background = {}
        for key in ["seasons", "episodes", "ignore_locked", "source"]:
            full_key = f"{library_type}-library_{lib_id}-attribute_mass_background_{key}"
            val = attr_group.get(full_key)
            if val not in [None, False, ""]:
                background[key] = val
        if background:
            operations["mass_background_update"] = background

        # Remove/Reset Overlays
        top_group = top_level.get(lib_id, {})

        remove_key = f"{library_type}-library_{lib_id}-top_level_remove_overlays"
        reset_key = f"{library_type}-library_{lib_id}-top_level_reset_overlays"

        remove_overlays = top_group.get(remove_key)
        reset_overlays = top_group.get(reset_key)

        if app.config["QS_DEBUG"]:
            print(f"[DEBUG] Top Level for {lib_id}: {top_group}")
            print(f"[DEBUG] {remove_key} = {remove_overlays}")
            print(f"[DEBUG] {reset_key} = {reset_overlays}")

        if remove_overlays:
            entry["remove_overlays"] = True
        if reset_overlays not in [None, "None", ""]:
            entry["reset_overlays"] = reset_overlays

        if operations:
            entry["operations"] = operations

        if app.config["QS_DEBUG"]:
            print(f"[DEBUG] Entry for {library_name}: {entry}")

        libraries_section[library_name] = reorder_library_section(entry)

    #############################################################################################

    # Process movie libraries
    for lk, ln in movie_libraries.items():
        add_entry(
            lk,
            ln,
            "mov",
            movie_collections,
            movie_overlays,
            movie_attributes,
            movie_templates,
            movie_top_level,
        )

    # Process show libraries
    for lk, ln in show_libraries.items():
        add_entry(
            lk,
            ln,
            "sho",
            show_collections,
            show_overlays,
            show_attributes,
            show_templates,
            show_top_level,
        )

    if app.config["QS_DEBUG"]:
        print("[DEBUG] Generated YAML Output:\n")
        buf = io.BytesIO()
        YAML().dump({"libraries": libraries_section}, buf)
        print(buf.getvalue().decode("utf-8"))

    return {"libraries": libraries_section}


def reorder_library_section(library_data):
    """
    Reorders library data so that:
    - `template_variables` appears right after the library name.
    - `remove_overlays` and `reset_overlays` come next.
    - Keys inside `operations` are ordered as per Kometa Wiki.
    - Other keys retain their natural order.
    """
    reordered_data = {}

    # Ensure remove/reset overlays come first
    if "remove_overlays" in library_data:
        reordered_data["remove_overlays"] = library_data["remove_overlays"]
    if "reset_overlays" in library_data:
        reordered_data["reset_overlays"] = library_data["reset_overlays"]

    # Ensure template_variables is placed second (if it exists)
    if "template_variables" in library_data:
        reordered_data["template_variables"] = library_data["template_variables"]

    # Reorder operations per official Kometa Wiki order
    operations_order = [
        "assets_for_all",
        "delete_collections",
        "mass_genre_update",
        "mass_content_rating_update",
        "mass_original_title_update",
        "mass_studio_update",
        "mass_originally_available_update",
        "mass_added_at_update",
        "mass_audience_rating_update",
        "mass_critic_rating_update",
        "mass_user_rating_update",
        "mass_episode_audience_rating_update",
        "mass_episode_critic_rating_update",
        "mass_episode_user_rating_update",
        "mass_poster_update",
        "mass_background_update",
        "mass_imdb_parental_labels",
        "mass_collection_mode",
        "update_blank_track_titles",
        "remove_title_parentheses",
        "split_duplicates",
        "radarr_add_all",
        "radarr_remove_by_tag",
        "sonarr_add_all",
        "sonarr_remove_by_tag",
        "genre_mapper",
        "content_rating_mapper",
        "metadata_backup",
    ]

    if "operations" in library_data:
        ordered_ops = {}
        ops = library_data["operations"]
        for key in operations_order:
            if key in ops:
                ordered_ops[key] = ops[key]
        # Include any unknown keys at the end
        for k, v in ops.items():
            if k not in ordered_ops:
                ordered_ops[k] = v
        reordered_data["operations"] = ordered_ops

    # Finally, add remaining keys (e.g., collection_files, overlay_files)
    for key, value in library_data.items():
        if key not in reordered_data:
            reordered_data[key] = value

    return reordered_data


def build_config(header_style="standard", config_name=None):
    """
    Build the final configuration, including all sections and headers,
    ensuring the libraries section is properly processed.
    """
    sections = helpers.get_template_list()
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
        elif header_style == "single line":  # Standardizes "single line" as divider format
            header_art[config_attribute] = "#==================== " + item["name"] + " ====================#"
        else:
            # Handle custom PyFiglet fonts dynamically (including "standard")
            try:
                figlet_text = pyfiglet.figlet_format(item["name"], font=header_style)
                header_art[config_attribute] = add_border_to_ascii_art(figlet_text)
            except pyfiglet.FontNotFound:
                # Fallback to "single line" divider format instead of basic text
                header_art[config_attribute] = "#==================== " + item["name"] + " ====================#"

        # Retrieve settings for each section
        section_data = persistence.retrieve_settings(persistence_key)

        if "validated" in section_data and section_data["validated"]:
            config_data[config_attribute] = clean_section_data(section_data, config_attribute)

    # Process playlist_files section
    if "playlist_files" in config_data:
        playlist_data = config_data["playlist_files"]

        # Debug raw data
        if app.config["QS_DEBUG"]:
            print(f"[DEBUG] Raw config_data['playlist_files'] content (Level 1): {playlist_data}")

        # Adjust for possible extra nesting
        if "playlist_files" in playlist_data and isinstance(playlist_data["playlist_files"], dict):
            playlist_data = playlist_data["playlist_files"]
            if app.config["QS_DEBUG"]:
                print(f"[DEBUG] Adjusted playlist_data after extra nesting: {playlist_data}")

        # Extract and process libraries
        libraries_value = playlist_data.get("libraries", "")
        if app.config["QS_DEBUG"]:
            print(f"[DEBUG] Extracted libraries value: {libraries_value}")

        libraries_list = [lib.strip() for lib in libraries_value.split(",") if lib.strip()]
        if app.config["QS_DEBUG"]:
            print(f"[DEBUG] Processed libraries list: {libraries_value}")

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
            webhooks_data = webhooks_data["webhooks"]  # Fix: Handle extra nesting

        # Remove empty values
        cleaned_webhooks = {key: value for key, value in webhooks_data.items() if value is not None and value != "" and value != [] and value != {}}

        # If no valid webhooks exist, remove the "webhooks" section entirely
        if cleaned_webhooks:
            config_data["webhooks"] = {"webhooks": cleaned_webhooks}  # Preserve webhooks key
        else:
            config_data.pop("webhooks", None)  # 🚀 Fully remove empty webhooks

        # 🔍 Debugging: Ensure webhooks are correctly cleaned
        if app.config["QS_DEBUG"]:
            print(f"[DEBUG] Cleaned Webhooks Data AFTER Removing Empty Values: {cleaned_webhooks}")
            if "webhooks" not in config_data:
                print("[DEBUG] Webhooks section completely removed.")

    # Process the libraries section
    if "libraries" in config_data and "libraries" in config_data["libraries"]:
        nested_libraries_data = config_data["libraries"]["libraries"]

        # Debugging
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Raw nested libraries data:", nested_libraries_data)

        # Extract selected libraries
        movie_libraries = {key: value for key, value in nested_libraries_data.items() if key.startswith("mov-library_") and key.endswith("-library")}
        show_libraries = {key: value for key, value in nested_libraries_data.items() if key.startswith("sho-library_") and key.endswith("-library")}

        # Extract **correct** movie and show library names
        movie_library_names = {helpers.extract_library_name(k) for k in movie_libraries}
        show_library_names = {helpers.extract_library_name(k) for k in show_libraries}

        # Debugging
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Movie Library Names:", movie_library_names)
            print("[DEBUG] Show Library Names:", show_library_names)

        def group_by_library(prefix, names):
            """
            Groups collection, overlay, and attribute data by library.
            """
            grouped = {}
            for key, value in [(k, v) for k, v in nested_libraries_data.items() if prefix in k and helpers.extract_library_name(k) in names]:
                library_name = helpers.extract_library_name(key)
                if library_name:
                    if library_name not in grouped:
                        grouped[library_name] = {}
                    grouped[library_name][key] = value
            return grouped

        # Group collections, overlays, attributes, and templates only for selected libraries
        movie_collections = group_by_library("collection_", movie_library_names)
        show_collections = group_by_library("collection_", show_library_names)
        movie_overlays = group_by_library("overlay_", movie_library_names)
        show_overlays = group_by_library("overlay_", show_library_names)
        movie_attributes = group_by_library("attribute_", movie_library_names)
        show_attributes = group_by_library("attribute_", show_library_names)
        movie_templates = group_by_library("template_variables", movie_library_names)
        show_templates = group_by_library("template_variables", show_library_names)
        movie_top_level = group_by_library("top_level_", movie_library_names)
        show_top_level = group_by_library("top_level_", show_library_names)

        # Debugging
        if app.config["QS_DEBUG"]:
            print(f"[DEBUG] Extracted Movie Libraries: {movie_libraries}")
            print(f"[DEBUG] Extracted Show Libraries: {show_libraries}")
            print(f"[DEBUG] Extracted Movie Collections: {movie_collections}")
            print(f"[DEBUG] Extracted Show Collections: {show_collections}")
            print(f"[DEBUG] Extracted Movie Overlays: {movie_overlays}")
            print(f"[DEBUG] Extracted Show Overlays: {show_overlays}")
            print(f"[DEBUG] Extracted Movie Attributes: {movie_attributes}")
            print(f"[DEBUG] Extracted Show Attributes: {show_attributes}")
            print(f"[DEBUG] Extracted Movie Templates: {movie_templates}")
            print(f"[DEBUG] Extracted Show Templates: {show_templates}")
            print(f"[DEBUG] Extracted Movie Top Level: {movie_top_level}")
            print(f"[DEBUG] Extracted Show Top Level: {show_top_level}")

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
            movie_templates,
            show_templates,
            movie_top_level,
            show_top_level,
        )
        config_data["libraries"] = libraries_section
        if app.config["QS_DEBUG"]:
            print(f"[DEBUG] Final Libraries Section: {libraries_section}")

    # Header comment for YAML file
    header_comment = (
        "### We highly recommend using Visual Studio Code with indent-rainbow by oderwat extension "
        "and YAML by Red Hat extension. VSC will also leverage the above link to enhance Kometa yml edits."
    )

    # Build YAML content
    yaml = YAML(typ="safe", pure=True)
    yaml.default_flow_style = False
    yaml.sort_keys = False

    helpers.ensure_json_schema()

    with open(os.path.join(helpers.JSON_SCHEMA_DIR, "config-schema.json"), "r") as file:
        schema = yaml.load(file)

    # Fetch kometa_branch dynamically
    version_info = helpers.check_for_update()
    kometa_branch = version_info.get("kometa_branch", "nightly")  # Default to nightly if not found

    # Get the current timestamp in a readable format
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    yaml_content = (
        f"# yaml-language-server: $schema=https://raw.githubusercontent.com/Kometa-Team/Kometa/{kometa_branch}/json-schema/config-schema.json\n\n"
        f"{add_border_to_ascii_art(section_heading('KOMETA', font=header_style)) if header_style not in ['none', 'single line'] else section_heading('KOMETA', font=header_style)}\n\n"
        f"# {config_name} config created by Quickstart on {timestamp}\n\n"
        f"{header_comment}\n\n"
    )

    # Function to dump YAML sections
    def dump_section(title, dump_name, data):

        dump_yaml = YAML()
        dump_yaml.default_flow_style = False
        dump_yaml.sort_keys = False  # Preserve original key order

        # Custom representation for `None` values
        dump_yaml.representer.add_representer(
            type(None),
            lambda self, _: self.represent_scalar("tag:yaml.org,2002:null", ""),
        )

        def clean_data(obj):
            if isinstance(obj, dict):
                # Sort specific sections alphabetically
                if dump_name in [
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
                    obj = dict(sorted(obj.items()))  # Alphabetically sort keys in the section
                return {k: clean_data(v) for k, v in obj.items() if k != "valid"}
            elif isinstance(obj, list):
                return [clean_data(v) for v in obj]
            else:
                return obj

        # Clean the data
        cleaned_data = clean_data(data)

        # Ensure `asset_directory` is serialized as a proper YAML list
        if dump_name == "settings" and "asset_directory" in cleaned_data.get("settings", {}):
            if isinstance(cleaned_data["settings"]["asset_directory"], str):
                # Convert multi-line string into a list
                cleaned_data["settings"]["asset_directory"] = [line.strip() for line in cleaned_data["settings"]["asset_directory"].splitlines() if line.strip()]
            elif isinstance(cleaned_data["settings"]["asset_directory"], list):
                # Ensure all list items are strings
                cleaned_data["settings"]["asset_directory"] = [str(i).strip() for i in cleaned_data["settings"]["asset_directory"]]

        # Dump the cleaned data to YAML
        with io.StringIO() as stream:
            dump_yaml.dump(cleaned_data, stream)
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
        authorization_data.pop("code_verifier", None)  # Remove safely

    # Apply enforce_string_fields to ensure proper formatting
    config_data = helpers.enforce_string_fields(config_data, helpers.STRING_FIELDS)

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
