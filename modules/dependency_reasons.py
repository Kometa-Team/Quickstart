"""Workspace dependency-reason calculations.

Pure helpers that inspect a configuration's ``libraries`` block (and the
matching database section rows) to figure out *why* a particular
third-party service is required. The results power the "X required by"
hints in the workspace status menu and the per-library dependency hint
endpoints.

Everything here is library/data centric — no Flask, no DB writes. The
two main entry-point families are:

* ``_libraries_data_<service>_dependency_reasons(libraries_data)`` —
  pure inspection of the in-memory libraries payload, used directly by
  the library dependency-hint routes.
* ``_config_<service>_dependency_reasons(section_rows)`` — thin
  adapters that pull ``libraries.libraries`` out of a section-rows dict
  before delegating to the libraries-data resolver.

The workspace status builder uses the ``_config_*`` adapters; library
routes call the ``_libraries_data_*`` resolvers directly.
"""

from __future__ import annotations

import json
import re

# --- value helpers ---------------------------------------------------------


def _normalize_status(value):
    status = str(value or "").strip().lower()
    if status in ("unknown", "ok", "warn", "error"):
        return status
    return "warn"


def _is_truthy_setting_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"", "0", "false", "none", "null", "[]", "{}"}:
            return False
        return True
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return bool(value)


def _parse_json_array(value):
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return []
    text = value.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return []
    if isinstance(parsed, list):
        return parsed
    return []


# --- dependency constants --------------------------------------------------

QS_TAUTULLI_REQUIRED_STEP_KEY = "030-tautulli"
QS_OMDB_REQUIRED_STEP_KEY = "050-omdb"
QS_MDBLIST_REQUIRED_STEP_KEY = "060-mdblist"
QS_ANIDB_REQUIRED_STEP_KEY = "100-anidb"
QS_RADARR_REQUIRED_STEP_KEY = "110-radarr"
QS_SONARR_REQUIRED_STEP_KEY = "120-sonarr"
QS_TRAKT_REQUIRED_STEP_KEY = "130-trakt"
QS_MAL_REQUIRED_STEP_KEY = "140-mal"

QS_TAUTULLI_DEP_COLLECTION_IDS = {"collection_tautulli"}
QS_TRAKT_DEP_COLLECTION_IDS = {"collection_trakt"}
QS_MAL_DEP_COLLECTION_IDS = {"collection_myanimelist"}
QS_OMDB_DEP_SOURCE_PREFIXES = ("omdb",)
QS_MDBLIST_DEP_SOURCE_PREFIXES = ("mdb",)
QS_ANIDB_DEP_SOURCE_PREFIXES = ("anidb",)
QS_MDBLIST_OVERLAY_IMAGE_VALUES = {"letterboxd", "metacritic", "rt_tomato", "rt_popcorn", "mdb"}
QS_ANIDB_OVERLAY_IMAGE_VALUES = {"anidb"}
QS_TRAKT_OVERLAY_IMAGE_VALUES = {"trakt"}
QS_MAL_OVERLAY_IMAGE_VALUES = {"mal"}
QS_RADARR_DEP_ATTRIBUTE_PREFIXES = ("radarr_add_all", "radarr_remove_by_tag")
QS_RADARR_DEP_COLLECTION_PREFIXES = ("collection_radarr_",)
QS_RADARR_DEP_TEMPLATE_COLLECTION_PREFIXES = ("radarr_add_missing_",)
QS_SONARR_DEP_ATTRIBUTE_PREFIXES = ("sonarr_add_all", "sonarr_remove_by_tag")
QS_SONARR_DEP_COLLECTION_PREFIXES = ("collection_sonarr_",)
QS_SONARR_DEP_TEMPLATE_COLLECTION_PREFIXES = ("sonarr_add_missing_",)
QS_MAL_DEP_ATTRIBUTE_OPERATIONS = {
    "mass_genre_update",
    "mass_content_rating_update",
    "mass_original_title_update",
    "mass_studio_update",
    "mass_originally_available_update",
    "mass_added_at_update",
    "mass_audience_rating_update",
    "mass_critic_rating_update",
    "mass_user_rating_update",
}
QS_MAL_DEP_ATTRIBUTE_VALUES = {"mal", "mal_english", "mal_japanese"}


