"""Service-connectivity validators for external services.

Split out of ``modules.validations`` -- this is the last thematic
cluster remaining, containing 15 ``validate_*_server`` (and 2
``validate_*_payload``) functions that verify Quickstart can talk
to a given external service.  All follow the same shape: pull
credentials from a JSON payload, attempt a real network round-trip,
return a Flask ``jsonify`` response indicating success/failure.

## The service families

* **Plex family** -- direct media-server integration:
  ``validate_plex_server``, ``validate_tautulli_server``,
  ``validate_trakt_server``.
* **Notification services** -- outbound push/webhook:
  ``validate_gotify_server``, ``validate_ntfy_server``,
  ``validate_apprise_server``, ``validate_webhook_server``,
  ``validate_notifiarr_server``.
* **Arr apps** -- Radarr / Sonarr have both a ``*_server`` (Flask
  wrapper) and a ``*_payload`` (plain dict return, used by
  ``quickstart.py`` for auto-population flows):
  ``validate_radarr_server``, ``validate_sonarr_server``,
  ``validate_radarr_payload``, ``validate_sonarr_payload``.
* **Metadata / rating APIs** -- API-key-based lookups:
  ``validate_omdb_server``, ``validate_github_server``,
  ``validate_tmdb_server``, ``validate_mdblist_server``.
* **Anime tracker** -- OAuth PKCE flow:
  ``validate_mal_server``.

## Public API used by external callers

The 15 ``_server`` and 2 ``_payload`` functions are called from:

* ``blueprints/validation_routes.py`` -- primary consumer (16 uses)
* ``blueprints/import_config_routes.py`` -- Plex + TMDb probes during
  YAML config import (7 uses)
* ``quickstart.py`` -- Radarr + Sonarr payload calls (2 uses)

All access via ``modules.validations.<name>`` re-exports, so this
module never needs to be imported directly.

## Shared helper

``_validate_service_url`` centralises the "did the user paste a
sane URL" pre-flight check.  Every validator that takes a URL uses
it before attempting the network call, so consumer-error responses
are consistent.
"""

from __future__ import annotations

import re
from html import unescape
from json import JSONDecodeError

import requests
from flask import jsonify, flash
from plexapi.server import PlexServer

from modules import helpers, url_validation
from modules.validations_yaml_files import _validate_yaml_location

# ---------------------------------------------------------------------------
# Shared helper: URL pre-flight validation
# ---------------------------------------------------------------------------


def _validate_service_url(raw_url, label, allow_local=True):
    if not raw_url:
        return False, f"{label} URL is required."
    valid, message = url_validation.validate_url(raw_url, allow_local=allow_local)
    if not valid:
        return False, f"{label} URL: {message}"
    return True, None


# ---------------------------------------------------------------------------
# Plex family
# ---------------------------------------------------------------------------


