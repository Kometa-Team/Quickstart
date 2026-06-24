"""Library-page routes: card fragments, autosave, dependency hints, copy."""

from flask import Blueprint, jsonify, render_template, request, session
from werkzeug.datastructures import MultiDict

import namesgenerator
from modules import database, helpers, path_validation, persistence
from modules.assets import build_preview_image_data as _build_preview_image_data
from modules.dependency_reasons import (
    _is_truthy_setting_value,
    _libraries_data_anidb_dependency_reasons,
    _libraries_data_mal_dependency_reasons,
    _libraries_data_mdblist_dependency_reasons,
    _libraries_data_omdb_dependency_reasons,
    _libraries_data_radarr_dependency_reasons,
    _libraries_data_sonarr_dependency_reasons,
    _libraries_data_tautulli_dependency_reasons,
    _libraries_data_trakt_dependency_reasons,
    _library_prefix_from_key,
)

# A handful of validation/normalization helpers still live in quickstart.py and are
# imported lazily inside the route bodies to avoid a load-order cycle: see route
# bodies for the `import quickstart as _qs` calls.

bp = Blueprint("library_routes", __name__)


# --- top-level imdb items route -------------------------------------------


@bp.route("/get_top_imdb_items/<library_name>")
def get_top_imdb_items_route(library_name):
    media_type = request.args.get("type", "movie")
    placeholder_id = request.args.get("placeholder_id")
    settings = persistence.retrieve_settings("010-plex")
    plex_settings = settings.get("plex", {})

    tmp_key = f"tmp_{media_type}_libraries"
    raw_libraries = plex_settings.get(tmp_key, "")
    library_names = [lib.strip() for lib in raw_libraries.split(",") if lib.strip()]

    helpers.ts_log(f"Searching for library name: {library_name}", level="DEBUG")
    helpers.ts_log(f"Available libraries of type '{media_type}': {library_names}", level="DEBUG")

    if library_name not in library_names:
        return jsonify(
            {
                "status": "error",
                "message": f"Library '{library_name}' not found in Plex settings.",
            }
        )

    # Call with placeholder_id
    items, saved_item = helpers.get_top_imdb_items(library_name, media_type, placeholder_id)

    return jsonify({"status": "success", "items": items, "saved_item": saved_item})


# --- library-list helpers -------------------------------------------------


def _configured_library_ids(library_data):
    """Return set of library IDs that have an active '-library' value saved."""
    if not isinstance(library_data, dict):
        return set()
    return {key.rsplit("-library", 1)[0] for key, value in library_data.items() if key.endswith("-library") and value not in [None, "", False]}


def _build_library_lists():
    """Shared helper to return movie/show library descriptors and telemetry data."""
    all_libraries = persistence.retrieve_settings("010-plex")
    plex_data = all_libraries.get("plex", {})
    telemetry = persistence.retrieve_settings("plex_telemetry")

    telemetry_data = plex_data.get("telemetry")
    if not isinstance(telemetry_data, dict) or "plex_pass" not in telemetry_data:
        telemetry_data = telemetry.get("plex_telemetry", {})

    movie_raw = plex_data.get("tmp_movie_libraries", "") if isinstance(plex_data.get("tmp_movie_libraries"), str) else ""
    show_raw = plex_data.get("tmp_show_libraries", "") if isinstance(plex_data.get("tmp_show_libraries"), str) else ""

    existing_ids = set()

    movie_libraries = [
        {
            "id": f"mov-library_{helpers.normalize_id(lib.strip(), existing_ids)}",
            "name": lib.strip(),
            "type": "movie",
        }
        for lib in movie_raw.split(",")
        if lib.strip()
    ]

    show_libraries = [
        {
            "id": f"sho-library_{helpers.normalize_id(lib.strip(), existing_ids)}",
            "name": lib.strip(),
            "type": "show",
        }
        for lib in show_raw.split(",")
        if lib.strip()
    ]

    return movie_libraries, show_libraries, telemetry_data


def _legacy_playlist_library_names():
    settings = persistence.retrieve_settings("027-playlist_files") or {}
    playlist_payload = settings.get("playlist_files", {}) if isinstance(settings, dict) else {}
    if isinstance(playlist_payload, dict) and isinstance(playlist_payload.get("playlist_files"), dict):
        playlist_payload = playlist_payload.get("playlist_files", {})
    raw_libraries = playlist_payload.get("libraries", "") if isinstance(playlist_payload, dict) else ""
    if isinstance(raw_libraries, list):
        return {str(item).strip() for item in raw_libraries if str(item).strip()}
    return {item.strip() for item in str(raw_libraries or "").split(",") if item.strip()}


