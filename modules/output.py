import copy
import io
import os

import jsonschema
from flask import current_app as app, has_request_context, session
from ruamel.yaml import YAML

from modules import helpers, persistence
from modules.output_collections import (  # noqa: F401 -- re-exported so output.<name> keeps working
    FRANCHISE_DYNAMIC_CHILD_FIELD_SPECS,
    _collapse_collection_data_template_vars,
    _expand_franchise_dynamic_child_overrides,
    _normalize_collection_template_var_value,
    _normalize_dynamic_child_override_value,
    _normalize_legacy_collection_template_vars,
    _normalize_settings_section_value,
    _parse_tmdb_person_window,
    build_collection_files,
)
from modules.output_config_sections import (
    normalize_apprise_section,
    normalize_playlist_files_section,
    normalize_webhooks_section,
)
from modules.output_defaults import (  # noqa: F401 -- re-exported so output.<name> keeps working
    _build_attribute_defaults,
    _build_collection_defaults,
    _build_overlay_defaults,
    _default_from_var,
    _extract_offset_defaults,
    _extract_template_defaults,
    _infer_default_from_options,
    _prune_template_variables,
    _values_match,
)
from modules.output_dump import dump_section
from modules.output_file_entries import (  # noqa: F401 -- re-exported so output.<name> keeps working
    _parse_collection_file_block_entries,
    _parse_metadata_file_entries,
    _parse_overlay_file_block_entries,
)
from modules.output_headers import (  # noqa: F401 -- re-exported so output.<name> and public callers keep working
    render_section_header,
    section_heading,
)
from modules.output_library_ops import (
    build_delete_collections_operation,
    build_grouped_mass_update_operations,
    build_library_operations,
    build_library_settings,
    build_mapper_operations,
    build_mass_background_update_operation,
    build_mass_genre_update_operation,
    build_mass_poster_update_operation,
    build_metadata_backup_operation,
    build_service_overrides,
    build_template_variables,
    build_top_level_fields,
)
from modules.output_grouping import group_movie_and_show_libraries
from modules.output_optimize import optimize_template_variables
from modules.output_overlay_builder import build_overlay_files_for_library
from modules.output_playlists import (  # noqa: F401 -- re-exported so output.<name> keeps working
    PLAYLIST_KEYED_TEMPLATE_VAR_SPECS,
    PLAYLIST_SHARED_TEMPLATE_VAR_SPECS,
    _collect_playlist_file_entries_from_libraries_data,
    _collect_playlist_template_variables_from_libraries_data,
    _format_playlist_file_entries,
    _legacy_playlist_libraries_for_selected_libraries,
    _legacy_playlist_libraries_from_settings,
    _library_names_in_output_order,
    _normalize_playlist_file_entry_for_output,
    _normalize_playlist_keyed_template_var_value,
    _normalize_playlist_template_var_value,
    _ordered_selected_libraries,
    _parse_playlist_file_entries_value,
    _playlist_libraries_from_library_toggles,
)
from modules.output_postprocess import (  # noqa: F401 -- re-exported so output.<name> keeps working
    _rewrite_custom_font_paths,
    clean_section_data,
)
from modules.output_reorder import reorder_library_section  # public API used by tests as output.reorder_library_section
from modules.output_yaml_header import render_yaml_header
from modules.output_values import (  # noqa: F401 -- re-exported for tests calling output._parse_string_list, etc.
    _coerce_bool,
    _coerce_string_list,
    _normalize_asset_directory_entry,
    _normalize_asset_directory_values,
    _normalize_template_value,
    _parse_comma_string_list,
    _parse_string_list,
    _parse_string_list_mapping,
    _parse_string_mapping,
    _parse_template_mapping_dict,
    _playlist_scalar_or_list,
    _to_number,
)

_EMPTY_OUTPUT = object()


