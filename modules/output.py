import io
import copy
import os
import shutil
import subprocess
from datetime import datetime
import platform
import psutil

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
    add_border_to_ascii_art,
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
from modules.output_optimize import optimize_template_variables
from modules.output_overlay_builder import build_overlay_entries
from modules.output_overlays import (
    apply_per_overlay_type_cleanup,
    reorder_rating_template_vars,
    sort_overlay_entries,
)
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

            # Process Overlays
            overlay_key = helpers.extract_library_name(library_key)
            overlay_entries = []
            overlay_name_order = []

            if overlay_key and overlay_key in overlays:
                raw_overlay_entries = overlays[overlay_key]
                overlay_entries, overlay_name_order = build_overlay_entries(library_type, overlay_key, raw_overlay_entries)

                # Final cleanup for specific overlays (e.g., drop text for aspect/video_format)
                apply_per_overlay_type_cleanup(overlay_entries)

                if overlay_entries:
                    # Final cleanup: drop rating pairs if either side is empty
                    for ov in overlay_entries:
                        default_name = ov.get("default", "")
                        if not (isinstance(default_name, str) and (default_name == "ratings" or default_name.startswith("overlay_ratings"))):
                            continue
                        tv = ov.get("template_variables")
                        if not isinstance(tv, dict):
                            continue
                        for idx in ["1", "2", "3"]:
                            r_key = f"rating{idx}"
                            i_key = f"{r_key}_image"
                            r_val = tv.get(r_key)
                            i_val = tv.get(i_key)

                            def _is_empty(val):
                                if val is None or val is False:
                                    return True
                                if isinstance(val, dict):
                                    raw_val = val.get("value", "")
                                    return raw_val is None or (isinstance(raw_val, str) and (raw_val.strip() == "" or raw_val.strip().lower() == "none"))
                                if isinstance(val, str):
                                    return val.strip() == "" or val.strip().lower() == "none"
                                return False

                            if _is_empty(r_val):
                                tv.pop(r_key, None)
                                tv.pop(i_key, None)
                                continue
                            if _is_empty(i_val):
                                tv.pop(r_key, None)
                                tv.pop(i_key, None)
                        if not tv:
                            ov.pop("template_variables", None)

                    for ov in overlay_entries:
                        reorder_rating_template_vars(ov)

                    sort_overlay_entries(overlay_entries, overlay_name_order)

                overlay_library_prefix = library_key[: -len("-library")] if isinstance(library_key, str) and library_key.endswith("-library") else library_key
                raw_overlay_file_entries = _parse_overlay_file_block_entries(overlays.get(overlay_key, {}).get(f"{overlay_library_prefix}-overlay_files"))
                if raw_overlay_file_entries:
                    overlay_entries.extend(raw_overlay_file_entries)

                if overlay_entries:
                    entry["overlay_files"] = overlay_entries

        metadata_group = (
            movie_metadata_files.get(helpers.extract_library_name(library_key), {})
            if library_type == "mov"
            else show_metadata_files.get(helpers.extract_library_name(library_key), {})
        )
        library_prefix = library_key[: -len("-library")] if isinstance(library_key, str) and library_key.endswith("-library") else library_key
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

    # Process playlist_files section
    if "playlist_files" in config_data:
        playlist_data = config_data["playlist_files"]

        # Debug raw data
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Raw config_data['playlist_files'] content (Level 1): {playlist_data}", level="DEBUG")

        # Adjust for possible extra nesting
        if "playlist_files" in playlist_data and isinstance(playlist_data["playlist_files"], dict):
            playlist_data = playlist_data["playlist_files"]
            if app.config["QS_DEBUG"]:
                helpers.ts_log(f" playlist_data after extra nesting: {playlist_data}", level="DEBUG")

        # Extract and process libraries
        libraries_value = playlist_data.get("libraries", "")
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Extracted libraries value: {libraries_value}", level="DEBUG")

        if isinstance(libraries_value, list):
            libraries_list = [str(lib).strip() for lib in libraries_value if str(lib).strip()]
        else:
            libraries_list = [lib.strip() for lib in str(libraries_value or "").split(",") if lib.strip()]
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Processed libraries list: {libraries_value}", level="DEBUG")

        playlist_template_variables = {key: value for key, value in playlist_data.items() if key != "libraries" and value not in (None, "", [], {})}

        # Format playlist_files data
        formatted_playlist_files = _format_playlist_file_entries(libraries_list=libraries_list, template_variables=playlist_template_variables)
        if app.config["QS_DEBUG"]:
            helpers.ts_log("Formatted playlist_files data:", formatted_playlist_files, level="DEBUG")

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
            config_data.pop("webhooks", None)  # Fully remove empty webhooks

        # Debugging: Ensure webhooks are correctly cleaned
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Cleaned Webhooks Data AFTER Removing Empty Values: {cleaned_webhooks}", level="DEBUG")
            if "webhooks" not in config_data:
                helpers.ts_log("Webhooks section completely removed.", level="DEBUG")

    if "apprise" in config_data:
        apprise_data = config_data["apprise"]
        apprise_location = None

        if isinstance(apprise_data, dict):
            if "apprise" in apprise_data:
                nested_apprise = apprise_data["apprise"]
                if isinstance(nested_apprise, dict):
                    apprise_location = nested_apprise.get("location")
                else:
                    apprise_location = nested_apprise
            elif "location" in apprise_data:
                apprise_location = apprise_data.get("location")
        elif isinstance(apprise_data, str):
            apprise_location = apprise_data

        apprise_location = str(apprise_location).strip() if apprise_location is not None else ""
        if apprise_location:
            config_data["apprise"] = {"apprise": {"config": apprise_location}}
        else:
            config_data.pop("apprise", None)

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

        def group_by_library(prefix, names, normalize_overlays=False):
            """
            Groups data (collections, overlays, attributes, etc.) by base library name.

            If `normalize_overlays` is True, it strips builder-level suffixes
            (e.g. `tv_shows-show` → `tv_shows`) to match show library names.
            """
            grouped = {}

            def matches_group_prefix(key):
                if not isinstance(key, str):
                    return False
                # Keep library-level *_files blocks isolated from the default
                # collection/overlay groups so they do not suppress built-in
                # defaults during YAML emission.
                if prefix == "collection_":
                    return "-collection_" in key or "-template_collection_" in key
                if prefix == "overlay_":
                    return "-overlay_" in key or "-template_overlay_" in key
                if prefix == "attribute_":
                    return "-attribute_" in key
                if prefix == "template_variables":
                    return "-template_variables" in key or "-attribute_template_variables" in key
                if prefix == "top_level_":
                    return "-top_level_" in key
                if prefix in {"collection_files", "overlay_files", "metadata_files"}:
                    return key.endswith(f"-{prefix}")
                return prefix in key

            for key, value in nested_libraries_data.items():
                if not matches_group_prefix(key):
                    continue

                lib_name_raw = helpers.extract_library_name(key)

                # Normalize overlays by trimming builder-level suffix (movie/show/season/episode),
                # without losing hyphenated library names.
                lib_name = lib_name_raw
                if normalize_overlays and isinstance(lib_name_raw, str):
                    for suffix in ("-movie", "-show", "-season", "-episode"):
                        if lib_name_raw.endswith(suffix):
                            lib_name = lib_name_raw[: -len(suffix)]
                            break

                if lib_name in names:
                    grouped.setdefault(lib_name, {})[key] = value

            return grouped

        # Group collections, overlays, attributes, and templates only for selected libraries
        movie_collections = group_by_library("collection_", movie_library_names)
        show_collections = group_by_library("collection_", show_library_names)
        movie_collection_files = group_by_library("collection_files", movie_library_names)
        show_collection_files = group_by_library("collection_files", show_library_names)
        movie_overlay_file_blocks = group_by_library("overlay_files", movie_library_names)
        show_overlay_file_blocks = group_by_library("overlay_files", show_library_names)
        # movie_overlays = group_by_library("overlay_", movie_library_names)
        # show_overlays = group_by_library("overlay_", show_library_names)
        movie_overlays = group_by_library("overlay_", movie_library_names, normalize_overlays=True)
        show_overlays = group_by_library("overlay_", show_library_names, normalize_overlays=True)
        for lib_name, payload in movie_overlay_file_blocks.items():
            movie_overlays.setdefault(lib_name, {}).update(payload)
        for lib_name, payload in show_overlay_file_blocks.items():
            show_overlays.setdefault(lib_name, {}).update(payload)
        movie_attributes = group_by_library("attribute_", movie_library_names)
        show_attributes = group_by_library("attribute_", show_library_names)
        movie_metadata_files = group_by_library("metadata_files", movie_library_names)
        show_metadata_files = group_by_library("metadata_files", show_library_names)
        movie_templates = group_by_library("template_variables", movie_library_names)
        show_templates = group_by_library("template_variables", show_library_names)
        movie_top_level = group_by_library("top_level_", movie_library_names)
        show_top_level = group_by_library("top_level_", show_library_names)

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

    # Header comment for YAML file
    header_comment = (
        "### \n# We highly recommend using Visual Studio Code with indent-rainbow by oderwat extension "
        "and YAML by Red Hat extension. Visual Studio Code will also leverage the above link (yaml-language-server) to enhance Kometa yml edits.\n###"
    )

    # Build YAML content
    yaml = YAML(typ="safe", pure=True)
    yaml.default_flow_style = False
    yaml.sort_keys = False

    helpers.ensure_json_schema()

    with open(os.path.join(helpers.JSON_SCHEMA_DIR, "config-schema.json"), "r") as file:
        schema = yaml.load(file)

    # Reuse the shared update snapshot instead of re-checking on every final-page render.
    version_info = app.config.get("VERSION_CHECK") or helpers.check_for_update()
    kometa_branch = version_info.get("kometa_branch", "nightly")  # Default to nightly if not found

    # Fetch other Quickstart details
    quickstart_branch = version_info.get("branch", "unknown")
    quickstart_version = version_info.get("local_version", "unknown")
    quickstart_environment = version_info.get("running_on", "unknown")

    system_name = platform.system() or "Unknown OS"
    system_release = platform.release() or ""
    cpu_name = platform.processor() or platform.uname().processor or "Unknown CPU"
    cpu_cores = psutil.cpu_count(logical=True) or 0
    vm = psutil.virtual_memory()
    mem_total = int(vm.total / (1024 * 1024))
    mem_available = int(vm.available / (1024 * 1024))
    mem_used = int((vm.total - vm.available) / (1024 * 1024))
    mem_percent = int(vm.percent)
    is_docker = bool(app.config.get("QUICKSTART_DOCKER")) or "Docker" in str(quickstart_environment)
    python_version = platform.python_version() or platform.python_version_tuple()[0]
    git_version = "Unavailable"
    git_path = shutil.which("git")
    if git_path:
        try:
            git_result = subprocess.run(
                [git_path, "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            git_output = (git_result.stdout or git_result.stderr or "").strip()
            if git_output:
                git_version = git_output
        except Exception:
            git_version = "Unavailable"
    os_line = f"# OS: {system_name} {system_release}".strip()
    browser_line = "Unknown"
    if has_request_context():
        browser_name = session.get("qs_user_agent_browser") or ""
        browser_version = session.get("qs_user_agent_version") or ""
        browser_platform = session.get("qs_user_agent_platform") or ""
        if browser_name:
            browser_line = browser_name
            if browser_version:
                browser_line = f"{browser_line} {browser_version}"
            if browser_platform:
                browser_line = f"{browser_line} ({browser_platform})"
        else:
            browser_line = session.get("qs_user_agent_raw") or session.get("qs_user_agent") or "Unknown"

    # Get the current timestamp in a readable format
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Get plex info
    plex_summary = helpers.get_plex_summary()
    qs_settings_lines = helpers.get_quickstart_settings_summary()
    qs_settings_block = "\n".join(qs_settings_lines) if qs_settings_lines else ""
    movie_summary_names = sorted(
        (str(name).strip() for name in movie_libraries.values() if str(name).strip()),
        key=lambda value: value.casefold(),
    )
    show_summary_names = sorted(
        (str(name).strip() for name in show_libraries.values() if str(name).strip()),
        key=lambda value: value.casefold(),
    )
    library_names = movie_summary_names + show_summary_names
    library_details = helpers.get_library_summaries(library_names)
    schema_header = f"# yaml-language-server: $schema=https://raw.githubusercontent.com/Kometa-Team/Kometa/{kometa_branch}/json-schema/config-schema.json"

    yaml_content = (
        f"{schema_header}\n\n"
        f"{add_border_to_ascii_art(section_heading('KOMETA', font=header_style)) if header_style not in ['none', 'single line'] else section_heading('KOMETA', font=header_style)}\n\n"
        f"#==================== {config_name} ====================#\n"
        f"# {config_name} config created by Quickstart on {timestamp}\n"
        f"# System Information\n"
        f"{os_line}\n"
        f"# Docker: {is_docker}\n"
        f"# CPU: {cpu_name} ({cpu_cores} cores)\n"
        f"# Memory: {mem_used} MB / {mem_total} MB ({mem_percent}%) | {mem_available} MB Free\n"
        f"# Python: {python_version}\n"
        f"# Git: {git_version}\n"
        f"# Browser: {browser_line}\n"
        f"{qs_settings_block}\n"
        f"{'# ' + plex_summary.replace(chr(10), chr(10) + '# ')}\n"
        f"# Quickstart: {quickstart_version} | Branch: {quickstart_branch} | Environment: {quickstart_environment}\n"
        f"###\n"
        f"# Libraries configured with Quickstart: {len(movie_libraries)} movie, {len(show_libraries)} show\n"
        f"{'# ' + library_details.replace(chr(10), chr(10) + '# ')}\n"
        f"{header_comment}\n\n"
        f"# This file is auto-generated by Quickstart. Do not edit manually unless you know what you are doing.\n"
        f"#==================== {config_name} ====================#\n"
        f"\n\n"
    )

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
