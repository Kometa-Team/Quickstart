import re
import urllib.parse
import re
from json import JSONDecodeError

import requests
from flask import current_app as app
from flask import jsonify, flash
from plexapi.server import PlexServer

from modules import iso, helpers, url_validation

GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


def validate_iso3166_1(code):
    try:
        return iso.get_country(alpha2=code, alpha3=code).alpha2
    except (NameError, ValueError):
        return None


def validate_iso639_1(code):
    try:
        return iso.get_language(alpha2=code, alpha3=code).alpha2
    except (NameError, ValueError):
        return None


def _validate_service_url(raw_url, label, allow_local=True):
    if not raw_url:
        return False, f"{label} URL is required."
    valid, message = url_validation.validate_url(raw_url, allow_local=allow_local)
    if not valid:
        return False, f"{label} URL: {message}"
    return True, None


def validate_plex_server(data):
    plex_url = data.get("plex_url")
    plex_token = data.get("plex_token")

    ok, msg = _validate_service_url(plex_url, "Plex", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400

    # Validate Plex URL and Token
    try:
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

        # Retrieve library sections
        music_libraries = [section.title for section in plex.library.sections() if section.type == "artist"]
        movie_libraries = [section.title for section in plex.library.sections() if section.type == "movie"]
        show_libraries = [section.title for section in plex.library.sections() if section.type == "show"]

        helpers.ts_log(f"Music libraries: {music_libraries}", level="INFO")
        helpers.ts_log(f"Movie libraries: {movie_libraries}", level="INFO")
        helpers.ts_log(f"Show libraries: {show_libraries}", level="INFO")

        plex_version = getattr(plex, "version", None)

    except Exception as e:
        helpers.ts_log(f"Error validating Plex server: {str(e)}", level="ERROR")
        flash(f"Invalid Plex URL or Token: {str(e)}", "error")
        return jsonify({"valid": False, "error": f"Invalid Plex URL or Token: {str(e)}"})

    # If PlexServer instance is successfully created and db_cache is retrieved, return success response
    return jsonify(
        {
            "validated": True,
            "db_cache": db_cache,  # Send back the integer value of db_cache
            "user_list": user_list,
            "music_libraries": music_libraries,
            "movie_libraries": movie_libraries,
            "show_libraries": show_libraries,
            "has_plex_pass": has_plex_pass,
            "plex_version": plex_version,
        }
    )


def validate_tautulli_server(data):
    tautulli_url = data.get("tautulli_url")
    tautulli_apikey = data.get("tautulli_apikey")

    ok, msg = _validate_service_url(tautulli_url, "Tautulli", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400

    api_url = f"{tautulli_url}/api/v2"
    params = {"apikey": tautulli_apikey, "cmd": "get_tautulli_info"}

    try:
        response = requests.get(api_url, params=params)

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
    tautulli_version = None
    if isinstance(data, dict):
        info = data.get("response", {}).get("data", {})
        if isinstance(info, dict):
            tautulli_version = info.get("tautulli_version") or info.get("version")

    return jsonify({"valid": is_valid, "tautulli_version": tautulli_version})


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
                "trakt_version": "v2",
            }
        )

    except requests.exceptions.RequestException as e:
        helpers.ts_log(f"Error validating Trakt connection: {e}", level="ERROR")
        flash("Invalid Trakt ID, Secret, or PIN.", "error")
        return jsonify({"valid": False, "error": "Invalid Trakt ID, Secret, or PIN."})