def _migrate_legacy_playlist_libraries_to_library_toggles(movie_libraries=None, show_libraries=None):
    legacy_names = _legacy_playlist_library_names()
    if not legacy_names:
        return set()

    settings = persistence.retrieve_settings("025-libraries") or {}
    libraries_data = settings.get("libraries", {}) if isinstance(settings, dict) else {}
    if not isinstance(libraries_data, dict):
        return legacy_names

    if any(isinstance(key, str) and key.endswith("-playlist") for key in libraries_data):
        return set()

    if movie_libraries is None or show_libraries is None:
        movie_libraries, show_libraries, _telemetry = _build_library_lists()

    migrated = {}
    for library in list(movie_libraries or []) + list(show_libraries or []):
        library_id = library.get("id")
        library_name = library.get("name")
        if not library_id or not library_name:
            continue
        if library_name not in legacy_names:
            continue
        if not _is_truthy_setting_value(libraries_data.get(f"{library_id}-library")):
            continue
        migrated[f"{library_id}-playlist"] = "true"

    if not migrated:
        return legacy_names

    updated_libraries = libraries_data.copy()
    updated_libraries.update(migrated)
    settings["libraries"] = updated_libraries
    config_name = session.get("config_name")
    if not config_name:
        return legacy_names
    try:
        database.save_section_data(
            name=config_name,
            section="libraries",
            validated=helpers.booler(settings.get("validated", False)),
            user_entered=True,
            data=settings,
        )
    except Exception as e:
        helpers.ts_log(f"Failed to migrate legacy playlist libraries: {e}", level="ERROR")
        return legacy_names

    return legacy_names


# --- card fragment + autosave ----------------------------------------------


@bp.route("/library_fragment/<library_id>")
def library_fragment(library_id):
    """Return a single library form fragment so we can lazy-load library settings on the page."""
    movie_libraries, show_libraries, telemetry_data = _build_library_lists()
    all_libraries = {lib["id"]: lib for lib in movie_libraries + show_libraries}
    library = all_libraries.get(library_id)

    if not library:
        return jsonify({"error": "Library not found"}), 404

    attribute_config = helpers.load_quickstart_config("quickstart_attributes.json")
    collection_config = helpers.load_quickstart_config("quickstart_collections.json")
    overlay_config = helpers.load_quickstart_overlay_config()

    legacy_playlist_libraries = _migrate_legacy_playlist_libraries_to_library_toggles(movie_libraries, show_libraries)
    data = persistence.retrieve_settings("025-libraries")
    configured_ids = _configured_library_ids(data.get("libraries", {}))

    image_data = _build_preview_image_data()

    page_info = {"telemetry": telemetry_data}

    html = render_template(
        "partials/_library_card.html",
        library=library,
        data=data,
        page_info=page_info,
        attribute_config=attribute_config,
        collection_config=collection_config,
        overlay_config=overlay_config,
        image_data=image_data,
        movie_images=image_data["movie"],
        configured_ids=configured_ids,
        legacy_playlist_libraries=legacy_playlist_libraries,
    )

    return html


