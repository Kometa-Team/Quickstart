import namesgenerator
import os
import secrets
import json
import datetime
import copy
import re

from flask import current_app as app
from flask import has_request_context, session
from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError  # noqa
from urllib.parse import urlparse
from werkzeug.datastructures import MultiDict

from modules import database, helpers, iso, url_validation

_ISO_639_1_LANGUAGES = None
_ISO_3166_1_REGIONS = None
_ISO_639_2_LANGUAGES = None
_DUMMY_CONFIG_CACHE = None

TRANSIENT_FORM_FIELDS = {
    "configSelector",
    "config_name",
    "newConfigName",
    "importMode",
}

KOMETA_INSTALL_SELECTION_FIELDS = (
    "install_mode",
    "existing_root",
    "external_config_root",
    "external_log_root",
)


def _normalize_plex_db_cache_value(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return ""
    match = re.search(r"\d+", text)
    if match:
        return int(match.group(0))
    return value


def _get_iso_reference_lists():
    global _ISO_639_1_LANGUAGES
    global _ISO_3166_1_REGIONS
    global _ISO_639_2_LANGUAGES

    if _ISO_639_1_LANGUAGES is None:
        _ISO_639_1_LANGUAGES = [(la.alpha2, la.name) for la in iso.languages]
    if _ISO_3166_1_REGIONS is None:
        _ISO_3166_1_REGIONS = [(c.alpha2, c.name) for c in iso.countries]
    if _ISO_639_2_LANGUAGES is None:
        _ISO_639_2_LANGUAGES = [(la.alpha3, la.name) for la in iso.languages]
    return _ISO_639_1_LANGUAGES, _ISO_3166_1_REGIONS, _ISO_639_2_LANGUAGES


def extract_names(raw_source):
    source = raw_source

    # get source from referrer
    if raw_source.startswith("http"):
        source = raw_source.split("/")[-1]
        source = source.split("?")[0]

    source_name = source.split("-")[-1]
    # source will be `010-plex`
    # source_name will be `plex`

    return source, source_name


def ensure_session_config_name():
    existing = session.get("config_name")
    if existing:
        return existing

    last_used = database.get_last_used_config_name()
    if last_used:
        session["config_name"] = last_used
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Recovered session config_name from DB: {session['config_name']}", level="DEBUG")
        return session["config_name"]

    session["config_name"] = namesgenerator.get_random_name()
    if app.config["QS_DEBUG"]:
        helpers.ts_log(f"Initialized missing session config_name: {session['config_name']}", level="DEBUG")
    return session["config_name"]


def resolve_request_config_name(payload=None):
    raw_config_name = str((payload or {}).get("config_name") or "").strip() if isinstance(payload, dict) else ""
    normalized = helpers.normalize_config_name_for_storage(raw_config_name) if raw_config_name else ""
    if normalized:
        if has_request_context():
            session["config_name"] = normalized
        return normalized
    resolved = session.get("config_name") or ensure_session_config_name()
    if has_request_context() and resolved:
        session["config_name"] = resolved
    return resolved


def retrieve_settings_for_config(config_name, target):
    source, source_name = extract_names(target)
    stored_validated, stored_user_entered, stored_payload = database.retrieve_section_data(config_name, source_name)
    payload = stored_payload if isinstance(stored_payload, dict) else {}
    section = payload.get(source_name, {}) if isinstance(payload.get(source_name), dict) else {}
    if not section:
        section = get_dummy_data(source_name)
    return {
        "validated": helpers.booler(stored_validated),
        "user_entered": helpers.booler(stored_user_entered),
        "validated_at": payload.get("validated_at") if isinstance(payload, dict) else None,
        source_name: section,
    }


def apply_validation_metadata(stored_data, status, reason=None, details=None, updated_at=None):
    if not isinstance(stored_data, dict):
        stored_data = {}
    timestamp = updated_at or helpers.utc_now_iso()
    stored_data["validation_status"] = status
    stored_data["validation_updated_at"] = timestamp
    if status == "validated":
        stored_data["validated"] = True
        stored_data["validated_at"] = timestamp
        stored_data.pop("validation_reason", None)
        stored_data.pop("validation_details", None)
    else:
        if reason is not None:
            stored_data["validation_reason"] = reason
        if details is not None:
            stored_data["validation_details"] = details
    return stored_data


def clean_form_data(form_data):
    # Make sure form_data is MultiDict for compatibility
    if not hasattr(form_data, "getlist"):
        form_data = MultiDict(form_data)

    clean_data = {}

    for key, value in form_data.items():
        if key in TRANSIENT_FORM_FIELDS:
            continue
        # Handle asset_directory as a list
        if key == "asset_directory" or key.endswith("-attribute_asset_directory"):
            if isinstance(value, list):
                value_list = value
            else:
                value_list = form_data.getlist(key)
            clean_data[key] = [v.strip() for v in value_list if v.strip()]

        elif key.endswith("template_overlay_languages[languages]") or key.endswith("template_overlay_languages_subtitles[languages]"):
            if isinstance(value, list):
                value_list = value
            else:
                value_list = form_data.getlist(key)
            clean_data[key] = [v.strip() for v in value_list if isinstance(v, str) and v.strip()]

        elif key.endswith("use_separator"):
            prefix = "mov" if key.startswith("mov") else "sho"
            clean_data.setdefault(f"{prefix}-template_variables", {})["use_separator"] = value if value != "none" else None

        elif key.endswith("sep_style"):
            prefix = "mov" if key.startswith("mov") else "sho"
            if form_data.get(f"{prefix}-template_variables[use_separator]", "false") != "none":
                clean_data.setdefault(f"{prefix}-template_variables", {})["sep_style"] = value.strip()

        elif url_validation.is_url_key(key) and isinstance(value, str) and url_validation.is_placeholder(value):
            clean_data[key] = None

        elif isinstance(value, str):
            if key == "plex_db_cache":
                clean_data[key] = _normalize_plex_db_cache_value(value)
                continue
            if key.endswith("template_overlay_runtimes[text]") and value == "":
                clean_data[key] = ""
                continue
            if url_validation.is_url_key(key):
                raw = value.strip()
                if raw:
                    try:
                        parsed = urlparse(raw)
                        if parsed.scheme:
                            value = parsed._replace(scheme=parsed.scheme.lower()).geturl()
                    except Exception:
                        value = value
            lc_value = value.lower().strip()
            if len(value) == 0 or lc_value == "none":
                clean_data[key] = None
            elif lc_value in ["true", "on"]:
                clean_data[key] = True
            elif lc_value == "false":
                clean_data[key] = False
            elif key.endswith("-library"):
                # Library display names from Plex — preserve exactly (leading/trailing spaces are significant)
                clean_data[key] = value
            else:
                clean_data[key] = value.strip()

        else:
            clean_data[key] = value

    cache_defaults = {
        "cache_expiration": "60",
        "tmdb_cache_expiration": "60",
        "omdb_cache_expiration": "60",
        "mdblist_cache_expiration": "60",
        "anidb_cache_expiration": "60",
        "mal_cache_expiration": "60",
    }
    for key, default_value in cache_defaults.items():
        if key not in clean_data:
            continue
        value = clean_data[key]
        if value is None:
            clean_data[key] = default_value
        elif isinstance(value, str) and value.strip() == "":
            clean_data[key] = default_value

    return clean_data


def _preserve_kometa_install_selection(data, clean_data):
    if not isinstance(data, dict):
        return data
    incoming_section = data.get("kometa")
    if not isinstance(incoming_section, dict):
        return data

    # The Start page owns these fields through /save-kometa-install-mode.
    # Generic Kometa-page saves often contain only final-page controls, so they
    # must not reset an existing/external install back to the managed default.
    if any(field in clean_data or field in incoming_section for field in KOMETA_INSTALL_SELECTION_FIELDS):
        return data

    try:
        _validated, _user_entered, stored_payload = database.retrieve_section_data(session["config_name"], "kometa")
    except Exception:
        return data

    stored_section = stored_payload.get("kometa", {}) if isinstance(stored_payload, dict) else {}
    if not isinstance(stored_section, dict):
        return data

    preserved = {field: stored_section.get(field) for field in KOMETA_INSTALL_SELECTION_FIELDS if field in stored_section}
    if not preserved:
        return data

    merged_section = dict(incoming_section)
    for field, value in preserved.items():
        if value is not None:
            merged_section[field] = value
    data["kometa"] = merged_section
    return data


def save_settings(raw_source, form_data):
    # Extract the source and source_name
    source, source_name = extract_names(raw_source)
    path = urlparse(raw_source).path
    source = os.path.basename(path)

    ensure_session_config_name()

    is_form = hasattr(form_data, "getlist")

    # Debug raw form data
    if app.config["QS_DEBUG"]:
        clean_dict = {k: (form_data.getlist(k) if len(form_data.getlist(k)) > 1 else form_data.get(k)) for k in form_data} if is_form else form_data
        debug_dir = os.path.join(helpers.CONFIG_DIR, "debug_logs")
        os.makedirs(debug_dir, exist_ok=True)
        debug_path = os.path.join(debug_dir, f"{source}_form_data.json")
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(clean_dict, f, indent=2, ensure_ascii=False)
        helpers.ts_log(f"Form data saved to: {debug_path}", level="DEBUG")

    # Respect config_name from form
    if "config_name" in form_data:
        session["config_name"] = form_data["config_name"]
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Received config name in form: {session['config_name']}", level="DEBUG")

    if is_form and "asset_directory" in form_data:
        asset_directories = form_data.getlist("asset_directory")
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"All asset_directory values from form: {asset_directories}", level="DEBUG")

    clean_data = clean_form_data(form_data if is_form else MultiDict(form_data))

    for field in ["plex_url", "plex_token"]:
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Cleaned value for {field}: {clean_data.get(field)}", level="DEBUG")

    if "asset_directory" in clean_data and app.config["QS_DEBUG"]:
        helpers.ts_log(f"Cleaned asset_directory: {clean_data['asset_directory']}", level="DEBUG")

    data = helpers.build_config_dict(source_name, clean_data)
    if source_name == "kometa":
        data = _preserve_kometa_install_selection(data, clean_data)

    if app.config["QS_DEBUG"]:
        helpers.ts_log(f"Final data structure to save: {data}", level="DEBUG")
        if source_name == "settings" and "asset_directory" in data.get("settings", {}):
            helpers.ts_log(f"Final asset_directory structure to save: {data['settings']['asset_directory']}", level="DEBUG")

    # Merge library data so switching cards doesn't wipe other libraries
    if source_name == "libraries":
        try:
            existing_settings = retrieve_settings("025-libraries")
            existing_validated = existing_settings.get("validated")
            existing_libraries = existing_settings.get("libraries", {})
            incoming_libraries = data.get("libraries", {})

            merged_libraries = existing_libraries.copy() if isinstance(existing_libraries, dict) else {}
            incoming_libraries = incoming_libraries if isinstance(incoming_libraries, dict) else {}

            def _library_prefix(key):
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
                    "-template_",
                    "-attribute_",
                    "-collection_",
                    "-overlay_",
                    "-top_level_",
                    "-library_service_",
                ):
                    if marker in key:
                        return key.split(marker, 1)[0]
                if key.endswith("-library"):
                    return key[: -len("-library")]
                for suffix in ("-playlist", "-collection_files", "-metadata_files", "-overlay_files"):
                    if key.endswith(suffix):
                        return key[: -len(suffix)]
                return None

            # Identify library prefixes present in this payload (e.g., mov-library_xxx, sho-library_yyy)
            prefixes = set()
            for key, value in incoming_libraries.items():
                prefix = _library_prefix(key)
                if not prefix:
                    continue
                # Lazy library cards can leave disabled/hidden false toggles in
                # form payloads. A false include/playlist toggle alone is not
                # enough evidence that this prefix was intentionally submitted.
                if key in (f"{prefix}-library", f"{prefix}-playlist") and value in [None, False, "", "false"]:
                    continue
                prefixes.add(prefix)

            # Remove existing entries for the affected prefixes so we can replace them cleanly
            for prefix in prefixes:
                for k in list(merged_libraries.keys()):
                    if k.startswith(prefix + "-") or k == f"{prefix}-library":
                        merged_libraries.pop(k, None)

            # Apply incoming values for the affected libraries
            for k, v in incoming_libraries.items():
                # Treat empty include/playlist toggles as removal
                if (k.endswith("-library") or k.endswith("-playlist")) and (v in [None, False, "", "false"]):
                    continue
                merged_libraries[k] = v

            # Preserve shared template variables if they weren't part of the payload
            for shared in ("mov-template_variables", "sho-template_variables"):
                if shared in incoming_libraries:
                    merged_libraries[shared] = incoming_libraries[shared]
                elif shared in existing_libraries and shared not in merged_libraries:
                    merged_libraries[shared] = existing_libraries[shared]

            data["libraries"] = merged_libraries

            # Keep previous validated flag and timestamp if caller didn't provide them
            if "validated" not in data and existing_validated is not None:
                data["validated"] = existing_validated
            existing_validated_at = existing_settings.get("validated_at")
            if "validated_at" not in data and existing_validated_at is not None:
                data["validated_at"] = existing_validated_at
        except Exception as e:
            helpers.ts_log(f"Failed to merge libraries during save: {e}", level="ERROR")

    # Ensure a timestamp for pages that validate without explicit validation buttons
    if source_name in ["libraries", "webhooks", "anidb"]:
        existing_validated_at = data.get("validated_at")
        if not existing_validated_at:
            try:
                stored = retrieve_settings(source)
                existing_validated_at = stored.get("validated_at") if isinstance(stored, dict) else None
            except Exception:
                existing_validated_at = None
        if helpers.booler(data.get("validated")) and not existing_validated_at:
            data["validated_at"] = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
        elif existing_validated_at and "validated_at" not in data:
            data["validated_at"] = existing_validated_at

    # Validation
    base_data = get_dummy_data(source_name)
    user_entered = data != base_data
    if source_name == "anidb":
        anidb_enabled = helpers.booler(data.get("anidb", {}).get("enable"))
        if not anidb_enabled:
            data["validated"] = False
            data["validated_at"] = ""
        elif "validated" not in data:
            data["validated"] = user_entered
    validated = data.get("validated", False)
    if source_name == "anidb" and validated and not data.get("validated_at"):
        data["validated_at"] = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")

    # Save to DB
    database.save_section_data(
        name=session["config_name"],
        section=source_name,
        validated=validated,
        user_entered=user_entered,
        data=data,
    )

    if app.config["QS_DEBUG"]:
        helpers.ts_log("Data saved successfully.", level="DEBUG")


