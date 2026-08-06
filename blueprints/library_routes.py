"""Library-page routes: card fragments, autosave, dependency hints, copy."""

import time

from flask import Blueprint, jsonify, render_template, request, session
from werkzeug.datastructures import MultiDict

import namesgenerator
from modules import database, helpers, path_validation, persistence
from modules.assets import build_preview_image_data as _build_preview_image_data
from modules.dependency_reasons import (
    _is_truthy_setting_value,
    _libraries_data_anidb_dependency_reasons,
    _libraries_data_floppy_dependency_reasons,
    _libraries_data_mal_dependency_reasons,
    _libraries_data_mdblist_dependency_reasons,
    _libraries_data_omdb_dependency_reasons,
    _libraries_data_radarr_dependency_reasons,
    _libraries_data_sonarr_dependency_reasons,
    _libraries_data_tautulli_dependency_reasons,
    _libraries_data_tracearr_dependency_reasons,
    _libraries_data_trakt_dependency_reasons,
    _library_prefix_from_key,
)

# A handful of validation/normalization helpers still live in quickstart.py and are
# imported lazily inside the route bodies to avoid a load-order cycle: see route
# bodies for the `import quickstart as _qs` calls.

bp = Blueprint("library_routes", __name__)

_TOP_PLACEHOLDER_CACHE_TTL_SECONDS = 600
_top_placeholder_cache = {}


# --- top-level imdb items route -------------------------------------------


