import requests
from flask import Blueprint, Flask, current_app as app, jsonify, request, session

from modules import database, helpers, persistence, url_validation, validations

bp = Blueprint("validation_routes", __name__)


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

    merged = {**plex_data, **telemetry}
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

        # Update stored libraries
        persistence.update_stored_plex_libraries(
            "010-plex",
            plex_data.get("movie_libraries", []),
            plex_data.get("show_libraries", []),
            plex_data.get("music_libraries", []),
            plex_data.get("user_list", []),
        )

        # Get fresh telemetry using helpers and store it
        telemetry = helpers.get_plex_metadata(plex_url=plex_url, plex_token=plex_token)
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


@bp.route("/validate_trakt", methods=["POST"])
def validate_trakt():
    data = request.json
    return validations.validate_trakt_server(data)


@bp.route("/validate_trakt_token", methods=["POST"])
def validate_trakt_token():
    data = request.get_json(silent=True) or {}
    access_token = data.get("access_token")
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    refresh_token = data.get("refresh_token")
    debug_enabled = helpers.booler(app.config.get("QS_DEBUG", False)) or helpers.booler(data.get("debug", False))

    def is_blank(value):
        if value is None:
            return True
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed == "" or trimmed.lower() in ("none", "null"):
                return True
        return False

    if is_blank(access_token) or is_blank(client_id) or is_blank(client_secret) or is_blank(refresh_token):
        settings = persistence.retrieve_settings("130-trakt") or {}
        trakt_data = settings.get("trakt", {}) if isinstance(settings, dict) else {}
        auth = trakt_data.get("authorization", {}) if isinstance(trakt_data, dict) else {}
        if is_blank(access_token):
            access_token = auth.get("access_token")
        if is_blank(client_id):
            client_id = trakt_data.get("client_id") or auth.get("client_id")
        if is_blank(client_secret):
            client_secret = trakt_data.get("client_secret") or auth.get("client_secret")
        if is_blank(refresh_token):
            refresh_token = auth.get("refresh_token")

    if is_blank(access_token) or is_blank(client_id):
        debug_payload = None
        if debug_enabled:
            settings = persistence.retrieve_settings("130-trakt") or {}
            trakt_data = settings.get("trakt", {}) if isinstance(settings, dict) else {}
            auth = trakt_data.get("authorization", {}) if isinstance(trakt_data, dict) else {}
            debug_payload = {
                "config_name": session.get("config_name"),
                "request": {
                    "access_token": not is_blank(data.get("access_token")),
                    "client_id": not is_blank(data.get("client_id")),
                    "client_secret": not is_blank(data.get("client_secret")),
                    "refresh_token": not is_blank(data.get("refresh_token")),
                },
                "stored": {
                    "access_token": not is_blank(auth.get("access_token")),
                    "client_id": not is_blank(trakt_data.get("client_id") or auth.get("client_id")),
                    "client_secret": not is_blank(trakt_data.get("client_secret") or auth.get("client_secret")),
                    "refresh_token": not is_blank(auth.get("refresh_token")),
                },
            }
        response = {"valid": False, "error": "Missing Trakt access token or client ID."}
        if debug_payload:
            response["debug"] = debug_payload
        return jsonify(response), 400
    try:
        response = requests.get(
            "https://api.trakt.tv/users/settings",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
                "trakt-api-version": "2",
                "trakt-api-key": client_id,
            },
            timeout=10,
        )
        if debug_enabled:
            helpers.ts_log(f"Trakt token check status={response.status_code}", level="DEBUG")
        if response.status_code == 200:
            return jsonify({"valid": True})
        if response.status_code == 423:
            return jsonify({"valid": False, "error": "Account is locked; please contact Trakt Support."}), 400
        if response.status_code in (401, 403):
            if is_blank(refresh_token) or is_blank(client_secret):
                return jsonify({"valid": False, "error": "Access token is invalid or expired."}), 400

            refresh_response = requests.post(
                "https://api.trakt.tv/oauth/token",
                json={
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if refresh_response.status_code != 200:
                debug_payload = None
                if debug_enabled:
                    debug_payload = {
                        "status": response.status_code,
                        "refresh_status": refresh_response.status_code,
                    }
                response_body = {"valid": False, "error": "Access token is invalid or expired."}
                if debug_payload:
                    response_body["debug"] = debug_payload
                return jsonify(response_body), 400

            refreshed = refresh_response.json()
            new_access = refreshed.get("access_token")
            if is_blank(new_access):
                return jsonify({"valid": False, "error": "Access token refresh failed."}), 400

            config_name = session.get("config_name") or persistence.ensure_session_config_name()
            stored_validated, user_entered, stored_data = database.retrieve_section_data(config_name, "trakt")
            if not isinstance(stored_data, dict):
                stored_data = {}
            trakt_data = stored_data.get("trakt", {}) if isinstance(stored_data.get("trakt"), dict) else {}
            auth = trakt_data.get("authorization", {}) if isinstance(trakt_data.get("authorization"), dict) else {}
            auth["access_token"] = new_access
            if refreshed.get("refresh_token"):
                auth["refresh_token"] = refreshed.get("refresh_token")
            if refreshed.get("token_type"):
                auth["token_type"] = refreshed.get("token_type")
            if refreshed.get("expires_in"):
                auth["expires_in"] = refreshed.get("expires_in")
            if refreshed.get("scope"):
                auth["scope"] = refreshed.get("scope")
            if refreshed.get("created_at"):
                auth["created_at"] = refreshed.get("created_at")
            trakt_data["authorization"] = auth
            stored_data["trakt"] = trakt_data
            stored_data["validated"] = True
            stored_data["validated_at"] = helpers.utc_now_iso()
            database.save_section_data(
                name=config_name,
                section="trakt",
                validated=True,
                user_entered=user_entered,
                data=stored_data,
            )
            return jsonify({"valid": True, "refreshed": True, "authorization": auth})
        response_body = {"valid": False, "error": f"Trakt validation failed ({response.status_code})."}
        if debug_enabled:
            response_body["debug"] = {"status": response.status_code}
        return jsonify(response_body), 400
    except requests.exceptions.RequestException as exc:
        helpers.ts_log(f"Trakt validation error: {exc}", level="ERROR")
        response_body = {"valid": False, "error": "Trakt validation error."}
        if debug_enabled:
            response_body["debug"] = {"status": "request_exception"}
        return jsonify(response_body), 400


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
    result = validations.validate_radarr_server(data)
    status_code = 200
    if isinstance(result, tuple):
        result, status_code = result

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), status_code or 400


@bp.route("/validate_sonarr", methods=["POST"])
def validate_sonarr():
    data = request.json
    result = validations.validate_sonarr_server(data)
    status_code = 200
    if isinstance(result, tuple):
        result, status_code = result

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), status_code or 400


@bp.route("/validate_omdb", methods=["POST"])
def validate_omdb():
    data = request.json
    result = validations.validate_omdb_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@bp.route("/validate_github", methods=["POST"])
def validate_github():
    data = request.json
    result = validations.validate_github_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@bp.route("/validate_tmdb", methods=["POST"])
def validate_tmdb():
    data = request.json
    result = validations.validate_tmdb_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@bp.route("/validate_mdblist", methods=["POST"])
def validate_mdblist():
    data = request.json
    result = validations.validate_mdblist_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@bp.route("/validate_notifiarr", methods=["POST"])
def validate_notifiarr():
    data = request.json
    result = validations.validate_notifiarr_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400