@bp.route("/autosave_library/<library_id>", methods=["POST"])
def autosave_library(library_id):
    """Merge-save a single library when switching cards without requiring full navigation submit."""
    # Lazy imports break a load-order cycle: quickstart imports this blueprint at module
    # load, but these helpers haven't finished defining at that point.
    import quickstart as _qs

    try:
        incoming = request.get_json(silent=True) or request.form
        config_name = persistence.resolve_request_config_name(incoming if isinstance(incoming, dict) else {})
        errors = path_validation.validate_payload(incoming)
        if errors:
            return jsonify({"success": False, "error": "Invalid path values.", "errors": errors}), 400
        clean_payload = persistence.clean_form_data(MultiDict(incoming))
        incoming_libraries = helpers.build_config_dict("libraries", clean_payload).get("libraries", {})
        selected_library_ids = _qs._selected_library_ids_from_libraries_data(incoming_libraries)
        collection_errors = _qs._validate_library_collection_files(incoming_libraries, selected_library_ids)
        metadata_errors = _qs._validate_library_metadata_files(incoming_libraries, selected_library_ids)
        overlay_errors = _qs._validate_library_overlay_files(incoming_libraries, selected_library_ids)
        auto_sort_hubs_errors = _qs._validate_library_auto_sort_hubs(incoming_libraries, selected_library_ids)
        if collection_errors:
            return jsonify({"success": False, "error": "Invalid collection files.", "errors": collection_errors}), 400
        if metadata_errors:
            return jsonify({"success": False, "error": "Invalid metadata files.", "errors": metadata_errors}), 400
        if overlay_errors:
            return jsonify({"success": False, "error": "Invalid overlay files.", "errors": overlay_errors}), 400
        if auto_sort_hubs_errors:
            return jsonify({"success": False, "error": "Invalid library settings.", "errors": auto_sort_hubs_errors}), 400
        normalized_libraries, normalization_errors, changed = _qs._normalize_library_file_entries_payload(
            incoming_libraries,
            config_name,
            validate_local=False,
        )
        if normalization_errors:
            return jsonify({"success": False, "error": "Unable to organize library files.", "errors": normalization_errors}), 400
        save_payload = dict(incoming) if isinstance(incoming, dict) else {}
        save_payload.update(normalized_libraries)
        save_payload["config_name"] = config_name
        persistence.save_settings("025-libraries", save_payload)
        return jsonify({"success": True, "normalized": bool(changed), "libraries": normalized_libraries})
    except Exception as e:
        helpers.ts_log(f"Autosave failed for library {library_id}: {e}", level="ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


# --- dependency-hint routes -----------------------------------------------


def _build_merged_libraries_hint_payload(payload):
    source_library_id = str(payload.get("source_library_id") or "").strip()
    source_payload = payload.get("source_payload") if isinstance(payload.get("source_payload"), dict) else {}

    settings = persistence.retrieve_settings("025-libraries")
    libraries_data = settings.get("libraries", {}) if isinstance(settings, dict) else {}
    merged = libraries_data.copy() if isinstance(libraries_data, dict) else {}

    if not source_payload:
        return merged

    clean_payload = persistence.clean_form_data(MultiDict(source_payload))
    incoming_dict = helpers.build_config_dict("libraries", clean_payload).get("libraries", {})
    incoming_dict = incoming_dict if isinstance(incoming_dict, dict) else {}

    prefixes = set()
    if source_library_id:
        source_prefix = source_library_id.split("-card-container")[0] if source_library_id.endswith("-card-container") else source_library_id
        if source_prefix:
            prefixes.add(source_prefix)

    for key in incoming_dict:
        prefix = _library_prefix_from_key(key)
        if prefix:
            prefixes.add(prefix)

    for prefix in prefixes:
        for existing_key in list(merged.keys()):
            if existing_key == f"{prefix}-library" or existing_key.startswith(prefix + "-"):
                merged.pop(existing_key, None)

    for key, value in incoming_dict.items():
        if (key.endswith("-library") or key.endswith("-playlist")) and not _is_truthy_setting_value(value):
            continue
        merged[key] = value

    return merged


def _libraries_dependency_hint_response(payload, resolver):
    merged = _build_merged_libraries_hint_payload(payload)
    reasons = resolver(merged)
    return jsonify({"success": True, "required": bool(reasons), "reasons": reasons})


# 7 dependency-hint endpoints used to be 7 near-identical 9-line copy/paste blocks.
# DRY them up with a registration loop driven by a (label, url-path, resolver) table.
_DEPENDENCY_HINT_ROUTES = (
    ("Tautulli", "tautulli", _libraries_data_tautulli_dependency_reasons),
    ("OMDb", "omdb", _libraries_data_omdb_dependency_reasons),
    ("MDBList", "mdblist", _libraries_data_mdblist_dependency_reasons),
    ("AniDB", "anidb", _libraries_data_anidb_dependency_reasons),
    ("Radarr", "radarr", _libraries_data_radarr_dependency_reasons),
    ("Sonarr", "sonarr", _libraries_data_sonarr_dependency_reasons),
    ("Trakt", "trakt", _libraries_data_trakt_dependency_reasons),
    ("MAL", "mal", _libraries_data_mal_dependency_reasons),
)


def _make_dependency_hint_view(label, resolver):
    """Closure factory so each registered route binds its own label + resolver."""

    def _view():
        try:
            payload = request.get_json(silent=True) or {}
            return _libraries_dependency_hint_response(payload, resolver)
        except Exception as e:
            helpers.ts_log(f"Failed to build {label} dependency hint: {e}", level="ERROR")
            return jsonify({"success": False, "required": False, "reasons": [], "error": str(e)}), 500

    _view.__doc__ = f"Preview {label}-required dependency reasons using current in-page library edits."
    return _view


for _label, _slug, _resolver in _DEPENDENCY_HINT_ROUTES:
    _view_func = _make_dependency_hint_view(_label, _resolver)
    _view_func.__name__ = f"libraries_{_slug}_dependency_hint"
    bp.add_url_rule(
        f"/libraries_{_slug}_dependency_hint",
        endpoint=f"libraries_{_slug}_dependency_hint",
        view_func=_view_func,
        methods=["POST"],
    )


# --- copy library settings -------------------------------------------------


@bp.route("/copy_library_settings", methods=["POST"])
def copy_library_settings():
    """Copy saved settings from one library to multiple targets of the same type."""
    import quickstart as _qs

    try:
        payload = request.get_json(force=True, silent=True) or {}
        source_id = payload.get("source_library_id")
        target_ids = payload.get("target_library_ids") or []
        source_payload = payload.get("source_payload") or {}

        if not source_id or not target_ids:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Missing source or targets (source={source_id}, targets={target_ids})",
                    }
                ),
                400,
            )

        source_prefix = source_id.split("-card-container")[0] if source_id.endswith("-card-container") else source_id
        source_type = source_prefix[:3]  # mov or sho

        if any(not str(t).startswith(source_type) for t in target_ids):
            helpers.ts_log(
                f"Copy aborted: targets must match source type '{source_type}', got targets={target_ids}",
                level="ERROR",
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Targets must match source type '{source_type}'",
                        "targets": target_ids,
                    }
                ),
                400,
            )

        settings = persistence.retrieve_settings("025-libraries")
        libraries_data = settings.get("libraries", {}) if isinstance(settings, dict) else {}

        # If the client sent a fresh payload for the source card, merge it in before copying
        if isinstance(source_payload, dict) and source_payload:
            payload_errors = path_validation.validate_payload(source_payload)
            if payload_errors:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Invalid path values in source payload: " + " ".join(payload_errors),
                            "errors": payload_errors,
                        }
                    ),
                    400,
                )
            try:
                clean_payload = persistence.clean_form_data(MultiDict(source_payload))
                incoming_dict = helpers.build_config_dict("libraries", clean_payload).get("libraries", {})
                normalized_incoming, normalization_errors, _ = _qs._normalize_library_file_entries_payload(
                    incoming_dict,
                    session.get("config_name") or source_payload.get("config_name"),
                    validate_local=False,
                )
                if normalization_errors:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "Unable to organize library files in source payload.",
                                "errors": normalization_errors,
                            }
                        ),
                        400,
                    )
                incoming_dict = normalized_incoming

                merged = libraries_data.copy()

                prefixes = set()
                for key in incoming_dict:
                    prefix = _library_prefix_from_key(key)
                    if prefix:
                        prefixes.add(prefix)

                for prefix in prefixes:
                    for existing_key in list(merged.keys()):
                        if existing_key.startswith(prefix + "-") or existing_key == f"{prefix}-library":
                            merged.pop(existing_key, None)

                for k, v in incoming_dict.items():
                    if k.endswith("-library") and (v in [None, False, ""]):
                        continue
                    merged[k] = v

                libraries_data = merged
                helpers.ts_log(f"Copy request merged live source payload for {source_prefix}: {len(incoming_dict)} fields", level="DEBUG")
            except Exception as merge_err:
                helpers.ts_log(f"Failed to merge live source payload during copy: {merge_err}", level="ERROR")

        source_items = {k: v for k, v in libraries_data.items() if k.startswith(f"{source_prefix}-")}
        source_errors = path_validation.validate_payload(source_items)
        source_collection_errors = _qs._validate_library_collection_files(libraries_data, [source_prefix])
        source_metadata_errors = _qs._validate_library_metadata_files(libraries_data, [source_prefix])
        source_overlay_errors = _qs._validate_library_overlay_files(libraries_data, [source_prefix])
        source_auto_sort_hubs_errors = _qs._validate_library_auto_sort_hubs(libraries_data, [source_prefix])
        if source_errors:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid path values found in source library: " + " ".join(source_errors),
                        "errors": source_errors,
                    }
                ),
                400,
            )
        if source_collection_errors:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid collection files found in source library: " + " ".join(source_collection_errors),
                        "errors": source_collection_errors,
                    }
                ),
                400,
            )
        if source_metadata_errors:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid metadata files found in source library: " + " ".join(source_metadata_errors),
                        "errors": source_metadata_errors,
                    }
                ),
                400,
            )
        if source_overlay_errors:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid overlay files found in source library: " + " ".join(source_overlay_errors),
                        "errors": source_overlay_errors,
                    }
                ),
                400,
            )
        if source_auto_sort_hubs_errors:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid library settings found in source library: " + " ".join(source_auto_sort_hubs_errors),
                        "errors": source_auto_sort_hubs_errors,
                    }
                ),
                400,
            )
        if not source_items:
            helpers.ts_log(f"Copy aborted: no saved settings found for source {source_prefix}", level="ERROR")
            return jsonify({"success": False, "error": "No saved settings found for source library"}), 404

        movie_libraries, show_libraries, _telemetry = _build_library_lists()
        name_map = {lib["id"]: lib["name"] for lib in (movie_libraries + show_libraries)}

        helpers.ts_log(
            f"Copy request for config={session.get('config_name')} source={source_prefix} targets={target_ids} "
            f"source_items={len(source_items)} existing_keys={len(libraries_data)}",
            level="DEBUG",
        )

        filtered_targets = [tid for tid in target_ids if str(tid).startswith(source_type)]
        if len(filtered_targets) != len(target_ids):
            helpers.ts_log(
                f"Copy filtering targets for type '{source_type}': accepted={filtered_targets} dropped={set(target_ids) - set(filtered_targets)}",
                level="WARNING",
            )
        if not filtered_targets:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"No valid target libraries of type '{source_type}' were selected.",
                    }
                ),
                400,
            )

        merged = libraries_data.copy()
        targets_to_process = [source_prefix] + [tid for tid in filtered_targets if tid != source_prefix]
        config_name = session.get("config_name") or source_payload.get("config_name") or namesgenerator.get_random_name()

        for target_id in targets_to_process:
            target_name = name_map.get(target_id, "")
            # Wipe any existing settings for this target before copying fresh
            for existing_key in list(merged.keys()):
                if existing_key.startswith(f"{target_id}-"):
                    merged.pop(existing_key, None)

            for key, value in source_items.items():
                # Do not mirror the include toggle; require explicit include after mirroring
                if target_id != source_prefix and key.endswith("-library"):
                    merged[f"{target_id}-library"] = ""
                    continue
                new_key = key.replace(source_prefix, target_id, 1)
                new_value = value
                if key.endswith("-library"):
                    new_value = target_name or value
                elif target_id != source_prefix:
                    if key.endswith("-metadata_files"):
                        new_value = _qs._clone_library_file_entries_for_target("metadata_files", value, config_name, target_id)
                    elif key.endswith("-collection_files"):
                        new_value = _qs._clone_library_file_entries_for_target("collection_files", value, config_name, target_id)
                    elif key.endswith("-overlay_files"):
                        new_value = _qs._clone_library_file_entries_for_target("overlay_files", value, config_name, target_id)
                merged[new_key] = new_value

        # Update the aggregated libraries list to include all configured library names
        configured_names = []
        for key, val in merged.items():
            if key.endswith("-library") and val not in [None, "", False]:
                configured_names.append(str(val))
        merged["libraries"] = ",".join(sorted(set(configured_names)))

        # Persist directly to the DB to avoid any loss of data during merge
        database.save_section_data(
            name=config_name,
            section="libraries",
            validated=settings.get("validated", False),
            user_entered=True,
            data={"libraries": merged, "validated": settings.get("validated", False)},
        )

        helpers.ts_log(
            f"Copy complete for config={session.get('config_name')} source={source_prefix} targets={target_ids} " f"merged_keys={len(merged)}",
            level="DEBUG",
        )

        return jsonify({"success": True, "updated": target_ids})

    except Exception as e:
        helpers.ts_log(f"Failed to copy library settings: {e}", level="ERROR")
        return jsonify({"success": False, "error": str(e)}), 500
