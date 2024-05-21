
from flask import jsonify, flash
from flask import current_app as app
from plexapi.server import PlexServer
import requests

import iso639
import iso3166

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
    plex_url = data.get('plex_url')
    plex_token = data.get('plex_token')

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

    except Exception as e:
        app.logger.error(f'Error validating Plex server: {str(e)}')
        flash(f'Invalid Plex URL or Token: {str(e)}', 'error')
        return jsonify({'valid': False, 'error': f'Invalid Plex URL or Token: {str(e)}'})

    # If PlexServer instance is successfully created and db_cache is retrieved, return success response
    return jsonify({
        'valid': True,
        'db_cache': db_cache  # Send back the integer value of db_cache
    })


def validate_tautulli_server(data):
    tautulli_url = data.get('tautulli_url')
    tautulli_token = data.get('tautulli_token')

    api_url = f"{tautulli_url}/api/v2"
    params = {
        'apikey': tautulli_token,
        'cmd': 'get_tautulli_info'
    }

    try:
        response = requests.get(api_url, params=params)

        # Raise an exception for HTTP errors
        response.raise_for_status()

        data = response.json()

        isValid = data.get('response', {}).get('result') == 'success'
        # Check if the response contains the expected data
        if isValid:
            app.logger.info(f"Tautulli connection successful.")
        else:
            app.logger.error(f"Tautulli connection failed.")
            
    except requests.exceptions.RequestException as e:
        print(f"Error validating Tautulli connection: {e}")
        flash(f'Invalid Tautulli URL or API Key: {str(e)}', 'error')
        return jsonify({'valid': False, 'error': f'Invalid Tautulli URL or Token: {str(e)}'})

    # return success response
    return jsonify({
        'valid': isValid
    })


def validate_trakt_server(data):
    trakt_client_id = data.get('trakt_client_id')
    trakt_client_secret = data.get('trakt_client_secret')
    trakt_pin = data.get('trakt_pin')

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
        "grant_type": "authorization_code"
    }
    try:
        response = requests.post(f"{base_url}/oauth/token", json=json, headers={"Content-Type": "application/json"})

        if response.status_code != 200:
            error = "Trakt Error: Invalid trakt pin, client_id, or client_secret."
        else:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {response.json()['access_token']}",
                "trakt-api-version": "2",
                "trakt-api-key": trakt_client_id,
            }
        
            validation_response = requests.get(f"{base_url}/users/settings", headers=headers)


            if validation_response.status_code == 423:
                error = "Account is locked; please contact Trakt Support"
            else:
                trakt_authorization_access_token = response.json()['access_token']
                trakt_authorization_token_type = response.json()['token_type']
                trakt_authorization_expires_in = response.json()['expires_in']
                trakt_authorization_refresh_token = response.json()['refresh_token']
                trakt_authorization_scope = response.json()['scope']
                trakt_authorization_created_at = response.json()['created_at']
                isValid = True
            
    except requests.exceptions.RequestException as e:
        print(f"Error validating Trakt connection: {e}")
        flash(f'Invalid Trakt ID, Secret, or PIN: {str(e)}', 'error')
        return jsonify({'valid': False, 'error': f'Invalid Trakt ID, Secret, or PIN: {str(e)}'})

    # return success response
    return jsonify({
        'valid': isValid,
        'error': error,
        'trakt_authorization_access_token': trakt_authorization_access_token,
        'trakt_authorization_token_type': trakt_authorization_token_type,
        'trakt_authorization_expires_in': trakt_authorization_expires_in,
        'trakt_authorization_refresh_token': trakt_authorization_refresh_token,
        'trakt_authorization_scope': trakt_authorization_scope,
        'trakt_authorization_created_at': trakt_authorization_created_at
    })