def validate_gotify_server(data):
    gotify_url = data.get("gotify_url")
    gotify_token = data.get("gotify_token")
    ok, msg = _validate_service_url(gotify_url, "Gotify", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400
    gotify_url = gotify_url.rstrip("#")
    gotify_url = gotify_url.rstrip("/")

    response = requests.get(f"{gotify_url}/version")

    try:
        response_json = response.json()
    except JSONDecodeError as e:
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

    gotify_version = None
    if isinstance(response_json, dict):
        gotify_version = response_json.get("version") or response_json.get("tag") or response_json.get("Version")

    json = {"message": "Kometa Quickstart Test Gotify Message", "title": "Kometa Quickstart Gotify Test"}

    response = requests.post(f"{gotify_url}/message", headers={"X-Gotify-Key": gotify_token}, json=json)

    if response.status_code != 200:
        return jsonify({"valid": False, "error": f"({response.status_code} [{response.reason}]) {response_json['errorDescription']}"})

    return jsonify({"valid": True, "gotify_version": gotify_version})


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
        response = requests.post(f"{ntfy_url}/{ntfy_topic}", headers=headers, data=test_message)

        if response.status_code != 200:
            return jsonify({"valid": False, "error": f"Failed to send test message ({response.status_code} [{response.reason}])."})
        helpers.ts_log(
            f"ntfy publish server-header={response.headers.get('Server')}",
            level="DEBUG",
        )

        # Step 2: Auto-subscribe the sender to the topic
        sub_headers = headers.copy()
        sub_headers["X-Subscriber"] = "true"  # Tell ntfy.sh to subscribe this client

        sub_response = requests.put(f"{ntfy_url}/{ntfy_topic}", headers=sub_headers)

        def fetch_ntfy_version(base_url, token=None):
            try:
                def extract_version_from_text(text):
                    if not text:
                        return None
                    match = re.search(r'"version"\s*:\s*"([^"]+)"', text)
                    if match:
                        return match.group(1).strip()
                    return None

                def extract_version(info_response):
                    if info_response.status_code != 200:
                        return None
                    try:
                        info_json = info_response.json()
                    except Exception:
                        info_json = None
                    if isinstance(info_json, dict):
                        version = info_json.get("version")
                        if isinstance(version, str) and version.strip():
                            return version.strip()
                    return extract_version_from_text(getattr(info_response, "text", ""))
                    return None

                def build_headers(with_token):
                    merged = {"Accept": "application/json"}
                    if with_token and token:
                        merged["Authorization"] = f"Bearer {token}"
                    return merged

                info_url = f"{base_url}/v1/info"
                info_response = requests.get(
                    f"{base_url}/v1/info",
                    headers=build_headers(with_token=True),
                    timeout=10,
                )
                helpers.ts_log(
                    f"ntfy /v1/info url={info_url} status={info_response.status_code} content-type={info_response.headers.get('Content-Type')} "
                    f"body={str(getattr(info_response, 'text', '')).strip()[:500]}",
                    level="DEBUG",
                )
                version = extract_version(info_response)
                if version:
                    return version
                if token:
                    fallback_response = requests.get(
                        info_url,
                        headers=build_headers(with_token=False),
                        timeout=10,
                    )
                    helpers.ts_log(
                        f"ntfy /v1/info fallback url={info_url} status={fallback_response.status_code} content-type={fallback_response.headers.get('Content-Type')} "
                        f"body={str(getattr(fallback_response, 'text', '')).strip()[:500]}",
                        level="DEBUG",
                    )
                    return extract_version(fallback_response)
            except Exception:
                pass
            return None

        def extract_ntfy_version(*responses):
            for resp in responses:
                if not resp:
                    continue
                server_header = resp.headers.get("Server") or resp.headers.get("server")
                if not server_header:
                    server_header = ""
                for token in server_header.replace(";", " ").split():
                    if token.lower().startswith("ntfy/"):
                        return token.split("/", 1)[1]
                for header_value in resp.headers.values():
                    if not header_value or not isinstance(header_value, str):
                        continue
                    for token in header_value.replace(";", " ").split():
                        if token.lower().startswith("ntfy/"):
                            return token.split("/", 1)[1]
            return None

        ntfy_version = fetch_ntfy_version(ntfy_url, token=ntfy_token) or extract_ntfy_version(response, sub_response)
        if not ntfy_version:
            ntfy_version = "N/A"

        if sub_response.status_code == 200:
            return jsonify({"valid": True, "ntfy_version": ntfy_version})
        else:
            return jsonify({"valid": False, "error": f"Failed to auto-subscribe ({sub_response.status_code} [{sub_response.reason}])."})

    except requests.RequestException as e:
        return jsonify({"valid": False, "error": f"Connection error: {str(e)}"})


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
            "mal_version": "v2",
        }
    )