def get_stored_plex_credentials(name):
    """Retrieve stored Plex URL & token from the database."""
    try:
        ensure_session_config_name()
        source, source_name = extract_names(name)
        db_data = database.retrieve_section_data(name=session["config_name"], section=source_name)
        payload = db_data[2] if isinstance(db_data, tuple) and len(db_data) >= 3 and isinstance(db_data[2], dict) else {}
        plex_settings = payload.get("plex", {})
        if not plex_settings:
            plex_settings = get_dummy_data("plex")
        plex_url = plex_settings.get("url")  # Correct key inside 'plex'
        plex_token = plex_settings.get("token")  # Correct key inside 'plex'

        if plex_url and plex_token:
            return plex_url, plex_token
        if app.config["QS_DEBUG"]:
            helpers.ts_log("Plex URL or Token is missing in stored settings", level="ERROR")
    except Exception as e:
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Failed to retrieve Plex credentials: {e}", level="ERROR")
    return None, None


def decode_library_ids(value):
    """Decode a stored library-ID list into a list of string IDs.

    Handles three forms:
    - Already a list of dicts  → extract 'id' field from each
    - Already a list           → returned as-is (strings or ints → coerced to str)
    - CSV string of integers   → split on comma (current format)
    - JSON string              → parsed; if it's a list of dicts, extract 'id'
    - Legacy JSON of names     → returned as-is (old pre-ID format; callers
                                 should detect non-integer items and treat as names)
    """
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return [str(item["id"]) for item in value if "id" in item]
        return [str(v) for v in value if v or v == 0]
    if not isinstance(value, str) or not value:
        return []
    try:
        result = json.loads(value)
        if isinstance(result, list):
            if result and isinstance(result[0], dict):
                return [str(item["id"]) for item in result if "id" in item]
            return [str(v) for v in result if v or v == 0]
    except (json.JSONDecodeError, ValueError):
        pass
    return [v for v in value.split(",") if v]


