import re
import urllib.parse
from json import JSONDecodeError

import requests
from flask import current_app as app
from flask import jsonify, flash
from plexapi.server import PlexServer

from modules import iso


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


def validate_plex_server(data):
    plex_url = data.get("plex_url")
    plex_token = data.get("plex_token")

    # Validate Plex URL and Token
    try:
        plex = PlexServer(plex_url, plex_token)

        # Fetch Plex settings
        srv_settings = plex.settings

        # Retrieve db_cache from Plex settings
        db_cache_setting = srv_settings.get("DatabaseCacheSize")

        # Get the value of db_cache
        db_cache = db_cache_setting.value

        # Log db_cache value
        app.logger.info(f"db_cache returned from Plex: {db_cache}")

        # If db_cache is None, treat it as invalid
        if db_cache is None:
            raise Exception("Unable to retrieve db_cache from Plex settings.")

        # Retrieve user list with only usernames
        user_list = [user.title for user in plex.myPlexAccount().users()]
        app.logger.info(f"User list retrieved from Plex: {user_list}")

        # Retrieve library sections
        music_libraries = [section.title for section in plex.library.sections() if section.type == "artist"]
        movie_libraries = [section.title for section in plex.library.sections() if section.type == "movie"]
        show_libraries = [section.title for section in plex.library.sections() if section.type == "show"]

        app.logger.info(f"Music libraries: {music_libraries}")
        app.logger.info(f"Movie libraries: {movie_libraries}")
        app.logger.info(f"Show libraries: {show_libraries}")

    except Exception as e:
        app.logger.error(f"Error validating Plex server: {str(e)}")
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
        }
    )


def validate_tautulli_server(data):
    tautulli_url = data.get("tautulli_url")
    tautulli_apikey = data.get("tautulli_apikey")

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
            app.logger.info(f"Tautulli connection successful.")
        else:
            app.logger.error(f"Tautulli connection failed.")

    except requests.exceptions.RequestException as e:
        print(f"[DEBUG] Error validating Tautulli connection: {e}")
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
        )

        if response.status_code != 200:
            return jsonify({"valid": False, "error": f"Trakt Error: Invalid trakt pin, client_id, or client_secret."})

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
            return jsonify({"valid": False, "error": f"Account is locked; please contact Trakt Support"})

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
        print(f"[DEBUG] Error validating Trakt connection: {e}")
        flash(f"Invalid Trakt ID, Secret, or PIN: {e}", "error")
        return jsonify({"valid": False, "error": f"Invalid Trakt ID, Secret, or PIN: {e}"})


def validate_gotify_server(data):
    gotify_url = data.get("gotify_url")
    gotify_token = data.get("gotify_token")
    gotify_url = gotify_url.rstrip("#")
    gotify_url = gotify_url.rstrip("/")

    response = requests.get(f"{gotify_url}/version")

    try:
        response_json = response.json()
    except JSONDecodeError as e:
        return jsonify({"valid": False, "error": f"Validation error: {str(e)}"})

    if response.status_code >= 400:
        return jsonify({"valid": False, "error": f"({response.status_code} [{response.reason}]) {response_json['errorDescription']}"})

    json = {"message": "Kometa Quickstart Test Gotify Message", "title": "Kometa Quickstart Gotify Test"}

    response = requests.post(f"{gotify_url}/message", headers={"X-Gotify-Key": gotify_token}, json=json)

    if response.status_code != 200:
        return jsonify({"valid": False, "error": f"({response.status_code} [{response.reason}]) {response_json['errorDescription']}"})

    return jsonify({"valid": True})


def validate_ntfy_server(data):
    ntfy_url = data.get("ntfy_url")
    ntfy_token = data.get("ntfy_token")
    ntfy_topic = data.get("ntfy_topic")

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

        # Step 2: Auto-subscribe the sender to the topic
        sub_headers = headers.copy()
        sub_headers["X-Subscriber"] = "true"  # Tell ntfy.sh to subscribe this client

        sub_response = requests.put(f"{ntfy_url}/{ntfy_topic}", headers=sub_headers)

        if sub_response.status_code == 200:
            return jsonify({"valid": True})
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
        return jsonify({"valid": False, "error": f"MAL Error: No required code in localhost URL."})

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
        return jsonify({"valid": False, "error": f"MAL Error: invalid code."})

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


def validate_anidb_server(data):
    username = data.get("username")
    password = data.get("password")
    client = data.get("client")
    clientver = data.get("clientver")

    safe_password = urllib.parse.quote_plus(password)

    special_chars = safe_password != password

    # AniDB API endpoint
    api_url = "http://api.anidb.net:9001/httpapi"

    try:
        # Make a GET request to AniDB API
        response = requests.get(
            api_url,
            params={
                "request": "hints",
                "user": username,
                "pass": password,
                "protover": "1",
                "client": client,
                "clientver": clientver,
                "type": "1",
            },
        )
        response_text = response.text

        # Check if the response contains 'hints'
        if "hints" in response_text:
            return jsonify({"valid": True})
        elif '<error code="302">' in response_text:
            return jsonify({"valid": False, "error": "Client version missing or invalid"})
        elif '<error code="303">' in response_text:
            return jsonify({"valid": False, "error": "Invalid username or password"})
        elif '<error code="500">' in response_text:
            return jsonify({"valid": False, "error": "You have been banned(likely for 24 hours)"})
        else:
            err_msg = f"Authentication failed {'; special characters in the password give the API trouble' if special_chars else ''}"
            return jsonify({"valid": False, "error": err_msg})

    except requests.exceptions.RequestException as e:
        # Handle request exceptions (e.g., connection error)
        return jsonify({"valid": False, "error": str(e)})


