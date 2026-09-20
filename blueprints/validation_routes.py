import requests
from flask import Blueprint, Flask, current_app as app, jsonify, request, session

from modules import database, helpers, persistence, url_validation, validations

bp = Blueprint("validation_routes", __name__)


def _telemetry_with_validated_plex_pass(telemetry, plex_data):
    """Keep Libraries telemetry aligned with the authoritative Plex validation result."""
    normalized = dict(telemetry) if isinstance(telemetry, dict) else {}
    if isinstance(plex_data, dict) and "has_plex_pass" in plex_data:
        normalized["plex_pass"] = bool(plex_data.get("has_plex_pass"))
    return normalized


def _unpack_validation_result(result):
    """Normalise a validator return value into ``(flask_response, status_code)``.

    Validator functions in ``modules.validations`` may return either:

    * ``jsonify(payload)`` -- a plain Flask ``Response`` (the common case).
    * ``(jsonify(payload), status_code)`` -- a tuple (used when the validator
      wants to signal a specific HTTP status, e.g. 400 for a bad URL).

    Both are valid Flask view-return values when returned *directly*, but when
    a route needs to *inspect* the payload first (to decide whether to re-emit
    the body with a different status code), it must unpack consistently.
    Without this helper, routes that call ``result.get_json()`` crash with
    ``AttributeError: 'tuple' object has no attribute 'get_json'`` whenever
    the underlying validator returns a tuple.

    ``status_code`` defaults to 200 for plain responses so callers can always
    use ``status_code or 400`` as the fallback error status.
    """
    if isinstance(result, tuple):
        return result[0], int(result[1])
    return result, None  # caller uses ``status_code or 400`` -- None keeps the fallback working


@bp.route("/validate_gotify", methods=["POST"])
def validate_gotify():
    data = request.get_json(silent=True) or {}
    valid, message = url_validation.validate_url(data.get("gotify_url"), allow_local=True)
    if not valid:
        return jsonify({"valid": False, "error": f"Gotify URL: {message}"}), 400
    return validations.validate_gotify_server(data)


@bp.route("/validate_ntfy", methods=["POST"])
def validate_ntfy():
    data = request.get_json(silent=True) or {}
    valid, message = url_validation.validate_url(data.get("ntfy_url"), allow_local=True)
    if not valid:
        return jsonify({"valid": False, "error": f"ntfy URL: {message}"}), 400
    return validations.validate_ntfy_server(data)


@bp.route("/validate_apprise", methods=["POST"])
def validate_apprise():
    data = request.get_json(silent=True) or {}
    return validations.validate_apprise_server(data)


@bp.route("/validate_yamtrack", methods=["POST"])
def validate_yamtrack():
    data = request.get_json(silent=True) or {}
    valid, message = url_validation.validate_url(data.get("yamtrack_url"), allow_local=True)
    if not valid:
        return jsonify({"valid": False, "error": f"Yamtrack URL: {message}"}), 400
    return validations.validate_yamtrack_server(data)


@bp.route("/validate_overlay_source_override", methods=["POST"])
def validate_overlay_source_override():
    data = request.get_json(silent=True) or {}
    return validations.validate_overlay_source_override_server(data)


@bp.route("/overlay-source-make-local", methods=["POST"])
def overlay_source_make_local():
    data = request.get_json(silent=True) or {}
    return validations.make_overlay_source_override_local_server(data)


@bp.route("/overlay-source-cleanup", methods=["POST"])
def overlay_source_cleanup():
    data = request.get_json(silent=True) or {}
    return validations.cleanup_overlay_source_override_server(data)