# --- library prefix helpers ------------------------------------------------


def _selected_library_ids_from_libraries_data(libraries_data):
    if not isinstance(libraries_data, dict):
        return []

    return [
        key[: -len("-library")]
        for key, value in libraries_data.items()
        if isinstance(key, str) and key.startswith(("mov-library_", "sho-library_")) and key.endswith("-library") and _is_truthy_setting_value(value)
    ]


def _library_prefix_from_key(key):
    if not isinstance(key, str) or not key.startswith(("mov-library_", "sho-library_")):
        return None
    for marker in (
        "-movie-template_",
        "-show-template_",
        "-season-template_",
        "-episode-template_",
        "-movie-overlay_",
        "-show-overlay_",
        "-season-overlay_",
        "-episode-overlay_",
    ):
        if marker in key:
            return key.split(marker, 1)[0]
    if "-template_" in key:
        return key.split("-template_", 1)[0]
    if "-attribute_" in key:
        return key.split("-attribute_", 1)[0]
    if "-collection_" in key:
        return key.split("-collection_", 1)[0]
    if "-overlay_" in key:
        return key.split("-overlay_", 1)[0]
    if "-top_level_" in key:
        return key.split("-top_level_", 1)[0]
    if key.endswith("-library"):
        return key[: -len("-library")]
    return None


def _active_library_prefixes(libraries_data):
    if not isinstance(libraries_data, dict):
        return set()

    active_prefixes = set()
    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        if not key.endswith("-library"):
            continue
        prefix = _library_prefix_from_key(key)
        if prefix and _is_truthy_setting_value(raw_value):
            active_prefixes.add(prefix)
    return active_prefixes


# --- reason builders -------------------------------------------------------


def _dependency_reason_label(libraries_data, prefix):
    library_name = libraries_data.get(f"{prefix}-library") if isinstance(libraries_data, dict) else None
    if isinstance(library_name, str) and library_name.strip():
        return library_name.strip()
    return prefix


def _append_dependency_reason(reasons, seen, libraries_data, prefix, detail):
    label = _dependency_reason_label(libraries_data, prefix)
    reason = f"{label}: {detail}"
    normalized = reason.lower()
    if normalized in seen:
        return
    seen.add(normalized)
    reasons.append(reason)


def _libraries_data_collection_dependency_reasons(libraries_data, collection_ids, detail):
    if not isinstance(libraries_data, dict):
        return []

    active_prefixes = _active_library_prefixes(libraries_data)
    reasons = []
    seen = set()

    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        if not key or "-collection_" not in key or not _is_truthy_setting_value(raw_value):
            continue

        prefix = _library_prefix_from_key(key)
        if prefix and prefix not in active_prefixes:
            continue

        collection_id = f"collection_{key.rsplit('-collection_', 1)[1]}"
        if collection_id in collection_ids:
            _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)

    return reasons


def _libraries_data_template_collection_dependency_reasons(libraries_data, child_ids, detail):
    if not isinstance(libraries_data, dict):
        return []

    active_prefixes = _active_library_prefixes(libraries_data)
    reasons = []
    seen = set()
    normalized_child_ids = tuple(str(child_id or "").strip().lower() for child_id in child_ids if str(child_id or "").strip())
    if not normalized_child_ids:
        return reasons

    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        if not key or "-template_collection_" not in key or not _is_truthy_setting_value(raw_value):
            continue

        prefix = _library_prefix_from_key(key)
        if prefix and prefix not in active_prefixes:
            continue

        matched_child_id = None
        for child_id in normalized_child_ids:
            if re.search(rf"-template_collection_[a-z0-9_]+_{re.escape(child_id)}$", key):
                matched_child_id = child_id
                break
        if matched_child_id:
            _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)

    return reasons


