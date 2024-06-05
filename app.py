from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, session, send_file
from flask_session import Session
from cachelib.file import FileSystemCache

import jsonschema
import requests
import io
from ruamel.yaml import YAML
import os
from dotenv import load_dotenv
from pathlib import Path
from plexapi.server import PlexServer
import pyfiglet
import secrets

from modules.validations import validate_iso3166_1, validate_iso639_1, validate_plex_server, validate_tautulli_server, validate_trakt_server, validate_mal_server, validate_anidb_server, validate_gotify_server
from modules.output import build_config
from modules.helpers import get_template_list, get_bits, get_menu_list
from modules.persistence import save_settings, retrieve_settings, check_minimum_settings, flush_session_storage, notification_systems_available
from modules.iso_639_1 import iso_639_1_languages  # Importing the languages list
from modules.iso_639_2 import iso_639_2_languages  # Importing the languages list
from modules.iso_3166_1 import iso_3166_1_regions  # Importing the regions list

# Load JSON Schema
yaml = YAML(typ='safe', pure=True)

# URL to the JSON schema
url = 'https://raw.githubusercontent.com/Kometa-Team/Kometa/nightly/json-schema/config-schema.json'

try:
    # Fetch the schema
    response = requests.get(url)
    response.raise_for_status()  # Ensure we notice bad responses

    # Load the schema
    schema = yaml.load(response.text)
except requests.RequestException as e:
    print(f"Error fetching the JSON schema: {e}")
    schema = None  # or handle the error appropriately

load_dotenv()


app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

# SESSION_TYPE = 'cachelib'
# SESSION_SERIALIZATION_FORMAT = 'json'
# SESSION_CACHELIB = FileSystemCache(threshold=500, cache_dir="sessions"),
# app.config.from_object(__name__)
# Session(app)

# Create the Flask application
# app = Flask(__name__)

# Details on the Secret Key: https://flask.palletsprojects.com/en/3.0.x/config/#SECRET_KEY
# NOTE: The secret key is used to cryptographically-sign the cookies used for storing
#       the session identifier.
# app.secret_key = os.getenv('SECRET_KEY', default='BAD_SECRET_KEY')

# Configure Redis for storing the session data on the server-side
app.config['SESSION_TYPE'] = 'cachelib'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = False
# app.config['SESSION_REDIS'] = redis.from_url('redis://127.0.0.1:6379')

# Create and initialize the Flask-Session object AFTER `app` has been configured
server_session = Session(app)

@app.route('/')
def start():
    return render_template('001-start.html')


@app.route('/clear_session', methods=['POST'])
def clear_session():
    flush_session_storage()
    flash('Session storage cleared successfully.', 'success')
    return redirect(url_for('start'))