@bp.route("/get_top_imdb_items/<library_name>")
def get_top_imdb_items_route(library_name):
    media_type = request.args.get("type", "movie")
    placeholder_id = request.args.get("placeholder_id")
    settings = persistence.retrieve_settings("010-plex")
    plex_settings = settings.get("plex", {})

    tmp_key = f"tmp_{media_type}_libraries"
    raw_libraries = plex_settings.get(tmp_key, "")
    library_names = [lib for lib in raw_libraries.split(",") if lib]

    helpers.ts_log(f"Searching for library name: {library_name}", level="DEBUG")
    helpers.ts_log(f"Available libraries of type '{media_type}': {library_names}", level="DEBUG")

    if library_name not in library_names:
        return jsonify(
            {
                "status": "error",
                "message": f"Library '{library_name}' not found in Plex settings.",
            }
        )

    cache_key = (str(media_type or "").strip().lower(), str(library_name or "").strip().lower())
    now = time.time()
    cached = _top_placeholder_cache.get(cache_key)
    if cached and now - cached.get("created", 0) < _TOP_PLACEHOLDER_CACHE_TTL_SECONDS:
        return jsonify(
            {
                "status": "success",
                "items": cached.get("items", []),
                "saved_item": cached.get("saved_item"),
                "cached": True,
            }
        )

    try:
        items, saved_item = helpers.get_top_imdb_items(library_name, media_type, placeholder_id)
    except Exception as e:
        helpers.ts_log(
            f"Separator placeholder top-item lookup failed for library='{library_name}' type='{media_type}': {e}",
            level="ERROR",
        )
        return jsonify(
            {
                "status": "lookup_unavailable",
                "items": [],
                "saved_item": None,
                "message": ("Unable to load top audience-rated Plex items. " "Check Plex connectivity, library metadata, and database health, then try again."),
            }
        )

    _top_placeholder_cache[cache_key] = {
        "created": now,
        "items": items,
        "saved_item": saved_item,
    }

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
            "id": f"mov-library_{helpers.normalize_id(lib, existing_ids)}",
            "name": lib,
            "type": "movie",
        }
        for lib in movie_raw.split(",")
        if lib
    ]

    show_libraries = [
        {
            "id": f"sho-library_{helpers.normalize_id(lib, existing_ids)}",
            "name": lib,
            "type": "show",
        }
        for lib in show_raw.split(",")
        if lib
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


def _library_fragment_context(library_id, *, include_attributes=True, include_collections=True, include_overlays=True):
    movie_libraries, show_libraries, telemetry_data = _build_library_lists()
    all_libraries = {lib["id"]: lib for lib in movie_libraries + show_libraries}
    library = all_libraries.get(library_id)

    if not library:
        return None

    attribute_config = helpers.load_quickstart_config("quickstart_attributes.json") if include_attributes else {}
    lazy_collection_config = helpers.load_quickstart_config("quickstart_collections.json")
    lazy_overlay_config = helpers.load_quickstart_overlay_config()
    collection_config = lazy_collection_config if include_collections else []
    overlay_config = lazy_overlay_config if include_overlays else []

    legacy_playlist_libraries = _migrate_legacy_playlist_libraries_to_library_toggles(movie_libraries, show_libraries)
    data = persistence.retrieve_settings("025-libraries")
    configured_ids = _configured_library_ids(data.get("libraries", {}))

    image_data = _build_preview_image_data() if include_overlays else {}

    page_info = {"telemetry": telemetry_data}

    return {
        "library": library,
        "data": data,
        "page_info": page_info,
        "telemetry": telemetry_data,
        "attribute_config": attribute_config,
        "collection_config": collection_config,
        "overlay_config": overlay_config,
        "image_data": image_data,
        "movie_images": image_data.get("movie", []),
        "configured_ids": configured_ids,
        "legacy_playlist_libraries": legacy_playlist_libraries,
        "lazy_section_override_counts": _lazy_section_override_counts(
            library,
            data.get("libraries", {}),
            telemetry_data,
            collection_config=lazy_collection_config,
            overlay_config=lazy_overlay_config,
        ),
        "lazy_section_active_states": _lazy_section_active_states(
            library,
            data.get("libraries", {}),
            collection_config=lazy_collection_config,
            overlay_config=lazy_overlay_config,
        ),
        "collection_group_override_counts": (
            _collection_group_override_counts_for_library(
                library,
                data.get("libraries", {}),
                collection_config,
                telemetry_data,
            )
            if include_collections
            else {}
        ),
        "collection_group_active_states": (
            _collection_group_active_states_for_library(
                library,
                data.get("libraries", {}),
                collection_config,
            )
            if include_collections
            else {}
        ),
    }


def _coerce_loaded_library_sections(raw_value):
    if isinstance(raw_value, list):
        return {str(item).strip() for item in raw_value if str(item).strip()}
    if isinstance(raw_value, tuple):
        return {str(item).strip() for item in raw_value if str(item).strip()}
    if isinstance(raw_value, str):
        return {item.strip() for item in raw_value.split(",") if item.strip()}
    return set()


def _coerce_loaded_collection_groups(raw_value):
    values = raw_value
    if isinstance(raw_value, str):
        values = raw_value.split(",")
    if not isinstance(values, (list, tuple, set)):
        return set()

    loaded = set()
    for item in values:
        try:
            loaded.add(int(str(item).strip()))
        except (TypeError, ValueError):
            continue
    return loaded


def _loaded_sections_with_payload_evidence(library_id, incoming_libraries, loaded_sections):
    """Ignore lazy-section loaded markers when their form fields are absent.

    A stale/incorrect ``__loaded_sections`` value is dangerous: autosave would
    believe a lazy section was intentionally posted and could replace saved
    collection/overlay selections with an incomplete payload. Raw
    ``*_collection_files`` / ``*_overlay_files`` fields are advanced file-entry
    controls and do not prove the heavy defaults section was loaded.
    """
    loaded_sections = set(loaded_sections or set())
    if not isinstance(incoming_libraries, dict) or not library_id:
        return loaded_sections

    def has_collection_payload():
        collection_files_key = f"{library_id}-collection_files"
        for key in incoming_libraries:
            if not isinstance(key, str) or not key.startswith(f"{library_id}-"):
                continue
            if key == collection_files_key:
                continue
            if f"{library_id}-collection_" in key or f"{library_id}-template_collection_" in key:
                return True
        return False

    def has_overlay_payload():
        overlay_files_key = f"{library_id}-overlay_files"
        overlay_markers = (
            f"{library_id}-overlay_",
            f"{library_id}-movie-overlay_",
            f"{library_id}-show-overlay_",
            f"{library_id}-season-overlay_",
            f"{library_id}-episode-overlay_",
            f"{library_id}-movie-template_overlay_",
            f"{library_id}-show-template_overlay_",
            f"{library_id}-season-template_overlay_",
            f"{library_id}-episode-template_overlay_",
        )
        for key in incoming_libraries:
            if not isinstance(key, str) or not key.startswith(f"{library_id}-"):
                continue
            if key == overlay_files_key:
                continue
            if any(marker in key for marker in overlay_markers):
                return True
        return False

    if "collections" in loaded_sections and not has_collection_payload():
        loaded_sections.discard("collections")
    if "overlays" in loaded_sections and not has_overlay_payload():
        loaded_sections.discard("overlays")
    return loaded_sections


def _has_saved_value(value):
    return value not in [None, "", [], {}, "[]", "{}"]


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _jsonish(value, fallback):
    if isinstance(value, (list, dict)):
        return value
    if value in [None, ""]:
        return fallback
    try:
        import json

        parsed = json.loads(str(value))
        if isinstance(parsed, type(fallback)):
            return parsed
    except Exception:
        return fallback
    return fallback


def _template_value_is_configured(value, default=None, field_type=""):
    field_type = str(field_type or "").strip().lower()
    if value is None:
        return False
    if field_type == "toggle" or isinstance(default, bool) or isinstance(value, bool):
        return _coerce_bool(value) != _coerce_bool(default)
    if field_type in {"string_list", "list"} or isinstance(default, list):
        return _jsonish(value, []) != _jsonish(default, [])
    if field_type in {"mapping_list", "dict", "map"} or isinstance(default, dict):
        return _jsonish(value, {}) != _jsonish(default, {})
    if not _has_saved_value(value):
        return False
    default_value = "" if default is None else str(default).strip()
    value = str(value).strip()
    return value != default_value if default_value else True


def _count_collection_overrides_for_library(library, libraries_data, collection_config):
    if not isinstance(libraries_data, dict):
        return 0
    library_id = library["id"]
    library_type = library["type"]
    count = 0
    for group in collection_config or []:
        for collection in group.get("collections", []):
            if library_type not in collection.get("media_types", []):
                continue
            clean_id = str(collection.get("id", "")).replace("collection_", "")
            for item in collection.get("template_variables", []) or []:
                key = item.get("key") if isinstance(item, dict) else None
                if not key:
                    continue
                media_types = item.get("media_types") or []
                if media_types and library_type not in media_types:
                    continue
                if str(key).startswith("visible_") and not library.get("plex_pass", False):
                    continue
                field_name = f"{library_id}-template_collection_{clean_id}_{key}"
                if _template_value_is_configured(libraries_data.get(field_name), item.get("default"), item.get("type")):
                    count += 1
    return count


def _count_collection_group_overrides_for_library(library, libraries_data, group):
    return _count_collection_overrides_for_library(library, libraries_data, [group] if isinstance(group, dict) else [])


def _collection_group_override_counts_for_library(library, libraries_data, collection_config, telemetry_data=None):
    if not isinstance(collection_config, list):
        return {}
    library_with_plex = dict(library or {})
    telemetry_data = telemetry_data if isinstance(telemetry_data, dict) else {}
    library_with_plex["plex_pass"] = bool(telemetry_data.get("plex_pass"))
    return {index: _count_collection_group_overrides_for_library(library_with_plex, libraries_data, group) for index, group in enumerate(collection_config)}


def _collection_group_has_active_selection_for_library(library, libraries_data, group):
    if not isinstance(libraries_data, dict) or not isinstance(group, dict) or not isinstance(library, dict):
        return False
    library_id = library.get("id")
    library_type = library.get("type")
    if not library_id or not library_type:
        return False
    for collection in group.get("collections", []) or []:
        media_types = collection.get("media_types") or []
        if media_types and library_type not in media_types:
            continue
        collection_id = str(collection.get("id", "")).strip()
        if not collection_id:
            continue
        if _coerce_bool(libraries_data.get(f"{library_id}-{collection_id}")):
            return True
    return False


def _collection_group_active_states_for_library(library, libraries_data, collection_config):
    if not isinstance(collection_config, list):
        return {}
    return {index: _collection_group_has_active_selection_for_library(library, libraries_data, group) for index, group in enumerate(collection_config)}


def _has_active_collection_selection_for_library(library, libraries_data, collection_config):
    return any(_collection_group_active_states_for_library(library, libraries_data, collection_config).values())


def _iter_overlay_template_items(template_variables):
    if isinstance(template_variables, dict):
        for key, details in template_variables.items():
            if isinstance(details, dict):
                yield key, details
    elif isinstance(template_variables, list):
        for item in template_variables:
            if isinstance(item, dict):
                key = item.get("key")
                if key:
                    yield key, item


def _overlay_template_defaults_map(template_variables):
    defaults = {}
    for key, details in _iter_overlay_template_items(template_variables):
        defaults[key] = details.get("default") if isinstance(details, dict) else None
    return defaults


def _meaningful_overlay_value(value):
    if value is None or value is False:
        return False
    if isinstance(value, str):
        stripped = value.strip()
        return bool(stripped) and stripped.lower() != "none"
    return True


def _overlay_template_value(libraries_data, template_name, key, defaults):
    value = libraries_data.get(f"{template_name}[{key}]")
    return value if value is not None else defaults.get(key)


def _rating_axis_positions(axis, position, count):
    safe_count = max(1, min(3, int(count or 1)))
    constants = {
        "edge_inset": 30,
        "center": 0,
        "v2": 235,
        "v3": 440,
        "cv2": 105,
        "cv3": 205,
        "h2": 345,
        "h3": 660,
        "ch2": 160,
        "ch3": 335,
    }
    if axis == "horizontal":
        if position == "center":
            if safe_count == 1:
                return [constants["center"]]
            if safe_count == 2:
                return [-constants["ch2"], constants["ch2"]]
            return [-constants["ch3"], constants["center"], constants["ch3"]]
        if position == "right":
            if safe_count == 1:
                return [-constants["edge_inset"]]
            if safe_count == 2:
                return [-constants["h2"], -constants["edge_inset"]]
            return [-constants["h3"], -constants["h2"], -constants["edge_inset"]]
        if safe_count == 1:
            return [constants["edge_inset"]]
        if safe_count == 2:
            return [constants["edge_inset"], constants["h2"]]
        return [constants["edge_inset"], constants["h2"], constants["h3"]]

    if position == "center":
        if safe_count == 1:
            return [constants["center"]]
        if safe_count == 2:
            return [-constants["cv2"], constants["cv2"]]
        return [-constants["cv3"], constants["center"], constants["cv3"]]
    if position == "bottom":
        if safe_count == 1:
            return [-constants["edge_inset"]]
        if safe_count == 2:
            return [-constants["v2"], -constants["edge_inset"]]
        return [-constants["v3"], -constants["v2"], -constants["edge_inset"]]
    if safe_count == 1:
        return [constants["edge_inset"]]
    if safe_count == 2:
        return [constants["edge_inset"], constants["v2"]]
    return [constants["edge_inset"], constants["v2"], constants["v3"]]


def _rating_overlay_dynamic_defaults(libraries_data, template_name, defaults):
    alignment = str(_overlay_template_value(libraries_data, template_name, "rating_alignment", defaults) or "vertical").strip().lower()
    alignment = "horizontal" if alignment == "horizontal" else "vertical"
    h_pos = str(_overlay_template_value(libraries_data, template_name, "horizontal_position", defaults) or "left").strip().lower()
    h_pos = h_pos if h_pos in {"left", "center", "right"} else "left"
    v_pos = str(_overlay_template_value(libraries_data, template_name, "vertical_position", defaults) or "center").strip().lower()
    v_pos = v_pos if v_pos in {"top", "center", "bottom"} else "center"

    active_slots = []
    for idx in (1, 2, 3):
        rating = _overlay_template_value(libraries_data, template_name, f"rating{idx}", defaults)
        image = _overlay_template_value(libraries_data, template_name, f"rating{idx}_image", defaults)
        if _meaningful_overlay_value(rating) and _meaningful_overlay_value(image):
            active_slots.append(idx)

    dynamic = {
        "back_width": 270 if alignment == "horizontal" else 160,
        "back_height": 80 if alignment == "horizontal" else 160,
        "addon_position": "left" if alignment == "horizontal" else "top",
        "horizontal_offset": 0 if h_pos == "center" else 15,
        "vertical_offset": 0 if v_pos == "center" else 15,
    }
    if not active_slots:
        return dynamic

    if alignment == "horizontal":
        h_positions = _rating_axis_positions("horizontal", h_pos, len(active_slots))
        shared_v = 0 if v_pos == "center" else (-30 if v_pos == "bottom" else 30)
        for position, idx in enumerate(active_slots):
            dynamic[f"rating{idx}_horizontal_offset"] = h_positions[position]
            dynamic[f"rating{idx}_vertical_offset"] = shared_v
        return dynamic

    v_positions = _rating_axis_positions("vertical", v_pos, len(active_slots))
    shared_h = 0 if h_pos == "center" else (-30 if h_pos == "right" else 30)
    for position, idx in enumerate(active_slots):
        dynamic[f"rating{idx}_horizontal_offset"] = shared_h
        dynamic[f"rating{idx}_vertical_offset"] = v_positions[position]
    return dynamic


def _overlay_template_effective_default(overlay, key, details, libraries_data, template_name):
    if overlay.get("id") == "overlay_ratings":
        defaults = _overlay_template_defaults_map(overlay.get("template_variables"))
        dynamic_defaults = _rating_overlay_dynamic_defaults(libraries_data, template_name, defaults)
        if key in dynamic_defaults:
            return dynamic_defaults[key]
    return details.get("default")


def _overlay_template_key_counts_as_override(overlay, key, details):
    if key == "builder_level":
        return False
    if details.get("input_type") == "hidden" and details.get("default") is None:
        return False
    if key == "text" and overlay.get("id") in {"overlay_aspect", "overlay_video_format"}:
        return False
    return True


def _overlay_group_is_active(library_id, render_type, group, overlay, libraries_data):
    input_type = str(group.get("input_type") or "checkbox").strip().lower()
    if input_type == "radio":
        radio_group_name = str(group.get("radio_group_name") or "").strip()
        if not radio_group_name:
            return False
        field_name = f"{library_id}-{render_type}-{radio_group_name}"
        return str(libraries_data.get(field_name, "")).strip() == str(overlay.get("value", "")).strip()

    field_name = f"{library_id}-{render_type}-{overlay.get('id')}"
    return _coerce_bool(libraries_data.get(field_name))


def _count_overlay_overrides_for_library(library, libraries_data, overlay_config):
    if not isinstance(libraries_data, dict):
        return 0
    library_id = library["id"]
    library_type = library["type"]
    render_types = ["movie"] if library_type == "movie" else ["show", "season", "episode"]
    count = 0
    for group in overlay_config or []:
        for overlay in group.get("overlays", []):
            for render_type in render_types:
                media_types = overlay.get("media_types") or []
                if media_types and render_type not in media_types:
                    continue
                if not _overlay_group_is_active(library_id, render_type, group, overlay, libraries_data):
                    continue
                template_name = f"{library_id}-{render_type}-template_{overlay.get('id')}"
                for key, details in _iter_overlay_template_items(overlay.get("template_variables")):
                    if not _overlay_template_key_counts_as_override(overlay, key, details):
                        continue
                    var_media_types = details.get("media_types") or []
                    if var_media_types and render_type not in var_media_types:
                        continue
                    field_name = f"{template_name}[{key}]"
                    effective_default = _overlay_template_effective_default(overlay, key, details, libraries_data, template_name)
                    if _template_value_is_configured(libraries_data.get(field_name), effective_default, details.get("input_type")):
                        count += 1
    return count


def _has_active_overlay_selection_for_library(library, libraries_data, overlay_config):
    if not isinstance(libraries_data, dict):
        return False
    library_id = library["id"]
    library_type = library["type"]
    render_types = ["movie"] if library_type == "movie" else ["show", "season", "episode"]
    for group in overlay_config or []:
        for overlay in group.get("overlays", []):
            for render_type in render_types:
                media_types = overlay.get("media_types") or []
                if media_types and render_type not in media_types:
                    continue
                if _overlay_group_is_active(library_id, render_type, group, overlay, libraries_data):
                    return True
    return False


def _lazy_section_override_counts(library, libraries_data, telemetry_data=None, collection_config=None, overlay_config=None):
    library_with_plex = dict(library)
    # Collection visibility for visible_* variables depends on Plex Pass.
    telemetry_data = telemetry_data if isinstance(telemetry_data, dict) else {}
    library_with_plex["plex_pass"] = bool(telemetry_data.get("plex_pass"))
    collection_config = collection_config if isinstance(collection_config, list) else helpers.load_quickstart_config("quickstart_collections.json")
    overlay_config = overlay_config if isinstance(overlay_config, list) else helpers.load_quickstart_overlay_config()
    return {
        "collections": _count_collection_overrides_for_library(library_with_plex, libraries_data, collection_config),
        "overlays": _count_overlay_overrides_for_library(library, libraries_data, overlay_config),
    }


def _lazy_section_active_states(library, libraries_data, collection_config=None, overlay_config=None):
    collection_config = collection_config if isinstance(collection_config, list) else helpers.load_quickstart_config("quickstart_collections.json")
    overlay_config = overlay_config if isinstance(overlay_config, list) else helpers.load_quickstart_overlay_config()
    return {
        "collections": _has_active_collection_selection_for_library(library, libraries_data, collection_config),
        "overlays": _has_active_overlay_selection_for_library(library, libraries_data, overlay_config),
    }


def _collection_key_group_indexes(library_id, collection_config, library_type):
    indexes_by_key = {}
    if not library_id or not isinstance(collection_config, list):
        return indexes_by_key
    for group_index, group in enumerate(collection_config):
        for collection in group.get("collections", []) if isinstance(group, dict) else []:
            if library_type not in collection.get("media_types", []):
                continue
            collection_id = str(collection.get("id", "")).strip()
            if not collection_id:
                continue
            clean_id = collection_id.replace("collection_", "")
            indexes_by_key[f"{library_id}-{collection_id}"] = group_index
            indexes_by_key[f"{library_id}-template_collection_{clean_id}_"] = group_index
    return indexes_by_key


def _collection_key_belongs_to_unloaded_group(key, collection_key_indexes, loaded_collection_groups):
    if loaded_collection_groups is None:
        return False
    for prefix, group_index in collection_key_indexes.items():
        if (key == prefix or key.startswith(prefix)) and group_index not in loaded_collection_groups:
            return True
    return False


def _is_collection_default_key(library_id, key):
    if not isinstance(key, str) or key == f"{library_id}-collection_files":
        return False
    return key.startswith(f"{library_id}-collection_") or key.startswith(f"{library_id}-template_collection_")


def _drop_collection_default_keys(library_id, libraries_data):
    if not isinstance(libraries_data, dict):
        return {}
    return {key: value for key, value in libraries_data.items() if not _is_collection_default_key(library_id, key)}


def _merge_active_library_payload_with_saved_libraries(library_id, incoming_libraries, existing_libraries):
    """Merge one active-card autosave with the full persisted libraries map.

    The browser only posts the mounted library card during lazy switching. The
    backend must validate and save against the whole libraries map or unrelated
    libraries lose their ``*-library`` selection flags and disappear from final
    output.
    """
    incoming_libraries = incoming_libraries if isinstance(incoming_libraries, dict) else {}
    existing_libraries = existing_libraries if isinstance(existing_libraries, dict) else {}
    merged = dict(existing_libraries)

    prefixes = set()
    if library_id:
        prefixes.add(library_id)
    for key in incoming_libraries:
        prefix = _library_prefix_from_key(key)
        if prefix:
            prefixes.add(prefix)

    for prefix in prefixes:
        for existing_key in list(merged.keys()):
            if existing_key == f"{prefix}-library" or existing_key.startswith(prefix + "-"):
                merged.pop(existing_key, None)

    for key, value in incoming_libraries.items():
        if (key.endswith("-library") or key.endswith("-playlist")) and not _is_truthy_setting_value(value):
            continue
        merged[key] = value

    return merged


def _is_library_file_entry_key(library_id, key):
    return key in {
        f"{library_id}-collection_files",
        f"{library_id}-metadata_files",
        f"{library_id}-overlay_files",
    }


def _preserve_unloaded_lazy_section_values(library_id, incoming_libraries, loaded_sections, loaded_collection_groups=None):
    """Keep persisted values for omitted lazy/partial library sections."""
    incoming_libraries = incoming_libraries if isinstance(incoming_libraries, dict) else {}
    unloaded_sections = {"collections", "overlays"} - set(loaded_sections or set())
    should_preserve_unloaded_collection_groups = "collections" in set(loaded_sections or set()) and loaded_collection_groups is not None
    missing_partial_fields = {
        f"{library_id}-{suffix}" for suffix in ("collection_files", "metadata_files", "overlay_files", "playlist") if f"{library_id}-{suffix}" not in incoming_libraries
    }
    if not unloaded_sections and not should_preserve_unloaded_collection_groups and not missing_partial_fields:
        return incoming_libraries

    settings = persistence.retrieve_settings("025-libraries")
    existing_libraries = settings.get("libraries", {}) if isinstance(settings, dict) else {}
    if not isinstance(existing_libraries, dict):
        return incoming_libraries

    preserved = dict(incoming_libraries)
    prefix = f"{library_id}-"
    library_type = "movie" if str(library_id).startswith("mov-") else "show"
    collection_key_indexes = {}
    if should_preserve_unloaded_collection_groups:
        collection_key_indexes = _collection_key_group_indexes(
            library_id,
            helpers.load_quickstart_config("quickstart_collections.json"),
            library_type,
        )

    def should_preserve(key):
        if not isinstance(key, str) or not key.startswith(prefix):
            return False
        if key in missing_partial_fields and (_is_library_file_entry_key(library_id, key) or key == f"{library_id}-playlist"):
            return True
        if should_preserve_unloaded_collection_groups and _collection_key_belongs_to_unloaded_group(key, collection_key_indexes, loaded_collection_groups):
            return True
        if "collections" in unloaded_sections and _is_collection_default_key(library_id, key):
            return True
        if "overlays" in unloaded_sections and (
            f"{library_id}-overlay_" in key
            or f"{library_id}-movie-overlay_" in key
            or f"{library_id}-show-overlay_" in key
            or f"{library_id}-season-overlay_" in key
            or f"{library_id}-episode-overlay_" in key
            or f"{library_id}-movie-template_overlay_" in key
            or f"{library_id}-show-template_overlay_" in key
            or f"{library_id}-season-template_overlay_" in key
            or f"{library_id}-episode-template_overlay_" in key
        ):
            return True
        if unloaded_sections and key.startswith(f"{library_id}-template_variables"):
            return True
        return False

    for key, value in existing_libraries.items():
        if key not in preserved and should_preserve(key):
            preserved[key] = value

    return preserved


def _save_lookup_label_only_library_payload(library_id, incoming):
    """Persist lookup-label metadata without running full library validation."""
    if not isinstance(incoming, dict):
        return jsonify({"success": False, "error": "Invalid lookup label payload."}), 400

    config_name = persistence.resolve_request_config_name(incoming)
    settings = persistence.retrieve_settings("025-libraries")
    existing_libraries = settings.get("libraries", {}) if isinstance(settings, dict) else {}
    existing_libraries = existing_libraries.copy() if isinstance(existing_libraries, dict) else {}
    allowed_prefixes = (f"{library_id}-", "playlist-template_variables[")
    updates = {}
    for key, value in incoming.items():
        key = str(key or "").strip()
        if not key.endswith("__lookup_labels"):
            continue
        if not key.startswith(allowed_prefixes):
            continue
        updates[key] = str(value or "{}").strip() or "{}"

    if not updates:
        return jsonify({"success": True, "lookup_labels_only": True, "updated": 0})

    existing_libraries.update(updates)
    database.save_section_data(
        name=config_name,
        section="libraries",
        validated=helpers.booler(settings.get("validated", False)),
        user_entered=True,
        data={"libraries": existing_libraries, "validated": helpers.booler(settings.get("validated", False))},
    )
    return jsonify({"success": True, "lookup_labels_only": True, "updated": len(updates)})


@bp.route("/library_fragment/<library_id>")
def library_fragment(library_id):
    """Return a single library form fragment so we can lazy-load library settings on the page."""
    context = _library_fragment_context(library_id, include_collections=False, include_overlays=False)

    if not context:
        return jsonify({"error": "Library not found"}), 404

    html = render_template(
        "partials/_library_card.html",
        defer_heavy_sections=True,
        **context,
    )

    return html


@bp.route("/library_fragment/<library_id>/section/<section_name>")
def library_fragment_section(library_id, section_name):
    """Return a heavy library section fragment on demand."""
    if section_name not in {"collections", "overlays"}:
        return jsonify({"error": "Unsupported library section"}), 404

    include_collections = section_name == "collections"
    include_overlays = section_name == "overlays"
    context = _library_fragment_context(
        library_id,
        include_attributes=False,
        include_collections=include_collections,
        include_overlays=include_overlays,
    )

    if not context:
        return jsonify({"error": "Library not found"}), 404

    library = context["library"]
    if section_name == "collections":
        template_name = "partials/_movie_collections.html" if library["type"] == "movie" else "partials/_show_collections.html"
    else:
        template_name = "partials/_movie_overlays.html" if library["type"] == "movie" else "partials/_show_overlays.html"

    return render_template(template_name, **context)


@bp.route("/library_fragment/<library_id>/section/collections/group/<int:group_index>")
def library_fragment_collection_group(library_id, group_index):
    """Return one collection group fragment on demand."""
    context = _library_fragment_context(
        library_id,
        include_attributes=False,
        include_collections=True,
        include_overlays=False,
    )

    if not context:
        return jsonify({"error": "Library not found"}), 404

    collection_config = context.get("collection_config") or []
    if group_index < 0 or group_index >= len(collection_config):
        return jsonify({"error": "Collection group not found"}), 404

    context = dict(context)
    context["group"] = collection_config[group_index]
    return render_template("partials/_collection_group_fragment.html", **context)


@bp.route("/autosave_library/<library_id>", methods=["POST"])
def autosave_library(library_id):
    """Merge-save a single library when switching cards without requiring full navigation submit."""
    # Lazy imports break a load-order cycle: quickstart imports this blueprint at module
    # load, but these helpers haven't finished defining at that point.
    import quickstart as _qs

    try:
        incoming = request.get_json(silent=True) or request.form
        if isinstance(incoming, dict) and helpers.booler(incoming.get("__lookup_labels_only")):
            return _save_lookup_label_only_library_payload(library_id, incoming)
        loaded_sections = _coerce_loaded_library_sections(incoming.get("__loaded_sections") if hasattr(incoming, "get") else None)
        loaded_collection_groups_raw = incoming.get("__loaded_collection_groups") if hasattr(incoming, "get") else None
        loaded_collection_groups = _coerce_loaded_collection_groups(loaded_collection_groups_raw) if loaded_collection_groups_raw is not None else None
        reset_collection_defaults = helpers.booler(incoming.get("__reset_collection_defaults") if hasattr(incoming, "get") else None)
        config_name = persistence.resolve_request_config_name(incoming if isinstance(incoming, dict) else {})
        errors = path_validation.validate_payload(incoming)
        if errors:
            return jsonify({"success": False, "error": "Invalid path values.", "errors": errors}), 400
        clean_source = dict(incoming) if isinstance(incoming, dict) else incoming
        if isinstance(clean_source, dict):
            clean_source.pop("__loaded_sections", None)
            clean_source.pop("__loaded_collection_groups", None)
            clean_source.pop("__reset_collection_defaults", None)
        clean_payload = persistence.clean_form_data(MultiDict(clean_source))
        incoming_libraries = helpers.build_config_dict("libraries", clean_payload).get("libraries", {})
        loaded_sections = _loaded_sections_with_payload_evidence(library_id, incoming_libraries, loaded_sections)
        if reset_collection_defaults:
            loaded_sections.add("collections")
            incoming_libraries = _drop_collection_default_keys(library_id, incoming_libraries)
        incoming_libraries = _preserve_unloaded_lazy_section_values(library_id, incoming_libraries, loaded_sections, loaded_collection_groups)
        if reset_collection_defaults:
            incoming_libraries = _drop_collection_default_keys(library_id, incoming_libraries)
        settings = persistence.retrieve_settings("025-libraries")
        existing_libraries = settings.get("libraries", {}) if isinstance(settings, dict) else {}
        merged_libraries = _merge_active_library_payload_with_saved_libraries(library_id, incoming_libraries, existing_libraries)
        selected_library_ids = _qs._selected_library_ids_from_libraries_data(merged_libraries)
        collection_errors = _qs._validate_library_collection_files(merged_libraries, selected_library_ids)
        metadata_errors = _qs._validate_library_metadata_files(merged_libraries, selected_library_ids)
        overlay_errors = _qs._validate_library_overlay_files(merged_libraries, selected_library_ids)
        auto_sort_hubs_errors = _qs._validate_library_auto_sort_hubs(merged_libraries, selected_library_ids)
        if collection_errors:
            return jsonify({"success": False, "error": "Invalid collection files.", "errors": collection_errors}), 400
        if metadata_errors:
            return jsonify({"success": False, "error": "Invalid metadata files.", "errors": metadata_errors}), 400
        if overlay_errors:
            return jsonify({"success": False, "error": "Invalid overlay files.", "errors": overlay_errors}), 400
        if auto_sort_hubs_errors:
            return jsonify({"success": False, "error": "Invalid library settings.", "errors": auto_sort_hubs_errors}), 400
        normalized_libraries, normalization_errors, changed = _qs._normalize_library_file_entries_payload(
            merged_libraries,
            config_name,
            validate_local=False,
        )
        if normalization_errors:
            return jsonify({"success": False, "error": "Unable to organize library files.", "errors": normalization_errors}), 400
        save_payload = dict(normalized_libraries)
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
    ("Tracearr", "tracearr", _libraries_data_tracearr_dependency_reasons),
    ("OMDb", "omdb", _libraries_data_omdb_dependency_reasons),
    ("MDBList", "mdblist", _libraries_data_mdblist_dependency_reasons),
    ("Floppy", "floppy", _libraries_data_floppy_dependency_reasons),
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
            source_payload_for_merge = dict(source_payload)
            loaded_sections = _coerce_loaded_library_sections(source_payload_for_merge.pop("__loaded_sections", []))
            loaded_collection_groups_raw = source_payload_for_merge.pop("__loaded_collection_groups", None)
            loaded_collection_groups = _coerce_loaded_collection_groups(loaded_collection_groups_raw) if loaded_collection_groups_raw is not None else None
            payload_errors = path_validation.validate_payload(source_payload_for_merge)
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
                clean_payload = persistence.clean_form_data(MultiDict(source_payload_for_merge))
                incoming_dict = helpers.build_config_dict("libraries", clean_payload).get("libraries", {})
                normalized_incoming, normalization_errors, _ = _qs._normalize_library_file_entries_payload(
                    incoming_dict,
                    session.get("config_name") or source_payload_for_merge.get("config_name"),
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
                loaded_sections = _loaded_sections_with_payload_evidence(source_prefix, normalized_incoming, loaded_sections)
                incoming_dict = _preserve_unloaded_lazy_section_values(
                    source_prefix,
                    normalized_incoming,
                    loaded_sections,
                    loaded_collection_groups,
                )

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
                if target_id != source_prefix and key.endswith("-library"):
                    # Do not opt target libraries into YAML automatically.
                    # Mirrored settings remain saved and become active if the
                    # user explicitly includes the target later.
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
