import jsonschema  # noqa: F401 -- re-exported so tests monkeypatching output.jsonschema.Draft7Validator keep working
from flask import current_app as app, has_request_context, session

from modules import helpers  # noqa: F401 -- re-exported so tests monkeypatching output.helpers.<name> keep working
from modules import persistence  # noqa: F401 -- re-exported so tests monkeypatching output.persistence.retrieve_settings keep working
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
from modules.output_file_entries import (  # noqa: F401 -- re-exported so output.<name> keeps working
    _parse_collection_file_block_entries,
    _parse_metadata_file_entries,
    _parse_overlay_file_block_entries,
)
from modules.output_headers import (  # noqa: F401 -- re-exported so output.<name> and public callers keep working
    render_section_header,
    section_heading,
)
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
from modules.output_render import emit_and_validate_config, process_libraries_block, retrieve_config_sections
from modules.output_reorder import reorder_library_section  # noqa: F401 -- re-exported so tests calling output.reorder_library_section keep working
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


def build_config(header_style="standard", config_name=None):
    """
    Build the final configuration, including all sections and headers,
    ensuring the libraries section is properly processed.
    """
    if not config_name and has_request_context():
        config_name = session.get("config_name")

    config_data, header_art = retrieve_config_sections(header_style)

    normalize_playlist_files_section(config_data, debug=app.config["QS_DEBUG"])
    normalize_webhooks_section(config_data, debug=app.config["QS_DEBUG"])
    normalize_apprise_section(config_data)

    movie_libraries, show_libraries, library_types = process_libraries_block(config_data, debug=app.config["QS_DEBUG"])

    return emit_and_validate_config(
        config_data,
        header_art,
        header_style,
        config_name,
        library_types,
        movie_libraries,
        show_libraries,
    )