def _libraries_data_service_dependency_reasons(libraries_data, attribute_prefixes, collection_prefixes, template_collection_prefixes=()):
    if not isinstance(libraries_data, dict):
        return []

    active_prefixes = _active_library_prefixes(libraries_data)
    reasons = []
    seen = set()
    normalized_attribute_prefixes = tuple(str(prefix or "").strip().lower() for prefix in attribute_prefixes if str(prefix or "").strip())
    normalized_collection_prefixes = tuple(str(prefix or "").strip().lower() for prefix in collection_prefixes if str(prefix or "").strip())
    normalized_template_collection_prefixes = tuple(str(prefix or "").strip().lower() for prefix in template_collection_prefixes if str(prefix or "").strip())

    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        if not key or not _is_truthy_setting_value(raw_value):
            continue

        prefix = _library_prefix_from_key(key)
        if prefix and prefix not in active_prefixes:
            continue

        if "-attribute_" in key:
            attribute_key = key.split("-attribute_", 1)[1]
            matched_attribute = next(
                (attr_prefix for attr_prefix in normalized_attribute_prefixes if attribute_key == attr_prefix or attribute_key.startswith(f"{attr_prefix}_")),
                None,
            )
            if matched_attribute:
                detail = f"{matched_attribute} configured" if attribute_key.endswith("_custom") else f"{attribute_key} enabled"
                _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)
                continue

        if "-collection_" in key:
            collection_id = f"collection_{key.rsplit('-collection_', 1)[1]}"
            if any(collection_id.startswith(collection_prefix) for collection_prefix in normalized_collection_prefixes):
                detail = f"{collection_id} enabled"
                _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)
                continue

        if "-template_collection_" in key:
            matched_child_key = None
            for template_prefix in normalized_template_collection_prefixes:
                match = re.search(
                    rf"-template_collection_[a-z0-9_]+_({re.escape(template_prefix)}[a-z0-9_]*)$",
                    key,
                )
                if match:
                    matched_child_key = match.group(1)
                    break
            if matched_child_key:
                detail = f"{matched_child_key} enabled"
                _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)

    return reasons


def _libraries_data_overlay_rating_dependency_reasons(libraries_data, image_values):
    if not isinstance(libraries_data, dict):
        return []

    active_prefixes = _active_library_prefixes(libraries_data)
    reasons = []
    seen = set()
    normalized_images = {str(value or "").strip().lower() for value in image_values if str(value or "").strip()}
    if not normalized_images:
        return reasons

    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        selected_image = str(raw_value or "").strip().lower()
        if selected_image not in normalized_images:
            continue

        match = re.match(
            r"^(?P<prefix>(?:mov|sho)-library_[a-z0-9_]+)-(?P<builder>movie|show|season|episode)-template_overlay_ratings\[rating[123]_image\]$",
            key,
        )
        if not match:
            continue

        prefix = match.group("prefix")
        builder = match.group("builder")
        if prefix not in active_prefixes:
            continue

        overlay_toggle_key = f"{prefix}-{builder}-overlay_ratings"
        if not _is_truthy_setting_value(libraries_data.get(overlay_toggle_key)):
            continue

        detail = f"{builder} ratings overlay uses {selected_image}"
        _append_dependency_reason(reasons, seen, libraries_data, prefix, detail)

    return reasons