def get_library_names(config_name="010-plex"):
    """Return the stored Plex section-ID → display-name mapping.

    Returns a dict like ``{"10": " Movies L", "3": "TV Shows"}``.
    Keys are string-coerced Plex section IDs.  Returns an empty dict
    when no mapping has been stored yet (fresh install, pre-validation).
    """
    plex_data = retrieve_settings(config_name).get("plex", {})
    raw = plex_data.get("tmp_library_names", "")
    if not raw:
        return {}
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return {str(k): v for k, v in result.items()}
    except (json.JSONDecodeError, ValueError):
        pass
    return {}


def migrate_library_keys_to_plex_ids(config_name, all_plex_libraries):
    """Rekey existing settings from normalised-name keys to Plex section-ID keys.

    Runs once at Plex validation time.  ``all_plex_libraries`` is a flat list
    of ``{"id": int, "name": str}`` dicts covering all library types.

    Returns the number of keys that were renamed (0 = already migrated or
    no matching keys found).
    """
    from modules.helpers._misc import normalize_id, extract_library_name  # local import to avoid circularity

    # Build normalised-name → Plex-ID lookup using the same dedup logic that
    # originally created the keys.
    existing_ids: set = set()
    norm_to_plex_id: dict = {}
    for lib in all_plex_libraries:
        norm = normalize_id(lib["name"].strip(), existing_ids)
        norm_to_plex_id[norm] = str(lib["id"])

    settings = retrieve_settings("025-libraries")
    libraries = settings.get("libraries", {})
    if not libraries:
        return 0

    # Short-circuit: if every library key already uses a numeric ID, skip.
    def _id_is_numeric(key):
        lib_id = extract_library_name(key)
        return lib_id is not None and lib_id.lstrip("-").isdigit()

    keyed_keys = [k for k in libraries if extract_library_name(k) is not None]
    if keyed_keys and all(_id_is_numeric(k) for k in keyed_keys):
        return 0

    new_libraries = {}
    rename_count = 0
    for key, value in libraries.items():
        lib_id = extract_library_name(key)
        if lib_id and lib_id in norm_to_plex_id:
            new_key = key.replace(f"library_{lib_id}-", f"library_{norm_to_plex_id[lib_id]}-", 1)
            new_libraries[new_key] = value
            rename_count += 1
        else:
            new_libraries[key] = value

    if rename_count > 0:
        try:
            database.save_section_data(
                name=config_name,
                section="libraries",
                validated=True,
                user_entered=False,
                data={"libraries": new_libraries},
            )
        except Exception as e:
            helpers.ts_log(f"Library key migration failed: {e}", level="WARNING")
            return 0

    return rename_count


