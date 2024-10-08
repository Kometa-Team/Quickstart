from flask import jsonify, flash
from flask import current_app as app
from json import JSONDecodeError
from plexapi.server import PlexServer
import re
import requests
import urllib.parse

import iso639
import iso3166

# TODO: maybe a single entry point here to clean up the imports


def validate_iso3166_1(code):
    try:
        country = iso3166.countries.get(code.upper())
        if country:
            return country.alpha2
        else:
            return None
    except KeyError:
        return None


def validate_iso639_1(code):
    if len(code) == 2 and iso639.languages.get(alpha2=code.lower()):
        return code.lower()
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
        music_libraries = [
            section.title
            for section in plex.library.sections()
            if section.type == "artist"
        ]
        movie_libraries = [
            section.title
            for section in plex.library.sections()
            if section.type == "movie"
        ]
        show_libraries = [
            section.title
            for section in plex.library.sections()
            if section.type == "show"
        ]

        app.logger.info(f"Music libraries: {music_libraries}")
        app.logger.info(f"Movie libraries: {movie_libraries}")
        app.logger.info(f"Show libraries: {show_libraries}")

    except Exception as e:
        app.logger.error(f"Error validating Plex server: {str(e)}")
        flash(f"Invalid Plex URL or Token: {str(e)}", "error")
        return jsonify(
            {"valid": False, "error": f"Invalid Plex URL or Token: {str(e)}"}
        )

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

        isValid = data.get("response", {}).get("result") == "success"
        # Check if the response contains the expected data
        if isValid:
            app.logger.info(f"Tautulli connection successful.")
        else:
            app.logger.error(f"Tautulli connection failed.")

    except requests.exceptions.RequestException as e:
        print(f"Error validating Tautulli connection: {e}")
        flash(f"Invalid Tautulli URL or API Key: {str(e)}", "error")
        return jsonify(
            {"valid": False, "error": f"Invalid Tautulli URL or Apikey: {str(e)}"}
        )

    # return success response
    return jsonify({"valid": isValid})