@app.route('/step/<name>', methods=['GET', 'POST'])
def step(name):

    if request.method == 'POST':
        save_settings(request.referrer, request.form)
        header_style = request.form.get('header_style', 'ascii')
    else:
        header_style = 'ascii'  # Default to ASCII art

    file_list = get_menu_list()

    template_list = get_template_list()

    total_steps = len(template_list)

    stem, num, b = get_bits(name)

    current_index = -1
    item = None

    try:
        current_index = list(template_list).index(num)
        item = template_list[num]
    except:
        # not in there
        return redirect(url_for('start'))
    
    progress = round((current_index + 1) / total_steps * 100)
    
    title = item['name']
    next_page = item['next']
    prev_page = item['prev']
        
    data = retrieve_settings(name)

    print(f"data retrieved for {name}: {data}")

    plex_valid, tmdb_valid = check_minimum_settings()
    
    # notifiarr_available, gotify_available = notification_systems_available()
    notifiarr_available = False
    gotify_available = False
    
    # This should not be based on name; maybe next being empty
    # Why does the error condition need its own page?
    if name == '900-final':
        validated, config_data, yaml_content = build_config(header_style)

        try:
            jsonschema.validate(instance=config_data, schema=schema)
        except jsonschema.exceptions.ValidationError as e:
            flash(f'Validation error: {e.message}', 'danger')
            return render_template('900-final.html', title=title, data=data, yaml_content=yaml_content, validation_error=e, template_list=file_list, next_page=next_page, prev_page=prev_page, curr_page=title, progress=progress, plex_valid=plex_valid, tmdb_valid=tmdb_valid, notifiarr_available=notifiarr_available, gotify_available=gotify_available, header_style=header_style)

        return render_template('900-final.html', title=title, data=data, yaml_content=yaml_content, template_list=file_list, next_page=next_page, prev_page=prev_page, curr_page=title, progress=progress, plex_valid=plex_valid, tmdb_valid=tmdb_valid, notifiarr_available=notifiarr_available, gotify_available=gotify_available, header_style=header_style)
    else:
        # Ensure 'anidb', 'settings', 'webhooks' exist in data
        if 'anidb' not in data:
            data['anidb'] = {}
        if 'webhooks' not in data:
            data['webhooks'] = {}
        if 'settings' not in data:
            data['settings'] = {}
            
        # Default values if they don't exist
        if 'language' not in data['anidb']:
            data['anidb']['language'] = 'en'  # Default to English
        if 'error' not in data['webhooks']:
            data['webhooks']['error'] = ''
        if 'run_start' not in data['webhooks']:
            data['webhooks']['run_start'] = ''
        if 'run_end' not in data['webhooks']:
            data['webhooks']['run_end'] = ''
        if 'changes' not in data['webhooks']:
            data['webhooks']['changes'] = ''
        if 'version' not in data['webhooks']:
            data['webhooks']['version'] = ''
        if 'delete' not in data['webhooks']:
            data['webhooks']['delete'] = ''
        if 'run_order' not in data['settings']:
            data['settings']['run_order'] = ['operations', 'metadata', 'collections', 'overlays']
        if 'overlay_artwork_filetype' not in data['settings']:
            data['settings']['overlay_artwork_filetype'] = 'jpg'
        if 'sync_mode' not in data['settings']:
            data['settings']['sync_mode'] = 'append'
        if 'default_collection_order' not in data['settings']:
            data['settings']['default_collection_order'] = ''
            
        # Retrieve the saved info
        run_order_list = data.get('settings', {}).get('run_order', ['operations', 'metadata', 'collections', 'overlays'])
        run_order = " ".join(run_order_list)        
        overlay_artwork_filetype = data['settings'].get('overlay_artwork_filetype', 'jpg')
        sync_mode = data['settings'].get('sync_mode', 'append')
        default_collection_order = data['settings'].get('default_collection_order', '')
        wh_error = data['webhooks'].get('error', '')
        wh_run_start = data['webhooks'].get('run_start', '')
        wh_run_end = data['webhooks'].get('run_end', '')
        wh_changes = data['webhooks'].get('changes', '')
        wh_version = data['webhooks'].get('version', '')
        wh_delete = data['webhooks'].get('delete', '')

        return render_template(name + '.html', title=title, data=data, template_list=file_list, next_page=next_page, prev_page=prev_page, curr_page=title, progress=progress, plex_valid=plex_valid, tmdb_valid=tmdb_valid, notifiarr_available=notifiarr_available, gotify_available=gotify_available, iso_639_1_languages=iso_639_1_languages, iso_639_2_languages=iso_639_2_languages, iso_3166_1_regions=iso_3166_1_regions, run_order=run_order, overlay_artwork_filetype=overlay_artwork_filetype, sync_mode=sync_mode, default_collection_order=default_collection_order, wh_error=wh_error, wh_run_start=wh_run_start, wh_run_end=wh_run_end, wh_changes=wh_changes, wh_version=wh_version, wh_delete=wh_delete)

@app.route('/download')
def download():
    yaml_content = session.get('yaml_content', '')
    if yaml_content:
        return send_file(
            io.BytesIO(yaml_content.encode('utf-8')),
            mimetype='text/yaml',
            as_attachment=True,
            download_name='config.yml'
        )
    flash('No configuration to download', 'danger')
    return redirect(url_for('final_step'))


@app.route('/validate_gotify', methods=['POST'])
def validate_gotify():
    data = request.json
    return validate_gotify_server(data)


@app.route('/validate_plex', methods=['POST'])
def validate_plex():
    data = request.json
    return validate_plex_server(data)


@app.route('/validate_tautulli', methods=['POST'])
def validate_tautulli():
    data = request.json
    return validate_tautulli_server(data)


@app.route('/validate_trakt', methods=['POST'])
def validate_trakt():
    data = request.json
    return validate_trakt_server(data)

@app.route('/validate_mal', methods=['POST'])
def validate_mal():
    data = request.json
    return validate_mal_server(data)

@app.route('/validate_anidb', methods=['POST'])
def validate_anidb():
    data = request.json
    return validate_anidb_server(data)


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