def update_stored_plex_libraries(name, movie_libraries, show_libraries, music_libraries, user_list=None):
    """Update stored Plex cache fields in the database and preserve `validated`.

    ``movie_libraries``, ``show_libraries``, and ``music_libraries`` are lists
    of ``{"id": int|str, "name": str}`` dicts as returned by the Plex validation
    endpoint.  IDs are stored as a simple comma-separated list of integers;
    the display-name lookup is stored as a JSON dict keyed by string ID.
    """
    try:
        # Fetch existing settings from DB before updating
        settings_before = retrieve_settings(name)
        if app.config["QS_DEBUG"]:
            helpers.ts_log("Settings before update:", settings_before, level="DEBUG")

        if "plex" not in settings_before:
            settings_before["plex"] = {}

        # Preserve `validated` status
        validated_before = settings_before.get("validated", True)
        validated_at_before = settings_before.get("validated_at")

        # Store library IDs as simple CSV (integers — no encoding issues).
        # Store the name lookup as a JSON dict so display names are preserved
        # exactly as Plex provides them (leading spaces, commas, etc. all safe).
        # Accept both new format ({id, name} dicts) and legacy format (name strings).
        def _lib_id(lib):
            return lib["id"] if isinstance(lib, dict) else lib

        def _lib_name(lib):
            return lib["name"] if isinstance(lib, dict) else str(lib)

        all_libs = list(movie_libraries) + list(show_libraries) + list(music_libraries)
        name_lookup = {str(_lib_id(lib)): _lib_name(lib) for lib in all_libs}

        settings_before["plex"]["tmp_movie_libraries"] = ",".join(str(_lib_id(lib)) for lib in movie_libraries)
        settings_before["plex"]["tmp_show_libraries"] = ",".join(str(_lib_id(lib)) for lib in show_libraries)
        settings_before["plex"]["tmp_music_libraries"] = ",".join(str(_lib_id(lib)) for lib in music_libraries)
        settings_before["plex"]["tmp_library_names"] = json.dumps(name_lookup)
        if user_list is not None:
            cleaned_users = [str(user).strip() for user in user_list if str(user).strip()]
            settings_before["plex"]["tmp_user_list"] = ",".join(cleaned_users)

        # Convert to a format that `save_settings()` expects
        settings_formatted = settings_before["plex"]  # Pass only the `plex` section

        # Restore `validated` before saving
        settings_formatted["validated"] = validated_before  # Prevents losing validation state
        if validated_at_before:
            settings_formatted["validated_at"] = validated_at_before

        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Sending updated Plex settings to save_settings(): {settings_formatted}", level="DEBUG")

        # Corrected function call (use "010-plex" as the raw_source)
        save_settings("010-plex", settings_formatted)  # Pass only `plex` settings, not full config

        # Fetch updated settings from DB after updating
        settings_after = retrieve_settings(name)
        if app.config["QS_DEBUG"]:
            helpers.ts_log("Settings after update:", settings_after, level="DEBUG")

    except Exception as e:
        helpers.ts_log(f"Failed to update Plex libraries in DB: {e}", level="ERROR")