def validate_webhook_server(data):
    webhook_url = data.get("webhook_url")
    message = data.get("message")

    if not webhook_url:
        return jsonify({"error": "Webhook URL is required"}), 400

    message_data = {"content": message}

    response = requests.post(webhook_url, json=message_data)

    if response.status_code == 204:
        return jsonify({"success": "Test message sent successfully! Go and ensure that you see the message on the server side."}), 200
    else:
        return jsonify({"error": f"Failed to send message: {response.status_code}, {response.text}"}), 400


def validate_radarr_server(data):
    radarr_url = data.get("radarr_url")
    radarr_apikey = data.get("radarr_token")

    status_api_url = f"{radarr_url}/api/v3/system/status?apikey={radarr_apikey}"
    root_folder_api_url = f"{radarr_url}/api/v3/rootfolder?apikey={radarr_apikey}"
    quality_profile_api_url = f"{radarr_url}/api/v3/qualityprofile?apikey={radarr_apikey}"

    try:
        # Validate API key by checking system status
        response = requests.get(status_api_url)
        response.raise_for_status()
        status_data = response.json()

        if "version" not in status_data:
            app.logger.error("Radarr connection failed. Invalid response data.")
            return jsonify({"valid": False, "error": "Invalid Radarr URL or Apikey"})

        # Fetch root folders
        response = requests.get(root_folder_api_url)
        response.raise_for_status()
        root_folders = response.json()

        # Fetch quality profiles
        response = requests.get(quality_profile_api_url)
        response.raise_for_status()
        quality_profiles = response.json()

        app.logger.info("Radarr connection successful.")

        return jsonify(
            {
                "valid": True,
                "root_folders": root_folders,
                "quality_profiles": quality_profiles,
            }
        )

    except requests.exceptions.RequestException as e:
        print(f"[DEBUG] Error validating Radarr connection: {e}")
        flash(f"Invalid Radarr URL or API Key: {str(e)}", "error")
        return jsonify({"valid": False, "error": f"Invalid Radarr URL or Apikey: {str(e)}"})


def validate_sonarr_server(data):
    sonarr_url = data.get("sonarr_url")
    sonarr_apikey = data.get("sonarr_token")

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
            app.logger.error("Sonarr connection failed. Invalid response data.")
            return jsonify({"valid": False, "error": "Invalid Sonarr URL or Apikey"})

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

        app.logger.info("Sonarr connection successful.")

        return jsonify(
            {
                "valid": True,
                "root_folders": root_folders,
                "quality_profiles": quality_profiles,
                "language_profiles": language_profiles,
            }
        )

    except requests.exceptions.RequestException as e:
        print(f"[DEBUG] Error validating Sonarr connection: {e}")
        flash(f"Invalid Sonarr URL or API Key: {str(e)}", "error")
        return jsonify({"valid": False, "error": f"Invalid Sonarr URL or Apikey: {str(e)}"})


def validate_omdb_server(data):
    omdb_apikey = data.get("omdb_apikey")

    api_url = f"http://www.omdbapi.com/?apikey={omdb_apikey}&s=test"
    try:
        response = requests.get(api_url)
        data = response.json()
        if data.get("Response") == "True" or data.get("Error") == "Movie not found!":
            return jsonify({"valid": True, "message": "OMDb API key is valid"})
        else:
            return jsonify({"valid": False, "message": data.get("Error", "Invalid API key")})
    except Exception as e:
        print(f"[DEBUG] Error validating OMDb connection: {e}")
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
    movie_response = requests.get(f"https://api.themoviedb.org/3/movie/550?api_key={api_key}")
    if movie_response.status_code == 200:
        return jsonify({"valid": True, "message": "API key is valid!"})
    else:
        return jsonify({"valid": False, "message": "Invalid API key"})


def validate_mdblist_server(data):
    api_key = data.get("mdblist_apikey")

    response = requests.get(f"https://mdblist.com/api/?apikey={api_key}&s=test")
    if response.status_code == 200 and response.json().get("response") is True:
        return jsonify({"valid": True, "message": "API key is valid!"})
    else:
        return jsonify({"valid": False, "message": "Invalid API key"})


def validate_notifiarr_server(data):
    api_key = data.get("notifiarr_apikey")

    response = requests.get(f"https://notifiarr.com/api/v1/user/validate/{api_key}")
    if response.status_code == 200 and response.json().get("result") == "success":
        return jsonify({"valid": True, "message": "API key is valid!"})
    else:
        return jsonify({"valid": False, "message": "Invalid API key"})