def validate_trakt_server(data):
    trakt_client_id = data.get("trakt_client_id")
    trakt_client_secret = data.get("trakt_client_secret")
    trakt_pin = data.get("trakt_pin")

    redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
    base_url = "https://api.trakt.tv"

    error = ""
    isValid = False
    trakt_authorization_access_token = ""
    trakt_authorization_token_type = ""
    trakt_authorization_expires_in = ""
    trakt_authorization_refresh_token = ""
    trakt_authorization_scope = ""
    trakt_authorization_created_at = ""

    json = {
        "code": trakt_pin,
        "client_id": trakt_client_id,
        "client_secret": trakt_client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        response = requests.post(
            f"{base_url}/oauth/token",
            json=json,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code != 200:
            return jsonify(
                {
                    "valid": False,
                    "error": f"Trakt Error: Invalid trakt pin, client_id, or client_secret.",
                }
            )
        else:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {response.json()['access_token']}",
                "trakt-api-version": "2",
                "trakt-api-key": trakt_client_id,
            }

            validation_response = requests.get(
                f"{base_url}/users/settings", headers=headers
            )

            if validation_response.status_code == 423:
                return jsonify(
                    {
                        "valid": False,
                        "error": f"Account is locked; please contact Trakt Support",
                    }
                )
            else:
                trakt_authorization_access_token = response.json()["access_token"]
                trakt_authorization_token_type = response.json()["token_type"]
                trakt_authorization_expires_in = response.json()["expires_in"]
                trakt_authorization_refresh_token = response.json()["refresh_token"]
                trakt_authorization_scope = response.json()["scope"]
                trakt_authorization_created_at = response.json()["created_at"]
                isValid = True

    except requests.exceptions.RequestException as e:
        print(f"Error validating Trakt connection: {e}")
        flash(f"Invalid Trakt ID, Secret, or PIN: {str(e)}", "error")
        return jsonify(
            {"valid": False, "error": f"Invalid Trakt ID, Secret, or PIN: {str(e)}"}
        )

    # return success response
    return jsonify(
        {
            "valid": isValid,
            "error": error,
            "trakt_authorization_access_token": trakt_authorization_access_token,
            "trakt_authorization_token_type": trakt_authorization_token_type,
            "trakt_authorization_expires_in": trakt_authorization_expires_in,
            "trakt_authorization_refresh_token": trakt_authorization_refresh_token,
            "trakt_authorization_scope": trakt_authorization_scope,
            "trakt_authorization_created_at": trakt_authorization_created_at,
        }
    )


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
        return jsonify(
            {
                "valid": False,
                "error": f"({response.status_code} [{response.reason}]) {response_json['errorDescription']}",
            }
        )

    json = {"message": "Kometa Test Message", "title": "Kometa Test"}

    response = requests.post(
        f"{gotify_url}/message", headers={"X-Gotify-Key": gotify_token}, json=json
    )

    if response.status_code != 200:
        return jsonify(
            {
                "valid": False,
                "error": f"({response.status_code} [{response.reason}]) {response_json['errorDescription']}",
            }
        )

    return jsonify({"valid": True})


def validate_mal_server(data):
    mal_client_id = data.get("mal_client_id")
    mal_client_secret = data.get("mal_client_secret")
    mal_code_verifier = data.get("mal_code_verifier")
    mal_localhost_url = data.get("mal_localhost_url")

    match = re.search("code=([^&]+)", str(mal_localhost_url))

    if not match:
        return jsonify(
            {"valid": False, "error": f"MAL Error: No required code in localhost URL."}
        )
    else:
        code = match.group(1)

        data = {
            "client_id": mal_client_id,
            "client_secret": mal_client_secret,
            "code": code,
            "code_verifier": mal_code_verifier,
            "grant_type": "authorization_code",
        }

        session = requests.Session()
        new_authorization = session.post(
            "https://myanimelist.net/v1/oauth2/token", data=data
        ).json()

        if "error" in new_authorization:
            return jsonify({"valid": False, "error": f"MAL Error: invalid code."})
        else:
            mal_authorization_access_token = new_authorization["access_token"]
            mal_authorization_token_type = new_authorization["token_type"]
            mal_authorization_expires_in = new_authorization["expires_in"]
            mal_authorization_refresh_token = new_authorization["refresh_token"]
            isValid = True

    # return success response
    return jsonify(
        {
            "valid": isValid,
            "mal_authorization_access_token": mal_authorization_access_token,
            "mal_authorization_token_type": mal_authorization_token_type,
            "mal_authorization_expires_in": mal_authorization_expires_in,
            "mal_authorization_refresh_token": mal_authorization_refresh_token,
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

    # Prepare the request parameters
    params = {
        "request": "hints",
        "user": username,
        "pass": password,
        "protover": "1",
        "client": client,
        "clientver": clientver,
        "type": "1",
    }

    try:
        # Construct the full URL with query parameters
        full_url = f"{api_url}?request=hints&user={username}&pass={safe_password}&protover=1&client={client}&clientver={clientver}&type=1"

        # Make a GET request to AniDB API
        response = requests.get(api_url, params=params)
        response_text = response.text

        # Check if the response contains 'hints'
        if "hints" in response_text:
            return jsonify({"valid": True})
        elif '<error code="302">' in response_text:
            return jsonify(
                {"valid": False, "error": "Client version missing or invalid"}
            )
        elif '<error code="303">' in response_text:
            return jsonify({"valid": False, "error": "Invalid username or password"})
        elif '<error code="500">' in response_text:
            return jsonify(
                {"valid": False, "error": "You have been banned(likely for 24 hours)"}
            )
        else:
            if special_chars:
                return jsonify(
                    {
                        "valid": False,
                        "error": "Authentication failed; special characters in the password give the API trouble",
                    }
                )
            else:
                return jsonify({"valid": False, "error": "Authentication failed"})

    except requests.exceptions.RequestException as e:
        # Handle request exceptions (e.g., connection error)
        return jsonify({"valid": False, "error": str(e)})

    return jsonify({"valid": False, "error": "Unknown error"})


def validate_webhook_server(data):
    webhook_url = data.get("webhook_url")
    message = data.get("message")

    if not webhook_url:
        return jsonify({"error": "Webhook URL is required"}), 400

    message_data = {"content": message}

    response = requests.post(webhook_url, json=message_data)

    if response.status_code == 204:
        return (
            jsonify(
                {
                    "success": "Test message sent successfully! Go and ensure that you see the message on the server side."
                }
            ),
            200,
        )
    else:
        return (
            jsonify(
                {
                    "error": f"Failed to send message: {response.status_code}, {response.text}"
                }
            ),
            400,
        )


def validate_radarr_server(data):
    radarr_url = data.get("radarr_url")
    radarr_apikey = data.get("radarr_token")

    status_api_url = f"{radarr_url}/api/v3/system/status?apikey={radarr_apikey}"
    root_folder_api_url = f"{radarr_url}/api/v3/rootfolder?apikey={radarr_apikey}"
    quality_profile_api_url = (
        f"{radarr_url}/api/v3/qualityprofile?apikey={radarr_apikey}"
    )

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
        print(f"Error validating Radarr connection: {e}")
        flash(f"Invalid Radarr URL or API Key: {str(e)}", "error")
        return jsonify(
            {"valid": False, "error": f"Invalid Radarr URL or Apikey: {str(e)}"}
        )


def validate_sonarr_server(data):
    sonarr_url = data.get("sonarr_url")
    sonarr_apikey = data.get("sonarr_token")

    status_api_url = f"{sonarr_url}/api/v3/system/status?apikey={sonarr_apikey}"
    root_folder_api_url = f"{sonarr_url}/api/v3/rootfolder?apikey={sonarr_apikey}"
    quality_profile_api_url = (
        f"{sonarr_url}/api/v3/qualityprofile?apikey={sonarr_apikey}"
    )
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
        print(f"Error validating Sonarr connection: {e}")
        flash(f"Invalid Sonarr URL or API Key: {str(e)}", "error")
        return jsonify(
            {"valid": False, "error": f"Invalid Sonarr URL or Apikey: {str(e)}"}
        )


def validate_omdb_server(data):
    omdb_apikey = data.get("omdb_apikey")

    api_url = f"http://www.omdbapi.com/?apikey={omdb_apikey}&s=test"
    try:
        response = requests.get(api_url)
        data = response.json()
        if data.get("Response") == "True" or data.get("Error") == "Movie not found!":
            return jsonify({"valid": True, "message": "OMDb API key is valid"})
        else:
            return jsonify(
                {"valid": False, "message": data.get("Error", "Invalid API key")}
            )
    except Exception as e:
        print(f"Error validating OMDb connection: {e}")
        flash(f"Invalid OMDb API Key: {str(e)}", "error")
        return jsonify({"valid": False, "message": str(e)})


def validate_github_server(data):
    github_token = data.get("github_token")

    api_url = "https://api.github.com/user"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    try:
        response = requests.get(api_url, headers=headers)
        if response.status_code == 200:
            user_data = response.json()
            return jsonify(
                {
                    "valid": True,
                    "message": f"GitHub token is valid. User: {user_data.get('login')}",
                }
            )
        else:
            return jsonify({"valid": False, "message": "Invalid GitHub token"}), 400
    except Exception as e:
        return jsonify({"valid": False, "message": str(e)})


def validate_tmdb_server(data):
    api_key = data.get("tmdb_apikey")

    # Validate the API key
    movie_response = requests.get(
        f"https://api.themoviedb.org/3/movie/550?api_key={api_key}"
    )
    if movie_response.status_code == 200:
        return jsonify({"valid": True, "message": "API key is valid!"})
    else:
        return jsonify({"valid": False, "message": "Invalid API key"})


def validate_mdblist_server(data):
    api_key = data.get("mdblist_apikey")

    response = requests.get(f"https://mdblist.com/api/?apikey={api_key}&s=test")
    if response.status_code == 200 and response.json().get("response") == True:
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