@bp.route("/validate_plex", methods=["POST"])
def validate_plex():
    data = request.get_json(silent=True) or {}
    valid, message = url_validation.validate_url(data.get("plex_url"), allow_local=True)
    if not valid:
        return jsonify({"valid": False, "error": f"Plex URL: {message}"}), 400
    plex_response = validations.validate_plex_server(data)
    plex_data = plex_response.get_json() if isinstance(plex_response, Flask.response_class) else plex_response
    if not isinstance(plex_data, dict) or not plex_data.get("validated"):
        return plex_response

    config_name = persistence.resolve_request_config_name(data)
    telemetry = {}
    try:
        telemetry = helpers.get_plex_metadata(plex_url=data.get("plex_url"), plex_token=data.get("plex_token")) or {}
        if telemetry:
            telemetry = _telemetry_with_validated_plex_pass(telemetry, plex_data)
            persistence.save_settings("plex_telemetry", telemetry)
            if config_name:
                try:
                    database.save_section_data(
                        name=config_name,
                        section="plex_telemetry",
                        validated=True,
                        user_entered=False,
                        data={"plex_telemetry": telemetry},
                    )
                except Exception as e:
                    helpers.ts_log(f"Failed to persist Plex telemetry during validation for {config_name}: {e}", level="WARNING")
    except Exception as e:
        helpers.ts_log(f"Failed to fetch Plex telemetry during validation: {e}", level="WARNING")

    # Migrate existing library settings from name-based keys to Plex-ID keys.
    all_libs = list(plex_data.get("movie_libraries") or []) + list(plex_data.get("show_libraries") or []) + list(plex_data.get("music_libraries") or [])
    if config_name and all_libs and isinstance(all_libs[0], dict):
        try:
            persistence.migrate_library_keys_to_plex_ids(config_name, all_libs)
        except Exception as e:
            helpers.ts_log(f"Library key migration failed during validate_plex: {e}", level="WARNING")
    try:
        persistence.update_stored_plex_libraries(
            "010-plex",
            plex_data.get("movie_libraries", []),
            plex_data.get("show_libraries", []),
            plex_data.get("music_libraries", []),
            plex_data.get("user_list", []),
        )
    except Exception as e:
        helpers.ts_log(f"Failed to persist Plex library lists during validation: {e}", level="WARNING")

    # Keep validator fields authoritative for the Plex page contract. Telemetry
    # uses display strings like "2048 MB", while the page's db_cache input needs
    # the numeric value returned by validate_plex_server.
    merged = {**telemetry, **plex_data}
    return jsonify(merged)


