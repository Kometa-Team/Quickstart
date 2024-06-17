from flask import session
import os
import secrets
from ruamel.yaml import YAML
from flask import current_app as app

from .helpers import build_config_dict, get_template_list, get_bits
from .iso_639_1 import iso_639_1_languages  # Importing the languages list
from .iso_639_2 import iso_639_2_languages  # Importing the languages list
from .iso_3166_1 import iso_3166_1_regions  # Importing the regions list

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

def clean_form_data (form_data):
    clean_data = {}

    for key in form_data:
        value = form_data[key]
        lc_value = value.lower() if isinstance(value, str) else None
        if len(value) == 0 or lc_value == 'none':
            clean_data[key] = None
        elif lc_value == 'true' or lc_value == 'on':
            clean_data[key] = True
        elif lc_value == 'false':
            clean_data[key] = False
        else:
            clean_data[key] = value

    return clean_data

def save_settings(raw_source, form_data):
    # get source from referrer
    source, source_name = extract_names(raw_source)
    # source will be `010-plex`
    # source_name will be `plex`
    
    clean_data = clean_form_data(form_data)

    if len(source) > 0:
        data = build_config_dict(source_name, clean_data)
        
        base_data = get_dummy_data(source_name)

        # we know that it is valid at this point
        data['valid'] = data != base_data
    
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

    if target == '020-tmdb':
        data['iso_639_1_languages'] = iso_639_1_languages
        data['iso_3166_1_regions'] = iso_3166_1_regions

    if target == '090-anidb':
        data['iso_639_1_languages'] = iso_639_1_languages

    if target == '150-settings':
        data['iso_639_2_languages'] = iso_639_2_languages

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
    template_list = get_template_list()
    for name in template_list:
        item = template_list[name]
        session[item['stem']] = None

def notification_systems_available():
    notifiarr_available = False
    gotify_available = False
    
    templates_dir = os.path.join(app.root_path, 'templates')
    file_list = sorted(os.listdir(templates_dir))

    for file in file_list:
        stem, this_num, b = get_bits(file)
        
        if "notifiarr" in stem:
            notifiarr_data = retrieve_settings(stem)
            # print(f"Checking Notifiarr settings: {notifiarr_data}")  # Debug print
            try:
                notifiarr_available = bool(notifiarr_data['valid'])
                # print(f"Notifiarr available: {notifiarr_available}")  # Debug print
            except Exception as e:
                # print(f"Error checking Notifiarr availability: {e}")  # Debug print
                notifiarr_available = False
        
        if "gotify" in stem:
            gotify_data = retrieve_settings(stem)
            # print(f"Checking Gotify settings: {gotify_data}")  # Debug print
            try:
                gotify_available = bool(gotify_data['valid'])
                # print(f"Gotify available: {gotify_available}")  # Debug print
            except Exception as e:
                # print(f"Error checking Gotify availability: {e}")  # Debug print
                gotify_available = False

    return notifiarr_available, gotify_available