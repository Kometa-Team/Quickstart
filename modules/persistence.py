from flask import session
import secrets
from ruamel.yaml import YAML

from .helpers import build_config_dict, get_template_list

def extract_names(raw_source):
    source = raw_source
    
    # get source from referrer
    if raw_source.startswith('http'):
        source = raw_source.split("/")[-1]
        source = source.split("?")[0]

    source_name = source.split('-')[-1]
    # source will be `010-plex`
    # source_name will be `plex`

    return source, source_name    

def save_settings(raw_source, form_data):
    # get source from referrer
    source, source_name = extract_names(raw_source)
    # source will be `010-plex`
    # source_name will be `plex`

    if len(source) > 0:
        data = build_config_dict(source_name, form_data)

        # we know that it is valid at this point
        data['valid'] = True
    
        # save under `010-plex`
        session[source] = data

        print(f"data saved for {source}: {data}")


def retrieve_settings(target):
    # target will be `010-plex`

    # get source from referrer
    source, source_name = extract_names(target)
    # source will be `010-plex`
    # source_name will be `plex`

    data = session.get(source)

    if not data:
        data = get_dummy_data(source_name)

    try:
        if data['validated']:
            data['valid'] = True
    except:
        data = data

    return data

def get_dummy_data(target):
    
    yaml = YAML(typ='safe', pure=True)
    with open('json-schema/prototype_config.yml', 'r') as file:
        base_config = yaml.load(file)

    data = {}
    # dummy data is not valid
    data['valid'] = False
    try:
        data[target] = base_config[target]
    except:
        data[target] = {}

    data[target]['valid'] = False


    if target == 'mal':
        data['code_verifier'] = secrets.token_urlsafe(100)[:128]
    
    return data

def check_minimum_settings():
    plex_settings = retrieve_settings('010-plex')
    tmdb_settings = retrieve_settings('020-tmdb')
    
    try:
        plex_valid = plex_settings['valid']
        tmdb_valid = tmdb_settings['valid']
    except:
        plex_valid = False
        tmdb_valid = False
    
    return plex_valid, tmdb_valid

def flush_session_storage():
    # this needs to use the dynamic template list,
    # but that needs to be changed to not use the app object
    session['000-base'] = None
    session['010-plex'] = None
    session['020-tmdb'] = None
    session['030-tautulli'] = None
    session['040-github'] = None
    session['050-omdb'] = None
    session['060-mdblist'] = None
    session['070-notifiarr'] = None
    session['080-gotify'] = None
    session['090-anidb'] = None
    session['100-radarr'] = None
    session['110-sonarr'] = None
    session['120-trakt'] = None
    session['130-mal'] = None
    session['140-webhooks'] = None
    session['150-settings'] = None
    session['666-test'] = None
    session['999-danger'] = None
    session['999-final'] = None
