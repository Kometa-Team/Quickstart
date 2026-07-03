import copy
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
from modules.output_libraries_data import extract_libraries_bundle
from modules.output_libraries_section import build_libraries_section  # noqa: F401 -- re-exported so tests calling output.build_libraries_section keep working
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
    apply_playlist_libraries_toggle,
)
from modules.output_postprocess import (  # noqa: F401 -- re-exported so output.<name> keeps working
    _rewrite_custom_font_paths,
    clean_section_data,
)
from modules.output_render import ORDERED_CONFIG_SECTIONS, apply_final_transformations
from modules.output_reorder import reorder_library_section  # noqa: F401 -- re-exported so tests calling output.reorder_library_section keep working
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
    library_types = {}

    # Process the libraries section
    if "libraries" in config_data and "libraries" in config_data["libraries"]:
        nested_libraries_data = config_data["libraries"]["libraries"]

        if app.config["QS_DEBUG"]:
            helpers.ts_log("Raw nested libraries data:", nested_libraries_data, level="DEBUG")

        bundle = extract_libraries_bundle(nested_libraries_data, debug=app.config["QS_DEBUG"])
        movie_libraries = bundle.movie_libraries
        show_libraries = bundle.show_libraries
        library_types = bundle.library_types

        # Build nested libraries structure
        libraries_section = build_libraries_section(
            movie_libraries=movie_libraries,
            show_libraries=show_libraries,
            movie_collections=bundle.movie_groups["collections"],
            show_collections=bundle.show_groups["collections"],
            movie_collection_files=bundle.movie_groups["collection_files"],
            show_collection_files=bundle.show_groups["collection_files"],
            movie_overlays=bundle.movie_groups["overlays"],
            show_overlays=bundle.show_groups["overlays"],
            movie_attributes=bundle.movie_groups["attributes"],
            show_attributes=bundle.show_groups["attributes"],
            movie_metadata_files=bundle.movie_groups["metadata_files"],
            show_metadata_files=bundle.show_groups["metadata_files"],
            movie_templates=bundle.movie_groups["templates"],
            show_templates=bundle.show_groups["templates"],
            movie_top_level=bundle.movie_groups["top_level"],
            show_top_level=bundle.show_groups["top_level"],
        )
        config_data["libraries"] = libraries_section.get("libraries", {}) if isinstance(libraries_section, dict) else {}
        apply_playlist_libraries_toggle(config_data, nested_libraries_data, libraries_section)
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

    optimize_defaults = helpers.booler(app.config.get("QS_OPTIMIZE_DEFAULTS", True))
    config_data = apply_final_transformations(config_data, library_types, optimize_defaults=optimize_defaults)

    for section_key, section_stem in ORDERED_CONFIG_SECTIONS:
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