def validate_plex_server(data):
    plex_url = data.get("plex_url")
    plex_token = data.get("plex_token")

    ok, msg = _validate_service_url(plex_url, "Plex", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400

    # Validate Plex URL and Token
    try:
        cached = helpers.get_cached_plex_validation(plex_url, plex_token)
        if cached:
            helpers.ts_log("Using cached Plex validation payload.", level="DEBUG")
            return jsonify(cached)

        plex = PlexServer(plex_url, plex_token, timeout=8)

        # Fetch Plex settings
        srv_settings = plex.settings

        # Retrieve db_cache from Plex settings
        db_cache_setting = srv_settings.get("DatabaseCacheSize")

        # Get the value of db_cache
        db_cache = db_cache_setting.value

        # Log db_cache value
        helpers.ts_log(f"db_cache returned from Plex: {db_cache}", level="INFO")

        # If db_cache is None, treat it as invalid.
        if db_cache is None:
            raise Exception("Unable to retrieve db_cache from Plex settings.")

        # Retrieve user list with only usernames
        user_list = [user.title for user in plex.myPlexAccount().users()]
        has_plex_pass = plex.myPlexAccount().subscriptionActive

        helpers.ts_log(f"User list retrieved from Plex: {user_list}", level="INFO")
        helpers.ts_log(f"User has Plex Pass: {has_plex_pass}", level="INFO")

        # Retrieve library sections once. This can be expensive on large Plex servers.
        sections = plex.library.sections()
        music_libraries = [section.title for section in sections if section.type == "artist"]
        movie_libraries = [section.title for section in sections if section.type == "movie"]
        show_libraries = [section.title for section in sections if section.type == "show"]

        helpers.ts_log(f"Music libraries: {music_libraries}", level="INFO")
        helpers.ts_log(f"Movie libraries: {movie_libraries}", level="INFO")
        helpers.ts_log(f"Show libraries: {show_libraries}", level="INFO")

    except Exception as e:
        helpers.ts_log(f"Error validating Plex server: {str(e)}", level="ERROR")
        flash(f"Invalid Plex URL or Token: {str(e)}", "error")
        return jsonify({"valid": False, "error": f"Invalid Plex URL or Token: {str(e)}"})

    # If PlexServer instance is successfully created and db_cache is retrieved, return success response
    payload = {
        "validated": True,
        "db_cache": db_cache,  # Send back the integer value of db_cache
        "user_list": user_list,
        "music_libraries": music_libraries,
        "movie_libraries": movie_libraries,
        "show_libraries": show_libraries,
        "has_plex_pass": has_plex_pass,
    }
    helpers.set_cached_plex_validation(plex_url, plex_token, payload)
    return jsonify(payload)


def validate_tautulli_server(data):
    tautulli_url = data.get("tautulli_url")
    tautulli_apikey = data.get("tautulli_apikey")

    ok, msg = _validate_service_url(tautulli_url, "Tautulli", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400

    api_url = f"{tautulli_url}/api/v2"
    params = {"apikey": tautulli_apikey, "cmd": "get_tautulli_info"}

    try:
        response = requests.get(api_url, params=params, timeout=10)

        # Raise an exception for HTTP errors
        response.raise_for_status()

        data = response.json()

        is_valid = data.get("response", {}).get("result") == "success"
        # Check if the response contains the expected data
        if is_valid:
            helpers.ts_log("Tautulli connection successful.")
        else:
            helpers.ts_log("Tautulli connection failed.")

    except requests.exceptions.RequestException as e:
        helpers.ts_log(f"Error validating Tautulli connection: {e}", level="ERROR")
        flash(f"Invalid Tautulli URL or API Key: {str(e)}", "error")
        return jsonify({"valid": False, "error": f"Invalid Tautulli URL or Apikey: {str(e)}"})

    # return success response
    return jsonify({"valid": is_valid})


def validate_trakt_server(data):
    trakt_client_id = data.get("trakt_client_id")
    trakt_client_secret = data.get("trakt_client_secret")
    trakt_pin = data.get("trakt_pin")

    redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
    base_url = "https://api.trakt.tv"

    try:
        response = requests.post(
            f"{base_url}/oauth/token",
            json={
                "code": trakt_pin,
                "client_id": trakt_client_id,
                "client_secret": trakt_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        if response.status_code != 200:
            return jsonify({"valid": False, "error": "Trakt Error: Invalid trakt pin, client_id, or client_secret."})

        validation_response = requests.get(
            f"{base_url}/users/settings",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {response.json()['access_token']}",
                "trakt-api-version": "2",
                "trakt-api-key": trakt_client_id,
            },
            timeout=10,
        )

        if validation_response.status_code == 423:
            return jsonify({"valid": False, "error": "Account is locked; please contact Trakt Support"})

        return jsonify(
            {
                "valid": True,
                "error": "",
                "trakt_authorization_access_token": response.json()["access_token"],
                "trakt_authorization_token_type": response.json()["token_type"],
                "trakt_authorization_expires_in": response.json()["expires_in"],
                "trakt_authorization_refresh_token": response.json()["refresh_token"],
                "trakt_authorization_scope": response.json()["scope"],
                "trakt_authorization_created_at": response.json()["created_at"],
            }
        )

    except requests.exceptions.RequestException as e:
        helpers.ts_log(f"Error validating Trakt connection: {e}", level="ERROR")
        flash("Invalid Trakt ID, Secret, or PIN.", "error")
        return jsonify({"valid": False, "error": "Invalid Trakt ID, Secret, or PIN."})


# ---------------------------------------------------------------------------
# Notification services
# ---------------------------------------------------------------------------


def validate_gotify_server(data):
    gotify_url = data.get("gotify_url")
    gotify_token = data.get("gotify_token")
    ok, msg = _validate_service_url(gotify_url, "Gotify", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400
    gotify_url = gotify_url.rstrip("#")
    gotify_url = gotify_url.rstrip("/")

    response = requests.get(f"{gotify_url}/version", timeout=10)

    try:
        response_json = response.json()
    except JSONDecodeError:
        status = response.status_code
        content_type = response.headers.get("Content-Type")
        helpers.ts_log(
            f"Gotify validation returned non-JSON response " f"(status={status}, content-type={content_type})",
            level="ERROR",
        )
        return jsonify(
            {
                "valid": False,
                "error": f"Gotify returned a non-JSON response (status {status}). Check the base URL.",
            }
        )

    if response.status_code >= 400:
        return jsonify({"valid": False, "error": f"({response.status_code} [{response.reason}]) {response_json['errorDescription']}"})

    json = {"message": "Kometa Quickstart Test Gotify Message", "title": "Kometa Quickstart Gotify Test"}

    response = requests.post(f"{gotify_url}/message", headers={"X-Gotify-Key": gotify_token}, json=json, timeout=10)

    if response.status_code != 200:
        return jsonify({"valid": False, "error": f"({response.status_code} [{response.reason}]) {response_json['errorDescription']}"})

    return jsonify({"valid": True})


def validate_ntfy_server(data):
    ntfy_url = data.get("ntfy_url")
    ntfy_token = data.get("ntfy_token")
    ntfy_topic = data.get("ntfy_topic")

    ok, msg = _validate_service_url(ntfy_url, "ntfy", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400

    # Ensure the URL is formatted correctly
    ntfy_url = ntfy_url.rstrip("#").rstrip("/")

    headers = {"Content-Type": "text/plain"}
    if ntfy_token:
        headers["Authorization"] = f"Bearer {ntfy_token}"

    test_message = "🔔 Kometa Quickstart Test ntfy Message"

    try:
        # Step 1: Send test notification
        response = requests.post(f"{ntfy_url}/{ntfy_topic}", headers=headers, data=test_message, timeout=10)

        if response.status_code != 200:
            return jsonify({"valid": False, "error": f"Failed to send test message ({response.status_code} [{response.reason}])."})

        # Step 2: Auto-subscribe the sender to the topic
        sub_headers = headers.copy()
        sub_headers["X-Subscriber"] = "true"  # Tell ntfy.sh to subscribe this client

        sub_response = requests.put(f"{ntfy_url}/{ntfy_topic}", headers=sub_headers, timeout=10)

        if sub_response.status_code == 200:
            return jsonify({"valid": True})
        else:
            return jsonify({"valid": False, "error": f"Failed to auto-subscribe ({sub_response.status_code} [{sub_response.reason}])."})

    except requests.RequestException as e:
        return jsonify({"valid": False, "error": f"Connection error: {str(e)}"})


def validate_apprise_server(data):
    apprise_location = str(data.get("apprise_location") or "").strip()
    if not apprise_location:
        return jsonify({"valid": False, "error": "Apprise YAML path or URL is required."}), 400

    valid, message = _validate_yaml_location(apprise_location, "Apprise location")
    if not valid:
        return jsonify({"valid": False, "error": message}), 400

    return jsonify({"valid": True})


def _extract_yamtrack_csrf_token(html):
    if not html:
        return ""
    match = re.search(r'name=["\']csrfmiddlewaretoken["\'][^>]*value=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']csrfmiddlewaretoken["\']', html, re.IGNORECASE)
    return match.group(1) if match else ""


def _extract_yamtrack_version(html):
    if not html:
        return ""

    markup_match = re.search(
        r"\bVersion\s*[:\-]?\s*<[^>]*>\s*(v?[0-9][A-Za-z0-9._+\-]*)\s*<",
        html,
        re.IGNORECASE,
    )
    if markup_match:
        return unescape(markup_match.group(1))

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    patterns = (
        r"\bVersion\s*[:\-]?\s*(v?[0-9][A-Za-z0-9._+\-]*)",
        r"\bYamtrack\s+(v?[0-9][A-Za-z0-9._+\-]*)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _is_yamtrack_login_page(html):
    if not html:
        return False
    lowered = html.lower()
    return "password" in lowered and ("username" in lowered or "csrfmiddlewaretoken" in lowered)


def validate_yamtrack_server(data):
    yamtrack_url = str(data.get("yamtrack_url") or "").strip()
    yamtrack_username = str(data.get("yamtrack_username") or "").strip()
    yamtrack_password = str(data.get("yamtrack_password") or "").strip()

    ok, msg = _validate_service_url(yamtrack_url, "Yamtrack", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400
    if not yamtrack_username:
        return jsonify({"valid": False, "error": "Yamtrack username is required."}), 400
    if not yamtrack_password:
        return jsonify({"valid": False, "error": "Yamtrack password is required."}), 400

    yamtrack_url = yamtrack_url.rstrip("#").rstrip("/")
    session = requests.Session()
    about_paths = ("/settings/about/", "/settings/about")
    login_paths = ("/accounts/login/", "/accounts/login", "/login/", "/login")

    def about_response():
        last_response = None
        for path in about_paths:
            response = session.get(f"{yamtrack_url}{path}", timeout=10)
            last_response = response
            if response.status_code == 200 and not _is_yamtrack_login_page(response.text):
                return response
        return last_response

    def success_payload(response):
        version = _extract_yamtrack_version(response.text)
        return {
            "valid": True,
            "version": version,
            "message": f"Yamtrack connection validated{f' (version {version})' if version else ''}.",
        }

    try:
        response = about_response()
        if response is not None and response.status_code == 200:
            return jsonify(success_payload(response))

        login_response = None
        for path in login_paths:
            login_page = session.get(f"{yamtrack_url}{path}", timeout=10)
            if login_page.status_code >= 500:
                continue
            csrf_token = session.cookies.get("csrftoken") or _extract_yamtrack_csrf_token(login_page.text)
            headers = {"Referer": f"{yamtrack_url}{path}"}
            if csrf_token:
                headers["X-CSRFToken"] = csrf_token
            login_response = session.post(
                f"{yamtrack_url}{path}",
                data={"username": yamtrack_username, "password": yamtrack_password},
                headers=headers,
                timeout=10,
                allow_redirects=True,
            )
            if login_response.status_code >= 400:
                continue
            response = about_response()
            if response is not None and response.status_code == 200:
                return jsonify(success_payload(response))

        status = login_response.status_code if login_response is not None else (response.status_code if response is not None else "unknown")
        return jsonify({"valid": False, "error": f"Unable to validate Yamtrack credentials (status {status})."})
    except requests.RequestException as exc:
        return jsonify({"valid": False, "error": f"Yamtrack connection error: {exc}"})


def validate_webhook_server(data):
    webhook_url = data.get("webhook_url")
    message = data.get("message")

    if not webhook_url:
        return jsonify({"error": "Webhook URL is required"}), 400

    ok, msg = _validate_service_url(webhook_url, "Webhook", allow_local=True)
    if not ok:
        return jsonify({"error": msg}), 400

    message_data = {"content": message}

    response = requests.post(webhook_url, json=message_data, timeout=10)

    if response.status_code == 204:
        return jsonify({"success": "Test message sent successfully! Go and ensure that you see the message on the server side."}), 200
    else:
        return jsonify({"error": f"Failed to send message: {response.status_code}, {response.text}"}), 400


def validate_notifiarr_server(data):
    api_key = data.get("notifiarr_apikey")

    response = requests.get(f"https://notifiarr.com/api/v1/user/validate/{api_key}", timeout=10)
    if response.status_code == 200 and response.json().get("result") == "success":
        return jsonify({"valid": True, "message": "API key is valid!"})
    else:
        return jsonify({"valid": False, "message": "Invalid API key"})


# ---------------------------------------------------------------------------
# Arr apps (Radarr / Sonarr)
# ---------------------------------------------------------------------------


def validate_radarr_server(data):
    result, status_code = validate_radarr_payload(data)
    if not result.get("valid"):
        error = result.get("error")
        if error:
            flash(f"Invalid Radarr URL or API Key: {error}", "error")
    return (jsonify(result), status_code) if status_code != 200 else jsonify(result)


def validate_sonarr_server(data):
    result, status_code = validate_sonarr_payload(data)
    if not result.get("valid"):
        error = result.get("error")
        if error:
            flash(f"Invalid Sonarr URL or API Key: {error}", "error")
    return (jsonify(result), status_code) if status_code != 200 else jsonify(result)


def validate_radarr_payload(data):
    radarr_url = data.get("radarr_url") or data.get("url")
    radarr_apikey = data.get("radarr_token") or data.get("token")

    ok, msg = _validate_service_url(radarr_url, "Radarr", allow_local=True)
    if not ok:
        return {"valid": False, "error": msg}, 400

    status_api_url = f"{radarr_url}/api/v3/system/status?apikey={radarr_apikey}"
    root_folder_api_url = f"{radarr_url}/api/v3/rootfolder?apikey={radarr_apikey}"
    quality_profile_api_url = f"{radarr_url}/api/v3/qualityprofile?apikey={radarr_apikey}"

    try:
        response = requests.get(status_api_url, timeout=10)
        response.raise_for_status()
        status_data = response.json()

        if "version" not in status_data:
            helpers.ts_log("Radarr connection failed. Invalid response data.")
            return {"valid": False, "error": "Invalid Radarr URL or Apikey"}, 200

        response = requests.get(root_folder_api_url, timeout=10)
        response.raise_for_status()
        root_folders = response.json()

        response = requests.get(quality_profile_api_url, timeout=10)
        response.raise_for_status()
        quality_profiles = response.json()

        helpers.ts_log("Radarr connection successful.")
        return {
            "valid": True,
            "root_folders": root_folders,
            "quality_profiles": quality_profiles,
        }, 200
    except requests.exceptions.RequestException as e:
        helpers.ts_log(f"Error validating Radarr connection: {e}", level="ERROR")
        return {"valid": False, "error": f"Invalid Radarr URL or Apikey: {str(e)}"}, 200


def validate_sonarr_payload(data):
    sonarr_url = data.get("sonarr_url") or data.get("url")
    sonarr_apikey = data.get("sonarr_token") or data.get("token")

    ok, msg = _validate_service_url(sonarr_url, "Sonarr", allow_local=True)
    if not ok:
        return {"valid": False, "error": msg}, 400

    status_api_url = f"{sonarr_url}/api/v3/system/status?apikey={sonarr_apikey}"
    root_folder_api_url = f"{sonarr_url}/api/v3/rootfolder?apikey={sonarr_apikey}"
    quality_profile_api_url = f"{sonarr_url}/api/v3/qualityprofile?apikey={sonarr_apikey}"
    language_profile_api_url = f"{sonarr_url}/api/v3/language?apikey={sonarr_apikey}"

    try:
        response = requests.get(status_api_url, timeout=10)
        response.raise_for_status()
        status_data = response.json()

        if "version" not in status_data:
            helpers.ts_log("Sonarr connection failed. Invalid response data.")
            return {"valid": False, "error": "Invalid Sonarr URL or Apikey"}, 200

        response = requests.get(root_folder_api_url, timeout=10)
        response.raise_for_status()
        root_folders = response.json()

        response = requests.get(quality_profile_api_url, timeout=10)
        response.raise_for_status()
        quality_profiles = response.json()

        response = requests.get(language_profile_api_url, timeout=10)
        response.raise_for_status()
        language_profiles = response.json()

        helpers.ts_log("Sonarr connection successful.")
        return {
            "valid": True,
            "root_folders": root_folders,
            "quality_profiles": quality_profiles,
            "language_profiles": language_profiles,
        }, 200
    except requests.exceptions.RequestException as e:
        helpers.ts_log(f"Error validating Sonarr connection: {e}", level="ERROR")
        return {"valid": False, "error": f"Invalid Sonarr URL or Apikey: {str(e)}"}, 200


# ---------------------------------------------------------------------------
# Metadata / rating APIs
# ---------------------------------------------------------------------------


def validate_omdb_server(data):
    omdb_apikey = data.get("omdb_apikey")

    api_url = f"https://www.omdbapi.com/?apikey={omdb_apikey}&s=test"
    try:
        response = requests.get(api_url, timeout=10)
        data = response.json()
        if data.get("Response") == "True" or data.get("Error") == "Movie not found!":
            return jsonify({"valid": True, "message": "OMDb API key is valid"})
        else:
            return jsonify({"valid": False, "message": data.get("Error", "Invalid API key")})
    except Exception as e:
        helpers.ts_log(f"Error validating OMDb connection: {e}", level="ERROR")
        flash(f"Invalid OMDb API Key: {str(e)}", "error")
        return jsonify({"valid": False, "message": str(e)})


def validate_github_server(data):
    github_token = data.get("github_token")

    try:
        response = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=10,
        )
        if response.status_code == 200:
            user_data = response.json()
            return jsonify({"valid": True, "message": f"GitHub token is valid. User: {user_data.get('login')}"})
        else:
            return jsonify({"valid": False, "message": "Invalid GitHub token"}), 400
    except Exception as e:
        return jsonify({"valid": False, "message": str(e)})


def validate_tmdb_server(data):
    api_key = data.get("tmdb_apikey")

    # Validate the API key
    movie_response = requests.get(f"https://api.themoviedb.org/3/movie/550?api_key={api_key}", timeout=10)
    if movie_response.status_code == 200:
        return jsonify({"valid": True, "message": "API key is valid!"})
    else:
        return jsonify({"valid": False, "message": "Invalid API key"})


def validate_mdblist_server(data):
    api_key = data.get("mdblist_apikey")

    response = requests.get(f"https://mdblist.com/api/?apikey={api_key}&s=test", timeout=10)
    if response.status_code == 200 and response.json().get("response") is True:
        return jsonify({"valid": True, "message": "API key is valid!"})
    else:
        return jsonify({"valid": False, "message": "Invalid API key"})


# ---------------------------------------------------------------------------
# Anime tracker (MyAnimeList)
# ---------------------------------------------------------------------------


def validate_mal_server(data):
    mal_client_id = data.get("mal_client_id")
    mal_client_secret = data.get("mal_client_secret")
    mal_code_verifier = data.get("mal_code_verifier")
    mal_localhost_url = data.get("mal_localhost_url")

    match = re.search("code=([^&]+)", str(mal_localhost_url))

    if not match:
        return jsonify({"valid": False, "error": "MAL Error: No required code in localhost URL."})

    new_authorization = requests.post(
        "https://myanimelist.net/v1/oauth2/token",
        data={
            "client_id": mal_client_id,
            "client_secret": mal_client_secret,
            "code": match.group(1),
            "code_verifier": mal_code_verifier,
            "grant_type": "authorization_code",
        },
        timeout=10,
    ).json()

    if "error" in new_authorization:
        return jsonify({"valid": False, "error": "MAL Error: invalid code."})

    # return success response
    return jsonify(
        {
            "valid": True,
            "mal_authorization_access_token": new_authorization["access_token"],
            "mal_authorization_token_type": new_authorization["token_type"],
            "mal_authorization_expires_in": new_authorization["expires_in"],
            "mal_authorization_refresh_token": new_authorization["refresh_token"],
        }
    )