def _attribute_dependency_source_reasons(libraries_data, source_prefixes):
    if not isinstance(libraries_data, dict):
        return []

    active_prefixes = _active_library_prefixes(libraries_data)
    reasons = []
    seen = set()
    normalized_prefixes = tuple(str(prefix or "").strip().lower() for prefix in source_prefixes if str(prefix or "").strip())
    if not normalized_prefixes:
        return reasons

    def matches_source(source_value):
        normalized = str(source_value or "").strip().lower()
        if not normalized:
            return False
        return any(normalized == prefix or normalized.startswith(f"{prefix}_") for prefix in normalized_prefixes)

    def extract_operation_and_source(key):
        attr_body = key.split("-attribute_", 1)[1] if "-attribute_" in key else ""
        if not attr_body or attr_body.endswith("_order"):
            return None, None
        parts = [part for part in attr_body.split("_") if part]
        if len(parts) < 3:
            return None, None
        for split_index in range(2, len(parts)):
            operation = "_".join(parts[:split_index])
            source_value = "_".join(parts[split_index:])
            if operation.startswith("mass_") and matches_source(source_value):
                return operation, source_value
        return None, None

    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        if not key or "-attribute_" not in key:
            continue

        prefix = _library_prefix_from_key(key)
        if prefix and prefix not in active_prefixes:
            continue

        operation, source_value = extract_operation_and_source(key)
        if operation and source_value and _is_truthy_setting_value(raw_value):
            detail = f"{operation} uses {source_value}"
            _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)
            continue

        order_match = re.search(r"-attribute_(mass_[a-z0-9_]+)_order$", key)
        if not order_match:
            continue

        operation = order_match.group(1)
        matched_sources = []
        for entry in _parse_json_array(raw_value):
            source_value = str(entry or "").strip().lower()
            if matches_source(source_value):
                matched_sources.append(source_value)
        if matched_sources:
            joined_sources = ", ".join(sorted(set(matched_sources)))
            detail = f"{operation} order includes {joined_sources}"
            _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)

    return reasons


# --- per-service libraries-data resolvers ----------------------------------


def _libraries_data_tautulli_dependency_reasons(libraries_data):
    return _libraries_data_collection_dependency_reasons(
        libraries_data,
        QS_TAUTULLI_DEP_COLLECTION_IDS,
        "Tautulli Charts collection enabled",
    )


def _libraries_data_trakt_dependency_reasons(libraries_data):
    collection_reasons = _libraries_data_collection_dependency_reasons(
        libraries_data,
        QS_TRAKT_DEP_COLLECTION_IDS,
        "Trakt Charts collection enabled",
    )
    overlay_reasons = _libraries_data_overlay_rating_dependency_reasons(
        libraries_data,
        QS_TRAKT_OVERLAY_IMAGE_VALUES,
    )
    return collection_reasons + [reason for reason in overlay_reasons if reason not in collection_reasons]


def _libraries_data_omdb_dependency_reasons(libraries_data):
    return _attribute_dependency_source_reasons(
        libraries_data,
        QS_OMDB_DEP_SOURCE_PREFIXES,
    )


def _libraries_data_mdblist_dependency_reasons(libraries_data):
    attribute_reasons = _attribute_dependency_source_reasons(
        libraries_data,
        QS_MDBLIST_DEP_SOURCE_PREFIXES,
    )
    overlay_reasons = _libraries_data_overlay_rating_dependency_reasons(
        libraries_data,
        QS_MDBLIST_OVERLAY_IMAGE_VALUES,
    )
    return attribute_reasons + [reason for reason in overlay_reasons if reason not in attribute_reasons]


def _libraries_data_anidb_dependency_reasons(libraries_data):
    attribute_reasons = _attribute_dependency_source_reasons(
        libraries_data,
        QS_ANIDB_DEP_SOURCE_PREFIXES,
    )
    overlay_reasons = _libraries_data_overlay_rating_dependency_reasons(
        libraries_data,
        QS_ANIDB_OVERLAY_IMAGE_VALUES,
    )
    return attribute_reasons + [reason for reason in overlay_reasons if reason not in attribute_reasons]


def _libraries_data_radarr_dependency_reasons(libraries_data):
    return _libraries_data_service_dependency_reasons(
        libraries_data,
        QS_RADARR_DEP_ATTRIBUTE_PREFIXES,
        QS_RADARR_DEP_COLLECTION_PREFIXES,
        QS_RADARR_DEP_TEMPLATE_COLLECTION_PREFIXES,
    )


def _libraries_data_sonarr_dependency_reasons(libraries_data):
    return _libraries_data_service_dependency_reasons(
        libraries_data,
        QS_SONARR_DEP_ATTRIBUTE_PREFIXES,
        QS_SONARR_DEP_COLLECTION_PREFIXES,
        QS_SONARR_DEP_TEMPLATE_COLLECTION_PREFIXES,
    )


