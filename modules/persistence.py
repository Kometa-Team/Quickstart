from flask import session
import os
import secrets
from ruamel.yaml import YAML
from flask import current_app as app

from .helpers import build_config_dict, get_template_list, get_bits

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
            notifiarr_available = notifiarr_data['valid']
        if "gotify" in stem:
            gotify_data = retrieve_settings(stem)
            gotify_available = gotify_data['valid']

    return notifiarr_available, gotify_available