def build_libraries_section(
    movie_libraries,
    show_libraries,
    movie_collections,
    show_collections,
    movie_collection_files,
    show_collection_files,
    movie_overlays,
    show_overlays,
    movie_attributes,
    show_attributes,
    movie_metadata_files,
    show_metadata_files,
    movie_templates,
    show_templates,
    movie_top_level,
    show_top_level,
):
    libraries_section = {}

    def sorted_library_items(libraries):
        """Return deterministic library ordering by display name, then key."""
        if not isinstance(libraries, dict):
            return []
        return sorted(
            libraries.items(),
            key=lambda item: (str(item[1]).casefold(), str(item[0]).casefold()),
        )

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
            helpers.ts_log(f"Processing Library: {library_key} -> {library_name}", level="DEBUG")

        # Process Library Settings and Operations Attributes
        operations = {}
        attr_group = attributes.get(lib_id, {})
        library_settings = build_library_settings(attr_group, library_type, lib_id)
        operations.update(build_library_operations(attr_group, library_type, lib_id))
        service_name, service_overrides = build_service_overrides(attr_group, library_type, lib_id)

        # Begin: Mass Genre Update Section
        mass_genre_update = build_mass_genre_update_operation(attr_group, library_type, lib_id)
        if mass_genre_update:
            operations["mass_genre_update"] = mass_genre_update

        # Handle nested delete_collections block
        delete_collections = build_delete_collections_operation(attr_group, library_type, lib_id)
        if delete_collections:
            operations["delete_collections"] = delete_collections

        if library_settings:
            entry["settings"] = library_settings

        if service_overrides:
            entry[service_name] = service_overrides

        if operations:
            entry["operations"] = operations

        # Process Collections
        collection_files, has_collectionless = build_collection_files(
            library_key,
            library_type,
            collections,
            templates,
            movie_collection_files,
            show_collection_files,
            debug=app.config["QS_DEBUG"],
        )
        if collection_files:
            entry["collection_files"] = collection_files

        collection_key = helpers.extract_library_name(library_key)
        if collection_key:
            overlay_files = build_overlay_files_for_library(library_key, library_type, overlays)
            if overlay_files:
                entry["overlay_files"] = overlay_files

        metadata_group = (
            movie_metadata_files.get(helpers.extract_library_name(library_key), {})
            if library_type == "mov"
            else show_metadata_files.get(helpers.extract_library_name(library_key), {})
        )
        library_prefix = helpers.strip_library_suffix(library_key)
        metadata_entries = _parse_metadata_file_entries(metadata_group.get(f"{library_prefix}-metadata_files"))
        if metadata_entries:
            entry["metadata_files"] = metadata_entries

        # Template Variables
        entry["template_variables"] = build_template_variables(templates, library_type, library_key, has_collectionless)

        # Grouped mass update operations (excluding mass_genre_update, handled earlier)
        operations.update(build_grouped_mass_update_operations(attr_group, library_type, lib_id))

        # genre_mapper and content_rating_mapper
        operations.update(build_mapper_operations(attr_group, library_type, lib_id))

        # metadata_backup
        backup = build_metadata_backup_operation(attr_group, library_type, lib_id)
        if backup:
            operations["metadata_backup"] = backup

        # mass_poster_update
        poster = build_mass_poster_update_operation(attr_group, library_type, lib_id)
        if poster:
            operations["mass_poster_update"] = poster

        # mass_background_update
        background = build_mass_background_update_operation(attr_group, library_type, lib_id)
        if background:
            operations["mass_background_update"] = background

        # Remove/Reset Overlays + other top-level fields
        top_group = top_level.get(lib_id, {})
        entry.update(build_top_level_fields(top_group, library_type, lib_id))

        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Top Level for {lib_id}: {top_group}", level="DEBUG")

        if operations:
            entry["operations"] = operations

        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Entry for {library_name}: {entry}", level="DEBUG")

        libraries_section[library_name] = reorder_library_section(entry)

    #############################################################################################

    # Process movie libraries (A->Z by display name, deterministic on key ties)
    for lk, ln in sorted_library_items(movie_libraries):
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

    # Process show libraries (A->Z by display name, deterministic on key ties)
    for lk, ln in sorted_library_items(show_libraries):
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
        helpers.ts_log("Generated YAML Output:\n", level="DEBUG")
        buf = io.BytesIO()
        YAML().dump({"libraries": libraries_section}, buf)
        helpers.ts_log(buf.getvalue().decode("utf-8"))

    return {"libraries": libraries_section}