def validate_webhook_server(data):
    webhook_url = data.get("webhook_url")
    message = data.get("message")

    if not webhook_url:
        return jsonify({"error": "Webhook URL is required"}), 400

    ok, msg = _validate_service_url(webhook_url, "Webhook", allow_local=True)
    if not ok:
        return jsonify({"error": msg}), 400

    message_data = {"content": message}

    response = requests.post(webhook_url, json=message_data)

    if response.status_code == 204:
        return jsonify({"success": "Test message sent successfully! Go and ensure that you see the message on the server side."}), 200
    else:
        return jsonify({"error": f"Failed to send message: {response.status_code}, {response.text}"}), 400


def validate_radarr_server(data):
    radarr_url = data.get("radarr_url")
    radarr_apikey = data.get("radarr_token")

    ok, msg = _validate_service_url(radarr_url, "Radarr", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400

    status_api_url = f"{radarr_url}/api/v3/system/status?apikey={radarr_apikey}"
    root_folder_api_url = f"{radarr_url}/api/v3/rootfolder?apikey={radarr_apikey}"
    quality_profile_api_url = f"{radarr_url}/api/v3/qualityprofile?apikey={radarr_apikey}"

    try:
        # Validate API key by checking system status
        response = requests.get(status_api_url)
        response.raise_for_status()
        status_data = response.json()

        if "version" not in status_data:
            helpers.ts_log("Radarr connection failed. Invalid response data.")
            return jsonify({"valid": False, "error": "Invalid Radarr URL or Apikey"})

        radarr_version = status_data.get("version")

        # Fetch root folders
        response = requests.get(root_folder_api_url)
        response.raise_for_status()
        root_folders = response.json()

        # Fetch quality profiles
        response = requests.get(quality_profile_api_url)
        response.raise_for_status()
        quality_profiles = response.json()

        helpers.ts_log("Radarr connection successful.")

        return jsonify(
            {
                "valid": True,
                "root_folders": root_folders,
                "quality_profiles": quality_profiles,
                "radarr_version": radarr_version,
            }
        )

    except requests.exceptions.RequestException as e:
        helpers.ts_log("Error validating Radarr connection: {e}", level="ERROR")
        flash(f"Invalid Radarr URL or API Key: {str(e)}", "error")
        return jsonify({"valid": False, "error": f"Invalid Radarr URL or Apikey: {str(e)}"})


def validate_sonarr_server(data):
    sonarr_url = data.get("sonarr_url")
    sonarr_apikey = data.get("sonarr_token")

    ok, msg = _validate_service_url(sonarr_url, "Sonarr", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400

    status_api_url = f"{sonarr_url}/api/v3/system/status?apikey={sonarr_apikey}"
    root_folder_api_url = f"{sonarr_url}/api/v3/rootfolder?apikey={sonarr_apikey}"
    quality_profile_api_url = f"{sonarr_url}/api/v3/qualityprofile?apikey={sonarr_apikey}"
    language_profile_api_url = f"{sonarr_url}/api/v3/language?apikey={sonarr_apikey}"

    try:
        # Validate API key by checking system status
        response = requests.get(status_api_url)
        response.raise_for_status()
        status_data = response.json()

        if "version" not in status_data:
            helpers.ts_log("Sonarr connection failed. Invalid response data.")
            return jsonify({"valid": False, "error": "Invalid Sonarr URL or Apikey"})

        sonarr_version = status_data.get("version")

        # Fetch root folders
        response = requests.get(root_folder_api_url)
        response.raise_for_status()
        root_folders = response.json()

        # Fetch quality profiles
        response = requests.get(quality_profile_api_url)
        response.raise_for_status()
        quality_profiles = response.json()

        # Fetch quality profiles
        response = requests.get(language_profile_api_url)
        response.raise_for_status()
        language_profiles = response.json()

        helpers.ts_log("Sonarr connection successful.")

        return jsonify(
            {
                "valid": True,
                "root_folders": root_folders,
                "quality_profiles": quality_profiles,
                "language_profiles": language_profiles,
                "sonarr_version": sonarr_version,
            }
        )

    except requests.exceptions.RequestException as e:
        helpers.ts_log(f"Error validating Sonarr connection: {e}", level="ERROR")
        flash(f"Invalid Sonarr URL or API Key: {str(e)}", "error")
        return jsonify({"valid": False, "error": f"Invalid Sonarr URL or Apikey: {str(e)}"})


def validate_omdb_server(data):
    omdb_apikey = data.get("omdb_apikey")

    api_url = f"https://www.omdbapi.com/?apikey={omdb_apikey}&s=test"
    try:
        response = requests.get(api_url)
        data = response.json()
        if data.get("Response") == "True" or data.get("Error") == "Movie not found!":
            omdb_version = data.get("Version") or data.get("version") or response.headers.get("X-API-Version") or response.headers.get("X-Api-Version")
            if not omdb_version:
                omdb_version = "N/A"
            return jsonify({"valid": True, "message": "OMDb API key is valid", "omdb_version": omdb_version})
        else:
            return jsonify({"valid": False, "message": data.get("Error", "Invalid API key")})
    except Exception as e:
        helpers.ts_log(f"Error validating OMDb connection: {e}", level="ERROR")
        flash(f"Invalid OMDb API Key: {str(e)}", "error")
        return jsonify({"valid": False, "message": str(e)})


def validate_github_server(data):
    github_token = data.get("github_token")

    try:
        version_headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
        github_version = None
        try:
            versions_response = requests.get(f"{GITHUB_API}/versions", headers=version_headers, timeout=10)
            if versions_response.status_code == 200:
                github_version = versions_response.headers.get("X-GitHub-Api-Version")
        except requests.RequestException:
            github_version = None

        response = requests.get(
            f"{GITHUB_API}/user",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
            timeout=10,
        )
        if response.status_code == 200:
            user_data = response.json()
            if not github_version:
                github_version = response.headers.get("X-GitHub-Api-Version") or response.headers.get("X-API-Version-Selected")
            if not github_version:
                github_version = GITHUB_API_VERSION
            if not github_version:
                github_version = "N/A"
            return jsonify(
                {
                    "valid": True,
                    "message": f"GitHub token is valid. User: {user_data.get('login')}",
                    "github_version": github_version,
                }
            )
        else:
            return jsonify({"valid": False, "message": "Invalid GitHub token"}), 400
    except Exception as e:
        return jsonify({"valid": False, "message": str(e)})


def validate_tmdb_server(data):
    api_key = data.get("tmdb_apikey")

    # Validate the API key
    movie_response = requests.get(f"https://api.themoviedb.org/3/movie/550?api_key={api_key}")
    if movie_response.status_code == 200:
        return jsonify({"valid": True, "message": "API key is valid!", "tmdb_version": "v3"})
    else:
        return jsonify({"valid": False, "message": "Invalid API key"})


def validate_mdblist_server(data):
    api_key = data.get("mdblist_apikey")

    response = requests.get(f"https://mdblist.com/api/?apikey={api_key}&s=test")
    response_data = {}
    try:
        response_data = response.json()
    except ValueError:
        response_data = {}
    if response.status_code == 200 and response_data.get("response") is True:
        mdblist_version = response_data.get("version") or response_data.get("api_version")
        if not mdblist_version:
            mdblist_version = "N/A"
        return jsonify({"valid": True, "message": "API key is valid!", "mdblist_version": mdblist_version})
    else:
        return jsonify({"valid": False, "message": "Invalid API key"})


def validate_notifiarr_server(data):
    api_key = data.get("notifiarr_apikey")

    response = requests.get(f"https://notifiarr.com/api/v1/user/validate/{api_key}")
    response_data = {}
    if response.status_code == 200:
        try:
            response_data = response.json()
        except ValueError:
            response_data = {}
    if response.status_code == 200 and response_data.get("result") == "success":
        notifiarr_version = None
        if isinstance(response_data, dict):
            notifiarr_version = response_data.get("version") or response_data.get("build") or response_data.get("serverVersion")
        if not notifiarr_version:
            notifiarr_version = "N/A"
        return jsonify({"valid": True, "message": "API key is valid!", "notifiarr_version": notifiarr_version})
    else:
        return jsonify({"valid": False, "message": "Invalid API key"})