@bp.route("/refresh_plex_libraries", methods=["POST"])
def refresh_plex_libraries():
    try:
        config_name = session.get("config_name")
        if not config_name:
            return jsonify({"valid": False, "error": "Missing config_name"}), 400

        # Get stored Plex credentials
        plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")
        dummy = persistence.get_dummy_data("plex")
        default_plex_url = dummy.get("url", "")
        default_plex_token = dummy.get("token", "")

        # Validate credentials
        if not plex_url or not plex_token or plex_url == default_plex_url or plex_token == default_plex_token:
            return (
                jsonify(
                    {
                        "valid": False,
                        "error": "Plex credentials are using default placeholder values",
                    }
                ),
                400,
            )

        cached_refresh = helpers.get_cached_plex_refresh(plex_url, plex_token)
        if cached_refresh:
            helpers.ts_log("Using cached Plex library refresh payload.", level="DEBUG")
            cached_refresh = dict(cached_refresh)
            if "has_plex_pass" in cached_refresh:
                cached_refresh["plex_pass"] = bool(cached_refresh.get("has_plex_pass"))
            all_libs = list(cached_refresh.get("movie_libraries") or []) + list(cached_refresh.get("show_libraries") or []) + list(cached_refresh.get("music_libraries") or [])
            if all_libs and isinstance(all_libs[0], dict):
                persistence.migrate_library_keys_to_plex_ids(config_name, all_libs)
            persistence.update_stored_plex_libraries(
                "010-plex",
                cached_refresh.get("movie_libraries", []),
                cached_refresh.get("show_libraries", []),
                cached_refresh.get("music_libraries", []),
                cached_refresh.get("user_list", []),
            )
            cached_telemetry = {
                key: value
                for key, value in cached_refresh.items()
                if key
                not in {
                    "validated",
                    "user_list",
                    "music_libraries",
                    "movie_libraries",
                    "show_libraries",
                    "has_plex_pass",
                }
            }
            cached_telemetry = _telemetry_with_validated_plex_pass(cached_telemetry, cached_refresh)
            persistence.save_settings("plex_telemetry", cached_telemetry)
            try:
                database.save_section_data(
                    name=config_name,
                    section="plex_telemetry",
                    validated=True,
                    user_entered=False,
                    data={"plex_telemetry": cached_telemetry},
                )
            except Exception as e:
                helpers.ts_log(f"Failed to persist cached Plex telemetry for {config_name}: {e}", level="WARNING")
            return jsonify(cached_refresh)

        # Validate Plex server and get updated libraries
        plex_response = validations.validate_plex_server({"plex_url": plex_url, "plex_token": plex_token})
        plex_data = plex_response.get_json() if isinstance(plex_response, Flask.response_class) else plex_response

        if not plex_data.get("validated"):
            return jsonify({"valid": False, "error": "Plex validation failed"}), 500

        # Migrate existing settings from name-based keys to Plex-ID keys, then store.
        all_libs = list(plex_data.get("movie_libraries") or []) + list(plex_data.get("show_libraries") or []) + list(plex_data.get("music_libraries") or [])
        if all_libs and isinstance(all_libs[0], dict):
            persistence.migrate_library_keys_to_plex_ids(config_name, all_libs)
        persistence.update_stored_plex_libraries(
            "010-plex",
            plex_data.get("movie_libraries", []),
            plex_data.get("show_libraries", []),
            plex_data.get("music_libraries", []),
            plex_data.get("user_list", []),
        )

        # Get fresh telemetry using helpers and store it
        telemetry = helpers.get_plex_metadata(plex_url=plex_url, plex_token=plex_token)
        telemetry = _telemetry_with_validated_plex_pass(telemetry, plex_data)
        persistence.save_settings("plex_telemetry", telemetry)
        try:
            database.save_section_data(
                name=config_name,
                section="plex_telemetry",
                validated=True,
                user_entered=False,
                data={"plex_telemetry": telemetry},
            )
        except Exception as e:
            helpers.ts_log(f"Failed to persist Plex telemetry for {config_name}: {e}", level="WARNING")

        # Merge both plex_data and telemetry for response
        merged_response = {**plex_data, **telemetry}
        helpers.set_cached_plex_refresh(plex_url, plex_token, merged_response)

        return jsonify(merged_response)

    except Exception as e:
        helpers.ts_log(f"Plex validation failed: {e}", level="ERROR")
        return jsonify({"valid": False, "error": "Server error."}), 500


@bp.route("/validate_tautulli", methods=["POST"])
def validate_tautulli():
    data = request.json
    return validations.validate_tautulli_server(data)


@bp.route("/validate_tracearr", methods=["POST"])
def validate_tracearr():
    data = request.json
    return validations.validate_tracearr_server(data)


@bp.route("/validate_trakt", methods=["POST"])
def validate_trakt():
    return jsonify({"valid": False, "error": "Trakt support was removed in Kometa 2.4.9. Use MDBList, SIMKL, FlickList, TMDb, or IMDb instead."}), 410


@bp.route("/import_trakt_yaml", methods=["POST"])
def import_trakt_yaml():
    return jsonify({"valid": False, "error": "Trakt support was removed in Kometa 2.4.9. Use MDBList, SIMKL, FlickList, TMDb, or IMDb instead."}), 410


@bp.route("/validate_trakt_token", methods=["POST"])
def validate_trakt_token():
    return jsonify({"valid": False, "error": "Trakt support was removed in Kometa 2.4.9. Use MDBList, SIMKL, FlickList, TMDb, or IMDb instead."}), 410


@bp.route("/validate_mal", methods=["POST"])
def validate_mal():
    data = request.json
    return validations.validate_mal_server(data)