def build_config(header_style="standard", config_name=None):
    """
    Build the final configuration, including all sections and headers,
    ensuring the libraries section is properly processed.
    """
    if not config_name and has_request_context():
        config_name = session.get("config_name")

    sections = helpers.get_template_list()
    config_data = {}
    header_art = {}
    library_types = {}

    def header_for_section(section_key, display_name):
        if section_key in header_art:
            return header_art[section_key]
        return render_section_header(display_name, header_style)

    # Process sections and generate header art
    for name in sections:
        item = sections[name]
        persistence_key = item["stem"]
        config_attribute = item["raw_name"]

        # Handle all header styles
        header_art[config_attribute] = render_section_header(item["name"], header_style)

        # Retrieve settings for each section.
        # Deep-copy here so YAML normalization cannot mutate the in-memory
        # structure returned from persistence for this request lifecycle.
        section_data = copy.deepcopy(persistence.retrieve_settings(persistence_key))

        if "validated" in section_data and section_data["validated"]:
            config_data[config_attribute] = clean_section_data(section_data, config_attribute)

    normalize_playlist_files_section(config_data, debug=app.config["QS_DEBUG"])
    normalize_webhooks_section(config_data, debug=app.config["QS_DEBUG"])
    normalize_apprise_section(config_data)

    # Initialize movie and show libraries
    movie_libraries = {}
    show_libraries = {}

    # Process the libraries section
    if "libraries" in config_data and "libraries" in config_data["libraries"]:
        nested_libraries_data = config_data["libraries"]["libraries"]

        # Debugging
        if app.config["QS_DEBUG"]:
            helpers.ts_log("Raw nested libraries data:", nested_libraries_data, level="DEBUG")

        # Extract selected libraries
        movie_libraries = {
            key: value
            for key, value in nested_libraries_data.items()
            if key and isinstance(key, str) and key.startswith("mov-library_") and key.endswith("-library") and value not in [None, "", False]
        }
        show_libraries = {
            key: value
            for key, value in nested_libraries_data.items()
            if key and isinstance(key, str) and key.startswith("sho-library_") and key.endswith("-library") and value not in [None, "", False]
        }

        # Extract **correct** movie and show library names
        movie_library_names = {helpers.extract_library_name(k) for k in movie_libraries}
        show_library_names = {helpers.extract_library_name(k) for k in show_libraries}
        library_types = {name: "movie" for name in movie_libraries.values()}
        library_types.update({name: "show" for name in show_libraries.values()})

        # Debugging
        if app.config["QS_DEBUG"]:
            helpers.ts_log("Movie Library Names:", movie_library_names, level="DEBUG")
            helpers.ts_log("Show Library Names:", show_library_names, level="DEBUG")

        movie_groups, show_groups = group_movie_and_show_libraries(nested_libraries_data, movie_library_names, show_library_names)
        movie_collections = movie_groups["collections"]
        show_collections = show_groups["collections"]
        movie_collection_files = movie_groups["collection_files"]
        show_collection_files = show_groups["collection_files"]
        movie_overlay_file_blocks = movie_groups["overlay_file_blocks"]
        show_overlay_file_blocks = show_groups["overlay_file_blocks"]
        movie_overlays = movie_groups["overlays"]
        show_overlays = show_groups["overlays"]
        movie_attributes = movie_groups["attributes"]
        show_attributes = show_groups["attributes"]
        movie_metadata_files = movie_groups["metadata_files"]
        show_metadata_files = show_groups["metadata_files"]
        movie_templates = movie_groups["templates"]
        show_templates = show_groups["templates"]
        movie_top_level = movie_groups["top_level"]
        show_top_level = show_groups["top_level"]

        # Debugging
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Extracted Movie Libraries: {movie_libraries}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Libraries: {show_libraries}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Collections: {movie_collections}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Collections: {show_collections}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Collection Files: {movie_collection_files}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Collection Files: {show_collection_files}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Overlay File Blocks: {movie_overlay_file_blocks}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Overlay File Blocks: {show_overlay_file_blocks}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Overlays: {movie_overlays}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Overlays: {show_overlays}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Attributes: {movie_attributes}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Attributes: {show_attributes}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Metadata Files: {movie_metadata_files}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Metadata Files: {show_metadata_files}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Templates: {movie_templates}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Templates: {show_templates}", level="DEBUG")
            helpers.ts_log(f"Extracted Movie Top Level: {movie_top_level}", level="DEBUG")
            helpers.ts_log(f"Extracted Show Top Level: {show_top_level}", level="DEBUG")

        # Build nested libraries structure
        libraries_section = build_libraries_section(
            movie_libraries,
            show_libraries,
            movie_collections,
            show_collections,
            movie_collection_files,
            show_collection_files,
            movie_overlays,
            show_overlays,
            movie_attributes,
            show_attributes,
            movie_metadata_files,
            show_metadata_files,
            movie_templates,
            show_templates,
            movie_top_level,
            show_top_level,
        )
        config_data["libraries"] = libraries_section.get("libraries", {}) if isinstance(libraries_section, dict) else {}
        ordered_library_names = _library_names_in_output_order(libraries_section)
        has_playlist_toggle, playlist_libraries = _playlist_libraries_from_library_toggles(
            nested_libraries_data,
            ordered_library_names=ordered_library_names,
        )
        playlist_template_variables = _collect_playlist_template_variables_from_libraries_data(nested_libraries_data)
        playlist_file_entries = _collect_playlist_file_entries_from_libraries_data(nested_libraries_data)
        if has_playlist_toggle:
            if playlist_libraries or playlist_file_entries:
                config_data["playlist_files"] = _format_playlist_file_entries(
                    libraries_list=playlist_libraries,
                    template_variables=playlist_template_variables,
                    extra_entries=playlist_file_entries,
                )
            else:
                config_data.pop("playlist_files", None)
        else:
            legacy_playlist_libraries = _legacy_playlist_libraries_for_selected_libraries(
                nested_libraries_data,
                ordered_library_names=ordered_library_names,
            )
            if legacy_playlist_libraries or playlist_file_entries:
                config_data["playlist_files"] = _format_playlist_file_entries(
                    libraries_list=legacy_playlist_libraries,
                    template_variables=playlist_template_variables,
                    extra_entries=playlist_file_entries,
                )
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Final Libraries Section: {libraries_section}", level="DEBUG")

    # Build YAML content
    yaml = YAML(typ="safe", pure=True)
    yaml.default_flow_style = False
    yaml.sort_keys = False

    helpers.ensure_json_schema()

    with open(os.path.join(helpers.JSON_SCHEMA_DIR, "config-schema.json"), "r") as file:
        schema = yaml.load(file)

    # Reuse the shared update snapshot instead of re-checking on every final-page render.
    version_info = app.config.get("VERSION_CHECK") or helpers.check_for_update()

    yaml_content = render_yaml_header(header_style, config_name, movie_libraries, show_libraries, version_info)

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
        ("apprise", "087-apprise"),
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

    config_data = _normalize_legacy_collection_template_vars(config_data)
    optimize_defaults = helpers.booler(app.config.get("QS_OPTIMIZE_DEFAULTS", True))
    if optimize_defaults:
        config_data = optimize_template_variables(config_data, library_types)
    config_data = _collapse_collection_data_template_vars(config_data)

    # Apply enforce_string_fields to ensure proper formatting
    config_data = helpers.enforce_string_fields(config_data, helpers.STRING_FIELDS)
    config_data = _rewrite_custom_font_paths(config_data)

    for section_key, section_stem in ordered_sections:
        if section_key in config_data:
            section_data = config_data[section_key]
            section_art = header_for_section(section_key, helpers.user_visible_name(section_key))
            yaml_content += dump_section(section_art, section_key, section_data, header_style, config_name)

    validated = False
    validation_error = None
    validation_errors = []
    parsed_yaml = yaml.load(yaml_content)
    validator = jsonschema.Draft7Validator(schema)
    validation_errors = sorted(validator.iter_errors(parsed_yaml), key=lambda err: list(err.path))
    if validation_errors:
        validation_error = validation_errors[0]
    else:
        validated = True

    return validated, validation_error, config_data, yaml_content, validation_errors