def retrieve_settings(target):
    ensure_session_config_name()

    # target will be `010-plex`
    data = {}

    # Get source from referrer
    source, source_name = extract_names(target)
    # source will be `010-plex`
    # source_name will be `plex`

    # Fetch stored data from DB
    db_data = database.retrieve_section_data(name=session["config_name"], section=source_name)
    # db_data is a tuple of validated, user_entered, data

    # Extract validation flags
    data["validated"] = helpers.booler(db_data[0])
    data["user_entered"] = helpers.booler(db_data[1])
    data[source_name] = db_data[2].get(source_name, {}) if db_data[2] else {}
    if db_data[2] and isinstance(db_data[2], dict):
        data["validated_at"] = db_data[2].get("validated_at")
    else:
        data["validated_at"] = None

    if not data[source_name]:
        data[source_name] = get_dummy_data(source_name)

    if source_name == "settings" and isinstance(data[source_name], dict):
        asset_directory = data[source_name].get("asset_directory")
        if isinstance(asset_directory, str):
            data[source_name]["asset_directory"] = [line.strip() for line in asset_directory.splitlines() if line.strip()]
        elif isinstance(asset_directory, list):
            data[source_name]["asset_directory"] = [str(item).strip() for item in asset_directory if str(item).strip()]

    if source_name == "trakt":
        section = data[source_name]
        if isinstance(section, dict):
            auth = section.get("authorization")
            if isinstance(auth, dict) and "force_refresh" in auth and "force_refresh" not in section:
                section["force_refresh"] = auth.pop("force_refresh")
            section.setdefault("force_refresh", False)

    if source_name == "plex":
        section = data[source_name]
        if isinstance(section, dict) and "db_cache" in section:
            section["db_cache"] = _normalize_plex_db_cache_value(section.get("db_cache"))

    # Only modify if the target is 'libraries'
    if source_name == "libraries":
        # Ensure mov-template_variables and sho-template_variables are always present
        data[source_name].setdefault("mov-template_variables", {})
        data[source_name].setdefault("sho-template_variables", {})

        # Migrate incorrectly stored flat keys into the correct nested structure
        for key in list(data[source_name].keys()):
            if key.startswith("mov-template_variables[") or key.startswith("sho-template_variables["):
                prefix, variable = key.split("[")
                variable = variable.strip("]")  # Extract 'use_separator' or 'sep_style'
                data[source_name][prefix][variable] = data[source_name].pop(key)

    data["code_verifier"] = secrets.token_urlsafe(100)[:128]
    iso_639_1_languages, iso_3166_1_regions, iso_639_2_languages = _get_iso_reference_lists()
    data["iso_639_1_languages"] = iso_639_1_languages
    data["iso_3166_1_regions"] = iso_3166_1_regions
    data["iso_639_2_languages"] = iso_639_2_languages

    return data