@bp.route("/validate_mal_token", methods=["POST"])
def validate_mal_token():
    data = request.get_json(silent=True) or {}
    access_token = data.get("access_token")
    debug_enabled = helpers.booler(app.config.get("QS_DEBUG", False)) or helpers.booler(data.get("debug", False))

    def is_blank(value):
        if value is None:
            return True
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed == "" or trimmed.lower() in ("none", "null"):
                return True
        return False

    if is_blank(access_token):
        settings = persistence.retrieve_settings("140-mal") or {}
        mal_data = settings.get("mal", {}) if isinstance(settings, dict) else {}
        auth = mal_data.get("authorization", {}) if isinstance(mal_data, dict) else {}
        access_token = auth.get("access_token")

    if is_blank(access_token):
        debug_payload = None
        if debug_enabled:
            settings = persistence.retrieve_settings("140-mal") or {}
            mal_data = settings.get("mal", {}) if isinstance(settings, dict) else {}
            auth = mal_data.get("authorization", {}) if isinstance(mal_data.get("authorization"), dict) else {}
            debug_payload = {
                "config_name": session.get("config_name"),
                "request": {"access_token": not is_blank(data.get("access_token"))},
                "stored": {"access_token": not is_blank(auth.get("access_token"))},
            }
        response = {"valid": False, "error": "Missing MyAnimeList access token."}
        if debug_payload:
            response["debug"] = debug_payload
        return jsonify(response), 400
    try:
        response = requests.get(
            "https://api.myanimelist.net/v2/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if response.status_code == 200:
            return jsonify({"valid": True})
        if response.status_code in (401, 403):
            return jsonify({"valid": False, "error": "Access token is invalid or expired."}), 400
        return jsonify({"valid": False, "error": f"MyAnimeList validation failed ({response.status_code})."}), 400
    except requests.exceptions.RequestException as exc:
        helpers.ts_log(f"MyAnimeList validation error: {exc}", level="ERROR")
        return jsonify({"valid": False, "error": "MyAnimeList validation error."}), 400


@bp.route("/validate_webhook", methods=["POST"])
def validate_webhook():
    data = request.json
    return validations.validate_webhook_server(data)


@bp.route("/validate_radarr", methods=["POST"])
def validate_radarr():
    data = request.json
    result, status_code = _unpack_validation_result(validations.validate_radarr_server(data))
    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    return jsonify(result.get_json()), status_code or 400


@bp.route("/validate_sonarr", methods=["POST"])
def validate_sonarr():
    data = request.json
    result, status_code = _unpack_validation_result(validations.validate_sonarr_server(data))
    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    return jsonify(result.get_json()), status_code or 400


@bp.route("/validate_omdb", methods=["POST"])
def validate_omdb():
    data = request.json
    result, status_code = _unpack_validation_result(validations.validate_omdb_server(data))
    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    return jsonify(result.get_json()), status_code or 400


@bp.route("/validate_github", methods=["POST"])
def validate_github():
    data = request.json
    result, status_code = _unpack_validation_result(validations.validate_github_server(data))
    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    return jsonify(result.get_json()), status_code or 400


@bp.route("/validate_tmdb", methods=["POST"])
def validate_tmdb():
    data = request.json
    result, status_code = _unpack_validation_result(validations.validate_tmdb_server(data))
    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    return jsonify(result.get_json()), status_code or 400


@bp.route("/validate_mdblist", methods=["POST"])
def validate_mdblist():
    data = request.json
    result, status_code = _unpack_validation_result(validations.validate_mdblist_server(data))
    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    return jsonify(result.get_json()), status_code or 400


@bp.route("/validate_notifiarr", methods=["POST"])
def validate_notifiarr():
    data = request.json
    result, status_code = _unpack_validation_result(validations.validate_notifiarr_server(data))
    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    return jsonify(result.get_json()), status_code or 400


@bp.route("/validate_serializd", methods=["POST"])
def validate_serializd():
    data = request.get_json(silent=True) or {}
    result, status_code = _unpack_validation_result(validations.validate_serializd_server(data))
    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    return jsonify(result.get_json()), status_code or 400


@bp.route("/validate_floppy", methods=["POST"])
def validate_floppy():
    data = request.get_json(silent=True) or {}
    result, status_code = _unpack_validation_result(validations.validate_floppy_server(data))
    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    return jsonify(result.get_json()), status_code or 400