def _libraries_data_mal_dependency_reasons(libraries_data):
    if not isinstance(libraries_data, dict):
        return []

    active_prefixes = _active_library_prefixes(libraries_data)
    reasons = []
    seen = set()

    for raw_key, raw_value in libraries_data.items():
        key = str(raw_key or "").strip().lower()
        if not key:
            continue

        prefix = _library_prefix_from_key(key)
        if prefix and prefix not in active_prefixes:
            continue

        if "-collection_" in key and _is_truthy_setting_value(raw_value):
            collection_id = f"collection_{key.rsplit('-collection_', 1)[1]}"
            if collection_id in QS_MAL_DEP_COLLECTION_IDS:
                _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", "MyAnimeList Charts collection enabled")
                continue

        attr_match = re.search(r"-attribute_(mass_[a-z0-9_]+)_(mal(?:_english|_japanese)?)$", key)
        if attr_match and _is_truthy_setting_value(raw_value):
            operation = attr_match.group(1)
            source_value = attr_match.group(2)
            if operation in QS_MAL_DEP_ATTRIBUTE_OPERATIONS and source_value in QS_MAL_DEP_ATTRIBUTE_VALUES:
                detail = f"{operation} uses {source_value}"
                _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)
                continue

        order_match = re.search(r"-attribute_(mass_[a-z0-9_]+)_order$", key)
        if not order_match:
            continue
        operation = order_match.group(1)
        if operation not in QS_MAL_DEP_ATTRIBUTE_OPERATIONS:
            continue
        matched_sources = []
        for entry in _parse_json_array(raw_value):
            source_value = str(entry or "").strip().lower()
            if source_value in QS_MAL_DEP_ATTRIBUTE_VALUES:
                matched_sources.append(source_value)
        if matched_sources:
            joined_sources = ", ".join(sorted(set(matched_sources)))
            detail = f"{operation} order includes {joined_sources}"
            _append_dependency_reason(reasons, seen, libraries_data, prefix or "library", detail)

    overlay_reasons = _libraries_data_overlay_rating_dependency_reasons(
        libraries_data,
        QS_MAL_OVERLAY_IMAGE_VALUES,
    )
    return reasons + [reason for reason in overlay_reasons if reason not in reasons]


def _libraries_data_requires_mal(libraries_data):
    return bool(_libraries_data_mal_dependency_reasons(libraries_data))


# --- section-rows adapter family -------------------------------------------


def _config_dependency_reasons(section_rows, dependency_resolver):
    if not isinstance(section_rows, dict):
        return []
    libraries_row = section_rows.get("libraries")
    if not isinstance(libraries_row, dict):
        return []
    libraries_payload = libraries_row.get("data")
    if not isinstance(libraries_payload, dict):
        return []
    libraries_data = libraries_payload.get("libraries", {})
    return dependency_resolver(libraries_data)


def _config_requires_mal(section_rows):
    if not isinstance(section_rows, dict):
        return False
    libraries_row = section_rows.get("libraries")
    if not isinstance(libraries_row, dict):
        return False
    libraries_payload = libraries_row.get("data")
    if not isinstance(libraries_payload, dict):
        return False
    libraries_data = libraries_payload.get("libraries", {})
    return _libraries_data_requires_mal(libraries_data)


def _config_tautulli_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_tautulli_dependency_reasons)


def _config_omdb_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_omdb_dependency_reasons)


def _config_mdblist_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_mdblist_dependency_reasons)


def _config_anidb_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_anidb_dependency_reasons)


def _config_radarr_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_radarr_dependency_reasons)


def _config_sonarr_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_sonarr_dependency_reasons)


def _config_trakt_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_trakt_dependency_reasons)


def _config_mal_dependency_reasons(section_rows):
    return _config_dependency_reasons(section_rows, _libraries_data_mal_dependency_reasons)