def retrieve_status(target):
    # target will be `010-plex`
    # get source from referrer
    source, source_name = extract_names(target)
    # source will be `010-plex`
    # source_name will be `plex`

    db_data = database.retrieve_section_data(name=session["config_name"], section=source_name)
    # db_data is a tuple of validated, user_entered, data

    validated = helpers.booler(db_data[0])
    user_entered = helpers.booler(db_data[1])

    return validated, user_entered


def get_dummy_data(target):
    """
    Load dummy data from config.yml.template while handling duplicate keys gracefully.
    """

    global _DUMMY_CONFIG_CACHE

    if _DUMMY_CONFIG_CACHE is None:
        yaml = YAML(typ="safe", pure=True)  # Safe loading mode
        helpers.ensure_json_schema()

        try:
            with open(os.path.join(helpers.JSON_SCHEMA_DIR, "config.yml.template"), "r") as file:
                _DUMMY_CONFIG_CACHE = yaml.load(file) or {}
        except DuplicateKeyError as e:
            helpers.ts_log(f"Duplicate key detected in config.yml.template: {e}", level="WARNING")
            _DUMMY_CONFIG_CACHE = {}

    # Return a copy so callers can mutate safely without mutating cache
    return copy.deepcopy(_DUMMY_CONFIG_CACHE.get(target, {}))


def check_minimum_settings():
    plex_valid, plex_user_entered = retrieve_status("plex")
    tmdb_valid, tmdb_user_entered = retrieve_status("tmdb")
    libs_valid, libs_user_entered = retrieve_status("libraries")
    sett_valid, sett_user_entered = retrieve_status("settings")

    return plex_valid, tmdb_valid, libs_valid, sett_valid


def flush_session_storage(name):
    if not name:
        name = session["config_name"]
    [session.pop(key) for key in list(session.keys()) if not key.startswith("config_name")]
    database.reset_data(name)


def notification_systems_available():
    notifiarr_available, notifiarr_user_entered = retrieve_status("notifiarr")
    gotify_available, gotify_user_entered = retrieve_status("gotify")
    ntfy_available, ntfy_user_entered = retrieve_status("ntfy")
    apprise_available, apprise_user_entered = retrieve_status("apprise")

    return notifiarr_available, gotify_available, ntfy_available, apprise_available
